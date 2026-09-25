"""The defaults a configuration file gives the command line.

A ``sluicer.toml``, or a ``[tool.sluicer]`` table in ``pyproject.toml``, holds
the options a user would otherwise repeat on every command -- a proxy, the
headers a site wants, a cache, a crawl's delay, JSON output -- keyed as the
options are spelt, without their dashes::

    proxy = "socks5h://127.0.0.1:1080"
    header = ["Accept-Language: de-DE"]
    cache = "~/.cache/sluicer"

    [crawl]
    delay = 2.0
    max-pages = 500

A key at the top applies to every command that takes that option with that
value -- ``format = "jsonl"`` is crawl's and batch's, and map, which writes
json or csv, keeps its own -- and a value no command taking it accepts is
refused; a table named after a command applies to that command, over the
top. The command line
wins over the environment, the environment over the file, and the file over
the built-in defaults: the file's values become click's ``default_map``, which
click consults only after the command line and an option's variable, and a
key whose variable is set -- ``SLUICER_PROXY`` for ``proxy``,
``SLUICER_MCP_TOOLS`` for ``tools`` -- is left to it. Every flag a file may
turn on can be turned off for one run (``--no-json``, ``--robots``), and
``--no-config`` reads no file at all.

Which file: ``--config FILE``, else the file ``SLUICER_CONFIG`` names (empty,
none), else the first ``sluicer.toml``, or ``pyproject.toml`` with a
``[tool.sluicer]`` table, in the working directory or above it. A file found
that way must be the user's own and writable by no one else, since a proxy or
a header in it would be sent on their behalf; a file named is read as named.

A file is read whole before anything runs, and anything in it that cannot be
used is an error naming the file and the key: an unknown key (with the
nearest known one), a key the command does not take, a value of the wrong
type, and the options that belong to one run -- an output file, the stealth
rung, a server with no token. The values of ``proxy``, ``header`` and
``cookie`` may be secrets, and no message ever repeats them.

Python 3.10 has no ``tomllib``; there the file is read with ``tomli``, which
the package depends on for 3.10 alone: MIT, pure Python, one module of the
same code the standard library took as ``tomllib`` in 3.11.
"""

from __future__ import annotations

import difflib
import importlib
import os
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import click
from click.core import ParameterSource

from sluicer.fetch.http_rung import PROXY_ENV
from sluicer.fetch.identity import outgoing
from sluicer.fetch.wire import Proxy

CONFIG_ENV = "SLUICER_CONFIG"
"""The file to read; set and empty, no file at all."""

FILE_NAME = "sluicer.toml"
PYPROJECT = "pyproject.toml"

SETTABLE = frozenset(
    {
        "proxy",
        "header",
        "cookie",
        "cache",
        "max-age",
        "no-robots",
        "respect",
        "induce",
        "microformats",
        "visible",
        "front-matter",
        "json",
        "plain",
        "delay",
        "retries",
        "jobs",
        "format",
        "max-pages",
        "max-depth",
        "include",
        "exclude",
        "limit",
        "no-site",
        "host",
        "port",
        "timeout",
        "tools",
    }
)
"""The options a file may give a default to, spelt as on the command line."""

PER_RUN = {
    "output": "it names one run's file, and a default would overwrite it",
    "out": "it names one run's file, and a default would overwrite it",
    "resume": "it continues one run's file",
    "url": "it says where one page came from",
    "at": "it names one capture",
    "want": "it names one extractor's values",
    "listing": "it describes one extractor's pages",
    "select": "it names one extractor's fields",
    "rows": "it names one extractor's rows",
    "force": "it overrides one refusal, once",
    "stealth": "the stealth rung is asked for page by page, never by default",
    "any-site": "a crawl leaves the site it was given only when that run asks",
    "template": "it changes what one crawl reads, and every crawl would read it so",
    "allow-unauthenticated": "a server with no token is asked for where it is "
    "seen, on the command line",
}
"""Options a file may not set, and why: each belongs to one run."""

SECRET = frozenset({"proxy", "header", "cookie"})
"""Keys whose values no message repeats: a password, a token, a session."""

PATHS = frozenset({"cache"})
"""Keys that are directories: ``~`` is expanded, and a relative one is the
file's directory's, not the working directory's."""


def _tools_env() -> str:
    from sluicer.mcp_server import TOOLS_ENV

    return TOOLS_ENV


ENVIRONMENT: dict[str, Callable[[], str]] = {
    "proxy": lambda: PROXY_ENV,
    "tools": _tools_env,
}
"""The keys an environment variable also sets, which wins over the file."""

_HAS_TOMLLIB = sys.version_info >= (3, 11)

# RFC 9110's token: what a header's or a cookie's name may be spelt with.
_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")

_META = "sluicer.config"


class ConfigError(click.ClickException):
    """A configuration file that cannot be used as it is. Exits 2, as every
    input Sluicer could not read does. ``what`` is what is wrong with a
    value, without the file and the key, where one was refused."""

    exit_code = 2

    def __init__(self, message: str, what: str = "") -> None:
        super().__init__(message)
        self.what = what


def key_of(param: click.Parameter) -> str | None:
    """The key a file sets ``param`` with: its long option, undashed."""
    if not isinstance(param, click.Option):
        return None
    for option in param.opts:
        if option.startswith("--"):
            return option[2:]
    return None


class ConfiguredGroup(click.Group):
    """A group whose commands take their defaults from a configuration file.

    It adds ``--config FILE`` and ``--no-config`` to the group, reads the file
    before the command is made, so every option finds its default there, and
    gives every flag a file may turn on its opposite, as each command is
    added to it.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.params += [
            click.Option(
                ["--config", "config_file"],
                metavar="FILE",
                help=f"Take defaults from this TOML file; else {CONFIG_ENV}, else "
                f"the nearest {FILE_NAME} or [tool.sluicer].",
            ),
            click.Option(
                ["--no-config"],
                is_flag=True,
                help="Read no configuration file.",
            ),
        ]

    def add_command(self, cmd: click.Command, name: str | None = None) -> None:
        cmd.params = [_with_opposite(param) for param in cmd.params]
        super().add_command(cmd, name)

    def invoke(self, ctx: click.Context) -> Any:
        named = ctx.params.pop("config_file", None)
        ignored = ctx.params.pop("no_config", False)
        found = None if ignored else _find(named)
        if found is not None:
            path, from_pyproject = found
            ctx.meta[_META] = path
            ctx.default_map = defaults(
                _read(path, from_pyproject), path, self.commands, from_pyproject
            )
        return super().invoke(ctx)


def _with_opposite(param: click.Parameter) -> click.Parameter:
    """``param``, a flag a file may turn on, with a second name that turns it
    off: ``--json/--no-json``, ``--no-robots/--robots``."""
    key = key_of(param)
    if (
        not isinstance(param, click.Option)
        or not param.is_flag
        or param.secondary_opts
        or len(param.opts) != 1
        or key not in SETTABLE
        or param.name is None
    ):
        return param
    primary = param.opts[0]
    opposite = f"--{key[3:]}" if key.startswith("no-") else f"--no-{key}"
    return click.Option(
        [param.name, f"{primary}/{opposite}"],
        is_flag=True,
        default=False,
        help=param.help,
        hidden=param.hidden,
        callback=_said_if_robots_off if key == "no-robots" else param.callback,
    )


def _said_if_robots_off(ctx: click.Context, param: click.Parameter, value: Any) -> Any:
    """Say, every time, that robots.txt is not obeyed because a file said so:
    a default nobody sees on the command line is the one to repeat."""
    if value and ctx.get_parameter_source(param.name or "") == (
        ParameterSource.DEFAULT_MAP
    ):
        source = ctx.find_root().meta.get(_META, "a configuration file")
        click.echo(
            f"sluicer: robots.txt is not obeyed: no-robots = true in {source}",
            err=True,
        )
    return value


def _find(named: str | None) -> tuple[Path, bool] | None:
    """The file to read, and whether it is a pyproject.toml, or None."""
    if named is None:
        named = os.environ.get(CONFIG_ENV)
        if named is not None and not named.strip():
            return None
    if named is not None:
        path = Path(named).expanduser()
        if not path.is_file():
            raise ConfigError(f"{path}: no such configuration file")
        return path, path.name == PYPROJECT
    here = Path.cwd()
    for directory in (here, *here.parents):
        own = directory / FILE_NAME
        project = directory / PYPROJECT
        candidates = [
            (own, False) if own.is_file() else None,
            (project, True) if _has_our_table(project) else None,
        ]
        found = [candidate for candidate in candidates if candidate is not None]
        if len(found) == 2:
            raise ConfigError(
                f"{own} and the [tool.sluicer] table in {project} both configure "
                "sluicer: keep one."
            )
        if found:
            _check_owner(found[0][0])
            return found[0]
    return None


def _has_our_table(project: Path) -> bool:
    try:
        text = project.read_text(encoding="utf-8")
    except OSError:
        return False
    if "sluicer" not in text:
        return False
    return "sluicer" in _parsed(text, project).get("tool", {})


def _check_owner(path: Path) -> None:
    """Refuse a file found by searching that is not the user's own, or that
    others may write: its proxy and headers would be sent as theirs."""
    if not hasattr(os, "getuid"):
        return
    status = path.stat()
    if status.st_uid != os.getuid():
        why = "belongs to another user"
    elif status.st_mode & 0o022:
        why = "others can write it"
    else:
        return
    raise ConfigError(
        f"{path} {why}, and a configuration file sets what is sent on your "
        f"behalf: make it yours alone (chmod go-w), name it with --config, or "
        f"run with --no-config."
    )


def _read(path: Path, from_pyproject: bool) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as failure:
        raise ConfigError(f"{path}: could not be read: {failure}") from None
    data = _parsed(text, path)
    if not from_pyproject:
        return data
    table = data.get("tool", {}).get("sluicer", {})
    if not isinstance(table, dict):
        raise ConfigError(f"{path}: tool.sluicer is not a table")
    return table


def _parsed(text: str, path: Path) -> dict[str, Any]:
    name = "tomllib" if _HAS_TOMLLIB else "tomli"
    try:
        toml = importlib.import_module(name)
    except ImportError:
        raise ConfigError(
            f"{path}: reading it on Python {sys.version_info[0]}."
            f"{sys.version_info[1]} needs tomli, which sluicer's install brings "
            f"there: pip install tomli"
        ) from None
    try:
        data: dict[str, Any] = toml.loads(text)
    except toml.TOMLDecodeError as invalid:
        raise ConfigError(f"{path} is not TOML: {invalid}") from None
    return data


def defaults(
    data: Mapping[str, Any],
    path: Path,
    commands: Mapping[str, click.Command],
    from_pyproject: bool = False,
) -> dict[str, dict[str, Any]]:
    """Click's ``default_map`` from a file's ``data``: for each command, its
    parameters' defaults, the file's top-level keys under its own table's.

    Raises:
        ConfigError: a key or a value in ``data`` cannot be used; the message
            names ``path`` and the key, and never a secret's value.
    """
    prefix = "tool.sluicer." if from_pyproject else ""
    options = {
        name: {key: p for p in command.params if (key := key_of(p)) is not None}
        for name, command in commands.items()
    }
    known = {key for keys in options.values() for key in keys}
    top = {k: v for k, v in data.items() if not isinstance(v, dict)}
    tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    for key in top:
        _allowed(key, known, path, f"{prefix}{key}" if prefix else key)
    for name, table in tables.items():
        if name not in commands:
            nearest = _nearest(name, commands)
            raise ConfigError(
                f"{path}: [{prefix}{name}] names no command{nearest}; a table "
                "is a command's own defaults"
            )
        for key, value in table.items():
            where = f"[{prefix}{name}] {key}"
            if isinstance(value, dict):
                raise ConfigError(
                    f"{path}: {where} is a table, and a command's options are values"
                )
            _allowed(key, known, path, where)
            if key not in options[name]:
                raise ConfigError(f"{path}: {where}: {name} does not take {key}")
    answer: dict[str, dict[str, Any]] = {}
    # A key at the top is for the commands that take it with its value: map's
    # format is "json" or "csv" and crawl's "jsonl" or "csv", so format =
    # "jsonl" is crawl's and batch's, and no reason for every command to
    # stop. Only a value no command that takes the key takes is refused.
    refused: dict[str, list[tuple[str, ConfigError]]] = {}
    taken: set[str] = set()
    for name in commands:
        own = tables.get(name, {})
        answer[name] = {}
        for key, value in top.items():
            param = options[name].get(key)
            if param is None or param.name is None or key in own or _in_env(key):
                continue
            try:
                answer[name][param.name] = _value(
                    key, value, param, path, f"{prefix}{key}"
                )
            except ConfigError as refusal:
                refused.setdefault(key, []).append((name, refusal))
            else:
                taken.add(key)
        for key, value in own.items():
            param = options[name][key]
            if param.name is None or _in_env(key):
                continue
            where = f"[{prefix}{name}] {key}"
            answer[name][param.name] = _value(key, value, param, path, where)
    for key, refusals in refused.items():
        if key not in taken:
            names = ", ".join(name for name, _ in refusals)
            first, refusal = refusals[0]
            raise ConfigError(
                f"{path}: {prefix}{key} is refused by every command that takes it "
                f"({names}); {first} says it {refusal.what}"
            )
    return answer


def _in_env(key: str) -> bool:
    """Whether the variable that also sets ``key`` is set, and wins."""
    return key in ENVIRONMENT and ENVIRONMENT[key]() in os.environ


def _allowed(key: str, known: set[str], path: Path, where: str) -> None:
    if key in SETTABLE:
        return
    if key in PER_RUN:
        raise ConfigError(
            f"{path}: {where} cannot be set in a file: {PER_RUN[key]}. Give "
            f"--{key} on the command line."
        )
    if key in known:
        raise ConfigError(f"{path}: {where} cannot be set in a file")
    raise ConfigError(f"{path}: {where} is not an option{_nearest(key, SETTABLE)}")


def _nearest(word: str, choices: Any) -> str:
    close = difflib.get_close_matches(word, sorted(choices), n=1)
    return f" (did you mean {close[0]}?)" if close else ""


def _value(key: str, value: Any, param: click.Parameter, path: Path, where: str) -> Any:
    """``value`` as the option takes it, checked; a secret's never shown."""

    def wrong(what: str) -> ConfigError:
        return ConfigError(f"{path}: {where} {what}", what)

    assert isinstance(param, click.Option)
    if param.is_flag:
        if not isinstance(value, bool):
            raise wrong("is a flag: true or false")
        return value
    if param.multiple:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise wrong('is a list of strings: ["...", "..."]')
        if key == "header":
            _check_headers(value, wrong)
        elif key == "cookie":
            _check_cookies(value, wrong)
        else:
            for item in value:
                _converted(item, param, wrong)
        return list(value)
    if key in SECRET:
        if not isinstance(value, str):
            raise wrong("is a string")
        try:
            Proxy.parse(value)
        except ValueError:
            raise wrong(
                "is not a proxy Sluicer speaks to: http://host:port, "
                "socks5://host:port or socks5h://host:port, with user:password@ "
                "if it needs one"
            ) from None
        return value
    if isinstance(value, bool):
        raise wrong("is not a flag")
    converted = _converted(value, param, wrong)
    if key in PATHS:
        return str(path.parent / Path(str(converted)).expanduser())
    return converted


def _converted(value: Any, param: click.Option, wrong: Any) -> Any:
    try:
        return param.type.convert(value, param, None)
    except click.BadParameter as bad:
        raise wrong(f"is refused: {bad.message}") from None


def _check_headers(given: list[str], wrong: Any) -> None:
    """Each of ``given`` a header ``outgoing`` would send. A refusal names the
    entry, and its name only when that is spelt as a header's name can be."""
    for number, header in enumerate(given, start=1):
        name, colon, value = header.partition(":")
        name = name.strip()
        if not colon or not _TOKEN.fullmatch(name):
            raise wrong(f"entry {number} is not a header: write 'NAME: VALUE'")
        try:
            outgoing({name: value.strip()})
        except ValueError as refused:
            raise wrong(f"entry {number} is refused: {refused}") from None


def _check_cookies(given: list[str], wrong: Any) -> None:
    """Each of ``given`` a cookie ``outgoing`` would send, refused as a header
    is."""
    for number, cookie in enumerate(given, start=1):
        name, equals, value = cookie.partition("=")
        name = name.strip()
        if not equals or not _TOKEN.fullmatch(name):
            raise wrong(f"entry {number} is not a cookie: write NAME=VALUE")
        try:
            outgoing(None, {name: value.strip()})
        except ValueError as refused:
            raise wrong(f"entry {number} is refused: {refused}") from None
