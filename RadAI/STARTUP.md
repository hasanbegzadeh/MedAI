# RadAI — Startup Guide

## Prerequisites

- **Docker Desktop** installed (the launcher will start it for you)
- **NVIDIA GPU** (RTX 5060 or similar, 8+ GB VRAM)
- **NVIDIA Container Toolkit** installed on host
- **Ollama** installed locally (optional — for AI report polishing)

---

## Option 1: One-Click Launch (Recommended, Windows)

The first time only, create a desktop shortcut:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\launcher\Install-DesktopShortcut.ps1
```

From then on, **double-click the `RadAI` icon on your desktop** (or `RadAI.bat`
in the repo root). The launcher will:

1. Start Docker Desktop if it isn't already running.
2. Create `.env` from `.env.development` on first run.
3. Bring the full stack up with `docker compose up -d`.
4. Wait for the backend to report healthy (migrations + admin seeding run
   automatically inside the container).
5. Open `https://localhost` in your browser.

To stop everything: double-click **`Stop-RadAI.bat`** (or the Stop shortcut).

**Access points:**
- **OHIF Viewer**: https://localhost
- **Orthanc PACS**: https://localhost/orthanc/
- **API Docs**: https://localhost/api/docs
- **Celery Flower**: https://localhost/flower/

**Default credentials:** `admin / changeme`

> First run builds the CUDA + PyTorch backend image and can take 20–40 minutes
> depending on network speed. Subsequent launches take ~60 seconds.

---

## Option 2: Makefile (manual)

```bash
cd RadAI
cp .env.development .env   # first run only
make up                    # build + start everything
```

Migrations (`alembic upgrade head`) and the default admin user
(`admin / changeme`) are now applied automatically by the backend
container's entrypoint — no separate `make migrate` / `make seed-admin`
step is required.

If you want to reset the admin password at any time:
```bash
make seed-admin
```

### Verify Everything Works

```bash
# Run comprehensive health checks
make verify
```

Expected output:
```
✅ Backend API: OK
✅ PostgreSQL: OK
✅ Redis: OK
✅ Orthanc PACS: OK
✅ Ollama: OK (if running)
✅ GPU: OK (if available)
```

---

## Option 3: Docker Commands Directly

```bash
cd RadAI

# Start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f --tail=100

# View specific service logs
docker compose logs -f backend
docker compose logs -f celery-worker
docker compose logs -f orthanc
```

---

## Ollama Setup (For AI Report Polishing)

### Install Ollama

```bash
# Windows: Download from https://ollama.ai
# Or use WSL2:
curl -fsSL https://ollama.ai/install.sh | sh
```

### Pull Required Model

```bash
# MedGemma 1.5 4B (quantized for 8GB VRAM)
ollama pull MedAIBase/MedGemma1.5:4b-it

# Verify model is available
ollama list
```

### Configure Ollama URL

In `.env`, set:
```bash
# For WSL2 or host Ollama
OLLAMA_URL=http://host.docker.internal:11434

# For Ollama running in Docker
OLLAMA_URL=http://ollama:11434
```

---

## Accessing Services

### Web Interfaces

| Service | URL | Credentials |
|---------|-----|-------------|
| **OHIF Viewer** | https://localhost | admin / changeme |
| **Orthanc Explorer** | https://localhost/orthanc/ | orthanc / <ORTHANC_PASSWORD> |
| **API Docs** | https://localhost/api/docs | JWT token required |
| **Celery Flower** | https://localhost/flower/ | None (dev only) |

### API Endpoints

```bash
# Health check
curl https://localhost/health | jq

# Login
curl -X POST https://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}' | jq

# Save token
TOKEN=$(curl -s -X POST https://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}' | jq -r '.access_token')

# List supported modalities (Phase 3.6)
curl https://localhost/api/v1/ai/modalities \
  -H "Authorization: Bearer $TOKEN" | jq

# Get AI recommendations for a study
curl https://localhost/api/v1/ai/studies/{study-id}/recommend-ai \
  -H "Authorization: Bearer $TOKEN" | jq
```

---

## Uploading DICOM Studies

### Via Orthanc Web Interface

1. Open https://localhost/orthanc/
2. Login with `orthanc / <ORTHANC_PASSWORD>`
3. Click "Upload"
4. Select DICOM files or folder
5. Wait for import to complete

### Via API

```bash
# Upload DICOM file
curl -X POST https://localhost/api/v1/studies/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@path/to/study.dcm"

# Upload DICOM folder (ZIP)
curl -X POST https://localhost/api/v1/studies/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@path/to/study.zip"
```

### Using Test Scripts

```bash
# Upload sample DICOM
make upload-sample

# Download and upload real CT from TCIA
make upload-real-ct
```

---

## Running AI Analysis

### Via OHIF Viewer

1. Open a study in OHIF
2. Click **RadAI AI Tools** panel
3. Click "Run TotalSegmentator"
4. Watch progress bar
5. View results in **RadAI Findings** panel

### Via API

```bash
# Run TotalSegmentator (local GPU, Tier 1)
curl -X POST https://localhost/api/v1/ai/studies/{study-id}/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_type":"totalsegmentator","fast":true,"tier":1}'

# Run nodule detection
curl -X POST https://localhost/api/v1/ai/studies/{study-id}/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_type":"nodule_detection","tier":1}'

# Check job status
curl https://localhost/api/v1/ai/jobs/{job-id} \
  -H "Authorization: Bearer $TOKEN" | jq
```

### Generate Report with RAG

```bash
# RAG-enhanced report generation
curl -X POST https://localhost/api/v1/reports/studies/{study-id}/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template": "lung_rads",
    "use_ai_polish": true,
    "use_rag": true,
    "ai_tier": 1
  }' | jq

# Preview RAG references
curl -X POST https://localhost/api/v1/reports/rag/retrieve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"findings_text":"8mm solid nodule in RUL","modality":"CT","body_part":"chest"}' | jq
```

---

## Common Operations

### View Logs

```bash
# All services
make logs

# Backend only
make logs-backend

# Celery worker
make logs-celery

# Orthanc
make logs-orthanc
```

### Restart Services

```bash
# Restart everything
make restart

# Restart only backend (after code changes)
docker compose restart backend

# Rebuild and restart
make build
make restart
```

### Stop Everything

```bash
# Stop containers (keep data)
make down

# Stop and delete all data
make down-clean  # WARNING: Destroys all studies and findings!
```

### Database Operations

```bash
# Open psql shell
make db-shell

# Run migrations
make migrate

# Create new migration
make migration MSG="add_new_column"
```

### GPU Verification

```bash
# Check GPU is accessible
make verify-gpu

# Expected output:
# CUDA: True
# Device: NVIDIA GeForce RTX 5060
# Capability: (12, 0)
```

---

## Troubleshooting

### Services Won't Start

```bash
# Check Docker is running
docker ps

# Check GPU passthrough
nvidia-smi

# Rebuild from scratch
make down-clean
make build-nocache
make up
```

### Database Connection Errors

```bash
# Check PostgreSQL is healthy
docker compose ps postgres

# Reset database
make down-clean
make up
make migrate
make seed-admin
```

### Ollama Not Reachable

```bash
# Test Ollama directly
curl http://localhost:11434/api/tags

# Check Ollama is running
ollama list

# If using WSL2, use host.docker.internal
# In .env: OLLAMA_URL=http://host.docker.internal:11434
```

### Port Conflicts

```bash
# Check what's using port 443
netstat -ano | findstr :443

# Stop conflicting services (e.g., IIS)
# Or change ports in docker-compose.yml
```

### Permission Errors (Windows)

```bash
# Run Docker Desktop as Administrator
# Or fix volume mount permissions:
docker compose down
docker compose up -d
```

---

## Next Steps

After successful startup:

1. **Upload a test DICOM study** → `make upload-sample`
2. **Run AI segmentation** → OHIF panel or API
3. **Review findings** → RadAI Findings panel
4. **Generate a report** → RadAI Reporting panel
5. **Export results** → PDF or DICOM-SR

See [TESTING.md](TESTING.md) for verification procedures.
