### Fixed

- `--visible` did not read a byline written as "Name, role" or "Name, role, Organisation" on the line right under the page's heading, as Framer's blog posts write it ("Diogo Almeida, founder, TypeSafe"). It now guesses the name, naming its element and the rule `name, role`.
- A publication date that was only a clock time ("10:52", "2:33 PM") was answered as the page's date. It is no date now, and the next declaration is asked.
