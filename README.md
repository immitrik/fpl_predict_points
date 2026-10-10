# FPL Predict Points

Predicts Fantasy Premier League points for every player over the next 5 gameweeks.

## Architecture

- `backend/` - Python pipeline: fetch data -> features -> model -> export static JSON.
- `web/` - React + Vite + TypeScript site that reads the JSON (deployed to GitHub Pages).
- GitHub Actions runs the pipeline on a schedule and redeploys the site; there is no server.

Data: official FPL API (current season) + [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League) (past seasons).

## Development

```
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m fplpredict.cli fetch     # writes data/processed/*.parquet
.venv/Scripts/python -m fplpredict.cli predict   # 5-GW expected points -> data/processed/predictions.parquet
.venv/Scripts/python -m fplpredict.cli backtest --seasons 2024-25 2025-26
.venv/Scripts/python -m pytest
```
