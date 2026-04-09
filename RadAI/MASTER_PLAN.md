# RadAI — Unified Master Plan

## 1. Hardware Reality Check

**Your GPU**: RTX 5060 (8 GB GDDR7 VRAM) + 32 GB RAM

**The constraint**: You cannot run two AI models simultaneously. 8 GB fits one model at a time.

**The solution**: A model scheduler that loads → runs → unloads → loads next. Heavy batch jobs go to cloud GPU.

---

## 2. Architecture: Decoupled Microservices

The system follows a **Decoupled Microservices Architecture**. Storage, visualization, and intelligence are separate services communicating via APIs.

| Layer | Component | Purpose |
|-------|-----------|---------|
| **Storage** | Orthanc + PostgreSQL | DICOM storage, metadata indexing, audit trail |
| **Visualization** | OHIF Viewer v3.12 | Web-based MPR, volume rendering, annotations, contour tools, auto-statistics |
| **Inference** | MONAI Label + Model Scheduler | GPU-accelerated AI model management |
| **Orchestration** | FastAPI (Python) | Backend logic, reporting, cloud API routing, WebSocket progress |
| **Reasoning** | MedGemma 1.5 4B (Ollama) | Report language polish, local LLM |
| **Cloud Reasoning** | Gemma 4 31B (OpenRouter) | Tier 2 premium report polishing for complex cases |
| **Queue** | Redis + Celery | Async job management, cloud GPU task routing |
| **Voice** | faster-whisper (local) | Medical speech-to-text for report dictation |

**Core Principle**: Never ask an LLM to "look" at DICOM images. LLMs cannot see 16-bit depth — they only see 8-bit screenshots. Always use MONAI to extract quantitative data first (volumes, diameters, HU values), then use the LLM only for textual reasoning based on that structured data.

---

## 3. VRAM Budget — Every Model

| Model | VRAM | Fits 8 GB? | Strategy |
|-------|------|-----------|----------|
| **OHIF Viewer** | 0 (browser) | Yes | Runs in browser |
| **Orthanc** | 0 (CPU/disk) | Yes | CPU + disk only |
| **TotalSegmentator --fast --body_seg** | ~2 GB | Yes | Low-res + body crop, ~15 sec/study |
| **TotalSegmentator --fast** | ~2-3 GB | Yes | Low-res 3mm, ~15 sec/study |
| **TotalSegmentator --roi_subset** | ~3-5 GB | Yes | Full-res specific organs only |
| **TotalSegmentator full** | ~12+ GB | **NO** | ⚠️ Cloud-only (Tier 3). Needs 12+ GB VRAM. |
| **nnInteractive** | 6-10 GB | Tight but yes | Works for standard volumes |
| **LiteMedSAM** | ~2-3 GB | Yes | Lightweight fallback |
| **MedSAM2** | ~6-8 GB | Marginal | May OOM on large 3D volumes |
| **MedGemma 1.5 4B (Q4 Ollama)** | ~3 GB | Yes | 4-bit quantized |
| **MedGemma 1.5 4B (FP16)** | ~8-10 GB | Yes (alone) | Full precision, fits alone |
| **faster-whisper large-v3** | ~3 GB | Yes | Medical speech-to-text |
| **SAM3 / VoxTell** | ~8-12 GB | Marginal | Cloud API preferred |
| **MONAI Brain 133-cls** | ~4-6 GB | Yes (alone) | After TotalSeg freed |

**Golden rule: NEVER load two models simultaneously.**

---

## 3. Unified Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      BROWSER (Client)                           │
│              OHIF Viewer v3.12 (native extensions)             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐│
│  │ Cornerstone3D│ │  RadAI       │ │  RadAI                   ││
│  │ Rendering    │ │  AI Tools    │ │  Reporting               ││
│  │ • MPR        │ │ • Auto-      │ │ • Findings Panel         ││
│  │ • Volume     │ │   Detect     │ │ • Accept/Reject/Modify   ││
│  │ • Windowing  │ │ • Segment    │ │ • Template Reports       ││
│  │ • Annotate   │ │ • Refine     │ │ • Lung-RADS/BI-RADS      ││
│  │ • Built-in   │ │              │ │ • Voice Dictation        ││
│  │   AI Tools   │ │              │ │ • MedASR (optional)      ││
│  └──────────────┘ └──────────────┘ └──────────────────────────┘│
└──────────────────────────────┬──────────────────────────────────┘
                               │ DICOMweb + REST API + WebSocket
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                  LOCAL BACKEND (Your PC)                        │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ Orthanc      │  │ MONAI Label   │  │ Model Scheduler     │  │
│  │ DICOM Server │  │ Server        │  │ (load/unload models │  │
│  │ (CPU+disk)   │  │ (GPU broker)  │  │  one at a time)     │  │
│  └──────────────┘  └──────────────┘  └─────────────────────┘  │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ PostgreSQL   │  │ Redis        │  │ WebSocket Server    │  │
│  │ (metadata,   │  │ (job queue,  │  │ (real-time AI       │  │
│  │  audit log,  │  │  cache)      │  │  progress stream)   │  │
│  │  findings)   │  │              │  │                     │  │
│  └──────────────┘  └──────────────┘  └─────────────────────┘  │
│                                                                 │
│  LOCAL GPU MODELS (one at a time, 8 GB budget):                │
│  ┌────────────────┐ ┌────────────────┐ ┌──────────────────┐   │
│  │ TotalSegmentator│ │ nnInteractive  │ │ LiteMedSAM       │   │
│  │ (batch, unload)│ │ (interactive)  │ │ (fallback seg)   │   │
│  └────────────────┘ └────────────────┘ └──────────────────┘   │
│                                                                 │
│  LOCAL LLM (via Ollama, loads when GPU is free):               │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ MedGemma 1.5 4B Q4 (~3 GB) — draft report generation      │ │
│  │ MedASR — medical speech-to-text for dictation             │ │
│  │ medllama2 (3.8 GB) — medical text backup                  │ │
│  │ llama3:8b (4.7 GB) — general language fallback            │ │
│  └───────────────────────────────────────────────────────────┘ │
└───────────────────┬──────────────────────┬──────────────────────┘
                    │                      │
          Anonymized DICOM          Structured findings
          for segmentation          for report polish
                    │                      │
                    ▼                      ▼
┌──────────────────────────┐  ┌──────────────────────────────────┐
│  CLOUD GPU (on demand)   │  │  LOCAL Ollama (always available) │
│  RunPod/Vast.ai/Lambda   │  │                                  │
│                          │  │  POST http://localhost:11434     │
│  • TotalSegmentator full │  │  /api/generate                   │
│  • nnInteractive (large) │  │                                  │
│  • MedSAM2 / SAM3        │  │  Model: MedGemma1.5:4b-it        │
│  • VoxTell               │  │  (or medllama2 / llama3:8b)      │
│  • Large MRI volumes     │  │                                  │
│                          │  │  Input: structured findings text │
│                          │  │  Output: polished report prose   │
│  Cost: $0.20-0.70/hr     │  │  Cost: $0 (local, offline)       │
└──────────────────────────┘  └──────────────────────────────────┘
```

---

## 4. Model Scheduler (Critical for 8 GB)

> **Implementation**: See [`backend/app/scheduler.py`](./backend/app/scheduler.py) for the production-ready, thread-safe implementation.

Key design decisions implemented in the full `ModelScheduler`:

- **`threading.Lock()`** — prevents concurrent GPU loads from parallel HTTP requests
- **`subprocess.TimeoutExpired`** — TotalSegmentator hard timeout (default 300s) to prevent hangs
- **`subprocess.CalledProcessError`** — non-zero exit captured and surfaced as `ModelSchedulerError`
- **`ModelType` enum** — tracks which model is loaded; skips reload if already loaded (e.g. nnInteractive sessions)
- **`gc.collect()`** — forces Python GC after `del model` to return host RAM
- **`torch.cuda.empty_cache()`** — returns VRAM to the CUDA allocator
- **`get_scheduler()` singleton** — one scheduler per process, safe for FastAPI + Celery

**Verified local models** (from `ollama list`):
- ✅ `MedAIBase/MedGemma1.5:4b-it` — confirmed installed (5.6 GB)
- ✅ `minimax-m2.5:cloud` — general LLM fallback (7.8 GB)

---

## 5. Three Tiers of Execution

### Tier 1: Local (Always Available, No Internet)

| Model | Use | VRAM | Command |
|-------|-----|------|---------|
| **TotalSegmentator --fast --body_seg** | Quick 117-class overview | ~2 GB | `TotalSegmentator -i ct.nii -o out/ --fast --body_seg --gpu` |
| **TotalSegmentator --roi_subset** | Full-res specific organs | ~3-5 GB | `TotalSegmentator -i ct.nii -o out/ --roi_subset liver spleen --gpu` |
| **nnInteractive** | Interactive pathology segmentation | 6-8 GB | Load on first click, unload when done |
| **LiteMedSAM** | Bounding-box segmentation fallback | 2-3 GB | Draw box → get mask |
| **MedGemma 1.5 4B (Ollama)** | Report language polish | ~3 GB | `ollama pull MedAIBase/MedGemma1.5:4b-it` |
| **faster-whisper large-v3** | Medical speech-to-text | ~3 GB | Local voice dictation (replaces MedASR) |

### Tier 2: Cloud API (Pay-Per-Use)

| Service | Model | Cost | Use Case |
|---------|-------|------|----------|
| **OpenRouter** | **Gemma 4 31B** (`google/gemma-4-31b-it`) | ~$0.01-0.05/study | **Premium report polishing** — frontier-quality for complex/ambiguous cases. Text-only, no DICOM pixels sent. |
| **Hugging Face Inference** | MedGemma 1.5 4B | Free tier + paid | Higher throughput report generation |
| **Google Vertex AI** | MedGemma 1.5 4B | ~$0.05-0.15/study | Complex case reports with 3D image understanding |
| **Replicate** | SAM2, MedSAM | ~$0.000225/sec | On-demand segmentation |

> **Gemma 4 31B routing**: `POST https://openrouter.ai/api/v1/chat/completions` with `model: google/gemma-4-31b-it` and `Authorization: Bearer $OPENROUTER_API_KEY`. Only structured text is sent — no DICOM pixel data ever leaves the machine on Tier 2. Includes automatic retry (3 attempts with exponential backoff) for reliability.

### Tier 3: Cloud GPU Instance (Batch Processing)

| Provider | GPU | Cost/Hour | Use Case |
|----------|-----|-----------|----------|
| **RunPod** | RTX 4090 (24GB) | $0.44 | All models simultaneously |
| **Vast.ai** | RTX 4090 (24GB) | $0.20-0.35 | Cheapest, variable reliability |
| **Lambda** | A100 (80GB) | $1.10 | Enterprise batch pipelines |

---

## 6. Data Flow: Complete CT Study Analysis

```
1. LOAD STUDY
   Radiologist opens CT Chest study in OHIF
   OHIF fetches DICOM via DICOMweb from local Orthanc
   Cornerstone3D renders slices, MPR, volume

2. BATCH PHASE (Automatic, Background)
   ┌─────────────────────────────────────────────────┐
   │ Model Scheduler: Load TotalSegmentator          │
   │ DICOM → NIfTI → TotalSegmentator --fast --body_seg │
   │ Results: 117 anatomical structures segmented    │
   │ UNLOAD TotalSegmentator → torch.cuda.empty      │
   └─────────────────────────────────────────────────┘

3. INTERACTIVE PHASE (Radiologist Opens Study)
   ┌─────────────────────────────────────────────┐
   │ Model Scheduler: Load nnInteractive         │
   │ Radiologist clicks on suspicious area       │
   │ Point/scribble/bbox → 3D segmentation       │
   │ Measurements calculated (diameter, volume)  │
   │ When done: UNLOAD nnInteractive             │
   └─────────────────────────────────────────────┘

4. FINDINGS REVIEW
   OHIF displays:
   ├─ Segmentation overlays (color-coded)
   ├─ Findings panel with detected abnormalities
   ├─ Measurements (size, volume, HU)
   └─ Key image markers

   Radiologist reviews each finding:
   ├─ Accept / Reject / Modify
   ├─ Add descriptors, clinical context
   └─ Assign classification (Lung-RADS, etc.)

5. REPORT GENERATION (3 Tiers)
   ┌─────────────────────────────────────────────┐
   │ Tier 1: Template Engine (instant, free)     │
   │   Structured findings → Lung-RADS template  │
   │                                              │
   │ Tier 2: MedGemma 4B via Ollama (~30 sec)    │
   │   Template text → polished radiology prose  │
   │   Runs locally, offline, no data leaves PC   │
   │                                              │
│ Tier 3: MedGemma 1.5 4B via Cloud API (~$0.05-0.15, ~10 sec)│
│   For complex cases, multimodal (3D scan understanding)     │
│   Anonymized data only, HTTPS                                │
   └─────────────────────────────────────────────┘

6. SAVE & ARCHIVE
   ├─ Report saved to Orthanc (DICOM-SR)
   ├─ Segmentations saved (DICOM-SEG)
   └─ Study linked to report for future reference
```

---

## 7. Anonymization Pipeline (Before Cloud Upload)

```
┌─────────────────────────────────────────────────────────────┐
│              DATA PRIVACY PIPELINE                           │
│                                                              │
│  1. DICOM Study loaded locally (Orthanc)                    │
│     ↓                                                        │
│  2. RadAI Backend extracts pixel data + metadata            │
│     ↓                                                        │
│  3. ANONYMIZATION (before any cloud upload)                 │
│     • Remove: Patient Name, ID, DOB, Sex, Institution        │
│     • Remove: Study Date, Accession Number, Referring MD     │
│     • Keep: Pixel data, spacing, orientation, modality       │
│     • Replace: StudyInstanceUID with random UUID             │
│     ↓                                                        │
│  4. Convert to NIfTI (smaller, cloud-model friendly)        │
│     ↓                                                        │
│  5. HTTPS upload to cloud GPU or API                        │
│     ↓                                                        │
│  6. Cloud processes → returns SEG + JSON findings           │
│     (cloud server auto-deletes NIfTI after processing)       │
│     ↓                                                        │
│  7. Results mapped back to original DICOM Study UID         │
│     ↓                                                        │
│  8. SEG overlays + findings displayed in OHIF               │
│     ↓                                                        │
│  9. Structured findings → LOCAL Ollama (MedGemma 4B)        │
│     (NO patient data sent — only structured text findings)   │
│     ↓                                                        │
│  10. Polished report → saved locally to Orthanc (DICOM-SR)  │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Report Generation — 3-Tier Strategy

### Level 1: Template Engine (Free, Instant, Offline)

```
CT ABDOMEN AND PELVIS WITH CONTRAST

TECHNIQUE: Axial images from the diaphragm to symphysis pubis
after IV contrast administration.

FINDINGS:
- Liver: {liver_volume} ml. {lesion_count} focal lesion(s) identified.
  {lesion_details}
- Spleen: {spleen_volume} ml. {spleen_status}.
- Kidneys: Right {r_vol} ml, Left {l_vol} ml. {renal_findings}.
- Pancreas: {pancreas_status}.
- Adrenals: {adrenal_status}.
- Aorta: {aorta_status}.
- Lymph nodes: {lymph_status}.
- Bowel: {bowel_status}.
- Bones: {bone_status}.

IMPRESSION:
{impression}

Classification: {lung_rads_or_li_rads}
Recommendations: {recommendations}
```

### Level 2: MedGemma 4B via Ollama (Free, ~30 sec, Offline)

Feed structured findings as text. MedGemma rewrites into natural radiology prose. Quality is decent for straightforward cases.

### Level 3: MedGemma 1.5 4B via Cloud API (~$0.05-0.15, ~10 sec, Online)

For complex cases. Supports 3D scan understanding natively (multimodal). Same 4B model but with more throughput and full precision.

**You always make the final call.** Every AI-generated report is a draft requiring your review, modification, and sign-off.

---

## 9. Practical VRAM Management

### Maximize Available VRAM

```bash
# Close all GPU-using applications before running AI
nvidia-smi

# Kill lingering Python/PyTorch processes:
fuser -v /dev/nvidia* 2>/dev/null | awk '{print $2}' | xargs -r kill

# Set environment to minimize PyTorch VRAM overhead:
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

### TotalSegmentator Memory-Saving Options

```bash
# Fast + body crop (recommended for 8 GB, ~2 GB VRAM):
TotalSegmentator -i ct.nii.gz -o output/ --fast --body_seg --gpu

# Fast mode without body crop (~2-3 GB VRAM):
TotalSegmentator -i ct.nii.gz -o output/ --fast --gpu

# Specific organs only (full-res, ~3-5 GB VRAM):
TotalSegmentator -i ct.nii.gz -o output/ --roi_subset liver spleen kidneys --gpu

# Full resolution — REQUIRES 12+ GB VRAM (cloud-only on 8 GB GPU):
# TotalSegmentator -i ct.nii.gz -o output/ --gpu

# CPU fallback (slow but no VRAM):
TotalSegmentator -i ct.nii.gz -o output/ --device cpu
```

### Ollama Memory Management

```bash
# Check loaded models:
ollama ps

# Unload a model to free VRAM:
ollama stop MedAIBase/MedGemma1.5:4b-it

# Set VRAM limit for Ollama:
export OLLAMA_MAX_VRAM=4000000000  # 4 GB max

# Ollama auto-offloads to CPU if GPU is busy
```

---

## 10. Project Structure

```
RadAI/
├── /docker                         # Docker orchestration
│   ├── /orthanc
│   │   ├── orthanc.json
│   │   └── plugins/
│   ├── /ohif
│   │   └── app-config.js
│   ├── /postgres
│   │   ├── init.sql               # Schema: studies, findings, audit_log, users
│   │   └── schema/
│   │       ├── studies.sql
│   │       ├── findings.sql
│   │       ├── audit_log.sql
│   │       └── users.sql
│   ├── /redis
│   │   └── redis.conf
│   └── docker-compose.yml          # Full stack: OHIF + Orthanc + PostgreSQL + Redis + Backend
│
├── viewer/                         # OHIF Viewer (v3.10+ extended)
│   ├── platform/                   # OHIF platform
│   ├── extensions/
│   │   ├── radai-ai-tools/        # AI tools panel extension
│   │   ├── radai-reporting/       # Reporting panel extension
│   │   ├── radai-findings/        # Findings panel extension
│   │   └── radai-voice/           # Voice dictation (MedASR) extension
│   └── public/
│
├── backend/                        # RadAI FastAPI Backend
│   ├── app/
│   │   ├── main.py                # FastAPI entry point
│   │   ├── config.py              # Pydantic settings
│   │   ├── scheduler.py           # Model scheduler (load/unload)
│   │   ├── websocket.py           # WebSocket for real-time AI progress
│   │   ├── feature_extractor.py   # Query MONAI API for segmentation stats
│   │   ├── dicom/
│   │   │   ├── converter.py       # DICOM ↔ NIfTI
│   │   │   ├── anonymizer.py      # DICOM anonymization
│   │   │   ├── metadata.py        # Metadata extraction
│   │   │   └── seg_export.py      # DICOM-SEG generation
│   │   ├── ai/
│   │   │   ├── models.py          # Model registry
│   │   │   ├── totalsegmentator.py
│   │   │   ├── nninteractive.py
│   │   │   ├── litemedsam.py
│   │   │   └── detection.py
│   │   ├── reporting/
│   │   │   ├── templates/
│   │   │   │   ├── lung_rads.j2
│   │   │   │   ├── li_rads.j2
│   │   │   │   └── general_ct.j2
│   │   │   ├── engine.py          # Jinja2 template engine
│   │   │   ├── rag_pipeline.py    # RAG: retrieve findings → augment context → generate
│   │   │   ├── ollama_client.py   # Local MedGemma 1.5 via Ollama
│   │   │   ├── medasr_client.py   # MedASR voice dictation
│   │   │   └── dicom_sr.py        # DICOM-SR generation
│   │   ├── db/
│   │   │   ├── models.py          # SQLAlchemy models
│   │   │   ├── session.py         # DB session management
│   │   │   └── queries.py         # Study/finding/audit queries
│   │   ├── queue/
│   │   │   ├── celery_app.py      # Celery configuration
│   │   │   └── tasks.py           # Async cloud GPU tasks
│   │   └── api/
│   │       ├── studies.py
│   │       ├── ai.py
│   │       ├── reports.py
│   │       └── auth.py            # JWT authentication
│   ├── models/                    # Model weights (gitignored)
│   └── requirements.txt
│
├── cloud/                          # Cloud GPU server config
│   ├── Dockerfile                  # MONAI inference server
│   ├── docker-compose.yml          # Cloud stack
│   └── deploy.sh                   # RunPod/Vast.ai deployment
│
├── /data                           # Persistent DICOM storage (Orthanc + PostgreSQL)
│
├── .env                            # Environment variables (API keys, paths, JWT secret)
├── MASTER_PLAN.md                  # This document
├── RESEARCH.md                     # Competitive analysis
├── ARCHITECTURE.md                 # System diagrams
│
└── docs/
    ├── setup.md
    ├── models.md
    └── api.md
```

---

## 11. Security & Privacy (Mandatory)

Before any clinical testing, implement these layers:

### 11.1 De-identification
- Use `pydicom` to scrub Patient Name, DOB, ID, Institution before files touch AI/LLM layers
- Replace StudyInstanceUID with random UUID for cloud uploads
- Keep pixel data, spacing, orientation, modality intact

### 11.2 Transport Security
- TLS/SSL: All traffic between Orthanc and browser must be encrypted (HTTPS)
- Use Nginx reverse proxy with Let's Encrypt certificates
- Internal Docker network isolation for service-to-service communication

### 11.3 Authentication & Authorization
- JWT-based auth for OHIF frontend and backend API
- Keycloak for enterprise SSO (optional, Phase 3+)
- Role-based access: Radiologist (full), Resident (read + draft), Admin (system config)
- Password hashing with bcrypt, token expiry (24h access, 7d refresh)

### 11.4 Data Governance
- Audit log for all AI operations (who ran what, when, results) — stored in PostgreSQL
- Auto-cleanup of temporary NIfTI files after processing
- Persistent DICOM storage encrypted at rest
- Cloud API contracts: HTTPS + auth tokens + auto-delete on cloud server
- Configurable data retention policies (30/90/365 days) with auto-cleanup

---

## 12. Day-One Action Plan

1. **Install Docker + NVIDIA Container Toolkit**
2. **Deploy Orthanc + OHIF** (no GPU needed) — test DICOM loading
3. **Verify Ollama is running** — `ollama ps` should show your models
4. **Install TotalSegmentator:** `pip install TotalSegmentator`
5. **Upload a test CT study** to Orthanc
6. **Run TotalSegmentator --fast** on the study → view segmentation masks in OHIF
7. **Test Ollama with MedGemma:** `ollama run MedAIBase/MedGemma1.5:4b-it` — verify it responds to medical prompts
8. **Clone OHIF-AI** and configure it to talk to your local backend
9. **Test nnInteractive** — load after TotalSegmentator finishes, click on an organ
10. **Evaluate:** Is the one-at-a-time workflow acceptable for your clinical needs?

---

## 13. Phase Plan

### Phase 0: The Backbone — Storage & View (Week 1-2)
- [ ] Docker + Orthanc + PostgreSQL + Redis + OHIF v3.12 deployed and communicating
- [ ] Ollama verified with MedGemma 1.5 4B (Q4 quantization)
- [ ] PyTorch ≥2.6.0 verified for Blackwell (sm_120) RTX 5060 support
- [ ] TLS/SSL configured for browser-to-Orthanc traffic
- [ ] JWT authentication for OHIF frontend
- [ ] WebSocket endpoint for real-time AI progress streaming (120s heartbeat)
- [ ] **Test OHIF v3.12 built-in AI + contour tools** — contour tools + auto-statistics cover ~70% of Phase 1 interactive UI
- [ ] **Verification:** Drag-and-drop a CT scan into Orthanc → see it rendered in OHIF with Axial, Coronal, and Sagittal views (MPR)

### Phase 1: The Brain — AI Segmentation (Weeks 3-6)
- [ ] Model scheduler implemented (load→run→unload with `torch.cuda.empty_cache()`)
- [ ] TotalSegmentator --fast integrated (batch phase)
- [ ] DICOM → NIfTI → SEG pipeline working
- [ ] Feature extraction: query MONAI API for segmentation statistics (volumes, diameters, HU values)
- [ ] Segmentation overlays visible in OHIF
- [ ] nnInteractive integrated for interactive refinement
- [ ] **Verification:** Click "Run AI" in OHIF → color-coded organ masks overlay on the CT in real-time

### Phase 2: The Voice — Report Generation (Weeks 7-10)
- [ ] Findings panel UI (accept/reject/modify)
- [ ] Feature extraction pipeline: segmentation stats → structured JSON
- [ ] RAG pipeline: retrieve findings → augment context → generate report draft
- [ ] Template engine (Jinja2) with Lung-RADS template
- [ ] Ollama MedGemma 1.5 4B integration for report polish
- [ ] faster-whisper voice dictation integration for hands-free report editing
- [ ] Audit trail database schema + audit middleware (PostgreSQL)
- [ ] DICOM-SR export to Orthanc
- [ ] PDF report generation
- [ ] FHIR DiagnosticReport export (future-proofing)
- [ ] **Verification:** Run AI on a study → review findings → click "Generate Report" → get a structured radiology report with Findings and Impression sections

### Phase 3: Cloud Integration (Weeks 11-14)
- [ ] Cloud GPU server setup (RunPod Docker image)
- [ ] Celery + Redis async job queue for cloud tasks
- [ ] Anonymization pipeline before cloud upload
- [ ] Cloud model API endpoints (TotalSegmentator full, MedSAM2, VoxTell)
- [ ] MedGemma 1.5 4B cloud API for complex reports (multimodal 3D understanding)
- [ ] DICOMweb proxy mode for hospital PACS integration
- [ ] Result caching (never re-process same study)
- [ ] **Verification:** Process a study on cloud GPU → results appear in local OHIF → no patient data stored on cloud

### Phase 4: Expansion (Weeks 15-20)
- [ ] Brain MRI support (MONAI brain bundle, 133 structures)
- [ ] Chest X-Ray classification (CheXpert)
- [ ] LiteMedSAM integration as fallback segmentation
- [ ] Multi-study comparison (prior studies side-by-side)
- [ ] Performance optimization (model loading speed, inference time)
- [ ] **Verification:** Load a brain MRI → auto-segment 133 structures → interactive tumor refinement → generate report

### Phase 5: Mammography + Ultrasound (Weeks 21-28)
- [ ] Viewing + interactive segmentation only (limited AI models available)
- [ ] Report templates for BI-RADS
- [ ] MedGemma for report polish
- [ ] **Verification:** Load mammography → interactive segmentation → BI-RADS report generation

---

## 14. Safety Rules (CRITICAL)

1. **NEVER** generate medical findings with LLMs. LLMs only polish language of pre-validated structured data.
2. **ALWAYS** mark AI-generated content clearly in reports.
3. **NEVER** commit DICOM files, patient data, or model weights to the repository.
4. **ALWAYS** anonymize DICOM data before cloud processing.
5. **ALWAYS** include confidence scores on all AI findings.
6. **NEVER** load two models simultaneously on 8 GB GPU. Use the scheduler.
7. **ALWAYS** verify AI segmentations visually before using measurements.
8. **NEVER** ask an LLM to "look" at DICOM images — they only see 8-bit screenshots, not 16-bit depth.
9. **ALWAYS** log AI operations to audit trail (who, what, when, result).
10. **NEVER** store cloud-processed data on remote servers beyond processing time.

---

## 15. GPU Upgrade Path

| GPU | VRAM | Price | What It Unlocks |
|-----|------|-------|-----------------|
| **RTX 5060 Ti 16 GB** | 16 GB | ~$450 | Two models concurrently, eliminates most scheduling complexity |
| **RTX 4090 (used)** | 24 GB | ~$1,200 | All models locally, MedGemma 1.5 4B + nnInteractive simultaneously |
| **RTX 5080** | 16 GB | ~$1,000 | Fast inference, two concurrent models |
| **RTX A6000 (used)** | 48 GB | ~$2,000 | Full MedGemma 1.5 4B FP16 locally, entire stack concurrent |

**Best value upgrade**: RTX 5060 Ti 16 GB (~$450). Doubling VRAM eliminates most scheduling complexity.

**Note**: MedGemma 27B no longer exists in the 1.5 release. The 4B variant is the only option, and it runs locally on 8 GB with Q4 quantization.

---

## 16. Cost Estimates

| Scenario | Cloud GPU Hours | Monthly Cost | Notes |
|----------|----------------|--------------|-------|
| **Light** (5 studies/day) | ~15 hrs | $7-10 | RunPod RTX 4090 auto-shutdown |
| **Medium** (20 studies/day) | ~60 hrs | $26-35 | Includes batch processing |
| **Heavy** (50+ studies/day) | ~150 hrs | $66-80 | Consider dedicated instance |

**Compare to commercial radiology AI**: $5,000-50,000/year. This is **10-100x cheaper**.

---

## 17. Key Repositories

| Component | Link | License |
|-----------|------|---------|
| OHIF Viewer | github.com/OHIF/Viewers | MIT |
| OHIF v3.10 Release | ohif.org/newsletters/2025-04-09 | — |
| OHIF-AI | github.com/CCI-Bonn/OHIF-AI | Apache 2.0 |
| TotalSegmentator | github.com/wasserth/TotalSegmentator | Apache 2.0 |
| nnInteractive | pypi.org/project/nnInteractive | Apache 2.0 |
| MONAI Label | github.com/Project-MONAI/MONAILabel | Apache 2.0 |
| LiteMedSAM | github.com/bowang-lab/MedSAM | Apache 2.0 |
| MedGemma 1.5 4B | huggingface.co/google/medgemma-1.5-4b-it | Gemma |
| MedASR | developers.google.com/health-ai-developer-foundations | Gemma |
| Ollama | ollama.com | MIT |
| Orthanc | orthanc-server.com | GPL |

---

*Updated April 2026. Reflects MedGemma 1.5 (4B only), Gemma 4 31B (Tier 2 cloud), OHIF v3.12 (contour tools + auto-statistics), TotalSegmentator v2.13 (117 structures), faster-whisper (voice dictation), PostgreSQL/Redis/WebSocket. PyTorch ≥2.6.0 required for RTX 5060 Blackwell. All tools open-source and free for research use. Cloud services incur usage costs. NOT a medical device — all AI outputs require physician review.*
