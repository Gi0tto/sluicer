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
    assert set(fetch_package.__all__) == {"Climb", "Fetched", "RobotsRefused", "fetch"}


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
    assert any(
        "scrapling" in line or "sluicer[fetch]" in line for line in under_mcp
    ), f"the mcp extra does not bring the fetch extra: {under_mcp}"
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
        and "sluicer.fetch.ladder" in path.read_text()
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

    assert any(
        "protego" in line for line in under_fetch
    ), f"the fetch extra does not declare protego: {under_fetch}"


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
    from sluicer.structure.shape import signature

    assert sluicer.structure is structure_package, "a name means one thing"
    assert sluicer.induce is structure_package.induce
    assert structure_package.__all__ == ["induce"]
    assert structure_package.groups.repeating_groups is repeating_groups
    assert structure_package.records.records_from is records_from
    assert structure_package.shape.signature is signature


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
            [sys.executable, "-c", statement], capture_output=True, text=True
        )

        assert done.returncode == 0, f"{statement}\n{done.stderr}"
