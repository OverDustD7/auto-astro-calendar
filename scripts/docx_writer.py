"""把结构化文档规格写成"天象预报"docx——严格复刻样本排版。

样本（天象预报 2024年12月.docx）实测规格
----------------------------------------
* 页面：A4 21×29.7 cm，左右边距 3.175 cm，上下 2.54 cm。
* Normal 样式：宋体（中文）/Calibri（西文），10.5 pt（w:sz=21），
  两端对齐（jc=both），kerning 2；无段前段后、单倍行距。
* **全文没有任何加粗、字号、颜色、居中**——标题与正文同字号同字体，
  靠空行和行文节奏分节。这是样本的真实排版，本模块照做。
* 字符：全角冒号 U+FF1A（"14：22"、"ZHR：7"）；度 U+00B0；
  角分 U+2019（右单引号，样本如此，不是 U+2032）；星 U+2B50；箭头 U+2192。
* "主要天象"每行形如 `1日␣␣14：22␣␣朔（新月）`（两个半角空格分隔），
  无时刻的条目形如 `9日␣␣长蛇座σ流星雨极大期（ZHR：7）`。
* 月相图：独立段落内联，宽度撑满版心（14.6 cm 左右），不居中对齐。

本模块只负责"排版"，不懂天文；输入是一份文档规格（dict）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

#: 版心宽度 = 21 - 3.175*2 = 14.65 cm；样本内联图正好撑满
TEXT_WIDTH_CM = 14.65
#: 图片比版心略窄一点，避免 Word 因舍入把图挤到下一行
IMAGE_WIDTH_CM = 14.6


def _set_normal(doc: Document) -> None:
    """把 Normal 样式调成样本的实测值。

    样本的 Normal 里**没有** spacing 元素，WPS 模板默认就是"单倍行距、段前段后
    0"；而 python-docx 自带模板的 Normal 是 Word 默认的 1.08 倍行距 + 8 磅段后，
    直接用会让整篇被撑开一倍（同样的内容从 2 页变 5 页）。所以这里必须显式写死
    spacing = 0/0/single，才是样本**渲染出来**的样子。
    """
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    rpr = st.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    # 显式写死字体，不依赖主题：中文宋体、西文 Calibri，与样本渲染一致
    rfonts.set(qn("w:ascii"), "Calibri")
    rfonts.set(qn("w:hAnsi"), "Calibri")
    rfonts.set(qn("w:eastAsia"), "宋体")
    rfonts.set(qn("w:cs"), "Calibri")
    ppr = st.element.get_or_add_pPr()
    ppr.append(ppr.makeelement(qn("w:widowControl"), {qn("w:val"): "0"}))
    ppr.append(ppr.makeelement(qn("w:spacing"), {
        qn("w:before"): "0", qn("w:after"): "0",
        qn("w:line"): "240", qn("w:lineRule"): "auto",
    }))
    ppr.append(ppr.makeelement(qn("w:jc"), {qn("w:val"): "both"}))
    # 字距调整 + 东亚语言
    rpr.append(rpr.makeelement(qn("w:kern"), {qn("w:val"): "2"}))
    rpr.append(rpr.makeelement(qn("w:szCs"), {qn("w:val"): "24"}))
    # 注意：**不要**关闭 autoSpaceDE/DN。样本里 "12.31 日"、"本月 8 日" 是带
    # 中西文自动间距的，关掉反而比样本更紧，属于过度修正。


def _set_page(doc: Document) -> None:
    for s in doc.sections:
        s.page_width = Cm(21.0)
        s.page_height = Cm(29.7)
        s.left_margin = Cm(3.175)
        s.right_margin = Cm(3.175)
        s.top_margin = Cm(2.54)
        s.bottom_margin = Cm(2.54)


@dataclass
class DocSpec:
    """一份完整月历的排版规格。所有字符串都当作"已排版好的正文行"。"""
    title: str
    intro: str
    highlights: list[dict] = field(default_factory=list)   # 推荐天象
    event_lines: list[str] = field(default_factory=list)    # 主要天象
    planet_lines: list[str] = field(default_factory=list)   # 大天体动态
    ps_line: str = ""                                       # P.S. 那句
    moon_image: Optional[Path] = None
    moon_caption: str = ""
    target_lines: list[str] = field(default_factory=list)   # 望远镜目标
    section_headers: dict = field(default_factory=lambda: {
        "highlights": "推荐天象",
        "events": "主要天象",
        "planets": "部分太阳系大天体动态",
        "moon": "本月月相日历",
        "targets": "本月部分望远镜目标推荐",
    })


def _add_decimal_numbering(doc: Document, num_id: int = 90) -> int:
    """加一个"1. 2. 3."式编号定义，返回 numId。

    样本最后三行（望远镜目标）用的是 Word 自动编号（numId=1，lvlText `%1.`），
    所以正文里没有手写的 "1."，渲染出来却有序号。为了让"本月部分望远镜目标
    推荐"一节与样本一致，这里照做：自己插一个 abstractNum + num。
    """
    numbering = doc.part.numbering_part.element
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    abstract = numbering.makeelement(qn("w:abstractNum"), {qn("w:abstractNumId"): "90"})
    abstract.append(abstract.makeelement(qn("w:multiLevelType"), {qn("w:val"): "singleLevel"}))
    lvl = abstract.makeelement(qn("w:lvl"), {qn("w:ilvl"): "0"})
    lvl.append(lvl.makeelement(qn("w:start"), {qn("w:val"): "1"}))
    lvl.append(lvl.makeelement(qn("w:numFmt"), {qn("w:val"): "decimal"}))
    # suff=space：序号后跟一个空格，渲染成 "1. 太阳系天体：…"。
    # 若留默认的 tab，序号会跳到下一个默认制表位（约 1.5 cm），中间空出一大截。
    lvl.append(lvl.makeelement(qn("w:suff"), {qn("w:val"): "space"}))
    lvl.append(lvl.makeelement(qn("w:lvlText"), {qn("w:val"): "%1."}))
    lvl.append(lvl.makeelement(qn("w:lvlJc"), {qn("w:val"): "left"}))
    ppr = lvl.makeelement(qn("w:pPr"), {})
    # 不设缩进：样本渲染出来是顶格 "1. 太阳系天体：…"
    ppr.append(ppr.makeelement(qn("w:ind"), {qn("w:left"): "0", qn("w:firstLine"): "0"}))
    lvl.append(ppr)
    abstract.append(lvl)

    # abstractNum 必须排在所有 num 之前
    nums = numbering.findall(qn("w:num"))
    if nums:
        nums[0].addprevious(abstract)
    else:
        numbering.append(abstract)

    num = numbering.makeelement(qn("w:num"), {qn("w:numId"): str(num_id)})
    num.append(num.makeelement(qn("w:abstractNumId"), {qn("w:val"): "90"}))
    numbering.append(num)
    return num_id


def _apply_numbering(p, num_id: int, ilvl: int = 0) -> None:
    ppr = p._p.get_or_add_pPr()
    numpr = ppr.makeelement(qn("w:numPr"), {})
    numpr.append(numpr.makeelement(qn("w:ilvl"), {qn("w:val"): str(ilvl)}))
    numpr.append(numpr.makeelement(qn("w:numId"), {qn("w:val"): str(num_id)}))
    ppr.append(numpr)


def _para(doc: Document, text: str = ""):
    """加一个空段落或纯文本段落（零缩进零间距，与样本一致）。返回该段落。"""
    return doc.add_paragraph(text)


def write_docx(spec: DocSpec, out_path: Path) -> Path:
    """按样本排版写出 docx。段落顺序与空行位置逐条对齐样本。"""
    doc = Document()
    _set_normal(doc)
    _set_page(doc)

    h = spec.section_headers
    # --- 抬头 ---
    _para(doc, spec.title)          # P00 标题（与正文同字号）
    _para(doc, spec.intro)          # P01 导语
    _para(doc)                      # P02 空行

    # --- 推荐天象 ---
    _para(doc, h["highlights"])
    for i, item in enumerate(spec.highlights, 1):
        _para(doc, f"{i}.{item['title']}")
        _para(doc, item["body"])
        _para(doc, f"罕见程度：{item['rarity']}")
        _para(doc, f"推荐程度：{'⭐' * item['recommend']}")
        _para(doc, f"观测难度：{item['difficulty']}")
        _para(doc, f"观测时间：{item['when']}")
        _para(doc, f"观测提示：{item['tip']}")
    _para(doc)

    # --- 主要天象 ---
    _para(doc, h["events"])
    for line in spec.event_lines:
        _para(doc, line)
    _para(doc)

    # --- 大天体动态 ---
    _para(doc, h["planets"])
    for line in spec.planet_lines:
        _para(doc, line)
    if spec.ps_line:
        _para(doc, spec.ps_line)
    _para(doc)

    # --- 月相日历 ---
    _para(doc, h["moon"])
    if spec.moon_image is not None:
        p = doc.add_paragraph()
        run = p.add_run()
        run.add_picture(str(spec.moon_image), width=Cm(IMAGE_WIDTH_CM))
        if spec.moon_caption:
            _para(doc, spec.moon_caption)
    _para(doc)

    # --- 望远镜目标（样本用自动编号，正文里不写 "1."） ---
    _para(doc, h["targets"])
    num_id = _add_decimal_numbering(doc)
    for line in spec.target_lines:
        _apply_numbering(_para(doc, line), num_id)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


def dump_spec_text(spec: DocSpec) -> list[str]:
    """把规格展开成逐段文本，供测试核对段落序列（图片段记为 '<IMAGE>'）。"""
    h = spec.section_headers
    out: list[str] = [spec.title, spec.intro, ""]
    out.append(h["highlights"])
    for i, item in enumerate(spec.highlights, 1):
        out += [
            f"{i}.{item['title']}", item["body"],
            f"罕见程度：{item['rarity']}",
            f"推荐程度：{'⭐' * item['recommend']}",
            f"观测难度：{item['difficulty']}",
            f"观测时间：{item['when']}",
            f"观测提示：{item['tip']}",
        ]
    out.append("")
    out.append(h["events"])
    out += spec.event_lines
    out.append("")
    out.append(h["planets"])
    out += spec.planet_lines
    if spec.ps_line:
        out.append(spec.ps_line)
    out.append("")
    out.append(h["moon"])
    if spec.moon_image is not None:
        out.append("<IMAGE>")
        if spec.moon_caption:
            out.append(spec.moon_caption)
    out.append("")
    out.append(h["targets"])
    out += spec.target_lines
    return out
