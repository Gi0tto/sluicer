### Fixed

- `to_markdown` and `sluicer markdown` gave nothing but an error on a page with a link holding a control character, such as a backspace in a share link's text. The character is now percent-encoded, as the URL standard encodes it, and the page is read.
