"""天文计算内核：把 astronomy-engine 封装成"天象月历"需要的事件原语。

设计原则
--------
1. **只算事实，不写文案。** 本模块输出的是结构化事件（时间、角距、方位、
   星等…），中文措辞在 prose.py 里生成。
2. **所有对外时间都是北京时间（UTC+8）**，且一律用 `Time` 对象承载，
   渲染时才格式化。
3. **每个事件都带 `conv` 字段说明所用约定**（例如合月按地心最小角距），
   因为不同历表对"合月""大距"的定义不同，可能相差一小时以上。本模块
   的约定写进 docs/CONVENTIONS.md，用户拿别家历表对照时能对上号。

约定速查（详见 docs/CONVENTIONS.md）
------------------------------------
* 朔/上弦/望/下弦：`SearchMoonQuarter`，日月视黄经差 = 0/90/180/270。
* 节气：太阳视黄经（当日平黄道）达到 15° 整数倍。
* 内行星大距：与太阳的**视黄经差**达极大（中文历书的传统口径）。
* 冲日/合日：`SearchRelativeLongitude(body, 0/180)`——对地外行星 0 是冲日，
  对水星金星 0 是下合、180 是上合。
* 留（顺逆行转换）：视黄经变化率过零。
* 合月：地心视位置的最小角距；角距小于月球视半径记为月掩。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

import astronomy as A

# ---------------------------------------------------------------- 基本常数

BJT = timezone(timedelta(hours=8))
DEG = "\u00b0"          # °
MIN = "\u2032"          # ′
SEC = "\u2033"          # ″

#: 默认观测地（北京）。月历以它为方位/可见性口径，可用 --lat/--lon 覆盖。
BEIJING = (39.9042, 116.4074, 50.0)

#: 月球赤道半径（km）
MOON_RADIUS_KM = 1737.4


# ---------------------------------------------------------------- 中文名表

BODY_CN = {
    "Sun": "太阳",
    "Moon": "月球",
    "Mercury": "水星",
    "Venus": "金星",
    "Mars": "火星",
    "Jupiter": "木星",
    "Saturn": "土星",
    "Uranus": "天王星",
    "Neptune": "海王星",
    "Pluto": "冥王星",
}

#: 地外行星（会冲日）
SUPERIOR = ["Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]
#: 内行星（有大距、上下合）
INFERIOR = ["Mercury", "Venus"]
#: 月历"部分太阳系大天体动态"一节的顺序（与样本一致）
DYNAMICS_ORDER = [
    "Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune",
]

#: 24 节气：太阳视黄经 → 名称
SOLAR_TERMS = {
    0: "春分", 15: "清明", 30: "谷雨", 45: "立夏", 60: "小满", 75: "芒种",
    90: "夏至", 105: "小暑", 120: "大暑", 135: "立秋", 150: "处暑", 165: "白露",
    180: "秋分", 195: "寒露", 210: "霜降", 225: "立冬", 240: "小雪", 255: "大雪",
    270: "冬至", 285: "小寒", 300: "大寒", 315: "立春", 330: "雨水", 345: "惊蛰",
}

#: 88 星座拉丁缩写 → 中文名（含属格不影响，缩写唯一）
CONSTELLATION_CN = {
    "And": "仙女座", "Ant": "唧筒座", "Aps": "天燕座", "Aqr": "宝瓶座",
    "Aql": "天鹰座", "Ara": "天坛座", "Ari": "白羊座", "Aur": "御夫座",
    "Boo": "牧夫座", "Cae": "雕具座", "Cam": "鹿豹座", "Cnc": "巨蟹座",
    "CVn": "猎犬座", "CMa": "大犬座", "CMi": "小犬座", "Cap": "摩羯座",
    "Car": "船底座", "Cas": "仙后座", "Cen": "半人马座", "Cep": "仙王座",
    "Cet": "鲸鱼座", "Cha": "蝘蜓座", "Cir": "圆规座", "Col": "天鸽座",
    "Com": "后发座", "CrA": "南冕座", "CrB": "北冕座", "Crv": "乌鸦座",
    "Crt": "巨爵座", "Cru": "南十字座", "Cyg": "天鹅座", "Del": "海豚座",
    "Dor": "剑鱼座", "Dra": "天龙座", "Equ": "小马座", "Eri": "波江座",
    "For": "天炉座", "Gem": "双子座", "Gru": "天鹤座", "Her": "武仙座",
    "Hor": "时钟座", "Hya": "长蛇座", "Hyi": "水蛇座", "Ind": "印第安座",
    "Lac": "蝎虎座", "Leo": "狮子座", "LMi": "小狮座", "Lep": "天兔座",
    "Lib": "天秤座", "Lup": "豺狼座", "Lyn": "天猫座", "Lyr": "天琴座",
    "Men": "山案座", "Mic": "显微镜座", "Mon": "麒麟座", "Mus": "苍蝇座",
    "Nor": "矩尺座", "Oct": "南极座", "Oph": "蛇夫座", "Ori": "猎户座",
    "Pav": "孔雀座", "Peg": "飞马座", "Per": "英仙座", "Phe": "凤凰座",
    "Pic": "绘架座", "Psc": "双鱼座", "PsA": "南鱼座", "Pup": "船尾座",
    "Pyx": "罗盘座", "Ret": "网罟座", "Sge": "天箭座", "Sgr": "人马座",
    "Sco": "天蝎座", "Scl": "玉夫座", "Sct": "盾牌座", "Ser": "巨蛇座",
    "Sex": "六分仪座", "Tau": "金牛座", "Tel": "望远镜座", "Tri": "三角座",
    "TrA": "南三角座", "Tuc": "杜鹃座", "UMa": "大熊座", "UMi": "小熊座",
    "Vel": "船帆座", "Vir": "室女座", "Vol": "飞鱼座", "Vul": "狐狸座",
}

#: 月掩/合月候选亮恒星：中文名 → (视赤经 h, 视赤纬 °, 距离 ly)
#: 只收黄道带附近、月球真能掩到的亮星与星团。
OCCULT_TARGETS = [
    ("角宿一", 13.41988, -11.16132, 250.0),
    ("心宿二", 16.49013, -26.43200, 550.0),
    ("轩辕十四", 10.13953, 11.96721, 79.0),
    ("毕宿五", 4.59867, 16.50930, 65.0),
    ("井宿三", 6.62853, 16.39928, 109.0),
    ("北河三", 7.75526, 28.02620, 34.0),
    ("昴星团", 3.79250, 24.10500, 444.0),
    ("鬼宿星团", 8.67333, 19.66667, 577.0),
]

#: 恒星名字 → astronomy-engine 的 Body（DefineStar 用）
_STAR_BODY_CACHE: dict[str, A.Body] = {}


def _star_body(name: str, ra_h: float, dec: float, dist_ly: float) -> A.Body:
    """把亮恒星注册成 astronomy-engine 的 Star1..Star8 之一（幂等）。"""
    if name in _STAR_BODY_CACHE:
        return _STAR_BODY_CACHE[name]
    star_bodies = [
        A.Body.Star1, A.Body.Star2, A.Body.Star3, A.Body.Star4,
        A.Body.Star5, A.Body.Star6, A.Body.Star7, A.Body.Star8,
    ]
    idx = len(_STAR_BODY_CACHE)
    if idx >= len(star_bodies):
        raise RuntimeError("OCCULT_TARGETS 超过 astronomy-engine 的 8 颗自定义恒星上限")
    body = star_bodies[idx]
    A.DefineStar(body, ra_h, dec, dist_ly)
    _STAR_BODY_CACHE[name] = body
    return body


def register_targets() -> dict[str, A.Body]:
    """注册全部月掩候选目标，返回 名称 → Body。行星直接用内置 Body。"""
    out: dict[str, A.Body] = {}
    for name, ra, dec, dist in OCCULT_TARGETS:
        out[name] = _star_body(name, ra, dec, dist)
    for planet in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"):
        out[BODY_CN[planet]] = getattr(A.Body, planet)
    return out


# ---------------------------------------------------------------- 时间工具

def bjt(t: A.Time) -> datetime:
    """astronomy-engine 的 Time → 北京时间 datetime。"""
    return t.Utc().replace(tzinfo=timezone.utc).astimezone(BJT).replace(tzinfo=None)


def make_time(year: int, month: int, day: int = 1, hour: int = 0) -> A.Time:
    return A.Time.Make(year, month, day, hour, 0, 0)


def _bjt_to_time(dt: datetime) -> A.Time:
    """北京时间 datetime（无时区）→ astronomy-engine 的 Time（UTC）。"""
    u = dt - timedelta(hours=8)
    return A.Time.Make(u.year, u.month, u.day, u.hour, u.minute, u.second)


def month_range(year: int, month: int) -> tuple[A.Time, A.Time]:
    """返回 [当月1日 00:00 北京, 次月1日 00:00 北京) 的 UTC 端点。

    边界必须按**北京时间**切，不能按 UTC 切：2026-12-01 00:55（北京）对应
    UTC 11-30 16:55，按 UTC 切会被算进 11 月，于是 11 月的报表里冒出 12 月的
    事件；反过来，每月 1 日 00:00–08:00（北京）发生的事又会被漏掉。
    """
    start_bjt = datetime(year, month, 1)
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    end_bjt = datetime(ny, nm, 1)
    return _bjt_to_time(start_bjt), _bjt_to_time(end_bjt)


def fmt_hm(t: A.Time) -> str:
    """HH:MM（北京时间，半角冒号，内部用；正文渲染时换成全角）。"""
    return bjt(t).strftime("%H:%M")


def refine(f: Callable[[A.Time], float], t: A.Time, days: float, tol_sec: float = 1.0) -> Optional[A.Time]:
    """在 t±days 内用黄金分割把 f 的极小值细化到 tol_sec 秒。

    用于"最小角距"这类没有解析解的量。f 越小越好；发散时返回 None。
    """
    lo = t.AddDays(-days)
    hi = t.AddDays(days)
    gr = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = 0.0, 1.0
    c = b - gr * (b - a)
    d = a + gr * (b - a)
    fc = f(lo.AddDays((hi.tt - lo.tt) * c))
    fd = f(lo.AddDays((hi.tt - lo.tt) * d))
    span_days = hi.tt - lo.tt
    for _ in range(200):
        if abs(b - a) * span_days * 86400.0 < tol_sec:
            break
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - gr * (b - a)
            fc = f(lo.AddDays(span_days * c))
        else:
            a, c, fc = c, d, fd
            d = a + gr * (b - a)
            fd = f(lo.AddDays(span_days * d))
    return lo.AddDays(span_days * (a + b) / 2.0)


# ---------------------------------------------------------------- 位置原语

def geo_sep(body1: A.Body, body2: A.Body, t: A.Time) -> float:
    """两天体的地心视位置角距（度）。"""
    v1 = A.GeoVector(body1, t, True)
    v2 = A.GeoVector(body2, t, True)
    return A.AngleBetween(v1, v2)


def ecl_lon(body: A.Body, t: A.Time) -> float:
    """视黄经，0..360。

    注意：必须走 `Ecliptic(GeoVector(...))` 这条路径。已验证它在冬至时给出
    太阳视黄经 270.000°、水星大距极大时刻与中文历书一致；自己再用
    `Rotation_EQJ_ECT` 旋转一次会重复换系（黄经偏 ~0.35°、大距时刻偏 6 小时）。
    """
    return A.Ecliptic(A.GeoVector(body, t, True)).elon


def eq_of_date(body: A.Body, t: A.Time) -> tuple[float, float]:
    """视赤经（小时）/视赤纬（度），当日平赤道。"""
    v = A.GeoVector(body, t, True)
    e = A.EquatorFromVector(A.RotateVector(A.Rotation_EQJ_EQD(t), v))
    return e.ra, e.dec


def horizon(body: A.Body, t: A.Time, observer: A.Observer) -> tuple[float, float]:
    """地平坐标：方位角（度，自北向东）、高度角（度，含大气折射修正前的地平线）。"""
    ra, dec = eq_of_date(body, t)
    h = A.Horizon(t, observer, ra, dec, A.Refraction.Normal)
    # HorizonInfo: azimuth 自北向东 0..360, altitude 度
    return h.azimuth, h.altitude


def moon_radius_deg(t: A.Time) -> float:
    """月球视半径（度）。"""
    dist_km = moon_distance_km(t)
    return math.degrees(math.asin(MOON_RADIUS_KM / dist_km))


def moon_distance_km(t: A.Time) -> float:
    return A.GeoMoon(t).Length() * A.KM_PER_AU


def magnitude(body: A.Body, t: A.Time) -> float:
    """视星等。对太阳返回 None 由调用方处理。"""
    return A.Illumination(body, t).mag


def illum_fraction(body: A.Body, t: A.Time) -> float:
    return A.Illumination(body, t).phase_fraction


# ---------------------------------------------------------------- 事件搜索

@dataclass
class Event:
    """一条天象。time=None 表示当月只有日期没有时刻。"""
    kind: str                 # quarter / apsis / term / opposition / conjunction /
                              # station / elongation / moon_planet / occultation / shower
    time: Optional[A.Time]
    label: str                # 中文条目文案，如 "朔（新月）"、"木星冲日"
    data: dict = field(default_factory=dict)

    @property
    def date(self) -> Optional[datetime]:
        return bjt(self.time) if self.time else None


MOON_PHASE_LABEL = {0: "朔（新月）", 1: "上弦月", 2: "望（满月）", 3: "下弦月"}


def search_quarters(start: A.Time, end: A.Time) -> list[Event]:
    out: list[Event] = []
    t = A.SearchMoonQuarter(start)
    while t.time.Utc() < end.Utc():
        out.append(Event("quarter", t.time, MOON_PHASE_LABEL[t.quarter],
                         {"quarter": t.quarter}))
        t = A.NextMoonQuarter(t)
    return out


def search_apsides(start: A.Time, end: A.Time) -> list[Event]:
    out: list[Event] = []
    t0 = A.SearchLunarApsis(start)
    cur = t0
    while cur.time.Utc() < end.Utc():
        if cur.time.Utc() >= start.Utc():
            perigee = cur.kind == A.ApsisKind.Pericenter
            out.append(Event(
                "apsis", cur.time,
                "月球过近地点" if perigee else "月球过远地点",
                {"dist_km": cur.dist_km, "perigee": perigee},
            ))
        cur = A.NextLunarApsis(cur)
    return out


def search_solar_terms(start: A.Time, end: A.Time) -> list[Event]:
    out: list[Event] = []
    # 从 start 前 20 天起搜，保证月初的节气不会被漏掉
    probe = start.AddDays(-20)
    for lon, name in SOLAR_TERMS.items():
        t = A.SearchSunLongitude(float(lon), probe, 45.0)
        if t is not None and start.Utc() <= t.Utc() < end.Utc():
            out.append(Event("term", t, name, {"lon": lon}))
    return sorted(out, key=lambda e: e.time.Utc())


def search_oppositions(start: A.Time, end: A.Time) -> list[Event]:
    """地外行星冲日 + 合日。"""
    out: list[Event] = []
    for name in SUPERIOR:
        body = getattr(A.Body, name)
        # target=0 → 冲日；target=180 → 合日（被太阳淹没）
        t = A.SearchRelativeLongitude(body, 0.0, start)
        if t.Utc() < end.Utc():
            out.append(Event("opposition", t, f"{BODY_CN[name]}冲日",
                             {"body": name, "kind": "opposition"}))
        t = A.SearchRelativeLongitude(body, 180.0, start)
        if t.Utc() < end.Utc():
            out.append(Event("conjunction", t, f"{BODY_CN[name]}合日",
                             {"body": name, "kind": "conjunction"}))
    return out


def search_inferior_conjunctions(start: A.Time, end: A.Time) -> list[Event]:
    """水星/金星的上下合日。target=0 → 下合（内合），180 → 上合。"""
    out: list[Event] = []
    for name in INFERIOR:
        body = getattr(A.Body, name)
        t = A.SearchRelativeLongitude(body, 0.0, start)
        if t.Utc() < end.Utc():
            out.append(Event("conjunction", t, f"{BODY_CN[name]}下合日",
                             {"body": name, "kind": "inferior"}))
        t = A.SearchRelativeLongitude(body, 180.0, start)
        if t.Utc() < end.Utc():
            out.append(Event("conjunction", t, f"{BODY_CN[name]}上合日",
                             {"body": name, "kind": "superior"}))
    return out


def search_stations(start: A.Time, end: A.Time) -> list[Event]:
    """行星"留"：视黄经变化率过零。返回当月内的顺→逆、逆→顺两个方向。

    实现要点（踩过的坑）：步长必须细到 1 小时（0.5 天会让火星、海王星的
    留落到错误日期），导数用 ±0.02 天的中心差分，再用二分把零点收敛到秒级。
    """
    out: list[Event] = []
    bodies = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]

    def rate(body: A.Body, t: A.Time, h: float = 0.02) -> float:
        return (ecl_lon(body, t.AddDays(h)) - ecl_lon(body, t.AddDays(-h))) / (2 * h)

    for name in bodies:
        body = getattr(A.Body, name)
        t = start.AddDays(-2)
        prev_t: Optional[A.Time] = None
        prev_rate: Optional[float] = None
        while t.Utc() < end.Utc() + timedelta(days=2):
            r = rate(body, t)
            if prev_rate is not None and prev_rate * r < 0 and prev_t is not None:
                lo, hi = prev_t, t
                for _ in range(80):
                    mid = lo.AddDays((hi.tt - lo.tt) / 2.0)
                    if rate(body, lo) * rate(body, mid) <= 0:
                        hi = mid
                    else:
                        lo = mid
                    if (hi.tt - lo.tt) * 86400 < 0.5:
                        break
                st = lo.AddDays((hi.tt - lo.tt) / 2.0)
                if start.Utc() <= st.Utc() < end.Utc():
                    out.append(Event(
                        "station", st, f"{BODY_CN[name]}留",
                        {"body": name, "to_retrograde": r < 0},
                    ))
            prev_t, prev_rate = t, r
            t = t.AddDays(1.0 / 24.0)
    return sorted(out, key=lambda e: e.time.Utc())


def search_elongations(start: A.Time, end: A.Time) -> list[Event]:
    """水星/金星大距：与太阳的**视角距**达极大（国际通用定义）。

    为什么用角距而不是黄经差：AstroPixels、NASA、天文通三家给的
    2025-03-08 水星东大距时刻都是**角距极大**（北京 14:00／实测 14:05），
    而"视黄经差极大"在同一事件上是 09:40，差 4.4 小时。早先为了贴合样本
    里 2024-12-25 的 15:10 曾改用黄经差，那是**对单一样本过拟合**，已改回。
    样本那一条的来源用的是旧式黄经差口径，差异记在 docs/KNOWN_ISSUES.md。
    """
    out: list[Event] = []
    for name in INFERIOR:
        body = getattr(A.Body, name)
        e = A.SearchMaxElongation(body, start.AddDays(-15))
        while e is not None and e.time.Utc() < end.Utc() + timedelta(days=15):
            if start.Utc() <= e.time.Utc() < end.Utc():
                east = e.visibility == A.Visibility.Evening
                out.append(Event("elongation", e.time,
                                 f"{BODY_CN[name]}{'东' if east else '西'}大距",
                                 {"body": name, "east": east,
                                  "elongation": e.elongation}))
            e = A.SearchMaxElongation(body, e.time.AddDays(5))
    return sorted(out, key=lambda e: e.time.Utc())


def search_moon_planet(start: A.Time, end: A.Time,
                       max_sep_deg: float = 7.0) -> list[Event]:
    """行星合月/月掩行星：地心最小角距。

    扫 6 小时步长找角距极小，再用黄金分割细化；角距 < 月球视半径记为"月掩"。
    """
    out: list[Event] = []
    for name in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"):
        body = getattr(A.Body, name)
        # 行星合月周期约 27.3 天，一个月最多两次，扫全程步长 0.25 天足够
        t = start.AddDays(-1)
        samples: list[tuple[A.Time, float]] = []
        while t.Utc() < end.Utc() + timedelta(days=1):
            samples.append((t, geo_sep(A.Body.Moon, body, t)))
            t = t.AddDays(0.25)
        for i in range(1, len(samples) - 1):
            if samples[i][1] < samples[i - 1][1] and samples[i][1] < samples[i + 1][1]:
                tmin = refine(lambda tt: geo_sep(A.Body.Moon, body, tt),
                              samples[i][0], 0.3)
                if tmin is None or not (start.Utc() <= tmin.Utc() < end.Utc()):
                    continue
                sep = geo_sep(A.Body.Moon, body, tmin)
                if sep > max_sep_deg:
                    continue
                occulted = sep < moon_radius_deg(tmin)
                label = (f"月掩{BODY_CN[name]}" if occulted
                         else f"{BODY_CN[name]}合月")
                out.append(Event("moon_planet", tmin, label,
                                 {"body": name, "sep_deg": sep,
                                  "occulted": occulted}))
    return sorted(out, key=lambda e: e.time.Utc())


def search_occultations(start: A.Time, end: A.Time) -> list[Event]:
    """月掩亮恒星 / 星团（黄道附近，月球视半径内）。"""
    out: list[Event] = []
    targets = register_targets()
    for name, body in targets.items():
        # 行星已在 search_moon_planet 处理，这里只做恒星与星团
        if name in BODY_CN.values():
            continue
        t = start.AddDays(-1)
        samples: list[tuple[A.Time, float]] = []
        while t.Utc() < end.Utc() + timedelta(days=1):
            samples.append((t, geo_sep(A.Body.Moon, body, t)))
            t = t.AddDays(0.2)
        for i in range(1, len(samples) - 1):
            if samples[i][1] < samples[i - 1][1] and samples[i][1] < samples[i + 1][1]:
                tmin = refine(lambda tt: geo_sep(A.Body.Moon, body, tt),
                              samples[i][0], 0.2)
                if tmin is None or not (start.Utc() <= tmin.Utc() < end.Utc()):
                    continue
                sep = geo_sep(A.Body.Moon, body, tmin)
                if sep < moon_radius_deg(tmin):
                    out.append(Event("occultation", tmin, f"月掩{name}",
                                     {"target": name, "sep_deg": sep}))
    return sorted(out, key=lambda e: e.time.Utc())


def search_eclipses(start: A.Time, end: A.Time,
                    observer: A.Observer) -> list[Event]:
    """日月食。

    * 月食：`SearchLunarEclipse`，报食甚时刻与食分（obscuration 是本影食分）。
    * 日食：`SearchGlobalSolarEclipse` 取全球事件，再用 `SearchLocalSolarEclipse`
      判断本地是否真的能看到（日食是否可见完全取决于地点，不能全球一刀切）。

    可见性写进 label 的括注里——一份写给北京读者的月历，把发生在美洲的
    月全食不加说明地列出来是误导。
    """
    out: list[Event] = []
    lunar_label = {
        A.EclipseKind.Total: "月全食",
        A.EclipseKind.Partial: "月偏食",
        A.EclipseKind.Penumbral: "半影月食",
    }
    solar_label = {
        A.EclipseKind.Total: "日全食",
        A.EclipseKind.Annular: "日环食",
        A.EclipseKind.Partial: "日偏食",
    }

    e = A.SearchLunarEclipse(start)
    while e.peak.Utc() < end.Utc():
        if e.peak.Utc() >= start.Utc():
            name = lunar_label.get(e.kind, "月食")
            # 不写"食分"：引擎给的是 obscuration（被食面积比），而历书里的
            # 食分是"被食直径比"，全食时前者恒为 1.00、后者可到 1.18。
            # 把面积比当食分写出去是错数，宁可只报类型。
            _, alt = horizon(A.Body.Moon, e.peak, observer)
            text = name + ("（本地可见）" if alt > 0 else "（本地不可见）")
            out.append(Event("eclipse", e.peak, text,
                             {"eclipse": "lunar", "kind": e.kind.name,
                              "obs": e.obscuration}))
        e = A.NextLunarEclipse(e.peak)

    g = A.SearchGlobalSolarEclipse(start)
    while g.peak.Utc() < end.Utc() + timedelta(days=1):
        if start.Utc() <= g.peak.Utc() < end.Utc():
            name = solar_label.get(g.kind, "日食")
            # 本地是否能看到：在该时刻附近找本地日食，且峰值相去不远
            local = A.SearchLocalSolarEclipse(g.peak.AddDays(-1), observer)
            visible = (local is not None
                       and abs(local.peak.time.tt - g.peak.tt) < 0.5)
            text = f"{name}（本地可见）" if visible else f"{name}（本地不可见）"
            out.append(Event("eclipse", g.peak, text,
                             {"eclipse": "solar", "kind": g.kind.name,
                              "local_visible": visible}))
        g = A.NextGlobalSolarEclipse(g.peak)
    return sorted(out, key=lambda e: e.time.Utc())


# ---------------------------------------------------------------- 行星动态

@dataclass
class PlanetMotion:
    body: str
    constellation_path: list[str]     # 按时间顺序经过的星座（去重、相邻合并）
    movement: str                     # "顺行" / "逆行" / ""（无位移）
    station_days: list[tuple[int, bool]]  # (日, 是否转为逆行)
    magnitude_series: list[float]     # 月初 / 月中极值 / 月末
    mag_text: str
    visibility: str                   # 中文可见性描述
    events: list[str] = field(default_factory=list)


def _constellation_at(body: A.Body, t: A.Time) -> str:
    ra, dec = eq_of_date(body, t)
    sym = A.Constellation(ra, dec).symbol
    return CONSTELLATION_CN.get(sym, sym)


def constellation_path(body: A.Body, start: A.Time, end: A.Time,
                       samples: int = 60) -> list[str]:
    """按天采样，返回去重后的星座序列（相邻重复合并）。"""
    seq: list[str] = []
    for i in range(samples + 1):
        t = start.AddDays((end.tt - start.tt) * i / samples)
        c = _constellation_at(body, t)
        if not seq or seq[-1] != c:
            seq.append(c)
    return seq


def magnitude_series(body: A.Body, start: A.Time, end: A.Time,
                     samples: int = 120) -> list[float]:
    """返回 [月初, （中间极值）, 月末] 的星等序列。

    中间极值只在"明显偏离两端连线"时插入——水星下合前后会先暗到 6 等再
    亮回负等，样本写作 `1.7→6.2→-0.4`；曲线基本单调时就不插。
    """
    mags: list[tuple[float, float]] = []
    for i in range(samples + 1):
        frac = i / samples
        t = start.AddDays((end.tt - start.tt) * frac)
        mags.append((frac, magnitude(body, t)))
    first, last = mags[0][1], mags[-1][1]
    # 挑"离两端连线最远"的点，而不是简单找拐点（拐点在单调段也会被误判）
    best_dev, best_val = 0.0, None
    for frac, m in mags[1:-1]:
        line = first + (last - first) * frac
        dev = abs(m - line)
        if dev > best_dev:
            best_dev, best_val = dev, m
    if best_val is not None and best_dev > 0.25:
        return [first, best_val, last]
    return [first, last]


def night_snapshot(body: A.Body, date: A.Time, observer: A.Observer) -> dict:
    """一个当地夜里的可见性快照。

    方位角的取值时刻很关键（踩过的坑）：判断"从哪方升起"必须取**升起那一刻**
    的方位，不能取天亮前的方位——火星前半夜 20:40 从东北升起，到 07:00 已经
    跑到西南了，取错时刻就会写成"升起于西方"。
    """
    set_sun = A.SearchRiseSet(A.Body.Sun, observer, A.Direction.Set, date, 2.0)
    rise_sun = A.SearchRiseSet(A.Body.Sun, observer, A.Direction.Rise, date, 2.0)
    out = {"sunset": set_sun, "sunrise": rise_sun, "alt_dusk": None,
           "az_dusk": None, "alt_dawn": None, "az_dawn": None,
           "set_body": None, "rise_body": None,
           "az_rise": None, "hours_after_sunset": None}
    if set_sun is not None:
        t = set_sun.AddDays(1.0 / 24.0)
        out["az_dusk"], out["alt_dusk"] = horizon(body, t, observer)
        st = A.SearchRiseSet(body, observer, A.Direction.Set, set_sun, 1.2)
        if st is not None and (st.tt - set_sun.tt) < 0.9:
            out["set_body"] = st
            out["hours_after_sunset"] = (st.tt - set_sun.tt) * 24.0
    if rise_sun is not None:
        t = rise_sun.AddDays(-1.0 / 24.0)
        out["az_dawn"], out["alt_dawn"] = horizon(body, t, observer)
        # 只认"夜里"的升起：从日落后开始找，且必须在天亮之前
        start = set_sun if set_sun is not None else rise_sun.AddDays(-1.0)
        rb = A.SearchRiseSet(body, observer, A.Direction.Rise, start, 0.9)
        if rb is not None and rb.tt < rise_sun.tt:
            out["rise_body"] = rb
            az, _ = horizon(body, rb, observer)
            out["az_rise"] = az
    return out


def _fall_phrase(hours_after_sunset: float) -> str:
    """落下时刻 → 中文短语（阈值参照样本措辞：不久/数小时/夜半/后半夜）。"""
    if hours_after_sunset <= 2.5:
        return "不久落下"
    if hours_after_sunset <= 4.5:
        return "数小时后落下"
    if hours_after_sunset <= 7.5:
        return "夜半前后落下"
    if hours_after_sunset <= 10.0:
        return "后半夜落下"
    return "几乎整夜可见"


def visibility_state(body: A.Body, date: A.Time, observer: A.Observer) -> dict:
    """把可见性归纳成 {kind, text}。

    kind ∈ {allnight, dusk, dawn, none}——用于判断"月初/月末要不要分两句写"：
    同一 kind 只是方位略有差别时合并成一句，kind 变了才写转变。
    """
    s = night_snapshot(body, date, observer)
    up_dusk = s["alt_dusk"] is not None and s["alt_dusk"] > 0
    up_dawn = s["alt_dawn"] is not None and s["alt_dawn"] > 0
    if up_dusk and up_dawn:
        return {"kind": "allnight",
                "text": f"日落后可见于{_az_name(s['az_dusk'])}方，几乎整夜可见"}
    if up_dusk:
        hours = s.get("hours_after_sunset")
        tail = _fall_phrase(hours) if hours is not None else "入夜后落下"
        # 落下时刻晚到"几乎整夜"时，归为 allnight：这样月初/月末只是方位
        # 略变（东北→东）时不会写成两句，读者也不必被这种差别打扰
        kind = "allnight" if tail == "几乎整夜可见" else "dusk"
        return {"kind": kind,
                "text": f"日落后可见于{_az_name(s['az_dusk'])}方，{tail}"}
    if up_dawn:
        if s["rise_body"] is not None and s["az_rise"] is not None:
            hh = bjt(s["rise_body"]).hour
            az = _az_name(s["az_rise"])
            if hh >= 18 or hh == 0:
                return {"kind": "dawn",
                        "text": f"前半夜{hh}时前后升起于{az}方，后半夜一直可见"}
            if hh < 3:
                return {"kind": "dawn",
                        "text": f"凌晨{hh}时前后升起于{az}方，天亮前可见"}
            return {"kind": "dawn", "text": f"日出前可见于{az}方"}
        return {"kind": "dawn", "text": f"日出前可见于{_az_name(s['az_dawn'])}方"}
    return {"kind": "none", "text": ""}


def visibility_clause(body: A.Body, date: A.Time,
                      observer: A.Observer) -> str:
    """生成"日落后可见于西南方，不久落下"这一句（不含句号）。"""
    return visibility_state(body, date, observer)["text"]



def observable_at(t: A.Time, body: A.Body, observer: A.Observer,
                  sun_alt_max: float = -6.0, body_alt_min: float = 3.0) -> bool:
    """事件发生时是否真的看得见：天体在地平线上、太阳已落入暮光之下。"""
    _, alt = horizon(body, t, observer)
    if alt < body_alt_min:
        return False
    _, sun_alt = horizon(A.Body.Sun, t, observer)
    return sun_alt < sun_alt_max



def _az_name(az: float) -> str:
    dirs = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    idx = int((az + 22.5) // 45) % 8
    return dirs[idx]


def planet_motion(name: str, year: int, month: int,
                  observer: A.Observer, events: list[Event]) -> PlanetMotion:
    """汇总一颗行星当月的动态：星座路径、顺逆行、留、星等、可见性。"""
    start, end = month_range(year, month)
    body = getattr(A.Body, name)
    path = constellation_path(body, start, end)
    # 顺逆行：用月初与月末的视黄经变化率判定主体状态，再用"留"修正
    rate_start = ecl_lon(body, start.AddDays(0.5)) - ecl_lon(body, start)
    rate_end = ecl_lon(body, end) - ecl_lon(body, end.AddDays(-0.5))
    movement = ""
    if abs(rate_start) > 0.02 or abs(rate_end) > 0.02:
        movement = "顺行" if (rate_start + rate_end) > 0 else "逆行"
    station_days = [
        (bjt(e.time).day, e.data["to_retrograde"])
        for e in events if e.kind == "station" and e.data.get("body") == name
    ]
    mags = magnitude_series(body, start, end)
    if len(mags) == 3:
        mag_text = f"{mags[0]:.1f}\u2192{mags[1]:.1f}\u2192{mags[2]:.1f}"
    else:
        mag_text = f"{mags[0]:.1f}\u2192{mags[-1]:.1f}"
    return PlanetMotion(
        body=name,
        constellation_path=path,
        movement=movement,
        station_days=station_days,
        magnitude_series=mags,
        mag_text=mag_text,
        visibility=nightly_visibility(body, year, month, observer),
    )


def sun_path(year: int, month: int) -> list[str]:
    start, end = month_range(year, month)
    return constellation_path(A.Body.Sun, start, end)


def moon_day_series(year: int, month: int) -> list[dict]:
    """逐日月相：供月相日历图使用。每天的 12:00（北京时间）取相位。"""
    import calendar as _cal
    days_in_month = _cal.monthrange(year, month)[1]
    out: list[dict] = []
    for day in range(1, days_in_month + 1):
        t = make_time(year, month, day, 4)   # BJT 12:00 = UTC 04:00
        phase = A.MoonPhase(t)
        dt = datetime(year, month, day)
        out.append({
            "day": day,
            "weekday": dt.weekday(),
            "illum": round(A.Illumination(A.Body.Moon, t).phase_fraction, 4),
            "phase_angle": round(phase.phase_angle, 2),
        })
    return out
