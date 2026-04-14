# Project State

## Current Position

**Milestone:** RadAI Phase 0-3
**Phase:** ALL PHASES COMPLETE
**Status:** Phase 0 ✅ | Phase 1 ✅ (7/7) | Phase 2 ✅ (8/8) | Phase 3 ✅ (6/6) | Fortification ✅ (12/12)

## What Was Added (2026-04-13 — Phase 3 Completion)

### Plan 3.5: RAG Pipeline
- **Clinical RAG system** — `app/reporting/rag.py`: 10 embedded clinical guidelines
  - Lung-RADS v2022, Fleischner 2017, BI-RADS 2013, LI-RADS v2018
  - Incidental thyroid/adrenal, Spine degenerative, Brain MRI lesions
  - Chest X-ray reporting, TI-RADS 2017
- **RAG-enhanced report generation** — Modality/body-part-aware clinical context injection
- **`/api/v1/reports/rag/retrieve` endpoint** — Preview which references will be used
- **`use_rag` flag** — Optional in `GenerateReportRequest` (defaults to True)

### Plan 3.6: Multi-Modality Support
- **Modality registry** — `app/ai/modality_registry.py`: 5 imaging modalities
  - CT (Tier 1): TotalSegmentator, nodule detection, nnInteractive, LiteMedSAM
  - MRI (Tier 2): Brain, spine, MSK (planned models)
  - X-ray (Tier 2): CheXpert 14-pathology classification
  - Ultrasound (Tier 3): Fetal biometry, thyroid TI-RADS (planned)
  - Mammography (Tier 3): BI-RADS density, mass detection (planned)
- **`/api/v1/ai/modalities` endpoint** — List all supported modalities
- **`/api/v1/ai/modalities/{code}/models` endpoint** — List AI models per modality
- **`/api/v1/ai/studies/{id}/recommend-ai` endpoint** — AI recommendations for study

### Verification
- **Phase 3 verification script** — `scripts/verify_phase_3.py` with `make verify-phase3`
- Tests: cloud GPU client, anonymizer, RAG retrieval, modality registry, API endpoints

## Remaining Work

| Item | Priority | Notes |
|------|----------|-------|
| LiteMedSAM checkpoint download | MEDIUM | `make download-models` script exists, checkpoint not yet fetched |
| Deploy cloud GPU server | MEDIUM | Need RunPod/Vast.ai endpoint + API key |
| Future modality models | LOW | MRI brain/spine, CheXpert, US fetal/thyroid, MG density (all "planned") |

## Active Decisions

| Decision | Choice | Affects |
|----------|--------|---------|
| Cloud GPU pattern | HTTP REST API (RunPod serverless) | gpu_client.py expects `/upload`, `/infer`, `/jobs/{id}` endpoints |
| Anonymization | DICOM PS 3.15 Table E.1-1 profile | PHI removed before any cloud upload |
| Test strategy | Pytest with SQLite for unit tests, Docker for integration | CI runs both on push/PR |
| OHIF extensions | Runtime JS injection via Nginx (no OHIF rebuild) | All three panels load independently |
| RAG strategy | Keyword-based embedded references (production: vector DB) | Scalable to hundreds of guidelines |

## Blockers

- [ ] No blockers. All phases complete. System ready for deployment and production testing.
