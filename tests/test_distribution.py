"""What Sluicer ships beside the wheel says what the wheel says.

The image, the plugins, the Claude Desktop bundle, the skill's zip, the
catalogue entries and the GitHub Action each state a version, a licence or the
tools, and each is built by a script under ``packaging/`` or a job in
``release.yml``. These tests hold every one of them to the package, and run the
scripts on something that should pass and on something that should not: a
check nobody has seen fail is a check nobody knows works.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import textwrap
from importlib import metadata
from pathlib import Path

import pytest

import sluicer

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
WORKFLOWS = ROOT / ".github" / "workflows"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, PACKAGING / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _job(workflow: str, job: str) -> str:
    """One job's text in a workflow: from its key to the next job's."""
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    start = re.search(rf"^  {re.escape(job)}:\n", text, re.MULTILINE)
    assert start, f"{workflow} has no job {job}"
    end = re.search(r"^  [\w-]+:\n", text[start.end() :], re.MULTILINE)
    return text[start.start() : start.end() + end.start() if end else len(text)]


# -- the image ---------------------------------------------------------------


def test_the_image_states_the_version_it_is_built_from():
    """The Dockerfile's label said 0.7.0 when the package said 0.7.1: its
    build stops when the wheel disagrees, so the default has to agree too."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    [stated] = re.findall(r"^ARG SLUICER_VERSION=(\S+)$", dockerfile, re.MULTILINE)
    assert stated == sluicer.__version__


def test_the_image_is_built_with_every_licence_file_the_wheel_names():
    """0.7.0's image copied LICENSE alone, so its wheel was built without
    NOTICE and LICENSES/, and shipped schema.org's and CLDR's data with
    neither their licences nor the notice saying which files they cover."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    listed = re.search(r"^license-files = \[(.+)\]$", pyproject, re.MULTILINE)
    assert listed
    named = {entry.strip().strip('"').split("/")[0] for entry in listed[1].split(",")}
    assert named == {"LICENSE", "NOTICE", "LICENSES"}
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    wheel_stage = dockerfile.split("FROM ", 2)[1]
    for name in named:
        assert f"!{name}" in ignore or f"!{name}/" in ignore, name
        assert re.search(rf"^COPY .*\b{name}\b", wheel_stage, re.MULTILINE), name
        # And where a person looking at the image finds them.
        assert re.search(
            rf"^COPY .*\b{name}\b.* /usr/share/licenses/sluicer/", dockerfile, re.M
        ), name


def test_the_image_writes_the_licences_of_everything_it_installs():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "!packaging/third_party.py" in (ROOT / ".dockerignore").read_text(
        encoding="utf-8"
    )
    assert re.search(
        r"python /tmp/third_party.py /usr/share/licenses/sluicer/THIRD-PARTY\.txt",
        dockerfile,
    )


def test_the_licence_inventory_holds_the_text_each_distribution_installed():
    third_party = _script("third_party")
    lxml = metadata.distribution("lxml")
    text, missing = third_party.inventory([lxml, metadata.distribution("click")])
    assert missing == []
    assert f"lxml {lxml.version}" in text and "click " in text
    # The text itself, not the name of the licence: libxml2's is in lxml's.
    [licences] = [p for p in lxml.files or [] if p.name == "LICENSES.txt"]
    body = Path(str(lxml.locate_file(licences))).read_text(encoding="utf-8")
    assert body.strip()[:200] in text


def test_the_licence_inventory_refuses_a_distribution_with_no_licence_file(tmp_path):
    info = tmp_path / "bare-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.4\nName: bare\nVersion: 1.0\nLicense-Expression: MIT\n",
        encoding="utf-8",
    )
    (info / "RECORD").write_text(
        "bare-1.0.dist-info/METADATA,,\nbare-1.0.dist-info/RECORD,,\n",
        encoding="utf-8",
    )
    [bare] = metadata.distributions(path=[str(tmp_path)])
    _text, missing = _script("third_party").inventory([bare])
    assert missing == ["bare"]
    done = subprocess.run(
        # -S leaves site-packages off the path, so the fake is all it sees.
        [
            sys.executable,
            "-S",
            str(PACKAGING / "third_party.py"),
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PYTHONPATH": str(tmp_path), "PATH": ""},
    )
    assert done.returncode == 1 and "bare" in done.stderr
    assert not (tmp_path / "out").exists()


# -- the smoke check the release runs on the image and the bundle -----------

FAKE_SERVER = textwrap.dedent(
    """
    import json, sys
    for line in sys.stdin:
        message = json.loads(line)
        if message.get("method") == "initialize":
            result = {"serverInfo": {"name": "fake", "version": "1"},
                      "capabilities": {}, "protocolVersion": "2025-06-18"}
        elif message.get("method") == "tools/list":
            result = {"tools": [{"name": "extract_declared",
                                 "annotations": {"readOnlyHint": True}}]}
        else:
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}),
              flush=True)
    """
)


def test_the_smoke_check_passes_on_sluicer_s_own_server():
    pytest.importorskip("mcp")
    listed = _script("mcp_smoke").check([sys.executable, "-m", "sluicer", "mcp"])
    assert len(listed) == 10


def test_the_smoke_check_fails_on_a_server_that_lists_other_tools(tmp_path):
    server = tmp_path / "server.py"
    server.write_text(FAKE_SERVER, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(PACKAGING / "mcp_smoke.py"), "--", sys.executable, server],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert done.returncode != 0
    assert "listed ['extract_declared']" in done.stderr


# -- the workflows -----------------------------------------------------------


def test_every_action_the_project_uses_is_pinned_to_a_commit():
    """A tag can be moved to other code; a commit cannot. The workflows pin
    every action by its commit, with the tag it had in a comment, and the
    GitHub Action this repository offers does the same."""
    files = [*WORKFLOWS.glob("*.yml"), ROOT / "action.yml"]
    seen = 0
    for path in files:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            used = re.match(r"^\s*(?:- )?uses: (\S+)(.*)$", line)
            if not used or used[1].startswith("./"):
                continue
            seen += 1
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", used[1]), (
                f"{path.name}: {line.strip()}"
            )
            assert re.fullmatch(r" # v\d+(\.\d+)*", used[2]), f"{path.name}: {line}"
    assert seen > 10


def test_the_release_tests_each_image_before_it_pushes_it():
    image = _job("release.yml", "image")
    assert "needs: build" in image, "the suite passes before an image is built"
    smoke = image.index("packaging/mcp_smoke.py -- docker run -i --rm")
    served = image.index("sluicer serve --host 0.0.0.0")
    licences = image.index("THIRD-PARTY.txt")
    pushed = image.index("docker push")
    assert max(smoke, served, licences) < pushed
    # Only the push is gated, so every tag builds and tests the image.
    assert re.search(r"if: .*vars\.PUBLISH_TO_GHCR == 'true'", image)
    assert "packages: write" in image
    manifest = _job("release.yml", "image-index")
    assert "needs: image" in manifest
    assert "docker buildx imagetools create" in manifest
