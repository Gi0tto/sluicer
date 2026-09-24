"""Read what a page declares, and see where each value came from.

python 01_declared_fields.py        # an article on the small site in site/
python 01_declared_fields.py URL    # or any page you may fetch
"""

import sys

from _site import serve

import sluicer
from sluicer.fetch import fetch

url = sys.argv[1] if len(sys.argv) > 1 else serve() + "/article.html"
page = fetch(url)
result = sluicer.extract(page.html, url=page.url)

print(f"got it on the {page.rung} rung, after {len(page.climbs)} climbs")
print(f"vocabularies that fired: {result.sources}")

for record in result.records:
    print(f"\n{record.type or 'untyped'}:")
    for name, field in record.fields.items():
        print(f"  {name:22} {str(field.value)[:50]!r}  via {field.source}")

print("\nthe summary, one answer to each question, and where it was declared:")
for question, answer in result.summary.items():
    print(f"  {question:12} {str(answer.value)[:50]!r}  {answer.source} {answer.key}")
