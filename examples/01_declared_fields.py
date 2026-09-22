"""Read what a page declares, and see where each value came from."""

import sluicer
from sluicer.fetch import fetch

page = fetch("https://www.gutenberg.org/ebooks/84")
result = sluicer.extract(page.html, url=page.url)

print(f"got it on the {page.rung} rung, after {len(page.climbs)} climbs")
print(f"vocabularies that fired: {result.sources}")

for record in result.records:
    print(f"\n{record.type or 'untyped'}:")
    for name, field in record.fields.items():
        print(f"  {name:16} {field.value[:60]!r}  via {field.source}")
