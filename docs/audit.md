# Audit

`sluicer audit` holds what a page declares to what its documentation asks of
it. For every record JSON-LD, microdata and RDFa declare, it says which of
Google's rich-result features the record's type is documented for, which
required and recommended properties it lacks, and which of its values are in a
form the documentation or schema.org refuses. Then what the page as a whole
lacks, where two vocabularies contradict each other, which AI agents the site's
robots.txt admits, and whether its llms.txt keeps to llmstxt.org's format.

No model reads the page. The rules are data, transcribed from the pages that
state them, and every finding names the page its rule comes from, so the same
page always gets the same audit and any finding can be checked by opening one
link. SEO tooling for coding agents usually does this by handing a model the
HTML; the difference is the one Sluicer makes everywhere else.

```bash
sluicer audit https://example.com/product          # a report for a person
sluicer audit https://example.com/product --json   # the same audit as JSON
sluicer audit saved.html --url https://example.com/p  # a file: no site is read
sluicer audit https://example.com/p --no-site      # the page only
```

```python
from sluicer.audit import audit
from sluicer.fetch import fetch
from sluicer.fetch.site import read_site

page = fetch("https://example.com/product")
result = audit(page.html, url=page.url, site=read_site(page.url))
for record in result.records:
    for feature in record.features:
        print(record.source, record.types, feature.name, feature.requirements_met)
```

`audit` itself fetches nothing: `read_site` reads robots.txt, llms.txt and
llms-full.txt, over plain HTTP, under Sluicer's own name and the site's
robots.txt, and `audit` is handed what it read. It also takes an `Extraction`
already made; its records are then audited as merged, and what needs the page
itself is listed as not checked. For an agent, the MCP tool is `audit_page`.

## What is checked, and against what

### Records, one vocabulary at a time

A record is one item a reader returned -- a JSON-LD node, a top-level microdata
item, an RDFa subject -- before any folding. Google reads each syntax on its
own, and a finding has to name the vocabulary that declared the value, so a
product described in JSON-LD and in microdata is audited twice, once as each.
A JSON-LD graph that names its nodes by `@id` is followed through them, and a
node that is a record of its own is audited once, where it is, not again inside
every record that points at it.

Each finding carries its `severity`, a `code`, the record's `source` and
`index` (its position among that reader's records), the property `path`
(`offers[1].price`), the `feature` it serves if any, the offending `value`, and
the `rule`: the address of the page the rule is written on.

### Features

Read from each feature's "Structured data type definitions" on Google Search
Central, every page read on 2026-09-23. A property is required or recommended
because the page's table says so. Where the prose adds a condition the table
does not carry -- a breadcrumb's last item needs no `item`, a recipe that
states calories needs a yield, a remote job needs no `jobLocation` when it
names `applicantLocationRequirements` -- the condition is written on the
property. A subtype counts where the page says it does: a `Restaurant` is a
local business, and a `Car` is not a product, because the product pages say
"Car isn't supported automatically as a subtype of Product".

| Feature | Types | Required on the record | Status | Page, last updated |
|---|---|---|---|---|
| Product snippet | Product and subtypes (not Car, ProductGroup) | `name`, `review` or `aggregateRating` or `offers` | supported | [product-snippet](https://developers.google.com/search/docs/appearance/structured-data/product-snippet), 2026-09-08 |
| Merchant listing | Product and subtypes (not Car, ProductGroup) | `name`, `image`, `offers` | supported | [merchant-listing](https://developers.google.com/search/docs/appearance/structured-data/merchant-listing), 2026-09-08 |
| Review snippet | Review | `author`, `itemReviewed`, `itemReviewed.name`, `reviewRating`, `reviewRating.ratingValue` | supported | [review-snippet](https://developers.google.com/search/docs/appearance/structured-data/review-snippet), 2026-09-08 |
| Review snippet | AggregateRating | `itemReviewed`, `itemReviewed.name`, `ratingCount` or `reviewCount`, `ratingValue` | supported | the same |
| Review snippet | the types the page lists a review may be about, with subtypes, when they carry `review` or `aggregateRating` | `name`, `review` or `aggregateRating` | supported | the same |
| Article | Article, NewsArticle, BlogPosting and subtypes (not the two posting types the forum page claims) | none | supported | [article](https://developers.google.com/search/docs/appearance/structured-data/article), 2026-09-08 |
| Breadcrumb | BreadcrumbList | `itemListElement` | supported | [breadcrumb](https://developers.google.com/search/docs/appearance/structured-data/breadcrumb), 2026-09-08 |
| Organization | Organization and subtypes | none | supported | [organization](https://developers.google.com/search/docs/appearance/structured-data/organization), 2026-09-08 |
| Local business | LocalBusiness and subtypes | `address`, `name` | supported | [local-business](https://developers.google.com/search/docs/appearance/structured-data/local-business), 2026-09-08 |
| Recipe | Recipe | `image`, `name`, `recipeYield` if `nutrition.calories` | supported | [recipe](https://developers.google.com/search/docs/appearance/structured-data/recipe), 2026-09-08 |
| Event | Event and subtypes | `location`, `location.address`, `name`, `startDate` | supported | [event](https://developers.google.com/search/docs/appearance/structured-data/event), 2026-09-08 |
| Job posting | JobPosting | `datePosted`, `description`, `hiringOrganization`, `jobLocation` or `applicantLocationRequirements`, `jobLocation.address.addressCountry`, `title` | supported | [job-posting](https://developers.google.com/search/docs/appearance/structured-data/job-posting), 2026-09-08 |
| Video | VideoObject and subtypes | `name`, `thumbnailUrl`, `uploadDate` | supported | [video](https://developers.google.com/search/docs/appearance/structured-data/video), 2026-09-08 |
| Software app | SoftwareApplication and subtypes (not VideoGame alone) | `name`, `offers.price`, `aggregateRating` or `review` | supported | [software-app](https://developers.google.com/search/docs/appearance/structured-data/software-app), 2026-09-08 |
| Course list | Course | `description`, `name` | limited | [course](https://developers.google.com/search/docs/appearance/structured-data/course), 2026-09-08 |
| Dataset | Dataset | `description`, `name` | limited | [dataset](https://developers.google.com/search/docs/appearance/structured-data/dataset), 2026-09-08 |
| Book actions | Book and subtypes | `@id`, `author`, `name`, `url`, `workExample` | limited | [book](https://developers.google.com/search/docs/appearance/structured-data/book), 2025-12-10 |
| Q&A | QAPage | `mainEntity` | supported | [qapage](https://developers.google.com/search/docs/appearance/structured-data/qapage), 2026-09-08 |
| Discussion forum | DiscussionForumPosting, SocialMediaPosting | `author`, `author.name`, `datePublished`, `text` or `image` or `video` | supported | [discussion-forum](https://developers.google.com/search/docs/appearance/structured-data/discussion-forum), 2026-09-08 |
| Profile page | ProfilePage | `mainEntity` | supported | [profile-page](https://developers.google.com/search/docs/appearance/structured-data/profile-page), 2026-09-08 |
| Site name | WebSite | `name`, `url` | supported | [site-names](https://developers.google.com/search/docs/appearance/structured-data/site-names), 2025-12-10 |

The nested types each page defines are rules of their own, applied to the
values of the property that holds them: an `Offer` in `offers`, an
`AggregateOffer` beside it, a `UnitPriceSpecification`, `OfferShippingDetails`,
`MerchantReturnPolicy`, a nested `Review` and `AggregateRating`, `HowToStep` and
`HowToSection`, `BroadcastEvent`, `Clip`, `Question`, `Answer`, `Comment`,
`ReadAction`. The full transcription, recommended properties included, is
`sluicer/audit/google.py`.

**Limited** means Google names a condition the markup cannot show: course
lists need three courses and a carousel; Dataset markup has been used by
Dataset Search only, not Google Search, since November 2025; Book actions are
read from a data feed Google accepts from providers it has admitted, so what a
page's Book markup lacks for them is reported as a note, not an error. A
merchant listing and a product snippet are both reported for a product,
because which one applies depends on whether the page sells it, which markup
does not say.

**Parts.** A nested value the feature needs -- a merchant listing's `offers`,
a Q&A page's `mainEntity`, a product's only reviews -- is part of the feature:
what it lacks, the feature lacks. One the feature can do without -- an offer's
`shippingDetails`, a product's reviews beside its offers -- is a part of its
own. Google writes of those "you must add the following properties if you
want" them used; what they lack makes the part unusable and not the feature,
and is reported as `incomplete-part`, a warning.

Properties a table recommends that its own prose confines to some pages -- a
live video's `publication`, a segmented video's `hasPart`, a seasonal
closure's `validFrom` -- are never reported missing, nor are the job posting
page's beta education properties.

### Retired and restricted features

A record of a type whose feature Google no longer shows says so, as a note:

| Feature | Types | What happened | Source |
|---|---|---|---|
| FAQ | FAQPage | Restricted to well-known government and health sites from 2023-08-08; not shown in Google Search since 2026-05-07; its documentation was removed in June 2026. | [changelog](https://developers.google.com/search/updates#faq-deprecation) |
| How-to | HowTo | Not shown on mobile from August 2023, nor on desktop since 2023-09-13. | [blog](https://developers.google.com/search/blog/2023/08/howto-faq-changes) |
| Sitelinks search box | WebSite with `potentialAction` | Not shown since 2024-11-21; WebSite markup still names the site. | [blog](https://developers.google.com/search/blog/2024/10/sitelinks-search-box) |
| Fact check | ClaimReview | Being phased out of Google Search since 2025-06-12; still read by the Fact Check Explorer. | [page](https://developers.google.com/search/docs/appearance/structured-data/factcheck) |
| Course info, Estimated salary, Learning video, Special announcement, Vehicle listing | Course with `hasCourseInstance`, Occupation, LearningResource, SpecialAnnouncement, Car and Vehicle with `offers` | Phased out from 2025-06-12; removed from Search Console and the Rich Results Test on 2025-09-09. | [blog](https://developers.google.com/search/blog/2025/06/simplifying-search-results) |

The practice problem feature, removed in January 2026, shares its `Quiz` type
with Education Q&A, which is still shown, so it is not matched. Features Google
documents that this audit does not check -- movie carousels, vacation rentals,
math solvers, education Q&A, employer ratings, image metadata, product
variants, loyalty programs, return and shipping policies, carousels -- are
named on the record as not checked, so that no feature is never mistaken for
none.

### Values

Each is checked wherever its property appears, at any depth of a record:

| Property | Checked against | Source |
|---|---|---|
| `price`, `lowPrice`, `highPrice` | digits 0-9 and a full stop; a comma or a currency symbol is named as such | [schema.org/price](https://schema.org/price) |
| `priceCurrency`, `currency` | ISO 4217 list one, the edition published 2026-09-17 | [product snippet](https://developers.google.com/search/docs/appearance/structured-data/product-snippet), the [maintenance agency's list](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml) |
| dates (`datePublished`, `startDate`, `validThrough`, `uploadDate` ...) | an ISO 8601 calendar date, optionally `T`, a time and a zone; a space for the `T` is named | [article](https://developers.google.com/search/docs/appearance/structured-data/article) |
| two dates of one object | `dateModified` not before `datePublished`, `endDate` not before `startDate`, `validThrough` not before `validFrom` | [merchant listing](https://developers.google.com/search/docs/appearance/structured-data/merchant-listing) |
| durations (`cookTime`, `duration` ...) | an ISO 8601 duration | [recipe](https://developers.google.com/search/docs/appearance/structured-data/recipe) |
| URLs (`url`, `image`, `logo`, `sameAs`, `contentUrl` ...) | absolute http or https; a warning, since Google accepts relative URLs in places | [local business](https://developers.google.com/search/docs/appearance/structured-data/local-business) |
| `availability`, `itemCondition`, `eventStatus`, `dayOfWeek`, `bookFormat`, return-policy terms | the terms of the schema.org enumeration, with or without its address | [schema.org 30.1](https://schema.org/docs/releases.html#v30.1) |
| `ratingValue` | a number on the scale `worstRating` to `bestRating`, 1 to 5 when unstated; a fraction or a percentage | [review snippet](https://developers.google.com/search/docs/appearance/structured-data/review-snippet) |
| counts, `position`, coordinates | whole numbers, from 1 for a position; latitude within 90, longitude within 180 | the pages that define them |
| `gtin`, `gtin8` ... `gtin14`, `isbn` | length and check digit | [GS1](https://www.gs1.org/services/check-digit-calculator), [ISBN Users' Manual](https://www.isbn-international.org/sites/default/files/ISBN%20Manual%202012%20-corr.pdf) |
| `opens`, `closes`, booleans, `employmentType`, `jobLocationType`, `applicationCategory`, `priceRange` | the forms and lists the feature's page gives | the feature's page |

Checks a feature adds for itself: a merchant listing's price above zero and its
offer an `Offer`, not an `AggregateOffer`; a reviewer's name under 100
characters; a review's `itemReviewed` a type Google shows reviews for; a
dataset's description 50 to 5,000 characters; a salary's `unitText` one of the
five units.

### The page, and its vocabularies side by side

A `<title>`
([Google](https://developers.google.com/search/docs/appearance/title-link)), a
meta description
([Google](https://developers.google.com/search/docs/appearance/snippet)), one
absolute canonical
([Google](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)),
and OpenGraph's four required properties, `og:title`, `og:type`, `og:image` and
`og:url` ([ogp.me](https://ogp.me/)). Each missing one is a warning.

Two vocabularies that each declare one record of a type describe one thing,
and the facts they state about it must agree: identifiers, prices, the
currency, availability, the rating and its counts, the dates. Each is compared
as what it is -- 41.9 is 41.90, `eur` is `EUR`, two moments in two zones are
one moment -- and a disagreement is a warning citing Google's rule that
structured data "must be a true representation of the page content". With two
products in one vocabulary and one in another, which is which would be a
guess, and nothing is compared.

### AI agents

Every agent is named on its vendor's own page about its crawlers, read on
2026-09-23; nothing comes from a third-party list. For each, the site's
robots.txt is read by protego, the parser Sluicer obeys itself, and the report
names the `User-agent` line that decided.

| Agent | Vendor | For | Honours robots.txt, per the vendor | Page |
|---|---|---|---|---|
| `GPTBot` | OpenAI | training | yes | [OpenAI](https://developers.openai.com/api/docs/bots) |
| `OAI-SearchBot` | OpenAI | search | yes | the same |
| `ChatGPT-User` | OpenAI | user | may not | the same |
| `ClaudeBot` | Anthropic | training | yes | [Anthropic](https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler) |
| `Claude-User` | Anthropic | user | yes | the same |
| `Claude-SearchBot` | Anthropic | search | yes | the same |
| `Google-Extended` | Google | training, and grounding Gemini | yes; a control token, no crawler | [Google, common crawlers](https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers) |
| `Google-CloudVertexBot` | Google | agents a site owner builds | yes | the same |
| `Google-Agent` | Google | user | may not | [Google, user-triggered fetchers](https://developers.google.com/crawling/docs/crawlers-fetchers/google-user-triggered-fetchers) |
| `Google-GeminiNotebook` | Google | user | may not | the same |
| `PerplexityBot` | Perplexity | search | yes | [Perplexity](https://docs.perplexity.ai/docs/resources/perplexity-crawlers) |
| `Perplexity-User` | Perplexity | user | may not | the same |
| `CCBot` | Common Crawl | an open crawl others train on | yes | [Common Crawl](https://commoncrawl.org/ccbot) |
| `Applebot` | Apple | search; may train unless `Applebot-Extended` is disallowed | yes | [Apple](https://support.apple.com/en-us/119829) |
| `Applebot-Extended` | Apple | training; crawls nothing | yes | the same |
| `Amazonbot` | Amazon | training | yes | [Amazon](https://developer.amazon.com/amazonbot) |
| `Amzn-SearchBot` | Amazon | search | yes | the same |
| `Amzn-User` | Amazon | user | may not | the same |
| `Meta-ExternalAgent` | Meta | training | yes | [Meta](https://developers.facebook.com/docs/sharing/webmasters/web-crawlers/) |
| `Meta-WebIndexer` | Meta | search | yes | the same |
| `Meta-ExternalFetcher` | Meta | user | may not | the same |
| `MistralAI-Training` | Mistral | training | yes | [Mistral](https://docs.mistral.ai/robots) |
| `MistralAI-Index` | Mistral | search | yes | the same |
| `MistralAI-User` | Mistral | user | yes | the same |
| `DuckAssistBot` | DuckDuckGo | search | yes | [DuckDuckGo](https://duckduckgo.com/duckduckgo-help-pages/results/duckassistbot) |

Left out, deliberately: `anthropic-ai`, which Anthropic's page does not list;
`cohere-ai`, since [Cohere's page](https://docs.cohere.com/docs/cohere-web-crawlers)
lists no crawler at all; `Bytespider`, since ByteDance publishes no page about
it; and ad crawlers and link-preview fetchers, which are on the same pages and
are not what a page is being read for. Every `User-agent` a robots.txt names
that no agent here answers to is listed as `other_agents`: a site that names
`anthropic-ai` and not `ClaudeBot` has turned nobody away.

What the deciding group says about *use* is read too, from the lines protego
passes over. `Content-Usage` is the IETF aipref working group's rule
(draft-ietf-aipref-attach-05, its vocabulary draft-ietf-aipref-vocab-08):
`train-ai`, `ai-use` and `search`, each `y` or `n`, optionally for a path.
`Content-Signal` is Cloudflare's (`search`, `ai-input`, `ai-train`, each `yes`
or `no`), which its managed robots.txt writes -- GitHub's code search counted
3,448 robots.txt files with a `Content-Signal` line on 2026-09-23 -- and whose
draft, draft-romm-aipref-contentsignals-00, expired on 2026-04-04. The rule whose path matches the page longest applies, rules on the
same path combine with the most restrictive winning, and a page the agent may
not fetch has no preferences, as the aipref drafts say. None of them is an RFC,
and each agent's line says only what the site stated: `allow`, `disallow`, or
nothing when it stated nothing. The report says them once per group.

A robots.txt that answered 4xx has no rules, which allows everything; one that
could not be read decides nothing, and every verdict is unknown.

### Text and data mining

The page's TDMRep reservation is reported as `tdm` -- reserved or not, the
policy it names, and which declaration last said so: the site's
`/.well-known/tdmrep.json`, read with the other files, or the page's
`<meta name="tdm-reservation">`, which supersedes it. It is a statement
recorded, never a finding: a page may reserve its rights, and one that does
not has broken no rule.

### llms.txt

Read against the proposal at [llmstxt.org](https://llmstxt.org/) (v2, August
2026): an H1 with the site's name, "the only required section", is an error
when missing; a blockquote summary, no headings besides the H1 and the H2
sections, and H2 sections that are lists of `[name](url)` links, optionally
followed by `:` and notes, are warnings when departed from. A site that
answers /llms.txt with an HTML page -- a single-page app's fallback, a 404 page
served with 200 -- is an error. `llms-full.txt` is not part of the proposal and
has no format to check; whether the site serves one, and how long it is, is
reported. Google said in June 2026 that these files are not used by Google
Search and neither help nor harm a page there
([changelog](https://developers.google.com/search/updates)); they are for the
agents and tools that read them.

## Severity and exit codes

`error`: the page breaks a rule its documentation states -- a required
property missing, a value in a form the documentation refuses, an llms.txt
with no name. `warning`: it could do what the documentation recommends and
does not, an optional part is unusable, two vocabularies disagree, a URL is
relative. `info`: worth knowing and nothing to fix, such as a retired feature.

The command exits 3 when there is any error, whatever else is true -- as `run`
does for a page that broke its extractor, 3 means the page was read and breaks
a rule it is held to. Otherwise 1 when no record was declared, since there was
nothing to audit, and 0. 2, as everywhere, when the page could not be read. A
page the site answered with 403 or 404 is audited as the answer it is, and the
audit says so first.

## An example

The repository's example product page, which declares its product in JSON-LD
and again in microdata, and leaves out what a merchant listing needs:

```bash
sluicer audit examples/brake-pads.html --url https://example.com/p/bp-2210
```

```text
page      https://example.com/p/bp-2210

records   2 audited (jsonld 1, microdata 1)
  Product  (jsonld record 0)
    Product snippet   requirements met
                      recommended, missing: aggregateRating, review, offers.priceValidUntil
    Merchant listing  1 required missing: image
                      recommended, missing: aggregateRating, audience, category, color, description, gtin|gtin8|gtin12|gtin13|gtin14|isbn, hasAdultConsideration, hasCertification, inProductGroupWithID, isVariantOf, material, mpn, pattern, review, size, sku, subjectOf, offers.hasMerchantReturnPolicy, offers.itemCondition, offers.priceValidUntil, offers.shippingDetails, offers.url, offers.validFrom, offers.validThrough
  Product  (microdata record 0)
    Product snippet   1 required missing: review|aggregateRating|offers
                      recommended, missing: aggregateRating, offers, review
    Merchant listing  2 required missing: image, offers
                      recommended, missing: aggregateRating, audience, brand.name, category, color, description, hasAdultConsideration, hasCertification, inProductGroupWithID, isVariantOf, material, pattern, review, size, sku, subjectOf

page      1 finding
  warning  og:url is absent; OpenGraph requires it on every page  [https://ogp.me/]

not checked
  The AI agents robots.txt admits, and llms.txt: the site is read only for a URL.

summary   4 errors, 47 warnings, 0 notes
```

It exits 3: the page breaks rules its documentation states. Each record is
held to every feature its type is documented for, so the JSON-LD product meets
the product snippet's requirements and lacks the image a merchant listing
requires, and the microdata product, which declares no offer, lacks more. Run
on a page at a URL, the audit also reads the site's robots.txt and llms.txt.

## What it does not do

It checks what Google's documentation says, not what Google's own validator
decides, which is not published; a page that meets every documented
requirement may still not be shown. Nothing is checked against today's date --
a price valid until last year, an event that is over -- because the answer
would change with the clock. It reads the HTML the server sent, as the rest of
Sluicer does, so markup a page's script adds later is only seen when the fetch
climbed to a browser. The rest is in [known limits](known-limits.md#in-the-audit).
