"""One answer to "is the optional extra installed?", for every entry point.

The base install reads HTML you already have. Fetching, markdown, microformats
and the MCP server each need a tree most readers never want, so each lives
behind an optional extra and is imported on first use.

Exactly one failure means "the extra is not installed": the top-level package
is absent, which is a ``ModuleNotFoundError`` whose ``name`` is the first
dotted component of the module imported.

Everything else is re-raised untouched. A ``ModuleNotFoundError`` naming a
submodule (``scrapling.fetchers``, ``mcp.server.mcpserver``), or an
``ImportError`` raised while a working package runs, is a broken install;
telling it to "pip install ..." would send the reader to install what they
have and hide the real error.
"""

from __future__ import annotations

import importlib
from types import ModuleType


class MissingExtra(ImportError):
    """An optional extra is not installed, as opposed to broken.

    ``extra`` names it, so a caller can react to which one without parsing the
    message. Constructed like any ``ImportError``, with ``extra`` an optional
    keyword, so a test can raise one as a stand-in.
    """

    def __init__(self, *args: object, extra: str | None = None) -> None:
        super().__init__(*args)
        self.extra = extra


def _sentence(doing: str, package: str, extra: str) -> str:
    """The one message an absent extra produces, install line included: at a
    command line or in a tool result, the command that fixes it is the next
    useful thing. It is the command for the way this Sluicer was installed
    (``sluicer.installer``): ``uv pip install``, said to everyone, fails
    outside a virtual environment and misses a ``uv tool`` or pipx one."""
    from sluicer.installer import how_to_add

    return f"{doing} needs {package}, which is not installed. {how_to_add(extra)}"


def import_extra(
    module: str,
    extra: str,
    *,
    doing: str,
    package: str | None = None,
    error: type[MissingExtra] = MissingExtra,
) -> ModuleType:
    """Import ``module``, or say that the ``extra`` that provides it is missing.

    Args:
        module: the dotted module to import.
        extra: the extra that provides it, as in ``sluicer[fetch]``.
        doing: the job in the reader's terms ("Fetching a URL").
        package: how to spell the dependency in the sentence, when its import
            name reads badly alone ("the mcp package"); the top-level name by
            default.
        error: the ``MissingExtra`` subclass to raise, for entry points that
            catch their own by name.

    Raises ``error`` only when the top-level package is absent; any other
    import failure keeps its traceback.
    """
    top_level = module.split(".")[0]
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as missing:
        if missing.name != top_level:
            raise
        spelled = package or top_level
        raise error(_sentence(doing, spelled, extra), extra=extra) from missing
