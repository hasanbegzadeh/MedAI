# AGENTS.md — RadAI Development Guidelines

## Project Overview

RadAI is a multi-modality DICOM viewer with AI-powered pathology detection, segmentation, and structured reporting. Forked from [OHIF-AI](https://github.com/CCI-Bonn/OHIF-AI), extending OHIF Viewer with automated medical image analysis.

**Phase 1 Target**: CT Chest AI Assistant (auto-detect nodules, segment anatomy, generate Lung-RADS reports).

## Architecture

- **Viewer**: OHIF v3.10+ + Cornerstone3D (React/ TypeScript) — now with built-in AI segmentation tools
- **PACS**: Orthanc (DICOMweb server, Docker)
- **Backend**: FastAPI (Python) with MONAI for AI inference + WebSocket for real-time progress
- **AI Models**: TotalSegmentator, nnInteractive, MedSAM2, MONAI Lung Nodule Detection, MedGemma 1.5 4B, MedASR
- **Database**: PostgreSQL (metadata, findings, audit trail, users)
- **Cache/Queue**: Redis (job queue, result cache, sessions)
- **Deployment**: Docker Compose with NVIDIA GPU (CUDA)
- **Key principle**: AI suggests findings → radiologist confirms → template engine generates structured reports. **Never autonomous diagnosis.**

## Tech Stack

| Layer | Tech | Version |
|-------|------|---------|
| Frontend | React + TypeScript | OHIF v3.10+ |
| Backend | Python + FastAPI | Latest |
| AI Framework | MONAI + PyTorch | Latest + 2.x |
| DICOM Processing | pydicom + SimpleITK | Latest |
| Database | PostgreSQL | 16+ |
| Cache/Queue | Redis | 7+ |
| PACS | Orthanc | Latest |
| Deployment | Docker Compose | Latest |

## Code Style

### Python (Backend)
- **Type hints**: Required on all function signatures and class attributes
- **Imports**: Standard library → third-party → local, sorted alphabetically within groups
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants
- **Error handling**: Use custom exceptions in `app/exceptions.py`. Never bare `except:`. Log errors with context.
- **Docstrings**: Google style for all public functions and classes
- **Config**: Use Pydantic settings in `app/config.py`, never hardcoded values

### TypeScript/React (Frontend)
- **Strict mode**: `strict: true` in tsconfig, no `any` types
- **Components**: Functional components with hooks, no class components
- **Naming**: `PascalCase` for components, `camelCase` for functions/variables
- **Props**: Define explicit interfaces, use `React.FC<Props>` or function signature style
- **State**: Use OHIF services and Cornerstone3D state management. Avoid local state for shared data.
- **Imports**: Absolute paths from project root, group by: external → OHIF core → RadAI extensions

## Safety Rules (CRITICAL)

1. **NEVER** generate medical findings with LLMs. LLMs only polish language of pre-validated structured data.
2. **ALWAYS** mark AI-generated content clearly in reports.
3. **NEVER** commit DICOM files, patient data, or model weights to the repository.
4. **ALWAYS** anonymize DICOM data before cloud processing.
5. **ALWAYS** include confidence scores on all AI findings.

## Project Structure

```
RadAI/
├── viewer/                    # OHIF Viewer (forked)
│   ├── extensions/
│   │   ├── radai-ai-tools/   # AI tools panel
│   │   ├── radai-reporting/  # Reporting panel
│   │   └── radai-findings/   # Findings panel
│   └── platform/
├── backend/
│   ├── app/
│   │   ├── dicom/            # DICOM processing
│   │   ├── ai/               # AI model orchestration
│   │   ├── reporting/        # Report generation
│   │   └── api/              # FastAPI routes
│   └── models/               # Model weights (gitignored)
├── orthanc/                  # Orthanc config
├── docker-compose.yml
└── docs/
```

## Development Workflow

1. Create feature branch: `feature/<description>` or `fix/<description>`
2. Implement changes following existing patterns
3. Test locally with sample DICOM data
4. Commit with conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
5. Never commit without testing AI pipeline changes

## Key References

- [RESEARCH.md](./RESEARCH.md) — Competitive analysis and model ecosystem
- [ARCHITECTURE.md](./ARCHITECTURE.md) — System architecture and data flow
- [OHIF-AI](https://github.com/CCI-Bonn/OHIF-AI) — Base repository to fork
- [OHIF Docs](https://docs.ohif.org/) — Viewer documentation
- [MONAI](https://monai.io/) — Medical AI framework documentation
