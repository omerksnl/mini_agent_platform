from pathlib import Path
from uuid import UUID

from pypdf import PdfReader
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.report_templates import REPORT_TEMPLATES
from app.core.services.generated_file_service import GeneratedFileError, GeneratedFileService
from app.core.services.report_pdf_service import ReportPdfService
from app.core.tools.text_to_pdf_tools import build_text_to_pdf_tool
from app.models import Agent, Tenant


SAMPLE_MARKDOWN = """# Final Candidate Assessment

## Score Summary

| Component | Score |
|---|---:|
| CV and Job Fit | 77.5 / 100 |
| Interview | 91.7 / 100 |

## Executive Summary

The candidate demonstrates strong role alignment supported by project and interview evidence.

## Strengths

- Strong evidence from the role-specific project.
- Clear explanation of technical trade-offs.

## Risks

- Production monitoring remains unverified.

## Development Areas

- Build practical experience with model monitoring and drift detection.
- Add reproducible experiment tracking and model versioning.

## CV-Interview Consistency

- Project responsibilities described in the interview are consistent with the CV evidence.

## Recommended Follow-Up

- Ask for a concrete production-monitoring and rollback plan.

## Human Review Notice

This report supports human review and does not make an employment decision.
"""


def test_registered_templates_render_readable_pdfs() -> None:
    for template_id in REPORT_TEMPLATES:
        data = ReportPdfService().render(SAMPLE_MARKDOWN, template_id)
        assert data.startswith(b"%PDF-")
        reader = PdfReader(__import__("io").BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert "Final Candidate" in text
        assert "Assessment" in text
        assert "Strengths" in text


def test_two_column_template_splits_long_colored_sections() -> None:
    long_markdown = "# Final Candidate Assessment\n\n## Strengths\n\n" + "\n\n".join(
        f"Evidence item {index}: " + ("role-specific verified evidence " * 30)
        for index in range(1, 18)
    )

    data = ReportPdfService().render(long_markdown, "two_column")

    assert data.startswith(b"%PDF-")
    reader = PdfReader(__import__("io").BytesIO(data))
    assert len(reader.pages) > 1
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Evidence item 17" in text


def test_assessment_sections_have_dedicated_palettes() -> None:
    service = ReportPdfService()

    assert service._section_palette("Overall Score") is not None
    assert service._section_palette("Strengths") is not None
    assert service._section_palette("Weaknesses") is not None
    assert service._section_palette("Inconsistencies") is not None
    assert service._section_palette("Overall Opinion") is not None


def test_text_to_pdf_creates_tenant_scoped_generated_file(
    db_session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db_session_factory() as db:
        tenant = Tenant(name="Acme")
        agent = Agent(tenant=tenant, name="Reporter", system_tools=["text_to_pdf"])
        db.add_all([tenant, agent])
        db.commit()
        service = GeneratedFileService(db)
        monkeypatch.setattr(service.settings, "upload_directory", str(tmp_path))

        tool = build_text_to_pdf_tool(db, agent)
        result = tool.invoke({
            "content": SAMPLE_MARKDOWN,
            "template_id": "two_column",
            "filename": "../candidate report.pdf",
            "title": "Candidate Report",
        })
        db.commit()

        assert '"template_id": "two_column"' in result
        assert "candidate report.pdf" in result
        generated_id = __import__("json").loads(result)["generated_file_id"]
        generated = service.get(UUID(generated_id), tenant.id)
        assert generated.original_name == "candidate report.pdf"
        assert service.path_for(generated).is_file()


def test_generated_file_cannot_cross_tenants(
    db_session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db_session_factory() as db:
        tenant_a = Tenant(name="A")
        tenant_b = Tenant(name="B")
        agent = Agent(tenant=tenant_a, name="Reporter")
        db.add_all([tenant_a, tenant_b, agent])
        db.commit()
        service = GeneratedFileService(db)
        monkeypatch.setattr(service.settings, "upload_directory", str(tmp_path))
        generated = service.create_pdf(
            tenant_a.id,
            agent.id,
            "report.pdf",
            "blank_markdown",
            ReportPdfService().render("# Report", "blank_markdown"),
        )
        db.commit()

        try:
            service.get(generated.id, tenant_b.id)
        except GeneratedFileError as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("Cross-tenant generated file access was allowed")
