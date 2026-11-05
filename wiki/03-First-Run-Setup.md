# Chapter 3 — First-run configuration

*Link devices, import history, invite your friends.*

## 3.1 — Connect Garmin (the UI way)

Garmin uses the official Personal API for the owner's own account. In Settings →
Devices & Services → Garmin API, paste a key created in
[Garmin settings](https://connect.garmin.com/app/settings/personalApiToken).
The key is verified and stored encrypted; access tokens renew automatically.
Password/MFA login is removed. Friend accounts need separately approved Business
API support. Existing imported data is retained when reconnecting.

The first sync pages activities and walks daily wellness backwards until the
configured empty gap; that does not guarantee all history after long gaps. There
is no 30-day pilot cap. See [setup, explicit history ranges and limits](../docs/GARMIN_PERSONAL_API.md)
for owner maintenance. Check partial/pending status before assuming completeness.
The scheduler runs incremental syncs every six hours. Original FITs supply
recorded samples/laps/sets; supplemental responses may be archive-only.

## 3.2 — Whoop, Strava, weather

Whoop (official API v2, a first-class primary device) and Strava (GPS companion) each need a one-time, **manual app registration** because you own the developer account. Both flows then finish in the UI: **Settings → Devices & Services → Connect**, which opens the provider's consent page and stores the tokens encrypted.

| Source | Register at | Critical detail |
|---|---|---|
| Whoop | developer.whoop.com → Create an app, data access **USER** | Request all `read:*` scopes plus `offline` (that yields the refresh token). Redirect URI must match `WHOOP_REDIRECT_URI` character-for-character. |
| Strava | strava.com/settings/api | Authorization Callback Domain = your host (`localhost` now, your domain later). Scope defaults to `activity:read_all`. |
| Weather | no account — Open-Meteo is keyless | Set `WEATHER_HOME_LAT` / `WEATHER_HOME_LON` in `.env`, restart the stack; the next 6-hourly tick fills the forecast cache and enriches activities. |

After filling `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET` (or the Strava pair) in `.env`, restart with `docker compose -f infra/docker-compose.yml up -d` so the API picks the values up. Beat syncs Whoop at :05, Strava at :07, every 6 hours; first sync is a full backfill to the origin of the account.

## 3.3 — Add data

Start with an empty account, then import an original FIT/CSV file from **Data
Health** or connect a provider from **Settings**. The application never creates
sample health records during normal use.

## 3.4 — Invite your friends

The app is multi-user with strict server-side isolation: a friend's session can only ever address their own rows — someone else's row ID answers 404, owner-only settings answer 403. Friends default to the `cheap_only` AI tier (bounded cost); you can raise an account to full from the owner's settings at any time.

1. **Mint an invite.** As owner: Settings → Invites → create (7-day expiry by default). The code is shown once.
2. **Friend redeems.** Send the code over a channel you trust. Your friend opens `/join` on your public URL (see [Remote access](06-Remote-Access.md)), picks name/email/password, and is in — one step, no admin work.
**Next:** [Daily usage →](04-Daily-Usage.md)
