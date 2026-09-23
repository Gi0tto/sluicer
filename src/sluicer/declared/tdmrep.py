"""TDMRep: whether a page's text and data mining rights are reserved.

The TDM Reservation Protocol (TDMRep) is a W3C Community Group final report of
2024-05-10, not a W3C standard, written for the opt-out of the EU's DSM
Directive, Article 4. A site declares it three ways, and its section 6.7 sets
the order: a file at ``/.well-known/tdmrep.json`` first, then the response's
``TDM-Reservation`` and ``TDM-Policy`` headers, which supersede it, then the
page's ``<meta name="tdm-reservation">`` and ``tdm-policy``, which supersede
both; "the absence of tdm-reservation and tdm-policy MUST not reset current
values".

``tdm-reservation`` is ``1`` for reserved and ``0`` for not; any other value
is not a reservation either way, and is passed over. What is reported is the
reservation and where it came from, never an opinion on what it permits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sluicer.declared.rights import Rights
from sluicer.pathmatch import matches, target_of

WELL_KNOWN = "/.well-known/tdmrep.json"
# The most rules read from one file: a site is not a rights registry, and a
# hostile file should not make every page cost its length.
_MOST_RULES = 1000


@dataclass(frozen=True)
class TdmRule:
    """One rule of a ``tdmrep.json``: a path pattern and what it declares."""

    location: str
    reservation: str
    policy: str | None = None


@dataclass(frozen=True)
class Reservation:
    """A page's TDM reservation: ``reserved``, its policy, and which of
    ``tdmrep.json``, ``header`` or ``meta`` last said so."""

    reserved: bool
    policy: str | None
    source: str


def read_tdmrep(text: str | None) -> list[TdmRule]:
    """The rules a ``tdmrep.json`` holds, in its order; none when it holds none.

    The file is "an array of JSON objects", each with a ``location`` and a
    ``tdm-reservation`` (both mandatory) and perhaps a ``tdm-policy``; an
    object missing either is not a rule, and a file that is not an array is
    no file.
    """
    if not text or not text.strip():
        return []
    try:
        parsed = json.loads(text)
    except (ValueError, RecursionError):
        return []
    if not isinstance(parsed, list):
        return []
    rules: list[TdmRule] = []
    for item in parsed[:_MOST_RULES]:
        if not isinstance(item, dict):
            continue
        location = item.get("location")
        reservation = _value(item.get("tdm-reservation"))
        if not isinstance(location, str) or not location or reservation is None:
            continue
        policy = item.get("tdm-policy")
        rules.append(
            TdmRule(location, reservation, policy if isinstance(policy, str) else None)
        )
    return rules


def rule_for(rules: list[TdmRule], url: str) -> TdmRule | None:
    """The rule ``url`` falls under: the first that matches, as the report says.

    "The most specific match is the first in sequence": unlike robots.txt,
    TDMRep takes a file's order, not its longest pattern.
    """
    target = target_of(url)
    return next((rule for rule in rules if matches(rule.location, target)), None)


def reservation(
    rules: list[TdmRule], url: str | None, rights: Rights
) -> Reservation | None:
    """The page's reservation, from the file, its headers and its meta tags.

    ``rights`` is ``Extraction.rights``: its ``tdm_reservation`` and
    ``tdm_policy`` are the page's meta tags, and ``http`` holds the headers'.
    None when nothing declares a reservation either way.
    """
    reserved: str | None = None
    policy: str | None = None
    source = ""
    rule = rule_for(rules, url) if url else None
    if rule is not None:
        reserved, policy, source = rule.reservation, rule.policy, WELL_KNOWN
    for declared, where in ((rights.get("http", {}), "header"), (rights, "meta")):
        value = _value(declared.get("tdm_reservation"))
        if value is not None:
            reserved, source = value, where
        stated_policy = declared.get("tdm_policy")
        if isinstance(stated_policy, str) and stated_policy:
            policy = stated_policy
            source = source or where
    if reserved is None:
        return None
    return Reservation(reserved == "1", policy, source)


def _value(declared: object) -> str | None:
    """``1`` or ``0``, however the file or tag wrote it; None for anything else."""
    if isinstance(declared, bool):
        return None
    if isinstance(declared, int) and declared in (0, 1):
        return str(declared)
    if isinstance(declared, str) and declared.strip() in ("0", "1"):
        return declared.strip()
    return None
