"""What Google's structured-data documentation asks of each rich-result feature.

Transcribed from the "Structured data type definitions" of each feature's page
on Google Search Central, every page read on 2026-09-23 and named here with
the date it says it was last updated. A property is required or recommended
because the page's table says so; where the prose adds a condition the table
does not carry -- a breadcrumb's last item needs no ``item``, a recipe with
calories needs a yield -- the condition is written on the property, and that
is the one kind of addition made to the tables.

The rules say what the documentation says, which is not what Google's own
Rich Results Test decides: Google does not publish that validator's rules, and
a page that meets every documented requirement may still not be shown.

A rule is one documented type. Its needs are written as short strings:

* ``"name"`` -- the property must be present;
* ``"price|priceSpecification.price"`` -- one of these will do;
* ``"author.name"`` -- a property of a property, checked on every value of
  ``author`` that is an object;
* ``"menu @FoodEstablishment"`` -- only on a node of that type or below it;
* ``"recipeYield if nutrition.calories"`` -- only when the other path is
  present; ``"previousStartDate if eventStatus=EventRescheduled"`` -- only
  when it holds that schema.org term;
* ``"item except last"`` -- not on the last item of the list the node is in.

A rule may send the values of a property to another rule, chosen by the type
each value declares, the first named being the one for a value that declares
none of them. A choice of None means that type is not checked there.

A property the table recommends but its prose confines to some pages -- a
live video's ``publication``, a seasonal ``validFrom`` -- is kept on the rule
as ``optional`` and never reported missing, and the page's beta properties
likewise: reporting them on every page would be noise the documentation does
not ask for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

READ_ON = "2026-09-23"
"""The day every page cited here was read."""

_DOCS = "https://developers.google.com/search/docs/appearance/structured-data/"
UPDATES = "https://developers.google.com/search/updates"
"""Google Search Central's documentation changelog, last updated 2026-09-18."""


@dataclass(frozen=True)
class Need:
    """One property a rule asks for, or several of which any one will do."""

    paths: tuple[str, ...]
    only: str | None = None
    """The need holds only on a node of this type or below it."""
    when: str | None = None
    """The need holds only when this path is present on the node."""
    when_term: str | None = None
    """... and, when set, holds this schema.org term."""
    except_last: bool = False
    """The need does not hold on the last value of the list the node is in."""


_SPEC = re.compile(
    r"(?P<paths>[^\s]+)"
    r"(?:\s+@(?P<only>\w+))?"
    r"(?:\s+if\s+(?P<when>[\w.@]+)(?:=(?P<term>\w+))?)?"
    r"(?P<last>\s+except\s+last)?"
)


def need(spec: str) -> Need:
    """Read one need from the short form this module's docstring describes."""
    found = _SPEC.fullmatch(spec.strip())
    if found is None:
        raise ValueError(f"not a need: {spec!r}")
    return Need(
        paths=tuple(found["paths"].split("|")),
        only=found["only"],
        when=found["when"],
        when_term=found["term"],
        except_last=found["last"] is not None,
    )


Choices = tuple[tuple[str, "str | None"], ...]


@dataclass(frozen=True)
class Rule:
    """What one feature's documentation asks of one schema.org type."""

    name: str
    type: str
    required: tuple[Need, ...] = ()
    recommended: tuple[Need, ...] = ()
    nested: tuple[tuple[str, Choices], ...] = ()
    """``(property, ((type, rule name), ...))``: the rule each value gets."""
    checks: tuple[tuple[str, str], ...] = ()
    """``(path, check)``: checks from ``values.FEATURE_CHECKS`` this feature
    asks of a path, beyond what the property always gets."""
    optional: tuple[str, ...] = ()
    """Properties the table recommends that its own prose says apply only to
    some pages -- a live video's ``publication``, a seasonal closure's
    ``validFrom`` -- and that are therefore never reported missing."""


RULES: dict[str, Rule] = {}
"""Every rule, by name, so rules can send values to each other -- a comment
holds comments."""


def _rule(
    name: str,
    type_: str,
    required: tuple[str, ...] = (),
    recommended: tuple[str, ...] = (),
    nested: dict[str, str | dict[str, str | None]] | None = None,
    checks: tuple[tuple[str, str], ...] = (),
    optional: tuple[str, ...] = (),
) -> str:
    chosen: list[tuple[str, Choices]] = []
    for prop, target in (nested or {}).items():
        options = target if isinstance(target, dict) else {"": target}
        chosen.append((prop, tuple(options.items())))
    RULES[name] = Rule(
        name,
        type_,
        tuple(need(spec) for spec in required),
        tuple(need(spec) for spec in recommended),
        tuple(chosen),
        checks,
        optional,
    )
    return name


# -- Reviews and ratings: review-snippet, last updated 2026-09-08 -----------

REVIEW_TARGETS = (
    "Book",
    "Course",
    "CreativeWorkSeason",
    "CreativeWorkSeries",
    "Episode",
    "Event",
    "Game",
    "HowTo",
    "LocalBusiness",
    "MediaObject",
    "Movie",
    "MusicPlaylist",
    "MusicRecording",
    "Organization",
    "Product",
    "Recipe",
    "SoftwareApplication",
)
"""The types the review snippet page says a review may be about, with their
subtypes."""

_REVIEW_NESTED = _rule(
    "Review, nested",
    "Review",
    required=("author", "reviewRating", "reviewRating.ratingValue"),
    recommended=(
        "datePublished",
        "reviewRating.bestRating",
        "reviewRating.worstRating",
    ),
    checks=(("author", "under-100"), ("author.name", "under-100")),
)
_AGGREGATE_NESTED = _rule(
    "AggregateRating, nested",
    "AggregateRating",
    required=("ratingCount|reviewCount", "ratingValue"),
    recommended=("bestRating", "worstRating"),
)
_REVIEW = _rule(
    "Review",
    "Review",
    required=(
        "author",
        "itemReviewed",
        "itemReviewed.name",
        "reviewRating",
        "reviewRating.ratingValue",
    ),
    recommended=(
        "datePublished",
        "reviewRating.bestRating",
        "reviewRating.worstRating",
    ),
    checks=(
        ("author", "under-100"),
        ("author.name", "under-100"),
        ("itemReviewed", "review-target"),
    ),
)
_AGGREGATE = _rule(
    "AggregateRating",
    "AggregateRating",
    required=(
        "itemReviewed",
        "itemReviewed.name",
        "ratingCount|reviewCount",
        "ratingValue",
    ),
    recommended=("bestRating", "worstRating"),
    checks=(("itemReviewed", "review-target"),),
)
_REVIEWED = _rule(
    "Reviewed item",
    "Thing",
    required=("name", "review|aggregateRating"),
    nested={"review": _REVIEW_NESTED, "aggregateRating": _AGGREGATE_NESTED},
)

# -- Product snippets: product-snippet, last updated 2026-09-08 --------------

_UNIT_PRICE_SNIPPET = _rule(
    "UnitPriceSpecification, product snippet",
    "UnitPriceSpecification",
    required=("price",),
    recommended=("priceCurrency",),
)
_OFFER_SNIPPET = _rule(
    "Offer, product snippet",
    "Offer",
    required=("price|priceSpecification.price",),
    recommended=(
        "availability",
        "priceCurrency|priceSpecification.priceCurrency",
        "priceValidUntil",
    ),
    nested={"priceSpecification": _UNIT_PRICE_SNIPPET},
)
_AGGREGATE_OFFER = _rule(
    "AggregateOffer",
    "AggregateOffer",
    required=("lowPrice", "priceCurrency"),
    recommended=("highPrice", "offerCount"),
)
_PRODUCT_SNIPPET = _rule(
    "Product, product snippet",
    "Product",
    required=("name", "review|aggregateRating|offers"),
    recommended=("aggregateRating", "offers", "review"),
    nested={
        "offers": {"Offer": _OFFER_SNIPPET, "AggregateOffer": _AGGREGATE_OFFER},
        "aggregateRating": _AGGREGATE_NESTED,
        "review": _REVIEW_NESTED,
    },
)

# -- Merchant listings: merchant-listing, last updated 2026-09-08 ------------

_UNIT_PRICE_MERCHANT = _rule(
    "UnitPriceSpecification, merchant listing",
    "UnitPriceSpecification",
    required=("price", "priceCurrency"),
    recommended=(
        "membershipPointsEarned",
        "priceType",
        "referenceQuantity",
        "validForMemberTier",
        "validFrom",
        "validThrough",
    ),
    nested={
        "referenceQuantity": _rule(
            "QuantitativeValue, unit pricing",
            "QuantitativeValue",
            required=("unitCode", "value"),
            recommended=("valueReference",),
        )
    },
    checks=(("price", "positive-price"),),
)
_SHIPPING_TIME = _rule(
    "QuantitativeValue, shipping time",
    "QuantitativeValue",
    required=("maxValue", "minValue", "unitCode"),
)
_SHIPPING = _rule(
    "OfferShippingDetails",
    "OfferShippingDetails",
    required=(
        "deliveryTime",
        "shippingDestination",
        "shippingRate",
        "shippingRate.currency",
        "shippingRate.value|shippingRate.maxValue",
    ),
    nested={
        "shippingDestination": _rule(
            "DefinedRegion",
            "DefinedRegion",
            required=("addressCountry",),
            recommended=("addressRegion|postalCode",),
        ),
        "deliveryTime": _rule(
            "ShippingDeliveryTime",
            "ShippingDeliveryTime",
            recommended=("handlingTime", "transitTime"),
            nested={"handlingTime": _SHIPPING_TIME, "transitTime": _SHIPPING_TIME},
        ),
    },
)
_RETURN_POLICY = _rule(
    "MerchantReturnPolicy",
    "MerchantReturnPolicy",
    required=("applicableCountry", "returnPolicyCategory"),
    recommended=(
        "merchantReturnDays",
        "returnFees",
        "returnMethod",
        "returnShippingFeesAmount",
    ),
)
_OFFER_MERCHANT = _rule(
    "Offer, merchant listing",
    "Offer",
    required=(
        "price|priceSpecification.price",
        "priceCurrency|priceSpecification.priceCurrency",
    ),
    recommended=(
        "availability",
        "hasMerchantReturnPolicy",
        "itemCondition",
        "priceValidUntil",
        "shippingDetails",
        "url",
        "validFrom",
        "validThrough",
    ),
    nested={
        "priceSpecification": _UNIT_PRICE_MERCHANT,
        "shippingDetails": _SHIPPING,
        "hasMerchantReturnPolicy": _RETURN_POLICY,
    },
    checks=(("price", "positive-price"),),
)
_PRODUCT_MERCHANT = _rule(
    "Product, merchant listing",
    "Product",
    required=("name", "image", "offers"),
    recommended=(
        "aggregateRating",
        "audience",
        "brand.name",
        "category",
        "color",
        "description",
        "gtin|gtin8|gtin12|gtin13|gtin14|isbn",
        "hasAdultConsideration",
        "hasCertification",
        "inProductGroupWithID",
        "isVariantOf",
        "material",
        "mpn",
        "pattern",
        "review",
        "size",
        "sku",
        "subjectOf",
    ),
    nested={
        # A merchant has to be the seller: an AggregateOffer is refused by
        # the "not-aggregate-offer" check, not held to the Offer rule.
        "offers": {"Offer": _OFFER_MERCHANT, "AggregateOffer": None},
        "aggregateRating": _AGGREGATE_NESTED,
        "review": _REVIEW_NESTED,
        "audience": _rule(
            "PeopleAudience",
            "PeopleAudience",
            recommended=(
                "suggestedGender",
                "suggestedMaxAge|suggestedAge.maxValue",
                "suggestedMinAge|suggestedAge.minValue",
            ),
        ),
        "size": {
            "SizeSpecification": _rule(
                "SizeSpecification",
                "SizeSpecification",
                recommended=("name", "sizeGroup", "sizeSystem"),
            )
        },
        "hasCertification": _rule(
            "Certification",
            "Certification",
            required=("issuedBy",),
            recommended=("certificationIdentification", "certificationRating"),
        ),
        "subjectOf": {
            "3DModel": _rule(
                "3DModel",
                "3DModel",
                required=("encoding", "encoding.contentUrl"),
            )
        },
    },
    checks=(("offers", "not-aggregate-offer"),),
)

# -- Article: article, last updated 2026-09-08 ---------------------------------

_ARTICLE = _rule(
    "Article",
    "Article",
    recommended=(
        "author",
        "author.name",
        "author.url|author.sameAs",
        "dateModified",
        "datePublished",
        "headline",
        "image",
    ),
)

# -- Breadcrumb: breadcrumb, last updated 2026-09-08 ---------------------------

_BREADCRUMB = _rule(
    "BreadcrumbList",
    "BreadcrumbList",
    required=("itemListElement",),
    nested={
        "itemListElement": _rule(
            "ListItem, breadcrumb",
            "ListItem",
            required=("item except last", "name|item.name", "position"),
        )
    },
)

# -- Organization: organization, last updated 2026-09-08 -----------------------

_ORGANIZATION = _rule(
    "Organization",
    "Organization",
    recommended=(
        "address",
        "address.addressCountry",
        "address.addressLocality",
        "address.addressRegion",
        "address.postalCode",
        "address.streetAddress",
        "alternateName",
        "contactPoint",
        "contactPoint.email",
        "contactPoint.telephone",
        "description",
        "duns",
        "email",
        "foundingDate",
        "globalLocationNumber",
        "hasMerchantReturnPolicy",
        "hasMemberProgram",
        "hasShippingService",
        "iso6523Code",
        "legalName",
        "leiCode",
        "logo",
        "naics",
        "name",
        "numberOfEmployees",
        "sameAs",
        "taxID",
        "telephone",
        "url",
        "vatID",
    ),
)

# -- Local business: local-business, last updated 2026-09-08 -------------------

_LOCAL_BUSINESS = _rule(
    "LocalBusiness",
    "LocalBusiness",
    required=("address", "name"),
    recommended=(
        "aggregateRating",
        "department",
        "geo",
        "geo.latitude",
        "geo.longitude",
        "menu @FoodEstablishment",
        "openingHoursSpecification",
        "openingHoursSpecification.closes",
        "openingHoursSpecification.dayOfWeek",
        "openingHoursSpecification.opens",
        "priceRange",
        "review",
        "servesCuisine @FoodEstablishment",
        "telephone",
        "url",
    ),
    optional=(
        "openingHoursSpecification.validFrom",
        "openingHoursSpecification.validThrough",
    ),
)

# -- Recipe: recipe, last updated 2026-09-08 -----------------------------------

_HOWTO_STEP = _rule(
    "HowToStep",
    "HowToStep",
    required=("text|itemListElement",),
    recommended=("image", "name", "url", "video"),
    nested={
        "itemListElement": _rule(
            "HowToDirection or HowToTip", "HowToDirection", required=("text",)
        )
    },
)
_VIDEO = "VideoObject"  # defined below, and sent to by name
_RECIPE = _rule(
    "Recipe",
    "Recipe",
    required=("image", "name", "recipeYield if nutrition.calories"),
    recommended=(
        "aggregateRating",
        "author",
        "cookTime",
        "datePublished",
        "description",
        "keywords",
        "nutrition.calories",
        "prepTime",
        "recipeCategory",
        "recipeCuisine",
        "recipeIngredient",
        "recipeInstructions",
        "recipeYield",
        "totalTime",
        "video",
    ),
    nested={
        "recipeInstructions": {
            "HowToStep": _HOWTO_STEP,
            "HowToSection": _rule(
                "HowToSection",
                "HowToSection",
                required=("itemListElement", "name"),
                nested={"itemListElement": {"HowToStep": _HOWTO_STEP}},
            ),
        },
        "video": _VIDEO,
    },
)

# -- Event: event, last updated 2026-09-08 -------------------------------------

_EVENT = _rule(
    "Event",
    "Event",
    required=("location", "location.address", "name", "startDate"),
    recommended=(
        "description",
        "endDate",
        "eventStatus",
        "image",
        "location.name",
        "offers",
        "offers.availability",
        "offers.price",
        "offers.priceCurrency",
        "offers.url",
        "offers.validFrom",
        "organizer",
        "organizer.name",
        "organizer.url",
        "performer",
        "performer.name",
        "previousStartDate if eventStatus=EventRescheduled",
    ),
)

# -- Job posting: job-posting, last updated 2026-09-08 -------------------------

_JOB_POSTING = _rule(
    "JobPosting",
    "JobPosting",
    required=(
        "datePosted",
        "description",
        "hiringOrganization",
        # "The jobLocation property isn't required if
        # applicantLocationRequirements is present", and it "must include the
        # addressCountry property".
        "jobLocation|applicantLocationRequirements",
        "jobLocation.address.addressCountry",
        "title",
    ),
    recommended=(
        "applicantLocationRequirements",
        "baseSalary",
        "directApply",
        "employmentType",
        "identifier",
        "jobLocationType",
        "validThrough",
    ),
    # The page's beta education and experience properties.
    optional=(
        "educationRequirements",
        "experienceInPlaceOfEducation",
        "experienceRequirements",
    ),
    checks=(("baseSalary.value.unitText", "salary-unit"),),
)

# -- Video: video, last updated 2026-09-08 -------------------------------------

_rule(
    _VIDEO,
    "VideoObject",
    required=("name", "thumbnailUrl", "uploadDate"),
    recommended=(
        "contentUrl|embedUrl",
        "description",
        "duration",
        "interactionStatistic",
    ),
    optional=(
        "expires",
        "hasPart",
        "ineligibleRegion",
        "publication",
        "regionsAllowed",
    ),
    nested={
        # Each is optional, and complete when present: "While BroadcastEvent
        # properties aren't required, you must add the following properties
        # if you want your video to display with a LIVE badge."
        "publication": _rule(
            "BroadcastEvent",
            "BroadcastEvent",
            required=("isLiveBroadcast", "startDate", "endDate"),
        ),
        "hasPart": _rule(
            "Clip",
            "Clip",
            required=("name", "startOffset", "url"),
            recommended=("endOffset",),
        ),
        "potentialAction": {
            "SeekToAction": _rule(
                "SeekToAction",
                "SeekToAction",
                required=("target", "startOffset-input"),
            )
        },
    },
)

# -- Software app: software-app, last updated 2026-09-08 -----------------------

_SOFTWARE_APP = _rule(
    "SoftwareApplication",
    "SoftwareApplication",
    required=("name", "offers.price", "aggregateRating|review"),
    recommended=("applicationCategory", "operatingSystem"),
)

# -- Course list: course, last updated 2026-09-08 ------------------------------

_COURSE = _rule(
    "Course",
    "Course",
    required=("description", "name"),
    recommended=("provider",),
)

# -- Dataset: dataset, last updated 2026-09-08 ---------------------------------

_DATASET = _rule(
    "Dataset",
    "Dataset",
    required=("description", "name"),
    recommended=(
        "alternateName",
        "citation",
        "creator",
        "distribution",
        "funder",
        "hasPart|isPartOf",
        "identifier",
        "includedInDataCatalog",
        "isAccessibleForFree",
        "keywords",
        "license",
        "measurementTechnique",
        "sameAs",
        "spatialCoverage",
        "temporalCoverage",
        "url",
        "variableMeasured",
        "version",
    ),
    nested={
        "distribution": _rule(
            "DataDownload",
            "DataDownload",
            required=("contentUrl",),
            recommended=("encodingFormat",),
        )
    },
    checks=(("description", "dataset-description"),),
)

# -- Book actions: book, last updated 2025-12-10 -------------------------------

_BOOK_EDITION = _rule(
    "Book, edition",
    "Book",
    required=("@id", "bookFormat", "inLanguage", "isbn", "potentialAction"),
    recommended=(
        "author",
        "bookEdition",
        "datePublished",
        "identifier",
        "name",
        "sameAs",
        "url",
    ),
    nested={
        "potentialAction": {
            "ReadAction": _rule(
                "ReadAction",
                "ReadAction",
                required=(
                    "expectsAcceptanceOf",
                    "expectsAcceptanceOf.category",
                    "expectsAcceptanceOf.eligibleRegion",
                    "expectsAcceptanceOf.eligibleRegion.name",
                    "target",
                    "target.actionPlatform",
                    "target.urlTemplate",
                ),
                recommended=(
                    "expectsAcceptanceOf.availabilityEnds",
                    "expectsAcceptanceOf.availabilityStarts",
                    "expectsAcceptanceOf.price",
                    "expectsAcceptanceOf.priceCurrency",
                ),
            ),
            "BorrowAction": _rule(
                "BorrowAction",
                "BorrowAction",
                required=(
                    "lender",
                    "lender.@id",
                    "target",
                    "target.actionPlatform",
                    "target.urlTemplate",
                ),
            ),
        },
        "identifier": _rule(
            "PropertyValue, book identifier",
            "PropertyValue",
            required=("propertyID", "value"),
        ),
    },
)
_BOOK = _rule(
    "Book, work",
    "Book",
    required=("@id", "author", "name", "url", "workExample"),
    recommended=("sameAs",),
    nested={
        "workExample": _BOOK_EDITION,
        "author": _rule(
            "Book author",
            "Person",
            required=("name",),
            recommended=("sameAs",),
        ),
    },
)

# -- Q&A: qapage, last updated 2026-09-08 --------------------------------------

_POST_EXTRAS = (
    "author",
    "author.url",
    "comment",
    "commentCount",
    "dateModified",
    "datePublished",
    "digitalSourceType",
    "image",
)
_COMMENT_QA = _rule(
    "Comment, Q&A",
    "Comment",
    required=("text",),
    recommended=(*_POST_EXTRAS, "video"),
    nested={"comment": "Comment, Q&A"},
)
_ANSWER = _rule(
    "Answer",
    "Answer",
    required=("text",),
    recommended=(*_POST_EXTRAS, "upvoteCount", "url", "video"),
    nested={"comment": _COMMENT_QA},
)
_QA_PAGE = _rule(
    "QAPage",
    "QAPage",
    required=("mainEntity",),
    nested={
        "mainEntity": _rule(
            "Question",
            "Question",
            required=("answerCount", "acceptedAnswer|suggestedAnswer", "name"),
            recommended=(*_POST_EXTRAS, "text", "upvoteCount", "video"),
            nested={
                "acceptedAnswer": _ANSWER,
                "suggestedAnswer": _ANSWER,
                "comment": _COMMENT_QA,
            },
        )
    },
)

# -- Discussion forum: discussion-forum, last updated 2026-09-08 ---------------

_INTERACTION = _rule(
    "InteractionCounter",
    "InteractionCounter",
    required=("interactionType", "userInteractionCount"),
)
_FORUM_EXTRAS = (
    "author.url",
    "comment",
    "commentCount",
    "creativeWorkStatus",
    "dateModified",
    "digitalSourceType",
    "image",
    "interactionStatistic",
    "sharedContent",
    "url",
    "video",
)
_COMMENT_FORUM = _rule(
    "Comment, discussion forum",
    "Comment",
    required=("author", "datePublished", "text|image|video"),
    recommended=_FORUM_EXTRAS,
    nested={
        "comment": "Comment, discussion forum",
        "interactionStatistic": _INTERACTION,
    },
)
_FORUM_POST = _rule(
    "DiscussionForumPosting",
    "DiscussionForumPosting",
    required=("author", "author.name", "datePublished", "text|image|video"),
    recommended=(*_FORUM_EXTRAS, "headline", "isPartOf", "text"),
    nested={"comment": _COMMENT_FORUM, "interactionStatistic": _INTERACTION},
)

# -- Profile page: profile-page, last updated 2026-09-08 -----------------------

_PROFILE_PAGE = _rule(
    "ProfilePage",
    "ProfilePage",
    required=("mainEntity",),
    recommended=("dateCreated", "dateModified"),
    nested={
        "mainEntity": _rule(
            "Profile subject",
            "Person",
            required=("name",),
            recommended=(
                "agentInteractionStatistic",
                "alternateName",
                "description",
                "identifier",
                "image",
                "interactionStatistic",
                "sameAs",
            ),
            nested={"interactionStatistic": _INTERACTION},
        )
    },
)

# -- Site names: site-names, last updated 2025-12-10 ---------------------------

_SITE_NAME = _rule(
    "WebSite",
    "WebSite",
    required=("name", "url"),
    recommended=("alternateName",),
)


@dataclass(frozen=True)
class Feature:
    """One rich-result feature, the types it applies to, and the rule it holds
    a record to.

    ``status`` is ``supported``; ``limited``, when Google names a condition
    this audit cannot check -- a data feed, an invitation, a page that is not
    Google Search; or ``retired``, when Google no longer shows the feature,
    and ``rule`` is None: there is nothing left to meet.
    """

    name: str
    url: str
    updated: str
    types: tuple[str, ...]
    rule: str | None
    status: str = "supported"
    note: str = ""
    subtypes: bool = False
    """Whether schema.org's subtypes of ``types`` count too."""
    excluded: tuple[str, ...] = ()
    """Subtypes that do not count on their own, by the page's own words."""
    when: tuple[str, ...] = ()
    """The feature applies only to a record that declares one of these."""
    retired: str = ""
    """When Google stopped showing it, and where it says so."""
    on_page: bool = True
    """False for a feature Google reads from somewhere else -- a data feed --
    whose requirements a page's markup is not held to: what it lacks is
    reported as a note, not as an error or a warning."""


_UPDATED = "2026-09-08"

FEATURES: tuple[Feature, ...] = (
    Feature(
        "Product snippet",
        _DOCS + "product-snippet",
        _UPDATED,
        ("Product",),
        _PRODUCT_SNIPPET,
        subtypes=True,
        # "Car isn't supported automatically as a subtype of Product. For now,
        # include both Car and Product types"; a ProductGroup is a product
        # variant, a feature of its own.
        excluded=("Car", "ProductGroup"),
    ),
    Feature(
        "Merchant listing",
        _DOCS + "merchant-listing",
        _UPDATED,
        ("Product",),
        _PRODUCT_MERCHANT,
        note="For pages where the product can be bought: Google decides "
        "between a merchant listing and a product snippet by what the page "
        "is, which a page's markup does not say.",
        subtypes=True,
        excluded=("Car", "ProductGroup"),
    ),
    Feature(
        "Review snippet",
        _DOCS + "review-snippet",
        _UPDATED,
        ("Review",),
        _REVIEW,
    ),
    Feature(
        "Review snippet",
        _DOCS + "review-snippet",
        _UPDATED,
        ("AggregateRating",),
        _AGGREGATE,
    ),
    Feature(
        "Review snippet",
        _DOCS + "review-snippet",
        _UPDATED,
        # Product is left out: its snippets and listings already hold its
        # reviews and ratings to these rules.
        tuple(target for target in REVIEW_TARGETS if target != "Product"),
        _REVIEWED,
        note="A local business or organization is not eligible for reviews "
        "it controls about itself; that is not something markup says.",
        subtypes=True,
        when=("review", "aggregateRating"),
    ),
    Feature(
        "Article",
        _DOCS + "article",
        _UPDATED,
        ("Article", "NewsArticle", "BlogPosting"),
        _ARTICLE,
        subtypes=True,
        # The discussion forum page claims these.
        excluded=("DiscussionForumPosting", "SocialMediaPosting"),
    ),
    Feature(
        "Breadcrumb",
        _DOCS + "breadcrumb",
        _UPDATED,
        ("BreadcrumbList",),
        _BREADCRUMB,
    ),
    Feature(
        "Organization",
        _DOCS + "organization",
        _UPDATED,
        ("Organization",),
        _ORGANIZATION,
        subtypes=True,
    ),
    Feature(
        "Local business",
        _DOCS + "local-business",
        _UPDATED,
        ("LocalBusiness",),
        _LOCAL_BUSINESS,
        subtypes=True,
    ),
    Feature("Recipe", _DOCS + "recipe", _UPDATED, ("Recipe",), _RECIPE),
    Feature("Event", _DOCS + "event", _UPDATED, ("Event",), _EVENT, subtypes=True),
    Feature(
        "Job posting",
        _DOCS + "job-posting",
        _UPDATED,
        ("JobPosting",),
        _JOB_POSTING,
    ),
    Feature(
        "Video",
        _DOCS + "video",
        _UPDATED,
        ("VideoObject",),
        _VIDEO,
        subtypes=True,
    ),
    Feature(
        "Software app",
        _DOCS + "software-app",
        _UPDATED,
        ("SoftwareApplication",),
        _SOFTWARE_APP,
        subtypes=True,
        # "Google doesn't show a rich result for Software Apps that only have
        # the VideoGame type."
        excluded=("VideoGame",),
    ),
    Feature(
        "Course list",
        _DOCS + "course",
        _UPDATED,
        ("Course",),
        _COURSE,
        status="limited",
        note="Needs at least three courses and Carousel markup on a summary "
        "or all-in-one page; the page's guidelines also ask for a valid "
        "provider, which its table lists as recommended.",
    ),
    Feature(
        "Dataset",
        _DOCS + "dataset",
        _UPDATED,
        ("Dataset",),
        _DATASET,
        status="limited",
        note="Used by Dataset Search only, not Google Search, since November "
        "2025 (Search Central changelog).",
    ),
    Feature(
        "Book actions",
        _DOCS + "book",
        "2025-12-10",
        ("Book",),
        _BOOK,
        status="limited",
        note="Read from a data feed Google accepts from book providers it has "
        "admitted, not from the page; the requirements are the feed's.",
        subtypes=True,
        on_page=False,
    ),
    Feature("Q&A", _DOCS + "qapage", _UPDATED, ("QAPage",), _QA_PAGE),
    Feature(
        "Discussion forum",
        _DOCS + "discussion-forum",
        _UPDATED,
        ("DiscussionForumPosting", "SocialMediaPosting"),
        _FORUM_POST,
    ),
    Feature(
        "Profile page",
        _DOCS + "profile-page",
        _UPDATED,
        ("ProfilePage",),
        _PROFILE_PAGE,
    ),
    Feature(
        "Site name",
        _DOCS + "site-names",
        "2025-12-10",
        ("WebSite",),
        _SITE_NAME,
        note="Read from the site's home page only.",
    ),
    # -- Retired: Google no longer shows these. -------------------------------
    Feature(
        "FAQ",
        UPDATES + "#faq-deprecation",
        "2026-09-18",
        ("FAQPage",),
        None,
        status="retired",
        retired="Not shown in Google Search since 2026-05-07; restricted to "
        "well-known government and health sites from 2023-08-08; its "
        "documentation was removed in June 2026.",
    ),
    Feature(
        "How-to",
        "https://developers.google.com/search/blog/2023/08/howto-faq-changes",
        "2023-09-14",
        ("HowTo",),
        None,
        status="retired",
        retired="Not shown on mobile from August 2023, nor on desktop since "
        "2023-09-13.",
    ),
    Feature(
        "Sitelinks search box",
        "https://developers.google.com/search/blog/2024/10/sitelinks-search-box",
        "2024-10-21",
        ("WebSite",),
        None,
        status="retired",
        when=("potentialAction",),
        retired="Not shown since 2024-11-21. WebSite markup still names the "
        "site (the Site name feature).",
    ),
    Feature(
        "Fact check",
        _DOCS + "factcheck",
        _UPDATED,
        ("ClaimReview",),
        None,
        status="retired",
        retired="Being phased out of Google Search since 2025-06-12; still "
        "read by the Fact Check Explorer.",
    ),
    *(
        Feature(
            name,
            "https://developers.google.com/search/blog/2025/06/simplifying-search-results",
            "2025-09-08",
            types,
            None,
            status="retired",
            when=when,
            retired="Phased out from 2025-06-12; removed from Search Console "
            "and the Rich Results Test on 2025-09-09.",
        )
        for name, types, when in (
            ("Course info", ("Course",), ("hasCourseInstance",)),
            ("Estimated salary", ("Occupation",), ()),
            ("Learning video", ("LearningResource",), ()),
            ("Special announcement", ("SpecialAnnouncement",), ()),
            ("Vehicle listing", ("Car", "Vehicle"), ("offers",)),
        )
    ),
)
"""Every feature the audit knows, in the order records are reported against
them. Retired ones last."""

NOT_CHECKED: dict[str, tuple[str, str]] = {
    "Movie": ("Movie carousel", _DOCS + "movie"),
    "VacationRental": ("Vacation rental", _DOCS + "vacation-rental"),
    "MathSolver": ("Math solver", _DOCS + "math-solvers"),
    "Quiz": ("Education Q&A", _DOCS + "education-qa"),
    "EmployerAggregateRating": (
        "Employer aggregate rating",
        _DOCS + "employer-rating",
    ),
    "ImageObject": ("Image metadata", _DOCS + "image-license-metadata"),
    "ProductGroup": ("Product variants", _DOCS + "product-variants"),
    "MemberProgram": ("Loyalty program", _DOCS + "loyalty-program"),
    "MerchantReturnPolicy": ("Return policy", _DOCS + "return-policy"),
    "ShippingService": ("Shipping policy", _DOCS + "shipping-policy"),
    "ItemList": ("Carousel", _DOCS + "carousel"),
}
"""Types a feature in Google's search gallery (last updated 2026-06-15) is
documented for, that this audit does not check. A record of one of them says
so rather than looking as if nothing applied."""


@dataclass(frozen=True)
class Source:
    """A page this module's rules were read from."""

    title: str
    url: str
    updated: str
    read: str = READ_ON


SOURCES: tuple[Source, ...] = tuple(
    dict.fromkeys(
        Source(feature.name, feature.url.split("#")[0], feature.updated)
        for feature in FEATURES
        if feature.status != "retired"
    )
)
"""The documentation pages behind the supported and limited features."""
