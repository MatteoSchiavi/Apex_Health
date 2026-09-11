# Apex Health — Connect IQ glance

A Connect IQ **glance** (watch-app with glance view) for Garmin wearables:
on your watch face's glance strip it shows **today's readiness, recovery and
strain** — the three §7 composite scores — color-banded like the rest of the
platform (green/amber/red, `--` when the day has no scores yet).

```
┌──────────────────────────┐        ┌──────────────────────────┐
│ READY              82.5  │        │ READY              88.0  │  green
│ RECOVERY           61.0  │        │ RECOVERY           38.0  │  red
│ STRAIN             14.2  │        │ STRAIN              9.5  │  green
│            2026-09-11    │        │            2026-09-10    │  stale: date shown
└──────────────────────────┘        └──────────────────────────┘
```

## How it talks to the server

- Data source: `GET /watch/today` (Bearer token) — see `backend/app/api/watch.py`.
  The server answers with the **token owner's** scores for the **owner's
  local date** (§17 day-boundary rule); a friend's watch can only ever see
  the friend's numbers — isolation is structural, not a parameter.
- Token: mint with `POST /watch/tokens` (any session — owner or friend):

  ```sh
  curl -X POST https://<funnel-host>.ts.net/watch/tokens \
       -H "Content-Type: application/json" \
       -H "X-CSRF-Token: t" \
       -b "hcc_session=<your session cookie>" \
       -d '{"name": "fr965"}'
  # {"id": 3, "name": "fr965", "token": "<ONE-TIME SECRET>", ...}
  ```

  Revoke with `DELETE /watch/tokens/{id}` (immediate: the next request
  answers 401 and the watch drops its cache).
- On the watch: open **Settings → Connect IQ → Apex Health → Settings** and
  paste the **Funnel URL** (`https://<host>.<tailnet>.ts.net`) and the token.
- Refresh model: a background temporal event (every 30 min) fetches and
  caches into `Application.Storage`; the **glance never touches the network**
  — it paints from cache in milliseconds. Opening the app refreshes live.
- When today isn't scored yet (the nightly engine runs 03:00 user-local),
  the server serves the most recent scored day with `stale: true` — the
  glance shows that date so yesterday's recovery never poses as today's.

## Building the .prg

You need the Garmin Connect IQ SDK and a developer key (once):

```sh
# 1. SDK: install via https://developer.garmin.com/connect-iq/sdk/ or:
#    SDK Manager -> "Connect IQ SDK" (linux tarball), unzip anywhere.
# 2. Developer key (used to sign the .prg):
openssl genrsa -out developer_key.pem 4096

# 3. Compile (from this directory):
monkeyc -f monkey.jungle \
        -y developer_key.pem \
        -d fr965 \
        -w \
        -o bin/apexhealth.prg

# 4. Sideload: copy bin/apexhealth.prg to GARMIN/Apps/ on the watch (or use
#    the SDK's device simulator: connectiq -d fr965, then File > Load App).
```

Alternatively open this folder in VS Code with the official *Connect IQ
SDK* extension — it reads `monkey.jungle` and builds/simulates with F5.

Products pinned in `manifest.xml`: **fr965, fenix7x, epix2** (all Connect IQ
4.0+, all with glance support). Add more `<iq:product id="..."/>` lines as
needed — the code uses only CIQ-4.0 APIs (`GlanceView`, `ServiceDelegate`,
`makeWebRequest`).

## Repo layout

```
connectiq/
├── manifest.xml            # app metadata, products, permissions, glances entry
├── monkey.jungle           # build config consumed by monkeyc
├── resources/
│   ├── strings/strings.xml     # user-visible strings
│   ├── properties/properties.xml  # server_url + api_token defaults
│   ├── settings/settings.xml   # editable from Garmin Connect / Express
│   └── drawables/              # launcher icon (generated, 34x34)
└── source/
    ├── ApexApp.mc              # entry: glance + app + background service
    ├── ApexTodayService.mc     # /watch/today fetch + Storage cache
    ├── ApexGlanceView.mc       # THE GLANCE (readiness/recovery/strain)
    ├── ApexView.mc             # full-screen view + manual refresh
    ├── ApexBackgroundService.mc# 30-min temporal fetch
    └── ApexScore.mc            # shared format/color bands
```

## Honest limitations

- Built and reviewed against the Connect IQ 4.0 API surface, but **not
  compiled or run on real hardware from this environment** (the SDK needs
  Garmin's installer; sideloading needs the physical watch). First build on
  the owner's machine: `monkeyc` will catch any API drift on the exact SDK
  version you have.
- `makeWebRequest` from the watch routes through the **phone's** internet
  connection (Garmin Connect app, BLE) — that's why the public Funnel URL
  works from anywhere without the watch joining a network.
- Battery: one small HTTPS request per 30 minutes; adjust
  `30 * 60 * 1000L` in `ApexBackgroundService.mc` if you prefer hourly.
