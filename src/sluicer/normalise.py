"""What a summary's dates, price and currency mean, when that is certain.

Pages write a date as ``2026-03-06T09:00:00+01:00``, ``Jun 16, 2025``,
``10. Mai 2023`` or ``Tue, 03 Jun 2025 10:00:00 GMT``, and a price as
``41.90``, ``£51.77`` or ``1.299,00 €``. The summary keeps what the page
wrote; this reads it into one form: ISO 8601 for a date, a plain decimal for an
amount, the ISO 4217 code for a currency. Where the text could mean two things
-- ``03/04/2025``, ``1,299``, ``$`` -- there is no normalised value: a guess
would look exactly like a fact.

A date keeps the offset the page gave it and is never moved to UTC, so a date
stays the date the page's readers saw.
"""

from __future__ import annotations

import datetime
import email.utils
import re
import unicodedata
from decimal import Decimal
from typing import TYPE_CHECKING

from sluicer.calendar_names import MONTHS, WEEKDAYS

if TYPE_CHECKING:
    # For its annotation only: the summary reads amounts with this module.
    from sluicer.summary import SummaryField

ISO_4217 = frozenset(
    """
    AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV BRL
    BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE CZK
    DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD
    HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD
    KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK
    MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR
    RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL
    THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES
    VND VUV WST XAD XAF XAG XAU XBA XBB XBC XBD XCD XCG XDR XOF XPD XPF XPT XSU
    XTS XUA XXX YER ZAR ZMW ZWG
    """.split()  # noqa: SIM905 -- the list as the standard prints it
)
"""Every code in ISO 4217's list one, as SIX published it on 2026-09-17."""

# Symbols that name one currency wherever they are written. ``$``, ``¥`` and
# ``kr`` name several, so they name none here.
_SYMBOLS = {
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "₩": "KRW",
    "₽": "RUB",
    "₺": "TRY",
    "₴": "UAH",
    "₪": "ILS",
    "₫": "VND",
    "₦": "NGN",
    "₱": "PHP",
    "฿": "THB",
    "zł": "PLN",
    "kč": "CZK",
    "us$": "USD",
    "r$": "BRL",
    "c$": "CAD",
    "a$": "AUD",
    "nz$": "NZD",
    "hk$": "HKD",
    "s$": "SGD",
}

_ENGLISH_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ),
        start=1,
    )
    for name in names
}

_ISO = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:[.,]\d+)?)?"
    r"\s*(Z|[+-]\d{2}:?\d{2})?(\s*UTC)?)?"
)
# Every language CLDR covers, English's own spellings first: "Sept" is English.
_MONTHS = {**MONTHS, **_ENGLISH_MONTHS}
# A month's name as written, in any script -- "Mai", "ม.ค.", "जनवरी" -- and in
# more than one word where a language writes it so, Scottish Gaelic's "am
# màrt", Romansh's "da december": the shortest run with no digit or comma
# that the date around it allows, looked up whole.
_NAME = r"([^\s\d,](?:[^\d,]*?[^\s\d,])?)\.?"
_MONTH_FIRST = re.compile(_NAME + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})")
# "16 June 2025", "10. Mai 2023", "1er mai 2023", "10 de mayo de 2023", and the
# mark Russian and Ukrainian write after the year, the letters U+0433 and U+0440.
_DAY_FIRST = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th|er|\.|º|ª)?\s*(?:de\s+)?"
    + _NAME
    + r",?\s+(?:de\s+|del\s+)?(\d{4})(?:\s*[\u0433\u0440]\.?)?"
)
# Year first: PubMed's "2023 Jan 7", Hungarian's "2023. május 10.", and
# Lithuanian's "2023 m. gegužės 10 d.".
_YEAR_FIRST = re.compile(
    r"(\d{4})\.?\s*(?:m\.\s*)?" + _NAME + r"\s+(\d{1,2})\.?(?:\s*d\.)?"
)
# Chinese, Japanese and Korean write a date in numbers, each with its unit:
# "2023年5月10日", "2023년 5월 10일". Unambiguous, the units saying which is which.
_UNITS = re.compile(r"(\d{4})\s*[年년]\s*(\d{1,2})\s*[月월]\s*(\d{1,2})\s*[日일]")
# Thai writes a date's year in the Buddhist era, 543 ahead of the common one:
# "10 ม.ค. 2566" is 10 January 2023. A year from 2400 on beside a Thai month
# is that era's; a smaller one is the common era's, as Thai also writes it.
_THAI = re.compile(f"[{chr(0x0E00)}-{chr(0x0E7F)}]")
_BUDDHIST_ERA_FROM = 2400
_BUDDHIST_ERA_OFFSET = 543
# A weekday in any language before the date, with its comma: "Mittwoch, 10.
# Mai 2023". Without the comma only an English one, as before.
_ANY_WEEKDAY = re.compile(r"^([^\s\d,]+?)\.?,\s+")
# The month, day, year, time and offset of JavaScript's Date.toString(), the
# weekday already taken off: "Oct 24 2025 03:22:33 GMT+0000 (GMT)".
_JAVASCRIPT = re.compile(
    r"([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})"
    r"\s+GMT([+-]\d{4})(?:\s+\([^()]*\))?"
)
_WEEKDAY = re.compile(r"^(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+", re.I)
# A twelve-hour clock's time and its half of the day: 10:00 PM, 9:15:30 a.m.
_HALF_OF_THE_DAY = re.compile(
    r"(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp]\.?\s?[Mm]\.?)(?!\w)"
)
# What ``email.utils`` splits a date on.
_TOKENS = re.compile(r"[\s,]+")
# A time of day, and the word after it: ``email.utils`` reads that word as the
# zone, whatever it is.
_TIME_AND_NEXT = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?(?=([\s,]+)(\S+))")
# The zones ``email.utils`` knows by name, and an offset with its sign.
_ZONE = re.compile(r"(?:[+-]\d{4}|UT|UTC|GMT|Z|[ECMP][SD]T|A[SD]T)\b", re.IGNORECASE)


def normalised(summary: dict[str, SummaryField]) -> dict[str, str]:
    """The normalised value of every summary answer that has one, by question.

    ``published`` and ``modified`` as ISO 8601, every price as a decimal with a
    point, ``currency`` as its ISO 4217 code. Each is read from the answer of
    the same name, so it shares that answer's source and key.
    """
    readers = {
        "published": iso_date,
        "modified": iso_date,
        "price": amount,
        "price_regular": amount,
        "price_low": amount,
        "price_high": amount,
        "currency": currency,
        "gtin": gtin,
    }
    found = {}
    for question, read in readers.items():
        answer = summary.get(question)
        value = read(answer.value) if answer is not None else None
        if value is not None:
            found[question] = value
    return found


def iso_date(text: str) -> str | None:
    """``text`` as an ISO 8601 date or date-time, or None when it is not sure.

    Read: ISO 8601 and its common variants (a space for the ``T``, an offset
    without a colon, a trailing ``UTC``), RFC 2822 (``Tue, 03 Jun 2025 10:00:00
    GMT``), a month's name in any language CLDR covers either side of the day
    (``Jun 16, 2025``, ``16 June 2025``, ``10. Mai 2023``, ``10 de mayo de
    2023``, Russian's with its year mark) or after the year (PubMed's ``2023 Jan 7``,
    Hungarian's ``2023. május 10.``), a weekday before it with its comma,
    the numbers with units Chinese, Japanese and Korean write (``2023年5月10日``),
    and JavaScript's ``Date.toString()`` (``Fri Oct 24 2025 03:22:33 GMT+0000
    (GMT)``). A Thai month's year from 2400 on is the Buddhist era's, and is
    converted. Not read: all-number forms other than ISO's, since
    ``03/04/2025`` is March in one country and April in another.
    """
    text = text.strip()
    iso = _ISO.fullmatch(text)
    if iso:
        return _from_iso(iso)
    if "," in text[:12] and ":" in text:
        rfc_2822 = _from_rfc_2822(text)
        if rfc_2822 is not None:
            return rfc_2822
    units = _UNITS.fullmatch(text)
    if units:
        year, month, day = (int(part) for part in units.groups())
        return _day(year, month, day)
    words = _WEEKDAY.sub("", text)
    weekday = _ANY_WEEKDAY.match(words)
    if weekday and _month_or_day(weekday.group(1)) in WEEKDAYS:
        words = words[weekday.end() :]
    javascript = _JAVASCRIPT.fullmatch(words)
    if javascript:
        return _from_javascript(javascript)
    for pattern, year_at, month_at, day_at in (
        (_MONTH_FIRST, 3, 1, 2),
        (_DAY_FIRST, 3, 2, 1),
        (_YEAR_FIRST, 1, 2, 3),
    ):
        match = pattern.fullmatch(words)
        if match:
            name = match.group(month_at)
            named = _MONTHS.get(_month_or_day(name))
            if named is not None:
                year = int(match.group(year_at))
                if year >= _BUDDHIST_ERA_FROM and _THAI.search(name):
                    year -= _BUDDHIST_ERA_OFFSET
                return _day(year, named, int(match.group(day_at)))
    return None


def _from_rfc_2822(text: str) -> str | None:
    """An RFC 2822 date, read by ``email.utils``, when its year is written whole.

    ``email.utils`` reads a two-digit year by a rule of its own, 25 as 2025
    and 69 as 1969, and a three-digit one as the first millennium's, where
    the page may have meant another century or another field: a guess.
    RFC 850's ``03-Jun-2025`` writes the year inside its date's token, and
    ``-2025`` is an offset, not a year.

    A twelve-hour clock, ``10:00 PM``, is read with its half of the day: to
    ``email.utils`` "PM" was a zone it did not know, and the evening was the
    morning. An hour no such clock shows, ``13:05 PM``, is not read.

    Only a zone is an offset: ``email.utils`` reads whatever word follows the
    time as one, and "10:05 am 4 min read" was at +00:04. A word after the
    time that is neither an offset with its sign nor a zone it knows by name
    ends the date there, which then has no offset.
    """
    halves = list(_HALF_OF_THE_DAY.finditer(text))
    if len(halves) > 1:
        return None
    half = halves[0] if halves else None
    if half is not None:
        # Taken out, or "PM" is a zone email.utils does not know, and ignores.
        text = text[: half.start(3)] + text[half.end(3) :]
    time = _TIME_AND_NEXT.search(text)
    if time is not None and not _zone_or_year(time, text):
        # "10:05 am 4 min read": the 4 is no zone, and was read as +00:04.
        text = text[: time.end()]
    try:
        parsed = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if half is not None:
        hour, minute = int(half.group(1)), int(half.group(2))
        if not 1 <= hour <= 12 or (parsed.hour, parsed.minute) != (hour, minute):
            return None
        after_noon = half.group(3)[0] in "Pp"
        parsed = parsed.replace(hour=hour % 12 + (12 if after_noon else 0))
    year = f"{parsed.year:04}"
    if not any(
        token == year or (any(c.isalpha() for c in token) and year in token.split("-"))
        for token in _TOKENS.split(text)
    ):
        return None
    return parsed.isoformat()


def _zone_or_year(time: re.Match[str], text: str) -> bool:
    """Whether the word after ``time`` is the date's zone, or its year.

    asctime's order writes the year after the time, ``03 Jun 10:00:00 2025``;
    four digits there are the year only where none was written before it.
    """
    after = time.group(2)
    if _ZONE.match(after):
        return True
    return bool(
        re.fullmatch(r"\d{4}", after)
        and not re.search(r"(?<!\d)\d{4}(?!\d)", text[: time.start()])
    )


def _month_or_day(name: str) -> str:
    """A month's or weekday's name as the tables spell it."""
    return unicodedata.normalize("NFC", name).casefold().rstrip(".")


def _from_javascript(match: re.Match[str]) -> str | None:
    """A ``Date.toString()``: its moment, at the offset it was written in."""
    name, day, year, hour, minute, second, zone = match.groups()
    month = _ENGLISH_MONTHS.get(name.lower())
    date = _day(int(year), month, int(day)) if month else None
    if date is None:
        return None
    return _at(date, hour, minute, second, zone)


def _from_iso(match: re.Match[str]) -> str | None:
    year, month, day, hour, minute, second, zone, utc = match.groups()
    date = _day(int(year), int(month), int(day))
    if date is None or hour is None:
        return date
    # A trailing UTC with no offset before it is the offset it names; after
    # one, the offset written is the one kept.
    return _at(date, hour, minute, second, zone or ("+00:00" if utc else None))


def _at(
    date: str, hour: str, minute: str, second: str | None, zone: str | None
) -> str | None:
    """``date`` at a time of day, with the offset it was written in, if any."""
    try:
        moment = datetime.time(int(hour), int(minute), int(second or 0))
    except ValueError:
        return None
    offset = ""
    if zone == "Z":
        offset = "Z"
    elif zone:
        digits = zone.replace(":", "")
        if int(digits[1:3]) > 23 or int(digits[3:]) > 59:
            return None
        offset = f"{digits[0]}{int(digits[1:3]):02}:{int(digits[3:]):02}"
    return f"{date}T{moment.isoformat()}{offset}"


def _day(year: int, month: int, day: int) -> str | None:
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


_AMOUNT = re.compile(r"[\d.,\s']+")
_SPACE_OR_APOSTROPHE = re.compile(r"[\s']")
# A number as JSON writes one with an exponent, sign left out: a price has none.
_EXPONENT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?[eE][+-]?[0-9]+")
# Thousands grouped with a space or an apostrophe: one to three digits, then
# threes, then perhaps a separator and what follows it.
_SPACED = re.compile(r"\d{1,3}(?:[\s']\d{3})+(?:[.,]\d+)?")
# Longer than any price written with its symbol and grouping: past it, a text
# is a sentence or a page, and reading it as one would cost its length for
# every currency symbol there is.
_LONGEST_AMOUNT = 64
_BY_LENGTH = sorted(_SYMBOLS, key=len, reverse=True)


def amount(text: str) -> str | None:
    """``text`` as a decimal amount with a point, or None when it is not sure.

    A currency symbol or code around the number is dropped. When both a point
    and a comma appear, the last one is the decimal separator. When only one
    appears once, it is the decimal separator unless exactly three digits follow
    it: ``1,299`` and ``1.299`` are refused, since each is a thousand somewhere
    and a little over one somewhere else (``0.999`` is not ambiguous). Digits
    grouped by a separator, a space or an apostrophe are grouped in thousands,
    ``1 299,00`` or ``1'299.00``, or the text is refused: ``12 50`` is not 1250.
    A number JSON writes with an exponent, ``1.5e3``, is the amount it names.
    """
    stripped = text.strip()
    if len(stripped) > _LONGEST_AMOUNT:
        return None
    if _EXPONENT.fullmatch(stripped):
        return _from_exponent(stripped)
    for symbol in _BY_LENGTH:
        lowered = stripped.lower()
        if lowered.startswith(symbol):
            stripped = stripped[len(symbol) :]
        elif lowered.endswith(symbol):
            stripped = stripped[: -len(symbol)]
    stripped = re.sub(r"^[A-Za-z]{3}\s*|\s*[A-Za-z]{3}$", "", stripped.strip())
    stripped = stripped.strip().lstrip("$¥").rstrip("$¥").strip()
    if (
        not stripped
        or not _AMOUNT.fullmatch(stripped)
        or not any(c.isdigit() for c in stripped)
    ):
        return None
    # \s holds the no-break spaces French and Swiss prices group with. A space
    # or an apostrophe only ever groups thousands: "12 50" is two numbers, or
    # twelve and a half, and never 1250.
    if _SPACE_OR_APOSTROPHE.search(stripped) and not _SPACED.fullmatch(stripped):
        return None
    number = _SPACE_OR_APOSTROPHE.sub("", stripped)
    points, commas = number.count("."), number.count(",")
    if points and commas:
        decimal = "." if number.rfind(".") > number.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        whole, _, fraction = number.rpartition(decimal)
        if not _grouped(whole, thousands) or not fraction.isdigit():
            return None
        number = whole.replace(thousands, "") + "." + fraction
    elif points + commas == 1:
        separator = "." if points else ","
        whole, _, fraction = number.partition(separator)
        if len(fraction) == 3 and whole not in ("", "0"):
            return None
        number = f"{whole or '0'}.{fraction}"
    elif points + commas > 1:
        # Only thousands separators, all alike: 1.299.000 or 1,299,000.
        separator = "." if points else ","
        if not _grouped(number, separator):
            return None
        number = number.replace(separator, "")
    if not re.fullmatch(r"\d+(\.\d+)?", number):
        return None
    whole, _, fraction = _in_ascii(number).partition(".")
    whole = whole.lstrip("0") or "0"
    return f"{whole}.{fraction}" if fraction else whole


def _from_exponent(number: str) -> str | None:
    """A number JSON wrote with an exponent, ``1.5e3``, as a plain decimal.

    Its point is a point and nothing is grouped, so it is never ambiguous;
    an exponent that would write more digits than a price holds is refused.
    """
    value = Decimal(number)
    if abs(value.adjusted()) > _LONGEST_AMOUNT:
        return None
    whole, _, fraction = format(value, "f").partition(".")
    return f"{whole}.{fraction}" if fraction else whole


def _grouped(number: str, separator: str) -> bool:
    """Whether ``number`` is digits in thousands: 1 to 3, then threes."""
    groups = number.split(separator)
    return (
        all(group.isdigit() for group in groups)
        and 1 <= len(groups[0]) <= 3
        and all(len(group) == 3 for group in groups[1:])
    )


def gtin(text: str) -> str | None:
    """``text`` as a GTIN whose check digit is right, or None.

    GTIN-8, -12, -13 and -14, and an ISBN-13, which is a GTIN-13; spaces and
    hyphens dropped. A wrong check digit is a typo or an invention, and the
    number it would normalise to identifies some other product, or none.
    Measured on the pages as served that the scoreboard holds: 12 of 17 GTINs
    were wrong.
    """
    digits = re.sub(r"[\s-]", "", text)
    # Decimal digits only: ``str.isdigit`` also takes a superscript two, which
    # ``int`` refuses, and that was a traceback from a page that wrote one.
    if not digits.isdecimal() or len(digits) not in (8, 12, 13, 14):
        return None
    digits = _in_ascii(digits)
    body, check = digits[:-1], int(digits[-1])
    total = sum(
        int(digit) * (3 if position % 2 == 0 else 1)
        for position, digit in enumerate(reversed(body))
    )
    return digits if (10 - total % 10) % 10 == check else None


def _in_ascii(digits: str) -> str:
    """``digits`` with every decimal digit written as its ASCII one.

    ``\\d`` and ``int`` read every script's decimal digits, fullwidth and
    Arabic-Indic among them, and a normalised value is one form whatever
    the page's script: a date's are rewritten by ``int``, and these the same.
    """
    if digits.isascii():
        return digits
    return "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in digits)


def currency(text: str) -> str | None:
    """``text`` as an ISO 4217 code, or None when it names no one currency."""
    stripped = text.strip()
    if stripped.upper() in ISO_4217:
        return stripped.upper()
    return _SYMBOLS.get(stripped.lower())
