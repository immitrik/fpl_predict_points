"""Past-season data from the vaastav/Fantasy-Premier-League archive (cached on disk)."""
import io

import pandas as pd
import requests

from .config import RAW_DIR, VAASTAV_RAW

STAT_COLS = [
    "minutes", "starts", "goals_scored", "assists", "clean_sheets", "goals_conceded",
    "own_goals", "penalties_saved", "penalties_missed", "yellow_cards", "red_cards",
    "saves", "bonus", "bps", "defensive_contribution",
    "expected_goals", "expected_assists", "expected_goals_conceded",
    "influence", "creativity", "threat", "ict_index",
]
POS_FIX = {"GK": "GKP", "AM": "MID"}


def _download(url: str, cache_name: str, refresh: bool = False) -> bytes:
    path = RAW_DIR / cache_name
    if path.exists() and not refresh:
        return path.read_bytes()
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return r.content


def _csv(url: str, cache_name: str, refresh: bool) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(_download(url, cache_name, refresh)), low_memory=False)


def load_season(season: str, refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (player-gameweek rows, teams) for a finished season."""
    base = f"{VAASTAV_RAW}/{season}"
    gw = _csv(f"{base}/gws/merged_gw.csv", f"{season}/merged_gw.csv", refresh)
    raw = _csv(f"{base}/players_raw.csv", f"{season}/players_raw.csv", refresh)
    teams = _csv(f"{base}/teams.csv", f"{season}/teams.csv", refresh)

    team_name = dict(zip(teams["id"], teams["name"]))
    code_of = dict(zip(raw["id"], raw["code"]))

    for c in STAT_COLS:
        if c not in gw:
            gw[c] = pd.NA
    out = pd.DataFrame({
        "season": season,
        "code": gw["element"].map(code_of),
        "name": gw["name"],
        "position": gw["position"].replace(POS_FIX),
        "team": gw["team"],
        "opponent": gw["opponent_team"].map(team_name),
        "was_home": gw["was_home"].astype(bool),
        "round": gw["round"],
        "kickoff_time": pd.to_datetime(gw["kickoff_time"], utc=True),
        "fixture": gw["fixture"],
        "value": gw["value"],
        "total_points": gw["total_points"],
        **{c: pd.to_numeric(gw[c], errors="coerce") for c in STAT_COLS},
    })
    # the archive occasionally lists a player twice for the same fixture
    out = out.drop_duplicates(["code", "fixture"]).reset_index(drop=True)
    return out, teams
