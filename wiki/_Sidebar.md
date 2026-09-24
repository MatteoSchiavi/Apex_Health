**[Apex Health Guide](Home.md)**

- **Getting started**
  - [1 · What you are running](01-What-You-Are-Running.md)
  - [2 · Installation (Windows)](02-Installation-Windows.md)
  - [3 · First-run setup](03-First-Run-Setup.md)
- **Living with it**
  - [4 · Daily usage](04-Daily-Usage.md)
  - [5 · Maintenance](05-Maintenance.md)
- **Going further**
  - [6 · Remote access (free)](06-Remote-Access.md)
  - [7 · Homeserver migration](07-Homeserver-Migration.md)
- **[Quick reference](Quick-Reference.md)**

---
**Golden rules**

- Never lose `ENCRYPTION_KEY` / `BACKUP_ENCRYPTION_KEY`
- Never port-forward `:8000` — tunnels only
- Run the restore drill after major changes
- `alembic upgrade head` after every update
