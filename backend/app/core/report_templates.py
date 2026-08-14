from dataclasses import dataclass


@dataclass(frozen=True)
class ReportTemplate:
    id: str
    name: str
    description: str
    columns: int


REPORT_TEMPLATES = {
    "blank_markdown": ReportTemplate(
        id="blank_markdown",
        name="Blank Markdown",
        description="Clean single-column document for general Markdown content.",
        columns=1,
    ),
    "two_column": ReportTemplate(
        id="two_column",
        name="Two Column",
        description=(
            "Compact two-column document inspired by the installed Overleaf CV template, "
            "with red section headings and fine divider rules."
        ),
        columns=2,
    ),
}

DEFAULT_REPORT_TEMPLATE_ID = "blank_markdown"


def template_catalog_for_model() -> str:
    return "\n".join(
        f"- {item.id}: {item.description}" for item in REPORT_TEMPLATES.values()
    )
