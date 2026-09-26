# The HTTP API

`sluicer serve` answers the MCP server's tools over HTTP, one address per
tool, so any language that can send a POST can use Sluicer. They are the twelve
tools an agent gets, each in the [MCP reference](reference/mcp.md), with the
same arguments, the same answers and the same output schemas, because it is
built from them: an HTTP call goes through the MCP SDK's own `call_tool`, argument
validation and output-schema check included. A tool the MCP server gains is
served here with nothing else to change. At `/mcp` it is the MCP server itself,
over MCP's streamable HTTP transport, for a client that does not start servers
over stdio: [MCP over HTTP](#mcp-over-http), with n8n and Dify.

It needs the `api` extra, which brings the other three:

```bash
uv tool install "sluicer[api]"
sluicer serve
```

That listens on `127.0.0.1:8000`, needs no token, and answers only requests
addressed to this machine.

## Run it

| Option | Default | |
|---|---|---|
| `--host` | `127.0.0.1` | Where to listen. Anything but loopback needs a token. |
| `--port` | `8000` | |
| `--timeout` | `120` | Seconds a request may take, its body included, before it is answered 504. A caller's selectors are evaluated in a process of their own, killed at the same time, so a selector that would run for minutes frees its worker when its call is answered. |
| `--allow-unauthenticated` | off | Listen beyond loopback with no token. |

| Variable | |
|---|---|
| `SLUICER_API_TOKEN` | When set, every request but `GET /health` must carry `Authorization: Bearer <token>`. Read from the environment only: a token on the command line is visible to every user of the machine through `ps`. |
| `SLUICER_ALLOW_PRIVATE` | `1` lets the tools fetch `localhost`, private networks and metadata endpoints, which they refuse by default. Read by the tools themselves, exactly as for the MCP server. |

To serve other machines, give it a token and listen on every interface:

```bash
export SLUICER_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
sluicer serve --host 0.0.0.0
```

Without a token it refuses to start there, and exits 2: anyone who can reach
the port could make this machine fetch any URL. `--allow-unauthenticated`
starts it anyway, for a server behind something that already decides who may
call it. The server speaks plain HTTP; beyond one machine, put TLS in front of
it, or the token crosses the network in the clear.

### In Docker

The image carries the extra. From 0.8.0 each release publishes it, for amd64
and arm64, as `ghcr.io/gi0tto/sluicer` (at the version, and at `latest`), or
build it from a checkout with `docker build -t sluicer .`. Inside a container
the server has to listen on every interface to be reachable through a
published port, so it needs a token:

```bash
docker run --rm -p 127.0.0.1:8000:8000 -e SLUICER_API_TOKEN="$SLUICER_API_TOKEN" \
  ghcr.io/gi0tto/sluicer sluicer serve --host 0.0.0.0
```

`-p 127.0.0.1:8000:8000` publishes it on the host's loopback only; write
`-p 8000:8000` to publish it on every interface of the host. The published
image has no browser; build with `--build-arg WITH_BROWSER=1` for pages that
need the browser rung. It runs as an unprivileged user, and carries Sluicer's
licences and those of everything it installs under
`/usr/share/licenses/sluicer/`.

## Call it

```bash
curl -s http://127.0.0.1:8000/v1/tools/extract_declared \
  -H "Authorization: Bearer $SLUICER_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"html_or_url": "https://shop.example/p/1"}'
```

The body is the tool's arguments as a JSON object, exactly as an MCP client
sends them, and the answer is what the tool answers:

```json
{
  "ok": true,
  "url": "https://shop.example/p/1",
  "summary": {
    "title": { "value": "Brake pad set", "source": "jsonld", "key": "Product.name",
               "where": "/html/head/script[1]#/name" }
  },
  "records": [
    {
      "type": "Product",
      "types": ["Product"],
      "fields": {
        "name": { "value": "Brake pad set", "source": "jsonld", "where": "/html/head/script[1]#/name" }
      },
      "source": "jsonld",
      "where": "/html/head/script[1]#"
    }
  ],
  "sources": ["jsonld"],
  "fetch": { "rung": "http", "status": 200, "seconds": 0.412, "climbs": [] }
}
```

Abridged: a real page declares more, and the summary answers more questions.

| Method and path | Token | Answers |
|---|---|---|
| `GET /health` | not needed | `{"ok": true, "version": "..."}` |
| `GET /v1/tools` | needed | `{"ok": true, "tools": [...]}`: every tool as the MCP server lists it, with `name`, `description`, `inputSchema` and `outputSchema` |
| `POST /v1/tools/{name}` | needed | the tool's answer |
| `GET /openapi.json` | needed | an OpenAPI 3.1 document, generated from those same schemas |
| `POST /mcp` | needed | MCP over streamable HTTP: [MCP over HTTP](#mcp-over-http) |

A client generator pointed at `/openapi.json` gets one operation per tool,
named after it. The tools themselves, and what each argument means, are
described in the listing and in [Extractors](extractors.md).

## MCP over HTTP

`/mcp` is the MCP SDK's own streamable HTTP transport over the same server:
the same twelve tools, listed with the same descriptions, annotations and both
schemas, and each call answers what it answers over stdio, the bounds of each
tool included. A call runs on the same workers as a `POST /v1/tools/{name}`,
within the same `--timeout`. The token, the `Host` check and the refusal of
private addresses hold as for every other route.

- **Stateless.** Every tool only reads, so no session is kept: no
  `Mcp-Session-Id`, and each request stands alone. Both the `initialize`
  handshake (protocol revisions 2024-11-05 to 2025-11-25) and the 2026-07-28
  revision, which has none, are answered.
- **POST only.** A stateless server sends nothing unasked, so a `GET`, which
  asks for a stream of what the server sends unasked, is answered 405, as the
  transport allows, and so is every other method.
- **JSON answers**, one per request, rather than an event stream.
- **An `Origin` that is not this server's own is refused** with 403
  (`cross_origin`), as the transport requires of a server: a browser sends
  one, and this server serves no page. A client that is not a browser sends
  none, as n8n's and Dify's do not.
- **A call past its time** is a failed call in MCP's own way, `isError` true
  and a text starting `timed_out:`. A refusal of the door is a JSON-RPC error
  with no `id`, its code in `data`:
  `{"jsonrpc": "2.0", "id": null, "error": {"code": -32600, "message": "...", "data": {"code": "unauthorized"}}}`,
  with the status of the table below.

The address is `http://127.0.0.1:8000/mcp`, and the token, when there is one,
goes in `Authorization: Bearer <token>`. Measured on 2026-09-25 against
`sluicer serve`: the `mcp` Python SDK's client (2.2.0) in both of its modes,
and the TypeScript SDK's (1.30.1), which n8n's MCP nodes are built on, list the
ten tools it had before `select_values` and `extract_many` and call `extract_declared`; the TypeScript client asks for the
stream once, takes the 405 and goes on.

### n8n

The **MCP Client Tool** node, on an AI Agent's Tool input, offers the tools to
the agent; the **MCP Client** node calls one tool as a step of a workflow. Both
take the same connection:

| Field | Value |
|---|---|
| Endpoint URL | `http://<host>:8000/mcp` |
| Server Transport | HTTP Streamable |
| Authentication | Bearer Auth, with a credential whose Bearer Token is `SLUICER_API_TOKEN` |
| Options > Timeout | above the server's `--timeout`, in milliseconds: `130000` for the default 120 s. The node's own default is 60000. |

In the MCP Client Tool node, Tools to Include can leave out the tools the agent
does not need; each costs context.

### Dify

Tools > MCP > **Add MCP Server (HTTP)**:

| Field | Value |
|---|---|
| Server URL | `http://<host>:8000/mcp` |
| Name, Server Identifier | `sluicer` |
| Advanced Options > Custom Headers | `Authorization`: `Bearer <token>` |
| Advanced Options > Timeouts | above the server's `--timeout` |

Dify takes only MCP servers over HTTP. Neither n8n's nor Dify's clients were
run here; both configurations are written from their documentation as it read
on 2026-09-25.

### From a container

n8n and Dify usually run in Docker, and a container's `127.0.0.1` is its own,
not the host's. So the server has to listen where the container can reach it,
which is beyond loopback and needs a token:

```bash
export SLUICER_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
sluicer serve --host 0.0.0.0
```

and the Endpoint URL names the host as the container sees it:
`http://host.docker.internal:8000/mcp` with Docker Desktop, or the host's
address on the Docker network on Linux. Better, run Sluicer as a container on
the same network as n8n or Dify ([In Docker](#in-docker)) and name it:
`http://sluicer:8000/mcp`. A server on loopback refuses a `Host` of
`host.docker.internal` with 421 in any case: a name that is not loopback's is
what DNS rebinding sends. A Dify or n8n in the cloud reaches only a public
address, so there the server needs the token and TLS in front of it.

## Answers and statuses

Every answer is a JSON object with `ok`, true exactly when the answer can be
used as it is. When the tool could not answer, `ok` is false and `error` says
why, in the shape the MCP tools use: `{"code", "message", "retryable"}`, with
`url` or `extra` when there is one. The status follows the code:

| Code | Status | From | Means |
|---|---|---|---|
| `bad_input` | 400 | tool or door | Something the tool cannot take: literal HTML to `fetch_page`, no pages, an object that is not an extractor, arguments that do not fit the input schema, a body that is not a JSON object, a caller's selector that ran too long and was stopped half a second before `--timeout` (a quarter of a budget under two seconds). Not retryable: the same selector on the same page runs as long again. |
| `unauthorized` | 401 | door | No token, or the wrong one. |
| `payment_required` | 402 | tool | The site answered 402 Payment Required. Sluicer never pays, and asks no other rung. |
| `refused_by_robots` | 403 | tool | The site's robots.txt says no. Do not work around it. |
| `refused_by_site` | 403 | tool | The site answered with a challenge page ("Just a moment..."), on every rung. Not the page, and not to be worked around. |
| `refused_address` | 403 | tool | A private address, refused unless `SLUICER_ALLOW_PRIVATE=1`. |
| `not_found` | 404 | door | No tool, or no path, by that name. |
| `cross_origin` | 403 | door | At `/mcp` only: a request whose `Origin` is not this server's own. |
| `method_not_allowed` | 405 | door | A tool is a POST, and so is `/mcp`. |
| `too_large` | 413 | tool or door | A page over 16 MiB, fetched or handed in, or a request body over 16 MiB, at `/mcp` too. |
| `unsupported_media_type` | 415 | door | The body must be `application/json`. |
| `misdirected` | 421 | door | Listening on loopback, it answers only requests addressed to `localhost`, `127.0.0.1` or `[::1]`. |
| `internal_error` | 500 | door | A bug. The message is generic; the traceback is in the server's log. |
| `missing_extra` | 501 | tool | An extra this call needs is not installed; `extra` names it. |
| `fetch_failed` | 502 | tool | Every rung failed, or the site answered with its error, a 4xx or a 5xx, which the message names: an error page is not the page. Retryable, unless what failed would fail again: a redirect loop, an encoding this install cannot read, a 4xx other than 429. `fetch_page` and `audit_page` answer about an error page as it is, with its status in `fetch`. |
| `timed_out` | 504 | door | The request ran past `--timeout`. At `/mcp`, a body that took longer to arrive; a tool call past it is a failed call. Retryable. |

`retryable` is true for `fetch_failed` and `timed_out` only: the same call may
work later. Not every `fetch_failed` is: one whose every rung was answered
with what it would be answered again -- a redirect loop, an encoding this
install cannot read, an empty page -- is not retryable. Every other code
needs something to change first.

### A page that drifted is a 200

`run_extractor` on a page that broke its extractor answers `ok` false with
`failed`, and `heal_extractor` that lost data answers `ok` false with `lost`.
Neither has an `error`, and both are sent with 200. The request did what it
asked: the tool read the page, checked it against what it learnt, and its
answer is that the page drifted. That finding is what the call is for: a 4xx
would tell a client to fix a request that was right, and a 5xx would send a
retrying proxy round again for the same finding. So a client checks `ok`, as an
agent does, and reads `error` when there is one; the status is for the HTTP
machinery in between.

## Safe by default

- **Loopback, and only requests addressed to it.** A page in your own browser
  can reach a server on loopback by pointing a name it owns at 127.0.0.1 (DNS
  rebinding). The browser still sends that name as `Host`, so on loopback any
  other `Host` is refused with 421.
- **JSON only.** A web page can POST `text/plain` to any address without asking
  first; it cannot send `application/json` across origins without a preflight,
  which this server never grants. So a tool never runs for a request that is
  not JSON.
- **No CORS.** A page on another origin cannot read an answer. To call it from
  a browser app you control, wrap the app in Python:

    ```python
    import uvicorn
    from starlette.middleware.cors import CORSMiddleware
    from sluicer.http_api import build_app

    app = CORSMiddleware(
        build_app(token="..."),
        allow_origins=["https://app.example"],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    uvicorn.run(app, host="127.0.0.1", port=8000)
    ```

- **A token beyond loopback**, or an explicit `--allow-unauthenticated`. The
  token is compared in constant time.
- **Private addresses refused**, as for the MCP server: see
  [Security](security.md) for what that filter covers.
- **Bounds.** A body over 16 MiB is refused, from its declared length before a
  byte is read, or as it arrives when sent in chunks. A request past its time
  budget is answered 504. Four tool calls that may fetch run at once
  (`MAX_CALLS`), and one waiting for a worker is inside its own budget;
  uvicorn answers 503 when 63 connections are inside a request.
- **A call that fetches nothing never waits behind one that does.** A call
  whose every page is handed in -- `html_or_url`, `url`, `url_or_text` or
  `pages` holding the page, not an `http(s)://` address -- runs on four
  workers of its own (`MAX_READS`). Before, four slow sites held every worker,
  and `extract_declared` on HTML handed in waited behind them for about 65
  seconds of HTTP, browser and robots.txt deadlines.

- **A connection that sends nothing is closed.** One that has not sent a
  whole request's line and headers ten seconds after it opened, or after its
  last answer (`HEAD_SECONDS`), is closed. uvicorn times a connection out only
  between two requests: measured, 64 connections that sent nothing held
  every one it serves at once, and every later request, `/health` included,
  was answered 503 for as long as they stayed. A client that sends its
  headers a byte at a time for longer is cut off too; one that sends them
  and then a slow body is not, and beyond loopback a reverse proxy in front
  is still what bounds that.
- **Nor does one hold a place a request needs.** uvicorn counts every
  connection toward its 64, one that has sent nothing included, so closing
  them at ten seconds was not enough: 64 opened again the moment each was
  closed kept `/health` at 503 on 60 probes of 60 over a minute. When a
  request arrives with every place taken, the connections that have waited
  longest for a request -- none sent, or none since their last answer -- are
  closed until there is room for it, and 64, 128 or 256 such connections
  left 60 probes of 60 answered 200. Connections that send nothing never
  close each other, so they cannot keep the server busy closing and
  accepting them. It answers 503 only when 63 connections are inside a
  request. What is left beyond loopback is a reverse proxy's: connections
  opened faster than a request's headers arrive, a file descriptor held by
  each until it is closed, and, with no token asked for, 63 requests that
  each send a slow body.

The body bound and the workers are arguments of
`sluicer.http_api.build_app` (`max_body`, `max_calls`, `max_reads`), and the 64 connections
are `MAX_CONNECTIONS`, which `serve` hands uvicorn. None is an option of the
command.

## How it is built

`sluicer.http_api.build_app` takes the server `sluicer.mcp_server.build_server`
returns and asks the SDK for its tools. `GET /v1/tools` is the SDK's own
listing; `POST /v1/tools/{name}` is the SDK's `call_tool` with the body as its
arguments, and the answer is the structured content it returns, already
checked against the tool's output schema; `/openapi.json` moves each schema's
`$defs` into `components` and leaves the rest as the SDK wrote it. No tool is
written twice, so none can drift from its MCP twin.

A call runs on a worker thread with an event loop of its own, so the time
budget does not rest on how the SDK's worker takes a cancel. The SDK runs a
tool on a worker of the loop that called it, and anyio holds a cancel from its
own scopes until that worker returns: measured, a two-second page under a
0.3-second `anyio.move_on_after` ended at 2.01 s, and under `asyncio.wait_for`
at 0.30 s, only because asyncio's own cancel is not held. The pools are also
what bound the calls still running after their 504: four that fetch, and four
that only parse.

`/mcp` is the SDK's `streamable_http_app` over the same server, stateless, its
own `Host` and `Origin` checks turned off for the door's, which, unlike the
SDK's, answer a `Host` of `localhost` with no port and refuse a page served on
another loopback port. The
server's `call_tool` is replaced by one that runs on the door's workers within
the budget, so a call over MCP and one over `POST /v1/tools/{name}` wait for
the same four workers, and the door reads the body itself before the SDK sees
it.

The suite reaches the app through starlette's TestClient and `/mcp` through
the SDK's own client over httpx2's ASGI transport, with the real SDK and no
socket, and CI runs it with the network taken away. `tests/live/api_check.py`
starts `sluicer serve` three times and asks it over a real socket: every tool
it lists, and one error of each kind a request can provoke, each answer checked
against the schema the server publishes for it. The Docker job serves from the
image. `tests/live/mcp_http_check.py` starts it twice and connects with the
`mcp` package's own client over streamable HTTP: the tools it lists against
stdio's, `extract_declared` on a fixture page handed in and fetched from a local
server, and each refusal of the door. What it does not do is in [Known limits](known-limits.md#in-the-http-api).
