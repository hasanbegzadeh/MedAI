# Project State

## Current Position

**Milestone:** RadAI Phase 0-3
**Phase:** Phase 1 - AI Segmentation (starting)
**Status:** Phase 0 verified ✅ | Phase 1 plans defined, execution beginning
**Plan:** Execute Plan 1.2 (E2E DICOM→NIfTI→SEG pipeline) → Plan 1.1 (real LiteMedSAM) → Plan 1.3 (OHIF extension)

## Assessment Summary (2026-04-11 Full Review)

A comprehensive review of all project files was completed. Key findings:

### Phase 0 — Complete & Verified
- Docker stack: all 7 services defined (PostgreSQL, Redis, Orthanc, OHIF, FastAPI, Celery, Nginx)
- GPU model scheduler: thread-safe singleton with VRAM tracking, load/unload cycle
- TotalSegmentator: subprocess integration with timeout, progress callbacks
- nnInteractive: integration scaffolded (simulated prediction step)
- Ollama MedGemma 1.5 4B: async report generation
- OpenRouter Gemma 4 31B: Tier 2 cloud with retry logic
- WebSocket: real-time progress streaming with 120s heartbeat
- JWT auth + rate limiting (slowapi) + audit middleware
- CUDA 12.8 Blackwell support (RTX 5060 sm_120 confirmed)
- Verification: `verify_phase_0.py` passes 4/4 critical checks

### Phase 1 — Plans Defined, Not Yet Executed
| Plan | Status | Description |
|------|--------|-------------|
| 1.1 | ⬜ Pending | Replace LiteMedSAM mock with real SAM checkpoint |
| 1.2 | 🟡 Next | E2E DICOM→NIfTI→TotalSegmentator→DICOM-SEG round-trip |
| 1.3 | ⬜ Pending | OHIF custom extension (AI tools panel) |
| 1.4 | ⬜ Pending | TotalSegmentator E2E on real CT study |
| 1.5 | ⬜ Pending | Segmentation overlays in OHIF |
| 1.6 | ⬜ Pending | Nodule detection heuristic |
| 1.7 | ⬜ Pending | nnInteractive interactive refinement |

### Code Quality
- Duplicate `_is_retryable_openrouter_error` was already fixed (commit `e637ab6`)
- `from __future__ import annotations` correctly removed from slowapi-decorated files
- LiteMedSAM still returns mock `"simulated_local_mask"` string
- nnInteractive job simulates prediction (no real model call yet)

## Active Decisions

| Decision | Choice | Made | Affects |
|----------|--------|------|---------|
| GSD methodology adopted | SPEC→PLAN→EXECUTE→VERIFY→COMMIT | 2026-04-11 | All future work |
| Phase 0 scope finalized | No new features, only verification | 2026-04-11 | Phase 0 |
| LiteMedSAM priority | Replace mock before Phase 1.2+ | 2026-04-11 | Phase 0/1 boundary |
| bcrypt pinned <4.1 | keep passlib 1.7.4 compatible | 2026-04-11 | Auth subsystem |
| Admin seed script | idempotent, env-overridable | 2026-04-11 | dev/CI bootstrap |
| slowapi + PEP 563 | never combine in endpoint files | 2026-04-11 | all API routers |
| Plan 1.2 first | E2E pipeline has highest signal | 2026-04-11 | Phase 1 execution order |

## Blockers

- [ ] Docker stack must be running for E2E tests
- [ ] Real CT study needed for meaningful verification (synthetic works for smoke test)

## Next Actions (Phase 1 Execution Order)

1. **Plan 1.2** — E2E DICOM→NIfTI→SEG round-trip verification
   - Upload synthetic CT via `upload_test_dicom.py --synthetic`
   - Create Study record in PostgreSQL
   - POST `/api/v1/ai/studies/{id}/run` with `job_type=totalsegmentator`
   - Poll job status until completed
   - Verify DICOM-SEG in Orthanc via QIDO-RS

2. **Plan 1.1** — Replace LiteMedSAM mock with real implementation
   - Download LiteMedSAM checkpoint
   - Implement real inference path in `scheduler.load_litemedsam()`
   - Update `medsam2.py` to return real mask files

3. **Plan 1.3** — OHIF extension skeleton
   - Custom panel with "Run AI" button
   - WebSocket progress display
   - SEG series auto-load

## Session Context

**What was done this session (2026-04-11 review):**
- Completed comprehensive project file review
- Confirmed Phase 0 is complete and verified
- Confirmed Phase 1 plans are well-defined in `.gsd/plans/phase-1-ai-segmentation.md`
- Identified that duplicate function fix was already applied
- Ready to begin Phase 1 execution

**Key architectural reminders:**
- Model scheduler: singleton, ONE model in VRAM at a time
- LLMs never generate findings — only polish language
- All AI operations logged for audit trail
- Backend talks to Ollama at `host.docker.internal:11434`
- `from __future__ import annotations` banned in slowapi-decorated files
