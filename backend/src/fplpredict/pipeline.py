"""End-to-end: processed data -> features -> expected points (backtest and future predictions)."""
import numpy as np
import pandas as pd

from .news import row_availability
from .odds import load_odds
from .baseline import events_to_points, expected_events, position_priors
from .config import PROCESSED_DIR
from .features import FeatureBuilder
from .ml import MAX_H, make_models
from .scoring import actual_points, load_scoring

HORIZON = 5


def _read(name: str) -> pd.DataFrame:
    return pd.read_parquet(PROCESSED_DIR / f"{name}.parquet")


def upcoming_rows(season: str, horizon: int = HORIZON) -> pd.DataFrame:
    """One row per (non-removed player, unplayed fixture) in the next `horizon` gameweeks."""
    players, teams, fx = _read("current_players"), _read("current_teams"), _read("current_fixtures")
    fx = fx[fx["event"].notna() & ~fx["started"]]
    events = sorted(fx["event"].unique())[:horizon]
    fx = fx[fx["event"].isin(events)]

    name = dict(zip(teams["id"], teams["name"]))  # already canonical (see current.py)
    sides = pd.concat([
        pd.DataFrame({"fixture": fx["id"], "round": fx["event"], "kickoff_time": fx["kickoff_time"],
                      "team_id": fx["team_h"], "opponent": fx["team_a"].map(name), "was_home": True}),
        pd.DataFrame({"fixture": fx["id"], "round": fx["event"], "kickoff_time": fx["kickoff_time"],
                      "team_id": fx["team_a"], "opponent": fx["team_h"].map(name), "was_home": False}),
    ])
    pl = players[~players["removed"]].rename(columns={"id": "element", "team": "team_id"})
    pl["position"] = pl["element_type"].map({1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"})
    pl["name"] = pl["web_name"]
    pl["team"] = pl["team_id"].map(name)
    rows = sides.merge(pl, on="team_id")
    rows["season"] = season
    rows = attach_roles(rows)
    rows["value"] = rows["now_cost"]
    rows["selected"] = rows["selected_by_percent"].astype(float)  # current ownership (cold-start signal)
    rows["kickoff_time"] = pd.to_datetime(rows["kickoff_time"], utc=True)
    rows["gw_index"] = rows["round"].map({e: i for i, e in enumerate(events)})
    rows = rows.sort_values(["kickoff_time", "fixture"])
    rows["h"] = rows.groupby("code").cumcount() + 1  # which upcoming match this is for the player
    return rows


def attach_roles(d: pd.DataFrame) -> pd.DataFrame:
    """Add set-piece role strengths (pen / corner / fk) by (season, code); 0 when no role."""
    roles = _read("set_pieces").drop_duplicates(["season", "code"])
    d = d.merge(roles, on=["season", "code"], how="left")
    d[["pen", "corner", "fk"]] = d[["pen", "corner", "fk"]].fillna(0.0)
    return d


def load_played() -> pd.DataFrame:
    d = _read("player_gw")
    return attach_roles(d[d["team_score"].notna()])  # drop rows of fixtures that haven't finished


ODDS_H1_KEEP = 0.7   # share of next-match fixtures whose odds are already published


def visible_odds(f: pd.DataFrame, h: int, seed: int = 0) -> pd.DataFrame:
    """Mimic production: odds exist only a few days ahead, so hide them for h>1 and for some h=1."""
    f = f.copy()
    if h == 1:
        fx = f["season"] + "_" + f["fixture"].astype(str)
        keep = pd.Series(np.random.default_rng(seed).random(fx.nunique()) < ODDS_H1_KEEP,
                         index=fx.unique())
        hide = ~fx.map(keep).to_numpy(bool)
    else:
        hide = np.ones(len(f), bool)
    f.loc[hide, ["odds_gf", "odds_ga"]] = np.nan
    return f


def use_odds(f: pd.DataFrame, weight: float = 0.7) -> pd.DataFrame:
    """Where odds are known, blend the market's expected goals into the fixture estimate."""
    f = f.copy()
    for col, odds in (("exp_gf", "odds_gf"), ("exp_ga", "odds_ga")):
        f[col] = np.where(f[odds].notna(), weight * f[odds] + (1 - weight) * f[col], f[col])
    return f


def eligible(f: pd.DataFrame, first_season: str) -> pd.Series:
    """Rows with history, plus genuinely new players (no earlier matches in a later season).

    Rows without history in the very first season are excluded: those are established players
    whose past simply is not in our data, not newcomers.
    """
    return (f["n"] > 0) | (f["season"] > first_season)


def train_frame(fb: FeatureBuilder, before: str | None = None, include_new: bool = True) -> pd.DataFrame:
    """Stacked horizon-h feature frames of played rows for model training."""
    first = fb.base["season"].min()
    parts = []
    for h in range(1, MAX_H + 1):
        f = use_odds(visible_odds(fb.at(h), h))
        m = f["minutes"].notna() & (eligible(f, first) if include_new else f["n"] > 0)
        if before is not None:
            m &= f["season"] < before
        parts.append(f[m])
    return pd.concat(parts, ignore_index=True)


def _blend(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Average the model outputs (event expectations and points)."""
    out = frames[0].copy()
    cols = [c for c in out.columns if (c.startswith("x") and c != "xpts_naive")
            or c in ("p_play", "p60", "m_play", "p_cs_team")]
    out[cols] = sum(fr[cols] for fr in frames) / len(frames)
    return out


ALGOS = {"lgbm": ["lgbm"], "rf": ["rf"], "ens": ["lgbm", "rf"],
         "lgbm-pos": ["lgbm-pos"], "rf-pos": ["rf-pos"], "ens-pos": ["lgbm-pos", "rf-pos"], "baseline": []}


def predict(horizon: int = HORIZON, algo: str = "ens") -> pd.DataFrame:
    sc = load_scoring()
    played = load_played()
    season = sorted(played["season"].unique())[-1]
    up = upcoming_rows(season, horizon)
    cols = [c for c in up.columns if c in played.columns]
    fb = FeatureBuilder(pd.concat([played, up[cols]], ignore_index=True), load_odds(season))
    priors = position_priors(fb.at(1))

    train = train_frame(fb) if ALGOS[algo] else None
    models = [make_models(a).fit(train) for a in ALGOS[algo]]
    extra = ["season", "fixture", "code", "element", "gw_index", "status", "now_cost",
             "chance_of_playing_next_round", "selected_by_percent", "news", "news_added", "cost_change_start"]
    parts = []
    for h in sorted(up["h"].unique()):
        f = use_odds(fb.at(min(h, MAX_H)))  # real (not masked) odds: only known ones are non-NaN
        f = f.merge(up[up["h"] == h][extra], on=["season", "fixture", "code"])
        avail = row_availability(f.assign(h=h))  # h = how many matches ahead (uncapped)
        f["h"] = min(h, MAX_H)
        ev = expected_events(f, priors, avail)
        outs = [events_to_points(m.apply(ev), sc) for m in models] or [events_to_points(ev, sc)]
        parts.append(_blend(outs))
    return pd.concat(parts, ignore_index=True)


def backtest(test_season: str, algos: tuple[str, ...] = ("lgbm", "rf"),
             horizons: tuple[int, ...] = (1, 3, 5), include_new: bool = True) -> dict[int, pd.DataFrame]:
    """Train on seasons before `test_season`; compare baseline and ML on every row of it."""
    sc = load_scoring()
    played = load_played()
    fb = FeatureBuilder(played, load_odds(sorted(played["season"].unique())[-1]))
    priors = position_priors(fb.at(1))
    train = train_frame(fb, before=test_season, include_new=include_new)
    models = {a: make_models(a).fit(train) for a in algos}
    results = {}
    for h in horizons:
        f = fb.at(h)
        if h > 1:
            f = visible_odds(f, h)  # distant fixtures have no published odds yet
        f = use_odds(f)
        f = f[(f["season"] == test_season) & eligible(f, fb.base["season"].min())]
        ev = expected_events(f, priors)
        base = events_to_points(ev, sc)
        res = base[["season", "round", "code", "name", "position", "ew_minutes"]].copy()
        res["actual"] = actual_points(f, sc)
        res["naive"], res["baseline"] = base["xpts_naive"], base["xpts"]
        outs = {a: events_to_points(m.apply(ev), sc) for a, m in models.items()}
        for a, o in outs.items():
            res[a] = o["xpts"]
        if len(outs) > 1:
            res["ens"] = _blend(list(outs.values()))["xpts"]
        res["fpl_xp"] = f["fpl_xp"]
        res["n"] = f["n"]
        results[h] = res
    return results


def summarize(results: dict[int, pd.DataFrame]) -> pd.DataFrame:
    rows = {}
    for h, res in results.items():
        models = [c for c in res.columns if c not in
                  ("season", "round", "code", "name", "position", "ew_minutes", "actual", "fpl_xp", "n")]
        if h == 1 and res["fpl_xp"].notna().any():
            res = res[res["fpl_xp"].notna()]  # same rows for every model incl. FPL's own xP
            models.append("fpl_xp")
        groups = [("all", res), ("regulars", res[res["ew_minutes"] >= 45]),
                  ("new (n=0)", res[res["n"] == 0]), ("n>0", res[res["n"] > 0])]
        for label, g in groups:
            row = {"rows": len(g)}
            for m in models:
                err = g[m] - g["actual"]
                row[f"mae_{m}"], row[f"corr_{m}"] = err.abs().mean(), g[m].corr(g["actual"])
            rows[(f"h={h}", label)] = row
    return pd.DataFrame(rows).T
