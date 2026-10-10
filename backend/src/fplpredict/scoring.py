"""FPL scoring rules (values come from the API's game_config.scoring) and point calculation."""
import json

import numpy as np
import pandas as pd
from scipy.stats import poisson

from .config import PROCESSED_DIR

# Not exposed by the API: thresholds for the defensive-contribution bonus (from 2025/26).
DC_THRESHOLD = {"GKP": np.inf, "DEF": 10, "MID": 12, "FWD": 12}
GC_PER_POINT = 2   # -1 per 2 goals conceded (GKP/DEF)
SAVES_PER_POINT = 3


def load_scoring() -> dict:
    return json.loads((PROCESSED_DIR / "scoring.json").read_text())


def actual_points(df: pd.DataFrame, sc: dict) -> pd.Series:
    """Recompute FPL points from raw match stats."""
    pos = df["position"]

    def by_pos(key: str) -> pd.Series:
        return pos.map(sc[key]).astype(float)

    mins = df["minutes"].fillna(0)
    pts = (
        (mins > 0) * sc["short_play"] + (mins >= 60) * (sc["long_play"] - sc["short_play"])
        + df["goals_scored"].fillna(0) * by_pos("goals_scored")
        + df["assists"].fillna(0) * sc["assists"]
        + df["clean_sheets"].fillna(0) * by_pos("clean_sheets")
        + np.floor(df["goals_conceded"].fillna(0) / GC_PER_POINT) * by_pos("goals_conceded")
        + np.floor(df["saves"].fillna(0) / SAVES_PER_POINT) * sc["saves"] * (pos == "GKP")
        + df["penalties_saved"].fillna(0) * sc["penalties_saved"]
        + df["penalties_missed"].fillna(0) * sc["penalties_missed"]
        + df["yellow_cards"].fillna(0) * sc["yellow_cards"]
        + df["red_cards"].fillna(0) * sc["red_cards"]
        + df["own_goals"].fillna(0) * sc["own_goals"]
        + df["bonus"].fillna(0) * sc["bonus"]
        + dc_hit(df) * by_pos("defensive_contribution")
    )
    return pts


def dc_hit(df: pd.DataFrame) -> pd.Series:
    """1 if the player reached the defensive-contribution threshold, NaN if the stat is unknown."""
    thr = df["position"].map(DC_THRESHOLD).astype(float)
    hit = (df["defensive_contribution"] >= thr).astype(float)
    return hit.where(df["defensive_contribution"].notna(), 0.0)


def expected_floor(mu: np.ndarray, divisor: int, kmax: int = 25) -> np.ndarray:
    """E[floor(X / divisor)] for X ~ Poisson(mu)."""
    mu = np.asarray(mu, dtype=float)[..., None]
    k = np.arange(kmax + 1)
    return (poisson.pmf(k, mu) * (k // divisor)).sum(axis=-1)
