# UI and integration refinements

The overview starts with recorded HRV, resting heart rate, sleep duration, SpO₂, respiration and VO₂ max, with 7-day, 4-week and 6-month views. Body fat, floors and hydration are shown when supplied. Quick links lead to Calendar, Training, Labs, Coach and Devices. Apex estimates remain available in a folded section with their existing limitations.

HRV/RMSSD, resting heart rate, SpO₂ and respiration use a personal empirical range from the same provider, device and measurement context: the preceding 28 calendar days, at least 14 recorded days, excluding the assessed reading. Device changes restart calibration. These are personal distribution bands, not diagnostic thresholds. A higher VO₂ max or recovery score gets a positive directional cue; higher training load has no automatic good/bad color. Count, volume and body measurements retain precise neutral values. Missing data is shown as missing.

The collapsed sidebar retains the Apex mark. Sleep stage charts share muted, distinct stage colors. Hour-valued durations use `H:MMh`. Remember me renews session and CSRF cookies for 30 days of inactivity, at most once daily, with a 90-day absolute server-session cap; existing remembered rows retain their original cap. Ordinary login uses browser-session cookies and the existing 12-hour inactivity limit. Logout revokes the server session and clears both cookies.

## Sport details

Strength sessions show recorded exercises, expandable per-set repetitions and weights, session totals, weighted volume in the selected kg/lb units, known-volume coverage, a selectable muscle-group diagram and previous-session comparisons. Session ownership and time windows determine the associated logs. Imported sessions without recorded sets show a clear empty state. Repetition/volume deltas compare actual recorded sessions of the same exercise; partial weighted volume is not treated as a complete progression value.

Running uses pace; cycling uses speed and recorded cadence/power zones. Sailing uses nautical miles and knots and omits elevation, including timeline/lap metadata. Skiing shows recorded runs when a provider explicitly supplies them and maximum recorded speed. No skiing flow metric was implemented or researched. HIIT shows the available workout measures without requiring a GPS map. Source payloads that lack exercise detail, cadence, zones or run counts cannot produce those fields.

## Device connections

- [WHOOP setup](WHOOP_SETUP.md): add client ID, secret and the exact public HTTPS callback URL to `.env`; authorize the account in Devices. Live authorization requires the operator's credentials and provider approval.
- [COROS MCP](COROS_MCP.md): configure the real server URL, read-only activity tool and arguments, then connect each account's token in Devices. No particular external MCP server has been verified.
- [Apple Health](APPLE_HEALTH.md): manually upload Apple Health's `export.zip` through Settings → Data health. Automatic HealthKit synchronization needs a native iOS companion and is not part of this server implementation.

The former interactive Telegram connector, routes, tasks and Compose service were removed. Historical tables remain to preserve existing records. A disabled, network-free polling entrypoint supports older Compose snapshots during upgrades; the updater stops and removes only its own project's legacy bot container. Optional outbound owner notifications now run through the API and Celery worker, using separate `OWNER_TELEGRAM_*` settings; see [OWNER_ADMIN.md](OWNER_ADMIN.md).
