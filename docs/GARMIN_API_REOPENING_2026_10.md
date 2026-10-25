# Garmin API reopening: implications for Apex

Research verified 22 October 2026; written 23 October 2026. This is an
implementation decision record, not a claim that Apex has migrated or that a
live API call has succeeded.

## Confirmed from Garmin

| Access | Data direction and products | Practical role for Apex |
| --- | --- | --- |
| Personal | Pull access to the user's own Activity, Health and Women's Health data | Validate official ingestion for the owner's personal use |
| Business Starter | Activity, Health, Women's Health, Training and Courses; incoming data by push; no historical backfill | Multi-user connection and workout delivery |
| Business Enterprise | Push or ping/pull, expanded historical access and capacity, support and additional options | Reassess when Starter limits become a demonstrated problem |

The [official overview](https://developer.garmin.com/gc-developer-program/overview/)
describes all three paths. The
[developer portal](https://developerportal.garmin.com/developer-programs/connect-developer-api)
specifies up to 1,000 connected users for Starter. Business access requires an
application; publication of this page does not mean Apex has been accepted.
Pricing and approval turnaround were not verified from the current public
documentation. Older cached FAQs about the paused program are not the basis
for this decision.

## Personal authentication and coverage

The owner creates a key in
[Garmin Connect settings](https://connect.garmin.com/app/settings/personalApiToken).
Garmin displays it once. Expiration choices are 30, 90 or 180 days, or one year.
Exchange it at the documented token endpoint using `Authorization: ApiKey …`;
data requests use the resulting bearer token. Tokens last up to 24 hours,
bounded by the key's expiration. There is no refresh token: request a new
access token using the key. Deleting the key revokes its associated tokens.
The [Personal API FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/)
describes personal use and directs organizations serving multiple users to
the Business program.

The public [Swagger specification](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/)
inspected on 22 October contains 26 data paths, all GET operations. These
cover activity search/detail and downloads, sleep, HRV, Body Battery, heart
rate, stress/steps, daily summaries, weight, hydration/nutrition and other
read surfaces. The activity-summary schema includes `vO2MaxValue` and
`summarizedExerciseSets`; a declared field does not guarantee a populated
value for a particular device or activity. No workout-upload operation is
present. `activity/{activityId}/workouts` reads associated workout information;
it is not a way to send a workout to a watch. Dedicated training-readiness
and training-status paths were not present in this snapshot.

Garmin supplies an Apache-2.0
[Python client and CLI](https://github.com/garmin/connect-personal-api-python),
requiring Python 3.12+. It separates authentication from data requests.
Its default authenticator writes a local plaintext token cache; embedding
that default unchanged in a multi-account web worker would be inappropriate.
Apex should retain encrypted, account-scoped credential storage. SDK source
is a useful reference, not a reason to bypass existing credential isolation.

The public material inspected does not establish numeric rate limits,
Personal historical-retention guarantees, complete metric parity, or the
terms applicable to Apex's hosted AI processing. These need the current
contract and actual authorized payloads, rather than assumptions based on
unofficial endpoints or third-party claims.

## Impact on the current code

`backend/app/connectors/garmin/client.py` authenticates through the unofficial
`garminconnect` library. `transport.py` has a reusable operation boundary but
its `OfficialGarminTransport` deliberately raises `NotImplementedError`.
The current worker and encrypted integration records are account-scoped.
Neither those sessions nor an Apex login password are Personal API keys.

An official connection can remove dependence on private login/session
behavior. It does not by itself fix existing partial-data handling, incorrect
normalization, queue retries, or product usability. Those fixes remain part
of the v0.1 acceptance work.

## Recommended implementation order

1. **Owner-only proof:** add a separately selected Personal transport with an
   encrypted key/token lifecycle, bounded retries and explicit expiry/revocation
   states. Keep it disabled until an authorized key is configured. Fetch a
   recent activity, one sleep record, HRV and a daily summary; compare timestamps,
   units and completeness with current data without replacing history.
2. **Contract mapping:** derive fixtures from reviewed, redacted official
   payloads. Map only equivalent fields into canonical records. Preserve
   existing source IDs and avoid duplicate activities when switching transport.
   Validate FIT downloads before treating them as equivalent to existing samples
   and exercise-set ingestion. Missing fields remain missing, not zero.
3. **Business application:** prepare Apex's actual use case, URLs and required
   Activity/Health/Training products for the owner to submit. Obtain the granted
   scopes, current terms, event authentication and delivery contract. No
   application was submitted or agreement accepted during this research.
4. **Multi-user ingestion:** implement the documented authorization and push
   receiver with tenant isolation, duplicate/out-of-order handling, durable
   processing and revocation. Preserve previously imported history; Starter's
   lack of backfill must be visible during onboarding.
5. **Workout delivery:** add an explicit Send to Garmin action after the
   athlete approves a structured workout. Track provider acceptance separately
   from device synchronization. Validate running, cycling and strength support
   against the granted contract and an actual compatible device.
6. **Cutover:** require passing contract tests, successful real account sync,
   metric coverage comparison and rollback planning before retiring the old
   connection. Keep this provider migration independently reviewable from the
   already tested UI/workout repairs.

This was the implementation state at the time of the original research.
The owner Personal API pilot is now implemented in the follow-up branch; see
[setup, coverage and limitations](GARMIN_PERSONAL_API.md). Live authentication
and activity, sleep, HRV, daily-summary and weight-range reads have succeeded
with an owner-supplied key. Full-pipeline acceptance, release checks and the
installed production revision must be assessed separately. Business enrollment
and workout delivery remain outside the Personal API pilot.
