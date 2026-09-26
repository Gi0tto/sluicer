"""The Homebrew formula and the conda-forge recipe under packaging/.

Both are written by ``packaging/recipes.py`` and submitted by hand, so nothing
else notices when they fall behind: a floor raised in ``pyproject.toml``, a
dependency added to the base install, a file edited by hand and overwritten by
the next run. Read offline: the sdist's checksum is taken from the committed
formula, which is either PyPI's or the placeholder.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import sluicer

ROOT = Path(__file__).resolve().parent.parent


def _recipes() -> ModuleType:
    path = ROOT / "packaging" / "recipes.py"
    spec = importlib.util.spec_from_file_location("recipes", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["recipes"] = module
    spec.loader.exec_module(module)
    return module


recipes = _recipes()


def _committed_source() -> tuple[str, str]:
    """The sdist's address and checksum the committed formula names."""
    formula = recipes.FORMULA.read_text(encoding="utf-8")
    url = re.search(r'^  url "(.+)"$', formula, re.MULTILINE)
    sha256 = re.search(r'^  sha256 "([0-9a-f]{64})"$', formula, re.MULTILINE)
    assert url and sha256, "the formula names no sdist, or a malformed checksum"
    return url[1], sha256[1]


def _base_dependencies() -> list[tuple[str, str, str]]:
    """``pyproject.toml``'s base dependencies as (name, floor, marker).

    Read with a pattern, not ``tomllib``, which Python 3.10 lacks.
    """
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    listed = re.search(r"^dependencies = \[([^\]]*)\]$", pyproject, re.MULTILINE)
    assert listed, "pyproject.toml's dependencies are no longer a list of strings"
    found = []
    for double, single in re.findall(r'"([^"]+)"|\'([^\']+)\'', listed[1]):
        entry = double or single
        requirement, _, marker = entry.partition(";")
        parsed = re.fullmatch(r"\s*([\w.-]+)\s*>=\s*([\w.]+)\s*", requirement)
        assert parsed, f"not a name and a floor: {entry}"
        found.append((parsed[1].lower(), parsed[2], marker.strip().replace("'", '"')))
    return found


def test_the_committed_files_are_the_script_s_output():
    url, sha256 = _committed_source()
    for path, text in recipes.written(url, sha256).items():
        assert path.read_text(encoding="utf-8") == text, (
            f"{path.relative_to(ROOT)} is not what packaging/recipes.py writes: "
            "edit the script and run it again"
        )


def test_the_recipe_carries_the_formula_s_checksum():
    _, sha256 = _committed_source()
    recipe = recipes.RECIPE.read_text(encoding="utf-8")
    assert re.findall(r"^  sha256: (\S+)$", recipe, re.MULTILINE) == [sha256]


def test_a_placeholder_says_so_in_both_files():
    _, sha256 = _committed_source()
    for path in (recipes.FORMULA, recipes.RECIPE):
        text = path.read_text(encoding="utf-8")
        assert ("PLACEHOLDER" in text) == (sha256 == recipes.PLACEHOLDER), path


def test_the_version_is_stated_once_and_used_where_expected():
    version = recipes.VERSION
    script = (ROOT / "packaging" / "recipes.py").read_text(encoding="utf-8")
    assert re.findall(r"^VERSION = \"(.+)\"$", script, re.MULTILINE) == [version]
    url, _ = _committed_source()
    assert url.endswith(f"/sluicer-{version}.tar.gz")
    recipe = recipes.RECIPE.read_text(encoding="utf-8")
    assert re.findall(r'^  version: "(.+)"$', recipe, re.MULTILINE) == [version]
    # Everywhere else the recipe says ${{ version }}, never the number.
    assert recipe.count(version) == 1 + recipe.count(f"sluicer {version} has no")


def test_the_recipes_are_not_behind_the_package():
    """A release past ``VERSION`` that forgot to move the recipes fails."""
    assert _parts(recipes.VERSION) >= _parts(sluicer.__version__)


def test_the_formula_installs_every_base_dependency_at_or_above_its_floor():
    """Homebrew's Python is 3.14, so a dependency pyproject asks for below
    3.11 only is not installed by the formula; every other one is."""
    resources = {resource.name: resource for resource in recipes.RESOURCES}
    formula = recipes.FORMULA.read_text(encoding="utf-8")
    assert sorted(re.findall(r'^  resource "(.+)" do$', formula, re.MULTILINE)) == (
        sorted(resources)
    )
    assert recipes.PYTHON == "python@3.14"
    wanted = {}
    for name, floor, marker in _base_dependencies():
        if marker:
            assert marker == 'python_version < "3.11"', f"a marker to judge: {marker}"
            continue
        wanted[name] = floor
    assert set(wanted) <= set(resources)
    for name, floor in wanted.items():
        resource = resources[name]
        assert _parts(resource.version) >= _parts(floor), name
        assert resource.url.endswith(f"/{name}-{resource.version}.tar.gz")
    for resource in resources.values():
        assert resource.url.startswith("https://files.pythonhosted.org/packages/")
        assert re.fullmatch(r"[0-9a-f]{64}", resource.sha256), resource.name


def test_the_formula_installs_the_whole_tree_under_the_base_install():
    """A formula installs its resources with no index to fall back on, so
    every package the base install needs on macOS and Linux is one of them,
    each at a version its dependents accept, and nothing else is. Since 0.10
    that is trafilatura's tree. Read from the metadata of the packages this
    suite runs with, which is the tree pip would install."""
    from importlib import metadata

    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    environment = default_environment() | {
        "python_version": "3.14",
        "python_full_version": "3.14.0",
        "sys_platform": "darwin",
        "platform_system": "Darwin",
        "os_name": "posix",
        "extra": "",
    }
    resources = {
        canonicalize_name(resource.name): resource for resource in recipes.RESOURCES
    }
    tree: set[str] = set()
    seen: set[tuple[str, str]] = set()
    # A requirement's own extras count: justext asks for lxml[html_clean].
    waiting = [("sluicer", "")]
    while waiting:
        name, extra = waiting.pop()
        if (name, extra) in seen:
            continue
        seen.add((name, extra))
        for line in metadata.requires(name) or []:
            wanted = Requirement(line)
            marker = wanted.marker
            if marker is not None and not marker.evaluate(
                environment | {"extra": extra}
            ):
                continue
            if marker is None and extra:
                continue
            key = canonicalize_name(wanted.name)
            assert key in resources, f"the formula does not install {key}"
            version = resources[key].version
            assert wanted.specifier.contains(version, prereleases=True), (
                f"{name} wants {wanted}, the formula installs {version}"
            )
            tree.add(key)
            waiting += [(wanted.name, ""), *((wanted.name, e) for e in wanted.extras)]
    assert set(resources) == tree


def test_the_recipe_runs_on_pyproject_s_floors():
    """conda-forge builds a noarch package for its own ``python_min`` and
    later, 3.11, so a dependency pyproject asks for below 3.11 only is left
    out; every other one is stated at pyproject's floor."""
    recipe = recipes.RECIPE.read_text(encoding="utf-8")
    run = re.search(r"^  run:\n((?:    - .+\n)+)", recipe, re.MULTILINE)
    assert run
    stated = dict(re.findall(r"^    - (\S+) >=(.+)$", run[1], re.MULTILINE))
    assert stated.pop("python") == "${{ python_min }}"
    assert "python_min:" not in recipe, "conda-smithy asks not to redefine it"
    wanted = {}
    for name, floor, marker in _base_dependencies():
        if marker:
            assert marker == 'python_version < "3.11"', f"a marker to judge: {marker}"
            assert _parts(recipes.PYTHON_MIN) >= (3, 11)
            continue
        wanted[name] = floor
    assert stated == wanted
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requires = re.search(r'^requires-python = ">=(.+)"$', pyproject, re.MULTILINE)
    assert requires and _parts(requires[1]) <= _parts(recipes.PYTHON_MIN)
    backend = re.search(r'^requires = \["hatchling>=(.+)"\]$', pyproject, re.MULTILINE)
    assert backend and f"hatchling >={backend[1]}" in recipes.HOST


def test_both_state_pyproject_s_licence():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    licence = re.search(r'^license = "(.+)"$', pyproject, re.MULTILINE)
    assert licence and licence[1] == " AND ".join(recipes.LICENSE)
    recipe = recipes.RECIPE.read_text(encoding="utf-8")
    assert f"  license: {licence[1]}\n" in recipe
    formula = recipes.FORMULA.read_text(encoding="utf-8")
    spelled = ", ".join(f'"{name}"' for name in recipes.LICENSE)
    assert f"  license all_of: [{spelled}]\n" in formula


def test_the_extraction_both_test_gives_the_price_they_assert():
    found = sluicer.extract(recipes.page())
    assert found.summary["price"].value == "19.99"
    assert found.summary["price"].source == "jsonld"


def test_a_local_sdist_must_be_of_the_version_named(tmp_path):
    wrong = tmp_path / "sluicer-0.0.1.tar.gz"
    wrong.write_bytes(b"not an sdist")
    try:
        recipes.from_sdist(wrong)
    except SystemExit as refused:
        assert recipes.VERSION in str(refused)
    else:
        raise AssertionError("an sdist of another version was accepted")
    right = tmp_path / f"sluicer-{recipes.VERSION}.tar.gz"
    right.write_bytes(b"not an sdist")
    url, sha256 = recipes.from_sdist(right)
    assert url.endswith(f"/sluicer-{recipes.VERSION}.tar.gz")
    assert sha256 == hashlib.sha256(b"not an sdist").hexdigest()


def _parts(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))
