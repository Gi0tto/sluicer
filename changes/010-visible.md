### Fixed

- `--visible` did not read a byline written as "Name, role" or "Name, role, Organisation" on the line right under the page's heading, as Framer's blog posts write it ("Diogo Almeida, founder, TypeSafe"). It now guesses the name, naming its element and the rule `name, role`.
