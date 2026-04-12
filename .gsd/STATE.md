# Project State

## Current Position

**Milestone:** RadAI Phase 0-3
**Phase:** Phase 1 - AI Segmentation (Plans 1.1 ✅, 1.2 ✅, 1.3 ✅, 1.6 ✅ COMPLETE)
**Status:** 4/7 Phase 1 plans done | Phase 1 substantially complete
**Plan:** Remaining Phase 1 (1.4 real CT, 1.5 overlays, 1.7 nnInteractive) or move to Phase 2

## Last Action

**Plan 1.2 E2E DICOM→NIfTI→SEG pipeline: VERIFIED ✅**

End-to-end TotalSegmentator workflow confirmed working:
1. Synthetic CT (32 slices) uploaded to Orthanc
2. Studies synced from Orthanc → PostgreSQL via `/api/v1/studies/sync-from-orthanc`
3. AI job triggered via `POST /api/v1/ai/studies/{id}/run` with `job_type=totalsegmentator`
4. Job completed with `status=completed`, `progress_pct=100`
5. DICOM-SEG series confirmed in Orthanc: `Modality=SEG`, `SeriesDescription=RadAI Segmentation`

**Three bugs found and fixed during Plan 1.2:**
1. **Missing TotalSegmentator weights** — container had no cached weights; pre-download script added
2. **highdicom API change** — `SegmentDescription` requires `algorithm_identification` (AlgorithmIdentificationSequence), not `algorithm_name`
3. **Missing required DICOM attributes** — `Segmentation` constructor needs 6 mandatory fields + source DICOMs need StudyDate/PatientName/etc.

**Commits:**
- `af1905a` fix(seg-export): use algorithm_identification instead of algorithm_name
- `cfcf99d` fix(phase-1.2): complete E2E DICOM→NIfTI→SEG pipeline

## Phase 1 Progress

| Plan | Status | Notes |
|------|--------|-------|
| 1.1 LiteMedSAM real impl | ✅ COMPLETE | Real TinyViT model, needs checkpoint download |
| 1.2 E2E SEG pipeline | ✅ COMPLETE | Verified with synthetic CT |
| 1.3 OHIF extension | ✅ COMPLETE | Scaffold + runtime injection |
| 1.4 TotalSegmentator real CT | ⬜ Pending | Needs real CT dataset |
| 1.5 SEG overlays in OHIF | ⬜ Pending | Depends on 1.3 |
| 1.6 Nodule detection | ✅ COMPLETE | 3/3 synthetic nodules detected accurately |
| 1.7 nnInteractive refine | ⬜ Pending | |

## Active Decisions

| Decision | Choice | Made | Affects |
|----------|--------|------|---------|
| GSD methodology adopted | SPEC→PLAN→EXECUTE→VERIFY→COMMIT | 2026-04-11 | All future work |
| Plan 1.2 first | E2E pipeline has highest signal | 2026-04-11 | Phase 1 execution order |
| highdicom API pinned | AlgorithmIdentificationSequence required | 2026-04-11 | seg_export.py, converter.py |
| Synthetic DICOM attrs | Default PatientName/StudyDate added | 2026-04-11 | converter.py robustness |
| Weights pre-download | Script added to backend/scripts/ | 2026-04-11 | Container setup |

## Blockers

- [ ] No blockers. E2E pipeline working.

## Next Actions

1. **Plan 1.4** — Test with real CT dataset (NSCLC-Radiomics or similar)
2. **Download LiteMedSAM checkpoint** → `backend/models/lite_medsam.pth`
3. **Phase 2** — Report Generation (findings panel, templates, voice dictation)
