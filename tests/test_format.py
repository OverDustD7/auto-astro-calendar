"""格式回归测试：生成器产出的文档必须与样本的**版式结构**一致。

基准来自 `tests/fixtures/sample-reference.json`——从样本 docx 实测出的
结构（85 段的角色序列、页面几何、Normal 样式、图片宽度、分隔符）。基准里
**不含样本正文**：样本是他人撰写的社团会刊，整段复制其文字没有再分发依据，
而排版回归只需要结构。

做法：用自造的占位文案搭出一份 DocSpec，走 `docx_writer.write_docx`，
再用 `tests/structure.py` 判定产出文档的段落角色序列，与基准逐项比对；
另外核对页面设置、字体字号、行距段距、以及"全文无加粗/无字号覆盖/无居中"。

依赖说明：本测试不需要样本 docx，也不需要联网。
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Cm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import docx_writer  # noqa: E402
import structure  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "sample-reference.json"


# ---------------------------------------------------------------- 造占位内容

def synthetic_spec(fx: dict, image_path: Path) -> docx_writer.DocSpec:
    """按基准里的结构，用自造文案搭一份规格。

    文案全部是本测试自己的占位句，避免任何样本措辞。
    """
    roles = fx["roles"]
    n_highlights = roles.count("numbered_heading")
    n_events = roles.count("event_line")
    n_planets = roles.count("planet_line")
    n_targets = roles.count("target_line")

    highlights = []
    for i in range(n_highlights):
        highlights.append({
            "title": f"示例天象{i + 1}",
            "body": "这是用于版式回归的占位正文，不含任何样本措辞。",
            "rarity": "每年一次",
            "recommend": 3,
            "difficulty": "\u2b50\u2b50",
            "when": "1日20时后",
            "tip": "这是用于版式回归的占位观测提示。",
        })

    event_lines = []
    for i in range(n_events):
        day = i + 1
        # 前三条故意不带时刻，覆盖「无时刻事件行」这一支
        if i < 3:
            event_lines.append(f"{day}日  示例极大期（ZHR：10）")
        elif i == 3:
            # 带角距的事件行，覆盖度符号与角分符号（样本 2°15’ 的写法）
            event_lines.append(f"{day}日  12：00  示例合月，距离2\u00b015\u2019")
        else:
            event_lines.append(f"{day}日  12：00  示例天象{i + 1}")

    names = ["太阳", "水星", "金星", "火星", "木星", "土星", "天王星", "海王星"]
    planet_lines = [
        f"{names[i] if i < len(names) else '太阳'}  在示例座顺行。样例动态行。视星等0.0\u21920.1。"
        for i in range(n_planets)
    ]

    target_lines = ["太阳系天体：示例天体", "窄带目标：示例星云", "其他目标：示例星系"][:n_targets]

    return docx_writer.DocSpec(
        title="天象预报 2099年1月",
        intro="这是版式回归用的占位导语，只用来占住导语这一段的位置。",
        highlights=highlights,
        event_lines=event_lines,
        planet_lines=planet_lines,
        ps_line="P.S.：示例附注。",
        moon_image=image_path,
        moon_caption="（图源 示例来源）",
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
    spacing = st.element.pPr.find(qn("w:spacing"))
    return {
        "sz": st.font.size.pt,
        "jc": st.element.pPr.find(qn("w:jc")).get(qn("w:val")),
        "kern": rpr.find(qn("w:kern")).get(qn("w:val")),
        "eastAsia": rfonts.get(qn("w:eastAsia")),
        "ascii": rfonts.get(qn("w:ascii")),
        "before": spacing.get(qn("w:before")) if spacing is not None else None,
        "after": spacing.get(qn("w:after")) if spacing is not None else None,
        "line": spacing.get(qn("w:line")) if spacing is not None else None,
        "rule": spacing.get(qn("w:lineRule")) if spacing is not None else None,
    }


def image_widths(doc) -> list[float]:
    return [
        round(int(e.get("cx")) / 360000, 3)
        for p in doc.paragraphs
        for e in p._p.findall(".//" + qn("wp:extent"))
    ]


# ---------------------------------------------------------------- 主流程

def main() -> int:
    if not FIXTURE.exists():
        print(f"缺少结构基准：{FIXTURE}", file=sys.stderr)
        return 2
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fails: list[str] = []

    with tempfile.TemporaryDirectory(prefix="astro-fmt-") as tmp:
        tmp_dir = Path(tmp)
        # 造一张与样本同比例的占位图（14.6cm 宽，4:3 附近）
        from PIL import Image
        dummy = tmp_dir / "placeholder.png"
        Image.new("RGB", (1460, 1415), (12, 14, 20)).save(dummy)
        out_docx = tmp_dir / "rebuilt.docx"

        spec = synthetic_spec(fx, dummy)
        docx_writer.write_docx(spec, out_docx)
        built = Document(str(out_docx))

        # 1. 段落角色序列（含空行位置）
        actual_roles = structure.role_sequence(built)
        expected_roles = fx["roles"]
        if len(actual_roles) != len(expected_roles):
            fails.append(f"段落数不一致：基准 {len(expected_roles)} / 生成 {len(actual_roles)}")
        for i, (a, b) in enumerate(zip(expected_roles, actual_roles)):
            if a != b:
                fails.append(f"首个角色不一致 @{i}：基准 {a} / 生成 {b}")
                break
        if expected_roles != actual_roles and not any("角色不一致" in f for f in fails):
            diff = [(i, a, b) for i, (a, b) in enumerate(zip(expected_roles, actual_roles)) if a != b]
            fails.append(f"角色序列有 {len(diff)} 处不同，首个 {diff[0]}")

        # 2. 页面设置
        want_page = tuple(fx["page"][k] for k in
                          ("width_cm", "height_cm", "left_cm",
                           "right_cm", "top_cm", "bottom_cm"))
        got_page = page_geometry(built)
        if tuple(round(v, 3) for v in want_page) != tuple(round(v, 3) for v in got_page):
            fails.append(f"页面设置不一致：基准 {want_page} / 生成 {got_page}")

        # 3. Normal 样式（字号/对齐/kern/字体/行距段距）
        want = fx["normal"]
        got = normal_props(built)
        for key, gkey in (("size_pt", "sz"), ("jc", "jc"), ("kern", "kern")):
            if want[key] != got[gkey]:
                fails.append(f"Normal.{key} 不一致：基准 {want[key]} / 生成 {got[gkey]}")
        if got["eastAsia"] != want["eastAsia_font"]:
            fails.append(f"中文字体应为 {want['eastAsia_font']}，实际 {got['eastAsia']}")
        if got["ascii"] != want["ascii_font"]:
            fails.append(f"西文字体应为 {want['ascii_font']}，实际 {got['ascii']}")
        # 样本 Normal 没有 spacing 元素 = 单倍行距、段前段后 0；生成侧必须显式写死
        if (got["before"], got["after"], got["line"], got["rule"]) != ("0", "0", "240", "auto"):
            fails.append(f"行距段距未写死：{ {k: got[k] for k in ('before','after','line','rule')} }")

        # 4. 图片宽度
        widths = image_widths(built)
        if len(widths) != 1:
            fails.append(f"应有 1 张内联图，实际 {len(widths)}")
        elif fx["image_width_cm"] and abs(widths[0] - fx["image_width_cm"]) > 0.2:
            fails.append(f"图片宽度不一致：基准 {fx['image_width_cm']} / 生成 {widths[0]}")

        # 5. 全文不得出现加粗 / 字号覆盖 / 居中 / 段间距
        for i, p in enumerate(built.paragraphs):
            pf = p.paragraph_format
            if any(r.bold for r in p.runs):
                fails.append(f"第 {i} 段出现加粗：{p.text[:24]}")
            if any(r.font.size is not None for r in p.runs):
                fails.append(f"第 {i} 段出现字号覆盖：{p.text[:24]}")
            if p.alignment is not None and p.text.strip():
                fails.append(f"第 {i} 段出现对齐覆盖：{p.text[:24]}")
            if pf.space_before or pf.space_after:
                fails.append(f"第 {i} 段出现段间距：{p.text[:24]}")

        # 6. 分隔符实测：标签用全角冒号，难度用星，行星行动态用箭头
        sep = fx["separators"]
        texts = [p.text for p in built.paragraphs]
        if not any(t.startswith("罕见程度" + sep["colon"]) for t in texts):
            fails.append("标签行未使用全角冒号")
        if not any(sep["star"] in t for t in texts):
            fails.append("推荐程度/观测难度未使用星号字符")
        if not any(sep["degree"] in t for t in texts):
            fails.append("未出现度符号")
        if not any(sep["arrow"] in t for t in texts):
            fails.append("星等变化未使用箭头字符")

    print(f"结构基准：{len(fx['roles'])} 段，"
          f"{fx['roles'].count('event_line')} 事件行 / "
          f"{fx['roles'].count('numbered_heading')} 推荐块 / "
          f"{fx['roles'].count('planet_line')} 动态行")
    print(f"页面：{tuple(fx['page'][k] for k in ('width_cm','height_cm','left_cm','right_cm','top_cm','bottom_cm'))}")
    print(f"Normal：{fx['normal']}")
    if fails:
        print("\n格式不一致：")
        for f in fails:
            print("  -", f)
        return 1
    print("\n格式与样本结构一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
