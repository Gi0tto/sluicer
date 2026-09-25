"""Shell completion is click's, asked for by ``_SLUICER_COMPLETE``: the
scripts the documentation tells bash, zsh and fish users to load are
generated, parse in the shell they are for when it is installed, and
complete the commands and options ``sluicer`` has."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from sluicer.cli import main

GUIDE = Path(__file__).resolve().parent.parent / "docs" / "getting-started.md"
SHELLS = ["bash", "zsh", "fish"]


def _complete(env: dict[str, str]):
    return CliRunner().invoke(main, [], prog_name="sluicer", env=env)


@pytest.mark.parametrize("shell", SHELLS)
def test_the_completion_script_is_generated(shell):
    result = _complete({"_SLUICER_COMPLETE": f"{shell}_source"})

    assert result.exit_code == 0, result.output
    assert "_SLUICER_COMPLETE" in result.stdout
    assert f"{shell}_complete" in result.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_the_script_parses_in_its_shell(shell, tmp_path):
    program = shutil.which(shell)
    if program is None:
        pytest.skip(f"{shell} is not installed here")
    script = tmp_path / f"sluicer.{shell}"
    generated = _complete({"_SLUICER_COMPLETE": f"{shell}_source"}).stdout
    script.write_text(generated, encoding="utf-8")

    checked = subprocess.run(
        [program, "-n", str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert checked.returncode == 0, checked.stderr


def test_bash_completes_a_command_and_its_options():
    commands = _complete(
        {
            "_SLUICER_COMPLETE": "bash_complete",
            "COMP_WORDS": "sluicer cr",
            "COMP_CWORD": "1",
        }
    )
    options = _complete(
        {
            "_SLUICER_COMPLETE": "bash_complete",
            "COMP_WORDS": "sluicer crawl --max-",
            "COMP_CWORD": "2",
        }
    )

    assert commands.stdout.split() == ["plain,crawl"]
    assert sorted(options.stdout.split()) == ["plain,--max-depth", "plain,--max-pages"]


@pytest.mark.parametrize("shell", SHELLS)
def test_the_guide_says_how_for_each_shell(shell):
    guide = GUIDE.read_text(encoding="utf-8")

    assert f"_SLUICER_COMPLETE={shell}_source sluicer" in guide
