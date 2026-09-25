# The state of declared data

What web pages declare about themselves -- JSON-LD, microdata, RDFa,
microformats, OpenGraph, the Twitter card, Dublin Core, HTML's own meta
names -- counted by Sluicer on 86,029 pages of Common Crawl's `CC-MAIN-2026-39`: every HTML
page answered 200 in 4 of the crawl's 100,000 WARC files, chosen
by a rule fixed before any was downloaded. Each is read as
`sluicer.extract` reads a page, with its provenance, and the conflicts
between what one page declares twice are counted with the rest.

Counted on 2026-09-25 by `bench/declared_report.py`, with Sluicer 0.9.0 at the last commit to `src/`, `10211f3` (lxml 6.1.3, libxml2 2.14.6, mf2py 2.0.2). Every number below is written by the script from its counts, `bench/declared-counts.json`,
except Web Data Commons', which are cited where they stand.

!!! warning "A few WARC files are not the web"
    4 files of one crawl, 77,257 hosts. Common Crawl chooses what it
    fetches by its own ranking of hosts and obeys robots.txt, so a site
    that refuses its crawler is not here; it keeps a body only up to a
    length, marking the rest truncated; it runs no script, so what a
    page declares only once its scripts have run is not here, nor
    what a page behind a login or an anti-bot wall declares; and it
    takes many pages from one host, so pages are not independent
    draws. The intervals, 95% Wilson intervals over pages, are
    therefore narrower than the sample's real uncertainty; for the
    vocabularies the share of hosts is given too.

## The sample

The crawl is the first listed in Common Crawl's `collinfo.json` whose
WARC listing is published. From its listing, pinned by SHA-256 in
`bench/declared-manifest.json`, the files are the lines at the middle
of each of 4 equal parts of the list, by position alone (3,737 MB
compressed in all). `bench/PREREG.md` fixed the rule and every count
before a file was downloaded.

| line | file | MB | pages | SHA-256 |
|---|---|---|---|---|
| 12,500 | `CC-MAIN-20260906015231-20260906045231-00500.warc.gz` | 942 | 21,782 | `2ffa9e966f482827…` |
| 37,500 | `CC-MAIN-20260909055742-20260909085742-00500.warc.gz` | 915 | 21,535 | `e20e5bc41518abfc…` |
| 62,500 | `CC-MAIN-20260912100909-20260912130909-00500.warc.gz` | 947 | 21,491 | `227d09081ab2836f…` |
| 87,500 | `CC-MAIN-20260915142231-20260915172231-00500.warc.gz` | 932 | 21,221 | `45d372d9ffd7226e…` |

A page is a `response` record answered 200 and read as HTML: 86,029 pages, from 77,257 hosts. 162 of them (0.2%) were truncated by the crawler and are read as it kept them. Common Crawl writes its redirects and
errors to other files, its `crawldiagnostics`, so these hold its
successful answers. Left out, and counted by why:

| left out | records |
|---|---|
| metadata record | 87,506 |
| request record | 87,506 |
| not HTML | 1,477 |
| warcinfo record | 4 |

Every page was read: none raised an error.

The top-level domains of the pages' hosts, the twenty commonest:

| top-level domain | pages | share |
|---|---|---|
| `.com` | 36,107 | 42.0% |
| `.org` | 4,772 | 5.5% |
| `.ru` | 4,244 | 4.9% |
| `.de` | 3,646 | 4.2% |
| `.net` | 2,419 | 2.8% |
| `.jp` | 1,985 | 2.3% |
| `.uk` | 1,773 | 2.1% |
| `.fr` | 1,745 | 2.0% |
| `.it` | 1,636 | 1.9% |
| `.pl` | 1,591 | 1.8% |
| `.br` | 1,448 | 1.7% |
| `.nl` | 1,234 | 1.4% |
| `.cz` | 925 | 1.1% |
| `.au` | 882 | 1.0% |
| `.ua` | 757 | 0.9% |
| `.es` | 743 | 0.9% |
| `.cn` | 733 | 0.9% |
| `.ca` | 696 | 0.8% |
| `.edu` | 631 | 0.7% |
| `.eu` | 595 | 0.7% |

## What pages declare

A vocabulary counts on a page when Sluicer's reader for it found
something (`Extraction.sources`). RDFa is RDFa Lite, and OpenGraph's
`<meta property>` tags are OpenGraph's, never RDFa's; HTML's meta
names are the closed list HTML itself defines (`description`,
`author`, `keywords`, `generator`, `application-name`,
`theme-color`). A host counts when any of its pages declares it.

| vocabulary | pages | share of pages | share of hosts |
|---|---|---|---|
| JSON-LD | 44,404 | 51.6% (51.3-51.9) | 51.7% (51.4-52.1) |
| microdata | 20,382 | 23.7% (23.4-24.0) | 24.1% (23.8-24.4) |
| microformats | 26,509 | 30.8% (30.5-31.1) | 31.5% (31.2-31.9) |
| RDFa | 1,871 | 2.2% (2.1-2.3) | 2.2% (2.1-2.3) |
| Dublin Core | 1,506 | 1.8% (1.7-1.8) | 1.7% (1.6-1.8) |
| OpenGraph | 59,368 | 69.0% (68.7-69.3) | 69.0% (68.7-69.3) |
| Twitter card | 43,700 | 50.8% (50.5-51.1) | 50.8% (50.5-51.2) |
| HTML meta names | 73,126 | 85.0% (84.8-85.2) | 85.2% (84.9-85.4) |
| **any about things** (the first four) | 59,380 | 69.0% (68.7-69.3) | 69.3% (69.0-69.6) |
| **any about things**, microformats only microformats2's own | 57,848 | 67.2% (66.9-67.6) | 67.5% (67.2-67.9) |
| **anything at all** | 79,236 | 92.1% (91.9-92.3) | 92.2% (92.0-92.4) |
| **nothing** | 6,793 | 7.9% (7.7-8.1) | 8.1% (7.9-8.2) |

Microformats need a word. microformats2's parsing rules take any class
of the form `h-` and letters for the root of an item, and CSS
frameworks name classes so: Tailwind's `h-full` and Bootstrap's
`h-auto` set a height. So the pages where the microformats reader
found something, 26,509, are split here by what they hold: a
record of one of the thirteen vocabularies the microformats wiki lists
as microformats2's (`h-entry`, `h-card`, `h-feed` and the rest; a
classic `hentry` or `vcard` is read as one), records of other types
only, or roots that gave no field at all. This split was decided after
the first count was read, and `bench/PREREG.md` says so.

| pages with microformats | pages | share of them |
|---|---|---|
| a record of microformats2's own vocabularies | 14,149 | 53.4% (52.8-54.0) |
| records of other types only | 4,500 | 17.0% (16.5-17.4) |
| roots with no field | 7,860 | 29.7% (29.1-30.2) |

The types of their records, the fifteen commonest:

| type | pages | microformats2's own |
|---|---|---|
| `h-entry` | 10,100 | yes |
| `h-feed` | 3,123 | yes |
| `h-full` | 2,640 | no |
| `h-auto` | 1,255 | no |
| `h-card` | 1,111 | yes |
| `h-fit` | 236 | no |
| `h-screen` | 175 | no |
| `h-relative` | 126 | no |
| `h-adr` | 108 | yes |
| `h-text` | 72 | no |
| `h-px` | 56 | no |
| `h-ni` | 47 | no |
| `h-pot` | 47 | no |
| `h-logo` | 45 | no |
| `h-date` | 38 | no |

The combinations pages declare, the fifteen commonest, in Sluicer's
order of precedence:

| readers that found something | pages | share |
|---|---|---|
| JSON-LD + OpenGraph + Twitter card + HTML meta names | 13,637 | 15.9% |
| JSON-LD + microformats + OpenGraph + Twitter card + HTML meta names | 9,007 | 10.5% |
| HTML meta names | 8,900 | 10.3% |
| (nothing) | 6,793 | 7.9% |
| JSON-LD + microdata + microformats + OpenGraph + Twitter card + HTML meta names | 5,024 | 5.8% |
| OpenGraph + Twitter card + HTML meta names | 4,554 | 5.3% |
| OpenGraph + HTML meta names | 4,320 | 5.0% |
| JSON-LD + microdata + OpenGraph + Twitter card + HTML meta names | 3,472 | 4.0% |
| JSON-LD + OpenGraph + HTML meta names | 3,313 | 3.9% |
| microformats + HTML meta names | 2,946 | 3.4% |
| microdata + OpenGraph + HTML meta names | 1,768 | 2.1% |
| JSON-LD + HTML meta names | 1,622 | 1.9% |
| microdata + HTML meta names | 1,418 | 1.6% |
| microdata + OpenGraph + Twitter card + HTML meta names | 1,348 | 1.6% |
| microformats + OpenGraph + Twitter card + HTML meta names | 1,250 | 1.5% |

## Beside Web Data Commons

[Web Data Commons](https://webdatacommons.org/structureddata/) (Bizer,
Meusel, Primpeli, Brinkmann; University of Mannheim) extracts the
structured data of a whole Common Crawl with Apache Any23. Its latest
extraction, released 2025-01-10, is of the October 2024 crawl,
`CC-MAIN-2024-42`; the figures below are from [its statistics page](https://webdatacommons.org/structureddata/2024-12/stats/stats.html),
read on 2026-09-25. Its crawl is two years older than this one, and it
reads differently: full RDFa rather than RDFa Lite, microformats one
format at a time, and JSON-LD with Any23's own parser, which that page
does not say is lenient. Read the two columns side by side, never as
one series.

| pages declaring | WDC, October 2024 | here |
|---|---|---|
| pages with any of JSON-LD, microdata, RDFa, microformats | 1,245,622,627 of 2,391,039,772 (52.1%; the page states 51.25%, and its per-format table's total is 1,221,984,070) | 69.0% (68.7-69.3) |
| … the same, microformats only microformats2's own vocabularies |  | 67.2% (66.9-67.6) |
| JSON-LD -- WDC's `html-embedded-jsonld` | 833,818,654 (34.9%) | 51.6% (51.3-51.9) |
| microdata -- WDC's `html-microdata` | 574,648,578 (24.0%) | 23.7% (23.4-24.0) |
| RDFa -- WDC's `html-rdfa` | 49,636,704 (2.1%) | 2.2% (2.1-2.3) |
| microformats (any, here; WDC's commonest format, hCard, alone) -- WDC's `html-mf-hcard` | 179,698,044 (7.5%) | 30.8% (30.5-31.1) |

## Types

The schema.org types of the records Sluicer reads from the
vocabularies about things, by the pages declaring each:
567 distinct types, the twenty-five commonest.
A schema.org type is written by its name whatever the page wrote
(`http://schema.org/Product`, `schema:Product`); another vocabulary's,
which keeps its whole IRI, and microformats' classes are not counted.

| type | pages | share of pages |
|---|---|---|
| `BreadcrumbList` | 33,453 | 38.9% (38.6-39.2) |
| `WebSite` | 27,512 | 32.0% (31.7-32.3) |
| `Organization` | 22,457 | 26.1% (25.8-26.4) |
| `WebPage` | 19,302 | 22.4% (22.2-22.7) |
| `ImageObject` | 13,581 | 15.8% (15.5-16.0) |
| `Person` | 10,040 | 11.7% (11.5-11.9) |
| `Article` | 9,649 | 11.2% (11.0-11.4) |
| `Product` | 8,748 | 10.2% (10.0-10.4) |
| `CollectionPage` | 4,701 | 5.5% (5.3-5.6) |
| `BlogPosting` | 4,015 | 4.7% (4.5-4.8) |
| `NewsArticle` | 3,268 | 3.8% (3.7-3.9) |
| `LocalBusiness` | 3,030 | 3.5% (3.4-3.6) |
| `CreativeWork` | 2,226 | 2.6% (2.5-2.7) |
| `SiteNavigationElement` | 2,152 | 2.5% (2.4-2.6) |
| `FAQPage` | 1,955 | 2.3% (2.2-2.4) |
| `Blog` | 1,572 | 1.8% (1.7-1.9) |
| `WPHeader` | 1,359 | 1.6% (1.5-1.7) |
| `ItemPage` | 1,219 | 1.4% (1.3-1.5) |
| `ItemList` | 1,151 | 1.3% (1.3-1.4) |
| `Event` | 955 | 1.1% (1.0-1.2) |
| `NewsMediaOrganization` | 846 | 1.0% (0.9-1.1) |
| `Place` | 817 | 0.9% (0.9-1.0) |
| `WPFooter` | 787 | 0.9% (0.9-1.0) |
| `VideoObject` | 581 | 0.7% (0.6-0.7) |
| `ListItem` | 562 | 0.7% (0.6-0.7) |

Every typed object in every JSON-LD block, nested ones included --
not a context's term definitions, not a value's datatype -- as
written and before references are resolved: 624,635 typed objects, the
twenty commonest classes, beside the share of Web Data Commons' 9,689,931,985 JSON-LD entities
of October 2024 (an entity of two types counts in both, here and there;
WDC's is an RDF node, so two objects with one `@id` are one entity
there and two here). A dash is a class outside WDC's twenty.

| class | objects | share here | share in WDC |
|---|---|---|---|
| `ListItem` | 111,342 | 17.8% | 17.8% |
| `ImageObject` | 61,808 | 9.9% | 10.5% |
| `Organization` | 41,872 | 6.7% | 7.4% |
| `BreadcrumbList` | 31,199 | 5.0% | 6.0% |
| `WebSite` | 28,947 | 4.6% | 5.0% |
| `Person` | 28,133 | 4.5% | 4.4% |
| `WebPage` | 27,266 | 4.4% | 4.5% |
| `Offer` | 23,593 | 3.8% | 6.4% |
| `SearchAction` | 17,676 | 2.8% | 4.3% |
| `Product` | 15,768 | 2.5% | 3.2% |
| `EntryPoint` | 14,840 | 2.4% | 3.5% |
| `SiteNavigationElement` | 14,172 | 2.3% | 1.1% |
| `PostalAddress` | 12,987 | 2.1% | 1.5% |
| `Answer` | 12,115 | 1.9% | – |
| `PropertyValueSpecification` | 11,845 | 1.9% | 1.8% |
| `Article` | 11,031 | 1.8% | 1.3% |
| `ReadAction` | 10,771 | 1.7% | 2.7% |
| `Question` | 10,716 | 1.7% | – |
| `QuantitativeValue` | 8,236 | 1.3% | – |
| `Brand` | 7,246 | 1.2% | 1.3% |

## One thing, declared in two vocabularies

Sluicer folds records of one type declared in two vocabularies about
things -- a Product in JSON-LD and again in microdata -- into one, the
earlier vocabulary's fields winning and the later one filling gaps.
Of the 59,380 pages declaring a thing, 27,213 (45.8% (45.4-46.2)) declare
them in two or more of those vocabularies, and on 1,800 (6.6% (6.3-6.9) of those) one record
holds fields from two or more: the fold added what the first
vocabulary left out. A fold that added no field is not seen here.
Microformats count here with every root, `h-full` and `h-auto`
among them, as the first count had them; only What pages declare
splits them.

| folded from | pages |
|---|---|
| JSON-LD + microdata | 1,770 |
| JSON-LD + RDFa | 29 |
| JSON-LD + microdata + RDFa | 2 |

## Conflicts

A conflict is a question the page answers twice with two meanings
(`Extraction.conflicts`): two prices that are two amounts, two
currencies, two publication or modification dates that are two days
or two instants. `126` and `126.00` agree, and a value no rule can read
disagrees with nothing. Sluicer compares these four questions only.
Of the 86,029 pages, 355 (0.4% (0.4-0.5)) declare at least one conflict.

| question | pages answering it | in conflict | share | the summary's answer / the other, most often |
|---|---|---|---|---|
| price | 8,051 | 122 | 1.5% (1.3-1.8) | JSON-LD / OpenGraph (92), microdata / OpenGraph (29), OpenGraph / OpenGraph (1) |
| currency | 8,714 | 22 | 0.3% (0.2-0.4) | JSON-LD / OpenGraph (22) |
| published | 23,361 | 109 | 0.5% (0.4-0.6) | JSON-LD / OpenGraph (87), microdata / OpenGraph (15), JSON-LD / Dublin Core (5) |
| modified | 21,403 | 145 | 0.7% (0.6-0.8) | JSON-LD / OpenGraph (117), microdata / OpenGraph (13), OpenGraph / OpenGraph (4) |

A title is not compared: a page's `<title>` adds the site's name, its
`og:title` drops it, and the two are one title. How often they differ:
62,625 pages (72.8% (72.5-73.1)) declare a title in two or more of
the subject's name, `og:title`, `twitter:title` and `<title>`; on
38,118 of them (60.9% (60.5-61.2)) the texts differ once
spaces are collapsed and case folded, and on 12,099
(19.3% (19.0-19.6)) two differ with neither holding the other.

## JSON-LD that is not JSON

44,511 pages carry 76,732 `<script type="application/ld+json">`
blocks with something in them. Each is read three ways, in order: as
`json.loads` reads JSON, NaN and Infinity refused; as written but with
a raw control character allowed inside a string, the newline a CMS
leaves in a description; and as Sluicer's lenient reader reads it,
unwrapping an HTML comment or CDATA, a byte order mark, JavaScript's
comments and a trailing comma, never mending a string's text.

| block | blocks | share of blocks |
|---|---|---|
| JSON | 75,987 | 99.0% (99.0-99.1) |
| JSON once a raw control character is allowed | 348 | 0.5% (0.4-0.5) |
| recovered by Sluicer's lenient reader | 138 | 0.2% (0.2-0.2) |
| lost | 259 | 0.3% (0.3-0.4) |

Of the 745 blocks that are not JSON, Sluicer reads 486 (65.2% (61.7-68.6)).
667 pages (1.5% (1.4-1.6) of those with a block) carry one that is not
JSON, and 238 (0.5% (0.5-0.6)) one that no reading recovers.

## What a declared value means

The summary keeps what the page wrote; `Extraction.normalised` reads
it into one form -- ISO 8601, a decimal, an ISO 4217 code, a GTIN whose
check digit is right -- only where the text leaves no doubt:
`03/04/2025` is two dates and `1,299` two amounts, and neither is read.

| question | pages answering it | read | share read |
|---|---|---|---|
| published | 23,361 | 22,039 | 94.3% (94.0-94.6) |
| modified | 21,403 | 21,024 | 98.2% (98.0-98.4) |
| price | 8,051 | 8,010 | 99.5% (99.3-99.6) |
| price_regular | 167 | 167 | 100.0% (97.8-100.0) |
| price_low | 680 | 680 | 100.0% (99.4-100.0) |
| price_high | 616 | 616 | 100.0% (99.4-100.0) |
| currency | 8,714 | 8,600 | 98.7% (98.4-98.9) |
| gtin | 948 | 800 | 84.4% (81.9-86.6) |

Of 948 GTINs, 800 (84.4% (81.9-86.6)) are right,
45 (4.7% (3.6-6.3)) have a GTIN's shape and a wrong check digit, and
103 (10.9% (9.0-13.0)) are not 8, 12, 13 or 14 digits at all once
spaces and hyphens are dropped.

The dates not read, by shape (every digit written 9, every letter
a), the ten commonest:

| shape | answers |
|---|---|
| `9999` | 258 |
| `9:99 aa` | 135 |
| `99:99` | 120 |
| `9999/99/99` | 90 |
| `99:99 aa` | 64 |
| `-9999-99-99a99:99:99+99:99` | 59 |
| `999 aaaa aaa` | 52 |
| `99/99/9999` | 49 |
| `9999999999` | 48 |
| `9999-99-99aaa99:99:99+99:99` | 40 |

The prices not read, by shape (every digit written 9, every letter
a), the ten commonest:

| shape | answers |
|---|---|
| `999.999` | 7 |
| `99.999` | 5 |
| `9,999` | 4 |
| `9.999` | 3 |
| `9999.999` | 2 |
| `$ 9,999` | 1 |
| `9 aaa.` | 1 |
| `9.99 aaa.` | 1 |
| `99 999 aaa.` | 1 |
| `99 999.99 ₽/aa.` | 1 |

## Where else a page lives

From `<link>` in the page and `Link` in its headers (`Extraction.links`).

| declares | pages | share |
|---|---|---|
| a canonical | 60,280 | 70.1% (69.8-70.4) |
| … the page's own address, exactly | 50,339 | 83.5% (83.2-83.8) |
| … another address | 9,941 | 16.5% (16.2-16.8) |
| two different canonicals | 219 | 0.3% (0.2-0.3) |
| `hreflang` alternates | 10,237 | 11.9% (11.7-12.1) |
| … with `x-default` | 5,750 | 56.2% (55.2-57.1) |

## How a page may be used

What the page's `<meta>` tags and its headers declare
(`Extraction.rights`): the robots directives, and TDMRep's reservation
of text and data mining rights, a W3C Community Group report written
for the EU's DSM Directive, Article 4. A page that declares nothing
declares nothing, which is not the same as allowing everything; and
robots.txt and `/.well-known/tdmrep.json`, the site's own rules, are
not read here.

| declares | pages | share |
|---|---|---|
| `<meta name="robots">` | 48,053 | 55.9% (55.5-56.2) |
| `X-Robots-Tag` | 733 | 0.9% (0.8-0.9) |
| `tdm-reservation` in the page | 128 | 0.1% (0.1-0.2) |
| `tdm-policy` in the page | 6 | 0.0% (0.0-0.0) |
| `TDM-Reservation` in the headers | 113 | 0.1% (0.1-0.2) |
| `TDM-Policy` in the headers | 5 | 0.0% (0.0-0.0) |
| `rel=license` | 685 | 0.8% (0.7-0.9) |

`<meta name="robots">`'s directives, by pages:

| said | pages |
|---|---|
| `max-image-preview:large` | 32,648 |
| `follow` | 30,462 |
| `index` | 29,847 |
| `max-snippet:-1` | 19,008 |
| `max-video-preview:-1` | 18,891 |
| `noindex` | 3,316 |
| `all` | 1,606 |
| `nofollow` | 1,013 |
| `noodp` | 743 |
| `noarchive` | 443 |
| `max-image-preview:standard` | 411 |
| `noydir` | 386 |
| `archive` | 56 |
| `noai` | 40 |
| `none` | 40 |

The crawlers named in its place, by pages:

| said | pages |
|---|---|
| `googlebot` | 1,384 |
| `bingbot` | 243 |
| `googlebot-news` | 119 |
| `msnbot` | 69 |
| `slurp` | 42 |
| `yandex` | 31 |
| `baiduspider` | 26 |
| `googlebot-image` | 18 |
| `duckduckbot` | 10 |
| `gptbot` | 7 |
| `ccbot` | 4 |
| `applebot` | 3 |
| `google-extended` | 2 |
| `googlebot-video` | 2 |

`X-Robots-Tag`'s directives, by pages:

| said | pages |
|---|---|
| `follow` | 277 |
| `noindex` | 259 |
| `index` | 213 |
| `all` | 185 |
| `max-image-preview:large` | 140 |
| `max-snippet:-1` | 121 |
| `max-video-preview:-1` | 117 |
| `nofollow` | 108 |
| `noodp` | 55 |
| `noarchive` | 43 |
| `nosnippet` | 20 |
| `none` | 18 |
| `noimageindex` | 7 |
| `noai` | 6 |
| `noimageai` | 4 |

`tdm-reservation`'s values in the page, by pages:

| said | pages |
|---|---|
| `0` | 106 |
| `1` | 22 |

`TDM-Reservation`'s values in the headers, by pages:

| said | pages |
|---|---|
| `0` | 105 |
| `1` | 8 |

## Reproduce it

```bash
.venv/bin/python bench/declared_report.py          # the pinned files, then this page
.venv/bin/python bench/declared_report.py --report-only   # this page from the counts
```

The first run downloads the pinned files from `data.commoncrawl.org`,
one at a time, into `bench/commoncrawl/`, and stops if one does not
hash to its pin. The counts are the same on every run: every page of
every file is read, and the files' counts are summed.
