"""What a response's headers declare beside the page: Link, X-Robots-Tag, TDMRep."""

from __future__ import annotations

import sluicer
from sluicer.declared.headers import (
    charset,
    lowered,
    parse_link,
    read_header_links,
    read_header_rights,
)

URL = "https://shop.example/p/1"
PAGE = "<html><head><title>A page</title></head><body><p>text</p></body></html>"


# -- the Link header, as RFC 8288 writes it ------------------------------------


def test_a_link_header_is_read_link_by_link():
    links = parse_link('<https://a.example/x>; rel="canonical", </next>; rel=next')
    assert links == [
        {"href": "https://a.example/x", "rel": ["canonical"], "params": {}},
        {"href": "/next", "rel": ["next"], "params": {}},
    ]


def test_a_comma_inside_quotes_does_not_end_the_link():
    links = parse_link(
        '</a>; rel="alternate"; title="one, two"; hreflang=de, </b>; rel=next'
    )
    assert [link["href"] for link in links] == ["/a", "/b"]
    assert links[0]["params"] == {"title": "one, two", "hreflang": "de"}


def test_a_rel_holds_several_types_matched_without_case():
    [link] = parse_link('</x>; rel="Canonical Alternate"')
    assert link["rel"] == ["canonical", "alternate"]


def test_a_repeated_rel_keeps_its_first_as_the_rfc_says():
    [link] = parse_link("</x>; rel=next; rel=canonical")
    assert link["rel"] == ["next"]


def test_a_quoted_string_keeps_its_escapes_meaning():
    [link] = parse_link(r'</x>; rel=next; title="say \"hi\""')
    assert link["params"]["title"] == 'say "hi"'


def test_a_link_that_does_not_open_with_an_angle_bracket_is_skipped():
    links = parse_link("garbage; rel=canonical, </ok>; rel=canonical, <unclosed")
    assert [link["href"] for link in links] == ["/ok"]


def test_a_parameter_with_no_value_is_kept_empty():
    [link] = parse_link("</x>; crossorigin; rel=preload")
    assert link["params"] == {"crossorigin": ""}
    assert link["rel"] == ["preload"]


def test_an_extended_parameter_name_is_read_as_its_plain_name():
    [link] = parse_link("</x>; rel=next; title*=UTF-8'de'n%c3%a4chstes")
    assert "title" in link["params"]


def test_an_empty_target_is_no_link():
    assert parse_link("<>; rel=canonical") == []


def test_a_hostile_header_is_read_only_so_far():
    links = parse_link(", ".join(f"</p{i}>; rel=next" for i in range(10_000)))
    assert len(links) == 200


def test_link_header_targets_resolve_against_the_response_address():
    found = read_header_links(
        {
            "link": '</p/1>; rel="canonical", '
            '</de/p/1>; rel="alternate"; hreflang="de", '
            "</p/2>; rel=next, </p/0>; rel=prev"
        },
        URL,
    )
    assert found == {
        "canonicals": ["https://shop.example/p/1"],
        "alternates": [("de", "https://shop.example/de/p/1")],
        "next": "https://shop.example/p/2",
        "prev": "https://shop.example/p/0",
    }


def test_a_link_about_another_resource_is_not_read():
    found = read_header_links({"link": '</other>; rel=canonical; anchor="/x"'}, URL)
    assert found["canonicals"] == []


def test_an_alternate_with_no_hreflang_is_not_a_language_version():
    found = read_header_links({"link": "</feed>; rel=alternate"}, URL)
    assert found["alternates"] == []


# -- the Link header in an extraction ------------------------------------------


def test_a_canonical_only_in_the_header_answers_the_url():
    result = sluicer.extract(
        PAGE, url=URL, headers={"Link": '<https://shop.example/p/1>; rel="canonical"'}
    )
    assert result.links["canonical"] == "https://shop.example/p/1"
    answer = result.summary["url"]
    assert (answer.value, answer.source, answer.key) == (
        "https://shop.example/p/1",
        "http",
        "Link: rel=canonical",
    )


def test_the_same_canonical_in_head_and_header_is_one_canonical():
    page = PAGE.replace("</head>", '<link rel="canonical" href="/p/1"></head>')
    result = sluicer.extract(
        page, url=URL, headers={"link": "<https://shop.example/p/1>; rel=canonical"}
    )
    assert result.links["canonical"] == "https://shop.example/p/1"
    assert result.summary["url"].source == "html"


def test_a_header_canonical_that_disagrees_with_the_head_is_a_conflict():
    page = PAGE.replace("</head>", '<link rel="canonical" href="/p/1"></head>')
    result = sluicer.extract(
        page, url=URL, headers={"link": "<https://shop.example/p/9>; rel=canonical"}
    )
    assert "canonical" not in result.links
    assert result.links["canonical_conflict"] == [
        "https://shop.example/p/1",
        "https://shop.example/p/9",
    ]
    assert "url" not in result.summary


def test_header_alternates_join_the_markups_without_repeating():
    page = PAGE.replace(
        "</head>", '<link rel="alternate" hreflang="de" href="/de/p/1"></head>'
    )
    result = sluicer.extract(
        page,
        url=URL,
        headers={
            "link": "</de/p/1>; rel=alternate; hreflang=de, "
            '</fr/p/1>; rel=alternate; hreflang="fr"'
        },
    )
    assert result.links["alternates"] == [
        {"hreflang": "de", "href": "https://shop.example/de/p/1"},
        {"hreflang": "fr", "href": "https://shop.example/fr/p/1"},
    ]


def test_the_markups_next_page_wins_over_the_headers():
    page = PAGE.replace("</head>", '<link rel="next" href="/p/2"></head>')
    result = sluicer.extract(
        page, url=URL, headers={"link": "</p/3>; rel=next, </p/0>; rel=previous"}
    )
    assert result.links["next"] == "https://shop.example/p/2"
    assert result.links["prev"] == "https://shop.example/p/0"


def test_no_headers_reads_as_before():
    assert sluicer.extract(PAGE, url=URL) == sluicer.extract(PAGE, url=URL, headers={})
    assert "http" not in sluicer.extract(PAGE, url=URL).rights


# -- X-Robots-Tag and TDMRep ---------------------------------------------------


def test_x_robots_tag_directives_for_everyone():
    assert read_header_rights({"x-robots-tag": "noindex, NoFollow"}) == {
        "robots": ["noindex", "nofollow"]
    }


def test_x_robots_tag_directives_for_one_crawler_as_google_documents():
    found = read_header_rights(
        {"x-robots-tag": "googlebot: nofollow, otherbot: noindex, nofollow"}
    )
    assert found == {
        "agents": {"googlebot": ["nofollow"], "otherbot": ["noindex", "nofollow"]}
    }


def test_a_directive_with_a_value_is_not_a_crawlers_name():
    found = read_header_rights(
        {
            "x-robots-tag": "max-snippet:20, max-image-preview:large, "
            "unavailable_after: 25 Jun 2010 15:00:00 PST"
        }
    )
    assert found == {
        "robots": [
            "max-snippet:20",
            "max-image-preview:large",
            "unavailable_after: 25 jun 2010 15:00:00 pst",
        ]
    }


def test_a_value_directive_after_a_crawler_stays_that_crawlers():
    found = read_header_rights({"x-robots-tag": "googlebot: noindex, max-snippet:0"})
    assert found == {"agents": {"googlebot": ["noindex", "max-snippet:0"]}}


def test_a_hostile_x_robots_tag_is_bounded():
    many = ", ".join(f"bot{i}: noindex" for i in range(100))
    found = read_header_rights({"x-robots-tag": many})
    assert len(found["agents"]) == 20
    endless = ", ".join(f"directive{i}" for i in range(500))
    assert len(read_header_rights({"x-robots-tag": endless})["robots"]) == 50


def test_tdmrep_headers_are_read_first_repeat_wins():
    found = read_header_rights(
        {"tdm-reservation": "1, 0", "tdm-policy": "https://site.example/policy.json"}
    )
    assert found == {
        "tdm_reservation": "1",
        "tdm_policy": "https://site.example/policy.json",
    }


def test_the_servers_directives_are_reported_apart_from_the_pages():
    page = PAGE.replace("</head>", '<meta name="robots" content="index"></head>')
    result = sluicer.extract(
        page, url=URL, headers={"X-Robots-Tag": "noindex", "TDM-Reservation": "1"}
    )
    assert result.rights["robots"] == ["index"]
    assert result.rights["http"] == {"robots": ["noindex"], "tdm_reservation": "1"}


def test_headers_that_declare_nothing_add_no_http_rights():
    result = sluicer.extract(PAGE, url=URL, headers={"content-type": "text/html"})
    assert "http" not in result.rights


# -- the charset ---------------------------------------------------------------


def test_the_content_type_charset_decodes_bytes_before_the_pages_own():
    body = '<html><head><meta charset="utf-8"><title>Цена</title></head></html>'
    result = sluicer.extract(
        body.encode("windows-1251"),
        url=URL,
        headers={"Content-Type": "text/html; charset=windows-1251"},
    )
    assert result.summary["title"].value == "Цена"


def test_charset_reads_the_content_type_parameter():
    assert charset({"content-type": 'text/html; Charset="ISO-8859-2"'}) == "ISO-8859-2"
    assert charset({"content-type": "text/html"}) is None
    assert charset({}) is None


def test_header_names_are_matched_without_case_and_repeats_join():
    assert lowered({"Link": "<a>", "LINK": "<b>"}) == {"link": "<a>, <b>"}
    assert lowered(None) == {}


def test_the_links_spacing_and_a_trailing_comma_are_tolerated():
    links = parse_link('</x> ;  rel= "next" ;title= plain , ')
    assert links == [{"href": "/x", "rel": ["next"], "params": {"title": "plain"}}]


def test_a_quoted_comma_in_a_skipped_link_does_not_start_a_new_one():
    links = parse_link('broken; title="a, <nope>", </ok>; rel=next')
    assert [link["href"] for link in links] == ["/ok"]


def test_an_alternate_named_twice_is_listed_once():
    found = read_header_links(
        {"link": ", ".join(["</de>; rel=alternate; hreflang=de"] * 2)},
        URL,
    )
    assert found["alternates"] == [("de", "https://shop.example/de")]


def test_charset_passes_over_other_parameters():
    assert charset({"content-type": "text/html; q=1; charset=utf-8"}) == "utf-8"
