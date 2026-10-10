"""Current-season data from the live FPL API, normalised to the same schema as history.py."""
import pandas as pd

from .config import POSITIONS
from .fpl_api import FplApi
from .history import STAT_COLS


def load_current(api: FplApi) -> dict:
    boot = api.bootstrap()
    teams = pd.DataFrame(boot["teams"])
    players = pd.DataFrame(boot["elements"])
    team_name = dict(zip(teams["id"], teams["name"]))

    summaries = api.all_element_summaries(players["id"].tolist())
    hist = pd.DataFrame([row for s in summaries.values() for row in s["history"]])

    meta = players.set_index("id")
    hist["code"] = hist["element"].map(meta["code"])
    hist["name"] = hist["element"].map(meta["web_name"])
    hist["position"] = hist["element"].map(meta["element_type"]).map(POSITIONS)
    hist["team"] = hist["element"].map(meta["team"]).map(team_name)
    hist["opponent"] = hist["opponent_team"].map(team_name)
    hist["kickoff_time"] = pd.to_datetime(hist["kickoff_time"], utc=True)
    for c in STAT_COLS:
        hist[c] = pd.to_numeric(hist[c], errors="coerce")
    hist["team_score"] = hist["team_h_score"].where(hist["was_home"], hist["team_a_score"])
    hist["opp_score"] = hist["team_a_score"].where(hist["was_home"], hist["team_h_score"])
    season = _season_label(boot)
    hist["season"] = season
    cols = ["season", "code", "name", "position", "team", "opponent", "was_home", "round",
            "kickoff_time", "fixture", "team_score", "opp_score", "value", "total_points", *STAT_COLS]
    return {
        "season": season,
        "rows": hist[cols],
        "players": players,
        "teams": teams,
        "events": pd.DataFrame(boot["events"]),
        "fixtures": pd.DataFrame(api.fixtures()),
        "scoring": boot["game_config"]["scoring"],
    }


def _season_label(boot: dict) -> str:
    first = min(e["deadline_time"] for e in boot["events"])
    y = int(first[:4])
    return f"{y}-{str(y + 1)[2:]}"
