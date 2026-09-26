### Fixed

- `--visible` took a box whose class says there is no byline ("no-byline"), or the page's `<body>` itself, for a byline and read the first capitalised words in it as the author, and took the "By" line on another article's card, inside its link, for the page's own. None of them is read as the author now.
