"""Which AI agents a site's robots.txt lets have a page, and what each is for.

The list is the vendors' own: every agent below is named on a page its vendor
publishes about its crawlers, cited on the agent and read on 2026-09-23, and
nothing is added from a third-party list. Two consequences are deliberate.
``anthropic-ai`` and ``cohere-ai``, which many robots.txt files name, are on no
vendor's page: Anthropic's lists ClaudeBot, Claude-User and Claude-SearchBot,
and Cohere's lists none. ByteDance publishes no page about Bytespider
at all. A robots.txt naming any of them has that reported as a name
no documented agent answers to (``other_agents``), which is the finding: a
site that thinks it has turned one of these away may have turned away nobody.

Ad crawlers (OAI-AdsBot, Meta-ExternalAds) and link-preview fetchers are left
out: they are on the same pages, and are not what the page is being read for.

Whether an agent may have the page is read by protego, the robots.txt parser
Sluicer obeys itself, from the agent's product token. Some vendors say a fetch
a user asked for may not honour robots.txt at all; ``honours_robots`` carries
what the vendor says, so an ``allowed: false`` beside ``honours_robots:
false`` reads as what it is: a request the site made, which the agent may not
follow.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlsplit

from sluicer.audit.report import CrawlerVerdict, SiteFile
from sluicer.declared.headers import stated
from sluicer.extras import import_extra

_OPENAI = "https://developers.openai.com/api/docs/bots"
_ANTHROPIC = (
    "https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-"
    "from-the-web-and-how-can-site-owners-block-the-crawler"
)
_GOOGLE = "https://developers.google.com/crawling/docs/crawlers-fetchers/"
_PERPLEXITY = "https://docs.perplexity.ai/docs/resources/perplexity-crawlers"
_APPLE = "https://support.apple.com/en-us/119829"
_AMAZON = "https://developer.amazon.com/amazonbot"
_META = "https://developers.facebook.com/docs/sharing/webmasters/web-crawlers/"
_MISTRAL = "https://docs.mistral.ai/robots"

VENDOR_PAGES = (
    ("OpenAI", _OPENAI),
    ("Anthropic", _ANTHROPIC),
    ("Google", _GOOGLE + "google-common-crawlers"),
    ("Google", _GOOGLE + "google-user-triggered-fetchers"),
    ("Perplexity", _PERPLEXITY),
    ("Common Crawl", "https://commoncrawl.org/ccbot"),
    ("Apple", _APPLE),
    ("Amazon", _AMAZON),
    ("Meta", _META),
    ("Mistral", _MISTRAL),
    (
        "DuckDuckGo",
        "https://duckduckgo.com/duckduckgo-help-pages/results/duckassistbot",
    ),
    ("Cohere", "https://docs.cohere.com/docs/cohere-web-crawlers"),
)
"""Every vendor page read, Cohere's included, which lists no crawler."""

USES = ("training", "search", "user", "dataset", "agents")
"""``training``: content for training models. ``search``: an index an AI
assistant answers from. ``user``: a page fetched because a person asked the
assistant for it. ``dataset``: an open crawl others train on. ``agents``: a
crawl a site owner asked for, to build their own agents."""


@dataclass(frozen=True)
class Agent:
    """One AI agent, as its vendor's page describes it."""

    token: str
    vendor: str
    use: str
    honours_robots: bool | None
    note: str
    doc: str


AGENTS: tuple[Agent, ...] = (
    Agent(
        "GPTBot",
        "OpenAI",
        "training",
        True,
        "Disallowing it says the content should not be used to train "
        "OpenAI's foundation models.",
        _OPENAI,
    ),
    Agent(
        "OAI-SearchBot",
        "OpenAI",
        "search",
        True,
        "Surfaces sites in ChatGPT's search features.",
        _OPENAI,
    ),
    Agent(
        "ChatGPT-User",
        "OpenAI",
        "user",
        False,
        "Visits a page when a ChatGPT user asks; OpenAI says robots.txt rules "
        "may not apply.",
        _OPENAI,
    ),
    Agent(
        "ClaudeBot",
        "Anthropic",
        "training",
        True,
        "Collects content that could contribute to training Anthropic's models.",
        _ANTHROPIC,
    ),
    Agent(
        "Claude-User",
        "Anthropic",
        "user",
        True,
        "Fetches a page when a Claude user asks; Anthropic says its bots "
        "honour robots.txt.",
        _ANTHROPIC,
    ),
    Agent(
        "Claude-SearchBot",
        "Anthropic",
        "search",
        True,
        "Indexes content to improve Claude's search results.",
        _ANTHROPIC,
    ),
    Agent(
        "Google-Extended",
        "Google",
        "training",
        True,
        "A control token with no crawler of its own: whether content Google "
        "crawls may train Gemini models and ground Gemini's answers. It does "
        "not affect Google Search.",
        _GOOGLE + "google-common-crawlers",
    ),
    Agent(
        "Google-CloudVertexBot",
        "Google",
        "agents",
        True,
        "Crawls site owners request for building Vertex AI agents.",
        _GOOGLE + "google-common-crawlers",
    ),
    Agent(
        "Google-Agent",
        "Google",
        "user",
        False,
        "Agents on Google's infrastructure acting on a user's request; Google "
        "says user-triggered fetchers generally ignore robots.txt.",
        _GOOGLE + "google-user-triggered-fetchers",
    ),
    Agent(
        "Google-GeminiNotebook",
        "Google",
        "user",
        False,
        "URLs Gemini Notebook users add as sources (formerly Google-NotebookLM); "
        "user-triggered, so generally not bound by robots.txt.",
        _GOOGLE + "google-user-triggered-fetchers",
    ),
    Agent(
        "PerplexityBot",
        "Perplexity",
        "search",
        True,
        "Surfaces and links sites in Perplexity's results; Perplexity says it is "
        "not used to crawl content for AI foundation models.",
        _PERPLEXITY,
    ),
    Agent(
        "Perplexity-User",
        "Perplexity",
        "user",
        False,
        "Fetches a page when a Perplexity user asks; Perplexity says it "
        "generally ignores robots.txt.",
        _PERPLEXITY,
    ),
    Agent(
        "CCBot",
        "Common Crawl",
        "dataset",
        True,
        "Builds Common Crawl's open repository of web crawl data.",
        "https://commoncrawl.org/ccbot",
    ),
    Agent(
        "Applebot",
        "Apple",
        "search",
        True,
        "Apple's search crawler (Spotlight, Siri, Safari); what it crawls may "
        "also train Apple's models unless Applebot-Extended is disallowed.",
        _APPLE,
    ),
    Agent(
        "Applebot-Extended",
        "Apple",
        "training",
        True,
        "Crawls nothing: whether what Applebot crawled may train Apple's "
        "foundation models.",
        _APPLE,
    ),
    Agent(
        "Amazonbot",
        "Amazon",
        "training",
        True,
        "Improves Amazon's products and services and may be used to train "
        "Amazon AI models.",
        _AMAZON,
    ),
    Agent(
        "Amzn-SearchBot",
        "Amazon",
        "search",
        True,
        "Search experiences such as Alexa; where robots.txt does not name it, it "
        "follows the rules given to other search bots.",
        _AMAZON,
    ),
    Agent(
        "Amzn-User",
        "Amazon",
        "user",
        False,
        "Fetches live information for a user's request; Amazon says it may not "
        "follow all robots.txt directives.",
        _AMAZON,
    ),
    Agent(
        "Meta-ExternalAgent",
        "Meta",
        "training",
        True,
        "Training foundation AI models, or improving products by indexing "
        "content directly.",
        _META,
    ),
    Agent(
        "Meta-WebIndexer",
        "Meta",
        "search",
        True,
        "Improves Meta AI's search results, citing and linking content.",
        _META,
    ),
    Agent(
        "Meta-ExternalFetcher",
        "Meta",
        "user",
        False,
        "Fetches links at a user's request; Meta says it may bypass robots.txt.",
        _META,
    ),
    Agent(
        "MistralAI-Training",
        "Mistral",
        "training",
        True,
        "Builds datasets for training Mistral's generative models.",
        _MISTRAL,
    ),
    Agent(
        "MistralAI-Index",
        "Mistral",
        "search",
        True,
        "Indexes content for Mistral search; not used for training.",
        _MISTRAL,
    ),
    Agent(
        "MistralAI-User",
        "Mistral",
        "user",
        True,
        "Visits a page when a user asks Vibe; Mistral says it governs which "
        "sites those requests reach.",
        _MISTRAL,
    ),
    Agent(
        "DuckAssistBot",
        "DuckDuckGo",
        "search",
        True,
        "Crawls in real time for DuckDuckGo's AI-assisted answers; not used to "
        "train models.",
        "https://duckduckgo.com/duckduckgo-help-pages/results/duckassistbot",
    ),
)


def user_agents(text: str) -> list[str]:
    """Every name a ``User-agent`` line in ``text`` gives, lowercased, in order."""
    names: list[str] = []
    for line in text.splitlines():
        key, colon, value = line.split("#", 1)[0].partition(":")
        if colon and key.strip().lower() == "user-agent":
            name = value.strip().lower()
            if name and name not in names:
                names.append(name)
    return names


def deciding_group(token: str, names: list[str]) -> str | None:
    """The ``User-agent`` name whose group applies to ``token``, as protego picks.

    protego matches a group's name inside the agent's name at a token
    boundary, the longest match wins, and ``*`` matches anything with the
    lowest score; this is its rule, restated to name the line.
    """
    robot = token.lower()
    best, score = None, 0
    for name in names:
        if name == "*":
            found = 1
        else:
            found = 0
            index = robot.find(name)
            while index != -1:
                if index == 0 or not (
                    robot[index - 1].isalnum() or robot[index - 1] in "-_"
                ):
                    found = len(name)
                    break
                index = robot.find(name, index + 1)
        if found > score:
            best, score = name, found
    return best


def verdicts(url: str, robots: SiteFile) -> tuple[list[CrawlerVerdict], list[str]]:
    """Each agent's verdict on ``url``, and the names no agent here answers to.

    A robots.txt that answered 4xx has no rules and allows everything, as RFC
    9309 says; one that could not be read has every verdict None, which RFC
    9309 would have a crawler treat as a refusal.

    Raises:
        FetchExtraMissing: protego, part of the ``fetch`` extra, is not
            installed.
    """
    readable = robots.found or (
        robots.status is not None and 400 <= robots.status < 500
    )
    text = (robots.text or "") if robots.found else ""
    names = user_agents(text)
    parser = _parse(text) if text else None
    known = {agent.token.lower() for agent in AGENTS}
    groups = _groups(text)
    target = _target(url)
    found = [
        CrawlerVerdict(
            agent=agent.token,
            vendor=agent.vendor,
            use=agent.use,
            allowed=(
                None
                if not readable
                else parser is None or bool(parser.can_fetch(url, agent.token))
            ),
            group=deciding_group(agent.token, names) if readable else None,
            honours_robots=agent.honours_robots,
            note=agent.note,
            doc=agent.doc,
            **_preferences(groups, deciding_group(agent.token, names), target),
        )
        for agent in AGENTS
    ]
    # No preference is stated for a page the agent may not fetch: "usage
    # preferences apply only to those resources that can be crawled".
    found = [
        verdict
        if verdict.allowed
        else replace(verdict, content_usage={}, content_signal={})
        for verdict in found
    ]
    others = [name for name in names if name != "*" and name not in known]
    return found, others


# What a site says in robots.txt about the use of what it lets be fetched.
# Content-Usage is the IETF aipref working group's rule
# (draft-ietf-aipref-attach-05, section 3), its statement in the vocabulary of
# draft-ietf-aipref-vocab-08; Content-Signal is Cloudflare's, which its managed
# robots.txt writes (draft-romm-aipref-contentsignals-00, an individual draft
# that expired on 2026-04-04). Neither is an RFC.
_USAGE = (
    "content-usage",
    ("train-ai", "ai-use", "search"),
    {"y": "allow", "n": "disallow"},
)
_SIGNAL = (
    "content-signal",
    ("search", "ai-input", "ai-train"),
    {"yes": "allow", "no": "disallow"},
)


def _groups(text: str) -> dict[str, list[tuple[str, str]]]:
    """Each ``User-agent`` name's rules, lowercased keys, every group of it merged.

    RFC 9309's grouping: consecutive ``User-agent`` lines open one group, and
    the rules after them belong to it until a ``User-agent`` line follows a
    rule. Rules before any group belong to none.
    """
    rules: dict[str, list[tuple[str, str]]] = {}
    current: list[str] = []
    opening = False
    for line in text.splitlines():
        key, colon, value = line.split("#", 1)[0].partition(":")
        if not colon:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if not opening:
                current = []
            opening = True
            name = value.lower()
            if name:
                current.append(name)
                rules.setdefault(name, [])
            continue
        opening = False
        for name in current:
            rules[name].append((key, value))
    return rules


def _target(url: str) -> str:
    """The part of ``url`` a robots.txt path is matched against."""
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def _preferences(
    groups: dict[str, list[tuple[str, str]]], group: str | None, target: str
) -> dict[str, dict[str, str]]:
    """``content_usage`` and ``content_signal``, as the deciding group states them.

    Each rule's value is a path and a statement, or a statement alone, which
    applies everywhere; the rule whose path matches ``target`` longest applies,
    as ``Allow`` and ``Disallow`` do, and rules with that same path combine,
    the most restrictive preference winning each category, as
    draft-ietf-aipref-vocab-08 section 5.1 says.
    """
    rules = groups.get(group or "", [])
    found: dict[str, dict[str, str]] = {}
    for label, categories, meanings in (_USAGE, _SIGNAL):
        best = -1
        chosen: list[str] = []
        for key, value in rules:
            if key != label:
                continue
            path, statement = _path_and_statement(value)
            if not _matches(path, target):
                continue
            if len(path) > best:
                best, chosen = len(path), [statement]
            elif len(path) == best:
                chosen.append(statement)
        combined: dict[str, str] = {}
        for statement in chosen:
            for category, preference in stated(statement, categories, meanings).items():
                if combined.get(category) != "disallow":
                    combined[category] = preference
        found[label.replace("-", "_")] = {
            category: combined[category]
            for category in categories
            if category in combined
        }
    return found


def _path_and_statement(value: str) -> tuple[str, str]:
    """A rule value's path, empty when absent, and its statement of preference.

    A path starts with ``/`` and ends at the first space or tab, as
    draft-ietf-aipref-attach-05 section 3.2 says; a value that does not start
    with ``/`` is a statement alone.
    """
    if not value.startswith("/"):
        return "", value
    for index, char in enumerate(value):
        if char in " \t":
            return value[:index], value[index + 1 :].strip()
    return value, ""


def _matches(path: str, target: str) -> bool:
    """Whether a robots.txt path pattern matches ``target``, RFC 9309 2.2.3.

    ``*`` is any run of characters and a final ``$`` ends the path; anything
    else matches itself, as a prefix of ``target``. Matched with two pointers,
    not a regular expression: a pattern written as ``/*a*a*a*a*b$`` took a
    backtracking regular expression 13 seconds against a 300-character path,
    and a site's robots.txt is anyone's to write.
    """
    anchored = path.endswith("$")
    pattern = path[:-1] if anchored else path + "*"
    at = seen = 0
    star = mark = -1
    while seen < len(target):
        if at < len(pattern) and pattern[at] == "*":
            star, mark = at, seen
            at += 1
        elif at < len(pattern) and pattern[at] == target[seen]:
            at += 1
            seen += 1
        elif star != -1:
            at, mark = star + 1, mark + 1
            seen = mark
        else:
            return False
    return all(char == "*" for char in pattern[at:])


def _parse(text: str) -> Any:
    # Imported here, as ``sluicer.fetch.identity`` does, and for its reason:
    # the class a missing extra raises lives beside the rungs.
    from sluicer.fetch.scrapling_rungs import FetchExtraMissing

    protego = import_extra(
        "protego",
        "fetch",
        doing="Reading a site's robots.txt",
        error=FetchExtraMissing,
    )
    return protego.Protego.parse(text)
