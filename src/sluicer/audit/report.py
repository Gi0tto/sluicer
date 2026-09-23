"""What an audit says, as plain data: every class here turns into JSON with
``dataclasses.asdict``."""

from __future__ import annotations

from dataclasses import dataclass, field

from sluicer.declared.tdmrep import Reservation

SEVERITIES = ("error", "warning", "info")
"""``error``: the page breaks a rule its documentation states -- a required
property missing, a value in a form refused. ``warning``: it could do what the
documentation recommends and does not, or two of its declarations disagree.
``info``: worth knowing and nothing to fix, such as a feature Google retired."""


@dataclass(frozen=True)
class Finding:
    """One thing the audit found, where, and the rule it comes from.

    ``source`` names who declared it: a reader (``jsonld``, ``microdata``,
    ``rdfa``) for a record, ``html`` or ``opengraph`` for the page itself,
    ``robots.txt`` or ``llms.txt`` for the site. ``record`` is the record's
    position among that reader's records, from 0, in document order; ``path``
    the property, with a position in brackets for a value in a list
    (``offers[1].price``). ``rule`` is the address of the page the rule is
    written on.
    """

    severity: str
    code: str
    message: str
    source: str | None = None
    record: int | None = None
    type: str | None = None
    path: str = ""
    feature: str | None = None
    value: str | None = None
    rule: str | None = None


@dataclass(frozen=True)
class FeatureVerdict:
    """One rich-result feature a record's type is documented for.

    ``requirements_met`` is true when every property the feature's
    documentation requires is there and no check the feature adds refused a
    value; it is None for a retired feature, which has nothing left to meet.
    Whether a value is well formed -- a price, a date -- is reported by the
    record's findings, whichever feature it serves. A missing property that
    has alternatives is written with them,
    ``offers[0].price|offers[0].priceSpecification.price``.
    ``incomplete_parts`` are what an optional part lacks -- shipping details,
    a review beside an offer -- which makes that part unusable and not the
    feature.
    """

    name: str
    url: str
    status: str
    note: str = ""
    requirements_met: bool | None = None
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    incomplete_parts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RecordAudit:
    """One declared record, the features it is documented for, and its findings.

    ``not_checked`` names features Google documents for the record's type that
    this audit does not check, so that no feature is not mistaken for none.
    """

    source: str
    index: int
    types: list[str]
    features: list[FeatureVerdict] = field(default_factory=list)
    not_checked: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


@dataclass(frozen=True)
class CrawlerVerdict:
    """Whether a site's robots.txt lets one AI agent have the page.

    ``allowed`` is None when the robots.txt could not be read. ``group`` is the
    ``User-agent`` line that decided, ``*`` for the catch-all, None when no
    group applies and everything is allowed. ``honours_robots`` is what the
    vendor's page says of the agent: False where it says a user-requested
    fetch may ignore robots.txt, None where it does not say.

    ``content_usage`` and ``content_signal`` are the preferences the deciding
    group states for the page -- the IETF aipref drafts' ``Content-Usage`` and
    Cloudflare's ``Content-Signal`` -- each category ``allow`` or
    ``disallow``, an unknown one absent; empty for a page the agent may not
    fetch, which has none.
    """

    agent: str
    vendor: str
    use: str
    allowed: bool | None
    group: str | None
    honours_robots: bool | None
    note: str
    doc: str
    content_usage: dict[str, str] = field(default_factory=dict)
    content_signal: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SiteFile:
    """What a site answered for one file beside the page.

    ``status`` is None when nothing answered, and ``error`` says why nothing
    was read: a network failure, or a robots.txt that refuses it to us.
    """

    url: str
    status: int | None = None
    text: str | None = None
    error: str | None = None

    @property
    def found(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


@dataclass(frozen=True)
class Site:
    """The files a site serves beside a page, as ``sluicer.fetch.site`` read them."""

    robots: SiteFile
    llms_txt: SiteFile
    llms_full_txt: SiteFile
    tdmrep: SiteFile | None = None
    """TDMRep's ``/.well-known/tdmrep.json``, when it was read."""


@dataclass(frozen=True)
class LlmsSection:
    """One H2 section of an llms.txt file and how many links it lists."""

    name: str
    links: int


@dataclass(frozen=True)
class LlmsTxt:
    """What a site's llms.txt says, read against llmstxt.org's format."""

    url: str
    status: int | None
    present: bool
    name: str | None = None
    summary: str | None = None
    sections: list[LlmsSection] = field(default_factory=list)
    links: int = 0
    length: int = 0
    findings: list[Finding] = field(default_factory=list)


@dataclass
class Audit:
    """Everything one audit found, and what it did not check.

    ``records`` holds each record JSON-LD, microdata and RDFa declared.
    ``page`` holds what the page as a whole lacks or contradicts. ``crawlers``
    and the two llms files are there only when the site was read;
    ``robots_txt`` then says what the site answered for it, its text left out,
    and ``other_agents`` every ``User-agent`` it names that no agent here
    answers to.
    ``tdm`` is the page's TDMRep reservation -- from the site's tdmrep.json
    when the site was read, and the page's own meta tags -- or None when
    nothing declares one.
    ``not_checked`` says, in a sentence each, what was not checked and why, so
    that a silence is never taken for a pass. ``errors``, ``warnings`` and
    ``notes`` count the findings of each severity, everywhere.
    """

    url: str | None = None
    records: list[RecordAudit] = field(default_factory=list)
    page: list[Finding] = field(default_factory=list)
    crawlers: list[CrawlerVerdict] = field(default_factory=list)
    robots_txt: SiteFile | None = None
    other_agents: list[str] = field(default_factory=list)
    llms_txt: LlmsTxt | None = None
    llms_full_txt: LlmsTxt | None = None
    tdm: Reservation | None = None
    not_checked: list[str] = field(default_factory=list)
    errors: int = 0
    warnings: int = 0
    notes: int = 0

    def findings(self) -> list[Finding]:
        """Every finding, records first, then the page, then the site."""
        found = [finding for record in self.records for finding in record.findings]
        found.extend(self.page)
        for llms in (self.llms_txt, self.llms_full_txt):
            if llms is not None:
                found.extend(llms.findings)
        return found
