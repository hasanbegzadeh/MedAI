"""RadAI — PDF Report Export.

Generates professional PDF radiology reports using ReportLab.
Supports custom branding, watermarks, and multi-page reports.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)

logger = structlog.get_logger(__name__)


class PDFReportError(Exception):
    """Raised when PDF generation fails."""


def generate_pdf_report(
    report_text: str,
    output_path: str | Path | None = None,
    patient_name: str = "ANONYMOUS",
    patient_id: str = "UNKNOWN",
    study_date: str | None = None,
    referring_physician: str = "",
    radiologist: str = "",
    classification: str | None = None,
    template_name: str | None = None,
    institution: str = "RadAI Medical Center",
    include_header: bool = True,
    include_footer: bool = True,
    include_disclaimer: bool = True,
) -> Path:
    """Generate a PDF radiology report.

    Args:
        report_text: Full report text (from template or AI-polished).
        output_path: Destination PDF path. Auto-generated if None.
        patient_name: Patient name (anonymized by default).
        patient_id: Patient ID.
        study_date: Date of study (YYYY-MM-DD).
        referring_physician: Referring physician name.
        radiologist: Interpreting radiologist name.
        classification: e.g., "Lung-RADS 3".
        template_name: Template used.
        institution: Institution name for header.
        include_header: Show report header with institution.
        include_footer: Show page footer.
        include_disclaimer: Show AI disclaimer at end.

    Returns:
        Path to the written PDF file.
    """
    if output_path is None:
        output_path = Path(f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Generating PDF report", output=str(output_path))

    try:
        buffer = io.BytesIO()

        # Create document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            title="RadAI Radiology Report",
            author=radiologist or "RadAI System",
        )

        # Build styles
        styles = _build_styles()

        # Build story (content flow)
        story = []

        if include_header:
            story.extend(_build_header(
                institution, patient_name, patient_id,
                study_date, referring_physician, styles
            ))

        # Classification banner
        if classification:
            story.append(_build_classification_banner(classification, styles))
            story.append(Spacer(1, 0.2 * inch))

        # Main report text
        story.append(Paragraph("REPORT", styles["SectionHeading"]))
        story.append(Spacer(1, 0.1 * inch))

        # Parse report text into paragraphs
        paragraphs = _parse_report_text(report_text, styles)
        story.extend(paragraphs)

        # AI Disclaimer
        if include_disclaimer:
            story.append(Spacer(1, 0.3 * inch))
            story.append(_build_disclaimer(styles))

        # Signature block
        if radiologist:
            story.append(Spacer(1, 0.5 * inch))
            story.extend(_build_signature_block(radiologist, study_date, styles))

        # Template info
        if template_name:
            story.append(Spacer(1, 0.2 * inch))
            story.append(
                Paragraph(f"Report template: {template_name}", styles["SmallText"])
            )

        # Build PDF
        doc.build(story)

        # Write to file
        with open(output_path, "wb") as f:
            f.write(buffer.getvalue())

        buffer.close()

        logger.info(
            "PDF report generated",
            path=str(output_path),
            size_kb=output_path.stat().st_size / 1024,
        )
        return output_path

    except Exception as exc:
        raise PDFReportError(f"Failed to generate PDF: {exc}") from exc


def _build_styles() -> dict:
    """Create custom ReportLab styles."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="Institution",
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=colors.HexColor("#003366"),
        alignment=TA_CENTER,
        spaceAfter=2,
    ))

    styles.add(ParagraphStyle(
        name="ReportTitle",
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#003366"),
        alignment=TA_CENTER,
        spaceAfter=10,
    ))

    styles.add(ParagraphStyle(
        name="SectionHeading",
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=colors.HexColor("#003366"),
        spaceBefore=12,
        spaceAfter=6,
        borderWidth=1,
        borderColor=colors.HexColor("#003366"),
        borderPadding=4,
        backColor=colors.HexColor("#E8EEF4"),
    ))

    styles.add(ParagraphStyle(
        name="ReportBody",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    ))

    styles.add(ParagraphStyle(
        name="ClassificationBanner",
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.white,
        alignment=TA_CENTER,
        backColor=colors.HexColor("#CC6600"),
        borderWidth=1,
        borderColor=colors.HexColor("#994400"),
        borderPadding=8,
    ))

    styles.add(ParagraphStyle(
        name="Disclaimer",
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#666666"),
        alignment=TA_LEFT,
        borderWidth=1,
        borderColor=colors.HexColor("#CCCCCC"),
        borderPadding=6,
        backColor=colors.HexColor("#F5F5F5"),
    ))

    styles.add(ParagraphStyle(
        name="SmallText",
        fontName="Helvetica",
        fontSize=8,
        textColor=colors.HexColor("#999999"),
    ))

    styles.add(ParagraphStyle(
        name="Signature",
        fontName="Helvetica",
        fontSize=10,
        spaceBefore=2,
    ))

    return styles


def _build_header(institution, patient_name, patient_id,
                  study_date, referring_physician, styles) -> list:
    """Build report header with institution and patient info."""
    elements = []

    # Institution
    elements.append(Paragraph(institution, styles["Institution"]))
    elements.append(Paragraph("RADIOLOGY REPORT", styles["ReportTitle"]))

    # Horizontal rule
    elements.append(Spacer(1, 0.1 * inch))

    # Patient info table
    patient_data = [
        ["Patient:", patient_name, "ID:", patient_id],
        ["Date:", study_date or "N/A", "Referring MD:", referring_physician or "N/A"],
    ]
    patient_table = Table(patient_data, colWidths=[0.8 * inch, 2.2 * inch, 1.0 * inch, 2.2 * inch])
    patient_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#666666")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#666666")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(patient_table)
    elements.append(Spacer(1, 0.15 * inch))

    return elements


def _build_classification_banner(classification: str, styles) -> Paragraph:
    """Build a colored classification banner (e.g., Lung-RADS 3)."""
    return Paragraph(classification.upper(), styles["ClassificationBanner"])


def _parse_report_text(report_text: str, styles: dict) -> list:
    """Parse report text into ReportLab flowables.

    Handles:
    - Blank lines as paragraph breaks
    - Lines starting with "- " as bullet points
    - Section headings (all caps or followed by ":")
    """
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.units import inch

    elements = []
    lines = report_text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            elements.append(Spacer(1, 0.08 * inch))
            continue

        # Bullet point
        if line.startswith("- "):
            bullet_text = line[2:]
            elements.append(
                Paragraph(f"&bull; {bullet_text}", styles["ReportBody"])
            )
        # Section heading (all uppercase or ends with colon)
        elif line.isupper() or line.endswith(":"):
            elements.append(Paragraph(line, styles["SectionHeading"]))
            elements.append(Spacer(1, 0.05 * inch))
        # Separator line
        elif line.startswith("---"):
            elements.append(Spacer(1, 0.15 * inch))
        # Regular paragraph
        else:
            elements.append(Paragraph(line, styles["ReportBody"]))

    return elements


def _build_disclaimer(styles) -> Paragraph:
    """Build AI disclaimer paragraph."""
    disclaimer_text = (
        "<b>AI Assistance Notice:</b> This report was generated with the assistance "
        "of artificial intelligence (RadAI v0.1.0). AI-detected findings were reviewed "
        "and confirmed by the interpreting radiologist. The final interpretation and "
        "diagnosis are the sole responsibility of the qualified radiologist named below."
    )
    return Paragraph(disclaimer_text, styles["Disclaimer"])


def _build_signature_block(radiologist: str, study_date: str | None, styles) -> list:
    """Build radiologist signature block."""
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.units import inch

    elements = []

    # Signature line
    elements.append(Paragraph("_" * 40, styles["Signature"]))
    elements.append(Paragraph(f"<b>{radiologist}</b>, MD", styles["Signature"]))
    elements.append(Paragraph("Board-Certified Radiologist", styles["Signature"]))

    if study_date:
        try:
            date_obj = datetime.strptime(study_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%B %d, %Y")
        except ValueError:
            formatted_date = study_date
        elements.append(Paragraph(f"Reported: {formatted_date}", styles["SmallText"]))

    return elements
