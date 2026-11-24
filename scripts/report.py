"""把"某年某月"变成一份完整的《天象预报》文档规格。

分工：
* `astro_core` 只算事实；
* 本模块负责**挑选**（哪些事象值得进"推荐天象"）与**写话**（中文措辞）；
* `docx_writer` 只管排版。

所有中文措辞都由计算出的数值驱动——日期、角距、ZHR、月光干扰、方位，
不写死任何月份相关的内容，因此可以生成任意年月。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import astronomy as A

import astro_core as C
from docx_writer import DocSpec

DATA = Path(__file__).resolve().parent / "data"

#: 全角冒号 + 度/角分/星/箭头——样本实测字符，见 docx_writer 文档字符串
COLON = "\uff1a"
STAR = "\u2b50"
ARROW = "\u2192"
DEG_S = "\u00b0"
MIN_S = "\u2019"      # 样本用的是右单引号，不是 prime

CITY_DEFAULT = "北京"

#: 行星会合周期（月），用于"罕见程度"
SYNODIC_MONTHS = {
    "Mercury": 3.8, "Venus": 19.2, "Mars": 25.6, "Jupiter": 13.0,
    "Saturn": 12.4, "Uranus": 12.4, "Neptune": 12.4,
}

#: 大流星雨的推荐语：北半球三大流星雨
MAJOR_SHOWERS = {"GEM", "PER", "QUA"}


# ---------------------------------------------------------------- 格式化

def fmt_hm(t: A.Time) -> str:
    """`14：22`——样本用全角冒号。"""
    d = C.bjt(t)
    return f"{d.hour:02d}{COLON}{d.minute:02d}"


def fmt_angle(deg: float) -> str:
    """角距 → `2°15’` / `54’`（样本：不足 1° 只写角分）。"""
    if deg < 1.0:
        return f"{round(deg * 60)}{MIN_S}"
    d = int(deg)
    m = round((deg - d) * 60)
    if m == 60:
        d, m = d + 1, 0
    return f"{d}{DEG_S}{m:02d}{MIN_S}"


def fmt_day(day: int) -> str:
    return f"{day}日"


# ---------------------------------------------------------------- 事件采集

def _load_json(name: str) -> dict:
    p = DATA / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def collect_showers(year: int, month: int) -> list[dict]:
    """当月极大、且 ZHR >= 5 的流星雨。"""
    data = _load_json("meteor_showers.json")
    showers = data.get("showers", []) if isinstance(data, dict) else data
    out = []
    for s in showers:
        if s.get("peak_month") != month:
            continue
        if (s.get("zhr") or 0) < 5:
            continue
        out.append(s)
    return sorted(out, key=lambda s: s["peak_day"])


def collect_events(year: int, month: int, observer: A.Observer) -> list[C.Event]:
    """当月全部"主要天象"事件（不含行星留，留只进动态一节）。"""
    start, end = C.month_range(year, month)
    events: list[C.Event] = []
    events += C.search_quarters(start, end)
    events += C.search_solar_terms(start, end)
    events += C.search_apsides(start, end)
    events += C.search_oppositions(start, end)
    events += C.search_inferior_conjunctions(start, end)
    events += C.search_elongations(start, end)
    events += C.search_moon_planet(start, end)
    events += C.search_occultations(start, end)
    events += C.search_eclipses(start, end, observer)
    for s in collect_showers(year, month):
        # 流星雨只有日期没有时刻（样本即如此：`14日␣␣双子座流星雨极大期（ZHR：150）`）
        events.append(C.Event("shower", None,
                              f"{s['name_cn']}极大期（ZHR：{int(s['zhr'])}）",
                              {"shower": s, "day": s["peak_day"]}))
    return events


def event_sort_key(e: C.Event) -> tuple:
    """按日期排序；同一天内无时刻的条目在前，其余按时刻（与样本一致）。"""
    day = e.data.get("day") if e.kind == "shower" else (
        C.bjt(e.time).day if e.time else 1)
    has_time = 0 if e.time is None else 1
    hhmm = C.bjt(e.time).strftime("%H%M") if e.time else "0000"
    return (day, has_time, hhmm)


def format_event_line(e: C.Event, city: str) -> str:
    """主要天象一行：`5日␣␣06：41␣␣金星合月，距离2°15’`。"""
    day = e.data.get("day") if e.kind == "shower" else C.bjt(e.time).day
    label = e.label
    if e.kind == "moon_planet" and not e.data.get("occulted"):
        label = f"{label}，距离{fmt_angle(e.data['sep_deg'])}"
    if e.kind == "occultation":
        vis = _occultation_visibility(e, city)
        if vis:
            label = f"{label}（{vis}）"
    # 日月食的可见性括注在 astro_core 里写作"本地"，这里统一成观测地名，
    # 免得同一份文档里一会儿"北京不可见"、一会儿"本地不可见"。
    if city != "本地":
        label = label.replace("（本地可见）", f"（{city}可见）")
        label = label.replace("（本地不可见）", f"（{city}不可见）")
    if e.time is None:
        return f"{fmt_day(day)}  {label}"
    return f"{fmt_day(day)}  {fmt_hm(e.time)}  {label}"


def _occultation_visibility(e: C.Event, city: str = CITY_DEFAULT) -> str:
    """月掩事件在默认观测地是否**真的看得见**。

    必须同时要求：月球与目标都在地平线上，且太阳已落入暮光之下（-6°）。
    只判断高度角会把白天的掩星写成"可见"。
    """
    obs = A.Observer(*C.BEIJING)
    body = None
    for name, b in C.register_targets().items():
        if e.label.endswith(name):
            body = b
            break
    if body is None or e.time is None:
        return ""
    ok = C.observable_at(e.time, body, obs, body_alt_min=0.0)
    return f"{city}可见" if ok else f"{city}不可见"


# ---------------------------------------------------------------- 行星动态

def _constellation_clause(path: list[str], movement: str) -> str:
    """星座路径 → `由蛇夫座逆行至天蝎座` / `在巨蟹座顺行` / `由A经B至C`。"""
    mv = movement or ""
    if len(path) == 1:
        return f"在{path[0]}{mv}"
    if len(path) == 2:
        return f"由{path[0]}{mv}至{path[1]}"
    # 三条以上：首、中、尾；若首尾相同则用"然后回到"
    if path[0] == path[-1]:
        mid = path[1:-1]
        if len(mid) == 1:
            return f"由{path[0]}{mv}至{mid[0]}，然后回到{path[0]}"
        return f"由{path[0]}{mv}至{mid[0]}，再至{mid[-1]}，然后回到{path[0]}"
    return f"由{path[0]}经{path[1]}至{path[-1]}"


def planet_line(name: str, year: int, month: int, observer: A.Observer,
                events: list[C.Event]) -> str:
    """一行"大天体动态"。

    措辞规则（对齐样本）：`{星座路径}{顺逆行}[，N日留后转X]。{可见性}。视星等a→b→c。`
    关键点：当月有"留"时，星座路径那句要用**留之前**的运动方向——样本
    `火星  在巨蟹座顺行，7日留后转逆行` 就是这个形状，不能写成"逆行…转逆行"。
    """
    start, end = C.month_range(year, month)
    body = getattr(A.Body, name)

    if name == "Sun":
        path = C.constellation_path(body, start, end)
        clause = (f"由{path[0]}移至{path[-1]}" if len(path) >= 2 else f"在{path[0]}")
        return f"太阳  {clause}。"

    path = C.constellation_path(body, start, end)
    stations = [e for e in events
                if e.kind == "station" and e.data.get("body") == name]
    rate = (C.ecl_lon(body, start.AddDays(1)) - C.ecl_lon(body, start)
            + C.ecl_lon(body, end) - C.ecl_lon(body, end.AddDays(-1)))
    if stations:
        # 留之前的运动方向 = 将要转向的反面
        first = min(stations, key=lambda e: e.time.Utc())
        movement = "顺行" if first.data["to_retrograde"] else "逆行"
    else:
        movement = "顺行" if rate > 0 else "逆行"
    clause = _constellation_clause(path, movement)

    station_txt = ""
    for e in stations:
        d = C.bjt(e.time).day
        station_txt += (f"，{d}日留后转"
                        f"{'逆行' if e.data['to_retrograde'] else '顺行'}")

    # 可见性：月初 / 月末各看一次。**同一 kind 就合并成一句**（方位随时间
    # 推移略有差别不值得写两遍），kind 变了才写"月初…，N日合日后转为…"。
    st_start = C.visibility_state(body, start.AddDays(2), observer)
    st_end = C.visibility_state(body, end.AddDays(-2), observer)
    st_mid = C.visibility_state(body, start.AddDays(14), observer)
    conj = [e for e in events if e.kind == "conjunction"
            and e.data.get("body") == name]
    if st_start["kind"] == st_end["kind"]:
        vis = (st_mid["text"] or st_start["text"])
    elif st_start["kind"] == "none":
        detail = ""
        if conj:
            e = conj[0]
            verb = ("下合日后" if e.data.get("kind") == "inferior"
                    else "上合日后" if e.data.get("kind") == "superior" else "合日后")
            detail = f"{C.bjt(e.time).day}日{verb}"
        vis = (f"{detail}转为{st_end['text']}" if detail else st_end["text"])
    elif st_end["kind"] == "none":
        detail = ""
        if conj:
            e = conj[0]
            verb = ("下合日后" if e.data.get("kind") == "inferior"
                    else "上合日后" if e.data.get("kind") == "superior" else "合日后")
            detail = f"{C.bjt(e.time).day}日{verb}"
        vis = (f"月初{st_start['text']}，{detail}被阳光淹没"
               if detail else f"月初{st_start['text']}，月末隐入阳光")
    elif conj:
        e = conj[0]
        verb = ("下合日后" if e.data.get("kind") == "inferior"
                else "上合日后" if e.data.get("kind") == "superior" else "合日后")
        vis = (f"月初{st_start['text']}，{C.bjt(e.time).day}日{verb}"
               f"转为{st_end['text']}")
    else:
        vis = f"月初{st_start['text']}，月末{st_end['text']}"

    mags = C.magnitude_series(body, start, end)
    mag_txt = ARROW.join(f"{m:.1f}" for m in mags)
    parts = [f"{clause}{station_txt}。"]
    if vis:
        parts.append(f"{vis}。")
    parts.append(f"视星等{mag_txt}。")
    return f"{C.BODY_CN[name]}  " + "".join(parts)


def sun_dynamics(year: int, month: int) -> str:
    start, end = C.month_range(year, month)
    path = C.constellation_path(A.Body.Sun, start, end)
    if len(path) >= 2:
        return f"太阳  由{path[0]}移至{path[-1]}。"
    return f"太阳  在{path[0]}。"


# ---------------------------------------------------------------- 推荐天象

def _moon_interference(year: int, month: int, day: int) -> tuple[float, str]:
    """极大夜的月光干扰：返回（照亮比例, 中文说明）。"""
    t = A.Time.Make(year, month, day, 14, 0, 0)      # BJT 22:00 前后近似
    k = A.Illumination(A.Body.Moon, t).phase_fraction
    if k >= 0.85:
        note = ("不过峰值夜正撞上望前后，月光会把暗弱流星洗掉大半，"
                "实际能数到的比标称值少。")
    elif k >= 0.5:
        note = "峰值夜有月光在场，亮流星仍然够看。"
    elif k >= 0.2:
        note = "月光只占住一部分夜空，后半夜月落之后更清爽。"
    else:
        note = "峰值夜接近无月，是很干净的一晚。"
    return k, note


def _radiant_constellation(ra_deg: Optional[float], dec_deg: Optional[float]) -> str:
    if ra_deg is None or dec_deg is None:
        return "辐射点附近"
    sym = A.Constellation(ra_deg / 15.0, dec_deg).symbol
    return C.CONSTELLATION_CN.get(sym, "")


def _twilight_window(body_name: str, year: int, month: int, day: int,
                     observer: A.Observer) -> Optional[tuple[str, str, float]]:
    """当天"天体高于地平且太阳低于暮光"的窗口 (start, end, 时长小时)。"""
    body = getattr(A.Body, body_name)
    base = datetime(year, month, day)
    best = None
    for offset in range(-1, 2):     # 跨午夜时允许前一天/后一天
        d0 = base + timedelta(days=offset)
        for minute in range(0, 24 * 60, 10):
            t = A.Time.Make(d0.year, d0.month, d0.day, 0, 0, 0).AddDays(minute / 1440.0)
            _, alt = C.horizon(body, t, observer)
            if alt < 4.0:
                continue
            _, sun_alt = C.horizon(A.Body.Sun, t, observer)
            if sun_alt > -6.0:
                continue
            b = C.bjt(t)
            if best is None or b < best[0]:
                best = [b, b]
            else:
                best[1] = b
    if best is None:
        return None
    dur = (best[1] - best[0]).total_seconds() / 3600.0
    return (best[0].strftime("%H:%M").replace(":", COLON),
            best[1].strftime("%H:%M").replace(":", COLON), dur)


def _observable(e: C.Event) -> bool:
    """事件在当地能否真正看到。

    这里要分清两类事件，否则会把好天象判掉：
    * **点事件**（月掩、日月食）：只有那一个瞬间，必须按该时刻判——2024-12-01
      15:25 的月掩心宿二几何上成立，但当时是白天、月球在地平线下。
    * **时间窗事件**（合月、大距、冲日）：事件时刻常在白天，能看的是前后几天
      的黄昏/黎明。判"当下那一刻"会把水星大距（凌晨可见、事件时刻在上午）
      整条扔掉，2025-03 的推荐栏因此一度空掉。
    """
    if e.kind == "eclipse":
        return "本地可见" in e.label
    if e.kind in ("elongation", "opposition", "conjunction", "shower"):
        return True
    if e.time is None:
        return True
    obs = A.Observer(*C.BEIJING)
    if e.kind == "moon_planet":
        # 合月的精确时刻可能落在白天，退到同一天夜里最合适的时刻再判
        return _observable_moment(e.data["body"], e.time, obs) is not None
    if e.kind == "occultation":
        body: Optional[A.Body] = None
        for name, b in C.register_targets().items():
            if e.label.endswith(name):
                body = b
                break
        return C.observable_at(e.time, body, obs) if body is not None else True
    return True


def pick_highlights(events: list[C.Event], n: int = 5) -> list[C.Event]:
    """按"新闻价值"打分挑出 n 条，再按日期排序（样本即按日期排列）。"""
    scored: list[tuple[float, C.Event]] = []
    for e in events:
        s = 0.0
        if e.kind == "shower":
            zhr = e.data["shower"].get("zhr") or 0
            s = 95 if zhr >= 100 else 82 if zhr >= 60 else 68 if zhr >= 30 else 52 if zhr >= 15 else 40
        elif e.kind == "opposition":
            s = 88 if e.data["body"] in ("Jupiter", "Saturn", "Mars") else 60
        elif e.kind == "elongation":
            s = 70 if e.data["body"] == "Venus" else 62
        elif e.kind == "occultation":
            s = 66
        elif e.kind == "moon_planet":
            if e.data.get("occulted"):
                s = 72
            else:
                body = e.data["body"]
                sep = e.data["sep_deg"]
                if body in ("Venus", "Jupiter", "Saturn") and sep < 4:
                    s = 68
                elif body in ("Venus", "Jupiter") and sep < 7:
                    s = 56
                else:
                    s = 44
        elif e.kind == "conjunction":
            # 合日/上下合日 = 天体被太阳淹没，恰恰是**看不见**的时候，
            # 不能当推荐观测目标（2027-03 的"海王星合日"就这么混进来过）。
            # 它们只进主要天象清单与大天体动态。
            s = 0
        elif e.kind in ("quarter", "apsis", "term"):
            # 月相/节气/近远地点不是"观测目标"，只进主要天象清单。
            # 早先给它们 16~30 分，导致天象平淡的月份（如 2026-02）里
            # 推荐栏被"满月/下弦/朔"占满，而这几类没有正文可写 → 空段落。
            s = 0
        elif e.kind == "eclipse":
            s = 100 if "本地可见" in e.label else 0
        elif e.kind == "term":
            s = 16
        # 看不见的事件一律不进推荐（但仍留在主要天象里，供核对）
        if s > 0 and _observable(e):
            scored.append((s, e))
    scored.sort(key=lambda x: -x[0])
    # 同一个"目标"一个月可能出现两次（如 2026-11 的木星合月在 3 日和 30 日各一次），
    # 推荐栏里两篇同名条目既重复又浪费篇幅：按身份去重，只留分高的那条。
    def ident(e: C.Event) -> tuple:
        if e.kind == "moon_planet":
            return ("moon_planet", e.data["body"])
        if e.kind == "shower":
            return ("shower", e.data["shower"].get("code"))
        if e.kind == "eclipse":
            return ("eclipse", e.label.split("（")[0])
        return (e.kind, e.label)

    chosen: list[C.Event] = []
    used: set[tuple] = set()
    for _, e in scored:
        if len(chosen) >= n:
            break
        key = ident(e)
        if key in used:
            continue
        used.add(key)
        chosen.append(e)
    return sorted(chosen, key=event_sort_key)


def _synodic_text(name: str) -> str:
    m = SYNODIC_MONTHS.get(name, 12.4)
    if m < 6:
        return "每年3-4次"
    return f"约每{round(m)}个月一次"


def _recommend_stars(e: C.Event) -> int:
    if e.kind == "shower":
        zhr = e.data["shower"].get("zhr") or 0
        return 5 if zhr >= 100 else 4 if zhr >= 40 else 3
    if e.kind == "opposition":
        return 5 if e.data["body"] in ("Jupiter", "Saturn") else 4 if e.data["body"] == "Mars" else 2
    if e.kind == "elongation":
        return 3 if e.data["body"] == "Venus" else 2
    if e.kind == "occultation":
        return 3
    if e.kind == "moon_planet":
        return 3 if e.data["body"] in ("Venus", "Jupiter") else 2
    return 2


#: 观测难度里"校内/郊区"这一档说的其实是**光污染**：样张作者的语境是
#: 校园观测，所以"校内"= 校园（夜空亮、只能数亮流星），"郊区"= 校外暗处。
#: 换观测地时用 --venue-label 改这个词（如"市区""校园"）。
VENUE_LABEL = "校内"


def _difficulty_stars(e: C.Event, venue: str = "") -> str:
    venue = venue or VENUE_LABEL
    if e.kind == "shower":
        return f"{STAR*2}（{venue}）/{STAR}（郊区）"
    if e.kind == "opposition":
        b = e.data["body"]
        return STAR if b in ("Jupiter", "Saturn", "Mars") else f"{STAR*3}（需望远镜）"
    if e.kind == "elongation":
        return f"{STAR*3}" if e.data["body"] == "Mercury" else f"{STAR*2}"
    if e.kind in ("occultation", "moon_planet"):
        return f"{STAR*2}"
    return STAR


def compose_highlight(e: C.Event, year: int, month: int,
                      observer: A.Observer, city: str,
                      venue: str = "") -> dict:
    """把一条事件写成 推荐天象 的一组字段。"""
    if e.kind == "shower":
        return _hl_shower(e, year, month, observer, venue)
    if e.kind == "opposition":
        return _hl_opposition(e, observer, city)
    if e.kind == "elongation":
        return _hl_elongation(e, year, month, observer)
    if e.kind == "occultation":
        return _hl_occultation(e, city)
    if e.kind == "moon_planet":
        return _hl_moon_planet(e, city)
    if e.kind == "conjunction":
        return _hl_conjunction(e, city)
    if e.kind == "eclipse":
        return _hl_eclipse(e, city)
    raise ValueError(
        f"compose_highlight 没处理这种事件：kind={e.kind} label={e.label!r}。"
        f"要么补一个文案分支，要么在 pick_highlights 里把它排除。")


def _hl_shower(e: C.Event, year: int, month: int, observer: A.Observer,
               venue: str = "") -> dict:
    s = e.data["shower"]
    name = s["name_cn"]
    day = s["peak_day"]
    zhr = int(s["zhr"])
    _, moon_note = _moon_interference(year, month, day)
    radiant = _radiant_constellation(s.get("radiant_ra"), s.get("radiant_dec"))
    is_major = s.get("code") in MAJOR_SHOWERS
    head = f"{name}的峰值落在{day}日。"
    if is_major:
        head += "这是北半球三大流星雨之一，另两个是象限仪座与英仙座。"
    body = head + f"预报天顶每小时出现率约 {zhr} 颗"
    if s.get("velocity_km_s"):
        body += f"，流星速度约 {s['velocity_km_s']} km/s"
    body += "。" + moon_note
    if s.get("parent"):
        body += f"这批尘埃来自{s['parent']}。"
    # 观测时段：极大夜的整晚，取辐射点高度较好的时刻
    when = f"{day}日和{day+1}日21时后的整晚"
    tip = (f"朝{radiant or '辐射点'}方向躺下来守候，挑视野开阔、离路灯远的位置；"
           f"不需要设备，相机固定机位连拍可以留住偶发的亮流星。")
    return {
        "title": f"{name}极大", "body": body, "rarity": "每年一次",
        "recommend": _recommend_stars(e), "difficulty": _difficulty_stars(e, venue),
        "when": when, "tip": tip,
    }


def _hl_opposition(e: C.Event, observer: A.Observer, city: str) -> dict:
    name = e.data["body"]
    cn = C.BODY_CN[name]
    day = C.bjt(e.time).day
    start, _ = C.month_range(C.bjt(e.time).year, C.bjt(e.time).month)
    mags = C.magnitude_series(getattr(A.Body, name), start,
                              C.month_range(C.bjt(e.time).year,
                                            C.bjt(e.time).month)[1])
    extra = {
        "Jupiter": "双筒里能看清四颗伽利略卫星排成一线，高倍下可见云带与大红斑。",
        "Saturn": "这一轮正是观察土星环倾角的时机，高倍下环面细节最清楚。",
        "Mars": "冲日期间火星视直径最大，高倍下能分辨极冠与暗区。",
        "Uranus": "亮度约 5.7 等，在足够暗的郊外肉眼勉强能看见。",
        "Neptune": "需要星图加望远镜，冲日是定位它最省事的时机。",
    }.get(name, "")
    body = (f"{day}日{cn}到达冲日：它和太阳分居地球两侧，整夜都在地平线上，"
            f"视直径与亮度也达到这一轮会合周期里的最好水平，"
            f"目视星等约 {mags[0]:.1f} 等。前后各一个月都是观察它的窗口。")
    # 方位取"日落后"那一刻，不能取月初某个固定时刻——冲日时木星黄昏在东，
    # 半夜在南，"日落后位于西北方"这种错就是时刻取错造成的。
    start = C.month_range(C.bjt(e.time).year, C.bjt(e.time).month)[0]
    snap = C.night_snapshot(getattr(A.Body, name), start.AddDays(14), observer)
    az = snap["az_dusk"] if snap["az_dusk"] is not None else 180.0
    when = "本月夜晚几乎任何时间"
    tip = (f"{cn}入夜后出现在{C._az_name(az)}方，通常就是那片天区最亮的点；{extra}")
    return {
        "title": f"{cn}冲日", "body": body, "rarity": _synodic_text(name),
        "recommend": _recommend_stars(e), "difficulty": _difficulty_stars(e),
        "when": when, "tip": tip,
    }


def _hl_elongation(e: C.Event, year: int, month: int,
                   observer: A.Observer) -> dict:
    name = e.data["body"]
    cn = C.BODY_CN[name]
    east = e.data["east"]
    day = C.bjt(e.time).day
    # 找一个"明显可见"的日期区间：以事件日为中心 ±若干天
    span = 7 if name == "Mercury" else 20
    windows = []
    for delta in range(-span, span + 1):
        d = C.bjt(e.time) + timedelta(days=delta)
        w = _twilight_window(name, d.year, d.month, d.day, observer)
        if w:
            windows.append((d.day, w))
    if windows:
        best = max(windows, key=lambda x: x[1][2])
        t1, t2, _ = best[1]
        days = [w[0] for w in windows]
        # 窗口常常只有十几分钟，10 分钟采样会退化成 "06：00-06：00"，读着像 bug
        span = f"{t1}-{t2}" if t1 != t2 else f"{t1}"
        when = (f"{min(days)}日-{max(days)}日，{span}前后"
                f"（最佳约在{best[0]}日）")
    else:
        when = f"{day}日前后"
    dir_word = "西南" if east else "东南"
    phase = "日落后" if east else "日出前"
    body = (f"{cn}平时紧贴太阳，很难从晨昏天光里分出来。{day}日前后它到达"
            f"{'东' if east else '西'}大距，与太阳的角距拉开到约 "
            f"{e.data['elongation']:.1f} 度，是这一轮里最容易被找到的窗口："
            f"{phase}{dir_word}低空，肉眼就有机会看到。")
    tip = (f"{phase}把视线压到{dir_word}方低空，找一颗不闪的亮白点；"
            f"窗口只有几十分钟，建议提前踩点，双筒能明显提高把握。")
    return {
        "title": f"{cn}{'东' if east else '西'}大距", "body": body,
        "rarity": _synodic_text(name), "recommend": _recommend_stars(e),
        "difficulty": _difficulty_stars(e), "when": when, "tip": tip,
    }


def _time_of_day_word(t: A.Time) -> str:
    h = C.bjt(t).hour
    if h < 5:
        return "凌晨"
    if h < 8:
        return "清晨"
    if h < 11:
        return "上午"
    if h < 14:
        return "正午前后"
    if h < 17:
        return "下午"
    if h < 20:
        return "傍晚"
    return "夜间"


def _hl_occultation(e: C.Event, city: str) -> dict:
    day = C.bjt(e.time).day
    tgt = e.label.replace("月掩", "")
    word = _time_of_day_word(e.time)
    body = (f"{day}日{word}，月球边缘会从{tgt}前面经过，把它的光遮住一段时间，"
            f"这就是月掩{tgt}。月球视差大，各地看到掩入与掩出的时刻能差几分钟"
            f"到几十分钟，越靠近预报地点越准。")
    when = f"{day}日{fmt_hm(e.time)}前后"
    tip = (f"提前把望远镜对准{tgt}，盯住它就行：星光骤然消失是掩入，"
            f"重新亮起是掩出。想留记录就开间隔连拍，事后能拼出光变过程。")
    return {
        "title": f"月掩{tgt}", "body": body, "rarity": "近年较常见（约1-4个月一次）",
        "recommend": _recommend_stars(e), "difficulty": _difficulty_stars(e),
        "when": when, "tip": tip,
    }


def _observable_moment(name: str, t: A.Time,
                       observer: A.Observer) -> Optional[A.Time]:
    """若事件瞬间不可见，退到同一夜最合适的观测时刻（当晚日落后 1h 起扫）。"""
    if C.observable_at(t, getattr(A.Body, name), observer):
        return t
    sunset = A.SearchRiseSet(A.Body.Sun, observer, A.Direction.Set,
                             t.AddDays(-0.6), 2.0)
    if sunset is None:
        return None
    body = getattr(A.Body, name)
    for minutes in range(0, 12 * 60, 10):
        cand = sunset.AddDays(minutes / 1440.0)
        if C.observable_at(cand, body, observer):
            return cand
    return None


def _hl_moon_planet(e: C.Event, city: str) -> dict:
    name = e.data["body"]
    cn = C.BODY_CN[name]
    observer = A.Observer(*C.BEIJING)
    day = C.bjt(e.time).day
    sep = e.data["sep_deg"]
    t = e.time
    moon_illum = A.Illumination(A.Body.Moon, t).phase_fraction
    # 分档按照亮比例，但"满月"要收紧到 97%：2027-03-19 的月亮照亮 93%、
    # 离望还有三天，写成"满月"会被懂行的读者挑错。
    phase_name = ("蛾眉月" if moon_illum < 0.35 else
                  "上弦月" if moon_illum < 0.55 else
                  "盈凸月" if moon_illum < 0.97 else "满月")
    # 合月的精确时刻常在白天，样本的处理是"距离最近在凌晨，但当晚效果也不错"
    obs_t = _observable_moment(name, t, observer)
    if obs_t is None or abs(obs_t.tt - t.tt) < 0.02:
        body = (f"{day}日{fmt_hm(t)}前后，{cn}与{phase_name}在天球上相合，"
                f"中心相距约{fmt_angle(sep)}。一暗一亮凑在一处，构图很紧凑。")
        when = f"{day}日{fmt_hm(t)}前后"
        az, _ = C.horizon(getattr(A.Body, name), obs_t or t, observer)
        lead = f"面向{C._az_name(az)}方"
    else:
        d_obs = C.bjt(obs_t)
        body = (f"两者最接近的时刻落在{_time_of_day_word(t)}，那时未必便于观看；"
                f"改到{day}日{'晚' if d_obs.hour >= 17 else '早'}上"
                f"{fmt_hm(obs_t)}前后，{cn}与{phase_name}相距约{fmt_angle(sep)}，"
                f"画面依然紧凑。")
        when = f"{day}日{fmt_hm(obs_t)}前后"
        az, _ = C.horizon(getattr(A.Body, name), obs_t, observer)
        lead = f"面向{C._az_name(az)}方"
    tip = (f"{lead}先把月亮框进来，{cn}就在旁边不远处；"
            f"双筒里看得更利落，广角到中焦都能拍。")
    return {
        "title": f"{cn}合月", "body": body, "rarity": "几乎每月一次",
        "recommend": _recommend_stars(e), "difficulty": _difficulty_stars(e),
        "when": when, "tip": tip,
    }


def _hl_eclipse(e: C.Event, city: str) -> dict:
    """日月食的推荐文案。"""
    label = e.label
    lunar = e.data.get("eclipse") == "lunar"
    kind = e.data.get("kind", "")
    day = C.bjt(e.time).day
    when_word = _time_of_day_word(e.time)
    if lunar:
        if kind == "Total":
            body = (f"{day}日{when_word}{fmt_hm(e.time)}前后将发生月全食。"
                    f"月球完全进入地球本影，全食阶段月亮会变成暗红色的血月——"
                    f"那是地球大气把阳光中的红光折射进影锥的结果。"
                    f"月食是夜半球同时可见的天象，不需要任何设备。")
        elif kind == "Partial":
            body = (f"{day}日{when_word}{fmt_hm(e.time)}前后将发生月偏食，"
                    f"月球一部分进入地球本影，肉眼就能看出月亮缺了一块。"
                    f"无需设备，阳台即可观测。")
        else:
            body = (f"{day}日{when_word}{fmt_hm(e.time)}前后将发生半影月食，"
                    f"月球只掠过地球半影，亮度略微变暗，肉眼不易分辨，"
                    f"适合用相机固定参数连拍做对比。")
    else:
        if kind == "Total":
            body = (f"{day}日{when_word}{fmt_hm(e.time)}前后将发生日全食。"
                    f"全食带内可见日冕与钻石环，但绝对不要用肉眼或未经"
                    f"滤光片的光学设备直视太阳。")
        elif kind == "Annular":
            body = (f"{day}日{when_word}{fmt_hm(e.time)}前后将发生日环食，"
                    f"环食带内可见金环。观测必须使用合格的太阳滤光片。")
        else:
            body = (f"{day}日{when_word}{fmt_hm(e.time)}前后将发生日偏食，"
                    f"太阳会被咬掉一块。观测必须使用合格的太阳滤光片，"
                    f"或用小孔成像投影法。")
    when = f"{day}日{fmt_hm(e.time)}前后"
    tip = ("找一个东南或西南方向开阔、光污染少的位置；三脚架固定相机，"
           "每隔几分钟拍一张可做成全过程合成图。"
           if lunar else
           "提前确认本地的初亏/食甚/复圆时刻；用长焦或望远镜拍摄时"
           "务必在物镜前加装太阳滤光片。")
    return {
        "title": label.split("（")[0], "body": body,
        "rarity": "每年全球 2-5 次，本地可见的更少",
        "recommend": 5, "difficulty": STAR if lunar else f"{STAR*2}（需滤光片）",
        "when": when, "tip": tip,
    }


def _hl_conjunction(e: C.Event, city: str) -> dict:
    name = e.data["body"]
    cn = C.BODY_CN[name]
    day = C.bjt(e.time).day
    kind = e.data.get("kind")
    if kind == "inferior":
        body = (f"{day}日{fmt_hm(e.time)}前后{cn}走到地球与太阳之间，即下合日。"
                f"此后它由昏星转为晨星，天亮前出现在东方低空。")
    elif kind == "superior":
        body = (f"{day}日{fmt_hm(e.time)}前后{cn}绕到太阳背后，即上合日。"
                f"这段时间它与太阳同升同落，整月无法观测。")
    else:
        body = (f"{day}日{fmt_hm(e.time)}前后{cn}与太阳同黄经，即合日。"
                f"此时它淹没在阳光里，整月不适合观测。")
    return {
        "title": f"{cn}{'下合日' if kind == 'inferior' else '上合日' if kind == 'superior' else '合日'}",
        "body": body, "rarity": "约每13个月一次" if kind else _synodic_text(name),
        "recommend": _recommend_stars(e), "difficulty": _difficulty_stars(e),
        "when": f"{day}日", "tip": f"{cn}此时离太阳太近，不建议观测。",
    }


# ---------------------------------------------------------------- 望远镜目标

def target_lines(year: int, month: int) -> list[str]:
    """本月望远镜目标推荐三行。深空表按 2026 排，其他年份可用 by_year 覆盖。"""
    data = _load_json("deep_sky.json")
    months = data.get("months", {})
    by_year = data.get("by_year", {})
    entry = by_year.get(str(year), {}).get(str(month)) or months.get(str(month), {})
    solar = entry.get("solar_system", [])
    narrow = entry.get("narrowband", [])
    other = entry.get("other", [])
    lines = []
    if solar:
        lines.append("太阳系天体：" + "，".join(solar))
    if narrow:
        lines.append("窄带目标：" + "；".join(narrow))
    if other:
        lines.append("其他目标：" + "；".join(other))
    return lines


# ---------------------------------------------------------------- 组装

def build_spec(year: int, month: int, *, city: str = CITY_DEFAULT,
               lat: Optional[float] = None, lon: Optional[float] = None,
               n_highlights: int = 5,
               venue: str = "",
               moon_image: Optional[Path] = None,
               moon_caption: str = "") -> DocSpec:
    """生成一个月的完整文档规格。"""
    lat = C.BEIJING[0] if lat is None else lat
    lon = C.BEIJING[1] if lon is None else lon
    observer = A.Observer(lat, lon, 50.0)

    import calendar as _cal
    days = _cal.monthrange(year, month)[1]

    events = collect_events(year, month, observer)
    # 天王星、海王星的"合月"月月都有、角距又大，只在真正接近时才值得列出
    events = [e for e in events if not (
        e.kind == "moon_planet" and e.data["body"] in ("Uranus", "Neptune")
        and not e.data.get("occulted") and e.data["sep_deg"] > 1.0)]
    # 北京看不到的月掩不进正文清单（留在 json 里备查）：一份给本地读者的月历，
    # 列两条"发生在白天、根本看不见"的掩星只是噪音。日月食例外——那是全球性
    # 事件，读者即使看不到也往往想知道，所以保留并注明"本地不可见"。
    # 注意：可见性括注是在 format_event_line 里才拼进 label 的，所以这里必须
    # 调 _occultation_visibility 现算，直接查 e.label 永远匹配不到。
    printed = [e for e in events
               if not (e.kind == "occultation"
                       and "不可见" in _occultation_visibility(e))]
    lines = [format_event_line(e, city) for e in sorted(printed, key=event_sort_key)]

    # 大天体动态
    start, end = C.month_range(year, month)
    all_events = events + C.search_stations(start, end)
    planet_lines = [sun_dynamics(year, month)]
    for name in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"):
        planet_lines.append(planet_line(name, year, month, observer, all_events))

    # 推荐天象
    picked = pick_highlights(events, n_highlights)
    highlights = [compose_highlight(e, year, month, observer, city, venue)
                  for e in picked]

    title = f"天象预报 {year}年{month}月"
    intro = (f"{year}年{month}月的夜空，从{month}.1 到 {month}.{days}："
             f"下面按日列出主要天象与行星动态，另挑出 {len(highlights)} 项重点。"
             f"时刻一律北京时间，方位按{city}计算。")

    return DocSpec(
        title=title, intro=intro, highlights=highlights, event_lines=lines,
        planet_lines=planet_lines,
        ps_line="P.S.：各条事件的计算口径见 docs/CONVENTIONS.md；"
                "与别的历表对照时，先确认口径是否一致。",
        moon_image=moon_image,
        # 图注只认调用方显式给的：脚本无法判断用户传进来的图从哪来，
        # 替他们署名 NASA/Goddard 会造成错误署名（自制的图也会被冠上这个来源）。
        # 没图时留空，交给 docx_writer 落"未附图"的说明。
        moon_caption=moon_caption, 
        target_lines=target_lines(year, month),
    )


def minutes_span(year: int, month: int) -> str:
    """导语里的一句补充：本月的日月食/大距等亮点数量，避免空话。"""
    import calendar as _cal
    days = _cal.monthrange(year, month)[1]
    return f"全月{days}天"
