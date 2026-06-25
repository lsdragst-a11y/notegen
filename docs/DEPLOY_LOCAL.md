# Local Deployment

This document describes how to run NoteGen locally for the v1 demo checkpoint.

## Architecture

The local stack has four moving parts:

```text
Browser -> Next.js web (:3000)
        -> FastAPI API (:8000)
        -> Redis/RQ (:6379)
        -> one Python worker for qa + default queues
```

The worker stays on the host machine because it owns the GPU path. Redis can run in Docker. The API and web app can run either directly on the host or through the `full` Docker Compose profile.

## Prerequisites

- Windows 11.
- NVIDIA GPU for full video pipeline runs.
- Python 3.10 virtualenv at `.venv`.
- Node.js 18+ with dependencies installed in `web`.
- Docker Desktop.
- `ffmpeg` available on `PATH`.
- Local model directories under `models/` for full pipeline and QA generation.

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd web
npm install
```

Install the CUDA PyTorch build separately when setting up a new machine:

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

## Recommended Local Demo Startup

Open separate terminals from the repository root.

Terminal 1: Redis

```powershell
docker compose up -d redis
```

Terminal 2: API

```powershell
.\.venv\Scripts\python.exe server.py
```

For a clean smoke run without automatic maintenance or backup side effects:

```powershell
$env:NOTEGEN_AUTO_MAINTENANCE="0"
$env:NOTEGEN_AUTO_BACKUP="0"
.\.venv\Scripts\python.exe server.py
```

Terminal 3: Worker

```powershell
.\.venv\Scripts\python.exe scripts\run_worker.py
```

Only run one worker. The v1 GPU model assumes serial execution across QA and generation jobs.

Terminal 4: Web

```powershell
cd web
npm run dev
```

Open:

```text
http://localhost:3000
```

## Production Build Check

Before a demo checkpoint, verify the web app builds:

```powershell
cd web
npm run lint
npm run test
npx tsc --noEmit
npm run build
```

## Full Compose Option

Redis, API, and web can be started through Docker Compose:

```powershell
docker compose --profile full up -d --build
```

The worker still runs on the host:

```powershell
.\.venv\Scripts\python.exe scripts\run_worker.py
```

Use the full Compose path when you want to test container wiring. Use the host path when you want the shortest local iteration loop.

## Environment Variables

Common local variables:

| Variable | Default | Purpose |
|---|---:|---|
| `NOTEGEN_REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis queue backend. |
| `NOTEGEN_DB_PATH` | `data/notegen.db` | SQLite database path. |
| `NOTEGEN_COOKIE_SECURE` | `0` | Set to `1` only behind HTTPS. |
| `NOTEGEN_VERIFY_BASE` | `http://localhost:3000` | Base URL used in email verification links. |
| `NOTEGEN_SMTP_HOST` / `NOTEGEN_SMTP_USER` / `NOTEGEN_SMTP_PASS` | unset | SMTP settings for real email verification. |
| `NOTEGEN_AUTO_MAINTENANCE` | `1` | Set to `0` to stop startup/daily raw cleanup. |
| `NOTEGEN_AUTO_BACKUP` | `1` | Set to `0` to stop startup/daily backup. |
| `NOTEGEN_BACKUP_DIR` | `backups/` | Backup output directory. |
| `NOTEGEN_MIN_FREE_RATIO` | `0.15` | Disk low-water mark. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | API URL baked into the web build. |

## Health Check

Verify API and Redis:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Expected shape:

```json
{
  "ok": true,
  "redis": true,
  "queue_depth": 0,
  "disk": {
    "low": false
  }
}
```

Run the smoke script after all services are up:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_local.ps1
```

## Shutdown

Stop Docker Redis:

```powershell
docker compose down
```

Stop host API, worker, and web processes with `Ctrl+C` in their terminals.

If they were started in the background, find them with:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'server\.py|run_worker\.py|next' } |
  Select-Object ProcessId,CommandLine
```

Then stop a specific process:

```powershell
Stop-Process -Id <pid>
```

## Git Hygiene

Running the local stack can change runtime data:

- Redis writes to `data/redis`.
- API startup can create backups in `backups/`.
- maintenance can remove old files under `data/raw` and `data/audio`.

Before committing, check:

```powershell
git status --short
```

Do not include runtime data in a v1 code/docs commit unless that is the explicit intent.
