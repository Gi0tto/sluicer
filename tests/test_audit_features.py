"""Every documented feature, on a record written by hand three ways.

A record that keeps to the documentation has its requirements met and no
error; the same record less one required property has that property named as
missing; and the same record with one value in a form the documentation
refuses has that value named, at its path. The records are JSON-LD, as
Google's own examples are; microdata and RDFa are read by the same rules and
are checked in ``test_audit.py``.
"""

import copy
import json

import pytest

from sluicer.audit import audit

ADDRESS = {
    "@type": "PostalAddress",
    "streetAddress": "148 W 51st St",
    "addressLocality": "New York",
    "addressRegion": "NY",
    "postalCode": "10019",
    "addressCountry": "US",
}

VALID = {
    "product": {
        "@type": "Product",
        "name": "Brake pad set",
        "image": "https://example.com/pads.jpg",
        "sku": "BP-1187",
        "gtin13": "4006381333931",
        "brand": {"@type": "Brand", "name": "ATE"},
        "offers": {
            "@type": "Offer",
            "price": "41.90",
            "priceCurrency": "EUR",
            "availability": "https://schema.org/InStock",
            "itemCondition": "https://schema.org/NewCondition",
            "url": "https://example.com/pads",
        },
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": "4.6",
            "reviewCount": "89",
        },
    },
    "review": {
        "@type": "Review",
        "author": {"@type": "Person", "name": "Ada"},
        "itemReviewed": {"@type": "Book", "name": "Dune"},
        "reviewRating": {"@type": "Rating", "ratingValue": "4"},
        "datePublished": "2026-01-02",
    },
    "aggregate-rating": {
        "@type": "AggregateRating",
        "itemReviewed": {"@type": "Recipe", "name": "Apple pie"},
        "ratingValue": "88",
        "bestRating": "100",
        "ratingCount": "20",
    },
    "article": {
        "@type": "NewsArticle",
        "headline": "Rates held",
        "image": ["https://example.com/1x1.jpg"],
        "datePublished": "2026-09-01T08:00:00+02:00",
        "dateModified": "2026-09-01T09:20:00+02:00",
        "author": [
            {"@type": "Person", "name": "Jane", "url": "https://example.com/jane"}
        ],
    },
    "breadcrumb": {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Books",
                "item": "https://example.com/books",
            },
            {"@type": "ListItem", "position": 2, "name": "Science fiction"},
        ],
    },
    "local-business": {
        "@type": "Restaurant",
        "name": "Dave's Steak House",
        "address": ADDRESS,
        "geo": {"@type": "GeoCoordinates", "latitude": 40.76, "longitude": -73.98},
        "menu": "https://example.com/menu",
        "servesCuisine": "American",
        "openingHoursSpecification": [
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": ["Monday", "https://schema.org/Tuesday"],
                "opens": "11:30",
                "closes": "22:00:00",
            }
        ],
        "telephone": "+12122459600",
        "url": "https://example.com/daves",
        "priceRange": "$$$",
    },
    "recipe": {
        "@type": "Recipe",
        "name": "Apple pie",
        "image": "https://example.com/pie.jpg",
        "cookTime": "PT1H",
        "prepTime": "PT15M",
        "totalTime": "PT1H15M",
        "recipeYield": "8",
        "nutrition": {"@type": "NutritionInformation", "calories": "270 calories"},
        "recipeIngredient": ["6 apples", "1 crust"],
        "recipeInstructions": [
            {"@type": "HowToStep", "text": "Peel the apples."},
            {
                "@type": "HowToSection",
                "name": "Bake",
                "itemListElement": [{"@type": "HowToStep", "text": "Bake it."}],
            },
        ],
    },
    "event": {
        "@type": "MusicEvent",
        "name": "The Adventures of Kira and Morrison",
        "startDate": "2026-07-21T19:00-05:00",
        "endDate": "2026-07-21T23:00-05:00",
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {"@type": "Place", "name": "Snickerpark", "address": ADDRESS},
        "offers": {
            "@type": "Offer",
            "price": "30",
            "priceCurrency": "USD",
            "availability": "InStock",
            "validFrom": "2026-05-21T12:00",
            "url": "https://example.com/tickets",
        },
    },
    "job-posting": {
        "@type": "JobPosting",
        "title": "Software Engineer",
        "description": "<p>Build things.</p>",
        "datePosted": "2026-01-18",
        "validThrough": "2026-03-18T00:00",
        "employmentType": ["FULL_TIME", "CONTRACTOR"],
        "hiringOrganization": {"@type": "Organization", "name": "Google"},
        "jobLocation": {"@type": "Place", "address": ADDRESS},
        "baseSalary": {
            "@type": "MonetaryAmount",
            "currency": "USD",
            "value": {"@type": "QuantitativeValue", "value": 40.0, "unitText": "HOUR"},
        },
        "directApply": True,
    },
    "video": {
        "@type": "VideoObject",
        "name": "Introducing the self-driving bicycle",
        "thumbnailUrl": ["https://example.com/1x1/photo.jpg"],
        "uploadDate": "2026-03-31T08:00:00+08:00",
        "duration": "PT1M54S",
        "contentUrl": "https://example.com/video/123/file.mp4",
    },
    "software-app": {
        "@type": ["MobileApplication"],
        "name": "Angry Birds",
        "operatingSystem": "ANDROID",
        "applicationCategory": "GameApplication",
        "offers": {"@type": "Offer", "price": 0},
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": "4.6",
            "ratingCount": "8864",
        },
    },
    "course": {
        "@type": "Course",
        "name": "Introduction to Computer Science and Programming",
        "description": "Introductory CS course laying out the basics.",
        "provider": {"@type": "Organization", "name": "University of Technology"},
    },
    "dataset": {
        "@type": "Dataset",
        "name": "NCDC Storm Events Database",
        "description": "Storm Data is provided by the National Weather Service "
        "and contains statistics on storms.",
        "url": "https://catalog.data.gov/dataset/ncdc-storm-events-database",
        "isAccessibleForFree": True,
    },
    "book": {
        "@type": "Book",
        "@id": "https://example.com/work/the_catcher_in_the_rye",
        "name": "The Catcher in the Rye",
        "url": "https://example.com/work/the_catcher_in_the_rye",
        "author": {"@type": "Person", "name": "J.D. Salinger"},
        "workExample": {
            "@type": "Book",
            "@id": "https://example.com/edition/the_catcher_in_the_rye_paperback",
            "bookFormat": "https://schema.org/Paperback",
            "inLanguage": "en",
            "isbn": "9780306406157",
            "potentialAction": {
                "@type": "ReadAction",
                "target": {
                    "@type": "EntryPoint",
                    "urlTemplate": "https://example.com/read",
                    "actionPlatform": "https://schema.org/DesktopWebPlatform",
                },
                "expectsAcceptanceOf": {
                    "@type": "Offer",
                    "category": "purchase",
                    "price": "6.99",
                    "priceCurrency": "USD",
                    "eligibleRegion": {"@type": "Country", "name": "US"},
                },
            },
        },
    },
    "qa-page": {
        "@type": "QAPage",
        "mainEntity": {
            "@type": "Question",
            "name": "How many ounces are there in a pound?",
            "answerCount": 1,
            "acceptedAnswer": {"@type": "Answer", "text": "1 pound (lb) is 16 oz."},
        },
    },
    "discussion-forum": {
        "@type": "DiscussionForumPosting",
        "headline": "I went to the concert!",
        "text": "Look at how cool this concert was!",
        "datePublished": "2024-03-01T08:34:34+02:00",
        "author": {"@type": "Person", "name": "Katie Pope"},
        "comment": {
            "@type": "Comment",
            "text": "Who's the person you're with?",
            "datePublished": "2024-03-01T09:46:02+02:00",
            "author": {"@type": "Person", "name": "Saul Douglas"},
        },
    },
    "profile-page": {
        "@type": "ProfilePage",
        "dateCreated": "2024-12-23T12:34:00-05:00",
        "mainEntity": {"@type": "Person", "name": "Angelo Huff"},
    },
    "site-name": {
        "@type": "WebSite",
        "name": "Example",
        "url": "https://example.com/",
    },
}

# (fixture, feature, what to delete, the path reported missing)
MISSING = [
    ("product", "Product snippet", ["offers", "aggregateRating"], "review"),
    ("product", "Merchant listing", ["image"], "image"),
    ("product", "Merchant listing", ["offers.priceCurrency"], "offers.priceCurrency"),
    ("review", "Review snippet", ["itemReviewed"], "itemReviewed"),
    (
        "review",
        "Review snippet",
        ["reviewRating.ratingValue"],
        "reviewRating.ratingValue",
    ),
    ("aggregate-rating", "Review snippet", ["ratingCount"], "ratingCount"),
    ("breadcrumb", "Breadcrumb", ["itemListElement.0.item"], "itemListElement[0].item"),
    (
        "breadcrumb",
        "Breadcrumb",
        ["itemListElement.1.position"],
        "itemListElement[1].position",
    ),
    ("breadcrumb", "Breadcrumb", ["itemListElement.1.name"], "itemListElement[1].name"),
    ("local-business", "Local business", ["address"], "address"),
    ("recipe", "Recipe", ["image"], "image"),
    ("recipe", "Recipe", ["recipeYield"], "recipeYield"),
    ("event", "Event", ["location.address"], "location.address"),
    ("event", "Event", ["startDate"], "startDate"),
    ("job-posting", "Job posting", ["hiringOrganization"], "hiringOrganization"),
    (
        "job-posting",
        "Job posting",
        ["jobLocation.address.addressCountry"],
        "jobLocation.address.addressCountry",
    ),
    ("video", "Video", ["thumbnailUrl"], "thumbnailUrl"),
    ("software-app", "Software app", ["offers"], "offers.price"),
    ("software-app", "Software app", ["aggregateRating"], "aggregateRating"),
    ("course", "Course list", ["description"], "description"),
    ("dataset", "Dataset", ["name"], "name"),
    ("book", "Book actions", ["workExample.isbn"], "workExample.isbn"),
    (
        "book",
        "Book actions",
        ["workExample.potentialAction.target.urlTemplate"],
        "workExample.potentialAction.target.urlTemplate",
    ),
    ("qa-page", "Q&A", ["mainEntity.answerCount"], "mainEntity.answerCount"),
    (
        "qa-page",
        "Q&A",
        ["mainEntity.acceptedAnswer.text"],
        "mainEntity.acceptedAnswer.text",
    ),
    ("discussion-forum", "Discussion forum", ["author.name"], "author.name"),
    ("profile-page", "Profile page", ["mainEntity.name"], "mainEntity.name"),
    ("site-name", "Site name", ["url"], "url"),
]

# A part the feature can do without, less a property the part needs: the part
# is unusable, the feature is not.
PARTS = [
    ("recipe", "Recipe", ["recipeInstructions.1.name"], "recipeInstructions[1].name"),
    (
        "discussion-forum",
        "Discussion forum",
        ["comment.datePublished"],
        "comment.datePublished",
    ),
    (
        "product",
        "Product snippet",
        ["aggregateRating.ratingValue"],
        "aggregateRating.ratingValue",
    ),
    ("qa-page", "Q&A", ["mainEntity.acceptedAnswer.text"], None),
]

# (fixture, where to write, the bad value, the path of the finding, its code)
INVALID = [
    ("product", "offers.price", "41,90", "offers.price", "invalid-value"),
    ("product", "offers.priceCurrency", "€", "offers.priceCurrency", "invalid-value"),
    (
        "product",
        "offers.availability",
        "InStok",
        "offers.availability",
        "invalid-value",
    ),
    ("product", "gtin13", "4006381333932", "gtin13", "invalid-value"),
    ("product", "offers.price", "0", "offers.price", "refused-by-feature"),
    (
        "review",
        "reviewRating.ratingValue",
        "6",
        "reviewRating.ratingValue",
        "invalid-value",
    ),
    ("review", "author.name", "x" * 100, "author.name", "refused-by-feature"),
    (
        "review",
        "itemReviewed",
        {"@type": "Person", "name": "Ada"},
        "itemReviewed",
        "refused-by-feature",
    ),
    ("aggregate-rating", "ratingCount", "1,204", "ratingCount", "invalid-value"),
    ("article", "datePublished", "2026-09-01 08:00", "datePublished", "invalid-value"),
    (
        "article",
        "dateModified",
        "2026-08-31T08:00:00+02:00",
        "dateModified",
        "date-order",
    ),
    (
        "breadcrumb",
        "itemListElement.0.position",
        "0",
        "itemListElement[0].position",
        "invalid-value",
    ),
    ("local-business", "geo.latitude", "95", "geo.latitude", "invalid-value"),
    (
        "local-business",
        "openingHoursSpecification.0.opens",
        "11h30",
        "openingHoursSpecification.opens",
        "invalid-value",
    ),
    ("local-business", "priceRange", "$" * 100, "priceRange", "invalid-value"),
    ("recipe", "cookTime", "1 hour", "cookTime", "invalid-value"),
    ("event", "startDate", "21/07/2026", "startDate", "invalid-value"),
    ("event", "eventStatus", "Scheduled", "eventStatus", "invalid-value"),
    ("job-posting", "employmentType", "full time", "employmentType", "invalid-value"),
    (
        "job-posting",
        "baseSalary.value.unitText",
        "hourly",
        "baseSalary.value.unitText",
        "refused-by-feature",
    ),
    ("video", "uploadDate", "2026-02-30", "uploadDate", "invalid-value"),
    ("video", "duration", "1:54", "duration", "invalid-value"),
    (
        "software-app",
        "applicationCategory",
        "Game",
        "applicationCategory",
        "invalid-value",
    ),
    ("dataset", "description", "Too short.", "description", "refused-by-feature"),
    ("book", "workExample.isbn", "9780306406158", "workExample.isbn", "invalid-value"),
    (
        "book",
        "workExample.bookFormat",
        "Softcover",
        "workExample.bookFormat",
        "invalid-value",
    ),
    (
        "qa-page",
        "mainEntity.answerCount",
        "two",
        "mainEntity.answerCount",
        "invalid-value",
    ),
    (
        "discussion-forum",
        "datePublished",
        "yesterday",
        "datePublished",
        "invalid-value",
    ),
    ("profile-page", "dateCreated", "12/23/2024", "dateCreated", "invalid-value"),
]

FEATURE_OF = {
    "product": ["Product snippet", "Merchant listing"],
    "review": ["Review snippet"],
    "aggregate-rating": ["Review snippet"],
    "article": ["Article"],
    "breadcrumb": ["Breadcrumb"],
    "local-business": ["Organization", "Local business"],
    "recipe": ["Recipe"],
    "event": ["Event"],
    "job-posting": ["Job posting"],
    "video": ["Video"],
    "software-app": ["Review snippet", "Software app"],
    "course": ["Course list"],
    "dataset": ["Dataset"],
    "book": ["Book actions"],
    "qa-page": ["Q&A"],
    "discussion-forum": ["Discussion forum"],
    "profile-page": ["Profile page"],
    "site-name": ["Site name"],
}


def page(*nodes):
    blocks = "".join(
        '<script type="application/ld+json">'
        + json.dumps({"@context": "https://schema.org", **node})
        + "</script>"
        for node in nodes
    )
    return f"<html><head>{blocks}</head><body></body></html>"


def audited(node):
    result = audit(page(node), url="https://example.com/page")
    assert len(result.records) == 1
    return result.records[0]


def _walk(node, dotted):
    *steps, last = dotted.split(".")
    for step in steps:
        node = node[int(step)] if step.isdigit() else node[step]
    return node, (int(last) if last.isdigit() else last)


def without(name, paths):
    node = copy.deepcopy(VALID[name])
    for dotted in paths:
        parent, key = _walk(node, dotted)
        del parent[key]
    return node


def written(name, dotted, value):
    node = copy.deepcopy(VALID[name])
    parent, key = _walk(node, dotted)
    parent[key] = value
    return node


@pytest.mark.parametrize("name", sorted(VALID))
def test_a_record_that_keeps_to_the_documentation_has_nothing_wrong(name):
    record = audited(VALID[name])

    assert [feature.name for feature in record.features] == FEATURE_OF[name]
    assert all(feature.requirements_met for feature in record.features), [
        (feature.name, feature.missing_required) for feature in record.features
    ]
    assert [f for f in record.findings if f.severity == "error"] == []
    assert all(feature.missing_required == [] for feature in record.features)


@pytest.mark.parametrize(("name", "feature", "deleted", "path"), MISSING)
def test_a_required_property_removed_is_named(name, feature, deleted, path):
    record = audited(without(name, deleted))

    verdict = next(v for v in record.features if v.name == feature)
    assert verdict.requirements_met is False
    assert [entry.split("|")[0] for entry in verdict.missing_required] == [path]
    finding = next(
        f
        for f in record.findings
        if f.code == "missing-required" and f.feature == feature
    )
    assert finding.path == path
    # Book actions reads a feed, not the page: what a page lacks is a note.
    assert finding.severity == ("info" if feature == "Book actions" else "error")
    assert finding.source == "jsonld"
    assert finding.record == 0
    assert finding.rule.startswith("https://developers.google.com/search/")


@pytest.mark.parametrize(("name", "feature", "deleted", "path"), PARTS)
def test_what_an_optional_part_lacks_is_the_parts_not_the_features(
    name, feature, deleted, path
):
    record = audited(without(name, deleted))

    verdict = next(v for v in record.features if v.name == feature)
    if path is None:
        # A Q&A page's accepted answer is what the question needs: not a part.
        assert verdict.requirements_met is False
        return
    assert verdict.requirements_met is True
    assert verdict.missing_required == []
    assert verdict.incomplete_parts == [path]
    finding = next(f for f in record.findings if f.code == "incomplete-part")
    assert (finding.path, finding.severity) == (path, "warning")


@pytest.mark.parametrize(("name", "where", "value", "path", "code"), INVALID)
def test_a_value_in_a_refused_form_is_named_at_its_path(name, where, value, path, code):
    record = audited(written(name, where, value))

    found = [f for f in record.findings if f.path == path and f.code == code]
    assert found, [(f.path, f.code, f.message) for f in record.findings]
    assert found[0].severity == "error"
    assert found[0].source == "jsonld"
    assert found[0].rule.startswith("https://")


def test_the_valid_fixtures_are_not_valid_by_accident():
    """Each invalid write changes the fixture: a check that cannot fail is none."""
    for name, where, value, _path, _code in INVALID:
        parent, key = _walk(copy.deepcopy(VALID[name]), where)
        assert parent[key] != value, (name, where)
