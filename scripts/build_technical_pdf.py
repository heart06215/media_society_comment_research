"""Render the competition technical document from its Markdown source.

Authoring dependency: reportlab (not required by the application).
Usage: python scripts/build_technical_pdf.py [--font PATH] [--bold-font PATH]
"""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, Image, KeepInFrame, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "参赛技术文档.md"
OUTPUT = ROOT / "output" / "pdf" / "破妄-参赛技术文档.pdf"
BLUE = colors.HexColor("#2743FF")
INK = colors.HexColor("#14203A")
MUTED = colors.HexColor("#526078")
PALE = colors.HexColor("#F1F4FC")
LINE = colors.HexColor("#DCE2EE")
PAGE_W, PAGE_H = A4
MARGIN = 45
WIDTH = PAGE_W - 2 * MARGIN


def register_fonts(normal: str | None, bold: str | None) -> None:
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    ]
    font = Path(normal) if normal else next((p for p in candidates if p.exists()), None)
    if font is None or not font.exists():
        raise FileNotFoundError("Provide a Chinese TrueType font with --font PATH")
    bold_path = Path(bold) if bold else Path("C:/Windows/Fonts/msyhbd.ttc")
    if not bold_path.exists():
        bold_path = font
    pdfmetrics.registerFont(TTFont("BodyCN", str(font), subfontIndex=0))
    pdfmetrics.registerFont(TTFont("BoldCN", str(bold_path), subfontIndex=0))
    pdfmetrics.registerFontFamily("BodyCN", normal="BodyCN", bold="BoldCN")


def styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName="BodyCN", textColor=INK, wordWrap="CJK")
    return {
        "body": ParagraphStyle("body", fontSize=10.2, leading=17.7, spaceAfter=10, **base),
        "h2": ParagraphStyle("h2", fontSize=23, leading=32, spaceAfter=19, fontName="BoldCN", textColor=INK, wordWrap="CJK"),
        "h3": ParagraphStyle("h3", fontSize=13, leading=20, spaceBefore=10, spaceAfter=9, fontName="BoldCN", textColor=BLUE, wordWrap="CJK"),
        "cell": ParagraphStyle("cell", fontSize=8.8, leading=14.3, **base),
        "th": ParagraphStyle("th", fontSize=9.1, leading=15, fontName="BoldCN", textColor=colors.white, wordWrap="CJK"),
        "caption": ParagraphStyle("caption", fontSize=8.5, leading=13, spaceAfter=10, alignment=TA_CENTER, fontName="BodyCN", textColor=MUTED, wordWrap="CJK"),
        "code": ParagraphStyle("code", fontSize=8.2, leading=14, backColor=PALE, borderPadding=10, spaceBefore=4, spaceAfter=12, **base),
    }


def markup(text: str) -> str:
    value = html.escape(text)
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"`([^`]+)`", r'<font color="#2743FF">\1</font>', value)
    return value


class Diagram(Flowable):
    """A vector diagram with the same three paths as the frontend workflow."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.width = WIDTH
        self.height = 200 if kind == "architecture" else 170

    def draw(self) -> None:
        c = self.canv
        c.setStrokeColor(LINE)
        c.setLineWidth(1)
        if self.kind == "architecture":
            labels = [
                ("前端工作空间", "治理总览 / 证据库 / 标注 / 洞察"),
                ("Flask 数据与研究接口", "统计查询 / 人工操作 / 报告导出"),
                ("AI分类与工具问答", "人工示范检索 + 圈层知识 + 模型 API"),
                ("可追溯研究数据", "原文 / 模型记录 / 人工标签 / 评测记录"),
            ]
            for index, (title, subtitle) in enumerate(labels):
                y = self.height - 43 - index * 49
                c.setFillColor(PALE)
                c.roundRect(0, y, WIDTH, 40, 5, fill=1, stroke=1)
                c.setFont("BoldCN", 10)
                c.setFillColor(BLUE)
                c.drawString(14, y + 24, title)
                c.setFont("BodyCN", 8.5)
                c.setFillColor(MUTED)
                c.drawString(14, y + 10, subtitle)
                if index < 3:
                    c.line(WIDTH / 2, y - 1, WIDTH / 2, y - 8)
        else:
            c.setFillColor(BLUE)
            c.roundRect(125, 137, WIDTH - 250, 28, 4, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("BoldCN", 10)
            c.drawCentredString(WIDTH / 2, 146, "评论研究工作流")
            branches = [
                ("分类与标注", ["评论原文", "人工示范 + 圈层词条", "模型调用与结构校验", "标签 / 理由 / 词条"]),
                ("数据问答", ["理解研究问题", "选择统计与知识工具", "查询结果回传模型", "回答 + 工具记录"]),
                ("报告与研究", ["汇总分析记录", "保留原文与标签", "导出报告与数据集", "二次审查 / 立法研究"]),
            ]
            col = (WIDTH - 20) / 3
            c.line(WIDTH / 2, 137, WIDTH / 2, 126)
            c.line(col / 2, 126, WIDTH - col / 2, 126)
            for index, (title, items) in enumerate(branches):
                x = index * (col + 10)
                c.line(x + col / 2, 126, x + col / 2, 119)
                c.setFillColor(PALE)
                c.roundRect(x, 5, col, 114, 5, fill=1, stroke=1)
                c.setFont("BoldCN", 10)
                c.setFillColor(BLUE)
                c.drawCentredString(x + col / 2, 99, title)
                c.setFont("BodyCN", 8)
                c.setFillColor(INK)
                for row, label in enumerate(items):
                    c.drawCentredString(x + col / 2, 78 - row * 19, label)


def table(lines: list[str], sty: dict[str, ParagraphStyle]) -> Table:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    rows = [row for row in rows if not all(re.fullmatch(r":?-+:?", cell) for cell in row)]
    count = len(rows[0])
    ratios = {2: [0.27, 0.73], 3: [0.23, 0.39, 0.38], 4: [0.12, 0.60, 0.12, 0.16]}.get(count)
    if rows[0] == ["章节", "内容", "页码"]:
        ratios = [0.13, 0.72, 0.15]
    if rows[0][0] == "分类":
        ratios = [0.21, 0.64, 0.15]
    cells = [[Paragraph(markup(cell), sty["th" if i == 0 else "cell"]) for cell in row] for i, row in enumerate(rows)]
    result = Table(cells, colWidths=[WIDTH * ratio for ratio in ratios] if ratios else WIDTH / count, repeatRows=1, hAlign="LEFT", spaceBefore=5, spaceAfter=14)
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return result


def page_chrome(canvas, doc) -> None:
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, PAGE_H - 35, PAGE_W - MARGIN, PAGE_H - 35)
    canvas.setFont("BoldCN", 8)
    canvas.setFillColor(BLUE)
    canvas.drawString(MARGIN, PAGE_H - 25, "POWANG / 破妄")
    canvas.setFont("BodyCN", 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 25, "参赛技术文档 · 2026.11.16")
    canvas.line(MARGIN, 35, PAGE_W - MARGIN, 35)
    canvas.drawString(MARGIN, 21, "人工示范 · 圈层检索 · 可追溯研究")
    canvas.drawRightString(PAGE_W - MARGIN, 21, f"{doc.page:02d}")
    canvas.restoreState()


class Cover(Flowable):
    def __init__(self):
        super().__init__()
        self.width = WIDTH
        self.height = 695

    def draw(self) -> None:
        c = self.canv
        c.setFillColor(INK)
        c.rect(-MARGIN, -60, PAGE_W, PAGE_H, fill=1, stroke=0)
        c.setFillColor(BLUE)
        c.rect(-MARGIN, 500, PAGE_W, 195, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#ABFFF4"))
        c.setFont("Helvetica-Bold", 15)
        c.drawString(0, 651, "POWANG / TECHNICAL DOCUMENT")
        c.setFont("BoldCN", 63)
        c.setFillColor(colors.white)
        c.drawString(-2, 549, "破妄")
        c.setFont("BoldCN", 24)
        c.drawString(0, 443, "社区评论与网络治理研究平台")
        c.setFont("BodyCN", 12)
        c.setFillColor(colors.HexColor("#CCD6F1"))
        c.drawString(0, 409, "基于微调大模型的对互联网社区的评论情感分析软件")
        c.setFillColor(colors.HexColor("#ABFFF4"))
        c.setFont("BoldCN", 17)
        c.drawString(0, 333, "让圈层表达被理解，让网络治理有依据。")
        c.setFont("BodyCN", 11)
        c.setFillColor(colors.white)
        for i, line in enumerate([
            "以人工示范与圈层知识增强模型分类，",
            "连接统计洞察、评论原文与人工复核，",
            "导出可继续审查的分析报告和研究数据集。",
        ]):
            c.drawString(0, 286 - 23 * i, line)
        for i, (value, label) in enumerate([("7,199", "本地去重评论"), ("107", "人工锚定样本"), ("6", "表达分类")]):
            x = i * 172
            c.setFillColor(colors.HexColor("#ABFFF4"))
            c.setFont("Helvetica-Bold", 25)
            c.drawString(x, 161, value)
            c.setFillColor(colors.HexColor("#CCD6F1"))
            c.setFont("BodyCN", 9)
            c.drawString(x, 140, label)
        c.setStrokeColor(colors.HexColor("#455373"))
        c.line(0, 104, WIDTH, 104)
        c.setFont("BodyCN", 9)
        c.drawString(0, 79, "参赛技术文档 / V3.0 / 2026年11月16日")
        c.drawString(0, 58, "项目维护：heart06215")
        c.setFont("Helvetica", 8)
        c.drawString(0, 32, "github.com/heart06215/media_society_comment_research")


def parse_page(text: str, sty: dict[str, ParagraphStyle]) -> list:
    result = []
    lines = text.strip().splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("<!-- diagram:"):
            result += [Diagram(re.search(r"diagram: (\w+)", line).group(1)), Spacer(1, 10)]
        elif line.startswith("|"):
            block = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index])
                index += 1
            result.append(table(block, sty))
            continue
        elif line.startswith("```"):
            code = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                code.append(html.escape(lines[index]))
                index += 1
            result.append(Paragraph("<br/>".join(code), sty["code"]))
        elif line.startswith("!["):
            match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
            path = SOURCE.parent / match.group(2)
            if not path.exists():
                raise FileNotFoundError(f"Missing document illustration: {path}")
            img = Image(str(path))
            img.drawHeight = WIDTH * img.imageHeight / img.imageWidth
            img.drawWidth = WIDTH
            result.extend([img, Spacer(1, 5), Paragraph(match.group(1), sty["caption"])])
        elif line.startswith("### "):
            result.append(Paragraph(markup(line[4:]), sty["h3"]))
        elif line.startswith("## "):
            result.append(Paragraph(markup(line[3:]), sty["h2"]))
        else:
            result.append(Paragraph(markup(line), sty["body"]))
        index += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font")
    parser.add_argument("--bold-font")
    args = parser.parse_args()
    register_fonts(args.font, args.bold_font)
    content = SOURCE.read_text(encoding="utf-8")
    parts = re.split(r"<!-- page: \w+ -->", content)
    story = [Cover(), PageBreak()]
    sty = styles()
    for index, part in enumerate(parts[1:]):
        if index:
            story.append(PageBreak())
        story.append(KeepInFrame(WIDTH, PAGE_H - 108, parse_page(part, sty), mode="shrink", hAlign="LEFT", vAlign="TOP"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(OUTPUT), pagesize=A4, title="破妄 · 参赛技术文档", author="heart06215", subject="社区评论、人工标注增强与网络治理研究", leftMargin=MARGIN, rightMargin=MARGIN, topMargin=58, bottomMargin=49, allowSplitting=0)
    frame = Frame(MARGIN, 49, WIDTH, PAGE_H - 107, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id="technical", frames=frame, onPage=page_chrome))
    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    main()
