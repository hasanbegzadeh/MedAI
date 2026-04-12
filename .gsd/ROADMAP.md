---
milestone: RadAI Phase 0-3
version: 1.3.0
updated: 2026-04-11T21:00:00Z
---

# Roadmap

> **Current Phase:** Phase 1 - AI Segmentation (6/7 ✅ COMPLETE)
> **Status:** Phase 0 ✅ | Phase 1 substantially complete | Ready for Phase 2

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

**Deferred into Phase 1 (carried over, not blocking Phase 0):**
- [ ] Replace LiteMedSAM mock with real implementation → Plan 1.1
- [ ] Verify DICOM converter pipeline on a real CT study → Plan 1.2
- [ ] Test Celery queue system end-to-end → Plan 1.2

---

### Phase 1: AI Segmentation
**Status:** 🟢 Substantially Complete (2026-04-11)
**Objective:** End-to-end AI segmentation workflow with OHIF integration
**Depends on:** Phase 0 verification ✅

**Plans:**
- [x] Plan 1.1: Implement real LiteMedSAM (remove mock) ✅
- [x] Plan 1.2: Verify DICOM → NIfTI → SEG pipeline ✅
- [x] Plan 1.3: Build minimal OHIF extension (RadAI AI tools panel) ✅
- [ ] Plan 1.4: Test TotalSegmentator end-to-end on real CT study (external dataset needed)
- [x] Plan 1.5: Add segmentation overlays to OHIF ✅
- [x] Plan 1.6: Implement nodule detection heuristic ✅
- [x] Plan 1.7: Test nnInteractive interactive refinement workflow ✅

**Verification Criteria:**
- Upload DICOM → run TotalSegmentator → see segmentation in OHIF
- Click "Refine" → nnInteractive loads → user adjusts → mask updates
- All AI operations stream progress via WebSocket
- Model scheduler correctly unloads/loads models

---

### Phase 2: Report Generation
**Status:** ⬜ Not Started
**Objective:** Findings review, report generation, voice dictation, export
**Depends on:** Phase 1

**Plans:**
- [ ] Plan 2.1: Build OHIF findings panel (accept/reject/modify AI findings)
- [ ] Plan 2.2: Implement Jinja2 report template engine (Lung-RADS, BI-RADS)
- [ ] Plan 2.3: Integrate Ollama MedGemma for report polishing
- [ ] Plan 2.4: Implement voice dictation (faster-whisper)
- [ ] Plan 2.5: Build OHIF reporting panel
- [ ] Plan 2.6: Implement DICOM-SR generation
- [ ] Plan 2.7: Add PDF report export
- [ ] Plan 2.8: Test end-to-end report workflow

**Verification Criteria:**
- AI findings visible in OHIF findings panel
- Radiologist can accept/reject/modify each finding
- Report generated from findings with template formatting
- Voice dictation transcribes speech to text accurately
- DICOM-SR export valid and viewable in PACS
- PDF export professional and complete

---

### Phase 3: Cloud Integration
**Status:** ⬜ Not Started
**Objective:** Cloud GPU fallback, anonymization, advanced features
**Depends on:** Phase 2

**Plans:**
- [ ] Plan 3.1: Set up cloud GPU server (RunPod/Vast.ai)
- [ ] Plan 3.2: Implement anonymization pipeline for cloud upload
- [ ] Plan 3.3: Configure Celery queue for cloud jobs
- [ ] Plan 3.4: Add TotalSegmentator full-res (cloud-only, Tier 3)
- [ ] Plan 3.5: Implement RAG pipeline for report context
- [ ] Plan 3.6: Add multi-modality support (MRI, X-ray, ultrasound)

**Verification Criteria:**
- Cloud GPU job queued → anonymized data uploaded → results returned
- Full-resolution TotalSegmentator runs on cloud
- RAG-enhanced reports use relevant clinical context
- All cloud operations logged for audit

---

## Progress Summary

| Phase | STATUS | Complete | Remaining |
|-------|--------|----------|-----------|
| 0 | ✅ Verified | 18/18 | 0 |
| 1 | 🟢 Substantially Complete | 6/7 | 1 (real CT test — external) |
| 2 | ⬜ Not Started | 0/8 | 8 |
| 3 | ⬜ Not Started | 0/6 | 6 |

---

## Timeline

| Phase | Started | Completed | Duration |
|-------|---------|-----------|----------|
| 0 | 2026-04-10 | 2026-04-11 | ~1 day |
| 1 | 2026-04-11 | 2026-04-11 | ~1 day |
| 2 | — | — | — |
| 3 | — | — | — |

---

## Known Issues

| Issue | Phase | Priority | Status |
|-------|-------|----------|--------|
| LiteMedSAM uses mock | Phase 1 | HIGH | Plan 1.1 — next |
| DICOM processing depth unverified | Phase 1 | MEDIUM | Plan 1.2 |
| Celery not tested end-to-end | Phase 1 | MEDIUM | Plan 1.2 |
| Voice dictation not verified | Phase 2 | MEDIUM | Plan 2.4 |
| No OHIF extensions yet | Phase 1 | HIGH | Plan 1.3 |
| Report template engine missing | Phase 2 | HIGH | Plan 2.2 |
