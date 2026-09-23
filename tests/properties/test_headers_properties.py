"""What a response's headers add is read the way the page's markup is: never
raising, never inventing, and the same however the names are cased.

Every page drawn is read with headers drawn beside it -- a ``Link`` header of
links with quotes, commas and parameters in them, ``X-Robots-Tag`` directives,
a ``Content-Type`` charset, a ``Content-Usage`` dictionary, TDMRep's headers --
and the answers are checked against the headers themselves, parsed here with
the standard library rather than by sluicer's reader.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urljoin

from hypothesis import given, strategies as st
from strategies import broken_pages, pages

from sluicer import extract

_TEXT = st.text(
    alphabet=st.sampled_from([*"abcAB/.:-_ ;,=\"'<>*?#%\\\t", "é", chr(0xA0)]),
    max_size=12,
)
_HREF = st.one_of(
    st.sampled_from(
        ["/c", "https://s.example/c", "c/d", "", "#x", "/a b", "//o.example/"]
    ),
    _TEXT,
)
_REL = st.sampled_from(
    ["canonical", "Canonical", "alternate", "next", "prev", "previous", "nofollow"]
)


@st.composite
def _link(draw) -> str:
    rels = draw(st.lists(_REL, min_size=0, max_size=3))
    parts = [f"<{draw(_HREF)}>"]
    if rels or draw(st.booleans()):
        quoted = draw(st.booleans())
        joined = " ".join(rels)
        parts.append(f'rel="{joined}"' if quoted else f"rel={joined}")
    for name in draw(
        st.lists(
            st.sampled_from(["hreflang", "anchor", "title", "type", "rel"]), max_size=3
        )
    ):
        parts.append(
            f'{name}="{draw(_TEXT)}"'
            if draw(st.booleans())
            else f"{name}={draw(_TEXT)}"
        )
    return "; ".join(parts)


@st.composite
def headers(draw) -> dict[str, str]:
    found: dict[str, str] = {}
    if draw(st.booleans()):
        found[draw(st.sampled_from(["Link", "link", "LINK"]))] = draw(
            st.one_of(
                st.lists(_link(), max_size=5).map(", ".join),
                _TEXT,
            )
        )
    if draw(st.booleans()):
        found["X-Robots-Tag"] = draw(
            st.one_of(
                st.lists(
                    st.sampled_from(
                        [
                            "noindex",
                            "nofollow",
                            "googlebot: noai",
                            "max-snippet:20",
                            "none",
                            "",
                        ]
                    ),
                    max_size=4,
                ).map(", ".join),
                _TEXT,
            )
        )
    if draw(st.booleans()):
        found["Content-Type"] = "text/html; charset=" + draw(
            st.one_of(
                st.sampled_from(["utf-8", "windows-1251", "latin1", "utf-7", "x"]),
                _TEXT,
            )
        )
    if draw(st.booleans()):
        found["Content-Usage"] = draw(
            st.one_of(
                st.sampled_from(
                    ["train-ai=n", "train-ai=y, search=n", "Train-AI=n", "ai-use=?1"]
                ),
                _TEXT,
            )
        )
    if draw(st.booleans()):
        found["TDM-Reservation"] = draw(st.one_of(st.sampled_from(["1", "0"]), _TEXT))
    return found


def _header_canonicals(sent: dict[str, str], url: str | None) -> set[str]:
    """Every target the Link header gives with a canonical relation, loosely:
    a superset of what a careful reader could find, from a regular expression."""
    link = next((v for k, v in sent.items() if k.lower() == "link"), "")
    found = set()
    for target in re.findall(r"<([^>]*)>", link):
        # As the URL standard reads an address: controls and spaces off the
        # ends, every tab and newline inside dropped.
        cleaned = target.strip("".join(map(chr, range(0x21))))
        cleaned = cleaned.replace("\t", "").replace("\n", "").replace("\r", "")
        try:
            found.add(urljoin(url, cleaned) if url else cleaned)
        except ValueError:
            # https://[domain]/, an unfilled template: kept as written.
            found.add(cleaned)
    return found


def _check(html, url, sent):
    result = extract(html, url=url, headers=sent)
    assert result == extract(html, url=url, headers=sent), "same input, same answer"
    recased = {name.swapcase(): value for name, value in sent.items()}
    assert result == extract(html, url=url, headers=recased), "names have no case"

    answer = result.summary.get("url")
    if answer is not None and answer.source == "http":
        assert answer.key == "Link: rel=canonical"
        loose = _header_canonicals(sent, url)
        # A space in an address is percent-encoded, as a browser encodes it.
        said = unquote(answer.value)
        assert any(said.split("#")[0] in c or c in said for c in loose), (
            answer,
            sent,
        )

    http = result.rights.get("http")
    if http is not None:
        assert sent, "the server's directives need headers to come from"
        assert set(http) <= {
            "robots",
            "agents",
            "tdm_reservation",
            "tdm_policy",
            "content_usage",
        }
        assert set(http.get("content_usage", {}).values()) <= {"allow", "disallow"}
        assert set(http.get("content_usage", {})) <= {"train-ai", "ai-use", "search"}
    for question, found in result.summary.items():
        assert found.value == found.value.strip(), (question, found)


@given(pages(), headers())
def test_headers_beside_any_page_are_read_without_raising_or_inventing(page, sent):
    _check(page.html(), page.url, sent)


@given(broken_pages(), headers())
def test_headers_beside_a_broken_page_too(page, sent):
    html, url = page
    _check(html, url, sent)


@given(pages(), headers())
def test_bytes_with_a_transport_charset_are_read_without_raising(page, sent):
    html = page.html()
    data = html.encode("utf-8", errors="replace") if isinstance(html, str) else html
    extract(data, url=page.url, headers=sent)
