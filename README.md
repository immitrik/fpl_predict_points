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
.venv/Scripts/python -m fplpredict.cli predict   # 5-GW expected points (LightGBM+RF ensemble) -> data/processed/predictions.parquet
.venv/Scripts/python -m fplpredict.cli backtest --seasons 2025-26 2026-27   # baseline vs LightGBM vs RF vs ensemble
.venv/Scripts/python -m pytest
```

## Website

```
cd backend && .venv/Scripts/python -m fplpredict.cli export   # writes web/public/data/*.json
cd ../web && npm install && npm run dev                       # http://localhost:5173
```

Deployment is automatic: `.github/workflows/deploy.yml` fetches data, trains the models, exports
the JSON, builds the site and publishes it to GitHub Pages on every push to `main` and every 6 hours.
One-time setup: repository **Settings -> Pages -> Source: GitHub Actions**.

## Data sources

Used: official FPL API; [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League)
archive (past seasons, set-piece roles); [football-data.co.uk](https://www.football-data.co.uk/) (results and betting odds).

Evaluated and not used (free/open data only):
- **Understat**: `robots.txt` disallows all crawling and there is no API; the vaastav mirror stops at 2024-25.
- **FBref**: lost its Opta advanced stats in January 2026.
- **Penalty takers from xG in match logs**: penalties leave no clean xG fingerprint, so roles come from the
  FPL/archive set-piece order plus anyone who missed a penalty this season.
- **Net transfers (`transfers_balance`)** as a form signal: no measurable gain in backtests.
- **Per-position models**: not better than one global model (still available via `--algo ens-pos`).
