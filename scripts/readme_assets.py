# /// script
# requires-python = ">=3.10"
# dependencies = ["rich==14.2.0", "sluicer"]
#
# [tool.uv.sources]
# sluicer = { path = "..", editable = true }
# ///
"""Regenerate the pictures the README shows, from the code and the scoreboards.

    uv run scripts/readme_assets.py

``docs/assets/inspect.svg`` is ``sluicer inspect`` run on
``examples/brake-pads.html``, drawn as a terminal: the output itself, not a
mock-up of it. ``docs/assets/dates-light.svg`` and ``dates-dark.svg`` chart the
date columns of ``docs/scoreboard-served.md`` as published, so the picture and
the table cannot say two things.
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"
PAGE = "examples/brake-pads.html"
URL = "https://example.com/p/bp-2210"


def inspect_svg() -> None:
    command = [
        str(Path(sys.executable).parent / "sluicer"),
        "inspect",
        PAGE,
        "--url",
        URL,
    ]
    output = subprocess.run(
        command, cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout
    # As wide as the longest line, so no line wraps as a terminal would not.
    width = max(len(line) for line in output.splitlines()) + 1
    console = Console(
        record=True, width=width, force_terminal=True, color_system="truecolor"
    )
    console.print(Text(f"$ sluicer inspect {PAGE.split('/')[-1]}", style="bold"))
    for line in output.rstrip("\n").splitlines():
        text = Text(line)
        text.highlight_regex(
            r"^(page|readers|links|rights|records|summary)\b", "bold #7aa2f7"
        )
        text.highlight_regex(r"\[[^\]]+\]\s*$", "#73daca")
        text.highlight_regex(r"conflict: .*", "bold #e0af68")
        text.highlight_regex(r"^\s{6}\S+(?=\s+\[)", "#e0af68")
        console.print(text)
    ASSETS.joinpath("inspect.svg").write_text(
        console.export_svg(title="sluicer inspect"), encoding="utf-8"
    )


def _served_dates() -> list[tuple[str, float, float, int]]:
    """Each tool's date row on the pages as served: name, hit rate, right when
    answering, inventions, read off the published scoreboard."""
    table = (ROOT / "docs" / "scoreboard-served.md").read_text(encoding="utf-8")
    rows = []
    for line in table.splitlines():
        cells = [cell.strip().strip("*") for cell in line.strip("|").split("|")]
        if len(cells) == 11 and cells[1] == "date":
            rows.append((cells[0], float(cells[4]), float(cells[6]), int(cells[10])))
        if len(rows) == 4:
            break
    return rows


def dates_svg(dark: bool) -> str:
    rows = _served_dates()
    ink, muted, grid = (
        ("#e6edf3", "#8b949e", "#30363d") if dark else ("#1f2328", "#59636e", "#d1d9e0")
    )
    found, right = "#58a6ff", "#3fb950"
    width, left, bar_width, row_height = 760, 190, 500, 58
    height = 96 + row_height * len(rows)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="-apple-system, Segoe UI, '
        'Helvetica, Arial, sans-serif">',
        f'<text x="{left}" y="26" font-size="15" font-weight="600" fill="{ink}">'
        "Publication dates on 360 real pages, as their servers sent them</text>",
        f'<rect x="{left}" y="40" width="12" height="12" rx="2" fill="{found}"/>',
        f'<text x="{left + 18}" y="51" font-size="12" fill="{muted}">'
        "found (hit rate)</text>",
        f'<rect x="{left + 150}" y="40" width="12" height="12" rx="2" fill="{right}"/>',
        f'<text x="{left + 168}" y="51" font-size="12" fill="{muted}">'
        "right when it answers</text>",
    ]
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = left + bar_width * tick
        parts.append(
            f'<line x1="{x:.1f}" y1="66" x2="{x:.1f}" y2="{height - 22}" '
            f'stroke="{grid}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{height - 6}" font-size="11" fill="{muted}" '
            f'text-anchor="middle">{tick:.2f}</text>'
        )
    for index, (name, hit, correct, invented) in enumerate(rows):
        top = 72 + row_height * index
        label = html.escape(re.sub(r"\s+\d[\w.]*$", "", name))
        weight = "700" if label == "sluicer" else "400"
        parts.append(
            f'<text x="{left - 12}" y="{top + 17}" font-size="14" '
            f'font-weight="{weight}" fill="{ink}" text-anchor="end">{label}</text>'
        )
        parts.append(
            f'<text x="{left - 12}" y="{top + 34}" font-size="11" fill="{muted}" '
            f'text-anchor="end">{invented} dates invented</text>'
        )
        for offset, value, colour in ((0, hit, found), (21, correct, right)):
            parts.append(
                f'<rect x="{left}" y="{top + offset}" width="{bar_width * value:.1f}" '
                f'height="17" rx="3" fill="{colour}"/>'
            )
            parts.append(
                f'<text x="{left + bar_width * value + 6:.1f}" y="{top + offset + 13}" '
                f'font-size="12" fill="{ink}">{value:.3f}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _swde_rows() -> list[tuple[str, float, float, int]]:
    """Each tool's row on SWDE: name, mean F1, right when answering, wrong
    answers, read off the published scoreboard."""
    table = (ROOT / "docs" / "scoreboard-swde.md").read_text(encoding="utf-8")
    scores: dict[str, tuple[float, float]] = {}
    wrong: dict[str, int] = {}
    for line in table.splitlines():
        cells = [cell.strip().strip("*") for cell in line.strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"\d\.\d{3}", cells[1]):
            scores.setdefault(cells[0], (float(cells[1]), float(cells[2])))
        elif len(cells) == 4 and re.fullmatch(r"[\d,]+", cells[1]):
            wrong.setdefault(cells[0], int(cells[1].replace(",", "")))
    return [(name, f1, right, wrong[name]) for name, (f1, right) in scores.items()]


def swde_svg(dark: bool) -> str:
    """The README's first chart: extractors learnt from three pages of a site
    and replayed on the rest, beside Scrapling's adaptive selectors."""
    rows = _swde_rows()
    ink, muted, grid = (
        ("#e6edf3", "#8b949e", "#30363d") if dark else ("#1f2328", "#59636e", "#d1d9e0")
    )
    score, right = "#58a6ff", "#3fb950"
    width, left, bar_width, row_height = 760, 210, 480, 62
    height = 100 + row_height * len(rows)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="-apple-system, Segoe UI, '
        'Helvetica, Arial, sans-serif">',
        f'<text x="{left}" y="26" font-size="15" font-weight="600" fill="{ink}">'
        "Learnt from 3 pages, read on 124,291 pages of 80 real sites (SWDE)</text>",
        f'<rect x="{left}" y="40" width="12" height="12" rx="2" fill="{score}"/>',
        f'<text x="{left + 18}" y="51" font-size="12" fill="{muted}">mean F1</text>',
        f'<rect x="{left + 110}" y="40" width="12" height="12" rx="2" fill="{right}"/>',
        f'<text x="{left + 128}" y="51" font-size="12" fill="{muted}">'
        "right when it answers</text>",
    ]
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = left + bar_width * tick
        parts.append(
            f'<line x1="{x:.1f}" y1="66" x2="{x:.1f}" y2="{height - 22}" '
            f'stroke="{grid}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{height - 6}" font-size="11" fill="{muted}" '
            f'text-anchor="middle">{tick:.2f}</text>'
        )
    for index, (name, f1, correct, wrong) in enumerate(rows):
        top = 74 + row_height * index
        label = html.escape(re.sub(r"\s+\d[\w.]*(, adaptive)?$", "", name))
        weight = "700" if label == "sluicer" else "400"
        parts.append(
            f'<text x="{left - 12}" y="{top + 17}" font-size="14" '
            f'font-weight="{weight}" fill="{ink}" text-anchor="end">{label}</text>'
        )
        parts.append(
            f'<text x="{left - 12}" y="{top + 34}" font-size="11" fill="{muted}" '
            f'text-anchor="end">{wrong:,} wrong answers</text>'
        )
        for offset, value, colour in ((0, f1, score), (21, correct, right)):
            parts.append(
                f'<rect x="{left}" y="{top + offset}" width="{bar_width * value:.1f}" '
                f'height="17" rx="3" fill="{colour}"/>'
            )
            parts.append(
                f'<text x="{left + bar_width * value + 6:.1f}" y="{top + offset + 13}" '
                f'font-size="12" fill="{ink}">{value:.3f}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    inspect_svg()
    ASSETS.joinpath("dates-light.svg").write_text(
        dates_svg(dark=False), encoding="utf-8"
    )
    ASSETS.joinpath("dates-dark.svg").write_text(dates_svg(dark=True), encoding="utf-8")
    ASSETS.joinpath("swde-light.svg").write_text(swde_svg(dark=False), encoding="utf-8")
    ASSETS.joinpath("swde-dark.svg").write_text(swde_svg(dark=True), encoding="utf-8")
    print("wrote docs/assets/inspect.svg, dates-*.svg, swde-*.svg")


if __name__ == "__main__":
    main()
