def test_package_exposes_a_version():
    import sluicer

    assert sluicer.__version__.count(".") == 2


def test_the_types_users_touch_are_exported_from_the_package_root():
    import sluicer
    from sluicer.declared.merge import Field, Record

    assert sluicer.Record is Record
    assert sluicer.Field is Field
    assert set(sluicer.__all__) >= {"Extraction", "Field", "Record", "extract"}


def test_the_fetch_package_has_a_surface_of_its_own():
    """The plan calls it "the package's fetch surface": it has to be one."""
    import sluicer.fetch as fetch_package
    from sluicer.fetch.ladder import RobotsRefused, fetch
    from sluicer.fetch.result import Climb, Fetched

    assert fetch_package.fetch is fetch
    assert fetch_package.Fetched is Fetched
    assert fetch_package.Climb is Climb
    assert fetch_package.RobotsRefused is RobotsRefused
    assert set(fetch_package.__all__) == {
        "AddressRefused",
        "Climb",
        "FetchFailed",
        "Fetched",
        "PaymentRequired",
        "RedirectRefused",
        "ResponseTooLarge",
        "RobotsRefused",
        "RungMemory",
        "STICKY",
        "SiteRefused",
        "fetch",
        "robots_reader_from",
    }


def test_the_rung_type_lives_beside_the_result_it_returns():
    """The adapter must not have to import a type from the orchestrator."""
    from sluicer.fetch import browser, result, rungs

    assert rungs.Rung is result.Rung
    assert browser.Rung is result.Rung


def test_installing_the_mcp_extra_gives_a_server_whose_tools_all_work():
    """page_markdown needs trafilatura for any input, so the extra must pull
    it; fetching needs nothing past the base install, so it must pull no
    browser: until 0.8 it brought two Playwright drivers, 86 to 96 MB of
    wheels, for a rung most calls never reach.

    Read back out of the built metadata rather than out of pyproject.toml: a
    self-referential extra is a thing the packaging machinery has to resolve,
    and the only proof that it did is what the installer will read.
    """
    from importlib import metadata

    required = metadata.requires("sluicer")
    under_mcp = [line for line in required if "extra == 'mcp'" in line]

    # Asserted by effect, not by spelling: hatchling may flatten the
    # self-reference sluicer[markdown] to trafilatura itself.
    assert any(
        "trafilatura" in line or "sluicer[markdown]" in line for line in under_mcp
    ), f"the mcp extra does not bring the markdown extra: {under_mcp}"
    for heavy in ("scrapling", "playwright", "patchright", "sluicer[fetch]"):
        assert not any(heavy in line for line in under_mcp), (
            f"the mcp extra brings {heavy}: {under_mcp}"
        )


def test_the_fetch_extra_still_installs_every_rung_it_meant():
    """Deprecated, not removed: a line written for 0.7 keeps its browser and
    its stealth rung."""
    from importlib import metadata

    under_fetch = [
        line for line in metadata.requires("sluicer") if "extra == 'fetch'" in line
    ]

    assert any(
        "playwright" in line or "sluicer[browser]" in line for line in under_fetch
    )
    assert any(
        "scrapling" in line or "sluicer[stealth]" in line for line in under_fetch
    )


def test_nothing_outside_the_fetch_package_reaches_past_its_surface():
    """``sluicer.fetch`` says it is the surface; one import has to mean one thing.

    ``cli.py`` imported ``fetch`` from ``sluicer.fetch.ladder`` while
    ``mcp_server.py`` imported it from ``sluicer.fetch``, so the same function
    had two spellings and the stated convention had no way to be wrong. The
    fetch package's own modules may of course name each other.
    """
    from pathlib import Path

    import sluicer

    root = Path(sluicer.__file__).parent
    offenders = [
        path.relative_to(root).as_posix()
        for path in sorted(root.rglob("*.py"))
        if "fetch" not in path.relative_to(root).parts
        and "sluicer.fetch.ladder" in path.read_text(encoding="utf-8")
    ]

    assert offenders == [], f"these import past the fetch surface: {offenders}"


def test_the_base_install_declares_everything_a_fetch_uses():
    """A transitive dependency is not a declared one, and this is the fourth time.

    ``identity.py`` imports protego to parse robots.txt, and until 0.7.1
    nothing declared it: it arrived only because ``scrapling[fetchers]``
    pulled it in. Since 0.8 the base install fetches, so protego is the base
    install's, and the HTTP rung is the standard library's: no curl_cffi, no
    scrapling, no browser among what every install gets.

    Read out of the built metadata, not out of pyproject.toml, for the same
    reason the mcp test above does: what the installer will read is the only
    proof that matters.
    """
    from importlib import metadata

    base = [line for line in metadata.requires("sluicer") if "extra ==" not in line]

    assert any(line.startswith("protego") for line in base), base
    for absent in ("curl", "scrapling", "playwright"):
        assert not any(absent in line for line in base), base


def test_the_structure_package_has_a_surface_of_its_own():
    """`induce` the function shadowed `sluicer.induce` the package, and won.

    The suite never saw it because every test imported `from sluicer.induce
    import ...`, which resolves the package before the root `__init__` rebinds
    the name. Read as an attribute, or imported in a process that had done
    neither, the package was gone.
    """
    import sluicer
    import sluicer.structure as structure_package
    from sluicer.structure.groups import repeating_groups
    from sluicer.structure.records import records_from
    from sluicer.structure.shape import same_kind

    assert sluicer.structure is structure_package, "a name means one thing"
    assert sluicer.induce is structure_package.induce
    assert structure_package.__all__ == ["induce"]
    assert structure_package.groups.repeating_groups is repeating_groups
    assert structure_package.records.records_from is records_from
    assert structure_package.shape.same_kind is same_kind


def test_a_submodule_is_importable_in_a_process_that_knows_nothing():
    """`import sluicer.induce.records as r` raised ImportError in a clean process."""
    import subprocess
    import sys

    for statement in (
        "import sluicer.structure.records as r; assert r.records_from",
        "import sluicer.structure.records; import sluicer;"
        " assert sluicer.structure.records.records_from",
    ):
        done = subprocess.run(
            [sys.executable, "-c", statement],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        assert done.returncode == 0, f"{statement}\n{done.stderr}"


def test_every_file_that_states_the_version_or_the_licence_agrees():
    """The version is written in six files and the licence in five: a release
    that bumps one and forgets another tells PyPI, npm, the plugin, the skill
    and a citation five different things. The npm package carries the wheel
    built from this checkout, and its build refuses a version other than
    pyproject's. Read with patterns, not ``tomllib``, which Python 3.10
    lacks."""
    import json
    import re
    from pathlib import Path

    import sluicer

    root = Path(__file__).resolve().parent.parent
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    plugin = json.loads(
        (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    skill = (root / "skills" / "sluicer" / "SKILL.md").read_text(encoding="utf-8")
    citation = (root / "CITATION.cff").read_text(encoding="utf-8")
    npm = json.loads((root / "js" / "package.json").read_text(encoding="utf-8"))

    def stated(pattern: str, text: str) -> str:
        found = re.search(pattern, text, re.MULTILINE)
        assert found, pattern
        return found[1]

    version = sluicer.__version__
    assert stated(r'^version = "(.+)"$', pyproject) == version
    assert plugin["version"] == version
    # Under metadata: the Agent Skills standard allows no top-level version.
    assert stated(r'^metadata:\n(?:  .+\n)*?  version: "(.+)"$', skill) == version
    assert stated(r"^version: (.+)$", citation) == version
    assert npm["version"] == version

    licence = stated(r'^license = "(.+)"$', pyproject)
    assert licence == "MIT AND CC-BY-SA-3.0 AND Unicode-3.0"
    assert plugin["license"] == licence
    # The wheel inside the npm package holds the same two files that are not
    # under MIT.
    assert npm["license"] == licence
    listed = stated(r"^license:\n((?:  - .+\n)+)", citation).splitlines()
    assert " AND ".join(line.removeprefix("  - ") for line in listed) == licence


def test_the_plugin_counts_the_tools_the_server_registers():
    """The server's docstring is held to the registered tools elsewhere; the
    plugin's description, which a marketplace shows, is held to it here."""
    import json
    import re
    from pathlib import Path

    import sluicer.mcp_server

    root = Path(__file__).resolve().parent.parent
    plugin = json.loads(
        (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    counted = re.match(
        r"(\w+) tools -- ", (sluicer.mcp_server.__doc__ or "").split("\n\n")[1]
    )
    assert counted, "the server's docstring counts its tools"
    assert f"with {counted[1].lower()} tools" in plugin["description"]


def test_the_skill_keeps_to_the_agent_skills_standard():
    """Codex and the other clients that read agentskills.io skills refuse a
    field the standard does not name: 0.4.0's skill had a top-level version,
    and the standard's own validator refused it."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    skill = root / "skills" / "sluicer" / "SKILL.md"
    front = skill.read_text(encoding="utf-8").split("---\n", 2)[1]
    fields = dict(
        line.split(":", 1)
        for line in front.splitlines()
        if line and not line.startswith(" ")
    )
    allowed = {"name", "description", "license", "compatibility", "metadata"}
    assert set(fields) <= allowed | {"allowed-tools"}, set(fields) - allowed
    name = fields["name"].strip()
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) and len(name) <= 64
    assert name == skill.parent.name, "the standard wants the directory's name"
    assert 0 < len(fields["description"].strip()) <= 1024
    assert 0 < len(fields["compatibility"].strip()) <= 500


def test_the_mcp_registry_entry_is_the_package_it_names():
    """The MCP Registry lists server.json, and verifies it owns the package by
    reading ``mcp-name`` in the README PyPI serves; a release that bumps the
    package and not the entry lists the old one."""
    import json
    import re
    from pathlib import Path

    import sluicer

    root = Path(__file__).resolve().parent.parent
    entry = json.loads((root / "server.json").read_text(encoding="utf-8"))
    readme = (root / "README.md").read_text(encoding="utf-8")
    marker = re.search(r"<!-- mcp-name: (\S+) -->", readme)
    assert marker and marker[1] == entry["name"] == "io.github.Gi0tto/sluicer"
    assert len(entry["description"]) <= 100, "the registry refuses a longer one"
    [package] = entry["packages"]
    version = sluicer.__version__
    assert entry["version"] == package["version"] == version
    assert package["identifier"] == "sluicer" and package["runtimeHint"] == "uvx"
    # uvx --with "sluicer[mcp]==VERSION" sluicer mcp: the command this suite
    # tests, with the extra it needs, at the version listed.
    assert package["runtimeArguments"] == [
        {
            "type": "named",
            "name": "--with",
            "value": f"sluicer[mcp]=={version}",
            "description": package["runtimeArguments"][0]["description"],
        }
    ]
    assert package["packageArguments"] == [{"type": "positional", "value": "mcp"}]


def test_the_package_runs_as_a_module():
    """``python -m sluicer`` is the command line, for a Python whose scripts
    directory is not on PATH: Glama's image installs the package so, and
    ``sluicer`` there was not found."""
    import subprocess
    import sys

    import sluicer

    ran = subprocess.run(
        [sys.executable, "-m", "sluicer", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert sluicer.__version__ in ran.stdout


def test_every_action_a_workflow_uses_is_pinned_to_a_commit():
    """A tag can be moved to other code; a commit cannot. Every workflow names
    each action by its full commit, with the release it is in a comment, so a
    reader sees which version it is and a moved tag changes nothing."""
    import re
    from pathlib import Path

    folder = Path(__file__).parent.parent / ".github" / "workflows"
    workflows = sorted(folder.glob("*.yml"))
    assert any(path.name == "js.yml" for path in workflows)
    for path in workflows:
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.match(r"\s*(?:- )?uses:", line):
                assert re.search(r"uses: [\w.-]+/[\w./-]+@[0-9a-f]{40} # v\d", line), (
                    f"{path.name}: {line.strip()}"
                )


def test_the_npm_package_is_tested_and_published_only_from_a_tag():
    """js.yml runs the npm package's tests on the answers the native package
    gives at the same commit, and publishes only as the PyPI job does: from a
    tag, in its own environment, behind a repository variable, after the
    tests, with the version the tag names."""
    from pathlib import Path

    workflow = (
        Path(__file__).parent.parent / ".github" / "workflows" / "js.yml"
    ).read_text(encoding="utf-8")
    jobs = workflow.split("\njobs:\n", 1)[1]
    publish = jobs.split("\n  publish:\n", 1)[1]
    tests = jobs.split("\n  publish:\n", 1)[0]

    assert "permissions:\n  contents: read" in workflow
    assert "npm ci" in tests and "npm test" in tests
    # The committed answers are this commit's native ones.
    assert "js/scripts/expected.py" in tests and "git diff --exit-code" in tests
    assert "tests/test_package.py" in tests
    assert "npm publish" not in tests
    assert (
        "if: startsWith(github.ref, 'refs/tags/v') && vars.PUBLISH_TO_NPM == 'true'"
        in publish
    )
    assert "environment: npm" in publish
    assert "needs:" in publish
    assert "GITHUB_REF_NAME" in publish
    assert "npm publish --provenance" in publish
