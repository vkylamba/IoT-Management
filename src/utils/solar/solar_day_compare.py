#!/usr/bin/env python3
"""Render a day-by-day comparison HTML report from daily summaries."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from html import escape
from typing import Any

COMPARE_TEMPLATE = r"""<!DOCTYPE html>
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
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/20px ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
    }
    .page { max-width: 1080px; margin: 0 auto; padding: 24px 20px 48px; display: flex; flex-direction: column; gap: 22px; }
    h1 { font-size: 24px; line-height: 30px; font-weight: 590; margin: 0; }
    h2 { font-size: 18px; line-height: 24px; font-weight: 590; margin: 0; }
    .lede, .muted { color: var(--text-2); margin: 0; }
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
    }
    table.framed th, table.framed td {
      padding: 8px 10px;
      text-align: left;
      border-bottom: 1px solid var(--stroke-3);
      font-size: 13px;
    }
    table.framed th { color: var(--text-2); font-weight: 500; }
    table.framed th.tip-th {
      cursor: help;
      text-decoration: underline dotted;
      text-underline-offset: 3px;
      position: relative;
    }
    table.framed th.tip-th .col-tip {
      display: none;
      position: absolute;
      top: calc(100% + 6px);
      left: 0;
      z-index: 8;
      width: 280px;
      padding: 10px 12px;
      background: var(--elevated);
      border: 1px solid var(--stroke);
      color: var(--text-2);
      font-size: 12px;
      line-height: 16px;
      font-weight: 400;
      text-align: left;
      text-decoration: none;
      white-space: normal;
    }
    table.framed th.tip-th.right .col-tip { left: auto; right: 0; }
    table.framed th.tip-th:hover .col-tip,
    table.framed th.tip-th:focus-within .col-tip { display: block; }
    table.framed tr:last-child td { border-bottom: none; }
    table.framed tr.best td { background: rgba(31,138,101,0.12); }
    table.framed tr.worst td { background: rgba(192,96,40,0.10); }
    .right { text-align: right; }
    .callout { border: 1px solid var(--stroke); padding: 12px 14px; }
    .callout.info { background: var(--info-bg); }
    .callout.warn { background: var(--warn-bg); }
    .callout .title { font-weight: 590; margin: 0 0 4px; }
    .callout p { margin: 0; color: var(--text-2); }
    .chart-wrap svg { display: block; width: 100%; height: auto; }
    .day-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)); gap: 10px; }
    .day-card {
      border: 1px solid var(--stroke);
      background: var(--elevated);
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      text-decoration: none;
      color: inherit;
    }
    .day-card .dow { font-size: 11px; color: var(--text-3); }
    .day-card .date { font-weight: 590; }
    .day-card .wx { font-size: 12px; color: var(--text-2); min-height: 32px; }
    .meter { height: 8px; background: rgba(240,240,240,0.08); overflow: hidden; display: flex; }
    .meter span { display: block; height: 100%; }
    .podium { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
    .podium .card { border: 1px solid var(--stroke); background: var(--elevated); padding: 12px; }
    .podium .rank { font-size: 11px; color: var(--text-3); letter-spacing: 0.04em; text-transform: uppercase; }
    a { color: var(--accent); }
    @media (max-width: 720px) {
      .grid-4, .podium { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <div class="page">
    <div class="stack-6">
      <h1>__TITLE__</h1>
      <p class="lede">__LEDE__</p>
    </div>

    <div class="grid-4">
      <div><div class="stat-value tone-success">__EXPORT_KWH__ kWh</div><div class="stat-label">Exported over the range</div></div>
      <div><div class="stat-value tone-warning">__IMPORT_KWH__ kWh</div><div class="stat-label">Imported over the range</div></div>
      <div><div class="stat-value">₹__BILL__</div><div class="stat-label">Grid bill for the range</div></div>
      <div><div class="stat-value">__MISSED_KWH__ kWh</div><div class="stat-label">Missed utilization from grid outages</div></div>
    </div>

    <div class="callout info">
      <div class="title">The range in one sentence</div>
      <p>__NARRATIVE__</p>
    </div>

    <h2>Daily character cards</h2>
    <p class="muted">Each card is one UTC day. The bar is export (green) versus import (orange). Click through to the full daily report.</p>
    <div class="day-cards">__DAY_CARDS__</div>

    <h2>Who won the week</h2>
    <div class="podium">
      <div class="card">
        <div class="rank">Sunniest export</div>
        <div class="stat-value tone-success">__BEST_EXPORT__</div>
        <p class="tiny">__BEST_EXPORT_NOTE__</p>
      </div>
      <div class="card">
        <div class="rank">Hungriest house</div>
        <div class="stat-value">__BEST_LOAD__</div>
        <p class="tiny">__BEST_LOAD_NOTE__</p>
      </div>
      <div class="card">
        <div class="rank">Cheapest grid day</div>
        <div class="stat-value tone-info">__BEST_BILL__</div>
        <p class="tiny">__BEST_BILL_NOTE__</p>
      </div>
      <div class="card">
        <div class="rank">Most unused sun</div>
        <div class="stat-value">__BEST_MISSED__</div>
        <p class="tiny">__BEST_MISSED_NOTE__</p>
      </div>
    </div>

    <h2>Import versus export by day</h2>
    <p class="muted">Orange bars are grid import (kWh). Green bars are grid export (kWh). The dashed line is clear-sky ideal yield. Tan ticks on the axis are missed utilization from daytime grid unavailability.</p>
    <div class="chart-wrap" id="bars"></div>

    <h2>Self-sufficiency and sky capture</h2>
    <p class="muted">Self-sufficiency is weather-adjusted generation as a share of inferred house load. Sky capture is that generation as a share of the clear-sky ideal over hours that have meter samples. Missing samples are omitted, not treated as zero generation.</p>
    <div class="chart-wrap" id="ratios"></div>

    <h2>Net grid fingerprint</h2>
    <p class="muted">Hourly net grid power for every day, overlaid. Positive is export. The thick line is the range average. Days that peel away below zero in late afternoon are the ones that spent the battery or ran heavy loads after the sun dropped.</p>
    <div class="chart-wrap" id="overlay"></div>

    <h2>CO2 ledger</h2>
    <p class="muted">Daily avoided generation versus emissions, then the running net. Below zero means the range is a net emitter so far.</p>
    <div class="chart-wrap" id="co2"></div>

    <h2>Scoreboard</h2>
    <p class="muted">Hover a column title for the unit and how that number is made.</p>
    <table class="framed">
      <thead>
        <tr>__SCOREBOARD_HEAD__</tr>
      </thead>
      <tbody>__ROWS__</tbody>
    </table>
    __MISSING__

    <p class="tiny">Source: IoT raw_data via solar_day_html.py · device __DEVICE__ · __SITE__ · clocks are device local time (__TZ__). Bill uses JVVNL/RERC FY 2025-26 rates. CO2 = signed kWh × 0.727 kg/kWh. Range is UTC calendar days __START__ to __END__.</p>
  </div>
  <script>
  const DATA = __DATA_JSON__;
  const COLORS = {
    text: "#f0f0f0", text2: "rgba(240,240,240,0.74)", text3: "rgba(240,240,240,0.60)",
    stroke: "rgba(240,240,240,0.20)", stroke2: "rgba(240,240,240,0.12)", stroke3: "rgba(240,240,240,0.08)",
    bg: "#181818", accent: "#80a3ff", green: "#1F8A65", orange: "#C06028", purple: "#7B64B8", missed: "#8A6D3B"
  };
  function svgNS() { return "http://www.w3.org/2000/svg"; }
  function el(tag, attrs, parent) {
    const n = document.createElementNS(svgNS(), tag);
    Object.entries(attrs).forEach(([k,v]) => { if (v !== undefined && v !== null) n.setAttribute(k, String(v)); });
    if (parent) parent.appendChild(n);
    return n;
  }
  function niceMax(values, pad) {
    const m = Math.max(...values, 0.1);
    const step = m <= 5 ? 1 : m <= 20 ? 5 : 10;
    return Math.ceil((m * (pad || 1.12)) / step) * step;
  }
  function yTicks(max, n) {
    const out = [];
    for (let i = 0; i <= n; i++) out.push(Math.round((max * i / n) * 10) / 10);
    return out;
  }

  function drawBars(host) {
    const days = DATA.days;
    const width = 1040, height = 280;
    const pad = { top: 18, right: 16, bottom: 40, left: 46 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const yMax = niceMax(days.flatMap(d => [d.importKwh, d.exportKwh, d.idealKwh, d.missedKwh]));
    const groupW = innerW / days.length;
    const barW = groupW * 0.28;
    const svg = el("svg", { viewBox: "0 0 "+width+" "+height, width: "100%", role: "img" });
    yTicks(yMax, 4).forEach(tick => {
      const y = pad.top + ((yMax - tick) / yMax) * innerH;
      el("line", { x1: pad.left, x2: width-pad.right, y1: y, y2: y, stroke: COLORS.stroke3, "stroke-dasharray": "3 4" }, svg);
      const t = el("text", { x: pad.left-8, y: y+4, "text-anchor": "end", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = String(tick);
    });
    days.forEach((d, i) => {
      const x0 = pad.left + i * groupW;
      const importH = (d.importKwh / yMax) * innerH;
      const exportH = (d.exportKwh / yMax) * innerH;
      const idealY = pad.top + ((yMax - d.idealKwh) / yMax) * innerH;
      const missedH = (d.missedKwh / yMax) * innerH;
      el("rect", { x: x0 + groupW*0.18, y: pad.top + innerH - importH, width: barW, height: Math.max(0, importH), fill: COLORS.orange, opacity: 0.92 }, svg);
      el("rect", { x: x0 + groupW*0.18 + barW + 3, y: pad.top + innerH - exportH, width: barW, height: Math.max(0, exportH), fill: COLORS.green, opacity: 0.92 }, svg);
      el("rect", { x: x0 + groupW*0.18 + 2*barW + 6, y: pad.top + innerH - missedH, width: Math.max(3, barW*0.55), height: Math.max(0, missedH), fill: COLORS.missed, opacity: 0.9 }, svg);
      el("line", { x1: x0 + groupW*0.14, x2: x0 + groupW*0.86, y1: idealY, y2: idealY, stroke: COLORS.accent, "stroke-dasharray": "4 3" }, svg);
      const t = el("text", { x: x0 + groupW/2, y: height-14, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = d.short;
    });
    const ylab = el("text", { x: 14, y: pad.top+8, fill: COLORS.text3, "font-size": 11, "font-family": "inherit",
      transform: "rotate(-90 14 "+(pad.top+innerH/2)+")" }, svg);
    ylab.textContent = "Energy (kWh)";
    const lg1 = el("text", { x: pad.left, y: 12, fill: COLORS.orange, "font-size": 11, "font-family": "inherit" }, svg);
    lg1.textContent = "Import";
    const lg2 = el("text", { x: pad.left + 70, y: 12, fill: COLORS.green, "font-size": 11, "font-family": "inherit" }, svg);
    lg2.textContent = "Export";
    const lg3 = el("text", { x: pad.left + 140, y: 12, fill: COLORS.missed, "font-size": 11, "font-family": "inherit" }, svg);
    lg3.textContent = "Missed util";
    const lg4 = el("text", { x: pad.left + 230, y: 12, fill: COLORS.accent, "font-size": 11, "font-family": "inherit" }, svg);
    lg4.textContent = "Clear-sky ideal";
    host.appendChild(svg);
  }

  function drawRatios(host) {
    const days = DATA.days;
    const width = 1040, height = 240;
    const pad = { top: 18, right: 16, bottom: 40, left: 46 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const yMax = 100;
    const groupW = innerW / days.length;
    const barW = groupW * 0.28;
    const svg = el("svg", { viewBox: "0 0 "+width+" "+height, width: "100%", role: "img" });
    [0,25,50,75,100].forEach(tick => {
      const y = pad.top + ((yMax - tick) / yMax) * innerH;
      el("line", { x1: pad.left, x2: width-pad.right, y1: y, y2: y, stroke: COLORS.stroke3, "stroke-dasharray": "3 4" }, svg);
      const t = el("text", { x: pad.left-8, y: y+4, "text-anchor": "end", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = tick + "%";
    });
    days.forEach((d, i) => {
      const x0 = pad.left + i * groupW;
      const coverH = (d.coverPct / yMax) * innerH;
      const capH = (d.capturePct / yMax) * innerH;
      el("rect", { x: x0 + groupW*0.18, y: pad.top + innerH - coverH, width: barW, height: Math.max(0, coverH), fill: COLORS.purple, opacity: 0.9 }, svg);
      el("rect", { x: x0 + groupW*0.18 + barW + 3, y: pad.top + innerH - capH, width: barW, height: Math.max(0, capH), fill: COLORS.accent, opacity: 0.9 }, svg);
      const t = el("text", { x: x0 + groupW/2, y: height-14, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = d.short;
    });
    const ylab = el("text", { x: 14, y: pad.top+8, fill: COLORS.text3, "font-size": 11, "font-family": "inherit",
      transform: "rotate(-90 14 "+(pad.top+innerH/2)+")" }, svg);
    ylab.textContent = "Share (%)";
    const lg1 = el("text", { x: pad.left, y: 12, fill: COLORS.purple, "font-size": 11, "font-family": "inherit" }, svg);
    lg1.textContent = "Load cover";
    const lg2 = el("text", { x: pad.left + 90, y: 12, fill: COLORS.accent, "font-size": 11, "font-family": "inherit" }, svg);
    lg2.textContent = "Sky capture";
    host.appendChild(svg);
  }

  function drawOverlay(host) {
    const days = DATA.days;
    const width = 1040, height = 280;
    const pad = { top: 18, right: 16, bottom: 40, left: 50 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const yMin = -4, yMax = 4;
    const n = days[0].hourlyNetKw.length;
    const xAt = i => pad.left + (i / (n - 1)) * innerW;
    const yAt = v => pad.top + ((yMax - v) / (yMax - yMin)) * innerH;
    const svg = el("svg", { viewBox: "0 0 "+width+" "+height, width: "100%", role: "img" });
    [-4,-2,0,2,4].forEach(tick => {
      const y = yAt(tick);
      el("line", { x1: pad.left, x2: width-pad.right, y1: y, y2: y,
        stroke: tick===0 ? COLORS.stroke : COLORS.stroke3, "stroke-dasharray": tick===0?undefined:"3 4" }, svg);
      const t = el("text", { x: pad.left-8, y: y+4, "text-anchor": "end", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = String(tick);
    });
    function netPath(values) {
      const parts = [];
      let drawing = false;
      values.forEach((v,i) => {
        if (v == null) { drawing = false; return; }
        parts.push((drawing?"L":"M")+xAt(i).toFixed(1)+","+yAt(v).toFixed(1));
        drawing = true;
      });
      return parts.join(" ");
    }
    days.forEach(d => {
      el("path", { d: netPath(d.hourlyNetKw), fill: "none", stroke: COLORS.stroke, "stroke-width": 1.1 }, svg);
    });
    el("path", { d: netPath(DATA.averageHourlyNetKw), fill: "none", stroke: COLORS.text, "stroke-width": 2 }, svg);
    [0,6,12,18].forEach(h => {
      const t = el("text", { x: xAt(h), y: height-14, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = DATA.hourLabels[h];
    });
    const xlab = el("text", { x: width/2, y: height-1, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
    xlab.textContent = "Time ("+DATA.timezone+")";
    const ylab = el("text", { x: 14, y: pad.top+8, fill: COLORS.text3, "font-size": 11, "font-family": "inherit",
      transform: "rotate(-90 14 "+(pad.top+innerH/2)+")" }, svg);
    ylab.textContent = "Net grid (kW)";
    const lg1 = el("text", { x: pad.left, y: 12, fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
    lg1.textContent = "Each day";
    const lg2 = el("text", { x: pad.left + 80, y: 12, fill: COLORS.text, "font-size": 11, "font-family": "inherit" }, svg);
    lg2.textContent = "Range average";
    host.appendChild(svg);
  }

  function drawCo2(host) {
    const days = DATA.days;
    const width = 1040, height = 260;
    const pad = { top: 18, right: 16, bottom: 40, left: 50 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const running = [];
    let acc = 0;
    days.forEach(d => { acc += d.co2NetKg; running.push(acc); });
    const yMin = Math.min(-1, ...running, ...days.map(d => -d.co2EmittedKg));
    const yMax = Math.max(1, ...running, ...days.map(d => d.co2AvoidedKg));
    const span = yMax - yMin || 1;
    const groupW = innerW / days.length;
    const barW = groupW * 0.28;
    const xAt = i => pad.left + (i + 0.5) * groupW;
    const yAt = v => pad.top + ((yMax - v) / span) * innerH;
    const svg = el("svg", { viewBox: "0 0 "+width+" "+height, width: "100%", role: "img" });
    [yMax, 0, yMin].forEach(tick => {
      const y = yAt(tick);
      el("line", { x1: pad.left, x2: width-pad.right, y1: y, y2: y,
        stroke: tick===0 ? COLORS.stroke : COLORS.stroke3, "stroke-dasharray": tick===0?undefined:"3 4" }, svg);
      const t = el("text", { x: pad.left-8, y: y+4, "text-anchor": "end", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = String(Math.round(tick));
    });
    days.forEach((d, i) => {
      const x0 = pad.left + i * groupW;
      const aH = (d.co2AvoidedKg / span) * innerH;
      const eH = (d.co2EmittedKg / span) * innerH;
      el("rect", { x: x0 + groupW*0.18, y: yAt(d.co2AvoidedKg), width: barW, height: Math.max(0, aH), fill: COLORS.green, opacity: 0.9 }, svg);
      el("rect", { x: x0 + groupW*0.18 + barW + 3, y: yAt(0), width: barW, height: Math.max(0, eH), fill: COLORS.orange, opacity: 0.9 }, svg);
      const t = el("text", { x: x0 + groupW/2, y: height-14, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = d.short;
    });
    const line = running.map((v,i) => (i===0?"M":"L")+xAt(i).toFixed(1)+","+yAt(v).toFixed(1)).join(" ");
    el("path", { d: line, fill: "none", stroke: COLORS.text, "stroke-width": 1.8 }, svg);
    running.forEach((v,i) => el("circle", { cx: xAt(i), cy: yAt(v), r: 3, fill: COLORS.bg, stroke: COLORS.text }, svg));
    const ylab = el("text", { x: 14, y: pad.top+8, fill: COLORS.text3, "font-size": 11, "font-family": "inherit",
      transform: "rotate(-90 14 "+(pad.top+innerH/2)+")" }, svg);
    ylab.textContent = "CO2 (kg)";
    const lg1 = el("text", { x: pad.left, y: 12, fill: COLORS.green, "font-size": 11, "font-family": "inherit" }, svg);
    lg1.textContent = "Avoided";
    const lg2 = el("text", { x: pad.left + 70, y: 12, fill: COLORS.orange, "font-size": 11, "font-family": "inherit" }, svg);
    lg2.textContent = "Emitted";
    const lg3 = el("text", { x: pad.left + 140, y: 12, fill: COLORS.text, "font-size": 11, "font-family": "inherit" }, svg);
    lg3.textContent = "Running net";
    host.appendChild(svg);
  }

  drawBars(document.getElementById("bars"));
  drawRatios(document.getElementById("ratios"));
  drawOverlay(document.getElementById("overlay"));
  drawCo2(document.getElementById("co2"));
  </script>
</body>
</html>
"""


def _human_date(iso_date: str) -> str:
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    return f"{dt.day} {dt.strftime('%b %Y')}"


def _short_date(iso_date: str) -> str:
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    return dt.strftime("%d %b")


def _weekday(iso_date: str) -> str:
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%a")


SCOREBOARD_COLUMNS = [
    {
        "label": "Day",
        "align": "",
        "tip": (
            "UTC calendar day of the raw meter file. "
            "Unit: date. "
            "Click through to that day's HTML report."
        ),
    },
    {
        "label": "Export",
        "align": "right",
        "tip": (
            "Energy sent to the grid. "
            "Unit: kWh. "
            "Sum of 5-minute meter 3 averages where signed power is positive "
            "(negative power factor). Buckets with no meter sample are omitted, not treated as zero."
        ),
    },
    {
        "label": "Import",
        "align": "right",
        "tip": (
            "Energy drawn from the grid. "
            "Unit: kWh. "
            "Sum of 5-minute meter 3 averages where signed power is negative "
            "(positive power factor). Missing samples are omitted."
        ),
    },
    {
        "label": "Load",
        "align": "right",
        "tip": (
            "Inferred house energy. "
            "Unit: kWh. "
            "For each 5-minute bucket, load = weather-adjusted PV generation minus net grid export, "
            "capped at the 5 kW household rating. Null when export exceeds the 3.2 kW DC model "
            "(battery discharge or extra array). Night islanding uses overnight standby. "
            "Only buckets with a meter sample are summed."
        ),
    },
    {
        "label": "Cover",
        "align": "right",
        "tip": (
            "Self-sufficiency: how much of inferred house load was met by modelled solar. "
            "Unit: percent. "
            "Weather-adjusted generation kWh ÷ inferred load kWh, capped at 100%."
        ),
    },
    {
        "label": "Capture",
        "align": "right",
        "tip": (
            "Sky capture: how much of the clear-sky potential was realised. "
            "Unit: percent. "
            "Weather-adjusted generation kWh ÷ Haurwitz clear-sky ideal kWh over hours that have meter samples. "
            "Missing samples are omitted, not treated as zero generation."
        ),
    },
    {
        "label": "Missed",
        "align": "right",
        "tip": (
            "Unused sun while the grid was unavailable. "
            "Unit: kWh. "
            "Daytime buckets (clear-sky ideal ≥ 0.2 kW) with meter samples, no export (≤ 0.05 kW) "
            "and only a small import (≥ −0.6 kW). Missed = weather-adjusted generation minus the small load still served. "
            "Patches shorter than 10 minutes are dropped. Telemetry gaps are not counted here."
        ),
    },
    {
        "label": "Gaps",
        "align": "right",
        "tip": (
            "Missing meter samples. "
            "Unit: minutes. "
            "Count of 5-minute buckets with no meter 3 sample, times 5. "
            "These holes are not treated as zero generation or as missed utilization."
        ),
    },
    {
        "label": "Bill",
        "align": "right",
        "key": "bill",
        "tip": (
            "Estimated daily grid bill. "
            "Unit: ₹. "
            "Import kWh × ₹8.40 − export kWh × ₹3.26, plus a ₹800/30 prorated fixed charge. "
            "Rates are RERC FY 2025-26 domestic 151–500 slab plus JVVNL net-metering export (Oct 2025)."
        ),
    },
    {
        "label": "Energy ₹",
        "align": "right",
        "key": "energy",
        "tip": (
            "Energy charge only, before the monthly fixed charge. "
            "Unit: ₹. "
            "Import kWh × ₹8.40 − export kWh × ₹3.26. "
            "The ₹800 connection charge is applied once on the monthly bill, not in this column."
        ),
    },
    {
        "label": "Net CO2",
        "align": "right",
        "tip": (
            "Net carbon versus the Indian grid. "
            "Unit: kg CO2. "
            "(Import kWh − export kWh) × 0.727 kg/kWh (CEA CO2 Baseline Database, FY 2023-24 weighted average). "
            "Positive is net emitted; negative is net avoided by export."
        ),
    },
    {
        "label": "Weather",
        "align": "",
        "tip": (
            "Most common OpenWeather description among that day's weather samples. "
            "Unit: text label from the weather payload, not a measured energy metric."
        ),
    },
]


def scoreboard_head_html(bill_key: str = "bill") -> str:
    cells = []
    for col in SCOREBOARD_COLUMNS:
        key = col.get("key")
        if key in {"bill", "energy"} and key != bill_key:
            continue
        klass = "tip-th right" if col["align"] == "right" else "tip-th"
        cells.append(
            f'<th class="{klass}" tabindex="0">{escape(col["label"])}'
            f'<span class="col-tip">{escape(col["tip"])}</span></th>'
        )
    return "".join(cells)


def _weather_label(summary: dict[str, Any]) -> str:
    marks = summary.get("weather") or []
    if not marks:
        return "no weather"
    counts = Counter(str(item.get("desc") or "unknown") for item in marks)
    return counts.most_common(1)[0][0]


def _cover_pct(totals: dict[str, Any]) -> float:
    load = float(totals.get("loadKwh") or 0.0)
    gen = float(totals.get("estimatedGenKwh") or 0.0)
    if load <= 0:
        return 0.0
    return round(min(100.0, 100.0 * gen / load), 1)


def _capture_pct(totals: dict[str, Any]) -> float:
    ideal = float(totals.get("idealObservedKwh") or totals.get("idealSolarKwh") or 0.0)
    gen = float(totals.get("estimatedGenKwh") or 0.0)
    if ideal <= 0:
        return 0.0
    return round(100.0 * gen / ideal, 1)


def _hourly_net(summary: dict[str, Any]) -> list[float | None]:
    series = summary["series"]["gridExportKw"]
    step = int(summary.get("stepMinutes") or 5)
    per_hour = max(1, 60 // step)
    out: list[float | None] = []
    for hour in range(24):
        chunk = [value for value in series[hour * per_hour : (hour + 1) * per_hour] if value is not None]
        out.append(round(sum(chunk) / len(chunk), 3) if chunk else None)
    return out


def _hour_labels(summary: dict[str, Any]) -> list[str]:
    offset = int(summary.get("tzOffsetMinutes") or 330)
    labels = []
    for hour in range(24):
        total = (hour * 60 + offset) % (24 * 60)
        labels.append(f"{total // 60:02d}:{total % 60:02d}")
    return labels


def _pct(value: float) -> str:
    return f"{value:.0f}" if float(value).is_integer() else f"{value:.1f}"


def build_compare_payload(
    summaries: list[dict[str, Any]],
    missing: list[str],
) -> dict[str, Any]:
    days = []
    for summary in summaries:
        totals = summary["totals"]
        days.append({
            "date": summary["date"],
            "short": _short_date(summary["date"]),
            "weekday": _weekday(summary["date"]),
            "href": f"grid-solar-day-{summary['date']}.html",
            "importKwh": totals["importKwh"],
            "exportKwh": totals["exportKwh"],
            "idealKwh": totals["idealSolarKwh"],
            "loadKwh": totals["loadKwh"],
            "genKwh": totals["estimatedGenKwh"],
            "billInr": totals["dailyBillInr"],
            "co2EmittedKg": totals["co2EmittedKg"],
            "co2AvoidedKg": totals["co2AvoidedKg"],
            "co2NetKg": totals["co2NetKg"],
            "coverPct": _cover_pct(totals),
            "capturePct": _capture_pct(totals),
            "missedKwh": float(totals.get("missedUtilKwh") or 0.0),
            "islandMinutes": int(totals.get("islandMinutes") or 0),
            "missingMinutes": int(totals.get("missingMinutes") or 0),
            "weather": _weather_label(summary),
            "hourlyNetKw": _hourly_net(summary),
        })
    n = len(days[0]["hourlyNetKw"]) if days else 0
    average = []
    for i in range(n):
        values = [day["hourlyNetKw"][i] for day in days if day["hourlyNetKw"][i] is not None]
        average.append(round(sum(values) / len(values), 3) if values else None)
    first = summaries[0]
    return {
        "timezone": first.get("timezone") or "IST",
        "hourLabels": _hour_labels(first),
        "days": days,
        "averageHourlyNetKw": average,
        "missing": missing,
    }


def _narrative(days: list[dict[str, Any]], missing: list[str]) -> str:
    sunniest = max(days, key=lambda d: d["exportKwh"])
    hungriest = max(days, key=lambda d: d["loadKwh"])
    cheapest = min(days, key=lambda d: d["billInr"])
    cloudiest = min(days, key=lambda d: d["capturePct"])
    most_missed = max(days, key=lambda d: d["missedKwh"])
    missed_total = sum(d["missedKwh"] for d in days)
    gap_total = sum(d["missingMinutes"] for d in days)
    net_export = sum(d["exportKwh"] - d["importKwh"] for d in days)
    direction = (
        f"a net exporter by {abs(net_export):.1f} kWh"
        if net_export > 0.05
        else f"a net importer by {abs(net_export):.1f} kWh"
        if net_export < -0.05
        else "almost grid-neutral"
    )
    miss = f" {len(missing)} day(s) had no meter data and are omitted." if missing else ""
    return (
        f"{sunniest['weekday']} {sunniest['short']} sent the most energy out "
        f"({sunniest['exportKwh']:.1f} kWh), {hungriest['weekday']} {hungriest['short']} "
        f"ran the heaviest house ({hungriest['loadKwh']:.1f} kWh inferred), and "
        f"{cheapest['weekday']} {cheapest['short']} was cheapest on the meter (₹{cheapest['billInr']:.0f}). "
        f"The cloudiest capture was {cloudiest['short']} at {cloudiest['capturePct']:.0f}% of clear-sky. "
        f"Grid unavailability left {missed_total:.1f} kWh unused, worst on {most_missed['short']} "
        f"({most_missed['missedKwh']:.1f} kWh over {most_missed['islandMinutes']} min). "
        + (f"{gap_total} min of meter data was missing and is not counted as unused sun. " if gap_total else "")
        + f"Over the whole range the plant was {direction}.{miss}"
    )


def render_compare_html(summaries: list[dict[str, Any]], missing: list[str] | None = None) -> str:
    missing = missing or []
    payload = build_compare_payload(summaries, missing)
    days = payload["days"]
    first = summaries[0]
    last = summaries[-1]
    export_kwh = sum(d["exportKwh"] for d in days)
    import_kwh = sum(d["importKwh"] for d in days)
    bill = sum(d["billInr"] for d in days)
    cover = sum(d["coverPct"] for d in days) / len(days)
    sunniest = max(days, key=lambda d: d["exportKwh"])
    hungriest = max(days, key=lambda d: d["loadKwh"])
    cheapest = min(days, key=lambda d: d["billInr"])
    most_missed = max(days, key=lambda d: d["missedKwh"])
    missed_kwh = sum(d["missedKwh"] for d in days)
    worst_bill = max(d["billInr"] for d in days)

    cards = []
    for day in days:
        share = day["exportKwh"] + day["importKwh"] or 1.0
        export_pct = 100.0 * day["exportKwh"] / share
        import_pct = 100.0 * day["importKwh"] / share
        cards.append(
            "<a class=\"day-card\" href=\"" + escape(day["href"]) + "\">"
            + "<div class=\"dow\">" + escape(day["weekday"]) + "</div>"
            + "<div class=\"date\">" + escape(day["short"]) + "</div>"
            + "<div class=\"wx\">" + escape(day["weather"]) + "</div>"
            + "<div class=\"meter\">"
            + f"<span style=\"width:{export_pct:.1f}%;background:var(--green)\"></span>"
            + f"<span style=\"width:{import_pct:.1f}%;background:var(--orange)\"></span>"
            + "</div>"
            + f"<div class=\"tiny\">{day['exportKwh']:.1f} out · {day['importKwh']:.1f} in</div>"
            + "</a>"
        )

    rows = []
    for day in days:
        klass = ""
        if day["date"] == sunniest["date"]:
            klass = " class=\"best\""
        elif day["billInr"] == worst_bill and day["date"] != sunniest["date"]:
            klass = " class=\"worst\""
        rows.append(
            f"<tr{klass}>"
            f"<td><a href=\"{escape(day['href'])}\">{escape(day['weekday'])} {escape(day['short'])}</a></td>"
            f"<td class=\"right\">{day['exportKwh']:.2f}</td>"
            f"<td class=\"right\">{day['importKwh']:.2f}</td>"
            f"<td class=\"right\">{day['loadKwh']:.2f}</td>"
            f"<td class=\"right\">{day['coverPct']:.0f}%</td>"
            f"<td class=\"right\">{day['capturePct']:.0f}%</td>"
            f"<td class=\"right\">{day['missedKwh']:.2f}</td>"
            f"<td class=\"right\">{day['missingMinutes']}</td>"
            f"<td class=\"right\">₹{day['billInr']:.1f}</td>"
            f"<td class=\"right\">{day['co2NetKg']:+.2f}</td>"
            f"<td>{escape(day['weather'])}</td>"
            "</tr>"
        )

    missing_html = ""
    if missing:
        listed = ", ".join(escape(day) for day in missing)
        missing_html = (
            "<div class=\"callout warn\"><div class=\"title\">Days without meter data</div>"
            f"<p>{listed}</p></div>"
        )

    site = first.get("site") or {}
    replacements = {
        "__TITLE__": escape(
            f"Day-by-day solar comparison — {_human_date(first['date'])} to {_human_date(last['date'])}"
        ),
        "__LEDE__": escape(
            f"{first.get('device') or 'device'}, {site.get('name') or ''} "
            f"({len(days)} days with data). Green is export, orange is import. "
            "Cards and the scoreboard link to each daily HTML report."
        ),
        "__EXPORT_KWH__": f"{export_kwh:.1f}",
        "__IMPORT_KWH__": f"{import_kwh:.1f}",
        "__BILL__": f"{bill:.0f}",
        "__SELF__": _pct(cover),
        "__MISSED_KWH__": f"{missed_kwh:.1f}",
        "__NARRATIVE__": escape(_narrative(days, missing)),
        "__DAY_CARDS__": "".join(cards),
        "__BEST_EXPORT__": escape(f"{sunniest['exportKwh']:.1f} kWh"),
        "__BEST_EXPORT_NOTE__": escape(f"{sunniest['weekday']} {sunniest['short']} · {sunniest['weather']}"),
        "__BEST_LOAD__": escape(f"{hungriest['loadKwh']:.1f} kWh"),
        "__BEST_LOAD_NOTE__": escape(f"{hungriest['weekday']} {hungriest['short']} inferred house load"),
        "__BEST_BILL__": escape(f"₹{cheapest['billInr']:.0f}"),
        "__BEST_BILL_NOTE__": escape(f"{cheapest['weekday']} {cheapest['short']} net payable"),
        "__BEST_MISSED__": escape(f"{most_missed['missedKwh']:.1f} kWh"),
        "__BEST_MISSED_NOTE__": escape(
            f"{most_missed['weekday']} {most_missed['short']} · {most_missed['islandMinutes']} min islanded"
        ),
        "__SCOREBOARD_HEAD__": scoreboard_head_html("bill"),
        "__ROWS__": "\n".join(rows),
        "__MISSING__": missing_html,
        "__DEVICE__": escape(str(first.get("device") or "")),
        "__SITE__": escape(f"{site.get('name') or ''} {site.get('lat', '')} N, {site.get('lon', '')} E"),
        "__TZ__": escape(str(first.get("timezone") or "IST")),
        "__START__": escape(first["date"]),
        "__END__": escape(last["date"]),
        "__DATA_JSON__": json.dumps(payload, separators=(",", ":")),
    }
    html = COMPARE_TEMPLATE
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html
