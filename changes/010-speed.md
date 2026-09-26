### Added

- `bench/golden.py`: a digest of every public reading of every cached benchmark page, so a change meant only to be faster is shown to change no byte of any answer, and a timer per page.

### Changed

- JSON-LD: a block that parses as written is no longer run through the comment and trailing-comma repair first; the repair is made only when the text as written fails. Same output, and the default `extract` is about 5% faster on the timed pages.
- The readers find the elements carrying an attribute through the attribute axis (`//@itemscope`, each attribute's element taken in Python) instead of testing a predicate on every element (`//*[@itemscope]`): the same elements in the same order, and the default `extract` about 18% faster on the timed pages. Taken in XPath (`//@itemscope/..`) the elements cost the square of their number, so a page of eighty thousand items is still read in linear time.
- The `<meta>` tags and the elements with a `rel` are found once per page and shared by the readers that filter them, and the canonical addresses are read once for the links and the summary; the same answers, about 5% less time per default `extract`.
- A page that is valid UTF-8 is parsed from its own bytes, its newlines read on the bytes, instead of being decoded and encoded back first: the same tree, about 4% less time per `extract`, and one copy of the page less in memory.
- The fetch ladder and the page cache decide whether a page declared a thing with the readers about things alone (`sluicer.declared.merge.declares_a_thing`), instead of a whole `extract` of it: the same verdict, and a fetch followed by an extraction takes about 13% less CPU.
- Judging a fetched page that declared a thing no longer strips its tags to count its text, which no rule then reads: the same verdicts, and about 11% less CPU per fetch and extraction.
- A fetched page is parsed once: the Document the fetch ladder (or the cache, the crawl, the MCP server's TDM check) parsed to judge the page is handed to the `extract` of that very page that follows in the same thread, instead of the page being parsed again. The same answers; a fetch followed by an extraction takes about 30% less CPU. One parsed page is kept per thread until it is extracted or replaced.
- `visible=True`: a text node is measured by stripping its ends instead of rewriting its white space with a regex, and the elements a class or an id names as a byline are found once for the author and the date: the same guesses, about 20% less time.
- A page given as a `str` (a fetched page is one) is handed to the parser as UTF-8 bytes, which libxml2 reads faster than a `str`, into the same tree; a `str` holding a lone surrogate is parsed as before.
