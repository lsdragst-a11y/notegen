# 2026-06-14 Current State and Next Steps Memory

## Context

The user asked to analyze the whole project memory/files, update project memory,
and decide what to optimize next.

This memory supersedes the "Current Working Tree Notes" section in
`docs/memory/2026-06-09-enterprise-observability.md`. The 2026-06-09 file remains
useful as historical context for observability, bookmarks, objectized note files,
and earlier validation, but its working-tree snapshot is stale.

## Repository Shape

Product shape:

- Python/FastAPI backend in `server.py` plus `src/`.
- RQ/Redis queue backend with one Windows `SimpleWorker`.
- Next.js App Router frontend in `web/`.
- GPU-heavy offline pipeline in `src/pipeline.py`.
- Local model copies under `models/`.
- Generated/demo data under `data/` and `web/public/`.

Largest code areas:

- `src/segment_llm.py`: 3539 lines. Main LLM prompting, validation, repair,
  title/recap/quiz generation, ASR mask handling, and segmentation logic.
- `src/pipeline.py`: 1711 lines. End-to-end video pipeline orchestration.
- `src/summarize.py`: 934 lines. Chunking and summary utilities.
- `server.py`: 672 lines. Auth, jobs, notes, bookmarks, sharing, export, QA,
  health, maintenance, backup startup loop.
- `web/components/NoteWorkspace.tsx`: 592 lines. Shared `/notes/[id]` and
  `/s/[token]` three-column workspace.
- `web/components/CreateNotePanel.tsx`: 395 lines. URL/upload generation panel.
- `web/components/ChatPanel.tsx`: 232 lines. QA UI.

The frontend redesign has moved past the older `docs/frontend-redesign.md` plan:
QA is no longer just an `AskBar` placeholder. `ChatPanel`, share links, and Word
export are implemented.

## Disk Snapshot

Snapshot from `E:\claudeproject\notegen`:

- Total project files: 82,803.
- Total project size: about 31.62 GB.
- `models/`: 17.92 GB.
- `.venv/`: 5.79 GB.
- `web/`: 5.33 GB.
- `wheels/`: 2.32 GB.
- `data/`: 591.81 MB.
- `.git/`: 254.74 MB.
- `backups/`: 154.46 MB.

Largest model directories:

- `models/Qwen2.5-VL-7B-Instruct-AWQ`: 6.62 GB.
- `models/Qwen2.5-7B-Instruct-AWQ`: 5.32 GB.
- `models/faster-whisper-large-v3`: 2.95 GB.
- `models/chinese-clip-vit-base-patch16`: 1.44 GB.
- `models/Randeng-Pegasus-238M-Summary-Chinese`: 1.13 GB.

Largest frontend/runtime data:

- `web/public/videos`: 3.82 GB.
- `web/public/notes`: 112.63 MB.
- `web/.next`: 940.3 MB.
- `web/node_modules`: 449.73 MB.

Largest `data/` areas:

- `data/outputs`: 397.55 MB.
- `data/user_notes`: 73.74 MB.
- `data/raw`: 69.8 MB.
- `data/audio`: 47.04 MB.
- `data/redis`: 0.22 MB.
- `data/notegen.db`: 0.11 MB.

Disk health:

- Drive E has about 281.17 GB free, 30.9% free.
- This is above the configured 15% low-disk rejection threshold.

## Current Git State

Branch:

- `main`.

Dirty state summary:

- 45 tracked modified files.
- 2 tracked deleted files: `data/audio/.gitkeep`, `data/raw/.gitkeep`.
- 119 untracked paths.

Tracked diff size:

- 47 files changed.
- 1709 insertions.
- 1757 deletions.

Important tracked modified areas:

- Backend/API and service layer:
  - `README.md`
  - `docker-compose.yml`
  - `requirements.txt`
  - `server.py`
  - `scripts/run_worker.py`
  - `src/accounts.py`
  - `src/db.py`
  - `src/download.py`
  - `src/jobqueue.py`
  - `src/pipeline.py`
  - `src/progress.py`
  - `src/segment_llm.py`
  - `src/service_common.py`
  - `src/summarize.py`
  - `src/userdata.py`
  - `src/worker_tasks.py`

- Frontend:
  - `web/app/page.tsx`
  - `web/app/notes/[id]/page.tsx`
  - `web/app/generate/page.tsx`
  - `web/app/history/page.tsx`
  - `web/app/library/page.tsx`
  - `web/components/NavBar.tsx`
  - `web/components/NotesContent.tsx`
  - `web/components/Spotlight.tsx`
  - `web/lib/api.ts`
  - many supporting pages/components.

Important untracked areas:

- `.dockerignore`, `.github/`, `docker/`.
- `docs/ROADMAP.md`, `docs/frontend-redesign.md`, `docs/memory/`.
- `src/backup.py`, `src/embeddings.py`, `src/logging_setup.py`,
  `src/mailer.py`, `src/maintenance.py`, `src/platform_meta.py`, `src/qa.py`,
  `src/ratelimit.py`, `src/asr_votefix.py`.
- Many test files under `scripts/test_*.py`.
- New frontend routes/components:
  - `web/app/notebooks/`
  - `web/app/s/`
  - `web/components/NoteWorkspace.tsx`
  - `web/components/ChatPanel.tsx`
  - `web/components/CreateNotePanel.tsx`
  - `web/lib/export.ts`
  - `web/lib/progress.ts`.
- Gold benchmark data under `data/gold/`.
- Runtime data under `data/redis/`, `backups/`.

Do not assume the old 2026-06-09 memory's working-tree list is still accurate.
The current tree contains a much larger implementation batch.

## Implemented Capabilities Observed

Backend/service:

- Multi-user auth with email verification and sessions.
- Redis/RQ default queue for generation.
- High-priority QA queue (`qa`) before the default queue, still single-worker
  serial execution.
- Job stage metrics in Redis.
- Runtime diagnostics merged into `/api/history`.
- Bookmark categories and bookmarks backendized, with frontend localStorage
  fallback/sync.
- Private notes with `local:` object-store refs.
- Public/private note file serving through backend endpoints.
- Share tokens:
  - `POST /api/notes/{note_id}/share`
  - `GET /api/notes/{note_id}/share`
  - `DELETE /api/notes/{note_id}/share`
  - `GET /api/shared/{token}`
  - `GET /api/shared/{token}/file/{path}`.
- Word export:
  - `POST /api/export/docx`.
- QA:
  - `POST /api/notes/{note_id}/ask`
  - `GET /api/qa/{qa_id}`.
- Hardening:
  - Upload size cap.
  - Low-disk rejection.
  - Login/register rate limiting.
  - SMTP verification when configured.
  - Daily maintenance loop.
  - Daily backup loop.
  - Log setup with fallback.

Pipeline:

- Platform metadata shortcuts:
  - creator CC subtitles can skip ASR.
  - platform chapters can anchor segmentation.
- bge-m3 embeddings:
  - chunk embeddings written beside outputs.
  - QA hybrid BM25 + dense RRF when embeddings exist.
  - `--chunker semantic` available for benchmark comparison, with fallback.
- Existing VRAM discipline is important and should be preserved:
  - single worker.
  - unload QA model before pipeline jobs.
  - clear Whisper/Pegasus/CLIP before loading Qwen.
  - clear other models before loading VLM.

Frontend:

- `/` is a compact landing page.
- `/notebooks` is the logged-in notebook library.
- `/dashboard` and `/library` redirect to `/notebooks`.
- `/notes/[id]` uses `NoteWorkspace`.
- `/s/[token]` uses `NoteWorkspace` in shared read-only mode.
- Workspace includes video, chapter rail, transcript, notes, bookmarks,
  progress, export, sharing, Spotlight, and ChatPanel QA.

## Validation Run on 2026-06-14

Commands run:

- PowerShell-expanded Python compile:
  - `.venv\Scripts\python.exe -m py_compile server.py src/*.py scripts/test_*.py scripts/md_to_docx.py scripts/run_worker.py`
  - Result: passed after expanding wildcards in PowerShell.
- No-GPU unit test subset:
  - `scripts/test_service_common.py`
  - `scripts/test_jobqueue.py`
  - `scripts/test_qa_unit.py`
  - `scripts/test_accounts_unit.py`
  - `scripts/test_userdata_unit.py`
  - `scripts/test_shares_unit.py`
  - `scripts/test_auth_api.py`
  - `scripts/test_export_unit.py`
  - `scripts/test_maintenance_unit.py`
  - `scripts/test_ratelimit_unit.py`
  - `scripts/test_mailer_unit.py`
  - `scripts/test_backup_unit.py`
  - `scripts/test_platform_meta_unit.py`
  - `scripts/test_retrieval_hybrid_unit.py`
  - `scripts/test_votefix_unit.py`
  - `scripts/test_quality_filters_unit.py`
  - `scripts/test_hardening_api.py`
  - Result: all passed.
- Frontend type check:
  - `cd web; npx tsc --noEmit`
  - Result: passed.

Notes:

- The first compile attempt using literal `src\*.py` failed on Windows with
  `Invalid argument`; this was a command shape issue, not a code issue.
- No full GPU pipeline or browser smoke was run in this pass.
- No local project server/worker/Next dev process was running during the process
  snapshot.
- GPU snapshot: RTX 4080 Laptop GPU, 12 GB class; about 1.4 GB used and about
  10.6 GB free at inspection time. This was not NoteGen workload.

## Main Risks

1. Worktree sprawl is now the biggest project risk.

   The repo contains a large, mostly coherent implementation batch, but many
   important files are still untracked. A clean release/commit split should happen
   before more feature work. Otherwise later changes will be hard to review,
   bisect, or safely publish.

2. Docs are behind implementation.

   `docs/frontend-redesign.md` still describes QA as an AskBar/placeholder in
   places, while `ChatPanel`, backend QA, sharing, and export are already present.
   `docs/ROADMAP.md` still lists some Stage C items as future work even though
   they are implemented or mostly implemented.

3. Browser validation is still the largest unknown.

   TypeScript passes, but the real value is the interactive workspace: video
   seeking, chapter rail, transcript sync, shared read-only route, share copy,
   docx download, and ChatPanel polling. These need a fresh browser smoke after
   Redis/API/web are running.

4. Runtime orchestration still depends on Redis and one worker.

   This is intentional, but demos must make Redis startup obvious. If Redis is
   down, generate/retry/upload correctly return 503, but an evaluator may read
   that as broken if the README/demo flow is not crisp.

5. Frontend cleanup is partly complete but not fully reconciled.

   `FluidBG.tsx` and `ParticleBG.tsx` still exist. They may no longer be used in
   the new product flow, but should be confirmed before deleting. Old routes now
   redirect, which is okay.

6. Data/demo asset strategy is still heavy.

   `web/public/videos` is 3.82 GB. That is acceptable locally but poor for a
   public repo/deploy story. The `.gitignore` excludes it, but the demo/deploy
   handoff should say clearly how example videos are supplied.

7. Redis-backed metrics are not durable.

   This was an explicit earlier decision. It is acceptable for live diagnostics,
   but if stage analytics become a product feature or benchmark input, add a
   SQLite `job_stage_metrics` table.

## Best Next Optimization

Best next move: **release stabilization and documentation reconciliation**, not
another feature.

Why this is the best return:

- Core features already exist: accounts, generation queue, private notes,
  sharing, export, bookmarks, QA, diagnostics, backups, maintenance.
- The main uncertainty is whether the whole thing is cleanly reproducible and
  easy to demo from a fresh checkout/startup.
- Cleaning this up will protect the large batch already in the tree and make
  every later optimization cheaper.

Recommended order:

1. Create a release checkpoint branch/commit set.

   Split the current batch into reviewable commits if possible:

   - service hardening and CI
   - auth/users/notes/jobs/bookmarks/shares
   - frontend NotebookLM redesign
   - QA/export/share
   - pipeline quality upgrades and benchmark data
   - docs/memory

   If splitting is too expensive, at least stage intentionally and make one
   coherent "v1 app hardening" commit after validating.

2. Update docs to match reality.

   Minimum doc fixes:

   - `docs/ROADMAP.md`: mark QA/export/share as implemented or mostly
     implemented; move remaining work to validation/deploy.
   - `docs/frontend-redesign.md`: replace AskBar placeholder language with
     ChatPanel status; mark P0/P1/P2 actual completion state.
   - README: add a "Demo startup checklist" with Redis/API/worker/web order,
     expected health checks, and common 503 cause.

3. Run an end-to-end local smoke.

   With Redis, API, worker, and web running:

   - register/login
   - create or open notebook
   - confirm `/notebooks`
   - confirm `/notes/[id]`
   - video seek by chapter and citation
   - bookmark and category sync
   - export Markdown and Word
   - create/revoke share link
   - open `/s/[token]`
   - ask one QA question on a note with embeddings
   - confirm `/history` diagnostics

4. Clean or document runtime artifacts.

   - Restore `.gitkeep` files if needed, or stop tracking them intentionally.
   - Keep `data/redis`, `backups`, videos, and generated runtime files untracked.
   - Confirm `.gitignore` protects secrets and heavy local artifacts.

5. Then choose the next product optimization.

   After stabilization, the highest-value product polish is likely:

   - "Demo polish": screenshots/GIF, first-run sample notebook, clearer empty
     states, and a short demo script.
   - "QA quality": citations, suggested questions, and handling "not in video"
     cases with confidence.
   - "Durable metrics": SQLite table for stage metrics only if diagnostics or
     benchmark reporting needs history across Redis restarts.

Do not prioritize Kubernetes, multi-worker, object storage cloud migration, or
multi-tenant billing. The current single-GPU/single-worker design is intentional
and aligned with the roadmap.

## Suggested Immediate Checklist

- [ ] Decide whether to keep this batch as one commit or split it.
- [ ] Update roadmap/frontend redesign docs to match implemented state.
- [ ] Run full local smoke with Redis/API/worker/web.
- [ ] Make one browser validation note in `docs/memory/`.
- [ ] Only then start another feature or quality pass.

## 2026-06-15 Stabilization Pass

Context:

- User said to proceed with the recommended release-stabilization path.
- This pass intentionally avoided business-code changes.

Changes made:

- `docs/ROADMAP.md`
  - Added a current "v1 release stabilization" priority section.
  - Marked video QA, Word export, and public share links as implemented.
  - Moved the next milestone from feature buildout to cleanup, docs, smoke,
    and demo assets.

- `docs/frontend-redesign.md`
  - Added 2026-06-15 status note.
  - Updated `/` vs `/notebooks` reality: `/` is compact landing, `/notebooks`
    is the logged-in notebook library.
  - Replaced stale AskBar/placeholder language with real `ChatPanel` status.
  - Marked P0/P1 as mostly done and P2 as browser/a11y cleanup.
  - Recorded that `FluidBG`, `ParticleBG`, and `AskBar` should be deleted only
    after confirming no references remain.

- `README.md`
  - Added a demo startup checklist for Redis, API, worker, web, health, login,
    notebook open, exports, share links, QA, and history diagnostics.
  - Added common failure notes for Redis 503, low-disk 507, stale frontend API
    base, and GPU OOM.
  - Added `test_votefix_unit.py` and `test_quality_filters_unit.py` to the
    documented no-GPU test list.

- `data/raw/.gitkeep` and `data/audio/.gitkeep`
  - Restored as zero-byte tracked placeholders, removing two noisy deleted
    entries from `git status`.

Validation run:

- PowerShell-expanded Python compile passed:
  - `server.py`
  - all `src/*.py`
  - all `scripts/test_*.py`
  - `scripts/md_to_docx.py`
  - `scripts/run_worker.py`
- No-GPU test subset passed:
  - `test_service_common.py`
  - `test_jobqueue.py`
  - `test_qa_unit.py`
  - `test_accounts_unit.py`
  - `test_userdata_unit.py`
  - `test_shares_unit.py`
  - `test_auth_api.py`
  - `test_export_unit.py`
  - `test_maintenance_unit.py`
  - `test_ratelimit_unit.py`
  - `test_mailer_unit.py`
  - `test_backup_unit.py`
  - `test_platform_meta_unit.py`
  - `test_retrieval_hybrid_unit.py`
  - `test_votefix_unit.py`
  - `test_quality_filters_unit.py`
  - `test_hardening_api.py`
- Frontend type check passed:
  - `cd web; npx tsc --noEmit`

Remaining next step:

- Run full browser smoke with Redis/API/worker/web. This was not done in this
  pass because it requires starting the full local stack and exercising the app
  interactively.

Follow-up smoke completed in the same stabilization pass:

- Docker CLI exists, but Docker Desktop's Linux engine was not running, so
  Redis/container smoke could not start from `docker compose`.
- Started a temporary FastAPI process with:
  - `NOTEGEN_DB_PATH=.codex-run/smoke-notegen.db`
  - `NOTEGEN_AUTO_MAINTENANCE=0`
  - `NOTEGEN_AUTO_BACKUP=0`
  - short Redis timeouts
- API smoke passed:
  - `/api/health` returned `redis=false` as expected without Redis.
  - Register, email-token verification, login, and `/api/auth/me` passed.
  - `/api/notes/mine` and `/api/notes/public` returned empty arrays against the
    temporary DB.
  - `/api/generate` returned 503 without Redis, matching the graceful
    queue-unavailable path.
- Started Next dev on `127.0.0.1:3000` with the temporary API base and checked
  routes via `curl.exe`.
  - `/`, `/login`, `/register`, `/notebooks`, `/dashboard`, `/bookmarks`,
    `/history`, `/generate`, `/notes/BV141Ly6LE7x_p0`, and `/api/notes` all
    returned HTTP 200.
- Production frontend build passed:
  - `cd web; npm run build`
  - Next reported only a Node deprecation warning for `module.register()`.
- Temporary API and web processes were stopped afterward; ports 3000 and 8000
  were no longer listening.

Remaining release smoke gap:

- Start Redis and the GPU worker, then run one real queue-backed job/QA flow:
  - create or open a real notebook,
  - ask one QA question with embeddings,
  - verify citations, bookmarks, Word/Markdown export, share create/revoke,
    `/s/[token]`, and `/history` diagnostics in a browser.

## 2026-06-16 Full-Chain Browser Smoke

Context:

- User asked to run a real notebook + QA + export + share browser smoke.
- Used temporary state only:
  - SQLite: `.codex-run/smoke-fullchain.db`
  - Redis: `redis://127.0.0.1:6379/15`
  - Note directory: `.codex-run/smoke-note/smoke_BV141Ly6LE7x_p0`
- Redis compose container was already running. API/worker/web were started for
  the smoke and stopped afterward.

Setup:

- Created verified smoke user:
  - `codex-fullchain@example.test`
- Copied existing demo note `BV141Ly6LE7x_p0` into a temporary private
  notebook with video file included:
  - note id `smoke_BV141Ly6LE7x_p0`
  - title `Google 发布 Gemini 3.5 Flash 模型【AI 早报 2026-05-20】`
- Started:
  - FastAPI on `127.0.0.1:8000`
  - RQ SimpleWorker listening on `qa` + `default`
  - Next dev server on `127.0.0.1:3000`

Browser smoke results:

- Login:
  - Logged in as the smoke user.
  - `/notebooks` loaded and showed the temporary private notebook under
    "我的笔记本".
- Notebook workspace:
  - Opened `/notes/smoke_BV141Ly6LE7x_p0`.
  - Backend served `summary.json`, `chapters.json`, `meta.json`, keyframes, and
    `video.mp4` through `/api/notes/{id}/file/...`.
  - Video range requests returned HTTP 206.
- QA:
  - Asked `这个视频最核心的结论是什么？`.
  - Worker loaded local `models/Qwen2.5-7B-Instruct-AWQ` and completed the job.
  - Browser showed an answer with timestamp citation `00:00`.
  - Asked follow-up `Wear OS 7 提升了什么？`.
  - Second QA completed quickly with the resident model and showed citation
    `05:45`.
  - Clicking the `05:45` citation moved the video currentTime to about
    `345.7s`.
- Export:
  - Clicked `导出 Markdown` and `导出 Word` in the browser.
  - The in-app browser cannot capture download events, but both button clicks
    completed without UI error.
  - Backend logged `POST /api/export/docx` as HTTP 200 and `md_to_docx` created
    the temporary `.docx`.
- Share:
  - Clicked `生成分享链接`; clipboard received:
    `http://127.0.0.1:3000/s/4zYW_2dA3DmnxpjkR4vLGg`
  - Opened `/s/4zYW_2dA3DmnxpjkR4vLGg`.
  - First load took about 17.7s due to Next compiling the dynamic route; second
    load was about 41ms.
  - Shared page loaded title, video tools, Markdown/Word export buttons, and
    shared backend files through `/api/shared/{token}/file/...`.
  - Shared page did not show QA input or share button.

Observed issue:

- Shared page snapshot still contained chapter-level `加入书签` controls. The
  right-side bookmark entry is hidden in shared mode, but chapter detail
  bookmark buttons appear to remain visible. This should be checked/fixed if
  shared pages are intended to be fully read-only and unauthenticated.

Cleanup:

- Stopped the API, worker, and web processes started for the smoke.
- Flushed Redis DB 15.
- Removed temporary smoke DB, copied note/video directory, and smoke logs.
- Left the existing Redis compose container running because it was already
  running before this smoke pass.
