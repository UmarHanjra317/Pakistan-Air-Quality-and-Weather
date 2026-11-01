
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

import config

log = logging.getLogger("aq.api")

MAX_WORKERS = 5

RAW_COLUMNS = (
    ["timestamp", "city", "latitude", "longitude"]
    + list(config.AIR_QUALITY_VARS.values())
    + list(config.WEATHER_VARS.values())
    + [
        "date",
        "hour",
        "day_of_week",
        "month",
        "month_name",
        "year",
        "is_weekend",
        "season"
    ]
)


def get_json(url: str, params: dict) -> tuple[dict, int]:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    last_error = None

    for attempt in range(1, config.API_RETRIES + 1):
        try:
            request = urllib.request.Request(
                full_url,
                headers={
                    "User-Agent": "pakistan-air-quality-dashboard/1.0"
                }
            )

            with urllib.request.urlopen(
                request,
                timeout=config.API_TIMEOUT_SECONDS
            ) as response:
                body = response.read()

            return json.loads(body), len(body)

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            last_error = f"HTTP {exc.code}: {detail}"

            if exc.code < 500 and exc.code != 429:
                break

        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            ConnectionError
        ) as exc:
            last_error = str(exc)

        if attempt < config.API_RETRIES:
            time.sleep(2 * attempt)

    raise ConnectionError(
        f"API request failed ({last_error}) for {url}"
    )


def _hourly_frame(
    url: str,
    variables: dict,
    lat: float,
    lon: float,
    window: dict
) -> tuple[pd.DataFrame, int]:

    data, size = get_json(
        url,
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(variables),
            "timezone": config.API_TIMEZONE,
            **window
        }
    )

    hourly = data.get("hourly") if isinstance(data, dict) else None

    if not hourly or "time" not in hourly:
        raise ValueError(
            f"Unexpected API response (no 'hourly.time'): {str(data)[:200]}"
        )

    frame = pd.DataFrame(hourly)
    frame["timestamp"] = pd.to_datetime(frame.pop("time"))

    return frame.rename(columns=variables), size


def _fill_weather_gaps(
    df: pd.DataFrame,
    lat: float,
    lon: float
) -> tuple[pd.DataFrame, int]:

    weather_cols = list(config.WEATHER_VARS.values())

    no_weather = df[weather_cols].isna().all(axis=1)

    last_day = (
        datetime.now(
            timezone(timedelta(hours=config.UTC_OFFSET_HOURS))
        )
        - timedelta(days=config.ARCHIVE_LAG_DAYS)
    ).date()

    if not no_weather.any():
        return df, 0

    start = df.loc[no_weather, "timestamp"].min().date()

    end = min(
        df.loc[no_weather, "timestamp"].max().date(),
        last_day
    )

    if start > end:
        return df, 0

    try:
        archive, size = _hourly_frame(
            config.WEATHER_ARCHIVE_API,
            config.WEATHER_VARS,
            lat,
            lon,
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat()
            }
        )

    except (ConnectionError, ValueError) as exc:
        log.warning(
            "Weather archive unavailable (%s) - weather stays empty for %s..%s",
            exc,
            start,
            end
        )
        return df, 0

    fill = archive.set_index("timestamp")[weather_cols].reindex(
        df["timestamp"]
    )

    fill.index = df.index

    df = df.copy()
    df[weather_cols] = df[weather_cols].fillna(fill)

    return df, size


def fetch_city(
    city: str,
    lat: float,
    lon: float,
    days: int
) -> tuple[pd.DataFrame, int]:

    window = {
        "past_days": days,
        "forecast_days": 1
    }

    air, size_a = _hourly_frame(
        config.AIR_QUALITY_API,
        config.AIR_QUALITY_VARS,
        lat,
        lon,
        window
    )

    weather, size_w = _hourly_frame(
        config.WEATHER_API,
        config.WEATHER_VARS,
        lat,
        lon,
        window
    )

    df = air.merge(
        weather,
        on="timestamp",
        how="outer"
    ).sort_values("timestamp")

    df, size_arch = _fill_weather_gaps(df, lat, lon)

    df.insert(1, "city", city)
    df.insert(2, "latitude", lat)
    df.insert(3, "longitude", lon)

    return df, size_a + size_w + size_arch


def add_calendar_fields(df: pd.DataFrame) -> pd.DataFrame:
    ts = df["timestamp"]

    df["date"] = ts.dt.normalize()
    df["hour"] = ts.dt.hour
    df["day_of_week"] = ts.dt.day_name()
    df["month"] = ts.dt.month
    df["month_name"] = ts.dt.month_name()
    df["year"] = ts.dt.year
    df["is_weekend"] = (ts.dt.dayofweek >= 5).astype(int)
    df["season"] = df["month"].map(config.SEASONS)

    return df


def fetch_all(days: int | None = None) -> tuple[pd.DataFrame, dict]:
    days = min(
        max(days or config.HISTORY_DAYS, 2),
        92
    )

    now_local = datetime.now(
        timezone(timedelta(hours=config.UTC_OFFSET_HOURS))
    ).replace(tzinfo=None)

    def one(item):
        city, (lat, lon) = item

        try:
            return city, fetch_city(city, lat, lon, days), None

        except (ConnectionError, ValueError) as exc:
            log.warning(
                "API fetch failed for %s: %s",
                city,
                exc
            )
            return city, None, str(exc)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(
            pool.map(one, config.CITIES.items())
        )

    frames = [
        res[0]
        for _, res, _ in results
        if res
    ]

    total_bytes = sum(
        res[1]
        for _, res, _ in results
        if res
    )

    errors = {
        city: err
        for city, _, err in results
        if err
    }

    if not frames:
        raise ConnectionError(
            "Could not download data for any city: "
            + "; ".join(
                f"{city}: {error}"
                for city, error in errors.items()
            )
        )

    df = pd.concat(frames, ignore_index=True)

    value_cols = (
        list(config.AIR_QUALITY_VARS.values())
        + list(config.WEATHER_VARS.values())
    )

    df = df[df["timestamp"] <= now_local]
    df = df.dropna(subset=value_cols, how="all")

    df = add_calendar_fields(df)

    return (
        df[RAW_COLUMNS].reset_index(drop=True),
        {
            "bytes": total_bytes,
            "errors": errors,
            "cities_ok": len(frames),
            "days": days
        }
    )

