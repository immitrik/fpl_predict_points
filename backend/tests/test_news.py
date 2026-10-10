from datetime import date

import pandas as pd

from fplpredict.news import FIRST_BACK, availability, parse, row_availability

REF = date(2026, 10, 10)


def test_parse_return_date():
    n = parse("Hamstring injury - Expected back 25 Oct", REF)
    assert n.kind == "date" and n.back == date(2026, 10, 25)


def test_parse_year_rollover():
    n = parse("Knee injury - Expected back 3 Jan", date(2026, 12, 20))
    assert n.back == date(2027, 1, 3)


def test_parse_kinds():
    assert parse("Suspended until 17 Oct", REF).kind == "suspended_date"
    assert parse("Suspended for 2 matches", REF).matches == 2
    assert parse("Knee injury - Unknown return date", REF).kind == "unknown"
    assert parse("Has joined Juventus on loan for the rest of the season", REF).kind == "left"
    assert parse("Unspecified injury - 75% chance of playing", REF).kind == "none"
    assert parse("", REF).kind == "none"


def test_availability_by_date():
    n = parse("Hamstring injury - Expected back 25 Oct", REF)
    assert availability(n, date(2026, 10, 18), 2, 0) == 0.0
    assert availability(n, date(2026, 10, 25), 3, 0) == FIRST_BACK


def test_unknown_return_ramps_up():
    n = parse("Knee injury - Unknown return date", REF)
    vals = [availability(n, date(2026, 11, 1), k, 0) for k in range(1, 6)]
    assert vals[0] == 0.0 and vals == sorted(vals) and vals[-1] < 0.5


def test_flag_only_regresses_to_one():
    n = parse("", REF)
    assert availability(n, REF, 1, 50) == 0.5
    assert availability(n, REF, 3, 50) == 0.75


def test_row_availability():
    rows = pd.DataFrame({
        "news": ["Hamstring injury - Expected back 25 Oct", "", "Has joined X permanently"],
        "news_added": ["2026-10-08T10:00:00Z", None, None],
        "status": ["i", "a", "u"],
        "chance_of_playing_next_round": [0.0, None, 0.0],
        "h": [1, 1, 1],
        "kickoff_time": pd.to_datetime(["2026-10-17", "2026-10-17", "2026-10-17"], utc=True),
    })
    assert row_availability(rows).tolist() == [0.0, 1.0, 0.0]
