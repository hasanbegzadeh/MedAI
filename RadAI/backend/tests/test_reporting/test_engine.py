"""Tests for the report generation engine."""

from __future__ import annotations

import pytest

from app.reporting.engine import (
    ReportTemplateEngine,
    TemplateError,
    build_lung_rads_context,
    build_general_context,
    get_template_engine,
)


class TestReportTemplateEngine:
    """Tests for Jinja2 report template engine."""

    def test_engine_is_singleton(self):
        """get_template_engine returns the same instance."""
        e1 = get_template_engine()
        e2 = get_template_engine()
        assert e1 is e2

    def test_list_templates(self):
        """Engine lists available templates."""
        engine = ReportTemplateEngine()
        templates = engine.list_templates()

        assert isinstance(templates, list)
        # Should find at least the default templates
        assert len(templates) > 0

    def test_render_lung_rads_template(self):
        """Lung-RADS template renders with valid context."""
        engine = ReportTemplateEngine()
        context = build_lung_rads_context(
            findings=[
                {
                    "finding_type": "nodule",
                    "location": "Right upper lobe",
                    "description": "Solid nodule, 8mm",
                    "measurements": {"longest_diameter_mm": 8.0, "mean_hu": -450},
                    "characteristics": ["solid"],
                    "confidence": 0.85,
                }
            ],
            lung_rads_category="Lung-RADS 3",
            clinical_indication="Lung cancer screening",
        )

        result = engine.render("lung_rads.j2", context)

        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain report structure
        assert any(keyword in result.lower() for keyword in [
            "findings", "impression", "chest", "ct"
        ])

    def test_render_general_template(self):
        """General CT template renders with valid context."""
        engine = ReportTemplateEngine()
        context = build_general_context(
            findings=[
                {
                    "finding_type": "nodule",
                    "location": "Right lung",
                    "description": "Small nodule",
                    "measurements": {},
                    "characteristics": [],
                }
            ],
            body_part="CHEST",
            clinical_indication="Clinical evaluation",
        )

        result = engine.render("general_ct.j2", context)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_missing_template_raises(self):
        """Requesting a non-existent template raises TemplateError."""
        engine = ReportTemplateEngine()

        with pytest.raises(TemplateError, match="not found"):
            engine.render("nonexistent_template.j2", {})

    def test_format_hu_filter(self):
        """HU formatting filter works correctly."""
        engine = ReportTemplateEngine()

        assert engine._format_hu(-450) == "-450 HU"
        assert engine._format_hu(0) == "0 HU"
        assert engine._format_hu(None) == "N/A"

    def test_format_mm_filter(self):
        """MM formatting filter works correctly."""
        engine = ReportTemplateEngine()

        assert engine._format_mm(8.5) == "8.5 mm"
        assert engine._format_mm(0.0) == "0.0 mm"
        assert engine._format_mm(None) == "N/A"


class TestContextBuilders:
    """Tests for report context building functions."""

    def test_build_lung_rads_context_categorizes_findings(self):
        """Lung-RADS context builder categorizes findings correctly."""
        findings = [
            {"finding_type": "nodule", "location": "Right upper lobe"},
            {"finding_type": "lymphadenopathy", "location": "Mediastinum"},
            {"finding_type": "pleural", "location": "Right pleura"},
        ]

        context = build_lung_rads_context(findings=findings)

        assert len(context["lung_findings"]) == 1
        assert len(context["mediastinal_findings"]) == 1
        assert len(context["pleural_findings"]) == 1

    def test_build_lung_rads_context_defaults(self):
        """Lung-RADS context builder provides sensible defaults."""
        context = build_lung_rads_context(findings=[])

        assert "clinical_indication" in context
        assert "comparison" in context
        assert context["clinical_indication"] == "Lung cancer screening"
        assert context["comparison"] == "None available"

    def test_build_general_context_groups_by_location(self):
        """General context groups findings by location."""
        findings = [
            {"finding_type": "nodule", "location": "Right lung"},
            {"finding_type": "nodule", "location": "Left lung"},
            {"finding_type": "mass", "location": "Right lung"},
        ]

        context = build_general_context(findings=findings, body_part="CHEST")

        assert "findings_by_region" in context
        assert "Right lung" in context["findings_by_region"]
        assert "Left lung" in context["findings_by_region"]
        assert len(context["findings_by_region"]["Right lung"]) == 2

    def test_build_general_context_defaults(self):
        """General context provides sensible defaults."""
        context = build_general_context(findings=[])

        assert context["body_part"] == "CHEST"
        assert context["clinical_indication"] == "Clinical evaluation"
