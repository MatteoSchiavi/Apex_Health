# Garmin API endpoint inventory — 5 November 2026

Checked against the [official Personal API Swagger](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/)
and [official Python SDK](https://github.com/garmin/connect-personal-api-python).
A minimal path/query contract with retrieval date and source SHA-256 is checked in
at `backend/tests/fixtures/garmin/personal_api_contract.json`. Tests verify every
requested route/query against that contract. This is schema validation, not a
new real-account acceptance run.

**Normalized** means typed measurements/activity projections. **Source document**
means the exact structured response is retained with endpoint/context and account
ownership, without claiming a canonical metric or chart. Routes listed as
alternatives are intentionally not fetched twice.

| Documented GET path | Handling |
|---|---|
| `/activitylist-service/activities/search/activities` | Paged activity summaries, normalized |
| `/activity-service/activity/{activityId}` | Source document |
| `/activity-service/activity/{activityId}/workouts` | Source document; associated workout definitions, not upload |
| `/download-service/files/activity/{activityId}` | Raw ZIP/FIT + validated samples/laps/recorded-set projection |
| `/sleep-service/sleep/dailySleep` | Normalized sleep + retained response |
| `/sleep-service/sleep/dailySleepSummariesByDate` | Range alternative; daily detail route used |
| `/hrv-service/hrv/{calendarDate}` | Normalized HRV + retained response |
| `/hrv-service/hrv/daily/{fromDate}/{toDate}` | Range alternative; daily detail route used |
| `/usersummary-service/usersummary/daily` | Normalized daily biometrics/stress observations + retained response |
| `/usersummary-service/v2/dailysummaries` | Source document |
| `/weight-service/weight/range/{startDate}/{endDate}` | Requested-day weight/body fat normalized; original retained |
| `/weight-service/weight/all/{startDate}/{endDate}` | Alternative not used: returned 400 in the October account check; official SDK uses `/range` |
| `/usersummary-service/stats/hydration/daily/{startDate}/{endDate}` | Source document |
| `/usersummary-service/stats/steps/daily/{startDate}/{endDate}` | Source document |
| `/usersummary-service/stats/stress/daily/{startDate}/{endDate}` | Source document; daily aggregates, not a stress timeline |
| `/nutrition-service/food/logs/{date}` | Source document; existing Food UI still uses Fitbit |
| `/wellness-service/wellness/bodyBattery/reports/daily` | Source document |
| `/wellness-service/wellness/dailyHeartRate` | Source document |
| `/wellness-service/wellness/daily/spo2acclimation/{calendarDate}` | Source document |
| `/fitnessage-service/fitnessage/v2/{calendarDate}` | Source document |
| `/wellnessactivity-service/activity/summary/range/{fromDate}/{untilDate}` | Source document |
| `/goal-service/goal/user/effective/weightgoal/{startDate}/{endDate}` | Source document |
| `/periodichealth-service/menstrualcycle/summary/{calendarDate}` | Source document, if supplied/authorized by Garmin |
| `/periodichealth-service/menstrualcycle/dayview/{calendarDate}` | Source document, with current account-local date |
| `/userprofile-service/userprofile/settings` | Source document, once per client/sync |
| `/biometric-service/heartRateZones/v2` | Source document, once per client/sync |

Date ranges are requested as individual days, respecting bounded-range APIs.
Core feeds determine the historical empty-gap heuristic; undated profile settings,
goals or default-shaped supplemental documents do not extend the history walk.
Supplemental errors are counted and reported as partial, not silently discarded.
Core daily failures preserve other fetched data and stop a backward walk for retry;
they are not counted as empty history. Unauthorized access stops authentication;
there is no cross-account/global fallback. Missing permissions do not erase data.

Archive ingestion checks source/user/activity ID and FIT start time, CRC, bounded
size and unambiguous single-session mapping. Provider summaries retain stable IDs;
original bytes are stored before normalization. JSON exercise aggregates are not
individual recorded strength sets. Failed parsing retains pending raw evidence.

No new live credential or production health database was accessed in this audit.
To establish completeness, compare a known date range and activity list against
the owner's Garmin account, review partial/pending rows, verify granted feeds,
and check timezone, units, gaps, multi-session and archive-size exceptions. Neither
a successful HTTP response nor zero normalization errors alone proves completeness.
