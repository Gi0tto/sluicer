"""Write Sluicer's Homebrew formula and its conda-forge recipe.

    python packaging/recipes.py                  # the sdist from PyPI, if it is there
    python packaging/recipes.py --sdist dist/sluicer-0.9.1.tar.gz
    python packaging/recipes.py --offline        # a placeholder checksum, no network
    python packaging/recipes.py --check          # exit 1 if a written file is stale

Both are prepared here and submitted by hand -- the formula to homebrew-core,
the recipe to conda-forge's staged-recipes -- and neither is submitted by
anything in this repository. Both install the base package, no extra: what
``pip install sluicer`` installs.

``VERSION`` is the one place the release is named. The sdist's checksum is
PyPI's once that version is published there, or a local sdist's when one is
given, or else a placeholder of zeros that says so in a comment beside it,
which neither Homebrew nor conda-forge would accept: a file written before the
release is a draft until it is written again after. The formula's resources
are exact versions, as homebrew-core pins them; the recipe's requirements are
the floors ``pyproject.toml`` declares, as conda-forge states them.
``tests/test_recipes.py`` holds both files to this script's output and to
``pyproject.toml``.

The standard library only, so it runs from any checkout with any Python 3.10
or later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

VERSION = "0.9.1"
"""The release both files install. Change it here, and nowhere else."""

ROOT = Path(__file__).resolve().parent.parent
FORMULA = ROOT / "packaging" / "homebrew" / "sluicer.rb"
RECIPE = ROOT / "packaging" / "conda-forge" / "recipe" / "recipe.yaml"

PLACEHOLDER = "0" * 64
"""The checksum written while ``VERSION`` has no sdist to be read."""

PYTHON = "python@3.14"
"""The Python homebrew-core builds its Python applications on, as of
2026-09-25 (scrapy, yle-dl, gcovr, howdoi all depend on it)."""

PYTHON_MIN = "3.11"
"""The oldest Python conda-forge builds a noarch package for: ``python_min``
in its global pinning (CFEP-25), read on 2026-09-25. The recipe does not set
it: conda-smithy's linter asks a recipe not to redefine it at or below the
default, which requires-python's 3.10 would be. So the recipe installs on
3.11 and later, where the standard library reads TOML."""


@dataclass(frozen=True)
class Resource:
    """One package the formula installs into its virtualenv, as PyPI serves
    its sdist."""

    name: str
    version: str
    url: str
    sha256: str


RESOURCES = (
    # The base install's own four, read from PyPI's JSON on 2026-09-25: each
    # project's newest release. None of them depends on anything on macOS or
    # Linux (click wants colorama on Windows only). trafilatura, in the base
    # install since 0.10, and the fifteen packages under it are pinned as
    # uv.lock pins them, read on 2026-09-26; tzlocal's tzdata is for Windows
    # only, and left out.
    # tomli is not here: pyproject asks for it below Python 3.11 only, and the
    # formula's Python is 3.14.
    Resource(
        "babel",
        "2.18.0",
        "https://files.pythonhosted.org/packages/7d/b2/51899539b6ceeeb420d40ed3cd4b7a40519404f9baf3d4ac99dc413a834b/babel-2.18.0.tar.gz",
        "b80b99a14bd085fcacfa15c9165f651fbb3406e66cc603abf11c5750937c992d",
    ),
    Resource(
        "certifi",
        "2026.7.22",
        "https://files.pythonhosted.org/packages/a3/c2/24167ea9858356b47a87a50d39908bfdb72ceeefe0041586e704e5376b3a/certifi-2026.7.22.tar.gz",
        "741e2c3b351ddf169a738da9f2c048608ff7f2c5cc02f1ebc6b118bb090d5d55",
    ),
    Resource(
        "charset-normalizer",
        "3.5.1",
        "https://files.pythonhosted.org/packages/e5/3f/143b048436775b0f76ac3eec145c019e8173ccc2885c8f20319b996d5e83/charset_normalizer-3.5.1.tar.gz",
        "6117b84ea48435e5356dc737f5121485c30920ba43375fa7b434fd753df0eac3",
    ),
    Resource(
        "click",
        "8.5.0",
        "https://files.pythonhosted.org/packages/c7/0e/7fa0ef50764b67090eca4114772a2abf8b6148198475e54c660b97caeee6/click-8.5.0.tar.gz",
        "ba0d2089de75ea0310e2dde03160e6ca10009947fb95a182f9b54021bb272e34",
    ),
    Resource(
        "courlan",
        "1.4.0",
        "https://files.pythonhosted.org/packages/bb/16/2a771612ee0b3acaa95ac21cc7e8a3319e815d6360f8ffc5987d1ce28499/courlan-1.4.0.tar.gz",
        "fbbac7b7fcde2195ea08e707609503c81cf39c891e8d26cdb1fed4585782d63d",
    ),
    Resource(
        "cssselect",
        "1.5.0",
        "https://files.pythonhosted.org/packages/8e/5a/6d6fcf922709391fac986f0a03ad4546f4f45b94d10aeb6c1ee041599993/cssselect-1.5.0.tar.gz",
        "3cbe82dd7acbee9ba9e5723b5f9e4749826912f1fb31cd7f92aabed5fde15b15",
    ),
    Resource(
        "dateparser",
        "1.4.3",
        "https://files.pythonhosted.org/packages/c7/5d/bd21ba1519b6b1e222b29878301d2e1fb928e890dc7d085fa4222ac5671b/dateparser-1.4.3.tar.gz",
        "bab8c43a746266e68142f4926e69438ce551441aa88e54e78bb6410bf3ee7000",
    ),
    Resource(
        "htmldate",
        "1.10.0",
        "https://files.pythonhosted.org/packages/ad/1f/e7cf83e23d7b68105de8b874a8b36ba23b450d6f71388583e4ca3ce475ca/htmldate-1.10.0.tar.gz",
        "a38df10772ab5d7dbb11896e3f6a852a8491fb1b0965465bc174e23fc2baae58",
    ),
    Resource(
        "justext",
        "3.0.2",
        "https://files.pythonhosted.org/packages/49/f3/45890c1b314f0d04e19c1c83d534e611513150939a7cf039664d9ab1e649/justext-3.0.2.tar.gz",
        "13496a450c44c4cd5b5a75a5efcd9996066d2a189794ea99a49949685a0beb05",
    ),
    Resource(
        "lxml",
        "6.1.3",
        "https://files.pythonhosted.org/packages/23/ad/28ecd7cb894d172f3c9c80a075eeeb2017ac62e3632cee05a5f9493547eb/lxml-6.1.3.tar.gz",
        "45222d94ddd511536f3b2f7d9deae3b2339b4ce0f075f1ca25703b07cad9dd21",
    ),
    Resource(
        "lxml-html-clean",
        "0.4.5",
        "https://files.pythonhosted.org/packages/0a/63/195dfdde380a84df309e3bccf4384b034b745dba43426886f7ae623b4fba/lxml_html_clean-0.4.5.tar.gz",
        "e2a4c7d5beedd17cd7b484d848a0571e54baa239a4f9df5546e3acba7f990560",
    ),
    Resource(
        "protego",
        "0.7.0",
        "https://files.pythonhosted.org/packages/7a/d9/5026b9e75db1172f02441a84eaf42efb199b4cea14dda7651a620d1acd40/protego-0.7.0.tar.gz",
        "2c032d9736a1f4f0c4318f3558353ae34da5cd038f1a5e064ded7548df315e5a",
    ),
    Resource(
        "python-dateutil",
        "2.9.0.post0",
        "https://files.pythonhosted.org/packages/66/c0/0c8b6ad9f17a802ee498c46e004a0eb49bc148f2fd230864601a86dcf6db/python-dateutil-2.9.0.post0.tar.gz",
        "37dd54208da7e1cd875388217d5e00ebd4179249f90fb72437e91a35459a0ad3",
    ),
    Resource(
        "pytz",
        "2026.3.post1",
        "https://files.pythonhosted.org/packages/fb/48/fb042503b6ca6cd271261dc559fd6432f7d8c713153e9ec5c591af4dfc1c/pytz-2026.3.post1.tar.gz",
        "2211d3fcf9a797d3405cac96ac7f61d80e6a644f72a3309607282fe8a2010c5d",
    ),
    Resource(
        "regex",
        "2026.9.10",
        "https://files.pythonhosted.org/packages/b9/5c/f403115361de25809e8f785686ec7096e30fef73be9ae35aa51da4e80abb/regex-2026.9.10.tar.gz",
        "1e321e2c84f0e52c457f5ea5944f796d6e8e09cb99738ea98dcc1bfe402a128d",
    ),
    Resource(
        "six",
        "1.17.0",
        "https://files.pythonhosted.org/packages/94/e7/b2c673351809dca68a0e064b6af791aa332cf192da575fd474ed7d6f16a2/six-1.17.0.tar.gz",
        "ff70335d468e7eb6ec65b95b99d3a2836546063f63acc5171de367e834932a81",
    ),
    Resource(
        "tld",
        "0.13.2",
        "https://files.pythonhosted.org/packages/5c/5d/76b4383ac4e5b5e254e50c09807b3e13820bed6d6c11cd540264988d6802/tld-0.13.2.tar.gz",
        "d983fa92b9d717400742fca844e29d5e18271079c7bcfabf66d01b39b4a14345",
    ),
    Resource(
        "trafilatura",
        "2.2.0",
        "https://files.pythonhosted.org/packages/a3/96/737133a93e73e967f9c888e6cfb1f2c31b2083d27263edb19fd65a9aca02/trafilatura-2.2.0.tar.gz",
        "8c2cabb84066465228d03183fb698ce0b1245b81c58140b8ae0de57fddf3aae7",
    ),
    Resource(
        "tzlocal",
        "5.4.4",
        "https://files.pythonhosted.org/packages/81/5b/879b2f932adfa7a053c360d50bc896c977fa6426109185f7c12ebdd0cb9d/tzlocal-5.4.4.tar.gz",
        "8dbb8660838688a7b6ba4fed31d18dedf842afb4d47ca050d6d891c2c15f3be4",
    ),
    Resource(
        "urllib3",
        "2.8.0",
        "https://files.pythonhosted.org/packages/e3/05/b17359e1cefb4f909b5e40b1b90a496d987258916dbbf88e842c729f510e/urllib3-2.8.0.tar.gz",
        "63bf2ead4c879426ebf22ef2a781eeb4aa3b4ae798a0435506f8687fd5bb9b63",
    ),
)

RUN = (
    "click >=8.2",
    "cssselect >=1.2",
    "lxml >=5.3",
    "protego >=0.3",
    "trafilatura >=2.0",
)
"""The recipe's run requirements beside Python: pyproject's floors, in
conda's spelling. tomli is not among them: pyproject asks for it below Python
3.11 only, and no Python the recipe installs on is (``PYTHON_MIN``)."""

HOST = ("hatchling >=1.27", "pip")
"""What building the wheel needs beside Python: pyproject's build backend."""

LICENSE = ("MIT", "CC-BY-SA-3.0", "Unicode-3.0")
"""pyproject's ``license``, one SPDX identifier each."""

HOMEPAGE = "https://github.com/Gi0tto/sluicer"
DOCUMENTATION = "https://gi0tto.github.io/sluicer/"
SUMMARY = "Turn a web page into structured data with no model in the loop"

SOURCE_URL = (
    "https://files.pythonhosted.org/packages/source/s/sluicer/sluicer-{version}.tar.gz"
)
"""PyPI's address for an sdist by name, which redirects to where it is kept:
the formula's URL until the release's own address can be read from PyPI."""

_PAGE = """\
<html><head><title>Brake pads</title>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Product", "name": "Brake pads",
 "offers": {"@type": "Offer", "price": "19.99", "priceCurrency": "EUR"}}
</script></head><body></body></html>
"""
"""The page both files' tests extract: a price only JSON-LD declares."""


def formula(url: str, sha256: str) -> str:
    """The Homebrew formula, for homebrew-core."""
    pending = (
        [
            f"  # PLACEHOLDER: sluicer {VERSION} has no sdist yet. Run",
            "  # packaging/recipes.py again once it is on PyPI.",
        ]
        if sha256 == PLACEHOLDER
        else []
    )
    resources = []
    for resource in RESOURCES:
        resources += [
            f'  resource "{resource.name}" do',
            f'    url "{resource.url}"',
            f'    sha256 "{resource.sha256}"',
            "  end",
            "",
        ]
    licences = ", ".join(f'"{name}"' for name in LICENSE)
    page = "".join(f"      {line}\n" if line else "\n" for line in _PAGE.splitlines())
    lines = [
        "class Sluicer < Formula",
        "  include Language::Python::Virtualenv",
        "",
        f'  desc "{SUMMARY}"',
        f'  homepage "{HOMEPAGE}"',
        f'  url "{url}"',
        *pending,
        f'  sha256 "{sha256}"',
        f"  license all_of: [{licences}]",
        f'  head "{HOMEPAGE}.git", branch: "main"',
        "",
        f'  depends_on "{PYTHON}"',
        "",
        # lxml is built against the system's libxml2 and libxslt on macOS,
        # and Homebrew's on Linux, as every homebrew-core formula that vendors
        # lxml declares them.
        '  uses_from_macos "libxml2", since: :ventura',
        '  uses_from_macos "libxslt"',
        "",
        *resources,
        "  def install",
        f'    venv = virtualenv_create(libexec, "{PYTHON.replace("@", "")}")',
        "    venv.pip_install resources",
        "    venv.pip_install buildpath",
        "    # sluicer-mcp is the MCP server, which needs the mcp extra; this",
        "    # formula installs the base package, so only sluicer is linked.",
        '    bin.install_symlink libexec/"bin/sluicer"',
        '    generate_completions_from_executable(bin/"sluicer", '
        "shell_parameter_format: :click)",
        "  end",
        "",
        "  test do",
        '    assert_match version.to_s, shell_output("#{bin}/sluicer --version")',
        "",
        '    (testpath/"page.html").write <<~HTML',
        page.rstrip("\n"),
        "    HTML",
        '    output = JSON.parse(shell_output("#{bin}/sluicer extract '
        '#{testpath}/page.html"))',
        '    assert_equal "19.99", output["summary"]["price"]["value"]',
        '    assert_equal "jsonld", output["summary"]["price"]["source"]',
        "  end",
        "end",
    ]
    return "\n".join(lines) + "\n"


def recipe(sha256: str) -> str:
    """The conda-forge recipe, in the v1 format rattler-build reads."""
    pending = (
        [
            f"  # PLACEHOLDER: sluicer {VERSION} has no sdist yet. Run",
            "  # packaging/recipes.py again once it is on PyPI.",
        ]
        if sha256 == PLACEHOLDER
        else []
    )
    lines = [
        "# The v1 format, which conda-forge asks of every new recipe: staged-recipes'",
        "# README (https://github.com/conda-forge/staged-recipes, 'Recipe format",
        "# policy') and the pure-Python example",
        "# (https://conda-forge.org/docs/maintainer/example_recipes/pure-python/),",
        "# read on 2026-09-25. python_min is conda-forge's global pinning's (3.11",
        "# then). Written by packaging/recipes.py: edit that, not this.",
        "schema_version: 1",
        "",
        "context:",
        f'  version: "{VERSION}"',
        "",
        "package:",
        "  name: sluicer",
        "  version: ${{ version }}",
        "",
        "source:",
        "  url: https://pypi.org/packages/source/s/sluicer/"
        "sluicer-${{ version }}.tar.gz",
        *pending,
        f"  sha256: {sha256}",
        "",
        "build:",
        "  noarch: python",
        "  number: 0",
        "  script: ${{ PYTHON }} -m pip install . -vv",
        "  python:",
        "    entry_points:",
        "      - sluicer = sluicer.cli:main",
        "      - sluicer-mcp = sluicer.mcp_server:main",
        "",
        "requirements:",
        "  host:",
        "    - python ${{ python_min }}.*",
        *(f"    - {name}" for name in HOST),
        "  run:",
        "    - python >=${{ python_min }}",
        *(f"    - {name}" for name in RUN),
        "",
        "tests:",
        "  - python:",
        "      imports:",
        "        - sluicer",
        "        - sluicer.fetch",
        "      python_version:",
        "        - ${{ python_min }}.*",
        '        - "*"',
        "      pip_check: true",
        "  - files:",
        "      recipe:",
        "        - page.html",
        "    script:",
        "      - sluicer --version",
        "      - sluicer extract page.html > found.json",
        "      - python -c \"import json; found = json.load(open('found.json')); "
        "assert found['summary']['price']['value'] == '19.99', found\"",
        "",
        "about:",
        f"  homepage: {HOMEPAGE}",
        f"  summary: {SUMMARY}.",
        "  description: |",
        "    Sluicer reads the data a web page already declares -- JSON-LD,",
        "    microdata, RDFa, OpenGraph, Dublin Core, Twitter cards, HTML's meta",
        "    names -- merged into one answer that names where every value came",
        "    from, with no model in the loop. This package is the base install:",
        "    it fetches over plain HTTP and turns a page into markdown; the",
        "    browser and MCP extras are on PyPI.",
        f"  license: {' AND '.join(LICENSE)}",
        "  license_file:",
        "    - LICENSE",
        "    - NOTICE",
        "    - LICENSES/",
        f"  documentation: {DOCUMENTATION}",
        f"  repository: {HOMEPAGE}",
        "",
        "extra:",
        "  recipe-maintainers:",
        "    - Gi0tto",
    ]
    return "\n".join(lines) + "\n"


def page() -> str:
    """The page the recipe's test extracts, a file beside the recipe."""
    return _PAGE


def written(url: str, sha256: str) -> dict[Path, str]:
    """Every file this script writes, by where it goes."""
    return {
        FORMULA: formula(url, sha256),
        RECIPE: recipe(sha256),
        RECIPE.parent / "page.html": page(),
    }


def from_pypi() -> tuple[str, str] | None:
    """``VERSION``'s sdist address and checksum on PyPI, or None when PyPI
    has no such release."""
    address = f"https://pypi.org/pypi/sluicer/{VERSION}/json"
    try:
        with urllib.request.urlopen(address, timeout=30) as answer:
            release = json.load(answer)
    except urllib.error.HTTPError as refused:
        if refused.code == 404:
            return None
        raise
    for artefact in release["urls"]:
        if artefact["packagetype"] == "sdist":
            return artefact["url"], artefact["digests"]["sha256"]
    return None


def from_sdist(path: Path) -> tuple[str, str]:
    """The source address and checksum for a local sdist of ``VERSION``."""
    expected = f"sluicer-{VERSION}.tar.gz"
    if path.name != expected:
        raise SystemExit(f"{path} is not {expected}: VERSION says {VERSION}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return SOURCE_URL.format(version=VERSION), digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sdist", type=Path, help="checksum this local sdist")
    parser.add_argument(
        "--offline", action="store_true", help="write a placeholder checksum"
    )
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if a file differs; write none"
    )
    args = parser.parse_args(argv)
    if args.sdist is not None:
        url, sha256 = from_sdist(args.sdist)
    else:
        published = None if args.offline else from_pypi()
        url, sha256 = published or (SOURCE_URL.format(version=VERSION), PLACEHOLDER)
    stale = []
    for path, text in written(url, sha256).items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        stale.append(path)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    for path in stale:
        verb = "differs" if args.check else "written"
        print(f"{path.relative_to(ROOT)}: {verb}", file=sys.stderr)
    if sha256 == PLACEHOLDER:
        print(
            f"sluicer {VERSION} is not on PyPI: the checksum is a placeholder",
            file=sys.stderr,
        )
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
