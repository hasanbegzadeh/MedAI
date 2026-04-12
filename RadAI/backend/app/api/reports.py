"""RadAI — Reports API router."""

# NOTE: do NOT add `from __future__ import annotations` here. See app/api/ai.py
# for the full explanation — slowapi's @limiter.limit decorator swaps out the
# wrapped function's __globals__, so PEP 563 stringified annotations cannot
# resolve module-level names like `UUID` at FastAPI schema-build time.

import tempfile
from pathlib import Path
from uuid import UUID

import httpx
import pydicom
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.rate_limiter import limiter
from app.db.models import Finding, Report, Study, User
from app.db.session import get_db
from app.scheduler import get_scheduler, ModelSchedulerError
from app.ai.metadata_agent import extract_keywords
from app.reporting.engine import get_template_engine, build_lung_rads_context, build_general_context
from app.reporting.dicom_sr import create_dicom_sr_text, save_dicom_sr, DicomSRError
from app.reporting.pdf_export import generate_pdf_report, PDFReportError

router = APIRouter()


class ReportOut(BaseModel):
    id: UUID
    study_id: UUID
    report_type: str
    template_name: str | None
    content_text: str | None
    classification: str | None
    ai_polished: bool
    ai_model_used: str | None
    extracted_keywords: list[str] | None = None

    model_config = {"from_attributes": True}


class PaginatedReports(BaseModel):
    items: list[ReportOut]
    total: int


class GenerateReportRequest(BaseModel):
    template: str = "lung_rads"
    use_ai_polish: bool = True
    ai_tier: int = 1
    classification: str | None = None
    clinical_indication: str | None = None


class ExportPDFRequest(BaseModel):
    report_id: UUID
    radiologist: str | None = None


class ExportSRRequest(BaseModel):
    report_id: UUID
    author: str | None = None


def _build_findings_text(findings: list[Finding]) -> str:
    """Convert ORM findings list to structured text for LLM polishing."""
    if not findings:
        return "No significant findings identified."

    lines = []
    for i, f in enumerate(findings, 1):
        m = f.measurements or {}
        lines.append(
            f"{i}. {f.finding_type.upper()} — {f.location or 'unspecified location'}"
        )
        if m.get("longest_diameter_mm"):
            lines.append(f"   Size: {m['longest_diameter_mm']} mm")
        if m.get("volume_mm3"):
            lines.append(f"   Volume: {m['volume_mm3']:.1f} mm³")
        if m.get("mean_hu") is not None:
            lines.append(f"   Mean HU: {m['mean_hu']}")
        if f.characteristics:
            lines.append(f"   Characteristics: {', '.join(f.characteristics)}")
        if f.confidence:
            lines.append(f"   AI confidence: {f.confidence:.0%}")
        if f.radiologist_notes:
            lines.append(f"   Notes: {f.radiologist_notes}")
        lines.append("")

    return "\n".join(lines)


def _findings_to_dicts(findings: list[Finding]) -> list[dict]:
    """Convert ORM findings to dict list for template context."""
    return [
        {
            "finding_type": f.finding_type,
            "location": f.location,
            "description": f"{f.finding_type} in {f.location or 'unspecified location'}",
            "measurements": f.measurements or {},
            "characteristics": f.characteristics or [],
            "confidence": f.confidence,
            "radiologist_notes": f.radiologist_notes,
        }
        for f in findings
    ]


@router.post(
    "/studies/{study_id}/generate",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a structured radiology report for a study",
)
@limiter.limit("2/minute")
async def generate_report(
    study_id: UUID,
    request: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Report:
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    result = await db.execute(
        select(Finding)
        .where(Finding.study_id == study_id)
        .where(Finding.status.in_(["accepted", "modified"]))
    )
    findings = list(result.scalars().all())

    findings_text = _build_findings_text(findings)
    findings_dicts = _findings_to_dicts(findings)

    # 1. Render with Jinja2 template
    engine = get_template_engine()

    # Determine which template to use
    template_file = f"{request.template}.j2"
    if request.template == "lung_rads":
        context = build_lung_rads_context(
            findings=findings_dicts,
            lung_rads_category=request.classification,
            clinical_indication=request.clinical_indication or "Lung cancer screening",
        )
    else:
        context = build_general_context(
            findings=findings_dicts,
            body_part=study.body_part or "CHEST",
            clinical_indication=request.clinical_indication or "Clinical evaluation",
        )

    content_text = engine.render(template_file, context)

    # 2. Optional AI polish
    ai_model_used = None
    ai_polished = False

    if request.use_ai_polish:
        scheduler = get_scheduler()
        try:
            if request.ai_tier == 1:
                content_text = await scheduler.generate_report_local(content_text)
                ai_model_used = "MedGemma1.5:4b-it (local Ollama)"
                ai_polished = True
            elif request.ai_tier == 2:
                content_text = await scheduler.generate_report_cloud_tier2(content_text)
                settings = get_settings()
                ai_model_used = f"OpenRouter/{settings.openrouter_model}"
                ai_polished = True
        except ModelSchedulerError:
            ai_polished = False

    # 3. Extract keywords
    extracted_keywords = await extract_keywords(content_text)

    report = Report(
        study_id=study_id,
        report_type="draft",
        template_name=request.template,
        content_text=content_text,
        classification=request.classification,
        ai_polished=ai_polished,
        ai_model_used=ai_model_used,
        extracted_keywords=extracted_keywords,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


@router.get(
    "/studies/{study_id}",
    response_model=PaginatedReports,
    summary="List reports for a study",
)
async def list_reports(
    study_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PaginatedReports:
    count_result = await db.execute(
        select(func.count()).where(Report.study_id == study_id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(select(Report).where(Report.study_id == study_id))
    reports = list(result.scalars().all())

    return PaginatedReports(
        items=[ReportOut.model_validate(r) for r in reports],
        total=total,
    )


@router.post(
    "/reports/{report_id}/export-pdf",
    summary="Export a report as PDF",
)
async def export_pdf(
    report_id: UUID,
    body: ExportPDFRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FileResponse:
    """Generate and return a PDF version of the report."""
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    study = await db.get(Study, report.study_id)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = generate_pdf_report(
                report_text=report.content_text or "",
                output_path=f"{tmpdir}/report_{report_id}.pdf",
                patient_name="ANONYMOUS",
                patient_id=str(study.orthanc_id)[:20] if study else "UNKNOWN",
                study_date=str(study.created_at.date()) if study and study.created_at else None,
                radiologist=body.radiologist or "",
                classification=report.classification,
                template_name=report.template_name,
            )
            return FileResponse(
                str(pdf_path),
                media_type="application/pdf",
                filename=f"report_{report_id}.pdf",
            )
    except PDFReportError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/reports/{report_id}/export-dicom-sr",
    summary="Export a report as DICOM-SR and upload to Orthanc",
)
async def export_dicom_sr(
    report_id: UUID,
    body: ExportSRRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Generate a DICOM-SR from the report and upload to Orthanc PACS."""
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    study = await db.get(Study, report.study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    settings = get_settings()

    # Download source DICOM images for SR evidence
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{settings.orthanc_url}/studies/{study.orthanc_id}",
                auth=(settings.orthanc_user, settings.orthanc_password),
            )
            resp.raise_for_status()
            series_ids = resp.json().get("Series", [])
            if not series_ids:
                raise HTTPException(status_code=400, detail="No series found in study")

            # Download instances from first series
            series_id = series_ids[0]
            resp = await client.get(
                f"{settings.orthanc_url}/series/{series_id}/instances",
                auth=(settings.orthanc_user, settings.orthanc_password),
            )
            resp.raise_for_status()
            instances = resp.json()

            source_images = []
            for inst in instances[:5]:  # Limit to 5 for evidence
                inst_resp = await client.get(
                    f"{settings.orthanc_url}/instances/{inst['ID']}/file",
                    auth=(settings.orthanc_user, settings.orthanc_password),
                )
                inst_resp.raise_for_status()
                ds = pydicom.dcmread(pydicom.filebase.DicomBytesIO(inst_resp.content))
                source_images.append(ds)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch source images: {exc}")

    # Create DICOM-SR
    try:
        sr = create_dicom_sr_text(
            report_text=report.content_text or "",
            source_images=source_images,
            title=f"RadAI Report — {study.study_description or 'CT Study'}",
            author=body.author,
            classification=report.classification,
            template_name=report.template_name,
        )

        # Save to temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            sr_path = save_dicom_sr(sr, f"{tmpdir}/sr_{report_id}.dcm")

            # Upload to Orthanc
            async with httpx.AsyncClient(timeout=30) as client:
                with open(sr_path, "rb") as f:
                    upload_resp = await client.post(
                        f"{settings.orthanc_url}/instances",
                        content=f.read(),
                        auth=(settings.orthanc_user, settings.orthanc_password),
                    )
                    upload_resp.raise_for_status()

        # Update report with DICOM-SR UID
        report.dicom_sr_uid = sr.SOPInstanceUID
        await db.commit()

        return {
            "status": "success",
            "sop_instance_uid": sr.SOPInstanceUID,
            "series_instance_uid": sr.SeriesInstanceUID,
            "message": "DICOM-SR uploaded to Orthanc",
        }

    except DicomSRError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
