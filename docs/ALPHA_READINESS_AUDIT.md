# Apex Health: alpha readiness audit

Audited 2026-10-03 against `main` at `1cc885a`. Fixes and this report are on
`codex/alpha-readiness-audit`. This is a first stabilization pass, not a beta
release or a claim that live integrations work.

## Assessment

The biggest problem is that two separate products occupy one repository. The
documented backend has authentication, canonical data, ingestion workers, a
feature engine, and an AI tool harness. The newer web app implements a second,
much thinner version of those responsibilities and mixes its results with
fixtures. A UI restyle alone cannot make these workflows reliable.

There is useful work to retain. The Python suite passes **436 tests** against
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
| A08 | **An activity list opens sample detail data.** [ActivityDetailPage](../src/features/apex/activities/ActivityDetailPage.tsx) calls `getActivityDetail` / `getActivityStreams` from [data.ts](../src/lib/apex/data.ts). Unknown real IDs fall back to the first fixture; routes, laps, weather and streams are generated. The Prisma activity model cannot store these detail structures. | **Open.** Fetch the selected canonical activity and its recorded streams/laps. Missing streams are an empty state, not generated measurements. Preserve IDs as strings where appropriate. |
| A09 | **Body signals and metric trends are fixtures.** [BiometricsPage](../src/features/apex/biometrics/BiometricsPage.tsx) and [MetricPage](../src/features/apex/biometrics/MetricPage.tsx) consume `metricCatalog`, `labMarkers` and generated trends. The overview uses a different source. | **Open.** Connect catalog, trend and lab views to the same canonical queries as the overview. Verify navigation preserves the value, date, units, source and completeness. |
| A10 | **Profile “Save” reports success without persistence.** [SettingsPage](../src/features/apex/settings/SettingsPage.tsx) only toasts on profile submission. AI tier, invitations and most device actions also use local state or cosmetic feedback. Units are persisted in the UI store while several views read fixture `me.units`. | **Open.** Wire server mutations and invalidate/refetch shared data. A saved profile must survive reload and a second device. Show unavailable actions honestly until connected. |
| A11 | **Coach data references and proposed actions are fabricated.** [messages route](../src/app/api/coach/chats/[id]/messages/route.ts) builds successful “tool calls” by matching words, without executing queries. Health readings are not loaded into the prompt. It creates preset workout/supplement drafts even after an LLM failure. | **Open.** Use the Python agent/tool registry, real query results, cost routing and failure handling. Remove keyword-generated supplement protocols and false tool audits. |
| A12 | **Confirming a coach draft does not apply its action.** [draft route](../src/app/api/coach/chats/[id]/drafts/[draftId]/route.ts) changes JSON `status` only, without creating a plan or protocol. Terminal states can be changed again. | **Open.** Transactional, idempotent application of the actual proposed payload, with a one-way state transition and ownership validation. |
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
| A23 | **Activities “pagination” loads the entire window.** [activities API](../src/app/api/activities/route.ts) fetches full rows for current and previous windows and slices in memory. `days` is not bounded and malformed numeric parameters are not rejected. | **Open.** Database pagination and aggregates, bounded ranges, input schemas. Use shared query caching, cancellation and invalidation for views. |
| A24 | **Historical windows are not always calendar windows.** Dashboard takes last N records, not necessarily last N days. Activity filtering mixes server-local dates with UTC strings; Node sync converts server-local midnight with `toISOString`. Sleep regularity uses UTC minutes rather than the user's local time. | **Open.** One timezone-aware contract, local calendar windows, UTC instants for timestamps, DST and sparse-data tests. |
| A25 | **Document pipeline is tied to prototype infrastructure.** Z-AI configuration is not represented by the backend's configured LLM providers. PDF parsing passes a Uint8Array directly to a constructor documented as accepting `{ data }`; errors are swallowed before raw-PDF fallback. Upload location depends on `process.cwd()`, which changes in standalone production. | **Open; extraction not exercised live.** Test digital/scanned PDFs, bound file/parser/provider work, validate extracted schemas, configure an absolute persistent upload directory and use an authenticated download route. |
| A26 | **Mobile overview overflowed by 32px at 390px width.** Browser geometry traced it to an invisible centered ChartInfoBadge tooltip extending beyond the viewport. | **Fixed.** Tooltip aligns to the trigger's right edge. Browser verification covers desktop and 390px mobile. |
| A27 | **Low workload was labeled “Elevated,” and ACWR copy implied a definitive injury prediction.** Seen in the overview at ACWR 0.00. | **Fixed in Overview.** Low load is labeled correctly; high ratio says “High load”; help text describes comparable units and contextual interpretation. Other metric explanations need the same review. |
| A28 | **Design rules are written but not enforced.** Stock component scaffolding and page-specific charts coexist; uppercase labels, small text and arbitrary metric formatting remain. Activities shows raw second/meter deltas such as `−96406` without units. Settings is a very long mixed-purpose page. | **Open.** A small real design system with tested formatting, accessibility and responsive states; automated token/contrast/typography checks. See the design direction below. |
| A29 | **Large components and stale compatibility code complicate changes.** TrainingPage has 2,617 lines, kit 1,305. `gearDb.ts` still uses raw SQL to work around a previously cached Prisma client. Several effects suppress failures. | **Open.** Split by real feature responsibilities; regenerate clients normally; remove obsolete workarounds and unify API error handling. |
| A30 | **Unused infrastructure/dependency candidates remain.** `useSyncStatus` has no current caller; its simulator mini-service is not part of the normal deployment. No active source imports were found for `next-auth`, `next-intl`, the DnD packages, MDX editor, React Query or TanStack Table. Large template component sets remain. | **Open.** Confirm with import/bundle analysis, then remove in a separate cleanup. Installed-but-unused dependencies are not necessarily shipped in the browser bundle. Keep the connected Vite app until replacement parity is demonstrated. |
| A31 | **Verbose database logging and missing Python ignore rules.** Root Prisma logged every query; normal pytest/collection created untracked cache artifacts. | **Fixed.** Log warnings/errors and ignore Python virtualenv/cache output. Raw API error serialization and credential redaction still need a broader review. |

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

- Python backend: **436 passed**, 93 warnings, both before changes and after the
  explicit test-reset guard, against disposable Docker services. Warnings are
  mostly framework/test deprecations and should be reviewed separately.
- Web regressions: **24 passed**, with mocked provider calls. Covers ACWR,
  readiness, stale sleep, complete/partial/failed sync, cache isolation,
  disconnect, empty labs/gear/integrations and setup failure paths.
- Both frontends build. Root TypeScript and ESLint pass. The final root build
  uses local fonts and produces the standalone server.
- Actual fresh setup created one demo account, 30 activities, 13 sleep sessions,
  seven biometric records, and zero integrations/labs/gear. A destructive
  schema push exited 1 and retained the populated column.
- Backend tests without the reset flag exited 2 before running tests.
- Production-server browser checks: welcome/login, overview, activities,
  settings and mobile overview; no page errors in those visited flows.
- No live Garmin, LLM, Telegram, watch or other provider account was tested.
  Full application Docker deployment, real data migration and target-host
  restore remain unverified. Green fixture tests do not establish these.

## Remaining limits of the fixes

This branch removes specific unsafe or misleading behavior; it does **not**
make the root web app authenticated or production-ready. Existing seeded data,
fixture-backed detail/metric/social screens, duplicated feature formulas and
plaintext connector storage remain. It also retains the bounded Node sync
adapter pending convergence. Database error logs and API error bodies still
need proper redaction. The roadmap above is the remaining release work.
