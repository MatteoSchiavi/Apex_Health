#!/usr/bin/env python3
"""Merge the v2 UI keys into en.json / it.json with full parity."""
import json

EN = {
  "search": {"placeholder": "Quick telemetry…", "no_results": "No matches"},
  "sync": {"no_devices": "No device connected"},
  "disc": {
    "unknown": "Activity",
    "running": "Running", "road_cycling": "Road Cycling", "gravel_cycling": "Gravel Cycling",
    "mountain_biking": "Mountain Biking", "strength": "Strength", "gym_general": "Gym",
    "yoga": "Yoga", "pilates": "Pilates", "swimming": "Swimming", "rowing": "Rowing",
    "tennis": "Tennis", "cardio": "Cardio", "walking": "Walking", "hiking": "Hiking"
  },
  "common": {"prev_day": "Previous day", "next_day": "Next day"},
  "overview": {
    "subtitle": "Physiological telemetry & analysis",
    "telemetry_state": "Telemetry state", "live": "Live acquisition", "paused": "Paused",
    "no_devices": "no device connected", "validated": "Validated biosignal",
    "showing_history": "History day", "epoch": "EPOCH",
    "peak_zone": "Peak Zone", "zone": "Zone", "avg7": "7d avg",
    "vs_mean": "vs mean", "vs_baseline": "vs baseline", "rolling": "rolling",
    "band": "Band", "sleep_epochs": "sleep epochs",
    "para_tone": "Parasympathetic Tone",
    "history_notice": "Today has no records yet — showing the most recent measured day ({{date}}).",
    "connect_cta": "Connect a device",
    "empty_body": "Nothing measured for this day yet. Connect Garmin to start the telemetry pipeline — the backfill walks your whole history."
  },
  "synth": {
    "title": "Synthesis Diagnosis",
    "body_prefix": "Autonomic status suggests",
    "level_optimal": "Central sympathetic tone is attenuated and parasympathetic recovery is primed.",
    "level_good": "Recovery reserves are adequate for moderate-to-hard work.",
    "level_low": "Autonomic friction is elevated — prioritize rest and hydration.",
    "level_unknown": "Not enough measured data for a diagnosis yet.",
    "acwr_high": "Acute load is running above the chronic base — cap intensity.",
    "acwr_low": "Detraining risk: chronic base is decaying — schedule stimulus.",
    "acwr_ok": "Load sits inside the optimal 0.8–1.3 window.",
    "no_load": "No measured load yet.",
    "hrv_up": "Overnight HRV is above baseline — parasympathetic response is strong.",
    "hrv_down": "Overnight HRV sits below baseline — monitor recovery.",
    "load_ceiling": "Today's sensible load ceiling"
  },
  "sleep": {
    "subtitle": "Multi-sensor sleep tracking & recovery",
    "architecture": "Architecture",
    "night_detail": "Night detail",
    "asleep": "Asleep",
    "avg_score7": "Avg score · 7d", "avg_duration7": "Avg duration · 7d",
    "avg_deep7": "Avg deep · 7d", "restorative": "restorative share",
    "nights_tracked": "Nights tracked", "window42": "last 6 weeks",
    "recovery_index": "Recovery Index",
    "stage_epochs": "Measured epochs", "proportional": "Proportional view",
    "hypnogram_title": "Continuous Sleep Stage Hypnogram",
    "hypnogram_measured": "Epoch-level stage segmentation read from the stored device payload.",
    "hypnogram_fallback": "No epoch timeline stored for this night — blocks are proportional to the measured stage totals.",
    "night_subtitle": "Bed window {{start}} → {{end}}",
    "bed_window": "window", "target_met": "optimal buffer met",
    "awake_time": "Awake", "disturbances": "micro-disturbances",
    "movement_index": "movement index", "autonomic": "Autonomic Biometrics",
    "overnight_sensors": "overnight optical & PPG sensors",
    "steady": "steady", "saturation_note": "mean saturation",
    "sleep_regularity_short": "Regularity", "stable": "Stable", "limited": "Limited data",
    "window7": "7-day window", "avg7": "avg",
    "hrv_envelope": "rMSSD Envelope", "overnight_hrv": "Overnight HRV",
    "readings": "readings", "circadian": "Circadian Synchronization",
    "rhythm_alignment": "Sleep Rhythm Alignment", "midpoint": "Sleep midpoint",
    "no_night_hint": "Nights appear as soon as a device reports sleep."
  },
  "activities": {
    "subtitle": "Every recorded session, full telemetry",
    "ago": "ago",
    "sessions": "Sessions", "in_range": "in range",
    "time_total": "Total time", "distance_total": "Total distance",
    "load_total": "Total load",
    "altitude_color": "colored by altitude",
    "timeline_title": "Synchronized Timeline Stream",
    "channels": "channels",
    "identified": "identified"
  },
  "biometrics": {
    "page_subtitle": "Single-metric telemetry with measured history",
    "group_cardiac": "Cardiac & Autonomic",
    "group_body": "Body & Capacity",
    "assess_optimal": "Optimal", "assess_watch": "Watch", "assess_no_data": "No data"
  },
  "weather": {
    "temp": "Temperature", "wind": "Wind max", "precip": "Precipitation",
    "clear": "Clear sky", "mostly_clear": "Mostly clear", "partly_cloudy": "Partly cloudy",
    "overcast": "Overcast", "fog": "Fog", "drizzle": "Drizzle", "rain": "Rain",
    "snow": "Snow", "showers": "Showers", "storm": "Thunderstorm"
  },
  "training": {"subtitle": "Events calendar, load management and gym prescription"},
  "coach": {"subtitle": "Ask about any metric — conversations persist locally and on the server", "conversation": "Conversation"},
  "social": {"subtitle": "Challenges and rankings with your friends"},
  "settings": {
    "page_subtitle": "Profile, appearance, devices and account",
    "garmin_not_connected": "Not linked yet — connect below, tokens are stored encrypted.",
    "provider_setup": "Awaiting provider setup",
    "garmin_connect_hint": "Sign in with your Garmin account once — Apex exchanges the credentials for session tokens, stores them app-layer-encrypted, and never keeps the password. The first sync walks your entire history.",
    "garmin_email": "Garmin email", "garmin_password": "Garmin password",
    "garmin_mfa": "One-time code (MFA)",
    "connecting": "Connecting…", "verify_code": "Verify code",
    "mfa_sent": "Enter the code Garmin sent you.",
    "sync_now": "Sync now",
    "tokens_note": "Access tokens are handled for you: stored encrypted on the owner's server and refreshed automatically — there is nothing to copy or manage by hand."
  }
}

IT = {
  "search": {"placeholder": "Telemetria rapida…", "no_results": "Nessun risultato"},
  "sync": {"no_devices": "Nessun dispositivo collegato"},
  "disc": {
    "unknown": "Attività",
    "running": "Corsa", "road_cycling": "Ciclismo su strada", "gravel_cycling": "Gravel",
    "mountain_biking": "Mountain bike", "strength": "Forza", "gym_general": "Palestra",
    "yoga": "Yoga", "pilates": "Pilates", "swimming": "Nuoto", "rowing": "Canottaggio",
    "tennis": "Tennis", "cardio": "Cardio", "walking": "Camminata", "hiking": "Trekking"
  },
  "common": {"prev_day": "Giorno precedente", "next_day": "Giorno successivo"},
  "overview": {
    "subtitle": "Telemetria fisiologica e analisi",
    "telemetry_state": "Stato telemetria", "live": "Acquisizione attiva", "paused": "In pausa",
    "no_devices": "nessun dispositivo collegato", "validated": "Biosegnale validato",
    "showing_history": "Giorno storico", "epoch": "EPOCA",
    "peak_zone": "Zona di picco", "zone": "Zona", "avg7": "media 7g",
    "vs_mean": "vs media", "vs_baseline": "vs baseline", "rolling": "progressiva",
    "band": "Fascia", "sleep_epochs": "epoche sonno",
    "para_tone": "Tono Parasimpatico",
    "history_notice": "Oggi non ci sono ancora dati — mostro il giorno più recente misurato ({{date}}).",
    "connect_cta": "Collega un dispositivo",
    "empty_body": "Nessun dato misurato per questo giorno. Collega Garmin per avviare la pipeline — il backfill ripercorre tutta la cronologia."
  },
  "synth": {
    "title": "Diagnosi di Sintesi",
    "body_prefix": "Lo stato autonomo suggerisce:",
    "level_optimal": "il tono simpatico centrale è attenuato e il recupero parasimpatico è pronto.",
    "level_good": "le riserve di recupero sono adeguate per lavoro da moderato a intenso.",
    "level_low": "l'attrito autonomo è elevato — privilegia riposo e idratazione.",
    "level_unknown": "servono più dati misurati per una diagnosi.",
    "acwr_high": "Il carico acuto supera la base cronica — limita l'intensità.",
    "acwr_low": "Rischio detraining: la base cronica scende — programma uno stimolo.",
    "acwr_ok": "Il carico è dentro la finestra ottimale 0,8–1,3.",
    "no_load": "Nessun carico misurato.",
    "hrv_up": "L'HRV notturna è sopra la baseline — risposta parasimpatica forte.",
    "hrv_down": "L'HRV notturna è sotto la baseline — monitora il recupero.",
    "load_ceiling": "Tetto di carico sensibile di oggi"
  },
  "sleep": {
    "subtitle": "Sonno multisensore e recupero",
    "architecture": "Architettura",
    "night_detail": "Dettaglio notte",
    "asleep": "Addormentato",
    "avg_score7": "Punteggio medio · 7g", "avg_duration7": "Durata media · 7g",
    "avg_deep7": "Sonno profondo medio · 7g", "restorative": "quota ristorativa",
    "nights_tracked": "Notti registrate", "window42": "ultime 6 settimane",
    "recovery_index": "Indice di Recupero",
    "stage_epochs": "Epoche misurate", "proportional": "Vista proporzionale",
    "hypnogram_title": "Iprogramma Continuo delle Fasi",
    "hypnogram_measured": "Segmentazione epoch-level letta dal payload memorizzato del dispositivo.",
    "hypnogram_fallback": "Nessuna cronologia di epoche per questa notte — i blocchi sono proporzionali ai totali misurati.",
    "night_subtitle": "Finestra a letto {{start}} → {{end}}",
    "bed_window": "finestra", "target_met": "buffer ottimale raggiunto",
    "awake_time": "Sveglio", "disturbances": "micro-risvegli",
    "movement_index": "indice di movimento", "autonomic": "Biomarcatori Autonomici",
    "overnight_sensors": "sensori notturni ottici e PPG",
    "steady": "stabile", "saturation_note": "saturazione media",
    "sleep_regularity_short": "Regolarità", "stable": "Stabile", "limited": "Dati limitati",
    "window7": "finestra 7 giorni", "avg7": "media",
    "hrv_envelope": "Inviluppo rMSSD", "overnight_hrv": "HRV Notturna",
    "readings": "letture", "circadian": "Sincronizzazione Circadiana",
    "rhythm_alignment": "Allineamento del Ritorno del Sonno", "midpoint": "Punto medio del sonno",
    "no_night_hint": "Le notti compaiono appena un dispositivo riporta il sonno."
  },
  "activities": {
    "subtitle": "Ogni sessione registrata, telemetria completa",
    "ago": "fa",
    "sessions": "Sessioni", "in_range": "nel periodo",
    "time_total": "Tempo totale", "distance_total": "Distanza totale",
    "load_total": "Carico totale",
    "altitude_color": "colorata per altitudine",
    "timeline_title": "Flusso Temporale Sincronizzato",
    "channels": "canali",
    "identified": "identificati"
  },
  "biometrics": {
    "page_subtitle": "Telemetria a metrica singola con cronologia misurata",
    "group_cardiac": "Cardiaco e Autonomico",
    "group_body": "Corpo e Capacità",
    "assess_optimal": "Ottimale", "assess_watch": "Da seguire", "assess_no_data": "Nessun dato"
  },
  "weather": {
    "temp": "Temperatura", "wind": "Vento max", "precip": "Precipitazioni",
    "clear": "Sereno", "mostly_clear": "Prevalentemente sereno", "partly_cloudy": "Parzialmente nuvoloso",
    "overcast": "Coperto", "fog": "Nebbia", "drizzle": "Pioviggine", "rain": "Pioggia",
    "snow": "Neve", "showers": "Rovesci", "storm": "Temporale"
  },
  "training": {"subtitle": "Calendario eventi, gestione del carico e prescrizione palestra"},
  "coach": {"subtitle": "Chiedi di ogni metrica — le conversazioni restano sul server e in locale", "conversation": "Conversazione"},
  "social": {"subtitle": "Sfide e classifiche con i tuoi amici"},
  "settings": {
    "page_subtitle": "Profilo, aspetto, dispositivi e account",
    "garmin_not_connected": "Non collegato — connettiti qui sotto, i token sono salvati cifrati.",
    "provider_setup": "In attesa di configurazione del fornitore",
    "garmin_connect_hint": "Accedi una sola volta con il tuo account Garmin — Apex scambia le credenziali con token di sessione, li salva cifrati e non conserva mai la password. La prima sincronizzazione ripercorre tutta la cronologia.",
    "garmin_email": "Email Garmin", "garmin_password": "Password Garmin",
    "garmin_mfa": "Codice monouso (MFA)",
    "connecting": "Connessione…", "verify_code": "Verifica codice",
    "mfa_sent": "Inserisci il codice che Garmin ti ha inviato.",
    "sync_now": "Sincronizza ora",
    "tokens_note": "I token di accesso sono gestiti per te: salvati cifrati sul server del proprietario e rinnovati automaticamente — non c'è nulla da copiare o gestire a mano."
  }
}


def merge(target, patch):
    for k, v in patch.items():
        if isinstance(v, dict):
            merge(target.setdefault(k, {}), v)
        else:
            target[k] = v


for path, patch in (("src/locales/en.json", EN), ("src/locales/it.json", IT)):
    data = json.load(open(path))
    merge(data, patch)
    json.dump(data, open(path, "w"), ensure_ascii=False, indent=2, sort_keys=False)
    open(path, "a").write("\n")
    print(f"{path}: {sum(1 for _ in json.load(open(path)).items())} top sections updated")
