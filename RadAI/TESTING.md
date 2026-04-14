# RadAI — Testing Guide

## Quick Start

```bash
cd RadAI

# Run all unit tests
make test

# Run all verification scripts
make verify-phase0
make verify-phase3
make verify-celery
make verify-voice

# Run everything
make test-all
```

---

## 1. Unit Tests (Pytest)

### Setup

```bash
cd RadAI/backend
pip install -r requirements.txt
pip install -r requirements-test.txt
pip install aiosqlite  # For SQLite-based unit tests
```

### Run Tests

```bash
# All tests
cd RadAI/backend
pytest tests/ -v

# Specific test module
pytest tests/test_ai/test_scheduler.py -v
pytest tests/test_api/test_auth.py -v
pytest tests/test_reporting/test_engine.py -v

# With coverage
pytest tests/ --cov=app --cov-report=term-missing

# Skip slow tests
pytest tests/ -v -m "not slow"

# Run only integration tests
pytest tests/ -v -m "integration"
```

### Test Structure

```
backend/tests/
├── conftest.py                    # Shared fixtures (DB, auth, mock scheduler)
├── test_ai/
│   ├── test_scheduler.py          # GPU model scheduler, VRAM management
│   └── test_nodule_detection.py   # Lung nodule detection algorithm
├── test_api/
│   ├── test_auth.py               # JWT token creation/validation
│   └── test_endpoints.py          # API endpoint auth checks
├── test_reporting/
│   └── test_engine.py             # Jinja2 template engine, context builders
└── test_dicom/
    └── test_converter.py          # DICOM conversion, anonymization, SEG export
```

---

## 2. Verification Scripts

These scripts test the actual running system (requires Docker stack).

### Phase 0: Backend Infrastructure

```bash
cd RadAI

# Start the stack
make up

# Run health checks
make verify
# or
python scripts/verify_phase_0.py
```

**Tests:**
- ✅ Backend API reachable
- ✅ PostgreSQL connection
- ✅ Redis connection
- ✅ Orthanc PACS connection
- ✅ Ollama (MedGemma) reachable
- ✅ GPU accessible from container

### Phase 3: Cloud + RAG + Multi-Modality

```bash
cd RadAI

# Run Phase 3 verification
make verify-phase3
# or
python scripts/verify_phase_3.py
```

**Tests:**
- ✅ Cloud GPU client loads correctly
- ✅ DICOM anonymizer module functional
- ✅ RAG system retrieves clinical references
- ✅ Multi-modality registry has all modalities
- ✅ New API endpoints registered

### Celery Queue System

```bash
cd RadAI

# Run Celery verification
make verify-celery
# or
python scripts/verify_celery_e2e.py
```

**Tests:**
- ✅ Celery broker (Redis) connection
- ✅ Redis accessible
- ✅ Task submission works
- ✅ Result backend configured
- ✅ Worker responding (if running)

### Voice Dictation

```bash
cd RadAI

# Run voice verification
make verify-voice
# or
python scripts/verify_voice_dictation.py
```

**Tests:**
- ✅ Test audio generation
- ✅ faster-whisper installed
- ✅ Scheduler Whisper integration
- ✅ Voice API endpoint registered

### Real CT Study (Optional)

```bash
cd RadAI

# Download real CT from TCIA
make download-real-ct

# Run E2E verification with real data
make verify-real-ct
```

---

## 3. Manual Testing

### 3.1 API Testing (with curl)

```bash
# Health check
curl http://localhost:8000/health | jq

# Register user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"testpassword123"}' | jq

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpassword123"}' | jq

# Save token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpassword123"}' | jq -r '.access_token')

# List modalities (Phase 3.6)
curl http://localhost:8000/api/v1/ai/modalities \
  -H "Authorization: Bearer $TOKEN" | jq

# Get CT models
curl http://localhost:8000/api/v1/ai/modalities/CT/models \
  -H "Authorization: Bearer $TOKEN" | jq

# RAG retrieval (Phase 3.5)
curl -X POST http://localhost:8000/api/v1/reports/rag/retrieve \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"findings_text":"8mm solid nodule in right upper lobe","modality":"CT","body_part":"chest"}' | jq
```

### 3.2 OHIF Viewer

1. Open http://localhost:3000
2. Upload DICOM study via Orthanc (http://localhost:8042)
3. Verify three RadAI panels load:
   - **AI Tools Panel** — Run TotalSegmentator
   - **Findings Panel** — Accept/reject/modify findings
   - **Reporting Panel** — Generate reports with RAG

### 3.3 Report Generation with RAG

```bash
# After uploading DICOM and running AI analysis
curl -X POST http://localhost:8000/api/v1/reports/studies/{study_id}/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "template": "lung_rads",
    "use_ai_polish": true,
    "use_rag": true,
    "ai_tier": 1
  }' | jq
```

---

## 4. CI Pipeline

Tests run automatically on push/PR via `.github/workflows/ci.yml`:

| Job | What It Does |
|-----|-------------|
| **Lint** | Ruff checks on `app/`, `scripts/`, `tests/` |
| **Type Check** | MyPy on core modules |
| **Unit Tests** | pytest with coverage |
| **Docker Build** | Build backend image |
| **Integration** | Start PostgreSQL + Redis, verify connectivity |

### Run CI Locally

```bash
# Install act (https://nektosact.com/)
brew install act  # macOS
# or download from GitHub

# Run CI workflow locally
act push
```

---

## 5. Troubleshooting

### Tests Fail with Import Errors

```bash
cd RadAI/backend
pip install -e .  # Install in editable mode
```

### Database Connection Refused

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check connection string
echo $DATABASE_URL
```

### Ollama Unreachable

```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Pull required model
ollama pull MedAIBase/MedGemma1.5:4b-it
```

### GPU Not Detected

```bash
# Verify from host
nvidia-smi

# Verify from container
docker compose exec backend python3 -c "import torch; print(torch.cuda.is_available())"
```

---

## 6. Test Coverage Goals

| Module | Current | Target |
|--------|---------|--------|
| `scheduler.py` | 60% | 80% |
| `auth.py` | 70% | 90% |
| `reporting/engine.py` | 80% | 90% |
| `dicom/anonymizer.py` | 40% | 80% |
| `reporting/rag.py` | 30% | 80% |
| `ai/modality_registry.py` | 30% | 80% |

**Overall target: 70%+ coverage**
