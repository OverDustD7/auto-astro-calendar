"""命令行入口：生成某年某月的《天象预报》。

用法
----
    python scripts/make_calendar.py --year 2026 --month 11
    python scripts/make_calendar.py --year 2024 --month 12 --moon-image assets/moon-2024-12.png

产出（默认写到 `out/`）：
* `天象预报 YYYY年M月.docx`——正文，排版严格对齐样本；
* `天象预报 YYYY年M月.json`——本次生成所用的全部结构化事实，便于复核；
* `天象预报 YYYY年M月.md`——纯文本版，便于 diff 与快速校对（不进 Word）。

月相日历图来源
--------------
站点上并没有"一张现成的月相日历图"可下载——日历是 CSS sprite 拼出来的，
所以走浏览器截图 + `crop_calendar.py` 裁剪，见 SKILL.md 的步骤。本脚本只吃
一个已经裁好的 PNG 路径。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import astronomy as A  # noqa: E402

import astro_core as C  # noqa: E402
import docx_writer  # noqa: E402
import report  # noqa: E402


def dump_json(year: int, month: int, city: str,
              observer: A.Observer) -> dict:
    """把本次生成用到的原始事实落盘，便于任何数字都能被复核。"""
    start, end = C.month_range(year, month)
    events = report.collect_events(year, month, observer)
    data = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "year": year,
        "month": month,
        "city": city,
        "observer": {"lat": observer.latitude, "lon": observer.longitude},
        "engine": "astronomy-engine (Meeus)",
        "conventions": {
            "quarter": "日月视黄经差 = 0/90/180/270",
            "solar_term": "太阳视黄经达 15° 整数倍（与紫金山天文台口径一致）",
            "elongation": "最大视黄经差（中文历书传统；与最大角距可差数小时）",
            "opposition_conjunction": "SearchRelativeLongitude(body, 0/180)",
            "station": "视黄经变化率过零，1 小时步长 + 二分细化",
            "moon_planet": "地心最小角距；小于月球视半径记为月掩",
            "observable": "天体在地平线上且太阳低于 -6°",
        },
        "events": [
            {
                "kind": e.kind,
                "bjtime": C.bjt(e.time).isoformat(sep=" ", timespec="minutes")
                if e.time else None,
                "day": e.data.get("day"),
                "label": e.label,
                **{k: v for k, v in e.data.items() if k != "shower"},
                "shower": e.data.get("shower", {}).get("code")
                if e.data.get("shower") else None,
            }
            for e in sorted(events, key=report.event_sort_key)
        ],
        "planets": [
            {
                "name": name,
                "constellation": C.constellation_path(getattr(A.Body, name), start, end),
                "magnitude": C.magnitude_series(getattr(A.Body, name), start, end),
                "visibility": C.visibility_state(getattr(A.Body, name),
                                                start.AddDays(14), observer),
            }
            for name in ("Sun", "Mercury", "Venus", "Mars", "Jupiter",
                         "Saturn", "Uranus", "Neptune")
        ],
    }
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成某年某月的天象预报 docx")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--month", type=int, required=True)
    ap.add_argument("--city", default="北京")
    ap.add_argument("--venue-label", default="校内",
                    help="观测难度里校园一档的叫法（默认 校内，指清华校园）")
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lon", type=float, default=None)
    ap.add_argument("--moon-image", type=Path, default=None,
                    help="已裁剪好的月相日历 PNG；缺省则留空并在文档里注明")
    ap.add_argument("--highlights", type=int, default=5,
                    help="推荐天象条数（样本为 5）")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "out")
    ap.add_argument("--stem", default=None, help="输出文件名主干（不含扩展名）")
    args = ap.parse_args(argv)

    if not 1 <= args.month <= 12:
        print("--month 必须在 1..12", file=sys.stderr)
        return 2

    lat = C.BEIJING[0] if args.lat is None else args.lat
    lon = C.BEIJING[1] if args.lon is None else args.lon
    observer = A.Observer(lat, lon, 50.0)

    moon_image = args.moon_image
    caption = ""
    if moon_image is None:
        caption = "（本月月相日历图未提供；可参考下方星座与相位时间）"
    if moon_image is not None and not Path(moon_image).exists():
        print(f"月相图不存在：{moon_image}", file=sys.stderr)
        return 2

    spec = report.build_spec(
        args.year, args.month, city=args.city, lat=lat, lon=lon,
        n_highlights=args.highlights, venue=args.venue_label,
        moon_image=Path(moon_image) if moon_image else None,
        moon_caption=caption,
    )

    stem = args.stem or f"天象预报 {args.year}年{args.month}月"
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = docx_writer.write_docx(spec, out_dir / f"{stem}.docx")

    # 结构化事实 + 纯文本版，便于复核
    (out_dir / f"{stem}.json").write_text(
        json.dumps(dump_json(args.year, args.month, args.city, observer),
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    (out_dir / f"{stem}.md").write_text(
        "\n".join(docx_writer.dump_spec_text(spec)), encoding="utf-8")

    print(f"docx: {docx_path}")
    print(f"json: {out_dir / f'{stem}.json'}")
    print(f"md  : {out_dir / f'{stem}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
