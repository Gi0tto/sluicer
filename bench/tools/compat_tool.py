"""sluicer.compat.extruct's default call, for ``bench/timing.py``.

Run in an environment holding this checkout, installed editable, and mf2py,
the microformats extra. It is the call ``bench/extruct_compat.py`` records
beside extruct's, every argument but the address at its default.
"""

from __future__ import annotations

from typing import Any

# Imported so that an environment without the microformats extra fails here:
# there, every default call raises MicroformatsExtraMissing, and timing it
# times the raise.
import mf2py  # noqa: F401

from sluicer.compat import extruct as compat


def extract(html: bytes, url: str | None) -> Any:
    """``compat.extract(html, base_url=url)``; what it raises is its answer."""
    try:
        return compat.extract(html, base_url=url)
    except Exception as raised:  # noqa: BLE001 -- the count is the point
        return type(raised).__name__
