"""版式结构的判定规则：把一段 docx 段落归到某个"角色"。

用途有两个：
* 从样本 docx 生成结构 fixture（`dist/_build_fixture.py`）；
* 测试时判定生成文档的段落角色序列（`tests/test_format.py`）。

这里只关心**版式特征**（是不是标题、是不是标签行、是不是事件行…），
不关心具体文字，所以仓库里不必保存任何第三方正文。
"""

from __future__ import annotations

import re

from docx.oxml.ns import qn

HEADERS = {
    "推荐天象": "header:highlights",
    "主要天象": "header:events",
    "部分太阳系大天体动态": "header:planets",
    "本月月相日历": "header:moon",
    "本月部分望远镜目标推荐": "header:targets",
}
LABELS = ("罕见程度", "推荐程度", "观测难度", "观测时间", "观测提示")
PLANETS = ("太阳", "水星", "金星", "火星", "木星", "土星", "天王星", "海王星")
TARGET_PREFIX = ("太阳系天体", "窄带目标", "其他目标")

RE_NUMBERED = re.compile(r"^\d+\..+$")
RE_LABEL = re.compile(r"^(罕见程度|推荐程度|观测难度|观测时间|观测提示)\uff1a")
# 事件行：`1日␣␣14：22␣␣朔（新月）`，无时刻的写作 `9日␣␣长蛇座σ流星雨极大期（ZHR：7）`。
# 样本里日期写法不统一（少数在数字与「日」之间夹了不换行空格 U+00A0），
# 这里放宽到「数字 + 可选空白 + 日」，两种写法都认。
RE_EVENT = re.compile(r"^\d+[\s\u00a0]?日\s{2}(?:\d{2}\uff1a\d{2}\s{2})?.+$")
RE_PS = re.compile(r"^P\.S\.")
RE_CAPTION = re.compile(r"^（图源")


def has_image(p) -> bool:
    return bool(p._p.findall(".//" + qn("a:blip")))


def classify(text: str, idx: int, image: bool = False) -> str:
    """返回段落角色。idx 用于区分「首段是标题」「次段是导语」。"""
    if image:
        return "image"
    if not text.strip():
        return "blank"
    if idx == 0:
        return "title"
    if text in HEADERS:
        return HEADERS[text]
    if RE_PS.match(text):
        return "ps"
    if RE_CAPTION.match(text):
        return "caption"
    m = RE_LABEL.match(text)
    if m:
        return "label:" + m.group(1)
    if any(text.startswith(t) for t in TARGET_PREFIX):
        return "target_line"
    if RE_EVENT.match(text):
        return "event_line"
    # 行星行的天体名后面跟空白，但样本自身不统一：有的用「空格+不换行空格」，
    # 有的用两个半角空格。判据只认「名字后面跟空白」，不认空格个数。
    for name in PLANETS:
        if text.startswith(name):
            rest = text[len(name):]
            if rest[:1] in (" ", "\u00a0"):
                return "planet_line"
    if RE_NUMBERED.match(text):
        return "numbered_heading"
    if idx == 1:
        return "intro"
    return "body"


def role_sequence(doc) -> list[str]:
    """整篇文档的角色序列。"""
    return [classify(p.text, i, has_image(p)) for i, p in enumerate(doc.paragraphs)]
