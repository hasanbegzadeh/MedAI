# SPEC.md — RadAI Project Specification

> **Status**: `FINALIZED`
> **Date**: 2026-04-11
> **Version**: 1.0

## Vision

RadAI is an AI-powered radiology assistant that provides automated pathology detection, anatomical segmentation, and structured radiology report generation. It integrates multiple AI models (TotalSegmentator, nnInteractive, LiteMedSAM, MedGemma) with a DICOM-compliant viewer (OHIF) to create a comprehensive, safety-first radiology workflow where "AI suggests, radiologist confirms."

## Goals

1. **AI-Assisted Segmentation** — Automatically detect and segment anatomical structures in medical imaging studies using multiple complementary AI models
2. **Structured Reporting** — Generate professional radiology reports from AI-detected findings with human-in-the-loop review
3. **Consumer Hardware Compatible** — Run on RTX 5060 (8 GB VRAM) via model scheduling with cloud GPU fallback for heavy workloads
4. **Clinical Safety** — Maintain audit trails, never allow autonomous diagnosis, ensure all AI findings are reviewable

## Non-Goals (Out of Scope)

- Autonomous diagnosis without radiologist oversight
- Real-time streaming or live imaging
- Training custom AI models (we use pretrained models only)
- Multi-institution PACS synchronization
- Mobile application
- Billing or scheduling systems

## Constraints

- **Hardware**: RTX 5060 with 8 GB GDDR7 VRAM, 32 GB RAM
- **Model Scheduling**: Only ONE model can occupy GPU VRAM at a time
- **Offline Capability**: Core features must work without internet (local Ollama, local models)
- **Clinical Compliance**: All AI operations must be logged for audit trail
- **Budget**: Cloud GPU usage limited to complex cases only (Tier 2/3)

## Success Criteria

- [ ] Docker stack runs with all services healthy (PostgreSQL, Redis, Orthanc, OHIF, FastAPI, Celery, Nginx)
- [ ] GPU model scheduler successfully loads, runs, and unloads TotalSegmentator, nnInteractive, and LiteMedSAM
- [ ] CT study can be uploaded, segmented, and reviewed with findings visible in OHIF
- [ ] Radiology report can be generated from findings and exported as PDF
- [ ] Voice dictation works for adding findings to reports
- [ ] All AI operations stream progress via WebSocket
- [ ] System handles cloud GPU fallback when local VRAM is insufficient
- [ ] End-to-end latency < 5 minutes for TotalSegmentator fast mode on typical CT study

## User Stories

### As a Radiologist
- I want to upload a DICOM study and see automatic segmentation overlays
- So that I can quickly identify anatomical structures and abnormalities

### As a Radiologist
- I want to review AI-generated findings and accept, reject, or modify them
- So that I maintain full control over the diagnostic process

### As a Radiologist
- I want to generate a structured radiology report from reviewed findings
- So that I can produce consistent, professional reports efficiently

### As a System Administrator
- I want the system to run on consumer hardware with cloud fallback
- So that I can deploy without expensive GPU servers

## Technical Requirements

| Requirement | Priority | Notes |
|-------------|----------|-------|
| DICOM ingestion via Orthanc PACS | Must-have | DICOMweb (QIDO-RS, WADO-RS, STOW-RS) |
| GPU model scheduler (1 model at a time) | Must-have | Thread-safe singleton with VRAM tracking |
| TotalSegmentator integration | Must-have | Fast mode, body_seg, roi_subset support |
| nnInteractive for refinement | Must-have | Interactive segmentation |
| LiteMedSAM fallback | Must-have | Real implementation (no mocks) |
| Ollama MedGemma report generation | Must-have | Async, non-blocking |
| OpenRouter cloud LLM | Should-have | Gemma 4 31B for complex cases |
| OHIF custom extensions | Must-have | AI tools, findings, reporting panels |
| Voice dictation | Should-have | faster-whisper for speech-to-text |
| DICOM-SR export | Must-have | Structured report export |
| PDF report generation | Should-have | Template-based with Jinja2 |
| WebSocket progress streaming | Must-have | Real-time AI task updates |
| JWT authentication | Must-have | Role-based access control |
| Audit logging | Must-home | All AI operations logged |
| Cloud GPU queue | Should-have | Celery-based job queue |
| Rate limiting | Must-have | SlowAPI for API protection |

---

*Last updated: 2026-04-11*
