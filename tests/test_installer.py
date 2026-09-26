"""The install line a message gives is the one for the way Sluicer was installed.

Every missing extra's message said ``uv pip install "sluicer[x]"``. Outside a
virtual environment uv refuses that line, and in a ``uv tool`` or pipx
environment it would install somewhere else. Each installer leaves a mark in
the environment it makes, laid out here in a temporary directory as the real
one leaves it (the marks were read from uv 0.11.32 and pipx 1.x on
2026-09-26). Playwright is faked, never asked to download anything.
"""

from __future__ import annotations

import ast
import json
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from sluicer import installer
from sluicer.installer import Installation, detect

ROOT = Path(__file__).resolve().parent.parent


def _declared_extras() -> set[str]:
    """The extras pyproject.toml declares, read with a pattern (no tomllib on
    3.10)."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    section = pyproject.split("[project.optional-dependencies]", 1)[1]
    section = section.split("\n[", 1)[0]
    return set(re.findall(r"^([a-z][\w-]*) = \[", section, re.MULTILINE))


def _venv(prefix: Path, *, uv: bool) -> Path:
    prefix.mkdir(parents=True)
    lines = ["home = /usr/bin", "include-system-site-packages = false"]
    if uv:
        lines.append("uv = 0.11.32")
    (prefix / "pyvenv.cfg").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return prefix


def _no_pip(_: str) -> None:
    return None


# -- which installer -------------------------------------------------------


def test_a_uv_tool_keeps_the_extras_its_receipt_asked_for(tmp_path):
    """uv tool install with other extras replaces the tool's requirements:
    measured, sluicer[mcp] over sluicer[microformats] removed mf2py. So the
    line names the extras the receipt records beside the new one."""
    prefix = _venv(tmp_path / "tools" / "sluicer", uv=True)
    (prefix / "uv-receipt.toml").write_text(
        "[tool]\n"
        'requirements = [{ name = "sluicer", extras = ["microformats"] }]\n'
        "entrypoints = [\n"
        '    { name = "sluicer", install-path = "/x/sluicer", from = "sluicer" },\n'
        "]\n",
        encoding="utf-8",
    )

    found = detect(prefix, str(prefix / "bin" / "python"), {}, _no_pip)

    assert found.kind == "uv tool"
    assert found.asked == {"microformats"}
    assert found.command(["browser"], found.kept()) == (
        'uv tool install "sluicer[browser,microformats]"'
    )


def test_a_bare_uv_tool_install_asks_for_only_the_new_extra(tmp_path):
    prefix = _venv(tmp_path / "sluicer", uv=True)
    (prefix / "uv-receipt.toml").write_text(
        '[tool]\nrequirements = [{ name = "sluicer" }]\n', encoding="utf-8"
    )

    found = detect(prefix, "python", {}, _no_pip)

    assert found.asked == frozenset()
    assert found.command(["mcp"], found.kept()) == 'uv tool install "sluicer[mcp]"'


def test_pipx_installs_over_its_environment_only_with_force(tmp_path):
    """pipx install without --force leaves an installed package alone:
    "Pass '--force' to force installation" (measured)."""
    prefix = _venv(tmp_path / "pipx" / "venvs" / "sluicer", uv=False)
    (prefix / "pipx_metadata.json").write_text(
        json.dumps(
            {
                "main_package": {"package_or_url": "sluicer[mcp]", "pip_args": []},
                "pipx_metadata_version": "0.5",
            }
        ),
        encoding="utf-8",
    )

    found = detect(prefix, "python", {}, _no_pip)

    assert found.kind == "pipx"
    assert found.command(["browser"], found.kept()) == (
        'pipx install --force "sluicer[browser,mcp]"'
    )


def test_a_pinned_pipx_requirement_keeps_its_extras(tmp_path):
    """pipx records the requirement as it was asked for; a pinned one,
    "sluicer[microformats]==0.10.0", was read as no extra at all, and the
    line given dropped microformats."""
    prefix = _venv(tmp_path / "pipx" / "venvs" / "sluicer", uv=False)
    for asked in ("sluicer[microformats]==0.10.0", "sluicer [microformats] >=0.10"):
        (prefix / "pipx_metadata.json").write_text(
            json.dumps({"main_package": {"package_or_url": asked}}),
            encoding="utf-8",
        )

        found = detect(prefix, "python", {}, _no_pip)

        assert found.asked == {"microformats"}, asked
        assert found.command(["browser"], found.kept()) == (
            'pipx install --force "sluicer[browser,microformats]"'
        )


def test_an_extra_asked_for_in_capitals_is_named_as_pip_names_it(tmp_path):
    """Found by the hostile review of 0.10: pipx recorded "Sluicer[MCP]" as
    asked, and the line given kept "MCP" beside the "mcp" it adds. Extras
    are named as PEP 685 normalises them: lowercased."""
    prefix = _venv(tmp_path / "pipx" / "venvs" / "sluicer", uv=False)
    (prefix / "pipx_metadata.json").write_text(
        json.dumps({"main_package": {"package_or_url": "Sluicer[MCP,Micro_Formats]"}}),
        encoding="utf-8",
    )

    found = detect(prefix, "python", {}, _no_pip)

    assert found.asked == {"mcp", "micro-formats"}
    assert found.command(["mcp"], found.kept()) == (
        'pipx install --force "sluicer[mcp,micro-formats]"'
    )


def test_homebrew_s_own_python_is_told_to_make_a_virtual_environment(
    tmp_path, monkeypatch
):
    """Found by the hostile review of 0.10: Homebrew's Python with no pip
    was told "python -m ensurepip", which puts pip into Homebrew's Cellar,
    and one with pip "python -m pip install", which it refuses (PEP 668). An
    interpreter no virtual environment wraps, in a Cellar or marked
    EXTERNALLY-MANAGED, is told to make one first."""
    cellar = tmp_path / "homebrew" / "Cellar" / "python@3.13" / "3.13.7" / "Frameworks"
    cellar.mkdir(parents=True)
    marked = tmp_path / "usr"
    (marked / "lib" / "python3.13").mkdir(parents=True)
    (marked / "lib" / "python3.13" / "EXTERNALLY-MANAGED").write_text(
        "[x]\n", encoding="utf-8"
    )
    for prefix in (cellar, marked):
        python = str(prefix / "bin" / "python3")
        for has_pip in (True, False):
            monkeypatch.setattr(installer.sys, "prefix", str(prefix))
            monkeypatch.setattr(installer, "_importable", lambda m, h=has_pip: h)

            found = detect(prefix, python, {}, _no_pip)

            venv = Path(".venv") / ("Scripts" if installer.os.name == "nt" else "bin")
            assert found.managed, prefix
            assert found.command(["mcp"]) == (
                f"{python} -m venv .venv, then: "
                f'{venv / "python"} -m pip install "sluicer[mcp]"'
            )
    # A virtual environment made from it is its own, and takes pip.
    venv = _venv(tmp_path / "homebrew" / "Cellar" / "env", uv=False)
    monkeypatch.setattr(installer, "_importable", lambda module: True)
    assert not detect(venv, "python", {}, _no_pip).managed


def test_an_environment_without_pip_is_not_told_to_run_pip(tmp_path, monkeypatch):
    """A venv made --without-pip was told "python -m pip install", which
    fails there: "No module named pip"."""
    prefix = _venv(tmp_path / "env", uv=False)
    python = str(prefix / "bin" / "python")
    monkeypatch.setattr(installer.sys, "prefix", str(prefix))
    monkeypatch.setattr(installer, "_importable", lambda module: module != "pip")

    with_uv = detect(prefix, python, {}, lambda name: f"/bin/{name}")
    without = detect(prefix, python, {}, _no_pip)

    assert with_uv.kind == without.kind == "pip"
    assert with_uv.command(["mcp"]) == (
        f'uv pip install --python {python} "sluicer[mcp]"'
    )
    assert without.command(["mcp"]) == (
        f'{python} -m ensurepip, then: {python} -m pip install "sluicer[mcp]"'
    )
    # One that has pip is told pip, as before.
    monkeypatch.setattr(installer, "_importable", lambda module: True)
    assert detect(prefix, python, {}, _no_pip).command(["mcp"]) == (
        f'{python} -m pip install "sluicer[mcp]"'
    )


def test_uvx_is_told_to_run_again_with_the_extra(tmp_path):
    """uvx installs nothing to keep: its environment is one in uv's cache,
    made for one set of requirements, so the fix is the next run's line."""
    prefix = _venv(tmp_path / "cache" / "uv" / "archive-v0" / "I25t_oXOG3dX", uv=True)

    found = detect(prefix, "python", {"UV": "/bin/uv"}, _no_pip)

    assert found.kind == "uvx"
    assert found.command(["browser"], set(), then="install browser") == (
        'uvx --from "sluicer[browser]" sluicer install browser'
    )


def test_a_uv_project_adds_the_extra_to_the_project(tmp_path, monkeypatch):
    """What uv pip install puts in a project's .venv the next uv sync takes
    away; uv add keeps it, and names the extras the project already has."""
    project = tmp_path / "shop"
    prefix = _venv(project / ".venv", uv=True)
    (project / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        '[project]\nname = "shop"\ndependencies = ["sluicer[mcp]>=0.9"]\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(project)

    found = detect(prefix, "python", {}, _no_pip)

    assert found.kind == "uv project"
    assert found.command(["browser"], {"mcp"}) == 'uv add "sluicer[browser,mcp]"'
    monkeypatch.chdir(tmp_path)
    assert found.command(["browser"], {"mcp"}) == (
        f'uv add --project {project} "sluicer[browser,mcp]"'
    )


def test_sluicer_s_own_checkout_is_not_a_project_that_depends_on_it(tmp_path):
    project = tmp_path / "sluicer"
    prefix = _venv(project / ".venv", uv=True)
    (project / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        '[project]\nname = "sluicer"\n'
        '[project.optional-dependencies]\nfetch = ["sluicer[browser]"]\n',
        encoding="utf-8",
    )

    assert detect(prefix, "python", {}, _no_pip).kind == "uv venv"


def test_a_venv_uv_made_has_no_pip_and_takes_uv_pip(tmp_path):
    """Active, uv pip install finds it; not active, the line names its Python,
    since uv would otherwise look for .venv in the working directory."""
    prefix = _venv(tmp_path / "env", uv=True)
    python = str(prefix / "bin" / "python")

    active = detect(prefix, python, {"VIRTUAL_ENV": str(prefix)}, _no_pip)
    elsewhere = detect(prefix, python, {}, _no_pip)

    assert active.command(["browser"]) == 'uv pip install "sluicer[browser]"'
    assert elsewhere.command(["browser"]) == (
        f'uv pip install --python {python} "sluicer[browser]"'
    )


def test_pip_by_name_only_when_the_path_leads_to_this_environment(tmp_path):
    """The line given outside a virtual environment used to be uv pip
    install, which uv refuses there: "No virtual environment found"."""
    prefix = _venv(tmp_path / "env", uv=False)
    (prefix / "bin").mkdir()
    python = str(prefix / "bin" / "python")

    here = detect(prefix, python, {}, lambda _: str(prefix / "bin" / "pip"))
    other = detect(prefix, python, {}, lambda _: "/usr/local/bin/pip")
    # A system Python no package manager marks as its own: not the real /usr,
    # which Debian's and Ubuntu's mark EXTERNALLY-MANAGED (a venv is advised).
    usr = tmp_path / "usr"
    (usr / "bin").mkdir(parents=True)
    system = detect(
        usr, str(usr / "bin" / "python3"), {}, lambda _: str(usr / "bin" / "pip")
    )

    assert here.command(["api"]) == 'pip install "sluicer[api]"'
    assert other.command(["api"]) == f'{python} -m pip install "sluicer[api]"'
    assert system.command(["mcp"]) == 'pip install "sluicer[mcp]"'
    assert "uv pip" not in system.command(["mcp"])


def test_a_python_whose_path_has_a_space_is_quoted(tmp_path):
    python = "C:\\Program Files\\Python314\\python.exe"

    found = Installation("pip", python, short=False)

    assert found.command(["mcp"]) == (f'"{python}" -m pip install "sluicer[mcp]"')


def test_an_extra_is_not_named_beside_one_that_brings_it():
    tool = Installation("uv tool", "python")

    assert tool.command(["mcp"], {"api"}) == 'uv tool install "sluicer[api]"'
    assert tool.command(["all"], {"api", "stealth", "microformats"}) == (
        'uv tool install "sluicer[all,stealth]"'
    )
    # markdown is the base install's: kept silently, named when asked for.
    assert tool.command(["mcp"], {"markdown"}) == 'uv tool install "sluicer[mcp]"'
    assert tool.command(["markdown"], set()) == 'uv tool install "sluicer[markdown]"'


def test_an_unreadable_record_falls_back_to_what_is_installed(tmp_path, monkeypatch):
    prefix = _venv(tmp_path / "sluicer", uv=False)
    (prefix / "pipx_metadata.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(installer, "present", lambda: {"microformats"})

    found = detect(prefix, "python", {}, _no_pip)

    assert found.asked is None
    assert found.kept() == {"microformats"}


def test_present_reads_the_packages_without_importing_them(absent):
    absent("mf2py", "playwright")

    have = installer.present()

    assert "microformats" not in have
    assert "browser" not in have
    assert "markdown" in have


# -- every message names a working command --------------------------------


def _import_extra_calls() -> list[tuple[str, str]]:
    """(file, extra) for every import_extra call in the package."""
    found = []
    for path in (ROOT / "src" / "sluicer").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "import_extra"
            ):
                extra = node.args[1]
                assert isinstance(extra, ast.Constant), path
                found.append((path.name, extra.value))
    return found


def test_every_extra_a_message_can_name_is_one_pyproject_declares():
    calls = _import_extra_calls()
    declared = _declared_extras()

    assert {extra for _, extra in calls} >= {
        "browser",
        "stealth",
        "markdown",
        "microformats",
        "mcp",
        "api",
    }
    for where, extra in calls:
        assert extra in declared, (where, extra)
    assert set(installer.EXTRAS) <= declared


def _programs(line: str) -> list[str]:
    return shlex.split(line)


_PROGRAM = {
    ("uv tool", True): ("uv", "tool", "install"),
    ("pipx", True): ("pipx", "install", "--force"),
    ("uvx", True): ("uvx", "--from"),
    ("uv project", True): ("uv", "add"),
    ("uv venv", False): ("uv", "pip", "install", "--python", "/env/bin/python"),
    ("uv venv", True): ("uv", "pip", "install"),
    ("pip", False): ("/env/bin/python", "-m", "pip", "install"),
    ("pip", True): ("pip", "install"),
}
"""The command each installer takes, as a shell splits it."""


@pytest.mark.parametrize(
    "found",
    [
        Installation("uv tool", "python", asked=frozenset({"microformats"})),
        Installation("pipx", "python", asked=frozenset()),
        Installation("uvx", "python"),
        Installation("uv project", "python", project=Path.cwd()),
        Installation("uv venv", "/env/bin/python", short=False),
        Installation("uv venv", "/env/bin/python"),
        Installation("pip", "/env/bin/python", short=False),
        Installation("pip", "python"),
    ],
    ids=lambda found: f"{found.kind}-{'short' if found.short else 'long'}",
)
def test_every_missing_extra_message_names_a_command_that_parses(
    found, monkeypatch, absent
):
    """For each installer and each extra, the message's command is one line a
    shell reads as: a known program, then exactly one requirement, sluicer
    with extras pyproject declares, the one asked for among them."""
    from sluicer.extras import MissingExtra, import_extra

    monkeypatch.setattr(installer, "current", lambda: found)
    monkeypatch.setattr(installer, "present", lambda: {"microformats"})
    absent("pretend_package")
    declared = _declared_extras()
    for extra in installer.EXTRAS:
        with pytest.raises(MissingExtra) as raised:
            import_extra("pretend_package", extra, doing="Doing it")
        message = str(raised.value)
        lead = "Run it with: " if found.kind == "uvx" else "Install it with: "
        assert lead in message, message
        words = _programs(message.split(lead, 1)[1])
        assert words[: len(_PROGRAM[found.kind, found.short])] == list(
            _PROGRAM[found.kind, found.short]
        ), words
        specs = [word for word in words if word.startswith("sluicer[")]
        assert len(specs) == 1, words
        named = set(specs[0][len("sluicer[") : -1].split(","))
        assert named <= declared
        assert extra in named or (extra == "mcp" and "api" in named)


# -- where Playwright's Chromium is -----------------------------------------


def test_chromium_is_ready_when_playwright_marked_every_part_complete(tmp_path):
    parts = [tmp_path / "chromium-1243", tmp_path / "ffmpeg-1011"]
    listing = "".join(
        f"Browser {n}\n  Install location:    {part}\n  Download url: x\n\n"
        for n, part in enumerate(parts)
    )

    def dry_run(argv, **kwargs):
        assert argv[-3:] == ["install", "--dry-run", "chromium"]
        return subprocess.CompletedProcess(argv, 0, listing, "")

    for part in parts:
        part.mkdir()
    (parts[0] / "INSTALLATION_COMPLETE").write_text("", encoding="utf-8")

    assert installer.chromium_missing(dry_run) == [str(parts[1])]
    (parts[1] / "INSTALLATION_COMPLETE").write_text("", encoding="utf-8")
    assert installer.chromium_missing(dry_run) == []


def test_chromium_is_unknown_when_playwright_cannot_say():
    def failing(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "boom")

    def absent(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    assert installer.chromium_missing(failing) is None
    assert installer.chromium_missing(absent) is None


def _package(folder: Path, main: str) -> None:
    (folder / "playwright").mkdir(parents=True)
    (folder / "playwright" / "__init__.py").write_text("", encoding="utf-8")
    (folder / "playwright" / "__main__.py").write_text(main, encoding="utf-8")


def test_a_playwright_in_the_working_directory_is_never_run(tmp_path, monkeypatch):
    """``python -m playwright`` put the working directory first on the path:
    a playwright/__main__.py planted in a cloned repository ran when
    ``sluicer doctor`` was run there. Only the installed one runs now, even
    when the working directory is on this process's own path, as it is under
    ``python -m sluicer``."""
    clone = tmp_path / "clone"
    installed = tmp_path / "site"
    planted = tmp_path / "PLANTED"
    _package(
        clone,
        "import pathlib, sys\n"
        f"pathlib.Path({str(planted)!r}).write_text(repr(sys.argv))\n",
    )
    location = tmp_path / "chromium-1243"
    location.mkdir()
    (location / "INSTALLATION_COMPLETE").write_text("", encoding="utf-8")
    _package(
        installed,
        "import sys\n"
        "assert sys.argv[1:] == ['install', '--dry-run', 'chromium'], sys.argv\n"
        f"print('Browser\\n  Install location:    ' + {str(location)!r})\n",
    )
    monkeypatch.syspath_prepend(str(installed))
    monkeypatch.syspath_prepend(str(clone))
    monkeypatch.chdir(clone)
    monkeypatch.setenv("PYTHONPATH", str(clone))

    assert installer.chromium_missing() == []
    assert not planted.exists()

    argv = installer.playwright_argv("install", "chromium")
    assert argv[:3] == [installer.sys.executable, "-I", "-c"]
    assert "-m" not in argv
    assert str(clone) not in json.loads(argv[4])
