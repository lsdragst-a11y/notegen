# Local Smoke Test

This guide describes the v1 local smoke path for NoteGen. It verifies that the local stack is ready for a demo without running a full GPU video pipeline.

## What It Checks

`scripts/smoke_local.ps1` checks:

- Redis is reachable on `127.0.0.1:6379`.
- API health responds from `http://127.0.0.1:8000/api/health`.
- Exactly one root `scripts/run_worker.py` process is running.
- Public notes can be read.
- Optional login works when smoke credentials are provided.
- Private notes can be read after login.
- DOCX export returns a valid binary response.
- `web` can produce a production build unless `-SkipBuild` is passed.

The script does not enqueue a full video generation job and does not run the GPU-heavy pipeline.

## Prerequisites

- Windows PowerShell.
- Docker Desktop running.
- Python virtualenv installed at `.venv`.
- Frontend dependencies installed in `web/node_modules`.
- Redis, API, and one worker started.

Start the services in separate terminals:

```powershell
docker compose up -d redis
.\.venv\Scripts\python.exe server.py
.\.venv\Scripts\python.exe scripts\run_worker.py
cd web
npm run dev
```

For a release smoke where you do not want startup maintenance or automatic backups to change local data, start the API with:

```powershell
$env:NOTEGEN_AUTO_MAINTENANCE="0"
$env:NOTEGEN_AUTO_BACKUP="0"
.\.venv\Scripts\python.exe server.py
```

## Run The Smoke

Run the full smoke from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_local.ps1
```

Run a faster smoke that skips the web production build:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_local.ps1 -SkipBuild
```

Run against a different API base:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_local.ps1 -ApiBase http://127.0.0.1:8000
```

## Optional Login Check

Set a verified test account before running the script:

```powershell
$env:NOTEGEN_SMOKE_EMAIL="demo@example.com"
$env:NOTEGEN_SMOKE_PASSWORD="your-password"
powershell -ExecutionPolicy Bypass -File scripts\smoke_local.ps1
```

If these variables are not set, the login and private-notes checks are skipped with a warning. That warning is acceptable for an unauthenticated infrastructure smoke.

## Expected Result

A passing infrastructure smoke ends with:

```text
== Summary ==
Failures: 0
```

Warnings are acceptable when they are intentional, for example:

- login skipped because no smoke credentials were provided.
- web build skipped because `-SkipBuild` was passed.

## Manual Browser Checks

After the script passes, use the browser for the parts that require real UI interaction:

1. Open `http://localhost:3000/notebooks`.
2. Confirm public notes and the create-note entry render.
3. Open an existing note.
4. Confirm video playback and seeking.
5. Confirm chapter navigation and transcript highlighting.
6. Export Markdown.
7. Export Word.
8. Create or copy a share link and open `/s/{token}`.
9. If logged in, ask one QA question and confirm timestamp citations seek the video.

The current v1 demo artifacts are stored in `output/playwright/`:

- `v1-home.png`
- `v1-login-gate.png`
- `v1-workspace.png`
- `v1-demo.gif`
- `v1-export.docx`

## Troubleshooting

### Redis TCP Fails

Start Redis:

```powershell
docker compose up -d redis
```

### API Health Fails

Start the API from the repository root:

```powershell
.\.venv\Scripts\python.exe server.py
```

Then verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

### Worker Check Fails

Start exactly one worker:

```powershell
.\.venv\Scripts\python.exe scripts\run_worker.py
```

Do not run multiple workers on one GPU. The current v1 architecture assumes single-worker serial execution.

### DOCX Export Fails

Check that the API is running and that `python-docx` is installed in the virtualenv:

```powershell
.\.venv\Scripts\python.exe -c "import docx; print('ok')"
```

### Web Build Fails

Run the frontend checks directly:

```powershell
cd web
npm run lint
npm run test
npx tsc --noEmit
npm run build
```
