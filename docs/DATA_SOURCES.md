# 天象数据源调研（DATA_SOURCES）

> 目的：为「天象预报 YYYY年M月」生成器提供**独立于本机计算引擎**的参照数据来源。
> 调研时间：2026-10-26（Asia/Shanghai）。所有「可达性」均为**当机实测**结果，未实测的一律标 `UNVERIFIED`。
> 测试方式：`curl.exe`（PowerShell 5.1）、`web_fetch`、`dsh_browser_*`（真实 Chromium）。
>
> **重要结论先行**：本机网络对 `*.mil`（USNO）与 `ssd.jpl.nasa.gov`（JPL Horizons）**不可达**，对 `timeanddate.com`/`in-the-sky.org` 有反爬；
> 真正稳定好用的是 **AstroPixels（Espenak）+ 天文通 API + 国立天文台暦要項 + NASA GSFC 月相表 + IMO 流星雨日历**。

---

## 1. 天文通（tianwentong.cn / App / 小程序）

### 1.1 域名真相（与任务假设不同，务必注意）

| 域名 | 实测结果 | 判定 |
|---|---|---|
| `https://www.tianwentong.cn/` | `ERR_SSL_UNRECOGNIZED_NAME_ALERT`（证书与域名不匹配，疑似 ISP/CDN 劫持） | **不可用** |
| `http://www.tianwentong.cn/` | HTTP 200，但正文是「503 服务暂时不可用／公开访问已暂时受限」托管商停站页 + `/ticket`「紧急委托通道」 | **不可用（站点已停）** |
| `https://api.tianwentong.cn/` | 连接失败（curl `000`） | **不可用** |
| `https://twtapp.com/` | HTTP 200（App 官网/下载页，无天象数据表） | 可达，无数据 |
| **`https://laysky.com/`** | **HTTP 200**，「天文通内容站」，页脚声明「天文通官网 twtapp.com」 | ✅ **真正可用的内容站** |

结论：**`tianwentong.cn` 不是可用入口**；天文通对外可用的内容站是 `laysky.com`，运营方为福州触梦科技有限公司。

### 1.2 可用 HTTP 接口（已逆向并实测成功）

`https://laysky.com/event/` 页面并非纯静态：首屏是「历史快照」，联网后由前端向**独立 API 域名**拉取实时数据。
接口签名与解密逻辑取自该站公开的 ES module（`/assets/events-api.js`，可直接 GET）：

**端点**

```
GET https://api.knockdream.com/events/<ISO8601起点>/<天数>
例：https://api.knockdream.com/events/2025-02-28T20:00:00.000Z/35
    https://api.knockdream.com/events/2026-10-31T20:00:00.000Z/35
```

**请求要点**

- 无 token、无 API key、无签名头、无 Cookie。实测请求头只需普通浏览器 `User-Agent`（本次另附了 `Referer: https://laysky.com/event/`，但未验证去掉 `Referer` 是否仍返回 200 —— 该点为 `UNVERIFIED`）。
- `<ISO8601起点>`：ISO 时间，带 `Z`。**起点可任意指定（可查历史月份）** —— 这是能取到 2025-03 的关键。
- `<天数>`：窗口长度（页面用 60；本文档取 35 以覆盖整月）。
- 响应 `Content-Type` 为**密文**：Base64 的 AES-128-CBC 密文，**不是 JSON**。

**解密参数**（来自 `/assets/events-api.js` 的 `decodeEvents()`）

| 项 | 值 |
|---|---|
| 算法 | AES-128-CBC |
| Key | UTF-8 字节 `apiknockdreamcom`（16 字节） |
| IV | 与 Key 相同 |
| Padding | PKCS7 |
| 明文 | JSON 数组，元素 `{"date": "...", "event": "..."}` |

**响应形状（截断样本，2025-03 窗口前 3 条，原文照抄）**

```json
[
  {"date":"2025-03-01T04:03:00.000Z","event":"水星合月，在月球以北0.4°，部分地区可见掩食"},
  {"date":"2025-03-01T05:40:00.000Z","event":"月球过升交点"},
  {"date":"2025-03-01T21:18:00.000Z","event":"月球过近地点：361967公里"}
]
```

**时区语义（关键，容易踩坑）**

- 载荷里的 `date` **带 `Z`，是 UTC**，不是北京时间。
- 站点前端用 `Intl.DateTimeFormat("zh-CN",{timeZone:"Asia/Shanghai"})` 渲染，因此**页面上看到的是 UTC+8**。
- 校验证据：`2025-03-14T06:55:00.000Z 满月` 与 AstroPixels/NASA 的 UTC 06:55 完全一致；若当作北京时间则与三家源全部冲突。
- 实测页面渲染：载荷 `2026-11-01T20:28:00Z 下弦月` 在浏览器里显示为「11月2日 04:28 下弦月」→ 确为 UTC+8 渲染。

**精度**

- 分钟级（`hh:mm`），但**整点事件只给到小时**（如 `水星东大距`、`金星下合`、`土星合日` 均为 `:00`），说明这些事件源数据本身只有小时精度。
- 事件词表**不含「留」（行星驻留/逆行转折）**，也**不含行星所在星座**。

**可靠性判定**

- 与 AstroPixels（Espenak）、NASA GSFC 在本月窗口内**逐条分钟级一致**（见 `docs/validation/ref-2025-03.md`、`ref-2026-11.md` 的交叉核对），可靠性高。
- 但它仍是**商业 App 的私有接口**：无文档、字段语义靠逆向、可能变化或加鉴权。**只用于交叉核对，不应成为生成器的运行时依赖**。抓取请克制频率。

### 1.3 其日历/天象页面

| 页面 | 状态 | 说明 |
|---|---|---|
| `https://laysky.com/event/` | 200 | 「未来 60 天天象」，UTC+8 渲染，含「历史快照」与「实时预报」两态（`data-state="snapshot"/"loaded"`） |
| `https://laysky.com/event/meteor-shower.html` | 200 | 流星雨日历入口 |
| `https://laysky.com/event/2025-meteor-shower.html`、`2026-meteor-shower-ob.html` | 200 | 年度流星雨一览（中文，无 ZHR 精确表） |
| `https://laysky.com/event/2025-03.html`、`/event/202503.html`、`/event/index.json` | 200 但为 **9362 字节 SPA 兜底页（软 404）** | **不存在按月归档路由** |
| `https://laysky.com/content/event/README.md` | 200 | 站点内容源文件（687 B），非数据 |

> 即：天文通**没有**「2025年3月天象预报」这样的按月静态归档页；要取任意月份只能用 §1.2 的 API 传自定义起点。

---

## 2. Stellarium

### 2.1 Stellarium Web（唯一在本机可验证的界面）

- 正确域名是 **`https://stellarium-web.org/`**（HTTP 200，实测可用）。
  ⚠️ `web.stellarium.org` **DNS 不存在**（`DNS name does not exist`）；`www.stellarium.org` 只解析到 GitHub Pages 的官网，无 Web 版星图。
- **设定到指定日期/时刻与观测点：URL 查询参数（已实测生效）**

```
https://stellarium-web.org/?date=2025-03-14T06:55:00Z&lat=39.9042&lon=116.4074&alt=50
```

| 参数 | 含义 | 实测 |
|---|---|---|
| `date` | ISO 8601 时刻，带 `Z` 表示 UTC | ✅ 生效。上例加载后，界面时钟显示 **`14:55 2025-03-14`**，即 06:55 UTC 的 **UTC+8** 呈现（与目标月份一致） |
| `lat` / `lon` | 观测点纬度/经度（度，北纬/东经为正） | ✅ 接受（上例为北京） |
| `alt` | 海拔（米） | ✅ 接受 |

  注意两点：① 首次访问会弹 cookie 同意层，**同意前读到的时钟是未初始化的 MJD 纪元值（`1858-11-17`）**，别据此误判参数无效；② 时钟载入后按真实时间继续走动（实测请求 06:55:00 显示 14:55:40），所以它适合**目视/截图核对**，不适合当作精密授时来源。

- **读取天体位置**：页面是 WebGL canvas，无 DOM 文本可抓；但页面暴露 JS 对象 `window._stel`（`window.stel` 不存在）：
  - `window._stel.core` 可读写 `utc`、`longitude`、`latitude`、`elevation`、`fov`、`yaw`、`pitch` 等；
  - `window._stel` 上还有 `MJD2date` / `date2MJD` / `a2tf` / `c2s` 等换算工具与 `FRAME_OBSERVED`、`FRAME_ECLIPTIC` 等坐标系常量。
  - 即：**可以通过浏览器 console/injection 精确设置时刻与观测点**（比 URL 参数更可控）。
  - `UNVERIFIED`：用哪个具体调用读出某天体的 RA/Dec 或地平坐标 —— 未找到公开文档，本文档未逐一定位；需先在浏览器里探索 `_stel.core` 的方法表。**不要假设它存在**。
- **可无头脚本化程度**：本机 `dsh_browser_*`（真实 Chromium）能加载、能执行 JS、能截图，因此「设定时刻 → 截图/读 canvas」这条链路**是可自动化的**；但它**不返回结构化数字**（除非破解上述 core API），所以只适合**抽检（spot-check）**，不适合批量取数。

### 2.2 Stellarium Remote Control HTTP API（`/api/...`）

- 该 API 属于**桌面版 Stellarium** 的 Remote Control 插件，默认监听 `http://localhost:8090/`，接口形如 `/api/main/status`、`/api/main/view`、`/api/objects/find` 等。
- **本机实测：不可用** —— `Test-NetConnection 127.0.0.1:8090` 返回 `False`（无进程监听），`http://localhost:8090/api/main/status`、`http://127.0.0.1:8090/` 全部 `curl 000`。
- 判定：**`UNVERIFIED`**。需要先安装并运行桌面版 Stellarium 且启用 Remote Control 插件，本文档无法在此环境确认其返回结构。

### 2.3 `.ssc` 脚本

- `.ssc` 是桌面版 Stellarium 的脚本引擎（可 `core.setDate()`、`StelMovementMgr`、`core.getObjectInfo()` 等），**必须在桌面版 GUI 内运行**。
- 判定：**不可无头运行**（本机无桌面版 Stellarium 安装/无法在此环境验证）→ `UNVERIFIED`，不适合作为 CI 参照源。
- 结论：三个界面里，**只有 Stellarium Web 的 URL 参数可用于本机抽检**；Remote Control 与 `.ssc` 都需要桌面版实例，本环境无法验证。

---

## 3. 其他数据源（≥4，均实测）

> 图例：✅ 实测 HTTP 200 且取到数据；⚠️ 可达但有反爬/无目标数据；❌ 不可达。

### 3.1 NASA GSFC 月相表 — ✅ **强烈推荐（月相第二源）**
- URL：`https://eclipse.gsfc.nasa.gov/phase/phases2001.html` → **HTTP 200**（128 KB）
- 内容：2001–2100 每年「朔/上弦/望/下弦」四列，**UT**，精确到分钟；望/朔后带 `T/A/H/P`、`t/p/n` 标食类型。
- 精度/单位：分钟；时间基准 UT。表格注明 ΔT 修正（`00h01m`）。
- 用途：**月相时刻的独立第二源**（与 AstroPixels、天文通三方对齐）。
- 授权：NASA/GSFC 公开发布，学术/教学引用需注明 NASA Eclipse Web Site（Espenak）。无明确再分发限制，但请注明出处。

### 3.2 NASA SKYCAL / GSFC 食表 — ✅ 可达
- SKYCAL 生成器：`https://astropixels.com/skycal/skycalmain.html` → **HTTP 200**（GSFC 版的镜像，客户端 JS 生成事件表）。
- 日食十年页：`https://eclipse.gsfc.nasa.gov/SEdecade/SEdecade2021.html` → **HTTP 200**。
- 用途：食象核对、事件表生成器（注意：SKYCAL 是**计算器**，不是现成表格，取值等于「用别人的引擎算」，仅宜作旁证）。
- 授权：NASA 公有领域（SKYCAL 镜像页含 Espenak 版权声明）。

### 3.3 AstroPixels Sky Event Almanac（Fred Espenak）— ✅ **最主力来源**
- 索引：`https://astropixels.com/almanac/almanac.html` → **HTTP 200**
- 全年事件表（21 世纪，24 个时区）：
  - UTC：`https://astropixels.com/almanac/almanac21/almanac2025gmt.html`、`almanac2026gmt.html` → **HTTP 200**
  - 其他时区把 `gmt` 换成 `pst/cst/est/ast/art/akst/hst/cvt/cet/eet/msk/gst` 等（**没有 UTC+8 版本**，只有 GMT 最方便 +8）。
  - ✅ **实测存在 UTC+9 版（`jst`，日本标准时）与 UTC+7 版（`ict`）**：
    `https://astropixels.com/almanac/almanac21/almanac2025jst.html`、`almanac2026jst.html` → **HTTP 200**。
    因为 **北京时间 = JST − 1 小时**，JST 版可作为**换算的算术校验**（本任务已用它逐条复核两份 ref 文档，见各文件 §10）。
  - ⚠️ 实测 **404** 的猜测路径（不要猜）：`almanac2025utc.html`、`almanac2025hkt.html`、`almanac2025sgt.html`、`almanac2025pht.html`、`almanac2025chst.html`、`almanac2026hkt.html`、`almanac21/almanac2025.html`（无年份裸页）。
  - 同页附「2025 Phases of the Moon」四列表，与 3.1 互为校验。
- 覆盖：月相、月球近/远地点（含 km）、升/降交点、行星合月/合恒星、**水金大距**、**上下合**、**外行星冲日/合日**、二分二至、流星雨（仅列名、无 ZHR）、日月食食分。
- 精度（页面自述）：月相 ±0.5 min；近/远地点 ±5 min、±5 km；大距/上下合 ±30 min；外行星冲/合 ±3 h；**整点事件 ±30 min**。
- 授权：页面明示 —— 可自由转载，须附「*Sky Event Almanacs Courtesy of Fred Espenak, www.AstroPixels.com*」。
- **不含**：行星「留」（stations）、行星所在星座。

### 3.4 国立天文台 暦要項（NAOJ）— ✅ **节气最佳来源（本任务关键发现）**
- 令和7年(2025)：`https://eco.mtk.nao.ac.jp/koyomi/yoko/2025/rekiyou252.html` → **HTTP 200**（Shift_JIS 编码！）
- 令和8年(2026)：`https://eco.mtk.nao.ac.jp/koyomi/yoko/2026/rekiyou262.html` → **HTTP 200**
- 同系列：`rekiyou251`=国民の祝日、`253`=朔弦望（月相，JST）、`254`=東京の日出入、`255`=日食・月食；`256+` 为 404。
- 内容：**二十四節気 + 雑節，精确到分，日本中央標準時（JST = UTC+9）**，并给出太阳黄经度数（285°/300°/…/0°=春分）。
- 换算：**北京时间 = JST − 1 小时**（整数小时，无分钟歧义）。
- 精度：分钟；官方历算机构（日本国立天文台历计算室），**权威度高**。
- 授权：页面「利用規定」链接在站内；学术引用请注明「国立天文台暦計算室 暦要項」。转载前请阅读其利用规定。
- 注意：**无行星现象（无大距/冲/合/留）**，只有历法类项目。

### 3.5 香港天文台 HKO 公曆與農曆對照表 — ✅ **节气日期旁证**
- `https://www.hko.gov.hk/tc/gts/time/calendar/text/files/T2025c.txt`、`T2026c.txt` → **HTTP 200**（各 23,536 B，纯文本，Big5/UTF-8）
- 内容：逐日的农历日期、星期、**节气名（仅有日期，无时刻）**。
- 用途：校验节气**落哪一天**（与 NAOJ 的时刻换算结果比对日期）。
- 授权：香港天文台，政府公开资料；引用注明 HKO。

### 3.6 IMO 流星雨年历（International Meteor Organization）— ✅ **ZHR 权威来源**
- 年历 PDF：`https://www.imo.net/files/meteor-shower/cal2025.pdf`（**HTTP 200**，2.9 MB）、`cal2026.pdf`（**HTTP 200**，988 KB）
- 内容：Table 5「Working List of Visual Meteor Showers」——每条含 活动期、极大日期（含 λ⊙）、辐射点 α/δ、V∞、r、**ZHR**；正文另给各群极大时刻（如 Leonids 2026-11-17 23h45m UT）。
- 精度：极大日期以太阳黄经 λ⊙ 给出（等效日期），个别群给到分钟（狮子座流星雨节点穿越）。
- ⚠️ `https://www.imo.net/resources/calendar/` 与 `/resources/meteor-showers/` 均 **404**（旧 URL 已废）。
- 授权：IMO 出版物，引用请注明 IMO Meteor Shower Calendar（IMO INFO 系列）。

### 3.7 其余来源一览

| 来源 | URL | 实测状态 | 最适合 | 备注 / 授权 |
|---|---|---|---|---|
| **USNO Astronomical Applications API** | `https://aa.usno.navy.mil/api/moon/phases/date?date=2025-03-01&nump=4`；`/api/seasons?year=2025&tz=8` | ❌ **DNS 解析失败**（`getaddrinfo EAI_AGAIN` / `DNS server failure`） | 本可给月相/节气/日月出没的权威 API（支持 `tz=8` 直接出北京时间） | 本机对 `.mil` 域不可达，**无法使用**。公有领域（美国政府作品） |
| **JPL Horizons** | `https://ssd.jpl.nasa.gov/api/horizons.api?...` | ❌ **TCP 连接超时**（`Failed to connect ... after 21133 ms`；DNS 能解析到 137.78.251.144） | 本可做任意天体任意时刻的高精度视位置（可反推「留」与星座） | 网络层被阻断，**无法使用**。NASA 公有领域 |
| **In-The-Sky.org** | `https://in-the-sky.org/newscal.php?year=2025&month=3`（可加 `&maxdiff=1`） | ⚠️ **HTTP 200，但先遇 Anubis 反爬挑战**（「正在确认你是不是机器人」）。**用真实浏览器 `dsh_browser_*` 等待约 9 秒后自动通过**；`curl` 只能拿到挑战页 | 按月的日历式事件清单（英文）、日月食/掩星/流星雨条目、事件专页 | 仅给到**日期**（日历视图不显示时刻）；默认观测点为 Washington；**不含「留」**。站长 Dominic Ford，引用注明 In-The-Sky.org |
| **timeanddate.com** | `https://www.timeanddate.com/moon/phases/china/beijing?year=2025&month=3` | ❌ **HTTP 403 + Cloudflare「Just a moment…」**（`web_fetch` 命中挑战页；**未再用浏览器重试**，避免与反爬纠缠） | 北京时间月相/日月出没网页 | 反爬拦截，本机取不到。商用内容，转载受限 |
| **IMCCE（法国经度局）** | `https://ssp.imcce.fr/`、`https://ssp.imcce.fr/forms/ephemeris` | ✅ 均 **HTTP 200**（`https://www.imcce.fr/` 反而 `000`） | 行星/卫星高精度历表与在线历表表单 | 本次未深入取数；其「行星留」未见现成年度表。引用注明 IMCCE |
| **Heavens-Above** | `https://heavens-above.com/PlanetSummary.aspx` | ✅ **HTTP 200** | 行星可见性/星等/星座的观测视角汇总 | 本次未逐项取数；页面按观测点渲染，需设地点 |
| **Minor Planet Center** | `https://www.minorplanetcenter.net/`、`https://www.minorplanetcenter.net/iau/mpec/K25/K25A01.html` | ✅ **HTTP 200** | 小行星/彗星历表、MPEC 公告 | 与「月度天象」关系弱；引用注明 MPC |
| **紫金山天文台（PMO）** | `https://www.pmo.cas.cn/` | ❌ **连接失败（000）**，DNS 可解析到 159.226.242.62 | 本可作《中国天文年历》节气/天象的国内权威 | 不可达。**《中国天文年历》无免费在线版**，未获取 |
| **中央氣象署（台湾）** | `https://www.cwa.gov.tw/V8/C/K/astronomy_day.html` | ❌ 被判定「解析到非公网 IP」而拒绝 | 中文节气/天象（含时刻） | 不可达 |
| **臺北市立天文科學教育館** | `https://tam.gov.taipei/`（如 `News_Content.aspx?n=B64052C7930D4913&s=22B29BF800549508` = 2026年3月天象概要） | ❌ 连接失败（000） | 中文「每月天象概要」，理想来源 | 不可达；搜索结果可见其存在但取不到正文 |
| **有趣天文奇观（china-vo.org）** | `https://interesting-sky.china-vo.org/` | ⚠️ HTTP 200 但内容是 **cPanel 默认页**（`/cgi-sys/defaultwebpage.cgi`） | 本为中文月度天象预报站 | **站点已无内容**，不可用 |
| **香港太空館** | `https://hk.space.museum/sc/web/spm/home.html` | ✅ **HTTP 200** | 馆务/天象厅节目 | 首页导航**未见**逐月天象数据入口（仅「天象厅节目」「参观资料」等），**未遍历全站**；本任务判定其不适合取值 |
| **NASA 日食十年页** | `https://eclipse.gsfc.nasa.gov/SEdecade/SEdecade2021.html` | ✅ **HTTP 200** | 日月食目录与食分 | 见 3.1/3.2 |

---

## 4. 选源建议（给生成器交叉验证用）

| 数据项 | 首选 | 次选（交叉核对） | 本机是否可得 |
|---|---|---|---|
| 月相（朔/上弦/望/下弦） | AstroPixels GMT | NASA GSFC 月相表 + 天文通 API | ✅ 三方齐 |
| 节气（含时刻） | NAOJ 暦要項（JST−1h） | HKO 校日期；二分二至再用 AstroPixels | ✅ |
| 月球近/远地点 | AstroPixels（含 km） | 天文通 API | ✅ |
| 水金大距 / 上下合 | AstroPixels | 天文通 API | ✅（整点事件仅小时精度） |
| 外行星冲日/合日 | AstroPixels | 天文通 API | ✅（整点事件仅小时精度） |
| **行星「留」** | **无权威可得** | 仅占星界历表（低置信，见 ref 文档） | ❌ 见下 |
| 流星雨 ZHR | IMO 年历 PDF | AstroPixels（仅日期）/ 天文通（仅名称） | ✅ |
| 中文全量天象清单 | 天文通 API（`api.knockdream.com`） | In-The-Sky（英文、仅日期） | ✅ |
| 行星所在星座（视位置） | **未获取** | — | ❌ 见下 |

### 明确的缺口（不要把「未获取」当成「没有」）

1. **行星「留」（stationary）**：USNO（`.mil`）与 JPL Horizons 均被网络阻断；In-The-Sky 的日历**不含**留；天文通事件词表**不含**留；NAOJ 暦要項只有历法项。
   → 本机只能找到**占星行业用 Swiss Ephemeris 计算的站点**（见 `ref-2026-11.md` 的「低置信度旁证」），**不建议**作为验证基准。
2. **行星所在星座（月初/月末视位置）**：需要按日期查星表（Horizons `QUANTITIES` 或 Stellarium 读数），两者在本机都不成体系（前者不可达，后者无结构化输出）。
   → 两份 ref 文档中该项均记为 **未获取**。