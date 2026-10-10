"""Betting-market data from football-data.co.uk -> implied expected goals per match.

Market average odds (1X2 and over/under 2.5) are converted to fair probabilities and a pair of
Poisson rates (lambda_home, lambda_away) is fitted to reproduce them. The result is a strong,
outcome-independent estimate of team strength for a specific fixture. Odds are only published a
few days ahead, so for later gameweeks the models fall back to market-based team ratings.
"""
import io

import numpy as np
import pandas as pd
import requests
from scipy.optimize import least_squares
from scipy.stats import poisson

from .config import RAW_DIR, canon_team

FD = "https://football-data.co.uk"
SEASON_CODES = {"2022-23": "2223", "2023-24": "2324", "2024-25": "2425", "2025-26": "2526",
                "2026-27": "2627"}
GRID = 11
_K = np.arange(GRID)


def _fetch(url: str, cache: str, refresh: bool) -> pd.DataFrame:
    path = RAW_DIR / "odds" / cache
    if not path.exists() or refresh:
        r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    return pd.read_csv(io.BytesIO(path.read_bytes()), encoding="utf-8-sig")


def _implied(odds: np.ndarray) -> np.ndarray:
    """Proportional de-vig: decimal odds (n, k) -> probabilities summing to 1 per row."""
    inv = 1.0 / odds
    return inv / inv.sum(axis=1, keepdims=True)


def _model_probs(lh: float, la: float) -> np.ndarray:
    ph, pa = poisson.pmf(_K, lh), poisson.pmf(_K, la)
    joint = np.outer(ph, pa)
    home, draw = np.tril(joint, -1).sum(), np.trace(joint)
    over = 1 - sum(joint[i, j] for i in range(3) for j in range(3) if i + j <= 2)
    return np.array([home, draw, over])


def fit_lambdas(p1x2: np.ndarray, p_over: float) -> tuple[float, float]:
    target = np.array([p1x2[0], p1x2[1], p_over])
    res = least_squares(lambda x: _model_probs(*np.exp(x)) - target, x0=np.log([1.5, 1.2]))
    lh, la = np.exp(res.x)
    return float(lh), float(la)


def _table(df: pd.DataFrame, season: str) -> pd.DataFrame:
    cols = ["AvgH", "AvgD", "AvgA", "Avg>2.5", "Avg<2.5"]
    df = df.dropna(subset=cols).copy()
    p = _implied(df[["AvgH", "AvgD", "AvgA"]].to_numpy(float))
    p_over = _implied(df[["Avg>2.5", "Avg<2.5"]].to_numpy(float))[:, 0]
    lam = np.array([fit_lambdas(p[i], p_over[i]) for i in range(len(df))])
    return pd.DataFrame({
        "season": season,
        "home": df["HomeTeam"].map(canon_team).to_numpy(),
        "away": df["AwayTeam"].map(canon_team).to_numpy(),
        "lam_h": lam[:, 0], "lam_a": lam[:, 1],
        "mk_p_home": p[:, 0], "mk_p_draw": p[:, 1], "mk_p_away": p[:, 2],
    })


def load_odds(current_season: str, refresh: bool = False) -> pd.DataFrame:
    """Odds-implied goal rates for played matches of all seasons plus upcoming fixtures."""
    parts = []
    for season, code in SEASON_CODES.items():
        if season > current_season:
            continue
        df = _fetch(f"{FD}/mmz4281/{code}/E0.csv", f"{code}_E0.csv", refresh or season == current_season)
        parts.append(_table(df, season))
    fx = _fetch(f"{FD}/fixtures.csv", "fixtures.csv", True)
    parts.append(_table(fx[fx["Div"] == "E0"], current_season))
    out = pd.concat(parts, ignore_index=True)
    return out.drop_duplicates(["season", "home", "away"], keep="first").reset_index(drop=True)
