#!/usr/bin/env python3
"""Render a monthly HTML report from daily summaries built off raw-data JSON."""

from __future__ import annotations

import calendar
import json
from collections import Counter
from datetime import date, datetime
from html import escape
from typing import Any

from .solar_day_compare import (
    _cover_pct,
    _capture_pct,
    _hourly_net,
    _hour_labels,
    _narrative,
    _short_date,
    _weather_label,
    _weekday,
    scoreboard_head_html,
)
from .solar_day_summary import FIXED_CHARGE_INR_PER_MONTH

MONTH_TEMPLATE = r"""<!DOCTYPE html>
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
    .podium { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
    .podium .card { border: 1px solid var(--stroke); background: var(--elevated); padding: 12px; }
    .podium .rank { font-size: 11px; color: var(--text-3); letter-spacing: 0.04em; text-transform: uppercase; }
    .cal {
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 6px;
    }
    .cal .head { font-size: 11px; color: var(--text-3); text-align: center; letter-spacing: 0.04em; text-transform: uppercase; }
    .cal a, .cal .pad, .cal .gone {
      min-height: 78px;
      border: 1px solid var(--stroke);
      background: var(--elevated);
      padding: 8px;
      text-decoration: none;
      color: inherit;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .cal .pad { border-color: transparent; background: transparent; }
    .cal .gone { opacity: 0.55; }
    .cal .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 4px; }
    .cal .num { font-weight: 590; }
    .cal .wx { width: 18px; height: 18px; color: var(--text-2); flex: 0 0 18px; }
    .cal .wx svg { display: block; width: 18px; height: 18px; }
    .cal .net { font-size: 12px; color: var(--text-2); }
    .meter { height: 6px; background: rgba(240,240,240,0.08); overflow: hidden; display: flex; }
    .meter span { display: block; height: 100%; }
    a { color: var(--accent); }
    @media (max-width: 720px) {
      .grid-4, .podium { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .cal a, .cal .gone { min-height: 64px; padding: 6px; }
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
      <div><div class="stat-value tone-success">__EXPORT_KWH__ kWh</div><div class="stat-label">Exported this month</div></div>
      <div><div class="stat-value tone-warning">__IMPORT_KWH__ kWh</div><div class="stat-label">Imported this month</div></div>
      <div><div class="stat-value">₹__BILL__</div><div class="stat-label">Estimated monthly grid bill</div></div>
      <div><div class="stat-value">__NET_KWH__ kWh</div><div class="stat-label">Net grid energy (export − import)</div></div>
    </div>
    <div class="grid-4">
      <div><div class="stat-value">__MISSED_KWH__ kWh</div><div class="stat-label">Missed utilization</div></div>
      <div><div class="stat-value">__ISLAND_MIN__ min</div><div class="stat-label">Grid-unavailable daytime</div></div>
      <div><div class="stat-value">__GAP_MIN__ min</div><div class="stat-label">Missing meter samples</div></div>
      <div><div class="stat-value">__CO2__ kg</div><div class="stat-label">Net CO2 (emitted − avoided)</div></div>
    </div>

    <div class="callout info">
      <div class="title">The month in one sentence</div>
      <p>__NARRATIVE__</p>
    </div>

    <h2>Calendar</h2>
    <p class="muted">Each cell is a UTC day. Green tint is net export, orange is net import. The icon is that day's most common daytime weather. Grey cells have no raw file. Click a day for the full report. The bar is export versus import that day.</p>
    <div class="cal">__CALENDAR__</div>

    <h2>Who stood out</h2>
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
        <div class="rank">Cheapest energy day</div>
        <div class="stat-value tone-info">__BEST_BILL__</div>
        <p class="tiny">__BEST_BILL_NOTE__</p>
      </div>
      <div class="card">
        <div class="rank">Most unused sun</div>
        <div class="stat-value">__BEST_MISSED__</div>
        <p class="tiny">__BEST_MISSED_NOTE__</p>
      </div>
    </div>

    <h2>Monthly grid bill</h2>
    <p class="muted">Energy charges are the sum of daily import and export. The ₹__FIXED_MONTH__ fixed charge is applied once for the month, not prorated onto each daily report.</p>
    <table class="framed">
      <thead>
        <tr><th>Item</th><th class="right">Energy</th><th class="right">Amount</th></tr>
      </thead>
      <tbody>
        <tr><td>Grid import</td><td class="right">__IMPORT_KWH_EXACT__ kWh</td><td class="right">₹__IMPORT_INR__</td></tr>
        <tr><td>Grid export credit</td><td class="right">__EXPORT_KWH_EXACT__ kWh</td><td class="right">−₹__EXPORT_INR__</td></tr>
        <tr><td>Fixed charge</td><td class="right">—</td><td class="right">₹__FIXED_MONTH__</td></tr>
        <tr><td>Net payable</td><td class="right">—</td><td class="right">₹__BILL_EXACT__</td></tr>
      </tbody>
    </table>

    <h2>Import versus export by day</h2>
    <p class="muted">Orange is import, green is export, tan is missed utilization. The dashed tick is that day's clear-sky ideal. Days without files are omitted from the chart.</p>
    <div class="chart-wrap" id="bars"></div>

    <h2>Weekday rhythm</h2>
    <p class="muted">Average export and import by weekday across days that have meter files. A weekday that imports more is usually heavier evening load or weaker sun, not a missing file.</p>
    <div class="chart-wrap" id="weekdays"></div>

    <h2>Running net energy</h2>
    <p class="muted">Cumulative export minus import. Above zero means the month is a net exporter so far.</p>
    <div class="chart-wrap" id="running"></div>

    <h2>Typical day on the meter</h2>
    <p class="muted">Hourly net grid power for every day with data, overlaid. Positive is export. The thick line is the monthly average of hours that actually have samples.</p>
    <div class="chart-wrap" id="overlay"></div>

    <h2>Scoreboard</h2>
    <p class="muted">Hover a column title for the unit and how that number is made.</p>
    <table class="framed">
      <thead>
        <tr>__SCOREBOARD_HEAD__</tr>
      </thead>
      <tbody>__ROWS__</tbody>
    </table>
    __MISSING__

    <p class="tiny">Source: raw-data/{YYYY-MM-DD}.json via solar_day_html.py --month · device __DEVICE__ · __SITE__ · clocks are device local time (__TZ__). Monthly bill = import energy − export credit + one ₹__FIXED_MONTH__ fixed charge. CO2 = signed kWh × 0.727 kg/kWh. Calendar is UTC days in __MONTH_NAME__.</p>
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
    const step = m <= 5 ? 1 : m <= 20 ? 5 : m <= 50 ? 10 : 20;
    return Math.ceil((m * (pad || 1.12)) / step) * step;
  }
  function yTicks(max, n) {
    const out = [];
    for (let i = 0; i <= n; i++) out.push(Math.round((max * i / n) * 10) / 10);
    return out;
  }
  function netPath(values, xAt, yAt) {
    const parts = [];
    let drawing = false;
    values.forEach((v,i) => {
      if (v == null) { drawing = false; return; }
      parts.push((drawing?"L":"M")+xAt(i).toFixed(1)+","+yAt(v).toFixed(1));
      drawing = true;
    });
    return parts.join(" ");
  }

  function drawBars(host) {
    const days = DATA.days;
    const width = 1040, height = 280;
    const pad = { top: 18, right: 16, bottom: 40, left: 46 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const yMax = niceMax(days.flatMap(d => [d.importKwh, d.exportKwh, d.idealKwh, d.missedKwh]));
    const groupW = innerW / days.length;
    const barW = Math.max(2, groupW * 0.26);
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
      const missedH = (d.missedKwh / yMax) * innerH;
      const idealY = pad.top + ((yMax - d.idealKwh) / yMax) * innerH;
      el("rect", { x: x0 + groupW*0.12, y: pad.top + innerH - importH, width: barW, height: Math.max(0, importH), fill: COLORS.orange, opacity: 0.92 }, svg);
      el("rect", { x: x0 + groupW*0.12 + barW + 2, y: pad.top + innerH - exportH, width: barW, height: Math.max(0, exportH), fill: COLORS.green, opacity: 0.92 }, svg);
      el("rect", { x: x0 + groupW*0.12 + 2*barW + 4, y: pad.top + innerH - missedH, width: Math.max(2, barW*0.55), height: Math.max(0, missedH), fill: COLORS.missed, opacity: 0.9 }, svg);
      el("line", { x1: x0 + groupW*0.1, x2: x0 + groupW*0.9, y1: idealY, y2: idealY, stroke: COLORS.accent, "stroke-dasharray": "4 3" }, svg);
      const t = el("text", { x: x0 + groupW/2, y: height-14, "text-anchor": "middle", fill: COLORS.text3, "font-size": 10, "font-family": "inherit" }, svg);
      t.textContent = d.dayNum;
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
    host.appendChild(svg);
  }

  function drawWeekdays(host) {
    const rows = DATA.weekdays;
    const width = 1040, height = 240;
    const pad = { top: 18, right: 16, bottom: 40, left: 46 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const yMax = niceMax(rows.flatMap(d => [d.importKwh, d.exportKwh]));
    const groupW = innerW / rows.length;
    const barW = groupW * 0.28;
    const svg = el("svg", { viewBox: "0 0 "+width+" "+height, width: "100%", role: "img" });
    yTicks(yMax, 4).forEach(tick => {
      const y = pad.top + ((yMax - tick) / yMax) * innerH;
      el("line", { x1: pad.left, x2: width-pad.right, y1: y, y2: y, stroke: COLORS.stroke3, "stroke-dasharray": "3 4" }, svg);
      const t = el("text", { x: pad.left-8, y: y+4, "text-anchor": "end", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = String(tick);
    });
    rows.forEach((d, i) => {
      const x0 = pad.left + i * groupW;
      const importH = (d.importKwh / yMax) * innerH;
      const exportH = (d.exportKwh / yMax) * innerH;
      el("rect", { x: x0 + groupW*0.22, y: pad.top + innerH - importH, width: barW, height: Math.max(0, importH), fill: COLORS.orange, opacity: 0.92 }, svg);
      el("rect", { x: x0 + groupW*0.22 + barW + 4, y: pad.top + innerH - exportH, width: barW, height: Math.max(0, exportH), fill: COLORS.green, opacity: 0.92 }, svg);
      const t = el("text", { x: x0 + groupW/2, y: height-14, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = d.label;
    });
    const ylab = el("text", { x: 14, y: pad.top+8, fill: COLORS.text3, "font-size": 11, "font-family": "inherit",
      transform: "rotate(-90 14 "+(pad.top+innerH/2)+")" }, svg);
    ylab.textContent = "Average kWh";
    host.appendChild(svg);
  }

  function drawRunning(host) {
    const days = DATA.days;
    const width = 1040, height = 260;
    const pad = { top: 18, right: 16, bottom: 40, left: 50 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const running = [];
    let acc = 0;
    days.forEach(d => { acc += d.exportKwh - d.importKwh; running.push(acc); });
    const yMin = Math.min(0, ...running);
    const yMax = Math.max(0.1, ...running);
    const span = yMax - yMin || 1;
    const xAt = i => pad.left + (days.length === 1 ? innerW / 2 : (i / (days.length - 1)) * innerW);
    const yAt = v => pad.top + ((yMax - v) / span) * innerH;
    const svg = el("svg", { viewBox: "0 0 "+width+" "+height, width: "100%", role: "img" });
    [yMax, 0, yMin].forEach(tick => {
      const y = yAt(tick);
      el("line", { x1: pad.left, x2: width-pad.right, y1: y, y2: y,
        stroke: tick===0 ? COLORS.stroke : COLORS.stroke3, "stroke-dasharray": tick===0?undefined:"3 4" }, svg);
      const t = el("text", { x: pad.left-8, y: y+4, "text-anchor": "end", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = String(Math.round(tick));
    });
    const zeroY = yAt(0);
    const fill = "M"+xAt(0).toFixed(1)+","+zeroY.toFixed(1)+" "+running.map((v,i)=>"L"+xAt(i).toFixed(1)+","+yAt(v).toFixed(1)).join(" ")+" L"+xAt(running.length-1).toFixed(1)+","+zeroY.toFixed(1)+" Z";
    el("path", { d: fill, fill: running[running.length-1] >= 0 ? COLORS.green : COLORS.orange, opacity: 0.18 }, svg);
    el("path", { d: netPath(running, xAt, yAt), fill: "none", stroke: COLORS.text, "stroke-width": 1.8 }, svg);
    running.forEach((v,i) => el("circle", { cx: xAt(i), cy: yAt(v), r: 2.5, fill: COLORS.bg, stroke: COLORS.text }, svg));
    days.forEach((d, i) => {
      if (i % 2 && days.length > 16) return;
      const t = el("text", { x: xAt(i), y: height-14, "text-anchor": "middle", fill: COLORS.text3, "font-size": 10, "font-family": "inherit" }, svg);
      t.textContent = d.dayNum;
    });
    const ylab = el("text", { x: 14, y: pad.top+8, fill: COLORS.text3, "font-size": 11, "font-family": "inherit",
      transform: "rotate(-90 14 "+(pad.top+innerH/2)+")" }, svg);
    ylab.textContent = "Cumulative net kWh";
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
    days.forEach(d => {
      el("path", { d: netPath(d.hourlyNetKw, xAt, yAt), fill: "none", stroke: COLORS.stroke, "stroke-width": 1.0 }, svg);
    });
    el("path", { d: netPath(DATA.averageHourlyNetKw, xAt, yAt), fill: "none", stroke: COLORS.text, "stroke-width": 2 }, svg);
    [0,6,12,18].forEach(h => {
      const t = el("text", { x: xAt(h), y: height-14, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
      t.textContent = DATA.hourLabels[h];
    });
    const xlab = el("text", { x: width/2, y: height-1, "text-anchor": "middle", fill: COLORS.text3, "font-size": 11, "font-family": "inherit" }, svg);
    xlab.textContent = "Time ("+DATA.timezone+")";
    const ylab = el("text", { x: 14, y: pad.top+8, fill: COLORS.text3, "font-size": 11, "font-family": "inherit",
      transform: "rotate(-90 14 "+(pad.top+innerH/2)+")" }, svg);
    ylab.textContent = "Net grid (kW)";
    host.appendChild(svg);
  }

  drawBars(document.getElementById("bars"));
  drawWeekdays(document.getElementById("weekdays"));
  drawRunning(document.getElementById("running"));
  drawOverlay(document.getElementById("overlay"));
  </script>
</body>
</html>
"""


WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEATHER_ICON_SVG = {
    "rain": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M6.5 12.5h9.2a3.2 3.2 0 0 0 .2-6.4 4.4 4.4 0 0 0-8.4-1.2A3.4 3.4 0 0 0 6.5 12.5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M8 15.5l-1 3M12 15.5l-1 3M16 15.5l-1 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>'
        "</svg>"
    ),
    "overcast": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M7 11h8.5a2.8 2.8 0 0 0 .15-5.6 3.9 3.9 0 0 0-7.5-1A3 3 0 0 0 7 11z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M6 16.5h11a3 3 0 0 0 .2-6 4.2 4.2 0 0 0-4.1-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ),
    "broken": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<circle cx="8" cy="8" r="3.2" fill="currentColor" opacity="0.35"/>'
        '<circle cx="8" cy="8" r="3.2" fill="none" stroke="currentColor" stroke-width="1.6"/>'
        '<path d="M7 16.5h9.2a3.2 3.2 0 0 0 .2-6.4 4.4 4.4 0 0 0-8.4-1.2A3.4 3.4 0 0 0 7 16.5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ),
    "night": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M14.5 6.2a6.2 6.2 0 1 0 3.3 11.4A7 7 0 0 1 10 8.4 6.4 6.4 0 0 0 14.5 6.2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ),
    "clear": (
        '<svg viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M10 7.2a4.2 4.2 0 1 0 5.3 5.4A4.6 4.6 0 0 1 10 7.2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M6.5 17h10a2.8 2.8 0 0 0 .15-5.5 3.6 3.6 0 0 0-6.6-.7A2.9 2.9 0 0 0 6.5 17z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    ),
}


def parse_month(value: str) -> tuple[int, int]:
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise SystemExit(f"month must be YYYY-MM, got {value!r}") from exc
    return parsed.year, parsed.month


def month_dates(year: int, month: int) -> list[date]:
    last = calendar.monthrange(year, month)[1]
    return [date(year, month, day) for day in range(1, last + 1)]


def _weather_kind(summary: dict[str, Any]) -> str | None:
    marks = summary.get("weather") or []
    daytime = [str(item.get("kind")) for item in marks if item.get("kind") and item.get("kind") != "night"]
    kinds = daytime or [str(item.get("kind")) for item in marks if item.get("kind")]
    if not kinds:
        return None
    return Counter(kinds).most_common(1)[0][0]


def _weather_icon_html(kind: str | None, label: str) -> str:
    if not kind:
        return ""
    svg = WEATHER_ICON_SVG.get(kind) or WEATHER_ICON_SVG["broken"]
    title = escape(label) if label and label != "no weather" else escape(kind)
    return f'<span class="wx" title="{title}">{svg}</span>'


def _day_payload(summary: dict[str, Any]) -> dict[str, Any]:
    totals = summary["totals"]
    stamp = summary["date"]
    return {
        "date": stamp,
        "dayNum": str(int(stamp.split("-")[2])),
        "short": _short_date(stamp),
        "weekday": _weekday(stamp),
        "href": f"grid-solar-day-{stamp}.html",
        "importKwh": totals["importKwh"],
        "exportKwh": totals["exportKwh"],
        "idealKwh": totals["idealSolarKwh"],
        "loadKwh": totals["loadKwh"],
        "genKwh": totals["estimatedGenKwh"],
        "energyBillInr": float(totals.get("energyBillInr") or 0.0),
        "billInr": float(totals.get("energyBillInr") or 0.0),
        "importInr": float(totals.get("importInr") or 0.0),
        "exportCreditInr": float(totals.get("exportCreditInr") or 0.0),
        "co2EmittedKg": totals["co2EmittedKg"],
        "co2AvoidedKg": totals["co2AvoidedKg"],
        "co2NetKg": totals["co2NetKg"],
        "coverPct": _cover_pct(totals),
        "capturePct": _capture_pct(totals),
        "missedKwh": float(totals.get("missedUtilKwh") or 0.0),
        "islandMinutes": int(totals.get("islandMinutes") or 0),
        "missingMinutes": int(totals.get("missingMinutes") or 0),
        "weather": _weather_label(summary),
        "weatherKind": _weather_kind(summary),
        "hourlyNetKw": _hourly_net(summary),
    }


def _weekday_averages(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, label in enumerate(WEEKDAY_LABELS):
        subset = [
            day for day in days
            if datetime.strptime(day["date"], "%Y-%m-%d").weekday() == index
        ]
        count = len(subset)
        rows.append({
            "label": label,
            "count": count,
            "exportKwh": round(sum(d["exportKwh"] for d in subset) / count, 2) if count else 0.0,
            "importKwh": round(sum(d["importKwh"] for d in subset) / count, 2) if count else 0.0,
        })
    return rows


def _cell_background(net_kwh: float, peak: float) -> str:
    if peak <= 0:
        return "var(--elevated)"
    intensity = min(1.0, abs(net_kwh) / peak)
    alpha = 0.08 + 0.32 * intensity
    if net_kwh >= 0:
        return f"rgba(31,138,101,{alpha:.2f})"
    return f"rgba(192,96,40,{alpha:.2f})"


def _calendar_html(
    year: int,
    month: int,
    by_date: dict[str, dict[str, Any]],
    missing: list[str],
) -> str:
    missing_set = set(missing)
    present_nets = [d["exportKwh"] - d["importKwh"] for d in by_date.values()]
    peak = max((abs(value) for value in present_nets), default=1.0) or 1.0
    cells = [f'<div class="head">{label}</div>' for label in WEEKDAY_LABELS]
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    for week in weeks:
        for day in week:
            if day.month != month:
                cells.append('<div class="pad"></div>')
                continue
            stamp = day.isoformat()
            payload = by_date.get(stamp)
            if payload is None:
                reason = "no raw file" if stamp in missing_set else "no meter data"
                cells.append(
                    f'<div class="gone"><div class="num">{day.day}</div>'
                    f'<div class="tiny">{reason}</div></div>'
                )
                continue
            net = payload["exportKwh"] - payload["importKwh"]
            share = payload["exportKwh"] + payload["importKwh"] or 1.0
            export_pct = 100.0 * payload["exportKwh"] / share
            import_pct = 100.0 * payload["importKwh"] / share
            sign = "+" if net >= 0 else "−"
            icon = _weather_icon_html(payload.get("weatherKind"), payload.get("weather") or "")
            cells.append(
                f'<a href="{escape(payload["href"])}" style="background:{_cell_background(net, peak)}">'
                f'<div class="top"><div class="num">{day.day}</div>{icon}</div>'
                f'<div class="net">{sign}{abs(net):.1f} kWh</div>'
                '<div class="meter">'
                f'<span style="width:{export_pct:.1f}%;background:var(--green)"></span>'
                f'<span style="width:{import_pct:.1f}%;background:var(--orange)"></span>'
                "</div>"
                f'<div class="tiny">{payload["exportKwh"]:.1f} out</div>'
                "</a>"
            )
    return "".join(cells)


def render_month_html(
    year: int,
    month: int,
    summaries: list[dict[str, Any]],
    missing: list[str] | None = None,
) -> str:
    missing = missing or []
    if not summaries:
        raise SystemExit(f"no days with meter data in {year:04d}-{month:02d}")
    days = [_day_payload(summary) for summary in summaries]
    by_date = {day["date"]: day for day in days}
    n = len(days[0]["hourlyNetKw"]) if days else 0
    average = []
    for i in range(n):
        values = [day["hourlyNetKw"][i] for day in days if day["hourlyNetKw"][i] is not None]
        average.append(round(sum(values) / len(values), 3) if values else None)
    first = summaries[0]
    month_name = date(year, month, 1).strftime("%B %Y")
    days_in_month = calendar.monthrange(year, month)[1]
    export_kwh = sum(d["exportKwh"] for d in days)
    import_kwh = sum(d["importKwh"] for d in days)
    import_inr = sum(d["importInr"] for d in days)
    export_inr = sum(d["exportCreditInr"] for d in days)
    energy_bill = import_inr - export_inr
    monthly_bill = energy_bill + FIXED_CHARGE_INR_PER_MONTH
    missed_kwh = sum(d["missedKwh"] for d in days)
    island_min = sum(d["islandMinutes"] for d in days)
    gap_min = sum(d["missingMinutes"] for d in days)
    co2_net = sum(d["co2NetKg"] for d in days)
    sunniest = max(days, key=lambda d: d["exportKwh"])
    hungriest = max(days, key=lambda d: d["loadKwh"])
    cheapest = min(days, key=lambda d: d["energyBillInr"])
    most_missed = max(days, key=lambda d: d["missedKwh"])
    worst_energy = max(d["energyBillInr"] for d in days)

    rows = []
    for day in days:
        klass = ""
        if day["date"] == sunniest["date"]:
            klass = ' class="best"'
        elif day["energyBillInr"] == worst_energy and day["date"] != sunniest["date"]:
            klass = ' class="worst"'
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
            f"<td class=\"right\">₹{day['energyBillInr']:.1f}</td>"
            f"<td class=\"right\">{day['co2NetKg']:+.2f}</td>"
            f"<td>{escape(day['weather'])}</td>"
            "</tr>"
        )

    missing_html = ""
    if missing:
        listed = ", ".join(escape(day) for day in missing)
        missing_html = (
            '<div class="callout warn"><div class="title">Days without a usable raw file</div>'
            f"<p>{listed}</p></div>"
        )

    payload = {
        "timezone": first.get("timezone") or "IST",
        "hourLabels": _hour_labels(first),
        "days": days,
        "weekdays": _weekday_averages(days),
        "averageHourlyNetKw": average,
        "missing": missing,
    }
    site = first.get("site") or {}
    replacements = {
        "__TITLE__": escape(f"{month_name} — grid-tied solar month"),
        "__LEDE__": escape(
            f"{first.get('device') or 'device'}, {site.get('name') or ''} · "
            f"{len(days)} of {days_in_month} UTC days from raw-data. "
            "Green is export, orange is import. Daily pages open from the calendar."
        ),
        "__EXPORT_KWH__": f"{export_kwh:.1f}",
        "__IMPORT_KWH__": f"{import_kwh:.1f}",
        "__NET_KWH__": f"{export_kwh - import_kwh:.1f}",
        "__BILL__": f"{monthly_bill:.0f}",
        "__BILL_EXACT__": f"{monthly_bill:.1f}",
        "__MISSED_KWH__": f"{missed_kwh:.1f}",
        "__ISLAND_MIN__": str(island_min),
        "__GAP_MIN__": str(gap_min),
        "__CO2__": f"{co2_net:+.1f}",
        "__NARRATIVE__": escape(_narrative(days, missing)),
        "__CALENDAR__": _calendar_html(year, month, by_date, missing),
        "__BEST_EXPORT__": escape(f"{sunniest['exportKwh']:.1f} kWh"),
        "__BEST_EXPORT_NOTE__": escape(f"{sunniest['weekday']} {sunniest['short']} · {sunniest['weather']}"),
        "__BEST_LOAD__": escape(f"{hungriest['loadKwh']:.1f} kWh"),
        "__BEST_LOAD_NOTE__": escape(f"{hungriest['weekday']} {hungriest['short']} inferred house load"),
        "__BEST_BILL__": escape(f"₹{cheapest['energyBillInr']:.0f}"),
        "__BEST_BILL_NOTE__": escape(f"{cheapest['weekday']} {cheapest['short']} energy only, before the monthly fixed charge"),
        "__BEST_MISSED__": escape(f"{most_missed['missedKwh']:.1f} kWh"),
        "__BEST_MISSED_NOTE__": escape(
            f"{most_missed['weekday']} {most_missed['short']} · {most_missed['islandMinutes']} min islanded"
        ),
        "__IMPORT_KWH_EXACT__": f"{import_kwh:.2f}",
        "__EXPORT_KWH_EXACT__": f"{export_kwh:.2f}",
        "__IMPORT_INR__": f"{import_inr:.1f}",
        "__EXPORT_INR__": f"{export_inr:.1f}",
        "__FIXED_MONTH__": f"{FIXED_CHARGE_INR_PER_MONTH:.0f}",
        "__SCOREBOARD_HEAD__": scoreboard_head_html("energy"),
        "__ROWS__": "\n".join(rows),
        "__MISSING__": missing_html,
        "__DEVICE__": escape(str(first.get("device") or "")),
        "__SITE__": escape(f"{site.get('name') or ''} {site.get('lat', '')} N, {site.get('lon', '')} E"),
        "__TZ__": escape(str(first.get("timezone") or "IST")),
        "__MONTH_NAME__": escape(month_name),
        "__DATA_JSON__": json.dumps(payload, separators=(",", ":")),
    }
    html = MONTH_TEMPLATE
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html
