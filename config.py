import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


RAW_PATH = BASE_DIR / "data" / "raw" / "original_dataset.csv"
API_CACHE_PATH = BASE_DIR / "data" / "raw" / "api_cache.csv"
PROCESSED_PATH = BASE_DIR / "data" / "processed" / "cleaned_dataset.csv"
REJECTED_PATH = BASE_DIR / "data" / "processed" / "rejected_records.csv"
DB_PATH = BASE_DIR / "data" / "processed" / "air_quality.db"
DB_TABLE = "air_quality"
ETL_REPORT_PATH = BASE_DIR / "reports" / "etl_report.json"
EDA_REPORT_PATH = BASE_DIR / "reports" / "eda_report.html"
FRONTEND_DIR = BASE_DIR / "frontend"

AIR_QUALITY_API = os.getenv(
    "AIR_QUALITY_API_URL",
    "https://air-quality-api.open-meteo.com/v1/air-quality"
)
WEATHER_API = os.getenv(
    "WEATHER_API_URL",
    "https://api.open-meteo.com/v1/forecast"
)
WEATHER_ARCHIVE_API = os.getenv(
    "WEATHER_ARCHIVE_API_URL",
    "https://archive-api.open-meteo.com/v1/archive"
)

ARCHIVE_LAG_DAYS = 5
API_TIMEZONE = "Asia/Karachi"
UTC_OFFSET_HOURS = 5
API_TIMEOUT_SECONDS = 30
API_RETRIES = 3

HISTORY_DAYS = min(_env_int("HISTORY_DAYS", 90), 92)
CACHE_MAX_DAYS = _env_int("CACHE_MAX_DAYS", 365)
REFRESH_MINUTES = max(_env_int("REFRESH_MINUTES", 15), 5)
REFRESH_MIN_INTERVAL_SECONDS = _env_int("REFRESH_MIN_INTERVAL_SECONDS", 60)

CITIES = {
    "Faisalabad": (31.4504, 73.1350),
    "Islamabad": (33.6844, 73.0479),
    "Karachi": (24.8607, 67.0011),
    "Lahore": (31.5497, 74.3436),
    "Multan": (30.1575, 71.5249),
    "Peshawar": (34.0151, 71.5249),
    "Quetta": (30.1798, 66.9750),
    "Rahim Yar Khan": (28.4202, 70.2952),
    "Rawalpindi": (33.5651, 73.0169),
    "Sialkot": (32.4945, 74.5229),
}

AIR_QUALITY_VARS = {
    "pm10": "pm10",
    "pm2_5": "pm2_5",
    "carbon_monoxide": "carbon_monoxide",
    "nitrogen_dioxide": "nitrogen_dioxide",
    "sulphur_dioxide": "sulphur_dioxide",
    "ozone": "ozone",
    "dust": "dust",
}

WEATHER_VARS = {
    "temperature_2m": "temperature",
    "relative_humidity_2m": "humidity",
    "precipitation": "precipitation",
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_direction",
    "pressure_msl": "pressure",
}

SEASONS = {
    12: "Winter",
    1: "Winter",
    2: "Winter",
    3: "Spring",
    4: "Spring",
    5: "Spring",
    6: "Summer",
    7: "Summer",
    8: "Summer",
    9: "Autumn",
    10: "Autumn",
    11: "Autumn",
}

POLLUTANTS = {
    "aqi": "AQI (derived from PM2.5)",
    "pm2_5": "PM2.5 (µg/m³)",
    "pm10": "PM10 (µg/m³)",
    "carbon_monoxide": "CO (µg/m³)",
    "nitrogen_dioxide": "NO₂ (µg/m³)",
    "sulphur_dioxide": "SO₂ (µg/m³)",
    "ozone": "O₃ (µg/m³)",
    "dust": "Dust (µg/m³)",
}

WEATHER = {
    "temperature": "Temperature (°C)",
    "humidity": "Humidity (%)",
    "precipitation": "Precipitation (mm)",
    "wind_speed": "Wind speed (km/h)",
    "wind_direction": "Wind direction (°)",
    "pressure": "Pressure (hPa)",
}

AQI_CATEGORIES = [
    "Good",
    "Moderate",
    "Unhealthy for Sensitive Groups",
    "Unhealthy",
    "Very Unhealthy",
    "Hazardous",
]
