# UI and data changes, October 2026

The application remains a private, invite-only, self-hosted service. Privacy,
terms and storage pages are public so they can be read before signing in.
Deployment facts and remaining operator responsibilities are documented in
[LEGAL_DEPLOYMENT.md](LEGAL_DEPLOYMENT.md).

## Navigation and phone installation

Notifications open from the header bell. Preferences and Data Health live in
Settings; old page URLs redirect there. The desktop sidebar can be collapsed
and remembers that choice. Calendar shows one month, past and upcoming events,
confirmed training sessions and imported activities; selecting a day opens all
its entries.

The PWA manifest and icons support installation on compatible browsers. Open
Settings → Appearance for the browser install button; on iOS use Safari's
Share → Add to Home Screen. Phone access requires a trusted HTTPS origin.
The service worker caches public static assets only, with a generic offline
page. Health records, documents, authenticated HTML and API responses are not
cached for offline use. Native installation on a physical phone still needs
validation against the deployment's HTTPS origin.

## Metrics and imports

Body Signals supports 7 days, 4 weeks and 6 months. Duration displays use hours
and minutes, including chart labels. Sleep trends select the longest complete
night on each date, rather than independently maximizing each sleep stage.

Recorded nightly HRV has a personal, empirical P10–P90 band from the preceding
28 days, excluding the latest day. It requires 14 recorded days and keeps
provider, device and reading context separate. A recorded device-change entry
resets its history. This is a comparison with the person's own recordings,
not a medical reference range; a high value is not automatically good or bad.
Arrows describe change, and only metrics with a supported directional
interpretation receive a favorable/unfavorable color.

The Estimates tab explains the older Apex readiness, recovery, strain, sleep
architecture and risk scores. These are heuristics retained for history and
are not validated diagnoses or probability estimates. Device sleep score and
nightly HRV are separately accessible. Generic provider training load is
labelled as load points rather than assuming it is Training Stress Score.

Garmin nightly HRV summaries without five-minute samples are now retained.
Summary-only typed records use a documented local-day anchor because the
provider supplies no measurement timestamp. No missing provider measurements
are fabricated. Existing raw imports can be replayed through the normalizer;
new connector imports use the corrected parser. Garmin Developer Program
access remains an external prerequisite for a future official connector.

Sport mapping distinguishes mountain biking, hiking, walking, swimming,
rowing, yoga, Pilates and gravel cycling. Unknown sports remain unknown.
Migration 0011 repairs previously generic/enduro activity labels only where
account-owned source links and raw records identify the sport. The selected
main integration wins over fallback source priority. It snapshots changed
labels and preserves subsequent edits during rollback.

## Labs and external food diary

Labs includes an encrypted TXT/Markdown/PDF file inbox with authenticated,
account-scoped original download and deletion. Food uses an external Fitbit
diary: Apex does not offer a new manual food-entry application. Existing
historical nutrition records remain exportable.

To enable the optional Fitbit connector, register a Fitbit app with the exact
HTTPS `/integrations/fitbit/callback` URL, set `FITBIT_CLIENT_ID`,
`FITBIT_CLIENT_SECRET` and `FITBIT_REDIRECT_URI` securely, and grant the
nutrition scope. The server needs HTTPS egress to `api.fitbit.com`; users
authorize through `www.fitbit.com`. Tokens are encrypted at rest. The diary
is fetched for the selected day rather than stored as a second food log.
The provider flow has mocked regression coverage but has not been exercised
with real application credentials.

Wearable disconnect controls remove local credentials and pending connection
state without deleting imported history. Strava revocation is attempted at
the provider; other services may also require revocation in their own account
settings. Data deletion is a separate action in Settings → Data Health.

## Research boundaries

[SYSTEM1_MODELS.md](SYSTEM1_MODELS.md) compares small local classifiers and
describes a benchmark before adding a resident model. No inference dependency
or model service was added. The metrics research attachment was not available
in this conversation, so no claim is made that its suggestions were reviewed.

## Verification

The isolated PostgreSQL/Redis backend suite passed all 537 tests. Chromium UI
tests passed all 41 cases, including mobile/desktop layouts and accessibility;
the service-worker unit suite passed all 5 cases. Production build and English/
Italian translation parity passed. The API-served bundle was also checked in
Chromium: registration, static caching, API exclusion and offline navigation
passed. The development database is at migration 0012, and API/worker startup,
owner login and four Celery round trips passed after restart.

No real Fitbit authorization, Garmin account sync or physical phone installation
was performed. Legal authority pages and the TypeSafe Jev article were blocked
by the environment proxy. The added `api.fitbit.com` and `typesafe.ai` network
destinations are saved in the environment draft; they require Environment
settings Save and Publish before they become active.
