# RadAI — System Architecture

## 1. High-Level Architecture Diagram (Hybrid Cloud/Local)

**Key Decision**: Segmentation/detection models (PyTorch/MONAI) run in cloud. MedGemma 1.5 4B + text LLMs run locally via Ollama.

**Updated April 2026**: Added PostgreSQL (metadata, audit trail), Redis (job queue), WebSocket (real-time progress, 120s heartbeat), faster-whisper (voice dictation), Gemma 4 31B (Tier 2 cloud). PyTorch ≥2.6.0 required for RTX 5060 Blackwell (sm_120).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          BROWSER (Client)                               │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    OHIF Viewer v3.12                           │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐│   │
│  │  │ Cornerstone3D│ │  RadAI       │ │  RadAI                   ││   │
│  │  │ Rendering    │ │  AI Tools    │ │  Reporting               ││   │
│  │  │ Engine       │ │  Panel       │ │  Panel                   ││   │
│  │  │              │ │              │ │                          ││   │
│  │  │ • MPR        │ │ • Auto-      │ │ • Findings Panel         ││   │
│  │  │ • Volume     │ │   Detect     │ │ • Accept/Reject/Modify   ││   │
│  │  │ • Windowing  │ │ • Segment    │ │ • Template Reports       ││   │
│  │  │ • Scroll     │ │ • Measure    │ │ • Lung-RADS/BI-RADS      ││   │
│  │  │ • Annotate   │ │ • Refine     │ │ • Export PDF/DICOM-SR    ││   │
│  │  └──────────────┘ └──────────────┘ └──────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ DICOMweb (HTTP/REST)
                               │ QIDO-RS, WADO-RS, STOW-RS
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     ORTHANC PACS SERVER (Local)                         │
│                                                                         │
│  • DICOM Storage    • DICOMweb API    • REST API    • Plugin System    │
│  • Local file import              • Study/Series/Instance queries      │
│  • Anonymization (before cloud upload)                                  │
│                                                                         │
└───────────────────┬──────────────────────────┬──────────────────────────┘
                    │                          │
          DICOMweb  │ (Internal)               │ HTTPS (Anonymized DICOM)
                    ▼                          ▼
┌──────────────────────────┐    ┌──────────────────────────────────────────┐
│  RadAI Backend (Local)   │    │         CLOUD GPU SERVER                 │
│  FastAPI / Python        │    │  (RunPod / Vast.ai / Colab / AWS)       │
│                          │    │                                         │
│  ┌────────────────────┐  │    │  ┌──────────────────────────────────┐  │
│  │ DICOM Service      │  │    │  │  MONAI Inference Server          │  │
│  │ • DICOM↔NIfTI      │  │    │  │                                  │  │
│  │ • Metadata extract │  │    │  │  Segmentation Models:            │  │
│  │ • Windowing params │  │    │  │  • TotalSegmentator (CT)         │  │
│  └─────────┬──────────┘  │    │  │  • nnInteractive                 │  │
│            │             │    │  │  • MedSAM2 / SAM2                │  │
│  ┌─────────▼──────────┐  │    │  │  • VoxTell (text-prompt seg)    │  │
│  │ AI Orchestrator    │──┼────┼─►│  │  • LungMask (lung lobes)      │  │
│  │ • Model Router     │  │    │  │  │                                  │  │
│  │ • Cloud API Client │  │    │  │  Detection Models:               │  │
│  │ • Result Cache     │  │    │  │  • MONAI Lung Nodule Detection  │  │
│  │ • Job Queue        │  │    │  │  • CheXpert (X-Ray)             │  │
│  └─────────┬──────────┘  │    │  │  • BraTS (Brain MRI)            │  │
│            │             │    │  │                                  │  │
│  ┌─────────▼──────────┐  │    │  │  DICOM → NIfTI → AI → SEG/JSON  │  │
│  │ Report Service     │  │    │  └──────────────┬───────────────────┘  │
│  │ • Template Engine  │  │    │                 │                      │
│  │ • DICOM-SR Gen     │  │    │                 │ Results (SEG + JSON) │
│  │ • PDF Export       │  │    │                 ▼                      │
│  │ • Voice Dictation  │  │    └─────────────────┼─────────────────────┘
│  └─────────┬──────────┘  │                      │
│            │             │                      │
│  ┌─────────▼──────────┐  │                      │
│  │ Ollama (Local)     │  │                      │
│  │                    │  │                      │
│  │ ✅ MedGemma 1.5 4B │  │                      │
│  │    (Q4, ~3 GB)     │  │                      │
│  │                    │  │                      │
│  │ Report polishing:  │◄─┼──────────────────────┘
│  │ Structured findings│  │
│  │ → polished text    │  │
│  └────────────────────┘  │
│                          │
│  ┌────────────────────┐  │
│  │ faster-whisper     │  │
│  │ (local, ~3 GB)     │  │
│  │                    │  │
│  │ Voice dictation:   │  │
│  │ audio → text       │  │
│  │ (NOT via Ollama)   │  │
│  └────────────────────┘  │
│                          │
│  ┌────────────────────┐  │
│  │ PostgreSQL         │  │
│  │ • Study metadata   │  │
│  │ • Findings cache   │  │
│  │ • Audit log        │  │
│  │ • User accounts    │  │
│  └────────────────────┘  │
│  ┌────────────────────┐  │
│  │ Redis              │  │
│  │ • Job queue        │  │
│  │ • Result cache     │  │
│  │ • Session state    │  │
│  └────────────────────┘  │
│  ┌────────────────────┐  │
│  │ WebSocket Server   │  │
│  │ • AI progress      │  │
│  │ • Real-time alerts │  │
│  └────────────────────┘  │
└──────────────────────────┘
```

**Data Flow Summary**:
1. OHIF → Orthanc: Load DICOM studies locally
2. Orthanc → RadAI Backend: DICOM via DICOMweb
3. RadAI Backend → Cloud: Anonymized NIfTI for segmentation/detection (via Redis job queue)
4. Cloud → RadAI Backend: SEG overlays + JSON findings
5. RadAI Backend → Ollama: Structured findings for report polishing
6. Ollama → RadAI Backend: Polished report text
7. RadAI Backend → OHIF: Display results + final report (via WebSocket for progress)
8. All operations logged to PostgreSQL audit trail

## 2. Data Flow: CT Study Analysis

```
1. LOAD STUDY
   Radiologist opens CT Chest study in OHIF
   OHIF fetches DICOM via DICOMweb from Orthanc
   Cornerstone3D renders slices, MPR, volume

2. AUTO-DETECT (One-Click Analysis)
   Radiologist clicks "AI Analysis" button
   ┌─────────────────────────────────────────────┐
   │ OHIF sends StudyInstanceUID to RadAI Backend│
   │ Backend fetches DICOM from Orthanc          │
   │ DICOM → NIfTI conversion                    │
   │                                             │
   │ Parallel AI Inference:                      │
   │  ├─ TotalSegmentator → 117 structures       │
   │  ├─ Lung Nodule Detection → nodule list     │
   │  └─ LungMask → lung lobe segmentation       │
   │                                             │
   │ Results → DICOM-SEG + JSON findings         │
   │ Results sent back to OHIF                   │
   └─────────────────────────────────────────────┘

3. VISUALIZE RESULTS
   OHIF displays:
   ├─ Segmentation overlays on slices (color-coded)
   ├─ Findings panel with detected abnormalities
   ├─ Measurements (size, volume, HU)
   └─ Key image markers

4. INTERACTIVE REFINEMENT
   Radiologist clicks on finding → nnInteractive refines
   ├─ Point prompt → auto-segment lesion
   ├─ Scribble → include/exclude regions
   ├─ Bounding box → define area of interest
   └─ 3D propagation → segments entire volume

5. STRUCTURED REPORTING
   Radiologist reviews each finding:
   ├─ Accept / Reject / Modify
   ├─ Add measurements, descriptors
   ├─ Assign Lung-RADS category
   └─ Add clinical context

   Template Engine generates report:
   ├─ Pre-defined templates (Lung-RADS, Fleischner)
   ├─ Structured findings → formatted text
   ├─ MedGemma polishes language (optional)
   └─ Export: PDF, DICOM-SR, FHIR

6. SAVE & ARCHIVE
   ├─ Report saved to Orthanc (DICOM-SR)
   ├─ Segmentations saved (DICOM-SEG)
   └─ Study linked to report for future reference
```

## 3. Component Detail: AI Model Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                    AI MODEL PIPELINE                         │
│                                                              │
│  Input: DICOM Study                                          │
│       ↓                                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  DICOM Preprocessing                                   │ │
│  │  • Extract pixel data + metadata                       │ │
│  │  • Apply rescale slope/intercept (HU conversion)       │ │
│  │  • Handle multi-series studies                         │ │
│  │  • DICOM → NIfTI conversion (SimpleITK)                │ │
│  │  • Spacing normalization                               │ │
│  └────────────────────────────────────────────────────────┘ │
│       ↓                                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Model Selection (based on modality + body part)       │ │
│  │                                                        │ │
│  │  IF CT Chest:                                          │ │
│  │    ├─ TotalSegmentator (anatomy)                       │ │
│  │    ├─ MONAI Lung Nodule Detection                      │ │
│  │    └─ LungMask (lobes)                                 │ │
│  │                                                        │ │
│  │  IF CT Abdomen:                                        │ │
│  │    ├─ TotalSegmentator (organs)                        │ │
│  │    ├─ nnU-Net (lesion detection)                       │ │
│  │    └─ Liver/Kidney specific models                     │ │
│  │                                                        │ │
│  │  IF MRI Brain:                                         │ │
│  │    ├─ BraTS tumor segmentation                         │ │
│  │    ├─ HD-GLIO classification                           │ │
│  │    └─ FreeSurfer (volumetry)                           │ │
│  │                                                        │ │
│  │  IF X-Ray Chest:                                       │ │
│  │    ├─ CheXpert classification                          │ │
│  │    └─ Pneumothorax detection                           │ │
│  └────────────────────────────────────────────────────────┘ │
│       ↓                                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Post-Processing                                       │ │
│  │  • NIfTI → DICOM-SEG conversion                        │ │
│  │  • Findings extraction → structured JSON               │ │
│  │  • Measurement calculation (diameter, volume, HU)      │ │
│  │  • Confidence scoring                                  │ │
│  │  • Result caching (avoid re-processing same study)     │ │
│  └────────────────────────────────────────────────────────┘ │
│       ↓                                                      │
│  Output: DICOM-SEG + JSON Findings → OHIF Viewer            │
└──────────────────────────────────────────────────────────────┘
```

## 4. Component Detail: Reporting Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                   REPORTING PIPELINE                         │
│                                                              │
│  Input: AI Findings + Radiologist Modifications              │
│       ↓                                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Structured Findings Data Model                        │ │
│  │                                                        │ │
│  │  {                                                     │ │
│  │    "study_uid": "...",                                 │ │
│  │    "modality": "CT",                                   │ │
│  │    "body_part": "Chest",                               │ │
│  │    "findings": [                                       │ │
│  │      {                                                 │ │
│  │        "type": "nodule",                               │ │
│  │        "location": "Right Upper Lobe",                 │ │
│  │        "segmentation_id": "...",                       │ │
│  │        "measurements": {                               │ │
│  │          "longest_diameter_mm": 12.3,                  │ │
│  │          "volume_mm3": 920.5,                          │ │
│  │          "mean_hu": -45,                               │ │
│  │          "solid_component_mm": 8.1                     │ │
│  │        },                                              │ │
│  │        "characteristics": ["solid", "spiculated"],     │ │
│  │        "confidence": 0.94,                             │ │
│  │        "status": "accepted",  // accepted/rejected/mod │ │
│  │        "radiologist_notes": ""                         │ │
│  │      }                                                 │ │
│  │    ],                                                  │ │
│  │    "impression": "...",                                │ │
│  │    "classification": "Lung-RADS 3",                    │ │
│  │    "recommendations": ["Follow-up CT in 6 months"]     │ │
│  │  }                                                     │ │
│  └────────────────────────────────────────────────────────┘ │
│       ↓                                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Template Engine                                       │ │
│  │                                                        │ │
│  │  Templates:                                            │ │
│  │  • Lung-RADS (CT Chest)                                │ │
│  │  • LI-RADS (Liver CT/MRI)                              │ │
│  │  • BI-RADS (Mammography - future)                      │ │
│  │  • PI-RADS (Prostate MRI - future)                     │ │
│  │  • Fleischner Society (incidental nodules)             │ │
│  │  • General CT/MRI Report                               │ │
│  │                                                        │ │
│  │  Template fills structured data → formatted report     │ │
│  └────────────────────────────────────────────────────────┘ │
│       ↓                                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Optional: MedGemma 1.5 4B Language Polish (Ollama)    │ │
│  │                                                        │ │
│  │  Endpoint: POST http://localhost:11434/api/generate     │ │
│  │  Model: MedAIBase/MedGemma1.5:4b-it (Q4, ~3 GB)        │ │
│  │                                                        │ │
│  │  Input: Structured report text                         │ │
│  │  Prompt: "Improve the language of this radiology       │ │
│  │           report while preserving all findings and     │ │
│  │           measurements exactly as stated."             │ │
│  │  Output: Polished report text                          │ │
│  │                                                        │ │
│  │  Backup models (if MedGemma unavailable):              │ │
│  │  • medllama2 (3.8 GB) — medical domain knowledge       │ │
│  │  • llama3:8b (4.7 GB) — general language polish        │ │
│  │                                                        │ │
│  │  ⚠️  NEVER generates new findings. Only language.      │ │
│  └────────────────────────────────────────────────────────┘ │
│       ↓                                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Optional: Voice Dictation (faster-whisper, LOCAL)      │ │
│  │                                                        │ │
│  │  Model: faster-whisper large-v3 (~3 GB VRAM)           │ │
│  │  NOTE: Audio → text via Python, NOT Ollama.            │ │
│  │  Ollama only handles text-in → text-out.               │ │
│  │                                                        │ │
│  │  Input: Audio stream from browser microphone           │ │
│  │  Output: Transcribed medical text for report editing   │ │
│  │  Cleanup: OllamaClient.transcribe_medical_speech()     │ │
│  └────────────────────────────────────────────────────────┘ │
│       ↓                                                      │
│  Output: Final Report                                        │
│  ├─ PDF export                                               │
│  ├─ DICOM-SR (Structured Report) → saved to Orthanc         │
│  ├─ FHIR DiagnosticReport (Phase 2+)                        │
│  └─ Copy to clipboard                                       │
└──────────────────────────────────────────────────────────────┘
```

## 5. Technology Stack Summary

| Layer | Technology | Version | Location | Purpose |
|-------|-----------|---------|----------|---------|
| **Viewer** | OHIF Viewer | 3.12 | Local | DICOM web viewer (contour tools, auto-statistics, SAM segmentation) |
| **Rendering** | Cornerstone3D | 2.x | Local | GPU-accelerated medical image rendering |
| **PACS** | Orthanc | Latest | Local | DICOM storage + DICOMweb server |
| **Backend API** | FastAPI | Latest | Local | Python REST API + WebSocket |
| **AI Framework** | MONAI | Latest | Cloud | Medical AI models |
| **Deep Learning** | PyTorch | ≥2.6.0 | Cloud/Local | Neural network runtime (Blackwell sm_120 support) |
| **DICOM Processing** | SimpleITK + pydicom | Latest | Local | DICOM↔NIfTI conversion |
| **Segmentation** | TotalSegmentator | 2.x | Cloud | Auto-anatomy segmentation |
| **Interactive Seg** | nnInteractive | Latest | Cloud | Prompt-based segmentation |
| **Detection** | MONAI Model Zoo | Latest | Cloud | Pathology detection |
| **Report Gen** | MedGemma 1.5 4B | Ollama | **Local** | Report language polish (Q4, ~3 GB) |
| **Voice Dictation** | faster-whisper | large-v3 | **Local** | Speech-to-text for reports (~3 GB VRAM) |
| **Medical LLM** | medllama2 | Ollama | **Local** | Medical text processing |
| **Templates** | Jinja2 | Latest | Local | Report template engine |
| **LLM Runtime** | Ollama | Latest | Local | Local model serving |
| **Database** | PostgreSQL | 16+ | Local | Metadata, findings, audit trail, users |
| **Cache/Queue** | Redis | 7+ | Local | Job queue, result cache, sessions |
| **Task Queue** | Celery | Latest | Local | Async cloud GPU task management |
| **Real-time** | WebSocket | — | Local | AI progress streaming to OHIF |
| **Deployment** | Docker Compose | Latest | Local | Containerized deployment |
| **Cloud GPU** | PyTorch + CUDA | 12.x | Cloud | Segmentation/detection inference |

## 6. Deployment Architecture (Hybrid)

### Local Stack (Your Machine)

```
┌─────────────────────────────────────────────────────────────┐
│                    Local Docker Compose                     │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   OHIF      │  │   Orthanc   │  │   RadAI Backend     │ │
│  │   (React)   │  │   (C++/     │  │   (Python/FastAPI)  │ │
│  │   :3000     │  │    Lua)     │  │   :8000             │ │
│  │             │  │   :4242     │  │                     │ │
│  │             │  │   :8042     │  │  ┌───────────────┐  │ │
│  │             │◄─┤   DICOMweb  │◄─┤  │  DICOM Service│  │ │
│  │             │  │   DICOM     │  │  │  + Cloud API  │  │ │
│  │  Browser    │  │   Storage   │  │  │  Client       │  │ │
│  │  UI         │  └─────────────┘  │  └───────────────┘  │ │
│  │             │                   │                     │ │
│  │             │                   │  ┌───────────────┐  │ │
│  │             │                   │  │  Report Svc   │  │ │
│  │             │                   │  │  (Templates + │  │ │
│  │             │                   │  │   Ollama API) │  │ │
│  └─────────────┘                   └─────────┬─────────┘ │
│                                              │           │
│                                    ┌─────────▼─────────┐ │
│                                    │  Ollama (Local)   │ │
│                                    │  :11434           │ │
│                                    │                   │ │
│                                    │  • MedGemma 1.5 4B│ │
│                                    │    (Q4, ~3 GB)    │ │
│                                    │                   │ │
│                                    │  NOTE: Voice      │ │
│                                    │  dictation uses   │ │
│                                    │  faster-whisper,  │ │
│                                    │  NOT Ollama.      │ │
│                                    └───────────────────┘ │
│                                                         │
│  ┌─────────────────────────┐  ┌───────────────────────┐ │
│  │  PostgreSQL (:5432)     │  │  Redis (:6379)        │ │
│  │                         │  │                       │ │
│  │  • Study metadata       │  │  • Job queue          │ │
│  │  • Findings cache       │  │  • Result cache       │ │
│  │  • Audit log            │  │  • Session state      │ │
│  │  • User accounts        │  │                       │ │
│  │  • RBAC permissions     │  │                       │ │
│  └─────────────────────────┘  └───────────────────────┘ │
│                                                         │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  WebSocket Server (FastAPI)                         │ │
│  │                                                     │ │
│  │  • Real-time AI progress streaming                  │ │
│  │  • Segmentation status updates                      │ │
│  │  • Cloud job status notifications                   │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Cloud GPU Server (Segmentation/Detection Models)

```
┌─────────────────────────────────────────────────────────────┐
│              Cloud GPU Instance (RunPod/Vast.ai/etc)        │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  MONAI Inference Server (FastAPI + PyTorch + CUDA)   │ │
│  │                                                       │ │
│  │  Endpoints:                                           │ │
│  │  POST /api/v1/segment/totalsegmentator                │ │
│  │  POST /api/v1/segment/nninteractive                   │ │
│  │  POST /api/v1/segment/medsam2                         │ │
│  │  POST /api/v1/detect/lung-nodule                      │ │
│  │  POST /api/v1/detect/chexpert                         │ │
│  │  POST /api/v1/segment/voxtell                         │ │
│  │                                                       │ │
│  │  Models loaded on startup (or lazy):                  │ │
│  │  • TotalSegmentator full-res (~12+ GB VRAM)           │ │
│  │  • nnInteractive (~6-10 GB VRAM)                      │ │
│  │  • MedSAM2 (~6-10 GB VRAM)                            │ │
│  │  • MONAI Lung Nodule Detection (~4-8 GB VRAM)        │ │
│  │  • VoxTell (~6-10 GB VRAM)                            │ │
│  │  • LungMask (~2-4 GB VRAM)                            │ │
│  │                                                       │ │
│  │  Total VRAM needed: ~16-24 GB (fits RTX 3090/4090)   │ │
│  │  Or run models sequentially on smaller GPU            │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  GPU: RTX 3090/4090 (24 GB) or A100 (40-80 GB)            │
│  Cost: ~$0.40-0.70/hr (RunPod), ~$0.20-0.40/hr (Vast.ai)  │
└─────────────────────────────────────────────────────────────┘
```

### Network Flow

```
Local Machine                          Cloud GPU Server
─────────────                          ──────────────────
OHIF (:3000)
  ↕ DICOMweb
Orthanc (:4242, :8042)
  ↕ HTTP + WebSocket
RadAI Backend (:8000) ──HTTPS──────►  MONAI Inference Server
  ↕ HTTP (localhost)                      ↕
  ↕ TCP (localhost)
PostgreSQL (:5432)                    NVIDIA GPU (CUDA)
  ↕ TCP (localhost)
Redis (:6379)
  ↕ HTTP (localhost)
Ollama (:11434)
```

### Volumes (Local)

- `orthanc-db`: Persistent DICOM storage
- `postgres-data`: Study metadata, findings, audit trail, user accounts
- `redis-data`: Job queue persistence, cached results
- `temp-processing`: Temporary NIfTI files (cleaned after cloud round-trip)
- `reports`: Generated reports (PDF, DICOM-SR)

### Cost Estimate (Cloud GPU)

| Usage Pattern | GPU | Hours/Month | Cost/Month |
|--------------|-----|-------------|------------|
| Light (10 studies/day) | RTX 4090 | ~5 hrs | $6-10 |
| Medium (30 studies/day) | RTX 4090 | ~15 hrs | $18-30 |
| Heavy (100+ studies/day) | A100 | ~40 hrs | $40-60 |

**Tip**: Use auto-shutdown on cloud GPU. Spin up only when processing needed.

## 7. Security & Compliance Considerations

```
┌─────────────────────────────────────────────────────────────┐
│                    Security Layers                           │
│                                                             │
│  1. Network                                                  │
│     • Local-only deployment (no external exposure)           │
│     • Docker internal network isolation                      │
│     • No data leaves the machine                             │
│                                                             │
│  2. Data                                                     │
│     • DICOM anonymization before AI processing               │
│     • Temporary files encrypted at rest                      │
│     • Auto-cleanup of temp processing files                  │
│                                                             │
│  3. Access                                                   │
│     • Optional authentication (Orthanc basic auth)           │
│     • No multi-user in Phase 1 (single radiologist)          │
│     • Audit log for all AI operations                        │
│                                                             │
│  4. AI Safety                                                │
│     • Human-in-the-loop: AI suggests, radiologist confirms   │
│     • Confidence scores on all AI findings                   │
│     • Clear labeling of AI-generated vs. radiologist content │
│     • No autonomous reporting                                │
│                                                             │
│  5. Regulatory                                               │
│     • Research/personal use only (not FDA cleared)           │
│     • Clear disclaimer on all reports                        │
│     • SaMD awareness for future distribution                 │
└─────────────────────────────────────────────────────────────┘
```

## 8. File Structure (Proposed)

```
RadAI/
├── docker-compose.yml              # Orchestration
├── .env                            # Configuration
├── RESEARCH.md                     # This research document
├── ARCHITECTURE.md                 # This document
│
├── viewer/                         # OHIF Viewer v3.12 (native extensions, NOT forked)
│   ├── platform/                   # OHIF platform
│   ├── extensions/                 # Custom RadAI extensions
│   │   ├── radai-ai-tools/        # AI tools panel extension
│   │   ├── radai-reporting/       # Reporting panel extension
│   │   └── radai-findings/        # Findings panel extension
│   └── public/                     # Static assets
│
├── backend/                        # RadAI FastAPI Backend
│   ├── app/
│   │   ├── main.py                # FastAPI app entry
│   │   ├── config.py              # Configuration
│   │   ├── dicom/                 # DICOM processing
│   │   │   ├── converter.py       # DICOM ↔ NIfTI
│   │   │   ├── metadata.py        # Metadata extraction
│   │   │   └── seg_export.py      # DICOM-SEG generation
│   │   ├── ai/                    # AI model orchestration
│   │   │   ├── models.py          # Model registry
│   │   │   ├── totalsegmentator.py
│   │   │   ├── nninteractive.py
│   │   │   ├── medsam2.py
│   │   │   ├── detection.py       # Nodule/lesion detection
│   │   │   └── medgemma.py        # Report generation
│   │   ├── reporting/             # Report generation
│   │   │   ├── templates/         # Report templates
│   │   │   │   ├── lung_rads.j2
│   │   │   │   ├── li_rads.j2
│   │   │   │   └── general_ct.j2
│   │   │   ├── engine.py          # Template engine
│   │   │   └── dicom_sr.py        # DICOM-SR generation
│   │   └── api/                   # API routes
│   │       ├── studies.py
│   │       ├── ai.py
│   │       └── reports.py
│   ├── models/                    # Downloaded model weights
│   │   ├── totalsegmentator/
│   │   ├── nninteractive/
│   │   ├── medsam2/
│   │   └── detection/
│   ├── tests/
│   └── requirements.txt
│
├── orthanc/                        # Orthanc configuration
│   ├── orthanc.json
│   └── plugins/
│
└── docs/                           # Documentation
    ├── setup.md
    ├── models.md
    └── api.md
```

## 9. Phase 1 Implementation Plan (CT Chest AI Assistant)

### Sprint 1 (Week 1-2): Infrastructure
- [ ] Set up OHIF v3.12 with native extensions (DO NOT fork OHIF-AI — stale project)
- [ ] Set up Docker Compose with OHIF + Orthanc + Backend skeleton
- [ ] Configure DICOMweb communication between OHIF and Orthanc
- [ ] Test local DICOM file import

### Sprint 2 (Week 3-4): TotalSegmentator Integration
- [ ] Integrate TotalSegmentator in backend
- [ ] DICOM → NIfTI → TotalSegmentator → DICOM-SEG pipeline
- [ ] Display segmentation overlays in OHIF
- [ ] Test with sample CT Chest studies

### Sprint 3 (Week 5-6): Lung Nodule Detection
- [ ] Integrate MONAI Lung Nodule Detection model
- [ ] Auto-detect nodules → findings JSON
- [ ] Display findings panel in OHIF
- [ ] Click finding → jump to slice + highlight

### Sprint 4 (Week 7-8): Interactive Refinement
- [ ] Integrate nnInteractive for manual refinement
- [ ] Point/scribble/bbox tools in OHIF
- [ ] Live segmentation feedback
- [ ] Measurement tools (diameter, volume, HU)

### Sprint 5 (Week 9-10): Reporting
- [ ] Build findings panel UI (accept/reject/modify)
- [ ] Implement Lung-RADS template engine
- [ ] DICOM-SR export
- [ ] PDF report generation

### Sprint 6 (Week 11-12): Polish & Testing
- [ ] End-to-end testing with real studies
- [ ] Performance optimization
- [ ] UI/UX refinement
- [ ] Documentation
