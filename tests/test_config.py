"""The defaults a ``sluicer.toml`` gives the command line, and their order.

The command line wins over the environment, the environment over the file,
and the file over the built-in defaults. Each test writes a file in a
directory of its own, runs a command there with the fetch, the crawl or the
server replaced by a recorder, and reads what the command asked for.
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest
from click.testing import CliRunner

from sluicer import cli, config
from sluicer.crawl import Crawl
from sluicer.crawl.schedule import DEFAULT_DELAY_SECONDS
from sluicer.fetch.http_rung import PROXY_ENV
from sluicer.fetch.result import Fetched

URL = "https://example.com/p"


@pytest.fixture
def here(tmp_path, monkeypatch):
    """A directory of its own to run in, with no file and no variable set."""
    monkeypatch.chdir(tmp_path)
    # Set, then taken away: whatever a command writes into them is undone
    # when the test ends, as --proxy writes SLUICER_PROXY.
    for name in (config.CONFIG_ENV, PROXY_ENV, "SLUICER_MCP_TOOLS"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    return tmp_path


@pytest.fixture
def fetched(monkeypatch):
    """What ``sluicer fetch`` asked of the ladder, the proxy included."""
    asked: list[dict] = []

    def recorder(url, **kwargs):
        asked.append({**kwargs, "url": url, "proxy": os.environ.get(PROXY_ENV)})
        return Fetched(url=url, html="<title>t</title>", status=200, rung="http")

    monkeypatch.setattr("sluicer.cli.source.fetch_url", recorder)
    return asked


@pytest.fixture
def crawled(monkeypatch):
    """What ``sluicer crawl`` and ``batch`` asked of the crawler."""
    asked: list[dict] = []

    def recorder(*args, **kwargs):
        asked.append(kwargs)
        return Crawl(lambda crawl: iter(()))

    monkeypatch.setattr("sluicer.cli.sites.crawl_site", recorder)
    monkeypatch.setattr("sluicer.cli.sites.extract_many", recorder)
    return asked


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run(*args: str, env: dict[str, str] | None = None):
    return CliRunner().invoke(cli.main, list(args), env=env, catch_exceptions=False)


def test_a_file_gives_the_defaults_a_command_takes(here, fetched):
    _write(
        here / "sluicer.toml",
        'proxy = "http://127.0.0.1:8080"\n'
        'header = ["Accept-Language: de-DE", "X-Team: data"]\n'
        'cookie = ["session=abc"]\n'
        "no-robots = true\n"
        "json = true\n",
    )

    result = _run("fetch", URL)

    assert result.exit_code == 0, result.output
    (asked,) = fetched
    assert asked["proxy"] == "http://127.0.0.1:8080"
    assert asked["headers"] == {"Accept-Language": "de-DE", "X-Team": "data"}
    assert asked["cookies"] == {"session": "abc"}
    assert asked["obey_robots"] is False
    assert json.loads(result.stdout)["url"] == URL


def test_the_command_line_wins_over_the_file(here, fetched):
    _write(
        here / "sluicer.toml",
        'proxy = "http://127.0.0.1:8080"\n'
        'header = ["X-Team: data"]\n'
        "no-robots = true\n"
        "json = true\n",
    )

    result = _run(
        "fetch",
        URL,
        "--proxy",
        "socks5h://127.0.0.1:1080",
        "-H",
        "X-Other: 1",
        "--robots",
        "--no-json",
    )

    assert result.exit_code == 0, result.output
    (asked,) = fetched
    assert asked["proxy"] == "socks5h://127.0.0.1:1080"
    # A list the command line gives replaces the file's; it does not add to it.
    assert asked["headers"] == {"X-Other": "1"}
    assert asked["obey_robots"] is True
    assert result.stdout.strip() == "<title>t</title>"


def test_the_environment_wins_over_the_file_and_loses_to_the_command_line(
    here, fetched
):
    _write(here / "sluicer.toml", 'proxy = "http://file:8080"\n')

    _run("fetch", URL, env={PROXY_ENV: "http://environment:8080"})
    _run(
        "fetch",
        URL,
        "--proxy",
        "http://line:8080",
        env={PROXY_ENV: "http://environment:8080"},
    )

    assert [asked["proxy"] for asked in fetched] == [
        "http://environment:8080",
        "http://line:8080",
    ]


def test_the_mcp_server_s_tools_follow_the_same_order(here, monkeypatch):
    import sluicer.mcp_server

    started: list[object] = []
    monkeypatch.setattr(
        sluicer.mcp_server, "main", lambda tools=None: started.append(tools)
    )
    _write(here / "sluicer.toml", '[mcp]\ntools = "page_markdown"\n')

    _run("mcp")
    _run("mcp", env={"SLUICER_MCP_TOOLS": "fetch_page"})
    _run("mcp", "--tools", "audit_page", env={"SLUICER_MCP_TOOLS": "fetch_page"})

    # None: the server reads SLUICER_MCP_TOOLS itself.
    assert started == [["page_markdown"], None, ["audit_page"]]


def test_without_a_file_the_built_in_defaults_hold(here, crawled, fetched):
    _run("crawl", URL)
    _run("fetch", URL)

    assert crawled[0]["min_delay"] == DEFAULT_DELAY_SECONDS
    assert fetched[0]["obey_robots"] is True and fetched[0]["proxy"] is None


def test_a_command_s_table_wins_over_the_top_level(here, crawled):
    _write(here / "sluicer.toml", "delay = 3.0\n\n[crawl]\ndelay = 5\nmax-pages = 7\n")
    urls = _write(here / "urls.txt", f"{URL}\n")

    _run("crawl", URL)
    _run("batch", str(urls))

    assert crawled[0]["min_delay"] == 5 and crawled[1]["min_delay"] == 3.0


def test_a_crawl_s_limits_come_from_its_table(here, monkeypatch):
    seen: list[tuple] = []
    monkeypatch.setattr(
        "sluicer.cli.sites.crawl_site",
        lambda *args, **kwargs: seen.append(args) or Crawl(lambda crawl: iter(())),
    )
    _write(here / "sluicer.toml", "[crawl]\nmax-pages = 7\nmax-depth = 1\n")

    _run("crawl", URL)

    assert seen[0][1:3] == (7, 1)


def test_pyproject_s_tool_table_is_read(here, crawled):
    _write(
        here / "pyproject.toml", '[project]\nname = "x"\n\n[tool.sluicer]\ndelay = 2\n'
    )

    _run("crawl", URL)

    assert crawled[0]["min_delay"] == 2


def test_the_file_is_found_from_a_directory_below_it(here, crawled, monkeypatch):
    _write(here / "sluicer.toml", "delay = 4\n")
    # A pyproject.toml with no table of ours on the way up is passed by.
    _write(here / "a" / "pyproject.toml", '[project]\nname = "x"\n')
    below = here / "a" / "b"
    below.mkdir(parents=True)
    monkeypatch.chdir(below)

    _run("crawl", URL)

    assert crawled[0]["min_delay"] == 4


def test_two_files_in_one_directory_are_refused(here, crawled):
    _write(here / "sluicer.toml", "delay = 4\n")
    _write(here / "pyproject.toml", "[tool.sluicer]\ndelay = 2\n")

    result = _run("crawl", URL)

    assert result.exit_code == 2 and crawled == []
    assert "sluicer.toml" in result.stderr and "pyproject.toml" in result.stderr


def test_the_variable_and_the_option_name_a_file(here, crawled, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    by_variable = _write(elsewhere / "one.toml", "delay = 6\n")
    by_option = _write(elsewhere / "two.toml", "delay = 7\n")
    _write(here / "sluicer.toml", "delay = 4\n")

    _run("crawl", URL, env={config.CONFIG_ENV: str(by_variable)})
    _run(
        "--config",
        str(by_option),
        "crawl",
        URL,
        env={config.CONFIG_ENV: str(by_variable)},
    )

    assert [asked["min_delay"] for asked in crawled] == [6, 7]


def test_no_config_and_an_empty_variable_read_no_file(here, crawled):
    _write(here / "sluicer.toml", "delay = 4\n")

    _run("--no-config", "crawl", URL)
    _run("crawl", URL, env={config.CONFIG_ENV: ""})

    assert [asked["min_delay"] for asked in crawled] == [DEFAULT_DELAY_SECONDS] * 2


def test_a_file_named_that_does_not_exist_is_an_error(here, crawled):
    result = _run("--config", str(here / "missing.toml"), "crawl", URL)

    assert result.exit_code == 2 and crawled == []
    assert "missing.toml" in result.stderr


def test_an_unknown_key_is_refused_by_name_with_the_nearest_known(here, crawled):
    _write(here / "sluicer.toml", "dealy = 4\n")

    result = _run("crawl", URL)

    assert result.exit_code == 2 and crawled == []
    assert "dealy" in result.stderr and "delay" in result.stderr
    assert str(here / "sluicer.toml") in result.stderr


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("[crawll]\ndelay = 1\n", "crawll"),
        ("[map]\ndelay = 1\n", "map does not take delay"),
        ("[crawl.deep]\nx = 1\n", "deep"),
        ("output = 'a.json'\n", "output"),
        ("[crawl]\nout = 'a.jsonl'\n", "out"),
        ("stealth = true\n", "stealth"),
        ("[serve]\nallow-unauthenticated = true\n", "allow-unauthenticated"),
        ("delay = 'fast'\n", "delay"),
        ("delay = -1\n", "delay"),
        ("json = 'yes'\n", "json"),
        ("[crawl]\nmax-pages = 0\n", "max-pages"),
        ("respect = ['tmd']\n", "respect"),
        ("respect = 'tdm'\n", "respect"),
        ("delay = true\n", "delay"),
        ("delay = 1\ndelay = 2\n", "sluicer.toml"),
    ],
)
def test_a_key_that_cannot_be_used_is_refused_before_anything_runs(
    here, crawled, fetched, text, said
):
    _write(here / "sluicer.toml", text)

    result = _run("crawl", URL)

    assert result.exit_code == 2, result.output
    assert crawled == [] and fetched == []
    assert said in result.stderr


@pytest.mark.parametrize(
    "text",
    [
        'header = ["Authorization Bearer s3cr3t"]\n',
        'header = ["Authorization: Bearer s3cr3t\\nX: y"]\n',
        'header = ["User-Agent: s3cr3t"]\n',
        'cookie = ["session s3cr3t"]\n',
        'cookie = ["session=s3cr3t;x"]\n',
        'proxy = "ftp://user:s3cr3t@proxy.example:21"\n',
        'proxy = "http://user:s3cr3t@proxy.example:notaport"\n',
        "proxy = 8080\n",
        'header = "Authorization: Bearer s3cr3t"\n',
    ],
)
def test_a_secret_the_file_holds_is_never_repeated(here, fetched, text):
    _write(here / "sluicer.toml", text)

    result = _run("fetch", URL)

    assert result.exit_code == 2 and fetched == []
    assert "s3cr3t" not in result.output
    assert "sluicer.toml" in result.stderr


@pytest.mark.parametrize("text", ["delay = \n", "delay = 2021-02-30\n"])
def test_a_file_that_is_not_toml_is_refused_with_where(here, crawled, text):
    _write(here / "sluicer.toml", text)

    result = _run("crawl", URL)

    assert result.exit_code == 2 and crawled == []
    assert "sluicer.toml" in result.stderr and "line 1" in result.stderr


def test_a_relative_cache_is_the_file_s_directory_s_and_a_tilde_is_home(
    here, monkeypatch
):
    used: list[str] = []

    def cached(url, cache, **kwargs):
        used.append(str(cache.directory))
        return Fetched(url=url, html="<title>t</title>", status=200, rung="http")

    monkeypatch.setattr("sluicer.fetch.cache.fetch_cached", cached)
    _write(here / "sluicer.toml", 'cache = "kept"\n\n[extract]\ncache = "~/kept"\n')
    below = here / "below"
    below.mkdir()
    monkeypatch.chdir(below)
    monkeypatch.setenv("HOME", str(here / "home"))

    _run("fetch", URL)
    _run("extract", URL)

    assert used == [str(here / "kept"), str(here / "home" / "kept")]


def test_robots_turned_off_by_the_file_is_said_every_time(here, fetched):
    _write(here / "sluicer.toml", "no-robots = true\n")

    quiet = _run("fetch", URL, "--robots")
    said = _run("fetch", URL)

    assert "robots.txt" not in quiet.stderr
    assert "robots.txt is not obeyed" in said.stderr
    assert str(here / "sluicer.toml") in said.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_a_file_found_that_others_may_write_is_refused(here, crawled):
    found = _write(here / "sluicer.toml", "delay = 4\n")
    found.chmod(0o666)

    result = _run("crawl", URL)

    assert result.exit_code == 2 and crawled == []
    assert "others can write" in result.stderr and "--no-config" in result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_a_file_named_is_read_whatever_its_permissions(here, crawled):
    named = _write(here / "shared.toml", "delay = 4\n")
    named.chmod(0o666)

    _run("--config", str(named), "crawl", URL)

    assert crawled[0]["min_delay"] == 4


def test_python_3_10_reads_the_file_with_tomli(here, crawled, monkeypatch):
    tomllib = pytest.importorskip("tomllib")
    fake = types.ModuleType("tomli")
    fake.loads = lambda text: {**tomllib.loads(text), "delay": 9}  # type: ignore[attr-defined]
    fake.TOMLDecodeError = tomllib.TOMLDecodeError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tomli", fake)
    monkeypatch.setattr(config, "_HAS_TOMLLIB", False)
    _write(here / "sluicer.toml", "delay = 4\n")

    _run("crawl", URL)

    assert crawled[0]["min_delay"] == 9


def test_python_3_10_without_tomli_says_what_to_install(here, crawled, monkeypatch):
    monkeypatch.setitem(sys.modules, "tomli", None)
    monkeypatch.setattr(config, "_HAS_TOMLLIB", False)
    _write(here / "sluicer.toml", "delay = 4\n")

    result = _run("crawl", URL)

    assert result.exit_code == 2 and crawled == []
    assert "pip install tomli" in result.stderr


def test_every_flag_a_file_may_set_can_be_turned_off_on_the_command_line():
    for name, command in cli.main.commands.items():
        for param in command.params:
            key = config.key_of(param)
            if key in config.SETTABLE and getattr(param, "is_flag", False):
                assert param.secondary_opts, (name, key)


def test_every_key_is_an_option_of_some_command_and_documented():
    guide = Path(__file__).resolve().parent.parent / "docs" / "configuration.md"
    text = guide.read_text(encoding="utf-8")
    taken = {
        config.key_of(param)
        for command in cli.main.commands.values()
        for param in command.params
    }
    for key in config.SETTABLE:
        assert key in taken, key
        assert f"`{key}`" in text, key
    for key in config.PER_RUN:
        assert key in taken, key


def test_a_crawl_s_retries_jobs_and_format_come_from_the_file(here, crawled):
    _write(here / "sluicer.toml", '[crawl]\nretries = 0\njobs = 8\nformat = "csv"\n')

    result = _run("crawl", URL)

    assert crawled[0]["retries"] == 0 and crawled[0]["concurrency"] == 8
    assert result.stdout.startswith("url,ok,depth,")


def test_a_template_is_one_run_s_and_not_a_file_s(here, crawled):
    _write(here / "sluicer.toml", '[crawl]\ntemplate = "sitemap"\n')

    result = _run("crawl", URL)

    assert result.exit_code == 2 and crawled == []
    assert "template cannot be set in a file: it changes what one crawl" in (
        result.stderr
    )


def test_a_top_level_value_one_command_refuses_is_left_to_the_others(
    here, fetched, crawled
):
    """Found by review: format = "jsonl" at the top is crawl's and batch's
    value, map takes "json" or "csv", and map's refusal made every command
    exit 2 without saying it was map's. A key at the top applies to the
    commands that take it, and those that take it but refuse that value
    ignore it, as those that do not take it do."""
    _write(here / "sluicer.toml", 'format = "jsonl"\n')

    assert _run("fetch", URL).exit_code == 0
    _run("crawl", URL)
    assert fetched and crawled

    defaults = config.defaults(
        {"format": "jsonl"}, here / "sluicer.toml", cli.main.commands
    )
    assert defaults["crawl"]["output_format"] == "jsonl"
    assert defaults["batch"]["output_format"] == "jsonl"
    assert "output_format" not in defaults["map"]


def test_a_top_level_value_every_command_refuses_is_refused_naming_them(here, fetched):
    _write(here / "sluicer.toml", 'format = "xml"\n')

    result = _run("fetch", URL)

    assert result.exit_code == 2 and fetched == []
    assert "format is refused by every command that takes it" in result.stderr
    assert "batch" in result.stderr and "crawl" in result.stderr
    assert "map" in result.stderr
