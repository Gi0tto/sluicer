# RDFa, against the W3C test suite

Sluicer's two RDFa readers, and extruct's, on the RDFa test suite the W3C's RDFa working group wrote and [rdfa.info](https://rdfa.info/test-suite/) runs: every test written for HTML5, each document handed to each reader, each answer read into a graph and asked the test's own SPARQL query.

- **Sluicer's reader** is `extract()`'s, `sluicer.declared.rdfa`: RDFa Lite read into records, one per `typeof`, which name no subject and hold text and addresses, not a graph. Its records are written as triples the way a caller has to read them: each record a blank node, a short name a schema.org term, a value that begins with a scheme an address.
- **`sluicer.compat.extruct`** is the processor that answers what extruct answers, graph and all.
- **extruct 0.18.0**, in an environment holding exactly `bench/requirements/extruct.txt`, with `extract(html, base_url=url, syntaxes=["rdfa"])`.

What `extract()`'s reader leaves out on purpose -- links, `about`, typed literals, languages, the page as a subject -- is in [Known limits](known-limits.md); every test it fails is filed below under one of those, or listed as not explained.

Regenerated on 2026-09-25 from commit `354ef6b` by `uv run bench/rdfa_conformance.py`, with Sluicer 0.9.0, extruct 0.18.0 and rdflib 7.6.0 on Python 3.14, against the suite at `b388107da890` of [`rdfa/rdfa.github.io`](https://github.com/rdfa/rdfa.github.io), which is distributed under both the W3C Test Suite License and the W3C 3-clause BSD License. A test passes when its query answers what the suite expects.

| set | tests | Sluicer's reader | `sluicer.compat.extruct` | extruct 0.18.0 |
|---|---|---|---|---|
| RDFa 1.1 | 170 | 7 | 137 | 132 |
| RDFa 1.1 Lite | 54 | 5 | 30 | 30 |
| processor graph | 4 | 1 | 1 | 1 |
| vocabulary expansion | 6 | 0 | 0 | 0 |
| `role` | 3 | 0 | 2 | 2 |

A test whose query expects false is passed by an answer with nothing in it, so the same without those tests, what each reader found:

| set | tests expecting true | Sluicer's reader | `sluicer.compat.extruct` | extruct 0.18.0 |
|---|---|---|---|---|
| RDFa 1.1 | 166 | 3 | 133 | 129 |
| RDFa 1.1 Lite | 51 | 2 | 27 | 27 |
| processor graph | 3 | 0 | 0 | 0 |
| vocabulary expansion | 6 | 0 | 0 | 0 |
| `role` | 3 | 0 | 2 | 2 |

extruct raises on 5 of the 237 documents (rdfa1.1/0122, rdfa1.1/0297, rdfa1.1/0298, rdfa1.1/0299, rdfa1.1/0300); each is counted as failed. Sluicer's readers raise on none.

## Values, subjects aside

Each answer held against the graph the suite expects, its `.ttl`, subjects aside: every triple is a predicate and a value -- a literal's words, spaces collapsed, its type and language left out; an address; or a node, for a resource the graph describes -- and a value is right when the expected graph has it, wrong when it does not, and missing when only the expected graph has it. `rdfa:usesVocabulary` is left out, and so are the tests asking for an option and the 2 whose expected graph rdflib cannot parse (0281 (RDFa 1.1 Lite), 0282 (RDFa 1.1 Lite)). A reader's tests are those it answered: a document it raised on gives no values, and is left out of its row, not counted missing.

| set | tests | reader | right | wrong | missing |
|---|---|---|---|---|---|
| RDFa 1.1 | 170 | Sluicer's reader | 99 | 1 | 248 |
| RDFa 1.1 | 170 | `sluicer.compat.extruct` | 333 | 13 | 14 |
| RDFa 1.1 | 165 | extruct | 327 | 13 | 14 |
| RDFa 1.1 Lite | 45 | Sluicer's reader | 51 | 0 | 72 |
| RDFa 1.1 Lite | 45 | `sluicer.compat.extruct` | 116 | 8 | 7 |
| RDFa 1.1 Lite | 45 | extruct | 116 | 8 | 7 |
| `role` | 3 | Sluicer's reader | 0 | 0 | 3 |
| `role` | 3 | `sluicer.compat.extruct` | 3 | 0 | 0 |
| `role` | 3 | extruct | 3 | 0 | 0 |

Every wrong value, by reader:

- Sluicer's reader: 0197 (RDFa 1.1) `type` <http://schema.org/class/Person>.
- `sluicer.compat.extruct` and extruct, alike: 0073 (RDFa 1.1) `creator` <http://rdfa.info/test-suite/test-cases/rdfa1.1/html5/jane>; 0074 (RDFa 1.1) `creator` <http://rdfa.info/test-suite/test-cases/rdfa1.1/html5/jane>; 0074 (RDFa 1.1 Lite) `creator` <http://rdfa.info/test-suite/test-cases/rdfa1.1-lite/html5...>; 0272 (RDFa 1.1) `value` `18 March 2012`; 0272 (RDFa 1.1 Lite) `value` `18 March 2012`; 0273 (RDFa 1.1) `value` `midnight`; 0273 (RDFa 1.1 Lite) `value` `midnight`; 0274 (RDFa 1.1) `value` `18 March 2012 at midnight`; 0274 (RDFa 1.1 Lite) `value` `18 March 2012 at midnight`; 0277 (RDFa 1.1) `value` `2012-03-18T00:00:00Z`; 0277 (RDFa 1.1 Lite) `value` `2012-03-18T00:00:00Z`; 0279 (RDFa 1.1) `value` `18 March 2012 at midnight`; 0281 (RDFa 1.1) `value` `Two Thousand Twelve`; 0282 (RDFa 1.1) `value` `March, Two Thousand Twelve`; 0287 (RDFa 1.1) `value` `18 March 2012 at midnight in San Francisco`; 0287 (RDFa 1.1 Lite) `value` `18 March 2012 at midnight in San Francisco`; 0312 (RDFa 1.1) `homepage` `Some Body`; 0312 (RDFa 1.1) `nofollow` <http://example.org/>; 0312 (RDFa 1.1 Lite) `homepage` `Some Body`; 0312 (RDFa 1.1 Lite) `nofollow` <http://example.org/>; 0334 (RDFa 1.1) `homepage` <http://greggkellogg.net/>.

## With the subjects' names set aside

162 of the 237 runs ask for a subject by its address -- the document's, an `about`, a `resource` -- which Sluicer's records never carry, so its reader passes 0 of them. Asked again with each address in a subject's place replaced by a variable, the same address by the same variable, and nothing else changed, it passes 21; `sluicer.compat.extruct` 150, extruct 147.

## By feature

Each test is filed under the first of these its document uses, so a test of chaining with a datatype is under datatypes. Sluicer's column counts the suite's queries; in brackets, the same with the subjects' names set aside.

| feature | runs | Sluicer's reader | `compat.extruct` | extruct | Sluicer's reader does not read it |
|---|---|---|---|---|---|
| processor graph | 8 | 2 (2) | 2 | 2 | an option no reader here takes |
| vocabulary expansion | 9 | 0 (0) | 0 | 0 | an option no reader here takes |
| `role` | 6 | 0 (0) | 4 | 4 | `role` is not RDFa Lite |
| property copying (`rdfa:copy`) | 14 | 0 (2) | 10 | 10 | property copying is not read |
| lists (`inlist`) | 6 | 0 (0) | 6 | 6 | `inlist` is not RDFa Lite |
| `<time>` | 25 | 0 (0) | 6 | 6 | typed literals are not read |
| datatypes (`datatype`) | 15 | 0 (0) | 12 | 12 | typed literals are not read |
| languages (`lang`) | 4 | 0 (0) | 0 | 0 | languages are not read |
| `<base>` | 15 | 0 (2) | 0 | 0 |  |
| reverse links (`rev`) | 11 | 0 (0) | 10 | 10 | `rev` is not RDFa Lite |
| links and chaining (`rel`) | 51 | 4 (4) | 49 | 47 | `rel` links are not read |
| explicit subjects (`about`) | 35 | 1 (4) | 35 | 32 | `about` is not RDFa Lite |
| `vocab` and `prefix` | 24 | 2 (14) | 22 | 22 |  |
| `typeof` and `resource` | 6 | 0 (2) | 6 | 6 |  |
| `property` alone | 8 | 4 (4) | 8 | 8 |  |

## Losses

`sluicer.compat.extruct` fails 0 tests extruct passes, and passes 5 extruct fails: 0122 (RDFa 1.1), 0297 (RDFa 1.1), 0298 (RDFa 1.1), 0299 (RDFa 1.1), 0300 (RDFa 1.1). On the 65 runs both fail, the two give the same values, right, wrong and missing.

Sluicer's reader fails 224 of the 237 runs, first reason first:

| why | runs |
|---|---|
| `rel` links are not read | 47 |
| typed literals are not read | 40 |
| `about` is not RDFa Lite | 34 |
| no `typeof`, so no record | 29 |
| records name no subject | 16 |
| an option no reader here takes | 15 |
| property copying is not read | 14 |
| `rev` is not RDFa Lite | 11 |
| `inlist` is not RDFa Lite | 6 |
| `role` is not RDFa Lite | 6 |
| languages are not read | 4 |
| records name no subject, and more is missing | 2 |

Not explained by what the reader leaves out on purpose: none.

## Every test

| set | test | feature | what it tests | Sluicer's reader | `compat.extruct` | extruct |
|---|---|---|---|---|---|---|
| RDFa 1.1 | 0001 | explicit subjects (`about`) | Predicate establishment with @property | **fail** | pass | pass |
| RDFa 1.1 | 0006 | reverse links (`rev`) | @rel and @rev | **fail** | pass | pass |
| RDFa 1.1 | 0007 | reverse links (`rev`) | @rel, @rev, @property, @content | **fail** | pass | pass |
| RDFa 1.1 | 0008 | links and chaining (`rel`) | empty string @about | **fail** | pass | pass |
| RDFa 1.1 | 0009 | reverse links (`rev`) | @rev | **fail** | pass | pass |
| RDFa 1.1 | 0010 | reverse links (`rev`) | @rel, @rev, @href | **fail** | pass | pass |
| RDFa 1.1 | 0014 | datatypes (`datatype`) | @datatype, xsd:integer | **fail** | pass | pass |
| RDFa 1.1 | 0015 | links and chaining (`rel`) | meta and link | **fail** | pass | pass |
| RDFa 1.1 Lite | 0015 | links and chaining (`rel`) | meta and link | **fail** | pass | pass |
| RDFa 1.1 | 0017 | links and chaining (`rel`) | Related blanknodes | **fail** | pass | pass |
| RDFa 1.1 | 0018 | links and chaining (`rel`) | @rel for predicate | **fail** | pass | pass |
| RDFa 1.1 | 0020 | explicit subjects (`about`) | Inheriting @about for subject | **fail** | pass | pass |
| RDFa 1.1 | 0021 | `vocab` and `prefix` | Subject inheritance with no @about | **fail** | pass | pass |
| RDFa 1.1 Lite | 0021 | `vocab` and `prefix` | Subject inheritance with no @about | **fail** | pass | pass |
| RDFa 1.1 | 0023 | `vocab` and `prefix` | @id does not generate subjects | **fail** | pass | pass |
| RDFa 1.1 Lite | 0023 | `vocab` and `prefix` | @id does not generate subjects | **fail** | pass | pass |
| RDFa 1.1 | 0025 | links and chaining (`rel`) | simple chaining test | **fail** | pass | pass |
| RDFa 1.1 | 0026 | explicit subjects (`about`) | @content | **fail** | pass | pass |
| RDFa 1.1 | 0027 | explicit subjects (`about`) | @content, ignore element content | **fail** | pass | pass |
| RDFa 1.1 | 0029 | datatypes (`datatype`) | markup stripping with @datatype | **fail** | pass | pass |
| RDFa 1.1 | 0030 | links and chaining (`rel`) | omitted @about | **fail** | pass | pass |
| RDFa 1.1 Lite | 0030 | links and chaining (`rel`) | omitted @about | **fail** | pass | pass |
| RDFa 1.1 | 0031 | links and chaining (`rel`) | simple @resource | **fail** | pass | pass |
| RDFa 1.1 | 0032 | links and chaining (`rel`) | @resource overrides @href | **fail** | pass | pass |
| RDFa 1.1 | 0033 | links and chaining (`rel`) | simple chaining test with bNode | **fail** | pass | pass |
| RDFa 1.1 | 0034 | links and chaining (`rel`) | simple img[@src] test | **fail** | pass | pass |
| RDFa 1.1 | 0036 | links and chaining (`rel`) | @src/@resource test | **fail** | pass | pass |
| RDFa 1.1 | 0038 | reverse links (`rev`) | @rev - img[@src] test | **fail** | pass | pass |
| RDFa 1.1 | 0048 | links and chaining (`rel`) | @typeof with @about and @rel present, no @resource | **fail** | pass | pass |
| RDFa 1.1 | 0049 | explicit subjects (`about`) | @typeof with @about, no @rel or @resource | **fail** | pass | pass |
| RDFa 1.1 | 0050 | `vocab` and `prefix` | @typeof without anything else | pass | pass | pass |
| RDFa 1.1 Lite | 0050 | `vocab` and `prefix` | @typeof without anything else | pass | pass | pass |
| RDFa 1.1 | 0051 | explicit subjects (`about`) | @typeof with a single @property | **fail** | pass | pass |
| RDFa 1.1 | 0052 | `vocab` and `prefix` | @typeof with @resource and nothing else | **fail** | pass | pass |
| RDFa 1.1 Lite | 0052 | `vocab` and `prefix` | @typeof with @resource and nothing else | **fail** | pass | pass |
| RDFa 1.1 | 0053 | `vocab` and `prefix` | @typeof with @resource and nothing else, with a subelement | **fail** | pass | pass |
| RDFa 1.1 Lite | 0053 | `vocab` and `prefix` | @typeof with @resource and nothing else, with a subelement | **fail** | pass | pass |
| RDFa 1.1 | 0054 | explicit subjects (`about`) | multiple @property | **fail** | pass | pass |
| RDFa 1.1 | 0055 | links and chaining (`rel`) | multiple @rel | **fail** | pass | pass |
| RDFa 1.1 | 0056 | links and chaining (`rel`) | @typeof applies to @about on same element with hanging rel | **fail** | pass | pass |
| RDFa 1.1 | 0057 | links and chaining (`rel`) | hanging @rel creates multiple triples | **fail** | pass | pass |
| RDFa 1.1 | 0059 | links and chaining (`rel`) | multiple hanging @rels with multiple children | **fail** | pass | pass |
| RDFa 1.1 | 0060 | explicit subjects (`about`) | UTF-8 conformance | **fail** | pass | pass |
| RDFa 1.1 | 0063 | links and chaining (`rel`) | @rel in head using reserved XHTML value and empty-prefix CURIE syntax | **fail** | pass | pass |
| RDFa 1.1 | 0064 | links and chaining (`rel`) | @about with safe CURIE | **fail** | pass | pass |
| RDFa 1.1 | 0065 | links and chaining (`rel`) | @rel with safe CURIE | **fail** | pass | pass |
| RDFa 1.1 | 0066 | `vocab` and `prefix` | @about with @typeof in the head | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0066 | `vocab` and `prefix` | @about with @typeof in the head | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0067 | `vocab` and `prefix` | @property in the head | **fail** | pass | pass |
| RDFa 1.1 Lite | 0067 | `vocab` and `prefix` | @property in the head | **fail** | pass | pass |
| RDFa 1.1 | 0068 | explicit subjects (`about`) | Relative URI in @about | **fail** | pass | pass |
| RDFa 1.1 | 0069 | links and chaining (`rel`) | Relative URI in @href | **fail** | pass | pass |
| RDFa 1.1 | 0070 | links and chaining (`rel`) | Relative URI in @resource | **fail** | pass | pass |
| RDFa 1.1 | 0071 | links and chaining (`rel`) | No explicit @about | **fail** | pass | pass |
| RDFa 1.1 Lite | 0071 | links and chaining (`rel`) | No explicit @about | **fail** | pass | pass |
| RDFa 1.1 | 0072 | `<base>` | Relative URI in @about (with XHTML base in head) | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0073 | `<base>` | Relative URI in @resource (with XHTML base in head) | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0074 | `<base>` | Relative URI in @href (with XHTML base in head) | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0074 | `<base>` | Relative URI in @href (with XHTML base in head) | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0075 | `<base>` | Reserved word 'license' in @rel with no explicit @about | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0075 | `<base>` | Reserved word 'license' in @rel with no explicit @about | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0080 | links and chaining (`rel`) | @about overrides @resource in incomplete triples | **fail** | pass | pass |
| RDFa 1.1 | 0083 | links and chaining (`rel`) | multiple ways of handling incomplete triples (merged) | **fail** | pass | pass |
| RDFa 1.1 | 0084 | reverse links (`rev`) | multiple ways of handling incomplete triples, this time with both @rel and @rev | **fail** | pass | pass |
| RDFa 1.1 | 0088 | links and chaining (`rel`) | Interpretation of the CURIE "_:" | **fail** | pass | pass |
| RDFa 1.1 | 0089 | `vocab` and `prefix` | @src sets a new subject (@typeof) | **fail** | pass | pass |
| RDFa 1.1 Lite | 0089 | `vocab` and `prefix` | @src sets a new subject (@typeof) | **fail** | pass | pass |
| RDFa 1.1 | 0091 | explicit subjects (`about`) | Non-reserved, un-prefixed CURIE in @property | **fail** | pass | pass |
| RDFa 1.1 | 0093 | datatypes (`datatype`) | Tests XMLLiteral content with explicit @datatype (user-data-typed literal) | **fail** | pass | pass |
| RDFa 1.1 | 0099 | explicit subjects (`about`) | Preservation of white space in literals | **fail** | pass | pass |
| RDFa 1.1 | 0104 | links and chaining (`rel`) | rdf:value | **fail** | pass | pass |
| RDFa 1.1 | 0106 | links and chaining (`rel`) | chaining with empty value in inner @rel | **fail** | pass | pass |
| RDFa 1.1 | 0107 | links and chaining (`rel`) | no garbage collecting bnodes | pass | pass | pass |
| RDFa 1.1 | 0110 | links and chaining (`rel`) | bNode generated even though no nested @about exists | **fail** | pass | pass |
| RDFa 1.1 | 0111 | links and chaining (`rel`) | two bNodes generated after three levels of nesting | **fail** | pass | pass |
| RDFa 1.1 | 0112 | datatypes (`datatype`) | plain literal with datatype="" | **fail** | pass | pass |
| RDFa 1.1 | 0115 | `vocab` and `prefix` | XML Entities must be supported by RDFa parser | **fail** | pass | pass |
| RDFa 1.1 Lite | 0115 | `vocab` and `prefix` | XML Entities must be supported by RDFa parser | **fail** | pass | pass |
| RDFa 1.1 | 0117 | `<base>` | Fragment identifiers stripped from BASE | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0117 | `<base>` | Fragment identifiers stripped from BASE | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0118 | explicit subjects (`about`) | empty string "" is not equivalent to NULL - @about | **fail** | pass | pass |
| RDFa 1.1 | 0119 | explicit subjects (`about`) | "[prefix:]" CURIE format is valid | **fail** | pass | pass |
| RDFa 1.1 | 0120 | explicit subjects (`about`) | "[:]" CURIE format is valid | **fail** | pass | pass |
| RDFa 1.1 | 0122 | links and chaining (`rel`) | resource="[]" does not set the object | pass | pass | **fail** |
| RDFa 1.1 | 0126 | explicit subjects (`about`) | Multiple @typeof values | **fail** | pass | pass |
| RDFa 1.1 | 0134 | links and chaining (`rel`) | Uppercase reserved words | **fail** | pass | pass |
| RDFa 1.1 Lite | 0134 | links and chaining (`rel`) | Uppercase reserved words | **fail** | pass | pass |
| RDFa 1.1 | 0140 | `property` alone | Blank nodes identifiers are not allowed as predicates | pass | pass | pass |
| RDFa 1.1 Lite | 0140 | `property` alone | Blank nodes identifiers are not allowed as predicates | pass | pass | pass |
| RDFa 1.1 | 0174 | explicit subjects (`about`) | Support single character prefix in CURIEs | **fail** | pass | pass |
| RDFa 1.1 | 0175 | explicit subjects (`about`) | IRI for @property is allowed | **fail** | pass | pass |
| RDFa 1.1 | 0176 | reverse links (`rev`) | IRI for @rel and @rev is allowed | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0177 | `<base>` | Test @prefix | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0178 | `<base>` | Test @prefix with multiple mappings | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0181 | links and chaining (`rel`) | Test default XHTML vocabulary | **fail** | pass | pass |
| RDFa 1.1 | 0182 | `<base>` | Test prefix locality | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0186 | `<base>` | @vocab after subject declaration | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0187 | `<base>` | @vocab redefinition | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0188 | `<base>` | @vocab only affects predicates | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0189 | links and chaining (`rel`) | @vocab overrides default term | **fail** | pass | pass |
| RDFa 1.1 | 0190 | links and chaining (`rel`) | Test term case insensitivity | **fail** | pass | pass |
| RDFa 1.1 | 0196 | datatypes (`datatype`) | Test process explicit XMLLiteral | **fail** | pass | pass |
| RDFa 1.1 | 0197 | datatypes (`datatype`) | Test TERMorCURIEorAbsURI requires an absolute URI | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0206 | links and chaining (`rel`) | Usage of Initial Context | **fail** | pass | pass |
| RDFa 1.1 | 0207 | datatypes (`datatype`) | Vevent using @typeof | **fail** | pass | pass |
| RDFa 1.1 | 0213 | explicit subjects (`about`) | Datatype generation for a literal with XML content, version 1.1 | **fail** | pass | pass |
| RDFa 1.1 | 0214 | `typeof` and `resource` | Root element has implicit @about="" | **fail** | pass | pass |
| RDFa 1.1 Lite | 0214 | `typeof` and `resource` | Root element has implicit @about="" | **fail** | pass | pass |
| RDFa 1.1 | 0216 | explicit subjects (`about`) | Proper character encoding detection in spite of large headers | **fail** | pass | pass |
| RDFa 1.1 | 0217 | `<base>` | @vocab causes rdfa:usesVocabulary triple to be added | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0218 | lists (`inlist`) | @inlist to create empty list | **fail** | pass | pass |
| RDFa 1.1 | 0219 | lists (`inlist`) | @inlist with literal | **fail** | pass | pass |
| RDFa 1.1 | 0220 | lists (`inlist`) | @inlist with IRI | **fail** | pass | pass |
| RDFa 1.1 | 0221 | lists (`inlist`) | @inlist with hetrogenious membership | **fail** | pass | pass |
| RDFa 1.1 | 0224 | lists (`inlist`) | @inlist hanging @rel | **fail** | pass | pass |
| RDFa 1.1 | 0225 | lists (`inlist`) | @inlist on different elements with same subject | **fail** | pass | pass |
| RDFa 1.1 | 0228 | reverse links (`rev`) | 1.1 alternate for test 0040: @rev - @src/@resource test | **fail** | pass | pass |
| RDFa 1.1 | 0229 | links and chaining (`rel`) | img[@src] test with omitted @about | **fail** | pass | pass |
| RDFa 1.1 | 0231 | reverse links (`rev`) | Set image license information | **fail** | pass | pass |
| RDFa 1.1 | 0232 | links and chaining (`rel`) | @typeof with @rel present, no @href, @resource, or @about (1.1 behavior of 0046); | **fail** | pass | pass |
| RDFa 1.1 | 0233 | links and chaining (`rel`) | @typeof with @rel and @resource present, no @about (1.1 behavior of 0047) | **fail** | pass | pass |
| RDFa 1.1 Lite | 0235 | processor graph | rdfagraph='processor' does not generate standard triples | pass | pass | pass |
| processor graph | 0235 | processor graph | rdfagraph='processor' does not generate standard triples | pass | pass | pass |
| RDFa 1.1 Lite | 0238 | processor graph | rdfagraph='processor' with missing Term definition generates rdfa:Warning | **fail** | **fail** | **fail** |
| processor graph | 0238 | processor graph | rdfagraph='processor' with missing Term definition generates rdfa:Warning | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0239 | processor graph | rdfagraph='processor' with undefined prefix generates rdfa:Warning | **fail** | **fail** | **fail** |
| processor graph | 0239 | processor graph | rdfagraph='processor' with undefined prefix generates rdfa:Warning | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0240 | vocabulary expansion | vocab_expansion='true' expands sub-property | **fail** | **fail** | **fail** |
| vocabulary expansion | 0240 | vocabulary expansion | vocab_expansion='true' expands sub-property | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0241 | vocabulary expansion | vocab_expansion='true' expands equivalent-property | **fail** | **fail** | **fail** |
| vocabulary expansion | 0241 | vocabulary expansion | vocab_expansion='true' expands equivalent-property | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0242 | vocabulary expansion | vocab_expansion='true' expands referenced equivalent-property | **fail** | **fail** | **fail** |
| vocabulary expansion | 0242 | vocabulary expansion | vocab_expansion='true' expands referenced equivalent-property | **fail** | **fail** | **fail** |
| vocabulary expansion | 0243 | vocabulary expansion | vocab_expansion='true' expands sub-class | **fail** | **fail** | **fail** |
| vocabulary expansion | 0244 | vocabulary expansion | vocab_expansion='true' expands equivalent-class | **fail** | **fail** | **fail** |
| vocabulary expansion | 0245 | vocabulary expansion | vocab_expansion='true' expands referenced equivalent-class | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0246 | links and chaining (`rel`) | hanging @rel creates multiple triples, @typeof permutation; RDFa 1.1 version | **fail** | pass | pass |
| RDFa 1.1 | 0247 | links and chaining (`rel`) | Multiple incomplete triples, RDFa 1.1version | **fail** | pass | pass |
| RDFa 1.1 | 0248 | reverse links (`rev`) | multiple ways of handling incomplete triples (with @rev); RDFa 1.1 version | **fail** | pass | pass |
| RDFa 1.1 | 0249 | reverse links (`rev`) | multiple ways of handling incomplete triples (with @rel and @rev); RDFa 1.1 version | **fail** | pass | pass |
| RDFa 1.1 | 0250 | explicit subjects (`about`) | Checking the right behaviour of @typeof with @about, in presence of @property | **fail** | pass | pass |
| RDFa 1.1 | 0251 | languages (`lang`) | lang | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0252 | languages (`lang`) | lang inheritance | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0253 | datatypes (`datatype`) | plain literal with datatype="" and lang preservation | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0254 | datatypes (`datatype`) | @datatype="" generates plain literal in presence of child nodes | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0255 | languages (`lang`) | lang="" clears language setting | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0255 | languages (`lang`) | lang="" clears language setting | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0257 | explicit subjects (`about`) | element with @property and no child nodes generates empty plain literal (HTML5 version of 0113) | **fail** | pass | pass |
| RDFa 1.1 | 0259 | `property` alone | XML+RDFa Initial Context | **fail** | pass | pass |
| RDFa 1.1 Lite | 0259 | `property` alone | XML+RDFa Initial Context | **fail** | pass | pass |
| RDFa 1.1 | 0261 | datatypes (`datatype`) | White space preservation in XMLLiteral | **fail** | pass | pass |
| RDFa 1.1 | 0262 | explicit subjects (`about`) | Predicate establishment with @property, with white spaces before and after the attribute value | **fail** | pass | pass |
| RDFa 1.1 | 0263 | `typeof` and `resource` | @property appearing on the html element yields the base as the subject | **fail** | pass | pass |
| RDFa 1.1 Lite | 0263 | `typeof` and `resource` | @property appearing on the html element yields the base as the subject | **fail** | pass | pass |
| RDFa 1.1 | 0264 | `typeof` and `resource` | @property appearing on the head element gets the subject from <html>, ie, parent | **fail** | pass | pass |
| RDFa 1.1 Lite | 0264 | `typeof` and `resource` | @property appearing on the head element gets the subject from <html>, ie, parent | **fail** | pass | pass |
| RDFa 1.1 | 0265 | explicit subjects (`about`) | @property appearing on the head element gets the subject from <html>, ie, parent | **fail** | pass | pass |
| RDFa 1.1 | 0266 | explicit subjects (`about`) | @property without @content or @datatype, typed object set by @href and @typeof | **fail** | pass | pass |
| RDFa 1.1 | 0267 | explicit subjects (`about`) | @property without @content or @datatype, typed object set by @resource and @typeof | **fail** | pass | pass |
| RDFa 1.1 | 0268 | explicit subjects (`about`) | @property without @content or @datatype, typed object set by @src and @typeof | **fail** | pass | pass |
| RDFa 1.1 | 0269 | `property` alone | Use of @property in HEAD without explicit subject | **fail** | pass | pass |
| RDFa 1.1 | 0271 | explicit subjects (`about`) | Use of @property in HEAD with explicit parent subject via @about | **fail** | pass | pass |
| RDFa 1.1 | 0272 | `<time>` | time element with @datetime an xsd:date | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0272 | `<time>` | time element with @datetime an xsd:date | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0273 | `<time>` | time element with @datetime an xsd:time | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0273 | `<time>` | time element with @datetime an xsd:time | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0274 | `<time>` | time element with @datetime an xsd:dateTime | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0274 | `<time>` | time element with @datetime an xsd:dateTime | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0275 | `<time>` | time element with value an xsd:date | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0275 | `<time>` | time element with value an xsd:date | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0276 | `<time>` | time element with value an xsd:time | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0276 | `<time>` | time element with value an xsd:time | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0277 | `<time>` | time element with value an xsd:dateTime | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0277 | `<time>` | time element with value an xsd:dateTime | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0278 | `<time>` | @content overrides @datetime | **fail** | pass | pass |
| RDFa 1.1 | 0279 | `<time>` | @datatype used with @datetime overrides default datatype | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0281 | `<time>` | time element with @datetime an xsd:gYear | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0281 | `<time>` | time element with @datetime an xsd:gYear | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0282 | `<time>` | time element with @datetime an xsd:gYearMonth | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0282 | `<time>` | time element with @datetime an xsd:gYearMonth | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0283 | `<time>` | time element with @datetime an invalid datatype generates plain literal | **fail** | pass | pass |
| RDFa 1.1 Lite | 0283 | `<time>` | time element with @datetime an invalid datatype generates plain literal | **fail** | pass | pass |
| RDFa 1.1 | 0284 | `<time>` | time element not matching datatype but with explicit @datatype | **fail** | pass | pass |
| RDFa 1.1 | 0287 | `<time>` | time element with @datetime an xsd:dateTime with TZ offset | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0287 | `<time>` | time element with @datetime an xsd:dateTime with TZ offset | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0289 | `property` alone | @href becomes subject when @property and @content are present | **fail** | pass | pass |
| RDFa 1.1 | 0290 | datatypes (`datatype`) | @href becomes subject when @property and @datatype are present | **fail** | pass | pass |
| RDFa 1.1 | 0291 | explicit subjects (`about`) | @href as subject overridden by @about | **fail** | pass | pass |
| RDFa 1.1 | 0292 | explicit subjects (`about`) | @about overriding @href as subject is used as parent resource | **fail** | pass | pass |
| RDFa 1.1 | 0293 | explicit subjects (`about`) | Testing the ':' character usage in a CURIE | **fail** | pass | pass |
| RDFa 1.1 | 0296 | `vocab` and `prefix` | @property does set parent object without @typeof | **fail** | pass | pass |
| RDFa 1.1 Lite | 0296 | `vocab` and `prefix` | @property does set parent object without @typeof | **fail** | pass | pass |
| RDFa 1.1 | 0297 | explicit subjects (`about`) | @about=[] with @typeof does not create a new subject | **fail** | pass | **fail** |
| RDFa 1.1 | 0298 | explicit subjects (`about`) | @about=[] with @typeof does not create a new object | pass | pass | **fail** |
| RDFa 1.1 | 0299 | links and chaining (`rel`) | @resource=[] with @href or @src uses @href or @src (@rel) | **fail** | pass | **fail** |
| RDFa 1.1 | 0300 | explicit subjects (`about`) | @resource=[] with @href or @src uses @href or @src (@property) | **fail** | pass | **fail** |
| RDFa 1.1 | 0301 | `vocab` and `prefix` | @property with @typeof creates a typed_resource for chaining | **fail** | pass | pass |
| RDFa 1.1 Lite | 0301 | `vocab` and `prefix` | @property with @typeof creates a typed_resource for chaining | **fail** | pass | pass |
| RDFa 1.1 | 0302 | `vocab` and `prefix` | @typeof with different content types | **fail** | pass | pass |
| RDFa 1.1 Lite | 0302 | `vocab` and `prefix` | @typeof with different content types | **fail** | pass | pass |
| RDFa 1.1 Lite | 0305 | `role` | role attribute with explicit id and term | **fail** | pass | pass |
| `role` | 0305 | `role` | role attribute with explicit id and term | **fail** | pass | pass |
| RDFa 1.1 Lite | 0306 | `role` | role attribute with explicit base id and term | **fail** | **fail** | **fail** |
| `role` | 0306 | `role` | role attribute with explicit base id and term | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0307 | `role` | role attribute with term and no id | **fail** | pass | pass |
| `role` | 0307 | `role` | role attribute with term and no id | **fail** | pass | pass |
| RDFa 1.1 | 0311 | `property` alone | Ensure no triples are generated when @property is empty | pass | pass | pass |
| RDFa 1.1 Lite | 0311 | `property` alone | Ensure no triples are generated when @property is empty | pass | pass | pass |
| RDFa 1.1 | 0312 | links and chaining (`rel`) | Mute plain @rel if @property is present | pass | **fail** | **fail** |
| RDFa 1.1 Lite | 0312 | links and chaining (`rel`) | Mute plain @rel if @property is present | pass | **fail** | **fail** |
| RDFa 1.1 Lite | 0313 | processor graph | rdfagraph='processor' redefining an initial context prefix generates rdfa:PrefixRedefinition warning | **fail** | **fail** | **fail** |
| processor graph | 0313 | processor graph | rdfagraph='processor' redefining an initial context prefix generates rdfa:PrefixRedefinition warning | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0315 | links and chaining (`rel`) | @property and @typeof with incomplete triples | **fail** | pass | pass |
| RDFa 1.1 | 0316 | links and chaining (`rel`) | @property and @typeof with incomplete triples (@href variant) | **fail** | pass | pass |
| RDFa 1.1 | 0317 | datatypes (`datatype`) | @datatype inhibits new @property behavior | **fail** | pass | pass |
| RDFa 1.1 | 0318 | explicit subjects (`about`) | Setting @vocab to empty strings removes default vocabulary | **fail** | pass | pass |
| RDFa 1.1 | 0321 | property copying (`rdfa:copy`) | rdfa:copy to rdfa:Pattern | **fail** | pass | pass |
| RDFa 1.1 Lite | 0321 | property copying (`rdfa:copy`) | rdfa:copy to rdfa:Pattern | **fail** | pass | pass |
| RDFa 1.1 | 0322 | property copying (`rdfa:copy`) | rdfa:copy for additional property value | **fail** | pass | pass |
| RDFa 1.1 Lite | 0322 | property copying (`rdfa:copy`) | rdfa:copy for additional property value | **fail** | pass | pass |
| RDFa 1.1 | 0323 | property copying (`rdfa:copy`) | Multiple references to rdfa:Pattern | **fail** | pass | pass |
| RDFa 1.1 Lite | 0323 | property copying (`rdfa:copy`) | Multiple references to rdfa:Pattern | **fail** | pass | pass |
| RDFa 1.1 | 0324 | property copying (`rdfa:copy`) | Multiple references to rdfa:Pattern | **fail** | pass | pass |
| RDFa 1.1 Lite | 0324 | property copying (`rdfa:copy`) | Multiple references to rdfa:Pattern | **fail** | pass | pass |
| RDFa 1.1 | 0325 | property copying (`rdfa:copy`) | Multiple references to rdfa:Pattern creating a resource | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0325 | property copying (`rdfa:copy`) | Multiple references to rdfa:Pattern creating a resource | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0326 | property copying (`rdfa:copy`) | rdfa:Pattern removed only if referenced | **fail** | **fail** | **fail** |
| RDFa 1.1 Lite | 0326 | property copying (`rdfa:copy`) | rdfa:Pattern removed only if referenced | **fail** | **fail** | **fail** |
| RDFa 1.1 | 0327 | property copying (`rdfa:copy`) | rdfa:Pattern chaining | **fail** | pass | pass |
| RDFa 1.1 Lite | 0327 | property copying (`rdfa:copy`) | rdfa:Pattern chaining | **fail** | pass | pass |
| RDFa 1.1 | 0328 | `<time>` | @content overrides the content of the time element. | **fail** | pass | pass |
| RDFa 1.1 | 0329 | explicit subjects (`about`) | Recursive triple generation | **fail** | pass | pass |
| RDFa 1.1 | 0330 | datatypes (`datatype`) | @datatype overrides inherited @lang | **fail** | pass | pass |
| RDFa 1.1 | 0331 | datatypes (`datatype`) | @datatype overrides inherited @lang, with @content | **fail** | pass | pass |
| RDFa 1.1 | 0332 | datatypes (`datatype`) | Empty @datatype doesn't override inherited @lang, with @content | **fail** | pass | pass |
| RDFa 1.1 | 0333 | `<time>` | @content overrides @datetime (with @datatype specified) | **fail** | pass | pass |
| RDFa 1.1 | 0334 | links and chaining (`rel`) | @resource changes the current subject for the nested elements | **fail** | pass | pass |
