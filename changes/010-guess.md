### Fixed

- The summary's title kept the site's name after a separator whenever the page did not declare that name ("Personal Training - UT RecSports"), and took a business's name or a description written into `headline` over the title the page shows. Of the titles a page declares, the one its `<h1>` heading shows is now the title, cut where the heading ends; the answer is still the declared text, and with no such heading nothing changes.
- `--visible` took a box whose class says there is no byline ("no-byline"), or the page's `<body>` itself, for a byline and read the first capitalised words in it as the author, and took the "By" line on another article's card, inside its link, for the page's own. None of them is read as the author now.
