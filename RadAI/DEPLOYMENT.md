# RadAI Production Deployment Guide

## Prerequisites

- **Hardware**: NVIDIA GPU with 8+ GB VRAM (RTX 3060+ / RTX 4060+ / RTX 5060+)
- **Software**: Docker Engine 24+, Docker Compose v2, NVIDIA Container Toolkit
- **OS**: Ubuntu 22.04 LTS (recommended) or Windows 11 with WSL2
- **Domain**: A domain name with DNS pointing to the server (for HTTPS)

## Pre-deployment Checklist

- [ ] NVIDIA drivers installed (`nvidia-smi` works)
- [ ] NVIDIA Container Toolkit installed (`docker run --gpus all nvidia/cuda:12.8.0-base nvidia-smi`)
- [ ] Docker Compose v2 available (`docker compose version`)
- [ ] SSL/TLS certificate obtained (Let's Encrypt recommended)
- [ ] Secrets generated (see below)

## 1. Generate Secrets

```bash
# Generate a strong JWT secret (64 chars minimum for production)
JWT_SECRET=$(openssl rand -base64 48)

# Generate database password
POSTGRES_PASSWORD=$(openssl rand -base64 24)

# Generate Orthanc password
ORTHANC_PASSWORD=$(openssl rand -base64 24)

echo "JWT_SECRET=$JWT_SECRET"
echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
echo "ORTHANC_PASSWORD=$ORTHANC_PASSWORD"
```

## 2. Create Production Environment File

Create `.env.production` (never commit this file):

```env
# ─── Application ─────────────────────────────────────────
ENVIRONMENT=production
LOG_LEVEL=WARNING
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# ─── Security (CHANGE THESE) ────────────────────────────
JWT_SECRET=<paste-generated-secret>
JWT_ACCESS_EXPIRY_HOURS=8
JWT_REFRESH_EXPIRY_DAYS=7

# ─── Database ────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://radai:<POSTGRES_PASSWORD>@postgres:5432/radai
POSTGRES_DB=radai
POSTGRES_USER=radai
POSTGRES_PASSWORD=<paste-generated-password>

# ─── Redis ───────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# ─── Orthanc PACS ───────────────────────────────────────
ORTHANC_URL=http://orthanc:8042
ORTHANC_USER=orthanc
ORTHANC_PASSWORD=<paste-generated-password>

# ─── Ollama (Local LLM) ────────────────────────────────
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=MedAIBase/MedGemma1.5:4b-it
OLLAMA_TIMEOUT=120

# ─── Cloud APIs (optional) ──────────────────────────────
OPENROUTER_API_KEY=
CLOUD_GPU_URL=
CLOUD_GPU_API_KEY=

# ─── Voice Dictation ────────────────────────────────────
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16

# ─── Storage ────────────────────────────────────────────
TEMP_PROCESSING_DIR=/tmp/radai-processing
REPORTS_DIR=/app/reports
MODELS_DIR=/app/models
```

## 3. Configure HTTPS (Nginx)

Replace the self-signed cert in `docker/nginx/` with your real certificate:

```bash
# Using Let's Encrypt with certbot
sudo certbot certonly --standalone -d radai.yourdomain.com

# Copy certs to the nginx config directory
cp /etc/letsencrypt/live/radai.yourdomain.com/fullchain.pem docker/nginx/ssl/cert.pem
cp /etc/letsencrypt/live/radai.yourdomain.com/privkey.pem docker/nginx/ssl/key.pem
```

Update `docker/nginx/nginx.conf` to use the real certs and your domain.

## 4. Download AI Model Weights

```bash
# Pull Ollama model (run on host, not in Docker)
ollama pull MedAIBase/MedGemma1.5:4b-it

# Download TotalSegmentator weights (happens on first run, or pre-download):
docker compose run --rm backend python scripts/download_models.py
```

## 5. Deploy

```bash
# Build and start all services
docker compose --env-file .env.production up -d --build

# Verify all services are healthy
docker compose ps

# Seed the admin user
docker compose exec backend python scripts/seed_admin.py

# Run database migrations
docker compose exec backend alembic upgrade head

# Check logs
docker compose logs -f backend
```

## 6. Verify Deployment

```bash
# Health check
curl -s https://radai.yourdomain.com/api/health | jq .

# Login
curl -s -X POST https://radai.yourdomain.com/api/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}' | jq .

# OHIF viewer should be accessible at:
# https://radai.yourdomain.com/
```

## 7. Post-deployment Security

1. **Change the admin password** immediately after first login
2. **Restrict network access**: Only expose ports 80/443 via firewall
3. **Enable audit logging**: Already configured in the backend
4. **Set up log rotation**: Configure Docker log rotation in `daemon.json`
5. **Database backups**: Set up automated PostgreSQL backups

```bash
# Backup PostgreSQL
docker compose exec postgres pg_dump -U radai radai > backup_$(date +%Y%m%d).sql

# Backup Orthanc DB
docker compose exec orthanc tar -czf - /var/lib/orthanc/db > orthanc_backup_$(date +%Y%m%d).tar.gz
```

## 8. Monitoring

### Health Checks
All services have built-in Docker health checks. Monitor with:

```bash
docker compose ps  # Shows health status
docker inspect --format='{{json .State.Health}}' radai-backend-1 | jq .
```

### Log Monitoring
```bash
# All services
docker compose logs -f --tail=100

# Backend only (structured JSON logs in production)
docker compose logs -f backend

# AI operations audit trail
docker compose exec postgres psql -U radai -c "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 20;"
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| GPU not detected | Check `nvidia-smi`, reinstall NVIDIA Container Toolkit |
| Out of VRAM | Only one model loads at a time (scheduler enforces this). Restart backend if stuck. |
| Orthanc unreachable | Check `docker compose logs orthanc`, verify DICOMweb is enabled |
| Redis connection refused | Check `docker compose logs redis`, verify port 6379 is not used by host |
| Slow inference | Verify GPU is being used (`nvidia-smi` during inference). Check CUDA version matches PyTorch. |
| Database migration failed | Check `docker compose logs backend`, run `alembic upgrade head` manually |

## Architecture Overview

```
Internet ──► Nginx (443) ──┬── OHIF Viewer (3000)
                           ├── FastAPI Backend (8000) ──► PostgreSQL (5432)
                           │                          ──► Redis (6379)
                           │                          ──► Ollama (11434)
                           │                          ──► Orthanc (8042)
                           └── Orthanc DICOMweb (8042)

GPU: Backend ──► TotalSegmentator / nnInteractive / LiteMedSAM / Whisper
     (only one model loaded at a time, managed by ModelScheduler)
```
