import argparse

import pandas as pd

from .config import HISTORY_SEASONS, PROCESSED_DIR
from .current import load_current
from .fpl_api import FplApi
from .history import load_season


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
    for name in ("players", "teams", "events", "fixtures", "element_types"):
        cur[name].astype(str).to_parquet(PROCESSED_DIR / f"current_{name}.parquet")
    print("saved to", PROCESSED_DIR)


def main() -> None:
    p = argparse.ArgumentParser(prog="fplpredict")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download history + current season data")
    f.add_argument("--refresh", action="store_true", help="re-download cached archive files")
    f.set_defaults(func=cmd_fetch)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
