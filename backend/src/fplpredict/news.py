"""Turn FPL injury / suspension news into per-match availability.

The API only gives a fitness flag for the next round plus free text such as
"Hamstring injury - Expected back 25 Oct" or "Knee injury - Unknown return date". We parse the
text into a return date where one is given, and otherwise fall back to a prior over how long such
injuries last. All numbers below are hand-set heuristics (no historical news is archived to fit
them on), so they are kept in one place and deliberately conservative.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

DATE_RE = re.compile(r"(expected back|suspended until)\s+(\d{1,2})\s+([A-Za-z]{3})", re.I)
MATCHES_RE = re.compile(r"suspended for (\d+) (?:match|game)", re.I)
LEFT_RE = re.compile(r"has joined|has left|permanent|transfer", re.I)

FIRST_BACK = 0.75    # first match after an injury return: likely managed minutes
SECOND_BACK = 0.9
# Unknown return date: chance the player is available in the k-th upcoming match (k = 1, 2, ...)
UNKNOWN_STEP = 0.12
UNKNOWN_CAP = 0.6


@dataclass
class News:
    kind: str                       # none | left | date | suspended_date | suspended_matches | unknown
    back: date | None = None        # first date the player can feature
    matches: int = 0                # matches still to miss (suspended_matches)


def _resolve_date(day: int, mon: str, ref: date) -> date | None:
    month = MONTHS.get(mon.lower())
    if month is None:
        return None
    try:
        d = date(ref.year, month, day)
    except ValueError:
        return None
    if d < ref - timedelta(days=60):
        d = d.replace(year=d.year + 1)
    return d


def parse(text: str | None, ref: date) -> News:
    """`ref` is the date the news was written (or today)."""
    if not text:
        return News("none")
    if LEFT_RE.search(text) and "injur" not in text.lower():
        return News("left")
    m = DATE_RE.search(text)
    if m:
        back = _resolve_date(int(m.group(2)), m.group(3), ref)
        if back:
            return News("suspended_date" if m.group(1).lower().startswith("susp") else "date", back)
    m = MATCHES_RE.search(text)
    if m:
        return News("suspended_matches", matches=int(m.group(1)))
    if "unknown return" in text.lower() or "suspended" in text.lower():
        return News("unknown")
    return News("none")


def availability(news: News, kickoff: date, k: int, next_chance: float | None) -> float:
    """Chance the player features in his k-th upcoming match (k=1 is the next one)."""
    if news.kind == "left":
        return 0.0
    if news.kind in ("date", "suspended_date"):
        if kickoff < news.back:
            return 0.0
        return 1.0 if news.kind == "suspended_date" else FIRST_BACK
    if news.kind == "suspended_matches":
        return 0.0 if k <= news.matches else 1.0
    if news.kind == "unknown":
        return float(np.clip(UNKNOWN_STEP * (k - 1), 0.0, UNKNOWN_CAP)) * FIRST_BACK
    # no usable text: rely on the flag (doubtful players: flag for the next match, then regress to 1)
    c = 1.0 if next_chance is None or pd.isna(next_chance) else float(next_chance) / 100
    return c if k == 1 else (c + 1) / 2


def row_availability(rows: pd.DataFrame, today: date | None = None) -> pd.Series:
    """Availability per (player, upcoming match); needs news, news_added, status, chance, h, kickoff_time."""
    today = today or datetime.utcnow().date()
    out = np.empty(len(rows))
    cache: dict[tuple, News] = {}
    for i, r in enumerate(rows.itertuples()):
        if r.status == "u":
            out[i] = 0.0
            continue
        added = pd.to_datetime(r.news_added, errors="coerce", utc=True)
        ref = added.date() if pd.notna(added) else today
        key = (r.news, ref)
        if key not in cache:
            cache[key] = parse(r.news or None, ref)
        out[i] = availability(cache[key], r.kickoff_time.date(), int(r.h),
                              r.chance_of_playing_next_round)
    return pd.Series(out, index=rows.index)
