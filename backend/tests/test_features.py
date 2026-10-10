import numpy as np
import pandas as pd

from fplpredict.features import add_player_features, prepare

STATS = ["minutes", "goals_scored", "expected_goals", "assists", "expected_assists", "bonus", "saves",
         "yellow_cards", "red_cards", "own_goals", "penalties_saved", "penalties_missed",
         "defensive_contribution", "total_points"]


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
    a = add_player_features(prepare(_frame([90, 90, 90, 90])))
    b = add_player_features(prepare(_frame([90, 90, 90, 0])))
    assert a["ew_minutes"].iloc[3] == b["ew_minutes"].iloc[3]  # last row's own minutes unseen
    assert a["n"].tolist() == [0, 1, 2, 3]


def test_upcoming_rows_carry_last_played_state():
    f = add_player_features(prepare(_frame([90, 60, np.nan, np.nan])))
    ew = f["ew_minutes"]
    assert ew.iloc[2] == ew.iloc[3]
    assert 60 < ew.iloc[2] < 90
    assert f["n"].tolist() == [0, 1, 2, 2]
