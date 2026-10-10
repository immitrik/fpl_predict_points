import pandas as pd
import pytest

from fplpredict.config import PROCESSED_DIR

PATH = PROCESSED_DIR / "player_gw.parquet"


@pytest.mark.skipif(not PATH.exists(), reason="run `fplpredict fetch` first")
def test_player_gw_schema():
    d = pd.read_parquet(PATH)
    assert d["code"].notna().all()
    assert set(d["position"]) <= {"GKP", "DEF", "MID", "FWD"}
    assert d["opponent"].notna().all()
    assert not d.duplicated(["season", "code", "fixture"]).any()
