"""End-to-end: processed data -> features -> expected points (backtest and future predictions)."""
import numpy as np
import pandas as pd

from .baseline import expected_points, position_priors
from .config import PROCESSED_DIR
from .features import build_features
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

    name = dict(zip(teams["id"], teams["name"]))
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
    rows["kickoff_time"] = pd.to_datetime(rows["kickoff_time"], utc=True)
    rows["gw_index"] = rows["round"].map({e: i for i, e in enumerate(events)})
    return rows


def availability(rows: pd.DataFrame) -> pd.Series:
    """Heuristic from the API's fitness flag: GW1 uses it directly, later GWs regress to 1."""
    chance = rows["chance_of_playing_next_round"].astype(float).div(100).fillna(1.0)
    later = (chance + 1) / 2
    av = chance.where(rows["gw_index"] == 0, later)
    return av.where(rows["status"] != "u", 0.0)


def load_played() -> pd.DataFrame:
    d = _read("player_gw")
    return d[d["team_score"].notna()]  # drop rows from fixtures that haven't finished


def predict(horizon: int = HORIZON) -> pd.DataFrame:
    sc = load_scoring()
    played = load_played()
    season = sorted(played["season"].unique())[-1]
    up = upcoming_rows(season, horizon)
    frame = pd.concat([played, up[[c for c in up.columns if c in played.columns]]], ignore_index=True)
    feats, _ = build_features(frame)
    priors = position_priors(feats)

    is_up = feats["minutes"].isna() & (feats["kickoff_time"] > played["kickoff_time"].max())
    f_up = feats[is_up].merge(
        up[["season", "fixture", "code", "element", "gw_index", "status",
            "chance_of_playing_next_round", "now_cost", "selected_by_percent", "news"]],
        on=["season", "fixture", "code"])
    return expected_points(f_up, sc, priors, availability(f_up))


def backtest(seasons: list[str]) -> pd.DataFrame:
    sc = load_scoring()
    feats, _ = build_features(load_played())
    priors = position_priors(feats)
    f = feats[feats["season"].isin(seasons) & feats["n"].gt(0)]
    res = expected_points(f, sc, priors)
    res["actual"] = actual_points(res, sc)
    return res


def summarize(res: pd.DataFrame) -> pd.DataFrame:
    def stats(g: pd.DataFrame) -> pd.Series:
        return pd.Series({
            "rows": len(g),
            "mae_model": (g["xpts"] - g["actual"]).abs().mean(),
            "mae_naive": (g["xpts_naive"] - g["actual"]).abs().mean(),
            "rmse_model": np.sqrt(((g["xpts"] - g["actual"]) ** 2).mean()),
            "rmse_naive": np.sqrt(((g["xpts_naive"] - g["actual"]) ** 2).mean()),
            "corr_model": g["xpts"].corr(g["actual"]),
            "corr_naive": g["xpts_naive"].corr(g["actual"]),
            "bias_model": (g["xpts"] - g["actual"]).mean(),
        })
    regulars = res[res["xmin"] >= 45]
    return pd.concat({"all": stats(res), "xmin>=45": stats(regulars)}, axis=1).T
