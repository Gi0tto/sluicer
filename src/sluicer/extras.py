"""One answer to "is the optional extra installed?", for every entry point.

Sluicer's base install reads HTML you already have. Fetching, markdown and the
MCP server each need a tree that most readers never want, so each lives behind
an optional extra and is imported when it is first used, not when the module is
imported. Every one of those entry points then has to answer the same question,
and answering it separately is how the answers drift: this package once carried
three exception classes, three message strings and three lazy-import helpers,
and the third had quietly adopted a different rule with no note of why.

The rule, stated once
---------------------
Exactly one failure means "the extra is not installed": the *top-level* package
is absent. Measured, that is a ``ModuleNotFoundError`` whose ``name`` is the
first dotted component of the module being imported.

Everything else is re-raised untouched, and this is the part worth defending. A
``ModuleNotFoundError`` naming a *submodule* -- ``scrapling.fetchers``,
``mcp.server.fastmcp`` -- means the package is there and something inside it is
not. So does a plain ``ImportError`` raised while a working package executes.
Both are broken installs, and a broken install told to "install it with uv pip
install ..." is told to install what it already has: the real bug is hidden
behind an instruction that cannot help. A traceback is the right answer there,
and it is the answer a wider match would take away.
"""

from __future__ import annotations

import importlib
from types import ModuleType


class MissingExtra(ImportError):
    """An optional extra is genuinely not installed, as opposed to broken.

    Carries the extra's name in ``.extra``, so a caller that wants to react to
    *which* extra is missing does not have to read it back out of the message.

    Constructed like any ``ImportError`` -- a message, and ``extra`` as an
    optional keyword. That is on purpose: these are raised by the library and
    caught at entry points, and a subclass that refused a plain message would
    break every caller and test that raises one to stand in for the real thing.
    """

    def __init__(self, *args: object, extra: str | None = None) -> None:
        super().__init__(*args)
        self.extra = extra


def _sentence(doing: str, package: str, extra: str) -> str:
    """The one message an absent extra produces, everywhere.

    The install line is part of it because the message is the whole user
    interface at that moment: someone is at a command line, or an agent is
    reading a tool result, and in both cases the next useful thing is the
    command that fixes it.
    """
    return (
        f"{doing} needs {package}, which is not installed. "
        f"Install it with: uv pip install 'sluicer[{extra}]'"
    )


def import_extra(
    module: str,
    extra: str,
    *,
    doing: str,
    package: str | None = None,
    error: type[MissingExtra] = MissingExtra,
) -> ModuleType:
    """Import ``module``, or say that the ``extra`` that provides it is missing.

    ``doing`` names the job in the reader's terms ("Fetching a URL"), since
    "scrapling is missing" answers a question nobody asked. ``package`` is how
    the dependency is spelled in that sentence when its import name reads badly
    on its own -- "the mcp package" rather than "mcp" -- and defaults to the
    top-level import name.

    ``error`` is the class to raise, for the callers that publish a name of
    their own: ``sluicer.cli`` catches ``FetchExtraMissing`` and
    ``MarkdownExtraMissing`` by name to print their message instead of a
    traceback. The rule is shared; only the label differs.

    Raises ``MissingExtra`` only when the top-level package is absent. See this
    module's docstring for why everything else keeps its traceback.
    """
    top_level = module.split(".")[0]
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as missing:
        if missing.name != top_level:
            raise
        spelled = package or top_level
        raise error(_sentence(doing, spelled, extra), extra=extra) from missing
