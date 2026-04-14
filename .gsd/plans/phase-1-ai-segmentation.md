# Phase 1 — AI Segmentation (starting 2026-04-11)

> **Depends on:** Phase 0 verified ✅ (`verify_phase_0.py` 4/4 green)
> **Goal:** End-to-end AI segmentation from DICOM upload to OHIF overlay,
> exercising TotalSegmentator + LiteMedSAM + nnInteractive with the GPU
> model scheduler on a real CT study.

## Plans in this phase

### Plan 1.1 — Replace LiteMedSAM mock with real implementation

**Where the mock lives:**
- `backend/app/scheduler.py:214-244` — `load_litemedsam()` returns an
  inline `MockLiteMedSAM` class whose `segment_bbox()` returns the string
  `"simulated_local_mask"`.
- `backend/app/ai/medsam2.py` — `MedSAM2Agent.segment_bbox()` calls
  `scheduler.load_litemedsam().segment_bbox(image_path, bbox)` and returns
  the mock string verbatim.

**What "real" looks like:**
- Download the official LiteMedSAM checkpoint from
  `https://github.com/bowang-lab/MedSAM/tree/LiteMedSAM` (the `lite_medsam.pth`
  weights, ~50 MB).
- Pin an inference dependency: either
  (a) install `segment-anything` and implement the slice-wise LiteMedSAM
      forward pass (image encoder + prompt encoder + mask decoder), or
  (b) use the upstream `LiteMedSAM` repo class directly via a vendored
      `litemedsam_infer.py` module.
- Load checkpoint into `torch.device("cuda")` when scheduler grants it
  the VRAM slot; support unloading via `unload_current()`.
- `segment_bbox(image_path, bbox)` must:
  - Read NIfTI volume via SimpleITK
  - Extract the target 2D slice (axial by default, or pick the slice with
    the largest bbox intersection)
  - Normalize to `[0,255]` × 3-channel per LiteMedSAM preprocessing
  - Run image encoder → prompt encoder → mask decoder with the bbox prompt
  - Threshold the 256×256 logits and resample back into the full volume
    geometry, returning a NIfTI mask path (NOT a string).
- VRAM budget: LiteMedSAM is ~50 MB. Fits comfortably under 8 GB.

**Dependencies to add to `backend/requirements.txt`:**
- `segment-anything==1.0` (from GitHub, commit-pinned) or a vendored fork
- Nothing new otherwise — torch, SimpleITK, numpy already present.

**Acceptance:**
- `scheduler.load_litemedsam()` returns a real torch module, not a class
  defined inside the method.
- `MedSAM2Agent.segment_bbox(nifti_path, [x1,y1,x2,y2])` returns
  `{"mask_path": "/tmp/radai-processing/<uuid>.nii.gz", ...}` — a real
  mask file on disk.
- Unit-level smoke: send an all-zero NIfTI + a bbox and verify the call
  returns without exception (model forward pass executes).

---

### Plan 1.2 — TotalSegmentator DICOM → SEG round-trip E2E

**Entrypoint already built:** `app/ai/totalsegmentator.py:run_totalsegmentator_job`
— drops a FastAPI BackgroundTasks job that pulls the study from Orthanc,
converts to NIfTI, runs `scheduler.run_totalsegmentator(...)`, converts
the result back to DICOM-SEG via highdicom, and POSTs it back to Orthanc.

**What has not been exercised yet:**
- Whether `scheduler.run_totalsegmentator` actually runs (the module calls
  the TotalSegmentator PyPI package, so this will load ~3 GB of PyTorch
  weights from `~/.totalsegmentator/`)
- Whether the highdicom NIfTI-SEG → DICOM-SEG path is correct for a real
  CT series (`nifti_to_dicom_seg` picks only the **first mask file**
  found, currently).
- Multi-mask merging is explicitly TODO'd in `totalsegmentator.py:114`.

**Execution:**
1. `python scripts/upload_test_dicom.py --synthetic` → a tiny synthetic
   CT lands in Orthanc, confirming the upload path.
2. For a real test, a real lung CT series (NSCLC-Radiomics or similar)
   needs to be on disk and uploaded via the same script. Add a small
   notes file listing what sample datasets are acceptable.
3. `POST /api/v1/ai/studies/{study_id}/run` with
   `{"job_type": "totalsegmentator", "fast": true, "roi_subset": ["liver"]}`.
4. Poll `/api/v1/ai/jobs/{job_id}` until status transitions
   `queued → running → completed` (or `failed` with a concrete error).
5. Verify the generated DICOM-SEG is queryable via QIDO-RS and renders
   in OHIF.

**Acceptance:**
- A synthetic study and a real study both complete `run_totalsegmentator_job`.
- Orthanc contains a new `MODALITY=SEG` series attached to the same study.
- Job progress hits 100% and the WebSocket stream emits `complete`.

---

### Plan 1.3 — OHIF extension skeleton (`@radai/extension-ai-panel`)

**Why a custom extension, not a mode:**
OHIF v3.12 extensions are the right scaffold for injecting a sidebar panel
with study-level AI actions. Modes are reserved for whole-viewer experiences.

**Minimum viable extension:**
- `frontend/extensions/extension-ai-panel/` with `package.json`,
  `src/index.ts`, `src/getPanelModule.tsx`, `src/getToolbarModule.ts`
- A single panel `RadAI AI` with:
  - "Run TotalSegmentator" button → `POST /api/v1/ai/studies/{id}/run`
  - Live progress bar driven by the existing WebSocket
    `/ws/ai/jobs/{job_id}`
  - List of completed jobs for the current study
- Wire the extension into `docker/ohif/app-config.js` via the existing
  bind-mount so no OHIF rebuild is needed.

**Acceptance:**
- Opening a study in OHIF renders the `RadAI AI` panel on the right.
- Clicking "Run TotalSegmentator" returns a job id and the progress bar
  updates in real time.
- When the job completes, the new SEG series is automatically loaded
  into the viewport as an overlay.

---

## Execution order

1.  **Plan 1.2 first (highest signal).** The code exists, needs a real
    study to find actual bugs. Any failures here block everything else.
2.  **Plan 1.1 second.** LiteMedSAM is a fallback path that only matters
    once TotalSegmentator works end-to-end; replacing the mock in isolation
    has no observable effect otherwise.
3.  **Plan 1.3 last.** The AI panel depends on Plans 1.1 + 1.2 working
    from the backend side.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| TotalSegmentator weight download fails (no internet in container) | Blocks Plan 1.2 | Pre-bake weights into Docker image or volume-mount `~/.totalsegmentator` |
| TotalSegmentator subprocess OOM on 8 GB VRAM | Job fails | Enforce `fast=True`, add `CUDA_VISIBLE_DEVICES` check in scheduler |
| highdicom `Segmentation(...)` rejects synthetic CT geometry | `nifti_to_dicom_seg` raises | Test on real data first; synthetic is optional |
| OHIF extension bind-mount not picked up on cached build | Frontend changes invisible | Use `ohif dev` in a separate container or rebuild on each iteration |
| BackgroundTasks is not Celery — no retry, no visibility | Silent failures | Migrate to Celery in Plan 1.2 follow-up once the baseline works |
