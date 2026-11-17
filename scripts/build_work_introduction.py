"""Build the editable work introduction from its Markdown source.

Authoring dependency: python-docx; application startup does not require it.
"""
from __future__ import annotations

import re
import argparse
import json
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "作品介绍文档.md"
OUTPUT = ROOT / "output" / "doc" / "澄明-作品介绍文档.docx"
FONT = "Microsoft YaHei"


def font_style(style, size: float, bold: bool = False) -> None:
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.italic = False
    style.font.underline = False
    style.font.color.rgb = RGBColor(0, 0, 0)
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for name in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "csTheme"):
        fonts.attrib.pop(qn("w:" + name), None)
    for name in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn("w:" + name), FONT)


def inline(paragraph, text: str) -> None:
    position = 0
    for match in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", text):
        paragraph.add_run(text[position:match.start()].replace("`", ""))
        link = OxmlElement("w:hyperlink")
        link.set(qn("r:id"), paragraph.part.relate_to(match.group(2), RELATIONSHIP_TYPE.HYPERLINK, is_external=True))
        run = OxmlElement("w:r")
        properties = OxmlElement("w:rPr")
        color = OxmlElement("w:color"); color.set(qn("w:val"), "2743FF")
        properties.append(color)
        run.append(properties)
        value = OxmlElement("w:t"); value.text = match.group(1)
        run.append(value); link.append(run); paragraph._p.append(link)
        position = match.end()
    paragraph.add_run(text[position:].replace("`", ""))


def format_table(table, rows: list[list[str]]) -> None:
    table.autofit = False
    widths = [4.3, 12.7] if len(rows[0]) == 2 else [3.5, 5.5, 8.0]
    for column, width in zip(table.columns, widths):
        column.width = Cm(width)
    properties = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement("w:" + side)
        for name, value in (("val", "single"), ("sz", "4"), ("color", "D9D9D9")):
            border.set(qn("w:" + name), value)
        borders.append(border)
    properties.append(borders)
    for index, values in enumerate(rows):
        row = table.rows[index]
        if index == 0:
            repeat = OxmlElement("w:tblHeader")
            row._tr.get_or_add_trPr().append(repeat)
        no_split = OxmlElement("w:cantSplit")
        row._tr.get_or_add_trPr().append(no_split)
        for col, value in enumerate(values):
            cell = row.cells[col]
            cell.width = Cm(widths[col])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            props = cell._tc.get_or_add_tcPr()
            margins = OxmlElement("w:tcMar")
            for side in ("top", "bottom", "left", "right"):
                margin = OxmlElement("w:" + side)
                margin.set(qn("w:w"), "95")
                margin.set(qn("w:type"), "dxa")
                margins.append(margin)
            props.append(margins)
            shading = OxmlElement("w:shd")
            shading.set(qn("w:fill"), "E8EDF7" if index == 0 else "F5F7FB" if index % 2 == 0 else "FFFFFF")
            props.append(shading)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(1)
            paragraph.paragraph_format.line_spacing = 1.15
            inline(paragraph, value)
            for run in paragraph.runs:
                run.font.size = Pt(9.7)
                run.font.bold = index == 0


def add_page(doc, text: str, cover: bool = False) -> None:
    lines = text.strip().splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", value) for value in row):
                    rows.append(row)
                index += 1
            table = doc.add_table(rows=len(rows), cols=len(rows[0]))
            format_table(table, rows)
            doc.add_paragraph().paragraph_format.space_after = Pt(2)
            continue
        if line.startswith("# "):
            doc.add_paragraph(line[2:], "Title")
        elif line.startswith("## "):
            doc.add_paragraph(line[3:], "Heading 1")
        elif line.startswith("### "):
            doc.add_paragraph(line[4:], "Heading 2")
        elif line.startswith("!["):
            match = re.fullmatch(r"!\[(.*?)\]\((.*?)\)", line)
            paragraph = doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.keep_with_next = True
            paragraph.paragraph_format.space_after = Pt(3)
            paragraph.paragraph_format.line_spacing = 1.0
            width = 15.0 if match.group(2).endswith(("technical.home.jpg", "technical.insight.jpg")) else 16.8
            shape = paragraph.add_run().add_picture(str(ROOT / "docs" / match.group(2)), width=Cm(width))
            shape._inline.docPr.set("descr", match.group(1))
            caption = doc.add_paragraph(match.group(1), "Caption")
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif cover and line.startswith("基于微调"):
            doc.add_paragraph(line, "Subtitle")
        else:
            paragraph = doc.add_paragraph()
            inline(paragraph, line)
        index += 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", action="store_true", help="Use local registration for signed submission materials")
    args = parser.parse_args()
    registration = json.loads((ROOT / "output/submission-local/registration.json").read_text(encoding="utf-8")) if args.private else {}
    output = ROOT / "output/submission-local/澄明-作品介绍文档.docx" if args.private else OUTPUT
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(1.8)
    section.left_margin = section.right_margin = Cm(2)
    section.footer_distance = Cm(0.8)
    normal = doc.styles["Normal"]
    font_style(normal, 10.3)
    normal.paragraph_format.line_spacing = 1.25
    normal.paragraph_format.space_after = Pt(7)
    font_style(doc.styles["Title"], 30, True)
    doc.styles["Title"].paragraph_format.space_after = Pt(18)
    font_style(doc.styles["Subtitle"], 13)
    doc.styles["Subtitle"].paragraph_format.space_after = Pt(17)
    for name, size in (("Heading 1", 18), ("Heading 2", 12)):
        style = doc.styles[name]
        font_style(style, size, True)
        style.paragraph_format.space_before = Pt(8)
        style.paragraph_format.space_after = Pt(8)
        style.paragraph_format.keep_with_next = True
    font_style(doc.styles["Caption"], 9)
    doc.styles["Caption"].paragraph_format.space_after = Pt(9)
    core = doc.core_properties
    core.title = "澄明作品介绍文档"
    core.subject = "AI WEB网页开发挑战赛参赛作品介绍"
    core.author = "、".join(registration.get("members", [])) or "我周围的都是高手"
    core.last_modified_by = "我周围的都是高手"
    core.comments = ""
    content = re.sub(r"\A---.*?---\s*", "", SOURCE.read_text(encoding="utf-8"), count=1, flags=re.S)
    if registration:
        content = content.replace("| 团队名称 | 我周围的都是高手 |", "| 团队名称 | 我周围的都是高手 |\n| 团队编号及组别 | " + registration["team_id"] + "　B组 |\n| 团队成员 | " + "、".join(registration["members"]) + " |\n| 指导教师 | " + "、".join(registration["advisors"]) + " |")
    for index, text in enumerate(content.split("<!-- page -->")):
        first = len(doc.paragraphs)
        add_page(doc, text, cover=index == 0)
        if index:
            doc.paragraphs[first].paragraph_format.page_break_before = True
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = footer.add_run()
    field = OxmlElement("w:fldSimple"); field.set(qn("w:instr"), "PAGE")
    run._r.addnext(field)
    for root in (doc.styles.element, doc._element):
        for border in root.xpath(".//w:pBdr"):
            border.getparent().remove(border)
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)
    print(output)


if __name__ == "__main__":
    main()
