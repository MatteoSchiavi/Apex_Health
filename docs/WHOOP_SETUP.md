# Connect WHOOP

Apex Health uses WHOOP's official Developer API v2 and a separate OAuth connection for each Apex Health account. The developer application keys identify your application; each athlete authorizes their own WHOOP account through Settings → Devices & Services → WHOOP.

## Configure the application

Create or open your application at <https://developer.whoop.com/> and configure the OAuth redirect URL. Enter these values securely in the deployment's `.env` or secret manager; do not paste keys into chat or commit them:

```dotenv
WHOOP_CLIENT_ID=
WHOOP_CLIENT_SECRET=
WHOOP_REDIRECT_URI=https://your-apex-host.example/integrations/whoop/callback
```

Use the exact public callback URL, including its scheme, hostname, port if present, and path, in both WHOOP's developer portal and `WHOOP_REDIRECT_URI`. Apex's reverse proxy and development Vite proxy preserve `/integrations/whoop/callback`; there is no `/api` prefix in the repository's routes. A custom proxy that adds a prefix must forward that public callback to this backend route. The provider redirects the athlete's browser, so the callback must be reachable from that browser. Register the chosen development callback separately if WHOOP permits it; the direct backend default is `http://localhost:8000/integrations/whoop/callback`.

The API and Celery worker both need the same application settings and the existing, stable `ENCRYPTION_KEY`. That key encrypts saved OAuth tokens locally; keep its real value in the application's secret storage. Do not use an outbound proxy placeholder as the local encryption key, and do not replace an existing key without migrating encrypted data.

Defaults already specify:

```dotenv
WHOOP_API_BASE=https://api.prod.whoop.com/developer/v2
WHOOP_OAUTH_AUTHORIZE_URL=https://api.prod.whoop.com/oauth/oauth2/auth
WHOOP_OAUTH_TOKEN_URL=https://api.prod.whoop.com/oauth/oauth2/token
WHOOP_SCOPE=offline read:profile read:body_measurement read:cycles read:recovery read:sleep read:workout
```

Keep `offline` to receive a refresh token and all listed read scopes for the collections Apex imports. If application permissions or scopes change, reconnect the account to grant the new permissions. Requests use the API base once; do not append another `/v2` to these endpoint paths. Sleep and workout identifiers are UUIDs in v2; cycle identifiers remain numeric.

Allow HTTPS to `api.prod.whoop.com` for token exchange, refresh, and data imports. Allow `developer.whoop.com` when consulting official developer documentation. Preserve the deployment's other required destinations. Cloud environment draft changes require saving in environment settings before runtime network access or key bindings can be validated.

## Authorize and import

Restart the API and worker after supplying settings. Sign into the intended Apex Health account, open Settings → Devices & Services, select WHOOP, and complete WHOOP's consent page. A new connection stores encrypted OAuth tokens on that account's integration. The callback state expires after ten minutes, is consumed once, and shares the account lock used by sync and disconnect.

Run a manual sync from the integration controls. The worker performs an initial history import and later syncs with a one-day overlap for late-scored records. Select the main device when using both Garmin and WHOOP. A matching effort receives one canonical activity and separate provider links; WHOOP Strain and zones remain available in WHOOP metadata. Repeated imports preserve the main device's measurements.

Disconnect invalidates pending authorization and removes access credentials. Previously imported history remains subject to the application's retention and deletion controls; revoking an application's access at WHOOP is a separate provider action.

## Units and provenance

| WHOOP measurement | Apex storage |
| --- | --- |
| Sleep stages and zone durations in milliseconds | Seconds; sleep duration observations use hours |
| Overnight HRV RMSSD in milliseconds | `hrv_overnight_rmssd`, milliseconds, overnight context |
| Resting heart rate | Beats per minute |
| Recovery SpO₂ | Percent, associated with the related sleep/cycle wake date |
| Sleep respiratory rate | Breaths per minute |
| Workout energy in kilojoules | Kilocalories, divided by 4.184 |
| Weight | Kilograms; body measurement API is a retrieved snapshot |
| WHOOP Recovery and Strain | WHOOP metadata; Strain does not become training load |

Sleep performance is stored on a 0–100 scale with explicit WHOOP semantics in its observation metadata. It uses WHOOP's algorithm and should not be interpreted as the same score formula as Garmin's sleep score. Observations retain their provider, feed, IDs, available device context, timestamps, and raw-record reference for source-specific analysis.

Timestamps are normalized to UTC. Day boundaries use the athlete's configured timezone and sleep's wake-up date. Recovery records contain sleep/cycle IDs rather than a measurement timestamp; Apex joins the related records and never uses the import date to date historical recovery. Missing context leaves the raw record available for retry. `PENDING_SCORE` and `UNSCORABLE` records do not replace scored measurements with zeros or nulls. Naps remain in the raw history and do not enter nightly sleep summaries.

## Diagnose a connection

- “Client not configured”: check that the API and worker received `WHOOP_CLIENT_ID` and `WHOOP_CLIENT_SECRET`.
- Callback or redirect mismatch: compare the portal URL and `WHOOP_REDIRECT_URI` exactly, and verify proxy forwarding.
- Expired or already used state: start a new connection from Settings; do not replay an old callback.
- Access denied: check application permissions and reconnect with the required scopes.
- Missing historical recovery: check that cycle/sleep data is accessible; incomplete timing context stays unprocessed rather than being placed on today's date.
- HTTP 429 or temporary provider errors: the client performs bounded retries, then the durable account sync can retry. A repeated HTTP 401 produces a reconnect error instead of looping indefinitely.

The automated connector tests use mocked OAuth/API responses and a disposable database. They verify URL composition, pagination, token refresh, encrypted token storage, single-use state, units, recovery dates, provenance, and main-device deduplication. A live end-to-end connection also requires the real keys, permitted network access, and the athlete's browser consent.
