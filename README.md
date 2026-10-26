# auto-astro-calendar

生成任意年月的中文《天象预报》Word 文档，排版对齐 `天象预报 2024年12月.docx`。

```bash
pip install astronomy-engine python-docx Pillow

# 1) 月相日历图（首次会自动下载月面照片雪碧图到 assets/phases.jpg）
python scripts/moon_grid.py --year 2026 --month 11 --out assets/moon-2026-11.png

# 2) 生成文档
python scripts/make_calendar.py --year 2026 --month 11 --moon-image assets/moon-2026-11.png
```

产出 `out/天象预报 2026年11月.docx`，外加同名 `.json`（全部结构化事实）与 `.md`（纯文本版）。

`examples/` 里放了几份已审阅的成品（2027-03、2027-04），可直接对照观感；`out/` 是默认输出目录，不入库。

观测难度里的「校内 / 郊区」评的是光污染，样本作者的「校内」指**清华校园**。换观测地时用 `--venue-label 市区` 之类改这个叫法，可见性口径用 `--city/--lat/--lon`。

## 结构

| 路径 | 作用 |
|---|---|
| `SKILL.md` | **给智能体看的技能说明**：何时用、怎么跑、格式契约、改代码指引 |
| `scripts/astro_core.py` | 历算内核：只算事实，不出中文 |
| `scripts/report.py` | 挑事件、写中文措辞 |
| `scripts/docx_writer.py` | 排版：不懂天文，只按规格写 docx |
| `scripts/moon_grid.py` | 月相日历图（真实月面照片 + 中文网格） |
| `scripts/make_calendar.py` | 命令行入口 |
| `scripts/crop_calendar.py` | 备用：把网页截图裁成干净图（换图源时用） |
| `scripts/data/*.json` | 流星雨、深空目标参考表 |
| `tests/test_format.py` | 排版回归：用样本文字重跑，逐段比对 |
| `tests/test_accuracy.py` | 数值回归：对 4 家外部历表核 2025-03 |
| `docs/CONVENTIONS.md` | 每个天象的口径定义与验证结果 |
| `docs/KNOWN_ISSUES.md` | 已知问题与取舍（含与样本的差异逐条说明） |
| `docs/DATA_SOURCES.md` | 外部数据源实测可用性（含天文通真实 API） |
| `docs/validation/` | 两个月的独立参考基准（逐条带 URL） |

## 验证

```bash
python tests/test_format.py     # 格式与样本一致
python tests/test_accuracy.py   # 16 项数值对 4 家独立历表，全通过
```

## 数据来源与致谢

- 历算：`astronomy-engine`（基于 Meeus《Astronomical Algorithms》）。
- 月面照片：NASA / Goddard Space Flight Center Scientific Visualization Studio（公有领域），经 Calendar-12.com 雪碧图分发。
- 流星雨 ZHR：IMO Meteor Shower Calendar 工作列表。
- 核对基准：AstroPixels（Fred Espenak）、NASA GSFC、天文通 API、NAOJ 暦要項、HKO、IMO。
