# The HTTP API

`sluicer serve` answers the MCP server's tools over HTTP, one address per
tool, so any language that can send a POST can use Sluicer. They are the ten
tools an agent gets, each in the [MCP reference](reference/mcp.md), with the
same arguments, the same answers and the same output schemas, because it is
built from them: an HTTP call goes through the MCP SDK's own `call_tool`, argument
validation and output-schema check included. A tool the MCP server gains is
served here with nothing else to change.

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
| `--timeout` | `120` | Seconds a request may take, its body included, before it is answered 504. |
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

The image carries the extra. Inside a container the server has to listen on
every interface to be reachable through a published port, so it needs a token:

```bash
docker build -t sluicer .
docker run --rm -p 127.0.0.1:8000:8000 -e SLUICER_API_TOKEN="$SLUICER_API_TOKEN" \
  sluicer sluicer serve --host 0.0.0.0
```

`-p 127.0.0.1:8000:8000` publishes it on the host's loopback only; write
`-p 8000:8000` to publish it on every interface of the host. Build with
`--build-arg WITH_BROWSER=1` for pages that need the browser rung.

## Call it

```bash
curl -s http://127.0.0.1:8000/v1/tools/extract_declared \
  -H "Authorization: Bearer $SLUICER_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"html_or_url": "https://example.com/product"}'
```

The body is the tool's arguments as a JSON object, exactly as an MCP client
sends them, and the answer is what the tool answers:

```json
{
  "ok": true,
  "url": "https://example.com/product",
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

A client generator pointed at `/openapi.json` gets one operation per tool,
named after it. The tools themselves, and what each argument means, are
described in the listing and in [Extractors](extractors.md).

## Answers and statuses

Every answer is a JSON object with `ok`, true exactly when the answer can be
used as it is. When the tool could not answer, `ok` is false and `error` says
why, in the shape the MCP tools use: `{"code", "message", "retryable"}`, with
`url` or `extra` when there is one. The status follows the code:

| Code | Status | From | Means |
|---|---|---|---|
| `bad_input` | 400 | tool or door | Something the tool cannot take: literal HTML to `fetch_page`, no pages, an object that is not an extractor, arguments that do not fit the input schema, a body that is not a JSON object. |
| `unauthorized` | 401 | door | No token, or the wrong one. |
| `refused_by_robots` | 403 | tool | The site's robots.txt says no. Do not work around it. |
| `refused_by_site` | 403 | tool | The site answered with a challenge page ("Just a moment..."), on every rung. Not the page, and not to be worked around. |
| `refused_address` | 403 | tool | A private address, refused unless `SLUICER_ALLOW_PRIVATE=1`. |
| `not_found` | 404 | door | No tool, or no path, by that name. |
| `method_not_allowed` | 405 | door | A tool is a POST. |
| `too_large` | 413 | tool or door | A page over 16 MiB, fetched or handed in, or a request body over 16 MiB. |
| `unsupported_media_type` | 415 | door | The body must be `application/json`. |
| `misdirected` | 421 | door | Listening on loopback, it answers only requests addressed to `localhost`, `127.0.0.1` or `[::1]`. |
| `internal_error` | 500 | door | A bug. The message is generic; the traceback is in the server's log. |
| `missing_extra` | 501 | tool | An extra this call needs is not installed; `extra` names it. |
| `fetch_failed` | 502 | tool | Every rung failed. Retryable. |
| `timed_out` | 504 | door | The request ran past `--timeout`. Retryable. |

`retryable` is true for `fetch_failed` and `timed_out` only: the same call may
work later. Every other code needs something to change first.

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
  budget is answered 504. Four tool calls run at once (`MAX_CALLS`), and one
  waiting for a worker is inside its own budget; uvicorn answers 503 beyond 64
  connections.

The body bound and the four workers are arguments of
`sluicer.http_api.build_app` (`max_body`, `max_calls`), and the 64 connections
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
at 0.30 s, only because asyncio's own cancel is not held. The pool is also what
bounds the calls still running after their 504 to four.

The suite reaches the app through starlette's TestClient, with the real SDK and
no socket, and CI runs it with the network taken away. `tests/live/api_check.py`
starts `sluicer serve` three times and asks it over a real socket: every tool
it lists, and one error of each kind a request can provoke, each answer checked
against the schema the server publishes for it. The Docker job serves from the
image. What it does not do is in [Known limits](known-limits.md#in-the-http-api).
