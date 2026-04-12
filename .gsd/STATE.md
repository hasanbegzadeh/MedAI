# Project State

## Current Position

**Milestone:** RadAI Phase 0-3
**Phase:** Phase 2 - Report Generation (substantially complete)
**Status:** Phase 2 substantially complete (7/8) | Ready for Phase 3
**Plan:** Phase 2 UI + backend complete; Plan 1.4 (real CT) remains external dependency

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

## Phase 2 Plans (Report Generation)

| Plan | Status | Description |
|------|--------|-------------|
| 2.1 Findings panel UI | ✅ COMPLETE | OHIF panel + findings CRUD API (accept/reject/modify/batch/manual) |
| 2.2 Jinja2 template engine | ✅ COMPLETE | Lung-RADS, general CT templates |
| 2.3 Ollama report polishing | ✅ COMPLETE | Wired into generate_report endpoint |
| 2.4 Voice dictation | ✅ COMPLETE | faster-whisper integrated with model scheduler VRAM management |
| 2.5 OHIF reporting panel | ✅ COMPLETE | Report generation, review, edit, voice dictation, PDF/SR export |
| 2.6 DICOM-SR generation | ✅ COMPLETE | Basic Text SR, upload to Orthanc |
| 2.7 PDF report export | ✅ COMPLETE | ReportLab with custom styles |
| 2.8 E2E report workflow | ✅ COMPLETE | Nodule detection → findings DB → review → report → export |

## Active Decisions

| Decision | Choice | Affects |
|----------|--------|---------|
| Voice VRAM mgmt | Scheduler-coordinated whisper loading | Prevents OOM with other GPU models |
| Findings persistence | Nodule detection auto-creates Finding rows (status: pending) | E2E workflow completion |
| Panel injection | Runtime JS injection via Nginx (no OHIF rebuild) | All three panels load independently |

## Blockers

- [ ] Plan 1.4 needs real CT dataset (external dependency)
