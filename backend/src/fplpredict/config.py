from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

FPL_API = "https://fantasy.premierleague.com/api"
VAASTAV_RAW = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"

# Seasons with xG/xA data in the archive. The current season comes from the live API.
HISTORY_SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]

# One spelling per club across FPL archive, live FPL API and football-data.co.uk.
TEAM_CANON = {
    "Man Utd": "Man United", "Spurs": "Tottenham", "Hull City": "Hull", "Coventry City": "Coventry",
    "Sheffield Utd": "Sheffield United", "Ipswich Town": "Ipswich", "Leeds United": "Leeds",
    "Luton Town": "Luton", "Nottingham Forest": "Nott'm Forest", "Newcastle United": "Newcastle",
    "West Ham United": "West Ham", "Wolverhampton Wanderers": "Wolves", "Leicester City": "Leicester",
    "Norwich City": "Norwich", "Brighton & Hove Albion": "Brighton", "Sunderland AFC": "Sunderland",
}


def canon_team(name):
    return TEAM_CANON.get(name, name)


POSITIONS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
