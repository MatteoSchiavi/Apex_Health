# Chapter 6 — Free remote access, ranked

*Reach your box from anywhere — without opening a single port.*

All three recommended options are free, encrypt end-to-end, and require **no port-forwarding** on your router. The API already binds to `127.0.0.1` inside the host, so nothing is reachable until you put a tunnel in front of it — and cookies are `Secure; HttpOnly; SameSite=Lax`, which is why plain-HTTP exposure is both unsafe and literally broken (browsers drop the cookie).

## The ranking

| Option | Public URL | Needs a domain? | Best for |
|---|---|---|---|
| **1 · Tailscale** (private) | tailnet-only, e.g. `http://apex-host:8000` | no | You + friends who install the Tailscale app. Zero public exposure, zero config. **Recommended default.** |
| **2 · Tailscale Funnel** | `https://host.tailnet.ts.net` | no | A real HTTPS URL in any browser, no domain, ~10 minutes. Watch app works through it too. |
| **3 · Cloudflare Tunnel** | `https://apex.yourdomain.com` | yes (free plan) | The smoothest friend experience — just a link, nothing to install. |

## 6.1 — Tailscale (private tailnet or public Funnel)

```bash
# on the server (or WSL host)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale cert      # enable HTTPS certs for the tailnet

# tailnet-only first — verify from your phone on the tailnet:
curl http://apex-host:8000/health

# then, when you want a public HTTPS URL:
sudo tailscale serve --bg --https=443 http://127.0.0.1:8000
sudo tailscale funnel 443 on
curl https://apex-host.<tailnet>.ts.net/health
```

Set `TRUST_PROXY_HEADERS=true` in `.env` and restart the stack — the app adopts the forwarded scheme/real client IP, but only from loopback peers, so it cannot be spoofed. Access control stays in the app: the invite flow is the gate, no route answers without a session except `/health`. Turning exposure off is one command: `sudo tailscale funnel 443 off`.

Full recipe: [`infra/tailscale-funnel-setup.md`](https://github.com/MatteoSchiavi/Apex_Health/blob/main/infra/tailscale-funnel-setup.md).

## 6.2 — Cloudflare Tunnel (best friend experience)

Point a (sub)domain at Cloudflare, create a tunnel in the Zero Trust dashboard (**Networks → Tunnels**) and map `apex.yourdomain.com` to the API, then run the connector on the server:

```powershell
docker run -d --name cloudflared --restart unless-stopped `
  --network apex-health_default cloudflare/cloudflared:latest tunnel `
  --no-autoupdate run --token <TUNNEL_TOKEN>
```

Also set `TRUST_PROXY_HEADERS=true`, and update the Whoop/Strava redirect URIs (in `.env` and in each provider's app console) from `http://localhost:8000/...` to the public domain; the values must match character-for-character or the OAuth flows reject the callback.

## What NOT to do

**Don't port-forward `:8000` on your router.** Plain HTTP breaks logins (Secure cookies) and exposes `/docs` to the LAN/internet. If you ever need bare port-forwarding for a workshop, put Caddy (automatic HTTPS) in front and keep the API on loopback — but for a homeserver, tunnels are strictly better.

**Next:** [Homeserver migration →](07-Homeserver-Migration.md)
