# Data lifecycle and storage

The selected account export now includes optional athlete context, voluntary AI consent, budget reservations, encrypted-plan drafts as reviewed plaintext, training plans and workouts, explicit activity associations and session check-ins. Profile deletion leaves an empty revision tombstone and removes its managed target events. Consent withdrawal stops new processing and preserves history under the documented account/operator retention rules; it is separate from source/account erasure. See [AI_CONSENT.md](AI_CONSENT.md).

This note describes the current PostgreSQL/TimescaleDB schema and the cleanup
performed by scheduled maintenance. It records the alpha implementation; it
does not imply that cold storage or automated partition retention is deployed.

## Tables and time-series layout

| Data | Current storage | Indexes / access path | Retention |
| --- | --- | --- | --- |
| `activity_streams` | Ordinary PostgreSQL table, keyed by `(activity_id, t_offset_s)`. It is the largest expected table because providers commonly send one row per second. `t_offset_s` is relative to an activity, so it is not a suitable time partition key. | Primary key on `(activity_id, t_offset_s)` and `idx_streams_activity` on `activity_id`. | 400 days for activities marked `full` with canonical `avg_hr`; streams for incomplete activities remain available. The activity row is never removed by this task. |
| `sleep_sessions` | TimescaleDB hypertable on absolute `start_time`. | Primary key `(id, start_time)`; `idx_sleep_user_date` on `(user_id, local_date DESC)`. | No automated retention policy. |
| `hrv_readings` | TimescaleDB hypertable on absolute `timestamp`. | Primary key `(id, timestamp)`; `idx_hrv_user_ts` on `(user_id, timestamp DESC)`. | No automated retention policy. |
| `stress_readings` | TimescaleDB hypertable on absolute `timestamp`. | Primary key `(id, timestamp)`; `idx_stress_user_ts` on `(user_id, timestamp DESC)`. | No automated retention policy. |
| `daily_biometrics` | Ordinary daily-grain table, primary key `(user_id, date)`. | `idx_bio_user_date` on `(user_id, date DESC)`. | No automated retention policy. |
| `raw_ingest` | Ordinary table retaining provider payloads for replay and audit. | `idx_raw_ingest_unprocessed` and partial `idx_raw_unproc` cover unprocessed rows. There is no processed-row age index for the cleanup query. | Processed rows older than 180 days are deleted in batches of 500. Unprocessed rows are retained. |
| `token_usage`, `agent_tool_calls` | Ordinary AI accounting and tool history tables. | No `created_at` cleanup index is declared in the migrations. | Rows older than 400 days are deleted. |
| `alpha_events` | Ordinary table for a fixed event vocabulary and whitelisted, non-health-payload metadata. | `idx_alpha_events_time_event` begins with `created_at` and supports age cleanup; `idx_alpha_events_user_time` supports per-user history queries. | Rows older than 400 days are deleted with the nightly maintenance task. |
| `sessions` | Ordinary authentication table. | `idx_sessions_expires_at`, `idx_sessions_absolute_expires`, and `idx_sessions_token_hash`. | Expired sliding or absolute sessions are deleted nightly. |

The migrations create the three hypertables above, but do not configure
TimescaleDB compression, chunk retention, or continuous aggregates. The stream
table is intentionally not a hypertable: partitioning by an activity-relative
offset would not distribute samples by real time. If stream growth becomes a
measured problem, evaluate storing an absolute sample timestamp, compression,
or a compact per-activity representation before changing the schema.

## Scheduled cleanup

`maintenance.prune_streams` runs nightly at 04:30 UTC. It removes streams only
when their activity is older than 400 days, has `data_completeness = 'full'`,
and has canonical `avg_hr`. `full` by itself is not a safe signal because it
has a model default; the canonical heart-rate summary is the feature engine's
fallback for HR-based load when stream samples are absent. Rows without that
summary remain for future computation. All canonical activity rows remain.

The same task removes processed raw-ingest rows older than 180 days, then
removes `token_usage`, `agent_tool_calls` and `alpha_events` rows older than
400 days. Alpha events are fixed-vocabulary usage and workflow records; their
metadata excludes prompts and health payloads. The schema has no generic
`sync_log` table, so it is not part of retention. Stream and log deletes are
set-based; raw-ingest deletion is bounded to limit each delete batch.
PostgreSQL `CHECKPOINT` is not issued by the job because it is a server-wide,
privileged operation. Weekly `maintenance.vacuum_analyze` runs `VACUUM ANALYZE`
on the bulk and frequently queried tables through an autocommit connection.

The feature engine reads a 28-day activity window. The 400-day stream window
therefore leaves a substantial margin for its normal recomputation path; old
streams beyond that window may still matter for detailed activity presentation
or a future historical analysis, and those use cases should be checked before
shortening retention.

## Growth and future cold-storage candidates

At one sample per second, streams grow by approximately 3,600 rows for each
hour of recorded activity. For example, one hour of activity per day produces
about 1.31 million rows per user-year before retention; the 400-day window
holds about 1.44 million rows per such user. Actual size depends on activity
frequency and duration, and incomplete activities can exceed that window
because their streams are deliberately retained.

If alpha usage makes storage cost material, the first candidates to evaluate
for archival are old processed `raw_ingest` payloads, old activity streams
whose summaries have been retained, and expired AI tool/accounting history.
The three wellness hypertables may also be candidates after checking feature
lookback requirements. No table currently moves to object storage, and no
manual archival workflow is implemented. Any future move needs a restore path
and a verified boundary for the feature engine's historical lookbacks.

## Operational dependencies and gaps

The initial migration creates the `timescaledb` and `vector` extensions and
calls `create_hypertable`; provisioning must provide those extensions and a
database role allowed to install/use them. The maintenance role must own the
tables it vacuums. The raw-ingest and AI-log retention predicates currently
have no matching age indexes, so their cost should be checked against real
table sizes before alpha volume grows. There is no measured growth dashboard,
automated cold archive, or Timescale chunk-retention policy in the current
repository.
