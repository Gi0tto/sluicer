"""fundus's parser fixtures as a page list, each page paired with its labels.

Run by ``bench/news.py`` in an environment holding fundus's own checkout,
installed from the pinned commit: which labels belong to which page is
decided by fundus's own code, the parser version valid on the day the page
was crawled, exactly as its test suite pairs them. Nothing here guesses it.

Writes one entry per fixture: the page's path relative to the output file,
its address, its country group, and the title, authors and publishing date
fundus's reviewed parser extracts from it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(checkout: str, out_path: str) -> None:
    root = Path(checkout)
    sys.path.insert(0, str(root))  # fundus's tests/ is a package of the checkout
    from fundus.publishers import PublisherCollection
    from tests.utility import load_html_test_file_mapping, load_test_case_data

    out = Path(out_path)
    pages = []
    for publisher in PublisherCollection:
        try:
            expected = load_test_case_data(publisher)
            mapping = load_html_test_file_mapping(publisher)
        except (FileNotFoundError, KeyError, ValueError):
            continue
        for version, html_file in mapping.items():
            labels = expected.get(version.__name__)
            if labels is None:
                continue
            authors = labels.get("authors") or []
            date = labels.get("publishing_date")
            country = publisher.__group__.__name__.lower()
            pages.append(
                {
                    "id": f"{country}/{publisher.__name__}/{version.__name__}",
                    "country": country,
                    "publisher": publisher.__name__,
                    "path": str(html_file.path.relative_to(out.parent.resolve()))
                    if html_file.path.is_relative_to(out.parent.resolve())
                    else str(html_file.path),
                    "url": html_file.url,
                    "page_type": "article",
                    "title": labels.get("title") or None,
                    "author": ", ".join(authors) if authors else None,
                    "date": str(date) if date else None,
                }
            )
    out.write_text(json.dumps(pages, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(pages)} fixtures from {len({p['country'] for p in pages})} groups")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
