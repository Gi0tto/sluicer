"""What Sluicer ships beside the wheel says what the wheel says.

The image, the plugins, the Claude Desktop bundle, the skill's zip, the
catalogue entries and the GitHub Action each state a version, a licence or the
tools, and each is built by a script under ``packaging/`` or a job in
``release.yml``. These tests hold every one of them to the package, and run the
scripts on something that should pass and on something that should not: a
check nobody has seen fail is a check nobody knows works.
"""

from __future__ import annotations

import importlib
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


# -- what the documentation tells agents: llms.txt and context7.json --------

MKDOCS = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")


def _setting(name: str) -> str:
    found = re.search(rf"^{name}: (.+)$", MKDOCS, re.MULTILINE)
    assert found, name
    return found[1]


def _hook():
    spec = importlib.util.spec_from_file_location(
        "docs_llms", ROOT / "scripts" / "docs_llms.py"
    )
    assert spec is not None and spec.loader is not None
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    return hook


def _llms_txt() -> tuple[list, str]:
    hook = _hook()
    entries = hook.nav_of(MKDOCS)
    text = hook.llms_txt(
        _setting("site_name"),
        _setting("site_description"),
        _setting("site_url"),
        entries,
        lambda path: (ROOT / "docs" / path).read_text(encoding="utf-8"),
    )
    return entries, text


def test_the_docs_build_writes_an_llms_txt():
    hooks = MKDOCS.split("\nhooks:\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert "  - scripts/docs_llms.py" in hooks


def test_the_docs_llms_txt_keeps_to_llmstxt_org_s_format():
    """Read by the reader `sluicer audit` holds a site's llms.txt to."""
    from sluicer.audit.llmstxt import read_llms_txt
    from sluicer.audit.report import SiteFile

    entries, text = _llms_txt()
    url = _setting("site_url") + "llms.txt"
    read = read_llms_txt(SiteFile(url=url, status=200, text=text))
    assert [f for f in read.findings if f.severity != "info"] == []
    assert read.name == "Sluicer"
    assert read.summary == _setting("site_description")
    assert read.links == len(entries)
    assert len(read.sections) == len({section for section, _, _ in entries})


def test_the_docs_llms_txt_links_every_page_with_its_first_paragraph():
    entries, text = _llms_txt()
    pages = {
        path.relative_to(ROOT / "docs").as_posix()
        for path in (ROOT / "docs").rglob("*.md")
    }
    assert {path for _, _, path in entries} == pages, "a page outside the nav"
    base = _setting("site_url")
    for _section, title, path in entries:
        assert f"- [{title}]({base}{path})" in text, path
    agents = next(line for line in text.splitlines() if "agents.md)" in line)
    assert agents.endswith(
        ": Sluicer's MCP server is one command, and every client "
        "that speaks MCP can start it."
    )


def test_a_page_s_note_is_its_opening_paragraph_or_nothing():
    hook = _hook()
    page = "# Title\n\n<p>\n  A badge line.\n</p>\n\nThe [first](x.md) one:\ngoes on.\n"
    assert hook.summary_of(page) == "The first one: goes on."
    assert hook.summary_of("# FAQ\n\n## A question?\n\nIts answer.\n") == ""
    assert hook.summary_of("# Title\n\n```\ncode\n```\n\nThen prose:\n") == (
        "Then prose."
    )


def test_the_docs_nav_reader_refuses_a_line_it_does_not_know():
    hook = _hook()
    with pytest.raises(ValueError, match="Blog"):
        hook.nav_of("nav:\n  - Home: index.md\n  - Blog: https://example.com/\n")


CONTEXT7_FIELDS = {
    "$schema",
    "projectTitle",
    "description",
    "branch",
    "folders",
    "excludeFolders",
    "excludeFiles",
    "rules",
    "disallow",
    "redirect",
    "previousVersions",
    "url",
    "public_key",
}
"""The fields https://context7.com/schema/context7.json allows, read on
2026-09-25: the schema is closed."""


def test_context7_indexes_the_docs_and_says_what_the_package_says():
    config = _json(ROOT / "context7.json")
    assert set(config) <= CONTEXT7_FIELDS, set(config) - CONTEXT7_FIELDS
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    described = re.search(r'^description = "(.+)"$', pyproject, re.MULTILINE)
    assert described and config["description"] == described[1]
    assert 10 <= len(config["description"]) <= 200
    for folder in config["folders"] + config.get("excludeFolders", []):
        assert (ROOT / folder).is_dir(), folder
    for name in config.get("excludeFiles", []):
        assert (ROOT / "docs" / name).is_file(), name


def test_context7_s_rules_name_only_what_exists():
    """A rule an agent reads as fact, so each command, extra and name it
    gives is one Sluicer has."""
    from click.testing import CliRunner

    from sluicer.cli import main

    rules = _json(ROOT / "context7.json")["rules"]
    assert 0 < len(rules) <= 50 and all(0 < len(rule) <= 255 for rule in rules)
    text = " ".join(rules)
    commands = CliRunner().invoke(main, ["--help"]).output
    for command, options in re.findall(r"`sluicer ([a-z]+)((?: --[a-z-]+)*)", text):
        assert re.search(rf"^  {command} ", commands, re.MULTILINE), command
        told = CliRunner().invoke(main, [command, "--help"]).output
        for option in options.split():
            assert re.search(rf"^  {option}\b", told, re.MULTILINE), option
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for extra in re.findall(r"sluicer\[([a-z]+)\]", text):
        assert re.search(rf"^{extra} = \[", pyproject, re.MULTILINE), extra
    for dotted in re.findall(r"`(sluicer(?:\.[A-Za-z_]+)+)", text):
        module, _, name = dotted.rpartition(".")
        assert hasattr(importlib.import_module(module), name), dotted
    assert re.findall(r"`sluicer ([a-z]+)", text) and re.findall(r"sluicer\.", text)


# -- the GitHub Action -------------------------------------------------------

ACTION = ROOT / "action.yml"
CLEAN = ROOT / "examples" / "site" / "article.html"
"""No error, two warnings: the made-up site's article."""
BROKEN = ROOT / "examples" / "brake-pads.html"
"""Four errors: required properties its Product lacks."""


def _audit_action(tmp_path, **inputs):
    env = {
        "PATH": str(Path(sys.executable).parent),
        "SYSTEMROOT": "",
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "RUNNER_TEMP": str(tmp_path),
        "FAIL_ON": "error",
        "SITE": "false",
        **{key.upper(): value for key, value in inputs.items()},
    }
    done = subprocess.run(
        [sys.executable, str(PACKAGING / "audit_action.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=ROOT,
    )
    output, summary = tmp_path / "output", tmp_path / "summary.md"
    outputs = dict(
        line.split("=", 1)
        for line in (
            output.read_text(encoding="utf-8") if output.exists() else ""
        ).splitlines()
    )
    return (
        done,
        outputs,
        summary.read_text(encoding="utf-8") if summary.exists() else "",
    )


def test_the_action_passes_a_page_with_no_error(tmp_path):
    done, outputs, summary = _audit_action(tmp_path, urls=str(CLEAN))
    assert done.returncode == 0, done.stdout + done.stderr
    assert outputs["errors"] == "0" and outputs["warnings"] == "2"
    assert outputs["pages"] == "1" and outputs["unreadable"] == "0"
    assert "examples/site/article.html" in summary
    [line] = Path(outputs["report"]).read_text(encoding="utf-8").splitlines()
    assert json.loads(line)["exit"] == 0


def test_the_action_fails_on_a_page_that_breaks_a_rule_and_says_where(tmp_path):
    done, outputs, summary = _audit_action(
        tmp_path, urls=f"{CLEAN}\n  {BROKEN}\n\n# a comment\n"
    )
    assert done.returncode == 1
    assert outputs["errors"] == "4" and outputs["pages"] == "2"
    annotations = [
        line for line in done.stdout.splitlines() if line.startswith("::error")
    ]
    assert len(annotations) == 4
    assert all("brake-pads.html" in line for line in annotations)
    # Each error is linked to the documentation that states the rule.
    assert summary.count("https://developers.google.com/") >= 4


def test_the_action_reports_without_failing_when_told(tmp_path):
    done, outputs, _summary = _audit_action(tmp_path, urls=str(BROKEN), fail_on="never")
    assert done.returncode == 0 and outputs["errors"] == "4"


def test_the_action_fails_on_warnings_when_told(tmp_path):
    done, _outputs, _summary = _audit_action(
        tmp_path, urls=str(CLEAN), fail_on="warning"
    )
    assert done.returncode == 1


def test_the_action_fails_on_a_page_it_cannot_read(tmp_path):
    done, outputs, summary = _audit_action(tmp_path, urls=str(tmp_path / "gone.html"))
    assert done.returncode == 1
    assert outputs["unreadable"] == "1" and "could not be read" in summary


def test_the_action_refuses_an_input_it_does_not_know(tmp_path):
    done, _outputs, _summary = _audit_action(tmp_path, urls=str(CLEAN), fail_on="often")
    assert done.returncode == 2 and "fail-on" in done.stderr


def test_the_action_installs_this_version_and_keeps_inputs_out_of_its_shell():
    """An input written into a run: block is code the caller's workflow
    injects (GitHub's security hardening guide); every one goes through env."""
    action = ACTION.read_text(encoding="utf-8")
    assert "using: composite" in action
    [default] = re.findall(
        r"^  version:\n(?:    .+\n)*?    default: \"(.+)\"$", action, re.M
    )
    assert default == sluicer.__version__
    run = action.split("\n      run: ", 1)[1]
    assert "${{" not in run, "an expression inside the script"
    for name in ("urls", "fail-on", "site", "version", "package"):
        assert f"${{{{ inputs.{name} }}}}" in action, name
    assert "packaging/audit_action.py" in run


def test_a_workflow_runs_the_action_on_pages_it_serves_itself():
    workflow = (WORKFLOWS / "github-action.yml").read_text(encoding="utf-8")
    assert "python3 -m http.server" in workflow
    assert workflow.count("uses: ./") >= 3
    assert "steps.broken.outcome" in workflow
