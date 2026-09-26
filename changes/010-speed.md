### Added

- `bench/golden.py`: a digest of every public reading of every cached benchmark page, so a change meant only to be faster is shown to change no byte of any answer, and a timer per page.

### Changed

- JSON-LD: a block that parses as written is no longer run through the comment and trailing-comma repair first; the repair is made only when the text as written fails. Same output, and the default `extract` is about 5% faster on the timed pages.
