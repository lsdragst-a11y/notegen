# 2026-06-09 Enterprise Observability Memory

## Context

User wanted to continue the enterprise-grade optimization path for NoteGen. From the selected roadmap:

- Backendize bookmarks, notes, tasks; objectize file storage.
- Build a 30-video gold segmentation benchmark.
- Add pipeline stage metrics and failure tracking panel.
- Upgrade chapter segmentation into candidate boundaries + LLM rerank + rule validation.

We started with the smallest useful foundation: pipeline observability. Then continued into a user-facing failure tracking panel.

## Completed Change Set 1: Pipeline Stage Metrics

Backend:

- `src/jobqueue.py`
  - Added Redis-backed `metrics_json` on job hashes.
  - Added `stage_metrics(jid)`, `record_stage_start(jid, marker, now=None)`, and `finish_stage_metrics(jid, status="done", now=None)`.
  - `record_stage_start` closes the previous running stage when a new `[PROGRESS]` marker arrives.
  - Terminal `set_progress(... stage="done|failed|interrupted")` auto-closes the last running stage when metrics are not explicitly supplied.
  - `job_state()` now exposes parsed `metrics` and hides raw `metrics_json`.
  - SSE events can include `metrics`.

- `src/worker_tasks.py`
  - `_run_pipeline_subprocess` now records stage metrics whenever it parses a `[PROGRESS]` marker.
  - Existing percentage interpolation and progress messages remain unchanged.

- `src/progress.py`
  - Added missing label for `ocr_captions`: `OCR 识别`.

Frontend:

- `web/lib/api.ts`
  - Added/used `JobStageMetric` typing for SSE job events.

- `web/app/generate/page.tsx`
  - Added a compact `阶段耗时` panel on the generation page.
  - Shows stage number, label, duration, and `运行中` state.
  - Falls back to the most recent history event containing metrics if the current progress event does not include them.

Tests:

- `scripts/test_jobqueue.py`
  - Added coverage for stage metric start/finish, job state parsing, and terminal SSE event metrics.

Verification run:

- `.venv\Scripts\python.exe -m compileall -q server.py src`
- `.venv\Scripts\python.exe scripts\test_jobqueue.py`
- `.venv\Scripts\python.exe scripts\test_progress_marker.py`
- `.venv\Scripts\python.exe scripts\test_worker_integration.py`
- `npm run lint`
- `npm run build`

Result:

- All passed.
- `npm run lint` still reports only the pre-existing 5 `<img>` warnings.
- `scripts/test_worker_integration.py` prints an expected failure stack for the deliberate "no output" failed-registry case, but exits successfully.

## Completed Change Set 2: History Failure Tracking Panel

Backend:

- `server.py`
  - `/api/history` now enriches SQLite job history with Redis runtime snapshots when available.
  - Runtime snapshot fields:
    - `stage`
    - `percent`
    - `msg`
    - `returncode`
    - `metrics`
    - `log_tail` last 20 lines
  - If SQLite `error` is empty and Redis reports failed/interrupted/error, history uses the Redis message as the visible error.
  - Redis diagnostics are soft-fail:
    - If Redis is unavailable, history still returns SQLite rows.
    - If Redis fails once during a history request, the remaining rows skip Redis reads for that request.

- `src/jobqueue.py`
  - Added short Redis connection/response timeouts for KV/status reads:
    - `NOTEGEN_REDIS_CONNECT_TIMEOUT`, default `1.0`
    - `NOTEGEN_REDIS_KV_TIMEOUT`, default `2.0`
  - RQ Redis connection only gets connect timeout, avoiding accidental blocking timeout changes for worker queue behavior.

Frontend:

- `web/lib/types.ts`
  - Added shared `JobStageMetric`.
  - Added `JobRuntimeSnapshot`.
  - Added optional `runtime?: JobRuntimeSnapshot` on `HistoryItem`.

- `web/lib/api.ts`
  - Reuses shared `JobStageMetric` from `types.ts` instead of keeping a duplicate local definition.

- `web/app/history/page.tsx`
  - Reworked history into an operational task-health view.
  - Top summary:
    - `失败/中断`
    - `进行中`
    - `有诊断`
  - Per-job row still shows status, source, timestamp, retry, and note deep link.
  - Adds a `诊断` expandable section when useful:
    - Failed/interrupted tasks open by default.
    - Done tasks only show diagnostics when there is useful payload such as metrics/logs/non-zero return code.
  - Diagnostic contents:
    - Last stage and percent
    - Total metric duration
    - Slowest stage
    - Error message and return code
    - Last 10 stage metrics
    - Log tail

Tests:

- Added `scripts/test_history_diagnostics.py`
  - Creates isolated temp SQLite DB and fakeredis.
  - Verifies `/api/history` merges Redis runtime data into SQLite history.
  - Verifies Redis failed message fills missing SQLite error.
  - Verifies metrics, log tail, and returncode are exposed.
  - Verifies multi-user history isolation.

Verification run:

- `.venv\Scripts\python.exe -m compileall -q server.py src`
- `.venv\Scripts\python.exe scripts\test_history_diagnostics.py`
- `.venv\Scripts\python.exe scripts\test_multiuser_integration.py`
- `.venv\Scripts\python.exe scripts\test_review_fixes.py`
- `.venv\Scripts\python.exe scripts\test_jobqueue.py`
- `npm run lint`
- `npm run build`

Result:

- All passed.
- `npm run lint` still reports only the pre-existing 5 `<img>` warnings.
- `npm run build` passes with the existing Node `DEP0205` deprecation warning.

Browser smoke:

- Started temporary frontend/backend on `3001/8001` with a temp DB.
- Confirmed `/history` renders, shows a failed task, shows the diagnostics entry, and has no console errors.
- Temporary `3001/8001` processes were cleaned up.

## Current Working Tree Notes

At time of this memory write:

- Branch: `main...origin/main [ahead 2]`.
- Current tracked modified files from the second optimization:
  - `server.py`
  - `src/jobqueue.py`
  - `web/app/history/page.tsx`
  - `web/lib/api.ts`
  - `web/lib/types.ts`
- New untracked test file:
  - `scripts/test_history_diagnostics.py`
- Pre-existing untracked items intentionally not touched:
  - `data/notegen.db.e2ebak`
  - `web/public/notes/BV1L24y1i7v3_p0/`

## Completed Change Set 3: Backendized Bookmarks and Objectized Note Files

Backend:

- `src/db.py`
  - Added `bookmark_categories` table.
  - Added `bookmarks` table.
  - Both are scoped by `user_id`; bookmarks use `(user_id, key)` as primary key.

- `src/userdata.py`
  - Added `bookmarks_repo`.
  - Supports:
    - full bookmark state read
    - upsert/delete bookmark
    - upsert/rename/delete category
    - deleting a category detaches that category id from all of the user's bookmarks but keeps the bookmarks.

- `server.py`
  - Added authenticated bookmark APIs:
    - `GET /api/bookmarks`
    - `PUT /api/bookmarks`
    - `DELETE /api/bookmarks/{key}`
    - `PUT /api/bookmark-categories`
    - `PATCH /api/bookmark-categories/{category_id}`
    - `DELETE /api/bookmark-categories/{category_id}`
  - `/api/notes/{note_id}/file/{path}` now supports public and private DB-backed notes.
  - Private notes still require owner auth; public notes can be served via backend when present in `notes_repo`.

- `src/object_store.py`
  - Added local object-store adapter.
  - New storage refs use `local:...`.
  - Old raw filesystem paths remain supported.
  - Provides `storage_ref`, `resolve_ref`, `file_path`, and `delete_prefix`.

- `src/service_common.py`
  - `publish_private` now returns an object storage ref for `storage_path` instead of a raw path for new notes.

Frontend:

- `web/lib/bookmarks.ts`
  - Replaced localStorage-only implementation with backend-synced implementation.
  - Existing component API remains mostly unchanged.
  - localStorage remains optimistic cache and anonymous/offline fallback.
  - When backend state is empty but local cache has bookmarks/categories, local data is pushed to backend once, providing a lightweight migration path for old browser-only bookmarks.

- `web/lib/notes.ts`
  - `fetchCatalog()` is backend-first via `GET {API_BASE}/api/notes/public`.
  - Falls back to the old Next `/api/notes` static scan, then `public/notes/catalog.json`.
  - `fetchNote()` is backend file endpoint first via `{API_BASE}/api/notes/{id}/file/...`.
  - Falls back to static public note files when backend is unavailable or public notes have not been migrated into DB.

Tests:

- Added `scripts/test_bookmarks_backend.py`.
  - Covers category create/rename/delete.
  - Covers bookmark upsert/delete.
  - Covers category deletion preserving bookmarks while detaching category ids.
  - Covers multi-user bookmark isolation.

- Updated `scripts/test_publish_private.py`.
  - Resolves `local:` object refs through `object_store.resolve_ref`.
  - Verifies new private note storage paths are object refs.

Verification run:

- `.venv\Scripts\python.exe -m compileall -q server.py src scripts\test_bookmarks_backend.py`
- `.venv\Scripts\python.exe scripts\test_bookmarks_backend.py`
- `.venv\Scripts\python.exe scripts\test_publish_private.py`
- `.venv\Scripts\python.exe scripts\test_multiuser_integration.py`
- `.venv\Scripts\python.exe scripts\test_userdata_unit.py`
- `.venv\Scripts\python.exe scripts\test_worker_user_mirror.py`
- `.venv\Scripts\python.exe scripts\test_history_diagnostics.py`
- `.venv\Scripts\python.exe scripts\test_review_fixes.py`
- `npm run lint`
- `npm run build`
- `git diff --check`

Result:

- All passed.
- `npm run lint` still reports only the pre-existing 5 `<img>` warnings.
- `npm run build` still passes with the existing Node `DEP0205` deprecation warning.

Important behavior decisions:

- Bookmarks are now backend data, but localStorage is retained as offline/anonymous fallback rather than removed.
- The old localStorage bookmark state is opportunistically migrated into backend when an authenticated user with empty backend bookmark state loads bookmarks.
- Note file storage is objectized at the reference/adapter layer first. It is still local disk underneath, but callers no longer need to assume a raw filesystem path.
- Existing raw `notes.storage_path` values are intentionally supported for backward compatibility.

## Important Behavior Decisions

- Metrics are stored in Redis job hashes, not SQLite.
- History uses SQLite as source of truth and Redis only as optional runtime diagnostics.
- Redis failure must not break `/api/history`.
- Redis failure must not be retried once per row in the same history request.
- Failure diagnostics are intentionally visible to the owning user only because `/api/history` is behind `require_user` and rows are sourced from `jobs_repo.list_history(user["id"])`.

## Suggested Next Steps

1. Backendize bookmarks, notes, and tasks.
2. Move generated files behind an object-storage abstraction.
3. Add a durable `job_stage_metrics` table if stage metrics should survive Redis eviction/restart.
4. Build the 30-video gold segmentation benchmark.
5. Use the metrics and benchmark to guide the hybrid chapter splitting system: candidate boundaries + LLM rerank + rule validation.

## 2026-06-10 Local Validation Follow-up

Context:

- Validated the user's 7-change frontend/backend optimization batch locally.
- Target page: `http://localhost:3000/notes/BV19E411D78Q_p93_p0`.

Findings and fixes:

- `server.py`
  - Found backend note file endpoint returned `404` for public-note `video.mp4` while summary, chapters, metadata, and keyframes returned `200`.
  - Added public-note video fallback in `/api/notes/{note_id}/file/video.mp4` to serve `web/public/videos/{note_id}.mp4` when the object note directory does not contain `video.mp4`.
  - Verified with `curl.exe -r 0-10`: endpoint returns `206 video/mp4`.

- `web/components/NavBar.tsx`
  - Found nav middle slot overflow on the in-app browser viewport: the note-page search button visually overlapped the right-side bookmarks link, so clicking search navigated to `/bookmarks`.
  - Added `overflow-hidden` to the NavBar children slot.

- `web/app/notes/[id]/page.tsx`
  - Kept the new `ChapterChip` integration and cancellation guard.
  - Changed the visible search button breakpoint from `sm` to `lg` so narrow desktop widths use the keyboard shortcut instead of overlapping nav actions.

- `web/components/Spotlight.tsx`
  - Found English mode still showed Chinese result type labels (`章节`, `知识点`, `术语`) and Chinese search placeholder.
  - Localized result type labels, placeholder, empty state, footer hints, and result count.
  - Key-point details now prefer `keywords_en` in English mode.
  - English glossary snippets that only have CJK fallback text now degrade to `Appears N times`.

Browser validation:

- NavBar unauthenticated state shows `登录` / `注册` with no console errors.
- Public note files load through backend object-file endpoint.
- Keyframes render from backend note file paths.
- Ctrl+K opens Spotlight after the nav-overlap fix.
- In English mode, searching `HTTP` shows:
  - `Search chapters / key points / terms...`
  - `HTTP Appears 6 times Term`
  - `Chapter`, `Key point`, `Term`, `Navigate`, `Jump`, and `items` labels.
- In-app browser could not trigger actual media playback despite:
  - video endpoint returning `206 video/mp4`;
  - video element `readyState=4`;
  - correct Play button hit target from `elementFromPoint`.
  - Chrome extension connector was unavailable, so the dynamic `ChapterChip` play-state animation still needs a manual Chrome check.

Verification run:

- `.venv\Scripts\python.exe -m py_compile server.py src\jobqueue.py src\worker_tasks.py`
- `.venv\Scripts\python.exe scripts\test_jobqueue.py`
- `.venv\Scripts\python.exe scripts\test_worker_integration.py`
- `cd web; npx tsc --noEmit`
- `git diff --check -- server.py web\components\NavBar.tsx web\app\notes\[id]\page.tsx web\components\Spotlight.tsx`

Result:

- All commands passed.
- `test_worker_integration.py` still prints the expected RQ traceback for the intentionally simulated no-output failure path, but exits `0`.
- `git diff --check` only emitted CRLF normalization warnings for touched files.

## 2026-06-10 P0 Redesign Validation

Context:

- Validated the user's P0 redesign batch after homepage/token/nav cleanup.
- Local services already running:
  - frontend: `http://localhost:3000`
  - backend: `http://localhost:8000`

Validation results:

- `cd web; npx tsc --noEmit` passed.
- Unauthenticated homepage showed the compact public-example entry with login/register navigation and no console errors.
- `/dashboard` redirects to `/`.
- `/library` redirects to `/`.
- Created and verified temporary account `p0test+8fa6a06c@example.com` for browser validation.
- After login, homepage became the notebook library:
  - nav showed user menu (`P0 Test`) and bookmarks badge;
  - `全部` showed 36 notebooks;
  - `我的` showed the private-empty state;
  - `公开示例` showed the public notebook set.
- `新建笔记本` opened the modal and reused `CreateNotePanel` without the old macOS fake window header.
- Bilibili URL probe succeeded for `BV19E411D78Q?p=93` and showed the resolved title/uploader/duration/quality buttons.

Finding and fix:

- Submit from the create modal reached `POST /api/generate`, but Redis was unavailable on this machine.
- Initial behavior was `500 Internal Server Error` because Redis `TimeoutError` was not caught by the narrower `ConnectionError` handlers.
- Updated `server.py` enqueue endpoints (`/api/generate`, `/api/upload`, `/api/jobs/{id}/retry`) to catch `_redis_pkg.exceptions.RedisError`.
- Restarted the local API and verified the same generate request now returns:
  - status: `503`
  - body: `{"detail":"队列服务暂不可用，请稍后再试"}`
- Docker is not installed/in PATH on this machine, so Redis could not be started locally and the final `/generate?job=...` navigation could not be fully verified.

Dark-mode checks:

- Dark theme applied with body background `rgb(31, 31, 32)` and accent `#8ab4f8`.
- Measured contrast ratios:
  - bookmark link: `8.18:1`
  - bookmark badge: `6.12:1`
  - active filter chip: `5.95:1`
  - inactive filter chip: `9.10:1`
  - create notebook card: `9.10:1`
  - user menu button: `8.18:1`
- Browser console had no `error` or `warn` entries after homepage/filter/dark-mode checks.

## 2026-06-11 Auth Verification Follow-up

Context:

- User reported login/register screenshots showing:
  - register initially failed while backend was not listening on `localhost:8000`;
  - after backend restart, login failed with the expected unverified-email message;
  - navbar still showed the stale `服务离线` badge.

Findings and fixes:

- Started the local FastAPI backend on `127.0.0.1:8000`.
- Confirmed `lsdragst@gmail.com` existed in `data/notegen.db` with `email_verified=0`.
- Found its pending dev verification token in `.codex-run/api.out.log`.
- Called `/api/auth/verify` with that token; the account is now `email_verified=1` and the token row was consumed.
- `web/components/AuthContext.tsx`
  - Login now clears `offline` when the backend returns an HTTP business error such as `403`.
  - Network/API reachability failures still set `offline=true`.
- `web/app/register/page.tsx`
  - Registration success now calls `refresh()` so a stale offline badge clears without a manual page reload.

Verification run:

- `cd web; npx tsc --noEmit`
- `git diff --check -- web\components\AuthContext.tsx web\app\register\page.tsx`

Result:

- TypeScript passed.
- `git diff --check` only emitted CRLF normalization warnings.
- Redis is still unavailable, so queue/generate flows can still return `503` until Redis is started.
