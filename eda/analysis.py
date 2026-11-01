import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

import config

LABELS: dict[str, str] = {**config.POLLUTANTS, **config.WEATHER}
ANALYSIS_VARS: list[str] = list(LABELS)
DAY_ORDER = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday"
]
SEASON_ORDER = ["Winter", "Spring", "Summer", "Autumn"]


def _short(column: str) -> str:
    return LABELS.get(column, column).split(" (")[0]


def _numeric(
    df: pd.DataFrame,
    columns: list[str] | None = None
) -> pd.DataFrame:
    cols = [
        c for c in (columns or ANALYSIS_VARS)
        if c in df.columns
    ]

    return df[cols].apply(
        pd.to_numeric,
        errors="coerce"
    ).astype("float64")


def load_clean_data() -> pd.DataFrame:
    if not config.PROCESSED_PATH.exists():
        raise FileNotFoundError(
            f"{config.PROCESSED_PATH} not found - run: python etl/etl_pipeline.py"
        )

    return pd.read_csv(
        config.PROCESSED_PATH,
        parse_dates=["timestamp", "date"]
    )


def descriptive_statistics(df: pd.DataFrame) -> list[dict]:
    rows = []

    for col, values in _numeric(df).items():
        s = values.dropna()

        rows.append({
            "variable": col,
            "label": LABELS[col],
            "count": int(s.size),
            "mean": s.mean() if s.size else np.nan,
            "std": s.std() if s.size > 1 else np.nan,
            "min": s.min() if s.size else np.nan,
            "q25": s.quantile(.25) if s.size else np.nan,
            "median": s.median() if s.size else np.nan,
            "q75": s.quantile(.75) if s.size else np.nan,
            "max": s.max() if s.size else np.nan,
            "skew": s.skew() if s.size > 2 else np.nan
        })

    return rows


def missing_summary(df: pd.DataFrame) -> list[dict]:
    total = max(len(df), 1)

    return [
        {
            "column": c,
            "dtype": str(df[c].dtype),
            "missing": int(df[c].isna().sum()),
            "pct": round(100 * df[c].isna().sum() / total, 2)
        }
        for c in df.columns
    ]


def city_ranking(df: pd.DataFrame) -> pd.DataFrame:
    num = _numeric(df)
    num["city"] = df["city"].values

    rank = num.groupby("city", as_index=False).mean()

    return rank.sort_values(
        "aqi",
        ascending=False
    ).reset_index(drop=True)


def histogram(series: pd.Series, bins: int = 30) -> dict:
    s = pd.to_numeric(
        series,
        errors="coerce"
    ).dropna().astype(float)

    if s.empty:
        return {
            "labels": [],
            "counts": [],
            "mean": None,
            "median": None
        }

    counts, edges = np.histogram(s, bins=bins)

    span = float(edges[-1] - edges[0])
    digits = 0 if span >= 50 else 1 if span >= 5 else 2

    labels = [
        f"{edges[i]:.{digits}f}–{edges[i + 1]:.{digits}f}"
        for i in range(len(counts))
    ]

    return {
        "labels": labels,
        "counts": counts.tolist(),
        "mean": float(s.mean()),
        "median": float(s.median())
    }


def boxplot_stats(series: pd.Series) -> dict:
    s = pd.to_numeric(
        series,
        errors="coerce"
    ).dropna().astype(float)

    if s.empty:
        return {}

    q1, med, q3 = (
        float(x) for x in s.quantile([.25, .5, .75])
    )

    iqr = q3 - q1

    inside = s[
        (s >= q1 - 1.5 * iqr) &
        (s <= q3 + 1.5 * iqr)
    ]

    return {
        "min": float(s.min()),
        "whisker_low": float(inside.min()),
        "q1": q1,
        "median": med,
        "q3": q3,
        "whisker_high": float(inside.max()),
        "max": float(s.max()),
        "outliers": int(len(s) - len(inside))
    }


def correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    return _numeric(df).corr()


def _strength(r: float) -> str:
    a = abs(r)

    return (
        "very strong" if a >= .8
        else "strong" if a >= .6
        else "moderate" if a >= .4
        else "weak"
    )


def correlation_insights(
    corr: pd.DataFrame,
    top: int = 6
) -> list[str]:

    if corr.empty:
        return [
            "Not enough data in the current selection to compute correlations."
        ]

    notes = []

    if "aqi" in corr.columns:
        weather = [
            c for c in config.WEATHER
            if c in corr.columns
        ]

        w = corr.loc["aqi", weather].dropna()

        if not w.empty:
            best = w.abs().idxmax()
            r = float(w[best])

            notes.append(
                f"Among weather variables, {_short(best)} has a "
                f"{_strength(r)} "
                f"{'positive' if r > 0 else 'negative'} "
                f"link with AQI (r = {r:.2f})."
            )

    pairs = []
    cols = list(corr.columns)

    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            r = corr.loc[a, b]

            if pd.notna(r):
                pairs.append((abs(float(r)), float(r), a, b))

    for _, r, a, b in sorted(pairs, reverse=True)[:top]:
        note = (
            f"{_short(a)} and {_short(b)}: "
            f"{_strength(r)} "
            f"{'positive' if r > 0 else 'negative'} "
            f"correlation (r = {r:.2f})."
        )

        if {a, b} == {"aqi", "pm2_5"}:
            note += " This is expected: AQI is derived from PM2.5."

        notes.append(note)

    return notes or [
        "No correlations could be computed for the current selection."
    ]