### Fixed

- `--visible` did not read a byline written as "Name, role" or "Name, role, Organisation" on the line right under the page's heading, as Framer's blog posts write it ("Diogo Almeida, founder, TypeSafe"). It now guesses the name, naming its element and the rule `name, role`.
- A publication date that was only a clock time ("10:52", "2:33 PM") was answered as the page's date. It is no date now, and the next declaration is asked.
- A page declaring its publication instant twice, once in UTC and once in its own time zone, was answered in UTC, which can fall on the next day. The declaration in the publisher's own offset is now the answer.
