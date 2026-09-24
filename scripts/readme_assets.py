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


# What goes in and what comes out, for the README's first picture: the
# scoreboards measure a few fields, and this says what the rest of it reads.
_INPUTS = (
    ("One page", "HTML you have, or a URL"),
    ("A whole site", "sluicer map, sluicer crawl"),
    ("A list of URLs", "sluicer batch"),
    ("Feeds and web archives", "sluicer feed, sluicer warc"),
)
_OUTPUTS = (
    (
        "Every record the page declares",
        "Product, Article, Recipe, Event, Person, any schema.org type,",
        "8 vocabularies merged, each value with its source and place",
    ),
    (
        "A summary of 25 questions",
        "title, author, dates, price, currency, availability, GTIN,",
        "brand, SKU, rating, breadcrumb, and every conflict between them",
    ),
    (
        "Any field you show it once",
        "price=41.90, an ISBN, a phone: learnt from 3 pages of a site,",
        "then checked on every page it reads",
    ),
    (
        "The rows of a listing",
        "a category page's products, a table's lines,",
        "on pages that declare nothing (--induce)",
    ),
    (
        "The main text as Markdown",
        "the article a reader came for,",
        "without menus, footers and cards",
    ),
    (
        "A loud failure when a site changes",
        "exit 3 instead of nulls for weeks, and heal says",
        "where each field moved",
    ),
)


def reads_svg(dark: bool) -> str:
    """What Sluicer takes in and what it gives back, on one picture."""
    ink, muted, card, edge = (
        ("#e6edf3", "#8b949e", "#161b22", "#30363d")
        if dark
        else ("#1f2328", "#59636e", "#f6f8fa", "#d1d9e0")
    )
    accent, accent_ink = ("#58a6ff", "#0d1117") if dark else ("#0969da", "#ffffff")
    width, row = 900, 74
    height = 64 + row * len(_OUTPUTS)
    left_w, mid_x, mid_w, right_x = 220, 262, 136, 440
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="-apple-system, Segoe UI, '
        'Helvetica, Arial, sans-serif">',
        f'<text x="0" y="22" font-size="13" font-weight="600" fill="{muted}" '
        'letter-spacing="1">YOU GIVE IT</text>',
        f'<text x="{right_x}" y="22" font-size="13" font-weight="600" fill="{muted}" '
        'letter-spacing="1">IT GIVES YOU BACK</text>',
    ]
    body_top = 40
    body_h = row * len(_OUTPUTS) - 10
    in_h = (body_h - 12 * (len(_INPUTS) - 1)) / len(_INPUTS)
    centre = body_top + body_h / 2
    for index, (name, how) in enumerate(_INPUTS):
        top = body_top + index * (in_h + 12)
        parts.append(
            f'<rect x="0.5" y="{top:.1f}" width="{left_w}" height="{in_h:.1f}" rx="8" '
            f'fill="{card}" stroke="{edge}"/>'
        )
        parts.append(
            f'<text x="16" y="{top + in_h / 2 - 3:.1f}" font-size="15" '
            f'font-weight="600" fill="{ink}">{html.escape(name)}</text>'
        )
        parts.append(
            f'<text x="16" y="{top + in_h / 2 + 16:.1f}" font-size="12" '
            f'font-family="ui-monospace, SFMono-Regular, Menlo, monospace" '
            f'fill="{muted}">{html.escape(how)}</text>'
        )
        y = top + in_h / 2
        parts.append(
            f'<path d="M{left_w + 1} {y:.1f} C{left_w + 24} {y:.1f} {mid_x - 24} '
            f'{centre:.1f} {mid_x} {centre:.1f}" fill="none" stroke="{edge}" '
            'stroke-width="1.5"/>'
        )
    parts.append(
        f'<rect x="{mid_x}" y="{centre - 52:.1f}" width="{mid_w}" height="104" rx="12" '
        f'fill="{accent}"/>'
    )
    for dy, text, size, weight in (
        (-14, "sluicer", 20, "700"),
        (10, "no model, no key", 12, "400"),
        (28, "same page, same answer", 11, "400"),
    ):
        parts.append(
            f'<text x="{mid_x + mid_w / 2}" y="{centre + dy:.1f}" font-size="{size}" '
            f'font-weight="{weight}" fill="{accent_ink}" text-anchor="middle">'
            f"{text}</text>"
        )
    for index, (name, one, two) in enumerate(_OUTPUTS):
        top = body_top + index * row
        y = top + (row - 10) / 2
        parts.append(
            f'<path d="M{mid_x + mid_w} {centre:.1f} '
            f"C{mid_x + mid_w + 24} {centre:.1f} "
            f'{right_x - 24} {y:.1f} {right_x} {y:.1f}" fill="none" stroke="{edge}" '
            'stroke-width="1.5"/>'
        )
        parts.append(
            f'<rect x="{right_x}" y="{top}" width="{width - right_x - 0.5}" '
            f'height="{row - 10}" rx="8" fill="{card}" stroke="{edge}"/>'
        )
        parts.append(
            f'<rect x="{right_x}" y="{top}" width="4" height="{row - 10}" rx="2" '
            f'fill="{accent}"/>'
        )
        parts.append(
            f'<text x="{right_x + 18}" y="{top + 22}" font-size="15" font-weight="600" '
            f'fill="{ink}">{html.escape(name)}</text>'
        )
        for n, text in enumerate((one, two)):
            parts.append(
                f'<text x="{right_x + 18}" y="{top + 40 + 15 * n}" font-size="12" '
                f'fill="{muted}">{html.escape(text)}</text>'
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
    for theme, dark in (("light", False), ("dark", True)):
        ASSETS.joinpath(f"reads-{theme}.svg").write_text(
            reads_svg(dark=dark), encoding="utf-8"
        )
    print("wrote docs/assets/inspect.svg, dates-*.svg, swde-*.svg, reads-*.svg")


if __name__ == "__main__":
    main()
