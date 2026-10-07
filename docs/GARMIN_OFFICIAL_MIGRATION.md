# Garmin official API migration boundary

## Current architecture

The existing Garmin path is an unofficial Garmin Connect integration. The
account connection stores encrypted credentials/session tokens on the
account's integration row. The worker decrypts that account's credentials,
constructs `LiveGarminClient`, runs the existing sync pipeline and persists
refreshed session tokens. A missing account credential fails; the worker does
not fall back to the server owner's global Garmin password.

`GarminTransport` in `backend/app/connectors/garmin/transport.py` is the
transport-facing protocol. Its methods match the operations consumed by the
existing sync path: activity pages and samples, sleep, HRV, stress, daily stats
and body composition. `GarminConnectTransport` calls the unofficial
`garminconnect` library and translates its current activity-detail shape into
the sample shape expected by sync. `LiveGarminClient` remains the
authentication/session facade and delegates to that transport. The former
`GarminClient` name and `LiveGarminClient` import remain available, and
`GarminConnectClient` is an explicit alias for new call sites. Callers can
inject a transport into `LiveGarminClient`, while existing sync code can keep
injecting a client directly. FIT enrichment is another ingestion path,
independent of the Garmin Connect client.

`OfficialGarminTransport` is only an unsupported placeholder. Its operations
raise `NotImplementedError` with the missing approval/schema dependency; it
does not return empty values, fabricate a DTO, or participate in client
construction. This makes the future boundary visible without implying an
official API integration exists.

Automated Garmin tests inject test clients/fixtures; the Garmin client module
states that automated tests never call Garmin's live API. The checked-in
fixtures establish only those test shapes. No live Garmin account validation
is recorded.

## Official access is a separate integration

The repository has no Garmin official API OAuth adapter, official API
credential settings, webhook receiver, official response fixtures, or
official-to-canonical mapper. Existing Garmin Connect session tokens and
passwords are not official API credentials and cannot be reused for an
official connection.

Garmin's official products, enrollment, access approval, data products,
authorization details, endpoints, payload schemas, webhook behavior, and
delivery semantics must be taken from the current partner documentation and
the specific access granted to Apex. This document intentionally does not
invent endpoint names, OAuth scopes, field names, response envelopes, or
webhook schemas. The codebase alone cannot confirm what Garmin would approve
or make available to this deployment.

Before implementation, obtain and verify the following with Garmin for the
intended legal entity and deployment:

1. **Program and product access:** written approval and current terms for each
   required official product. Health-data ingestion and workout delivery are
   separate capabilities; approval for one must not be treated as approval for
   the other.
2. **Application credentials:** the precise credential type(s), provisioning
   method, secret rotation rules, environment separation, and any required
   application registration metadata specified by Garmin.
3. **Athlete authorization:** the official per-user consent, access grant,
   revocation and refresh lifecycle, plus the precise permissions/data products
   an athlete can authorize.
4. **Transport and operations contract:** official base URLs, versioning,
   pagination, rate limits, retry rules, event/webhook signatures, replay
   handling, delivery guarantees and sandbox availability, as provided by the
   approved documentation.
5. **Data and deletion terms:** allowed retention, derived-use, export,
   user-erasure and downstream processing requirements, including whether the
   deployment may use the requested data for any AI-supported feature.
6. **Workout delivery contract, if needed:** supported workout formats,
   upload API and permissions, device/account compatibility, acceptance or
   synchronization receipts, failure handling and any compensating operation.

No official credential names are added here because none are established by
the current code or verified partner instructions. The existing settings
`GARMIN_EMAIL` and `GARMIN_PASSWORD` are for the unofficial login fallback;
they must not be presented as official API credentials.

## Recommended minimal transport boundary

Keep the current canonical normalization and database contract independent of
Garmin's transport. The narrow migration seam is the **fetch-and-auth adapter
that returns source-tagged raw payloads to the existing sync orchestration**:

- Keep the existing unofficial client as one transport while the private alpha
  needs it.
- Add a separate official adapter only after approved documentation and
  credentials exist. It should own official authentication/refresh, request
  construction, pagination, rate limits, and transport retries.
- Have that adapter map only verified official response records into the
  application's internal raw payload categories. Preserve the unmodified
  response (subject to retention rules), source, provider record identity,
  acquisition time and measurement time for audit and normalization.
- Keep official payload parsing in an explicit official-to-internal mapping
  layer. Do not force an unverified official schema through
  `LiveGarminClient`'s unofficial method semantics or silently reinterpret
  official payloads as `garminconnect` responses.
- Reuse downstream canonical normalizers only where an official mapper can
  demonstrate equivalent meaning and units. Add distinct payload categories
  or provenance when the official feed has different granularity or semantics.
- Treat official webhook delivery as a separate ingestion trigger if the
  approved product uses it; validate signatures and replay/idempotency rules
  from Garmin's documentation before writing a receiver. A webhook event must
  not be assumed to contain the data record itself.
- Keep workout delivery separate from read synchronization. A requested or
  uploaded workout is not “delivered” until the official contract provides a
  verifiable receipt for the required downstream state.

In this shape, the smallest practical new production seam is a new
`GarminTransport` implementation plus a verified response-to-raw mapper. Do
not widen the current protocol with guessed official endpoints. Once official
product documentation is available, decide whether a canonical client protocol
can be shared or whether official sync needs a distinct transport protocol.
That decision should follow actual payloads and operations contracts.

## Credential and release dependencies

The official path cannot be considered ready until all of these are satisfied:

- Garmin has approved Apex and the intended use for each required official
  product, and any commercial/legal review is complete.
- The deployment has official application credentials and the exact official
  athlete authorization configuration from Garmin. Per-athlete grants are
  stored encrypted, scoped to the owning account, and revocable.
- The operator has configured only the official endpoints and credential
  material specified by the approved integration documentation. Values are
  supplied through the secret manager/environment, not source control.
- Contract tests cover approved sample payloads and malformed, duplicate,
  delayed, revoked, rate-limited and partial responses. They do not require
  production credentials.
- A separately authorized live test verifies consent, one or more real data
  flows, revocation/deletion, and any official workout acceptance behavior.
  Record date, provider environment, account type, data scopes, tested outcome,
  and limits of that validation.
- Production deployment monitors authorization expiry, sync freshness,
  partial failures, rate-limit responses, duplicate events and data deletion.

Until those dependencies are evidenced, the official Garmin Health API,
official Garmin Training API, webhook ingestion, official workout delivery,
and commercial approval remain **unverified future work**. The current
unofficial Connect path and manual FIT enrichment remain separate alpha
capabilities, each with their own limitations.

Network-free protocol contract cases live in
`backend/tests/test_garmin_transport.py`. They cover method compatibility,
sample-shape adaptation, dependency injection and the explicit unsupported
official placeholder. They do not call Garmin or establish live behavior.
