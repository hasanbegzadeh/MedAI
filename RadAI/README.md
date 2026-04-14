# RadAI — AI-Powered Radiology Assistant

Multi-modality DICOM viewer with AI-powered pathology detection, anatomical segmentation, and structured reporting. Extends OHIF Viewer with automated medical image analysis.

**Supported Modalities**: CT, MRI, X-ray, Ultrasound, Mammography  
**AI Models**: TotalSegmentator, nnInteractive, LiteMedSAM, MedGemma 1.5 4B  
**Status**: All Phases 0-3 Complete ✅

## Quick Links

- 📘 **[Startup Guide](STARTUP.md)** — How to start the application
- 🧪 **[Testing Guide](TESTING.md)** — How to test all components
- 🏗️ **[Architecture](ARCHITECTURE.md)** — System design and diagrams
- 📋 **[Master Plan](MASTER_PLAN.md)** — Complete feature roadmap

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

See **[STARTUP.md](STARTUP.md)** for the complete startup guide.

**TL;DR:**

```bash
cd RadAI
cp .env.development .env    # Use safe development defaults
make up                      # Start Docker stack
make seed-admin              # Create admin user
make verify                  # Verify all services
```

Access: https://localhost (admin / changeme)

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

See **[TESTING.md](TESTING.md)** for the complete testing guide.

```bash
# Run backend locally
cd backend
uvicorn app.main:app --reload

# Run migrations
make migrate

# Run tests
cd backend && pytest tests/ -v

# Verify Phase 0 (health checks)
make verify

# Verify Phase 3 (cloud + RAG + multi-modality)
make verify-phase3

# View all Makefile targets
make help
```

## License

Apache 2.0 (research use only — NOT a medical device)
