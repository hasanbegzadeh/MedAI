# RadAI — Development Makefile
# Common commands for working with the Docker Compose stack.
#
# Usage: make <target>
#   make help             # List all available targets
#   make up               # Start the entire stack
#   make down             # Stop the entire stack
#   make logs             # Tail logs for all services
#   make verify           # Run Phase 0 verification script
#   make smoke            # Run backend API smoke test

COMPOSE := docker compose
GH      := "/c/Program Files/GitHub CLI/gh.exe"
PY_HOST := python

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help message
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ─── Stack lifecycle ─────────────────────────────────────────────────────────

.PHONY: up
up:  ## Start the entire stack in detached mode
	$(COMPOSE) up -d

.PHONY: up-infra
up-infra:  ## Start only infrastructure (postgres, redis, orthanc)
	$(COMPOSE) up -d postgres redis orthanc

.PHONY: up-app
up-app:  ## Start only application services (backend, celery, ohif, nginx)
	$(COMPOSE) up -d backend celery-worker ohif nginx

.PHONY: down
down:  ## Stop the stack and remove containers
	$(COMPOSE) down

.PHONY: down-clean
down-clean:  ## Stop and remove containers, networks, and named volumes (DESTROYS DATA)
	$(COMPOSE) down -v

.PHONY: restart
restart: down up  ## Restart the entire stack

.PHONY: ps
ps:  ## List running containers
	$(COMPOSE) ps

.PHONY: build
build:  ## Rebuild the backend image
	$(COMPOSE) build backend

.PHONY: build-nocache
build-nocache:  ## Rebuild the backend image from scratch
	$(COMPOSE) build --no-cache backend

# ─── Logs & debugging ────────────────────────────────────────────────────────

.PHONY: logs
logs:  ## Tail logs for all services
	$(COMPOSE) logs -f --tail=100

.PHONY: logs-backend
logs-backend:  ## Tail backend logs
	$(COMPOSE) logs -f --tail=100 backend

.PHONY: logs-celery
logs-celery:  ## Tail celery worker logs
	$(COMPOSE) logs -f --tail=100 celery-worker

.PHONY: logs-orthanc
logs-orthanc:  ## Tail Orthanc logs
	$(COMPOSE) logs -f --tail=100 orthanc

.PHONY: shell
shell:  ## Open a bash shell inside the backend container
	$(COMPOSE) exec backend bash

.PHONY: db-shell
db-shell:  ## Open a psql shell inside the postgres container
	$(COMPOSE) exec postgres psql -U radai -d radai

.PHONY: redis-cli
redis-cli:  ## Open redis-cli inside the redis container
	$(COMPOSE) exec redis redis-cli

# ─── Verification ────────────────────────────────────────────────────────────

.PHONY: seed-admin
seed-admin:  ## Seed or reset the default admin user (admin / changeme)
	MSYS_NO_PATHCONV=1 $(COMPOSE) exec backend python3 /app/scripts/seed_admin.py

.PHONY: verify
verify: seed-admin  ## Run Phase 0 verification script (healthchecks + connectivity)
	$(PY_HOST) scripts/verify_phase_0.py

.PHONY: verify-phase3
verify-phase3:  ## Run Phase 3 verification (cloud + RAG + multi-modality)
	$(PY_HOST) scripts/verify_phase_3.py

.PHONY: verify-gpu
verify-gpu:  ## Verify GPU is accessible from inside backend container
	$(COMPOSE) exec backend python3 -c "import torch; print('CUDA:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only'); print('Capability:', torch.cuda.get_device_capability(0) if torch.cuda.is_available() else 'N/A')"

.PHONY: smoke
smoke:  ## Run backend API smoke test (login, health, study list)
	$(PY_HOST) scripts/smoke_test.py

.PHONY: upload-sample
upload-sample:  ## Upload a sample DICOM study to Orthanc for testing
	$(PY_HOST) scripts/upload_test_dicom.py

.PHONY: upload-real-ct
upload-real-ct:  ## Download real CT from TCIA and upload to Orthanc
	$(PY_HOST) scripts/upload_test_dicom.py --tcia

.PHONY: download-real-ct
download-real-ct:  ## Download real CT from TCIA (no upload)
	$(PY_HOST) scripts/download_tcia_ct.py

.PHONY: verify-real-ct
verify-real-ct: seed-admin  ## Run Plan 1.4: full E2E with real CT (download + TotalSeg + nodules)
	$(PY_HOST) scripts/verify_real_ct_e2e.py

.PHONY: verify-e2e
verify-e2e: seed-admin  ## Run Plan 1.2: E2E segmentation with synthetic CT
	$(PY_HOST) scripts/verify_e2e_segmentation.py

.PHONY: verify-celery
verify-celery:  ## Verify Celery queue system end-to-end
	$(PY_HOST) scripts/verify_celery_e2e.py

.PHONY: verify-voice
verify-voice:  ## Verify voice dictation pipeline
	$(PY_HOST) scripts/verify_voice_dictation.py

# ─── Model management ────────────────────────────────────────────────────────

.PHONY: download-models
download-models:  ## Download required AI model checkpoints
	$(PY_HOST) scripts/download_models.py

.PHONY: list-models
list-models:  ## List available AI model checkpoints
	$(PY_HOST) scripts/download_models.py --list

# ─── Database migrations ─────────────────────────────────────────────────────

.PHONY: migrate
migrate:  ## Run Alembic migrations inside the backend container
	$(COMPOSE) exec backend alembic upgrade head

.PHONY: migration
migration:  ## Create a new Alembic migration (usage: make migration MSG="description")
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(MSG)"

# ─── Git / PR helpers ────────────────────────────────────────────────────────

.PHONY: pr-status
pr-status:  ## Show status of the current PR
	$(GH) pr status

.PHONY: pr-view
pr-view:  ## Open the current PR in browser
	$(GH) pr view --web

# ─── Clean ───────────────────────────────────────────────────────────────────

.PHONY: clean
clean:  ## Remove Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
