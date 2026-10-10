import numpy as np
import pandas as pd

from fplpredict.features import FeatureBuilder

STATS = ["minutes", "goals_scored", "expected_goals", "assists", "expected_assists", "bonus", "saves",
         "yellow_cards", "red_cards", "own_goals", "penalties_saved", "penalties_missed",
         "defensive_contribution", "total_points", "team_score", "opp_score", "value", "selected"]


def _frame(minutes: list[float]) -> pd.DataFrame:
    n = len(minutes)
    df = pd.DataFrame({
        "season": "2026-27", "code": 1, "position": "MID", "team": "A", "opponent": "B",
        "was_home": True, "round": range(1, n + 1), "fixture": range(1, n + 1),
        "kickoff_time": pd.date_range("2026-08-01", periods=n, freq="7D", tz="UTC"),
    })
    for c in STATS:
        df[c] = 1.0
    df["minutes"] = minutes
    return df


def test_features_do_not_see_own_row():
    a = FeatureBuilder(_frame([90, 90, 90, 90])).at(1)
    b = FeatureBuilder(_frame([90, 90, 90, 0])).at(1)
    assert a["ew_minutes"].iloc[3] == b["ew_minutes"].iloc[3]  # last row's own minutes unseen
    assert a["n"].tolist() == [0, 1, 2, 3]


def test_upcoming_rows_carry_last_played_state():
    f = FeatureBuilder(_frame([90, 60, np.nan, np.nan, np.nan])).at(1)
    ew = f["ew_minutes"]
    assert ew.iloc[2] == ew.iloc[3] == ew.iloc[4]
    assert 60 < ew.iloc[2] < 90
    assert f["n"].tolist() == [0, 1, 2, 2, 2]


def test_horizon_shifts_state_back():
    fb = FeatureBuilder(_frame([90, 60, 30, 90, 90, 90]))
    h1, h3 = fb.at(1), fb.at(3)
    assert h3["ew_minutes"].iloc[4] == h1["ew_minutes"].iloc[2]
    # an upcoming 3rd match sees the same state as the 1st upcoming one
    up = FeatureBuilder(_frame([90, 60, 30, np.nan, np.nan, np.nan]))
    assert up.at(3)["ew_minutes"].iloc[5] == up.at(1)["ew_minutes"].iloc[3]


def test_cold_start_eligibility():
    import pandas as pd
    from fplpredict.pipeline import eligible

    f = pd.DataFrame({"season": ["2022-23", "2022-23", "2023-24", "2023-24"], "n": [0, 3, 0, 5]})
    # first-season rows without history are established players with unseen pasts -> excluded;
    # a later-season player with n=0 is a genuine newcomer -> included
    assert eligible(f, "2022-23").tolist() == [False, True, True, True]
