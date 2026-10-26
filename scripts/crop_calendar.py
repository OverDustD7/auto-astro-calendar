"""把浏览器截下来的月相日历页裁成一张干净的图。

工作流（SKILL.md 里有同样的步骤）：

1. 用 `dsh_browser_open` 打开 `https://www.calendar-12.com/moon_calendar/<年>/<英文月名>`
2. 用 `dsh_browser_execute` 量出 `.moon_calendar` 的位置：
   ```js
   (() => { const r = document.querySelector('.moon_calendar').getBoundingClientRect();
     return {x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height, dpr: devicePixelRatio}; })()
   ```
3. `dsh_browser_screenshot` 全页截图到下载目录
4. 本脚本裁掉导航栏、广告、cookie 条，只留日历本体

为什么不直接下载图片：日历是 CSS sprite 拼出来的，页面上没有"一张图"，
必须截图；截图里混着页头/广告，所以要按元素矩形裁。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image


def crop_with_rect(shot: Path, rect: tuple[float, float, float, float],
                   dpr: float = 1.0) -> Image.Image:
    """按 CSS 像素矩形 × dpr 裁出设备像素区域。"""
    im = Image.open(shot)
    x, y, w, h = rect
    box = (round(x * dpr), round(y * dpr), round((x + w) * dpr), round((y + h) * dpr))
    box = (max(0, box[0]), max(0, box[1]),
           min(im.width, box[2]), min(im.height, box[3]))
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError(f"裁剪矩形超出图片范围：{box} vs {im.size}")
    return im.crop(box)


def trim_uniform_border(im: Image.Image, tol: int = 6) -> Image.Image:
    """去掉四周与角落同色的纯色边（截图偶尔会多出几像素页面底色）。"""
    px = im.convert("RGB")
    w, h = px.size
    corners = [px.getpixel(p) for p in
               [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]]
    if len(set(corners)) != 1:
        return im
    ref = corners[0]

    def row_uniform(y: int) -> bool:
        return all(sum(abs(a - b) for a, b in zip(px.getpixel((x, y)), ref)) <= tol
                   for x in range(0, w, max(1, w // 200)))

    def col_uniform(x: int) -> bool:
        return all(sum(abs(a - b) for a, b in zip(px.getpixel((x, y)), ref)) <= tol
                   for y in range(0, h, max(1, h // 200)))

    top, bottom = 0, h - 1
    while top < h - 1 and row_uniform(top):
        top += 1
    while bottom > top and row_uniform(bottom):
        bottom -= 1
    left, right = 0, w - 1
    while left < w - 1 and col_uniform(left):
        left += 1
    while right > left and col_uniform(right):
        right -= 1
    if (top, bottom, left, right) == (0, h - 1, 0, w - 1):
        return im
    return im.crop((left, top, right + 1, bottom + 1))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="裁剪月相日历截图")
    ap.add_argument("--shot", required=True, help="浏览器全页截图")
    ap.add_argument("--rect", required=True,
                    help="CSS 像素矩形 x,y,w,h（来自 dsh_browser_execute）")
    ap.add_argument("--dpr", type=float, default=2.0, help="devicePixelRatio")
    ap.add_argument("--out", required=True, help="输出 PNG")
    ap.add_argument("--no-trim", action="store_true", help="不裁纯色边")
    args = ap.parse_args(argv)

    try:
        rect = tuple(float(v) for v in args.rect.split(","))
        if len(rect) != 4:
            raise ValueError
    except ValueError:
        print("--rect 需要 4 个数字：x,y,w,h", file=sys.stderr)
        return 2
    im = crop_with_rect(Path(args.shot), rect, args.dpr)   # type: ignore[arg-type]
    if not args.no_trim:
        im = trim_uniform_border(im)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print(f"{out} {im.width}x{im.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
