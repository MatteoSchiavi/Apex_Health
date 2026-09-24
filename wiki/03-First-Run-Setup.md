# Chapter 3 — First-run configuration

*Link devices, seed history, invite your friends.*

## 3.1 — Connect Garmin (the UI way)

Everything happens in the app now — there are no access tokens to copy or manage by hand; they are exchanged, stored app-layer-encrypted, and refreshed automatically. The password is never persisted and is zeroed from memory after the exchange, and the connect endpoint is rate-limited (3 attempts/hour) so it can never be used as a brute-force proxy against your real account.

1. **Settings → Devices & Services → Garmin Connect → Connect.** Enter your Garmin email and password. If the account has MFA, a second inline step asks for the one-time code from your authenticator.
2. **Let the backfill run.** Connect enqueues the full-history backfill immediately: every activity ever recorded plus wellness (sleep, biometrics) walked backwards until a sustained 10-day empty gap. It is deliberately paced (unofficial client, ban-safe speed) — 3–6 months of history is normal, multi-year histories take longer. Watch progress on the same row; the button turns into **Sync now** for incremental pulls. The beat also syncs every 6 hours.
3. **Score the imported history now (optional).** Scores compute nightly at 03:00 user-local for the prior day. To score a fresh backfill immediately:

```powershell
docker compose -f infra/docker-compose.yml exec worker celery -A app.tasks.celery_app call `
  features.recompute_range --args '[1, "2026-03-01", "2026-09-24"]'
```

## 3.2 — Whoop, Strava, weather

Whoop (official API v2, a first-class primary device) and Strava (GPS companion) each need a one-time, **manual app registration** because you own the developer account. Both flows then finish in the UI: **Settings → Devices & Services → Connect**, which opens the provider's consent page and stores the tokens encrypted.

| Source | Register at | Critical detail |
|---|---|---|
| Whoop | developer.whoop.com → Create an app, data access **USER** | Request all `read:*` scopes plus `offline` (that yields the refresh token). Redirect URI must match `WHOOP_REDIRECT_URI` character-for-character. |
| Strava | strava.com/settings/api | Authorization Callback Domain = your host (`localhost` now, your domain later). Scope defaults to `activity:read_all`. |
| Weather | no account — Open-Meteo is keyless | Set `WEATHER_HOME_LAT` / `WEATHER_HOME_LON` in `.env`, restart the stack; the next 6-hourly tick fills the forecast cache and enriches activities. |

After filling `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET` (or the Strava pair) in `.env`, restart with `docker compose -f infra/docker-compose.yml up -d` so the API picks the values up. Beat syncs Whoop at :05, Strava at :07, every 6 hours; first sync is a full backfill to the origin of the account.

## 3.3 — Demo data (optional, exploratory)

Before trusting it with real data you can flood every surface with 240 days of deterministic synthetic data — dashboards, hypnograms, GPS routes, chats, challenges. **This wipes existing user data**, so use it on a fresh install only:

```powershell
docker compose -f infra/docker-compose.yml exec api env PYTHONPATH=/app python tools/seed_demo_data.py --days 240
# owner login afterwards: owner@apexhealth.dev / demo-owner-1234
```

## 3.4 — Invite your friends

The app is multi-user with strict server-side isolation: a friend's session can only ever address their own rows — someone else's row ID answers 404, owner-only settings answer 403. Friends default to the `cheap_only` AI tier (bounded cost); you can raise an account to full from the owner's settings at any time.

1. **Mint an invite.** As owner: Settings → Invites → create (7-day expiry by default). The code is shown once.
2. **Friend redeems.** Send the code over a channel you trust. Your friend opens `/join` on your public URL (see [Remote access](06-Remote-Access.md)), picks name/email/password, and is in — one step, no admin work.
3. **Optional: Telegram bot.** Put `TELEGRAM_BOT_TOKEN` (from @BotFather) in `.env`, then:

```powershell
docker compose -f infra/docker-compose.yml --profile telegram up -d
```

In the chat: `/link`, then `/confirm <code-from-server-log>`. The bot uses long polling — it works behind NAT with zero exposure, and it is where alerts and journal/gym shortcuts land.

**Next:** [Daily usage →](04-Daily-Usage.md)
