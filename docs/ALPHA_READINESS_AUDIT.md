# Apex Health: alpha readiness audit

Audited 2026-10-03 against `main` at `1cc885a`. Fixes and this report are on
`codex/alpha-readiness-audit`. This includes two stabilization passes, not a beta
release or a claim that live integrations work.

## Assessment

The biggest problem is that two separate products occupy one repository. The
documented backend has authentication, canonical data, ingestion workers, a
feature engine, and an AI tool harness. The newer web app implements a second,
much thinner version of those responsibilities and mixes its results with
fixtures. A UI restyle alone cannot make these workflows reliable.

There is useful work to retain. The Python suite passes **443 tests** against
isolated PostgreSQL with TimescaleDB/pgvector and Redis. The connected Vite
frontend builds. The current Next.js UI has reusable components and an explicit
design language. Stabilization should join those strengths into one product.

## What actually runs

| Entry point | UI | Data and services | Consequence |
|---|---|---|---|
| Root `bun run dev` | Next.js / React 19, `src/features/apex` | Prisma / SQLite, Node Garmin adapter, Z-AI SDK | Current redesigned UI; simulated account flow; several fixture-backed screens |
| `docker compose -f infra/docker-compose.yml up` | Vite / React 18, `frontend/` | FastAPI / PostgreSQL, Redis/Celery, Python connectors and agent | Builds and serves the UI the root README calls “legacy” |
| CI before this branch | No web build checks | Python tests only | Green CI did not validate the active Next.js app |

`docs/STACK.md` explicitly rejects Next.js and calls Vite official. The root
README calls Next.js active. `MASTER_SPEC.md` still defers the dashboard. These
documents describe different stages of the project; they cannot all serve as
current release instructions. No deployment was changed during this audit.

## Prioritized findings

“Fixed” describes this branch. “Open” remains a release blocker or follow-up.
Runtime observations used local, disposable demo data; no real account was
authenticated and no production database was accessed.

### P0: protection and data integrity

| ID | Finding and evidence | Status / required action |
|---|---|---|
| A01 | **Web authentication is simulated.** [LoginScreen](../src/features/apex/auth/LoginScreen.tsx) accepts a non-empty password through `mockLogin`; [JoinScreen](../src/features/apex/auth/JoinScreen.tsx) only calls `signIn`. [store.ts](../src/lib/apex/store.ts) persists `authed` in localStorage. | **Open.** Use real server sessions, login, invite redemption, logout/revocation and session restoration. A browser flag cannot establish identity. |
| A02 | **Root health APIs lack session authorization.** Unauthenticated requests to `/api/dashboard`, `/api/activities?limit=1`, `/api/integrations`, and `/api/garmin/sync` returned HTTP 200 and data. Handlers resolve the account from `GARMIN_EMAIL`, sometimes creating it during GET. There is no shared auth guard or CSRF layer in this stack. | **Open.** Derive identity from a validated session on every handler and scope every read/write to it. Test two users, direct-ID access, anonymous requests, and cookie/CSRF behavior. Reuse the backend's implementation. |
| A03 | **Device and account credentials are stored in plaintext in SQLite.** [schema.prisma](../prisma/schema.prisma) contains `User.password` and `Integration.garminPassword`. Several handlers copy `GARMIN_PASSWORD` into the account record. [connect](../src/app/api/garmin/connect/route.ts) saves the device password directly. | **Open.** Separate application identity from device identity, reuse password hashing and encrypted connector token storage, and rotate credentials exposed by any existing deployment. |
| A04 | **Normal startup automatically accepted destructive schema changes.** `scripts/setup.ts` and the `db:push` script used `--accept-data-loss`; setup hid failures and exited zero. | **Fixed.** No automatic data-loss acceptance; failed generation, push, or seed stops startup. A real disposable-schema experiment refused to drop a populated column and preserved the original row. Production still needs versioned migrations. |
| A05 | **Reading an empty medical history fabricated clinical records.** [labs route](../src/app/api/labs/route.ts) inserted three blood/donation panels with invented values and notes, marked `source: manual`. Gear and integration GETs also created sample objects. | **Fixed for new reads.** Empty GETs stay empty. Demo seed is explicitly gated by `APEX_DEMO_MODE=true`; it does not create fake connections. Existing sample records are not deleted automatically because the schema does not reliably distinguish them from real records. |
| A06 | **Test instructions could erase deployed data.** [conftest.py](../backend/tests/conftest.py) truncates the configured PostgreSQL schema and flushes configured Redis. INSTALL recommended running the suite in the deployed API container and incorrectly said it used separate databases. | **Fixed.** Tests refuse to run without `APEX_TEST_DATABASE_RESET=1`; CI sets it for disposable services. INSTALL now requires separate test stores. The refusal path was executed and exited 2 before tests ran. |

### P1: core workflows and truthful data

| ID | Finding and evidence | Status / required action |
|---|---|---|
| A07 | **Two databases and two business-logic implementations.** SQLite data is invisible to the Python feature engine, bot, watch endpoints, backups and workers. Docker ships a different UI than root development. | **Open.** Establish one canonical backend/database and one UI. Define and test the deployment topology before adding features. |
| A08 | **An activity list opens sample detail data.** [ActivityDetailPage](../src/features/apex/activities/ActivityDetailPage.tsx) calls `getActivityDetail` / `getActivityStreams` from [data.ts](../src/lib/apex/data.ts). Unknown real IDs fall back to the first fixture; routes, laps, weather and streams are generated. The Prisma activity model cannot store these detail structures. | **Fixed fabricated detail.** Detail now fetches the selected stored summary; IDs stay strings in list, overview, selection and comparison. Unknown/foreign records return 404; recordings not imported remain explicitly unavailable. GPS/streams/laps from the canonical backend are still pending convergence. |
| A09 | **Body signals and metric trends are fixtures.** [BiometricsPage](../src/features/apex/biometrics/BiometricsPage.tsx) and [MetricPage](../src/features/apex/biometrics/MetricPage.tsx) consume `metricCatalog`, `labMarkers` and generated trends. The overview uses a different source. | **Open.** Connect catalog, trend and lab views to the same canonical queries as the overview. Verify navigation preserves the value, date, units, source and completeness. |
| A10 | **Profile “Save” reports success without persistence.** [SettingsPage](../src/features/apex/settings/SettingsPage.tsx) only toasts on profile submission. AI tier, invitations and most device actions also use local state or cosmetic feedback. Units are persisted in the UI store while several views read fixture `me.units`. | **Open.** Wire server mutations and invalidate/refetch shared data. A saved profile must survive reload and a second device. Show unavailable actions honestly until connected. |
| A11 | **Coach data references and proposed actions are fabricated.** [messages route](../src/app/api/coach/chats/[id]/messages/route.ts) builds successful “tool calls” by matching words, without executing queries. Health readings are not loaded into the prompt. It creates preset workout/supplement drafts even after an LLM failure. | **Fixed false audits and preset drafts.** Conversation-only replies cite supplied context documents, never keyword-invented queries or protocols. Provider failure returns 502 with no successful reply/drafts persisted. Measured-data grounding, real tools and cost routing remain open in the root UI. |
| A12 | **Confirming a coach draft does not apply its action.** [draft route](../src/app/api/coach/chats/[id]/drafts/[draftId]/route.ts) changes JSON `status` only, without creating a plan or protocol. Terminal states can be changed again. | **Fixed false confirmation.** Confirmation returns 501 explaining that no plan/protocol was applied. Legacy drafts can be discarded idempotently; finalized drafts cannot be reversed and concurrent edits use compare-and-swap. Actual action application remains unavailable until canonical agent integration. |
| A13 | **Failed syncs returned success.** [sync adapter](../src/lib/garmin/sync.ts) swallowed per-day errors, and [sync API](../src/app/api/garmin/sync/route.ts) always returned `ok: true`, which Settings treated as success. | **Fixed.** Partial/provider failures remain in the report, return 502 with `ok: false`, mark an existing integration as error, and preserve its last successful timestamp. Empty valid provider results are still accepted. |
| A14 | **Garmin cached sessions used only the first two password characters and were global.** Disconnect could fall back to environment credentials. | **Fixed.** Cache is per-user and fingerprints full credentials. Paused integration blocks fallback and cached sessions. Remaining work: persistent tokens, expiry/re-auth handling, MFA, rate limits and queued jobs. |
| A15 | **Node ingestion is incomplete.** Only 50 activities, 14 sleep days and 7 biometric days are fetched. `hrvReadings` is never incremented. Power/training-load fields are not saved; no raw-first store, full backfill, deduplication across sources or background schedule exists in this adapter. | **Open.** Use the existing Python connector rather than extending a second ingestion engine. Add job progress, resumable checkpoints and recorded-provider integration tests. |
| A16 | **Provider activity IDs are global primary keys.** The Node upsert uses only external activity ID; its update does not validate or change `userId`. | **Open.** Introduce provider/user-scoped identity and canonical source links before multi-user ingestion. Migrate existing IDs without orphaning references. |
| A17 | **ACWR compared weekly total to daily average.** With identical daily loads, both web endpoints returned ratio 7 instead of 1. The Python engine uses `acute7 / (chronic28 / 4)`. | **Fixed.** A shared helper gives the overview and load chart the same weekly units. Golden examples test steady workload, spikes, rest days and absent history. |
| A18 | **Higher strain increased readiness.** Dashboard added the penalty instead of subtracting it. Latest historic sleep could be presented as today's readiness and “full” data. | **Fixed for these defects.** Subtract strain; only today's sleep can produce today's sleep-based readiness; completeness requires actual inputs. This web formula is still a heuristic separate from the versioned backend engine and should be replaced during convergence. |
| A19 | **Sync status and alerts contradict the real data.** Settings and sidebar use fixture `devices`; NotificationsBell uses fixture alerts. The sidebar says recently synced even without credentials. [use-sync-status](../src/hooks/use-sync-status.ts) and the mini-service generate simulated events. | **Open.** Display connection, job outcome and data freshness from the canonical backend. Do not confuse connection state with successful synchronization. |
| A20 | **Settings/security copy overstates capability.** It claims per-friend isolation even though root accounts are not real. The welcome screen advertises automatic multi-provider syncs and labels the product v1.0. | **Open.** Align claims and feature visibility with connected, tested capabilities. Explicitly label sample data. |

### P2: operations, performance, design and maintenance

| ID | Finding and evidence | Status / required action |
|---|---|---|
| A21 | **Fresh root build and typecheck were unreliable.** Fonts were downloaded during build; local build failed on font-fetch TLS. Root TypeScript scanned unrelated Vite, example and mini-service projects, producing missing `socket.io` errors. | **Fixed.** Use the already bundled fonts and scope root typechecking to its own code/tests/config. Root production build, typecheck and lint now pass. |
| A22 | **CI did not exercise root web work.** Only pytest ran. | **Fixed.** Add frozen Bun install, fresh setup, web tests, typecheck, lint and production build. Hosted workflow results must still be checked after pushing. |
| A23 | **Activities “pagination” loads the entire window.** [activities API](../src/app/api/activities/route.ts) fetches full rows for current and previous windows and slices in memory. `days` is not bounded and malformed numeric parameters are not rejected. | **Fixed.** Validated bounded filters, database skip/take, stable tie-breaking, transactionally consistent counts and aggregates. Weekly volume aggregates by day/discipline and shares the selected calendar window. Week drill-down queries all matching records, including those outside the first page. |
| A24 | **Historical windows are not always calendar windows.** Dashboard takes last N records, not necessarily last N days. Activity filtering mixes server-local dates with UTC strings; Node sync converts server-local midnight with `toISOString`. Sleep regularity uses UTC minutes rather than the user's local time. | **Partially fixed.** Activities use account-local calendar labels and equal bounded periods, exclude future records, and group by recorded local date. DST/year-boundary examples pass. Dashboard sparse baselines, sleep timezone semantics and Node ingestion dates still need correction. |
| A25 | **Document pipeline is tied to prototype infrastructure.** Z-AI configuration is not represented by the backend's configured LLM providers. PDF parsing passes a Uint8Array directly to a constructor documented as accepting `{ data }`; errors are swallowed before raw-PDF fallback. Upload location depends on `process.cwd()`, which changes in standalone production. | **Open; extraction not exercised live.** Test digital/scanned PDFs, bound file/parser/provider work, validate extracted schemas, configure an absolute persistent upload directory and use an authenticated download route. |
| A26 | **Mobile overview overflowed by 32px at 390px width.** Browser geometry traced it to an invisible centered ChartInfoBadge tooltip extending beyond the viewport. | **Fixed.** Tooltip aligns to the trigger's right edge. Browser verification covers desktop and 390px mobile. |
| A27 | **Low workload was labeled “Elevated,” and ACWR copy implied a definitive injury prediction.** Seen in the overview at ACWR 0.00. | **Fixed in Overview.** Low load is labeled correctly; high ratio says “High load”; help text describes comparable units and contextual interpretation. Other metric explanations need the same review. |
| A28 | **Design rules are written but not enforced.** Stock component scaffolding and page-specific charts coexist; uppercase labels, small text and arbitrary metric formatting remain. Activities shows raw second/meter deltas such as `−96406` without units. Settings is a very long mixed-purpose page. | **Partially fixed.** Activity deltas show durations/distances with units and neutral interpretation; list/detail/comparison honor the saved unit preference. Rows show recorded titles. Comparison no longer labels higher training load or lower HR universally better. Broader UI/accessibility work remains open. |
| A29 | **Large components and stale compatibility code complicate changes.** TrainingPage has 2,617 lines, kit 1,305. `gearDb.ts` still uses raw SQL to work around a previously cached Prisma client. Several effects suppress failures. | **Open.** Split by real feature responsibilities; regenerate clients normally; remove obsolete workarounds and unify API error handling. |
| A30 | **Unused infrastructure/dependency candidates remain.** `useSyncStatus` has no current caller; its simulator mini-service is not part of the normal deployment. No active source imports were found for `next-auth`, `next-intl`, the DnD packages, MDX editor, React Query or TanStack Table. Large template component sets remain. | **Open.** Confirm with import/bundle analysis, then remove in a separate cleanup. Installed-but-unused dependencies are not necessarily shipped in the browser bundle. Keep the connected Vite app until replacement parity is demonstrated. |
| A31 | **Verbose database logging and missing Python ignore rules.** Root Prisma logged every query; normal pytest/collection created untracked cache artifacts. | **Fixed.** Log warnings/errors and ignore Python virtualenv/cache output. Raw API error serialization and credential redaction still need a broader review. |

## Second-pass findings and fixes

| ID | Confirmed defect | Change and evidence |
|---|---|---|
| A32 | Backend `/me` ignored explicit `null`, making DOB, sex and height impossible to clear. | **Fixed.** Distinguish omitted fields from explicit clearing. Authenticated update/read regression covers both behaviors. Root Settings still has a cosmetic save and is not connected to this endpoint. |
| A33 | Backend stream decimation used floor division. A 199-point recording with `max_points=100` returned 199 points; an appended endpoint could exceed the budget again. | **Fixed.** Bounded evenly spaced sampling retains endpoints and aligned columns. Tests cover short/exact/over-budget recordings and sparse fields. The query still reads all stored stream rows before sampling; database-side sampling remains a performance opportunity. |
| A34 | SPA fallback used a textual path prefix for containment. A sibling such as `dist-private` and symlinks into it could expose files outside `dist`. | **Fixed.** Resolve paths and require actual ancestry. ASGI regressions request encoded traversal and an escaping symlink; neither returns the private fixture. |
| A35 | Slow activity/filter requests could overwrite later selections. Weekly chart ignored the selected period, retained stale data on failure, and week selection filtered only the currently loaded page. | **Fixed.** Abort obsolete requests, guard response updates, clear failed supporting charts, share range filters and paginate a selected week in the database. Selected filter chips remain removable even with zero matching rows. |
| A36 | Coach prompt treated instructions as an assistant reply and included the new user message twice. Failed provider work could appear as a persisted successful conversation. | **Fixed.** System role, bounded history/input, one pending message, atomic conversation persistence after a completed reply, explicit failures without fabricated drafts or provider-secret details. Provider timeouts/budgets and full agent integration remain open. |

The activity screen now has a smaller recorded-summary layout composed from the
existing Apex kit. Generated detail charts, weather, gear provenance, guessed
heart-rate zones and their unused generators were removed (over 1,000 lines).
CSV and comparison explicitly operate on loaded activities. This does not remove
real canonical backend recordings or change stored activity IDs.

## Product and UI direction

Keep Apex's DNA: private health/performance control center; personal baselines;
raw-first, reproducible measurements; multisport training; useful gym/watch
actions; labs handled as actual clinical records; AI proposals that remain
drafts until confirmed. Keep the restrained neutral surfaces, warm-orange
actions, readable tabular numbers, and coherent light/dark themes in
`ui-language/RULES.md`.

The design needs clearer decisions and truthful states more than another
palette swap:

1. **Today:** one answer using dated readings, then the next real action.
   First sync, syncing, incomplete data, stale data and errors each get a
   clear state. Missing data should direct the user to connect or retry.
2. **Training and activities:** consistent period filters; readable totals
   and deltas with units; actual selected activity details; gym logging that
   is usable on a phone. Secondary detail belongs behind drill-down.
3. **Recovery/body signals:** personal baseline band, value/date/source and
   confidence accessible without clutter. Do not show generated charts as
   measured data or generic ranges as personalized certainty.
4. **Labs/documents:** review an extracted draft against the source document,
   validate units/reference ranges, then explicitly save. Empty means empty.
5. **Coach:** real cited data, resumable conversations, understandable cost
   controls, and confirmed actions visible in the schedule afterwards.
6. **Settings:** separate account, devices, appearance and owner controls;
   meaningful save/error feedback; one device status per source everywhere.

Use a single route/navigation contract: browser Back, refresh and direct links
must preserve the selected screen and record. Root currently switches every
page under `/` in Zustand, so basic browser navigation is absent. Keep mobile
primary navigation short, with secondary sections in a drawer.

The [Settings screenshot](audit/screenshots/settings-audit.png) records the
contradictory device states and page density. The mobile screenshots document
the [overflow before the fix](audit/screenshots/mobile-overflow-before.png)
and [the corrected overview](audit/screenshots/mobile-overflow-after.png).

## Route out of alpha

Recommended target: **one React UI → same-origin FastAPI API → PostgreSQL**, with
Redis/Celery for ingestion and scheduled work. The Next.js visual work can be
retained while it is connected to that API; the Prisma business-logic copy
should not become a second source of truth. The actual deployed entry point
and the owner's most important workflows still need confirmation. No stack or
data migration is performed by this branch.

| Order | Deliverable | Evidence required to call it complete |
|---|---|---|
| 1 | Freeze the canonical runtime and protect access | One documented launch path; real owner and invited friend login; anonymous APIs denied; per-user isolation; real logout; CSRF checks; secrets encrypted |
| 2 | Reliable ingestion and migration | Inventory/export both stores; separate sample records from real data; fixture-tested full backfill and incremental sync; MFA/token refresh; progress/retry/error states; preserved raw payloads; no duplicates after rerun/restart |
| 3 | Complete core vertical flows | Overview → metric/activity detail uses the same dated data; profile saves persist; lab review/save and gear maintenance work; gym set logging survives reload; every action reaches the canonical service |
| 4 | Connect the real coach | Measured-data tool calls and sources; truthful provider failures; capped cost/time; persisted chats; draft application is transactional and idempotent; no preset medical protocols |
| 5 | UI pass over working flows | Apply the design direction above at desktop/mobile; readable dates/units; keyboard/focus/labels; honest loading/empty/stale/error states; direct-link and Back behavior; remove sample claims and unavailable controls |
| 6 | Prove release operations | Clean install and upgrade on the target server; restart during a sync; encrypted backup and restore drill; smoke/E2E tests for both accounts; retained job errors; one release version and accurate installation guide |

Do not delete one frontend, rewrite the database, or erase suspected fixture
records before the export/migration and parity criteria are demonstrated.

## Verification of this branch

- Python backend after the second pass: **443 passed**, 93 warnings, against
  disposable Docker services. The first pass had 436 tests; seven backend regressions were added in the second pass. Warnings are
  mostly framework/test deprecations and should be reviewed separately.
- Web regressions: **24 existing cases**, **23 activity API cases**, and
  **nine coach safety cases** pass. Activity cases use an isolated real SQLite
  store; coach/provider cases use fixtures in isolated processes. Also covers ACWR,
  readiness, stale sleep, complete/partial/failed sync, cache isolation,
  disconnect, empty labs/gear/integrations and setup failure paths.
- Both frontends build. Root TypeScript and ESLint pass. The final root build
  uses local fonts and produces the standalone server.
- Actual fresh setup created one demo account, 30 activities, 13 sleep sessions,
  seven biometric records, and zero integrations/labs/gear. A destructive
  schema push exited 1 and retained the populated column.
- Backend tests without the reset flag exited 2 before running tests.
- Production-server browser checks: welcome/login, overview, activities,
  settings and mobile overview from the first pass. Second pass: selected
  recorded detail, comparison with imperial units, missing-detail error/retry,
  mobile detail at 390px without overflow, and a deliberately delayed 90-day
  response unable to overwrite a newer 12-month selection. No page errors.
- No live Garmin, LLM, Telegram, watch or other provider account was tested.
  The subsequent backend pass verified an isolated Docker deployment, a
  populated schema upgrade and actual TimescaleDB restoration (below).
  Migration of real user data and restoration on the target host remain unverified.

## Remaining limits of the fixes

This branch removes specific unsafe or misleading behavior; it does **not**
make the root web app authenticated or production-ready. Existing seeded data,
fixture-backed metric/social screens, duplicated feature formulas and
plaintext connector storage remain. Activity detail is truthful but summary-only;
coach action application is explicitly unavailable. The bounded Node sync
adapter remains pending convergence. Database error logs and API error bodies still
need proper redaction. The roadmap above is the remaining release work.

## Backend release pass — 2026-10-03

Canonical release scope is the FastAPI/PostgreSQL/Celery platform. The root
Next.js prototype retains the limitations listed above; UI convergence is
the next phase after backend production acceptance.

| ID | Confirmed issue | Backend resolution |
|---|---|---|
| A37 | Client-selected CSRF token; cross-origin bootstrap and logout gaps | Session-bound signed tokens, fresh login tokens, Origin checks, logout protection |
| A38 | Other sessions survive password changes; cookie and server sliding expiry diverge | Revoke other sessions; serialize credential changes; renew cookie and expiry within lifetime cap |
| A39 | Unknown-email login bypasses limiting; failure keys persist forever and clock collisions undercount | Uniform Argon2 verification; atomic distinct failures with expiry and hashed identifiers |
| A40 | Provider IDs and source-link lookups have global ownership | Migration 0009 backfills account IDs; account uniqueness and ownership FK; all connector/CSV lookups scoped |
| A41 | Sync failures look successful; SQL errors poison bookkeeping; overlap and checkpoint gaps | Per-account retry jobs, advisory locks, rollback before escalation, live checkpoints and honest partial/failure outcomes |
| A42 | Sync endpoint blocks the event loop, then may start a duplicate inline run | 202 queued response and account-scoped status; queue failure is 503 |
| A43 | Asyncpg connections persist across Celery's closed event loops | Dispose pooled connections before each task loop ends; repeated real jobs verified |
| A44 | API starts before migrations; port binds publicly; queues and backup mounts lack recovery guarantees | Migration/health ordering, loopback binding, persistent Redis AOF, bounded worker concurrency and backup permissions/path |
| A45 | Restore drill adds fake clinical data and drops a fixed-name database | Read-only source, unique scratch targets, checksums and unconditional cleanup |
| A46 | Dump credentials appear in arguments; backup memory grows with database; failed restore can partially apply | libpq environment, streaming authenticated archives, legacy support, transactional restore and interruption rollback |
| A47 | Chat POST accesses a request field that does not exist | Define and validate session_id; test start/resume through HTTP |
| A48 | Explicit model tier bypasses a friend's AI access cap | Apply entitlement even with an explicit tier |
| A49 | CSV guesses units by numeric size; UTC offset can become NULL; malformed values crash | Header units, finite/range validation, bounded upload read and safe malformed-row handling |
| A50 | New web conversations reuse the bot's recent idle-window session | Explicit fresh web session, bounded replay for requested resume |
| A51 | Concurrent draft transitions race; replacement end date includes the new start date | Row locks and serialized same-account replacement; end previous protocol the day before |

Validation: **480 backend tests passed**, plus authenticated-route probing
with matching CSRF headers. Final production image and Compose startup
passed. Deployed HTTP smoke, four Celery round trips, pending-job recovery
across queue/worker restart, authenticated API restart, actual encrypted
TimescaleDB restore (58-table checksum match), and failed/interrupted
restore rollback passed. No real vendor account or production host was used.

See [BACKEND_RELEASE.md](BACKEND_RELEASE.md) for upgrade instructions, repeatable
checks and the live-account/TLS/target-host acceptance boundary.
