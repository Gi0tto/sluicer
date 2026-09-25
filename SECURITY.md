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

Sluicer holds no credentials of its own. There is no API key to leak because no
feature needs one, which is a deliberate design constraint rather than an
oversight. A header or cookie you hand a fetch (`headers=`, `cookies=`,
`--header`, `--cookie`) is sent to the origin you asked for -- scheme, host and
port -- and left off every hop a redirect takes elsewhere; in the browser, a
cookie is set for the host asked and follows the browser's cookie rules, under
which a cookie belongs to a host, not a port, and one set for https is sent
over https alone. The origin is the one you named, fixed before the first
request: a crawl sends it to the origin it starts at and to no other address
of the site -- not its `www.` twin, not its pages over plain http -- a batch
to the origins of the addresses you list, and no robots.txt, nor a sitemap
another host serves, is sent it. robots.txt is read as anyone reads it. It
is never written to disk: the
page cache keys a page fetched with one by a digest of what was sent. The page
itself is kept, as every page the cache keeps, in a file only you can read
(0600), in a directory it makes only yours (0700), whatever the umask; before,
under the usual one, a page read behind a login was 0644 in a 0755 directory,
readable by anyone on the machine. A cache directory that exists already keeps
its mode, since it is yours and may be shared on purpose, and a page kept
before stays as it was until it is written again. Windows has no such modes.
The MCP server and the HTTP API take none.

A user and password written in the address itself
(`https://user:password@host/page`) are sent to that origin, as curl sends
them, and to its robots.txt, and never repeated: every error a fetch raises
and its `url`, the address a fetched page hands back and its climbs, the MCP
server's and the HTTP API's answers, the command line's messages, a batch's
lines and the cache's entries write it `user:***`, as a proxy's password
already was. The cache still keeps two logins' pages apart, by a digest of
the whole address. Before, 0.7.1 included, each of them repeated the
password, and `--at` put the whole address in the path of its request to the
Wayback Machine, which is now asked for the page without it, as are a site's
`llms.txt` and TDMRep file. A crawl takes no address with a login in it.

A configuration file (`sluicer.toml`, or `[tool.sluicer]` in
`pyproject.toml`) is read by the command line only. One found by searching the
directories above the one you run in may be a repository's you cloned, so it
may not set a proxy, a header, a cookie, the cache directory, `serve`'s host
or `no-robots`: those come only from a file you name with `--config` or
`SLUICER_CONFIG`, and a file found that tries is refused before anything runs.
A found file that another user owns or can write, through its mode or a macOS
access list, is refused too. In 0.8's first form a cloned repository's
`pyproject.toml` could set `proxy`, and a `--cookie` session given on the
command line went through that proxy in plain HTTP.

Since 0.8 the base install fetches over plain HTTP, with Python's own
`http.client`, `ssl` and `socket`: no native HTTP library, and certificates
verified against the system's store. Only http and https: an address or a
redirect to any other scheme -- `file://`, `gopher://`, `dict://` -- is refused
before it is asked, whoever the caller is, and the client speaks nothing else.
With the `browser` extra, a page plain HTTP brings back as an empty shell is
rendered in Playwright's Chromium, which executes page JavaScript in its own
process, in a new context per page, in Chromium's sandbox. Playwright launches
Chromium with `--no-sandbox` unless told otherwise, and until 0.8 it was not
told. The sandbox needs unprivileged user namespaces: a container needs a
seccomp profile that allows them (or `--cap-add SYS_ADMIN`), and Ubuntu 23.10
and later lets only the programs AppArmor names have them
(`sysctl kernel.apparmor_restrict_unprivileged_userns=0`). Where it cannot
start, the browser rung fails and says so; `SLUICER_BROWSER_SANDBOX=0` runs
the browser without it, the machine or the container then its only boundary.
Treat fetching an untrusted URL with the same care you would treat opening it
in your own browser. The `stealth` extra
(scrapling's patched Chromium) runs only for one page a person asked for with
`--stealth`, never for the MCP server, the HTTP API or a crawl.

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
loopback, private ranges, link-local, `169.254.169.254`, multicast among them. Every
redirect is judged the same way before it is followed. The HTTP rung then
connects only to the addresses it checked, so a name that resolves differently
the second time (DNS rebinding) reaches nothing new; a connection it keeps open
for the site's next request is used again only while the address it reached is
still among the ones checked. The browser rung sends
every request the page makes -- images, frames, `fetch()`, websockets, and each
hop of a redirect -- through the same judgement, and gives pages no service
workers and no WebRTC. The browser also makes requests for a page that no
route of the page sees: until 0.8, a speculation rule's prefetch and
prerender -- written in the page, sent in a `Speculation-Rules` header, added
by a script, aimed at another site -- and a WebRTC connection to a STUN or a
TURN server reached a private address with the guard installed. So every
connection of a guarded page, the browser's own for it included, goes
through a proxy Sluicer runs on this machine's loopback, which judges each
host and port by the same rule and connects only to the addresses it
checked; Chromium is told not to pass loopback by it, and WebRTC's UDP, which
no proxy carries, is off. The browser then resolves no name itself, so a name
that answers differently the second time (DNS rebinding) reaches nothing new
through it either. `tests/live/guard_check.py` has a real Chromium try
thirteen routes to a private server -- six reach it without the guard -- and
none does. A browser driven over the DevTools protocol (`SLUICER_CDP_URL`)
runs elsewhere and cannot reach this machine's loopback, so it is given no
guard proxy: the routes still judge every request the page makes, by this
machine's resolver -- "private" then means private as seen from here, not
from the browser's network -- but a speculation rule's requests, and a name
that rebinds, reach past them there. Set `SLUICER_ALLOW_PRIVATE=1` to turn
the filter off.

No proxy is used unless one is asked for. Until 0.7.1 a fetch went through
whatever proxy the environment named (libcurl read `HTTPS_PROXY` itself), the
browser through the system's; now only a proxy given as `fetch(proxy=...)`,
`--proxy` or `SLUICER_PROXY` is used -- `http://`, `socks5://` or `socks5h://`
-- and without one the browser is launched with `--no-proxy-server`. Through a
proxy, the filter above holds less, and exactly this much:

- It still judges every address before it is requested, the one asked for and
  each hop of a redirect, by resolving the name on this machine: a name that
  resolves here to a private address is refused, and so is a name that does
  not resolve here at all, since it cannot be judged.
- It no longer pins the connection, except through `socks5://`, where the
  address checked here is the one the proxy is told. Otherwise the proxy
  looks the name up again in its own network and connects where that answer
  says, so a name that answers
  differently the second time (DNS rebinding) reaches whatever the proxy can
  reach, and "private" means private as seen from this machine, not from the
  proxy's. A proxy inside another network can reach that network's private
  addresses by a public name.
- The proxy's own address is not judged: it is the one you named.

If the proxy can reach something the filter is meant to keep Sluicer from,
the egress control belongs in the proxy.

`map_site` and `crawl_site` fetch many addresses from one an agent chose: every
page, every sitemap and every hop of a redirect is judged by the same filter
before it is requested, a crawl never leaves the site it started on, and both
are bounded: ten sitemaps or 25 pages, and no request started after a minute.
A request already started when the minute is up runs to its own bound, below,
so an answer can come that much later. A sitemap is parsed with
no entity resolved and nothing fetched from inside it, and one that declares a
document type is refused, so neither an external entity nor billion laughs
reaches the parser.

A selector an agent writes is a small program run on the server's CPU: XPath
lets one line cost the square or the cube of a page's size, and so does
ordinary CSS. The tools evaluate a caller's selectors in a process of their
own, started with `python -I` so that nothing in the server's working
directory is imported, and killed after 30 seconds
(`sluicer.isolated.SECONDS`), or sooner when the call's budget over HTTP,
below, ends first; such a call is answered `bad_input`. Four hostile selectors
can still keep `sluicer serve`'s four reading workers busy for those 30
seconds at a time: beyond loopback, put it behind a proxy that limits each
client. The
command line and the library evaluate selectors in their own process: run an
extractor file only from someone you would let run code that long.

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
- `/mcp`, the MCP server over streamable HTTP, is behind the same checks and
  one more, which MCP's transport requires: a request whose `Origin` is not
  this server's own is refused with 403 before anything runs. A browser sends
  an `Origin`; n8n's and Dify's clients, which are not browsers, send none.
  Only a POST is answered: a GET would hold open a stream the stateless server
  never writes to.
- A body over 16 MiB is refused, a request past its time budget (120 seconds
  by default) is answered 504, at `/mcp` a body that takes longer than that to
  arrive included, and four tool calls that may fetch run at once. A call that fetches nothing, its every page handed in, runs on four
  workers of its own, so slow sites cannot hold it back.
- A caller's selectors -- `select_values`, and `compile_extractor`,
  `run_extractor` and `heal_extractor` with an extractor written by
  selectors -- are evaluated in a process of their own, killed when the
  call's time budget ends (`sluicer.isolated`). XPath lets one line cost the
  cube of a page's size, `//p[count(//p[count(//p) > 0]) > 0]` on 3,000
  paragraphs, and CSS's `p ~ p` took 110 s on 8,000; lxml evaluates both in
  C, which no thread can stop. Before this, four such calls held every
  worker for as long as they ran, and the server answered every later call
  504.
- A connection that sends nothing holds no place a request needs. uvicorn
  answers 503 beyond 64 connections (`MAX_CONNECTIONS`) and counts one that
  has sent nothing among them: in 0.8's first form, 64 sockets that sent
  nothing, each opened again the moment it was closed at ten seconds, had
  `/health` answered 503 on 60 probes of 60 over a minute, with no token
  needed. Now a connection that has not sent a request's headers within ten
  seconds of opening, or of its last answer, is closed (`HEAD_SECONDS`), and
  when a request arrives with every place taken, the connections that have
  waited longest for a request are closed to make room for it: the same 64,
  and 128 and 256, left 60 probes of 60 answered 200. The server answers 503
  only when 63 connections are inside a request, and without the token a
  request is refused before its body is read.

What it does not do: it speaks plain HTTP, so beyond one machine the token
crosses the network in the clear unless TLS is put in front of it; there is one
token, not an identity per caller, no rate limit and no log beyond uvicorn's
access log. Nor does it bound connections by who opens them: a request that
arrives while connections are being opened faster than its headers, or 63
requests that send a slow body where no token is asked for (loopback, or
`--allow-unauthenticated`), still keep others waiting or at 503, and
connections that send nothing still cost a file descriptor each until they
are closed. Beyond loopback, a reverse proxy in front that limits
connections per client is what bounds those. A caller holding the token can make the machine fetch any public
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
directly is held to the same bound. No answer it hands an agent weighs more
than 75,000 bytes of JSON (`MOST_ANSWER_BYTES`), which bounds the agent's
context: a page or its markdown is read in slices of at most 60,000
characters, shorter when their bytes would pass the bound, and a tool leaves
out, and counts, the records, rows, items or addresses past it. An answer
that cannot be cut is refused as `too_large`. Before 0.7.1 only
`extract_declared`'s records were bounded: a page with a two-megabyte
`<title>` made a two-megabyte answer.

It can be slow. A plain HTTP request ends twenty seconds after it started,
looking the name up, connecting, every redirect hop and every byte of the body
included (`HTTP_TIMEOUT_SECONDS`): every wait on the connection is given what is
left of that, however slowly the server sends. Before 0.7.1 that bound did not reach the body: a
server sending eight bytes a second held a request as long as it kept sending,
and four such requests held every worker of `sluicer serve`, so it answered
nothing else. A browser page is bounded by the browser's own timeout, thirty
seconds for each thing it waits on (`BROWSER_TIMEOUT_MS`). A fetch makes a few
such requests -- the site's robots.txt, then each rung it climbs -- and each
keeps its own bound. The HTTP rung's own name lookups are inside its twenty
seconds since 0.8; the one the ladder makes to judge the address before any
request (`allow_private=False`) is the system resolver's, and not bounded.
