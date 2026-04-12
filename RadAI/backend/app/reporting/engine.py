"""RadAI — Report Template Engine (Jinja2).

Renders structured radiology reports from Jinja2 templates.
Supports Lung-RADS, BI-RADS (future), and general CT/MRI templates.

Usage::

    engine = ReportTemplateEngine()
    report = engine.render("lung_rads", context={...})
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = structlog.get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


class TemplateError(Exception):
    """Raised when template rendering fails."""


class ReportTemplateEngine:
    """Jinja2-based radiology report template engine."""

    def __init__(self, template_dir: str | Path | None = None):
        self._template_dir = Path(template_dir) if template_dir else TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self._template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Register custom filters
        self._env.filters["format_hu"] = self._format_hu
        self._env.filters["format_mm"] = self._format_mm

        logger.info(
            "ReportTemplateEngine initialized",
            template_dir=str(self._template_dir),
            templates=self.list_templates(),
        )

    def list_templates(self) -> list[str]:
        """Return list of available template names."""
        return self._env.list_templates()

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        """Render a report template with the given context.

        Args:
            template_name: Template filename (e.g., "lung_rads.j2").
            context: Dictionary of variables to pass to the template.

        Returns:
            Rendered report text.

        Raises:
            TemplateError: On template not found or rendering failure.
        """
        try:
            template = self._env.get_template(template_name)
        except Exception as exc:
            raise TemplateError(f"Template '{template_name}' not found: {exc}") from exc

        try:
            # Add default context values
            context.setdefault("ai_disclaimer", None)
            context.setdefault("ai_findings", [])
            context.setdefault("recommendations", [])
            context.setdefault("impression_text", None)

            report_text = template.render(**context)
            logger.info(
                "Report rendered",
                template=template_name,
                output_len=len(report_text),
            )
            return report_text
        except Exception as exc:
            raise TemplateError(f"Failed to render '{template_name}': {exc}") from exc

    @staticmethod
    def _format_hu(value: int | float | None) -> str:
        """Format Hounsfield Unit value."""
        if value is None:
            return "N/A"
        return f"{value} HU"

    @staticmethod
    def _format_mm(value: int | float | None) -> str:
        """Format millimeter value."""
        if value is None:
            return "N/A"
        return f"{value:.1f} mm"


# ─── Context builders ────────────────────────────────────────────────────────
def build_lung_rads_context(
    findings: list[dict],
    nodule_summary: list[dict] | None = None,
    lung_rads_category: str | None = None,
    lung_rads_description: str | None = None,
    clinical_indication: str = "Lung cancer screening",
    comparison: str = "None available",
    **extra: Any,
) -> dict[str, Any]:
    """Build template context from findings for a Lung-RADS report.

    Args:
        findings: List of finding dicts with keys:
            - finding_type: "nodule", "mass", "consolidation", etc.
            - location: Anatomical location
            - description: Free-text description
            - measurements: Dict with longest_diameter_mm, volume_mm3, mean_hu
        nodule_summary: Optional list of nodule candidate dicts from AI detection.
        lung_rads_category: e.g., "Lung-RADS 2", "Lung-RADS 3".
        lung_rads_description: Category description.
        clinical_indication: Clinical reason for exam.
        comparison: Prior study comparison text.

    Returns:
        Context dict for the lung_rads.j2 template.
    """
    # Categorize findings by body region
    lung_findings = [f for f in findings if f.get("finding_type") in ("nodule", "mass", "consolidation", "ground_glass", "interstitial")]
    mediastinal_findings = [f for f in findings if f.get("finding_type") in ("lymphadenopathy", "lymph_node")]
    cardiac_findings = [f for f in findings if f.get("finding_type") in ("cardiac", "pericardial", "aortic")]
    pleural_findings = [f for f in findings if f.get("finding_type") in ("pleural", "effusion", "pneumothorax")]
    bone_findings = [f for f in findings if f.get("finding_type") in ("bone", "osseous", "fracture")]

    context = {
        "lung_findings": lung_findings,
        "mediastinal_findings": mediastinal_findings,
        "cardiac_findings": cardiac_findings,
        "pleural_findings": pleural_findings,
        "bone_findings": bone_findings,
        "nodule_summary": nodule_summary or [],
        "lung_rads_category": lung_rads_category,
        "lung_rads_description": lung_rads_description,
        "clinical_indication": clinical_indication,
        "comparison": comparison,
    }
    context.update(extra)
    return context


def build_general_context(
    findings: list[dict],
    body_part: str = "CHEST",
    clinical_indication: str = "Clinical evaluation",
    comparison: str = "None available",
    **extra: Any,
) -> dict[str, Any]:
    """Build template context for a general CT/MRI report.

    Args:
        findings: List of finding dicts.
        body_part: Body part examined.
        clinical_indication: Clinical reason for exam.
        comparison: Prior study comparison text.

    Returns:
        Context dict for the general_ct.j2 template.
    """
    # Group findings by location
    findings_by_region: dict[str, list[dict]] = {}
    for f in findings:
        region = f.get("location", "Other")
        findings_by_region.setdefault(region, []).append(f)

    context = {
        "body_part": body_part,
        "findings_by_region": findings_by_region,
        "clinical_indication": clinical_indication,
        "comparison": comparison,
    }
    context.update(extra)
    return context


# ─── Singleton ───────────────────────────────────────────────────────────────
_engine: ReportTemplateEngine | None = None


def get_template_engine() -> ReportTemplateEngine:
    """Return the process-wide ReportTemplateEngine singleton."""
    global _engine
    if _engine is None:
        _engine = ReportTemplateEngine()
    return _engine
