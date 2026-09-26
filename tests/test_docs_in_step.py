"""The README says what the code does, and the site's home says what it says.

The README's quick start is run as it is written, so its output cannot fall
behind the library. And ``docs/index.md`` is the README with its links made
links within the site (``scripts/docs_home.py``): it had fallen behind twice
while it was kept by hand, once by three changes, once by a licence.
"""

from __future__ import annotations

import doctest
import importlib.util
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _generator():
    spec = importlib.util.spec_from_file_location(
        "docs_home", ROOT / "scripts" / "docs_home.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_docs_home_is_the_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    home = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    assert home == _generator().home(readme), "run: uv run scripts/docs_home.py"


def test_the_docs_home_leaves_no_link_into_the_repository_s_docs():
    home = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    assert "blob/main/docs/" not in home


def _run_python_blocks(text: str, name: str) -> None:
    blocks = re.findall(r"```python\n(.*?)```", text, re.DOTALL)
    assert blocks, f"{name} has no python block"
    parser = doctest.DocTestParser()
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    for number, block in enumerate(blocks):
        runner.run(parser.get_doctest(block, {}, f"{name} {number}", None, 0))
    assert runner.failures == 0, f"{runner.failures} line(s) of {name} differ"


def test_the_readme_s_quick_start_prints_what_it_says(monkeypatch):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    monkeypatch.chdir(ROOT)
    assert os.path.exists(ROOT / "examples" / "brake-pads.html")
    _run_python_blocks(section, "the README's quick start")


def test_the_getting_started_guide_prints_what_it_says(monkeypatch):
    guide = (ROOT / "docs" / "getting-started.md").read_text(encoding="utf-8")
    monkeypatch.chdir(ROOT)
    _run_python_blocks(guide, "the getting started guide")


def _assets():
    spec = importlib.util.spec_from_file_location(
        "readme_assets", ROOT / "scripts" / "readme_assets.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_readme_s_numbers_are_the_scoreboards():
    """The dates chart said metascraper found 0.811 and its alt text 0.384,
    and the README 1.4 s where the scoreboard said 1.50: the alt texts and the
    timings were written by hand, the charts from the scoreboards."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme == _assets().readme(readme), "run: uv run scripts/readme_assets.py"


def test_every_number_in_the_readme_s_scoreboard_table_is_in_its_scoreboard():
    """The README's one benchmark table is written by hand, one row per
    scoreboard: each number in a row must be in the scoreboard it links to,
    so a number copied wrong, or left behind by a new run, fails here."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Measured, losses included", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| [")]
    assert len(rows) == 7
    for row in rows:
        page = re.search(r"/docs/([\w-]+\.md)\)", row)
        assert page is not None, row
        board = (ROOT / "docs" / page.group(1)).read_text(encoding="utf-8")
        for number in re.findall(r"\d[\d,]*(?:\.\d+)?", row.split(")", 1)[1]):
            assert re.search(rf"(?<![\d.,]){re.escape(number)}(?![\d]|\.\d)", board), (
                f"{number} is not in {page.group(1)}"
            )


def test_the_javascript_page_says_what_the_npm_package_is():
    """docs/javascript.md names the versions js/package.json pins and every
    call the package offers: the page is how an npm user learns what the
    package does, and a version bumped or a call added without it tells them
    something else."""
    import json

    page = (ROOT / "docs" / "javascript.md").read_text(encoding="utf-8")
    npm = json.loads((ROOT / "js" / "package.json").read_text(encoding="utf-8"))
    types = (ROOT / "js" / "index.d.ts").read_text(encoding="utf-8")

    assert "npm install sluicer" in page
    assert f"Pyodide {npm['dependencies']['pyodide']}" in page
    assert f"Node {npm['engines']['node'].removeprefix('>=')} or later" in page
    sluicer = types.split("export interface Sluicer {", 1)[1].split("\n}", 1)[0]
    offered = set(re.findall(r"^  (\w+)\(", sluicer, re.MULTILINE))
    assert offered == {"extract", "toMarkdown", "compile", "run"}
    for call in (*offered, "createSluicer", "SluicerError"):
        assert f"`{call}" in page, call
    # What the package does not do is said, not left to be found out.
    assert "## What it does not do" in page
    assert "fetch" in page.split("## What it does not do", 1)[1]


def _commands(block: str) -> list[tuple[list[str], int]]:
    """Each ``sluicer`` command of a shell block, its line continuations
    joined, with the exit code its comment names (0 when it names none)."""
    import shlex

    commands = []
    for line in block.replace("\\\n", " ").splitlines():
        if not line.startswith("sluicer "):
            continue
        command, _, comment = line.partition("#")
        said = re.search(r"exit (\d)", comment)
        commands.append((shlex.split(command)[1:], int(said.group(1)) if said else 0))
    return commands


def test_the_readme_s_heal_runs_as_written_and_prints_what_it_shows(
    monkeypatch, tmp_path
):
    """The quick start's heal step, on the made-up shop in ``examples/shop``,
    is run command by command: the quick start once opened ``p1.html``, a file
    that exists nowhere, and healed ``https://shop.example/``."""
    import shutil

    from click.testing import CliRunner

    from sluicer.cli import main

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    shell, shown = re.search(
        r"```bash\n(sluicer compile examples/shop/.*?)```\n\n```text\n(.*?)```",
        section,
        re.DOTALL,
    ).groups()
    commands = _commands(shell)
    assert [c[0][0] for c in commands] == ["compile", "run", "heal"]

    shutil.copytree(ROOT / "examples" / "shop", tmp_path / "examples" / "shop")
    monkeypatch.chdir(tmp_path)
    for arguments, code in commands:
        result = CliRunner().invoke(main, arguments)
        assert result.exit_code == code, (arguments, result.stderr)
    assert result.stderr == shown

    healed = CliRunner().invoke(
        main, ["run", "shop-healed.json", "examples/shop/after.html"]
    )
    assert healed.exit_code == 0, healed.stderr


def test_what_the_readme_and_why_say_of_heal_is_the_drift_benchmark_s():
    """The README said `heal` "tells you where each field moved"; on the drift
    benchmark's redesigns it was fully right on none. What the README and the
    why page now say of heal's record is read from the drift page's heal
    table, so a regenerated benchmark cannot leave the claim behind."""
    drift = (ROOT / "docs" / "drift.md").read_text(encoding="utf-8")
    table = drift.split("| heal | on the pairs with drift |", 1)[1].split("\n\n", 1)[0]
    heal = {
        row.group(1): int(row.group(2))
        for row in re.finditer(r"^\| ([A-Za-z ]+) \| (\d+) \| \d+ \|$", table, re.M)
    }
    assert set(heal) == {"right", "partly right", "nothing to match", "no listing on B"}
    changed = sum(heal.values())
    right = "none" if heal["right"] == 0 else str(heal["right"])
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    said = " ".join(readme.split())
    assert f"{changed} real redesigns, {heal['nothing to match']} of the new" in said
    assert f"fully right on {right} and partly right on {heal['partly right']}" in said
    why = " ".join((ROOT / "docs" / "why.md").read_text(encoding="utf-8").split())
    assert f"{changed} real redesigns" in why
    assert f"fully right on {right} of them and partly right on" in why
    assert f"partly right on {heal['partly right']}." in why


def test_the_roadmap_names_every_release_the_changelog_does():
    """ROADMAP.md stopped at "Shipped in 0.6.0" while 0.7.0, 0.8.0 and 0.9.0
    had shipped: every minor release in the changelog has its section."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    releases = re.findall(r"^## (\d+\.\d+\.0) - ", changelog, re.MULTILINE)
    assert releases
    for release in releases:
        assert f"## Shipped in {release}\n" in roadmap, release


def test_every_call_the_guides_spell_from_sluicer_is_there_after_import_sluicer():
    """getting-started said `sluicer.fetch.fetch(url)` after `import sluicer`,
    which raises AttributeError: `sluicer.fetch` is a module `import sluicer`
    does not load. Each `sluicer.a.b(` a guide spells is looked up as a reader
    would, in a fresh interpreter that ran only `import sluicer`."""
    import subprocess
    import sys

    pages = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    names = set()
    for page in pages:
        if page.is_symlink():  # the changelog tells history, not usage
            continue
        text = page.read_text(encoding="utf-8")
        names.update(re.findall(r"`sluicer\.([A-Za-z_][\w.]*)\(", text))
    assert "extract" in names
    lookup = (
        "import sluicer, sys\n"
        "for name in sys.argv[1:]:\n"
        "    thing = sluicer\n"
        "    for part in name.split('.'):\n"
        "        thing = getattr(thing, part, None)\n"
        "    if thing is None:\n"
        "        print(name)\n"
    )
    missing = subprocess.run(
        [sys.executable, "-c", lookup, *sorted(names)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert missing == [], missing


def test_the_configuration_page_s_first_file_works_where_the_page_saves_it(
    monkeypatch, tmp_path
):
    """configuration.md's first example sets a proxy, and the page said only
    to call it `sluicer.toml`: saved in the directory a command runs in, it
    made every command exit 2. Saved where the page now says, and named as it
    says, a command reads it and runs; found in the working directory, it is
    still refused, as the page warns."""
    from click.testing import CliRunner

    from sluicer.cli import main

    page = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    lead = page.split("## A file", 1)[1]
    where = re.search(r"Save it as `~/([^`]+)`", lead)
    assert where is not None, "the page says where to save the file"
    named = re.search(r"export SLUICER_CONFIG=~/([^`]+)`", lead)
    assert named is not None and named.group(1) == where.group(1)
    toml = re.search(r"```toml\n(.*?)```", lead, re.DOTALL).group(1)

    home = tmp_path / "home"
    saved = home / where.group(1)
    saved.parent.mkdir(parents=True)
    saved.write_text(toml, encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in ("SLUICER_CONFIG", "SLUICER_PROXY"):
        monkeypatch.setenv(name, "")  # undone when the test ends
        monkeypatch.delenv(name)
    page_file = str(ROOT / "examples" / "brake-pads.html")

    monkeypatch.setenv("SLUICER_CONFIG", str(saved))
    read = CliRunner().invoke(main, ["extract", page_file])
    assert read.exit_code == 0, read.stderr

    monkeypatch.delenv("SLUICER_CONFIG")
    (work / "sluicer.toml").write_text(toml, encoding="utf-8")
    found = CliRunner().invoke(main, ["extract", page_file])
    assert found.exit_code == 2
    assert "only in a file you name" in found.stderr


def test_the_extruct_page_s_calls_do_what_it_says_on_a_base_install(absent):
    """docs/extruct.md called the move "one line", then listed the extra: on
    an install without mf2py the one line raises. The page installs the extra
    first, says the call raises without it, and gives the call that does not;
    each is run here with mf2py absent."""
    from sluicer import MicroformatsExtraMissing
    from sluicer.compat import extruct

    page = (ROOT / "docs" / "extruct.md").read_text(encoding="utf-8")
    lead = page.split("\n## ", 1)[0]
    install = re.search(r"```bash\n(.*?)```", lead, re.DOTALL).group(1)
    assert install.strip() == 'pip install "sluicer[microformats]"'
    one_line = re.search(r"^data = (extruct\.extract\(.*\))$", lead, re.MULTILINE)
    base = re.search(r"`(extruct\.extract\(html, base_url=url, syntaxes=.*?\))`", lead)
    assert one_line is not None and base is not None
    names = {
        "extruct": extruct,
        "html": (ROOT / "examples" / "brake-pads.html").read_text(encoding="utf-8"),
        "url": "https://example.com/p/bp-2210",
    }

    absent("mf2py")
    assert "MicroformatsExtraMissing" in lead
    with pytest.raises(MicroformatsExtraMissing):
        eval(one_line.group(1), names)
    data = eval(base.group(1), names)
    assert "microformat" not in data
    assert data["json-ld"][0]["@type"] == "Product"
