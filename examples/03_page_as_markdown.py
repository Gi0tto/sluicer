"""The readable article, without the furniture around it."""

from sluicer import to_markdown
from sluicer.fetch import fetch

page = fetch("https://www.gutenberg.org/ebooks/84")
text = to_markdown(page.html, url=page.url)

print(text[:600] if text else "this page had no main content to give")
