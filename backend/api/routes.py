import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Blueprint, abort, jsonify, request

sys.path.append(str(Path(__file__).resolve().parents[2]))
import config
from backend.data_store import store
from eda import analysis as an

api = Blueprint("api", __name__, url_prefix="/api")


@api.before_request
def auto_refresh():
    if request.endpoint != "api.refresh":
        store.maybe_refresh()


@api.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@api.errorhandler(400)
def bad_request(err):
    return jsonify({"error": err.description}), 400


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return round(float(value), 3) if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m-%d %H:%M")
    return value


def ok(payload):
    return jsonify(clean(payload))


def int_arg(name: str, default: int, low: int | None = None, high: int | None = None) -> int:
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        abort(400, f"'{name}' must be a whole number, got {raw!r}")
    if low is not None:
        value = max(value, low)
    if high is not None:
        value = min(value, high)
    return value


def date_arg(name: str):
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        return pd.to_datetime(raw)
    except (ValueError, TypeError):
        abort(400, f"'{name}' must be a date like 2026-01-31, got {raw!r}")


def filtered(apply_city: bool = True) -> pd.DataFrame:
    df = store.df
    city = request.args.get("city", "all")
    if apply_city and city != "all":
        df = df[df["city"].isin(city.split(","))]
    start, end = date_arg("start"), date_arg("end")
    if start is not None:
        df = df[df["date"] >= start]
    if end is not None:
        df = df[df["date"] <= end]
    if request.args.get("year", "all") != "all":
        df = df[df["year"] == int_arg("year", 0)]
    if request.args.get("month", "all") != "all":
        df = df[df["month"] == int_arg("month", 0)]
    return df


def variable() -> str:
    var = request.args.get("var", "aqi")
    return var if var in an.ANALYSIS_VARS else "aqi"


@api.get("/status")
def status():
    return ok(store.status())


@api.post("/refresh")
def refresh():
    wait = request.args.get("wait") == "1"
    if store.refreshing:
        if not wait:
            return ok({"status": "already_running"}), 202
        deadline = time.time() + 150
        while store.refreshing and time.time() < deadline:
            time.sleep(1)
        return ok({"status": "failed" if store.last_error else "ok", **store.status()}), (502 if store.last_error else 200)
    since = time.time() - store.last_attempt
    if since < config.REFRESH_MIN_INTERVAL_SECONDS:
        return ok({"status": "throttled", "retry_after_seconds": round(config.REFRESH_MIN_INTERVAL_SECONDS - since)}), 429
    if wait:
        store.refresh_blocking()
        return ok({"status": "ok" if not store.last_error else "failed", **store.status()}), (200 if not store.last_error else 502)
    store.start_refresh()
    return ok({"status": "started"}), 202


@api.get("/meta")
def meta():
    df = store.df
    months = df.drop_duplicates(["year", "month"]).sort_values(["year", "month"])[["month", "month_name"]]
    return ok({
        "cities": sorted(df["city"].unique()),
        "date_min": df["date"].min().strftime("%Y-%m-%d"),
        "date_max": df["date"].max().strftime("%Y-%m-%d"),
        "years": sorted(df["year"].unique().tolist()),
        "months": months.to_dict("records"),
        "pollutants": config.POLLUTANTS, "weather": config.WEATHER,
        "columns": store.columns, "has_lahore": "Lahore" in df["city"].values,
        "aqi_categories": config.AQI_CATEGORIES,
    })


@api.get("/etl")
def etl():
    return ok(store.etl_report)


@api.get("/summary")
def summary():
    df = filtered()
    if df.empty:
        return ok({"records": 0})
    missing = int(df.isna().sum().sum())
    return ok({
        "records": len(df), "cities": df["city"].nunique(), "features": df.shape[1],
        "avg_aqi": df["aqi"].mean(), "max_aqi": df["aqi"].max(),
        "avg_pm25": df["pm2_5"].mean(), "avg_pm10": df["pm10"].mean(),
        "avg_temp": df["temperature"].mean(), "avg_humidity": df["humidity"].mean(),
        "missing_values": missing,
        "data_quality": store.etl_report["quality"]["overall_quality_pct"],
        "worst_city": df.groupby("city")["aqi"].mean().idxmax(),
        "best_city": df.groupby("city")["aqi"].mean().idxmin(),
        "unhealthy_share": 100 * df["aqi"].ge(151).mean(),
    })


@api.get("/stats")
def stats():
    df = filtered()
    return ok({"stats": an.descriptive_statistics(df) if len(df) else [], "missing": an.missing_summary(df)})


@api.get("/timeseries")
def timeseries():
    df, var = filtered(), variable()
    by_city = request.args.get("by_city") == "1"
    if df.empty:
        return ok({"labels": [], "series": {}} if by_city else {"labels": [], "values": []})
    if request.args.get("freq") == "week":


        key = df["date"] - pd.to_timedelta(df["date"].dt.dayofweek, unit="D")
    else:
        key = df["date"]
    if by_city:
        pivot = df.groupby([key, df["city"]])[var].mean().unstack("city")
        return ok({"labels": [str(i)[:10] for i in pivot.index],
                   "series": {c: pivot[c].tolist() for c in pivot.columns}})
    s = df.groupby(key)[var].mean()
    return ok({"labels": [str(i)[:10] for i in s.index], "values": s.tolist()})


@api.get("/by_city")
def by_city():
    df = filtered(apply_city=False)
    rank = an.city_ranking(df) if len(df) else pd.DataFrame()
    return ok({"cities": rank.to_dict("records")})


@api.get("/distribution")
def distribution():
    df, var = filtered(), variable()
    if df.empty:
        return ok({"labels": [], "counts": []})
    return ok({**an.histogram(df[var]), "box": an.boxplot_stats(df[var])})


@api.get("/categories")
def categories():
    df = filtered()
    counts = df["aqi_category"].value_counts().reindex(config.AQI_CATEGORIES).fillna(0)
    return ok({"labels": list(counts.index), "counts": counts.tolist()})


@api.get("/temporal")
def temporal():
    df, var = filtered(), variable()
    by = request.args.get("by", "hour")
    if by == "hour":
        s = df.groupby("hour")[var].mean()
    elif by == "month":
        s = df.groupby(["year", "month", "month_name"])[var].mean()
        s.index = [f"{n[:3]} {y}" for y, _, n in s.index]
    elif by == "dow":
        s = df.groupby("day_of_week")[var].mean().reindex(an.DAY_ORDER)
    elif by == "season":
        s = df.groupby("season")[var].mean().reindex(an.SEASON_ORDER)
    elif by == "weekend":
        s = df.groupby("is_weekend")[var].mean()
        s.index = ["Weekday" if i == 0 else "Weekend" for i in s.index]
    else:
        s = df.groupby("year")[var].mean()
    s = s.dropna()
    return ok({"labels": [str(i) for i in s.index], "values": s.tolist()})


@api.get("/correlation")
def correlation():
    df = filtered()
    corr = an.correlation_matrix(df)
    return ok({"columns": list(corr.columns), "matrix": corr.values.tolist(),
               "insights": an.correlation_insights(corr)})


@api.get("/scatter")
def scatter():
    df, var = filtered(), variable()
    sample = df.sample(min(800, len(df)), random_state=1) if len(df) else df
    return ok({"x": sample[var].tolist(), "y": sample["aqi"].tolist()})


@api.get("/records")
def records():
    df = filtered()
    table_columns = store.columns
    search = request.args.get("search", "").strip().lower()
    if search:
        text_cols = ["city", "season", "aqi_category", "month_name", "day_of_week"]
        mask = pd.Series(False, index=df.index)
        for col in text_cols:
            mask |= df[col].astype(str).str.lower().str.contains(search, regex=False)
        mask |= df["timestamp"].dt.strftime("%Y-%m-%d %H:%M").str.contains(search, regex=False)
        df = df[mask]
    sort = request.args.get("sort", "timestamp")
    if sort in table_columns:
        df = df.sort_values(sort, ascending=request.args.get("dir", "asc") == "asc")
    cols = [c for c in request.args.get("cols", "").split(",") if c in table_columns] or table_columns
    size = int_arg("size", 25, 5, 100)
    page = int_arg("page", 1, 1)
    chunk = df.iloc[(page - 1) * size: page * size][cols].copy()
    for c in chunk.select_dtypes("datetime").columns:
        chunk[c] = chunk[c].dt.strftime("%Y-%m-%d %H:%M" if c == "timestamp" else "%Y-%m-%d")
    chunk = chunk.astype(object).where(chunk.notna(), None)
    return ok({"total": len(df), "page": page, "size": size, "columns": cols, "rows": chunk.values.tolist()})