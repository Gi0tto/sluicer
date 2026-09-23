"""What a summary's dates, price and currency mean, when that is certain.

Pages write a date as ``2026-03-06T09:00:00+01:00``, ``Jun 16, 2025`` or
``Tue, 03 Jun 2025 10:00:00 GMT``, and a price as ``41.90``, ``£51.77`` or
``1.299,00 €``. The summary keeps what the page wrote; this reads it into one
form: ISO 8601 for a date, a plain decimal for an amount, the ISO 4217 code for
a currency. Where the text could mean two things -- ``03/04/2025``, ``1,299``,
``$`` -- there is no normalised value: a guess would look exactly like a fact.

A date keeps the offset the page gave it and is never moved to UTC, so a date
stays the date the page's readers saw.
"""

from __future__ import annotations

import datetime
import email.utils
import re
from typing import TYPE_CHECKING

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

_MONTHS = {
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
    r"\s*(Z|[+-]\d{2}:?\d{2})?(?:\s*UTC)?)?"
)
_MONTH_FIRST = re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})")
_DAY_FIRST = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})")
_WEEKDAY = re.compile(r"^(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+", re.I)


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
    GMT``), and English month names either side of the day (``Jun 16, 2025``,
    ``16 June 2025``). Not read: all-number forms other than ISO's, since
    ``03/04/2025`` is March in one country and April in another.
    """
    text = text.strip()
    iso = _ISO.fullmatch(text)
    if iso:
        return _from_iso(iso)
    if "," in text[:12] and ":" in text:
        try:
            parsed = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            parsed = None
        if parsed is not None:
            return parsed.isoformat()
    words = _WEEKDAY.sub("", text)
    for pattern, month_at, day_at in ((_MONTH_FIRST, 1, 2), (_DAY_FIRST, 2, 1)):
        match = pattern.fullmatch(words)
        if match:
            month = _MONTHS.get(match.group(month_at).lower())
            if month is None:
                return None
            return _day(int(match.group(3)), month, int(match.group(day_at)))
    return None


def _from_iso(match: re.Match[str]) -> str | None:
    year, month, day, hour, minute, second, zone = match.groups()
    date = _day(int(year), int(month), int(day))
    if date is None or hour is None:
        return date
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
        offset = f"{digits[0]}{digits[1:3]}:{digits[3:]}"
    return f"{date}T{moment.isoformat()}{offset}"


def _day(year: int, month: int, day: int) -> str | None:
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


_AMOUNT = re.compile(r"[\d.,\s']+")
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
    and a little over one somewhere else (``0.999`` is not ambiguous).
    """
    stripped = text.strip()
    if len(stripped) > _LONGEST_AMOUNT:
        return None
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
    # \s holds the no-break spaces French and Swiss prices group with.
    number = re.sub(r"[\s']", "", stripped)
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
    whole, _, fraction = number.partition(".")
    whole = whole.lstrip("0") or "0"
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
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14):
        return None
    body, check = digits[:-1], int(digits[-1])
    total = sum(
        int(digit) * (3 if position % 2 == 0 else 1)
        for position, digit in enumerate(reversed(body))
    )
    return digits if (10 - total % 10) % 10 == check else None


def currency(text: str) -> str | None:
    """``text`` as an ISO 4217 code, or None when it names no one currency."""
    stripped = text.strip()
    if stripped.upper() in ISO_4217:
        return stripped.upper()
    return _SYMBOLS.get(stripped.lower())
