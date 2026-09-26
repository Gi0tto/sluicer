# Drift

What an extractor does when the page it was learnt from changes. Each
extractor is learnt on an old Wayback Machine capture of a listing page
and replayed on a later one. An oracle that does not use the extractor's
code judges the result. Losses come first.

Regenerated on 2026-09-26 from commit
`5e97f6b` (sluicer 0.10.0, Scrapling 0.4.15, anansi 1.1.0 at commit 117fbe2) with
`uv run --with brotli --with 'scrapling>=0.4' bench/drift/run.py`. It
prints no seconds: its run time is mostly reading the archive's
captures ([`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md),
"How a second is measured").

!!! warning "Read this before the numbers"
    This is 44 pairs on 25 sites,
    chosen as described below. That is a small sample, and the oracle
    judges structure, not meaning. The numbers show how the checks behave
    on real captures; they are not a rate to expect on your sites.

## The losses

No pair failed silently.

**www-imdb-com-chart-top-long**, heal partly right. Read by hand: a real redesign. In 2023 IMDb replaced the 250-row table with a list that serves 25 rows and loads the rest by script. heal moved both links of each film, the poster link and the title link, to their new places. That works only since this benchmark's fix for links that gained ?ref_=chttp_t_1. heal reported the titles and the poster images as vanished rather than guess. The new title text carries the rank, '1. The Shawshank Redemption', and the poster's alt text names an actor, 'Tim Robbins in The Shawshank Redemption (1994)', so none of the old values is seen again. A person would call the title moved; heal needs an old value to prove it. The oracle: drift, the listing's container is gone. The checks that failed: `summary: the summary answers url -> no answer`; `listing: the listing at html>body>div[2]>div.redesign>div[1]>div.pagecontent[3]>div>div[1]>div.article>span.ab_widget>div.seen-collection>div.article>div.lister>table.chart>tbody.lister-list -> not found`.

**sourceforge-net-directory-long**, heal partly right. Read by hand: a real redesign, reached through a redirect to the Windows directory, which is what a scraper asking for the address reads. heal moved each project's name, its link and its description to their new places, all right on the four projects both pages list. The icon went to the new icon, which some projects lack, since they show a default icon kept in another field; half the matched projects have none. The icon's alt text, 'Apache OpenOffice Icon', and the whole card's text, which carried the weekly downloads, are found nowhere and reported vanished. Before this benchmark's tie-break fix, heal put the name on the icon's alt text too. The oracle: drift, the listing's container is gone. The checks that failed: `type: a declared MobileSoftwareApplication -> none`; `listing: the listing at html>body>div[3]>article.content-wrapper>section[1]>section[1]>section>div.browse>section>ul.projects -> not found`.

Scrapling's misses:

- **www-imdb-com-chart-top-long**: asked for 'The Shawshank Redemption', returned nothing, after relocating by similarity.
- **metacpan-org-recent-short**: asked for 'Sim-OPT-0.193', returned 'Bencher-Scenario-GraphTopologicalSortModules-0.004'.
- **sourceforge-net-directory-long**: asked for 'Apache OpenOffice', returned 'Home', after relocating by similarity.

anansi's misses:

- **www-imdb-com-chart-top-long**: asked for 'The Shawshank Redemption' by `tbody.lister-list > tr > td.titleColumn > a`, returned nothing, after healing.
- **metacpan-org-recent-short**: asked for 'Sim-OPT-0.193' by `tr > td.name > strong > a.ellipsis`, returned 'Calendar-Dates-Academic-ID-UT-PPs-0.002'.
- **sourceforge-net-directory-long**: asked for 'Apache OpenOffice' by `div.project_info > header > a > span`, returned '35 Reviews Downloads: 3,154,039 This Week Last Update: 2014-08-28 See Project', after healing.
- **www-theverge-com-tech-short**: asked for 'The Real-World AI Issue' by `div.c-entry-box--compact.c-entry-box--compact--article > div.c-entry-box--compact__body > h2.c-entry-box--compact__title > a`, returned 'Google’s new two-factor authentication prompt now has dark mode on Android'.

## Results

| outcome | pairs | what it means |
|---|---|---|
| failed silently | 0 | the oracle saw drift and the run passed: the failure this project exists to prevent |
| false alarm | 0 | the oracle saw the same template and the run failed |
| failed loudly | 21 | drift, and the run said so |
| survived | 23 | same template, and the run passed |

`heal` was run on every B capture. A heal counts as right when the healed
extractor reads the items A and B share with the values A had.

| heal | on the pairs with drift | on the pairs without |
|---|---|---|
| right | 0 | 6 |
| partly right | 2 | 0 |
| nothing to match | 18 | 17 |
| no listing on B | 1 | 0 |

"Nothing to match" means no item was on both captures, so there was
nothing to judge the heal against. News front pages a month apart share
no stories.

Scrapling's adaptive selectors were asked, on each pair where A and B
share an item, to find that item's title and link again on B. This
ran on 10 pairs. It was right on 7 and wrong on 2, and found nothing on 1. On 2 of these
pairs the saved selector matched nothing on B, so Scrapling fell back
to relocating by similarity.
The comparison is narrow. Scrapling follows one element it was shown;
Sluicer checks and heals a whole listing. The two answer different
questions and are not ranked.

[anansi](https://github.com/mdowis/anansi) 1.1.0 at commit 117fbe2 (Apache-2.0), in
an environment of its own, was asked about the same item on the same
pairs: its selector for A's element holding the title, asked again on
B. This ran on 11 pairs. It was right on 7 and wrong on 3, and found nothing on 1. It healed on 2 of these pairs -- the selector matched nothing on B --
and does not tell its caller when it heals: it returns a value, as it
returns one read by the selector it was given. Its answer is judged on
the title alone, since it returns text and not an element, so its test
is looser than Scrapling's. Its decay, 1% a day for a selector unused
over a week, by the clock, cannot act here: A and B are replayed
seconds apart, and the selector given is tried before any stored one.

## What this benchmark found in Sluicer, and fixed

- heal called every title and link vanished on a page of the same template whose items had changed, which is any live listing a month later: Hacker News, Lobsters, arXiv, Pinboard. sluicer heal then exited 3 on a page that had not drifted.
- heal moved numbered slots onto each other when one value turned up in another slot: Pinboard's first tag to the fourth place, and an arXiv ninth author, who was a first author a month later, onto the first-author column.
- run failed pages of the same template when one row renumbered a step in the middle of a path: one Stack Overflow user with a second kind of badge, one Verge story with a second author. These were two of the three false alarms.
- heal called a link vanished when the site tagged every link with a new parameter, as IMDb did in its 2023 redesign with ?ref_=chttp_t_1.
- heal broke a tie between two new places holding a field's old values by the alphabet. On SourceForge's redesign it put each project's name on its icon's alt text, which a quarter of the rows lack, rather than on its heading.
- run passed a page whose rows had become empty shells, skeletons waiting for a script, as a short page: a member that carries nothing was not a row. No capture here did it; reading the benchmark's results found it. An extractor now learns the share of empty members its pages had.
- the values check read three rows that said the same thing by chance as a page of placeholders: metacpan's three day-tables, whose fifteenth release carried the same label. That was the benchmark's last false alarm; the check is now held from five rows up.
- compile took page furniture for the listing on 6 of the 25 sites: GitHub's language menu of 491 links, old Reddit's sidebar lists, the paragraphs of one Hackaday post, page sections on the BBC and Ars Technica, and the three day-tables that hold metacpan's releases. Regions the page marks with an ARIA role such as menu or navigation, or hides, are now furniture; a group whose members are mostly another listing is sections, not rows; and classes that name one item, a position or a state (id-t3_8gxz1, odd, category-reviews) no longer split a listing into as many kinds as rows. All 25 now learn the listing a person would point at.
- run held the link in a row's second span as a column once compile learnt GitHub's repositories: a row with no language renumbers its spans, so the check fired on a page of the same template. A numbered slot at any step of a path, not only the last, is now a count.

## Other pairs, read by hand

**news-ycombinator-com-newest-long**, failed loudly. Hacker News dropped the list's class, table.itemlist, and the run said so.

**stackoverflow-com-questions-short**, survived. A false alarm before this benchmark's fix to renumbering. One user on A with a second kind of badge had numbered the badge step for every row.

**weworkremotely-com-categories-remote-programming-long**, failed loudly. The address now redirects to another category, remote full-stack programming jobs.

**www-theverge-com-tech-short**, survived. A false alarm before the same fix; here one story had a second author.

**www-bbc-com-news-technology-long**, failed loudly. The address now redirects to /innovation, another section.

**www-producthunt-com-short**, failed loudly. Between January and February 2019 a wrapper, div.large_bbe28, was inserted above the list; the hashed class names stayed the same. By the path contract that is drift, and the run said so. heal found the list, but no product was on both captures.

**pypi-org-search--q-scraping-long**, failed loudly. B is not a listing: PyPI now answers a client without JavaScript with a 'Client Challenge' page. The run failed on every check, as it should for a page that is not the page.

## Every pair

| pair | rows A / B | oracle | run | outcome | heal | Scrapling | anansi |
|---|---|---|---|---|---|---|---|
| books-toscrape-com-short | 20 / 20 | same | passed | survived | right (20 items) | right | right |
| books-toscrape-com-long | 20 / 20 | same | passed | survived | right (20 items) | right | right |
| quotes-toscrape-com-short | 10 / 10 | same | passed | survived | right (10 items) | right | right |
| quotes-toscrape-com-long | 10 / 10 | same | passed | survived | right (10 items) | right | right |
| news-ycombinator-com-short | 29 / 30 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| news-ycombinator-com-long | 29 / 30 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| news-ycombinator-com-newest-short | 30 / 30 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| news-ycombinator-com-newest-long | 30 / 0 | drift: the listing's container is gone | failed: listing | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| lobste-rs-short | 25 / 25 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| lobste-rs-long | 25 / 0 | drift: the listing's container is gone | failed: listing | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| github-com-trending-short | 25 / 25 | same | passed | survived | nothing to match | title not found on A | right |
| github-com-trending-long | 25 / 0 | drift: the listing's container is gone | failed: listing | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| stackoverflow-com-questions-short | 15-50 / 15 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| old-reddit-com-r-programming-short | 23 / 25 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| old-reddit-com-r-programming-long | 23 / 0 | drift: the listing's container is gone | failed: listing | failed loudly | nothing to match (1 items) | no A item is still on B | no A item is still on B |
| sfbay-craigslist-org-search-sss-long | 120 / 0 | drift: the listing's container is gone | failed: listing, summary, type | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| www-imdb-com-chart-top-short | 250 / 250 | same | passed | survived | right (248 items) | right | right |
| www-imdb-com-chart-top-long | 250 / 0 | drift: the listing's container is gone | failed: listing, summary | failed loudly | partly right (23 items) | nothing found | nothing found, healed |
| www-python-org-jobs-long | 117 / 0 | drift: the listing's container is gone | failed: listing | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| arxiv-org-list-cs-CL-recent-short | 25 / 25 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| arxiv-org-list-cs-CL-recent-long | 25 / 0 | drift: the listing's container is gone | failed: listing | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| slashdot-org-short | 11-14 / 10 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| slashdot-org-long | 11-14 / 0 | drift: the listing's container is gone | failed: listing | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| www-npr-org-sections-news-short | 21-22 / 22 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| www-npr-org-sections-news-long | 21-22 / 21 | drift: div.item-image&gt;div.imagewrap&gt;a@href is in 0% of rows | failed: field | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| weworkremotely-com-categories-remote-programming-long | 90 / 0 | drift: the listing's container is gone | failed: listing | failed loudly | nothing to match (1 items) | no A item is still on B | no A item is still on B |
| metacpan-org-recent-short | 61 / 60 | same | passed | survived | nothing to match (1 items) | wrong | wrong |
| metacpan-org-recent-long | 61 / 0 | drift: the listing's container is gone | failed: listing | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| hackaday-com-blog-short | 7 / 7 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| hackaday-com-blog-long | 7 / 7 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| sourceforge-net-directory-short | 25 / 25 | same | passed | survived | right (23 items) | right | right |
| sourceforge-net-directory-long | 25 / 0 | drift: the listing's container is gone | failed: listing, type | failed loudly | partly right (4 items) | wrong | wrong, healed |
| pinboard-in-popular-short | 100 / 100 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| pinboard-in-popular-long | 100 / 0 | drift: no div.bookmark rows in the container | failed: rows | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| www-theverge-com-tech-short | 12 / 13 | same | passed | survived | nothing to match (1 items) | right | wrong |
| www-theverge-com-tech-long | 12 / 0 | drift: the listing's container is gone | failed: listing | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| techcrunch-com-category-startups-long | 20 / 0 | drift: the listing's container is gone | failed: listing, type | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| www-bbc-com-news-technology-short | 19 / 20 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| www-bbc-com-news-technology-long | 19 / 0 | drift: the listing's container is gone | failed: listing, summary | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| arstechnica-com-gadgets-short | 12 / 12 | same | passed | survived | nothing to match | no A item is still on B | no A item is still on B |
| arstechnica-com-gadgets-long | 12 / 0 | drift: the listing's container is gone | failed: listing, type | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| www-producthunt-com-short | 16-17 / 0 | drift: the listing's container is gone | failed: listing | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| www-producthunt-com-long | 16-17 / 0 | drift: the listing's container is gone | failed: listing, type | failed loudly | nothing to match | no A item is still on B | no A item is still on B |
| pypi-org-search--q-scraping-long | 20 / 0 | drift: the listing's container is gone | failed: listing, summary | failed loudly | no listing on B | no A item is still on B | no A item is still on B |

## Method

- **Pairs.** `discover.py` proposes 25 listing pages on varied sites,
  each with four dates: A and A2 a week apart to learn from, a short B a
  few weeks later, and a long B years later. The archive's nearest
  captures are taken. `make_pairs.py` keeps, by rule, every page where a
  listing was learnt, with each B that is a different capture from A.
  The short pairs mostly test false alarms. The long pairs mostly cross
  redesigns. `pairs.json` is the list of pairs; no archived page is
  committed.
  The archive kept failing to give the long B capture of https://stackoverflow.com/questions, so the pair it belongs to is missing.
- **The archive.** Captures are read in the `id_` form, one request a
  second, with a user agent naming this benchmark, and cached. A body is
  decoded from the encoding it was served in. When the site redirected,
  the capture is the page the redirect led to, as a scraper would get it.
- **Oracle.** It walks the learnt container path and row kind on B with
  its own code. It then checks that every field every learnt row had is
  in 80% of B's rows. Drift is any of these failing. The oracle judges
  structure only: a template whose markup is intact but whose meaning
  changed is "same" to it.
- **Heal.** Some fields name the item: different in almost every row,
  with letters or an address. An A row and a B row are one item when at
  least half of what names the A row is found anywhere in the B row, so
  a column heal put in the wrong place still matches. For each naming
  field, the healed value on B must equal A's. Digits in text and a rank
  before a title are ignored, and so is a parameter a link gained. The
  verdicts:
  - right: every naming field agrees on 80% of matched items;
  - partly right: one agrees on fewer, or is gone;
  - wrong: one agrees on fewer than half;
  - lost: all of them are gone.
- **Scrapling.** `css(selector, auto_save=True)` is called on A's element
  holding the title of an item still listed on B, with the selector
  Scrapling generates for it. `css(selector, adaptive=True)` is then
  called on B, using Scrapling's own storage. The result is right when
  the element returned has that title and, for a link, that address.
- **anansi.** On the same item: the innermost element of A whose text
  is its title, of several the one whose link is the item's, and the
  selector anansi writes for it (`AdaptiveParser._tag_to_selector`).
  A fresh store per pair is asked `extract(A, {"item": selector})`,
  then the same on B, from `bench/requirements/anansi.txt`'s own
  environment. Right when the text returned is the title.

## Limits

- 44 pairs on 25 sites chosen by hand is a small sample. Most
  sites are news and link aggregators, and no real shop is among them.
- Which group is the listing is read by eye: on all 25 sites the
  learnt listing is the one a person would point at, and nothing here
  measures that beyond these 25.
- The oracle shares the extractor's notion of a path, so a change the
  path cannot express is invisible to both.
- Heal is judged only on items A and B share. Where they share none,
  which is most news pages, heal is not judged at all.


