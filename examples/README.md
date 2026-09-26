# Examples

Each file runs on its own and reaches nothing beyond this machine: `_site.py`
serves the small made-up site in `site/` locally, and every example reads its
pages from there. Run them from this folder, with the extras they need:

```bash
cd examples
uv run --with "sluicer[markdown]" python 01_declared_fields.py
uv run --with "sluicer[markdown]" python 01_declared_fields.py https://example.com/
```

Given an address, `01`, `03` and `04` read that page instead. `uv tool install`
would put Sluicer in an environment of its own, where a plain `python` cannot
import it; `uv run --with` gives the script one that can.

| file | shows |
|---|---|
| `01_declared_fields.py` | what an article declares, every field with the reader it came from, and the summary with the key each answer was read at |
| `02_respecting_a_refusal.py` | a page the site's robots.txt keeps crawlers away from, not asked for at all |
| `03_page_as_markdown.py` | the article as markdown, without the page's furniture |
| `04_a_guess_from_the_visible_page.py` | on a page that declares no author or date, a guess from its visible byline, kept apart and named a guess |

`site/` holds an article that declares its author and date in JSON-LD,
OpenGraph and HTML, a page of notes that shows them but declares neither, and a
robots.txt that asks every crawler to stay out of `drafts/`. The documentation
site publishes the same pages at <https://gi0tto.github.io/sluicer/demo/>.

`brake-pads.html` is the product page the README's Python example and
`docs/assets/inspect.svg` read: one product in JSON-LD, microdata and
OpenGraph, with two prices.

`shop/` is a made-up shop's listing of books: two pages of it, `before-1.html`
and `before-2.html`, to learn an extractor from, and `after.html`, the first
page after a redesign that renamed every class and wrapped the listing in a new
element. The README's quick start learns from the first two, fails on the
third with exit 3, and heals the extractor on it:

```bash
sluicer compile shop/before-1.html shop/before-2.html \
  --want title="A Light in the Attic" --want price=51.77 -o shop.json
sluicer run shop.json shop/after.html     # exit 3
sluicer heal shop.json shop/after.html -o shop-healed.json
```
