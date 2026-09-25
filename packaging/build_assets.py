"""Stage what a release carries beside the wheel: the skill, the bundle, the entry.

    python3 packaging/build_assets.py OUT [--commit SHA]

writes, for the version in pyproject.toml:

- ``OUT/sluicer-skill-VERSION.zip``: ``skills/sluicer`` as a folder named
  ``sluicer`` at the top of the zip, which is the shape claude.ai's skill upload
  takes and what unzipping into ``~/.claude/skills/`` or ``~/.agents/skills/``
  needs. Built with fixed timestamps and in a fixed order, so the same tree
  always gives the same bytes.
- ``OUT/mcpb/``: the directory ``mcpb pack`` turns into
  ``sluicer-VERSION.mcpb`` -- the manifest, its pyproject.toml and server.py
  from ``packaging/mcpb/``, the icon, and the licence files. The bundle holds no
  Python and no dependencies: its server type is ``uv``, so the host installs
  ``sluicer[mcp]`` at this version from PyPI (MANIFEST.md, "UV Runtime").
- with ``--commit``, ``OUT/docker-mcp-registry/servers/sluicer/server.yaml``:
  the entry a pull request to docker/mcp-registry adds, pinned to that commit,
  which is how the registry says which source Docker builds and signs. The
  committed entry holds a placeholder, since a commit cannot name itself.

It stops if a file that states the version disagrees with pyproject.toml, so a
release never ships a bundle that installs another version. Standard library
only: the release job runs it before anything is installed.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCPB = ROOT / "packaging" / "mcpb"
SKILL = ROOT / "skills" / "sluicer"
# 1980-01-01, the earliest time a zip can hold: a build's clock never shows.
EPOCH = (1980, 1, 1, 0, 0, 0)


def version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    found = re.search(r'^version = "(.+)"$', pyproject, re.MULTILINE)
    if not found:
        raise SystemExit("pyproject.toml states no version")
    return found[1]


def _agrees(where: str, stated: str, wanted: str) -> None:
    # Not an assert: `python -O` would build the wrong bundle without a word.
    if stated != wanted:
        raise SystemExit(f"{where} says {stated}, pyproject.toml says {wanted}")


def skill_zip(out: Path, stated: str) -> Path:
    target = out / f"sluicer-skill-{stated}.zip"
    files = sorted(path for path in SKILL.rglob("*") if path.is_file())
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            name = f"{SKILL.name}/{path.relative_to(SKILL).as_posix()}"
            entry = zipfile.ZipInfo(name, date_time=EPOCH)
            entry.external_attr = 0o644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(entry, path.read_bytes())
    return target


def mcpb_stage(out: Path, stated: str) -> Path:
    manifest = json.loads((MCPB / "manifest.json").read_text(encoding="utf-8"))
    project = (MCPB / "pyproject.toml").read_text(encoding="utf-8")
    _agrees("the bundle's manifest.json", manifest["version"], stated)
    for pattern in (
        r'^version = "(.+)"$',
        r'^dependencies = \["sluicer\[mcp\]==(.+)"\]$',
    ):
        found = re.search(pattern, project, re.MULTILINE)
        _agrees("the bundle's pyproject.toml", found[1] if found else "nothing", stated)
    stage = out / "mcpb"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for name in ("manifest.json", "pyproject.toml", "server.py"):
        shutil.copy2(MCPB / name, stage / name)
    shutil.copy2(ROOT / "docs" / "assets" / "mark-512.png", stage / "icon.png")
    for name in ("LICENSE", "NOTICE"):
        shutil.copy2(ROOT / name, stage / name)
    shutil.copytree(ROOT / "LICENSES", stage / "LICENSES")
    return stage


CATALOG = ROOT / "packaging" / "docker-mcp-registry" / "servers" / "sluicer"
PLACEHOLDER = (
    "  commit: TAGGED_COMMIT # build_assets.py --commit writes the tagged one\n"
)


def catalog_entry(out: Path, commit: str) -> Path:
    # The registry's own check: a 40-character lowercase SHA-1, not a tag.
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SystemExit(f"--commit takes the 40-character commit, not {commit!r}")
    entry = (CATALOG / "server.yaml").read_text(encoding="utf-8")
    if entry.count(PLACEHOLDER) != 1:
        raise SystemExit("the catalog entry has no commit line to fill")
    target = out / "docker-mcp-registry" / "servers" / "sluicer" / "server.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        entry.replace(PLACEHOLDER, f"  commit: {commit}\n"), encoding="utf-8"
    )
    return target


def main(argv: list[str]) -> None:
    commit = None
    if len(argv) == 3 and argv[1] == "--commit":
        commit = argv.pop()
        argv.pop()
    if len(argv) != 1:
        raise SystemExit(__doc__)
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    stated = version()
    print(skill_zip(out, stated))
    print(mcpb_stage(out, stated))
    if commit is not None:
        print(catalog_entry(out, commit))


if __name__ == "__main__":
    main(sys.argv[1:])
