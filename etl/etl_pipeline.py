import argparse
import json
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError

sys.path.append(str(Path(__file__).resolve().parents[1]))
import config
from etl import api_client

NUMERIC_COLS = [
    "latitude", "longitude", "pm10", "pm2_5", "carbon_monoxide", "nitrogen_dioxide",
    "sulphur_dioxide", "ozone", "dust", "temperature", "humidity", "precipitation",
    "wind_speed", "wind_direction", "pressure",
]
CATEGORICAL_COLS = ["city", "day_of_week", "month_name", "season", "aqi_category"]

PM25_BREAKPOINTS = [
    (0.0, 12.0, 0, 50),
    (12.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 150.4, 151, 200),
    (150.5, 250.4, 201, 300),
    (250.5, 500.4, 301, 500),
]
CATEGORY_BY_BAND = config.AQI_CATEGORIES
_last_full_download = 0.0
MAX_MEDIAN_FILL_SHARE = 0.05


class AirQualityRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timestamp: datetime
    city: str = Field(min_length=1)
    latitude: float = Field(ge=23.0, le=37.5)
    longitude: float = Field(ge=60.0, le=78.0)
    pm10: float = Field(ge=0, le=2000)
    pm2_5: float = Field(ge=0, le=2000)
    carbon_monoxide: float = Field(ge=0, le=50000)
    nitrogen_dioxide: float = Field(ge=0, le=1000)
    sulphur_dioxide: float = Field(ge=0, le=1000)
    ozone: float = Field(ge=0, le=1000)
    dust: float = Field(ge=0, le=5000)
    temperature: float | None = Field(default=None, ge=-60, le=60)
    humidity: float | None = Field(default=None, ge=0, le=100)
    precipitation: float | None = Field(default=None, ge=0, le=500)
    wind_speed: float | None = Field(default=None, ge=0, le=300)
    wind_direction: float | None = Field(default=None, ge=0, le=360)
    pressure: float | None = Field(default=None, ge=800, le=1100)
    hour: int = Field(ge=0, le=23)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)


def pm25_to_aqi(pm25: pd.Series) -> pd.Series:
    conc = pm25.clip(lower=0).round(1)
    aqi = pd.Series(np.nan, index=conc.index)
    for c_lo, c_hi, i_lo, i_hi in PM25_BREAKPOINTS:
        mask = (conc >= c_lo) & (conc <= c_hi)
        aqi[mask] = (i_hi - i_lo) / (c_hi - c_lo) * (conc[mask] - c_lo) + i_lo
    aqi[conc > PM25_BREAKPOINTS[-1][1]] = 500
    return aqi.round().astype("Int64")


def category_from_pm25(pm25: pd.Series) -> pd.Series:
    conc = pm25.round(1)
    bounds = [b[1] for b in PM25_BREAKPOINTS[:-1]]
    values = conc.to_numpy(dtype=float)
    idx = np.searchsorted(bounds, values, side="left")
    return pd.Series([None if np.isnan(v) else CATEGORY_BY_BAND[i] for v, i in zip(values, idx)], index=pm25.index, dtype="object")


def extract(source: str = "api", input_path: Path | None = None) -> tuple[pd.DataFrame, dict]:
    if source == "csv":
        return extract_csv(input_path or config.RAW_PATH)
    if source == "api":
        return extract_api()
    raise ValueError(f"Unknown source {source!r} (use 'api' or 'csv')")


def extract_api() -> tuple[pd.DataFrame, dict]:
    now_local = datetime.now(timezone(timedelta(hours=config.UTC_OFFSET_HOURS))).replace(tzinfo=None)
    weather_cols = list(config.WEATHER_VARS.values())

    cache = None
    if config.API_CACHE_PATH.exists():
        try:
            cache = pd.read_csv(config.API_CACHE_PATH)
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError):
            print("[EXTRACT] api_cache.csv is unreadable - rebuilding it from the API")
        if cache is not None and not set(api_client.RAW_COLUMNS).issubset(cache.columns):
            cache = None

    global _last_full_download
    days = config.HISTORY_DAYS
    if cache is not None and len(cache):
        ts = pd.to_datetime(cache["timestamp"], errors="coerce")
        newest_per_city = ts.groupby(cache["city"]).max()
        complete = set(config.CITIES) <= set(newest_per_city.index) and newest_per_city.notna().all()
        healthy = not cache[weather_cols].isna().all(axis=1).any()
        recently_repaired = time.time() - _last_full_download < 3600
        if complete and (healthy or recently_repaired):
            days = min(max((now_local - newest_per_city.min()).days + 2, 2), config.HISTORY_DAYS)
    if days >= config.HISTORY_DAYS:
        _last_full_download = time.time()

    fresh, meta = api_client.fetch_all(days)
    fresh = fresh.copy()
    fresh["timestamp"] = fresh["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    fresh["date"] = fresh["date"].dt.strftime("%Y-%m-%d")

    merged = fresh
    if cache is not None:
        try:
            key = ["city", "timestamp"]
            merged = fresh.drop_duplicates(key, keep="last").set_index(key).combine_first(
                cache.drop_duplicates(key, keep="last").set_index(key))
            merged = merged.reset_index()[list(fresh.columns)]
            for col in ("hour", "month", "year", "is_weekend"):
                merged[col] = merged[col].astype(int)
        except (KeyError, ValueError, TypeError):
            print("[EXTRACT] could not merge with the cache - using the fresh download only")
            merged = fresh
    merged = merged.drop_duplicates(subset=["city", "timestamp"], keep="last")
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=config.CACHE_MAX_DAYS)
    merged = merged[pd.to_datetime(merged["timestamp"], errors="coerce") >= cutoff]
    merged = merged.sort_values(["city", "timestamp"]).reset_index(drop=True)
    config.API_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(config.API_CACHE_PATH, index=False)

    info = {
        "dataset_name": "Open-Meteo Air Quality + Weather API",
        "file_type": "API (JSON)",
        "file_size_kb": round(meta["bytes"] / 1024, 1),
        "encoding": "UTF-8 (JSON)",
        "original_rows": int(len(merged)),
        "original_columns": int(merged.shape[1]),
        "column_names": list(merged.columns),
        "original_dtypes": {c: str(t) for c, t in merged.dtypes.items()},
        "source": f"Live Open-Meteo API - this refresh downloaded the last {meta['days']} days "
                  f"({meta['cities_ok']}/{len(config.CITIES)} cities); history is kept in a local cache",
        "mode": "api",
        "days_fetched": meta["days"],
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "city_errors": meta["errors"],
    }
    print(f"[EXTRACT] API: last {meta['days']} days, {meta['cities_ok']}/{len(config.CITIES)} cities, "
          f"{len(fresh):,} fresh rows, {len(merged):,} rows in cache")
    return merged, info


def extract_csv(input_path: Path) -> tuple[pd.DataFrame, dict]:
    if not input_path.exists():
        raise FileNotFoundError(f"Dataset not found: {input_path}")

    df, used_encoding = None, None
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(input_path, encoding=encoding)
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        raise ValueError("Could not decode the dataset with utf-8 / utf-8-sig / latin-1.")

    config.RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    if input_path.resolve() != config.RAW_PATH.resolve():
        shutil.copyfile(input_path, config.RAW_PATH)

    info = {
        "dataset_name": input_path.name,
        "file_type": input_path.suffix.lstrip(".").upper() or "UNKNOWN",
        "file_size_kb": round(input_path.stat().st_size / 1024, 1),
        "encoding": used_encoding,
        "original_rows": int(len(df)),
        "original_columns": int(df.shape[1]),
        "column_names": list(df.columns),
        "original_dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "source": "Static CSV file (hourly air-quality + weather observations)",
        "mode": "csv",
    }
    print(f"[EXTRACT] {info['original_rows']:,} rows x {info['original_columns']} columns ({used_encoding})")
    return df, info


def validate_with_pydantic(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    bad_idx, field_errors = [], {}
    for idx, record in zip(df.index, df.to_dict("records")):
        record = {k: (None if pd.isna(v) else v) for k, v in record.items()}
        try:
            AirQualityRecord.model_validate(record)
        except ValidationError as exc:
            bad_idx.append(idx)
            for err in exc.errors():
                field = str(err["loc"][0]) if err["loc"] else "unknown"
                field_errors[field] = field_errors.get(field, 0) + 1
    rejected = df.loc[bad_idx]
    valid = df.drop(index=bad_idx)
    summary = {
        "rows_checked": int(len(df)),
        "rows_valid": int(len(valid)),
        "rows_rejected": int(len(rejected)),
        "errors_by_field": field_errors,
        "rules": {name: f"{f.metadata}" for name, f in AirQualityRecord.model_fields.items() if f.metadata},
    }
    print(f"[TRANSFORM] Pydantic validation: {summary['rows_valid']:,} valid, {summary['rows_rejected']:,} rejected")
    return valid, rejected, summary


def convert_types(df: pd.DataFrame, log: list) -> pd.DataFrame:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for col in NUMERIC_COLS + ["hour", "month", "year", "is_weekend"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in CATEGORICAL_COLS:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip()
    df["city"] = df["city"].str.title()
    log.append("timestamp -> datetime; measurement columns -> numeric; text columns trimmed and cast to string")
    return df


def handle_missing(df: pd.DataFrame, log: list) -> tuple[pd.DataFrame, dict]:
    df = df.sort_values(["city", "timestamp"]).reset_index(drop=True)
    decisions = {}
    for col in NUMERIC_COLS:
        n_missing = int(df[col].isna().sum())
        if n_missing == 0:
            continue
        if col in ("latitude", "longitude"):
            df[col] = df.groupby("city")[col].transform(lambda s: s.fillna(s.mode().iloc[0] if not s.mode().empty else s))
            decisions[col] = f"{n_missing} filled with the city's coordinate"
        else:
            df[col] = df.groupby("city")[col].transform(lambda s: s.interpolate(limit=6, limit_direction="both"))
            left = int(df[col].isna().sum())
            if left / len(df) <= MAX_MEDIAN_FILL_SHARE:
                df[col] = df[col].fillna(df.groupby("city")[col].transform("median"))
                decisions[col] = f"{n_missing} filled by per-city time interpolation (max 6 h), then city median"
            else:
                decisions[col] = (f"{n_missing} missing - {n_missing - left} bridged by interpolation (max 6 h); "
                                  f"{left} long-gap values left empty (not invented)")
    for col in CATEGORICAL_COLS:
        if col not in df.columns:
            continue
        n_missing = int(df[col].isna().sum())
        if n_missing:
            df[col] = df[col].fillna(df[col].mode().iloc[0])
            decisions[col] = f"{n_missing} filled with mode"
    log.append("Missing values: " + ("; ".join(f"{k}: {v}" for k, v in decisions.items()) if decisions else "none found — no imputation required"))
    return df, decisions


def add_datetime_features(df: pd.DataFrame, log: list) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    ts = df["timestamp"]
    rebuilt = {
        "hour": ts.dt.hour, "month": ts.dt.month, "year": ts.dt.year,
        "day_of_week": ts.dt.day_name(), "month_name": ts.dt.month_name(),
    }
    mismatches = {}
    for col, series in rebuilt.items():
        mismatches[col] = int((df[col].astype(str) != series.astype(str)).sum())
        df[col] = series if col in ("hour", "month", "year") else series.astype("string")
    df["date"] = ts.dt.normalize()
    df["day"] = ts.dt.day
    df["week"] = ts.dt.isocalendar().week.astype(int)
    df["is_weekend"] = (ts.dt.dayofweek >= 5).astype(int)
    log.append("Date-time features rebuilt from timestamp (hour, day, week, month, year, day_of_week, is_weekend); added: day, week")
    return df, mismatches


def add_aqi(df: pd.DataFrame, log: list) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    df["aqi"] = pm25_to_aqi(df["pm2_5"])
    derived_cat = category_from_pm25(df["pm2_5"])
    if "aqi_category" in df.columns:
        mismatch = int((derived_cat.astype(str) != df["aqi_category"].astype(str)).sum())
        log.append("Derived numeric `aqi` from PM2.5 via US EPA breakpoints and cross-checked it against the supplied aqi_category")
    else:
        df["aqi_category"] = derived_cat.astype("string")
        mismatch = 0
        log.append("Derived numeric `aqi` and `aqi_category` from PM2.5 via US EPA breakpoints (the API supplies neither)")
    return df, {"aqi_category_mismatches_vs_pm25": mismatch}


def analyse_outliers(df: pd.DataFrame, log: list) -> list[dict]:
    rows = []
    for col in ["pm10", "pm2_5", "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide", "ozone", "dust",
                "temperature", "humidity", "precipitation", "wind_speed", "pressure"]:
        s = df[col].astype(float)
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        z = (s - s.mean()) / s.std(ddof=0)
        rows.append({
            "variable": col,
            "q1": round(q1, 2), "q3": round(q3, 2),
            "iqr_lower": round(lo, 2), "iqr_upper": round(hi, 2),
            "iqr_outliers": int(((s < lo) | (s > hi)).sum()),
            "zscore_outliers": int((z.abs() > 3).sum()),
            "max": round(s.max(), 2),
            "decision": "Retained — values lie inside the physical limits, treated as genuine extremes"
                        if col in ("pm10", "pm2_5", "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide", "ozone", "dust", "precipitation", "wind_speed")
                        else "Retained — within plausible range",
        })
    pm_gap = int((df["pm2_5"] > df["pm10"] + 0.5).sum())
    log.append(f"Outlier analysis (IQR, |z|>3) performed; none deleted. PM2.5 > PM10 inconsistencies found: {pm_gap}")
    return rows


def transform(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    log: list[str] = []
    missing_before = df_raw.isna().sum()

    dup_full = int(df_raw.duplicated().sum())
    dup_key = int(df_raw.duplicated(subset=["city", "timestamp"]).sum())
    df = df_raw.drop_duplicates().drop_duplicates(subset=["city", "timestamp"], keep="first")
    duplicates = {
        "full_row_duplicates_before": dup_full,
        "city_timestamp_duplicates_before": dup_key,
        "removed": int(len(df_raw) - len(df)),
        "remaining": int(len(df)),
    }
    log.append(f"Duplicates: {duplicates['removed']} removed ({duplicates['remaining']:,} remain)")
    print(f"[TRANSFORM] duplicates removed: {duplicates['removed']}")

    df = convert_types(df, log)

    df, missing_decisions = handle_missing(df, log)

    df, rejected, validation = validate_with_pydantic(df)
    log.append(f"Pydantic validation: {validation['rows_rejected']} invalid rows quarantined to rejected_records.csv")
    if df.empty:
        raise ValueError("No valid rows left after validation - see data/processed/rejected_records.csv")

    df, calendar_mismatches = add_datetime_features(df, log)
    df, aqi_checks = add_aqi(df, log)

    outliers = analyse_outliers(df, log)

    counts = df.groupby("city").size()
    full_range = pd.date_range(df["timestamp"].min(), df["timestamp"].max(), freq="h")
    gaps = {c: int(len(full_range) - n) for c, n in counts.items()}

    ordered = ["timestamp", "date", "city", "latitude", "longitude",
               "aqi", "aqi_category", "pm2_5", "pm10", "carbon_monoxide", "nitrogen_dioxide",
               "sulphur_dioxide", "ozone", "dust",
               "temperature", "humidity", "precipitation", "wind_speed", "wind_direction", "pressure",
               "year", "month", "month_name", "day", "week", "day_of_week", "hour", "is_weekend", "season"]
    df = df[ordered].sort_values(["city", "timestamp"]).reset_index(drop=True)

    details = {
        "missing_before": {c: int(v) for c, v in missing_before.items()},
        "missing_before_total": int(missing_before.sum()),
        "missing_after": {c: int(v) for c, v in df.isna().sum().items()},
        "missing_after_total": int(df.isna().sum().sum()),
        "missing_decisions": missing_decisions,
        "duplicates": duplicates,
        "validation": validation,
        "calendar_feature_mismatches_fixed": calendar_mismatches,
        "aqi_checks": aqi_checks,
        "outliers": outliers,
        "missing_hours_per_city": gaps,
        "type_conversions": {c: str(t) for c, t in df.dtypes.items()},
        "transformations": log,
    }
    return df, rejected, details


def load(df: pd.DataFrame, rejected: pd.DataFrame) -> dict:
    config.PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.PROCESSED_PATH, index=False)
    if len(rejected):
        rejected.to_csv(config.REJECTED_PATH, index=False)
    elif config.REJECTED_PATH.exists():
        config.REJECTED_PATH.unlink()

    db_df = df.copy()
    db_df["timestamp"] = db_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    db_df["date"] = db_df["date"].dt.strftime("%Y-%m-%d")
    with sqlite3.connect(config.DB_PATH) as conn:
        db_df.to_sql(config.DB_TABLE, conn, if_exists="replace", index=False)
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_city_ts ON {config.DB_TABLE}(city, timestamp)")
        db_rows = conn.execute(f"SELECT COUNT(*) FROM {config.DB_TABLE}").fetchone()[0]
    print(f"[LOAD] {len(df):,} rows -> {config.PROCESSED_PATH.name} and SQLite table '{config.DB_TABLE}' ({db_rows:,} rows)")
    return {
        "final_rows": int(len(df)),
        "final_columns": int(df.shape[1]),
        "processed_csv": str(config.PROCESSED_PATH.relative_to(config.BASE_DIR)),
        "database": str(config.DB_PATH.relative_to(config.BASE_DIR)),
        "database_table": config.DB_TABLE,
        "database_rows_verified": int(db_rows),
        "clean_dataset_status": "Ready" if db_rows == len(df) else "Check required",
    }


def quality_scores(info: dict, details: dict, loaded: dict) -> dict:
    cells_before = info["original_rows"] * info["original_columns"]
    completeness = 100 * (1 - details["missing_before_total"] / cells_before)
    validity = 100 * details["validation"]["rows_valid"] / max(details["validation"]["rows_checked"], 1)
    uniqueness = 100 * (1 - details["duplicates"]["removed"] / info["original_rows"])
    overall = float(np.mean([completeness, validity, uniqueness]))
    return {
        "completeness_pct": round(completeness, 2),
        "validity_pct": round(validity, 2),
        "uniqueness_pct": round(uniqueness, 2),
        "overall_quality_pct": round(overall, 2),
        "rows_retained_pct": round(100 * loaded["final_rows"] / info["original_rows"], 2),
    }


def run(source: str = "api", input_path: Path | None = None) -> dict:
    raw_df, extract_info = extract(source, input_path)
    clean_df, rejected, details = transform(raw_df)
    loaded = load(clean_df, rejected)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extract": extract_info,
        "transform": details,
        "load": loaded,
        "quality": quality_scores(extract_info, details, loaded),
        "date_range": {"start": str(clean_df["timestamp"].min()), "end": str(clean_df["timestamp"].max())},
        "cities": sorted(clean_df["city"].unique().tolist()),
    }
    config.ETL_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.ETL_REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[REPORT] {config.ETL_REPORT_PATH}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Phase-01 ETL pipeline")
    parser.add_argument("--source", choices=["api", "csv"], default="api", help="Where to extract data from (default: live API)")
    parser.add_argument("--input", type=Path, default=config.RAW_PATH, help="CSV path (only used with --source csv)")
    args = parser.parse_args()
    run(args.source, args.input)
