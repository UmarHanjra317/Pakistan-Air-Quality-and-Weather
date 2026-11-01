
"use strict";

const COLORS = {
  primary: "#1769aa",
  accent: "#00a6a6",
  green: "#2e9e5b",
  red: "#d9382f",
  orange: "#f28c28",
  purple: "#8e3b9c"
};

const CAT_COLORS = ["#2e9e5b", "#e6b800", "#f28c28", "#d9382f", "#8e3b9c", "#6d1b2b"];
const CITY_PALETTE = ["#1769aa", "#d9382f", "#2e9e5b", "#f28c28", "#8e3b9c", "#00a6a6", "#795548", "#e91e63", "#607d8b", "#9ccc65"];
const DEFAULT_COLS = ["timestamp", "city", "aqi", "aqi_category", "pm2_5", "pm10", "temperature", "humidity", "wind_speed"];

let lastRefresh = null;

const state = {
  meta: null,
  page: "dashboard",
  charts: {},
  table: {
    page: 1,
    sort: "timestamp",
    dir: "asc",
    cols: [...DEFAULT_COLS]
  }
};

const $ = (id) => document.getElementById(id);

const fmt = (n, d = 1) =>
  n === null || n === undefined || Number.isNaN(n)
    ? "—"
    : Number(n).toLocaleString(undefined, { maximumFractionDigits: d });

const short = (label) => label.split(" (")[0];

const label = (key) => ({ ...state.meta.pollutants, ...state.meta.weather }[key] || key);

function filterParams(extra = {}) {
  const p = new URLSearchParams({
    city: $("fCity").value,
    start: $("fStart").value,
    end: $("fEnd").value,
    year: $("fYear").value,
    month: $("fMonth").value,
    ...extra
  });

  return p.toString();
}

async function api(path, extra = {}) {
  const res = await fetch(`/api/${path}?${filterParams(extra)}`);

  if (!res.ok) {
    throw new Error(`${path}: ${res.status}`);
  }

  return res.json();
}

function chart(id, type, data, options = {}, aspect = 2) {
  if (state.charts[id]) {
    state.charts[id].destroy();
  }

  state.charts[id] = new Chart($(id), {
    type,
    data,
    options: {
      responsive: true,
      aspectRatio: aspect,
      plugins: {
        legend: {
          display: (data.datasets || []).length > 1 || type === "doughnut"
        }
      },
      ...options
    }
  });
}

function line(id, labels, values, name, color = COLORS.primary, aspect = 2.4) {
  chart(
    id,
    "line",
    {
      labels,
      datasets: [{
        label: name,
        data: values,
        borderColor: color,
        backgroundColor: color + "22",
        fill: true,
        pointRadius: 0,
        borderWidth: 1.8,
        tension: 0.25
      }]
    },
    {
      scales: {
        x: {
          ticks: {
            maxTicksLimit: 10
          }
        }
      }
    },
    aspect
  );
}

function bar(id, labels, values, name, color = COLORS.primary, horizontal = false, aspect = 2) {
  chart(
    id,
    "bar",
    {
      labels,
      datasets: [{
        label: name,
        data: values,
        backgroundColor: color
      }]
    },
    {
      indexAxis: horizontal ? "y" : "x"
    },
    aspect
  );
}

function table(id, headers, rows) {
  $(id).innerHTML =
    `<thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>` +
    `<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody>`;
}

function kv(id, pairs) {
  $(id).innerHTML = pairs.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
}

const aqiInfo = (v) => {
  const bands = [
    [50, "Good", 0],
    [100, "Moderate", 1],
    [150, "Unhealthy for Sensitive Groups", 2],
    [200, "Unhealthy", 3],
    [300, "Very Unhealthy", 4],
    [Infinity, "Hazardous", 5]
  ];

  const b = bands.find((x) => v <= x[0]);

  return {
    name: b[1],
    color: CAT_COLORS[b[2]]
  };
};

const catBadge = (name) =>
  `<span class="badge" style="background:${CAT_COLORS[state.meta.aqi_categories.indexOf(name)] || "#888"}">${name}</span>`;

async function renderDashboard() {
  const s = await api("summary");

  const avgInfo = aqiInfo(s.avg_aqi || 0);
  const maxInfo = aqiInfo(s.max_aqi || 0);

  const cards = [
    ["Total records", fmt(s.records, 0), `${s.features || "—"} features`, COLORS.primary],
    ["Cities", fmt(s.cities, 0), `Highest AQI: ${s.worst_city || "—"}`, COLORS.accent],
    ["Average AQI", fmt(s.avg_aqi, 0), avgInfo.name, avgInfo.color],
    ["Maximum AQI", fmt(s.max_aqi, 0), maxInfo.name, maxInfo.color],
    ["Average PM2.5", fmt(s.avg_pm25), "µg/m³", COLORS.orange],
    ["Average PM10", fmt(s.avg_pm10), "µg/m³", COLORS.purple],
    ["Missing values", fmt(s.missing_values, 0), "in the processed data", COLORS.green],
    ["Data quality", `${fmt(s.data_quality, 1)}%`, "completeness · validity · uniqueness", COLORS.green]
  ];

  $("summaryCards").innerHTML = cards
    .map(([t, v, sub, c]) => `<div class="card" style="border-left-color:${c}"><small>${t}</small><b>${v}</b><span>${sub}</span></div>`)
    .join("");

  if (!s.records) return;

  const v = $("fVar").value;

  const [aqi, sel, pm25, pm10, cats, byCity, month, season] = await Promise.all([
    api("timeseries", { var: "aqi" }),
    api("timeseries", { var: v }),
    api("timeseries", { var: "pm2_5" }),
    api("timeseries", { var: "pm10" }),
    api("categories"),
    api("by_city"),
    api("temporal", { by: "month", var: "aqi" }),
    api("temporal", { by: "season", var: "aqi" })
  ]);

  line("cAqiTrend", aqi.labels, aqi.values, "Daily mean AQI", COLORS.primary, 3.2);

  $("tSelTrend").textContent = `${label(v)} — daily mean`;

  line("cSelTrend", sel.labels, sel.values, label(v), COLORS.accent);

  chart(
    "cCategories",
    "doughnut",
    {
      labels: cats.labels,
      datasets: [{
        data: cats.counts,
        backgroundColor: CAT_COLORS
      }]
    },
    {
      plugins: {
        legend: {
          position: "right"
        }
      }
    },
    1.8
  );

  line("cPm25", pm25.labels, pm25.values, "PM2.5", COLORS.orange);
  line("cPm10", pm10.labels, pm10.values, "PM10", COLORS.purple);

  bar(
    "cCityAqi",
    byCity.cities.map((c) => c.city),
    byCity.cities.map((c) => c.aqi),
    "Mean AQI",
    COLORS.primary,
    true
  );

  bar("cMonthAqi", month.labels, month.values, "Mean AQI", COLORS.red);
  bar("cSeason", season.labels, season.values, "Mean AQI", COLORS.green);
}

async function renderEtl() {
  const r = await (await fetch("/api/etl")).json();

  const t = r.transform;
  const e = r.extract;
  const l = r.load;
  const q = r.quality;

  $("etlFlow").innerHTML = [
    ["Extract", `${fmt(e.original_rows, 0)} rows`, `${e.original_columns} columns · ${e.file_type}`],
    ["Transform", `${t.duplicates.removed} duplicates · ${t.validation.rows_rejected} invalid`, `${t.missing_before_total} missing values handled`],
    ["Load", `${fmt(l.final_rows, 0)} rows`, `${l.final_columns} columns · ${l.clean_dataset_status}`]
  ]
    .map(([a, b, c], i) => `<div class="step"><small>Step ${i + 1} · ${a}</small><b>${b}</b><span class="note">${c}</span></div>`)
    .join("");

  kv("etlExtract", [
    ["Dataset", e.dataset_name],
    ["File type", e.file_type],
    ["Size", `${fmt(e.file_size_kb)} KB`],
    ["Encoding", e.encoding],
    ["Original rows", fmt(e.original_rows, 0)],
    ["Original columns", e.original_columns],
    ["Source", e.source]
  ]);

  kv("etlTransform", [
    ["Missing values (before → after)", `${t.missing_before_total} → ${t.missing_after_total}`],
    ["Full-row duplicates found", t.duplicates.full_row_duplicates_before],
    ["City+timestamp duplicates", t.duplicates.city_timestamp_duplicates_before],
    ["Duplicates removed", t.duplicates.removed],
    ["Rows failing validation", t.validation.rows_rejected],
    ["Calendar-feature mismatches fixed", Object.values(t.calendar_feature_mismatches_fixed).reduce((a, b) => a + b, 0)],
    ["AQI category vs PM2.5 mismatches", t.aqi_checks.aqi_category_mismatches_vs_pm25],
    ["Missing hourly records (all cities)", Object.values(t.missing_hours_per_city).reduce((a, b) => a + b, 0)]
  ]);

  kv("etlLoad", [
    ["Final rows", fmt(l.final_rows, 0)],
    ["Final columns", l.final_columns],
    ["Clean CSV", l.processed_csv],
    ["Database", l.database],
    ["DB table / rows verified", `${l.database_table} / ${fmt(l.database_rows_verified, 0)}`],
    ["Status", `<span class="badge" style="background:#2e9e5b">${l.clean_dataset_status}</span>`],
    ["Date range", `${r.date_range.start.slice(0, 10)} → ${r.date_range.end.slice(0, 10)}`]
  ]);

  $("etlQuality").innerHTML = [
    ["Completeness", q.completeness_pct],
    ["Validity (Pydantic)", q.validity_pct],
    ["Uniqueness", q.uniqueness_pct],
    ["Overall quality", q.overall_quality_pct],
    ["Rows retained", q.rows_retained_pct]
  ]
    .map(([n, v]) => `<div class="bar"><b>${n}</b> — ${fmt(v, 2)}%<div class="track"><div class="fill" style="width:${v}%"></div></div></div>`)
    .join("");

  $("etlLog").innerHTML = t.transformations.map((x) => `<li>${x}</li>`).join("");

  table(
    "etlRules",
    ["Field", "Rule"],
    Object.entries(t.validation.rules).map(([k, v]) => [
      k,
      v.replace(/Ge\(ge=/g, "≥ ")
        .replace(/Le\(le=/g, "≤ ")
        .replace(/(?:Min)?Len\(min_length=(\d+)\)/, "min length $1")
        .replace(/\)/g, "")
        .replace(/[\[\]]/g, "")
    ])
  );

  table(
    "etlOutliers",
    ["Variable", "Q1", "Q3", "IQR lower", "IQR upper", "IQR outliers", "|z|>3", "Max", "Decision"],
    t.outliers.map((o) => [
      o.variable,
      o.q1,
      o.q3,
      o.iqr_lower,
      o.iqr_upper,
      fmt(o.iqr_outliers, 0),
      fmt(o.zscore_outliers, 0),
      o.max,
      `<span style="white-space:normal">${o.decision}</span>`
    ])
  );

  table(
    "etlMissing",
    ["Column", "Original dtype", "Final dtype", "Missing before", "Missing after"],
    Object.keys(t.missing_after).map((c) => [
      c,
      e.original_dtypes[c] || "<i>derived</i>",
      t.type_conversions[c],
      e.original_dtypes[c] ? t.missing_before[c] : "—",
      t.missing_after[c]
    ])
  );
}

function renderHeatmap(corr) {
  const n = corr.columns.length;
  const el = $("heatmap");

  el.style.gridTemplateColumns = `auto repeat(${n}, minmax(44px, 1fr))`;

  let html = `<div class="hl"></div>` +
    corr.columns.map((c) => `<div class="ht">${short(label(c)).replace("PM2.5", "PM2.5")}</div>`).join("");

  corr.matrix.forEach((row, i) => {
    html += `<div class="hl">${short(label(corr.columns[i]))}</div>`;

    row.forEach((r) => {
      const a = r === null ? 0 : Math.abs(r);
      const bg = r === null
        ? "#eee"
        : r >= 0
          ? `rgba(23,105,170,${a})`
          : `rgba(217,56,47,${a})`;

      html += `<div style="background:${bg};color:${a > 0.55 ? "#fff" : "#1c2b36"}" title="r = ${fmt(r, 3)}">${r === null ? "—" : r.toFixed(2)}</div>`;
    });
  });

  el.innerHTML = html;
}

async function renderEda() {
  const v = $("fVar").value;

  const [stats, dist, hour, dow, wk, corr] = await Promise.all([
    api("stats"),
    api("distribution", { var: v }),
    api("temporal", { by: "hour", var: v }),
    api("temporal", { by: "dow", var: v }),
    api("temporal", { by: "weekend", var: v }),
    api("correlation")
  ]);

  const s = await api("summary");

  $("edaOverview").innerHTML = [
    ["Records", fmt(s.records, 0)],
    ["Features", s.features],
    ["Cities", s.cities],
    ["Missing cells", fmt(s.missing_values, 0)],
    ["Worst city (mean AQI)", s.worst_city],
    ["Cleanest city", s.best_city],
    ["Hours with AQI ≥ 151", `${fmt(s.unhealthy_share)}%`]
  ]
    .map(([k, val]) => `<div class="chip">${k}: <b>${val}</b></div>`)
    .join("");

  table(
    "edaStats",
    ["Variable", "Count", "Mean", "Std", "Min", "25%", "Median", "75%", "Max", "Skew"],
    stats.stats.map((r) => [
      r.label,
      fmt(r.count, 0),
      fmt(r.mean, 2),
      fmt(r.std, 2),
      fmt(r.min, 2),
      fmt(r.q25, 2),
      fmt(r.median, 2),
      fmt(r.q75, 2),
      fmt(r.max, 2),
      fmt(r.skew, 2)
    ])
  );

  table(
    "edaMissing",
    ["Column", "Type", "Missing", "%"],
    stats.missing.map((m) => [m.column, m.dtype, m.missing, m.pct])
  );

  $("tDist").textContent = `Distribution — ${label(v)}`;

  bar("cDist", dist.labels, dist.counts, "Hours", COLORS.primary);

  $("distNote").textContent =
    `Mean ${fmt(dist.mean, 2)} vs median ${fmt(dist.median, 2)}` +
    (dist.mean > dist.median * 1.05
      ? " — mean above median indicates a right-skewed distribution (occasional high episodes)."
      : ".");

  line("cHour", hour.labels, hour.values, label(v), COLORS.accent);

  if (hour.values.length) {
    const hi = hour.values.indexOf(Math.max(...hour.values));
    const lo = hour.values.indexOf(Math.min(...hour.values));

    $("hourNote").textContent =
      `Highest mean at ${hour.labels[hi]}:00 (${fmt(hour.values[hi])}), lowest at ${hour.labels[lo]}:00 (${fmt(hour.values[lo])}).`;
  }

  bar("cDow", dow.labels, dow.values, label(v), COLORS.orange);
  bar("cWeekend", wk.labels, wk.values, label(v), COLORS.purple);

  renderHeatmap(corr);

  $("insights").innerHTML = corr.insights.map((x) => `<li>${x}</li>`).join("");
}

async function renderAirQuality() {
  const v = $("fVar").value;

  const [byCity, dist, hour, month] = await Promise.all([
    api("by_city"),
    api("distribution", { var: v }),
    api("temporal", { by: "hour", var: v }),
    api("temporal", { by: "month", var: v })
  ]);

  const pols = [
    "pm2_5",
    "pm10",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
    "dust"
  ];

  const datasets = pols.map((p, i) => {
    const max = Math.max(...byCity.cities.map((c) => c[p]));

    return {
      label: short(label(p)),
      data: byCity.cities.map((c) => (100 * c[p]) / max),
      backgroundColor: CITY_PALETTE[i]
    };
  });

  chart(
    "cPollCompare",
    "bar",
    {
      labels: byCity.cities.map((c) => c.city),
      datasets
    },
    {
      scales: {
        y: {
          title: {
            display: true,
            text: "% of highest city mean"
          }
        }
      }
    },
    3
  );

  $("tAqDist").textContent = `Distribution — ${label(v)}`;

  bar("cAqDist", dist.labels, dist.counts, "Hours", COLORS.primary);

  const b = dist.box || {};

  kv("boxStats", [
    ["Min", fmt(b.min, 2)],
    ["Lower whisker", fmt(b.whisker_low, 2)],
    ["Q1", fmt(b.q1, 2)],
    ["Median", fmt(b.median, 2)],
    ["Q3", fmt(b.q3, 2)],
    ["Upper whisker", fmt(b.whisker_high, 2)],
    ["Max", fmt(b.max, 2)]
  ]);

  line("cAqHour", hour.labels, hour.values, label(v), COLORS.accent, 3);
  bar("cAqMonth", month.labels, month.values, label(v), COLORS.red, false, 3);
}

async function renderWeather() {
  const w = $("wVar").value;

  const [ts, byCity, hour, sc] = await Promise.all([
    api("timeseries", { var: w }),
    api("by_city"),
    api("temporal", { by: "hour", var: w }),
    api("scatter", { var: w })
  ]);

  $("tWTrend").textContent = `${label(w)} — daily mean`;

  line("cWTrend", ts.labels, ts.values, label(w), COLORS.green, 3);

  $("tWCity").textContent = `${label(w)} — mean by city`;

  bar(
    "cWCity",
    byCity.cities.map((c) => c.city),
    byCity.cities.map((c) => c[w]),
    label(w),
    COLORS.green,
    true
  );

  $("tWHour").textContent = `${label(w)} — mean by hour`;

  line("cWHour", hour.labels, hour.values, label(w), COLORS.accent);

  $("tScatter").textContent = `AQI vs ${short(label(w))} (sample of up to 800 records)`;

  chart(
    "cScatter",
    "scatter",
    {
      datasets: [{
        label: "Records",
        data: sc.x.map((x, i) => ({ x, y: sc.y[i] })),
        backgroundColor: COLORS.primary + "66",
        pointRadius: 2.5
      }]
    },
    {
      scales: {
        x: {
          title: {
            display: true,
            text: label(w)
          }
        },
        y: {
          title: {
            display: true,
            text: "AQI"
          }
        }
      }
    },
    3
  );
}

async function renderCities() {
  const v = $("fVar").value;
  const sel = $("fCity").value;

  const [byCity, trend] = await Promise.all([
    api("by_city"),
    api("timeseries", { var: v, by_city: 1, freq: "week" })
  ]);

  const cols = [
    "aqi",
    "pm2_5",
    "pm10",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
    "temperature",
    "humidity",
    "wind_speed",
    "pressure"
  ];

  table(
    "cityTable",
    ["City", ...cols.map((c) => short(label(c)))],
    byCity.cities.map((c, i) => [
      `${i + 1}. ${c.city}${c.city === sel ? " ★" : ""}`,
      ...cols.map((k) => fmt(c[k], 1))
    ])
  );

  const sorted = [...byCity.cities].sort((a, b) => b[v] - a[v]);

  $("tCityBar").textContent = `${label(v)} — mean by city`;

  bar(
    "cCityBar",
    sorted.map((c) => c.city),
    sorted.map((c) => c[v]),
    label(v),
    COLORS.primary,
    true
  );

  bar(
    "cCityTemp",
    byCity.cities.map((c) => c.city),
    byCity.cities.map((c) => c.temperature),
    "Mean temperature (°C)",
    COLORS.orange,
    true
  );

  $("tCityTrend").textContent = `${label(v)} — weekly mean by city`;

  chart(
    "cCityTrend",
    "line",
    {
      labels: trend.labels,
      datasets: Object.entries(trend.series).map(([c, vals], i) => ({
        label: c,
        data: vals,
        borderColor: CITY_PALETTE[i % 10],
        pointRadius: 0,
        borderWidth: 1.6,
        tension: 0.25
      }))
    },
    {
      plugins: {
        legend: {
          position: "bottom"
        }
      }
    },
    2.8
  );
}

async function renderData() {
  const t = state.table;

  const d = await api("records", {
    page: t.page,
    size: $("tSize").value,
    search: $("tSearch").value,
    sort: t.sort,
    dir: t.dir,
    cols: t.cols.join(",")
  });

  const arrow = (c) =>
    t.sort === c
      ? (t.dir === "asc" ? " ▲" : " ▼")
      : "";

  $("dataTable").innerHTML =
    `<thead><tr>${d.columns.map((c) => `<th data-col="${c}">${c}${arrow(c)}</th>`).join("")}</tr></thead><tbody>` +
    (
      d.rows.length
        ? d.rows.map((r) => `<tr>${r.map((cell, i) => `<td>${d.columns[i] === "aqi_category" ? catBadge(cell) : cell ?? "—"}</td>`).join("")}</tr>`).join("")
        : `<tr><td colspan="${d.columns.length}" class="empty">No matching records</td></tr>`
    ) +
    "</tbody>";

  const pages = Math.max(1, Math.ceil(d.total / d.size));

  $("pageInfo").textContent = `Page ${d.page} of ${pages} · ${fmt(d.total, 0)} records`;

  $("prevP").disabled = d.page <= 1;
  $("nextP").disabled = d.page >= pages;

  document.querySelectorAll("#dataTable th").forEach((th) =>
    th.addEventListener("click", () => {
      t.dir = t.sort === th.dataset.col && t.dir === "asc" ? "desc" : "asc";
      t.sort = th.dataset.col;
      t.page = 1;
      renderData();
    })
  );
}

async function loadStatus() {
  try {
    const res = await fetch("/api/status");

    if (!res.ok) {
      throw new Error(res.status);
    }

    const s = await res.json();
    const el = $("liveStatus");

    const when = s.last_refresh
      ? new Date(s.last_refresh).toLocaleString([], {
          day: "numeric",
          month: "short",
          hour: "2-digit",
          minute: "2-digit"
        })
      : "—";

    el.textContent = s.mode === "api"
      ? `● Live · updated ${when}`
      : `● Offline CSV data`;

    el.className = "live" + (s.last_error || s.mode !== "api" ? " warn" : "");

    el.title =
      (s.last_error ? `Last refresh failed: ${s.last_error}\n` : "") +
      `Latest record: ${s.latest_record}. Auto-refresh every ${s.refresh_minutes} min.`;

    return s;
  } catch (err) {
    return null;
  }
}

async function syncMeta() {
  const old = state.meta;

  state.meta = await (await fetch("/api/meta")).json();

  const m = state.meta;

  ["fStart", "fEnd"].forEach((id) => {
    $(id).min = m.date_min;
    $(id).max = m.date_max;
  });

  if ($("fEnd").value === old.date_max) {
    $("fEnd").value = m.date_max;
  }

  if ($("fStart").value < m.date_min) {
    $("fStart").value = m.date_min;
  }
}

async function pollStatus() {
  const s = await loadStatus();

  if (!s) return;

  const changed = lastRefresh && s.last_refresh !== lastRefresh && !s.refreshing;

  lastRefresh = s.last_refresh;

  if (changed) {
    await syncMeta();
    show(state.page);
  }
}

async function triggerRefresh() {
  try {
    const res = await fetch("/api/refresh", {
      method: "POST"
    });

    const body = await res.json().catch(() => ({}));

    return {
      code: res.status,
      body
    };
  } catch (err) {
    return {
      code: 0,
      body: {}
    };
  }
}

async function waitForRefresh(maxSeconds = 120) {
  for (let waited = 0; waited < maxSeconds; waited++) {
    await new Promise((r) => setTimeout(r, 1000));

    const s = await loadStatus();

    if (s && !s.refreshing) {
      return s;
    }
  }

  return null;
}

async function applyNewData(s) {
  lastRefresh = s.last_refresh;

  await syncMeta();
  await show(state.page);
}

function flash(text, ms = 3000) {
  $("liveStatus").textContent = text;
  setTimeout(loadStatus, ms);
}

async function manualRefresh() {
  const btn = $("refreshBtn");

  btn.disabled = true;
  btn.textContent = "↻ Refreshing…";

  try {
    const { code, body } = await triggerRefresh();

    if (code === 429) {
      await show(state.page);
      flash(`✓ Already up to date (next refresh in ${body.retry_after_seconds}s)`);
      return;
    }

    const s = await waitForRefresh();

    if (!s) {
      flash("Still working in the background — the dashboard will update by itself", 6000);
      return;
    }

    if (s.last_error) {
      await loadStatus();
      return;
    }

    await applyNewData(s);
    flash("✓ Dashboard updated");
  } finally {
    btn.disabled = false;
    btn.textContent = "↻ Refresh";
  }
}

async function refreshOnOpen() {
  const { code } = await triggerRefresh();

  if (code !== 200 && code !== 202) {
    return;
  }

  const s = await waitForRefresh();

  if (s && !s.last_error) {
    await applyNewData(s);
  }
}

const renderers = {
  dashboard: renderDashboard,
  etl: renderEtl,
  eda: renderEda,
  airquality: renderAirQuality,
  weather: renderWeather,
  cities: renderCities,
  data: renderData,
  about: () => {}
};

async function show(page) {
  if (!renderers[page]) {
    page = "dashboard";
  }

  state.page = page;

  document.querySelectorAll(".page").forEach((p) =>
    p.classList.toggle("active", p.id === `page-${page}`)
  );

  document.querySelectorAll("nav a").forEach((a) =>
    a.classList.toggle("active", a.dataset.page === page)
  );

  $("filters").style.display = ["etl", "about"].includes(page) ? "none" : "flex";
  $("nav").classList.remove("open");

  try {
    await renderers[page]();
  } catch (err) {
    console.error(err);
  }
}

const refresh = () => {
  state.table.page = 1;
  show(state.page);
};

function fillSelect(id, options, selected) {
  $(id).innerHTML = options
    .map(([v, t]) => `<option value="${v}">${t}</option>`)
    .join("");

  if (selected !== undefined) {
    $(id).value = selected;
  }
}

function resetFilters() {
  const m = state.meta;

  $("fCity").value = "all";
  $("fStart").value = m.date_min;
  $("fEnd").value = m.date_max;
  $("fYear").value = "all";
  $("fMonth").value = "all";
  $("fVar").value = "aqi";
}

async function init() {
  state.meta = await (await fetch("/api/meta")).json();

  const m = state.meta;

  fillSelect("fCity", [["all", "All cities"], ...m.cities.map((c) => [c, c])]);
  fillSelect("fYear", [["all", "All years"], ...m.years.map((y) => [y, y])]);
  fillSelect("fMonth", [["all", "All months"], ...m.months.map((x) => [x.month, x.month_name])]);
  fillSelect("fVar", Object.entries(m.pollutants));
  fillSelect("wVar", Object.entries(m.weather));

  ["fStart", "fEnd"].forEach((id) => {
    $(id).min = m.date_min;
    $(id).max = m.date_max;
  });

  resetFilters();

  ["fCity", "fStart", "fEnd", "fYear", "fMonth", "fVar"].forEach((id) =>
    $(id).addEventListener("change", refresh)
  );

  $("wVar").addEventListener("change", () => show("weather"));
  $("refreshBtn").addEventListener("click", manualRefresh);
  $("fReset").addEventListener("click", () => {
    resetFilters();
    refresh();
  });

  $("menuBtn").addEventListener("click", () => $("nav").classList.toggle("open"));

  window.addEventListener("hashchange", () => show(location.hash.slice(1)));

  let timer;

  $("tSearch").addEventListener("input", () => {
    clearTimeout(timer);

    timer = setTimeout(() => {
      state.table.page = 1;
      renderData();
    }, 300);
  });

  $("tSize").addEventListener("change", () => {
    state.table.page = 1;
    renderData();
  });

  $("prevP").addEventListener("click", () => {
    state.table.page--;
    renderData();
  });

  $("nextP").addEventListener("click", () => {
    state.table.page++;
    renderData();
  });

  $("colPicker").innerHTML = m.columns
    .map((c) => `<label><input type="checkbox" value="${c}" ${state.table.cols.includes(c) ? "checked" : ""}/> ${c}</label>`)
    .join("");

  $("colPicker").addEventListener("change", () => {
    const chosen = [...$("colPicker").querySelectorAll("input:checked")].map((i) => i.value);

    if (chosen.length) {
      state.table.cols = chosen;
      renderData();
    }
  });

  show(location.hash.slice(1) || "dashboard");

  lastRefresh = (await loadStatus() || {}).last_refresh || null;

  setInterval(pollStatus, 30000);
  refreshOnOpen();
}

init().catch((e) => {
  document.querySelector("main").innerHTML =
    `<div class="panel empty">Could not reach the API. Start the backend with <code>python backend/app.py</code>.<br>${e.message}</div>`;
});
