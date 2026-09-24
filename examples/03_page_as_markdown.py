"""The readable article, without the furniture around it.

python 03_page_as_markdown.py        # an article on the small site in site/
python 03_page_as_markdown.py URL    # or any page you may fetch
"""

import sys

from _site import serve

from sluicer import to_markdown
from sluicer.fetch import fetch

url = sys.argv[1] if len(sys.argv) > 1 else serve() + "/article.html"
page = fetch(url)
text = to_markdown(page.html, url=page.url)

print(text[:600] if text else "this page had no main content to give")
