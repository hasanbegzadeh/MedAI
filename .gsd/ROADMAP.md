---
milestone: RadAI Phase 0-3
version: 1.0.0
updated: 2026-04-11T00:00:00Z
---

# Roadmap

> **Current Phase:** Phase 0 - Backend Infrastructure
> **Status:** ✅ Complete (verification pending)

## Must-Haves (from SPEC)

- [x] Docker Compose stack with all services
- [x] FastAPI backend with JWT auth
- [x] GPU model scheduler (thread-safe singleton)
- [x] TotalSegmentator integration
- [x] Ollama MedGemma integration
- [x] OpenRouter cloud LLM integration
- [x] WebSocket progress streaming
- [x] Rate limiting (SlowAPI)
- [ ] Real LiteMedSAM implementation (currently mock)
- [ ] Verification evidence for all components

---

## Phases

### Phase 0: Backend Infrastructure
**Status:** ✅ Complete (verification pending)
**Objective:** Core backend, Docker stack, GPU scheduler, API layer
**Depends on:** None

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

**Remaining:**
- [ ] Replace LiteMedSAM mock with real implementation
- [ ] Verify DICOM converter pipeline (converter.py, anonymizer.py, seg_export.py)
- [ ] Test Celery queue system end-to-end
- [ ] Capture verification evidence for all components
- [ ] Fix slowapi compatibility issues (DONE, committed)
- [ ] Fix duplicate function in scheduler.py (DONE, committed)

---

### Phase 1: AI Segmentation
**Status:** ⬜ Not Started
**Objective:** End-to-end AI segmentation workflow with OHIF integration
**Depends on:** Phase 0 verification

**Plans:**
- [ ] Plan 1.1: Implement real LiteMedSAM (remove mock)
- [ ] Plan 1.2: Verify DICOM → NIfTI → SEG pipeline
- [ ] Plan 1.3: Build minimal OHIF extension (RadAI AI tools panel)
- [ ] Plan 1.4: Test TotalSegmentator end-to-end on real CT study
- [ ] Plan 1.5: Add segmentation overlays to OHIF
- [ ] Plan 1.6: Implement nodule detection heuristic (from TotalSegmentator lung ROI)
- [ ] Plan 1.7: Test nnInteractive interactive refinement workflow

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
| 0 | ✅ Verifying | 17/19 | 2 (LiteMedSAM, verification) |
| 1 | ⬜ Not Started | 0/7 | 7 |
| 2 | ⬜ Not Started | 0/8 | 8 |
| 3 | ⬜ Not Started | 0/6 | 6 |

---

## Timeline

| Phase | Started | Completed | Duration |
|-------|---------|-----------|----------|
| 0 | 2026-04-10 | ~2026-04-11 | ~1 day |
| 1 | — | — | — |
| 2 | — | — | — |
| 3 | — | — | — |

---

## Known Issues

| Issue | Phase | Priority | Status |
|-------|-------|----------|--------|
| LiteMedSAM uses mock | Phase 0 | HIGH | Identified |
| DICOM processing depth unverified | Phase 0 | MEDIUM | Needs verification |
| Celery not tested | Phase 0 | MEDIUM | Needs testing |
| Voice dictation not verified | Phase 0 | MEDIUM | Needs verification |
| No OHIF extensions yet | Phase 1 | HIGH | Planned |
| Report template engine missing | Phase 2 | HIGH | Not started |
