"""The author and date a page declares, and a guess from its visible text beside them.

Sluicer answers only what a page declares. When it declares no author or no
date, trafilatura -- which ``sluicer[markdown]`` installs -- can guess one from
the byline and the dates a reader sees. The guess is kept apart and named as
one: where nothing is declared it is right on 42% of the general web pages
Sluicer's scoreboards measure for an author and 24% for a date, and more often
on news (docs/known-limits.md has the numbers).

    python 04_a_guess_from_the_visible_page.py        # notes that declare neither
    python 04_a_guess_from_the_visible_page.py URL    # or any page you may fetch
"""

import sys

from _site import serve
from trafilatura import bare_extraction

import sluicer
from sluicer.fetch import fetch

url = sys.argv[1] if len(sys.argv) > 1 else serve() + "/notes.html"
page = fetch(url)
declared = sluicer.extract(page.html, url=page.url).summary
# Its date search capped at a fixed day, so the same page always gets the same
# guess: trafilatura's default cap is today.
guessed = bare_extraction(
    page.html,
    url=page.url,
    with_metadata=True,
    date_extraction_params={"max_date": "2099-12-31", "original_date": True},
)

for question, attribute in (("author", "author"), ("published", "date")):
    answer = declared.get(question)
    if answer is not None:
        print(f"{question}: {answer.value!r}  declared, {answer.source} {answer.key}")
    elif guess := getattr(guessed, attribute, None):
        print(f"{question}: {guess!r}  a guess from the visible page")
    else:
        print(f"{question}: neither declared nor guessed")
