# Changelog

All notable project changes are tracked here.

## v1.0.0-demo - 2026-06-25

This is the first demo checkpoint for a reproducible local NoteGen release. The goal is not feature expansion; it is a stable version that can be built, smoked, demonstrated, and rolled back.

### Added

- Added `scripts/smoke_local.ps1` for local release smoke checks:
  - Redis TCP availability.
  - API `/api/health`.
  - single worker process check.
  - public notes API.
  - optional login and private notes check.
  - DOCX export endpoint.
  - production web build.
- Added local release documentation:
  - `docs/SMOKE_TEST.md`
  - `docs/DEPLOY_LOCAL.md`
- Added v1 demo artifacts under `output/playwright/`:
  - `v1-home.png`
  - `v1-login-gate.png`
  - `v1-workspace.png`
  - `v1-demo.gif`
  - `v1-export.docx`

### Changed

- Migrated the core QA entry in `web/components/ChatPanel.tsx` from legacy `--bg` / `--fg` / `--accent` tokens to Warm Fold `--wf-*` tokens.
- Migrated the `/notes/[id]` workspace shell in `web/components/NoteWorkspace.tsx` to Warm Fold tokens for error state, skeleton state, top controls, right-side tools, and the mobile chapter drawer.
- Migrated `web/components/CreateNotePanel.tsx`, used by `/notebooks`, from legacy tokens and `apple-button` to Warm Fold tokens.
- Reworked `web/lib/progress.ts` to read chapter progress through `useSyncExternalStore`, keeping localStorage behavior while clearing the React hooks lint baseline.
- Removed unused legacy visual components after confirming no runtime references:
  - `web/components/AskBar.tsx`
  - `web/components/FluidBG.tsx`
  - `web/components/ParticleBG.tsx`

### Fixed

- Cleared blocking ESLint errors in:
  - `web/components/ChatPanel.tsx`
  - `web/lib/progress.ts`
- Adjusted local smoke worker detection for Windows virtualenv behavior, where a venv shim and the real Python child process can both contain `run_worker.py` in their command line.
- Adjusted DOCX smoke verification to use `Invoke-WebRequest -UseBasicParsing`, avoiding a Windows PowerShell null-reference failure on binary responses.

### Verified

Latest verified local commands:

```powershell
cd web
npm run lint
npm run test
npx tsc --noEmit
npm run build
```

Latest local smoke command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_local.ps1
```

Smoke result at checkpoint time:

- Failures: `0`
- Warnings: login skipped unless `NOTEGEN_SMOKE_EMAIL` and `NOTEGEN_SMOKE_PASSWORD` are provided.

### Known Baseline

- `npm run lint` exits successfully but still reports non-blocking warnings for existing `<img>` usage and one unused ESLint disable directive outside the files touched for this checkpoint.
- Learning progress is still localStorage-backed, not account-synchronized.
- Full GPU video generation is intentionally not part of the automated smoke script; the script checks service readiness and lightweight API behavior.
