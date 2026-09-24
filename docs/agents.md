# In your agent

Sluicer's MCP server is one command, and every client that speaks MCP can
start it:

```bash
uvx --with "sluicer[mcp]" sluicer mcp
```

It needs [uv](https://docs.astral.sh/uv/) on the `PATH`; `uvx` fetches Sluicer
and its `mcp` extra, which brings fetching and markdown, the first time.
`sluicer-mcp`, after `uv pip install "sluicer[mcp]"`, is the same server.

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
claude mcp add sluicer -- uvx --with "sluicer[mcp]" sluicer mcp
```

Or install the repository as a plugin, which brings the server and a skill
that tells the agent when to reach for it:

```bash
claude plugin marketplace add Gi0tto/sluicer
claude plugin install sluicer@sluicer
```

Verified end to end on 2026-09-24 with Claude Code 2.1.281: given the published
server, `claude -p` called `extract_declared` and answered a page's price, its
place and the conflict with the page's second price; the plugin, loaded with
`--plugin-dir`, brought the server and the skill; and `claude plugin validate`
passes the repository's manifests. Installing from the marketplace was not run.

## Codex

```bash
codex mcp add sluicer -- uvx --with "sluicer[mcp]" sluicer mcp
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

Gemini CLI was run here; the others are written from each client's own
documentation, as it read on 2026-09-24, and were not. Each starts the same
command.

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

**Gemini CLI** -- run on 2026-09-24:

```bash
gemini mcp add -s user sluicer uvx --with "sluicer[mcp]" sluicer mcp
```

writes this into `~/.gemini/settings.json` (or `.gemini/settings.json` in a
project, without `-s user`), and `gemini mcp list` then shows the server
connected. Gemini CLI starts MCP servers only in a folder it trusts: in one
it does not, the server is listed as disabled.

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

## In your own agent's code

Any framework that speaks MCP starts the same server. Run it as its own
process, as below, rather than importing it into your application's
environment: measured on 2026-09-24, `langchain-mcp-adapters` 0.3.1 resolves
mcp 1.30 and fails to import against mcp 2.2, which `sluicer[mcp]` needs, so
the two in one environment break the application. As separate processes they
speak MCP to each other, and every one of these listed the ten tools and
answered a page's price with its place:

LangChain (`langchain-mcp-adapters` 0.3.1, its client on mcp 1.30):

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({"sluicer": {
    "command": "uvx", "args": ["--with", "sluicer[mcp]", "sluicer", "mcp"],
    "transport": "stdio",
}})
tools = await client.get_tools()   # hand them to any LangChain agent
```

OpenAI Agents SDK (`openai-agents` 0.22.3):

```python
from agents import Agent
from agents.mcp import MCPServerStdio

async with MCPServerStdio(params={
    "command": "uvx", "args": ["--with", "sluicer[mcp]", "sluicer", "mcp"],
}) as sluicer:
    agent = Agent(name="reader", mcp_servers=[sluicer])
```

Pydantic AI (`pydantic-ai-slim[mcp]` 2.48, on FastMCP 4.0.7):

```python
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset, StdioTransport

sluicer = MCPToolset(StdioTransport("uvx", ["--with", "sluicer[mcp]", "sluicer", "mcp"]))
agent = Agent("openai:gpt-5", toolsets=[sluicer])
```

The model is the framework's to choose: Sluicer's answers are the same
whichever model reads them, since none is asked to produce them.

## Without MCP

`sluicer serve` answers the same ten tools over HTTP, for any language and any
model's function calling: `POST /v1/tools/<name>` with the tool's arguments as
JSON, described at `/openapi.json`. See [the HTTP API](http-api.md). And in
Python, `sluicer.extract(html, url=...)` is the library the server calls.

## With other tools

Sluicer reads HTML, whoever fetched it: `extract` never fetches. Hand it the
page as the other tool brought it back -- bytes are better than text, since
the page's own charset declaration is still in them -- with the address it
came from and, when the tool keeps them, the response's headers: a `Link`
header's canonical, an `X-Robots-Tag` and the charset are read from those.
Each of these was run on 2026-09-24 against a local page, and each answered
its price with its place and its canonical from the `Link` header:

```python
import sluicer

# httpx 0.28
r = httpx.get(url)
sluicer.extract(r.content, url=str(r.url), headers=dict(r.headers))

# Playwright 1.63: the rendered page, as text
response = page.goto(url)
sluicer.extract(page.content(), url=page.url, headers=response.all_headers())

# Scrapling 0.4
page = Fetcher.get(url)
sluicer.extract(page.body, url=page.url, headers=dict(page.headers))

# Crawl4AI 0.9: inside `async with AsyncWebCrawler() as crawler`
result = await crawler.arun(url=url)
sluicer.extract(result.html, url=result.url, headers=result.response_headers)

# Scrapy 2.19: in a spider's callback
headers = {k.decode(): v[0].decode() for k, v in response.headers.items()}
sluicer.extract(response.body, url=response.url, headers=headers)
```

Firecrawl's raw HTML is the page as it was received, and `firecrawl-py`
4.44 holds it in `raw_html`; this one was not run here, since Firecrawl's
service needs a key:

```python
doc = Firecrawl(api_key=key).scrape(url, formats=["rawHtml"])
sluicer.extract(doc.raw_html, url=doc.metadata.source_url)
```

All six install beside Sluicer's base package in one environment; the base
package needs only lxml and click.
