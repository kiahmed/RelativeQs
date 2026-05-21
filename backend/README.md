FastAPI backend for Price Flow Tracker

Overview
- FastAPI service providing:
  - WebSocket streaming for live market snapshots
  - REST endpoints for snapshots and scoring
  - A modular market-data adapter (mock by default)
  - A QQQ regime scoring engine (weighted factors)

Quick start (local)

1) Create a Python virtualenv and install dependencies:

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

> Note: If you are using Python 3.13, the backend now installs `numpy==2.4.6`, `scipy==1.17.1`, `scikit-learn==1.8.0`, and `aiohttp==3.13.5` because these versions publish prebuilt wheels for Python 3.13 on Windows.

2) Run the app:

```bash
uvicorn backend.main:app --reload --port 8000
```

3) Open the docs: http://localhost:8000/docs

Notes
- CORS is configured to allow the frontend at http://localhost:5173. Change as needed in `backend/main.py`.
- Market adapters: `mock` adapter provides synthetic signals. Replace with a real adapter (Alpaca, Polygon, Finnhub, etc.) inside `backend/app/services/market_data.py`.
- Redis is optional; the current scaffold uses an in-memory broadcaster for websockets.

- A secondary provider is now available using free Yahoo Finance price data via `DATA_PROVIDER=yahoo`.

Example:

```bash
set DATA_PROVIDER=yahoo
uvicorn backend.main:app --reload --port 8000
```

Configuration
- Copy `.env.example` to `.env` and set your provider and keys:
  - `DATA_PROVIDER` = `mock`, `yahoo`, `alphavantage`, `twelvedata`, `polygon`, `alpaca`, or `finnhub`
  - `ALPHAVANTAGE_KEY`, `TWELVEDATA_KEY`, `POLYGON_KEY`, `ALPACA_KEY`, `ALPACA_SECRET`, `FINNHUB_KEY`
  - `REDIS_URL` to enable Redis publish/persist behavior
  - `NORMALIZE_SIGNALS=true` to make the `/api/score` route normalize signals by default
- The backend reads these values through `backend/app/config.py` and uses them inside market adapters and scoring logic.

Using `.env` on Windows PowerShell:

```powershell
copy .env.example .env
notepad .env
# then run:
uvicorn backend.main:app --reload --port 8000
```

Recommended next steps
- Add your market-data provider and API keys via environment variables.
- Replace mock signal generation with real per-tick or minute series and persist raw series to a time-series DB (InfluxDB / Timescale / Databento / S3 + Parquet).
- Add authentication and rate-limiting for production.
- Add provider wrappers for Alpha Vantage, Finnhub, TwelveData, or Polygon to mix free and paid data.
