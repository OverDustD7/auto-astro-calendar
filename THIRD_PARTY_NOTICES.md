# 第三方材料与授权范围

本文件说明：哪些内容是本项目自有、按 MIT 授权；哪些是第三方材料、本仓库
**不**分发；以及运行时会访问哪些外部资源。

## 一、MIT 覆盖范围

[LICENSE](LICENSE)（MIT）覆盖**本项目自行编写的代码与文档**：

- `scripts/*.py`、`tests/*.py`
- `README.md`、`README.zh-CN.md`、`SKILL.md`、`AGENTS.md`
- `docs/*.md`（含 `docs/validation/*.md` 中本项目的整理与评注）
- `tests/fixtures/sample-reference.json`（本项目实测整理的结构数据）

## 二、本仓库不分发的材料

| 材料 | 为什么不分发 | 替代方式 |
|---|---|---|
| 月相照片雪碧图（`assets/phases.jpg`，Calendar-12.com 分发） | 是第三方站点的合成素材，再分发条款未核实 | 首次渲染时由 `scripts/moon_grid.py` 从源站下载并缓存；条款由使用者自行确认。也可用 `--moon-image` 传入自有图片 |
| 示例文档中的月相日历图 | 由上述雪碧图拼版，同属未核实素材 | `examples/` 中的示例不含图；需要图文版时本地运行 `scripts/moon_grid.py` 自行生成 |
| 原版排版样张 `天象预报 2024年12月.docx` | 内嵌 Star Walk 月历截图（第三方图片），且文档属性含他人姓名与学号 | 不进仓库、不进分发包。版式特征已实测为结构基准（见下） |
| 样张的逐段正文 | 系他人撰写的社团会刊文字，无再分发依据 | 结构基准只保留段落角色序列与样式数值，不保留任何正文措辞 |

`tests/fixtures/sample-reference.json` 里只有：段落角色序列、页面几何、
Normal 样式数值、内联图宽度、分隔符字符、事件行形式规则。**没有样张正文**。

## 三、随包分发的事实性数据

下列文件是天文事实的整理，随包分发，标注来源：

| 文件 | 内容 | 来源 |
|---|---|---|
| `scripts/data/meteor_showers.json` | 流星雨极大日期、ZHR、辐射点、母体 | IMO Meteor Shower Calendar 工作列表 |
| `scripts/data/deep_sky.json` | 深空天体编号与通行中文名、逐月可见性 | 公开星表与天文年历（逐条记于文件内 `sources`） |
| `docs/validation/ref-2025-03.md`、`ref-2026-11.md` | 两个月的天象时刻核对表 | AstroPixels、NASA GSFC、天文通 API、NAOJ、HKO、IMO；逐行附 URL |
| `docs/DATA_SOURCES.md` | 数据源可用性实测记录 | 同上，逐条附 URL |

其中 `ref-*.md` 为核对方便，转载了来源的**当月天象条目**：时刻、角距、事件名
这类事实性短句（如「水星合月，在月球以北0.4°」），逐条注明出处。它们不是成篇
文字，也不含第三方接口的密钥或载荷二进制；如来源方另有要求，可退化为只保留
数值列。

## 四、运行时网络访问

- 首次渲染月相图时，`moon_grid.py` 会 `GET https://www.calendar-12.com/media/images/phases.jpg`
  并写入 `assets/phases.jpg`（已列入 `.gitignore`）。之后再渲染走本地缓存，可离线。
- 生成文档本身**不联网**；所有天文计算在本机完成。
- 安装 Python 依赖时的网络访问由 pip 负责，与本项目无关。

## 五、依赖许可

| 依赖 | 本项目验证到的版本 | 许可 |
|---|---|---|
| `astronomy-engine` | 2.1.19 | MIT（Copyright 2019-2022 Don Cross） |
| `python-docx` | 1.2.0 | MIT |
| `Pillow` | 12.3.0 | HPND（PIL 系许可；元数据未声明，按上游 LICENSE 计） |
| `lxml`（python-docx 间接依赖） | 6.1.3 | BSD-3-Clause |

依赖本身不随本仓库分发，由使用者通过 pip 安装，各自许可随包。

## 六、仍待确认的项

1. **已发布历史中的旧素材**：仓库既有提交（`v1.0.0` 及其后一次提交）里仍
   含 `assets/phases.jpg`、带图的示例文档与含正文的旧版 fixture。本候选不再
   包含它们，但**未重写历史**（该动作需单独授权）。
2. **`ref-*.md` 的短句引用**：属事实条目，但若来源方主张编排权，需改为纯数值。
3. **月相图默认图源的许可**：Calendar-12 的雪碧图条款未核实；若要长期公开
   分发带图示例，建议改用 NASA SVS 原始图像自行按相位选图。
