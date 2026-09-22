"""What a fetch returns, including how much it had to spend."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Climb:
    """One step up the ladder, and the measurement that forced it."""

    from_rung: str
    to_rung: str
    reason: str


@dataclass
class Fetched:
    """A page, the rung that got it, and every climb along the way."""

    url: str
    html: str
    status: int
    rung: str
    climbs: list[Climb] = field(default_factory=list)
