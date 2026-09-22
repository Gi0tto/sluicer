# Roadmap

Ordered by what unblocks the most, not by what is easiest. Each item ships as
working software on its own, with tests, before the next one starts.

## Next

**The scoreboard.** A public, continuously run comparison of extraction quality:
the free annotated datasets plus a multilingual e-commerce split, scored on every
run, with other tools measured beside us and our losses published too. This is
the one that matters. Every claim about being good at this is unfalsifiable
today, in this project and in every other, because nobody publishes the ruler.
Until it exists, this repository makes no claim about being better than anything.

**We announce ourselves.** An identifiable user agent, `robots.txt` respected by
default, and the stealth rung made opt-in rather than automatic. A site owner
should be able to see us coming and turn us away with one line. The most
requested unaddressed issue on the largest project in this field asks exactly
that.

## After that

**Structure induction.** Reading pages that declare nothing, by finding the
repeating shapes in the markup and aligning the fields across them. This is old
research that never shipped as a maintained library, and it is the piece that
turns Sluicer from a reader of well-behaved pages into a reader of the web.

**Trust scoring.** A number saying how much to believe an extraction, computed
without a model: two pages built from the same template must produce the same
fields, and divergence is the signal.

**Schema healing.** When a site changes, say what broke. A pipeline that quietly
returns fewer rows is worse than one that stops.

**Crawling a site.** Sitemaps, `robots.txt` as a map rather than only a rule, and
a queue that resumes. Fetching one page is solved; fetching a site politely is
not, for us.

## Considered and declined

**Fetching as an arms race.** Browsers and anti-bot evasion are full-time work,
and better done by projects that do only that. Sluicer delegates fetching and
says so.

**Extraction with a model.** It would be easier and it would end determinism,
which is the property everything else here rests on.

**A managed service.** There is no plan to sell credits. The constraint that no
feature may require somebody's key is the point, not a stage.
