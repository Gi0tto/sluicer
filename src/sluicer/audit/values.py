"""What one declared value can get wrong, checked without judgement.

Each check reads one value as the page wrote it -- text, since every reader
hands leaves over as text -- and says why it is wrong, or nothing. Which
property a check applies to is ``PROPERTY_CHECKS``; the page each rule comes
from is ``SOURCES``. A check never consults the clock or the network: a price
that is valid today is valid tomorrow, so the same page always gets the same
answer.

What is checked is the form Google's documentation and schema.org ask for, not
whether the value is true: ``41.90`` passes as a price whatever the product
costs.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlsplit

from sluicer.audit.schema_org import ENUMERATIONS


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


READ_ON = "2026-09-23"
"""The day every page cited here was read."""

ISO_4217_PUBLISHED = "2026-09-17"
"""The edition of ISO 4217 list one below, as its maintenance agency dates it."""

# ISO 4217 list one, the codes in current use, from the maintenance agency's
# own file:
# https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml
ISO_4217 = _words(
    "AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV BRL"
    " BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE CZK"
    " DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD"
    " HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD"
    " KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK"
    " MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR"
    " RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL"
    " THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES"
    " VND VUV WST XAD XAF XAG XAU XBA XBB XBC XBD XCD XCG XDR XOF XPD XPF XPT XSU"
    " XTS XUA XXX YER ZAR ZMW ZWG"
)

_GOOGLE = "https://developers.google.com/search/docs/appearance/structured-data/"

SOURCES = {
    "price": "https://schema.org/price",
    "positive-price": _GOOGLE + "merchant-listing",
    "currency": _GOOGLE + "product-snippet",
    "date": _GOOGLE + "article",
    "date-order": _GOOGLE + "merchant-listing",
    "duration": _GOOGLE + "recipe",
    "url": _GOOGLE + "local-business",
    "enumeration": "https://schema.org/docs/releases.html#v30.1",
    "rating": _GOOGLE + "review-snippet",
    "count": _GOOGLE + "review-snippet",
    "position": _GOOGLE + "breadcrumb",
    "coordinate": "https://schema.org/GeoCoordinates",
    "gtin": "https://www.gs1.org/services/check-digit-calculator",
    "isbn": "https://www.isbn-international.org/sites/default/files/"
    "ISBN%20Manual%202012%20-corr.pdf",
    "time": _GOOGLE + "local-business",
    "boolean": "https://schema.org/Boolean",
    "employment-type": _GOOGLE + "job-posting",
    "job-location-type": _GOOGLE + "job-posting",
    "salary-unit": _GOOGLE + "job-posting",
    "app-category": _GOOGLE + "software-app",
    "under-100": _GOOGLE + "review-snippet",
    "price-range": _GOOGLE + "local-business",
    "dataset-description": _GOOGLE + "dataset",
    "not-aggregate-offer": _GOOGLE + "merchant-listing",
}
"""Where each check's rule is written. Every page was read on ``READ_ON``."""

_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_SIGNED = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
_WHOLE = re.compile(r"[0-9]+")
_SCHEMA_ORG = re.compile(r"(?i:https?://(?:www\.)?schema\.org/|schema:)")
_CURRENCY_SIGNS = frozenset("$€£¥₹₽₩₺₴₪฿₫")

_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_TIME = re.compile(
    r"([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:[.,]([0-9]+))?)?"
    r"(Z|[+-][0-9]{2}(?::?[0-9]{2})?)?"
)
_DURATION = re.compile(
    r"P(?=[0-9T])(?:[0-9]+(?:[.,][0-9]+)?Y)?(?:[0-9]+(?:[.,][0-9]+)?M)?"
    r"(?:[0-9]+(?:[.,][0-9]+)?W)?(?:[0-9]+(?:[.,][0-9]+)?D)?"
    r"(?:T(?=[0-9])(?:[0-9]+(?:[.,][0-9]+)?H)?(?:[0-9]+(?:[.,][0-9]+)?M)?"
    r"(?:[0-9]+(?:[.,][0-9]+)?S)?)?"
)

EMPLOYMENT_TYPES = frozenset(
    {
        "FULL_TIME",
        "PART_TIME",
        "CONTRACTOR",
        "TEMPORARY",
        "INTERN",
        "VOLUNTEER",
        "PER_DIEM",
        "OTHER",
    }
)
"""The case-sensitive values Google's job posting page lists for employmentType."""

SALARY_UNITS = frozenset({"HOUR", "DAY", "WEEK", "MONTH", "YEAR"})
"""The case-sensitive unitText values Google's job posting page lists for a salary."""

APP_CATEGORIES = _words(
    "GameApplication SocialNetworkingApplication TravelApplication"
    " ShoppingApplication SportsApplication LifestyleApplication"
    " BusinessApplication DesignApplication DeveloperApplication"
    " DriverApplication EducationalApplication HealthApplication"
    " FinanceApplication SecurityApplication BrowserApplication"
    " CommunicationApplication DesktopEnhancementApplication"
    " EntertainmentApplication MultimediaApplication HomeApplication"
    " UtilitiesApplication ReferenceApplication"
)
"""The supported app types Google's software app page lists for applicationCategory."""


def term(text: str) -> str:
    """``https://schema.org/InStock``, ``schema:InStock`` and ``InStock`` alike."""
    return _SCHEMA_ORG.sub("", text.strip(), count=1)


def price(text: str) -> str | None:
    if _NUMBER.fullmatch(text):
        return None
    if _NUMBER.fullmatch(text.replace(",", ".", 1)):
        return "a comma where schema.org asks for a full stop as the decimal point"
    if any(sign in text for sign in _CURRENCY_SIGNS):
        return "a currency symbol in the number; the currency is priceCurrency's"
    return "not a number written with the digits 0-9 and a full stop"


def number(text: str) -> str | None:
    return None if _NUMBER.fullmatch(text) else "not a number"


def positive(text: str) -> str | None:
    """Merchant listings, unlike product snippets, need a price above zero."""
    if not _NUMBER.fullmatch(text):
        return None  # ``price`` has said what is wrong with it
    if Decimal(text) > 0:
        return None
    return "merchant listings need a price greater than zero"


def currency(text: str) -> str | None:
    if text in ISO_4217:
        return None
    if text.upper() in ISO_4217:
        return f"ISO 4217 codes are upper case: {text.upper()}"
    if any(sign in text for sign in _CURRENCY_SIGNS):
        return "a currency symbol, not a three-letter ISO 4217 code"
    return f"not a code in ISO 4217 list one (published {ISO_4217_PUBLISHED})"


@dataclass(frozen=True)
class Instant:
    """A date as ISO 8601 writes it, with the time and zone when it has them."""

    day: date
    at: time | None = None
    zone: timezone | None = None

    def aware(self) -> datetime | None:
        """The moment itself, when the value says both its time and its zone."""
        if self.at is None or self.zone is None:
            return None
        return datetime.combine(self.day, self.at, tzinfo=self.zone)


def parse_instant(text: str) -> Instant | str:
    """``text`` as an ``Instant``, or the reason it is not ISO 8601.

    A complete calendar date, optionally followed by ``T``, a time to the minute
    or finer, and a zone. Python's own ``fromisoformat`` is not used: before
    3.11 it refuses a ``Z``, and it accepts forms ISO 8601 does not.
    """
    found = _DATE.match(text)
    if found is None:
        return "not an ISO 8601 date (YYYY-MM-DD), with or without a time"
    try:
        day = date(*(int(part) for part in found.groups()))
    except ValueError:
        return "not a day the calendar has"
    rest = text[found.end() :]
    if not rest:
        return Instant(day)
    if rest[0] == " " and _TIME.fullmatch(rest[1:]):
        return "a space where ISO 8601 puts a T between the date and the time"
    clock = _TIME.fullmatch(rest[1:]) if rest[0] == "T" else None
    if clock is None:
        return "not an ISO 8601 date (YYYY-MM-DD), with or without a time"
    hours, minutes, seconds, fraction, zone = clock.groups()
    try:
        at = time(
            int(hours),
            int(minutes),
            int(seconds or 0),
            int((fraction or "0")[:6].ljust(6, "0")),
        )
    except ValueError:
        return "not a time the clock has"
    offset = _zone(zone)
    if isinstance(offset, str):
        return offset
    return Instant(day, at, offset)


def _zone(zone: str | None) -> timezone | str | None:
    if zone is None:
        return None
    if zone == "Z":
        return timezone.utc
    digits = zone[1:].replace(":", "")
    hours, minutes = int(digits[:2]), int(digits[2:] or 0)
    if hours > 23 or minutes > 59:
        return "not a time zone offset"
    delta = timedelta(hours=hours, minutes=minutes)
    return timezone(-delta if zone[0] == "-" else delta)


def instant(text: str) -> str | None:
    found = parse_instant(text)
    return found if isinstance(found, str) else None


def duration(text: str) -> str | None:
    if _DURATION.fullmatch(text) and not text.endswith("T"):
        return None
    return "not an ISO 8601 duration such as PT1H30M"


def url(text: str) -> str | None:
    try:
        parts = urlsplit(text)
    except ValueError:
        return "not a URL"
    if parts.scheme.lower() in ("http", "https") and parts.netloc:
        return None
    if not parts.scheme:
        return "a relative address; Google asks for fully-qualified URLs"
    return f"a {parts.scheme}: address, not an http or https URL"


def enumeration(name: str) -> Callable[[str], str | None]:
    """A check that the value is one of the terms of schema.org's ``name``."""
    terms = ENUMERATIONS[name]
    folded = {known.casefold(): known for known in terms}

    def check(text: str) -> str | None:
        written = term(text)
        if written in terms:
            return None
        if written.casefold() in folded:
            return f"schema.org spells the term {folded[written.casefold()]}"
        return f"not a term of schema.org's {name}"

    return check


def count(text: str) -> str | None:
    if _WHOLE.fullmatch(text):
        return None
    return "not a whole number of zero or more"


def position(text: str) -> str | None:
    if _WHOLE.fullmatch(text) and int(text) >= 1:
        return None
    return "not a whole number from 1"


def _coordinate(limit: int, name: str) -> Callable[[str], str | None]:
    def check(text: str) -> str | None:
        if not _SIGNED.fullmatch(text):
            return f"not a {name} in decimal degrees"
        if abs(Decimal(text)) > limit:
            return f"a {name} beyond {limit} degrees"
        return None

    return check


latitude = _coordinate(90, "latitude")
longitude = _coordinate(180, "longitude")


def _gtin_valid(digits: str) -> bool:
    """GS1's check digit: weights 3 and 1 from the right, modulo 10."""
    body, check = digits[:-1], int(digits[-1])
    total = sum(
        int(digit) * (3 if index % 2 == 0 else 1)
        for index, digit in enumerate(reversed(body))
    )
    return (10 - total % 10) % 10 == check


def gtin(lengths: tuple[int, ...]) -> Callable[[str], str | None]:
    """A check for a GTIN of one of ``lengths`` digits and a valid check digit."""
    spelled = " or ".join(str(length) for length in lengths)

    def check(text: str) -> str | None:
        if not _WHOLE.fullmatch(text) or len(text) not in lengths:
            return f"not a GTIN of {spelled} digits"
        if not _gtin_valid(text):
            return "the check digit does not match the digits before it"
        return None

    return check


def isbn(text: str) -> str | None:
    digits = re.sub(r"[\s-]", "", text).upper()
    if re.fullmatch(r"97[89][0-9]{10}", digits):
        return None if _gtin_valid(digits) else "the ISBN-13 check digit is wrong"
    if re.fullmatch(r"[0-9]{9}[0-9X]", digits):
        total = sum(
            (10 - index) * (10 if char == "X" else int(char))
            for index, char in enumerate(digits)
        )
        return None if total % 11 == 0 else "the ISBN-10 check digit is wrong"
    return "not an ISBN-13 or ISBN-10"


def clock_time(text: str) -> str | None:
    found = _TIME.fullmatch(text)
    if found is None:
        return "not a time written hh:mm or hh:mm:ss"
    hours, minutes, seconds = (int(part or 0) for part in found.groups()[:3])
    if hours > 23 or minutes > 59 or seconds > 59:
        return "not a time the clock has (hours run 00 to 23)"
    return None


def boolean(text: str) -> str | None:
    if term(text).casefold() in ("true", "false"):
        return None
    return "not true or false"


def _one_of(allowed: frozenset[str], what: str) -> Callable[[str], str | None]:
    def check(text: str) -> str | None:
        return None if text in allowed else f"not one of the {what} Google lists"

    return check


employment_type = _one_of(EMPLOYMENT_TYPES, "employment types")
salary_unit = _one_of(SALARY_UNITS, "salary units")


def job_location_type(text: str) -> str | None:
    return None if text == "TELECOMMUTE" else "Google knows one value, TELECOMMUTE"


def app_category(text: str) -> str | None:
    if term(text) in APP_CATEGORIES:
        return None
    return "not one of the app types Google lists"


def under_100(text: str) -> str | None:
    return None if len(text) < 100 else "100 characters or longer"


def dataset_description(text: str) -> str | None:
    if 50 <= len(text) <= 5000:
        return None
    return f"{len(text)} characters, where Google asks for 50 to 5000"


@dataclass(frozen=True)
class Check:
    """One check: what it is called, how it reads a value, and where it is written.

    ``severity`` is ``error`` for a value the documentation refuses, and
    ``warning`` for one it only advises against: Google supports relative
    URLs in some places and asks for fully-qualified ones in others.
    """

    name: str
    read: Callable[[str], str | None]
    source: str
    severity: str = "error"


def _check(
    name: str,
    read: Callable[[str], str | None],
    source: str = "",
    severity: str = "error",
) -> Check:
    return Check(name, read, SOURCES[source or name], severity)


_PRICE = _check("price", price)
_CURRENCY = _check("currency", currency)
_DATE_CHECK = _check("date", instant)
_DURATION_CHECK = _check("duration", duration)
_URL = _check("url", url, severity="warning")
_COUNT = _check("count", count)

PROPERTY_CHECKS: dict[str, Check] = {
    "price": _PRICE,
    "lowPrice": _PRICE,
    "highPrice": _PRICE,
    "priceCurrency": _CURRENCY,
    "currency": _CURRENCY,
    **{
        name: _DATE_CHECK
        for name in (
            "availabilityEnds",
            "availabilityStarts",
            "dateCreated",
            "dateModified",
            "datePosted",
            "datePublished",
            "endDate",
            "expires",
            "foundingDate",
            "previousStartDate",
            "priceValidUntil",
            "startDate",
            "uploadDate",
            "validFrom",
            "validThrough",
        )
    },
    **{
        name: _DURATION_CHECK
        for name in ("cookTime", "duration", "prepTime", "timeRequired", "totalTime")
    },
    **{
        name: _URL
        for name in (
            "contentUrl",
            "embedUrl",
            "image",
            "item",
            "logo",
            "menu",
            "sameAs",
            "thumbnailUrl",
            "url",
        )
    },
    "availability": _check(
        "availability", enumeration("ItemAvailability"), "enumeration"
    ),
    "itemCondition": _check(
        "itemCondition", enumeration("OfferItemCondition"), "enumeration"
    ),
    "eventStatus": _check("eventStatus", enumeration("EventStatusType"), "enumeration"),
    "eventAttendanceMode": _check(
        "eventAttendanceMode",
        enumeration("EventAttendanceModeEnumeration"),
        "enumeration",
    ),
    "dayOfWeek": _check("dayOfWeek", enumeration("DayOfWeek"), "enumeration"),
    "bookFormat": _check("bookFormat", enumeration("BookFormatType"), "enumeration"),
    "returnPolicyCategory": _check(
        "returnPolicyCategory",
        enumeration("MerchantReturnEnumeration"),
        "enumeration",
    ),
    "returnFees": _check(
        "returnFees", enumeration("ReturnFeesEnumeration"), "enumeration"
    ),
    "returnMethod": _check(
        "returnMethod", enumeration("ReturnMethodEnumeration"), "enumeration"
    ),
    "bestRating": _check("rating", number),
    "worstRating": _check("rating", number),
    "ratingCount": _COUNT,
    "reviewCount": _COUNT,
    "answerCount": _COUNT,
    "commentCount": _COUNT,
    "upvoteCount": _COUNT,
    "offerCount": _COUNT,
    "userInteractionCount": _COUNT,
    "position": _check("position", position),
    "latitude": _check("coordinate", latitude),
    "longitude": _check("coordinate", longitude),
    "gtin": _check("gtin", gtin((8, 12, 13, 14))),
    "gtin8": _check("gtin", gtin((8,))),
    "gtin12": _check("gtin", gtin((12,))),
    "gtin13": _check("gtin", gtin((13,))),
    "gtin14": _check("gtin", gtin((14,))),
    "isbn": _check("isbn", isbn),
    "opens": _check("time", clock_time),
    "closes": _check("time", clock_time),
    **{
        name: _check("boolean", boolean)
        for name in (
            "directApply",
            "experienceInPlaceOfEducation",
            "isAccessibleForFree",
            "isLiveBroadcast",
        )
    },
    "employmentType": _check("employment-type", employment_type),
    "jobLocationType": _check("job-location-type", job_location_type),
    "applicationCategory": _check("app-category", app_category),
    "priceRange": _check("price-range", under_100),
}
"""The check each property's value gets, wherever on a record it appears.

Each applies to text: an ``image`` or an ``item`` that is an object is not a
URL, and the object's own ``url`` is checked where it is.
"""

FEATURE_CHECKS: dict[str, Check] = {
    "positive-price": _check("positive-price", positive),
    "under-100": _check("under-100", under_100),
    "dataset-description": _check("dataset-description", dataset_description),
    "salary-unit": _check("salary-unit", salary_unit),
}
"""Checks one feature asks of one path, beyond what the property always needs."""


def rating(value: str, best: str | None, worst: str | None) -> str | None:
    """Why ``value`` is not a rating on its scale, or None.

    Google reads a number, a fraction ("6 / 10") or a percentage ("60%"). A
    number is on the scale ``worstRating`` to ``bestRating``, which are 1 and
    5 when the page does not say.
    """
    text = value.strip()
    fraction = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*/\s*([0-9]+(?:\.[0-9]+)?)", text)
    if fraction:
        top, bottom = (Decimal(part) for part in fraction.groups())
        if bottom == 0 or top > bottom:
            return f"{text} is not a fraction between 0 and 1"
        return None
    percent = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*%", text)
    if percent:
        return None if Decimal(percent.group(1)) <= 100 else f"{text} is above 100%"
    if not _NUMBER.fullmatch(text):
        if _NUMBER.fullmatch(text.replace(",", ".", 1)):
            return "a comma where a full stop belongs"
        return "not a number, a fraction or a percentage"
    high = _decimal(best, Decimal(5))
    low = _decimal(worst, Decimal(1))
    if high is None or low is None:
        return None  # the scale itself is wrong, and is reported where it is
    if high <= low:
        return f"bestRating {high} is not above worstRating {low}"
    if not low <= Decimal(text) <= high:
        return f"{text} is outside the scale {low} to {high}"
    return None


def _decimal(text: str | None, default: Decimal) -> Decimal | None:
    if text is None:
        return default
    return Decimal(text.strip()) if _NUMBER.fullmatch(text.strip()) else None


DATE_ORDER = (
    ("datePublished", "dateModified"),
    ("startDate", "endDate"),
    ("validFrom", "validThrough"),
    ("validFrom", "priceValidUntil"),
)
"""Pairs of dates where the second may not come before the first."""


def before(earlier: str, later: str) -> bool:
    """True when ``later`` is before ``earlier``, as far as both say.

    Two moments with a time and a zone are compared as moments; otherwise only
    their days are, since a date without a zone is no particular moment.
    """
    first, second = parse_instant(earlier), parse_instant(later)
    if isinstance(first, str) or isinstance(second, str):
        return False
    start, end = first.aware(), second.aware()
    if start is not None and end is not None:
        return end < start
    return second.day < first.day
