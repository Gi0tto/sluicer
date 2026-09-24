# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright==1.63.0"]
# ///
"""Draw the repository's social preview, the card a shared link shows.

    uv run scripts/social_card.py      # then: uv run playwright install chromium, once

Writes ``docs/assets/social-preview.png`` at the 1280 x 640 GitHub asks for.
GitHub takes it only from the repository's settings (General, Social
preview), so it is uploaded there by hand; every page of the documentation
names it as its image, in ``docs/overrides/main.html``.
"""

from __future__ import annotations

import base64
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"


def page() -> str:
    logo = base64.b64encode((ASSETS / "logo.png").read_bytes()).decode()
    facts = [
        (
            "Eight vocabularies, one record",
            "every value with its source and its place on the page",
        ),
        (
            "Extractors that fail loudly",
            "a site that changed its layout exits 3, and heal says what moved",
        ),
        (
            "No model, no API key",
            "the same page gives the same answer, and a run costs CPU",
        ),
    ]
    items = "".join(
        f"<li><b>{title}</b><span>{text}</span></li>" for title, text in facts
    )
    style = """
    html, body { margin: 0; width: 1280px; height: 640px; }
    body {
      font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
      background: linear-gradient(135deg, #ffffff 0%, #eef4ff 100%);
      color: #1f2328; box-sizing: border-box; padding: 64px 80px;
      display: flex; flex-direction: column;
    }
    img { width: 520px; }
    h1 { font-size: 44px; line-height: 1.2; margin: 40px 0 36px; }
    ul { list-style: none; margin: 0; padding: 0; }
    li { font-size: 26px; margin: 0 0 18px; padding-left: 30px; position: relative; }
    li::before {
      content: ""; position: absolute; left: 0; top: 12px;
      width: 12px; height: 12px; border-radius: 50%; background: #f5a524;
    }
    li b { color: #1d4ed8; }
    li span { color: #59636e; }
    li span::before { content: " \u2014 "; }
    footer {
      margin-top: auto; font-size: 22px; color: #59636e;
      display: flex; justify-content: space-between;
    }
    code { font-family: ui-monospace, "SF Mono", Menlo, monospace; color: #1f2328; }
    """
    footer = (
        "<footer><code>pip install sluicer</code>"
        "<span>github.com/Gi0tto/sluicer</span></footer>"
    )
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><style>{style}</style>'
        f'</head><body><img src="data:image/png;base64,{logo}" alt="Sluicer">'
        f"<h1>Turn a web page into structured data.</h1><ul>{items}</ul>"
        f"{footer}</body></html>"
    )


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        tab = browser.new_page(viewport={"width": 1280, "height": 640})
        tab.set_content(page())
        tab.screenshot(path=str(ASSETS / "social-preview.png"))
        browser.close()
    print("wrote docs/assets/social-preview.png")


if __name__ == "__main__":
    main()
