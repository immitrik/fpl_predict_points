from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

FPL_API = "https://fantasy.premierleague.com/api"
VAASTAV_RAW = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"

# Seasons with xG/xA data in the archive. The current season comes from the live API.
HISTORY_SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]

POSITIONS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
