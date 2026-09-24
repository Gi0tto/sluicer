# Security

## Reporting

Report a vulnerability privately through
[GitHub's security advisories](https://github.com/Gi0tto/sluicer/security/advisories/new)
on this repository, not as a public issue. You will get an answer.

## Supported versions

The latest release on PyPI. A fix ships as a new release, and its changelog
entry says what it fixed once the fix is public.

## What Sluicer touches

It is worth knowing the shape of the risk before you read the code.

Sluicer parses HTML from places you do not control, so the parser is the attack
surface. Parsing runs through `lxml`, which is widely used and maintained; we
add no HTML parsing of our own.

Sluicer executes nothing from the pages it reads. It does not evaluate
JavaScript in the base install, does not follow instructions found in a page,
and has no plugin mechanism a page could reach.

Sluicer holds no credentials. There is no API key to leak because no feature
takes one, which is a deliberate design constraint rather than an oversight.

When the optional `fetch` extra is installed, page content is fetched and, on
the higher rungs, rendered in a browser. Only over http and https: an address
or a redirect to any other scheme -- `file://`, `gopher://`, `dict://` -- is
refused before it is asked, whoever the caller is, and curl is told to speak
nothing else. That browser executes page JavaScript
in its own process. Treat fetching an untrusted URL with the same care you would
treat opening it in your own browser.

## The MCP server fetches what it is told to fetch

When the `mcp` extra is installed and the server is running, an agent can hand
it any `http://` or `https://` URL and Sluicer will request it, from wherever the
server runs. An agent may be relaying a URL it read somewhere else, and a page it
read can ask it to. The classic shape of the problem is a request aimed inward:
a cloud metadata endpoint, a service bound to localhost, a machine reachable
only from inside your network.

The server refuses those by default, and the refusal is a filter, not a wall.
Before any request it reads the host the way the client will -- an octal,
hex or percent-encoded host, a backslash before an `@`, an IPv4 address
inside an IPv6 one -- resolves it, and refuses `localhost`, `.local` and
`.internal` names and any address that is not on the public internet:
loopback, private ranges, link-local, `169.254.169.254` among them. Every
redirect is judged the same way before it is followed. The HTTP rung then
connects only to the addresses it checked, so a name that resolves differently
the second time (DNS rebinding) reaches nothing new. The browser rung sends
every request the page makes -- images, frames, `fetch()`, websockets, and each
hop of a redirect -- through the same judgement, and gives pages no service
workers. What it does not stop, and cannot from inside a library: the browser
resolves names itself, so DNS rebinding is still possible through the browser
rung. `tests/live/guard_check.py` shows a real Chromium reaching a private
server by six routes without the guard and by none with it. Set
`SLUICER_ALLOW_PRIVATE=1` to turn the filter off.

`map_site` and `crawl_site` fetch many addresses from one an agent chose: every
page, every sitemap and every hop of a redirect is judged by the same filter
before it is requested, a crawl never leaves the site it started on, and both
are bounded: ten sitemaps or 25 pages, and no request started after a minute.
A request already started when the minute is up runs to its own bound, below,
so an answer can come that much later. A sitemap is parsed with
no entity resolved and nothing fetched from inside it, and one that declares a
document type is refused, so neither an external entity nor billion laughs
reaches the parser.

So: run the MCP server where you would be willing to run `curl` with a URL
somebody else chose. If that is not acceptable in your environment, put the
egress control where it belongs, in the network, not in this library.

## The HTTP API is the same door, on a socket

`sluicer serve` (the `api` extra) answers the MCP server's tools over HTTP, and
everything above holds for it: the tools fetch what a caller names, and refuse
private addresses unless `SLUICER_ALLOW_PRIVATE=1`. A socket reaches further
than stdio, though. An MCP server over stdio answers the one process that
started it; a port answers anything that can connect to it, a web page in the
user's own browser included. So it starts closed:

- It listens on `127.0.0.1` unless told otherwise, and there it answers only
  requests whose `Host` is `localhost`, `127.0.0.1` or `[::1]`, which is what
  stops a page reaching it by pointing a name of its own at 127.0.0.1 (DNS
  rebinding).
- A tool runs only for a body sent as `application/json`, which a page on
  another origin cannot send without a preflight, and no preflight is granted:
  the server sends no CORS headers, so no other origin can read an answer
  either.
- Beyond loopback it will not start without a bearer token in
  `SLUICER_API_TOKEN`, unless `--allow-unauthenticated` says something in front
  of it already decides who may call. The token is read from the environment,
  never from the command line where `ps` shows it, and compared in constant
  time. Only `GET /health`, which says the version, answers without it.
- A body over 16 MiB is refused, a request past its time budget (120 seconds
  by default) is answered 504, and four tool calls run at once.

What it does not do: it speaks plain HTTP, so beyond one machine the token
crosses the network in the clear unless TLS is put in front of it; there is one
token, not an identity per caller, no rate limit and no log beyond uvicorn's
access log. A caller holding the token can make the machine fetch any public
URL, four calls at once, one request at a time and a second apart to any one
site. Put it where you would put a `curl` that anyone holding the token may
point.

## What a page can still do to you

It can lie. Structured data is written by the site, so a record Sluicer returns
says what the page claimed, not what is true. Every field carries the reader
that produced it precisely so you can weigh it.

It can be large. A fetched page is bounded at 16 MiB (`MAX_RESPONSE_BYTES`):
the HTTP rung stops reading there, after decompression, and a browser's page
heavier than that is refused once loaded. Before 0.3.0 there was no bound, and a
200 MB response was measured holding 1.14 GB. HTML handed to the MCP server
directly is held to the same bound. What it hands an agent is at most 60,000
characters of a page or its markdown at a time, and an `extract_declared`
answer at most 75,000 bytes, which bounds the agent's context.

It can be slow. A plain HTTP request ends twenty seconds after it started,
connecting, every redirect hop and every byte of the body included
(`HTTP_TIMEOUT_SECONDS`). Before 0.7.1 that bound did not reach the body: a
server sending eight bytes a second held a request as long as it kept sending,
and four such requests held every worker of `sluicer serve`, so it answered
nothing else. A browser page is bounded by the browser's own timeout, thirty
seconds for each thing it waits on (`BROWSER_TIMEOUT_MS`). A fetch makes a few
such requests -- the site's robots.txt, then each rung it climbs -- and each
keeps its own bound; nothing bounds the name lookups, which are the system
resolver's.
