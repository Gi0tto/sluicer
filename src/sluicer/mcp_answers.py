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
    "refused_by_site",
    "payment_required",
    "refused_address",
    "fetch_failed",
    "too_large",
    "bad_input",
    "tdm_reserved",
]
"""What a whole tool call can fail with; the HTTP door has a status for each."""

PageErrorCode = Literal[
    "missing_extra",
    "refused_by_robots",
    "refused_by_site",
    "payment_required",
    "refused_address",
    "fetch_failed",
    "too_large",
    "bad_input",
    "tdm_reserved",
    "redirected_off_site",
    "crawl_delay_too_long",
    "rate_limited",
]
"""What one crawled page can have instead of an answer: a call's codes, and three
of a crawl's own, which never end a call and so have no HTTP status."""


class ErrorDetail(TypedDict, total=False):
    """Why a tool could not answer.

    ``retryable`` is true only for ``fetch_failed``, and on a crawled page for
    ``rate_limited``: the same call may work later. Not every ``fetch_failed``
    is: a redirect loop, or an encoding this install cannot read, would be
    met again. The others need something to change first -- an install, an
    input, or the caller's mind about a site that said no.
    """

    code: Required[ErrorCode]
    message: Required[str]
    retryable: Required[bool]
    url: str
    extra: str


class PageError(TypedDict, total=False):
    """Why one crawled page has nothing: ``redirected_off_site``, with the
    ``target`` it pointed to, ``crawl_delay_too_long``, a site asking for more
    time between requests than a crawl waits, ``rate_limited``, a site's
    Retry-After asking for longer than that, or any code a call has."""

    code: Required[PageErrorCode]
    message: Required[str]
    retryable: Required[bool]
    url: str
    extra: str
    target: str


class FieldAnswer(TypedDict):
    value: Any
    source: str
    where: str | None


class RecordAnswer(TypedDict):
    type: str | None
    types: list[str]
    fields: dict[str, FieldAnswer]
    source: str | None
    where: str | None


class SummaryAnswer(TypedDict):
    value: str
    source: str
    key: str
    where: str | None


class ClimbAnswer(TypedDict):
    from_rung: str
    to_rung: str
    reason: str
    seconds: float


class CaptureAnswer(TypedDict):
    """Which archived capture a page was read from."""

    archive: str
    asked: str
    captured: str
    url: str


class FetchRecord(TypedDict, total=False):
    """How a URL was fetched: the rung that got it, and every climb before;
    ``archived`` when it was read from an archive."""

    rung: Required[str]
    status: Required[int]
    seconds: Required[float]
    climbs: Required[list[ClimbAnswer]]
    archived: CaptureAnswer


class ConflictAnswer(TypedDict):
    """A question the page answers two ways: the summary's answer, then the rest."""

    question: str
    answers: list[SummaryAnswer]


class GuessAnswer(TypedDict):
    """What a page shows and may not declare: a guess, its element and rule."""

    value: str
    where: str
    rule: str


class ExtractAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    url: str | None
    summary: dict[str, SummaryAnswer]
    normalised: dict[str, str]
    conflicts: list[ConflictAnswer]
    records: list[RecordAnswer]
    records_left_out: int
    conflicts_left_out: int
    summary_left_out: list[str]
    visible_left_out: list[str]
    normalised_left_out: list[str]
    links_left_out: list[str]
    sources: list[str]
    links: dict[str, Any]
    rights: dict[str, Any]
    visible: dict[str, GuessAnswer]
    fetch: FetchRecord


class TextFromAnswer(TypedDict):
    """Where a page's markdown came from (``sluicer.markdown.MainText``)."""

    source: str
    method: str
    where: str | None


class MarkdownAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    markdown: str
    text_from: TextFromAnswer
    url: str | None
    length: int
    next_offset: int | None
    fetch: FetchRecord


class PageAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    html: str
    url: str
    fetch: FetchRecord
    truncated: bool
    length: int
    next_offset: int | None


class SelectedAnswer(TypedDict):
    value: str
    where: str


class SelectAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    url: str | None
    values: list[SelectedAnswer]
    values_left_out: int
    count: int
    fetch: FetchRecord


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
    rows_left_out: int
    fields: dict[str, str]
    fields_left_out: list[str]
    summary: dict[str, Any]
    summary_left_out: list[str]
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
    content_usage: dict[str, str]
    content_signal: dict[str, str]


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


class TdmAnswer(TypedDict):
    """A page's TDMRep reservation, and which declaration last said it."""

    reserved: bool
    policy: str | None
    source: str


class AuditAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    url: str | None
    records: list[RecordAuditAnswer]
    records_left_out: int
    page: list[FindingAnswer]
    page_left_out: int
    crawlers: list[CrawlerAnswer]
    robots_txt: SiteFileAnswer | None
    other_agents: list[str]
    other_agents_left_out: int
    llms_txt: LlmsTxtAnswer | None
    llms_full_txt: LlmsTxtAnswer | None
    tdm: TdmAnswer | None
    not_checked: list[str]
    errors: int
    warnings: int
    notes: int
    fetch: FetchRecord


class FeedItemAnswer(TypedDict):
    """One item of a feed, as ``sluicer.feeds.FeedItem`` holds it."""

    title: str | None
    link: str | None
    id: str | None
    published: str | None
    updated: str | None
    summary: str | None
    content: str | None
    authors: list[str]
    categories: list[str]
    enclosures: list[dict[str, str]]
    normalised: dict[str, str]


class FeedAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    url: str | None
    format: str
    title: str | None
    link: str | None
    description: str | None
    language: str | None
    updated: str | None
    items: list[FeedItemAnswer]
    items_total: int
    items_left_out: int
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
    urls_left_out: int
    sitemaps: list[SitemapReadAnswer]
    truncated: bool


class RetryAnswer(TypedDict):
    """One time a crawled page was asked again: what the request before came
    to, and the seconds from its end to this one's start."""

    reason: str
    after: float


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
    summary_left_out: list[str]
    sources: list[str]
    types: list[str]
    links: int
    retries: list[RetryAnswer]
    error: PageError


class ExtractedPage(TypedDict, total=False):
    """One page of ``extract_many``: a crawled page's fields but where a crawl
    found it, and its records when they were asked for and fit."""

    ok: Required[bool]
    url: str
    landed: str | None
    fetch: FetchRecord
    canonical: str | None
    summary: dict[str, SummaryAnswer]
    summary_left_out: list[str]
    records: list[RecordAnswer]
    records_left_out: int
    sources: list[str]
    types: list[str]
    links: int
    retries: list[RetryAnswer]
    error: PageError


class ManyAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    pages: list[ExtractedPage]
    pages_left_out: int
    stopped: Literal["done", "time_budget"]


class CrawlAnswer(TypedDict, total=False):
    ok: Required[bool]
    error: ErrorDetail
    url: str
    pages: list[CrawledPage]
    pages_left_out: int
    stopped: Literal["done", "max_pages", "time_budget"]
