import numpy as np
import pandas as pd
import pytest

from fplpredict.config import PROCESSED_DIR
from fplpredict.scoring import actual_points, expected_floor, load_scoring

PATH = PROCESSED_DIR / "player_gw.parquet"


@pytest.mark.skipif(not PATH.exists(), reason="run `fplpredict fetch` first")
def test_recomputed_points_match_official():
    d = pd.read_parquet(PATH)
    d = d[d["season"] >= "2025-26"]  # defensive-contribution rules apply from this season
    ok = (actual_points(d, load_scoring()) == d["total_points"]).mean()
    assert ok > 0.995, ok


def test_expected_floor():
    # P(X>=2) for Poisson(1) = 1 - 2/e ; floor(X/2) in {0,1,2,...}
    assert np.isclose(expected_floor(np.array([0.0]), 2)[0], 0.0)
    assert expected_floor(np.array([6.0]), 2)[0] > expected_floor(np.array([2.0]), 2)[0]
