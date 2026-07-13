from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "docs" / "compliance"
OUTPUT_DIR = ROOT / "output" / "pdf"

DOCUMENTS = [
    (
        SOURCE_DIR / "hmrc_production_credentials_technical_evidence_pack_2026_07_13.md",
        OUTPUT_DIR / "hmrc_production_credentials_technical_evidence_pack_2026_07_13.pdf",
        "LedgerHouse HMRC Technical Evidence Pack",
    ),
    (
        SOURCE_DIR / "hmrc_production_credentials_plain_english_guide_2026_07_13.md",
        OUTPUT_DIR / "hmrc_production_credentials_plain_english_guide_2026_07_13.pdf",
        "LedgerHouse HMRC Plain-English Guide",
    ),
]


def escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def inline_markup(text: str) -> str:
    text = escape(text)
    text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DocTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=25,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#12323b"),
            spaceAfter=10 * mm,
        ),
        "h1": ParagraphStyle(
            "Heading1Custom",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=colors.HexColor("#12323b"),
            spaceBefore=7 * mm,
            spaceAfter=3 * mm,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "Heading2Custom",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#1f4b57"),
            spaceBefore=5 * mm,
            spaceAfter=2 * mm,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "BodyCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            alignment=TA_LEFT,
            spaceAfter=2.3 * mm,
        ),
        "bullet": ParagraphStyle(
            "BulletCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.2,
            leftIndent=0,
            firstLineIndent=0,
        ),
        "code": ParagraphStyle(
            "CodeCustom",
            parent=base["Code"],
            fontName="Courier",
            fontSize=8,
            leading=10,
            leftIndent=4 * mm,
            rightIndent=4 * mm,
            backColor=colors.HexColor("#f3f6f7"),
            borderColor=colors.HexColor("#d7e0e3"),
            borderWidth=0.5,
            borderPadding=4,
            spaceBefore=2 * mm,
            spaceAfter=3 * mm,
        ),
        "footer": ParagraphStyle(
            "FooterCustom",
            parent=base["BodyText"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#5a676b"),
        ),
    }


def flush_paragraph(buffer: list[str], story: list, styles: dict[str, ParagraphStyle]) -> None:
    if not buffer:
        return
    text = " ".join(line.strip() for line in buffer if line.strip())
    if text:
        story.append(Paragraph(inline_markup(text), styles["body"]))
    buffer.clear()


def flush_bullets(buffer: list[str], story: list, styles: dict[str, ParagraphStyle]) -> None:
    if not buffer:
        return
    items = [
        ListItem(Paragraph(inline_markup(item), styles["bullet"]), leftIndent=5 * mm)
        for item in buffer
    ]
    story.append(
        ListFlowable(
            items,
            bulletType="bullet",
            start="circle",
            leftIndent=7 * mm,
            bulletFontName="Helvetica",
            bulletFontSize=6,
            spaceAfter=2 * mm,
        )
    )
    buffer.clear()


def markdown_to_story(markdown: str, title: str, styles: dict[str, ParagraphStyle]):
    story: list = []
    paragraph_buffer: list[str] = []
    bullet_buffer: list[str] = []
    code_buffer: list[str] = []
    in_code = False
    first_heading = True

    story.append(Paragraph(inline_markup(title), styles["title"]))
    story.append(Spacer(1, 2 * mm))

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.startswith("```"):
            if in_code:
                story.append(Preformatted("\n".join(code_buffer), styles["code"]))
                code_buffer.clear()
                in_code = False
            else:
                flush_paragraph(paragraph_buffer, story, styles)
                flush_bullets(bullet_buffer, story, styles)
                in_code = True
            continue

        if in_code:
            code_buffer.append(line)
            continue

        if not line.strip():
            flush_paragraph(paragraph_buffer, story, styles)
            flush_bullets(bullet_buffer, story, styles)
            continue

        if line.startswith("# "):
            flush_paragraph(paragraph_buffer, story, styles)
            flush_bullets(bullet_buffer, story, styles)
            if first_heading:
                first_heading = False
                continue
            story.append(PageBreak())
            story.append(Paragraph(inline_markup(line[2:].strip()), styles["h1"]))
            continue

        if line.startswith("## "):
            flush_paragraph(paragraph_buffer, story, styles)
            flush_bullets(bullet_buffer, story, styles)
            story.append(Paragraph(inline_markup(line[3:].strip()), styles["h1"]))
            continue

        if line.startswith("### "):
            flush_paragraph(paragraph_buffer, story, styles)
            flush_bullets(bullet_buffer, story, styles)
            story.append(Paragraph(inline_markup(line[4:].strip()), styles["h2"]))
            continue

        if line.startswith("- "):
            flush_paragraph(paragraph_buffer, story, styles)
            bullet_buffer.append(line[2:].strip())
            continue

        if re.match(r"^\d+\.\s+", line):
            flush_paragraph(paragraph_buffer, story, styles)
            bullet_buffer.append(re.sub(r"^\d+\.\s+", "", line).strip())
            continue

        flush_bullets(bullet_buffer, story, styles)
        paragraph_buffer.append(line)

    flush_paragraph(paragraph_buffer, story, styles)
    flush_bullets(bullet_buffer, story, styles)
    if code_buffer:
        story.append(Preformatted("\n".join(code_buffer), styles["code"]))
    return story


def draw_footer(canvas, doc, title: str):
    canvas.saveState()
    width, _height = A4
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#5a676b"))
    canvas.drawString(18 * mm, 12 * mm, title)
    canvas.drawRightString(width - 18 * mm, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(source: Path, output: Path, title: str) -> None:
    markdown = source.read_text(encoding="utf-8")
    styles = build_styles()
    story = markdown_to_story(markdown, title, styles)
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=title,
        author="KAFS / LedgerHouse",
    )
    doc.build(
        story,
        onFirstPage=lambda canvas, doc: draw_footer(canvas, doc, title),
        onLaterPages=lambda canvas, doc: draw_footer(canvas, doc, title),
    )


def main() -> None:
    for source, output, title in DOCUMENTS:
        build_pdf(source, output, title)
        print(output)


if __name__ == "__main__":
    main()
