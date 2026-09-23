"""Hold each declared record to the features its type is documented for.

A record here is one item a reader returned -- one JSON-LD node, one top-level
microdata item, one RDFa subject -- before any folding: Google reads each
syntax on its own, and a finding must name the vocabulary that declared the
value. Values are carried the way ``sluicer.declared.merge`` carries them,
every leaf as text, except that a node keeps its ``@id``: a JSON-LD graph that
names its nodes by reference is followed through them here, and a node that is
a record of its own is audited once, where it is, and not again inside every
record that points at it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sluicer.audit import google, values
from sluicer.audit.report import FeatureVerdict, Finding, RecordAudit
from sluicer.audit.schema_org import below
from sluicer.declared.merge import _scalar, _types

AUDITED_READERS = ("jsonld", "microdata", "rdfa")
"""The readers whose items are records: the syntaxes Google reads for rich
results. Microformats describe things too, in a vocabulary Google does not
read for them."""

MAX_DEPTH = 32
"""Deeper than any page nests values; a bound so a hostile one costs a fixed
amount, as everywhere else."""

MAX_NODES = 10_000
"""How many nodes one feature's rules may visit on one record. Following
references, a graph whose nodes all name each other has more paths through it
than any page has nodes, and a walk that exhausts this says so."""

TRUE_REPRESENTATION = (
    "https://developers.google.com/search/docs/appearance/structured-data/sd-policies"
)
"""Google's general guidelines: "Your structured data must be a true
representation of the page content."."""


def normalise(value: object, depth: int = 0) -> Any:
    """``value`` as the audit reads it, or None when it carries nothing.

    As ``sluicer.declared.merge`` does -- a value object is its value, a
    boolean is "true" or "false", blank text is no value -- but an object keeps
    its ``@id`` and its ``@type``, the type spelt the way records spell it, and
    an object that declares only a type is kept: an ``Offer`` with nothing in
    it is exactly what a requirement should be asked of.
    """
    if depth > MAX_DEPTH:
        return None
    if isinstance(value, list):
        items = [
            found for item in value if (found := normalise(item, depth + 1)) is not None
        ]
        return items or None
    if not isinstance(value, dict):
        return _scalar(value)
    for keyword in ("@value", "@list", "@set"):
        if keyword in value:
            return normalise(value[keyword], depth + 1)
    out: dict[str, Any] = {}
    types = _types(value.get("@type"))
    if types:
        out["@type"] = list(types)
    identifier = _scalar(value.get("@id"))
    if identifier is not None:
        out["@id"] = identifier
    for key, item in value.items():
        if key.startswith("@"):
            continue
        found = normalise(item, depth + 1)
        if found is not None:
            out[key] = found
    return out or None


def types_of(value: Any) -> tuple[str, ...]:
    """The types a node declares; merged records write one type as text."""
    declared = value.get("@type") if isinstance(value, dict) else None
    if isinstance(declared, str):
        return (declared,)
    return tuple(declared or ())


def is_a(types: tuple[str, ...], name: str) -> bool:
    """Whether a node of ``types`` is a ``name``, schema.org's subtypes included."""
    return name in types or bool(set(types) & below(name))


def _values(node: dict[str, Any], prop: str) -> list[Any]:
    found = node.get(prop)
    if found is None:
        return []
    return found if isinstance(found, list) else [found]


def _is_reference(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"@id"}


def definitions(nodes: list[Any]) -> dict[str, dict[str, Any]]:
    """Every node that defines an ``@id``, at any depth, the first one first."""
    index: dict[str, dict[str, Any]] = {}
    pending = list(reversed(nodes))
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(reversed(value))
        elif isinstance(value, dict):
            identifier = value.get("@id")
            if isinstance(identifier, str) and not _is_reference(value):
                index.setdefault(identifier, value)
            pending.extend(reversed(list(value.values())))
    return index


@dataclass
class _Record:
    """What one record's audit carries through its walk."""

    source: str
    index: int
    node: dict[str, Any]
    defined: dict[str, dict[str, Any]]
    own_ids: frozenset[str]
    check_urls: bool
    field_sources: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    unfollowed: dict[str, None] = field(default_factory=dict)

    @property
    def type(self) -> str | None:
        types = types_of(self.node)
        return types[0] if types else None

    def source_of(self, path: str) -> str:
        """The reader that declared the property ``path`` starts with."""
        return self.field_sources.get(path.split(".")[0].split("[")[0], self.source)

    def urls_checked(self, path: str) -> bool:
        """JSON-LD's URLs always are; microdata's and RDFa's only when the page's
        address was known, since those readers resolve links against it."""
        return self.check_urls or self.source_of(path) == "jsonld"

    def resolve(self, value: Any) -> Any:
        """A reference replaced by the node it names, when the page defines it."""
        if _is_reference(value) and value["@id"] in self.defined:
            return self.defined[value["@id"]]
        return value

    def find(
        self,
        severity: str,
        code: str,
        message: str,
        path: str = "",
        feature: str | None = None,
        value: str | None = None,
        rule: str | None = None,
    ) -> None:
        self.findings.append(
            Finding(
                severity=severity,
                code=code,
                message=message,
                source=self.source_of(path),
                record=self.index,
                type=self.type,
                path=path,
                feature=feature,
                value=None if value is None else value[:200],
                rule=rule,
            )
        )


def audit_record(
    source: str,
    index: int,
    node: dict[str, Any],
    defined: dict[str, dict[str, Any]],
    own_ids: frozenset[str],
    check_urls: bool = True,
    field_sources: dict[str, str] | None = None,
) -> RecordAudit:
    """Audit one record against every feature its type is documented for.

    Args:
        source: the reader that declared it.
        index: its position among that reader's records.
        node: the record, as ``normalise`` returns it.
        defined: every node on the page with an ``@id``, to follow references.
        own_ids: the ``@id`` of every record the page declares, so that a
            record met inside another is not audited twice.
        check_urls: whether to check that microdata and RDFa URLs are
            absolute; off when the page's address is unknown, since those
            readers resolve links against it. JSON-LD's always are.
        field_sources: for a record merged from several readers, the reader
            of each property, so each finding names its own.
    """
    record = _Record(
        source,
        index,
        node,
        defined,
        own_ids,
        check_urls,
        dict(field_sources or {}),
    )
    types = types_of(node)
    verdicts = [
        _feature(record, feature)
        for feature in google.FEATURES
        if _applies(feature, types, node)
    ]
    _check_values(record, node, "")
    for path in record.unfollowed:
        record.find(
            "info",
            "reference-not-followed",
            f"{path} names a node by @id that the page does not define, so what "
            "the rules ask of it could not be checked",
            path=path,
        )
    not_checked = [
        f"{name} ({url})"
        for kind in types
        if kind in google.NOT_CHECKED
        for name, url in [google.NOT_CHECKED[kind]]
    ]
    return RecordAudit(
        source=source,
        index=index,
        types=list(types),
        features=verdicts,
        not_checked=list(dict.fromkeys(not_checked)),
        findings=record.findings,
    )


def _applies(feature: google.Feature, types: tuple[str, ...], node: Any) -> bool:
    """Whether ``feature`` is documented for a record of ``types``.

    A type the feature excludes counts for nothing, so a record typed only
    ``VideoGame`` is no software app and one typed ``[VideoGame,
    SoftwareApplication]`` is.
    """
    typed = any(
        kind not in feature.excluded
        and (
            kind in feature.types
            or (feature.subtypes and any(kind in below(root) for root in feature.types))
        )
        for kind in types
    )
    return typed and (not feature.when or any(prop in node for prop in feature.when))


def _feature(record: _Record, feature: google.Feature) -> FeatureVerdict:
    if feature.rule is None:
        record.find(
            "info",
            "retired-feature",
            f"{feature.name}: {feature.retired}",
            feature=feature.name,
            rule=feature.url,
        )
        return FeatureVerdict(
            name=feature.name,
            url=feature.url,
            status=feature.status,
            note=feature.retired,
        )
    walk = _Walk(record, feature)
    own = record.node.get("@id")
    walk.rule(
        google.RULES[feature.rule],
        record.node,
        "",
        last=True,
        seen=frozenset({own}) if isinstance(own, str) else frozenset(),
    )
    return FeatureVerdict(
        name=feature.name,
        url=feature.url,
        status=feature.status,
        note=feature.note,
        requirements_met=not walk.required and not walk.refused,
        missing_required=walk.required,
        missing_recommended=walk.recommended,
        incomplete_parts=walk.parts,
    )


class _Walk:
    """One feature's rules, walked over one record.

    A nested value the feature needs -- a merchant listing's ``offers``, a Q&A
    page's ``mainEntity`` -- is part of the feature: what it lacks, the feature
    lacks. One the feature can do without -- an offer's ``shippingDetails``, a
    product's reviews beside its offers -- is a part of its own: Google says
    what such a part must hold "if you want" it used, so what it lacks makes
    the part unusable, not the feature, and is a warning (``incomplete-part``).
    """

    def __init__(self, record: _Record, feature: google.Feature) -> None:
        self.record = record
        self.feature = feature
        self.required: list[str] = []
        self.recommended: list[str] = []
        self.parts: list[str] = []
        self.refused = 0
        self.depth = 0
        self.left = MAX_NODES

    def rule(
        self,
        rule: google.Rule,
        node: dict[str, Any],
        prefix: str,
        last: bool,
        seen: frozenset[str] = frozenset(),
        needed: bool = True,
    ) -> None:
        if self.depth > MAX_DEPTH:
            return
        if self.left <= 0:
            if self.left == 0:
                self.record.find(
                    "info",
                    "walk-stopped",
                    f"{self.feature.name}: stopped after {MAX_NODES} nodes; what "
                    "lies further was not checked",
                    path=prefix.rstrip("."),
                    feature=self.feature.name,
                )
                self.left -= 1
            return
        self.left -= 1
        others = {
            path for need in (*rule.required, *rule.recommended) for path in need.paths
        }
        for severity, needs, missing, code in (
            (
                "error" if needed else "warning",
                rule.required,
                self.required if needed else self.parts,
                "missing-required" if needed else "incomplete-part",
            ),
            ("warning", rule.recommended, self.recommended, "missing-recommended"),
        ):
            kind = "required" if needs is rule.required else "recommended"
            if not self.feature.on_page:
                severity = "info"
            for need in needs:
                others_here = [prefix + path for path in need.paths[1:]]
                also = f" (or {', '.join(others_here)})" if others_here else ""
                for broken in self._need(need, node, prefix, others, last):
                    # The verdict names every alternative, the finding the
                    # first one's path.
                    missing.append("|".join((broken, *others_here)))
                    self.record.find(
                        severity,
                        code,
                        f"{self.feature.name}: {rule.type} is missing {kind} "
                        f"{broken}{also}"
                        + (
                            "; this part cannot be used without it"
                            if code == "incomplete-part"
                            else ""
                        ),
                        path=broken,
                        feature=self.feature.name,
                        rule=self.feature.url,
                    )
        for path, check in rule.checks:
            self._check(check, node, path, prefix, needed)
        self.depth += 1
        for prop, choices in rule.nested:
            found = _values(node, prop)
            for position, value in enumerate(found):
                value = self.record.resolve(value)
                if not isinstance(value, dict) or _is_reference(value):
                    continue
                identifier = value.get("@id")
                if identifier in seen:
                    continue
                chosen = _choose(choices, types_of(value))
                if chosen is None:
                    continue
                step = prefix + prop + (f"[{position}]" if len(found) > 1 else "")
                self.rule(
                    google.RULES[chosen],
                    value,
                    step + ".",
                    last=position == len(found) - 1,
                    seen=seen | {identifier} if isinstance(identifier, str) else seen,
                    needed=needed and _needs(rule, node, prop),
                )
        self.depth -= 1

    def _need(
        self,
        need: google.Need,
        node: dict[str, Any],
        prefix: str,
        others: set[str],
        last: bool,
    ) -> list[str]:
        """Every path where ``need`` is not met; none when it is met or moot.

        With alternatives, one met is enough, and when none is the first one's
        breaks are what is reported.
        """
        if need.only is not None and not is_a(types_of(node), need.only):
            return []
        if need.except_last and last:
            return []
        if need.when is not None and not self._holds(node, need.when, need.when_term):
            return []
        reported: list[str] | None = None
        for alternative in need.paths:
            broken, unknown = self._breaks(
                node, alternative.split("."), prefix, others - {alternative}
            )
            if not broken and not unknown:
                return []
            if broken and reported is None:
                reported = broken
        return reported or []

    def _breaks(
        self,
        node: dict[str, Any],
        segments: list[str],
        prefix: str,
        others: set[str],
        walked: str = "",
    ) -> tuple[list[str], bool]:
        """Every path where the chain ``segments`` breaks below ``node``, and
        whether some of it could not be told.

        A chain that breaks where another need of the same rule begins is not
        reported broken there -- that need reports it -- and a reference the
        page does not define is noted and left alone; either way the chain is
        not known to hold, which is what decides between alternatives. A value
        that is text where the chain wants an object breaks it.
        """
        head, rest = segments[0], segments[1:]
        found = _values(node, head)
        walked = f"{walked}.{head}" if walked else head
        if not found:
            if rest and walked in others:
                return [], True
            return [prefix + ".".join(segments)], False
        if not rest:
            return [], False
        broken: list[str] = []
        unknown = False
        for position, value in enumerate(found):
            step = prefix + head + (f"[{position}]" if len(found) > 1 else "")
            value = self.record.resolve(value)
            if _is_reference(value):
                self.record.unfollowed[step] = None
                unknown = True
                continue
            if not isinstance(value, dict):
                broken.append(f"{step}.{'.'.join(rest)}")
                continue
            below_it, untold = self._breaks(value, rest, step + ".", others, walked)
            broken.extend(below_it)
            unknown = unknown or untold
        return broken, unknown

    def _holds(self, node: dict[str, Any], path: str, wanted: str | None) -> bool:
        found = list(_leaves(node, path.split("."), self.record.resolve))
        if wanted is None:
            return bool(found)
        return any(
            isinstance(value, str) and values.term(value) == wanted for value in found
        )

    def _check(
        self, check: str, node: dict[str, Any], path: str, prefix: str, needed: bool
    ) -> None:
        for where, value in _located(
            node, path.split("."), prefix, self.record.resolve
        ):
            reason = self._reason(check, value)
            if reason is None:
                continue
            if needed:
                self.refused += 1
            self.record.find(
                ("error" if needed else "warning") if self.feature.on_page else "info",
                "refused-by-feature",
                f"{self.feature.name}: {where} is {reason}",
                path=where,
                feature=self.feature.name,
                value=value if isinstance(value, str) else None,
                rule=values.SOURCES.get(check, self.feature.url),
            )

    def _reason(self, check: str, value: Any) -> str | None:
        if check == "review-target":
            if not isinstance(value, dict):
                return "text, where Google asks for a typed item"
            kinds = types_of(value)
            if not kinds:
                return "an item that declares no type"
            if any(is_a(kinds, target) for target in google.REVIEW_TARGETS):
                return None
            return f"a {kinds[0]}, which is not a type Google shows reviews for"
        if check == "not-aggregate-offer":
            if isinstance(value, dict) and "AggregateOffer" in types_of(value):
                return (
                    "an AggregateOffer; merchant listings need an Offer, since "
                    "the merchant has to be the seller"
                )
            return None
        if not isinstance(value, str):
            return None
        return values.FEATURE_CHECKS[check].read(value)


def _needs(rule: google.Rule, node: dict[str, Any], prop: str) -> bool:
    """Whether ``rule`` needs ``node``'s ``prop`` to hold what its own rule asks.

    It does when ``prop`` is required outright, or is the one alternative of a
    required choice the node declares: a product's reviews are needed when it
    has no offers and no rating, and are a part of their own when it has.
    """
    for need in rule.required:
        heads = [path.split(".")[0] for path in need.paths]
        if prop not in heads:
            continue
        others = [head for head in heads if head != prop]
        if not any(head in node for head in others):
            return True
    return False


def _choose(choices: google.Choices, kinds: tuple[str, ...]) -> str | None:
    """The rule a value of ``kinds`` gets: its own type's, then a supertype's,
    then, for a value that declares no type, the first; a value of some other
    type gets none."""
    for wanted, rule in choices:
        if wanted in kinds or wanted == "":
            return rule
    for wanted, rule in choices:
        if is_a(kinds, wanted):
            return rule
    return choices[0][1] if not kinds else None


def _located(
    node: dict[str, Any],
    segments: list[str],
    prefix: str,
    resolve: Callable[[Any], Any],
) -> Iterator[tuple[str, Any]]:
    """Every value at a dotted path below ``node``, with the path that names it."""
    head, rest = segments[0], segments[1:]
    found = _values(node, head)
    for position, value in enumerate(found):
        step = prefix + head + (f"[{position}]" if len(found) > 1 else "")
        value = resolve(value)
        if not rest:
            yield step, value
        elif isinstance(value, dict):
            yield from _located(value, rest, step + ".", resolve)


def _leaves(
    node: dict[str, Any], segments: list[str], resolve: Callable[[Any], Any]
) -> Iterator[Any]:
    for _where, value in _located(node, segments, "", resolve):
        yield value


def _check_values(record: _Record, node: dict[str, Any], prefix: str) -> None:
    """Check every value on the record against what its property always needs.

    A node that is a record of its own is left to its own audit. ``normalise``
    has already bounded how deep the tree goes.
    """
    _check_object(record, node, prefix)
    for key, value in node.items():
        if key.startswith("@"):
            continue
        found = value if isinstance(value, list) else [value]
        for position, item in enumerate(found):
            path = prefix + key + (f"[{position}]" if len(found) > 1 else "")
            if isinstance(item, dict):
                if item.get("@id") in record.own_ids:
                    continue
                _check_values(record, item, path + ".")
                continue
            if not isinstance(item, str):
                continue
            check = values.PROPERTY_CHECKS.get(key)
            if check is None or (check.name == "url" and not record.urls_checked(path)):
                continue
            reason = check.read(item)
            if reason is not None:
                record.find(
                    check.severity,
                    "invalid-value",
                    f"{path} is {reason}",
                    path=path,
                    value=item,
                    rule=check.source,
                )


def _check_object(record: _Record, node: dict[str, Any], prefix: str) -> None:
    """The checks that need two properties of one object: a rating on its scale,
    two dates in order."""
    rating = node.get("ratingValue")
    if isinstance(rating, str):
        reason = values.rating(
            rating, _text(node.get("bestRating")), _text(node.get("worstRating"))
        )
        if reason is not None:
            record.find(
                "error",
                "invalid-value",
                f"{prefix}ratingValue is {reason}",
                path=prefix + "ratingValue",
                value=rating,
                rule=values.SOURCES["rating"],
            )
    for start, end in values.DATE_ORDER:
        first, second = _text(node.get(start)), _text(node.get(end))
        if first is not None and second is not None and values.before(first, second):
            record.find(
                "error",
                "date-order",
                f"{prefix}{end} {second} is before {prefix}{start} {first}",
                path=prefix + end,
                value=second,
                rule=values.SOURCES["date-order"],
            )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


# -- Conflicts between vocabularies ---------------------------------------------

FACTS = (
    "sku",
    "mpn",
    "gtin",
    "gtin8",
    "gtin12",
    "gtin13",
    "gtin14",
    "isbn",
    "offers.price",
    "offers.lowPrice",
    "offers.highPrice",
    "offers.priceCurrency",
    "offers.availability",
    "aggregateRating.ratingValue",
    "aggregateRating.ratingCount",
    "aggregateRating.reviewCount",
    "datePublished",
    "dateModified",
    "startDate",
    "endDate",
)
"""The facts two vocabularies describing one thing must agree on. Names and
descriptions are left out: they legitimately differ in length and wording."""


def conflicts(found: dict[str, list[dict[str, Any]]]) -> list[Finding]:
    """Facts two vocabularies state differently about what must be one thing.

    Two records are one thing when they share a type that each vocabulary
    declares on exactly one record: one product in JSON-LD and one in
    microdata. With two products in either, which is which is a guess, and no
    guess is reported. A value behind a reference the JSON-LD reader did not
    follow is not compared: it is not known.
    """
    findings: list[Finding] = []
    readers = [name for name in AUDITED_READERS if found.get(name)]
    for first_index, first in enumerate(readers):
        for second in readers[first_index + 1 :]:
            for left, right in _pairs(found[first], found[second]):
                findings.extend(
                    _compare(
                        (first, left, found[first][left]),
                        (second, right, found[second][right]),
                    )
                )
    return findings


def _pairs(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> list[tuple[int, int]]:
    pairs: dict[tuple[int, int], None] = {}
    kinds = {kind for node in left for kind in types_of(node)}
    for kind in sorted(kinds):
        here = [i for i, node in enumerate(left) if kind in types_of(node)]
        there = [i for i, node in enumerate(right) if kind in types_of(node)]
        if len(here) == 1 and len(there) == 1:
            pairs[(here[0], there[0])] = None
    return list(pairs)


_Side = tuple[str, int, dict[str, Any]]


def _compare(one: _Side, other: _Side) -> list[Finding]:
    findings = []
    for fact in FACTS:
        mine = _single(one[2], fact.split("."))
        theirs = _single(other[2], fact.split("."))
        if mine is None or theirs is None:
            continue
        if _same(fact.split(".")[-1], mine, theirs):
            continue
        kind = (types_of(one[2]) or ("?",))[0]
        findings.append(
            Finding(
                severity="warning",
                code="conflict",
                message=(
                    f"{kind} {fact} is {mine} in {one[0]} (record {one[1]}) and "
                    f"{theirs} in {other[0]} (record {other[1]})"
                ),
                source=f"{one[0]} and {other[0]}",
                record=one[1],
                type=kind,
                path=fact,
                value=mine,
                rule=TRUE_REPRESENTATION,
            )
        )
    return findings


def _single(node: dict[str, Any], segments: list[str]) -> str | None:
    """The one value at a path, or None when there is none or more than one."""
    value: Any = node
    for segment in segments:
        if not isinstance(value, dict):
            return None
        value = value.get(segment)
        if isinstance(value, list):
            if len(value) != 1:
                return None
            value = value[0]
    return value if isinstance(value, str) else None


def _same(prop: str, mine: str, theirs: str) -> bool:
    if prop in (
        "price",
        "lowPrice",
        "highPrice",
        "ratingValue",
        "ratingCount",
        "reviewCount",
    ):
        if values.number(mine) is None and values.number(theirs) is None:
            return Decimal(mine) == Decimal(theirs)
    elif prop == "priceCurrency":
        return mine.upper() == theirs.upper()
    elif prop == "availability":
        return values.term(mine) == values.term(theirs)
    elif prop in ("sku", "mpn", "isbn") or prop.startswith("gtin"):
        return _identifier(mine) == _identifier(theirs)
    elif prop.startswith(("date", "start", "end")):
        return not values.before(mine, theirs) and not values.before(theirs, mine)
    return mine == theirs


def _identifier(text: str) -> str:
    return "".join(char for char in text if char not in " -").casefold()
