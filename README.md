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

### Transfer planner

The **Planner** tab takes an FPL team ID and finds the best squad for the next gameweeks with 0-4 transfers
(integer programme solved in the browser with HiGHS; −4 per transfer beyond the free ones; selling prices use
the FPL half-profit rule). The FPL API sends no CORS headers, so loading by ID from a static site needs a proxy:

- deploy the free Cloudflare Worker (`cd worker && npx wrangler login && npx wrangler deploy`) and set the
  repository variable `FPL_PROXY` to `https://fpl-proxy.<subdomain>.workers.dev/?u={url}` (then re-run the
  workflow). The worker only serves FPL API URLs to the origins listed in `worker/fpl-proxy.js`, or
- visitors can paste the JSON copied from the FPL site, or enter the squad manually (no proxy needed).

Dev tools: `node web/scripts/dev-proxy.mjs` (local proxy), `node web/scripts/plan-check.ts <teamId> [free] [from-to]` (CLI check), `node web/scripts/ft-check.ts <fromId> <toId>` (validates the free-transfer simulation against real hits).

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
