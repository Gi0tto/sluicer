# Configuration

The options you give every command -- a proxy, the headers a site wants, a
cache, a crawl's delay, JSON output -- can be given once, in a file. The file
is read by the `sluicer` command only: the Python API, the MCP server and the
HTTP API take their arguments as they are called and read no file.

## A file

`sluicer.toml`, keyed as the options are spelt on the command line, without
their dashes. Save it as `~/.config/sluicer/sluicer.toml` and name it once, in
your shell's profile, with `export SLUICER_CONFIG=~/.config/sluicer/sluicer.toml`,
or for one command with `sluicer --config ~/.config/sluicer/sluicer.toml ...`:

```toml
proxy = "socks5h://127.0.0.1:1080"
header = ["Accept-Language: de-DE"]
cache = "~/.cache/sluicer"
json = true

[crawl]
delay = 2.0
max-pages = 500

[extract]
visible = true
```

This file sets a proxy, a header and a cache, which only a file you name may
set. The same file saved in the directory you run in, and found there, makes
every command exit 2 and say so: [which file](#which-file) says why.

A key at the top applies to every command that takes that option, and the
others ignore it: `json` above is for `fetch`, `diff` and `audit`. A command
whose option takes other values ignores it too: `format = "jsonl"` at the top
is for `crawl` and `batch`, and `map`, which writes `json` or `csv`, keeps its
own. A value that no command taking the key accepts is refused, even where
each of their tables sets its own. A table named after a command is that
command's own, and its keys win over the top's.
A repeatable option is a list; a flag is `true` or `false`; `cache` is a
directory, where `~` is your home and a relative path is taken from the file's
directory, not from where you run the command.

In a Python project the same keys can go in `pyproject.toml`, under
`[tool.sluicer]`, with a command's table under `[tool.sluicer.crawl]`.

## Which file

The first of these, and only one:

1. `--config FILE`, before the command: `sluicer --config team.toml crawl URL`.
2. The file the `SLUICER_CONFIG` variable names. For a file of your own
   everywhere, set it in your shell's profile:
   `export SLUICER_CONFIG=~/.config/sluicer/sluicer.toml`.
3. The nearest `sluicer.toml`, or `pyproject.toml` with a `[tool.sluicer]`
   table, in the directory you run in or any directory above it. Both in one
   directory is an error: keep one.

`--no-config`, or `SLUICER_CONFIG` set and empty, reads no file at all: what a
script that must behave the same on every machine wants.

A file found by looking up the directories may be one you did not write: a
repository you cloned can carry a `sluicer.toml` or a `[tool.sluicer]` table,
and it would be read from the moment you ran `sluicer` inside it. So such a
file may not set `proxy`, `header`, `cookie`, `cache`, `host` or `no-robots`
-- what is sent on your behalf, to whom and through what, where the pages you
fetch are kept, who can reach `sluicer serve`, and whether robots.txt is
obeyed. Only a file you name, with `--config` or `SLUICER_CONFIG`, sets
those; one found that tries is refused, naming the key and what to do. It must
also be yours, and writable by you alone: one someone else can write, in a
shared directory above yours or through a macOS access list, is refused too.
`chmod go-w` takes the mode's write bits away; an access list is not in them,
so `ls -le` shows its entries, `chmod -a# N` removes entry N and `chmod -N`
the whole list. An entry that lets only you, the file's owner, write it is no
reason to refuse it, and neither is a group whose only member is you: Ubuntu
and Fedora give each user a group of their own and a umask of 002, so a file
you make there is `-rw-rw-r--`, and it is read, as Debian's OpenSSH reads such
an `authorized_keys`. A group anyone else is in, or has as their own, is
others. A file you name is read as you named it.

## What wins

From the first to the last:

1. **The command line.** `--proxy`, `-H`, `--delay` given to one run win over
   everything. A flag the file turns on has an opposite for one run:
   `--no-json`, `--no-induce`, `--robots` against `no-robots = true`. A list
   the command line gives replaces the file's, it does not add to it: `-H`
   once sends that header and none of the file's.
2. **The environment.** `SLUICER_PROXY` wins over `proxy`, and
   `SLUICER_MCP_TOOLS` over `tools`, whenever the variable is set, even
   empty.
3. **The file.**
4. **The built-in defaults**, the ones `--help` shows when no file is read.

`sluicer COMMAND --help` shows the file's value wherever it shows a default at
all -- `[default: 3.0; x>=0]` for `--delay` -- and never shows a proxy, a
header or a cookie.

## The keys

| key | for | what |
|---|---|---|
| `proxy` | every command that fetches | the proxy, as `--proxy` takes it; `SLUICER_PROXY` wins; a file you name only |
| `header` | every command that fetches | a list of `"NAME: VALUE"`, as `-H`; a file you name only |
| `cookie` | every command that fetches | a list of `"NAME=VALUE"`, as `--cookie`; a file you name only |
| `cache` | `fetch`, `extract`, `inspect`, `markdown`, `diff`, `audit`, `feed`, `select` | the cache directory; a file you name only |
| `max-age` | the same | seconds a kept page is good for, with `cache` |
| `no-robots` | the commands that take `--no-robots` | `true` fetches where robots.txt says no; a file you name only |
| `respect` | the commands that take `--respect` | a list: `["tdm"]` |
| `induce` | `extract`, `inspect`, `crawl`, `batch`, `warc` | a flag |
| `microformats` | `extract`, `inspect`, `warc` | a flag |
| `visible` | `extract`, `inspect` | a flag |
| `front-matter` | `markdown` | a flag |
| `json` | `fetch`, `diff`, `audit` | a flag: print JSON |
| `plain` | `map` | a flag: one address a line |
| `delay` | `crawl`, `batch` | the least seconds between two requests to one site |
| `retries`, `jobs` | `crawl`, `batch` | as their options |
| `format` | `crawl`, `batch`, `map` | `"csv"`, or the command's own default (`"jsonl"`, `"json"`) |
| `max-pages`, `max-depth`, `include`, `exclude` | `crawl` | as their options |
| `limit` | `map` | as `--limit` |
| `no-site` | `audit` | a flag |
| `host` | `serve` | as `--host`; a file you name only |
| `port`, `timeout` | `serve` | as their options |
| `tools` | `mcp` | `"extract_declared,page_markdown"`; `SLUICER_MCP_TOOLS` wins |

`no-robots = true` is said on stderr on every run it applies to, with the
file that says so: a default nobody sees on the command line is one to
repeat. Some options cannot be set in a file, because each belongs to one run:
`-o`/`--output` and `--out`, `--resume`, `--url`, `--at`, `--want`,
`--select`, `--rows`, `--listing`, `--force`, `--stealth` (the stealth rung
is asked for page by page), `--any-site`, `crawl --template` and `serve --allow-unauthenticated`. A file that sets one
is refused and says why.

## When the file is wrong

Nothing runs: the command exits 2 with the file and the key. An unknown key
names the nearest known one (`dealy is not an option (did you mean delay?)`),
a table that is not a command says so, a key the command does not take says
which, and a value of the wrong type says what was expected; a key at the top
whose value every command taking it refuses names those commands and what the
first of them says. A file that is
not TOML gives the line and column. The values of `proxy`, `header` and
`cookie` can be passwords, tokens or sessions, and no message repeats them:
it names the key, and the entry by its number.

## Python 3.10

Python 3.11 and later read TOML with the standard library's `tomllib`. On
3.10, Sluicer's install brings `tomli`, the same parser `tomllib` was made
from: MIT, pure Python, and no dependencies of its own. It is installed on
3.10 only.
