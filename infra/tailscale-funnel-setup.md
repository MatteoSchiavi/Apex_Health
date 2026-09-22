# Tailscale Funnel — exposing the Health Control Center beyond your tailnet

§15 of the master spec: "Deferred alongside the dashboard: Tailscale Funnel /
public exposure generally." That deferral ends with Phase 9 (multi-user). This
document is the concrete recipe for the owner's host.

Why Funnel (and not a VPS, not port-forwarding):

- No new infrastructure: the app stays on your machine, Tailscale's edge
  terminates public TLS and relays into your machine over the existing
  WireGuard tunnel.
- No firewall holes, no port forwarding, no domain procurement: Funnel gives
  you `https://<host>.<tailnet>.ts.net` with a real certificate.
- Access control stays in the app: the invite flow (§15, §18) is the gate.
  Anyone on the internet holding the URL can *reach* the API — they still
  cannot *read* anything without an account (§17: no route answers without a
  session except /health and the auth endpoints).

## 1. Prerequisites (one-time, on the owner's host)

```sh
# Install Tailscale and log in (creates/joins your tailnet).
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Enable HTTPS certificates for your tailnet (once per tailnet, admin console
# may also ask you to enable HTTPS/MagicDNS).
sudo tailscale cert            # or: tailscale DNS admin page -> HTTPS -> enable

# Funnel is a node-level capability: allow this machine to funnel.
sudo tailscale funnel --set-headers   # first run will prompt for what it needs
```

Your public origin will look like `https://apex-host.tail-scale.ts.net` —
Everything below calls that `$FUNNEL_URL`.

## 2. Serve the API through Funnel

Tailscale `serve` (tailnet-local) and `funnel` (public) are configured in
`~/.config/tailscale/serve-config.json` or directly via CLI. The API speaks
plain HTTP on loopback — TLS termination happens at Tailscale:

```sh
# Inside the repo root, with the stack running per docs/INSTALL.md:
sudo tailscale funnel --bg 8000
# or, explicitly:
sudo tailscale serve --bg --https=443 http://127.0.0.1:8000
sudo tailscale funnel 443 on
```

That publishes `https://$FUNNEL_URL` -> `127.0.0.1:8000` (FastAPI/uvicorn).
Only the API is funneled — everything else stays local; the database and
redis publish no ports at all, and writes always ride the invite-flow
session + CSRF rules.

Verify from an outside network (phone on mobile data):

```sh
curl https://$FUNNEL_URL/health
# {"status":"ok","database":"up","redis":"up"}
```

## 3. App-side switches (already built, Phase 9)

Set in `.env` before starting the stack:

```sh
# Trust X-Forwarded-Proto/-For — but only from loopback peers, which is what
# tailscaled's local proxy is. Keeps logs and any URL generation honest
# behind the tunnel while ignoring forged headers from real clients.
TRUST_PROXY_HEADERS=true
```

What is already correct with no further work:

- **Cookies are `Secure; HttpOnly; SameSite=Lax` unconditionally** (§22.2) —
  they round-trip fine over Funnel's HTTPS and are dropped by browsers over
  plain HTTP. No change needed or possible.
- **CSRF (§22.3)**: state-changing requests need the `X-CSRF-Token` header.
  A future single-page frontend served from `$FUNNEL_URL` is same-origin and
  can attach it; cross-origin sites cannot (that is the design).
- **CORS**: intentionally absent. Funnel is same-origin; if you ever split
  the frontend onto another origin, add a NARROW allowlist (§22.6) — never
  `*` on a credential-bearing API.
- **Login rate limiting (§22.1)** is keyed on the account email with a
  Redis-backed sliding window, so it works unchanged behind the proxy.
- **Sessions are server-side rows** (§22.2): revocation is real (logout or
  `DELETE FROM sessions`), so a leaked cookie dies with one DELETE.

## 4. Onboarding a friend over Funnel (the §15 flow, end to end)

1. As owner: `POST /settings/invites` (owner session) — response carries the
   code once; send it to your friend over a channel you trust.
2. Friend opens the redeem endpoint (or, once Appendix A ships, the UI page)
   at `$FUNNEL_URL` and picks their own email + password:
   `POST /auth/invite/redeem` with `{code, name, email, password}` — the
   response sets their session cookie; they are in.
3. The account is `role=friend`, `ai_access_tier=cheap_only` (§15). Owner
   can raise the tier with `PATCH /settings/users/{id}/ai-tier` (§18).
4. Every friend query is user-scoped at the query layer (§8.2): labs, gear,
   activities, journal, plans, alerts, chat — a friend sees and mutates only
   their own rows; addressing someone else's row ID answers 404. This is
   asserted by `tests/test_multiuser_isolation.py`.

## 5. Operational notes

- **The Funnel URL is public knowledge.** Treat it like your bank's URL:
  fine to be known, pointless to attack without an account. Keep invites
  short-lived (`expires_in_days` default 7) and revoke unused ones.
- **Telegram does not need Funnel** — the bot uses long polling outbound
  (§10.1), it works behind NAT exactly as before.
- **Watch app (Phase 10)**: Connect IQ's `makeWebRequest` from the watch goes
  via the phone's internet connection, so the glance works over the same
  Funnel URL — set it in the watch app settings together with the API token
  minted from `POST /watch/tokens`.
- **Logs**: uvicorn access logs under Funnel show 127.0.0.1 as the peer;
  with `TRUST_PROXY_HEADERS=true` the app-level logs carry the real client
  IP from `X-Forwarded-For`.
- **Stopping exposure**: `sudo tailscale funnel 443 off` (and
  `sudo tailscale serve --https=443 off`). The API is again tailnet-only
  within seconds; nothing else changes.
