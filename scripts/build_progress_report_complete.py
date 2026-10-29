from __future__ import annotations

import hashlib
import shutil
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(r"D:\桌面\workspace\宏观2")
REFERENCE = Path(r"D:\桌面\宏观\FinGoose_宏观事件研究数据阶段成果汇报_2026-08-12.docx")
OUTPUT = ROOT / "FinGoose_宏观事件研究数据阶段成果汇报_完善版_2026-08-12.docx"
REFERENCE_SHA256 = "2c5f0599ee32d5314f2bdf60e80b8e1ebe019a070b4d50572c3bb1396deb1274"

NAVY = "16324F"
BLUE = "2E74B5"
TEXT = "1F2937"
MUTED = "5B6573"
LINE = "D1D5DB"
LIGHT_BLUE = "EAF2F8"
LIGHT_GREEN = "E8F3EC"
LIGHT_GOLD = "FFF4D6"
GREEN = "1F6B45"
GOLD = "7A5A00"


def set_font(run, size=10.5, color=TEXT, bold=False, italic=False):
    run.font.name = "Microsoft YaHei"
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{attr}"), "Microsoft YaHei")
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    run.bold = bold
    run.italic = italic


def paragraph_format(paragraph, before=0, after=4, line=1.08):
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = line


def reset_body(doc):
    body = doc._element.body
    sect_pr = body.sectPr
    for child in list(body):
        if child is not sect_pr:
            body.remove(child)


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        tc_pr.append(shading)
    shading.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=86, start=120, bottom=86, end=120):
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = tc_pr.first_child_found_in("w:tcMar")
    if mar is None:
        mar = OxmlElement("w:tcMar")
        tc_pr.append(mar)
    for edge, width in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = mar.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            mar.append(node)
        node.set(qn("w:w"), str(width))
        node.set(qn("w:type"), "dxa")


def set_borders(table, color=LINE, size="6"):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), size)
        node.set(qn("w:color"), color)


def set_table_geometry(table, widths):
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    tbl_w = table._tbl.tblPr.first_child_found_in("w:tblW")
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        table._tbl.tblPr.insert(0, tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = table._tbl.tblPr.first_child_found_in("w:tblInd")
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        table._tbl.tblPr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), "0")
    tbl_ind.set(qn("w:type"), "dxa")

    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        for cell, width in zip(row.cells, widths):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(width))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def set_keep(paragraph, next_paragraph=False):
    ppr = paragraph._p.get_or_add_pPr()
    node_name = "w:keepNext" if next_paragraph else "w:keepLines"
    if ppr.find(qn(node_name)) is None:
        ppr.append(OxmlElement(node_name))


def add_title(doc, title, subtitle):
    p = doc.add_paragraph(style="Title")
    paragraph_format(p, after=1, line=1.0)
    set_font(p.add_run(title), size=24, color=NAVY)
    p = doc.add_paragraph(style="Subtitle")
    paragraph_format(p, after=8, line=1.05)
    set_font(p.add_run(subtitle), size=10.5, color=MUTED)


def add_heading(doc, text):
    p = doc.add_paragraph(style="Heading 1")
    paragraph_format(p, before=10, after=4, line=1.0)
    set_font(p.add_run(text), size=15, color=BLUE, bold=True)
    set_keep(p, next_paragraph=True)
    return p


def add_bullet(doc, text, level=0):
    p = doc.add_paragraph(style="List Bullet")
    paragraph_format(p, after=2, line=1.04)
    p.paragraph_format.left_indent = Inches(0.26 + 0.18 * level)
    p.paragraph_format.first_line_indent = Inches(-0.16)
    set_font(p.add_run(text), size=9.8)
    set_keep(p)
    return p


def add_callout(doc, label, text, fill=LIGHT_BLUE):
    table = doc.add_table(rows=1, cols=1)
    set_table_geometry(table, [9360])
    set_borders(table, color="C7D9EB", size="4")
    cell = table.cell(0, 0)
    set_cell_shading(cell, fill)
    set_cell_margins(cell, top=110, start=150, bottom=110, end=150)
    p = cell.paragraphs[0]
    paragraph_format(p, after=0, line=1.08)
    set_font(p.add_run(label + "  "), size=10.2, color=NAVY, bold=True)
    set_font(p.add_run(text), size=10.2, color=TEXT)
    return table


def add_table(doc, headers, rows, widths, status_column=None):
    table = doc.add_table(rows=1, cols=len(headers), style="Table Grid")
    set_table_geometry(table, widths)
    set_borders(table)
    set_repeat_table_header(table.rows[0])
    for cell, text in zip(table.rows[0].cells, headers):
        set_cell_shading(cell, LIGHT_BLUE)
        p = cell.paragraphs[0]
        paragraph_format(p, after=0, line=1.0)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_font(p.add_run(text), size=9.1, color=NAVY, bold=True)
    for record in rows:
        cells = table.add_row().cells
        for col_idx, (cell, value) in enumerate(zip(cells, record)):
            p = cell.paragraphs[0]
            paragraph_format(p, after=0, line=1.03)
            if col_idx in (1,) and len(str(value)) <= 12:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            color = TEXT
            bold = False
            if status_column == col_idx:
                if value in ("完成", "通过", "正式版完成"):
                    color, bold = GREEN, True
                    set_cell_shading(cell, LIGHT_GREEN)
                elif value in ("待发布校验", "进行中"):
                    color, bold = GOLD, True
                    set_cell_shading(cell, LIGHT_GOLD)
            set_font(p.add_run(str(value)), size=8.85, color=color, bold=bold)
    return table


def add_small_note(doc, text):
    p = doc.add_paragraph()
    paragraph_format(p, before=2, after=2, line=1.0)
    set_font(p.add_run(text), size=8.6, color=MUTED, italic=True)
    return p


def main():
    if hashlib.sha256(REFERENCE.read_bytes()).hexdigest() != REFERENCE_SHA256:
        raise RuntimeError("参考文件哈希不一致，停止生成。")
    shutil.copy2(REFERENCE, OUTPUT)
    doc = Document(OUTPUT)
    reset_body(doc)

    section = doc.sections[0]
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)

    header = section.header.paragraphs[0]
    header.clear()
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    paragraph_format(header, after=0, line=1.0)
    set_font(header.add_run("FinGoose 财经事件研究数据 | 阶段成果汇报"), size=8, color="6B7280")
    footer = section.footer.paragraphs[0]
    footer.clear()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph_format(footer, after=0, line=1.0)
    set_font(footer.add_run("内部阶段材料 | 截至 2026-08-12"), size=8, color="6B7280")

    add_title(doc, "财经视频事件推理链数据集\n阶段成果汇报", "汇报口径：基于已归档视频/图文材料与外部证据的正式研究数据及 QA 访问接口；暂不包含 SFT 训练内容")
    add_callout(
        doc,
        "核心结论",
        "项目已完成 10 个独立事件案例的 V3 正式研究数据建设，形成可审计的事实传导链、作者推理链和外部核验链，并提供 90 条规范 QA 与 50 条连续追问路径。QA 不作为孤立题库，而是用户访问案例事实图谱、理解推理过程和核验证据边界的接口。",
    )

    add_heading(doc, "一、完成成果与当前状态")
    add_table(
        doc,
        ["成果项", "规模", "状态", "管理含义"],
        [
            ("正式事件案例包", "10 个", "正式版完成", "每案覆盖起点、机制、转折、结果与必要核验"),
            ("可审计推理链", "30 条", "完成", "每案三链：事实传导、作者推理、外部核验"),
            ("规范 QA", "90 条", "完成", "每案 9 条，均绑定局部完整链与证据定位"),
            ("用户追问图 / 对话路径", "10 / 50", "完成", "支持 2-6 轮连续追问，覆盖真实使用入口"),
            ("用户需求信号", "90 条", "完成", "问题按真实用户意图聚类，并映射到可审计事实链"),
        ],
        [1900, 1260, 1700, 4500],
        status_column=2,
    )
    add_small_note(doc, "覆盖案例包含徐翔、原野实业、小米、万科、娃哈哈及已恢复的粮食、日本、保健品等独立事件；同一事件不跨评测切分。")

    add_heading(doc, "二、已经形成的研究数据链路")
    add_callout(
        doc,
        "统一数据结构",
        "事件材料与外部来源 → 可定位事实主张 → 关系与推理步骤 → 支持状态/证据链接 → 用户问题、回答与引用。所有步骤保留输入引用、输出引用和支持状态，不保存模型自由式思维过程。",
        fill="F3F7FB",
    )
    for item in [
        "事实传导链：事实发生 → 作用机制 → 后续事件 → 最终结果；用于说明事件如何演进，严格保留时序与主体边界。",
        "作者推理链：作者前提 → 中间判断 → 隐含假设 → 作者结论；用于忠实复现作者如何得出结论，不等同于现实因果成立。",
        "外部核验链：外部证据 → 支持范围 → 证据缺口/冲突 → 现实可成立结论；用于把作者观点与可证实事实分开。",
        "QA 访问接口：问题按 understand、explain、verify、impact、evaluate、compare 六类用户意图组织；每个问题同时有连续对话问法与可独立使用的标准问法。",
    ]:
        add_bullet(doc, item)

    add_heading(doc, "三、质量控制与证据边界")
    add_table(
        doc,
        ["检查项", "结果", "说明"],
        [
            ("正式 QA 可回答性", "90 / 90 answerable", "回答同时说明可支持范围与不确定性，避免将观点直接写成事实"),
            ("链条完整性", "90 / 90 complete", "目标结论可回溯至必要中间步骤和引用"),
            ("正式 CLI 校验", "valid: true", "ID 引用、链路连续性、枚举与发布配置通过校验"),
            ("可重复构建", "哈希一致", "V3 正式文件固定种子重建保持字节一致；V2 原始策展数据未被覆盖"),
            ("外部核验边界", "保留未知/未支持", "没有直接反证时不标 contradicted；保健品赞助等命题仍保持 unknown"),
        ],
        [2300, 2200, 4860],
        status_column=None,
    )
    add_small_note(doc, "已完成的“可回答”表示能对证据边界作出完整答复，不表示问题中涉及的全部现实因果均已被外部证实。")

    add_heading(doc, "四、QA 问答设计的核心思考")
    for item in [
        "问题不是从固定题型或数量配额反推，而是从用户第一次了解、原因追问、真实性质疑、现实影响和评价比较等需求出发，再由事实链约束答案。",
        "每个重要问题内部同时绑定事实传导链、作者推理链和外部核验链；单轮回答包含完整局部链，整条对话路径累计覆盖事件起点、机制、转折、结果、影响和必要核验。",
        "连续对话问题与可独立使用的标准问题共用同一 QA ID、答案、推理链和证据，既支持 2-6 轮自然追问，也支持单题检索、评测和复核。",
        "用户可见答案由直接回答、解释链、外部核验、不确定性说明和来源引用构成；数据内部保留 source/context/evidence-link 定位，便于逐步审计。",
        "“可回答”表示可以完整说明证据支持到哪里；作者推理忠实不代表现实因果成立。高需求但证据不足的问题必须部分回答或拒答，没有直接反证时不得标为 contradicted。",
        "人物、日期、金额等基础抽取只作为理解入口，不大量单独制题；重点保留机制解释、多跳链重建、证据边界、替代解释、前提充分性和结论强度等高价值问题。",
    ]:
        add_bullet(doc, item)
    add_callout(
        doc,
        "建议对外汇报口径",
        "财经视频事件推理链的正式研究数据与 QA 访问层已完成，已形成 10 个事件案例、三类可审计链、90 条高价值 QA 和 50 条连续追问路径。QA 的价值不在题目数量，而在于能从真实用户问题进入事实图谱，重建推理链，并明确现实证据支持到哪里。",
        fill="EAF2F8",
    )

    add_heading(doc, "五、阶段交付物")
    add_table(
        doc,
        ["用途", "主要内容", "当前状态"],
        [
            ("V3 正式案例数据", "案例规格、来源、上下文、证据链接、审核记录与三类推理链", "完成"),
            ("V3 QA 访问层", "90 条问题与标准答案、10 个追问图、50 条连续对话路径", "完成"),
            ("质量与复现材料", "发布配置、校验结果、数据卡与固定种子构建规则", "完成"),
        ],
        [2500, 4680, 2180],
        status_column=2,
    )
    add_small_note(doc, "正式展示目录按用途分离：`data/cases/v3` 保存事件案例与证据，`data/qa/v3` 保存用户问题、答案和追问路径；`data/curation/v3` 是构建与审核底稿，不作为主要展示入口。")

    doc.core_properties.title = "财经视频事件推理链数据集阶段成果汇报"
    doc.core_properties.subject = "截至 2026-08-12 的阶段成果与训练数据转换进展"
    doc.core_properties.author = "FinGoose"
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
