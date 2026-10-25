# Garmin Personal API owner pilot

Garmin Personal API access is for your own Garmin data. Apex Health limits
this connection to the owner account. Connecting other athletes requires
separate Garmin Business API approval and is outside this pilot. See
[Garmin's Personal API FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/).

## Connect or replace a key

1. Sign into your own Garmin account and open
   [Personal API settings](https://connect.garmin.com/app/settings/personalApiToken).
   Create a Personal API key and review Garmin's current access terms.
2. Sign into Apex Health as the owner. Open Settings → Devices, select Garmin
   Personal API, and paste the key into the key field.
3. Save the connection. Apex Health verifies the key with Garmin before
   replacing any saved Garmin credentials, then queues a sync for your account.

The key and exchanged access token are stored encrypted in your integration
record. Responses, connection errors and status listings do not include them.
No `.env` entry or Garmin password is needed for this method. Access tokens
renew from the saved key; an expired or revoked key needs replacement.
The app does not infer the key's expiration from a date supplied by the user.

Switching from Garmin Connect preserves imported history, the selected main
device, and the existing sync watermark. The pilot limits imports to the most
recent 30 calendar days and reports that coverage window. This is an app pilot
limit, not a claim about Garmin's data retention. Available data still depends
on Garmin; this pilot does not promise a full historical import.
If saving succeeds while the task queue is unavailable, the saved connection
remains valid and the app reports that the sync was not queued. Retry Sync
once the queue is available.

## Coverage

The pilot imports the supported JSON feeds: activity summaries, supplied
VO2max values, sleep including available respiration/SpO2/score, HRV, daily
summary values such as steps, resting heart rate, stress and Body Battery,
and daily weight/body fat when supplied by Garmin.

Activity sample streams, individual strength sets, stress time series,
training readiness/status and recovery time are unsupported in this pilot.
Aggregated exercise summaries are not treated as individual strength sets.
Workout upload is not included. Missing values remain missing; support in
Garmin's own application does not establish availability in this connector.

Both Garmin connection methods share a limit of three connection attempts per
hour for the signed-in account. A running sync or connection returns a conflict;
retry when it finishes. Invalid keys keep the previous connection intact.
Disconnect removes locally saved credentials and retains imported history;
revoke the Personal API key in Garmin settings if you also want to invalidate
it at Garmin.

## API contract

`POST /settings/integrations/garmin/personal/connect` accepts only
`{"api_key": "your-personal-api-key"}` and requires an owner session plus the
existing CSRF header. Do not put keys in URLs or shell command arguments.
Successful responses include `connected`, `provider`, `auth_method` and
`backfill_enqueued`; they contain no key, access token or expiration claim.
Owner device/integration listings identify the connection as
`auth_method: "personal_api_key"`; saved legacy Garmin Connect sessions use
`"garmin_connect"`. Friend listings do not inspect encrypted credentials.
