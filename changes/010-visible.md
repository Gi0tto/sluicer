### Fixed

- `--visible` did not read a byline written as "Name, role" or "Name, role, Organisation" on the line right under the page's heading, as Framer's blog posts write it ("Diogo Almeida, founder, TypeSafe"). It now guesses the name, naming its element and the rule `name, role`.
- A publication date that was only a clock time ("10:52", "2:33 PM") was answered as the page's date. It is no date now, and the next declaration is asked.
- A page declaring its publication instant twice, once in UTC and once in its own time zone, was answered in UTC, which can fall on the next day. The declaration in the publisher's own offset is now the answer.
- An author written as `itemprop="author"` on an element outside any microdata item, `<span itemprop="author">Ann Smith</span>`, was not read; only a `<meta itemprop>` was. It is now the author when nothing else on the page declares one.
- RDFa properties with no subject in force, which RDFa gives to the page itself (`<meta property="dc:date">`, `<span property="dcterms:creator">`), were not read, since the RDFa reader reads only the subjects a `typeof` names. Their schema.org and Dublin Core author and publication date now answer the summary when nothing else on the page does.
- A product whose SKU was declared only on its offer, `"offers": {"sku": ...}`, had no SKU in the summary. The offer's SKU is now the product's when the product declares none and its offers name one SKU.
- The author Yoast SEO writes in the Twitter card's labelled pair, `twitter:label1` "Written by" and `twitter:data1` the name, was not read. It is now the author when nothing else on the page declares one, except on the site's home page and when it is the site's own name or a label such as "Staff".
