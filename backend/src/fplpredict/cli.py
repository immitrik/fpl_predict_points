import argparse
import json
import sys

import pandas as pd

from .config import HISTORY_SEASONS, PROCESSED_DIR
from .current import load_current
from .fpl_api import FplApi
from .history import load_season

PLAYER_COLS = ["id", "code", "web_name", "team", "element_type", "now_cost", "status",
               "chance_of_playing_next_round", "news", "selected_by_percent", "removed"]
FIXTURE_COLS = ["id", "event", "team_h", "team_a", "kickoff_time", "started", "finished"]


def cmd_fetch(args: argparse.Namespace) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for season in HISTORY_SEASONS:
        rows, _ = load_season(season, refresh=args.refresh)
        print(f"{season}: {len(rows)} rows")
        frames.append(rows)

    cur = load_current(FplApi())
    print(f"{cur['season']} (live): {len(cur['rows'])} rows")
    frames.append(cur["rows"])

    pd.concat(frames, ignore_index=True).to_parquet(PROCESSED_DIR / "player_gw.parquet")
    cur["players"][PLAYER_COLS].to_parquet(PROCESSED_DIR / "current_players.parquet")
    cur["teams"][["id", "name", "short_name"]].to_parquet(PROCESSED_DIR / "current_teams.parquet")
    cur["events"][["id", "finished", "is_current", "is_next"]].to_parquet(
        PROCESSED_DIR / "current_events.parquet")
    cur["fixtures"][FIXTURE_COLS].to_parquet(PROCESSED_DIR / "current_fixtures.parquet")
    (PROCESSED_DIR / "scoring.json").write_text(json.dumps(cur["scoring"], indent=1))
    print("saved to", PROCESSED_DIR)


def cmd_predict(args: argparse.Namespace) -> None:
    from .pipeline import predict

    pred = predict(algo=args.algo)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pred.to_parquet(PROCESSED_DIR / "predictions.parquet")
    total = pred.groupby(["code", "name", "team", "position"], as_index=False)["xpts"].sum()
    total = total.sort_values("xpts", ascending=False)
    print(f"{len(pred)} player-fixtures, rounds {sorted(pred['round'].unique())}")
    print(total.head(args.top).to_string(index=False, float_format="%.1f"))


def cmd_backtest(args: argparse.Namespace) -> None:
    from .pipeline import backtest, summarize

    for season in args.seasons:
        print(f"== test season {season} ({'+'.join(args.algos)}) ==")
        print(summarize(backtest(season, tuple(args.algos))).to_string(float_format="%.3f"))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="fplpredict")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download history + current season data")
    f.add_argument("--refresh", action="store_true", help="re-download cached archive files")
    f.set_defaults(func=cmd_fetch)
    pr = sub.add_parser("predict", help="expected points for the next 5 gameweeks")
    pr.add_argument("--top", type=int, default=20)
    pr.add_argument("--algo", choices=["lgbm", "rf", "ens", "baseline"], default="ens")
    pr.set_defaults(func=cmd_predict)
    b = sub.add_parser("backtest", help="evaluate the baseline on past rows")
    b.add_argument("--seasons", nargs="+", default=["2025-26"])
    b.add_argument("--algos", nargs="+", choices=["lgbm", "rf"], default=["lgbm", "rf"])
    b.set_defaults(func=cmd_backtest)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
