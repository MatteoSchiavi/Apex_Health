# Apex Health Control Center — Owner's Guide

**Install · Use · Maintain** — the complete field manual for your self-hosted health platform: from first boot on Windows Docker Desktop, through every feature of the web UI, to nightly backups, free remote access, and the 8 GB Linux homeserver migration.

| | |
|---|---|
| **Pages** | 13 UI pages |
| **Data sources** | 5 (Garmin, Whoop, Strava, weather, labs) |
| **Tests** | 436 green |
| **Data** | 100% local — nothing leaves the box |
| **UI** | EN / IT · light / dark |
| **Edition** | v2026.09 · commit `531316f` |

---

## The Guide

| Chapter | Page | What's inside |
|---|---|---|
| 1 | [What you are running](01-What-You-Are-Running.md) | The five containers, memory budget, three facts to memorize |
| 2 | [Installation (Windows)](02-Installation-Windows.md) | Docker Desktop + WSL2, clone, `.env` secrets, build & boot, first login |
| 3 | [First-run setup](03-First-Run-Setup.md) | Connect Garmin in the UI, Whoop/Strava registration, demo data, invites, Telegram |
| 4 | [Daily usage](04-Daily-Usage.md) | The 13 pages, the safety interlock, main-device law, the Connect IQ watch app |
| 5 | [Maintenance](05-Maintenance.md) | Update runbook, nightly schedule, backups & restore drill, troubleshooting table |
| 6 | [Remote access (free)](06-Remote-Access.md) | Tailscale / Funnel / Cloudflare Tunnel — ranked, with copy-paste recipes |
| 7 | [Homeserver migration](07-Homeserver-Migration.md) | Moving to the 8 GB Linux box with zero data loss |
| — | [Quick reference](Quick-Reference.md) | The commands you'll actually use + golden rules |

## The four golden rules

1. **Never lose `ENCRYPTION_KEY` or `BACKUP_ENCRYPTION_KEY`** — connector tokens, lab notes and every backup artifact are unrecoverable without them. Store both in a password manager now.
2. **Never port-forward `:8000` on your router** — tunnels only (see [Remote access](06-Remote-Access.md)). Plain HTTP breaks logins (Secure cookies) and exposes `/docs` to the world.
3. **Run the restore drill after every major change** — a backup is only as good as your last restore test.
4. **The API never auto-migrates** — after the first build and after every update, run `alembic upgrade head` once.

## Deep references in the repo

- [`docs/INSTALL.md`](https://github.com/MatteoSchiavi/Apex_Health/blob/main/docs/INSTALL.md) — exhaustive installation reference
- [`infra/tailscale-funnel-setup.md`](https://github.com/MatteoSchiavi/Apex_Health/blob/main/infra/tailscale-funnel-setup.md) — tunnel recipe
- [`docs/SECURITY.md`](https://github.com/MatteoSchiavi/Apex_Health/blob/main/docs/SECURITY.md) — owner-held keys, LUKS, incident playbook
- [`docs/DATA_COVERAGE.md`](https://github.com/MatteoSchiavi/Apex_Health/blob/main/docs/DATA_COVERAGE.md) — per-metric capture matrix
- [`docs/STACK.md`](https://github.com/MatteoSchiavi/Apex_Health/blob/main/docs/STACK.md) — technology stack and AI harness
