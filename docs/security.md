# Security

## Reporting

Report a vulnerability privately through GitHub's security advisories on this
repository, not as a public issue. You will get an answer.

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
the higher rungs, rendered in a browser. That browser executes page JavaScript
in its own process. Treat fetching an untrusted URL with the same care you would
treat opening it in your own browser.

## The MCP server fetches what it is told to fetch

When the `mcp` extra is installed and the server is running, an agent can hand
`fetch_page` any `http://` or `https://` URL and Sluicer will request it, from
wherever the server runs. There is no allowlist and no blocklist.

That matters more than it would for a command a person types, because an agent
may be relaying a URL it read somewhere else, and a page it read can ask it to.
The classic shape of the problem is a request aimed inward: a cloud metadata
endpoint, a service bound to localhost, a machine reachable only from inside
your network.

We do not ship a partial defence. A blocklist of private ranges looks like
protection and is not one: a name can resolve to an internal address, and it can
resolve differently on the second lookup than on the first, which the ladder
does not control. Saying so plainly is more useful than a filter that would be
trusted more than it deserves.

So: run the MCP server where you would be willing to run `curl` with a URL
somebody else chose. If that is not acceptable in your environment, put the
egress control where it belongs, in the network, not in this library.

## What a page can still do to you

It can lie. Structured data is written by the site, so a record Sluicer returns
says what the page claimed, not what is true. Every field carries the reader
that produced it precisely so you can weigh it.

It can be large. There is no size limit on input in this slice; a deliberately
enormous document will use memory in proportion.
