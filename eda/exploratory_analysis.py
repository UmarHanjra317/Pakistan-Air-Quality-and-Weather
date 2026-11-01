
import base64
import io
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

import config
from eda import analysis as an

plt.rcParams.update({
    "figure.dpi": 100,
    "axes.spines.top": False,
    "axes.spines.right": False
})

BLUE = "#1769aa"


def fig_to_html(fig, title: str, note: str = "") -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    img = base64.b64encode(buf.getvalue()).decode()

    return (
        f'<section><h3>{title}</h3>'
        f'<img src="data:image/png;base64,{img}"/>'
        f'<p class="note">{note}</p></section>'
    )


def table_html(df) -> str:
    return df.to_html(
        index=False,
        float_format=lambda v: f"{v:,.2f}",
        classes="tbl",
        border=0
    )


def build_sections(df) -> list[str]:
    sections = []

    overview = (
        f"<p><b>{len(df):,}</b> records · "
        f"<b>{df.shape[1]}</b> features · "
        f"<b>{df['city'].nunique()}</b> cities · "
        f"{df['timestamp'].min():%d %b %Y} to "
        f"{df['timestamp'].max():%d %b %Y}</p>"
    )

    sections.append(
        f"<section><h3>Dataset overview</h3>{overview}</section>"
    )

    sections.append(
        "<section><h3>Descriptive statistics</h3>"
        + table_html(
            pd.DataFrame(
                an.descriptive_statistics(df)
            ).drop(columns=["variable"])
        )
        + "</section>"
    )

    fig, axes = plt.subplots(2, 4, figsize=(15, 6))

    for ax, col in zip(axes.ravel(), config.POLLUTANTS):
        ax.hist(df[col].dropna(), bins=40, color=BLUE, alpha=0.85)
        ax.set_title(an.LABELS[col], fontsize=9)

    fig.tight_layout()

    sections.append(
        fig_to_html(
            fig,
            "Pollutant distributions",
            "Pollutant concentrations are right-skewed: most hours are moderate, with a long tail of severe episodes."
        )
    )

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))

    for ax, col in zip(axes, ["pm2_5", "pm10"]):
        order = df.groupby("city")[col].median().sort_values().index
        ax.boxplot([df.loc[df.city == c, col] for c in order])
        ax.set_xticks(range(1, len(order) + 1))
        ax.set_xticklabels(order)
        ax.set_title(f"{an.LABELS[col]} by city")
        ax.tick_params(axis="x", rotation=45)

    fig.tight_layout()

    sections.append(
        fig_to_html(
            fig,
            "PM2.5 and PM10 by city (box plots)",
            "Points beyond the whiskers are retained: they are genuine pollution episodes, not data errors."
        )
    )

    rank = an.city_ranking(df)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(rank["city"][::-1], rank["aqi"][::-1], color=BLUE)
    ax.set_xlabel("Mean AQI (derived from PM2.5)")

    sections.append(
        fig_to_html(
            fig,
            "Mean AQI by city",
            f"Highest: {rank.iloc[0]['city']} ({rank.iloc[0]['aqi']:.0f}); "
            f"lowest: {rank.iloc[-1]['city']} ({rank.iloc[-1]['aqi']:.0f})."
        )
    )

    sections.append(
        "<section><h3>City comparison table (means)</h3>"
        + table_html(rank)
        + "</section>"
    )

    fig, ax = plt.subplots(figsize=(12, 4))

    daily = df.groupby("date")["aqi"].mean()
    ax.plot(daily.index, daily.values, color=BLUE, lw=1.2)

    for city in ["Lahore"] if "Lahore" in df.city.values else []:
        d = df[df.city == city].groupby("date")["aqi"].mean()
        ax.plot(
            d.index,
            d.values,
            color="#c62828",
            lw=1.2,
            label=city
        )

    ax.plot([], [], color=BLUE, label="All cities")
    ax.legend()
    ax.set_ylabel("Daily mean AQI")

    sections.append(
        fig_to_html(
            fig,
            "Daily AQI trend",
            "Daily mean AQI across all cities (and Lahore where present)."
        )
    )

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    h = df.groupby("hour")["aqi"].mean()
    axes[0].plot(h.index, h.values, marker="o", color=BLUE)
    axes[0].set_title("Mean AQI by hour")

    m = df.groupby(["year", "month"])["aqi"].mean()
    axes[1].bar(
        [f"{y}-{mo:02d}" for y, mo in m.index],
        m.values,
        color=BLUE
    )
    axes[1].set_title("Mean AQI by month")

    d = df.groupby("day_of_week")["aqi"].mean().reindex(an.DAY_ORDER)
    axes[2].bar(d.index.str[:3], d.values, color=BLUE)
    axes[2].set_title("Mean AQI by weekday")

    fig.tight_layout()

    sections.append(
        fig_to_html(
            fig,
            "Temporal patterns of AQI",
            "Hourly, monthly and weekday averages of AQI."
        )
    )

    fig, axes = plt.subplots(2, 3, figsize=(15, 6))

    for ax, col in zip(axes.ravel(), config.WEATHER):
        ax.hist(
            df[col].dropna(),
            bins=35,
            color="#2e7d32",
            alpha=0.85
        )
        ax.set_title(an.LABELS[col], fontsize=9)

    fig.tight_layout()

    sections.append(
        fig_to_html(
            fig,
            "Weather variable distributions",
            "Distribution of the six weather variables in the dataset."
        )
    )

    corr = an.correlation_matrix(df)

    fig, ax = plt.subplots(figsize=(10, 8))

    im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)

    ax.set_xticks(range(len(corr)))
    ax.set_xticklabels(
        corr.columns,
        rotation=60,
        ha="right",
        fontsize=8
    )

    ax.set_yticks(range(len(corr)))
    ax.set_yticklabels(corr.columns, fontsize=8)

    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(
                j,
                i,
                f"{corr.iloc[i, j]:.2f}",
                ha="center",
                va="center",
                fontsize=6
            )

    fig.colorbar(im, shrink=0.8)

    insights = "".join(
        f"<li>{t}</li>"
        for t in an.correlation_insights(corr)
    )

    sections.append(
        fig_to_html(fig, "Correlation matrix", "")
        + f"<section><h3>Automatic insights</h3><ul>{insights}</ul></section>"
    )

    return sections


def main():
    df = an.load_clean_data()

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>EDA Report</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;max-width:1100px;margin:auto;padding:24px;background:#f4f8fb;color:#1c2b36}}
section{{background:#fff;border-radius:10px;padding:16px 20px;margin:16px 0;box-shadow:0 1px 4px #0001}}
img{{max-width:100%}}
.note{{color:#51606b;font-size:14px}}
.tbl{{border-collapse:collapse;font-size:12px;width:100%}}
.tbl td,.tbl th{{padding:4px 8px;border-bottom:1px solid #e3eaf0;text-align:right}}
h1{{color:#0d47a1}}
</style>
</head>
<body>
<h1>Pakistan Air Quality and Weather — EDA Report</h1>
<p>Phase 01 · generated {datetime.now():%d %b %Y %H:%M} from <code>data/processed/cleaned_dataset.csv</code></p>
{''.join(build_sections(df))}
</body>
</html>"""

    config.EDA_REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    config.EDA_REPORT_PATH.write_text(
        html,
        encoding="utf-8"
    )

    print(f"EDA report written to {config.EDA_REPORT_PATH}")


if __name__ == "__main__":
    main()