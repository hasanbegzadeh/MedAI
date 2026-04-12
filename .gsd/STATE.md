# Project State

## Current Position

**Milestone:** RadAI Phase 0-3
**Phase:** Phase 1 - AI Segmentation (6/7 plans ✅ COMPLETE, 1/7 pending)
**Status:** Phase 1 substantially complete | Remaining: 1.4 (real CT dataset)
**Plan:** Move to Phase 2 (Report Generation) or test with real CT data

## Phase 1 Final Progress

| Plan | Status | Verification |
|------|--------|-------------|
| 1.1 LiteMedSAM real impl | ✅ COMPLETE | TinyViT model, needs checkpoint download |
| 1.2 E2E SEG pipeline | ✅ COMPLETE | Synthetic CT → TotalSegmentator → DICOM-SEG in Orthanc |
| 1.3 OHIF extension | ✅ COMPLETE | Scaffold + runtime injection + Nginx serving |
| 1.4 TotalSegmentator real CT | ⬜ PENDING | Needs real CT dataset (external) |
| 1.5 SEG overlays in OHIF | ✅ COMPLETE | Panel v2 auto-detects SEG series |
| 1.6 Nodule detection | ✅ COMPLETE | 3/3 synthetic nodules detected accurately |
| 1.7 nnInteractive refine | ✅ COMPLETE | Heuristic refinement: 145 voxels from single click |

## Commits This Session (Phase 1)

| Commit | Description |
|--------|-------------|
| `af1905a` | fix: highdicom API compatibility |
| `cfcf99d` | fix: E2E DICOM→NIfTI→SEG pipeline (3 bugs) |
| `8b8a089` | feat: real LiteMedSAM inference |
| `e71101d` | feat: OHIF AI Tools panel scaffold |
| `2f34eab` | feat: lung nodule detection heuristic |
| `4821db6` | feat: SEG overlay detection + nnInteractive click-refine |

## Active Decisions

| Decision | Choice | Affects |
|----------|--------|---------|
| nnInteractive fallback | Heuristic region-growing when model unavailable | Always works, degrades gracefully |
| Nodule detection | Connected-component analysis (not ML model) | Phase 1 prototype, upgrade to MONAI later |
| OHIF extension | Runtime injection (no rebuild) | Fast iteration, documented build path |
| highdicom API | AlgorithmIdentificationSequence required | seg_export.py, converter.py |

## Blockers

- [ ] No blockers. All Phase 1 plans either complete or blocked on external resources.

## Next Actions

1. **Phase 2** — Report Generation (findings panel, templates, voice dictation, DICOM-SR)
2. **Optional** — Test with real CT dataset when available (NSCLC-Radiomics)
3. **Manual** — Download LiteMedSAM checkpoint from Google Drive
