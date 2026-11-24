# auto-astro-calendar

English | [简体中文](README.zh-CN.md)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat)](#requirements)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat)](LICENSE)
[![Source](https://img.shields.io/badge/GitHub-source-24292e?style=flat)](https://github.com/OverDustD7/auto-astro-calendar)

Generate a Chinese monthly astronomy forecast as Word, JSON and Markdown, with an optional moon-phase calendar image. The calculation, Chinese narrative and document layout are separate modules.

## Status and support

The repository supplies a skill and command-line scripts. The skill metadata identifies version 1.1.0; this does not identify a newly published package. Existing example reports and recorded numerical checks are reference evidence, not a guarantee for every month or location.

## Requirements

- Python 3.10 or later, `astronomy-engine`, `python-docx` and Pillow.
- The current moon-image renderer searches the Windows fonts directory for a Chinese font. Other systems need a font lookup adaptation; cross-platform moon rendering has not been verified.
- The moon sprite is **not** distributed with this repository. The renderer downloads it on first use, or you can pass your own figure with `--moon-image`. Cached generation runs offline.

## Installation

Download the source from this repository and install the Python dependencies in your chosen environment:

```bash
python -m pip install astronomy-engine python-docx Pillow
```

The original project code and documentation are licensed under MIT. Check the license section before redistributing examples or assets.

## Quick start

Run from the repository root:

```bash
python scripts/moon_grid.py --year 2026 --month 11 --out assets/moon-2026-11.png
python scripts/make_calendar.py --year 2026 --month 11 \
    --moon-image assets/moon-2026-11.png \
    --moon-caption "（图源 NASA/Goddard，经 Calendar-12）"
```

The figure caption is yours to supply: the script cannot tell where an arbitrary image came from, so it never writes a source credit on its own.

Expected outputs are `out/天象预报 2026年11月.docx`, the matching `.json` and `.md`. Without `--moon-image`, the document contains a note instead of a calendar image.

Use `--city`, `--lat` and `--lon` to set the observing context, and `--venue-label` to change the local observing-difficulty label. See [the skill instructions](SKILL.md) for the layout contract and remaining options.

## Data and permissions

The scripts read bundled data and write reports, image output and a cached sprite. The first sprite download contacts Calendar-12.com. No account or administrator access is required for document generation; installing dependencies has its own network activity.

Report JSON records the selected city, coordinates and generation time. Inspect these values, document properties, filenames and image metadata before sharing a report. A generic sample location does not establish a user's actual location. Never add private observations, local paths or credentials to published examples.

## Upgrade and removal

Preserve wanted reports and customized reference data before replacing source. Remove this source directory and its generated files to remove the tool; manage the Python environment separately. No service or scheduled task is installed by these generation commands.

## Limitations and troubleshooting

The difficulty labels describe light pollution, not personal identity. Location, time zone, event definitions and unsupported eclipse measurements affect interpretation. Read [conventions](docs/CONVENTIONS.md), [known issues](docs/KNOWN_ISSUES.md) and [data sources](docs/DATA_SOURCES.md). Example reports preserve their original context.

## Development

```bash
python tests/test_format.py
python tests/test_accuracy.py
python tests/test_content.py
```

These are the repository's regression entry points. Historical records describe a 16-case numerical comparison with independent references; this documentation change does not claim a new scientific or rendering verification. [Release preparation](docs/RELEASING.md) defines the checks for actual distribution bytes.

The [Chinese README](README.zh-CN.md) preserves the original module table, commands and source acknowledgements. The format test works from `tests/fixtures/sample-reference.json`, which records only the measured layout structure (paragraph roles, page geometry, style values) and contains no third-party prose. Example reports in `examples/` carry no embedded figure; see [third-party notices](THIRD_PARTY_NOTICES.md) for what is excluded and how to regenerate it locally.

## Feedback and security

Report non-sensitive defects through the repository's [Issues](https://github.com/OverDustD7/auto-astro-calendar/issues). No private security-report channel is documented. Do not attach real coordinates, personal document metadata or unredacted logs to public reports.

## License and third-party notices

The original project code and original documentation are licensed under the [MIT License](LICENSE). No third-party imagery or third-party prose is distributed in this repository: the moon sprite is downloaded at runtime, example reports embed no figure, and the original screenshot-bearing layout sample is excluded. Dependencies and the factual reference data retain their own rights and attribution; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the per-item breakdown and the still-open questions. Preserve [data-source notes](docs/DATA_SOURCES.md) and other third-party notices.
