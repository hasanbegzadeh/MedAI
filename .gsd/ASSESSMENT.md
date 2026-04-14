# RadAI Project Assessment & Improvement Recommendations

**Date:** 2026-04-11  
**Status:** Phase 0 — Backend infrastructure largely complete, Phase 1 pending  
**Overall Health:** GOOD — Strong technical foundation, missing GSD workflow artifacts

---

## Executive Summary

RadAI is a well-architected AI-powered radiology assistant with a clear multi-phase plan. The Phase 0 backend is substantially complete with a functional Docker stack, FastAPI backend, GPU model scheduler, and comprehensive API layer. However, the project is **not following the GSD methodology** it claims to use — critical GSD artifacts (SPEC.md, ROADMAP.md, STATE.md) are missing from `.gsd/`, and work has proceeded without the SPEC→PLAN→EXECUTE→VERIFY→COMMIT protocol.

---

## Current Progress Assessment

### ✅ Completed (Phase 0 — ~85% done)

| Component | Status | Quality |
|-----------|--------|---------|
| Docker Compose stack | ✅ Complete | Good — all services defined |
| PostgreSQL schema | ✅ Complete | Good — 6 tables, Alembic migration |
| FastAPI entry point | ✅ Complete | Good — CORS, audit middleware, health check |
| JWT authentication | ✅ Complete | Solid |
| API routers (auth, studies, ai, reports, voice) | ✅ Complete | Functional |
| GPU Model Scheduler | ✅ Complete | Well-implemented, thread-safe |
| TotalSegmentator integration | ✅ Complete | Subprocess-based, timeout handling |
| nnInteractive integration | ✅ Complete | Python import, VRAM tracking |
| Ollama (MedGemma) integration | ✅ Complete | Async, non-blocking |
| OpenRouter (Gemma 4 31B) | ✅ Complete | Retry logic, rate limiting |
| WebSocket progress streaming | ✅ Complete | 120s heartbeat |
| Rate limiting | ✅ Complete | slowapi |
| Health check endpoint | ✅ Complete | Tests DB, Redis, Ollama |
| Nginx reverse proxy | ✅ Complete | HTTPS, rate limiting, WebSocket |
| OHIF configuration | ✅ Complete | DICOMweb via Nginx |
| CUDA 12.8 Blackwell support | ✅ Complete | RTX 5060 sm_120 |
| Development tooling | ✅ Complete | Makefile, smoke tests, DICOM uploader |

### ⚠️ Partially Complete

| Component | Status | Gap |
|-----------|--------|-----|
| LiteMedSAM | ⚠️ MOCK only | Uses `MockLiteMedSAM`, not real implementation |
| DICOM processing | ⚠️ Structure only | converter.py, anonymizer.py, seg_export.py exist but implementation depth unknown |
| Celery queue system | ⚠️ Structure only | celery_app.py and tasks.py exist but not tested |
| Voice dictation | ⚠️ Structure only | API endpoint exists, faster-whisper module exists but not verified |
| Report generation | ⚠️ Structure only | Ollama client exists, no template engine yet |

### ❌ Not Started

| Component | Priority | Phase |
|-----------|----------|-------|
| Custom OHIF extensions (RadAI panels) | HIGH | Phase 1 |
| Nodule detection model | HIGH | Phase 1 |
| Report template engine (Jinja2) | HIGH | Phase 2 |
| Findings panel UI (accept/reject/modify) | HIGH | Phase 2 |
| DICOM-SR generation | HIGH | Phase 2 |
| RAG pipeline | MEDIUM | Phase 2 |
| PDF export | MEDIUM | Phase 2 |
| Cloud GPU server | MEDIUM | Phase 3 |
| Anonymization pipeline | MEDIUM | Phase 3 |
| Multi-modality expansion | LOW | Phase 4 |

---

## GSD Compliance Assessment

### ❌ Critical GSD Gaps

| GSD Requirement | Status | Impact |
|-----------------|--------|--------|
| **SPEC.md** (requirements, FINALIZED) | ❌ Missing | No formal spec — work proceeds ad-hoc |
| **ROADMAP.md** (phases, progress) | ❌ Missing | MASTER_PLAN.md serves this role but isn't GSD-format |
| **STATE.md** (session memory) | ❌ Missing | No persistent state between sessions |
| **SPEC→PLAN→EXECUTE→VERIFY→COMMIT** | ❌ Not followed | Commits exist but no verification evidence captured |
| **Empirical proof for changes** | ❌ Missing | No screenshots, test outputs, or curl responses captured |
| **Wave execution protocol** | ❌ Not followed | No wave summaries or state snapshots |
| **One task = one commit** | ⚠️ Partial | Commits are reasonable but not verified before commit |
| **Planning lock** (no code until SPEC FINALIZED) | ❌ Violated | Code written before any SPEC existed |

### ⚠️ GSD Style Issues

| Issue | Severity | Description |
|-------|----------|-------------|
| Duplicate function in scheduler.py | MEDIUM | `_is_retryable_openrouter_error` defined twice (lines 26-31 and 42-47) |
| Temporal language in docs | LOW | MASTER_PLAN uses "First, we'll..." patterns |
| No verification commands in tasks | MEDIUM | MASTER_PLAN checkboxes lack `<verify>` tags |
| No effort attributes | LOW | Tasks don't use `effort="low/medium/high"` hints |

---

## Technical Strengths

1. **GPU Model Scheduler** — Excellent thread-safe singleton with proper `threading.Lock()`, VRAM tracking, and `torch.cuda.empty_cache()`. This is the core architectural innovation.

2. **3-Tier Execution Strategy** — Clear separation of local (free/offline), cloud API (pay-per-use), and cloud GPU (batch) is well-designed for the 8 GB VRAM constraint.

3. **Safety-First AI Design** — "AI suggests, radiologist confirms" principle is correctly enforced. LLMs never generate findings, only polish language.

4. **Comprehensive Health Check** — Tests all dependencies (DB, Redis, Ollama) with graceful degradation reporting.

5. **Audit Middleware** — All AI/report operations logged for medical compliance. Good practice for clinical deployment.

6. **CUDA 12.8 Blackwell Support** — Correctly identified RTX 5060 sm_120 requirement and configured PyTorch accordingly.

7. **Retry Logic** — OpenRouter integration has proper exponential backoff with 5 attempts. Production-ready.

---

## Improvement Recommendations

### 🔴 Critical (Do First)

#### 1. Establish GSD Workflow Artifacts

**Why:** The project claims GSD methodology but doesn't use it. This causes scope creep and unverified work.

**Action:**
```
.gsd/
├── SPEC.md          ← Define Phase 0-2 requirements with "Status: FINALIZED"
├── ROADMAP.md       ← Convert MASTER_PLAN phases to GSD roadmap format
├── STATE.md         ← Current session state, progress, known issues
├── templates/       ← Already exists, good
└── examples/        ← Already exists, good
```

Create SPEC.md with explicit requirements for the next phase (Phase 1), then follow SPEC→PLAN→EXECUTE→VERIFY→COMMIT.

#### 2. Fix Duplicate Function in scheduler.py

**Why:** `_is_retryable_openrouter_error` is defined twice. Python uses the second definition silently — this is a maintenance hazard.

**Action:** Remove the first definition (lines 26-31), keep the second (lines 42-47) which is identical.

#### 3. Implement LiteMedSAM (Remove Mock)

**Why:** Mock segmentation defeats the purpose of having a fallback model. The architecture is ready for real implementation.

**Action:**
- Install `segment_anything` or `lightweight-medical-image-segmentation`
- Replace `MockLiteMedSAM` with real inference session
- Add verification: run on test image, confirm mask output

#### 4. Add Verification Evidence

**Why:** PROJECT_RULES.md requires empirical proof. "It looks correct" is not acceptable.

**Action:** For each completed component, capture:
- API endpoints: `curl` output showing 200 responses
- Health check: `/health` endpoint output
- Model scheduler: Test script showing load→run→unload cycle
- Docker stack: `docker compose ps` showing all services healthy

---

### 🟡 Important (Next Wave)

#### 5. Complete DICOM Processing Pipeline

**Priority:** HIGH — Required before Phase 1

**Components to verify/complete:**
- `dicom/converter.py` — Test DICOM → NIfTI → DICOM round-trip
- `dicom/anonymizer.py` — Test on sample DICOM, verify patient data removed
- `dicom/seg_export.py` — Test SEG creation from segmentation mask

**Verification:** Run `scripts/upload_test_dicom.py` and confirm successful processing.

#### 6. Implement Report Template Engine

**Priority:** HIGH — Required for Phase 2

**Action:**
- Create `backend/app/reporting/templates/lung_rads.j2`
- Create `backend/app/reporting/templates/general_ct.j2`
- Implement `backend/app/reporting/engine.py` with Jinja2 rendering
- Add API endpoint: `POST /api/v1/reports/{study_id}/generate`

**Verification:** Generate report from sample findings, confirm valid output.

#### 7. Build Custom OHIF Extensions

**Priority:** HIGH — Required for Phase 1 UI

**Action:**
- Create `viewer/extensions/radai-ai-tools/` — AI tools panel
- Create `viewer/extensions/radai-findings/` — Findings review panel
- Create `viewer/extensions/radai-reporting/` — Report generation panel
- Create `viewer/extensions/radai-voice/` — Voice dictation panel

**Approach:** Start with minimal extension (one panel button → API call → display result), then iterate.

**Verification:** OHIF loads with RadAI panel visible, clicking triggers backend API.

#### 8. Add Nodule Detection Model

**Priority:** HIGH — Core Phase 1 feature

**Options:**
- **Option A:** Use MONAI pretrained lung nodule model (recommended for Phase 1)
- **Option B:** Train custom model on LIDC-IDRI dataset (Phase 4+)
- **Option C:** Integrate with TotalSegmentator lung ROI + heuristic detection (quick win)

**Recommendation:** Start with Option C (heuristic-based detection from TotalSegmentator lung segmentation) for Phase 1, then Option A for Phase 2.

---

### 🟢 Nice-to-Have (Future Waves)

#### 9. Token Budget Tracking

**Why:** PROJECT_RULES.md specifies context quality thresholds but no mechanism exists to track them.

**Action:** Add optional token usage logging to workflows. Not critical but helps with context management.

#### 10. State Dump Automation

**Why:** After 3 debugging failures, state dump is required. Currently manual.

**Action:** Create `/state-dump` workflow that:
- Summarizes current progress
- Updates STATE.md
- Lists open tasks
- Clears context for fresh session

#### 11. CI/CD Pipeline

**Why:** No automated testing on commit.

**Action:** Add GitHub Actions workflow:
- Run smoke tests on PR
- Verify Docker build
- Run linting (ruff, mypy)

---

## Code Quality Issues

### scheduler.py

| Issue | Line | Severity | Action |
|-------|------|----------|--------|
| Duplicate `_is_retryable_openrouter_error` | 26-31, 42-47 | MEDIUM | Remove first definition |
| Mixed async/sync in same file | Throughout | LOW | Acceptable for scheduler pattern |
| No type hints on `run_totalsegmentator` progress_callback | 128 | LOW | Add `Optional[Callable[[int], None]]` |

### main.py

| Issue | Line | Severity | Action |
|-------|------|----------|--------|
| Redis import inside try block | 108 | LOW | Move to top-level import |
| Inline imports in health check | 92-120 | LOW | Acceptable for health check (lazy loading) |

### requirements.txt

| Issue | Severity | Action |
|-------|----------|--------|
| `nnInteractive>=0.1.0` — not on PyPI | MEDIUM | Verify installation source (GitHub?) |
| `faster-whisper>=1.1.0` — C++ dependencies | LOW | Document in setup.md |
| No dev dependencies | LOW | Add pytest, ruff, mypy to `[dev]` section |

---

## Architecture Assessment

### Strengths

| Aspect | Rating | Notes |
|--------|--------|-------|
| Scalability | GOOD | Decoupled microservices, can scale independently |
| Maintainability | GOOD | Clear separation of concerns, structured logging |
| Security | GOOD | JWT auth, audit logging, anonymization planned |
| Performance | GOOD | GPU scheduling, async operations, caching via Redis |
| Clinical Safety | EXCELLENT | Human-in-the-loop, audit trail, no autonomous diagnosis |

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| 8 GB VRAM insufficient for production | HIGH | Cloud GPU fallback already designed |
| OHIF v3.12 extension API changes | MEDIUM | Lock OHIF version, test upgrades separately |
| Model availability (nnInteractive not on PyPI) | MEDIUM | Pin to specific commit, build from source |
| Single GPU bottleneck | MEDIUM | Cloud queue handles overflow |
| No backup/recovery plan | LOW | Add PostgreSQL backups to Phase 3 |

---

## Recommended Next Steps (Prioritized)

### Wave 1: GSD Foundation (No code changes)

1. Create `.gsd/SPEC.md` for Phase 1 requirements → Status: FINALIZED
2. Create `.gsd/ROADMAP.md` with Phase 1-2 breakdown
3. Create `.gsd/STATE.md` with current progress summary
4. Capture verification evidence for all Phase 0 work

### Wave 2: Phase 1 Foundation (After Wave 1 verification)

1. Fix duplicate function in `scheduler.py`
2. Implement real LiteMedSAM (remove mock)
3. Verify DICOM converter pipeline
4. Test nodule detection heuristic (Option C)

### Wave 3: Phase 1 UI

1. Build minimal OHIF extension (single panel button)
2. Connect to backend AI API
3. Display segmentation overlays
4. Test end-to-end CT study analysis

---

## Summary

**What's working well:**
- Phase 0 backend is 85% complete with solid architecture
- GPU model scheduler is production-ready
- 3-tier execution strategy is well-designed
- Safety-first AI approach is correct

**What needs immediate attention:**
- Establish GSD workflow artifacts (SPEC, ROADMAP, STATE)
- Fix duplicate function in scheduler.py
- Replace LiteMedSAM mock with real implementation
- Capture verification evidence for completed work

**Biggest risk:**
- Proceeding without SPEC.md means scope is undefined. Define Phase 1 requirements formally before writing code.

**Overall verdict:** Strong technical foundation. Fix process gaps, then execute Phase 1 with GSD discipline.
