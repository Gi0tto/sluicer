import json

import pytest

from sluicer.fetch.rules import MARKUP_CEILING, challenge_marker, why_climb

FULL_PAGE = (
    "<html><body>" + ("Real sentences of real content. " * 40) + "</body></html>"
)


def test_a_good_page_does_not_climb():
    assert why_climb(200, FULL_PAGE, found_records=True) is None


def test_a_refusal_climbs_and_names_the_status():
    reason = why_climb(403, "<html><body>Forbidden</body></html>", found_records=False)

    assert reason is not None
    assert "403" in reason


def test_a_server_error_does_not_climb():
    assert why_climb(500, "<html><body>oops</body></html>", found_records=False) is None


def test_a_challenge_page_climbs_even_with_status_200():
    challenge = (
        '<html><body><div id="cf-challenge-running"></div>'
        "Just a moment...</body></html>"
    )

    reason = why_climb(200, challenge, found_records=False)

    assert reason is not None
    assert "challenge" in reason.lower()


def test_a_skeletal_body_climbs():
    skeleton = (
        '<html><body><div id="app"></div>'
        + ('<script src="a.js"></script>' * 80)
        + "</body></html>"
    )

    assert why_climb(200, skeleton, found_records=False) is not None


def test_a_thin_page_that_declared_records_stays_put():
    thin = "<html><body><p>Short.</p></body></html>"

    assert why_climb(200, thin, found_records=True) is None


def test_a_small_page_without_scripts_is_a_small_page_and_stays_put():
    """example.com is 152 characters of text and no script, and it is complete.

    Climbing it bought a browser for nothing, and on an install without one it
    turned a good page into a traceback.
    """
    thin = "<html><body><h1>Example Domain</h1><p>Short.</p></body></html>"

    assert why_climb(200, thin, found_records=False) is None


def test_a_small_page_that_runs_scripts_and_declared_nothing_climbs():
    shell = (
        '<html><body><div id="root"></div><script src="/app.js"></script></body></html>'
    )

    reason = why_climb(200, shell, found_records=False)

    assert reason is not None
    assert "script" in reason.lower()


def test_a_page_that_is_not_there_is_an_answer_not_a_reason_to_climb():
    for status in (404, 410, 400):
        assert why_climb(status, "<html><body>Not found</body></html>", False) is None


def test_a_refusal_that_is_also_a_challenge_names_the_challenge():
    challenge_refusal = (
        '<html><body><div id="cf-challenge-running"></div>Forbidden</body></html>'
    )

    reason = why_climb(403, challenge_refusal, found_records=False)

    assert reason is not None
    assert "challenge" in reason.lower()
    assert "403" not in reason


# A page that says everything in JSON-LD and nothing to the eye: the markup is
# heavy, the visible text is empty, and the record is already complete.
DECLARED_ONLY_PAGE = (
    '<html><head><script type="application/ld+json">'
    + json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Brake pad set",
            "sku": "BP-1234",
            "description": "Front axle brake pads for a 2014 hatchback. " * 40,
            "offers": {"@type": "Offer", "price": "49.90", "priceCurrency": "EUR"},
        }
    )
    + '</script></head><body><div id="app"></div></body></html>'
)


def test_a_skeletal_page_that_declared_records_stays_put():
    """A page that already yielded records has delivered: climbing buys nothing."""
    assert len(DECLARED_ONLY_PAGE) > MARKUP_CEILING

    assert why_climb(200, DECLARED_ONLY_PAGE, found_records=True) is None


def test_the_same_skeletal_page_climbs_when_nothing_was_declared():
    reason = why_climb(200, DECLARED_ONLY_PAGE, found_records=False)

    assert reason is not None
    assert "skeletal" in reason


ARTICLE_TEXT = "The minister paused. " * 90  # well past a challenge page's length


def test_an_article_quoting_a_challenge_phrase_is_not_a_challenge():
    """Measured on 0.2.0: this page, with its own NewsArticle, bought a browser."""
    article = (
        "<html><head><title>The interview</title></head><body><p>"
        + ARTICLE_TEXT
        + "She said: just a moment, before answering.</p></body></html>"
    )

    assert why_climb(200, article, found_records=True) is None
    assert why_climb(200, article, found_records=False) is None


def test_a_full_page_carrying_cloudflare_bot_detection_is_not_a_challenge():
    watched = (
        "<html><head><title>Brake pads</title></head><body><p>"
        + ARTICLE_TEXT
        + '</p><script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js">'
        "</script></body></html>"
    )

    assert why_climb(200, watched, found_records=False) is None


def test_a_title_that_is_the_challenge_climbs_whatever_the_body():
    titles = (
        "Just a moment...",
        "Just a moment\u2026",
        "Attention Required! | Cloudflare",
    )
    for title in titles:
        page = f"<html><head><title>{title}</title></head><body>{ARTICLE_TEXT}</body>"

        reason = why_climb(200, page, found_records=False)

        assert reason is not None, title
        assert "challenge" in reason


def test_a_headline_that_starts_like_a_challenge_is_a_headline():
    page = (
        "<html><head><title>Just a moment: the minister answers</title></head>"
        f"<body>{ARTICLE_TEXT}</body></html>"
    )

    assert why_climb(200, page, found_records=True) is None


# The interstitials below are the ones the cached benchmark pages hold, each
# cut to its structure: the title, the element or address that names the
# vendor, and about as much visible text. Each was a 200 with its page's
# address, and none was recognised.

# PyPI's, served by Fastly to a client without JavaScript: 3 kB, status 200,
# in bench/cache/drift for a PyPI search.
FASTLY_CLIENT_CHALLENGE = """<!DOCTYPE html><html lang="en"><head>
<link href="/_fs-ch-1T1wmsGaOgGaSxcX/assets/styles.css" rel="stylesheet" />
<title>Client Challenge</title></head><body>
<noscript><div class="noscript-container"><div class="noscript-content">
<img src="/_fs-ch-1T1wmsGaOgGaSxcX/assets/errorIcon.svg" alt="" role="presentation">
<span class="noscript-span">JavaScript is disabled in your browser.</span>
<p>Please enable JavaScript to proceed.</p></div></div></noscript>
<div id="loading-error" role="alert" aria-live="polite">A required part of this
site couldn't load. This may be due to a browser extension, network issues, or
browser settings. Please check your connection, disable any ad blockers, or try
using a different browser.</div>
<script>loadScript('/_fs-ch-1T1wmsGaOgGaSxcX/errors.js')</script>
</body></html>"""

# Imperva's, no title, the challenge in an iframe: realweb, one site.
INCAPSULA = """<html style="height:100%"><head>
<META NAME="ROBOTS" CONTENT="NOINDEX, NOFOLLOW">
<script src="/nly-What-neuer-of-my-But-of-Rosse-a-Say-thinke-v" async></script>
</head><body style="margin:0px;height:100%"><iframe id="main-iframe"
src="/_Incapsula_Resource?SWUDNSAI=9&amp;incident_id=7220-8218" frameborder=0
width="100%" height="100%">Request unsuccessful. Incapsula incident ID:
722000590077202780-82181532081589964</iframe></body></html>"""

# HUMAN's (PerimeterX), under the shop's own title: a Sam's Club page in WCXB.
PERIMETERX = """<html lang="en"><head>
<title>Let us know you're not a robot - Sam's Club</title></head><body>
<header><nav><a href="?xid=hdr_logo" aria-label="Sam's Club homepage logo"></a>
</nav></header><div class="sc-human-challenge-page"><div class="bst-alert-body">
Let us know you're human (no robots allowed)</div><div id="px-captcha"></div>
</div><footer><ul><li><a href="//help.samsclub.com">Help center</a></li>
<li><a href="/content/terms-and-conditions">Terms</a></li></ul></footer>
</body></html>"""

# Anubis's proof of work, its title written with an entity: a WCXB page.
ANUBIS = """<!doctype html><html lang="en"><head>
<title>Making sure you&#39;re not a bot!</title>
<script id="anubis_challenge" type="application/json">{"rules":{"difficulty":2}}
</script></head><body id="top"><main><h1 id="title">Making sure you&#39;re not a
bot!</h1><details><p>You are seeing this because
the administrator of this website has set up Anubis to protect the server
against the scourge of AI companies aggressively scraping websites.</p>
</details><noscript><p>Sadly, you must enable JavaScript to get past this
challenge.</p></noscript></main></body></html>"""

# A waiting room that runs a script, posts a form and reloads after five
# seconds, the same on four sites of realweb, which set it aside as "no text".
ONE_MOMENT = """<!DOCTYPE html><html lang="en"><head><meta charset="utf8">
<script>(function(){setTimeout(function(){window.location.reload();},5000);}())
</script><title>One moment, please...</title></head><body>
<div id="outer-container"><div id="container"><div class="throbber">
<svg class="spinner" width="90px" height="90px"><title>Loader</title></svg>
</div></div></div><script>var a0R=function(){return ['form','submit','webdriver'];}
</script></body></html>"""


@pytest.mark.parametrize(
    "page",
    [FASTLY_CLIENT_CHALLENGE, INCAPSULA, PERIMETERX, ANUBIS, ONE_MOMENT],
    ids=["fastly", "incapsula", "perimeterx", "anubis", "one-moment"],
)
def test_an_anti_bot_interstitial_the_benchmarks_met_is_a_challenge(page):
    reason = why_climb(200, page, found_records=False)

    assert reason is not None
    assert reason.startswith("the response is a challenge page")
    assert challenge_marker(page, found_records=False) is not None


def test_a_page_that_names_a_vendor_s_path_in_its_article_is_not_a_challenge():
    """The markers count only on a page with little text, as the others do."""
    article = (
        "<html><head><title>How Fastly's bot checks work</title></head><body><p>"
        + ARTICLE_TEXT
        + " Its challenge loads /_fs-ch-/script.js and Imperva's "
        "/_Incapsula_Resource; HUMAN draws into #px-captcha.</p></body></html>"
    )

    assert why_climb(200, article, found_records=False) is None
