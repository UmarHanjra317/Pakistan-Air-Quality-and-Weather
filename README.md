# Pakistan Air Quality and Weather — Phase 01

**Phase 01 — ETL & Exploratory Data Analysis**

## 1. Description
A university project that builds an **ETL pipeline** (extract → transform/validate with pandas and Pydantic → load into a database) and a structured **exploratory data analysis** of hourly air-quality and weather observations for Pakistani cities, presented through an interactive dashboard (HTML/CSS/JavaScript + Flask API).

## 2. Phase-01 scope
Included: ETL, EDA, interactive frontend.
**Not included (future phases):** machine learning, prediction, forecasting, model training/evaluation, MLflow/PyTorch.
**Data now comes from a live API.** The *Extract* step downloads hourly air-quality and weather data for the 10 cities from the free [Open-Meteo](https://open-meteo.com) APIs (no key needed, non-commercial use). The web app re-runs the ETL automatically every `REFRESH_MINUTES` (default 60), so the dashboard and every analysis keep changing as new hours arrive. The original CSV is kept only as an offline fallback (`--source csv`, or automatically if the API is unreachable on first start).

## 3. Dataset (verified programmatically)
| Item | Value |
|---|---|
| Rows × columns (original CSV; the live API gives ~21,800 rows for the last 90 days) | 21,840 × 26 |
| Cities (10) | Faisalabad, Islamabad, Karachi, Lahore, Multan, Peshawar, Quetta, Rahim Yar Khan, Rawalpindi, Sialkot |
| Period | 2025-11-06 00:00 → 2026-02-04 23:00 (hourly, 2,184 hours per city) |
| Pollutants | pm2_5, pm10, carbon_monoxide, nitrogen_dioxide, sulphur_dioxide, ozone, dust |
| Weather | temperature, humidity, precipitation, wind_speed, wind_direction, pressure |
| Existing calendar fields | date, hour, day_of_week, month, month_name, year, is_weekend, season |
| AQI | only `aqi_category` is provided (no numeric AQI) |
| Missing / duplicates | 0 / 0 |

**Derived AQI:** a numeric `aqi` is computed from PM2.5 with US EPA breakpoints and cross-checked against `aqi_category` (0 mismatches). It reflects PM2.5 only.
**Limitation:** the data covers ~3 months (Autumn and Winter), so yearly/seasonal comparisons are limited. Visibility and cloud cover do not exist in the dataset and are not shown.

## 4. Technologies
Python, pandas, NumPy, Pydantic v2, SQLite, Flask, matplotlib (static EDA report), HTML, CSS, JavaScript, Chart.js (CDN – internet needed in the browser).

## 5. Structure
```
Pakistan-Air-Quality-and-Weather/          <- this is the GitHub repository root (open THIS folder in VS Code)
├── .devcontainer/devcontainer.json        one-tap cloud editor (GitHub Codespaces), works from a phone
├── .github/workflows/refresh.yml          hourly "wake up and refresh" job (optional)
├── .vscode/launch.json                    Run / Debug buttons for VS Code
├── backend/
│   ├── __init__.py
│   ├── app.py                             Flask app (serves API + frontend)
│   ├── data_store.py                      live data store, auto-refreshes from the API
│   └── api/
│       ├── __init__.py
│       └── routes.py                      REST endpoints (/api/...)
├── data/
│   └── raw/original_dataset.csv           offline fallback data (the only data file in Git)
│       (generated at run time, NOT in Git: data/raw/api_cache.csv, data/processed/*)
├── eda/
│   ├── __init__.py
│   ├── analysis.py                        reusable EDA functions (stats, correlation, histograms ...)
│   └── exploratory_analysis.py            builds reports/eda_report.html
├── etl/
│   ├── __init__.py
│   ├── api_client.py                      Open-Meteo API client
│   └── etl_pipeline.py                    Extract / Transform / Load
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/script.js
├── reports/                               generated: etl_report.json, eda_report.html (NOT in Git)
├── config.py                              paths, API settings, variable metadata
├── requirements.txt
├── render.yaml                            free hosting blueprint (Render)
├── DEPLOY.md                              GitHub + hosting guide
├── README.md
└── .gitignore
```

## 6. Installation
```bash
python -m venv venv
venv\Scripts\activate          # Windows   (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
```

## 7. Run
```bash
# Dashboard - on first start it downloads the data from the API by itself, then refreshes every hour
python backend/app.py

# Optional, by hand:
python etl/etl_pipeline.py                                     # pull the latest data from the API now
python etl/etl_pipeline.py --source csv --input my_data.csv    # offline: use a CSV instead
python eda/exploratory_analysis.py                             # rebuild the static EDA report
```
Open **http://127.0.0.1:5000** — pages: Dashboard, ETL, EDA, Air Quality, Weather, Cities, Data, About. The full EDA report is at `/report`. The header shows when the data was last updated; **↻ Refresh** pulls new data immediately.

**REST API** (JSON): `/api/status`, `/api/meta`, `/api/summary`, `/api/timeseries`, `/api/by_city`, `/api/temporal`, `/api/correlation`, `/api/records`, … and `POST /api/refresh` (add `?wait=1` to wait for it to finish; limited to once per 5 minutes).

**Settings** (environment variables): `REFRESH_MINUTES` (default 15), `HISTORY_DAYS` (default 90, max 92), `CACHE_MAX_DAYS` (default 365).

**Deploy online:** see [DEPLOY.md](DEPLOY.md) (GitHub account → push → free hosting on Render).

## 8. What the ETL does
1. **Extract** – downloads the last `HISTORY_DAYS` days from the API (retries, timeouts, skips a failing city, drops hours that have not happened yet) and merges them into `data/raw/api_cache.csv` so history accumulates. CSV mode: safe read (utf-8 / utf-8-sig / latin-1 fallback).
2. **Transform** – duplicate removal; type conversion; **Pydantic** schema validation with physical limits (coordinates, humidity 0–100, wind direction 0–360, non-negative pollutants …) with rejected rows quarantined; column-aware missing-value strategy applied *before* validation (per-city interpolation → median; mode for categories; no blind zero fill); calendar features rebuilt and cross-checked; derived AQI; IQR/Z-score outlier analysis (extreme pollution values are **retained**, not deleted).
3. **Load** – cleaned CSV + SQLite table + `reports/etl_report.json` (row/column counts, missing values before/after, duplicates, quality scores).

## 9. Open it on any device
* **Dashboard (the running app):** after deploying with [DEPLOY.md](DEPLOY.md) you get a public link such as `https://pakistan-air-quality.onrender.com` - open it in any phone or computer browser (on a phone: browser menu -> *Add to Home Screen*).
* **Code on a phone/tablet:** open your repository in the GitHub app or on github.com; press **.** (period) on a computer, or change `github.com` to `github.dev` in the address, for a full VS Code editor in the browser.
* **Run it in the cloud without installing anything:** repository -> green **Code** button -> **Codespaces** -> **Create codespace**. Packages install automatically; run `python backend/app.py` and open the forwarded port 5000.

## 9b. Screenshots
Add dashboard screenshots to a `screenshots/` folder.

## 10. Future work
Phase 02 and later (outside this phase): scikit-learn pipeline and PyTorch/MLflow modelling.
