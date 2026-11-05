# Garmin API: setup and actual coverage

Apex uses Garmin's official **Personal API** for the owner's own data. There is
one runtime authentication path: API key → Garmin access token. Password login,
MFA, shared server credentials and the former third-party dependency are removed.
Other athletes require a separately approved Garmin Business API integration;
friend accounts cannot attach a Personal API key.

## Connect

1. Open [Garmin Personal API settings](https://connect.garmin.com/app/settings/personalApiToken)
   in your own account and create a key under Garmin's current terms.
2. In Apex, sign in as owner → Settings → Devices → Garmin API. Paste the key
   into the password-style key field and save.
3. Apex verifies the key before replacing credentials and queues a sync. If the
   queue is unavailable, the connection remains saved; retry **Sync now**.

Keys and exchanged tokens are encrypted in the account's integration record.
They are excluded from responses, validation errors and status listings. There
is no SDK plaintext cache and no Garmin credential in `.env`. Access tokens renew
from the key; revoked/expired keys require reconnection. Legacy saved sessions
are shown as `reconnect_required`; their history and main-device selection remain.
Three connection attempts per account per hour are allowed. Concurrent connection
or sync returns a conflict. Disconnect removes local credentials, retains history;
revoke the key in Garmin settings to revoke provider access too.

## History and sync

The old 30-calendar-day pilot cap is removed. Activities are paged by stable
Garmin IDs. Initial wellness import walks backwards until the configured run of
empty days (default 10); **this is a stopping heuristic, not proof of complete
account history**. Checkpointing retains completed work. Incremental wellness
refresh includes the previous day to pick up corrections. Changing a key preserves
the existing watermark and does not automatically reimport every historical day.
New supplemental daily feeds follow the dates actually visited by that sync;
use an explicit range to populate them for already imported history or retry an
older partial period.

For a known inclusive wellness range, run in the backend environment:

```sh
uv run python tools/garmin_sync.py connect
uv run python tools/garmin_sync.py sync --from-date 2024-01-01
uv run python tools/garmin_sync.py status
```

The key uses a hidden prompt, never a command argument. `--from-date` scans forward
to today without stopping at empty gaps; choose the date deliberately as historical
imports can take hours. Activity history is paged separately. The CLI is an owner
maintenance tool and shares the scheduled sync advisory lock. A failed daily
feed is reported and pauses a backward history walk rather than being counted as
an empty day. A durable retry marker prevents another successful feed on the
same day from hiding the failure during resume. Its sync watermark is retained for retry; explicit ranges can repair older gaps. Provider permission/rate-limit
failures retain prior measurements and make the report partial.

## Data handling

| Data | Treatment |
|---|---|
| Activity summaries, supplied VO2max/power/cadence/manual flags | Normalized with stable source IDs; original fields retained |
| Original activity ZIP/FIT | Downloaded with the account bearer; stored with SHA-256 before parsing; CRC, session identity, bounds checked |
| FIT HR/power/cadence/speed/altitude/GPS samples, laps, recorded strength sets | Projected onto the existing owned activity; actual recorded values only; duplicate imports do not create another activity; missing channels are filled while existing non-null samples are preserved |
| Sleep stages/duration/score/respiration/SpO2, HRV, daily steps/resting HR/stress/Body Battery, weight/body fat | Existing normalized tables and source observations; invalid/missing measurements are not invented |
| Hydration, daily steps/stress arrays, food logs, Body Battery reports, all-day HR, SpO2 detail, fitness age, daily summaries v2, wellness activity summaries, weight goals, cycle detail, profile settings, HR zones | Fetched and retained as **source documents**; not all are projected into typed metrics or displayed in the UI |
| Activity detail and associated workout definitions | Retained as source documents; associated workouts are not completed individual sets or workout delivery |
| Stress time series, dedicated readiness/status/recovery feeds | Not exposed by the checked Personal API contract; not synthesized |
| Workout upload / watch delivery | Not implemented by this read-only integration |

Archive-only means durably stored under the owning account in `raw_ingest`, included
in the account data export and provider erasure. It does not mean the value has a
chart or is eligible as a normalized coaching observation. Unsupported or malformed
FITs remain pending for retry/review; multi-session FITs need explicit mapping.
Response and ZIP expansion limits prevent unbounded memory use; files are never
extracted to provider-controlled paths. Original archives are limited to 20 MiB;
JSON responses to 4 MiB.

The weight `/range` response uses **grams**, based on the dated October account
check, despite the shared schema describing kg; normalization converts once to kg.
Adjacent graph-context weights are excluded. The original response and unit marker
are retained. Timestamps are interpreted in UTC and attributed to the account's
calendar timezone where required. Main-device precedence and source identity remain.

## HTTP contract and verification

`POST /settings/integrations/garmin/connect` accepts `{"api_key":"…"}` and requires
an owner session plus CSRF. The former `/garmin/personal/connect` URL remains an
alias for installed clients, with identical security and behavior. Email/password
bodies are rejected without echoing input. Responses contain connection/queue
status and `auth_method: "personal_api_key"`, never keys or access tokens.

See [endpoint inventory](GARMIN_API_COVERAGE.md) and
[Garmin's Personal API FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/).
Mocked HTTP, public-contract and synthetic FIT tests verify implementation behavior.
The [October acceptance record](PERSONAL_API_ACCEPTANCE_2026_10.md) covers an older
30-day revision only. These new changes require a separate authorized real-account
sync and comparison on the intended deployment before claiming complete delivery.
