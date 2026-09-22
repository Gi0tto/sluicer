"""A site that says no is obeyed, and says so loudly."""

from sluicer.fetch import RobotsRefused, fetch

for url in (
    "https://www.gutenberg.org/ebooks/84",
    "https://www.gutenberg.org/ebooks/search/",  # this one robots.txt disallows
):
    try:
        page = fetch(url)
        print(f"fetched  {url}  on the {page.rung} rung")
    except RobotsRefused as refusal:
        print(f"refused  {refusal.url}  by the site's own rules")
