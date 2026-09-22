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

## What a page can still do to you

It can lie. Structured data is written by the site, so a record Sluicer returns
says what the page claimed, not what is true. Every field carries the reader
that produced it precisely so you can weigh it.

It can be large. There is no size limit on input in this slice; a deliberately
enormous document will use memory in proportion.
