"""Write the static JSON files consumed by the web app."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import PROCESSED_DIR

FORM_MATCHES = 8


def _r(x: float, nd: int = 2) -> float:
    return round(float(x), nd)


def build(pred: pd.DataFrame, played: pd.DataFrame, model: str) -> tuple[dict, dict]:
    """Return (players.json payload, teams.json payload)."""
    teams = pd.read_parquet(PROCESSED_DIR / "current_teams.parquet")
    short = dict(zip(teams["name"], teams["short_name"]))
    gws = sorted(int(r) for r in pred["round"].unique())
    season = str(pred["season"].iloc[0])

    cur = played[played["season"] == season].sort_values(["kickoff_time", "fixture"])
    form = {
        code: [
            {"r": int(r.round), "o": short.get(r.opponent, r.opponent), "h": bool(r.was_home),
             "p": int(r.total_points), "m": int(r.minutes)}
            for r in g.tail(FORM_MATCHES).itertuples()
        ]
        for code, g in cur.groupby("code")
    }
    season_stats = cur.groupby("code").agg(pts=("total_points", "sum"), mins=("minutes", "sum"))

    players = []
    for element, g in pred.sort_values(["kickoff_time", "fixture"]).groupby("element"):
        first = g.iloc[0]
        by_gw = g.groupby("round")["xpts"].sum()
        stats = season_stats.loc[first["code"]] if first["code"] in season_stats.index else None
        chance = first["chance_of_playing_next_round"]
        players.append({
            "id": int(element),
            "name": first["name"],
            "team": short.get(first["team"], first["team"]),
            "pos": first["position"],
            "cost": _r(first["now_cost"] / 10, 1),
            "own": _r(float(first["selected_by_percent"]), 1),
            "status": first["status"],
            "chance": None if pd.isna(chance) else int(chance),
            "news": first["news"] or "",
            "pts": 0 if stats is None else int(stats["pts"]),
            "mins": 0 if stats is None else int(stats["mins"]),
            "gw": [_r(by_gw.get(r, 0.0)) for r in gws],
            "total": _r(g["xpts"].sum()),
            "fx": [
                {"r": int(x.round), "o": short.get(x.opponent, x.opponent), "h": bool(x.was_home),
                 "xp": _r(x.xpts), "mn": _r(x.xmin, 1), "g": _r(x.x_goals, 3), "a": _r(x.x_assists, 3),
                 "cs": _r(x.x_cs, 3), "b": _r(x.x_bonus, 3), "dc": _r(x.x_dc, 3), "sv": _r(x.x_saves, 2)}
                for x in g.itertuples()
            ],
            "form": form.get(first["code"], []),
        })
    players.sort(key=lambda p: -p["total"])

    fx = pred.drop_duplicates(["team", "fixture"]).sort_values(["kickoff_time", "fixture"])
    team_rows = []
    for team, g in fx.groupby("team"):
        team_rows.append({
            "team": short.get(team, team),
            "name": team,
            "fx": [{"r": int(x.round), "o": short.get(x.opponent, x.opponent), "h": bool(x.was_home),
                    "gf": _r(x.exp_gf), "ga": _r(x.exp_ga)} for x in g.itertuples()],
        })
    team_rows.sort(key=lambda t: t["team"])

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season": season,
        "gws": gws,
        "model": model,
    }
    return {**meta, "players": players}, {**meta, "teams": team_rows}


def write(pred: pd.DataFrame, played: pd.DataFrame, out: Path, model: str) -> None:
    players, teams = build(pred, played, model)
    out.mkdir(parents=True, exist_ok=True)
    for name, payload in (("players.json", players), ("teams.json", teams)):
        (out / name).write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
                                encoding="utf-8")
