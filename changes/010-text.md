### Added

- `sluicer markdown --full`, `to_markdown(full=True)` and `page_markdown`'s `full` write the whole page as markdown, menus and footers included, scripts and styles left out, links and images resolved against the page. It needs no extra.
- `sluicer.read_markdown` returns the text with where it came from (`MainText`: `source`, `method`, `where`), `page_markdown` answers it as `text_from`, and the front matter's `sources` gains a `text` line. The main text itself is trafilatura's extraction exactly as before.

### Fixed

- `to_markdown` and `sluicer markdown` gave nothing but an error on a page with a link holding a control character, such as a backspace in a share link's text. The character is now percent-encoded, as the URL standard encodes it, and the page is read.
