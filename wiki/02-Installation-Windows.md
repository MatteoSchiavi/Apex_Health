# Chapter 2 — Installation on Windows (Docker Desktop)

*Thirty minutes from a clean machine to a logged-in dashboard.*

You need two programs:

1. **Docker Desktop for Windows** with the WSL 2 backend — run `wsl --install` on a fresh machine, reboot, then install Docker Desktop and leave *"Use WSL 2 based engine"* enabled.
2. **Git for Windows** with default options.

The repo pins `.gitattributes` to LF endings, so Windows line-ending issues are already solved — shell scripts and Dockerfiles survive the clone intact.

## Step 1 — Clone

Somewhere local, **never a cloud-synced folder** — OneDrive/Dropbox paths cause file-lock conflicts with bind mounts. `C:\Users\you\apex-health` is ideal.

```powershell
git clone https://github.com/MatteoSchiavi/Apex_Health.git ~/apex-health
cd ~/apex-health
copy .env.example .env
```

## Step 2 — Fill `.env`

Three secrets plus your login. Generate three fresh values and paste one per line. In PowerShell:

```powershell
# each line prints one secret — SESSION_SECRET, ENCRYPTION_KEY, BACKUP_ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set `OWNER_EMAIL` / `OWNER_PASSWORD` (this becomes your login). Leave `DATABASE_URL` and `REDIS_URL` **empty** — compose overrides them with container-network values. Save as UTF-8 without BOM (VS Code or Notepad defaults are fine).

> **Guard these three keys with your life.** Losing `ENCRYPTION_KEY` means losing connector tokens and lab notes (they cannot be decrypted again); losing `BACKUP_ENCRYPTION_KEY` means losing every backup artifact. Store all of them in a password manager now.

## Step 3 — Build and boot the stack

The first build compiles the React SPA inside the image — `docker compose build` is the only UI deploy step you will ever need.

```powershell
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml exec api alembic upgrade head
curl.exe http://localhost:8000/health
# {"status":"ok","database":"up","redis":"up"}
```

## Step 4 — Log in

Open `http://localhost:8000` in a browser and sign in with your owner email/password. The SPA is served by the API itself — there is no second port.

## Windows traps, pre-solved

- Use **`curl.exe`, not `curl`** — in PowerShell `curl` aliases `Invoke-WebRequest` and breaks cookie-jar examples.
- Forward slashes work in every compose path.
- To run the 436-test suite inside the container (optional):

```powershell
docker compose -f infra/docker-compose.yml exec api sh -c "uv sync --frozen && uv run pytest -q"
```

**Next:** [First-run setup →](03-First-Run-Setup.md)
