"""内容体检：生成的文案不能有空字段、不能重复、不能跑题。

这个测试拦的是"排版对、数字对，但写出来是废话"这类问题：
* 推荐天象每一条都必须有正文、观测时间、观测提示（曾经在平淡月份里
  把"满月/下弦/朔"凑进推荐栏，产出一堆空段落）。
* 主要天象不能有空行、不能有完全重复的行、日期必须落在本月。
* 大天体动态必须 8 行、每行以句号收尾、都以天体名开头。
* 望远镜目标必须是 1~3 行（Word 自动编号），不能空。

覆盖的月份特意挑了三种极端：事情很多的、事情很少的（2026-02）、
有日月食但本地看不见的（2025-03）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import docx_writer  # noqa: E402
import report  # noqa: E402

MONTHS = [(2024, 12), (2026, 2), (2025, 3), (2026, 11), (2027, 7)]
PLANET_PREFIX = ("太阳", "水星", "金星", "火星", "木星", "土星", "天王星", "海王星")


def check_month(year: int, month: int) -> list[str]:
    fails: list[str] = []
    spec = report.build_spec(year, month)
    tag = f"{year}-{month:02d}"

    # --- 推荐天象 ---
    if not spec.highlights:
        fails.append(f"{tag}: 推荐天象为空")
    if len(spec.highlights) > 5:
        fails.append(f"{tag}: 推荐天象 {len(spec.highlights)} 条，超过 5 条")
    titles = set()
    for h in spec.highlights:
        for k in ("title", "body", "rarity", "when", "tip"):
            if not str(h.get(k, "")).strip():
                fails.append(f"{tag}: 推荐「{h.get('title','?')}」的 {k} 为空")
        if h["title"] in titles:
            fails.append(f"{tag}: 推荐标题重复 {h['title']}")
        titles.add(h["title"])
        if not 1 <= h["recommend"] <= 5:
            fails.append(f"{tag}: {h['title']} 推荐程度 {h['recommend']} 越界")
        if "⭐" not in str(h["difficulty"]):
            fails.append(f"{tag}: {h['title']} 观测难度没有星")

    # --- 主要天象 ---
    if not spec.event_lines:
        fails.append(f"{tag}: 主要天象为空")
    seen: set[str] = set()
    for line in spec.event_lines:
        if not line.strip():
            fails.append(f"{tag}: 主要天象有空行")
            continue
        if line in seen:
            fails.append(f"{tag}: 主要天象重复 —— {line}")
        seen.add(line)
        if not line[0].isdigit():
            fails.append(f"{tag}: 主要天象行不以日开头 —— {line[:20]}")
        else:
            day = int(line.split("日")[0])
            if not 1 <= day <= 31:
                fails.append(f"{tag}: 日期离谱 {line[:20]}")

    # --- 大天体动态 ---
    if len(spec.planet_lines) != 8:
        fails.append(f"{tag}: 动态应 8 行，实际 {len(spec.planet_lines)}")
    for i, line in enumerate(spec.planet_lines):
        if not line.startswith(PLANET_PREFIX[i]):
            fails.append(f"{tag}: 动态第 {i+1} 行开头不是 {PLANET_PREFIX[i]}：{line[:12]}")
        if not line.rstrip().endswith("。"):
            fails.append(f"{tag}: 动态第 {i+1} 行没有句号：{line[-12:]}")
        if "  " not in line:
            fails.append(f"{tag}: 动态第 {i+1} 行缺双空格分隔：{line[:12]}")

    # --- 望远镜目标 ---
    if not (1 <= len(spec.target_lines) <= 3):
        fails.append(f"{tag}: 望远镜目标应 1~3 行，实际 {len(spec.target_lines)}")

    # --- 整篇文本不能出现模板占位符 / 空括号 ---
    text = "\n".join(docx_writer.dump_spec_text(spec))
    for bad in ("{}", "None", "nan", "（）"):
        if bad in text:
            fails.append(f"{tag}: 正文出现 {bad!r}")
    return fails


def main() -> int:
    all_fails: list[str] = []
    for year, month in MONTHS:
        fails = check_month(year, month)
        print(f"{year}-{month:02d}: {'OK' if not fails else f'{len(fails)} 处问题'}")
        all_fails += fails
    if all_fails:
        print("\n问题：")
        for f in all_fails:
            print("  -", f)
        return 1
    print("\n内容体检通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
