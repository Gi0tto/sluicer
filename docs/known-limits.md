# Known limits

Everything here is deliberate, measured, and open. It is not a bug list: it is
the set of places where Sluicer currently stops, written down so nobody has to
rediscover them, and so the next plan inherits decided questions instead of
surprises.

## In the extraction path

**Nested values never reach a record.** `merge` carries scalars only, so a
JSON-LD `offers` object or an `image` array is read by the reader and then
dropped. On a product page that means the price, which lives inside `offers`, is
visible to `read_jsonld` and absent from the record. Belongs to the structure
induction plan, which has to decide how a nested object becomes fields.

**Gap-filling targets the first record of a type.** When a page declares several
records sharing a type, a lower-precedence reader fills the first one in document
order. On a page whose `@graph` opens with a `BreadcrumbList`, an `og:title`
lands on the breadcrumb rather than the product. Document order is the only
deterministic signal available in this slice; trust scoring is where a better one
can come from.

**`load()` takes text, not bytes.** When the first parse fails it retries by
encoding to UTF-8 and telling the parser so, which keeps a document whose
declaration disagrees with its bytes from corrupting the text. Honouring a
declared encoding properly needs the original bytes, and those only exist one
layer earlier, at the fetch. Settle it in the fetch ladder plan.

**RDFa is named in the design and not implemented.** `declared` covers JSON-LD,
microdata and OpenGraph today.

## In the shape of the code

**Adding a reader touches three places.** The reader names are written into
`merge`'s keyword signature, into `_record_from`'s source labels, and into the
tuple in `api`. Adding RDFa is therefore a breaking change to a published
signature plus edits in two modules. The seam belongs one level up, as a sequence
of named findings or a registry. Worth moving before the first release, cheap
while nobody depends on it.

**A hand-built `Record` can be silently inert.** `Record(type="Product")`
constructed by hand gets an empty `types`, and the fold reads `types`, so that
record never folds with anything. Nothing validates that the two agree. A
`__post_init__` would close it.

## In the tests

**The no-model test is a floor, not a ceiling.** It scans the source for
`requests`, `httpx`, `urllib.request`, `socket`, `aiohttp`, `openai`, `anthropic`
and `google.generativeai`. It does not catch `http.client`, `ftplib`, the current
`google.genai`, or anything reached through `importlib.import_module`. It fails
loudly on the obvious ways to break the promise, which is what it is for.

**Determinism is tested within one process.** Two calls, one fixture, same
answer. Stability across processes and across two pages built from the same
template is what the design actually promises, and neither is covered yet.

## In the repository

**No linter, no type checker, no CI.** Nothing here can enforce the constraints
the design calls binding: a wrong type annotation slipped through review once
already and no gate caught it.
