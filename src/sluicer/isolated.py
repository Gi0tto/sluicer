"""A caller's selectors, evaluated in a process of their own and stopped in time.

A selector is a small program, and XPath 1.0 lets one line of it cost the
square or the cube of a page's size: ``//p[count(//p) > 0]`` visits every
paragraph once for each paragraph, and CSS's sibling combinator is no better,
``p ~ p`` taking 110 s on 8,000 paragraphs, a page of 72 KB. lxml evaluates it
in C, where nothing stops it from outside: a server that evaluated its callers'
selectors on its own threads was held by four of them, every worker busy for
as long as they ran and every later call answered 504.

No rule on what a selector may say bounds that -- the costly selectors
include ordinary CSS -- so the servers bound the time instead. The MCP tools
(``sluicer mcp``, and ``sluicer serve`` over HTTP) evaluate a caller's
selectors through ``isolated``: in a child process, killed at a deadline --
the call's own budget when the HTTP door set one with ``until``, and never
past ``SECONDS`` -- and answered as the selector's fault. The command line and the
library evaluate selectors in the caller's own process, since whoever writes
the selector is then the one who waits.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import pickle
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

__all__ = ["SECONDS", "TookTooLong", "isolated", "until"]

SECONDS = 30.0
"""The most a caller's selectors may run on the pages of one call, whatever
the call's own budget: the pages are handed to them parsed, so this is
evaluation, not fetching, and far past what any honest selector takes. Held to
the call's two-minute budget alone, four hostile selectors kept every reading
worker of ``sluicer serve`` busy for all of it."""

_DEADLINE: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "sluicer_isolated_deadline", default=None
)

# The child: this interpreter, told where to import from, then handed the
# work. Not multiprocessing's spawn, which imports the parent's ``__main__``
# again in the child: a server started from a script without a ``__main__``
# guard would start again there, and one started from stdin could not.
_CHILD = (
    "import pickle, sys; sys.path[:] = pickle.load(sys.stdin.buffer); "
    "from sluicer.isolated import _child; _child()"
)

T = TypeVar("T")


class TookTooLong(Exception):
    """Work run ``isolated`` was stopped at its deadline."""

    def __init__(self, seconds: float) -> None:
        super().__init__(
            f"the selectors ran for longer than the call may and were stopped "
            f"after {seconds:g} s: XPath and CSS let one selector cost the "
            "square or the cube of a page's size, and this one does on this page"
        )
        self.seconds = seconds


@contextlib.contextmanager
def until(deadline: float) -> Iterator[None]:
    """Hold work run ``isolated`` inside this block to ``deadline``, a
    ``time.monotonic()`` reading: the budget of the call it belongs to."""
    token = _DEADLINE.set(deadline)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def isolated(function: Callable[..., T], *args: Any) -> T:
    """``function(*args)`` in a child process, stopped at the deadline.

    ``function`` is a module's own, and ``args`` and what it returns or raises
    are pickled across: a page's HTML and a selector's text go, values and
    ``Run``s come back. About 90 ms go to starting the child.

    Raises:
        TookTooLong: the deadline passed first; the child is killed.
        Exception: whatever ``function`` raised, raised here.
    """
    deadline = _DEADLINE.get()
    seconds = SECONDS if deadline is None else min(SECONDS, deadline - time.monotonic())
    if seconds <= 0:
        raise TookTooLong(0)
    work = pickle.dumps(sys.path) + pickle.dumps((function, args))
    # -I: no working directory or script folder on the path, no PYTHON*
    # variables, no user site. With -c alone the working directory came first,
    # and a pickle.py in the folder an agent started the server in -- a cloned
    # repository -- ran before the parent's path was taken.
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", _CHILD],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    try:
        answer, _ = child.communicate(work, timeout=seconds)
    except subprocess.TimeoutExpired:
        child.kill()
        child.communicate()
        raise TookTooLong(round(seconds, 1)) from None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    if child.returncode != 0 or not answer:
        raise RuntimeError(
            f"the process evaluating {function.__name__} ended with no answer, "
            f"exit code {child.returncode}"
        )
    how, what = pickle.loads(answer)
    if how == "raised":
        raise what
    return what  # type: ignore[no-any-return]


def _child() -> None:
    """The child's side: the work from stdin, what it gave to stdout."""
    function, args = pickle.load(sys.stdin.buffer)
    # stdout is the answer's channel: whatever the work might print goes to
    # stderr instead, where a server's log is.
    answering = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    try:
        answer: tuple[str, Any] = ("returned", function(*args))
    except Exception as raised:  # noqa: BLE001 -- raised again in the parent
        answer = ("raised", raised)
    with answering:
        pickle.dump(answer, answering)
