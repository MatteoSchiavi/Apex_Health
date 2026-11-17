"""A three-line, non-AI readout of the user's recorded observations."""
from datetime import date, timedelta
from math import isfinite

LABELS = {
    "resting_hr": ("resting HR", "FC a riposo", "bpm"),
    "sleep_duration": ("sleep", "sonno", "h"),
    "hrv_overnight_rmssd": ("night HRV", "HRV notturna", "ms"),
    "sleep_score": ("sleep score", "punteggio sonno", "/100"),
    "body_battery": ("Body Battery", "Body Battery", "/100"),
    "stress": ("stress", "stress", "/100"),
}


def recorded_lines(evidence, day: date, locale: str):
    italian = locale == "it"
    def tr(en, it): return it if italian else en
    def number(row):
        value = row.get("value")
        return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)
    def value(row): return f'{row["value"]:g}'
    current = {key: next((r for r in reversed(rows) if r["local_date"] == str(day) and number(r) and (key not in LABELS or r.get("unit") == LABELS[key][2])), None)
               for key, rows in evidence.items()}
    today = []
    for key, (en, it, unit) in LABELS.items():
        row = current.get(key)
        if row:
            today.append(f'{tr(en, it)} {value(row)} {unit}')
    first = tr("Today: ", "Oggi: ") + "; ".join(today[:2]) if today else tr(
        "Today: no recorded recovery readings yet.", "Oggi: nessuna misura di recupero ancora registrata.")
    second = tr("Past week: not enough comparable readings for a trend.", "Ultima settimana: misure comparabili insufficienti per una tendenza.")
    for key in ("resting_hr", "sleep_duration", "hrv_overnight_rmssd"):
        rows = [r for r in evidence.get(key, []) if str(day-timedelta(days=7)) <= r["local_date"] < str(day) and number(r) and r.get("unit") == LABELS[key][2]]
        if not rows:
            continue
        # Never describe a provider switch as a physiological trend.
        origin = (current.get(key) or rows[-1])["origin"]
        rows = [r for r in rows if r["origin"] == origin]
        days = len({r["local_date"] for r in rows})
        if days >= 3:
            en, it, unit = LABELS[key]
            second = tr("Past week: ", "Ultima settimana: ") + f'{tr(en,it)} {value(rows[0])} → {value(rows[-1])} {unit}' + tr(f" ({days}/7 recorded days).", f" ({days}/7 giorni registrati).")
            break
    third = tr("Next: review today's workout and record how it felt.", "Poi: rivedi l’allenamento di oggi e registra come ti sei sentito.") if today else tr(
        "Next: sync your watch, then review today's workout.", "Poi: sincronizza l’orologio e rivedi l’allenamento di oggi.")
    return [first, second, third]
