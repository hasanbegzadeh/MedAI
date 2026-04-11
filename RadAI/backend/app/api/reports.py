"""RadAI — Reports API router."""

# NOTE: do NOT add `from __future__ import annotations` here. See app/api/ai.py
# for the full explanation — slowapi's @limiter.limit decorator swaps out the
# wrapped function's __globals__, so PEP 563 stringified annotations cannot
# resolve module-level names like `UUID` at FastAPI schema-build time.

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
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
    template: str = "general_ct"
    use_ai_polish: bool = True
    ai_tier: int = 1
    classification: str | None = None


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
    scheduler = get_scheduler()

    content_text = findings_text
    ai_model_used = None
    ai_polished = False

    if request.use_ai_polish:
        try:
            if request.ai_tier == 1:
                content_text = await scheduler.generate_report_local(findings_text)
                ai_model_used = "MedGemma1.5:4b-it (local Ollama)"
                ai_polished = True
            elif request.ai_tier == 2:
                content_text = await scheduler.generate_report_cloud_tier2(
                    findings_text
                )
                settings = get_settings()
                ai_model_used = f"OpenRouter/{settings.openrouter_model}"
                ai_polished = True
        except ModelSchedulerError:
            content_text = findings_text
            ai_polished = False

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
