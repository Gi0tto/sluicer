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
        "RedirectRefused",
        "ResponseTooLarge",
        "RobotsRefused",
        "fetch",
        "robots_reader_from",
    }


def test_the_rung_type_lives_beside_the_result_it_returns():
    """The adapter must not have to import a type from the orchestrator."""
    import sluicer.fetch.scrapling_rungs as adapter
    from sluicer.fetch import result

    assert adapter.Rung is result.Rung


def test_installing_the_mcp_extra_gives_a_server_whose_tools_all_work():
    """Two of the three tools need the other extras, so the extra must pull them.

    Read back out of the built metadata rather than out of pyproject.toml: a
    self-referential extra is a thing the packaging machinery has to resolve,
    and the only proof that it did is what the installer will read.
    """
    from importlib import metadata

    required = metadata.requires("sluicer")
    under_mcp = [line for line in required if "extra == 'mcp'" in line]

    # Asserted by effect, not by spelling. pyproject.toml declares the
    # self-references sluicer[fetch] and sluicer[markdown], and the build
    # backend is free to resolve them: hatchling flattens them to the
    # underlying requirements. Both spellings install the same three
    # packages, and that is the thing worth pinning.
    assert any("scrapling" in line or "sluicer[fetch]" in line for line in under_mcp), (
        f"the mcp extra does not bring the fetch extra: {under_mcp}"
    )
    assert any(
        "trafilatura" in line or "sluicer[markdown]" in line for line in under_mcp
    ), f"the mcp extra does not bring the markdown extra: {under_mcp}"


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


def test_the_fetch_extra_declares_the_robots_parser_it_uses():
    """A transitive dependency is not a declared one, and this is the third time.

    ``identity.py`` imports protego to parse robots.txt, and nothing declared
    it: it arrived only because ``scrapling[fetchers]`` happens to pull it in
    today. The day scrapling drops it, or a reader installs protego's provider
    some other way, the robots gate stops working -- and the comment block
    above that import is this project's own record of learning exactly this
    lesson, twice, about scrapling's fetchers and about the mcp extra.

    Read out of the built metadata, not out of pyproject.toml, for the same
    reason the mcp test above does: what the installer will read is the only
    proof that matters.
    """
    from importlib import metadata

    under_fetch = [
        line for line in metadata.requires("sluicer") if "extra == 'fetch'" in line
    ]

    assert any("protego" in line for line in under_fetch), (
        f"the fetch extra does not declare protego: {under_fetch}"
    )


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
