# Conformance: JSON-LD in HTML

The W3C's JSON-LD 1.1 test suite has 50 tests of JSON-LD inside HTML:
which of a page's scripts a processor extracts (the first, the one a
fragment names, or all of them), which script text is an error, which
base IRI the page sets, and what expanding, compacting, flattening or
turning the result into RDF gives. Sluicer's JSON-LD reader, its extruct
interface and extruct itself read every page; each answer, as the reader
gives it, is processed by PyLD, a JSON-LD processor, with the test's
options, and compared with the suite's expected result by the suite's
own rules.
Regenerated on 2026-09-26 from commit `5e97f6b` by
`uv run bench/w3c_jsonld.py`, against the suite at `ffdb326121ea`; the
rules are in [`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md).

!!! warning "Read this before the numbers"
    A reader of JSON-LD is not a JSON-LD processor, and these are a
    processor's tests. A reader is given a page and its address and
    answers the JSON its scripts hold; it takes no option, so it cannot
    be told to read only the first script or the one a fragment names,
    and its answer carries no base IRI. Every test that asks for one of
    those fails for every reader alike, and is listed below as such.
    What the page measures is what a reader's answer keeps of what a
    processor needs: the scripts' JSON as written, and a refusal where
    the text is not JSON-LD.

## Results

Tests passed, of the 50, with the Wilson interval of the
share. PyLD reading every page itself is the check that the harness
scores a processor as the suite does: it passes 49 of
50.

| reads the page | all | expand (21) | compact (4) | flatten (5) | toRdf (20) | negative tests |
|---|---|---|---|---|---|---|
| PyLD 3.3.0 | 0.980 (0.89–1.00) | 21/21 | 4/4 | 4/5 | 20/20 | 15/15 |
| Sluicer's JSON-LD reader 0.10.0 | 0.480 (0.34–0.62) | 11/21 | 1/4 | 2/5 | 10/20 | 7/15 |
| sluicer.compat.extruct 0.10.0 | 0.660 (0.52–0.78) | 15/21 | 2/4 | 2/5 | 14/20 | 13/15 |
| extruct 0.18.0 | 0.660 (0.52–0.78) | 15/21 | 2/4 | 2/5 | 14/20 | 13/15 |

21 of the tests ask for what no reader's answer can give: a script named by its fragment, the first of several scripts alone, or the base a page's `<base href>` sets. On the other 29, which a reader passes or fails by what it answers, Sluicer's JSON-LD reader 0.690 (0.50–0.83), sluicer.compat.extruct 1.000 (0.88–1.00) and extruct 1.000 (0.88–1.00).

| first | against | difference in tests passed (95% interval) | verdict |
|---|---|---|---|
| Sluicer's JSON-LD reader 0.10.0 | extruct 0.18.0 | -0.180 (-0.300 to -0.079) | worse |
| Sluicer's JSON-LD reader 0.10.0 | sluicer.compat.extruct 0.10.0 | -0.180 (-0.300 to -0.079) | worse |

The difference is the first side's rate minus the second's, over the
same pages. Its interval is the 95% percentile interval of 10,000
resamples of the pages, drawn together for both sides (`bench/stats.py`,
seed 20260924): **better** when the interval is above zero, **worse**
when it is below, **inconclusive** when it holds zero. These are
2 comparisons, made with no correction for making many: where two
sides did not differ at all, about one in twenty would still be called
better or worse, so read the verdicts as a table, not one at a time.

## Where Sluicer's JSON-LD reader fails

26 tests fail. By the first reason that holds, 8 name one script by its fragment, 6 want an error the reader did not give, 5 want the first of several scripts, 4 set their base with the page's `<base href>` and 3 hold a `@graph` the reader answers node by node.

| test | what it asks | the answer | why it fails |
|---|---|---|---|
| `te002` | Expands first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (3 values). |
| `te003` | Expands targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (3 values). |
| `te004` | Expands all embedded JSON-LD script elements with extractAllScripts option | differs | The reader answers the nodes of a script's `@graph` one by one, each with the script's `@context`: the same statements, in the page's default graph, where a processor given every script puts them in a graph of their own. |
| `te011` | Errors if no element found at target | answered | The test names the script `#third`; a reader is given no fragment and answers every script (3 values). |
| `te014` | Errors if uncommented script text contains comment | answered | The test wants the error `invalid script element`: the script is not JSON-LD as written. The reader mended it and answered 1 value. |
| `te015` | Errors if end comment missing | answered | The test wants the error `invalid script element`: the script is not JSON-LD as written. The reader mended it and answered 1 value. |
| `te016` | Errors if start comment missing | answered | The test wants the error `invalid script element`: the script is not JSON-LD as written. The reader mended it and answered 1 value. |
| `te020` | Expands embedded JSON-LD script element relative to HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `te021` | Expands embedded JSON-LD script element relative to relative HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `te022` | Expands targeted JSON-LD script element with fragment and HTML base | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |
| `tc002` | Compacts first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (3 values). |
| `tc003` | Compacts targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (3 values). |
| `tc004` | Compacts all embedded JSON-LD script elements with extractAllScripts option | differs | The reader answers the nodes of a script's `@graph` one by one, each with the script's `@context`: the same statements, in the page's default graph, where a processor given every script puts them in a graph of their own. |
| `tf002` | Flattens first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (3 values). |
| `tf003` | Flattens targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (3 values). |
| `tf004` | Flattens first script element by default | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (3 values). |
| `tr002` | Transforms first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (3 values). |
| `tr003` | Transforms targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (3 values). |
| `tr004` | Expands all embedded JSON-LD script elements with extractAllScripts option | differs | The reader answers the nodes of a script's `@graph` one by one, each with the script's `@context`: the same statements, in the page's default graph, where a processor given every script puts them in a graph of their own. |
| `tr011` | Errors if no element found at target | answered | The test names the script `#third`; a reader is given no fragment and answers every script (3 values). |
| `tr014` | Errors if uncommented script text contains comment | answered | The test wants the error `invalid script element`: the script is not JSON-LD as written. The reader mended it and answered 1 value. |
| `tr015` | Errors if end comment missing | answered | The test wants the error `invalid script element`: the script is not JSON-LD as written. The reader mended it and answered 1 value. |
| `tr016` | Errors if start comment missing | answered | The test wants the error `invalid script element`: the script is not JSON-LD as written. The reader mended it and answered 1 value. |
| `tr020` | Expands embedded JSON-LD script element relative to HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `tr021` | Expands embedded JSON-LD script element relative to relative HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `tr022` | Expands targeted JSON-LD script element with fragment and HTML base | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |

## Where sluicer.compat.extruct fails

17 tests fail. By the first reason that holds, 8 name one script by its fragment, 5 want the first of several scripts and 4 set their base with the page's `<base href>`.

| test | what it asks | the answer | why it fails |
|---|---|---|---|
| `te002` | Expands first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (2 values). |
| `te003` | Expands targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |
| `te011` | Errors if no element found at target | answered | The test names the script `#third`; a reader is given no fragment and answers every script (2 values). |
| `te020` | Expands embedded JSON-LD script element relative to HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `te021` | Expands embedded JSON-LD script element relative to relative HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `te022` | Expands targeted JSON-LD script element with fragment and HTML base | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |
| `tc002` | Compacts first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (2 values). |
| `tc003` | Compacts targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |
| `tf002` | Flattens first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (2 values). |
| `tf003` | Flattens targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |
| `tf004` | Flattens first script element by default | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (3 values). |
| `tr002` | Transforms first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (2 values). |
| `tr003` | Transforms targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |
| `tr011` | Errors if no element found at target | answered | The test names the script `#third`; a reader is given no fragment and answers every script (2 values). |
| `tr020` | Expands embedded JSON-LD script element relative to HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `tr021` | Expands embedded JSON-LD script element relative to relative HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `tr022` | Expands targeted JSON-LD script element with fragment and HTML base | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |

## Where extruct fails

17 tests fail. By the first reason that holds, 8 name one script by its fragment, 5 want the first of several scripts and 4 set their base with the page's `<base href>`.

| test | what it asks | the answer | why it fails |
|---|---|---|---|
| `te002` | Expands first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (2 values). |
| `te003` | Expands targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |
| `te011` | Errors if no element found at target | answered | The test names the script `#third`; a reader is given no fragment and answers every script (2 values). |
| `te020` | Expands embedded JSON-LD script element relative to HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `te021` | Expands embedded JSON-LD script element relative to relative HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `te022` | Expands targeted JSON-LD script element with fragment and HTML base | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |
| `tc002` | Compacts first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (2 values). |
| `tc003` | Compacts targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |
| `tf002` | Flattens first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (2 values). |
| `tf003` | Flattens targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |
| `tf004` | Flattens first script element by default | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (3 values). |
| `tr002` | Transforms first embedded JSON-LD script element | differs | The test wants the first of the page's 2 scripts; the reader answers all of them (2 values). |
| `tr003` | Transforms targeted JSON-LD script element | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |
| `tr011` | Errors if no element found at target | answered | The test names the script `#third`; a reader is given no fragment and answers every script (2 values). |
| `tr020` | Expands embedded JSON-LD script element relative to HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `tr021` | Expands embedded JSON-LD script element relative to relative HTML base | differs | The page's `<base href>` sets the base IRI; a reader's answer does not carry it, so it is read against the page's address. |
| `tr022` | Expands targeted JSON-LD script element with fragment and HTML base | differs | The test names the script `#second`; a reader is given no fragment and answers every script (2 values). |

## Where PyLD fails

| test | what it asks | the answer | why it fails |
|---|---|---|---|
| `tf004` | Flattens first script element by default | differs |  |

## Method

- **Suite.** [`w3c/json-ld-api`](https://github.com/w3c/json-ld-api) at commit `ffdb326121ea`, `tests/html-manifest.jsonld` and the pages
  and expected results it names, under the W3C Software and Document
  License. Downloaded into `bench/cache/`, never committed here.
- **Readers.** Each is given the page's bytes and its address,
  `https://w3c.github.io/json-ld-api/tests/` and the test's input, its
  fragment included. Sluicer's reader is `read_jsonld` on
  `sluicer.document.load(html, url=...)`, what Sluicer's records are
  made from; the other two are `extract(html, base_url=url,
  syntaxes=["json-ld"])`. Sluicer's reader answers a number as the
  text the page wrote, `41.90` and not `41.9`, since a record holds
  every value as text; a processor reads that as a string. None of
  these pages writes a number.
- **Processing.** The answer, a list of values, is the document PyLD
  expands, compacts (with the test's context), flattens or turns into
  N-Quads, with the test's `base` option or else the page's address as
  its base, and JSON-LD 1.1's processing mode.
- **Comparison.** The suite's JSON-LD object comparison: objects member
  by member, arrays in any order but a `@list`'s, language tags in any
  case; flattened results also with blank nodes relabelled, when they
  are the same graph; RDF by canonical N-Quads (URDNA2015).
- **Negative tests.** A processor must raise the test's error. A
  reader passes one by answering nothing or by raising.
- **PyLD** reads each page itself through a document loader that serves
  the suite from disk, with the test's options, `extractAllScripts`
  included; it passes a negative test only with the test's error code.
- **Environments.** Python 3.12; extruct from `bench/requirements/extruct.txt`, PyLD from
  `bench/requirements/pyld.txt`, Sluicer from this checkout.
