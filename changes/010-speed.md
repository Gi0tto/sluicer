### Added

- `bench/golden.py`: a digest of every public reading of every cached benchmark page, so a change meant only to be faster is shown to change no byte of any answer, and a timer per page.

### Changed

- JSON-LD: a block that parses as written is no longer run through the comment and trailing-comma repair first; the repair is made only when the text as written fails. Same output, and the default `extract` is about 5% faster on the timed pages.
- The readers find the elements carrying an attribute through the attribute axis (`//@itemscope/..`) instead of testing a predicate on every element (`//*[@itemscope]`): the same elements in the same order, and the default `extract` about 18% faster on the timed pages.
- The `<meta>` tags and the elements with a `rel` are found once per page and shared by the readers that filter them, and the canonical addresses are read once for the links and the summary; the same answers, about 5% less time per default `extract`.
- A page that is valid UTF-8 is parsed from its own bytes, its newlines read on the bytes, instead of being decoded and encoded back first: the same tree, about 4% less time per `extract`, and one copy of the page less in memory.
- The fetch ladder and the page cache decide whether a page declared a thing with the readers about things alone (`sluicer.declared.merge.declares_a_thing`), instead of a whole `extract` of it: the same verdict, and a fetch followed by an extraction takes about 13% less CPU.
- Judging a fetched page that declared a thing no longer strips its tags to count its text, which no rule then reads: the same verdicts, and about 11% less CPU per fetch and extraction.
