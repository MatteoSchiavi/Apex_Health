# Apex Day — Connect IQ watch app (v3, battery-first companion)

The wrist companion for Apex Health. It shows **only what Apex knows and
Garmin does not**: the AI-coach safety verdict, today's workout + where to
find it, the gym plan with a set logger and rest timer, post-workout
feedback, supplement adherence, Apex alerts, gear/donation/event upkeep, the
weather window and the week. Readiness, recovery, Body Battery, HRV, sleep
and HR stay native on the device — a watch app duplicating them is a worse
copy of what the watch already shows.

**First target device: fēnix 7 Pro** (`fenix7pro` — 260×260 round MIP,
64-color palette, touch + 5 buttons, CIQ 4.x; app memory 768 KB, background
64 KB, glance 64 KB). The code is device-agnostic (relative layout, round
insets, buttons + touch), so more devices are one `<iq:product>` line each.

## What the owner sees

| # | Screen | Content | Data |
|---|---|---|---|
| G | **Glance** | verdict word (GO/MODIFY/REST, coloured) · workout name + status dot · supplement/alert/streak counts · data age | cached payload |
| 1 | **Today** | verdict + first reason + ceiling · workout card (title, minutes, status, *"Find it: Activity › Training › Workouts"*) · next supplement · gear due · event countdown · weather line · alerts · streak | `/watch/day` |
| 2 | **Workout status** | did the published workout reach the watch? (v3 `wo` block; honest "unknown — needs server v3" against the current backend) | `wo` block |
| 3 | **Gym session** | today's plan, progress, exercise picker (Menu2) → tracker: target "4 × 6–8", set dots, reps/kg steppers, **LOG SET**, rest timer with vibration + skip, next-exercise preview | `gym_plan` |
| 4 | **Feedback** | RPE 1–10 · soreness 1–5 · injury toggle · one confirm (flushes once immediately if the phone is up) | queued event |
| 5 | **Supplements** | one-tap adherence with checkbox + timestamp, resets on server date change | `supplements` |
| 6 | **Alerts** | newest 3 Apex alerts, severity-coloured, no ack on the wrist | `alerts` |
| 7 | **Body & upkeep** | gear hours vs service limit · donation eligibility countdown · event countdown + taper window (v3 blocks; honest fallback today) | `gear`/`don`/`ev` |
| 8 | **Conditions** | today's temperature range, wind, rain (v3 block; water-sport wind flag ≥ 25 km/h) | `wx` |
| 9 | **Quick mood** | mood/energy/stress 1–5 → journal event in three taps | queued event |
| 10 | **Week** | 7-day plan, today highlighted | `/watch/week` |

Every screen has empty/offline/error states, shows the age of the data
("synced 3 h ago") and never crashes on missing keys. All user-visible
strings ship in **English and Italian** (`resources-ita/`, device language
matched at runtime, English fallback).

## Battery policy (hard requirements, spec 6.5)

| Rule | Implementation |
|---|---|
| No foreground polling | views fetch on open + SELECT only; no repeating timers in views |
| Background interval 60 min default, 60/120/240 in settings | repeating `Time.Duration` temporal event registered **in the foreground only** (`ApexApp.onStart` / `onSettingsChanged`), seconds-based (the old app passed 30·60·1000 "seconds" ≈ 20.8 days — fixed), clamped to the 5-min platform minimum |
| Active hours only | background work exits before any radio use outside `active_start_min`–`active_end_min` (default 05:00–23:30) and when `phoneConnected == false` |
| Backoff | after 3 consecutive failures the wake-ups skip all radio for 4× the interval until the next success |
| Revision check first | v3 transport: `GET /watch/v3/day?rev=` → `{"v":3,"rev":n,"same":true}` (~100 B) is the common case; capability probed at most daily, falling back to `/watch/day` |
| One request per wake-up | the background fetch makes exactly one request; the only exception is a pending event batch riding along with a successful fetch (never its own wake-up) |
| Watchdog | the OS 30 s background kill is the guaranteed exit; note `Toybox.Timer` is flagged `disableBackground` by the platform (verified in `api.mir`), so no in-process watchdog exists — a hung request costs the current slot only, the Duration registration keeps repeating |
| Event queue | ≤ 100 events in `Application.Storage`, oldest dropped with a visible warning; flushed **with** the next fetch or on app open, max 50 per POST, removed only after a 200 (idempotent client ids) |
| Rest timer exception | 1 Hz tick only on the rest-timer screen, stopped on `onHide`, hard-capped at 600 s (the platform has no View-level sleep callback — `onEnterSleep` is watch-face-only) |
| No animations | `WatchUi.requestUpdate()` only after data or input changes |
| No GPS/sensors/recording/audio/BLE | only `makeWebRequest` over HTTPS |
| Memory | measured with `--build-stats`: **Foreground 42.4 KB / 768 KB · Background 9.4 KB / 64 KB · Glance 11.1 KB / 64 KB** |

**Measurable target (owner):** 24 h drain with the app installed vs a day
without it on the same watch — goal ≤ ~1 percentage point. Report the real
number (spec 6.5.11).

## Data contract

The app works against the **current v2 backend** (read-only for this repo
folder) and is **additive-ready for the v3 contract**:

* v2: `GET /watch/day` → `{date, weekday, sessions[], supplements[],
  alerts{count,items}, journal_streak, gym_plan{...}, safety{verdict,
  intensity_ceiling, reasons[]}}`; `GET /watch/week`; `POST /watch/tokens`
  mints the device token pasted into settings.
* v3 (future, additive): `wo` / `sup` / `al` / `gym` / `verdict` / `gear` /
  `don` / `ev` / `wx` short-key blocks + `?rev=` + `POST /watch/events` —
  `ApexPayload` prefers the v3 block whenever present, ignores unknown keys,
  and the transport probes `/watch/v3/day` + `/watch/events` (probe throttled
  to once per 24 h) so the features light up without a watch-side update.

Events queued by the watch (set logs, feedback, supplements, mood) carry a
client id; while `POST /watch/events` does not exist server-side they stay
queued (the UI shows the pending count) and never block anything.

## Building (one command per device)

On a machine with the [Connect IQ SDK](https://developer.garmin.com/connect-iq/sdk/)
(≥ 6.x; verified against **9.2.0**):

```bash
# one-time: developer key (either form works; DER is what monkeyc loads here)
openssl genrsa -traditional -out developer_key.pem 2048
openssl rsa -outform DER -in developer_key.pem -out developer_key.der

# debug build
monkeyc -f monkey.jungle -y developer_key.der -w \
        -o bin/ApexDay-fenix7pro.prg -d fenix7pro

# release build (strips test/debug code)
monkeyc -f monkey.jungle -y developer_key.der -w -r \
        -o bin/ApexDay-fenix7pro.prg -d fenix7pro

# simulator run, then sideload: copy the .prg to GARMIN/Apps/ over USB
monkeydo bin/ApexDay-fenix7pro.prg fenix7pro
```

`monkey.jungle` pins the manifest only (SDK ≥ 6 grammar — the legacy
`project.sourcePath`/`resources` keys are rejected by the current parser);
`source/` and `resources/` are derived from the manifest location. Keep
`.prg` out of git (`.gitignore` included). To add devices: one
`<iq:product id="..."/>` line in `manifest.xml` + one build command.

## Unit tests (Run No Evil)

Pure-logic tests (payload accessors, verdict blocks v2+v3, event queue drop
policy, event ids, age/weekday/pad/clamp formatters, tokenizer, colors)
live in `source/ApexTests.mc`; the compiler strips `(:test)` code from
release builds automatically.

```bash
monkeyc -f monkey.jungle -y developer_key.der -w \
        -o bin/ApexDay-test.prg -d fenix7pro --unit-test
monkeydo bin/ApexDay-test.prg fenix7pro -t      # all tests
monkeydo bin/ApexDay-test.prg fenix7pro -t testEventQueueDropPolicy
```

## Simulator checklist (before the watch)

1. App launches from the launcher; menu shows all ten entries in the
   simulator language (switch EN/IT in the simulator settings).
2. Settings: set Server URL + token → Today fills; revoke the token
   server-side → next sync wipes the cache and shows "Token invalid".
3. Glance updates after a simulated temporal event (`File → Perform
   Interactive... background event` or the simulator's background menu).
4. Gym: select exercise → step reps/weight → LOG SET → rest timer counts
   down, vibrates at 0, SELECT skips; event appears in the queue (pending
   count in the footer).
5. Rotate/resolution sanity: round 260×260 — no clipped text at pad = w/16.

## What only the owner's fēnix 7 Pro can prove (honest limits)

* **This code was compiled here (SDK 9.2.0, `fenix7pro`, debug + release +
  `--unit-test` builds green; memory budgets measured) — but it was NOT run
  in a simulator (headless sandbox lacks the GTK/X stack) and NOT run on a
  real watch.** The simulator checklist above is the first gate.
* Glance refresh cadence on real hardware; `onBackgroundData` delivery when
  a temporal event lands while the app is closed.
* Real-world 24 h battery delta (spec target ≤ ~1 percentage point).
* `POST /watch/events` end-to-end body encoding (dictionary +
  `Content-Type: application/json` — the platform serializes it; the
  backend 422ing would be the signal to switch to form encoding).
* v3 endpoints do not exist yet in the backend: Workout status shows
  "unknown — needs Apex server v3", Body/Conditions show their fallbacks,
  events stay queued (visible count). All three light up automatically when
  the backend ships.
* Vibration pattern feel (`Attention.vibrate` is foreground-only by
  platform design — the rest timer runs in the foreground, so this is fine).

## Files

```
connectiq/
├── manifest.xml                 # v3 manifest: fenix7pro, eng+ita, minSdk 4.0.0
├── monkey.jungle                # SDK ≥6 grammar (manifest + nothing else)
├── resources/
│   ├── strings/strings.xml      # English (base)
│   ├── properties/properties.xml# server_url, token, refresh, active hours, units
│   ├── settings/settings.xml    # phone-side settings (list/numeric/boolean)
│   └── drawables/               # 40×40 launcher icon
├── resources-ita/strings/       # Italian overrides
└── source/
    ├── ApexApp.mc               # AppBase: entry, menu (Menu2), temporal registration,
    │                            # onBackgroundData, onSettingsChanged
    ├── ApexBg.mc                # (:background) temporal service: battery gates,
    │                            # fetch+persist, event flush, Background.exit
    ├── ApexNet.mc               # (:background) transport: v3 probe + rev, /watch/day,
    │                            # /watch/week, POST /watch/events, 401 handling
    ├── ApexStore.mc             # (:background) Storage: day/week cache, meta,
    │                            # event queue (max 100, oldest drop), 401 wipe
    ├── ApexPayload.mc           # (:background) defensive accessors, v2/v3 blocks,
    │                            # event constructors, client ids
    ├── ApexFormat.mc            # localization, colors, age/weight labels, wrap
    ├── ApexUi.mc                # ApexBaseView (line painter, footer) + ApexDelegate
    ├── ApexGlanceView.mc        # (:glance) verdict · workout · counts · age
    ├── ApexTodayView.mc         # verdict, workout card, supplements, gear/ev/wx
    ├── ApexWorkoutView.mc       # publish status (v3) / honest unknown (v2)
    ├── ApexGymView.mc           # plan list + Menu2 picker + exercise tracker
    │                            # + steppers + LOG SET + session state
    ├── ApexRestView.mc          # countdown, vibrate, skip; 1 Hz while visible only
    ├── ApexFeedbackView.mc      # RPE / soreness / injury → event (+ single flush)
    ├── ApexSupplementsView.mc   # checkbox adherence → events
    ├── ApexAlertsView.mc        # newest 3, severity colors
    ├── ApexBodyView.mc          # gear / donation / event+taper (v3 blocks)
    ├── ApexConditionsView.mc    # weather window (v3 block)
    ├── ApexMoodView.mc          # mood/energy/stress → event
    ├── ApexWeekView.mc          # 7-day plan, today highlighted
    └── ApexTests.mc             # Run No Evil unit tests
```

## Security

* Bearer device token from `POST /watch/tokens`; HTTPS only; the token is
  never logged and lives only in app properties.
* A 401/403 **wipes every cached value** (day, week, queued events, marks)
  and flags auth-error — a revoked token can never pose stale data as
  current.
* The token resolves to exactly one user server-side; there is no parameter
  to fetch anyone else's data.
* No health data in logs (the app logs nothing).

## Platform facts this app relies on (verified against SDK 9.2.0 docs/api.mir)

* `Time.Duration` is **seconds**; a Duration temporal registration repeats;
  5-min minimum; registration is foreground-only in this app.
* Background process: ≤ 30 s, `Background.exit` payload ≤ ~8 KB,
  `System.ServiceDelegate` (not `Application.`).
* Storage: values ≤ 8 KB (conservative), total ≤ 128 KB, background writes
  need CIQ 3.2+; every write is try/caught **and read-back verified**
  (known firmware `Storage.setValue` bug reports).
* `makeWebRequest`: `:responseType` (singular); responseCode 0/negative =
  transport error; JSON → `Lang.Dictionary`.
* `Attention.vibrate(Array<VibeProfile>)` — foreground only
  (`disableBackground`); `Toybox.Timer` also `disableBackground`.
* Menu2 selection arrives via `Menu2InputDelegate.onSelect(MenuItem)`
  (`getId()`), **not** the legacy `onMenuItem`.
* Monkey C has **no `String.split`** (tokenizer in `ApexFormat`) and no
  `RoundDisplay` API (round insets are derived from `dc.getWidth()`).
* Manifest v3: `minSdkVersion` only (no `minApiVersion`), `<iq:language>`
  (not `display-language`), no `<iq:glances>` element (glance wired via
  `getGlanceView()` + `minSdkVersion ≥ 4.0.0`).
* `project.sourcePath`/`project.resources` etc. are rejected by the current
  jungle parser — only `project.manifest` (+ optional typecheck) exist.
