"""``sluicer install browser`` and ``sluicer doctor``, with Playwright faked.

The installation each runs under is faked as ``tests/test_installer.py`` lays
the installers out; nothing is downloaded and no browser is started.
"""

from __future__ import annotations

import re
import subprocess

import pytest
from click.testing import CliRunner

from sluicer import installer
from sluicer.installer import Installation

# -- sluicer install browser -----------------------------------------------


class _Ran:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.argv: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.argv.append(argv)
        return subprocess.CompletedProcess(argv, self.returncode, "", "")


@pytest.fixture
def cli(monkeypatch):
    from sluicer.cli import install as install_module, main

    ran = _Ran()
    monkeypatch.setattr(install_module, "_run", ran)
    monkeypatch.setattr(installer, "chromium_missing", lambda run=None: [])

    def invoke(*args: str):
        return CliRunner().invoke(main, list(args))

    invoke.ran = ran
    invoke.module = install_module
    return invoke


def test_install_browser_without_the_extra_says_how_to_add_it(cli, monkeypatch):
    monkeypatch.setattr(cli.module, "_importable", lambda name: name != "playwright")
    monkeypatch.setattr(
        installer,
        "current",
        lambda: Installation("uv tool", "python", asked=frozenset({"mcp"})),
    )

    result = cli("install", "browser")

    assert result.exit_code == 2
    assert cli.ran.argv == []
    assert (
        'Install it with: uv tool install "sluicer[browser,mcp]", '
        "then: sluicer install browser"
    ) in result.stderr


def test_install_browser_under_uvx_is_one_line_to_run(cli, monkeypatch):
    monkeypatch.setattr(cli.module, "_importable", lambda name: name != "playwright")
    monkeypatch.setattr(installer, "current", lambda: Installation("uvx", "python"))
    monkeypatch.setattr(installer, "present", set)

    result = cli("install", "browser")

    assert result.exit_code == 2
    assert 'Run: uvx --from "sluicer[browser]" sluicer install browser' in (
        result.stderr
    )


def test_install_browser_runs_playwright_with_this_python(cli, monkeypatch):
    import sys

    monkeypatch.setattr(cli.module, "_importable", lambda name: True)

    result = cli("install", "browser")

    assert result.exit_code == 0, result.output
    (argv,) = cli.ran.argv
    # Isolated, the installed Playwright's: never ``-m playwright``, which
    # ran a playwright/__main__.py from the working directory.
    assert argv[:3] == [sys.executable, "-I", "-c"]
    assert "-m" not in argv
    assert argv[-2:] == ["install", "chromium"]
    assert "playwright install chromium" in result.stderr
    assert "Chromium is installed" in result.stderr


def test_install_browser_passes_with_deps_on(cli, monkeypatch):
    monkeypatch.setattr(cli.module, "_importable", lambda name: True)

    cli("install", "browser", "--with-deps")

    assert cli.ran.argv[0][-2:] == ["--with-deps", "chromium"]


def test_a_failed_download_exits_2_and_says_so(cli, monkeypatch):
    monkeypatch.setattr(cli.module, "_importable", lambda name: True)
    cli.ran.returncode = 1

    result = cli("install", "browser")

    assert result.exit_code == 2
    assert "playwright install chromium failed with exit code 1" in result.stderr
    assert "Chromium is installed" not in result.stderr


def test_a_download_that_left_a_part_missing_is_not_success(cli, monkeypatch):
    monkeypatch.setattr(cli.module, "_importable", lambda name: True)
    monkeypatch.setattr(
        installer, "chromium_missing", lambda run=None: ["/cache/chromium-1243"]
    )

    result = cli("install", "browser")

    assert result.exit_code == 2
    assert "/cache/chromium-1243" in result.stderr
    assert "Chromium is installed" not in result.stderr


def test_install_names_what_it_can_install(cli):
    result = cli("install", "chrome")

    assert result.exit_code == 2
    assert "browser" in result.stderr


# -- sluicer doctor ---------------------------------------------------------


def _lines(output: str) -> dict[str, list[str]]:
    """Each piece's status line and the fix under it, by piece name."""
    found: dict[str, list[str]] = {}
    current = None
    for line in output.splitlines():
        match = re.match(
            r"^(ok|missing|off|unknown|invalid)\s+(\S+(?: pages)?)\s{2,}", line
        )
        if match:
            current = match[2]
            found[current] = [match[1]]
        elif current and line.startswith(" ") and line.strip():
            found[current].append(line.strip())
    return found


def test_doctor_reports_each_piece_with_the_command_that_adds_it(cli, monkeypatch):
    monkeypatch.setattr(
        installer,
        "current",
        lambda: Installation("pipx", "python", asked=frozenset({"microformats"})),
    )
    monkeypatch.setattr(installer, "present", lambda: {"markdown", "microformats"})

    result = cli("doctor")

    assert result.exit_code == 0, result.output
    assert "installed with pipx" in result.stdout
    pieces = _lines(result.stdout)
    assert pieces["reading pages"] == ["ok"]
    assert pieces["markdown"] == ["ok"]
    assert pieces["microformats"] == ["ok"]
    assert pieces["browser"] == [
        "missing",
        'pipx install --force "sluicer[browser,microformats]", '
        "then: sluicer install browser",
    ]
    assert pieces["mcp"] == [
        "missing",
        'pipx install --force "sluicer[mcp,microformats]"',
    ]
    assert (
        pieces["stealth"][1] == 'pipx install --force "sluicer[microformats,stealth]"'
    )
    assert 'Every extra but stealth at once: pipx install --force "sluicer[all]"' in (
        result.stdout
    )


def test_doctor_says_when_playwright_is_there_and_its_chromium_is_not(cli, monkeypatch):
    monkeypatch.delenv("SLUICER_BROWSER", raising=False)
    monkeypatch.delenv("SLUICER_CDP_URL", raising=False)
    monkeypatch.setattr(installer, "present", lambda: {"markdown", "browser"})
    monkeypatch.setattr(installer, "chromium_missing", lambda run=None: ["/c/x"])

    pieces = _lines(cli("doctor").stdout)

    assert pieces["browser"][0] == "missing"
    assert pieces["browser"][1] == "sluicer install browser"


def test_doctor_calls_the_browser_ok_only_with_chromium_downloaded(cli, monkeypatch):
    monkeypatch.delenv("SLUICER_BROWSER", raising=False)
    monkeypatch.delenv("SLUICER_CDP_URL", raising=False)
    monkeypatch.setattr(installer, "present", lambda: {"markdown", "browser"})

    assert _lines(cli("doctor").stdout)["browser"] == ["ok"]

    monkeypatch.setattr(installer, "chromium_missing", lambda run=None: None)
    assert _lines(cli("doctor").stdout)["browser"][0] == "unknown"

    monkeypatch.setenv("SLUICER_BROWSER", "none")
    assert _lines(cli("doctor").stdout)["browser"] == ["off"]


def test_doctor_exits_2_when_the_base_install_is_not_whole(cli, monkeypatch):
    """markdown is the base install's since 0.10: without trafilatura, part of
    what `pip install sluicer` promised does not work."""
    monkeypatch.setattr(installer, "present", set)

    result = cli("doctor")

    assert result.exit_code == 2
    pieces = _lines(result.stdout)
    assert pieces["markdown"] == ["missing", 'pip install "sluicer[markdown]"']


def test_doctor_in_a_uv_project_names_the_project_s_own_sluicer(
    cli, monkeypatch, tmp_path
):
    """ "then: sluicer install browser" ran whatever sluicer the PATH found,
    which a uv project's .venv is not on."""
    python = str(tmp_path / ".venv" / "bin" / "python")
    monkeypatch.setattr(
        installer,
        "current",
        lambda: Installation("uv project", python, project=tmp_path),
    )
    monkeypatch.setattr(installer, "present", lambda: {"markdown", "browser"})
    monkeypatch.setattr(installer, "chromium_missing", lambda run=None: ["/c/x"])
    monkeypatch.delenv("SLUICER_BROWSER", raising=False)
    monkeypatch.delenv("SLUICER_CDP_URL", raising=False)

    assert _lines(cli("doctor").stdout)["browser"] == [
        "missing",
        f"{python} -m sluicer install browser",
    ]

    monkeypatch.setattr(installer, "present", lambda: {"markdown"})
    fix = _lines(cli("doctor").stdout)["browser"][1]
    assert fix.endswith(f", then: {python} -m sluicer install browser")


def test_doctor_calls_a_browser_no_fetch_accepts_invalid(cli, monkeypatch):
    """SLUICER_BROWSER=chrome: every fetch refuses it, and doctor said "ok
    browser"."""
    monkeypatch.setenv("SLUICER_BROWSER", "chrome")
    monkeypatch.delenv("SLUICER_CDP_URL", raising=False)
    for present in ({"markdown", "browser"}, {"markdown"}):
        monkeypatch.setattr(installer, "present", lambda present=present: present)

        result = cli("doctor")

        assert result.exit_code == 2
        browser = _lines(result.stdout)["browser"]
        assert browser[0] == "invalid"
        assert "SLUICER_BROWSER='chrome'" in result.stdout
        assert browser[1] == "unset SLUICER_BROWSER"
