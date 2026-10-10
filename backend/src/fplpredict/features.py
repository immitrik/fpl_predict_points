"""As-of features: everything is computed from matches strictly before the row's fixture.

Player and team histories are exponentially weighted moving averages over matches. Future
(unplayed) rows carry NaN stats; an EWM over a NaN row keeps its previous value, so after the
one-step shift every upcoming row sees the state after the last *played* match.
"""
import numpy as np
import pandas as pd

from .scoring import DC_THRESHOLD

PLAYER_HALFLIFE = 5
TEAM_HALFLIFE = 6
TEAM_PRIOR_MATCHES = 5
TEAM_MAX_N = 17

PLAYER_EWM = [
    "minutes", "played", "p60", "goals_scored", "expected_goals", "assists", "expected_assists",
    "bonus", "saves", "yellow_cards", "red_cards", "own_goals", "penalties_saved",
    "penalties_missed", "dc_ind", "total_points",
]


def _ewm_asof(df: pd.DataFrame, by: str, cols: list[str], halflife: float) -> pd.DataFrame:
    """Per-group EWM of `cols`, shifted so each row only sees earlier rows. df must be sorted."""
    ew = df.groupby(by)[cols].ewm(halflife=halflife).mean().reset_index(level=0, drop=True)
    return ew.groupby(df[by]).shift(1)


def _count_asof(df: pd.DataFrame, by: str, col: str) -> pd.Series:
    return df[col].notna().groupby(df[by]).cumsum().groupby(df[by]).shift(1).fillna(0)


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Add derived per-match indicators; `frame` holds played rows plus upcoming rows (NaN stats)."""
    f = frame.sort_values(["kickoff_time", "fixture", "code"]).reset_index(drop=True)
    mins = f["minutes"]
    f["played"] = (mins > 0).astype(float).where(mins.notna())
    f["p60"] = (mins >= 60).astype(float).where(mins.notna())
    thr = f["position"].map(DC_THRESHOLD).astype(float)
    f["dc_ind"] = (f["defensive_contribution"] >= thr).astype(float).where(
        f["defensive_contribution"].notna())
    return f


def team_features(f: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Per (season, fixture, team) attack/defence strength as of kickoff, plus league averages."""
    tm = f.groupby(["season", "fixture", "team"], as_index=False).agg(
        opponent=("opponent", "first"), was_home=("was_home", "first"),
        kickoff_time=("kickoff_time", "first"), gf=("team_score", "first"),
        ga=("opp_score", "first"), xgf=("expected_goals", lambda s: s.sum(min_count=1)),
    )
    opp_xg = tm[["season", "fixture", "team", "xgf"]].rename(columns={"team": "opponent", "xgf": "xga"})
    tm = tm.merge(opp_xg, on=["season", "fixture", "opponent"], how="left")
    tm["att_raw"] = 0.5 * tm["gf"] + 0.5 * tm["xgf"]
    tm["def_raw"] = 0.5 * tm["ga"] + 0.5 * tm["xga"]
    tm = tm.sort_values(["kickoff_time", "fixture"]).reset_index(drop=True)

    played = tm[tm["att_raw"].notna()]
    lg = {
        "all": float(played["att_raw"].mean()),
        "home": float(played.loc[played["was_home"], "att_raw"].mean()),
        "away": float(played.loc[~played["was_home"], "att_raw"].mean()),
    }

    ew = _ewm_asof(tm, "team", ["att_raw", "def_raw"], TEAM_HALFLIFE)
    n = np.minimum(_count_asof(tm, "team", "att_raw"), TEAM_MAX_N)
    for col in ("att_raw", "def_raw"):
        tm[col.replace("_raw", "_s")] = (
            (n * ew[col].fillna(lg["all"]) + TEAM_PRIOR_MATCHES * lg["all"]) / (n + TEAM_PRIOR_MATCHES)
        )
    return tm[["season", "fixture", "team", "att_s", "def_s"]], lg


def add_team_context(f: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    tf, lg = team_features(f)
    f = f.merge(tf, on=["season", "fixture", "team"], how="left")
    opp = tf.rename(columns={"team": "opponent", "att_s": "opp_att_s", "def_s": "opp_def_s"})
    f = f.merge(opp, on=["season", "fixture", "opponent"], how="left")
    lg_for = np.where(f["was_home"], lg["home"], lg["away"])
    lg_against = np.where(f["was_home"], lg["away"], lg["home"])
    f["exp_gf"] = lg_for * (f["att_s"] / lg["all"]) * (f["opp_def_s"] / lg["all"])
    f["exp_ga"] = lg_against * (f["opp_att_s"] / lg["all"]) * (f["def_s"] / lg["all"])
    return f, lg


def add_player_features(f: pd.DataFrame) -> pd.DataFrame:
    f = f.sort_values(["code", "kickoff_time", "fixture"]).copy()
    ew = _ewm_asof(f, "code", PLAYER_EWM, PLAYER_HALFLIFE).add_prefix("ew_")
    f = pd.concat([f, ew], axis=1)
    f["n"] = _count_asof(f, "code", "minutes")
    f["n_dc"] = _count_asof(f, "code", "dc_ind")
    return f.sort_values(["kickoff_time", "fixture", "code"]).reset_index(drop=True)


def build_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    f = prepare(frame)
    f, lg = add_team_context(f)
    return add_player_features(f), lg
