#!/usr/bin/env python3
"""Render one day of meter JSON as a standalone HTML page matching the canvas.

Usage:
  python3 solar_day_html.py temp.json
  python3 solar_day_html.py temp.json -o reports/grid-solar-day.html
  python3 solar_day_html.py --day 2026-09-20 --device-ip 0.0.0.18 --token TOKEN_HERE
  python3 solar_day_html.py --day 2026-09-22 --days 7 --device-ip 0.0.0.18 --token TOKEN_HERE
  python3 solar_day_html.py --day 2026-09-22 --days 7 --skip-existing --device-ip 0.0.0.18 --token TOKEN_HERE
  python3 solar_day_html.py --month 2026-09
  # --skip-existing reuses raw-data/{day}.json when present
  # writes each day's raw-data/{day}.json and reports/grid-solar-day-{day}.html
  # plus reports/grid-solar-compare-{start}-to-{end}.html
  # --month reads raw-data/{YYYY-MM-DD}.json, regenerates daily HTML, and writes
  # reports/grid-solar-month-{YYYY-MM}.html
"""

from __future__ import annotations

import argparse
import json
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

from utils.solar.solar_day_summary import build_summary
from utils.solar.solar_month import month_dates, parse_month, render_month_html
from utils.solar.solar_day_compare import render_compare_html

class NoDayData(RuntimeError):
    """The API returned no usable meter records for that UTC day."""

PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <style>
    :root {
      --bg: #181818;
      --elevated: #1f1f1f;
      --text: #f0f0f0;
      --text-2: rgba(240,240,240,0.74);
      --text-3: rgba(240,240,240,0.60);
      --stroke: rgba(240,240,240,0.12);
      --stroke-3: rgba(240,240,240,0.08);
      --accent: #80a3ff;
      --green: #1f8a65;
      --orange: #c06028;
      --purple: #7b64b8;
      --info: #2e79b5;
      --warn-bg: rgba(192,96,40,0.12);
      --info-bg: rgba(46,121,181,0.12);
      --missed: #8a6d3b;
      --missed-bg: rgba(138,109,59,0.16);
      --gap: #5a5a5a;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/20px ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
    }
    .page { max-width: 960px; margin: 0 auto; padding: 24px 20px 48px; display: flex; flex-direction: column; gap: 20px; }
    h1 { font-size: 24px; line-height: 30px; font-weight: 590; margin: 0; }
    h2 { font-size: 18px; line-height: 24px; font-weight: 590; margin: 0; }
    .lede { color: var(--text-2); margin: 0; }
    .muted { color: var(--text-2); margin: 0; }
    .tiny { color: var(--text-3); font-size: 12px; line-height: 16px; margin: 0; }
    .stack-6 { display: flex; flex-direction: column; gap: 6px; }
    .grid-4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
    .stat-value { font-size: 22px; line-height: 28px; font-weight: 590; }
    .stat-label { font-size: 12px; line-height: 16px; color: var(--text-2); }
    .tone-success { color: var(--green); }
    .tone-warning { color: var(--orange); }
    .tone-info { color: var(--info); }
    table.framed {
      width: 100%;
      border-collapse: collapse;
      border: 1px solid var(--stroke);
      border-radius: 8px;
      overflow: hidden;
    }
    table.framed th, table.framed td {
      padding: 8px 12px;
      text-align: left;
      border-bottom: 1px solid var(--stroke-3);
      font-size: 13px;
    }
    table.framed th { color: var(--text-2); font-weight: 500; }
    table.framed tr:last-child td { border-bottom: none; }
    .right { text-align: right; }
    .callout {
      border: 1px solid var(--stroke);
      border-radius: 8px;
      padding: 12px 14px;
    }
    .callout.warn { background: var(--warn-bg); }
    .callout.info { background: var(--info-bg); }
    .callout .title { font-weight: 590; margin: 0 0 4px; }
    .callout p { margin: 0; color: var(--text-2); }
    .legend, .wx-row { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
    .wx-item { display: flex; gap: 6px; align-items: center; color: var(--text-2); font-size: 12px; }
    .chart-wrap { position: relative; }
    .chart-wrap svg { display: block; width: 100%; height: auto; }
    .tip {
      position: absolute;
      background: var(--elevated);
      border: 1px solid var(--stroke);
      padding: 8px 10px;
      font-size: 12px;
      pointer-events: none;
      min-width: 150px;
      display: none;
    }
    .usage { display: flex; flex-direction: column; gap: 6px; }
    .usage-labels { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-2); }
    .usage-bar { display: flex; height: 8px; border-radius: 999px; overflow: hidden; background: rgba(240,240,240,0.08); }
    .usage-bar span { display: block; height: 100%; }
    @media (max-width: 720px) {
      .grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <div class="page">
    <div class="stack-6">
      <h1>Grid import, export, and CO2 — __DATE_HUMAN__</h1>
      <p class="lede">Device __DEVICE__, __SITE_NAME__ (__LAT__ N, __LON__ E). __SOLAR_DC__ kW DC / __INVERTER__ kW inverter, __BATTERY_AH__ Ah lead-acid at __BATTERY_AGE__ years, __HOUSE_KW__ kW household. Clocks are device local time (__TZ_LABEL__, GMT+5:30), left to right from __LOCAL_START__. Green above zero is export; orange below zero is import. Dashed line is a clear-sky ideal for a south-facing __SOLAR_DC__ kW array.</p>
    </div>

    <table class="framed">
      <thead><tr><th>Plant</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Solar DC / inverter AC</td><td>__SOLAR_DC__ kW / __INVERTER__ kW</td></tr>
        <tr><td>Battery</td><td>__BATTERY_AH__ Ah lead-acid, __BATTERY_AGE__ years</td></tr>
        <tr><td>Household capacity</td><td>__HOUSE_KW__ kW · 3×1-ton AC, 3 kW EV, 2.5 kW pump</td></tr>
        <tr><td>Site</td><td>__SITE_NAME__ __LAT__ N, __LON__ E · sunrise __SUNRISE__ __TZ_LABEL__</td></tr>
      </tbody>
    </table>

    <div class="grid-4">
      <div><div class="stat-value tone-success">__EXPORT_KWH__ kWh</div><div class="stat-label">Exported to grid</div></div>
      <div><div class="stat-value tone-warning">__IMPORT_KWH__ kWh</div><div class="stat-label">Imported from grid</div></div>
      <div><div class="stat-value">₹__BILL_ROUND__</div><div class="stat-label">Estimated daily grid bill</div></div>
      <div><div class="stat-value tone-info">__IDEAL_KWH__ kWh</div><div class="stat-label">Clear-sky ideal yield</div></div>
    </div>

    <div>
      <div class="chart-wrap" id="power-chart"></div>
      <div class="legend" style="margin-top:8px">
        <span class="tiny">Solid: meter 3 export/import</span>
        <span class="tiny">Dashed: clear-sky __SOLAR_DC__ kW DC</span>
        <span class="tiny">Purple: estimated house load</span>
        <span class="tiny">Tan bands: grid unavailable, missed utilization</span>
        <span class="tiny">Grey bands: missing meter samples</span>
      </div>
      <div class="wx-row" id="wx-legend" style="margin-top:8px"></div>
    </div>

    <h2>Daily grid bill</h2>
    <p class="muted">__TARIFF_NOTES__</p>
    <div class="grid-4">
      <div><div class="stat-value tone-warning">₹__IMPORT_INR__</div><div class="stat-label">Import energy charge</div></div>
      <div><div class="stat-value tone-success">₹__EXPORT_INR__</div><div class="stat-label">Export credit</div></div>
      <div><div class="stat-value">₹__FIXED_INR__</div><div class="stat-label">Prorated fixed charge</div></div>
      <div><div class="stat-value">₹__DAILY_INR__</div><div class="stat-label">Net for this day</div></div>
    </div>
    <table class="framed">
      <thead>
        <tr><th>Item</th><th class="right">Energy</th><th class="right">Rate</th><th class="right">Amount</th></tr>
      </thead>
      <tbody>
        <tr><td>Grid import</td><td class="right">__IMPORT_KWH_EXACT__ kWh</td><td class="right">₹__IMPORT_RATE__/kWh</td><td class="right">₹__IMPORT_INR__</td></tr>
        <tr><td>Grid export credit</td><td class="right">__EXPORT_KWH_EXACT__ kWh</td><td class="right">₹__EXPORT_RATE__/kWh</td><td class="right">−₹__EXPORT_INR__</td></tr>
        <tr><td>Fixed charge (prorated)</td><td class="right">—</td><td class="right">₹__FIXED_MONTH__ / 30 d</td><td class="right">₹__FIXED_INR__</td></tr>
        <tr><td>Net payable today</td><td class="right">—</td><td class="right">—</td><td class="right">₹__DAILY_INR__</td></tr>
      </tbody>
    </table>

    <h2>Estimated running load</h2>
    <p class="muted">Load is inferred as weather-adjusted generation minus net grid flow. Gaps on the purple line are intervals where export exceeded the __SOLAR_DC__ kW DC model — likely battery discharge or extra array not in the nameplate. Night islanding (grid ≈ 0) uses the observed overnight standby of __NIGHT_KW__ kW. Peak inferred load __PEAK_LOAD__ kW at __PEAK_LOAD_CLOCK__ __TZ_LABEL__, consistent with AC plus house circuits; load-side activity is aggregated from configured LOAD_AC_METER inputs.</p>
    <div class="grid-4">
      <div><div class="stat-value">__LOAD_KWH__ kWh</div><div class="stat-label">Inferred load energy</div></div>
      <div><div class="stat-value">__PEAK_LOAD__ kW</div><div class="stat-label">Peak inferred load · __PEAK_LOAD_CLOCK__ __TZ_LABEL__</div></div>
      <div><div class="stat-value">__NIGHT_KW__ kW</div><div class="stat-label">Night standby (islanded)</div></div>
      <div><div class="stat-value">__CHARGER_KWH__ kWh</div><div class="stat-label">Load-meter energy</div></div>
    </div>
    <h2>Missed utilization from grid unavailability</h2>
    <p class="muted">Tan bands are daytime stretches with meter samples, no export, and only a small house load. Grey bands are missing samples and are not counted as missed utilization. Missed kWh is weather-adjusted generation minus the small load that was still served, using only buckets that actually arrived.</p>
    <div class="grid-4">
      <div><div class="stat-value">__MISSED_KWH__ kWh</div><div class="stat-label">Missed utilization</div></div>
      <div><div class="stat-value">__ISLAND_MIN__ min</div><div class="stat-label">Grid-unavailable daytime</div></div>
      <div><div class="stat-value">__MISSING_MIN__ min</div><div class="stat-label">Missing meter samples</div></div>
      <div><div class="stat-value">₹__MISSED_INR__</div><div class="stat-label">Export credit left on the table</div></div>
    </div>
    <div class="callout warn">
      <div class="title">How to read the patches</div>
      <p>__MISSED_NOTE__</p>
    </div>
    <div class="callout warn">
      <div class="title">Nameplate vs measured export</div>
      <p>Peak grid export is __PEAK_EXPORT__ kW at __PEAK_EXPORT_CLOCK__ __TZ_LABEL__, above the __PEAK_IDEAL__ kW clear-sky AC peak of a __SOLAR_DC__ kW DC array. Either the DC nameplate is low, or the __BATTERY_AGE__-year lead-acid bank is discharging into the grid during the morning.</p>
    </div>

    <h2>CO2 contribution versus the Indian grid</h2>
    <p class="muted">Each kilowatt-hour imported is counted as grid emissions. Each kilowatt-hour exported is counted as avoided grid generation. Factor is __CO2_FACTOR__ kg CO2 per kWh (CEA CO2 Baseline Database, FY 2023-24 weighted average).</p>
    <div class="grid-4">
      <div><div class="stat-value tone-success">__AVOIDED_KG__ kg</div><div class="stat-label">CO2 avoided by export</div></div>
      <div><div class="stat-value tone-warning">__EMITTED_KG__ kg</div><div class="stat-label">CO2 from grid import</div></div>
      <div><div class="stat-value">__NET_KG__ kg</div><div class="stat-label">Net over the day</div></div>
      <div><div class="stat-value tone-info">__PEAK_CREDIT_KG__ kg</div><div class="stat-label">Peak credit · __PEAK_CREDIT_CLOCK__ __TZ_LABEL__</div></div>
    </div>
    <div class="usage">
      <div class="usage-labels">
        <span>Share of the day's CO2 movement</span>
        <span>__EMITTED_KG__ kg emitted · __AVOIDED_KG__ kg avoided</span>
      </div>
      <div class="usage-bar">
        <span style="width:__EMITTED_PCT__%; background:var(--orange)"></span>
        <span style="width:__AVOIDED_PCT__%; background:var(--green)"></span>
      </div>
    </div>
    <div class="callout info">
      <div class="title">How to read the cumulative curve</div>
      <p>Values above zero mean solar export has more than offset import so far. The peak near __PEAK_CREDIT_CLOCK__ __TZ_LABEL__ is the maximum credit (__PEAK_CREDIT_KG_EXACT__ kg). Evening and overnight import then spends that credit; the day ends __NET_KG_EXACT__ kg net emitted.</p>
    </div>

    <div class="chart-wrap" id="co2-chart"></div>

    <h2>Hourly CO2 emitted vs avoided</h2>
    <p class="muted">Orange is CO2 attributed to grid import in that __TZ_LABEL__ hour. Green is CO2 avoided by export. Late morning through early afternoon are almost entirely credit; evening through night are almost entirely emissions. Categories are __TZ_LABEL__ clocks at the start of each chronological hour.</p>
    <div class="chart-wrap" id="hourly-chart"></div>

    <p class="tiny">Source: daily meter JSON via solar_day_summary.py · __METER_SAMPLES__ meter samples, __WEATHER_SAMPLES__ weather reports · __DATE_HUMAN__ __LOCAL_START__–__LOCAL_END__ __TZ_LABEL__. Ideal curve is Haurwitz clear-sky POA at __LAT__ N, __LON__ E, __SOLAR_DC__ kW DC, tilt __TILT__°, south, PR __PR__. Missed utilization is weather-adjusted generation minus served island load during daytime no-export patches with meter samples. Grey bands are missing samples and are omitted from energy totals. Bill uses JVVNL/RERC FY 2025-26 rates. CO2 = signed kWh × __CO2_FACTOR__ kg/kWh.</p>
  </div>
  <script>
  const DATA = __DATA_JSON__;
  const STEP_MIN = DATA.stepMinutes;
  const STEP_H = STEP_MIN / 60;
  const KW = DATA.series.gridExportKw;
  const IDEAL = DATA.series.idealSolarKw;
  const LOAD = DATA.series.loadKw;
  const WEATHER = DATA.weather;
  const SPAN_MIN = (KW.length - 1) * STEP_MIN;
  const TZ_OFFSET_MIN = DATA.tzOffsetMinutes || 330;
  const TZ_LABEL = DATA.timezone || "IST";
  const COLORS = {
    text: "#f0f0f0", text2: "rgba(240,240,240,0.74)", text3: "rgba(240,240,240,0.60)",
    stroke: "rgba(240,240,240,0.20)", stroke2: "rgba(240,240,240,0.12)", stroke3: "rgba(240,240,240,0.08)",
    bg: "#181818", elevated: "#1f1f1f", accent: "#80a3ff",
    green: "#1F8A65", orange: "#C06028", purple: "#7B64B8", missed: "#8A6D3B", gap: "#6A6A6A"
  };

  function clockFromMinutes(minutesFromUtcMidnight) {
    const total = ((minutesFromUtcMidnight + TZ_OFFSET_MIN) % (24 * 60) + 24 * 60) % (24 * 60);
    const h = Math.floor(total / 60);
    const m = total % 60;
    return String(h).padStart(2,"0") + ":" + String(m).padStart(2,"0");
  }
  function clockFromIndex(i) {
    return clockFromMinutes(i * STEP_MIN);
  }
  const HOUR_TICKS = DATA.hourTicks || [0,3,6,9,12,15,18,21].map(h => ({ minutesFromStart: h*60, clock: clockFromMinutes(h*60) }));
  function intervalKg(kw) { return kw * STEP_H * DATA.co2KgPerKwh; }
  function svgNS() { return "http://www.w3.org/2000/svg"; }
  function el(tag, attrs, parent) {
    const n = document.createElementNS(svgNS(), tag);
    Object.entries(attrs).forEach(([k,v]) => { if (v !== undefined && v !== null) n.setAttribute(k, String(v)); });
    if (parent) parent.appendChild(n);
    return n;
  }
  function weatherIcon(kind, color, size) {
    const g = document.createElementNS(svgNS(), "g");
    const stroke = { fill: "none", stroke: color, "stroke-width": 1.6, "stroke-linecap": "round", "stroke-linejoin": "round" };
    function p(d) { const n = el("path", { d, ...stroke }, g); return n; }
    if (kind === "broken") {
      el("circle", { cx: 8, cy: 8, r: 3.2, fill: color, opacity: 0.35 }, g);
      el("circle", { cx: 8, cy: 8, r: 3.2, ...stroke }, g);
      p("M7 16.5h9.2a3.2 3.2 0 0 0 .2-6.4 4.4 4.4 0 0 0-8.4-1.2A3.4 3.4 0 0 0 7 16.5z");
    } else if (kind === "rain") {
      p("M6.5 12.5h9.2a3.2 3.2 0 0 0 .2-6.4 4.4 4.4 0 0 0-8.4-1.2A3.4 3.4 0 0 0 6.5 12.5z");
      p("M8 15.5l-1 3M12 15.5l-1 3M16 15.5l-1 3");
    } else if (kind === "overcast") {
      p("M7 11h8.5a2.8 2.8 0 0 0 .15-5.6 3.9 3.9 0 0 0-7.5-1A3 3 0 0 0 7 11z");
      p("M6 16.5h11a3 3 0 0 0 .2-6 4.2 4.2 0 0 0-4.1-3");
    } else {
      p("M10 7.2a4.2 4.2 0 1 0 5.3 5.4A4.6 4.6 0 0 1 10 7.2z");
      p("M6.5 17h10a2.8 2.8 0 0 0 .15-5.5 3.6 3.6 0 0 0-6.6-.7A2.9 2.9 0 0 0 6.5 17z");
    }
    g.setAttribute("transform", "scale(" + (size/24) + ")");
    return g;
  }
  function buildAreas(xs, ys, zeroY) {
    const lineParts = [];
    const importParts = [], exportParts = [];
    let run = null;
    let drawing = false;
    const flush = () => {
      if (!run || !run.points.length) return;
      const pts = run.points;
      const d = "M" + pts[0][0].toFixed(1) + "," + zeroY.toFixed(1) + " " +
        pts.map(([x,y]) => "L"+x.toFixed(1)+","+y.toFixed(1)).join(" ") +
        " L" + pts[pts.length-1][0].toFixed(1) + "," + zeroY.toFixed(1) + " Z";
      (run.side === "import" ? importParts : exportParts).push(d);
      run = null;
    };
    for (let i=0;i<xs.length;i++) {
      const kw = KW[i];
      const x = xs[i], y = ys[i];
      if (kw == null || x === undefined || y == null) { flush(); drawing = false; continue; }
      lineParts.push((drawing?"L":"M") + x.toFixed(1) + "," + y.toFixed(1));
      drawing = true;
      if (kw === 0) { flush(); continue; }
      const side = kw > 0 ? "export" : "import";
      if (!run || run.side !== side) { flush(); run = { side, points: [] }; }
      run.points.push([x, y]);
    }
    flush();
    return { importPath: importParts.join(" "), exportPath: exportParts.join(" "), linePath: lineParts.join(" ") };
  }
  function polylinePath(xs, values, yAt) {
    const parts = [];
    let drawing = false;
    const n = Math.min(xs.length, values.length);
    for (let i=0;i<n;i++) {
      const value = values[i], x = xs[i];
      if (value === null || x === undefined) { drawing = false; continue; }
      parts.push((drawing?"L":"M") + x.toFixed(1) + "," + yAt(value).toFixed(1));
      drawing = true;
    }
    return parts.join(" ");
  }

  function drawPower(host) {
    const width = 920, height = 420;
    const pad = { top: 52, right: 18, bottom: 40, left: 58 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const yMin = -4, yMax = 4;
    const xAt = m => pad.left + (m / SPAN_MIN) * innerW;
    const yAt = kw => pad.top + ((yMax - kw) / (yMax - yMin)) * innerH;
    const zeroY = yAt(0);
    const xs = KW.map((_,i) => xAt(i * STEP_MIN));
    const ys = KW.map(kw => kw == null ? null : yAt(kw));
    const areas = buildAreas(xs, ys, zeroY);
    const svg = el("svg", { viewBox: "0 0 "+width+" "+height, width: "100%", role: "img", "aria-label": "Meter 3 grid import and export" });
    [4,2,0,-2,-4].forEach(tick => {
      el("line", { x1: pad.left, x2: width-pad.right, y1: yAt(tick), y2: yAt(tick),
        stroke: tick===0 ? COLORS.stroke : COLORS.stroke3, "stroke-dasharray": tick===0?undefined:"3 4" }, svg);
      const t = el("text", { x: pad.left-8, y: yAt(tick)+4, "text-anchor": "end", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = tick > 0 ? "+"+tick : String(tick);
    });
    const ylab = el("text", { x: 14, y: pad.top+8, fill: COLORS.text3, "font-size": 11, "font-family": "inherit",
      transform: "rotate(-90 14 "+(pad.top+innerH/2)+")" }, svg);
    ylab.textContent = "Meter 3 power (kW)";
    const ex = el("text", { x: pad.left-8, y: yAt(3.2), "text-anchor": "end", fill: COLORS.green, "font-size": 10, "font-family": "inherit" }, svg);
    ex.textContent = "export";
    const im = el("text", { x: pad.left-8, y: yAt(-3.2)+8, "text-anchor": "end", fill: COLORS.orange, "font-size": 10, "font-family": "inherit" }, svg);
    im.textContent = "import";
    if (areas.importPath) el("path", { d: areas.importPath, fill: COLORS.orange, opacity: 0.28 }, svg);
    if (areas.exportPath) el("path", { d: areas.exportPath, fill: COLORS.green, opacity: 0.28 }, svg);
    el("path", { d: areas.linePath, fill: "none", stroke: COLORS.text, "stroke-width": 1.4 }, svg);
    el("path", { d: polylinePath(xs, IDEAL, yAt), fill: "none", stroke: COLORS.accent, "stroke-width": 1.6, "stroke-dasharray": "5 4" }, svg);
    el("path", { d: polylinePath(xs, LOAD, yAt), fill: "none", stroke: COLORS.purple, "stroke-width": 1.5 }, svg);
    (DATA.dataGapWindows || []).forEach(win => {
      const x1 = xAt(win.startMinutesFromStart);
      const x2 = xAt(Math.min(SPAN_MIN, win.endMinutesFromStart));
      el("rect", { x: x1, y: pad.top, width: Math.max(0, x2-x1), height: innerH, fill: COLORS.gap, opacity: 0.28 }, svg);
    });
    (DATA.islandWindows || []).forEach(win => {
      const x1 = xAt(win.startMinutesFromStart);
      const x2 = xAt(Math.min(SPAN_MIN, win.endMinutesFromStart));
      el("rect", { x: x1, y: pad.top, width: Math.max(0, x2-x1), height: innerH, fill: COLORS.missed, opacity: 0.18 }, svg);
    });
    const chargerMin = DATA.chargerMinutesFromStart;
    if (chargerMin != null) {
      el("line", { x1: xAt(chargerMin), x2: xAt(chargerMin), y1: pad.top, y2: height-pad.bottom,
        stroke: COLORS.accent, "stroke-dasharray": "4 4", opacity: 0.7 }, svg);
      const ct = el("text", { x: xAt(chargerMin)+6, y: pad.top + innerH*0.12, fill: COLORS.accent, "font-size": 10, "font-family": "inherit" }, svg);
      ct.textContent = "Load meter";
    }
    WEATHER.forEach(wx => {
      const x = xAt(wx.minutesFromStart);
      el("line", { x1: x, x2: x, y1: 18, y2: height-pad.bottom, stroke: COLORS.stroke3, "stroke-dasharray": "2 5" }, svg);
      const g = el("g", { transform: "translate("+(x-11)+", 6)" }, svg);
      g.appendChild(weatherIcon(wx.kind, COLORS.text2, 22));
    });
    HOUR_TICKS.forEach(tick => {
      const t = el("text", { x: xAt(tick.minutesFromStart), y: height-14, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = tick.clock;
    });
    const xlab = el("text", { x: width/2, y: height-1, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
    xlab.textContent = "Time ("+TZ_LABEL+")";
    const guide = el("line", { y1: pad.top, y2: height-pad.bottom, stroke: COLORS.stroke2, visibility: "hidden" }, svg);
    const dot = el("circle", { r: 3.5, fill: COLORS.bg, stroke: COLORS.text, "stroke-width": 1.5, visibility: "hidden" }, svg);
    const tip = document.createElement("div");
    tip.className = "tip";
    host.appendChild(svg);
    host.appendChild(tip);
    svg.addEventListener("mousemove", (event) => {
      const rect = svg.getBoundingClientRect();
      const scale = width / rect.width;
      const x = (event.clientX - rect.left) * scale;
      const minutes = ((x - pad.left) / innerW) * SPAN_MIN;
      const index = Math.round(minutes / STEP_MIN);
      if (index < 0 || index >= KW.length) { tip.style.display = "none"; guide.setAttribute("visibility","hidden"); dot.setAttribute("visibility","hidden"); return; }
      const hoverX = xs[index], hoverY = ys[index], hoverKw = KW[index];
      guide.setAttribute("x1", hoverX); guide.setAttribute("x2", hoverX); guide.setAttribute("visibility","visible");
      if (hoverKw == null || hoverY == null) {
        dot.setAttribute("visibility","hidden");
        tip.innerHTML = "<div>"+clockFromIndex(index)+" "+TZ_LABEL+"</div><div>No meter sample</div>";
        tip.style.display = "block";
        tip.style.left = Math.min(hoverX/scale + 8, rect.width - 180) + "px";
        tip.style.top = "56px";
        return;
      }
      dot.setAttribute("cx", hoverX); dot.setAttribute("cy", hoverY); dot.setAttribute("visibility","visible");
      const load = LOAD[index];
      const missed = (DATA.series.missedUtilKw || [])[index];
      const powerLine = hoverKw === 0 ? "Idle (0 kW)" : hoverKw > 0 ? "Export "+hoverKw.toFixed(2)+" kW" : "Import "+Math.abs(hoverKw).toFixed(2)+" kW";
      const co2Line = hoverKw === 0 ? "0 g CO2 this interval" : hoverKw > 0 ? (intervalKg(hoverKw)*1000).toFixed(0)+" g CO2 avoided" : "+"+(Math.abs(intervalKg(hoverKw))*1000).toFixed(0)+" g CO2 from grid";
      const missedLine = missed == null ? "" : "<div>Missed utilization "+Number(missed).toFixed(2)+" kW (grid unavailable)</div>";
      tip.innerHTML = "<div>"+clockFromIndex(index)+" "+TZ_LABEL+"</div><div>"+powerLine+"</div><div>"+co2Line+"</div><div>Ideal solar "+(IDEAL[index]??0).toFixed(2)+" kW</div><div>"+(load==null?"Load unknown (export above PV model)":"Est. load "+Number(load).toFixed(2)+" kW")+"</div>"+missedLine;
      tip.style.display = "block";
      tip.style.left = Math.min(hoverX/scale + 8, rect.width - 180) + "px";
      tip.style.top = "56px";
    });
    svg.addEventListener("mouseleave", () => {
      tip.style.display = "none";
      guide.setAttribute("visibility","hidden");
      dot.setAttribute("visibility","hidden");
    });
  }

  function drawCo2(host) {
    let running = 0;
    const cum = KW.map(kw => { if (kw != null) running += intervalKg(kw); return running; });
    const width = 920, height = 280;
    const pad = { top: 16, right: 18, bottom: 40, left: 58 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const yMin = -1, yMax = 10;
    const xAt = m => pad.left + (m / SPAN_MIN) * innerW;
    const yAt = kg => pad.top + ((yMax - kg) / (yMax - yMin)) * innerH;
    const zeroY = yAt(0);
    const xs = KW.map((_,i) => xAt(i * STEP_MIN));
    const ys = cum.map(kg => yAt(kg));
    const linePath = xs.map((x,i) => (i===0?"M":"L")+x.toFixed(1)+","+ys[i].toFixed(1)).join(" ");
    const fillBelow = "M"+xs[0].toFixed(1)+","+zeroY.toFixed(1)+" "+xs.map((x,i)=>"L"+x.toFixed(1)+","+ys[i].toFixed(1)).join(" ")+" L"+xs[xs.length-1].toFixed(1)+","+zeroY.toFixed(1)+" Z";
    const svg = el("svg", { viewBox: "0 0 "+width+" "+height, width: "100%", role: "img" });
    [10,8,6,4,2,0].forEach(tick => {
      el("line", { x1: pad.left, x2: width-pad.right, y1: yAt(tick), y2: yAt(tick),
        stroke: tick===0 ? COLORS.stroke : COLORS.stroke3, "stroke-dasharray": tick===0?undefined:"3 4" }, svg);
      const t = el("text", { x: pad.left-8, y: yAt(tick)+4, "text-anchor": "end", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = String(tick);
    });
    const ylab = el("text", { x: 14, y: pad.top+8, fill: COLORS.text3, "font-size": 11, "font-family": "inherit",
      transform: "rotate(-90 14 "+(pad.top+innerH/2)+")" }, svg);
    ylab.textContent = "Cumulative CO2 credit (kg)";
    el("path", { d: fillBelow, fill: COLORS.green, opacity: 0.22 }, svg);
    el("path", { d: linePath, fill: "none", stroke: COLORS.text, "stroke-width": 1.4 }, svg);
    HOUR_TICKS.forEach(tick => {
      const t = el("text", { x: xAt(tick.minutesFromStart), y: height-14, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = tick.clock;
    });
    const xlab = el("text", { x: width/2, y: height-1, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
    xlab.textContent = "Time ("+TZ_LABEL+")";
    const guide = el("line", { y1: pad.top, y2: height-pad.bottom, stroke: COLORS.stroke2, visibility: "hidden" }, svg);
    const dot = el("circle", { r: 3.5, fill: COLORS.bg, stroke: COLORS.text, "stroke-width": 1.5, visibility: "hidden" }, svg);
    const tip = document.createElement("div");
    tip.className = "tip";
    host.appendChild(svg);
    host.appendChild(tip);
    svg.addEventListener("mousemove", (event) => {
      const rect = svg.getBoundingClientRect();
      const scale = width / rect.width;
      const x = (event.clientX - rect.left) * scale;
      const minutes = ((x - pad.left) / innerW) * SPAN_MIN;
      const index = Math.round(minutes / STEP_MIN);
      if (index < 0 || index >= KW.length) { tip.style.display="none"; guide.setAttribute("visibility","hidden"); dot.setAttribute("visibility","hidden"); return; }
      guide.setAttribute("x1", xs[index]); guide.setAttribute("x2", xs[index]); guide.setAttribute("visibility","visible");
      dot.setAttribute("cx", xs[index]); dot.setAttribute("cy", ys[index]); dot.setAttribute("visibility","visible");
      const v = cum[index];
      tip.innerHTML = "<div>"+clockFromIndex(index)+" "+TZ_LABEL+"</div><div>"+(v>=0 ? v.toFixed(2)+" kg CO2 credit so far" : Math.abs(v).toFixed(2)+" kg CO2 net emitted so far")+"</div>";
      tip.style.display = "block";
      tip.style.left = Math.min(xs[index]/scale + 8, rect.width - 200) + "px";
      tip.style.top = "20px";
    });
    svg.addEventListener("mouseleave", () => {
      tip.style.display = "none";
      guide.setAttribute("visibility","hidden");
      dot.setAttribute("visibility","hidden");
    });
  }

  function drawHourly(host) {
    const emitted = Array.from({length:24}, () => 0);
    const avoided = Array.from({length:24}, () => 0);
    KW.forEach((kw, index) => {
      if (kw == null) return;
      const hour = Math.floor((index * STEP_MIN) / 60);
      const kg = intervalKg(kw);
      if (kg > 0) avoided[hour] += kg; else emitted[hour] += -kg;
    });
    const width = 920, height = 260;
    const pad = { top: 16, right: 16, bottom: 36, left: 42 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const yMax = 2.5;
    const groupW = innerW / 24;
    const barW = groupW * 0.36;
    const svg = el("svg", { viewBox: "0 0 "+width+" "+height, width: "100%", role: "img" });
    [0, 0.5, 1, 1.5, 2, 2.5].forEach(tick => {
      const y = pad.top + ((yMax - tick) / yMax) * innerH;
      el("line", { x1: pad.left, x2: width-pad.right, y1: y, y2: y, stroke: COLORS.stroke3, "stroke-dasharray": "3 4" }, svg);
      const t = el("text", { x: pad.left-8, y: y+4, "text-anchor": "end", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = String(tick);
    });
    for (let h=0; h<24; h++) {
      const x0 = pad.left + h * groupW;
      const eH = (emitted[h] / yMax) * innerH;
      const aH = (avoided[h] / yMax) * innerH;
      el("rect", { x: x0 + groupW*0.12, y: pad.top + innerH - eH, width: barW, height: Math.max(0,eH), fill: COLORS.orange, opacity: 0.9 }, svg);
      el("rect", { x: x0 + groupW*0.12 + barW + 2, y: pad.top + innerH - aH, width: barW, height: Math.max(0,aH), fill: COLORS.green, opacity: 0.9 }, svg);
      if (h % 2 === 0) {
        const t = el("text", { x: x0 + groupW/2, y: height-12, "text-anchor": "middle", fill: COLORS.text3, "font-size": 10, "font-family": "inherit" }, svg);
        t.textContent = clockFromMinutes(h * 60);
      }
    }
    const ylab = el("text", { x: 12, y: pad.top+8, fill: COLORS.text3, "font-size": 11, "font-family": "inherit",
      transform: "rotate(-90 12 "+(pad.top+innerH/2)+")" }, svg);
    ylab.textContent = "CO2 (kg)";
    const lg1 = el("text", { x: pad.left, y: 12, fill: COLORS.orange, "font-size": 11, "font-family": "inherit" }, svg);
    lg1.textContent = "CO2 from import (kg)";
    const lg2 = el("text", { x: pad.left + 170, y: 12, fill: COLORS.green, "font-size": 11, "font-family": "inherit" }, svg);
    lg2.textContent = "CO2 avoided by export (kg)";
    host.appendChild(svg);
  }

  const wxLegend = document.getElementById("wx-legend");
  WEATHER.forEach(wx => {
    const item = document.createElement("div");
    item.className = "wx-item";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "16"); svg.setAttribute("height", "16"); svg.setAttribute("viewBox", "0 0 24 24");
    svg.appendChild(weatherIcon(wx.kind, COLORS.text2, 24));
    item.appendChild(svg);
    const span = document.createElement("span");
    span.textContent = wx.clock + " " + wx.desc + " (" + wx.tempC + " C)";
    item.appendChild(span);
    wxLegend.appendChild(item);
  });
  drawPower(document.getElementById("power-chart"));
  drawCo2(document.getElementById("co2-chart"));
  drawHourly(document.getElementById("hourly-chart"));
  </script>
</body>
</html>
"""


def _missed_note(summary: dict) -> str:
    windows = summary.get("islandWindows") or []
    gaps = summary.get("dataGapWindows") or []
    totals = summary.get("totals") or {}
    missed = float(totals.get("missedUtilKwh") or 0.0)
    minutes = int(totals.get("islandMinutes") or 0)
    missing = int(totals.get("missingMinutes") or 0)
    parts: list[str] = []
    if windows:
        spans = ", ".join(f"{w['startClock']}–{w['endClock']} ({w['minutes']} min, {w['missedKwh']:.2f} kWh)" for w in windows)
        parts.append(
            f"{len(windows)} islanding window(s), {minutes} min, {missed:.2f} kWh unused: {spans}."
        )
    else:
        parts.append("No daytime islanding patches in the samples that arrived.")
    if gaps:
        gap_spans = ", ".join(f"{w['startClock']}–{w['endClock']} ({w['minutes']} min)" for w in gaps if w["minutes"] >= 10)
        if gap_spans:
            parts.append(f"{missing} min of meter data is missing ({gap_spans}) and is not counted as missed utilization.")
        else:
            parts.append(f"{missing} min of meter data is missing and is not counted as missed utilization.")
    return " ".join(parts)


def _human_date(iso_date: str) -> str:
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    return f"{dt.day} {dt.strftime('%b %Y')}"


def render_html(summary: dict) -> str:
    totals = summary["totals"]
    peaks = summary["peaks"]
    plant = summary["plant"]
    site = summary["site"]
    tariff = summary["tariff"]
    kw = summary["series"]["gridExportKw"]
    step_h = summary["stepMinutes"] / 60.0
    factor = summary["co2KgPerKwh"]
    running = 0.0
    peak_credit = 0.0
    peak_credit_i = 0
    for i, value in enumerate(kw):
        if value is None:
            continue
        running += value * step_h * factor
        if running > peak_credit:
            peak_credit = running
            peak_credit_i = i
    peak_credit_min = peak_credit_i * summary["stepMinutes"]
    tz_offset = int(summary.get("tzOffsetMinutes") or 330)
    local_min = (peak_credit_min + tz_offset) % (24 * 60)
    peak_credit_clock = f"{local_min // 60:02d}:{local_min % 60:02d}"
    emitted = totals["co2EmittedKg"]
    avoided = totals["co2AvoidedKg"]
    move = emitted + avoided or 1.0
    net = totals["co2NetKg"]
    net_label = f"{'+' if net > 0 else ''}{round(net, 2)}"
    replacements = {
        "__TITLE__": escape(f"Grid import, export, and CO2 — {_human_date(summary['date'])}"),
        "__DATE_HUMAN__": escape(_human_date(summary["date"])),
        "__DEVICE__": escape(str(summary.get("device") or "")),
        "__SITE_NAME__": escape(str(site["name"])),
        "__LAT__": f"{site['lat']:.2f}",
        "__LON__": f"{site['lon']:.2f}",
        "__SOLAR_DC__": _num(plant["solarDcKw"]),
        "__INVERTER__": _num(plant["inverterAcKw"]),
        "__BATTERY_AH__": str(int(plant["batteryAh"])),
        "__BATTERY_AGE__": str(int(plant["batteryAgeYears"])),
        "__HOUSE_KW__": _num(plant["householdLoadKw"]),
        "__TZ_LABEL__": escape(str(summary.get("timezone") or "IST")),
        "__LOCAL_START__": escape(str(summary.get("localStartClock") or "05:30")),
        "__LOCAL_END__": escape(str(summary.get("localEndClock") or "05:25")),
        "__SUNRISE__": escape(str(site.get("sunriseLocal") or site.get("sunriseUtc") or "—")),
        "__EXPORT_KWH__": f"{totals['exportKwh']:.1f}",
        "__IMPORT_KWH__": f"{totals['importKwh']:.1f}",
        "__BILL_ROUND__": str(int(round(totals["dailyBillInr"]))),
        "__IDEAL_KWH__": f"{totals['idealSolarKwh']:.1f}",
        "__TARIFF_NOTES__": escape(str(tariff["notes"])),
        "__IMPORT_INR__": f"{totals['importInr']:.1f}",
        "__EXPORT_INR__": f"{totals['exportCreditInr']:.1f}",
        "__FIXED_INR__": f"{totals['fixedInr']:.1f}",
        "__DAILY_INR__": f"{totals['dailyBillInr']:.1f}",
        "__IMPORT_KWH_EXACT__": f"{totals['importKwh']:.2f}",
        "__EXPORT_KWH_EXACT__": f"{totals['exportKwh']:.2f}",
        "__IMPORT_RATE__": f"{tariff['importInrPerKwh']:.2f}",
        "__EXPORT_RATE__": f"{tariff['exportInrPerKwh']:.2f}",
        "__FIXED_MONTH__": _num(tariff["fixedInrPerMonth"]),
        "__NIGHT_KW__": f"{summary['nightStandbyKw']:.2f}",
        "__PEAK_LOAD__": _num(peaks["loadKw"]),
        "__PEAK_LOAD_CLOCK__": peaks["loadClock"],
        "__LOAD_KWH__": f"{totals['loadKwh']:.1f}",
        "__CHARGER_KWH__": f"{totals['chargerKwh']:.2f}",
        "__MISSED_KWH__": f"{totals.get('missedUtilKwh', 0):.2f}",
        "__ISLAND_MIN__": str(int(totals.get("islandMinutes") or 0)),
        "__MISSING_MIN__": str(int(totals.get("missingMinutes") or 0)),
        "__MISSED_INR__": f"{totals.get('missedUtilInr', 0):.1f}",
        "__MISSED_NOTE__": escape(_missed_note(summary)),
        "__PEAK_EXPORT__": _num(peaks["exportKw"]),
        "__PEAK_EXPORT_CLOCK__": peaks["exportClock"],
        "__PEAK_IDEAL__": _num(peaks["idealKw"]),
        "__CO2_FACTOR__": str(factor),
        "__AVOIDED_KG__": f"{round(avoided, 1)}",
        "__EMITTED_KG__": f"{round(emitted, 1)}",
        "__NET_KG__": net_label,
        "__NET_KG_EXACT__": f"{net:.2f}",
        "__PEAK_CREDIT_KG__": f"{round(peak_credit, 1)}",
        "__PEAK_CREDIT_KG_EXACT__": f"{peak_credit:.2f}",
        "__PEAK_CREDIT_CLOCK__": peak_credit_clock,
        "__EMITTED_PCT__": f"{100.0 * emitted / move:.2f}",
        "__AVOIDED_PCT__": f"{100.0 * avoided / move:.2f}",
        "__METER_SAMPLES__": str(summary["meterSamples"]),
        "__WEATHER_SAMPLES__": str(summary["weatherSamples"]),
        "__TILT__": _num(plant["tiltDeg"]),
        "__PR__": str(plant["performanceRatio"]),
        "__DATA_JSON__": json.dumps(summary, separators=(",", ":")),
    }
    html = PAGE_TEMPLATE
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html


def _num(value: float | None) -> str:
    if value is None:
        return "—"
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def parse_day(value: str) -> datetime:
    try:
        day = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"day must be YYYY-MM-DD, got {value!r}") from exc
    return day.replace(tzinfo=timezone.utc)


def day_range(start: datetime, extra_days: int) -> list[datetime]:
    """UTC days from start through start + extra_days, inclusive."""
    if extra_days < 0:
        raise SystemExit("--days must be 0 or greater")
    return [start + timedelta(days=offset) for offset in range(extra_days + 1)]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    print(f"wrote {path}")


def write_html(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html)
    print(f"wrote {path}")


def raw_path_for_day(raw_dir: Path, stamp: str) -> Path | None:
    canonical = raw_dir / f"{stamp}.json"
    if canonical.exists():
        return canonical
    year, month, day = stamp.split("-")
    alt = raw_dir / f"{day}-{month}-{year}.json"
    if alt.exists():
        return alt
    return None


def load_local_day(raw_dir: Path, stamp: str) -> list[dict[str, Any]]:
    path = raw_path_for_day(raw_dir, stamp)
    if path is None:
        raise NoDayData(f"no raw file for {stamp}")
    records = json.loads(path.read_text())
    print(f"reused {path}")
    return records


def process_day(
    records: list[dict[str, Any]],
    html_path: Path,
    raw_path: Path | None = None,
    lat_deg: float | None = None,
    lon_deg: float | None = None,
  meter_types_by_name: dict[str, str] | None = None,
) -> dict[str, Any]:
    if raw_path is not None:
        write_json(raw_path, records)
    try:
      summary = build_summary(
        records,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        meter_types_by_name=meter_types_by_name,
      )
    except SystemExit as exc:
        raise NoDayData(str(exc)) from exc
    write_html(html_path, render_html(summary))
    return summary


def ssl_context(insecure: bool = False) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def is_ssl_verify_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "certificate_verify_failed" in text or "ssl:" in text


def unwrap_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "records", "items"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return inner
    raise SystemExit("API response is not a JSON array of meter records")


def post_json(request: urllib.request.Request) -> Any:
    try:
        with urllib.request.urlopen(request, context=ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        if isinstance(exc, urllib.error.HTTPError) or not is_ssl_verify_error(exc):
            raise
        print("TLS verify failed; retrying without certificate verification")
        with urllib.request.urlopen(request, context=ssl_context(insecure=True)) as response:
            return json.loads(response.read().decode("utf-8"))


def fetch_day_records(device_ip: str, day: datetime, token: str) -> list[dict[str, Any]]:
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    url = f"{API_BASE}/{device_ip}"
    body = json.dumps({
        "exportType": "json",
        "startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataType": "raw_data",
    }).encode("utf-8")
    auth = token if token.lower().startswith("token ") else f"Token {token}"
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Authorization": auth,
            "Content-Type": "application/json",
            "Origin": API_ORIGIN,
            "Referer": f"{API_ORIGIN}/",
        },
    )
    try:
        payload = post_json(request)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"API {exc.code} {exc.reason}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"API request failed: {exc.reason}") from exc
    records = unwrap_records(payload)
    if not records:
        raise NoDayData(f"no records for {device_ip} on {start.date().isoformat()}")
    return records

def process_monthly_report(month_str: str, raw_dir) -> Path:
    year, month = parse_month(month_str)
    summaries: list[dict[str, Any]] = []
    missing: list[str] = []
    for day in month_dates(year, month):
        stamp = day.isoformat()
        html_path = Path("reports") / f"grid-solar-day-{stamp}.html"
        try:
            records = load_local_day(raw_dir, stamp)
            summaries.append(process_day(records, html_path))
        except NoDayData as exc:
            missing.append(stamp)
            print(f"skipped {stamp}: {exc}")
    if not summaries:
        raise SystemExit(f"no days with meter data in {raw_dir} for {month_str}")
    out = Path(raw_dir) / f"grid-solar-month-{year:04d}-{month:02d}.html"
    write_html(out, render_month_html(year, month, summaries, missing))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a canvas-matching HTML report from daily meter JSON.")
    parser.add_argument("input", nargs="?", type=Path, help="Path to meters JSON array")
    parser.add_argument("--day", help="UTC calendar day YYYY-MM-DD to fetch")
    parser.add_argument("--days", type=int, default=0, help="Additional UTC days after --day (7 with 2026-09-22 covers through 2026-09-29)")
    parser.add_argument("--month", help="UTC month YYYY-MM; build the monthly report from existing raw-data files")
    parser.add_argument("--raw-dir", type=Path, default=Path("raw-data"), help="Directory of raw-data/{YYYY-MM-DD}.json files")
    parser.add_argument("--device-ip", help="Device IP as used in the IoT API, e.g. 0.0.0.18")
    parser.add_argument("--token", help="IoT API token (with or without the Token prefix)")
    parser.add_argument("-o", "--output", type=Path, default=None, help="HTML output path for a single day or month")
    parser.add_argument("--save-json", type=Path, default=None, help="Raw JSON path for a single day (default: raw-data/{day}.json when fetching)")
    parser.add_argument("--skip-existing", action="store_true", help="Reuse raw-data/{day}.json when it already exists instead of fetching")
    args = parser.parse_args()

    if args.month and (args.input is not None or args.day):
        parser.error("--month cannot be combined with a JSON file or --day")
    if args.month and args.days:
        parser.error("--days cannot be used with --month")
    if args.month and args.save_json is not None:
        parser.error("--save-json does not apply to --month")
    if args.days and args.input is not None:
        parser.error("--days cannot be used with a local JSON file")
    if args.days and not args.day:
        parser.error("--days requires --day")
    if args.input is not None and args.day:
        parser.error("pass a JSON file or --day, not both")
    if args.input is None and not args.day and not args.month:
        parser.error("pass a JSON file, --day --device-ip --token, or --month YYYY-MM")
    if args.days and (args.output is not None or args.save_json is not None):
        parser.error("-o and --save-json apply to a single day; omit them when using --days")

    if args.month:
        process_monthly_report(args.month, args.raw_dir)
        return

    if args.input is not None:
        records = json.loads(args.input.read_text())
        summary = build_summary(records)
        out = args.output or Path("reports") / f"grid-solar-day-{summary['date']}.html"
        write_html(out, render_html(summary))
        return

    days = day_range(parse_day(args.day), args.days)
    raw_paths = {
        day.date().isoformat(): (args.save_json or Path("raw-data") / f"{day.date().isoformat()}.json")
        for day in days
    }
    need_fetch = [
        stamp for stamp, path in raw_paths.items()
        if not (args.skip_existing and path.exists())
    ]
    if need_fetch and (not args.device_ip or not args.token):
        parser.error("--device-ip and --token are required to download missing days")

    summaries: list[dict[str, Any]] = []
    missing: list[str] = []
    for day in days:
        stamp = day.date().isoformat()
        raw_path = raw_paths[stamp]
        html_path = args.output or Path("reports") / f"grid-solar-day-{stamp}.html"
        try:
            if args.skip_existing and raw_path.exists():
                records = json.loads(raw_path.read_text())
                print(f"reused {raw_path}")
                summaries.append(process_day(records, html_path))
            else:
                records = fetch_day_records(args.device_ip, day, args.token)
                summaries.append(process_day(records, html_path, raw_path))
        except NoDayData as exc:
            missing.append(stamp)
            print(f"skipped {stamp}: {exc}")

    if not summaries:
        raise SystemExit("no days with meter data in the requested range")

    if len(days) == 1:
        return

    start = days[0].date().isoformat()
    end = days[-1].date().isoformat()
    compare_path = Path("reports") / f"grid-solar-compare-{start}-to-{end}.html"
    write_html(compare_path, render_compare_html(summaries, missing))


if __name__ == "__main__":
    main()
