from pathlib import Path

import pytest

from sluicer.document import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_parses_html_and_keeps_the_source():
    html = (FIXTURES / "plain.html").read_text()

    doc = load(html, url="https://example.com/a")

    assert doc.url == "https://example.com/a"
    assert doc.html == html
    assert doc.tree.findtext(".//title") == "Plain page"


def test_load_survives_broken_markup():
    doc = load("<html><body><p>unclosed")

    assert doc.tree.findtext(".//p") == "unclosed"


@pytest.mark.parametrize(
    "text",
    [
        "<!doctype html>",
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!-- nothing at all -->",
        "﻿   \n  ",
        "",
        " ",
    ],
    ids=["doctype", "xml-declaration", "comment", "bom-whitespace", "empty", "space"],
)
def test_load_never_raises_on_a_document_lxml_cannot_parse(text):
    doc = load(text)

    assert doc.tree.tag == "html"
    assert len(doc.tree) == 0
    assert doc.tree.text_content() == ""
    assert doc.html == text
