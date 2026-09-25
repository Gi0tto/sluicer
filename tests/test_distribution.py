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
import json
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


# -- Agent Plugins: plugin.json and mcp.json at the root ---------------------

AGENT_PLUGINS = "https://agent-plugins.org/schemas/1.0.0/"
"""The published release. 1.1.0 is a working draft, and a client that does
not know the version a manifest names must refuse the plugin (§5.2): VS Code,
Cursor and Codex document 1.0.0."""


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_agent_plugin_manifest_keeps_to_the_closed_schema():
    manifest = _json(ROOT / "plugin.json")
    allowed = {
        "$schema",
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "extensions",
    }
    assert set(manifest) <= allowed, set(manifest) - allowed
    assert manifest["$schema"] == AGENT_PLUGINS + "plugin.schema.json"
    assert re.fullmatch(
        r"(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", manifest["name"]
    )
    assert set(manifest["author"]) <= {"name", "email", "url"}
    assert all(isinstance(manifest[key], str) for key in ("repository", "license"))


def test_the_agent_plugin_says_what_the_claude_plugin_says():
    """Two manifests for one plugin: the root one for the clients that load
    the standard, .claude-plugin/ for Claude Code. They name one version,
    licence and description, and the description counts the tools the server
    registers, as a test above holds the Claude plugin's to."""
    root = _json(ROOT / "plugin.json")
    claude = _json(ROOT / ".claude-plugin" / "plugin.json")
    assert root["version"] == claude["version"] == sluicer.__version__
    for key in ("name", "description", "license", "keywords", "repository"):
        assert root[key] == claude[key], key
    assert root["author"] == claude["author"]


def test_the_agent_plugin_starts_the_server_the_registry_lists():
    """mcp.json's command is server.json's, at the same version: a bare token
    with no ${PLUGIN_ROOT}, which Cursor does not expand, and nothing a client
    of the standard would refuse."""
    config = _json(ROOT / "mcp.json")
    assert set(config) == {"$schema", "mcpServers"}
    # §10.1: mcp.json names the version plugin.json names, or MCP is off.
    assert config["$schema"] == AGENT_PLUGINS + "mcp.schema.json"
    [(name, server)] = config["mcpServers"].items()
    assert name == "sluicer"
    assert set(server) <= {"type", "command", "args", "env", "cwd"}
    assert server["type"] == "stdio" and server["command"] == "uvx"
    assert "${" not in json.dumps(server)
    [package] = _json(ROOT / "server.json")["packages"]
    # uvx's arguments, the package, then the package's: `uvx --with
    # "sluicer[mcp]==VERSION" sluicer mcp`.
    registry = [
        part for a in package["runtimeArguments"] for part in (a["name"], a["value"])
    ]
    registry += [
        package["identifier"],
        *(a["value"] for a in package["packageArguments"]),
    ]
    assert server["args"] == registry
    assert server["args"][1] == f"sluicer[mcp]=={sluicer.__version__}"


# -- the Claude Desktop bundle and the skill's zip ---------------------------

MCPB = PACKAGING / "mcpb"


def _registered_tools() -> list[str]:
    import asyncio

    pytest.importorskip("mcp")
    from sluicer.mcp_server import build_server

    return sorted(tool.name for tool in asyncio.run(build_server().list_tools()))


def test_the_bundle_installs_the_package_at_its_own_version():
    manifest = _json(MCPB / "manifest.json")
    project = (MCPB / "pyproject.toml").read_text(encoding="utf-8")
    version = sluicer.__version__
    assert manifest["manifest_version"] == "0.4" and manifest["server"]["type"] == "uv"
    assert manifest["version"] == version
    assert re.findall(r"^version = \"(.+)\"$", project, re.MULTILINE) == [version]
    assert re.findall(r"^dependencies = \[(.+)\]$", project, re.MULTILINE) == [
        f'"sluicer[mcp]=={version}"'
    ]
    # No [build-system]: uv installs its dependency and never builds it.
    assert "[build-system]" not in project
    assert manifest["license"] == _json(ROOT / "plugin.json")["license"]


def test_the_bundle_lists_the_tools_the_server_registers():
    """Claude Desktop shows the manifest's tools before the server starts,
    and the release's smoke check expects exactly these from it."""
    listed = [tool["name"] for tool in _json(MCPB / "manifest.json")["tools"]]
    assert sorted(listed) == _registered_tools()


def test_the_bundle_s_settings_are_the_variables_the_server_reads():
    from sluicer import mcp_server

    manifest = _json(MCPB / "manifest.json")
    env = manifest["server"]["mcp_config"]["env"]
    assert env == {
        mcp_server.ALLOW_PRIVATE_ENV: "${user_config.allow_private}",
        mcp_server.TOOLS_ENV: "${user_config.tools}",
    }
    settings = manifest["user_config"]
    # A boolean arrives as "true" or "false" (the mcpb host's substitution);
    # the server reads "true" as on, and anything else as off.
    assert settings["allow_private"]["type"] == "boolean"
    assert settings["allow_private"]["default"] is False
    # Empty is all ten: the server ignores an empty SLUICER_MCP_TOOLS.
    assert settings["tools"]["default"] == ""


def test_the_release_assets_are_staged_from_the_repository(tmp_path):
    build = _script("build_assets")
    build.main([str(tmp_path)])
    version = sluicer.__version__
    stage = tmp_path / "mcpb"
    assert sorted(p.relative_to(stage).as_posix() for p in stage.rglob("*")) == [
        "LICENSE",
        "LICENSES",
        "LICENSES/CC-BY-SA-3.0.txt",
        "LICENSES/Unicode-3.0.txt",
        "NOTICE",
        "icon.png",
        "manifest.json",
        "pyproject.toml",
        "server.py",
    ]
    # The manifest's icon is in the bundle, the validator's one complaint
    # about the directory it was committed in.
    assert (stage / _json(stage / "manifest.json")["icon"]).read_bytes()[:4] == (
        b"\x89PNG"
    )
    import zipfile

    skill = tmp_path / f"sluicer-skill-{version}.zip"
    with zipfile.ZipFile(skill) as bundle:
        names = bundle.namelist()
        assert names == sorted(names) and "sluicer/SKILL.md" in names
        assert all(name.startswith("sluicer/") for name in names)
        assert (
            bundle.read("sluicer/SKILL.md")
            == (ROOT / "skills" / "sluicer" / "SKILL.md").read_bytes()
        )
    # The same tree gives the same bytes: a build's clock never shows.
    again = tmp_path / "again"
    build.main([str(again)])
    assert (again / skill.name).read_bytes() == skill.read_bytes()


def test_the_release_assets_stop_on_a_version_that_disagrees(tmp_path, monkeypatch):
    build = _script("build_assets")
    wrong = tmp_path / "mcpb"
    wrong.mkdir()
    for name in ("manifest.json", "pyproject.toml", "server.py"):
        (wrong / name).write_bytes((MCPB / name).read_bytes())
    manifest = _json(wrong / "manifest.json")
    manifest["version"] = "0.0.1"
    (wrong / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(build, "MCPB", wrong)
    with pytest.raises(SystemExit, match=re.escape("0.0.1")):
        build.main([str(tmp_path / "out")])


def test_the_release_builds_the_bundle_and_tests_it_before_attaching_it():
    assets = _job("release.yml", "assets")
    steps = [
        "packaging/build_assets.py",
        "@anthropic-ai/mcpb@2.1.2 validate",
        "@anthropic-ai/mcpb@2.1.2 pack",
        "packaging/mcp_smoke.py -- uv run --find-links",
    ]
    places = [assets.index(step) for step in steps]
    assert places == sorted(places)
    attach = _job("release.yml", "attach")
    assert "needs: [assets, publish]" in attach, "the bundle installs from PyPI"
    assert "contents: write" in attach
    assert re.search(r"if: .*vars\.PUBLISH_RELEASE_ASSETS == 'true'", attach)
    for asset in (".mcpb", "sluicer-skill-"):
        assert asset in attach, asset
