# Moving from extruct

extruct reads the vocabularies a page declares and returns each as the page
wrote it. It has had no release since 8 November 2024. `sluicer.compat.extruct`
answers extruct's calls with extruct's shapes, so the move is one line:

```python
from sluicer.compat import extruct      # was: import extruct

data = extruct.extract(html, base_url=url)
data["json-ld"], data["microdata"], data["opengraph"], data["rdfa"]
```

```bash
uv pip install "sluicer[microformats]"  # mf2py, for the microformat syntax
uv pip install sluicer                  # without it: syntaxes=[...] leaving it out
```

`extract` takes every argument extruct's does -- `base_url`, `encoding`,
`syntaxes`, `errors`, `uniform`, `return_html_node`, `schema_context`,
`with_og_array`, and the deprecated `url` -- and a page as text, bytes or an
`lxml.html` tree. The extractor classes are under extruct's module names:
`JsonLdExtractor` in `sluicer.compat.extruct.jsonld`, `MicrodataExtractor` in
`.w3cmicrodata` with its `nested`, `strict`, `add_text_content` and
`add_html_node` options, `OpenGraphExtractor` in `.opengraph`, `RDFaExtractor`
in `.rdfa`, `MicroformatExtractor` in `.microformat`, `DublinCoreExtractor` in
`.dublincore`, and the uniform functions in `.uniform`.

What it installs is sluicer's base, three packages, and mf2py's twelve for
microformats, where extruct brings twenty-one: RDFa is read by sluicer's own
processor, with no rdflib and no pyRdfa, and the only reader borrowed is
mf2py, which extruct uses too.

Not there: `RDFaExtractor(expanded=False)`, rdflib's compacted form, raises
`ValueError`; `XmlDomHTMLParser` and extruct's command line are not provided.

## Measured

<!-- measured by bench/extruct_compat.py: start -->
Measured with extruct 0.18.0 on Python 3.14, by `bench/extruct_compat.py`. A cell is the pages on which the two answers are identical, out of the pages in the corpus; for RDFa, the same graph.

| syntax | WCXB, as served | Zyte's product pages | sluicer's test fixtures |
|---|---|---|---|
| JSON-LD | 356 / 360 | 140 / 140 | 20 / 20 |
| microdata | 358 / 360 | 138 / 140 | 20 / 20 |
| OpenGraph | 360 / 360 | 140 / 140 | 20 / 20 |
| RDFa | 360 / 360 | 140 / 140 | 20 / 20 |
| microformats | 360 / 360 | 140 / 140 | 20 / 20 |
| Dublin Core | 47 / 360 | 6 / 140 | 19 / 20 |
| uniform microdata | 358 / 360 | 138 / 140 | 20 / 20 |
| uniform OpenGraph | 360 / 360 | 140 / 140 | 20 / 20 |
| uniform microformats | 360 / 360 | 140 / 140 | 20 / 20 |
| uniform Dublin Core | 47 / 360 | 6 / 140 | 19 / 20 |

`extruct.extract(html, base_url=url)`, every argument else at its default, raises on 4 of the 520 pages; sluicer's raises on none. The same call over every page took 28.7 s in extruct and 25.9 s in sluicer.

Every difference, by what explains it:

| syntax | explained by | pages | who is right | for example |
|---|---|---|---|---|
| JSON-LD | extruct raises | 4 | sluicer: extruct raises on a JSON-LD block that is not JSON, or holds only whitespace, and with `errors="strict"` that block loses every syntax on the page; sluicer skips the block | lafeeca.com/products/dj-electric-kettle |
| microdata | an address attribute that is absent | 1 | sluicer: the standard's value is `""`; extruct answers the page's own URL | inmotionhosting.com/support/edu/mediawiki/install-mediawiki-manually/ |
| microdata | `<time>` without `datetime` | 1 | sluicer: extruct answers `""`; the standard's value is the text | taketinyaction.com/debt-free-my-4-year-journey-to-financial-freedom/ |
| microdata | `itemref` | 2 | sluicer: extruct lists the item named as top-level and gives the property naming it `null`; the WHATWG standard nests it | pokupki.market.yandex.ru/product/luminarc-nabor-stakanov-octime-330-ml-6-sht-h9811/140212369 |
| Dublin Core | not Dublin Core | 448 | sluicer: extruct files any name after its last dot, so `description`, `title` and `rel="license"` are Dublin Core to it | nytimes.com/wirecutter/reviews/best-laptop-under-500/ |

extruct answers Dublin Core on 448 of the 520 pages; 2 of them write a name under a Dublin Core prefix.
Uniform mode differs on exactly the pages the syntax it reshapes differs on, for the same reasons.
<!-- measured by bench/extruct_compat.py: end -->

`uv run bench/extruct_compat.py` regenerates this section. It installs extruct in an
environment of its own from `bench/requirements/extruct.txt`, never beside
sluicer, and fails if a difference is one no test in it explains.

## Where the answers differ

Each of these is a place where extruct's answer is wrong and sluicer's is not,
and the module named says how it is read.

- **A JSON-LD block that is not JSON** (`jsonld`). extruct raises, and with its
  default `errors="strict"` that one block loses every syntax on the page; with
  `"log"` or `"ignore"` it loses every block of JSON-LD on the page. sluicer
  reads blocks as its own reader does -- a comment or CDATA wrapper, a byte
  order mark, JavaScript's comments, a trailing comma and a media type in
  another case forgiven -- and skips a block that is still not JSON, keeping
  the rest.
- **Dublin Core** (`dublincore`). extruct files whatever follows a name's last
  dot, so `<meta name="description">`, `name="title"`, `citation.date` and
  `<link rel="license">` are Dublin Core elements to it. sluicer counts a name
  whose prefix is `DC`, `DCTERMS`, or one the page declares for a Dublin Core
  namespace with `<link rel="schema.X">`. `<meta name="description">` is on
  most pages, so this is the difference seen most often.
- **`itemref`** (`w3cmicrodata`). extruct reads an item named by `itemref`
  from further down the page as a top-level item, and the property naming it
  is `null`; so is every property naming an item a second time, as two
  products sharing one brand do. sluicer nests the item in each item that names
  it, as the WHATWG standard does, never lists it as top-level, and orders
  properties in tree order.
- **`<time>` without `datetime`** (`w3cmicrodata`). extruct answers `""`; the
  standard's value is the element's text.
- **An address attribute that is absent** (`w3cmicrodata`). `<a itemprop>`
  with no `href` is `""` in the standard; extruct resolves nothing against the
  page's address and answers the page's own URL. An address that is present
  is resolved with `urljoin`, as extruct resolves it, and so as the running
  Python's `urljoin` does: 3.14 keeps an empty `#` or `?` that 3.13 drops.
- **`<base href>`** (`w3cmicrodata`). The standard resolves a microdata address
  against the document's base URL, which `<base href>` sets; extruct resolves
  it against `base_url` alone.
- **Bytes in another encoding** (`page`). extruct makes libxml2 read bytes as
  UTF-8 whatever the page declares, so a windows-1252 page loses its accents
  to U+FFFD even when its `<meta charset>` says windows-1252. sluicer believes
  the `encoding` passed when the bytes are valid in it -- UTF-8, the default,
  exactly when they are UTF-8 -- and otherwise decodes them as a browser does.
- **RDFa blank nodes and order** (`rdfa`). extruct names blank nodes at random
  and orders nodes and values by rdflib's hash sets, which Python seeds per
  process, so its answer changes from one run to the next. sluicer's is
  `_:b0`, `_:b1`, ... in the order they appear, with nodes and values in
  document order. The graph is the same, and it is compared as a graph.
- **Pages nested deep.** libxml2, as extruct calls it, stops at 256 levels of
  nesting and drops everything below, JSON-LD included; sluicer parses with
  `huge_tree`, as its own reader does. Microdata items nested about four
  hundred deep raise `RecursionError` in extruct; here an item nested more than
  64 deep is left out.
- **Pages extruct raises on.** An address `urljoin` refuses -- the
  `https://[domain]/` of an unfilled template, in a microdata `href`, an RDFa
  address or a `<base href>` mf2py reads -- an `xml:lang` rdflib refuses, such
  as `en_US`, and a `str` that carries an XML encoding declaration each raise
  in extruct. Here the address is kept as written, the language as declared,
  and the text is read; a page whose `<base href>` mf2py refuses declares no
  microformats. No page makes a syntax raise, so `errors` matters only for
  microformats without mf2py. A page whose answer would copy more than ten
  times the page -- properties nested in properties, each holding all the
  text below it -- gets the start of its answer, in document order.

## Reproduced on purpose

Some of extruct's answers are not what a standard says, and are kept, because
a caller of extruct has written code against every one of them.

- RDFa is read as extruct configures pyRdfa: as RDFa Core, not HTML+RDFa, so
  `lang` gives no literal a language (`xml:lang` does), `<base href>` is not
  read and a `<time>` is not typed; `role` attributes are statements, and a
  root whose `version` says RDFa 1.0 is read as 1.0.
- OpenGraph is the `<meta property>` tags that are children of `<head>`, and
  nothing in `<body>` or in `name=`.
- A microdata item's text is laid out as html-text lays it out, with line
  breaks around blocks.
- A Dublin Core name among the fifteen elements is an element, even written
  `DCTERMS.`.
- Uniform mode keeps extruct's reshaping, including an untyped microdata item's
  unflattened `properties` and the Dublin Core `@type` read from any attribute
  value ending in `type`.

For the records sluicer builds from the same declarations -- one per thing,
every field naming the vocabulary it came from -- call `sluicer.extract`.
