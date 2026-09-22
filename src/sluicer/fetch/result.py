"""What a fetch returns, including how much it had to spend."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


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


Rung = Callable[[str], Fetched]
"""One way of getting a page. It lives here, beside what it returns, so an
adapter does not have to import a type from the orchestrator that drives it."""
