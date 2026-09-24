"""A site that says no is obeyed, and says so loudly.

The small site in site/ asks every crawler, in its robots.txt, to stay out of
drafts/: the article is fetched, the draft is not asked for at all.
"""

from _site import serve

from sluicer.fetch import RobotsRefused, fetch

site = serve()
for url in (f"{site}/article.html", f"{site}/drafts/winter.html"):
    try:
        page = fetch(url)
        print(f"fetched  {url}  on the {page.rung} rung")
    except RobotsRefused as refusal:
        print(f"refused  {refusal.url}  by the site's own rules")
