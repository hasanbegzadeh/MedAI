# RadAI — AI-Powered Radiology Assistant

Multi-modality DICOM viewer with AI-powered pathology detection, segmentation, and structured reporting. Forked from [OHIF-AI](https://github.com/CCI-Bonn/OHIF-AI), extending OHIF Viewer with automated medical image analysis.

**Phase 1 Target**: CT Chest AI Assistant (auto-detect nodules, segment anatomy, generate Lung-RADS reports).

## Architecture

```
Browser (OHIF v3.10) → Orthanc PACS → FastAPI Backend → AI Models (MONAI/Ollama)
                                    ↕
                          PostgreSQL + Redis + Celery
```

- **Viewer**: OHIF v3.10+ with Cornerstone3D
- **PACS**: Orthanc (DICOMweb server)
- **Backend**: FastAPI (Python) with MONAI for AI inference
- **Database**: PostgreSQL (metadata, findings, audit trail)
- **Cache/Queue**: Redis + Celery (async jobs)
- **AI Models**: TotalSegmentator, nnInteractive, MedSAM2, MedGemma 1.5 4B
- **LLM Runtime**: Ollama (local, offline)

## Quick Start

### Prerequisites

- Docker + Docker Compose
- NVIDIA GPU (8+ GB VRAM recommended)
- Ollama installed locally

### 1. Clone and Configure

```bash
cd RadAI
cp .env.example .env
# Edit .env with your secrets
```

### 2. Start the Stack

```bash
docker compose up -d
```

### 3. Initialize Database

```bash
cd backend
alembic upgrade head
```

### 4. Pull Ollama Models

```bash
ollama pull MedAIBase/MedGemma1.5:4b-it
```

### 5. Access

- **OHIF Viewer**: http://localhost:3000
- **Orthanc**: http://localhost:8042
- **API Docs**: http://localhost:8000/docs
- **Flower (Celery)**: http://localhost:5555

## Project Structure

```
RadAI/
├── docker/              # Docker configs (Orthanc, OHIF, PostgreSQL)
├── backend/             # FastAPI backend
│   ├── app/
│   │   ├── api/        # REST endpoints (studies, ai, reports)
│   │   ├── auth.py     # JWT authentication
│   │   ├── config.py   # Pydantic settings
│   │   ├── db/         # SQLAlchemy models + session
│   │   ├── dicom/      # DICOM ↔ NIfTI conversion
│   │   ├── queue/      # Celery async tasks
│   │   ├── reporting/  # Report generation
│   │   ├── scheduler.py# GPU model scheduler
│   │   └── websocket.py# Real-time progress streaming
│   ├── alembic/        # Database migrations
│   └── requirements.txt
├── docker-compose.yml
└── .env.example
```

## Safety Rules

1. **NEVER** generate medical findings with LLMs — only polish language
2. **ALWAYS** mark AI-generated content in reports
3. **NEVER** commit DICOM files, patient data, or model weights
4. **ALWAYS** anonymize DICOM data before cloud processing
5. **ALWAYS** include confidence scores on AI findings
6. **NEVER** load two models simultaneously on 8 GB GPU

## Development

```bash
# Run backend locally
cd backend
uvicorn app.main:app --reload

# Run migrations
alembic revision --autogenerate -m "description"
alembic upgrade head

# Run Celery worker
celery -A app.queue.celery_app worker --loglevel=info
```

## License

Apache 2.0 (research use only — NOT a medical device)
