"""What each MCP tool answers, as types the SDK turns into output schemas.

Imported by ``build_server`` only once the ``mcp`` extra is known to be there:
``typing_extensions`` arrives with it, and the base install must not need it.

Every answer carries ``ok``. It is true exactly when the answer can be used as
it is. When it is false, the answer says why in one of two ways: ``error``, when
the tool could not answer at all, or the tool's own reason -- ``failed`` on a
replayed page that broke its extractor's contract, ``lost`` on a heal that lost
data. So an agent that checks only ``ok`` never reads rows from a page that
drifted.

No ``from __future__ import annotations``: ``Required`` inside a string is
invisible to the class's own ``__required_keys__``.
"""

from typing import Any, Literal

from typing_extensions import Required, TypedDict

ErrorCode = Literal[
    "missing_extra",
    "refused_by_robots",
    "refused_address",
    "fetch_failed",
    "too_large",
    "bad_input",
    "redirected_off_site",
    "crawl_delay_too_long",
]


class ErrorDetail(TypedDict, total=False):
    """Why a tool could not answer, or why one crawled page has nothing.

    ``retryable`` is true only for ``fetch_failed``: the same call may work
    later. The others need something to change first -- an install, an input,
    or the caller's mind about a site that said no. The last two codes are a
    crawled page's own: ``redirected_off_site``, with the ``target`` it
    pointed to, and ``crawl_delay_too_long``, a site asking for more time
    between requests than a crawl waits.
    """

    code: Required[ErrorCode]
    message: Required[str]
    retryable: Required[bool]
    url: str
    extra: str
    target: str


class FieldAnswer(TypedDict):
    value: Any
    source: str


class RecordAnswer(TypedDict):
    type: str | None
    types: list[str]
    fields: dict[str, FieldAnswer]
    source: str | None


class SummaryAnswer(TypedDict):
    value: str
    source: str
    key: str


class ClimbAnswer(TypedDict):
    from_rung: str
    to_rung: str
    reason: str
    seconds: float


class FetchRecord(TypedDict):
    """How a URL was fetched: the rung that got it, and every climb before."""

    rung: str
    status: int
    seconds: float
    climbs: list[ClimbAnswer]


class ExtractAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    url: str | None
    summary: dict[str, SummaryAnswer]
    normalised: dict[str, str]
    records: list[RecordAnswer]
    sources: list[str]
    links: dict[str, Any]
    rights: dict[str, Any]
    fetch: FetchRecord


class MarkdownAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    markdown: str
    url: str | None
    fetch: FetchRecord


class PageAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    html: str
    url: str
    fetch: FetchRecord
    truncated: bool
    length: int


class CompileAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    extractor: dict[str, Any]


class CheckAnswer(TypedDict):
    name: str
    ok: bool
    expected: str
    got: str


class RunAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    rows: list[dict[str, Any]]
    summary: dict[str, Any]
    failed: list[CheckAnswer]


class ChangeAnswer(TypedDict, total=False):
    kind: Required[str]
    before: Required[str | None]
    after: Required[str | None]
    evidence: dict[str, int]


class HealAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    extractor: dict[str, Any]
    changes: list[ChangeAnswer]
    lost: bool


class FindingAnswer(TypedDict):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    source: str | None
    record: int | None
    type: str | None
    path: str
    feature: str | None
    value: str | None
    rule: str | None


class FeatureVerdictAnswer(TypedDict):
    name: str
    url: str
    status: Literal["supported", "limited", "retired"]
    note: str
    requirements_met: bool | None
    missing_required: list[str]
    missing_recommended: list[str]
    incomplete_parts: list[str]


class RecordAuditAnswer(TypedDict):
    source: str
    index: int
    types: list[str]
    features: list[FeatureVerdictAnswer]
    not_checked: list[str]
    findings: list[FindingAnswer]


class CrawlerAnswer(TypedDict):
    """One AI agent, and whether the site's robots.txt admits the page."""

    agent: str
    vendor: str
    use: str
    allowed: bool | None
    group: str | None
    honours_robots: bool | None
    note: str
    doc: str


class SiteFileAnswer(TypedDict):
    url: str
    status: int | None
    text: str | None
    error: str | None


class LlmsSectionAnswer(TypedDict):
    name: str
    links: int


class LlmsTxtAnswer(TypedDict):
    url: str
    status: int | None
    present: bool
    name: str | None
    summary: str | None
    sections: list[LlmsSectionAnswer]
    links: int
    length: int
    findings: list[FindingAnswer]


class AuditAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    url: str | None
    records: list[RecordAuditAnswer]
    page: list[FindingAnswer]
    crawlers: list[CrawlerAnswer]
    robots_txt: SiteFileAnswer | None
    other_agents: list[str]
    llms_txt: LlmsTxtAnswer | None
    llms_full_txt: LlmsTxtAnswer | None
    not_checked: list[str]
    errors: int
    warnings: int
    notes: int
    fetch: FetchRecord


class SiteUrlAnswer(TypedDict):
    """One address of a site: its sitemap's ``lastmod`` as written, and the
    ``sitemap`` that listed it, null when it was a link on the start page."""

    url: str
    lastmod: str | None
    sitemap: str | None


class SitemapReadAnswer(TypedDict):
    """One sitemap tried, what it was, and why it was not read, if it was not."""

    url: str
    kind: str | None
    entries: int
    error: str | None


class MapAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    url: str
    source: Literal["sitemaps", "links"]
    urls: list[SiteUrlAnswer]
    sitemaps: list[SitemapReadAnswer]
    truncated: bool


class CrawledPage(TypedDict, total=False):
    """One page of a crawl: its summary and the types it declared, not its
    records, which ``extract_declared`` gives for any page worth reading whole.
    ``ok`` false means ``error`` says why the page has nothing."""

    ok: Required[bool]
    url: str
    depth: int
    found_on: str | None
    landed: str | None
    fetch: FetchRecord
    canonical: str | None
    summary: dict[str, SummaryAnswer]
    sources: list[str]
    types: list[str]
    links: int
    error: ErrorDetail


class CrawlAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    url: str
    pages: list[CrawledPage]
    stopped: Literal["done", "max_pages", "time_budget"]
