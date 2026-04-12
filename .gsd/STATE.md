# Project State

## Current Position

**Milestone:** RadAI Phase 0-3
**Phase:** Phase 2 - Report Generation (starting)
**Status:** Phase 1 substantially complete (6/7 ✅) | Phase 2 beginning
**Plan:** Execute Phase 2 plans: template engine → DICOM-SR → PDF export → voice dictation

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
| 2.1 Findings panel UI | ⬜ Pending | OHIF panel for accept/reject/modify |
| 2.2 Jinja2 template engine | ✅ COMPLETE | Lung-RADS, general CT templates |
| 2.3 Ollama report polishing | ✅ COMPLETE | Wired into generate_report endpoint |
| 2.4 Voice dictation | ⬜ Pending | faster-whisper speech-to-text |
| 2.5 OHIF reporting panel | ⬜ Pending | Report review UI |
| 2.6 DICOM-SR generation | ✅ COMPLETE | Basic Text SR, upload to Orthanc |
| 2.7 PDF report export | ✅ COMPLETE | ReportLab with custom styles |
| 2.8 E2E report workflow | 🟡 Partial | Backend pipeline verified, UI pending |

## Active Decisions

| Decision | Choice | Affects |
|----------|--------|---------|
| Phase 2 order | Backend first (templates, DICOM-SR, PDF) then UI | Fastest verification path |
| Template engine | Jinja2 with Lung-RADS standard | Industry standard for lung cancer screening |
| DICOM-SR library | highdicom (already installed) | Same library used for DICOM-SEG |

## Blockers

- [ ] No blockers.
