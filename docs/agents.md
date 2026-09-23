# In your agent

Sluicer's MCP server is one command, and every client that speaks MCP can
start it:

```bash
uvx --with 'sluicer[mcp]' sluicer mcp
```

It needs [uv](https://docs.astral.sh/uv/) on the `PATH`; `uvx` fetches Sluicer
and its `mcp` extra, which brings fetching and markdown, the first time.
`sluicer-mcp`, after `uv pip install 'sluicer[mcp]'`, is the same server.

Every one of its ten tools only reads -- the page it is given, or the web --
and says so in its MCP annotations (`readOnlyHint`, not `destructiveHint`), so
a client that asks before a tool writes runs them without asking. Measured
with Codex 0.144.4 on 2026-09-24: before the annotations, `codex exec`
cancelled the call unless the server's tools were approved in advance; with
them, it runs the tool in its default mode, in `writes` and in `auto`.

The server refuses to fetch `localhost`, a private network or a cloud's
metadata endpoint unless it is started with `SLUICER_ALLOW_PRIVATE=1`.

## Claude Code

```bash
claude mcp add sluicer -- uvx --with 'sluicer[mcp]' sluicer mcp
```

Or install the repository as a plugin, which brings the server and a skill
that tells the agent when to reach for it:

```bash
claude plugin marketplace add Gi0tto/sluicer
claude plugin install sluicer@sluicer
```

## Codex

```bash
codex mcp add sluicer -- uvx --with 'sluicer[mcp]' sluicer mcp
```

This writes the server into `~/.codex/config.toml`:

```toml
[mcp_servers.sluicer]
command = "uvx"
args = ["--with", "sluicer[mcp]", "sluicer", "mcp"]
```

Codex reads skills in the open [Agent Skills](https://agentskills.io) format
from `~/.agents/skills/` and from `.agents/skills/` in a repository. Sluicer's
skill keeps to that format: the standard's own validator passes it, and a
test in the suite holds it to the fields the standard allows.

```bash
git clone --depth 1 https://github.com/Gi0tto/sluicer /tmp/sluicer
mkdir -p ~/.agents/skills && cp -r /tmp/sluicer/skills/sluicer ~/.agents/skills/
```

Verified end to end on 2026-09-24 with codex-cli 0.144.4: Codex called
`extract_declared` and answered a page's price with its source and place.

## Other clients

These are written from each client's own documentation, as it read on
2026-09-24, and were not run here. Each starts the same command.

**Cursor** -- `.cursor/mcp.json` in a project, or `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "sluicer": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--with", "sluicer[mcp]", "sluicer", "mcp"]
    }
  }
}
```

**VS Code** -- `.vscode/mcp.json` in a workspace, or the user profile's
`mcp.json`:

```json
{
  "servers": {
    "sluicer": {
      "command": "uvx",
      "args": ["--with", "sluicer[mcp]", "sluicer", "mcp"]
    }
  }
}
```

or, from a terminal:

```bash
code --add-mcp '{"name":"sluicer","command":"uvx","args":["--with","sluicer[mcp]","sluicer","mcp"]}'
```

**Gemini CLI** -- `~/.gemini/settings.json`, or `.gemini/settings.json` in a
project:

```json
{
  "mcpServers": {
    "sluicer": {
      "command": "uvx",
      "args": ["--with", "sluicer[mcp]", "sluicer", "mcp"]
    }
  }
}
```

**Claude Desktop** -- `claude_desktop_config.json`, in
`~/Library/Application Support/Claude/` on macOS and `%APPDATA%\Claude\` on
Windows, with the same `mcpServers` entry as Gemini CLI's. An application
started from the Dock may not see your shell's `PATH`; if `uvx` is not found,
write its full path, which `which uvx` prints.

**Zed** -- `settings.json`:

```json
{
  "context_servers": {
    "sluicer": {
      "command": "uvx",
      "args": ["--with", "sluicer[mcp]", "sluicer", "mcp"],
      "env": {}
    }
  }
}
```

**Anything else that speaks MCP** -- over stdio, the command above.

## Without MCP

`sluicer serve` answers the same ten tools over HTTP, for any language and any
model's function calling: `POST /v1/tools/<name>` with the tool's arguments as
JSON, described at `/openapi.json`. See [the HTTP API](http-api.md). And in
Python, `sluicer.extract(html, url=...)` is the library the server calls.

## With other tools

Sluicer reads HTML, whoever fetched it: `extract` never fetches. A page
another crawler brought back -- a browser automation, a scraping framework, a
fetch service's raw HTML -- is handed to `sluicer.extract(html, url=...)` as
it is. Hand it the response's headers too, `headers=...`, and the answer is
the one Sluicer gives when it fetches the page itself: a `Link` header's
canonical, an `X-Robots-Tag` and the charset are read from them. Bytes are
better than text, since the page's own charset declaration is still in them.
