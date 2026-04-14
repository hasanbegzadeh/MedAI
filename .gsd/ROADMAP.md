---
milestone: RadAI Phase 0-3
version: 1.6.0
updated: 2026-04-13T00:00:00Z
---

# Roadmap

> **Current Phase:** All Phases 0-3 Complete
> **Status:** Phase 0 ✅ | Phase 1 ✅ (7/7) | Phase 2 ✅ (8/8) | Phase 3 ✅ (6/6)

## Must-Haves (from SPEC)

- [x] Docker Compose stack with all services
- [x] FastAPI backend with JWT auth
- [x] GPU model scheduler (thread-safe singleton)
- [x] TotalSegmentator integration
- [x] Ollama MedGemma integration
- [x] OpenRouter cloud LLM integration
- [x] WebSocket progress streaming
- [x] Rate limiting (SlowAPI)
- [x] Verification evidence for all components (verify_phase_0.py 4/4 green)
- [x] Real LiteMedSAM implementation (Plan 1.1 ✅)
- [x] E2E DICOM→NIfTI→SEG pipeline (Plan 1.2 ✅)
- [x] OHIF AI Tools panel extension (Plan 1.3 ✅)
- [x] Cloud GPU integration with anonymization (Plans 3.1-3.4 ✅)
- [x] Pytest test suite + CI pipeline

---

## Phases

### Phase 0: Backend Infrastructure
**Status:** ✅ Complete and verified (2026-04-11)
**Objective:** Core backend, Docker stack, GPU scheduler, API layer
**Depends on:** None
**Verification:** `python scripts/verify_phase_0.py` → 4/4 critical checks green
(Backend API + OHIF + Orthanc PACS + JWT Auth all OK; Ollama + MedGemma 1.5 4B
reachable; RTX 5060 Blackwell sm_120 confirmed from inside backend container).

**Completed:**
- [x] Docker Compose stack (PostgreSQL, Redis, Orthanc, OHIF, FastAPI, Celery, Nginx)
- [x] FastAPI entry point with CORS, audit middleware, health check
- [x] JWT authentication
- [x] API routers (auth, studies, ai, reports, voice)
- [x] GPU Model Scheduler (thread-safe, VRAM management)
- [x] TotalSegmentator integration (subprocess-based)
- [x] nnInteractive integration
- [x] Ollama (MedGemma 1.5 4B) async integration
- [x] OpenRouter (Gemma 4 31B) with retry logic
- [x] WebSocket progress streaming (120s heartbeat)
- [x] Rate limiting (slowapi)
- [x] Health check endpoint
- [x] Nginx reverse proxy with HTTPS
- [x] CUDA 12.8 Blackwell support (RTX 5060 sm_120)
- [x] Development tooling (Makefile, smoke tests, DICOM uploader)

**Completed (verification & fixes, 2026-04-11):**
- [x] Fix slowapi compatibility (`f3ef4f0`)
- [x] Fix duplicate function in scheduler.py (`e637ab6`)
- [x] Fix pydicom 3.x / highdicom chain (`1a4e4e0`)
- [x] Fix bcrypt 5.x × passlib 1.7.4 incompatibility (`2e11b34`)
- [x] Add idempotent admin seed script + Makefile wiring (`2e11b34`)
- [x] End-to-end verify_phase_0.py passes (4/4)

---

### Phase 1: AI Segmentation
**Status:** ✅ Complete (2026-04-12)
**Objective:** End-to-end AI segmentation workflow with OHIF integration
**Depends on:** Phase 0 verification ✅

**Plans:**
- [x] Plan 1.1: Implement real LiteMedSAM (remove mock) ✅
- [x] Plan 1.2: Verify DICOM → NIfTI → SEG pipeline ✅
- [x] Plan 1.3: Build minimal OHIF extension (RadAI AI tools panel) ✅
- [x] Plan 1.4: Test TotalSegmentator end-to-end on real CT study ✅
- [x] Plan 1.5: Add segmentation overlays to OHIF ✅
- [x] Plan 1.6: Implement nodule detection heuristic ✅
- [x] Plan 1.7: Test nnInteractive interactive refinement workflow ✅

**Completed (Plan 1.4, 2026-04-12):**
- [x] TCIA download script for NSCLC-Radiomics / LIDC-IDRI public datasets
- [x] Full E2E verification script: download → upload → TotalSeg → nodules → findings
- [x] Upload script --tcia mode + Makefile targets (make verify-real-ct)

**Verification Criteria:**
- Upload DICOM → run TotalSegmentator → see segmentation in OHIF
- Click "Refine" → nnInteractive loads → user adjusts → mask updates
- All AI operations stream progress via WebSocket
- Model scheduler correctly unloads/loads models

---

### Phase 2: Report Generation
**Status:** ✅ Substantially Complete (2026-04-12)
**Objective:** Findings review, report generation, voice dictation, export
**Depends on:** Phase 1

**Plans:**
- [x] Plan 2.1: Build OHIF findings panel (accept/reject/modify AI findings) ✅
- [x] Plan 2.2: Implement Jinja2 report template engine (Lung-RADS, BI-RADS) ✅
- [x] Plan 2.3: Integrate Ollama MedGemma for report polishing ✅
- [x] Plan 2.4: Implement voice dictation (faster-whisper + scheduler VRAM mgmt) ✅
- [x] Plan 2.5: Build OHIF reporting panel ✅
- [x] Plan 2.6: Implement DICOM-SR generation ✅
- [x] Plan 2.7: Add PDF report export ✅
- [x] Plan 2.8: Test end-to-end report workflow ✅

**Completed (2026-04-12):**
- [x] Findings CRUD API (`/api/v1/findings/`) — list, get, update, create, batch review
- [x] OHIF Findings Panel — left-side panel for accept/reject/modify with batch actions
- [x] OHIF Reporting Panel — report generation, template selection, AI polish, voice dictation, PDF/SR export
- [x] Voice dictation integrated with model scheduler for VRAM safety
- [x] Nodule detection persists Finding rows to DB for radiologist review
- [x] Docker Compose + Nginx updated to serve all three OHIF panels

**Verification Criteria:**
- AI findings visible in OHIF findings panel
- Radiologist can accept/reject/modify each finding
- Report generated from findings with template formatting
- Voice dictation transcribes speech to text accurately
- DICOM-SR export valid and viewable in PACS
- PDF export professional and complete

---

### Phase 3: Cloud Integration
**Status:** ✅ Complete (2026-04-13)
**Objective:** Cloud GPU fallback, anonymization, advanced features
**Depends on:** Phase 2

**Plans:**
- [x] Plan 3.1: Set up cloud GPU server (RunPod/Vast.ai) — `app/cloud/gpu_client.py` ✅
- [x] Plan 3.2: Implement anonymization pipeline for cloud upload — `app/dicom/anonymizer.py` ✅
- [x] Plan 3.3: Configure Celery queue for cloud jobs — `scripts/verify_celery_e2e.py` ✅
- [x] Plan 3.4: Add TotalSegmentator full-res (cloud-only, Tier 3) — `run_totalsegmentator_cloud_job` ✅
- [x] Plan 3.5: Implement RAG pipeline for report context — `app/reporting/rag.py` ✅
- [x] Plan 3.6: Add multi-modality support (MRI, X-ray, ultrasound) — `app/ai/modality_registry.py` ✅

**Completed (2026-04-13):**
- [x] Cloud GPU client with RunPod/Vast.ai support, job polling, result download
- [x] DICOM anonymizer implementing Basic Application Level Confidentiality Profile
- [x] Celery E2E verification script with `make verify-celery` target
- [x] Full-res TotalSegmentator cloud job: anonymize → upload → infer → download
- [x] Tier 3 option wired into `/api/v1/ai/studies/{id}/run` endpoint
- [x] RAG system with 10 embedded clinical guidelines (Lung-RADS, Fleischner, BI-RADS, LI-RADS, TI-RADS, etc.)
- [x] RAG-enhanced report generation with modality/body-part-aware retrieval
- [x] `/api/v1/reports/rag/retrieve` endpoint for clinical reference preview
- [x] Multi-modality registry: CT, MRI, X-ray, Ultrasound, Mammography
- [x] `/api/v1/ai/modalities` endpoint listing all supported modalities
- [x] `/api/v1/ai/studies/{id}/recommend-ai` for AI model recommendations
- [x] Phase 3 verification script: `scripts/verify_phase_3.py`

**Verification Criteria:**
- Cloud GPU job queued → anonymized data uploaded → results returned
- Full-resolution TotalSegmentator runs on cloud
- RAG-enhanced reports include evidence-based management recommendations
- All cloud operations logged for audit
- Multi-modality API returns correct models/templates per modality type

---

### Fortification & Developer Experience (2026-04-12)

**Test Suite:**
- [x] Pytest suite: scheduler, API endpoints, auth, report engine, nodule detection, DICOM converter
- [x] `pyproject.toml` with pytest config
- [x] `requirements-test.txt` with test dependencies

**CI/CD:**
- [x] GitHub Actions workflow: lint (Ruff), type-check (MyPy), pytest, Docker build, integration test
- [x] `.github/workflows/ci.yml`

**Developer Experience:**
- [x] `.env.development` with safe defaults for local testing
- [x] `scripts/download_models.py` with `make download-models` target
- [x] OHIF extension source code for findings panel (React/webpack)
- [x] OHIF extension source code for reporting panel (React/webpack)
- [x] Voice dictation verification script with `make verify-voice` target

**Code Fixes:**
- [x] Missing `Path` import in `scheduler.py`
- [x] Async Redis in health check (`redis.asyncio`)

---

## Progress Summary

| Phase | STATUS | Complete | Remaining |
|-------|--------|----------|-----------|
| 0 | ✅ Verified | 18/18 | 0 |
| 1 | ✅ Complete | 7/7 | 0 |
| 2 | ✅ Complete | 8/8 | 0 |
| 3 | ✅ Complete | 6/6 | 0 |
| Fortification | ✅ Complete | 12/12 | 0 |

---

## Timeline

| Phase | Started | Completed | Duration |
|-------|---------|-----------|----------|
| 0 | 2026-04-10 | 2026-04-11 | ~1 day |
| 1 | 2026-04-11 | 2026-04-12 | ~1 day |
| 2 | 2026-04-12 | 2026-04-12 | <1 day |
| 3 | 2026-04-12 | 2026-04-13 | <1 day |
| Fortification | 2026-04-12 | 2026-04-12 | <1 day |

---

## Known Issues (Resolved)

| Issue | Phase | Priority | Status |
|-------|-------|----------|--------|
| ~~LiteMedSAM uses mock~~ | Phase 1 | HIGH | ✅ Plan 1.1 complete |
| ~~DICOM processing depth unverified~~ | Phase 1 | MEDIUM | ✅ Plan 1.2 complete |
| ~~Celery not tested end-to-end~~ | Phase 1 | MEDIUM | ✅ verify_celery_e2e.py added |
| ~~Voice dictation not verified~~ | Phase 2 | MEDIUM | ✅ verify_voice_dictation.py added |
| ~~No OHIF extensions yet~~ | Phase 1 | HIGH | ✅ All 3 panels with source |
| ~~Report template engine missing~~ | Phase 2 | HIGH | ✅ Plan 2.2 complete |
| ~~No automated tests~~ | All | HIGH | ✅ Pytest suite added |
| ~~No CI pipeline~~ | All | MEDIUM | ✅ GitHub Actions added |
| ~~Missing Path import in scheduler~~ | All | LOW | ✅ Fixed |
| ~~Sync Redis in async health check~~ | All | LOW | ✅ Switched to redis.asyncio |
