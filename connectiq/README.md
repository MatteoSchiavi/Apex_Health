# Apex Day — Connect IQ watch app (Phase 10 v2)

The **rethought** watch app. The original Phase 10 put readiness / recovery /
strain on the wrist — which was the wrong idea: every supported device already
renders those natively (Training Readiness, Recovery Time, Body Battery /
Training Load). A data page duplicating them is a worse copy of what the watch
already shows.

**Apex Day shows what ONLY Apex knows:**

| Surface | Content | Source |
|---|---|---|
| **Glance** | today's gym session (title + time) or "Rest day"; supplement / open-alert / streak counts | `GET /watch/day` via 30-min background refresh |
| **Today** | gym sessions with the exercises block (recurring routine + `PLANNED SESSION` AI overrides), active supplements, open alerts, journal streak | `GET /watch/day` |
| **Week** | 7-day schedule, today highlighted — planned sessions override the recurring template on their dates | `GET /watch/week` |
| **Alerts** | open alerts, severity-colored (acking stays in Telegram/web) | `GET /watch/day` (cached) |

## Data flow

```
┌────────┐  makeWebRequest (Bearer device token, 15 min while open)  ┌────────┐
│  watch  │ ────────────────────────────────────────────────────────▶ │  Apex   │
│ (BLE +  │ ◀─────────────────────────── JSON /watch/day, /watch/week │ backend │
│  phone) │                                                            └────────┘
│         │  background temporal event every 30 min → /watch/day
│         │  results parked in Application.Storage ($ keys)
└────────┘
        glance + views paint from Storage — never block on the radio
```

- **Auth**: a per-user device token (`POST /watch/tokens`, plaintext shown
  once, peppered-hash at rest, soft-revocable). On 401 the app DELETES its
  cached data and shows "Token invalid" — a revoked token can never pose
  stale data as current.
- **Isolation**: the token resolves to exactly one user; there is no
  parameter to fetch anyone else's schedule (proven by tests,
  `tests/test_gym_schedule.py`).
- **Server URL**: your Tailscale Funnel URL (`https://host.tailnet.ts.net`) —
  the same surface friends use for remote access (§15).

## Files

```
connectiq/
├── manifest.xml                  # watch-app + glances, CIQ 4.0 (fr965/fenix7x/epix2)
├── monkey.jungle                 # build config
└── source/
    ├── ApexApp.mc                # entry: Menu2 (Today/Week/Alerts) + glance + service
    ├── ApexDayService.mc         # /watch/day + /watch/week fetch, Storage cache, 401 wipe
    ├── ApexFormat.mc             # weekday names, severity colors, word-wrap
    ├── ApexGlanceView.mc         # glance: session + counts
    ├── ApexTodayView.mc          # full day: gym / supplements / alerts / streak
    ├── ApexWeekView.mc           # 7-day schedule
    ├── ApexAlertsView.mc         # open alerts
    └── ApexBackgroundService.mc  # 30-min temporal refresh, re-arms + exits
```

## Setting your gym schedule

The recurring weekly routine lives in the backend (`gym_schedule_slots`,
migration 0005) and can be managed two ways:

- **Telegram** (phone-only, no REST client needed):
  - `/gym` — today's sessions · `/gym week` — the 7 days
  - `/gym set Mon 18:00 Push Day` — add a slot
  - `/gym note 1 Bench 4x8 · Incline 3x10` — attach the exercises block
  - `/gym list` — slots with ids · `/gym rm 1` — remove
- **REST** (session + CSRF): `GET/POST /schedule`, `PATCH/DELETE /schedule/{id}`.

Confirmed/active AI training plans (`training_plans`/`planned_sessions`)
override the recurring template on their specific dates — so the routine is
the baseline and the plan layer refines individual days.

## Building the .prg (requires the owner's machine)

The Monkey C sources here are complete but **not compiled in this
environment** (the Garmin SDK cannot be fetched non-interactively). On a
machine with the [Connect IQ SDK](https://developer.garmin.com/connect-iq/sdk/):

```bash
# 1. one-time: accept the SDK license and get a developer key
connectiq  # or: java -jar bin/monkeybrains.jar -a   (CIQ SDK ≥ 7 GUI)

# 2. build (from the repo root)
monkeyc \
  -f connectiq/monkey.jungle \
  -y ~/garmin/developer_key.pem \
  -w -o bin/apexday.prg \
  -d fr965            # or fenix7x / epix2

# 3. sideload: copy bin/apexday.prg to GARMIN/Apps/ on the watch over USB,
#    or use `monkeydo bin/apexday.prg fr965` with the simulator first.
```

Then in **Garmin Connect IQ settings** for Apex Day:

1. **Server URL** — your Funnel URL, e.g. `https://apex.tailnet-example.ts.net`
2. **API token** — mint from the web API:
   `curl -X POST $URL/watch/tokens -b "session=..." -H "X-CSRF-Token: ..." -d '{"name":"fenix"}'`
   (or via the documented flow in `docs/INSTALL.md` §8b) and paste the
   plaintext once.

## Honest limits

- Not compiled here — needs the owner's SDK + hardware for the .prg and
  on-device verification (monkeydo simulator run recommended first).
- `makeWebRequest` requires the phone companion app reachable (BLE) or
  Wi-Fi on devices that have it; the glance still paints the last cached
  day when the phone is away, stamped by freshness via the streak footer.
- Plan sessions have no clock time (`start: null`) — the week view and
  Today view handle this by omitting the time, not faking one.
