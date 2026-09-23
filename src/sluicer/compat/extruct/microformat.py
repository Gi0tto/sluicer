"""Microformats in extruct's shape: mf2py's items, as extruct asks mf2py for them.

extruct calls ``mf2py.parse(html, html_parser="lxml", url=base_url)`` and
answers its ``items``; so does this, with the page as sluicer decoded it
rather than the bytes, so a page's accents are read the same way by every
syntax. It needs mf2py, which is ``sluicer[microformats]``; without it the call
raises ``MicroformatsExtraMissing``, whose message is the install line.

A page mf2py cannot read at all -- its ``<base href>`` is a template's
``https://[domain]/``, which ``urlparse`` refuses -- declares no microformats
here, as it does to sluicer's own reader; extruct raises.
"""

from __future__ import annotations

import warnings
from typing import Any

from sluicer.compat.extruct.page import Page, read_page
from sluicer.declared.microformats import _mf2py


class MicroformatExtractor:
    """extruct's microformats extractor. It needs the page's text, not a tree."""

    def extract(
        self,
        htmlstring: str | bytes,
        base_url: str | None = None,
        encoding: str = "UTF-8",
    ) -> list[dict[str, Any]]:
        return self.read(read_page(htmlstring, base_url, encoding))

    def extract_items(
        self, html: str | bytes, base_url: str | None = None
    ) -> list[dict[str, Any]]:
        return self.read(read_page(html, base_url, "UTF-8"))

    def read(self, page: Page) -> list[dict[str, Any]]:
        if page.text is None:
            raise ValueError(
                "'microformat' syntax requires a string, not a parsed tree. "
                "Consider adjusting the 'syntaxes' argument to exclude it, "
                "or passing an HTML string or bytes."
            )
        mf2py = _mf2py()
        with warnings.catch_warnings():
            # mf2py warns about choices it made itself, which a caller can do
            # nothing with.
            warnings.simplefilter("ignore")
            try:
                parsed: dict[str, Any] = mf2py.parse(
                    page.text, html_parser="lxml", url=page.base_url
                )
            except ValueError:
                return []
        items: list[dict[str, Any]] = parsed.get("items") or []
        return items
