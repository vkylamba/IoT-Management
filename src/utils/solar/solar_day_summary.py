#!/usr/bin/env python3
"""Parse one day of mona meter JSON into a canvas-ready summary.

Usage:
  python3 solar_day_summary.py temp.json
  python3 solar_day_summary.py temp.json -o data/solar_day_summary.json
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc

# --- Site / plant -----------------------------------------------------------
LAT_DEG = 28.1278
LON_DEG = 75.6609
TZ_OFFSET_H = 5.5  # IST
SOLAR_DC_KW = 3.2
INVERTER_AC_KW = 5.0
# Typical India rooftop: south, tilt ≈ latitude.
TILT_DEG = LAT_DEG
AZIMUTH_DEG = 180.0  # south
# Module + inverter + wiring + soiling + temperature, clear cool day.
PERFORMANCE_RATIO = 0.82

# --- Grid / CO2 / tariff (RERC FY 2025-26, JVVNL net-metering Oct 2025) ----
GRID_KG_PER_KWH = 0.727
# Domestic 151–500 kWh/month slab. This site imports ~14 kWh/day.
IMPORT_ENERGY_INR = 7.00
REGULATORY_SURCHARGE_INR = 1.00
ELECTRICITY_DUTY_INR = 0.40
IMPORT_INR_PER_KWH = IMPORT_ENERGY_INR + REGULATORY_SURCHARGE_INR + ELECTRICITY_DUTY_INR
EXPORT_INR_PER_KWH = 3.26
FIXED_CHARGE_INR_PER_MONTH = 800.0  # >500 units/month domestic connection

STEP_MIN = 5
STEP_H = STEP_MIN / 60.0
BUCKETS_PER_DAY = 24 * 60 // STEP_MIN
# Daytime islanding: sun is up, no export, only a small house load on the meter.
ISLAND_EXPORT_MAX_KW = 0.05
ISLAND_IMPORT_MAX_KW = 0.6
DAYTIME_IDEAL_MIN_KW = 0.2
MIN_ISLAND_PATCH_BUCKETS = 2


def parse_utc(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(UTC)


def device_timezone(records: list[dict[str, Any]]) -> timezone:
    """Offset from the weather payload (`timezone` is seconds east of UTC)."""
    for rec in records:
        if rec.get("data_type") != "weather":
            continue
        offset = ((rec.get("data") or {}).get("timezone"))
        if offset is None:
            continue
        return timezone(timedelta(seconds=int(offset)))
    return timezone(timedelta(hours=TZ_OFFSET_H))


def tz_abbrev(tz: timezone, at: datetime) -> str:
    name = at.astimezone(tz).tzname()
    if name and name not in {"UTC", "UTC+05:30", "UTC+5:30"}:
        return name
    offset = tz.utcoffset(at) or timedelta(0)
    minutes = int(offset.total_seconds() // 60)
    if minutes == 330:
        return "IST"
    sign = "+" if minutes >= 0 else "-"
    hh, mm = divmod(abs(minutes), 60)
    return f"UTC{sign}{hh:02d}:{mm:02d}"


def device_id(records: list[dict[str, Any]]) -> str:
    for rec in records:
        data = rec.get("data") or {}
        name = data.get("dev")
        if name:
            return str(name)
    for rec in records:
        ip = rec.get("ip_address")
        if ip:
            return str(ip)
    return "unknown"


def signed_grid_export_w(meter_3: dict[str, Any]) -> float:
    """Positive watts = export to grid. Negative = import from grid."""
    power = float(meter_3.get("power") or 0.0)
    pf = float(meter_3.get("powerFactor") or 0.0)
    mag = abs(power)
    return mag if pf < 0 else -mag


def weather_kind(entry: dict[str, Any]) -> str:
    main = str(entry.get("main") or "")
    desc = str(entry.get("description") or "")
    icon = str(entry.get("icon") or "")
    if main == "Rain":
        return "rain"
    if icon.endswith("n"):
        return "night"
    if "overcast" in desc:
        return "overcast"
    return "broken"


def day_of_year(dt: datetime) -> int:
    return dt.timetuple().tm_yday


def declination_rad(doy: int) -> float:
    # Cooper 1969
    return math.radians(23.45) * math.sin(math.radians(360.0 * (284 + doy) / 365.0))


def equation_of_time_min(doy: int) -> float:
    b = math.radians(360.0 * (doy - 81) / 365.0)
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def solar_time_hours(dt: datetime) -> float:
    doy = day_of_year(dt)
    eot = equation_of_time_min(doy)
    lstm = 15.0 * TZ_OFFSET_H
    tc = 4.0 * (LON_DEG - lstm) + eot
    clock = dt.hour + dt.minute / 60.0 + dt.second / 3600.0 + TZ_OFFSET_H
    return (clock + tc / 60.0) % 24.0


def zenith_azimuth(dt: datetime) -> tuple[float, float]:
    lat = math.radians(LAT_DEG)
    dec = declination_rad(day_of_year(dt))
    hour_angle = math.radians(15.0 * (solar_time_hours(dt) - 12.0))
    cos_zen = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(hour_angle)
    cos_zen = max(-1.0, min(1.0, cos_zen))
    zen = math.acos(cos_zen)
    sin_zen = math.sin(zen)
    if sin_zen < 1e-6:
        az = 0.0
    else:
        cos_az = (math.sin(dec) - math.sin(lat) * cos_zen) / (math.cos(lat) * sin_zen)
        cos_az = max(-1.0, min(1.0, cos_az))
        az = math.acos(cos_az)
        if hour_angle > 0:
            az = 2.0 * math.pi - az
    return zen, az


def clear_sky_ghi_dhi_dni(zen: float) -> tuple[float, float, float]:
    """Haurwitz GHI + Erbs diffuse fraction. Returns W/m2."""
    if zen >= math.radians(90.0):
        return 0.0, 0.0, 0.0
    cosz = math.cos(zen)
    ghi = 1098.0 * cosz * math.exp(-0.057 / max(cosz, 0.02))
    ghi = max(0.0, ghi)
    kt = min(0.82, ghi / max(1361.0 * cosz, 1.0))
    if kt <= 0.22:
        kd = 1.0 - 0.09 * kt
    elif kt <= 0.80:
        kd = 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4
    else:
        kd = 0.165
    dhi = ghi * kd
    dni = (ghi - dhi) / max(cosz, 0.02)
    return ghi, dhi, max(0.0, dni)


def angle_of_incidence(zen: float, az: float) -> float:
    beta = math.radians(TILT_DEG)
    gamma = math.radians(AZIMUTH_DEG - 180.0)
    return math.acos(
        max(
            -1.0,
            min(
                1.0,
                math.cos(zen) * math.cos(beta)
                + math.sin(zen) * math.sin(beta) * math.cos(az - math.pi - gamma),
            ),
        )
    )


def plane_of_array_wm2(dt: datetime) -> float:
    zen, az = zenith_azimuth(dt)
    if zen >= math.radians(90.0):
        return 0.0
    ghi, dhi, dni = clear_sky_ghi_dhi_dni(zen)
    aoi = angle_of_incidence(zen, az)
    beam = dni * max(0.0, math.cos(aoi))
    beta = math.radians(TILT_DEG)
    sky = dhi * (1.0 + math.cos(beta)) / 2.0
    ground = ghi * 0.2 * (1.0 - math.cos(beta)) / 2.0
    return max(0.0, beam + sky + ground)


def ideal_ac_kw(dt: datetime) -> float:
    poa = plane_of_array_wm2(dt)
    dc = SOLAR_DC_KW * (poa / 1000.0)
    ac = dc * PERFORMANCE_RATIO
    return min(INVERTER_AC_KW, max(0.0, ac))


def bucket_floor(dt: datetime) -> datetime:
    minute = (dt.minute // STEP_MIN) * STEP_MIN
    return dt.replace(minute=minute, second=0, microsecond=0)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def is_grid_unavailable(grid_kw: float | None, ideal_kw: float, has_meter: bool) -> bool:
    """Daytime, no export, only a small house load. Missing samples are not islanding."""
    if not has_meter or grid_kw is None:
        return False
    return (
        ideal_kw >= DAYTIME_IDEAL_MIN_KW
        and grid_kw <= ISLAND_EXPORT_MAX_KW
        and grid_kw >= -ISLAND_IMPORT_MAX_KW
    )


def island_patches(flags: list[bool]) -> list[tuple[int, int]]:
    patches: list[tuple[int, int]] = []
    start: int | None = None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            if i - start >= MIN_ISLAND_PATCH_BUCKETS:
                patches.append((start, i - 1))
            start = None
    if start is not None and len(flags) - start >= MIN_ISLAND_PATCH_BUCKETS:
        patches.append((start, len(flags) - 1))
    return patches


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    meters = [r for r in records if r.get("data_type") == "meters-data" and r.get("data_arrival_time")]
    weather = [r for r in records if r.get("data_type") == "weather" and r.get("data_arrival_time")]
    if not meters:
        raise SystemExit("no meters-data records")

    meters.sort(key=lambda r: r["data_arrival_time"])
    first = parse_utc(meters[0]["data_arrival_time"])
    day_start = first.replace(hour=0, minute=0, second=0, microsecond=0)
    local_tz = device_timezone(records)
    tz_name = tz_abbrev(local_tz, first)
    tz_offset_min = int((local_tz.utcoffset(first) or timedelta(0)).total_seconds() // 60)

    def local_clock(dt: datetime) -> str:
        return dt.astimezone(local_tz).strftime("%H:%M")

    def local_clock_from_utc_minutes(minutes_from_utc_midnight: int) -> str:
        return local_clock(day_start + timedelta(minutes=minutes_from_utc_midnight))

    grid_b: dict[datetime, list[float]] = defaultdict(list)
    charger_b: dict[datetime, list[float]] = defaultdict(list)
    dht_temp: dict[datetime, list[float]] = defaultdict(list)
    dht_hum: dict[datetime, list[float]] = defaultdict(list)

    for rec in meters:
        t = bucket_floor(parse_utc(rec["data_arrival_time"]))
        data = rec.get("data") or {}
        m3 = data.get("meter_3") or {}
        m4 = data.get("meter_4") or {}
        grid_b[t].append(signed_grid_export_w(m3) / 1000.0)
        charger_b[t].append(float(m4.get("power") or 0.0) / 1000.0)
        dht = data.get("dht") or {}
        if dht.get("state") == 3:
            if dht.get("temperature") is not None:
                dht_temp[t].append(float(dht["temperature"]))
            if dht.get("humidity") is not None:
                dht_hum[t].append(float(dht["humidity"]))

    cloud_marks: list[tuple[datetime, float]] = []
    weather.sort(key=lambda r: r["data_arrival_time"])
    for rec in weather:
        t = parse_utc(rec["data_arrival_time"])
        clouds = ((rec.get("data") or {}).get("clouds") or {}).get("all")
        if clouds is None:
            continue
        cloud_marks.append((t, float(clouds) / 100.0))

    def cloud_fraction_at(dt: datetime) -> float:
        if not cloud_marks:
            return 0.0
        if dt <= cloud_marks[0][0]:
            return cloud_marks[0][1]
        for prev, nxt in zip(cloud_marks, cloud_marks[1:]):
            if prev[0] <= dt <= nxt[0]:
                span = (nxt[0] - prev[0]).total_seconds()
                if span <= 0:
                    return nxt[1]
                w = (dt - prev[0]).total_seconds() / span
                return prev[1] + w * (nxt[1] - prev[1])
        return cloud_marks[-1][1]

    keys = [day_start + timedelta(minutes=STEP_MIN * i) for i in range(BUCKETS_PER_DAY)]
    has_meter: list[bool] = []
    grid_kw: list[float | None] = []
    charger_kw: list[float | None] = []
    ideal_kw: list[float] = []
    gen_kw: list[float | None] = []

    night_imports: list[float] = []
    for key in keys:
        present = key in grid_b
        g = round(mean(grid_b[key]), 2) if present else None
        c = round(mean(charger_b[key]), 3) if present else None
        mid = key + timedelta(minutes=STEP_MIN / 2)
        ideal = round(ideal_ac_kw(mid), 2)
        # Overcast still has diffuse light; fully cloudy ≈ 25% of clear-sky POA.
        gen = round(ideal * (1.0 - 0.75 * cloud_fraction_at(mid)), 2) if present else None
        has_meter.append(present)
        grid_kw.append(g)
        charger_kw.append(c)
        ideal_kw.append(ideal)
        gen_kw.append(gen)
        if present and g is not None and ideal < 0.05 and g < 0:
            night_imports.append(-g)

    night_base = round(mean(night_imports), 2) if night_imports else 0.15
    # load = weather-adjusted generation − net grid export. Null when export exceeds
    # modelled PV, or when the meter sample is missing.
    load_kw: list[float | None] = []
    for present, g, c, gen, ideal in zip(has_meter, grid_kw, charger_kw, gen_kw, ideal_kw):
        if not present or g is None:
            load_kw.append(None)
            continue
        charger = c or 0.0
        if ideal < 0.05 and abs(g) < 0.05:
            load_kw.append(round(max(charger, night_base), 2))
            continue
        inferred = gen - g
        if inferred < 0:
            load_kw.append(None)
            continue
        load_kw.append(round(min(5.0, max(charger, inferred)), 2))

    island_flags = [
        is_grid_unavailable(g, ideal, present)
        for present, g, ideal in zip(has_meter, grid_kw, ideal_kw)
    ]
    missed_kw: list[float | None] = []
    for g, c, gen, flag in zip(grid_kw, charger_kw, gen_kw, island_flags):
        if not flag or g is None or gen is None:
            missed_kw.append(None)
            continue
        served = max(-g, c or 0.0, 0.0)
        missed_kw.append(round(max(0.0, gen - served), 2))
    patches = island_patches(island_flags)
    in_patch = [False] * len(grid_kw)
    for start, end in patches:
        for i in range(start, end + 1):
            in_patch[i] = True
    missed_kw = [value if in_patch[i] else None for i, value in enumerate(missed_kw)]
    missed_kwh = sum((value or 0.0) * STEP_H for value in missed_kw)
    island_minutes = sum(1 for flag in in_patch if flag) * STEP_MIN
    missed_credit_inr = missed_kwh * EXPORT_INR_PER_KWH
    island_windows = [
        {
            "startClock": local_clock_from_utc_minutes(start * STEP_MIN),
            "endClock": local_clock_from_utc_minutes(end * STEP_MIN),
            "startMinutesFromStart": start * STEP_MIN,
            "endMinutesFromStart": (end + 1) * STEP_MIN,
            "minutes": (end - start + 1) * STEP_MIN,
            "missedKwh": round(sum((missed_kw[i] or 0.0) * STEP_H for i in range(start, end + 1)), 2),
        }
        for start, end in patches
    ]
    gap_patches = island_patches([not present for present in has_meter])
    data_gap_windows = [
        {
            "startClock": local_clock_from_utc_minutes(start * STEP_MIN),
            "endClock": local_clock_from_utc_minutes(end * STEP_MIN),
            "startMinutesFromStart": start * STEP_MIN,
            "endMinutesFromStart": (end + 1) * STEP_MIN,
            "minutes": (end - start + 1) * STEP_MIN,
        }
        for start, end in gap_patches
    ]
    missing_minutes = sum(1 for present in has_meter if not present) * STEP_MIN

    import_kwh = sum(-g * STEP_H for g in grid_kw if g is not None and g < 0)
    export_kwh = sum(g * STEP_H for g in grid_kw if g is not None and g > 0)
    charger_kwh = sum((c or 0.0) * STEP_H for c in charger_kw if c is not None)
    ideal_kwh = sum(p * STEP_H for p in ideal_kw)
    ideal_observed_kwh = sum(ideal * STEP_H for ideal, present in zip(ideal_kw, has_meter) if present)
    gen_kwh = sum(p * STEP_H for p in gen_kw if p is not None)
    load_kwh = sum(p * STEP_H for p in load_kw if p is not None)
    emitted_kg = import_kwh * GRID_KG_PER_KWH
    avoided_kg = export_kwh * GRID_KG_PER_KWH

    import_inr = import_kwh * IMPORT_INR_PER_KWH
    export_credit_inr = export_kwh * EXPORT_INR_PER_KWH
    fixed_inr = FIXED_CHARGE_INR_PER_MONTH / 30.0
    energy_bill_inr = import_inr - export_credit_inr
    daily_bill_inr = energy_bill_inr + fixed_inr

    sampled = [i for i, value in enumerate(grid_kw) if value is not None]
    if not sampled:
        raise SystemExit("no meters-data records")
    peak_exp_i = max(sampled, key=lambda i: grid_kw[i] or 0)
    peak_imp_i = min(sampled, key=lambda i: grid_kw[i] or 0)
    load_sampled = [i for i, value in enumerate(load_kw) if value is not None]
    peak_load_i = max(load_sampled, key=lambda i: load_kw[i] or 0) if load_sampled else peak_exp_i
    peak_ideal_i = max(range(len(ideal_kw)), key=lambda i: ideal_kw[i])

    wx_out: list[dict[str, Any]] = []
    weather.sort(key=lambda r: r["data_arrival_time"])
    for rec in weather:
        t = parse_utc(rec["data_arrival_time"])
        w = ((rec.get("data") or {}).get("weather") or [{}])[0]
        main = (rec.get("data") or {}).get("main") or {}
        item = {
            "minutesFromStart": int((t - day_start).total_seconds() // 60),
            "clock": local_clock(t),
            "kind": weather_kind(w),
            "desc": w.get("description") or "",
            "tempC": round(float(main.get("temp") or 0.0) - 273.15, 1),
        }
        if wx_out and item["desc"] == wx_out[-1]["desc"] and item["minutesFromStart"] - wx_out[-1]["minutesFromStart"] < 20:
            continue
        wx_out.append(item)

    sunrise = sunset = None
    if weather:
        sys = (weather[0].get("data") or {}).get("sys") or {}
        if sys.get("sunrise"):
            sunrise = local_clock(datetime.fromtimestamp(sys["sunrise"], tz=UTC))
        if sys.get("sunset"):
            sunset = local_clock(datetime.fromtimestamp(sys["sunset"], tz=UTC))

    charger_on = next((i for i, c in enumerate(charger_kw) if c is not None and c > 0.05), None)
    charger_min = None if charger_on is None else charger_on * STEP_MIN
    local_start = day_start.astimezone(local_tz)
    local_end = (day_start + timedelta(minutes=(BUCKETS_PER_DAY - 1) * STEP_MIN)).astimezone(local_tz)
    hour_ticks = [
        {"minutesFromStart": hour * 60, "clock": local_clock_from_utc_minutes(hour * 60)}
        for hour in range(0, 24, 3)
    ]

    return {
        "date": day_start.date().isoformat(),
        "timezone": tz_name,
        "tzOffsetMinutes": tz_offset_min,
        "device": device_id(records),
        "site": {
            "name": "Chidawa",
            "lat": LAT_DEG,
            "lon": LON_DEG,
            "sunriseLocal": sunrise,
            "sunsetLocal": sunset,
        },
        "plant": {
            "solarDcKw": SOLAR_DC_KW,
            "inverterAcKw": INVERTER_AC_KW,
            "batteryAh": 4800,
            "batteryAgeYears": 5,
            "batteryType": "Lead Acid",
            "householdLoadKw": 5.0,
            "tiltDeg": round(TILT_DEG, 1),
            "azimuth": "south",
            "performanceRatio": PERFORMANCE_RATIO,
        },
        "tariff": {
            "importInrPerKwh": IMPORT_INR_PER_KWH,
            "exportInrPerKwh": EXPORT_INR_PER_KWH,
            "fixedInrPerMonth": FIXED_CHARGE_INR_PER_MONTH,
            "notes": "RERC FY 2025-26 domestic 151–500 slab ₹7.00 + ₹1.00 surcharge + ₹0.40 duty. Export credit ₹3.26/kWh JVVNL net metering (Oct 2025). Fixed charge prorated from ₹800/month.",
        },
        "co2KgPerKwh": GRID_KG_PER_KWH,
        "stepMinutes": STEP_MIN,
        "hourTicks": hour_ticks,
        "localStartClock": local_start.strftime("%H:%M"),
        "localEndClock": local_end.strftime("%H:%M"),
        "series": {
            "gridExportKw": grid_kw,
            "idealSolarKw": ideal_kw,
            "estimatedGenKw": gen_kw,
            "loadKw": load_kw,
            "chargerKw": charger_kw,
            "missedUtilKw": missed_kw,
            "hasMeter": has_meter,
        },
        "weather": wx_out,
        "totals": {
            "importKwh": round(import_kwh, 2),
            "exportKwh": round(export_kwh, 2),
            "idealSolarKwh": round(ideal_kwh, 2),
            "idealObservedKwh": round(ideal_observed_kwh, 2),
            "estimatedGenKwh": round(gen_kwh, 2),
            "loadKwh": round(load_kwh, 2),
            "chargerKwh": round(charger_kwh, 2),
            "missedUtilKwh": round(missed_kwh, 2),
            "missedUtilInr": round(missed_credit_inr, 1),
            "islandMinutes": island_minutes,
            "missingMinutes": missing_minutes,
            "co2EmittedKg": round(emitted_kg, 2),
            "co2AvoidedKg": round(avoided_kg, 2),
            "co2NetKg": round(emitted_kg - avoided_kg, 2),
            "importInr": round(import_inr, 1),
            "exportCreditInr": round(export_credit_inr, 1),
            "fixedInr": round(fixed_inr, 1),
            "energyBillInr": round(energy_bill_inr, 1),
            "dailyBillInr": round(daily_bill_inr, 1),
        },
        "peaks": {
            "exportKw": grid_kw[peak_exp_i],
            "exportClock": local_clock_from_utc_minutes(peak_exp_i * STEP_MIN),
            "importKw": abs(grid_kw[peak_imp_i]),
            "importClock": local_clock_from_utc_minutes(peak_imp_i * STEP_MIN),
            "idealKw": ideal_kw[peak_ideal_i],
            "idealClock": local_clock_from_utc_minutes(peak_ideal_i * STEP_MIN),
            "loadKw": load_kw[peak_load_i],
            "loadClock": local_clock_from_utc_minutes(peak_load_i * STEP_MIN),
        },
        "chargerMinutesFromStart": charger_min,
        "chargerClock": None if charger_min is None else local_clock_from_utc_minutes(charger_min),
        "islandWindows": island_windows,
        "dataGapWindows": data_gap_windows,
        "meterSamples": len(meters),
        "weatherSamples": len(weather),
        "nightStandbyKw": night_base,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize one day of solar meter JSON for the canvas.")
    parser.add_argument("input", type=Path, help="Path to meters JSON array")
    parser.add_argument("-o", "--output", type=Path, default=Path("data/solar_day_summary.json"))
    args = parser.parse_args()
    records = json.loads(args.input.read_text())
    summary = build_summary(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2))
    t = summary["totals"]
    p = summary["peaks"]
    print(f"wrote {args.output}")
    print(f"date {summary['date']} {summary['timezone']}  samples {summary['meterSamples']}")
    print(f"import {t['importKwh']} kWh  export {t['exportKwh']} kWh  ideal {t['idealSolarKwh']} kWh  load {t['loadKwh']} kWh")
    print(f"missed util {t['missedUtilKwh']} kWh  island {t['islandMinutes']} min  gaps {t['missingMinutes']} min  ₹{t['missedUtilInr']} export credit left on table")
    print(f"bill ₹{t['dailyBillInr']} (energy ₹{t['energyBillInr']} + fixed ₹{t['fixedInr']})")
    print(f"peak export {p['exportKw']} kW @ {p['exportClock']}  peak load {p['loadKw']} kW @ {p['loadClock']}")
    print(f"ideal peak {p['idealKw']} kW @ {p['idealClock']}")


if __name__ == "__main__":
    main()
