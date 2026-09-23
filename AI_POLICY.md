# AI contribution policy

If you used AI assistance to write a contribution, say so in the pull request or
the issue, and say roughly how much: a comment tidied, a function drafted, a
whole module generated. Trivial typo and spacing fixes do not need it.

This is not a hurdle and it is not disapproval. It is the same rule the rest of
this project runs on: state what happened so a reviewer can weigh it. A reviewer
who knows a test was generated reads that test differently, and should.

## Our own disclosure

Most of this repository was written with Claude, Anthropic's model, working
from plans and reviews that were themselves largely written by Claude, under a
maintainer who ruled on the decisions and verified the measurements. This file
is where that is said, once, for the whole history.

That produced code with a particular failure mode, and it is worth naming
because it will shape yours too. Twice on this project a generated report
asserted a measurement nobody had taken: one claimed a full test suite of eight
tests when the suite was fifty-seven, and one reported a text corruption that
did not exist, which cost a round of work fixing a defect that was never there.
Both were caught by running the thing rather than reading the report.

So the rule this project actually enforces is not about who wrote the code. It
is that a claim without a command and its output is not a claim. That applies to
a person as much as to a model, and the AI disclosure exists so a reviewer knows
which kind of carelessness to look for first.
