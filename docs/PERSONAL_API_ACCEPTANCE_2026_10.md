# Personal API and first-use follow-up — 25 October 2026

This follow-up builds on PR #5's daily training repairs. It adds the official
Garmin Personal API owner pilot and two source-observed onboarding fixes.
The production site still reported `5d516d4` during this assessment.

## Evidence and scope

- An authorized read-only Apex session confirmed saved athlete context, no
  active workout for the current day, and undated plan drafts. This supports
  the need for explicit date review and activation already implemented in PR #5.
- The supplied Personal API key authenticated successfully. Activity, sleep,
  HRV and daily-summary endpoints returned real responses. Their compatible
  fields were checked against the canonical normalizers in memory.
- Live testing found the documented weight `/all` endpoint returned 400. The
  `/range` endpoint used by Garmin's official SDK returned the expected shape.
  The connector now uses that route and only counts the requested day's
  measurements, excluding adjacent graph-context weights.
- Local targeted backend checks passed 73 tests, covering encryption handoff,
  owner authorization, CSRF, isolation, token renewal, safe errors, unit mapping,
  bounded imports and preservation of history when changing connection.
- A real 30-day import completed successfully in a separate local database:
  98 raw payloads normalized, zero pending normalization errors. The complete
  browser/release suites remain additional gates; consult the final PR checks.
- That import exposed repeated sport-fallback notices on every daily
  checkpoint. Reports now retain one cumulative notice. Unrecognized provider
  sports remain visibly unknown, rather than being reclassified as gym work.

Private keys, account payloads and session files are outside Git. These checks
do not establish a production installation or an exhaustive security audit.

## Implemented behavior

The owner can verify a Personal API key in Settings → Devices, replacing a
previous Garmin connection without deleting history or changing the main
device. Only verified credentials replace the old connection. Keys and tokens
use existing account-scoped encryption, with no SDK plaintext cache. Queue
failure leaves the connection saved and directs the user to Sync now.

Imports cover the most recent 30 calendar days as an application pilot limit,
not a statement about Garmin retention. Stable Garmin IDs preserve deduplication.
Unsupported feeds are explicit: detailed activity samples, individual gym sets,
stress time series, training readiness/status and recovery time. Existing
measurements remain available. Personal capability flags are reconciled when
switching back to the old transport. See [setup and coverage](GARMIN_PERSONAL_API.md).

The initial checklist now uses saved athlete context instead of account name
and timezone. Deleting athlete context requires an explicit confirmation;
cancel and failure preserve saved context and unsaved edits.

## Remaining work

1. Require all checks on the final commit, including production-stack API,
   worker and encrypted backup/restore checks.
2. Obtain actual host updater status, backup/migration preflight and installed
   version. Source changes and registry publishing do not install a release.
3. Verify the installed UI with the owner's intended plan, useful grounded
   live Coach output, completed sync and an actual workout on a phone.
4. Complete a fresh first-use journey through the actual UI/backend together.
   Browser automation access was unavailable for exploratory live navigation
   in this session; API reads and automated contract tests are distinct evidence.
5. Garmin Business enrollment, multiple-user authorization and sending workouts
   to a physical watch remain separate work; Personal API is an owner pilot.
