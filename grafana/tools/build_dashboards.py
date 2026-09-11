#!/usr/bin/env python3
"""Generate the temporary Grafana dashboards (JSON) for Apex Health — v2.

v2: colored visual system (per-series fixed colors, gradient fills,
threshold bands/dashed lines), sparkline stats, gauges + bar gauges,
donuts, emoji forecast/text panels, cross-dashboard navigation dropdown,
and ~40 new panels (YTD totals, elevation, hour-of-day, sleep debt,
bedtime consistency, tier/model mix, latency, lab reference checks,
rollups, invites, users, ops notes).

Emits one JSON file per dashboard into <repo>/grafana/dashboards/. Every
panel uses raw SQL against the real schema — re-run this script after
schema changes to regenerate. Generated artifacts are committed so Grafana
provisions them directly (grafana/provisioning/dashboards/provider.yml).

Usage: python3 build_dashboards.py [repo_root]
"""
import json
import sys
from pathlib import Path

DS = {"type": "grafana-postgresql-datasource", "uid": "apex-pg"}
TAGS = ["apex-health", "temp-ui"]

# --- semantic palette (Grafana-native hexes) --------------------------------
GREEN = "#73BF69"
DGREEN = "#56A64B"
RED = "#F2495C"
ORANGE = "#FF9830"
YELLOW = "#FADE2A"
BLUE = "#5794F2"
DBLUE = "#3D71D9"
CYAN = "#6ED0E0"
PURPLE = "#B877D9"
VIOLET = "#705DA0"
PINK = "#E02F44"
BROWN = "#C15C17"

_id = [100]


def nid() -> int:
    _id[0] += 1
    return _id[0]


def tgt(sql: str, ref: str = "A", fmt: str = "time_series") -> dict:
    return {"datasource": DS, "editorMode": "code", "rawQuery": True,
            "rawSql": sql, "refId": ref, "format": fmt}


TS_CUSTOM = {"drawStyle": "line", "lineWidth": 3, "fillOpacity": 22,
             "gradientMode": "opacity", "showPoints": "never",
             "spanNulls": True, "pointSize": 5, "axisPlacement": "auto",
             "thresholdsStyle": {"mode": "off"}}
BAR_CUSTOM = {"drawStyle": "bars", "lineWidth": 1, "fillOpacity": 85,
              "showPoints": "never", "spanNulls": False}
STACK = {"mode": "normal", "group": "A"}
HBAR_OPTS = {"orientation": "horizontal", "showValue": "never",
             "stacking": "off", "groupWidth": 0.7, "barWidth": 0.8,
             "legend": {"displayMode": "list", "placement": "right", "showLegend": True},
             "tooltip": {"mode": "multi", "sort": "desc"}, "xTickLabelRotation": 0}

LEGEND_TABLE = {"displayMode": "table", "placement": "bottom",
                "showLegend": True, "calcs": ["lastNotNull"]}
LEGEND_BOTTOM = {"displayMode": "list", "placement": "bottom", "showLegend": True}


def ov_color(field, hexcolor):
    return {"matcher": {"id": "byName", "options": field},
            "properties": [{"id": "color",
                            "value": {"mode": "fixed", "fixedColor": hexcolor}}]}


def ov_right(field):
    return {"matcher": {"id": "byName", "options": field},
            "properties": [{"id": "custom.axisPlacement", "value": "right"},
                           {"id": "custom.fillOpacity", "value": 8}]}


def ov_unit(field, unit):
    return {"matcher": {"id": "byName", "options": field},
            "properties": [{"id": "unit", "value": unit}]}


def ov_map(field, mapping):
    return {"matcher": {"id": "byName", "options": field},
            "properties": [{"id": "mappings", "value": mapping}]}


def sev_mapping():
    def m(key, color, idx):
        return {key: {"color": color, "index": idx, "text": key}}
    return {"type": "value",
            "options": {**m("critical", "red", 0), **m("error", "red", 1),
                        **m("warning", "orange", 2), **m("info", "blue", 3),
                        **m("sync_failure", "red", 4)}}


def panel(ptype, title, x, y, w, h, targets, desc=None, unit=None,
          opts=None, custom=None, overrides=None, minv=None, maxv=None,
          thresholds=None, thr_style=None, legend=None):
    if opts is None:
        if ptype == "timeseries":
            opts = {"legend": legend or LEGEND_BOTTOM,
                    "tooltip": {"mode": "multi", "sort": "desc"}}
        elif ptype == "stat":
            opts = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "",
                                      "values": False},
                    "textMode": "auto", "colorMode": "value",
                    "graphMode": "area", "wideLayout": True}
        elif ptype == "gauge":
            opts = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "",
                                      "values": False},
                    "showThresholdLabels": False, "showThresholdMarkers": True,
                    "minVizHeight": 75, "minVizWidth": 75}
        elif ptype == "bargauge":
            opts = {"displayMode": "gradient", "minVizHeight": 10,
                    "minVizWidth": 0, "namePlacement": "auto",
                    "orientation": "horizontal",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "",
                                      "values": False},
                    "showUnfilled": True, "sizing": "auto",
                    "valueMode": "color"}
        elif ptype == "table":
            opts = {"showHeader": True, "cellHeight": "sm"}
        elif ptype == "barchart":
            opts = {"orientation": "auto", "showValue": "never",
                    "stacking": "off", "groupWidth": 0.7, "barWidth": 0.8,
                    "legend": {"displayMode": "list", "placement": "bottom",
                               "showLegend": True},
                    "tooltip": {"mode": "multi", "sort": "desc"},
                    "xTickLabelRotation": -25}
        elif ptype == "piechart":
            opts = {"pieType": "donut", "displayLabels": ["name", "percent"],
                    "legend": {"displayMode": "table", "placement": "right",
                               "showLegend": True, "values": ["value"]},
                    "tooltip": {"mode": "single", "sort": "none"}}
        else:
            opts = {}
    if custom is None:
        custom = TS_CUSTOM if ptype == "timeseries" else {}
    if thr_style and ptype == "timeseries":
        custom = {**custom, "thresholdsStyle": {"mode": thr_style}}
    if ptype == "stat" and thresholds is None:
        thresholds = {"mode": "absolute",
                      "steps": [{"color": "blue", "value": None}]}
    return {"id": nid(), "type": ptype, "title": title,
            "description": desc or "",
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "datasource": DS, "targets": targets,
            "fieldConfig": {"defaults": {"unit": unit, "custom": custom,
                                         "min": minv, "max": maxv,
                                         "thresholds": thresholds or
                                         {"mode": "absolute", "steps": [
                                             {"color": "green", "value": None}]}},
                            "overrides": overrides or []},
            "options": opts}


def text_panel(title, x, y, w, h, content):
    return {"id": nid(), "type": "text", "title": title,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "fieldConfig": {"defaults": {}, "overrides": []},
            "options": {"mode": "markdown", "content": content}}


def th(*steps):
    """thresholds: th(("red", 30), ("yellow", 50)) — base green at None."""
    s = [{"color": "green", "value": None}]
    for color, value in steps:
        s.append({"color": color, "value": value})
    return {"mode": "absolute", "steps": s}


def th_rev(*steps):
    """inverted thresholds (high is bad): base color, then degrade upward."""
    return th(*steps)


def user_var():
    q = "SELECT name AS __text, id AS __value FROM users ORDER BY id"
    return {"current": {"selected": False, "text": "Demo Owner", "value": "1"},
            "datasource": DS, "definition": q, "hide": 0, "includeAll": False,
            "label": "Athlete", "multi": False, "name": "user", "options": [],
            "query": q,
            "refresh": 1, "regex": "", "skipUrlSync": False, "sort": 1,
            "type": "query"}


def metric_var():
    q = ("SELECT DISTINCT metric_name AS __text, metric_name AS __value "
         "FROM lab_metrics ORDER BY 1")
    return {"current": {"selected": False, "text": "Vitamin D (25-OH)",
                        "value": "Vitamin D (25-OH)"},
            "datasource": DS, "definition": q, "hide": 0, "includeAll": False,
            "label": "Metric", "multi": False, "name": "metric",
            "options": [], "query": q,
            "refresh": 1, "regex": "", "skipUrlSync": False, "sort": 1,
            "type": "query"}


def budget_var():
    return {"current": {"text": "0.25", "value": "0.25"}, "hide": 0,
            "label": "Daily budget $", "name": "budget", "skipUrlSync": False,
            "type": "textbox"}


def dash_links():
    return [{"asDropdown": True, "includeVars": True, "keepTime": True,
             "targetBlank": False, "tags": ["apex-health"],
             "title": "⌗ Dashboards", "type": "dashboards"}]


def dashboard(uid, title, panels, variables, time_from="now-90d",
              refresh="5m", desc=None):
    return {"uid": uid, "title": title, "description": desc or "",
            "tags": TAGS, "timezone": "browser", "editable": True,
            "graphTooltip": 1, "schemaVersion": 39, "version": 2,
            "refresh": refresh, "time": {"from": time_from, "to": "now"},
            "timepicker": {"refresh_intervals": ["30s", "1m", "5m", "15m", "1h"]},
            "templating": {"list": variables},
            "annotations": {"list": [{"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                                      "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
                                      "name": "Annotations & Alerts", "type": "dashboard"}]},
            "links": dash_links(), "panels": panels}


def write(repo, name, dash):
    out = Path(repo) / "grafana" / "dashboards" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dash, indent=1))
    print(f"wrote {out}")


# ---------------------------------------------------------------- overview
def build_overview():
    P = []
    P.append(text_panel(
        "", 0, 0, 24, 3,
        "## ⚡ Apex Health — personal health control center\n"
        "Temporary Grafana UI serving **every Phase 0–8 feature**. Pick the athlete (top-left), "
        "set a time range (top-right), hop between dashboards via **⌗ Dashboards**. "
        "Readiness band guide: 🔴 < 40 rest / 🟠 40–65 easy day / 🟢 > 65 full training. "
        "Jump to: [Training](/d/apex-activity) · [Recovery](/d/apex-recovery) · "
        "[Nutrition](/d/apex-nutrition) · [Labs](/d/apex-labs) · [AI](/d/apex-ai) · "
        "[Journal](/d/apex-journal) · [System](/d/apex-system)"))
    spark = [
        ("Readiness",
         'SELECT date AS "time", readiness_score AS value FROM daily_features '
         'WHERE user_id=$user AND $__timeFilter(date) ORDER BY date',
         None, th(("red", 40), ("yellow", 65))),
        ("Recovery",
         'SELECT date AS "time", recovery_score AS value FROM daily_features '
         'WHERE user_id=$user AND $__timeFilter(date) ORDER BY date',
         None, th(("red", 40), ("yellow", 60))),
        ("HRV last (ms)",
         'SELECT timestamp AS "time", hrv_ms AS value FROM hrv_readings '
         'WHERE user_id=$user AND $__timeFilter(timestamp) ORDER BY timestamp',
         None, None),
        ("Sleep (h)",
         'SELECT local_date AS "time", ROUND(total_sleep_s/3600.0,1) AS value '
         'FROM sleep_sessions WHERE user_id=$user AND $__timeFilter(local_date) '
         'ORDER BY local_date',
         None, th(("red", 6), ("yellow", 7))),
        ("Steps",
         'SELECT date AS "time", steps AS value FROM daily_biometrics '
         'WHERE user_id=$user AND steps IS NOT NULL AND $__timeFilter(date) ORDER BY date',
         "short", th(("red", 4000), ("yellow", 7000))),
        ("Weight (kg)",
         'SELECT date AS "time", weight_kg AS value FROM daily_biometrics '
         'WHERE user_id=$user AND weight_kg IS NOT NULL AND $__timeFilter(date) ORDER BY date',
         None, None),
        ("ACWR",
         'SELECT date AS "time", acwr AS value FROM daily_features '
         'WHERE user_id=$user AND acwr IS NOT NULL AND $__timeFilter(date) ORDER BY date',
         None, th(("red", None), ("green", 0.8), ("yellow", 1.3), ("red", 1.5))),
        ("Open alerts",
         'SELECT COUNT(*) AS value FROM alerts WHERE user_id=$user AND acknowledged = false',
         "short", th(("red", 1))),
    ]
    for i, (title, sql, unit, thr) in enumerate(spark):
        fmt = "table" if title in ("Open alerts",) else "time_series"
        P.append(panel("stat", title, i * 3, 3, 3, 5, [tgt(sql, fmt=fmt)],
                       unit=unit, thresholds=thr))
    P.append(panel("gauge", "Recovery", 0, 8, 4, 8,
                   [tgt('SELECT recovery_score AS value FROM daily_features '
                        'WHERE user_id=$user ORDER BY date DESC LIMIT 1', fmt="table")],
                   thresholds=th(("red", 40), ("yellow", 60)), minv=0, maxv=100))
    P.append(panel("gauge", "Readiness", 4, 8, 4, 8,
                   [tgt('SELECT readiness_score AS value FROM daily_features '
                        'WHERE user_id=$user ORDER BY date DESC LIMIT 1', fmt="table")],
                   thresholds=th(("red", 40), ("yellow", 65)), minv=0, maxv=100))
    P.append(panel("gauge", "ACWR (sweet spot 0.8–1.3)", 8, 8, 4, 8,
                   [tgt('SELECT acwr AS value FROM daily_features WHERE user_id=$user '
                        'AND acwr IS NOT NULL ORDER BY date DESC LIMIT 1', fmt="table")],
                   thresholds=th(("red", None), ("green", 0.8), ("yellow", 1.3), ("red", 1.5)),
                   minv=0.4, maxv=1.6))
    P.append(panel("table", "Alerts (§17)", 12, 8, 12, 8,
                   [tgt('SELECT type AS "type", severity AS "severity", message AS "message", '
                        'triggered_at AS "triggered", acknowledged AS "ack" FROM alerts '
                        'WHERE user_id=$user ORDER BY acknowledged ASC, triggered_at DESC LIMIT 8',
                        fmt="table")],
                   overrides=[ov_map("severity", sev_mapping())],
                   desc="§17 alert rows — lowest acknowledgement first."))
    P.append(panel("timeseries", "Readiness · Recovery · Strain", 0, 16, 16, 8,
                   [tgt('SELECT date AS "time", readiness_score AS readiness, '
                        'recovery_score AS recovery, strain_score AS strain '
                        'FROM daily_features WHERE user_id=$user AND $__timeFilter(date) '
                        'ORDER BY date')],
                   overrides=[ov_color("readiness", GREEN), ov_color("recovery", BLUE),
                              ov_color("strain", ORANGE)],
                   desc="Feature-engine daily outputs (§7).",
                   minv=0, maxv=100, legend=LEGEND_TABLE))
    P.append(panel("piechart", "Training mix (30d)", 16, 16, 8, 8,
                   [tgt('SELECT now() AS "time", d.name AS metric, SUM(a.duration_s)/3600.0 AS value '
                        'FROM activities a JOIN disciplines d ON d.id=a.discipline_id '
                        'WHERE a.user_id=$user AND a.local_date > CURRENT_DATE - 30 GROUP BY 2')]))
    P.append(panel("timeseries", "Training load — acute vs chronic", 0, 24, 12, 8,
                   [tgt('SELECT date AS "time", training_load_acute AS acute_7d, '
                        'training_load_chronic AS chronic_28d FROM daily_features '
                        'WHERE user_id=$user AND $__timeFilter(date) ORDER BY date')],
                   overrides=[ov_color("acute_7d", ORANGE), ov_color("chronic_28d", BLUE)],
                   desc="7-day vs 28-day rolling load; ACWR = ratio."))
    P.append(panel("timeseries", "Weight & resting HR", 12, 24, 12, 8,
                   [tgt('SELECT date AS "time", weight_kg AS weight_kg, resting_hr AS rhr '
                        'FROM daily_biometrics WHERE user_id=$user AND $__timeFilter(date) '
                        'ORDER BY date')],
                   overrides=[ov_color("weight_kg", YELLOW), ov_color("rhr", RED),
                              ov_right("rhr")], legend=LEGEND_TABLE))
    P.append(panel("barchart", "Sleep hours — last 14 nights", 0, 32, 12, 8,
                   [tgt('SELECT local_date AS "time", ROUND(total_sleep_s/3600.0,1) AS hours '
                        'FROM sleep_sessions WHERE user_id=$user '
                        'AND local_date > CURRENT_DATE - 14 ORDER BY local_date')],
                   thresholds=th(("red", None), ("yellow", 6), ("green", 7)),
                   thr_style="dashed", minv=0))
    P.append(panel("table", "Upcoming planned sessions", 12, 32, 12, 8,
                   [tgt('SELECT ps.date AS "date", dn.name AS "discipline", ps.session_type AS "type", '
                        'ps.target_duration_min AS "target min", ps.target_load AS "target load", '
                        'ps.description AS "description" FROM planned_sessions ps '
                        'JOIN training_plans tp ON tp.id = ps.training_plan_id '
                        'JOIN disciplines dn ON dn.id = ps.discipline_id '
                        'WHERE tp.user_id=$user AND tp.status IN (\'active\',\'confirmed\') '
                        'AND ps.date >= CURRENT_DATE ORDER BY ps.date LIMIT 10', fmt="table")],
                   desc="§11 — confirmed/active plans only; drafts stay hidden."))
    P.append(panel("table", "Forecast (home coords)", 0, 40, 24, 9,
                   [tgt("SELECT fc.date AS \"date\", \
CASE (fc.payload->>'weather_code')::int WHEN 0 THEN '☀️ Clear' WHEN 1 THEN '🌤️ Mostly clear' \
WHEN 2 THEN '⛅ Partly cloudy' WHEN 3 THEN '☁️ Overcast' WHEN 45 THEN '🌫️ Fog' WHEN 51 THEN '💧 Drizzle' \
WHEN 61 THEN '🌦️ Light rain' WHEN 63 THEN '🌧️ Rain' WHEN 65 THEN '⛈️ Heavy rain' WHEN 71 THEN '❄️ Snow' \
WHEN 80 THEN '🌦️ Showers' WHEN 95 THEN '⛈️ Thunderstorm' ELSE 'code ' || (fc.payload->>'weather_code') END AS \"weather\", \
fc.payload->>'temperature_2m_max' AS \"t max °C\", fc.payload->>'temperature_2m_min' AS \"t min °C\", \
fc.payload->>'wind_speed_10m_max' AS \"wind km/h\", fc.payload->>'precipitation_sum' AS \"precip mm\" \
FROM forecast_cache fc WHERE fc.date >= CURRENT_DATE ORDER BY fc.date LIMIT 7", fmt="table")],
                   desc="§14 forecast cache — WMO codes via §8.2 table. Good-window: 5–28 °C, rain ≤ 40 %, wind ≤ 35 km/h."))
    return dashboard("apex-overview", "Overview — Health at a glance", P,
                     [user_var()], time_from="now-30d", refresh="30s",
                     desc="Daily driver: readiness, alerts, load, plan, weather.")

# ---------------------------------------------------------------- activity
def build_activity():
    P = []
    stats = [
        ("Hours (7d)", "SELECT ROUND(SUM(duration_s)/3600.0,1) AS value FROM activities WHERE user_id=$user AND start_time > now() - interval '7 days'", None),
        ("Distance (7d)", "SELECT ROUND(SUM(distance_m)/1000.0,1) AS value FROM activities WHERE user_id=$user AND start_time > now() - interval '7 days'", "km"),
        ("Sessions (7d)", "SELECT COUNT(*) AS value FROM activities WHERE user_id=$user AND start_time > now() - interval '7 days'", "short"),
        ("Load (7d)", "SELECT ROUND(SUM(training_load)) AS value FROM activities WHERE user_id=$user AND start_time > now() - interval '7 days'", None),
        ("Hours YTD", "SELECT ROUND(SUM(duration_s)/3600.0,1) AS value FROM activities WHERE user_id=$user AND local_date >= date_trunc('year', CURRENT_DATE)", None),
        ("Distance YTD (km)", "SELECT ROUND(SUM(distance_m)/1000.0,1) AS value FROM activities WHERE user_id=$user AND local_date >= date_trunc('year', CURRENT_DATE)", None),
        ("Elevation 30d (m)", "SELECT ROUND(SUM(elevation_gain_m)) AS value FROM activities WHERE user_id=$user AND local_date > CURRENT_DATE - 30 AND elevation_gain_m IS NOT NULL", None),
        ("Run pace (30d)", "SELECT ROUND(SUM(duration_s)/60.0 / NULLIF(SUM(distance_m)/1000.0,0),2) AS value FROM activities a JOIN disciplines d ON d.id=a.discipline_id WHERE a.user_id=$user AND d.name='running' AND a.local_date > CURRENT_DATE - 30 AND a.distance_m > 0", None),
    ]
    for i, (title, sql, unit) in enumerate(stats):
        P.append(panel("stat", title, i * 3, 0, 3, 5, [tgt(sql, fmt="table")], unit=unit))
    P.append(panel("barchart", "Weekly hours by discipline", 0, 5, 12, 9,
                   [tgt('SELECT date_trunc(\'week\', local_date) AS "time", d.name AS metric, '
                        'SUM(a.duration_s)/3600.0 AS value FROM activities a '
                        'JOIN disciplines d ON d.id=a.discipline_id '
                        'WHERE a.user_id=$user AND $__timeFilter(local_date) '
                        'GROUP BY 1, 2 ORDER BY 1')],
                   custom={**BAR_CUSTOM, "stacking": STACK}))
    P.append(panel("piechart", "Time by discipline", 12, 5, 6, 9,
                   [tgt('SELECT now() AS "time", d.name AS metric, SUM(a.duration_s)/3600.0 AS value '
                        'FROM activities a JOIN disciplines d ON d.id=a.discipline_id '
                        'WHERE a.user_id=$user AND $__timeFilter(local_date) GROUP BY 2')]))
    P.append(panel("timeseries", "Avg / max HR", 18, 5, 6, 9,
                   [tgt('SELECT local_date AS "time", avg_hr AS avg_hr, max_hr AS max_hr '
                        'FROM activities WHERE user_id=$user AND avg_hr IS NOT NULL '
                        'AND $__timeFilter(local_date) ORDER BY local_date')],
                   overrides=[ov_color("avg_hr", ORANGE), ov_color("max_hr", RED)],
                   legend=LEGEND_TABLE))
    P.append(panel("table", "Recent activities", 0, 14, 24, 11,
                   [tgt('SELECT to_char(a.local_date,\'YYYY-MM-DD\') AS "date", d.name AS "discipline", '
                        "to_char(a.start_time AT TIME ZONE 'Europe/Rome', 'MM-DD HH24:MI') AS \"start\", "
                        'ROUND(a.duration_s/60.0) AS "min", ROUND(a.distance_m/1000.0,1) AS "km", '
                        'a.elevation_gain_m AS "↑ m", a.avg_hr AS "avg hr", a.max_hr AS "max hr", '
                        'a.avg_power AS "avg W", a.calories AS "kcal", a.training_load AS "load", '
                        'a.weather_snapshot->>\'temperature_2m_mean\' AS "temp", '
                        'a.data_completeness AS "quality" '
                        'FROM activities a JOIN disciplines d ON d.id=a.discipline_id '
                        'WHERE a.user_id=$user ORDER BY a.start_time DESC LIMIT 25',
                        fmt="table")],
                   desc="Weather column comes from §14 enrichment (weather_snapshot)."))
    P.append(panel("timeseries", "Run pace (min/km)", 0, 25, 8, 8,
                   [tgt('SELECT local_date AS "time", ROUND((duration_s/60.0)/(distance_m/1000.0),2) '
                        'AS min_per_km FROM activities a JOIN disciplines d ON d.id=a.discipline_id '
                        'WHERE a.user_id=$user AND d.name=\'running\' AND distance_m > 0 '
                        'AND $__timeFilter(local_date) ORDER BY local_date')],
                   overrides=[ov_color("min_per_km", GREEN)], minv=3.5, maxv=7.5))
    P.append(panel("timeseries", "Estimated FTP (cycling)", 8, 25, 8, 8,
                   [tgt('SELECT date AS "time", estimated_ftp AS ftp FROM discipline_features df '
                        'JOIN disciplines d ON d.id=df.discipline_id WHERE df.user_id=$user '
                        'AND d.name=\'road_cycling\' AND $__timeFilter(date) ORDER BY date')],
                   overrides=[ov_color("ftp", PURPLE)]))
    P.append(panel("table", "Segment efforts", 16, 25, 8, 8,
                   [tgt('SELECT to_char(a.local_date,\'YYYY-MM-DD\') AS "date", s.name AS "segment", '
                        'se.elapsed_time_s AS "seconds", se.is_pr AS "PR" FROM segment_efforts se '
                        'JOIN segments s ON s.id=se.segment_id '
                        'JOIN activities a ON a.id=se.activity_id '
                        'WHERE a.user_id=$user ORDER BY a.local_date DESC LIMIT 10', fmt="table")]))
    P.append(panel("barchart", "Weekly distance by discipline (km)", 0, 33, 8, 8,
                   [tgt('SELECT date_trunc(\'week\', local_date) AS "time", d.name AS metric, '
                        'ROUND(SUM(a.distance_m)/1000.0,1) AS value FROM activities a '
                        'JOIN disciplines d ON d.id=a.discipline_id '
                        'WHERE a.user_id=$user AND a.distance_m IS NOT NULL AND $__timeFilter(local_date) '
                        'GROUP BY 1, 2 ORDER BY 1')],
                   custom={**BAR_CUSTOM, "stacking": STACK}))
    P.append(panel("barchart", "Weekly elevation gain (m)", 8, 33, 8, 8,
                   [tgt('SELECT date_trunc(\'week\', local_date) AS "time", '
                        'ROUND(SUM(elevation_gain_m)) AS meters FROM activities '
                        'WHERE user_id=$user AND elevation_gain_m IS NOT NULL '
                        'AND $__timeFilter(local_date) GROUP BY 1 ORDER BY 1')],
                   custom={**BAR_CUSTOM}, thresholds=th(("blue", None))))
    P.append(panel("barchart", "Weekly kcal", 16, 33, 8, 8,
                   [tgt('SELECT date_trunc(\'week\', local_date) AS "time", SUM(calories) AS kcal '
                        'FROM activities WHERE user_id=$user AND calories IS NOT NULL '
                        'AND $__timeFilter(local_date) GROUP BY 1 ORDER BY 1')],
                   custom={**BAR_CUSTOM}, thresholds=th(("orange", None))))
    P.append(panel("barchart", "Activities by hour of day", 0, 41, 12, 8,
                   [tgt("SELECT to_char(EXTRACT(HOUR FROM start_time AT TIME ZONE 'Europe/Rome')::int, 'FM00') || ':00' "
                        "AS \"hour\", COUNT(*) AS \"sessions\" FROM activities "
                        "WHERE user_id=$user AND $__timeFilter(local_date) GROUP BY 1 ORDER BY 1",
                        fmt="table")],
                   desc="Local start hour (Europe/Rome)."))
    P.append(panel("timeseries", "Aerobic decoupling & efficiency (road cycling)", 12, 41, 12, 8,
                   [tgt('SELECT df.date AS "time", df.aerobic_decoupling_pct AS decoupling_pct, '
                        'df.efficiency_factor AS EF FROM discipline_features df '
                        'JOIN disciplines d ON d.id=df.discipline_id '
                        'WHERE df.user_id=$user AND d.name=\'road_cycling\' '
                        'AND $__timeFilter(df.date) ORDER BY df.date')],
                   overrides=[ov_color("decoupling_pct", RED), ov_color("EF", GREEN),
                              ov_right("EF")],
                   desc="Lower decoupling = better aerobic endurance; EF = normalised power / HR."))
    return dashboard("apex-activity", "Training & Activities", P, [user_var()],
                     desc="Workouts, disciplines, load, pace, FTP, segments, weather-enriched rows.")


# ---------------------------------------------------------------- recovery
def build_recovery():
    P = []
    stats = [
        ("HRV last (ms)", "SELECT hrv_ms AS value FROM hrv_readings WHERE user_id=$user ORDER BY timestamp DESC LIMIT 1", None),
        ("HRV 7d avg", "SELECT ROUND(AVG(hrv_ms),1) AS value FROM (SELECT hrv_ms FROM hrv_readings WHERE user_id=$user ORDER BY timestamp DESC LIMIT 7) h", None),
        ("RHR last", "SELECT resting_hr AS value FROM daily_biometrics WHERE user_id=$user AND resting_hr IS NOT NULL ORDER BY date DESC LIMIT 1", "short"),
        ("Sleep score", "SELECT sleep_score AS value FROM sleep_sessions WHERE user_id=$user ORDER BY local_date DESC LIMIT 1", None),
        ("Sleep debt 7d (h)", "SELECT ROUND(56 - SUM(total_sleep_s)/3600.0,1) AS value FROM (SELECT total_sleep_s FROM sleep_sessions WHERE user_id=$user ORDER BY local_date DESC LIMIT 7) s", None, th(("green", None), ("yellow", 3), ("red", 6))),
        ("Weight (kg)", "SELECT weight_kg AS value FROM daily_biometrics WHERE user_id=$user AND weight_kg IS NOT NULL ORDER BY date DESC LIMIT 1", "kg"),
        ("Body fat (%)", "SELECT body_fat_pct AS value FROM daily_biometrics WHERE user_id=$user AND body_fat_pct IS NOT NULL ORDER BY date DESC LIMIT 1", "percent"),
        ("Restlessness", "SELECT restlessness AS value FROM sleep_sessions WHERE user_id=$user AND restlessness IS NOT NULL ORDER BY local_date DESC LIMIT 1", "percentunit"),
    ]
    for i, (title, sql, unit, *thr) in enumerate(stats):
        P.append(panel("stat", title, i * 3, 0, 3, 5, [tgt(sql, fmt="table")],
                       unit=unit, thresholds=(thr[0] if thr else None)))
    P.append(panel("gauge", "Recovery", 0, 5, 4, 7,
                   [tgt('SELECT recovery_score AS value FROM daily_features WHERE user_id=$user '
                        'ORDER BY date DESC LIMIT 1', fmt="table")],
                   thresholds=th(("red", 40), ("yellow", 60)), minv=0, maxv=100))
    P.append(panel("gauge", "Readiness", 4, 5, 4, 7,
                   [tgt('SELECT readiness_score AS value FROM daily_features WHERE user_id=$user '
                        'ORDER BY date DESC LIMIT 1', fmt="table")],
                   thresholds=th(("red", 40), ("yellow", 65)), minv=0, maxv=100))
    P.append(panel("gauge", "Strain", 8, 5, 4, 7,
                   [tgt('SELECT strain_score AS value FROM daily_features WHERE user_id=$user '
                        'ORDER BY date DESC LIMIT 1', fmt="table")],
                   thresholds=th(("green", None), ("yellow", 50), ("red", 75)), minv=0, maxv=100))
    P.append(panel("timeseries", "HRV vs rolling baseline", 12, 5, 12, 7,
                   [tgt('SELECT timestamp AS "time", hrv_ms AS hrv, rolling_baseline_ms AS baseline '
                        'FROM hrv_readings WHERE user_id=$user AND $__timeFilter(timestamp) '
                        'ORDER BY timestamp')],
                   overrides=[ov_color("hrv", PURPLE), ov_color("baseline", ORANGE)],
                   desc="§7 baseline — deviation drives recovery/readiness."))
    P.append(panel("timeseries", "Sleep duration & score", 0, 12, 12, 8,
                   [tgt('SELECT local_date AS "time", ROUND(total_sleep_s/3600.0,2) AS hours, '
                        'sleep_score AS score FROM sleep_sessions WHERE user_id=$user '
                        'AND $__timeFilter(local_date) ORDER BY local_date')],
                   overrides=[ov_color("hours", DBLUE), ov_color("score", GREEN),
                              ov_right("score")],
                   minv=0, legend=LEGEND_TABLE))
    P.append(panel("barchart", "Sleep stages (h)", 12, 12, 12, 8,
                   [tgt('SELECT local_date AS "time", deep_s/3600.0 AS deep, light_s/3600.0 AS light, '
                        'rem_s/3600.0 AS rem, awake_s/3600.0 AS awake FROM sleep_sessions '
                        'WHERE user_id=$user AND $__timeFilter(local_date) ORDER BY local_date',
                        fmt="table")],
                   custom={**BAR_CUSTOM, "stacking": STACK},
                   overrides=[ov_color("deep", VIOLET), ov_color("light", BLUE),
                              ov_color("rem", GREEN), ov_color("awake", ORANGE)]))
    P.append(panel("barchart", "Sleep debt vs 8 h target (h)", 0, 20, 8, 8,
                   [tgt('SELECT local_date AS "time", ROUND(8.0 - total_sleep_s/3600.0,2) AS debt_h '
                        'FROM sleep_sessions WHERE user_id=$user AND $__timeFilter(local_date) '
                        'ORDER BY local_date')],
                   custom={**BAR_CUSTOM}, thresholds=th(("green", None)), thr_style="dashed",
                   desc="Above 0 = debt (slept < 8 h); below 0 = surplus."))
    P.append(panel("timeseries", "Bedtime consistency (local hour)", 8, 20, 8, 8,
                   [tgt("SELECT local_date AS \"time\", "
                        "EXTRACT(HOUR FROM start_time AT TIME ZONE 'Europe/Rome') "
                        "+ EXTRACT(MINUTE FROM start_time AT TIME ZONE 'Europe/Rome')/60.0 "
                        "+ CASE WHEN EXTRACT(HOUR FROM start_time AT TIME ZONE 'Europe/Rome') < 12 "
                        "THEN 24 ELSE 0 END AS bedtime_h "
                        "FROM sleep_sessions WHERE user_id=$user AND $__timeFilter(local_date) "
                        "ORDER BY local_date")],
                   overrides=[ov_color("bedtime_h", PURPLE)], minv=20, maxv=26,
                   desc="Times after midnight mapped to 24+ so bedtime stays continuous."))
    P.append(panel("timeseries", "Sleep architecture score & restlessness", 16, 20, 8, 8,
                   [tgt('SELECT df.date AS "time", df.sleep_architecture_score AS arch_score '
                        'FROM daily_features df WHERE df.user_id=$user '
                        'AND df.sleep_architecture_score IS NOT NULL AND $__timeFilter(df.date) '
                        'ORDER BY df.date'),
                    tgt('SELECT local_date AS "time", restlessness AS restlessness '
                        'FROM sleep_sessions WHERE user_id=$user AND restlessness IS NOT NULL '
                        'AND $__timeFilter(local_date) ORDER BY local_date', ref="B")],
                   overrides=[ov_color("arch_score", GREEN), ov_color("restlessness", ORANGE),
                              ov_right("restlessness")]))
    P.append(panel("timeseries", "Resting HR & respiration", 0, 28, 12, 8,
                   [tgt('SELECT date AS "time", resting_hr AS rhr FROM daily_biometrics '
                        'WHERE user_id=$user AND resting_hr IS NOT NULL AND $__timeFilter(date) '
                        'ORDER BY date'),
                    tgt('SELECT local_date AS "time", respiration_avg AS respiration '
                        'FROM sleep_sessions WHERE user_id=$user AND respiration_avg IS NOT NULL '
                        'AND $__timeFilter(local_date) ORDER BY local_date', ref="B")],
                   overrides=[ov_color("rhr", RED), ov_color("respiration", CYAN),
                              ov_right("respiration")]))
    P.append(panel("timeseries", "Stress & body battery (daily)", 12, 28, 12, 8,
                   [tgt("SELECT date_trunc('day', timestamp) AS \"time\", "
                        "AVG(stress_level) AS stress, MAX(body_battery) AS battery "
                        "FROM stress_readings WHERE user_id=$user AND $__timeFilter(timestamp) "
                        "GROUP BY 1 ORDER BY 1")],
                   overrides=[ov_color("stress", RED), ov_color("battery", GREEN),
                              ov_right("battery")]))
    P.append(panel("timeseries", "Weight & body fat", 0, 36, 8, 8,
                   [tgt('SELECT date AS "time", weight_kg AS weight_kg, body_fat_pct AS body_fat '
                        'FROM daily_biometrics WHERE user_id=$user AND weight_kg IS NOT NULL '
                        'AND $__timeFilter(date) ORDER BY date')],
                   overrides=[ov_color("weight_kg", YELLOW), ov_color("body_fat", BROWN),
                              ov_right("body_fat")]))
    P.append(panel("timeseries", "HRV deviation from baseline (%)", 8, 36, 8, 8,
                   [tgt('SELECT date AS "time", hrv_deviation_from_baseline AS deviation_pct '
                        'FROM daily_features WHERE user_id=$user AND $__timeFilter(date) '
                        'ORDER BY date')],
                   thresholds=th(("red", -15), ("yellow", 0), ("green", 5)), thr_style="dashed"))
    P.append(panel("timeseries", "VO2max & SpO2", 16, 36, 8, 8,
                   [tgt('SELECT date AS "time", vo2max AS vo2max, spo2_avg AS spo2 '
                        'FROM daily_biometrics WHERE user_id=$user AND vo2max IS NOT NULL '
                        'AND $__timeFilter(date) ORDER BY date')],
                   overrides=[ov_color("vo2max", DGREEN), ov_color("spo2", CYAN),
                              ov_right("spo2")]))
    P.append(panel("timeseries", "Illness · injury · cross-discipline fatigue", 0, 44, 24, 7,
                   [tgt('SELECT date AS "time", illness_risk_score AS illness, '
                        'injury_risk_score AS injury, cross_discipline_fatigue_index AS fatigue '
                        'FROM daily_features WHERE user_id=$user AND $__timeFilter(date) '
                        'ORDER BY date')],
                   overrides=[ov_color("illness", RED), ov_color("injury", ORANGE),
                              ov_color("fatigue", PURPLE)],
                   minv=0, maxv=1,
                   desc="§7 risk features (0–1). Sustained rises → §17 alerts."))
    return dashboard("apex-recovery", "Recovery & Sleep", P, [user_var()],
                     desc="HRV, sleep architecture, stress, body composition, risk scores.")

# --------------------------------------------------------------- nutrition
def build_nutrition():
    P = []
    stats = [
        ("Calories today", "SELECT COALESCE(SUM(calories),0) AS value FROM nutrition_logs WHERE user_id=$user AND calories IS NOT NULL AND timestamp::date = CURRENT_DATE", None),
        ("Protein today (g)", "SELECT COALESCE(SUM(protein_g),0) AS value FROM nutrition_logs WHERE user_id=$user AND protein_g IS NOT NULL AND timestamp::date = CURRENT_DATE", "short"),
        ("Caffeine today (mg)", "SELECT COALESCE(SUM(caffeine_mg),0) AS value FROM nutrition_logs WHERE user_id=$user AND caffeine_mg IS NOT NULL AND timestamp::date = CURRENT_DATE", "short"),
        ("Water today (L)", "SELECT COALESCE(SUM(water_ml),0)/1000.0 AS value FROM nutrition_logs WHERE user_id=$user AND water_ml IS NOT NULL AND timestamp::date = CURRENT_DATE", "litre"),
        ("Kcal 7d avg", "SELECT ROUND(AVG(c),0) AS value FROM (SELECT COALESCE(SUM(calories),0) AS c FROM nutrition_logs WHERE user_id=$user AND calories IS NOT NULL AND timestamp::date > CURRENT_DATE - 7 GROUP BY timestamp::date) x", None),
        ("Protein 7d avg (g)", "SELECT ROUND(AVG(p),0) AS value FROM (SELECT COALESCE(SUM(protein_g),0) AS p FROM nutrition_logs WHERE user_id=$user AND protein_g IS NOT NULL AND timestamp::date > CURRENT_DATE - 7 GROUP BY timestamp::date) x", "short"),
        ("Alcohol 7d (units)", "SELECT COALESCE(SUM(alcohol_units),0) AS value FROM nutrition_logs WHERE user_id=$user AND alcohol_units IS NOT NULL AND timestamp > now() - interval '7 days'", None),
        ("Meals logged 7d", "SELECT COUNT(*) AS value FROM nutrition_logs WHERE user_id=$user AND timestamp > now() - interval '7 days'", "short"),
    ]
    for i, (title, sql, unit) in enumerate(stats):
        P.append(panel("stat", title, i * 3, 0, 3, 5, [tgt(sql, fmt="table")], unit=unit))
    P.append(panel("timeseries", "Daily calories", 0, 5, 12, 8,
                   [tgt("SELECT date_trunc('day', timestamp) AS \"time\", SUM(calories) AS kcal "
                        "FROM nutrition_logs WHERE user_id=$user AND calories IS NOT NULL "
                        "AND $__timeFilter(timestamp) GROUP BY 1 ORDER BY 1")],
                   overrides=[ov_color("kcal", ORANGE)], minv=0))
    P.append(panel("timeseries", "Macros (g/day)", 12, 5, 12, 8,
                   [tgt("SELECT date_trunc('day', timestamp) AS \"time\", SUM(protein_g) AS protein, "
                        "SUM(carbs_g) AS carbs, SUM(fat_g) AS fat FROM nutrition_logs "
                        "WHERE user_id=$user AND protein_g IS NOT NULL AND $__timeFilter(timestamp) "
                        "GROUP BY 1 ORDER BY 1")],
                   overrides=[ov_color("protein", GREEN), ov_color("carbs", YELLOW),
                              ov_color("fat", PURPLE)]))
    P.append(panel("piechart", "Macro energy split (30d)", 0, 13, 8, 9,
                   [tgt('SELECT SUM(protein_g)*4 AS "Protein kcal", SUM(carbs_g)*4 AS "Carbs kcal", '
                        'SUM(fat_g)*9 AS "Fat kcal" FROM nutrition_logs WHERE user_id=$user '
                        "AND protein_g IS NOT NULL AND timestamp > now() - interval '30 days'",
                        fmt="table")]))
    P.append(panel("timeseries", "Caffeine & alcohol", 8, 13, 8, 9,
                   [tgt("SELECT date_trunc('day', timestamp) AS \"time\", SUM(caffeine_mg) AS caffeine_mg "
                        "FROM nutrition_logs WHERE user_id=$user AND caffeine_mg IS NOT NULL "
                        "AND $__timeFilter(timestamp) GROUP BY 1 ORDER BY 1"),
                    tgt("SELECT date_trunc('day', timestamp) AS \"time\", SUM(alcohol_units) AS alcohol_units "
                        "FROM nutrition_logs WHERE user_id=$user AND alcohol_units IS NOT NULL "
                        "AND $__timeFilter(timestamp) GROUP BY 1 ORDER BY 1", ref="B")],
                   overrides=[ov_color("caffeine_mg", BROWN), ov_color("alcohol_units", PINK)],
                   minv=0))
    P.append(panel("timeseries", "Water (L/day) vs 2.5 L target", 16, 13, 8, 9,
                   [tgt("SELECT date_trunc('day', timestamp) AS \"time\", SUM(water_ml)/1000.0 AS litres "
                        "FROM nutrition_logs WHERE user_id=$user AND water_ml IS NOT NULL "
                        "AND $__timeFilter(timestamp) GROUP BY 1 ORDER BY 1")],
                   overrides=[ov_color("litres", CYAN)],
                   thresholds=th(("red", None), ("green", 2.5)), thr_style="dashed",
                   minv=0))
    P.append(panel("table", "Supplement adherence (30d)", 0, 22, 12, 8,
                   [tgt("SELECT sp.supplement_name AS \"supplement\", sp.dose AS \"dose\", "
                        "COUNT(sl.*) AS \"logged\", COUNT(sl.*) FILTER (WHERE sl.adherence) AS \"taken\", "
                        "ROUND(100.0 * COUNT(sl.*) FILTER (WHERE sl.adherence) / NULLIF(COUNT(sl.*),0), 1) "
                        "AS \"adherence %\" FROM supplement_protocols sp "
                        "LEFT JOIN supplement_logs sl ON sl.protocol_id = sp.id "
                        "AND sl.taken_at > now() - interval '30 days' "
                        "WHERE sp.user_id=$user GROUP BY sp.id, sp.supplement_name, sp.dose "
                        "ORDER BY sp.supplement_name", fmt="table")]))
    P.append(panel("bargauge", "Adherence by supplement (30d)", 12, 22, 12, 8,
                   [tgt("SELECT sp.supplement_name AS \"supplement\", "
                        "ROUND(100.0 * COUNT(sl.*) FILTER (WHERE sl.adherence) / NULLIF(COUNT(sl.*),0)) "
                        "AS \"adherence %\" FROM supplement_protocols sp "
                        "LEFT JOIN supplement_logs sl ON sl.protocol_id = sp.id "
                        "AND sl.taken_at > now() - interval '30 days' "
                        "WHERE sp.user_id=$user GROUP BY sp.id, sp.supplement_name "
                        "ORDER BY 2 DESC", fmt="table")],
                   opts={"displayMode": "gradient", "minVizHeight": 10, "minVizWidth": 0,
                         "namePlacement": "auto", "orientation": "horizontal",
                         "reduceOptions": {"calcs": ["lastNotNull"], "fields": "",
                                           "values": True},
                         "showUnfilled": True, "sizing": "auto", "valueMode": "color"},
                   unit="percent", minv=0, maxv=100,
                   thresholds=th(("red", None), ("yellow", 70), ("green", 90))))
    P.append(panel("timeseries", "Adherence % (daily)", 0, 30, 12, 8,
                   [tgt("SELECT sl.taken_at::date AS \"time\", "
                        "ROUND(100.0 * SUM(CASE WHEN sl.adherence THEN 1 ELSE 0 END) / COUNT(*),1) AS pct "
                        "FROM supplement_logs sl JOIN supplement_protocols sp ON sp.id = sl.protocol_id "
                        "WHERE sp.user_id=$user AND $__timeFilter(sl.taken_at) "
                        "GROUP BY 1 ORDER BY 1")],
                   minv=0, maxv=100))
    P.append(panel("barchart", "Weekly protein (g)", 12, 30, 12, 8,
                   [tgt("SELECT date_trunc('week', timestamp) AS \"time\", ROUND(SUM(protein_g)) AS protein_g "
                        "FROM nutrition_logs WHERE user_id=$user AND protein_g IS NOT NULL "
                        "AND $__timeFilter(timestamp) GROUP BY 1 ORDER BY 1")],
                   custom={**BAR_CUSTOM}, thresholds=th(("green", None))))
    return dashboard("apex-nutrition", "Nutrition & Supplements", P, [user_var()],
                     desc="Meals, macros, hydration, caffeine/alcohol, supplement adherence.")


# -------------------------------------------------------------------- labs
def build_labs():
    P = []
    stats = [
        ("Ferritin (ng/mL)", "SELECT ferritin_ng_ml AS value FROM lab_panels WHERE user_id=$user ORDER BY date DESC LIMIT 1",
         {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 30}, {"color": "green", "value": 50}]}),
        ("Hemoglobin (g/dL)", "SELECT hemoglobin_g_dl AS value FROM lab_panels WHERE user_id=$user ORDER BY date DESC LIMIT 1",
         th(("yellow", 13.5), ("green", 14.0))),
        ("Iron (µg/dL)", "SELECT iron AS value FROM lab_panels WHERE user_id=$user AND iron IS NOT NULL ORDER BY date DESC LIMIT 1", None),
        ("WBC (10⁹/L)", "SELECT wbc AS value FROM lab_panels WHERE user_id=$user AND wbc IS NOT NULL ORDER BY date DESC LIMIT 1", None),
        ("Days to eligibility", "SELECT (next_eligible_date - CURRENT_DATE) AS value FROM lab_panels WHERE user_id=$user AND next_eligible_date IS NOT NULL ORDER BY date DESC LIMIT 1", None),
        ("Panels total", "SELECT COUNT(*) AS value FROM lab_panels WHERE user_id=$user", None),
        ("Metrics in range (%)", "SELECT ROUND(100.0*COUNT(*) FILTER (WHERE lm.value BETWEEN lm.ref_low AND lm.ref_high)/NULLIF(COUNT(*),0),0) AS value FROM lab_metrics lm JOIN lab_panels lp ON lp.id=lm.lab_panel_id WHERE lp.user_id=$user AND lm.ref_low IS NOT NULL AND lp.date = (SELECT MAX(date) FROM lab_panels WHERE user_id=$user)",
         th(("red", None), ("yellow", 70), ("green", 85))),
        ("Metrics tracked", "SELECT COUNT(DISTINCT metric_name) AS value FROM lab_metrics lm JOIN lab_panels lp ON lp.id=lm.lab_panel_id WHERE lp.user_id=$user", None),
    ]
    for i, (title, sql, thr, *rest) in enumerate(stats):
        P.append(panel("stat", title, i * 3, 0, 3, 5, [tgt(sql, fmt="table")],
                       thresholds=thr))
    P.append(panel("timeseries", "Ferritin — recovery story", 0, 5, 16, 9,
                   [tgt('SELECT date AS "time", ferritin_ng_ml AS ferritin FROM lab_panels '
                        'WHERE user_id=$user AND $__timeFilter(date) ORDER BY date')],
                   desc="Low-ferritin threshold 30 ng/mL (config default) — §17 alert fired on the dip.",
                   thresholds={"mode": "absolute", "steps": [{"color": "red", "value": None},
                                                            {"color": "yellow", "value": 30},
                                                            {"color": "green", "value": 50}]},
                   thr_style="dashed", minv=0))
    P.append(panel("timeseries", "Hemoglobin & hematocrit", 16, 5, 8, 9,
                   [tgt('SELECT date AS "time", hemoglobin_g_dl AS hemoglobin, hematocrit_pct AS hematocrit '
                        'FROM lab_panels WHERE user_id=$user AND $__timeFilter(date) ORDER BY date')],
                   overrides=[ov_color("hemoglobin", RED), ov_right("hematocrit")],
                   legend=LEGEND_TABLE))
    P.append(panel("table", "Latest metrics vs reference ranges", 0, 14, 14, 10,
                   [tgt('SELECT DISTINCT ON (lm.metric_name) lm.metric_name AS "metric", lm.value AS "value", '
                        'lm.unit AS "unit", lm.ref_low AS "ref low", lm.ref_high AS "ref high", '
                        'CASE WHEN lm.value < lm.ref_low THEN \'▼ LOW\' '
                        'WHEN lm.value > lm.ref_high THEN \'▲ HIGH\' ELSE \'● in range\' END AS "flag", '
                        'to_char(lp.date,\'YYYY-MM-DD\') AS "panel date" '
                        'FROM lab_metrics lm JOIN lab_panels lp ON lp.id = lm.lab_panel_id '
                        'WHERE lp.user_id=$user ORDER BY lm.metric_name, lp.date DESC', fmt="table")],
                   desc="Latest value per metric against the stored §12 reference range."))
    P.append(panel("barchart", "Ferritin change per panel (ng/mL)", 14, 14, 10, 10,
                   [tgt('SELECT date AS "time", ferritin_ng_ml - LAG(ferritin_ng_ml) OVER (ORDER BY date) '
                        'AS delta FROM lab_panels WHERE user_id=$user AND ferritin_ng_ml IS NOT NULL '
                        'ORDER BY date')],
                   custom={**BAR_CUSTOM},
                   thresholds=th(("green", None)), thr_style="dashed",
                   desc="Bars above 0 = improvement since previous panel."))
    P.append(panel("table", "Panel history", 0, 24, 24, 9,
                   [tgt('SELECT to_char(date,\'YYYY-MM-DD\') AS "date", panel_type AS "type", donation_type AS "donation", '
                        'hemoglobin_g_dl AS "hgb", hematocrit_pct AS "hct", ferritin_ng_ml AS "ferritin", '
                        'iron AS "iron", wbc AS "wbc", plt AS "plt", next_eligible_date AS "eligible", '
                        'source AS "source" FROM lab_panels WHERE user_id=$user '
                        'ORDER BY date DESC', fmt="table")],
                   desc="Notes are stored encrypted (notes_ciphertext) — not rendered here by design."))
    P.append(panel("timeseries", "Metric trend — ${metric}", 0, 33, 24, 9,
                   [tgt('SELECT lp.date AS "time", lm.value AS value FROM lab_metrics lm '
                        'JOIN lab_panels lp ON lp.id = lm.lab_panel_id '
                        "WHERE lp.user_id=$user AND lm.metric_name = '${metric}' "
                        'AND $__timeFilter(lp.date) ORDER BY lp.date')],
                   desc="Pick any extra metric from the panels via the Metric dropdown."))
    return dashboard("apex-labs", "Labs & Blood Health", P, [user_var(), metric_var()],
                     time_from="now-1y",
                     desc="Blood panels, donation tracking, extra lab metrics vs reference ranges.")

# ----------------------------------------------------------------------- ai
def build_ai():
    P = []
    stats = [
        ("Spend today", "SELECT COALESCE(SUM(cost_estimate_usd),0) AS value FROM token_usage WHERE user_id=$user AND created_at::date = CURRENT_DATE", "currencyUSD", None),
        ("Spend (7d)", "SELECT COALESCE(SUM(cost_estimate_usd),0) AS value FROM token_usage WHERE user_id=$user AND created_at > now() - interval '7 days'", "currencyUSD", None),
        ("Tool calls (7d)", "SELECT COUNT(*) AS value FROM agent_tool_calls atc JOIN ai_chat_sessions s ON s.id=atc.session_id WHERE s.user_id=$user AND atc.created_at > now() - interval '7 days'", "short", None),
        ("Tool error rate (30d)", "SELECT ROUND(100.0*COUNT(*) FILTER (WHERE error IS NOT NULL)/NULLIF(COUNT(*),0),1) AS value FROM agent_tool_calls atc JOIN ai_chat_sessions s ON s.id=atc.session_id WHERE s.user_id=$user AND atc.created_at > now() - interval '30 days'", "percent", th(("green", 5), ("red", 10))),
        ("Over-budget days", "SELECT COUNT(*) AS value FROM (SELECT created_at::date AS d, SUM(cost_estimate_usd) AS c FROM token_usage WHERE user_id=$user GROUP BY 1) x WHERE c > ${budget}", "short", None),
        ("Pending voice drafts", "SELECT COUNT(*) AS value FROM telegram_messages WHERE chat_id IN (SELECT chat_id FROM telegram_links WHERE user_id=$user) AND status='pending'", "short", None),
        ("Chat sessions (7d)", "SELECT COUNT(*) AS value FROM ai_chat_sessions WHERE user_id=$user AND started_at > now() - interval '7 days'", "short", None),
        ("Cache hit (7d)", "SELECT ROUND(100.0*SUM(cached_tokens)/NULLIF(SUM(tokens_in),0),1) AS value FROM token_usage WHERE user_id=$user AND created_at > now() - interval '7 days'", "percent", None),
    ]
    for i, (title, sql, unit, thr) in enumerate(stats):
        P.append(panel("stat", title, i * 3, 0, 3, 5, [tgt(sql, fmt="table")],
                       unit=unit, thresholds=thr))
    P.append(panel("gauge", "Budget used today (%)", 0, 5, 4, 8,
                   [tgt("SELECT COALESCE(100.0*SUM(cost_estimate_usd)/NULLIF(${budget}::numeric,0),0) "
                        "AS value FROM token_usage WHERE user_id=$user AND created_at::date = CURRENT_DATE",
                        fmt="table")],
                   unit="percent", minv=0, maxv=150,
                   thresholds=th(("green", None), ("yellow", 70), ("red", 100)),
                   desc="Daily token budget §8.6 — editable via the ${budget} textbox variable."))
    P.append(panel("timeseries", "Daily AI spend vs budget", 4, 5, 12, 8,
                   [tgt("SELECT date_trunc('day', created_at) AS \"time\", "
                        "SUM(cost_estimate_usd) AS spend FROM token_usage "
                        "WHERE user_id=$user AND $__timeFilter(created_at) GROUP BY 1 ORDER BY 1"),
                    tgt("SELECT date_trunc('day', created_at) AS \"time\", "
                        "${budget}::numeric AS budget FROM token_usage "
                        "WHERE user_id=$user AND $__timeFilter(created_at) GROUP BY 1 ORDER BY 1", ref="B")],
                   overrides=[ov_color("spend", ORANGE), ov_color("budget", RED)],
                   desc="Budget is editable via the textbox variable (DAILY_TOKEN_BUDGET_USD default 0.25)."))
    P.append(panel("piechart", "Model mix (calls)", 16, 5, 8, 8,
                   [tgt('SELECT now() AS "time", model AS metric, COUNT(*) AS value '
                        'FROM token_usage WHERE user_id=$user AND $__timeFilter(created_at) '
                        'GROUP BY 2 ORDER BY 3 DESC')]))
    P.append(panel("barchart", "Tool calls by tool", 0, 13, 8, 9,
                   [tgt('SELECT atc.tool_name AS "tool", COUNT(*) AS "calls" '
                        'FROM agent_tool_calls atc '
                        'JOIN ai_chat_sessions s ON s.id=atc.session_id '
                        'WHERE s.user_id=$user AND $__timeFilter(atc.created_at) '
                        'GROUP BY 1 ORDER BY 2 DESC', fmt="table")], opts=HBAR_OPTS))
    P.append(panel("barchart", "Tier usage by day (calls)", 8, 13, 8, 9,
                   [tgt("SELECT date_trunc('day', created_at) AS \"time\", tier AS metric, COUNT(*) AS value "
                        "FROM token_usage WHERE user_id=$user AND $__timeFilter(created_at) "
                        "GROUP BY 1, 2 ORDER BY 1")],
                   custom={**BAR_CUSTOM, "stacking": STACK},
                   overrides=[ov_color("free", GREEN), ov_color("cheap", YELLOW),
                              ov_color("powerful", RED)],
                   desc="§8.6 three-tier model routing: free / cheap / powerful."))
    P.append(panel("bargauge", "Avg latency by tool (ms)", 16, 13, 8, 9,
                   [tgt('SELECT atc.tool_name AS "tool", ROUND(AVG(atc.latency_ms)) AS "avg ms" '
                        'FROM agent_tool_calls atc '
                        'JOIN ai_chat_sessions s ON s.id=atc.session_id '
                        'WHERE s.user_id=$user AND atc.created_at > now() - interval \'30 days\' '
                        'GROUP BY 1 ORDER BY 2 DESC', fmt="table")],
                   opts={"displayMode": "gradient", "minVizHeight": 10, "minVizWidth": 0,
                         "namePlacement": "auto", "orientation": "horizontal",
                         "reduceOptions": {"calcs": ["lastNotNull"], "fields": "",
                                           "values": True},
                         "showUnfilled": True, "sizing": "auto", "valueMode": "color"},
                   unit="ms", thresholds=th(("green", None), ("yellow", 1500), ("red", 3000))))
    P.append(panel("timeseries", "Agent sessions & tool calls per day", 0, 22, 12, 8,
                   [tgt("SELECT date_trunc('day', started_at) AS \"time\", COUNT(*) AS sessions "
                        "FROM ai_chat_sessions WHERE user_id=$user AND $__timeFilter(started_at) "
                        "GROUP BY 1 ORDER BY 1"),
                    tgt("SELECT date_trunc('day', atc.created_at) AS \"time\", COUNT(*) AS tool_calls "
                        "FROM agent_tool_calls atc JOIN ai_chat_sessions s ON s.id=atc.session_id "
                        "WHERE s.user_id=$user AND $__timeFilter(atc.created_at) GROUP BY 1 ORDER BY 1",
                        ref="B")],
                   overrides=[ov_color("sessions", BLUE), ov_color("tool_calls", PURPLE)]))
    P.append(panel("timeseries", "Tokens in/out per day", 12, 22, 12, 8,
                   [tgt("SELECT date_trunc('day', created_at) AS \"time\", SUM(tokens_in) AS tokens_in, "
                        "SUM(tokens_out) AS tokens_out FROM token_usage WHERE user_id=$user "
                        "AND $__timeFilter(created_at) GROUP BY 1 ORDER BY 1")],
                   custom={**TS_CUSTOM, "fillOpacity": 20},
                   overrides=[ov_color("tokens_in", BLUE), ov_color("tokens_out", GREEN)]))
    P.append(panel("table", "Recent agent tool calls (§8.3 audit)", 0, 30, 14, 10,
                   [tgt('SELECT atc.created_at AS "at", atc.tool_name AS "tool", '
                        'atc.latency_ms AS "latency ms", atc.error AS "error", '
                        'LEFT(atc.input_json::text, 60) AS "input", '
                        'LEFT(atc.output_json::text, 60) AS "output" '
                        'FROM agent_tool_calls atc JOIN ai_chat_sessions s ON s.id=atc.session_id '
                        'WHERE s.user_id=$user ORDER BY atc.created_at DESC LIMIT 20', fmt="table")]))
    P.append(panel("barchart", "Telegram voice drafts by status", 14, 30, 10, 10,
                   [tgt("SELECT tm.status AS \"status\", COUNT(*) AS \"messages\" "
                        "FROM telegram_messages tm "
                        "WHERE tm.chat_id IN (SELECT chat_id FROM telegram_links WHERE user_id=$user) "
                        "GROUP BY 1 ORDER BY 2 DESC", fmt="table")],
                   opts=HBAR_OPTS,
                   desc="§8.5/§10.2 write-confirm flow: pending → confirmed/rejected."))
    P.append(panel("table", "AI reports (daily/weekly/monthly)", 0, 40, 24, 9,
                   [tgt("SELECT generated_at AS \"at\", report_type AS \"type\", "
                        "period_start AS \"from\", period_end AS \"to\", "
                        "COALESCE(model_used, 'template') AS \"model\", "
                        "LEFT(replace(content_md, E'\\n', ' '), 100) AS \"excerpt\" "
                        "FROM ai_reports WHERE user_id=$user ORDER BY generated_at DESC LIMIT 12",
                        fmt="table")],
                   desc="§9.2 templated daily summaries show model 'template' ($0.00)."))
    return dashboard("apex-ai", "AI & Agent", P, [user_var(), budget_var()],
                     desc="Token budget, tool-loop audit, reports, voice drafts, embeddings usage.")


# ------------------------------------------------------------------ journal
def build_journal():
    P = []
    stats = [
        ("Entries (7d)", "SELECT COUNT(*) AS value FROM journal_entries WHERE user_id=$user AND date > CURRENT_DATE - 7", "short"),
        ("Avg mood (30d)", "SELECT ROUND(AVG(mood_score),1) AS value FROM journal_entries WHERE user_id=$user AND date > CURRENT_DATE - 30", None),
        ("Avg energy (30d)", "SELECT ROUND(AVG(energy_score),1) AS value FROM journal_entries WHERE user_id=$user AND date > CURRENT_DATE - 30", None),
        ("Avg soreness (30d)", "SELECT ROUND(AVG(soreness_score),1) AS value FROM journal_entries WHERE user_id=$user AND date > CURRENT_DATE - 30", None),
        ("Streak (days)", "WITH RECURSIVE d AS (SELECT MAX(date) AS day FROM journal_entries WHERE user_id=$user UNION ALL SELECT day - 1 FROM d WHERE EXISTS (SELECT 1 FROM journal_entries je WHERE je.user_id=$user AND je.date = d.day - 1)) SELECT COUNT(*) AS value FROM d", "short"),
        ("Days logged (30d)", "SELECT COUNT(*) AS value FROM journal_entries WHERE user_id=$user AND date > CURRENT_DATE - 30", "short"),
        ("Voice entries (30d)", "SELECT COUNT(*) AS value FROM journal_entries WHERE user_id=$user AND source='telegram_voice' AND date > CURRENT_DATE - 30", "short"),
        ("Tags in use", "SELECT COUNT(DISTINCT tag) AS value FROM journal_entries je, unnest(je.tags) AS tag WHERE je.user_id=$user", "short"),
    ]
    for i, (title, sql, unit) in enumerate(stats):
        P.append(panel("stat", title, i * 3, 0, 3, 5, [tgt(sql, fmt="table")], unit=unit))
    P.append(panel("timeseries", "Mood · Energy · Motivation", 0, 5, 12, 8,
                   [tgt('SELECT date AS "time", mood_score AS mood, energy_score AS energy, '
                        'motivation_score AS motivation FROM journal_entries '
                        'WHERE user_id=$user AND $__timeFilter(date) ORDER BY date')],
                   overrides=[ov_color("mood", PINK), ov_color("energy", GREEN),
                              ov_color("motivation", BLUE)],
                   minv=0, maxv=10, legend=LEGEND_TABLE))
    P.append(panel("timeseries", "Mood vs training strain", 12, 5, 12, 8,
                   [tgt('SELECT date AS "time", mood_score AS mood FROM journal_entries '
                        'WHERE user_id=$user AND mood_score IS NOT NULL AND $__timeFilter(date) '
                        'ORDER BY date'),
                    tgt('SELECT date AS "time", strain_score AS strain FROM daily_features '
                        'WHERE user_id=$user AND $__timeFilter(date) ORDER BY date', ref="B")],
                   overrides=[ov_color("mood", PINK), ov_color("strain", ORANGE),
                              ov_right("strain")],
                   desc="Left axis 0–10 subjective mood; right axis daily strain (§7)."))
    P.append(panel("timeseries", "Soreness & subjective stress", 0, 13, 8, 8,
                   [tgt('SELECT date AS "time", soreness_score AS soreness, stress_subjective AS stress '
                        'FROM journal_entries WHERE user_id=$user AND $__timeFilter(date) '
                        'ORDER BY date')],
                   overrides=[ov_color("soreness", ORANGE), ov_color("stress", RED)],
                   minv=0, maxv=10))
    P.append(panel("timeseries", "Sleep: subjective vs measured", 8, 13, 8, 8,
                   [tgt('SELECT date AS "time", sleep_quality_subjective AS subjective '
                        'FROM journal_entries WHERE user_id=$user AND sleep_quality_subjective IS NOT NULL '
                        'AND $__timeFilter(date) ORDER BY date'),
                    tgt('SELECT local_date AS "time", sleep_score AS measured FROM sleep_sessions '
                        'WHERE user_id=$user AND $__timeFilter(local_date) ORDER BY local_date', ref="B")],
                   overrides=[ov_color("subjective", PURPLE), ov_color("measured", GREEN),
                              ov_right("measured")],
                   desc="Left axis 0–10 subjective; right axis 0–100 measured score."))
    P.append(panel("piechart", "Entry source", 16, 13, 8, 8,
                   [tgt('SELECT now() AS "time", je.source AS metric, COUNT(*) AS value '
                        'FROM journal_entries je WHERE je.user_id=$user AND $__timeFilter(je.date) '
                        'GROUP BY 2')],
                   desc="web vs telegram_voice (§10.2 speech-to-text flow)."))
    P.append(panel("barchart", "Tags", 0, 21, 12, 8,
                   [tgt("SELECT tag AS \"tag\", COUNT(*) AS \"uses\" "
                        "FROM journal_entries je, "
                        "unnest(je.tags) AS tag WHERE je.user_id=$user AND $__timeFilter(je.date) "
                        "GROUP BY 1 ORDER BY 2 DESC", fmt="table")], opts=HBAR_OPTS))
    P.append(panel("barchart", "Days logged per week", 12, 21, 12, 8,
                   [tgt("SELECT date_trunc('week', date) AS \"time\", COUNT(*) AS entries "
                        "FROM journal_entries je WHERE je.user_id=$user AND $__timeFilter(je.date) "
                        "GROUP BY 1 ORDER BY 1")],
                   custom={**BAR_CUSTOM}, thresholds=th(("blue", None))))
    P.append(panel("table", "Recent entries", 0, 29, 24, 10,
                   [tgt("SELECT to_char(je.date,'YYYY-MM-DD') AS \"date\", je.source AS \"source\", mood_score AS \"mood\", "
                        "energy_score AS \"energy\", soreness_score AS \"soreness\", "
                        "stress_subjective AS \"stress\", sleep_quality_subjective AS \"sleep q\", "
                        "array_to_string(tags, ', ') AS \"tags\", LEFT(free_text_notes, 80) AS \"notes\" "
                        "FROM journal_entries je WHERE je.user_id=$user ORDER BY je.date DESC LIMIT 20",
                        fmt="table")],
                   desc="Voice-sourced rows (§10.2) carry the transcript + confirm flow."))
    return dashboard("apex-journal", "Journal & Mind", P, [user_var()],
                     desc="Subjective scores vs measured data, tags, voice-note history.")


# ------------------------------------------------------------------- system
def build_system():
    P = []
    stats = [
        ("Watch sync age (h)", "SELECT ROUND(EXTRACT(EPOCH FROM (now()-MAX(synced_at)))/3600.0,1) AS value FROM watch_sync_log WHERE user_id=$user", None, th(("red", 30), ("yellow", 12))),
        ("Technogym sync age (h)", "SELECT ROUND(EXTRACT(EPOCH FROM (now()-MAX(synced_at)))/3600.0,1) AS value FROM technogym_sync_log WHERE user_id=$user", None, th(("red", 30), ("yellow", 12))),
        ("Active sessions", "SELECT COUNT(*) AS value FROM sessions WHERE expires_at > now()", "short", None),
        ("DB size", "SELECT pg_size_pretty(pg_database_size(current_database())) AS value", None, None),
        ("Embeddings (§6.2)", "SELECT COUNT(*) AS value FROM embeddings", "short", th(("yellow", 1))),
        ("Forecast days cached", "SELECT COUNT(*) AS value FROM forecast_cache WHERE date >= CURRENT_DATE", "short", None),
        ("Invite codes", "SELECT COUNT(*) AS value FROM invites", "short", None),
        ("Raw ingest unprocessed", "SELECT COUNT(*) AS value FROM raw_ingest WHERE processed = false", "short", th(("yellow", 1))),
    ]
    for i, (title, sql, unit, thr) in enumerate(stats):
        P.append(panel("stat", title, i * 3, 0, 3, 5, [tgt(sql, fmt="table")],
                       unit=unit, thresholds=thr))
    P.append(panel("table", "Integrations (§21)", 0, 5, 12, 8,
                   [tgt("SELECT provider AS \"provider\", status AS \"status\", "
                        "consecutive_failures AS \"failures\", last_synced_at AS \"last sync\", "
                        "ROUND(EXTRACT(EPOCH FROM (now()-last_synced_at))/3600.0,1) AS \"hours ago\" "
                        "FROM integrations WHERE user_id=$user ORDER BY provider", fmt="table")],
                   desc="3 consecutive failures trigger §21 escalation (sync_failure alert + push)."))
    P.append(panel("table", "Alerts (recent)", 12, 5, 12, 8,
                   [tgt("SELECT triggered_at AS \"at\", type AS \"type\", severity AS \"severity\", "
                        "message AS \"message\", acknowledged AS \"ack\" FROM alerts WHERE user_id=$user "
                        "ORDER BY triggered_at DESC LIMIT 12", fmt="table")],
                   overrides=[ov_map("severity", sev_mapping())]))
    P.append(panel("timeseries", "Raw ingest rows/day by source (§3)", 0, 13, 12, 8,
                   [tgt("SELECT date_trunc('day', fetched_at) AS \"time\", source AS metric, COUNT(*) AS value "
                        "FROM raw_ingest WHERE $__timeFilter(fetched_at) GROUP BY 1, 2 ORDER BY 1",
                        fmt="table")]))
    P.append(panel("table", "Users & access (§4)", 12, 13, 12, 8,
                   [tgt("SELECT u.id AS \"id\", u.name AS \"name\", ac.email AS \"email\", "
                        "ac.role AS \"role\", ac.ai_access_tier AS \"ai tier\", u.timezone AS \"tz\" "
                        "FROM users u JOIN auth_credentials ac ON ac.user_id = u.id "
                        "ORDER BY u.id", fmt="table")],
                   desc="Owner onboards friends via invite codes (§4.3)."))
    P.append(panel("table", "Gear service status (§13)", 0, 21, 12, 8,
                   [tgt("SELECT name AS \"gear\", gear_type AS \"type\", km_since_service AS \"km used\", "
                        "service_interval_km AS \"km interval\", "
                        "CASE WHEN service_interval_km > 0 THEN ROUND(100.0*km_since_service/service_interval_km) END "
                        "AS \"km %\", hours_since_service AS \"h used\", service_interval_hours AS \"h interval\", "
                        "CASE WHEN service_interval_hours > 0 THEN ROUND(100.0*hours_since_service/service_interval_hours) END "
                        "AS \"h %\" FROM gear WHERE user_id=$user ORDER BY name", fmt="table")]))
    P.append(panel("table", "Sync logs", 12, 21, 12, 8,
                   [tgt("SELECT 'watch' AS \"log\", synced_at AS \"at\", sync_type AS \"direction\", "
                        "'ok' AS \"status\" FROM watch_sync_log WHERE user_id=$user "
                        "UNION ALL SELECT 'technogym', synced_at, sync_direction, status "
                        "FROM technogym_sync_log WHERE user_id=$user "
                        "ORDER BY \"at\" DESC LIMIT 15", fmt="table")]))
    P.append(panel("table", "Data coverage", 0, 29, 10, 9,
                   [tgt("SELECT 'daily_features' AS \"source\", COUNT(*) AS \"rows\", MAX(date) AS \"latest\" "
                        "FROM daily_features WHERE user_id=$user "
                        "UNION ALL SELECT 'sleep_sessions', COUNT(*), MAX(local_date) FROM sleep_sessions WHERE user_id=$user "
                        "UNION ALL SELECT 'activities', COUNT(*), MAX(local_date) FROM activities WHERE user_id=$user "
                        "UNION ALL SELECT 'hrv_readings', COUNT(*), MAX(timestamp)::date FROM hrv_readings WHERE user_id=$user "
                        "UNION ALL SELECT 'nutrition_logs', COUNT(*), MAX(timestamp)::date FROM nutrition_logs WHERE user_id=$user "
                        "UNION ALL SELECT 'journal_entries', COUNT(*), MAX(date) FROM journal_entries WHERE user_id=$user "
                        "UNION ALL SELECT 'lab_panels', COUNT(*), MAX(date) FROM lab_panels WHERE user_id=$user "
                        "UNION ALL SELECT 'token_usage', COUNT(*), MAX(created_at)::date FROM token_usage WHERE user_id=$user",
                        fmt="table")]))
    P.append(panel("table", "Rollups (§7.4)", 10, 29, 8, 9,
                   [tgt("SELECT 'weekly' AS \"kind\", week_start::text AS \"period\", "
                        "metric_name AS \"metric\", mean_value AS \"mean\", trend_slope AS \"slope\" "
                        "FROM weekly_rollups WHERE user_id=$user "
                        "UNION ALL SELECT 'monthly', month_start::text, metric_name, mean_value, trend_slope "
                        "FROM monthly_rollups WHERE user_id=$user "
                        "ORDER BY 2 DESC LIMIT 14", fmt="table")]))
    P.append(panel("table", "Invite codes (§4.3)", 18, 29, 6, 9,
                   [tgt("SELECT LEFT(code, 4) || '…' AS \"code\", used_by AS \"used by\", "
                        "expires_at AS \"expires\" FROM invites ORDER BY created_at DESC LIMIT 8",
                        fmt="table")]))
    P.append(text_panel(
        "Ops notes", 0, 38, 24, 7,
        "### 🛠️ System context\n"
        "- **Backups (§22.7)**: nightly `02:00 UTC` — `pg_dump → gzip → Fernet(BACKUP_ENCRYPTION_KEY)`, "
        "14 daily + 6 monthly retained, B2 offsite upload (failure never blocks the local backup).\n"
        "- **Restore drill**: rerunnable `tools/restore_drill.py` — last run **46/46 tables matched**, crypto round-trip OK.\n"
        "- **Escalation (§21)**: 3 consecutive connector failures → `sync_failure` alert + Telegram push.\n"
        "- **Alerts vs logs**: alerts live here; structured JSON logs (§21) go to stdout.\n"
        "- **Honest limits**: read-only UI (no bot/agent interaction), lab notes encrypted-not-rendered, "
        "demo data is synthetic, Docker parity still unproven."))
    return dashboard("apex-system", "System & Sync Health", P, [user_var()],
                     time_from="now-30d", refresh="1m",
                     desc="Connectors, raw ingest, alerts, gear, rollups, invites, backups coverage, session state.")


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "/home/z/apex-health-clone"
    write(repo, "overview", build_overview())
    write(repo, "activity", build_activity())
    write(repo, "recovery", build_recovery())
    write(repo, "nutrition", build_nutrition())
    write(repo, "labs", build_labs())
    write(repo, "ai", build_ai())
    write(repo, "journal", build_journal())
    write(repo, "system", build_system())
    print("8 dashboards generated")


if __name__ == "__main__":
    main()
