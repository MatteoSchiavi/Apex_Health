# Reliability, planning recovery and multisport delivery

This implementation extends the existing canonical athlete, activity and training system. It does not deploy to the home server, resume automatic updates, activate a real athlete plan, send a Telegram message or grant AI consent.

| Phase | Delivered behavior |
| --- | --- |
| 0 | Before-downtime immutable release identity, successful publication, forward migration ancestry, actual schema, space and backup-key checks. Paused recovery is preserved. Owner-only host Telegram commands, confirmations, replay prevention, locks and transition notifications. |
| 1 | Whole-response JSON fences and Italian decimal claims normalized without weakening provenance. Bounded correction and useful safe fallback. Sync overlap, partial results, stale measurements, authentication episodes and persistent failures have distinct states and deduplicated alerts. Existing Remember Me renewal/revocation retained and verified. |
| 2 | Intent-based TXT/Markdown/PDF/paste import; encrypted original/review snapshot; review and selective fact acceptance; independent optional undated template; explicit date range and full calendar review; exact activation hash. Bulk availability and truthful save/conflict/navigation states. Today distinguishes context, draft, template, rest and recordings; mixed-sport distance is partitioned. |
| 3 | Canonical balanced/ordered/supporting focus, weekly allocation and seasonal priorities. Typed structured blocks including repeat groups and strength details, stable identities, encrypted drafts, immutable approved versions, protected/history rules, calendar duration approval and deterministic education. Imported blocks are visible and editable before activation. |
| 4 | Running overview, volume/consistency/adherence, pace and HR comparisons with quality gates, exact preceding 30-day long-run references, halves/splits/distributions, explicitly unit-qualified sensor dynamics and qualified critical-speed/route comparisons. |
| 5 | Cycling overview with power/HR modes, dense recorded power-duration curve, conservative NP/VI eligibility, distributions and descriptive efficiency retention. Accepted FTP assertion history is separate from protocol validation and legacy fractional estimates. W/kg requires owned recent eligible body mass. |
| 6 | Today/activity/workout links, explicit planned-versus-actual associations, optional fatigue/soreness/quality/modification/terrain journal detail, optimistic revision checks, conservative existing availability/recovery/pain rules, and no compulsory AI. |
| 7 | Recorded-date gridded weather provenance and unit checks; owned gear links, lifetime activity and maintenance history, configured intervals/defaults; portable approved workout JSON; granular exact-preview read-only sharing with expiry, revocation, encryption and source-erasure removal. |

## Validation

Tests use a dedicated synthetic TimescaleDB/pgvector database and Redis on ports 55433/56380. Production and the pre-existing local services were not used for destructive fixtures.

- Complete backend suite: **1,230 passed, 1 skipped**. AI budget fixtures are isolated, the exact schema inventory includes the five new tables, and the intentional public sharing route has an explicit missing-capability denial test.
- Final integrated athlete/import/workout/focus/sharing/equipment/weather/sport backend run: **265 passed**.
- Auth/Coach/sync/feature/registry regression run: **248 passed** (24 existing dependency deprecation warnings).
- Additional sensor-unit, source-erasure, FIT/COROS, export and Lab checks: **59 passed**.
- Integrated browser acceptance: **61 passed**, covering EN/IT profiles, mixed import, Today, journal, sharing, remember-me form, sync and sport views. Subsequent import/workout/sharing/sport checks: **31 passed**; final shared block editor/import verification: **21 passed**; equipment control browser journey: **1 passed**. Counts overlap and must not be summed.
- Complete browser run: **179 passed, 1 skipped**; the remaining short-screen sidebar case passed after its positioned-label containment fix (**1 targeted pass**). Provider names, canonical settings navigation and the general-document upload selector were checked against the new flows.
- Actual persistent Chromium with a synthetic HTTPS backend: Secure/HttpOnly remembered cookie survived close/reopen, authenticated `/me`, and disappeared on logout.
- Offline updater/Telegram tests: **81 passed**. Deterministic Coach evaluation: **26/26 passed**. PWA tests: **5 passed**.
- Frontend production build, EN/IT parity, Python compilation and diff whitespace checks passed. Updated source retains a single additive migration chain through **0029**.

## Scientific and operational limits

Missing recordings are not zero or proof of no training. Drift/decoupling need steady continuous eligible input; sparse power is not expanded into invented samples. Critical speed needs multiple explicitly qualified maximal performances. Route/climb comparisons need verified compatible segment/context identity. Unsupported grade-adjusted pace remains unavailable; efficiency retention is a descriptive proxy rather than a physiological diagnosis or injury prediction. User-confirmed FTP is a dated assertion, not a validated test protocol. Weather is a dated model estimate, with home-location and repeated-DST-hour limitations; no historical conditions or weather-corrected pace are invented.

Sharing recipients can save a copy. Revocation prevents future access but cannot erase that copy. Expired ciphertext is removed lazily during management/read; there is no scheduled purge. Portable JSON does not imply Garmin/device delivery or compatibility. Browser tests mock provider responses; production Garmin credentials/proxy behavior and actual Telegram delivery were not exercised.

## Host rollout

GitHub publication must finish successfully before an image is a release candidate. The host updater and Telegram controller are separate host scripts: an image update does not install them. Follow [AUTO_UPDATES.md](AUTO_UPDATES.md) and [TELEGRAM_CONTROL.md](TELEGRAM_CONTROL.md): update the host checkout, install the updater with `--install-only`, verify the candidate while paused, then install the private owner controller with the existing Docker context/project/compose settings. Recovery or timer resumption remains an explicit owner action after the server/image/schema checks pass. No automatic resumption is part of this change.
