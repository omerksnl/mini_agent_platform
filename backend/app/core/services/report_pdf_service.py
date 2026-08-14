from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    ListFlowable,
    ListItem,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.report_templates import REPORT_TEMPLATES


class ReportPdfError(Exception):
    pass


class ReportPdfService:
    accent = colors.HexColor("#B53333")
    text = colors.HexColor("#303030")
    muted = colors.HexColor("#666666")

    def render(self, content: str, template_id: str, title: str | None = None) -> bytes:
        template = REPORT_TEMPLATES.get(template_id)
        if template is None:
            raise ReportPdfError("Unknown report template")
        if not content.strip():
            raise ReportPdfError("PDF content cannot be empty")

        regular, bold = self._register_fonts()
        styles = self._styles(regular, bold)
        document_title = title
        body_content = content
        if template.columns == 2:
            heading_match = re.match(r"^\s*#\s+(.+?)\s*(?:\n+|$)", content)
            if heading_match:
                document_title = document_title or heading_match.group(1).strip()
                body_content = content[heading_match.end():]
        available_width = 78 * mm if template.columns == 2 else 174 * mm
        story = self._markdown_flowables(
            body_content,
            styles,
            available_width,
            enable_section_boxes=template.columns == 2,
        )
        if title and template.columns == 1 and not self._starts_with_h1(content):
            story.insert(0, Paragraph(self._inline(title), styles["Title"]))
            story.insert(1, Spacer(1, 4 * mm))

        output = BytesIO()
        if template.columns == 2:
            self._build_two_column(
                output, story, document_title or "Generated report", regular, bold
            )
        else:
            document = SimpleDocTemplate(
                output,
                pagesize=A4,
                leftMargin=18 * mm,
                rightMargin=18 * mm,
                topMargin=17 * mm,
                bottomMargin=17 * mm,
                title=title or "Generated report",
                author="Mini Agent Platform",
            )
            document.build(story, onFirstPage=self._footer(regular), onLaterPages=self._footer(regular))
        return output.getvalue()

    def _build_two_column(
        self, output: BytesIO, story: list, title: str, font: str, bold_font: str
    ) -> None:
        document = BaseDocTemplate(
            output,
            pagesize=A4,
            leftMargin=13 * mm,
            rightMargin=13 * mm,
            topMargin=30 * mm,
            bottomMargin=15 * mm,
            title=title,
            author="Mini Agent Platform",
        )
        gap = 8 * mm
        column_width = (document.width - gap) / 2
        frames = [
            Frame(document.leftMargin, document.bottomMargin, column_width, document.height, id="left"),
            Frame(document.leftMargin + column_width + gap, document.bottomMargin, column_width, document.height, id="right"),
        ]
        footer = self._footer(font)

        def draw_page(canvas, doc) -> None:
            footer(canvas, doc)
            if doc.page == 1:
                canvas.saveState()
                canvas.setFont(bold_font, 18)
                canvas.setFillColor(self.text)
                canvas.drawCentredString(A4[0] / 2, A4[1] - 18 * mm, title[:90])
                canvas.setStrokeColor(self.accent)
                canvas.setLineWidth(0.7)
                canvas.line(doc.leftMargin, A4[1] - 23 * mm, A4[0] - doc.rightMargin, A4[1] - 23 * mm)
                canvas.restoreState()

        document.addPageTemplates(PageTemplate(id="two_column", frames=frames, onPage=draw_page))
        document.build(story)

    def _styles(self, regular: str, bold: str) -> dict[str, ParagraphStyle]:
        sample = getSampleStyleSheet()
        return {
            "Body": ParagraphStyle(
                "Body",
                parent=sample["BodyText"],
                fontName=regular,
                fontSize=9.4,
                leading=13,
                textColor=self.text,
                spaceAfter=2.5 * mm,
            ),
            "Title": ParagraphStyle(
                "Title",
                parent=sample["Title"],
                fontName=bold,
                fontSize=20,
                leading=24,
                alignment=TA_CENTER,
                textColor=self.text,
                spaceAfter=4 * mm,
            ),
            "H2": ParagraphStyle(
                "H2",
                parent=sample["Heading2"],
                fontName=bold,
                fontSize=12.5,
                leading=15,
                textColor=self.accent,
                spaceBefore=4 * mm,
                spaceAfter=1.5 * mm,
                keepWithNext=True,
            ),
            "H3": ParagraphStyle(
                "H3",
                parent=sample["Heading3"],
                fontName=bold,
                fontSize=10.5,
                leading=13,
                textColor=self.text,
                spaceBefore=2.5 * mm,
                spaceAfter=1.5 * mm,
                keepWithNext=True,
            ),
            "Small": ParagraphStyle(
                "Small", parent=sample["BodyText"], fontName=regular, fontSize=7.5, leading=9.5
            ),
        }

    def _markdown_flowables(
        self,
        content: str,
        styles: dict[str, ParagraphStyle],
        available_width: float,
        enable_section_boxes: bool = False,
    ) -> list:
        lines = content.replace("\r\n", "\n").split("\n")
        flowables: list = []
        paragraph_lines: list[str] = []
        index = 0

        def flush_paragraph() -> None:
            if paragraph_lines:
                joined = " ".join(item.strip() for item in paragraph_lines).strip()
                if joined:
                    flowables.append(Paragraph(self._inline(joined), styles["Body"]))
                paragraph_lines.clear()

        while index < len(lines):
            line = lines[index].rstrip()
            stripped = line.strip()
            if not stripped:
                flush_paragraph()
                index += 1
                continue
            if stripped.startswith("|") and index + 1 < len(lines) and self._is_table_divider(lines[index + 1]):
                flush_paragraph()
                table_lines = [stripped]
                index += 2
                while index < len(lines) and lines[index].strip().startswith("|"):
                    table_lines.append(lines[index].strip())
                    index += 1
                flowables.append(self._table(table_lines, styles, available_width))
                continue
            heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
            if heading:
                flush_paragraph()
                level = len(heading.group(1))
                heading_text = heading.group(2).strip()
                palette = self._section_palette(heading_text) if level == 2 else None
                if enable_section_boxes and palette is not None:
                    section_lines: list[str] = []
                    index += 1
                    while index < len(lines) and not re.match(r"^##\s+", lines[index].strip()):
                        section_lines.append(lines[index])
                        index += 1
                    inner_width = available_width - 8 * mm
                    section_flowables = self._markdown_flowables(
                        "\n".join(section_lines),
                        styles,
                        inner_width,
                        enable_section_boxes=False,
                    )
                    flowables.append(
                        self._section_box(
                            heading_text,
                            section_flowables,
                            available_width,
                            styles,
                            palette,
                        )
                    )
                    flowables.append(Spacer(1, 3 * mm))
                    continue
                style = "Title" if level == 1 else "H2" if level == 2 else "H3"
                flowables.append(Paragraph(self._inline(heading_text), styles[style]))
                if level == 2:
                    flowables.append(HRFlowable(width="100%", thickness=0.5, color=self.accent, spaceAfter=1.5 * mm))
                index += 1
                continue
            if stripped in {"---", "***"}:
                flush_paragraph()
                flowables.append(HRFlowable(width="100%", thickness=0.45, color=colors.HexColor("#BBBBBB"), spaceBefore=2 * mm, spaceAfter=2 * mm))
                index += 1
                continue
            if re.match(r"^[-*+]\s+", stripped):
                flush_paragraph()
                items: list[ListItem] = []
                while index < len(lines) and re.match(r"^\s*[-*+]\s+", lines[index]):
                    item = re.sub(r"^\s*[-*+]\s+", "", lines[index]).strip()
                    items.append(ListItem(Paragraph(self._inline(item), styles["Body"]), leftIndent=4 * mm))
                    index += 1
                flowables.append(ListFlowable(items, bulletType="bullet", leftIndent=6 * mm, bulletFontName=styles["Body"].fontName))
                flowables.append(Spacer(1, 1.5 * mm))
                continue
            paragraph_lines.append(stripped)
            index += 1
        flush_paragraph()
        return flowables

    def _section_box(
        self,
        title: str,
        flowables: list,
        available_width: float,
        styles: dict[str, ParagraphStyle],
        palette: tuple[colors.Color, colors.Color],
    ) -> Table:
        border, background = palette
        heading_style = ParagraphStyle(
            f"BoxHeading-{title}",
            parent=styles["H2"],
            textColor=border,
            spaceBefore=0,
            spaceAfter=0,
        )
        content = flowables or [Paragraph("No information provided.", styles["Body"])]
        box = Table(
            [[Paragraph(self._inline(title), heading_style)], [content]],
            colWidths=[available_width],
            hAlign="LEFT",
        )
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), background),
            ("BOX", (0, 0), (-1, -1), 0.8, border),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, border),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 1), (-1, 1), 7),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return box

    @staticmethod
    def _section_palette(title: str) -> tuple[colors.Color, colors.Color] | None:
        normalized = re.sub(r"[^a-z]+", " ", title.casefold()).strip()
        if normalized in {"strengths", "pros", "key strengths"}:
            return colors.HexColor("#2E7D4F"), colors.HexColor("#EAF6EF")
        if normalized in {"risks", "cons", "limitations", "risk factors"}:
            return colors.HexColor("#B23A3A"), colors.HexColor("#FBEDED")
        if normalized in {"development areas", "development area", "growth areas"}:
            return colors.HexColor("#B36B00"), colors.HexColor("#FFF4DD")
        return None

    def _table(
        self, lines: list[str], styles: dict[str, ParagraphStyle], available_width: float
    ) -> Table:
        rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        data = [[Paragraph(self._inline(cell), styles["Small"]) for cell in row] for row in rows]
        table = Table(
            data,
            colWidths=[available_width / width] * width,
            repeatRows=1,
            hAlign="LEFT",
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4E6E6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), self.text),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CCCCCC")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    @staticmethod
    def _is_table_divider(line: str) -> bool:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)

    @staticmethod
    def _inline(text: str) -> str:
        safe = escape(text)
        safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
        safe = re.sub(r"`([^`]+)`", r"<font name=\"Courier\">\1</font>", safe)
        return safe

    @staticmethod
    def _starts_with_h1(content: str) -> bool:
        return bool(re.match(r"^\s*#\s+", content))

    @staticmethod
    def _register_fonts() -> tuple[str, str]:
        candidates = [
            (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
            (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        ]
        for regular_path, bold_path in candidates:
            if regular_path.exists() and bold_path.exists():
                if "ReportSans" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("ReportSans", str(regular_path)))
                    pdfmetrics.registerFont(TTFont("ReportSans-Bold", str(bold_path)))
                return "ReportSans", "ReportSans-Bold"
        return "Helvetica", "Helvetica-Bold"

    def _footer(self, font: str):
        def draw(canvas, document) -> None:
            canvas.saveState()
            canvas.setFont(font, 7)
            canvas.setFillColor(self.muted)
            canvas.drawString(document.leftMargin, 8 * mm, "Generated by Mini Agent Platform")
            canvas.drawRightString(A4[0] - document.rightMargin, 8 * mm, f"Page {document.page}")
            canvas.restoreState()

        return draw
