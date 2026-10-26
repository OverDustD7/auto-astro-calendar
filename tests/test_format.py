"""格式回归测试：用样本自己的文字走一遍写入器，逐项比对排版属性。

两种跑法：
* **样本在**（`天象预报 2024年12月.docx` 在仓库根目录）→ 直接从 docx 解析出
  DocSpec 再重生成，逐段比对。
* **样本不在**（公开仓库里没有这个文件——它内嵌了 Star Walk 的截图）→ 读
  `tests/fixtures/sample-reference.json`，那是从样本**实测**出来的排版事实
  （85 段原文、页面几何、字体字号、图片宽度）。两种跑法比对同一组事实。

用环境变量可强制走第二种分支：
    ASTRO_SAMPLE=none python tests/test_format.py

这个测试**不依赖天文计算**，只验证"排版是否与样本一致"，因此改排版的
代码要让它继续通过。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Cm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import docx_writer  # noqa: E402

SAMPLE = Path(os.environ.get("ASTRO_SAMPLE") or (ROOT / "天象预报 2024年12月.docx"))
FIXTURE = ROOT / "tests" / "fixtures" / "sample-reference.json"


# ---------------------------------------------------------------- 解析样本

def parse_sample(path: Path) -> docx_writer.DocSpec:
    """把样本 docx 解析成 DocSpec（结构固定，按标记切段）。"""
    d = Document(str(path))
    paras = [p.text for p in d.paragraphs]

    def idx(text: str, start: int = 0) -> int:
        for i in range(start, len(paras)):
            if paras[i] == text:
                return i
        raise AssertionError(f"样本中找不到段落：{text!r}")

    i_high = idx("推荐天象")
    i_events = idx("主要天象")
    i_planets = idx("部分太阳系大天体动态")
    i_ps = idx("P.S.：如果有会占星的小伙伴，或许可以试着自己解读一下哦！")
    i_moon = idx("本月月相日历")
    i_targets = idx("本月部分望远镜目标推荐")

    # 推荐天象：标题形如 `N.名称`，其后固定 6 段（正文 + 5 个性状行）
    # 注意不能靠 "以日结尾" 之类的内容特征来切分——"2.木星冲日" 也以日结尾。
    highlights = []
    i = i_high + 1
    while i < i_events:
        txt = paras[i].strip()
        if not txt or not txt[:1].isdigit() or "." not in txt[:4]:
            i += 1
            continue
        title = txt.split(".", 1)[1]
        body = paras[i + 1]
        rarity = paras[i + 2].split("：", 1)[1]
        recommend = paras[i + 3].count("\u2b50")
        difficulty = paras[i + 4].split("：", 1)[1]
        when = paras[i + 5].split("：", 1)[1]
        tip = paras[i + 6].split("：", 1)[1]
        highlights.append({
            "title": title, "body": body, "rarity": rarity,
            "recommend": recommend, "difficulty": difficulty,
            "when": when, "tip": tip,
        })
        i += 7

    event_lines = [p for p in paras[i_events + 1:i_planets] if p.strip()]
    planet_lines = [p for p in paras[i_planets + 1:i_ps] if p.strip()]
    caption = ""
    if i_moon + 1 < len(paras):
        caption = paras[i_moon + 2] if paras[i_moon + 1] == "" else paras[i_moon + 1]
    target_lines = [p for p in paras[i_targets + 1:] if p.strip()]

    return docx_writer.DocSpec(
        title=paras[0], intro=paras[1], highlights=highlights,
        event_lines=event_lines, planet_lines=planet_lines,
        ps_line=paras[i_ps], moon_image=None, moon_caption=caption,
        target_lines=target_lines,
    )


# ---------------------------------------------------------------- 比对工具

def page_geometry(doc):
    s = doc.sections[0]
    return (round(s.page_width.cm, 3), round(s.page_height.cm, 3),
            round(s.left_margin.cm, 3), round(s.right_margin.cm, 3),
            round(s.top_margin.cm, 3), round(s.bottom_margin.cm, 3))


def normal_props(doc):
    st = doc.styles["Normal"]
    rpr = st.element.rPr
    rfonts = rpr.find(qn("w:rFonts"))
    return {
        "sz": st.font.size.pt,
        "jc": st.element.pPr.find(qn("w:jc")).get(qn("w:val")),
        "eastAsia": rfonts.get(qn("w:eastAsia")),
        "ascii": rfonts.get(qn("w:ascii")),
        "kern": rpr.find(qn("w:kern")).get(qn("w:val")),
    }


def sample_normal_props(doc):
    """样本的 Normal 用主题字体，这里换算成实际渲染字体后比对。"""
    st = doc.styles["Normal"]
    rpr = st.element.rPr
    rfonts = rpr.find(qn("w:rFonts"))
    return {
        "sz": st.font.size.pt,
        "jc": st.element.pPr.find(qn("w:jc")).get(qn("w:val")),
        "eastAsia": rfonts.get(qn("w:eastAsia")),  # None（走主题=宋体）
        "ascii": rfonts.get(qn("w:ascii")),        # None（走主题=Calibri）
        "kern": rpr.find(qn("w:kern")).get(qn("w:val")),
    }


def para_props(p):
    pf = p.paragraph_format
    return {
        "text": p.text,
        "align": str(p.alignment) if p.alignment is not None else None,
        "before": pf.space_before.pt if pf.space_before is not None else None,
        "after": pf.space_after.pt if pf.space_after is not None else None,
        "firstline": pf.first_line_indent,
        "left": pf.left_indent,
        "n_runs": len(p.runs),
        "bold": any(r.bold for r in p.runs),
        "size": [r.font.size.pt if r.font.size else None for r in p.runs],
    }


def image_widths(doc):
    out = []
    for p in doc.paragraphs:
        for ext in p._p.findall(".//" + qn("wp:extent")):
            out.append(round(int(ext.get("cx")) / 360000, 3))  # EMU → cm
    return out


# ---------------------------------------------------------------- 主流程

def main() -> int:
    fails: list[str] = []
    use_fixture = not SAMPLE.exists()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8")) if use_fixture else None
    if use_fixture:
        print(f"样本 docx 不在，改用实测基准：{FIXTURE.name}")
        sample = None
        spec = docx_writer.DocSpec(**fixture["spec"])
        expected_paragraphs = fixture["paragraphs"]
        expected_page = tuple(fixture["page"][k] for k in
                              ("width_cm", "height_cm", "left_cm",
                               "right_cm", "top_cm", "bottom_cm"))
        expected_image_w = fixture["image_width_cm"]
    else:
        sample = Document(str(SAMPLE))
        spec = parse_sample(SAMPLE)
        expected_paragraphs = None
        expected_page = None
        expected_image_w = None
    out = ROOT / "tests" / "_tmp_sample_rebuild.docx"

    # 造一张与样本同尺寸比例的占位图：这样图片段与图注都会走一遍，
    # 段落序列才能与样本一一对齐（样本图 5.75in×5.57in ≈ 14.6cm 宽）。
    from PIL import Image
    dummy = ROOT / "tests" / "_tmp_moon.png"
    Image.new("RGB", (1460, 1415), (12, 14, 20)).save(dummy)
    spec.moon_image = dummy
    docx_writer.write_docx(spec, out)
    built = Document(str(out))

    # 图片宽度：基准 vs 生成（EMU 换算成 cm）
    sw = [expected_image_w] if expected_image_w else image_widths(sample)
    bw = image_widths(built)
    if len(bw) != 1:
        fails.append(f"生成文档应有 1 张图，实际 {len(bw)}")
    elif sw and abs(sw[0] - bw[0]) > 0.2:
        fails.append(f"图片宽度不一致：样本 {sw[0]} cm / 生成 {bw[0]} cm")

    # 1. 页面
    g1 = expected_page if expected_page else page_geometry(sample)
    g2 = page_geometry(built)
    if tuple(round(v, 3) for v in g1) != tuple(round(v, 3) for v in g2):
        fails.append(f"页面设置不一致：基准 {g1} / 生成 {g2}")

    # 2. Normal 样式
    if use_fixture:
        # 基准里存的是可读的键名，转成与 normal_props() 一致的形状再比
        f = fixture["normal"]
        n1 = {"sz": f["size_pt"], "jc": f["jc"], "kern": f["kern"]}
    else:
        n1 = sample_normal_props(sample)
    n2 = normal_props(built)
    if n1["sz"] != n2["sz"]:
        fails.append(f"字号不一致：{n1['sz']} vs {n2['sz']}")
    if n1["jc"] != n2["jc"]:
        fails.append(f"对齐不一致：{n1['jc']} vs {n2['jc']}")
    if n1["kern"] != n2["kern"]:
        fails.append(f"kern 不一致：{n1['kern']} vs {n2['kern']}")
    # 字体：样本走主题（None=宋体/Calibri），生成写死同名字体
    if n2["eastAsia"] != "宋体":
        fails.append(f"中文字体应为宋体，实际 {n2['eastAsia']}")
    if n2["ascii"] != "Calibri":
        fails.append(f"西文字体应为 Calibri，实际 {n2['ascii']}")

    # 3. 段落文本序列（图片段落为空文本，这里两边都排除）
    base_paras = expected_paragraphs if use_fixture else [p.text for p in sample.paragraphs]
    sp = [t for t in base_paras if t.strip()]
    bp = [p.text for p in built.paragraphs if p.text.strip()]
    if sp != bp:
        only_s = [x for x in sp if x not in bp]
        only_b = [x for x in bp if x not in sp]
        fails.append(f"段落文本不一致：样本多 {only_s[:3]} / 生成多 {only_b[:3]}")
        for k, (a, b) in enumerate(zip(sp, bp)):
            if a != b:
                fails.append(f"  首个差异 @{k}: 样本 {a[:40]!r} vs 生成 {b[:40]!r}")
                break

    # 4. 空行位置：把全量段落（含空）的"是否为空"序列对齐比较
    se = [bool(t.strip()) for t in base_paras]
    be = [bool(p.text.strip()) for p in built.paragraphs]
    # 样本含 1 个图片段（文本为空但非"空行"），生成的树里没有图片
    if len(se) != len(be):
        fails.append(f"段落总数不一致：样本 {len(se)} / 生成 {len(be)}")

    # 5. 逐段属性：样本与生成都不应有加粗/字号覆盖/居中
    for i, p in enumerate(built.paragraphs):
        pr = para_props(p)
        if pr["bold"]:
            fails.append(f"第 {i} 段出现加粗：{pr['text'][:30]!r}")
        if any(s is not None for s in pr["size"]):
            fails.append(f"第 {i} 段出现字号覆盖：{pr['text'][:30]!r}")
        if pr["align"] is not None and pr["text"].strip():
            fails.append(f"第 {i} 段出现对齐覆盖：{pr['text'][:30]!r}")
        if pr["before"] or pr["after"]:
            fails.append(f"第 {i} 段出现段间距：{pr['text'][:30]!r}")

    print(f"样本段落数（含空）：{len(se)}，生成：{len(be)}")
    print(f"非空段落数：样本 {len(sp)}，生成 {len(bp)}")
    print(f"页面：{g1}")
    print(f"样式：{n2}")
    if fails:
        print("\n格式不一致：")
        for f in fails:
            print("  -", f)
        return 1
    print("\n格式与样本一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
