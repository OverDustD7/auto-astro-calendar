"""用真实月面照片渲染"本月月相日历"（中文网格）。

素材来源
--------
月面照片取自 Calendar-12.com 的月相雪碧图 `phases.jpg`：120×12000 像素，
纵向 100 张 120×120 的月球照片，按相位从朔(0°)到下一次朔(360°)均匀排列，
每张约 3.6°。原站注明照片来自 NASA Goddard 可视化工作室，属公有领域。

为什么要自己拼而不是截整页
--------------------------
截整页会带进网页导航箭头、相邻月份的链接、英文相位说明，而且是竖长条；
按天取图自己排版，才能得到与样本一致的"中文月份 + 一格格月相 + 日期数字"
的印刷版式。

相位→图片的对应
----------------
每天取当地 20:00 的相位角（观测者真正抬头看的时段），
`index = round(phase_angle / 3.6) % 100`。因为该雪碧图本身就是按相位线性
排列的，所以这个映射是精确的，不需要按亮度反查。

用法
----
    python scripts/moon_grid.py --year 2024 --month 12 --out assets/moon-2024-12.png
    # 雪碧图默认缓存在 assets/phases.jpg，缺失时自动下载
"""

from __future__ import annotations

import argparse
import calendar as _cal
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import astronomy as A  # noqa: E402

import astro_core as C  # noqa: E402

SPRITE_URL = "https://www.calendar-12.com/media/images/phases.jpg"
SPRITE_TILES = 100
TILE_PX = 120

#: 版式参数。**像素尺寸要按最终印刷尺寸反推**：这张图在 Word 里按 14.6 cm
#: 宽插入，所以 1 pt ≈ 0.0353 cm；按 232 px 一格画时，插入后星期名只有约
#: 3.7 pt、相位名约 3 pt，打印出来基本读不清。改成下面这套尺度后，
#: 整图约 3300 px 宽 ≈ 226 px/cm，字号才落到括号里标的实际磅值。
SS = 2                       # 超采样倍数
CELL_W = 460
CELL_H = 430
HEADER_H = 72                # 星期栏高度
TITLE_H = 130                # 标题栏高度
PAD = 40                     # 外边距

#: 期望的字号（pt），实际像素 = pt / 72 * 2.54 * PX_PER_CM
PX_PER_CM = 226
F_TITLE_PT = 12.0
F_WEEKDAY_PT = 8.0
F_DAY_PT = 14.0
F_EVENT_PT = 7.0


def _px(pt: float) -> int:
    """磅值 → 本图的像素值。"""
    return max(8, round(pt / 72.0 * 2.54 * PX_PER_CM))


BG = (4, 6, 12)              # 近纯黑：与雪碧图的方形黑底无缝
CELL_BG = (6, 9, 16)
GRID_LINE = (30, 42, 66)
TITLE_COLOR = (232, 236, 245)
WEEKDAY_COLOR = (150, 162, 186)
DAYNUM_COLOR = (247, 249, 252)
ACCENT = (108, 156, 232)     # 相位事件用的强调色

WEEKDAYS_MON_FIRST = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

PHASE_LABEL = {0: "朔", 1: "上弦", 2: "望", 3: "下弦"}


# ---------------------------------------------------------------- 字体

def _find_font(bold: bool = False) -> Path:
    """找一个能渲染中文的字体。"""
    cands = (["msyhbd.ttc", "msyh.ttc", "simhei.ttf", "Deng.ttf", "simsun.ttc"]
             if bold else
             ["msyh.ttc", "simhei.ttf", "Deng.ttf", "simsun.ttc", "msyhbd.ttc"])
    for name in cands:
        p = Path(r"C:\Windows\Fonts") / name
        if p.exists():
            return p
    raise FileNotFoundError("找不到中文字体（试过 微软雅黑/黑体/等线/宋体）")


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_find_font(bold)), size)


# ---------------------------------------------------------------- 素材

def ensure_sprite(path: Path) -> Image.Image:
    """加载月相雪碧图；不存在则下载一次并缓存。"""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            SPRITE_URL, headers={"User-Agent": "Mozilla/5.0",
                                 "Referer": "https://www.calendar-12.com/"})
        with urllib.request.urlopen(req, timeout=30) as r:
            path.write_bytes(r.read())
    im = Image.open(path).convert("RGB")
    if im.height != SPRITE_TILES * TILE_PX:
        raise ValueError(f"雪碧图尺寸异常：{im.size}（期望宽 {TILE_PX}、高 {SPRITE_TILES*TILE_PX}）")
    return im


def tile_for_phase(sprite: Image.Image, phase_angle: float) -> Image.Image:
    """相位角 → 对应的小图。"""
    idx = int(round((phase_angle % 360.0) / 360.0 * SPRITE_TILES)) % SPRITE_TILES
    top = idx * TILE_PX
    return sprite.crop((0, top, TILE_PX, top + TILE_PX))


# ---------------------------------------------------------------- 月内数据

def month_cells(year: int, month: int) -> list[dict]:
    """逐日：日期、相位角、照明比例、当日相位事件名（若有）。"""
    days = _cal.monthrange(year, month)[1]
    start, end = C.month_range(year, month)
    # 相位事件：用内核搜当月四相
    events: dict[int, str] = {}
    for e in C.search_quarters(start, end):
        events.setdefault(C.bjt(e.time).day, e.label.split("（")[0])
    cells = []
    for day in range(1, days + 1):
        # 当地 20:00 的相位（UTC 12:00）
        t = A.Time.Make(year, month, day, 12, 0, 0)
        phase = A.MoonPhase(t)  # 视黄经差 = 相位角（度）
        cells.append({
            "day": day,
            "phase_angle": phase,
            "illum": A.Illumination(A.Body.Moon, t).phase_fraction,
            "event": events.get(day, ""),
        })
    return cells


# ---------------------------------------------------------------- 渲染

def render(year: int, month: int, sprite: Image.Image, out: Path) -> Path:
    cells = month_cells(year, month)
    # 周一开头的网格：weekday() 0=周一…6=周日
    lead = (datetime(year, month, 1).weekday()) % 7
    rows = (lead + len(cells) + 6) // 7

    width = PAD * 2 + CELL_W * 7
    height = PAD * 2 + TITLE_H + HEADER_H + CELL_H * rows
    img = Image.new("RGB", (width * SS, height * SS), BG)
    d = ImageDraw.Draw(img)

    s = SS
    # 标题
    title = f"{year}年{month}月"
    f_title = _font(_px(F_TITLE_PT) * s, bold=True)
    tw = d.textlength(title, font=f_title)
    d.text(((width * s - tw) / 2, (PAD + 10) * s), title, font=f_title, fill=TITLE_COLOR)
    # 细分隔线
    d.line([(PAD * s, (PAD + TITLE_H - 12) * s),
            ((width - PAD) * s, (PAD + TITLE_H - 12) * s)], fill=GRID_LINE, width=max(1, s))

    # 星期栏
    f_wd = _font(_px(F_WEEKDAY_PT) * s)
    grid_top = PAD + TITLE_H
    for col, name in enumerate(WEEKDAYS_MON_FIRST):
        cx = (PAD + col * CELL_W + CELL_W / 2) * s
        tw = d.textlength(name, font=f_wd)
        d.text((cx - tw / 2, (grid_top + (HEADER_H - _px(F_WEEKDAY_PT)) / 2) * s),
               name, font=f_wd, fill=WEEKDAY_COLOR)

    f_day = _font(_px(F_DAY_PT) * s, bold=True)
    f_ev = _font(_px(F_EVENT_PT) * s)
    event_band = _px(F_EVENT_PT) + 34     # 相位名占的底部高度
    grid_top += HEADER_H

    # 先把整张网格画满（含月首/月尾的空格），否则空白处会缺一块，行列看起来错位
    for pos in range(rows * 7):
        col, row = pos % 7, pos // 7
        x = PAD + col * CELL_W
        y = grid_top + row * CELL_H
        d.rectangle([x * s, y * s, (x + CELL_W) * s, (y + CELL_H) * s],
                    fill=CELL_BG, outline=GRID_LINE, width=max(1, s))

    for idx, cell in enumerate(cells):
        pos = lead + idx
        col, row = pos % 7, pos // 7
        x = PAD + col * CELL_W
        y = grid_top + row * CELL_H
        if cell["event"]:
            d.rectangle([x * s, y * s, (x + CELL_W) * s, (y + CELL_H) * s],
                        outline=ACCENT, width=2 * s)

        # 月面照片：底部留出 event_band 写相位名，避免文字压到月面上
        side = min(CELL_W - 40, CELL_H - event_band - 30)
        tile = tile_for_phase(sprite, cell["phase_angle"]).resize(
            (side * s, side * s), Image.LANCZOS)
        mx = x + (CELL_W - side) // 2
        my = y + (CELL_H - event_band - side) // 2
        # 用 screen 混合贴图：照片的纯黑底与深色格底自然融合，不会出现方形黑边
        region = img.crop((mx * s, my * s, (mx + side) * s, (my + side) * s))
        img.paste(ImageChops.screen(region, tile), (mx * s, my * s))

        # 日期数字压在月面上
        txt = str(cell["day"])
        tw = d.textlength(txt, font=f_day)
        bbox = d.textbbox((0, 0), txt, font=f_day)
        th = bbox[3] - bbox[1]
        d.text(((x + CELL_W / 2) * s - tw / 2,
                (my + side / 2) * s - th / 2 - bbox[1]),
               txt, font=f_day, fill=DAYNUM_COLOR,
               stroke_width=max(1, int(1.5 * s)), stroke_fill=(0, 0, 0))

        # 相位名贴底
        if cell["event"]:
            ev = cell["event"]
            tw = d.textlength(ev, font=f_ev)
            d.text(((x + CELL_W / 2) * s - tw / 2,
                    (y + CELL_H - event_band + 12) * s), ev, font=f_ev, fill=ACCENT)

    final = img.resize((width, height), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    final.save(out)
    print(f"{out} {final.width}x{final.height} rows={rows}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="渲染本月月相日历（真实月面照片）")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--month", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sprite", type=Path, default=ROOT / "assets" / "phases.jpg")
    args = ap.parse_args(argv)
    sprite = ensure_sprite(args.sprite)
    render(args.year, args.month, sprite, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
