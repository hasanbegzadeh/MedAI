# RadAI — Research & Competitive Analysis

## 1. Key Discovery: OHIF-AI (The Blueprint We Should Build On)

**Repository**: [CCI-Bonn/OHIF-AI](https://github.com/CCI-Bonn/OHIF-AI)  
**Stars**: 44 | **Forks**: 14 | **License**: Apache 2.0

This is the **single most important reference project** for RadAI. It's an OHIF viewer fork with integrated AI segmentation and report generation. It proves the exact architecture we want.

**⚠️ Important update (April 2026)**: OHIF-AI stars have dropped from 56 to 44, suggesting stagnation. **DO NOT FORK OHIF-AI.** OHIF v3.12 (Feb 2026) now includes native contour tools (freehand, spline, livewire), auto-statistics, and SAM-based segmentation. Build RadAI as **native OHIF v3.12 extensions** instead.

### What OHIF-AI Already Has:
- **OHIF Viewer** as the base (production-grade DICOM web viewer)
- **Interactive AI Segmentation** with visual prompts (points, scribbles, lasso, bounding boxes)
- **Models integrated**: nnInteractive, SAM2, MedSAM2, SAM3, VoxTell (text-prompt segmentation)
- **Report Generation**: MedGemma 1.5 4B for radiology-style reports from 3D CT/MRI
- **MONAI Label** backend for AI inference
- **Docker Compose** deployment with NVIDIA GPU support
- **Live mode**: Auto-segmentation on every prompt
- **3D propagation**: Single prompt segments entire volume

### What OHIF-AI is Missing (Our Opportunity):
1. **No automated pathology detection** — Only interactive (human prompts). No "find it for me" AI.
2. **No TotalSegmentator** integration — No automatic anatomical structure segmentation.
3. **No lung nodule detection** — No automated finding detection.
4. **No structured report templates** — MedGemma generates free-text, not structured reports.
5. **No multi-modality support** — Focused on CT/MRI, no mammography or ultrasound pipeline.
6. **No comparison with prior studies** — Critical for radiology workflows.
7. **No measurement tools** — No diameter, volume, or HU statistics.
8. **No DICOM-SR/SEG output** — Results not saved as DICOM objects.
9. **No PACS integration** — Only local file loading.
10. **No findings panel** — No UI for radiologist to accept/reject/modify AI findings.

### Critical Lesson from OHIF-AI:
> **MedGemma 1.5 is only available as a 4B variant** (released Jan 2026). The 27B version was dropped. The 4B model supports 3D scans natively (multimodal) and runs at ~8-12 GB VRAM in FP16, or ~3 GB with Q4 quantization via Ollama. This fits the RTX 5060 (8 GB).

### New Discovery: OHIF v3.12 Built-in AI + Contour Tools (Feb 2026)

> OHIF Viewer v3.12 includes:
> - **Freehand, spline, and livewire contour tools** — eliminates need for custom segmentation UI
> - **Sculpt contour tool** with dynamic brush — matches nnInteractive's interactive refinement UX
> - **Combine/intersect/subtract contour operations** — advanced region editing
> - **Programmatic contour API** — backend can manipulate segments
> - **Auto-statistics** (volume, intensity, centroid, SUVpeak) — eliminates custom measurement code
> - **SAM-based browser segmentation** — built-in from v3.10
>
> **Decision: Use OHIF v3.12 directly. Do NOT fork OHIF-AI.** Build RadAI as OHIF extensions.

---

## 2. Other Similar Projects

### 2.1 Med Image Scanner
**Repository**: [suxrobGM/med-image-scanner](https://github.com/suxrobGM/med-image-scanner)  
AI-powered web platform for viewing and analyzing X-rays, CT scans, and MRIs. Provides viewing, annotation, and deep learning analysis tools.

### 2.2 OHIF/Viewers (Official)
**Repository**: [OHIF/Viewers](https://github.com/OHIF/Viewers)  
**Stars**: 4,103 | **Forks**: 4,190

The official OHIF Viewer. 4,100+ stars. Production-grade, used by hospitals worldwide. Extension-based architecture. Supports:
- DICOMweb (QIDO-RS, WADO-RS, STOW-RS)
- Cornerstone3D rendering engine
- MPR (Multi-Planar Reconstruction)
- Volume rendering
- Annotations and measurements
- Segmentation display (DICOM-SR, DICOM-SEG)
- Extension system for adding AI modules

### 2.3 Niffler
DICOM framework for ML and processing pipelines. More of a data pipeline tool than a viewer.

### 2.4 DWV (DICOM Web Viewer)
Pure JavaScript DICOM viewer. Lightweight but lacks AI integration capabilities.

---

## 3. AI Models Ecosystem — What's Actually Available & Free

### 3.1 Segmentation Models (Production-Ready, Free)

| Model | Modality | What It Does | Source | VRAM |
|-------|----------|-------------|--------|------|
| **TotalSegmentator** | CT | 117 anatomical structures (v2.13) | [GitHub](https://github.com/wasserth/TotalSegmentator) | 2-3 GB (fast) / 12+ GB (full) |
| **nnInteractive** | CT/MRI | Interactive 3D segmentation (points, scribbles, lasso, bbox) | [GitHub](https://github.com/MIC-DKFZ/nnInteractive) | 6-10 GB |
| **MedSAM2** | CT/MRI/US | 3D medical SAM — promptable segmentation | [GitHub](https://github.com/bowang-lab/MedSAM2) | 6-10 GB |
| **SAM2** (Meta) | General | 2D/Video segmentation, works on medical | [GitHub](https://github.com/facebookresearch/sam2) | 4-8 GB |
| **SAM3** (Meta) | General | Concept-based segmentation | [GitHub](https://github.com/facebookresearch/sam3) | 8-12 GB |
| **VoxTell** | CT/MRI | Text-prompt 3D segmentation | [GitHub](https://github.com/MIC-DKFZ/VoxTell) | 6-10 GB |
| **LungMask** | CT | Lung lobe segmentation | [GitHub](https://github.com/JoHof/lungmask) | 2-4 GB |
| **BraTS Models** | MRI Brain | Brain tumor segmentation | MONAI Zoo | 4-8 GB |
| **nnU-Net** | Any | Self-configuring segmentation (wins challenges) | [GitHub](https://github.com/MIC-DKFZ/nnUNet) | 4-10 GB |

### 3.2 Detection/Classification Models

| Model | Modality | What It Does | Source |
|-------|----------|-------------|--------|
| **MONAI Lung Nodule Detection** | CT Chest | Detects pulmonary nodules | [NVIDIA NGC](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/monaitoolkit/models/monai_lung_nodule_ct_detection) |
| **CheXnet/CheXpert** | Chest X-Ray | 14 pathology classifications | Stanford |
| **LUNA16 Models** | CT Chest | Lung nodule detection challenge winners | MONAI Zoo |
| **MOOSE** | CT | Multi-Organ segmentation | [GitHub](https://github.com/MIC-DKFZ/MOOSE) |

### 3.3 Report Generation Models

| Model | What It Does | VRAM | Notes |
|-------|-------------|------|-------|
| **MedGemma 1.5 4B** | Radiology reports from 3D CT/MRI + clinical text | ~3 GB (Q4) / ~10 GB (FP16) | Google, Jan 2026, ONLY 4B variant exists. Multimodal (3D + text). |
| **Gemma 4 31B** | Premium report polishing (Tier 2, cloud only) | N/A (cloud) | Google, Apr 2026. Via OpenRouter. Text-only, general-purpose. |
| **faster-whisper** | Medical speech-to-text (voice dictation) | ~3 GB (large-v3) | Local Python library, NOT via Ollama. Replaces MedASR. |
| **LLaVA-Med** | Medical VLM for image QA | ~16 GB | Microsoft, less specialized |

> **⚠️ MedASR cannot run via Ollama.** MedASR requires audio input but Ollama only accepts text prompts. Use `faster-whisper` for local voice dictation instead.

**⚠️ MedGemma 27B no longer exists.** Google dropped the 27B variant in the 1.5 release. The 4B model is the only option, and it is sufficient for report polishing with Q4 quantization.

### 3.4 Model Maturity by Anatomical System

| System | Modality | Best Free Models | Maturity |
|--------|----------|-----------------|----------|
| **Chest/Lung** | CT | TotalSegmentator + MONAI Nodule Detection + LungMask | ★★★★★ |
| **Abdomen** | CT | TotalSegmentator (117 structures) + nnU-Net | ★★★★★ |
| **Brain** | MRI | BraTS tumor segmentation + FreeSurfer | ★★★★☆ |
| **Chest** | X-Ray | CheXnet, CheXpert models | ★★★★☆ |
| **Cardiac** | CT/MRI | TotalSegmentator (heart structures) | ★★★☆☆ |
| **Musculoskeletal** | CT/MRI | TotalSegmentator (bones, muscles) | ★★★☆☆ |
| **Breast** | Mammography | CBIS-DDSM models (limited, research-stage) | ★★☆☆☆ |
| **General** | Ultrasound | MedSAM2 (general-purpose, not US-specific) | ★★☆☆☆ |

---

## 4. Architecture Patterns from Research

### 4.1 OHIF-AI Architecture (Proven)
```
Browser (OHIF Viewer + Cornerstone3D)
    ↕ DICOMweb (HTTP)
Orthanc/DICOMweb Server
    ↕
MONAI Label Server (Python/FastAPI)
    ↕
AI Models (nnInteractive, SAM2, MedSAM2, VoxTell, MedGemma)
    ↕
NVIDIA GPU (CUDA)
```

### 4.2 What We Need to Add
```
Browser (OHIF + Custom RadAI Extensions)
    ↕
Orthanc PACS (DICOMweb)
    ↕
RadAI Backend (FastAPI)
    ├── MONAI Label → Interactive Segmentation (SAM2, MedSAM2, nnInteractive)
    ├── TotalSegmentator → Automatic Anatomy Segmentation
    ├── MONAI Zoo → Automated Pathology Detection (nodules, lesions)
    ├── MedGemma → Report Generation
    └── Template Engine → Structured Reports (DICOM-SR)
    ↕
NVIDIA GPU (CUDA)
```

---

## 5. Key Technical Decisions

### 5.1 Fork vs. Extend OHIF
**Decision: Extend OHIF v3.12 directly. Do NOT fork OHIF-AI.**

OHIF v3.12 (Feb 2026) now includes:
- Freehand, spline, livewire contour tools
- Sculpt contour tool with dynamic brush
- Combine/intersect/subtract contour operations
- Programmatic contour API
- Auto-statistics (volume, intensity, centroid, SUVpeak)
- SAM-based browser segmentation (from v3.10)
- AI-driven propagation across slices (from v3.10)

OHIF-AI (CCI-Bonn fork) is **stale** (44 stars, declining activity).

**Approach**:
1. Use OHIF v3.12 Docker image directly (`ohif/app:v3.12.0`)
2. Build RadAI as native OHIF extensions (extension system is production-grade)
3. Connect to FastAPI backend via REST + WebSocket
4. This saves 2-3 months vs. forking and maintaining a stale codebase

### 5.2 PACS Server
**Decision: Orthanc** (lightweight, free, DICOMweb-native)
- Docker deployment
- DICOMweb support (QIDO-RS, WADO-RS, STOW-RS)
- REST API
- Plugin system
- Can be replaced with dcm4chee later for enterprise scale

### 5.3 Report Generation Strategy
**Decision: Structured findings → Template engine → Polished report**

1. AI models detect findings → structured JSON
2. Radiologist reviews/edits findings in UI
3. Template engine fills radiology report templates (Lung-RADS, BI-RADS, etc.)
4. MedGemma optionally polishes language (NOT generates findings)

This prevents hallucination while maintaining quality.

### 5.4 GPU Requirements
| Component | Min VRAM | Recommended | Notes |
|-----------|----------|-------------|-------|
| TotalSegmentator --fast --body_seg | 2 GB | 8 GB | Recommended for 8 GB GPUs |
| TotalSegmentator --fast | 2-3 GB | 8 GB | Low-res 3mm |
| TotalSegmentator full | 12+ GB | 16 GB | **Cloud-only** on 8 GB GPU |
| nnInteractive/SAM2 | 6 GB | 10 GB | Tight fit on 8 GB |
| MedSAM2 | 6 GB | 10 GB | May OOM on large volumes |
| MONAI Detection | 4 GB | 8 GB | Fits locally |
| MedGemma 1.5 4B (Q4) | 3 GB | 8 GB | Fits RTX 5060 |
| MedGemma 1.5 4B (FP16) | 8-10 GB | 12 GB | Tight, Q4 recommended |
| faster-whisper large-v3 | 3 GB | 8 GB | Voice dictation |

**Practical approach**: MedGemma 1.5 4B with Q4 quantization runs on 8 GB VRAM (RTX 5060). Run segmentation models sequentially using the model scheduler (one model at a time). TotalSegmentator full-res requires 12+ GB and must be offloaded to cloud (Tier 3). Use `--fast --body_seg` for local inference.

**⚠️ PyTorch version**: RTX 5060 uses Blackwell architecture (sm_120). Requires `torch>=2.6.0`. Standard PyTorch 2.4.x will produce "no kernel image available" errors.

---

## 6. Recommended Starting Point

**Phase 1 Target: CT Chest AI Assistant**

Why CT Chest first:
1. Most mature free models (TotalSegmentator, nodule detection, lung segmentation)
2. Highest clinical volume (most common CT study)
3. Clear reporting standards (Lung-RADS, Fleischner Society guidelines)
4. OHIF-AI already has the viewer foundation

Models to integrate first:
1. **TotalSegmentator** → Auto-segment lungs, heart, vessels, bones
2. **MONAI Lung Nodule Detection** → Auto-detect pulmonary nodules
3. **nnInteractive** → Interactive refinement of any finding
4. **Template engine** → Structured Lung-RADS report

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| MedGemma hallucination | High | Never use for findings. Only for language. Structured templates instead. |
| GPU memory limits | Medium | Run models sequentially. Use smaller variants. Cloud GPU for MedGemma. |
| DICOM compatibility | Medium | Use OHIF + Cornerstone3D (proven). Orthanc for PACS. |
| Model accuracy | High | Human-in-the-loop. AI suggests, radiologist confirms. Never autonomous. |
| Regulatory (SaMD) | Medium | For personal/research use only. No distribution without FDA/CE clearance. |
| Ultrasound/Mammo AI | High | Very limited free models. Defer to Phase 3+. |

---

## 8. References

1. OHIF-AI: https://github.com/CCI-Bonn/OHIF-AI
2. OHIF Viewer: https://github.com/OHIF/Viewers
3. OHIF Docs: https://docs.ohif.org/
4. MONAI: https://monai.io/
5. MONAI Model Zoo: https://github.com/Project-MONAI/model-zoo
6. TotalSegmentator: https://github.com/wasserth/TotalSegmentator
7. nnInteractive: https://github.com/MIC-DKFZ/nnInteractive
8. MedSAM2: https://github.com/bowang-lab/MedSAM2
9. VoxTell: https://github.com/MIC-DKFZ/VoxTell
10. MedGemma: https://github.com/Google-Health/medgemma
11. MONAI Lung Nodule Detection: https://catalog.ngc.nvidia.com/orgs/nvidia/teams/monaitoolkit/models/monai_lung_nodule_ct_detection
12. Orthanc: https://www.orthanc-server.com/
13. Cornerstone3D: https://github.com/cornerstonejs/cornerstone3D
14. Lung lobe segmentation comparison: https://pmc.ncbi.nlm.nih.gov/articles/PMC12411369/
