"""How this Sluicer was installed, and the one command that adds an extra to it.

A missing extra's message said ``uv pip install "sluicer[x]"`` whatever the
install. Outside a virtual environment uv refuses that line, and in an
environment made by ``uv tool`` or pipx it installs into some other Python, or
nowhere. The command that adds an extra depends on what made the environment
the running Python lives in, and each leaves a mark there:

* ``uv tool install`` writes ``uv-receipt.toml`` in the tool's environment.
  Installing again with other extras replaces the tool's requirements (measured
  with uv 0.11: ``sluicer[mcp]`` over ``sluicer[microformats]`` removed mf2py),
  so the command names every extra already there beside the new one.
* pipx writes ``pipx_metadata.json``, and installs over an existing
  environment only with ``--force``; the command names every extra too.
* ``uvx`` runs from an environment in uv's cache, ``archive-v0/<id>``, made
  anew for each set of requirements: the fix is running again with the extra
  in ``--from``.
* a project uv manages keeps its environment in ``.venv`` beside
  ``uv.lock``; what ``uv pip install`` puts there the next ``uv sync`` takes
  away, so the command is ``uv add``.
* any other environment uv made has no pip in it, and takes
  ``uv pip install``; the rest take pip, and one with no pip in it takes
  ``uv pip install --python`` when uv is on the ``PATH``, or else
  ``python -m ensurepip`` first.
* an interpreter no virtual environment wraps, which Homebrew installed (its
  prefix in a ``Cellar``) or which says another package manager owns it (a
  PEP 668 ``EXTERNALLY-MANAGED`` file), takes a virtual environment made
  first: pip refuses to install into it, and ``ensurepip`` would have put
  pip into Homebrew's own tree.

Which extras are installed is read from the packages they bring, found without
importing them, so the answer is the same whichever way Sluicer was installed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "EXTRAS",
    "Installation",
    "chromium_missing",
    "current",
    "detect",
    "how_to_add",
    "playwright_argv",
    "present",
]

EXTRAS: dict[str, tuple[str, ...]] = {
    "browser": ("playwright",),
    "stealth": ("scrapling",),
    "microformats": ("mf2py",),
    "mcp": ("mcp",),
    "api": ("mcp", "starlette", "uvicorn"),
    "markdown": ("trafilatura",),
}
"""Each extra a command can ask for, by the top-level packages it installs.
``markdown`` is in the base install since 0.10, and is here for an
environment that lost trafilatura; ``all`` and the deprecated ``fetch`` are
only ever installed, never asked for."""

KINDS = ("uv tool", "pipx", "uvx", "uv project", "uv venv", "pip")
"""What can have made the environment, in the order the marks are looked for."""

_REPLACING = ("uv tool", "pipx", "uvx", "uv project")
"""The installers whose command states the whole requirement, so every extra
already installed is named again beside the new one."""


@dataclass(frozen=True)
class Installation:
    """Where the running Sluicer is installed, and what installed it.

    ``kind`` is one of ``KINDS``; ``python`` the interpreter, spelled as a
    command would; ``project`` the uv project's directory for ``uv project``;
    ``short`` whether the plain ``pip`` or ``uv pip`` on the ``PATH`` reaches
    this environment, so the command need not name the interpreter.
    """

    kind: str
    python: str
    project: Path | None = None
    short: bool = True
    asked: frozenset[str] | None = None
    """The extras the installer's own record says were asked for, where it
    keeps one (``uv tool``, pipx); ``None`` elsewhere."""
    pip: bool = True
    """For ``pip``: whether pip is installed in the environment. A venv made
    with ``--without-pip`` has none, and ``python -m pip`` fails there."""
    uv: bool = False
    """Whether ``uv`` is on the ``PATH``, to install into an environment
    that has no pip."""
    managed: bool = False
    """For ``pip``: whether the interpreter is no virtual environment's and
    another package manager owns it, Homebrew or the system's: nothing is
    installed into it, a virtual environment is made first."""

    def kept(self) -> set[str]:
        """The extras a command that replaces the requirement must name again:
        those asked for, where that is recorded, or else those installed. The
        record is preferred: mcp brings starlette and uvicorn, which read as
        the api extra installed when only mcp was asked for."""
        return set(self.asked) if self.asked is not None else present()

    @property
    def described(self) -> str:
        """The installer in a few words, for ``sluicer doctor``."""
        return {
            "uv tool": "uv tool install",
            "pipx": "pipx",
            "uvx": "uvx, for this run only",
            "uv project": f"uv, in the project at {self.project}",
            "uv venv": "uv, in a virtual environment",
            "pip": "pip",
        }[self.kind]

    def command(
        self, extras: Iterable[str] = (), have: Iterable[str] = (), *, then: str = ""
    ) -> str:
        """The one command line that adds ``extras`` to this installation.

        ``have`` is what is installed already, named again for the installers
        that replace the requirement rather than add to it. ``then`` is the
        sluicer command to run, for ``uvx``, which installs nothing to keep:
        ``uvx --from "sluicer[browser]" sluicer`` followed by it.
        """
        wanted = set(extras)
        if self.kind in _REPLACING:
            # markdown is the base install's since 0.10: named when asked
            # for, where trafilatura went missing, never merely kept.
            wanted |= set(have) - {"markdown"}
        spec = _spec(wanted)
        if self.kind == "uv tool":
            return f"uv tool install {spec}"
        if self.kind == "pipx":
            return f"pipx install --force {spec}"
        if self.kind == "uvx":
            return f"uvx --from {spec} sluicer {then or '...'}".rstrip()
        if self.kind == "uv project":
            here = self.project is not None and _within(Path.cwd(), self.project)
            where = "" if here else f" --project {_quoted(str(self.project))}"
            return f"uv add{where} {spec}"
        if self.kind == "uv venv":
            python = "" if self.short else f" --python {_quoted(self.python)}"
            return f"uv pip install{python} {spec}"
        python = _quoted(self.python)
        if self.managed:
            venv = str(Path(".venv") / ("Scripts" if os.name == "nt" else "bin"))
            return (
                f"{python} -m venv .venv, then: "
                f"{_quoted(str(Path(venv) / 'python'))} -m pip install {spec}"
            )
        if not self.pip:
            if self.uv:
                return f"uv pip install --python {python} {spec}"
            return f"{python} -m ensurepip, then: {python} -m pip install {spec}"
        if self.short:
            return f"pip install {spec}"
        return f"{python} -m pip install {spec}"


def _spec(extras: Iterable[str]) -> str:
    """``"sluicer[a,b]"``, quoted for every shell, or ``sluicer`` alone; an
    extra is left out beside one that brings it (``mcp`` beside ``api``)."""
    named = set(extras)
    if "all" in named:
        named -= {"browser", "mcp", "api", "microformats", "markdown"}
    if "api" in named:
        named.discard("mcp")
    if not named:
        return "sluicer"
    return f'"sluicer[{",".join(sorted(named))}]"'


def _quoted(word: str) -> str:
    """``word`` as one argument, in double quotes when it holds a space: the
    one quoting bash, zsh, PowerShell and cmd.exe all read the same way."""
    return f'"{word}"' if re.search(r"\s", word) else word


def _within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _made_by_uv(prefix: Path) -> bool:
    """uv writes its version into every ``pyvenv.cfg`` it makes."""
    try:
        config = (prefix / "pyvenv.cfg").read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(r"^uv\s*=", config, re.MULTILINE) is not None


def _uv_project(prefix: Path) -> Path | None:
    """The uv project ``prefix`` is the environment of, when it depends on
    Sluicer: ``.venv`` beside a ``uv.lock`` and a ``pyproject.toml`` naming
    ``sluicer`` among its requirements. Sluicer's own checkout is not one."""
    if prefix.name != ".venv":
        return None
    project = prefix.parent
    try:
        pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return None
    if not (project / "uv.lock").is_file():
        return None
    if re.search(r'^name\s*=\s*["\']sluicer["\']', pyproject, re.MULTILINE):
        return None
    if re.search(r"""["']sluicer\s*(\[|[<>=!~;]|["'])""", pyproject) is None:
        return None
    return project


def detect(
    prefix: str | Path,
    python: str,
    environ: Mapping[str, str],
    which: Callable[[str], str | None] = shutil.which,
) -> Installation:
    """What installed the environment at ``prefix``, whose interpreter is
    ``python``, as seen with ``environ`` and a ``PATH`` searched by ``which``.
    """
    root = Path(prefix)
    if (root / "uv-receipt.toml").is_file():
        return Installation("uv tool", python, asked=_asked(root / "uv-receipt.toml"))
    if (root / "pipx_metadata.json").is_file():
        return Installation("pipx", python, asked=_asked(root / "pipx_metadata.json"))
    if _made_by_uv(root):
        if re.fullmatch(r"archive-v\d+", root.parent.name):
            return Installation("uvx", python)
        project = _uv_project(root)
        if project is not None:
            return Installation("uv project", python, project=project)
        active = environ.get("VIRTUAL_ENV", "")
        short = bool(active) and _same(Path(active), root)
        return Installation("uv venv", python, short=short)
    found = which("pip")
    short = found is not None and _same(Path(found).parent, Path(python).parent)
    pip = _has_pip(root)
    return Installation(
        "pip",
        python,
        short=short and pip,
        pip=pip,
        uv=which("uv") is not None,
        managed=_managed(root),
    )


def _managed(prefix: Path) -> bool:
    """Whether the interpreter at ``prefix`` is no virtual environment's and
    another package manager owns it: Homebrew, whose prefixes resolve into
    its ``Cellar``, or any that marks its standard library
    ``EXTERNALLY-MANAGED`` (PEP 668), as Homebrew's and Debian's do."""
    if (prefix / "pyvenv.cfg").is_file():
        return False
    try:
        if "Cellar" in prefix.resolve().parts:
            return True
    except OSError:
        return False
    marked = [*prefix.glob("lib/python3*/EXTERNALLY-MANAGED")]
    return bool(marked) or (prefix / "Lib" / "EXTERNALLY-MANAGED").is_file()


def _has_pip(prefix: Path) -> bool:
    """Whether the environment at ``prefix`` has pip, asked of this process
    when it is the one running there; another is taken to have it."""
    return not _same(prefix, Path(sys.prefix)) or _importable("pip")


_UV_RECEIPT = re.compile(r"""name\s*=\s*"sluicer"[^}]*?extras\s*=\s*\[([^\]]*)\]""")
# The extras right after the name: "sluicer[api]", and pinned,
# "sluicer[microformats]==0.10.0", which a pattern anchored at the end missed.
_BRACKETS = re.compile(r"\s*[A-Za-z0-9][A-Za-z0-9._-]*\s*\[([^\]]*)\]")


def _asked(record: Path) -> frozenset[str] | None:
    """The extras of sluicer's requirement in uv's receipt or pipx's metadata:
    ``extras = ["api"]`` in the one, ``"package_or_url": "sluicer[api]"`` in
    the other; an empty set when sluicer was asked for bare, and ``None``
    when the record cannot be read. The receipt is read with a pattern, which
    is enough for its one key and holds on every Python."""
    try:
        text = record.read_text(encoding="utf-8")
        if record.suffix == ".json":
            asked = json.loads(text)["main_package"]["package_or_url"]
            found = _BRACKETS.match(asked) if isinstance(asked, str) else None
        else:
            found = _UV_RECEIPT.search(text)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if found is None:
        return frozenset()
    words = (word.strip().strip("\"'") for word in found[1].split(","))
    # Named as PEP 685 normalises an extra: "Sluicer[MCP]" asked for mcp.
    return frozenset(re.sub(r"[-_.]+", "-", word).lower() for word in words if word)


def _same(one: Path, other: Path) -> bool:
    try:
        return one.resolve() == other.resolve()
    except OSError:
        return False


def current() -> Installation:
    """The installation this process runs from."""
    return detect(sys.prefix, sys.executable, os.environ)


def _importable(module: str) -> bool:
    """Whether ``module`` is installed, found without importing it. One
    already imported counts, whatever its ``__spec__``, which ``find_spec``
    refuses when it is ``None``."""
    if sys.modules.get(module) is not None:
        return True
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def present() -> set[str]:
    """The extras whose packages are all installed here."""
    return {
        extra
        for extra, modules in EXTRAS.items()
        if all(_importable(module) for module in modules)
    }


def how_to_add(extra: str, *, then: str = "") -> str:
    """The sentence that ends a missing extra's message: the command that adds
    ``extra`` to this installation, the extras already there kept."""
    installation = current()
    command = installation.command([extra], installation.kept(), then=then)
    if installation.kind == "uvx":
        return f"Run it with: {command}"
    return f"Install it with: {command}"


# Playwright's command line, run the way ``sluicer.isolated`` runs its child:
# with -I, so the working directory is not on the path and no PYTHON*
# variable is read, and handed the parent's own path to import from, less the
# working directory. ``python -m playwright`` put the working directory first:
# a playwright/__main__.py in the folder ``sluicer doctor`` was run in -- a
# cloned repository -- ran in Playwright's place.
_PLAYWRIGHT = (
    "import json, runpy, sys; sys.path[:] = json.loads(sys.argv.pop(1)); "
    "runpy.run_module('playwright', run_name='__main__', alter_sys=True)"
)


def _trusted_path() -> list[str]:
    """This process's import path without the working directory: the empty
    entry ``-c`` and ``-m`` stand it in with, or its own spelling."""
    here = Path.cwd()
    return [entry for entry in sys.path if entry and not _same(Path(entry), here)]


def playwright_argv(*arguments: str) -> list[str]:
    """The command that runs the installed Playwright's command line with
    ``arguments``, on this interpreter, importing nothing from the working
    directory."""
    path = json.dumps(_trusted_path())
    return [sys.executable, "-I", "-c", _PLAYWRIGHT, path, *arguments]


_LOCATION = re.compile(r"^\s*Install location:\s*(.+?)\s*$", re.MULTILINE)


def chromium_missing(
    run: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> list[str] | None:
    """The parts of Playwright's Chromium that are not downloaded yet: an empty
    list when it is ready, ``None`` when Playwright could not say.

    Asked of the installed Playwright itself, with ``playwright install
    --dry-run chromium``, which prints where each part it would download goes
    (the browser, its headless shell and ffmpeg) and downloads nothing; a part
    is there when Playwright marked it ``INSTALLATION_COMPLETE``. A browser
    directory of another Playwright version does not count, since the path
    names the revision this one drives.
    """
    run = run or subprocess.run
    try:
        answer = run(
            playwright_argv("install", "--dry-run", "chromium"),
            capture_output=True,
            # Playwright's driver is Node, which writes UTF-8 everywhere; a
            # path it prints may hold any letter of a user's name.
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    locations = _LOCATION.findall(answer.stdout or "")
    if answer.returncode != 0 or not locations:
        return None
    return [
        location
        for location in locations
        if not (Path(location) / "INSTALLATION_COMPLETE").is_file()
    ]
