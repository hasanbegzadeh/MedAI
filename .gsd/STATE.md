---
updated: 2026-04-11T12:00:00Z
---

# Project State

## Current Position

**Milestone:** RadAI Phase 0-3
**Phase:** Phase 0 - Backend Infrastructure (VERIFIED)
**Status:** Phase 0 complete and end-to-end verified (4/4 critical checks green)
**Plan:** Enter Phase 1 — real LiteMedSAM + OHIF extension scaffold + E2E segmentation

## Last Action

Phase 0 brought fully green against running Docker Compose stack:
- Backend Docker image rebuilt with CUDA 12.8 + PyTorch 2.10.0+cu128
  (torch.cuda.is_available() confirmed from inside radai-backend, sees
  RTX 5060 at sm_120, 7.3 GB free VRAM)
- Fixed 4 cascading backend startup crashes:
  1. UUID NameError from `from __future__ import annotations` x slowapi globals
     swap (now-documented in ai.py / reports.py / voice.py headers)
  2. Missing email-validator for pydantic[email]
  3. `SlowAPIMiddleware(limiter=...)` kwarg is not accepted — middleware reads
     the limiter off `app.state.limiter`
  4. `/voice/transcribe` missing `Request` parameter required by `@limiter.limit`
- Fixed bcrypt 5.x incompatibility with passlib 1.7.4 by pinning `bcrypt<4.1`
- Added `backend/scripts/seed_admin.py` — idempotent seed/reset for the
  default admin (admin / changeme) so `make verify` is deterministic from a
  clean stack. Wired into Makefile as `make seed-admin`, and `make verify`
  depends on it.
- Backend `/health` endpoint returns `{"status": "ok", "checks": {"api": "ok",
  "database": "ok", "redis": "ok", "ollama": "ok"}}`
- `python scripts/verify_phase_0.py` reports **All critical checks passed (4/4)**

**Commits made (this session and prior):**
1. `1a4e4e0` Fix: drop pydicom-seg, bump pydicom to 3.x for highdicom compat
2. `f3ef4f0` fix(slowapi): resolve PEP 563 annotation compatibility with slowapi
3. `e637ab6` fix(scheduler): remove duplicate _is_retryable_openrouter_error
4. `542a277` docs(gsd): establish GSD workflow artifacts for RadAI project
5. `2e11b34` fix(phase-0): pin bcrypt<4.1 and add admin seed script

## Next Steps (Phase 1)

1. Plan 1.1 — LiteMedSAM: replace `app/ai/medsam_lite.py` mock with
   a real lightweight SAM checkpoint + inference path, VRAM-gated.
2. Plan 1.2 — DICOM pipeline E2E: upload test CT via `upload_test_dicom.py`
   → converter.py → TotalSegmentator v2.13.0 → seg_export.py → DICOM-SEG
   round-tripped back into Orthanc.
3. Plan 1.3 — OHIF extension skeleton: `@radai/extension-ai-panel` custom
   extension with "Run AI" / "Refine" buttons hitting `/api/v1/ai/studies/
   {study_id}/run` and streaming progress from `/ws/ai/jobs/{job_id}`.
4. Plan 1.4 — nnInteractive click-refine round trip (clicks from OHIF tool →
   API → nninteractive.py → updated mask overlay in OHIF).

## Active Decisions

| Decision | Choice | Made | Affects |
|----------|--------|------|---------|
| GSD methodology adopted | SPEC→PLAN→EXECUTE→VERIFY→COMMIT | 2026-04-11 | All future work |
| Phase 0 scope finalized | No new features, only verification | 2026-04-11 | Phase 0 |
| LiteMedSAM priority | Replace mock before Phase 1.2+ | 2026-04-11 | Phase 0/1 boundary |
| bcrypt pinned <4.1 | keep passlib 1.7.4 compatible, defer bcrypt 5 migration | 2026-04-11 | Auth subsystem |
| Admin seed script | idempotent, env-overridable, runs in verify target | 2026-04-11 | dev/CI bootstrap |
| slowapi + PEP 563 | never combine `from __future__ import annotations` with `@limiter.limit` on endpoints using module-level types | 2026-04-11 | all API routers |

## Blockers

- [ ] No blockers. All Phase 0 verification checks pass against the live stack.

## Concerns (unchanged)

- LiteMedSAM still uses a mock implementation — does not defeat any Phase 0
  tests but will block Plan 1.1 start.
- DICOM converter.py / anonymizer.py / seg_export.py exist but have not been
  exercised on a real CT series yet. First end-to-end run will happen in
  Plan 1.2.
- Celery queue has no end-to-end smoke yet — `/ai/studies/{id}/run` uses
  FastAPI BackgroundTasks, not Celery. Celery worker is up but idle.
- Voice dictation (`/voice/transcribe`) loads faster-whisper on first call;
  not yet exercised.

## Session Context

**What was done this session (2026-04-11):**
- Continued from context compaction — Antigravity had committed the earlier
  slowapi / scheduler / GSD changes (`f3ef4f0`, `e637ab6`, `542a277`).
- Diagnosed and fixed the bcrypt 5 × passlib 1.7.4 regression on
  `/auth/login` (hard ValueError on any >72-byte string).
- Added reproducible admin seeding via `scripts/seed_admin.py` + Makefile
  target `seed-admin`.
- Reached **4/4 critical** on `scripts/verify_phase_0.py`:
  - Backend API: ok (api + database + redis + ollama all ok)
  - OHIF Viewer: reachable at https://localhost
  - Orthanc PACS: reachable at https://localhost/orthanc/
  - JWT Auth: admin login returns access_token
- Committed all Phase 0 tail fixes as `2e11b34`.

**Key architectural decisions to remember:**
- Model scheduler is singleton — only ONE model in VRAM at a time
- LLMs never generate findings — they only polish language
- All AI operations must be logged for audit trail
- Cloud GPU fallback for jobs exceeding 8 GB VRAM
- Backend talks to Ollama at `host.docker.internal:11434` (not localhost)
- `from __future__ import annotations` is **banned** in files that combine
  slowapi `@limiter.limit` with module-level types in endpoint signatures
  (`UUID`, `User`, `Request`, `UploadFile`, etc.). The slowapi decorator
  replaces `__globals__`, breaking PEP 563 forward-ref resolution.

**Verification commands that now pass:**
- `python scripts/verify_phase_0.py` → 4/4 green
- `docker compose exec backend python3 /app/scripts/seed_admin.py`
- `curl -sk https://localhost/health` → `{"status":"ok",...}`
- GPU check from inside container → PyTorch 2.10.0+cu128, RTX 5060 sm_120
