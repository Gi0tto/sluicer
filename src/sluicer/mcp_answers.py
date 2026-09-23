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
]


class ErrorDetail(TypedDict, total=False):
    """Why a tool could not answer.

    ``retryable`` is true only for ``fetch_failed``: the same call may work
    later. The others need something to change first -- an install, an input,
    or the caller's mind about a site that said no.
    """

    code: Required[ErrorCode]
    message: Required[str]
    retryable: Required[bool]
    url: str
    extra: str


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
    records: list[RecordAnswer]
    sources: list[str]
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
