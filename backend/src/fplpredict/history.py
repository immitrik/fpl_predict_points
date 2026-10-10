"""Past-season data from the vaastav/Fantasy-Premier-League archive (cached on disk)."""
import io

import pandas as pd
import requests

from .config import RAW_DIR, VAASTAV_RAW, canon_team

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

    team_name = {i: canon_team(n) for i, n in zip(teams["id"], teams["name"])}
    code_of = dict(zip(raw["id"], raw["code"]))

    for c in STAT_COLS:
        if c not in gw:
            gw[c] = pd.NA
    out = pd.DataFrame({
        "season": season,
        "code": gw["element"].map(code_of),
        "name": gw["name"],
        "position": gw["position"].replace(POS_FIX),
        "team": gw["team"].map(canon_team),
        "opponent": gw["opponent_team"].map(team_name),
        "was_home": gw["was_home"].astype(bool),
        "round": gw["round"],
        "kickoff_time": pd.to_datetime(gw["kickoff_time"], utc=True),
        "fixture": gw["fixture"],
        "team_score": gw["team_h_score"].where(gw["was_home"].astype(bool), gw["team_a_score"]),
        "opp_score": gw["team_a_score"].where(gw["was_home"].astype(bool), gw["team_h_score"]),
        "value": gw["value"],
        "selected": pd.to_numeric(gw["selected"], errors="coerce"),
        "fpl_xp": pd.to_numeric(gw["xP"], errors="coerce"),
        "total_points": gw["total_points"],
        **{c: pd.to_numeric(gw[c], errors="coerce") for c in STAT_COLS},
    })
    # the archive occasionally lists a player twice for the same fixture
    out = out.drop_duplicates(["code", "fixture"]).reset_index(drop=True)
    return out, teams


ROLE_STRENGTH = {1: 1.0, 2: 0.5, 3: 0.25}


def role_strength(order: pd.Series) -> pd.Series:
    """Set-piece rota position (1 = first choice) -> 1.0 / 0.5 / 0.25 / 0.1 (4th+), 0 if none."""
    return order.map(ROLE_STRENGTH).fillna(order.notna().astype(float) * 0.1)


def set_pieces(raw: pd.DataFrame, season: str) -> pd.DataFrame:
    """Penalty / corner / direct free-kick roles per player from a players table (FPL schema)."""
    return pd.DataFrame({
        "season": season,
        "code": raw["code"],
        "pen": role_strength(raw["penalties_order"]),
        "corner": role_strength(raw["corners_and_indirect_freekicks_order"]),
        "fk": role_strength(raw["direct_freekicks_order"]),
    })


def load_set_pieces(season: str, refresh: bool = False) -> pd.DataFrame:
    """End-of-season roles of a finished season (archive snapshot)."""
    raw = _csv(f"{VAASTAV_RAW}/{season}/players_raw.csv", f"{season}/players_raw.csv", refresh)
    return set_pieces(raw, season)
