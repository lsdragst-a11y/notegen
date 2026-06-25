# 2026-06-25 v1 Demo Checkpoint

## Context

This memory records the v1 release-convergence pass after the Warm Fold UI work,
QA/export/share implementation, and local smoke automation work.

The goal was not to add more product surface. The goal was to make the current
project easier to verify, demonstrate, and roll back.

## Completed

- Cleared the active frontend lint baseline in `web/components/ChatPanel.tsx`
  and `web/lib/progress.ts`.
- Migrated the core workspace UI away from mixed legacy visual tokens:
  - `web/components/ChatPanel.tsx`
  - `web/components/NoteWorkspace.tsx`
  - `web/components/CreateNotePanel.tsx`
- Removed unused legacy visual components:
  - `web/components/AskBar.tsx`
  - `web/components/FluidBG.tsx`
  - `web/components/ParticleBG.tsx`
- Added `scripts/smoke_local.ps1` for repeatable local infrastructure smoke.
- Added release docs:
  - `CHANGELOG.md`
  - `docs/SMOKE_TEST.md`
  - `docs/DEPLOY_LOCAL.md`
- Linked the v1 checkpoint docs from `README.md`.
- Ignored generated backup zip files with `backups/*.zip`.

## Verification

Frontend verification passed after the code changes:

```powershell
cd web
npm run lint
npm run test
npx tsc --noEmit
npm run build
```

Results:

- ESLint completed with 0 errors.
- The remaining ESLint output was the existing warning baseline:
  - `<img>` usage warnings in image-heavy UI files.
  - One unused eslint-disable warning in `TranscriptPanel`.
- Vitest passed 6 files / 17 tests.
- TypeScript passed.
- Next production build passed.

Token migration scan passed for the migrated core surfaces:

```powershell
rg "var\(--(bg|fg|accent|border|shadow|on-accent)|apple-card|apple-button|tag-chip" `
  web\components\ChatPanel.tsx `
  web\components\NoteWorkspace.tsx `
  web\components\CreateNotePanel.tsx `
  web\app\notebooks `
  web\app\login `
  web\app\register `
  web\app\page.tsx -n
```

Result: no matches.

## Smoke Status

`scripts/smoke_local.ps1` passed earlier in this pass when Redis, API, and one
worker were running. It verified:

- Redis TCP availability.
- API `/api/health`.
- exactly one root worker process.
- public notes API.
- DOCX export.
- web production build.

After Redis was started again, the final rerun also passed:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_local.ps1
```

Result:

- Failures: 0
- Warnings: 1
- Warning: authenticated session was skipped because no
  `NOTEGEN_SMOKE_EMAIL` / `NOTEGEN_SMOKE_PASSWORD` credentials were provided.

Current honest status:

- Code-level v1 checkpoint verification is green.
- Automated local smoke exists and passes with Redis, API, and one worker.
- Authenticated login/private-notes smoke still needs configured smoke
  credentials.
- Browser walkthrough screenshots and a lightweight demo GIF are captured.

## Browser Walkthrough

After the automated smoke passed, a production Next server was started with
Redis, API, and one worker available. Playwright CLI was used at a 1440 x 1000
viewport.

Captured artifacts:

- `output/playwright/v1-home.png`
- `output/playwright/v1-login-gate.png`
- `output/playwright/v1-workspace.png`
- `output/playwright/v1-demo.gif`
- `output/playwright/v1-export.docx`

Validated:

- `/` loads with title `NoteGen · 教学视频结构化笔记`.
- `/notebooks` redirects unauthenticated users to `/login?next=%2Fnotebooks`.
- `/notes/BV141Ly6LE7x_p0` loads the three-column workspace.
- The source/chapter rail, note body, video panel, and tools panel render.
- The next-chapter control seeks the video to `01:07` and updates the current
  chapter card to `AI 订阅详情`.
- Word export downloads a DOCX file successfully.

Observed console errors:

- `401 Unauthorized` for `/api/auth/me` in unauthenticated mode.
- `401 Unauthorized` for `/api/bookmarks` in unauthenticated mode.

These match the current unauthenticated walkthrough. Authenticated notebooks,
bookmarks, share creation, and QA polling still require a configured smoke user.

## Worktree Notes

The expected code/docs changes are:

- `.gitignore`
- `README.md`
- `CHANGELOG.md`
- `docs/SMOKE_TEST.md`
- `docs/DEPLOY_LOCAL.md`
- `docs/memory/2026-06-25-v1-demo-checkpoint.md`
- `scripts/smoke_local.ps1`
- `web/components/ChatPanel.tsx`
- `web/components/CreateNotePanel.tsx`
- `web/components/NoteWorkspace.tsx`
- `web/lib/progress.ts`
- deleted `web/components/AskBar.tsx`
- deleted `web/components/FluidBG.tsx`
- deleted `web/components/ParticleBG.tsx`
- demo artifacts under `output/playwright/`

Runtime Redis files may also appear modified after local service runs:

- `data/redis/appendonlydir/appendonly.aof.1.incr.aof`
- `data/redis/dump.rdb`

Do not include those Redis runtime files in a code/docs checkpoint commit unless
the intent is to update repository-seeded Redis state.

## Next

1. Add smoke credentials and rerun authenticated smoke.
2. Commit code/docs and demo artifacts without Redis runtime state.
3. Tag or branch the resulting checkpoint as `v1.0.0-demo`.
