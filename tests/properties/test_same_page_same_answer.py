"""The same page gives the same answer, however it is written down.

Determinism is the project's promise: the same page always gives the same
answer. That is asked here of the answer as the CLI and the MCP server hand it
out -- ``asdict`` of the ``Extraction``, serialised with its order kept,
because an agent reads the order too.

The rest of this file asks it of pages that differ only in what the standards
say does not matter: the order of an element's attributes, the case of tag and
attribute names, the whitespace between the tokens of a token list, how an
attribute value is quoted, the case of a ``<meta>`` name, the order of a JSON
object's members, and the bytes a page is encoded in when it says which
encoding that is.
"""

from __future__ import annotations

import codecs
import copy
import json
import os
import random
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from hypothesis import assume, given, settings, strategies as st
from strategies import (
    Element,
    Page,
    Style,
    broken_pages,
    declaration,
    joined_meta,
    jsonld_documents,
    jsonld_script,
    pages,
    recased,
    styles,
)

from sluicer import extract


def answer(html: str | bytes, url: str | None = None, induce: bool = True) -> str:
    """The answer as it is handed out: every field, in the order it came."""
    return json.dumps(asdict(extract(html, url=url, induce=induce)))


def unordered(html: str | bytes, url: str | None = None) -> str:
    """The answer with every object's keys sorted, for where order is free."""
    return json.dumps(asdict(extract(html, url=url, induce=True)), sort_keys=True)


# -- determinism -----------------------------------------------------------------


@given(st.one_of(pages().map(lambda p: (p.html(), p.url)), broken_pages()))
def test_the_same_page_gives_the_same_answer_twice(page):
    html, url = page

    assert answer(html, url) == answer(html, url)
    assert answer(html.encode("utf-8", "replace"), url) == answer(
        html.encode("utf-8", "replace"), url
    )


_OTHER_PROCESS = """
import json, sys
from dataclasses import asdict
from sluicer import extract
pages = json.load(sys.stdin)
print(json.dumps([asdict(extract(html, url=url, induce=True)) for html, url in pages]))
"""


# Each example starts two interpreters, so one in a hundred of what the profile
# asks for: one by default, twenty-five under the fuzz profile.
@settings(max_examples=max(1, settings.default.max_examples // 100))
@given(st.lists(pages(), min_size=10, max_size=10))
def test_the_answer_does_not_depend_on_the_process(drawn):
    """Two interpreters with different hash seeds give this one's answer.

    Python salts the hash of every str per process, so a set iterated on the
    way to an answer would give a different order in each; a test in one
    process cannot see that.
    """
    batch = [(page.html(), page.url) for page in drawn]
    here = json.dumps(
        [asdict(extract(html, url=url, induce=True)) for html, url in batch]
    )
    source = Path(__file__).resolve().parents[2] / "src"
    for seed in ("1", "2"):
        environment = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(source)}
        run = subprocess.run(
            [sys.executable, "-c", _OTHER_PROCESS],
            input=json.dumps(batch),
            capture_output=True,
            text=True,
            env=environment,
            check=True,
            encoding="utf-8",
        )
        assert run.stdout.strip() == here, f"PYTHONHASHSEED={seed}"


# -- the same tree, written another way ------------------------------------------


@given(pages(), styles())
def test_how_the_markup_is_written_does_not_change_the_answer(page, style):
    """Attribute order, name case, token spacing and quoting mean nothing."""
    assert answer(page.html(style), page.url) == answer(page.html(), page.url)


@given(pages(), styles())
def test_nor_does_it_when_the_page_arrives_as_bytes(page, style):
    written = page.html(style).encode("utf-8")

    assert answer(written, page.url) == answer(page.html().encode("utf-8"), page.url)


def _metas_in_the_head(page: Page) -> list[Element]:
    head = page.tree.children[0]
    assert isinstance(head, Element)
    return [
        child
        for child in head.children
        if isinstance(child, Element) and child.tag == "meta"
    ]


@given(pages(), st.data())
def test_the_case_of_a_meta_name_does_not_change_the_answer(page, data):
    """HTML's metadata names are ASCII case-insensitive, and so is sluicer.

    ``property`` is re-cased only in the head: inside an RDFa subject it is an
    RDFa term, and RDFa terms are case-sensitive.
    """
    before = answer(page.html(), page.url)
    for meta in _metas_in_the_head(page):
        meta.attributes = [
            (name, data.draw(recased(value)))
            if name in ("name", "property") and isinstance(value, str)
            else (name, value)
            for name, value in meta.attributes
        ]

    assert answer(page.html(), page.url) == before


@given(pages(), st.data())
def test_a_later_duplicate_of_a_meta_changes_nothing(page, data):
    """The first declaration of a name wins, in every reader that reads one.

    Except the names whose every tag is read -- a paper lists each author in
    one ``citation_author``, and OpenGraph's arrays and structured properties
    are read by position -- which are left out.
    """
    metas = [
        meta
        for meta in _metas_in_the_head(page)
        if (dict(meta.attributes).get("content") or "").strip()
        and not joined_meta(meta)
    ]
    assume(metas)
    before = answer(page.html(), page.url)
    original = data.draw(st.sampled_from(metas))
    duplicate = copy.deepcopy(original)
    duplicate.attributes = [
        (name, "a later value" if name == "content" else value)
        for name, value in duplicate.attributes
    ]
    head = page.tree.children[0]
    assert isinstance(head, Element)
    head.children.append(duplicate)

    assert answer(page.html(), page.url) == before


# -- JSON objects are unordered --------------------------------------------------


def _reordered(value: Any, order: random.Random) -> Any:
    if isinstance(value, list):
        return [_reordered(item, order) for item in value]
    if isinstance(value, dict):
        keys = list(value)
        order.shuffle(keys)
        return {key: _reordered(value[key], order) for key in keys}
    return value


def _definitions(value: Any) -> list[dict[str, Any]]:
    """Every object that defines an ``@id``, as the reader decides what does."""
    found = []
    for item in _values(value):
        if (
            isinstance(item, dict)
            and isinstance(item.get("@id"), str)
            and any(not key.startswith("@") or key == "@value" for key in item)
        ):
            found.append(item)
    return found


def _values(value: Any):
    pending = [value]
    while pending:
        item = pending.pop()
        yield item
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def _weight(value: Any) -> int:
    return sum(
        1
        + (len(item) if isinstance(item, str) else 0)
        + (sum(len(key) for key in item) if isinstance(item, dict) else 0)
        for item in _values(value)
    )


@given(st.lists(jsonld_documents(), min_size=1, max_size=3), st.integers(1, 2**32))
def test_the_order_of_a_json_object_s_members_does_not_change_the_answer(blocks, seed):
    """RFC 8259: an object is an unordered collection of members.

    Two rules on the page follow document order on purpose, and the property
    stays out of their way: the first definition of an ``@id`` wins, so every
    id here is defined once; and past the reference budget a reference stays a
    reference in document order, so the pages here stay under it.
    """
    for block in blocks:
        seen: set[str] = set()
        for definition in _definitions(block):
            if definition["@id"] in seen:
                definition["@id"] = f"#only-{len(seen)}-{id(definition)}"
            seen.add(definition["@id"])
    ids = [d["@id"] for block in blocks for d in _definitions(block)]
    assume(len(ids) == len(set(ids)))
    references = sum(
        1
        for block in blocks
        for item in _values(block)
        if isinstance(item, dict)
        and isinstance(item.get("@id"), str)
        and all(key.startswith("@") and key != "@value" for key in item)
    )
    largest = max(
        (_weight(d) for block in blocks for d in _definitions(block)), default=0
    )
    assume(references * largest < 10_000)

    def page(documents: list[Any]) -> str:
        scripts = [jsonld_script(json.dumps(document)) for document in documents]
        return Page(Element("html", [], [Element("head", [], scripts)]), None).html()

    shuffled = [_reordered(block, random.Random(seed)) for block in blocks]

    assert unordered(page(shuffled)) == unordered(page(blocks))


# -- bytes -----------------------------------------------------------------------

# Labels, and the codec a browser decodes a page declaring each one with, as the
# WHATWG Encoding Standard maps them. Written out here rather than borrowed
# from sluicer, so the two can disagree.
DECLARED = {
    "utf-8": "utf-8",
    "UTF8": "utf-8",
    "windows-1252": "cp1252",
    "iso-8859-1": "cp1252",
    "Latin1": "cp1252",
    "us-ascii": "cp1252",
    "windows-1251": "cp1251",
    "koi8-r": "koi8-r",
    "iso-8859-2": "iso8859-2",
    "ISO-8859-15": "iso8859-15",
    "iso-8859-9": "cp1254",
    "tis-620": "cp874",
    "shift_jis": "cp932",
    "euc-jp": "euc_jp",
    "iso-2022-jp": "iso2022_jp",
    "gbk": "gb18030",
    "gb2312": "gb18030",
    "big5": "big5hkscs",
    "euc-kr": "cp949",
    "utf-16": "utf-8",
    "utf-16le": "utf-8",
}

PLACES = ("prefix", "head start", "head end")


def _declared(page: Page, label: str, how: str, where: str, style: Style) -> str:
    written = declaration(label, how)
    html = page.html(style, doctype=where != "prefix")
    if how == "xml" or where == "prefix":
        return written + html
    marker = "<head>" if not style.upper else "<HEAD>"
    if where == "head start":
        return html.replace(marker, marker + written, 1)
    closing = "</head>" if not style.upper else "</HEAD>"
    return html.replace(closing, written + closing, 1)


def _as_read(data: bytes, codec: str) -> str:
    """The text Sluicer reads ``data``, declared in ``codec``, as.

    Its declared codec, but for bytes that are valid UTF-8 and hold a
    character outside ASCII, which are UTF-8 whatever they declare
    (``sniff_encoding``): the fuzz profile drew an author ``Â\x80`` declared
    Latin-1, whose bytes are UTF-8's U+0080. Bytes the codec cannot read are
    replaced, as Sluicer replaces them: the fuzz profile drew ``\x1b)``, ASCII
    but no escape ISO-2022-JP knows.
    """
    if not data.isascii():
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            pass
    return data.decode(codec, errors="replace")


@given(
    pages(),
    st.sampled_from(sorted(DECLARED)),
    st.sampled_from(["charset", "bare", "http-equiv", "http-equiv-quoted", "xml"]),
    st.sampled_from(PLACES),
    styles(),
)
def test_a_page_is_read_in_the_encoding_it_declares(page, label, how, where, style):
    """Bytes in the declared encoding give the answer the text gives.

    Whatever the page cannot say in that encoding is replaced first, since
    the bytes cannot hold it; the answer compared is the text those bytes
    decode to, which is the declared encoding's but for bytes that are also
    UTF-8 (``_as_read``).
    """
    codec = DECLARED[label]
    html = _declared(page, label, how, where, style)
    data = html.encode(codec, errors="replace")

    assert answer(data, page.url) == answer(_as_read(data, codec), page.url)


@given(pages(), st.sampled_from(["utf-8", "cp1252"]), styles())
def test_a_page_that_declares_nothing_is_utf8_if_it_can_be_and_1252_if_not(
    page, codec, style
):
    data = page.html(style).encode(codec, errors="replace")
    if codec == "cp1252":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            assume(False)

    assert answer(data, page.url) == answer(data.decode(codec), page.url)


@given(
    pages(),
    st.sampled_from(
        [
            (codecs.BOM_UTF8, "utf-8"),
            (codecs.BOM_UTF16_LE, "utf-16-le"),
            (codecs.BOM_UTF16_BE, "utf-16-be"),
        ]
    ),
    st.sampled_from(sorted(DECLARED)),
)
def test_a_byte_order_mark_outranks_whatever_the_page_declares(page, bom, label):
    mark, codec = bom
    html = _declared(page, label, "charset", "head start", Style())

    assert answer(mark + html.encode(codec, "replace"), page.url) == answer(
        html.encode(codec, "replace").decode(codec), page.url
    )


# What else a <meta charset> can carry. The HTML standard's prescan reads an
# attribute's quoted value whole, ">" and all, so none of these can hide it.
_ALONGSIDE = (
    ("content", "text/html; a>b"),
    ("name", "x>y"),
    ("data-note", "it's > that"),
    ("id", "c"),
    ("lang", "en"),
)


@given(
    pages(),
    st.sampled_from(
        sorted(label for label, codec in DECLARED.items() if codec != "utf-8")
    ),
    st.lists(st.sampled_from(_ALONGSIDE), max_size=3, unique_by=lambda a: a[0]),
    styles(upper=False),
)
def test_a_declaration_is_read_whatever_else_its_meta_carries(
    page, label, extra, style
):
    meta = Element("meta", [("charset", label), *extra])
    head = page.tree.children[0]
    assert isinstance(head, Element)
    head.children.insert(0, meta)
    codec = DECLARED[label]
    data = page.html(style).encode(codec, errors="replace")

    assert answer(data, page.url) == answer(_as_read(data, codec), page.url)


def test_legacy_bytes_that_are_utf8_are_read_as_utf8():
    """Found by the fuzz profile: "Â\x80" in Latin-1 is the bytes C2 80, UTF-8's
    U+0080, and is read so -- the one departure from reading as declared."""
    html = '<meta charset="iso-8859-1"><meta itemprop="author" content="A\u00c2\u0080">'
    data = html.encode("latin-1")
    assert answer(data) == answer(_as_read(data, "latin-1"))
    assert _as_read(data, "latin-1") == data.decode("utf-8")
