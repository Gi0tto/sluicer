"""Read the JSON-LD blocks a page carries in its head or body."""

from __future__ import annotations

import json
import re
from typing import Any

from sluicer.declared.located import Located, Place, xpath_of
from sluicer.declared.types import _SCHEMA_ORG
from sluicer.document import Document

_XPATH = "//script[@type]"
# How many references one path may follow. One is enough for an article's
# author, publisher and image, and keeps the output in proportion: measured on
# 2026-09-22 on a Yoast blog post, one hop gives 22 KB of JSON against 10 KB
# with none and 38 KB with three, because every record re-expands the graph.
MAX_REFERENCE_HOPS = 1
# Deeper than anything downstream reads; see ``_Walk.resolve``.
_MAX_DEPTH = 32
_MEDIA_TYPE = "application/ld+json"


def read_jsonld(doc: Document) -> list[dict[str, Any]]:
    """Return every JSON-LD object in the page, with ``@graph`` flattened.

    A reference -- an object carrying nothing but an ``@id`` -- is replaced by
    the node on the page that defines that ``@id``, in whichever block it sits,
    so an article that names its author by reference (every Yoast page does)
    arrives with the author. A reference nobody defines stays a reference. A
    cycle ends, expansion stops at ``MAX_REFERENCE_HOPS``, and the total copied
    is bounded by a budget, so a hostile graph costs a fixed amount.

    Numbers keep the text the page wrote: ``41.90`` stays ``41.90``.

    Blocks are read as leniently as the consumers pages are written for: a raw
    newline inside a string, an HTML comment or CDATA wrapper, a byte order
    mark, JavaScript's ``//`` and ``/* */`` comments and a trailing comma are
    all common and none loses the block; a string's text is never mended. What
    still is not JSON is skipped, and so is a block nested past the parser's
    limit; the good blocks on the page are kept.

    The media type is matched ignoring case, whitespace and parameters:
    "application/ld+json;charset=UTF-8" is "application/LD+JSON".
    """
    found: list[dict[str, Any]] = []
    places: list[Place] = []
    for script in doc.tree.xpath(_XPATH):
        if not _is_ld_json(script.get("type") or ""):
            continue
        raw = (script.text_content() or "").strip()
        if not raw:
            continue
        parsed = _parse(raw)
        if parsed is not None:
            # Every node of one block is placed from one string, its own.
            block: Place = xpath_of(script) + "#"
            for node, steps in _flatten(parsed):
                found.append(node)
                at = block
                for step in steps:
                    at = (at, step)
                places.append(at)
    index, defined_at = _definitions(found, places)
    # Every copy a reference makes is paid for from one budget, ten times what
    # the page holds, in values and in characters: four thousand references to
    # one node of four thousand items were four gigabytes of copies from a
    # 119 KB page. Past the budget
    # a reference stays a reference, in document order, so the answer is
    # deterministic.
    walk = _Walk(index, [max(10_000, 10 * _size(found))], defined_at)
    # A top-level node is a dict, and resolving one gives a dict back; one
    # that was only a reference is where its definition is.
    return [
        resolved
        if isinstance(resolved := walk.resolve(node, _own_id(node), 0), Located)
        else Located(resolved, at)
        for node, at in zip(found, places, strict=True)
    ]


_OPENING = re.compile(r"^\s*(?:(?://|/\*)\s*)?(?:<!\[CDATA\[|<!--)\s*(?:\*/)?")
# A JSON string, read to its end or to the block's: what the two patterns
# below look for inside one is text. Left open, it runs to the end, and so does
# a comment, so no character is scanned twice whatever the block holds.
_STRING = r'"(?:[^"\\]|\\.)*(?:"|\Z)'
_COMMENT = re.compile(_STRING + r"|//[^\n]*|/\*.*?(?:\*/|\Z)", re.DOTALL)
_TRAILING_COMMA = re.compile(_STRING + r"|,(?=\s*[}\]])", re.DOTALL)


def _parse(raw: str) -> object | None:
    """The JSON in one block, every number as its text, or None when there is
    none to be had."""
    unwrapped = raw.lstrip("\ufeff")
    for _ in range(2):
        unwrapped = _without_closing(_OPENING.sub("", unwrapped))
    # The cleaned spellings are tried only after the text as written fails, so
    # a block that is valid JSON is never rewritten.
    for candidate in dict.fromkeys((raw, unwrapped, _mended(unwrapped))):
        try:
            parsed: object = json.loads(
                candidate,
                strict=False,
                parse_float=str,
                parse_int=str,
                parse_constant=lambda _name: None,
            )
        except (ValueError, RecursionError):
            continue
        return parsed
    return None


def _without_closing(text: str) -> str:
    """``text`` without the wrapper that may close it: ``]]>`` or ``-->``,
    after ``//`` or ``/*`` if a comment holds it, before ``*/`` if one does,
    and the whitespace around them to the end.

    Read from the end. As a pattern -- the mark, then whitespace, an
    optional ``*/`` and whitespace again -- a block that went on past its
    mark made the two runs of whitespace backtrack against each other:
    ``-->``, 40,000 spaces and a letter took seven seconds.
    """
    end = text.rstrip()
    if end.endswith("*/"):
        end = end[:-2].rstrip()
    for mark in ("]]>", "-->"):
        if end.endswith(mark):
            before = end[: -len(mark)]
            held = before.rstrip()
            return held[:-2] if held.endswith(("//", "/*")) else before
    return text


def _mended(text: str) -> str:
    """``text`` without JavaScript's comments and a trailing comma's comma.

    Both outside strings only. extruct strips the comments, so a block that
    has them was read there and lost here; and a comma mended inside a string
    changed its text, ``"Pad, ]"`` read as ``"Pad]"``. A comment is a space,
    which is what it separates as.
    """
    text = _COMMENT.sub(lambda m: m[0] if m[0].startswith('"') else " ", text)
    return _TRAILING_COMMA.sub(lambda m: m[0] if m[0].startswith('"') else "", text)


def _is_ld_json(declared: str) -> bool:
    """Is this script's type attribute the JSON-LD media type?"""
    return declared.split(";", 1)[0].strip().lower() == _MEDIA_TYPE


def _flatten(parsed: object) -> list[tuple[dict[str, Any], tuple[str | int, ...]]]:
    """Every top-level node in one block, ``@graph`` and arrays unwrapped.

    Each with the steps that lead to it inside the block -- ``("@graph", 1)``
    -- which make its JSON pointer. A node that holds a ``@graph`` and says
    something of its own besides -- a shop's Product carrying the page's other
    nodes -- is a node too, without its graph: unwrapped, the Product itself
    was lost. It comes after the nodes in its graph, so the order they had
    stays theirs: one shop's Brand holds its Products, and read first, the
    Brand stood where the product the page is about had stood. One that holds
    only a graph, its ``@context`` and its ``@id`` is the graph's wrapper, and
    no node.

    A node read out of a graph keeps the ``@context`` its terms were written
    in: the wrapper's, before any of its own. Without it ``ex:foo``, written
    under ``{"ex": "http://example.com/"}``, named nothing once unwrapped.
    The nodes of one graph that have no context of their own share one. The
    contexts carried are those from the last ``null`` on, which clears every
    context before it, and at most one past ``_MAX_CONTEXTS``: no more are
    read (see ``Terms``), and the one past them says that there were more.
    """
    found: list[tuple[dict[str, Any], tuple[str | int, ...]]] = []
    # A tuple is a node already read, waiting for its graph: JSON makes none.
    # Beside each value, the contexts of the graphs around it, outermost first.
    pending: list[tuple[object, tuple[str | int, ...], list[object]]] = [
        (parsed, (), [])
    ]
    while pending:
        value, steps, around = pending.pop()
        if isinstance(value, tuple):
            found.append((_within(value[0], around), steps))
        elif isinstance(value, list):
            pending.extend(
                (item, (*steps, n), around)
                for n, item in reversed(list(enumerate(value)))
            )
        elif isinstance(value, dict):
            if "@graph" in value:
                own = {key: item for key, item in value.items() if key != "@graph"}
                if any(not key.startswith("@") for key in own):
                    pending.append(((own,), steps, around))
                inner = (
                    _contexts(around, value["@context"])
                    if "@context" in value
                    else around
                )
                pending.append((value["@graph"], (*steps, "@graph"), inner))
            else:
                found.append((_within(value, around), steps))
    return found


def _within(node: dict[str, Any], around: list[object]) -> dict[str, Any]:
    """``node`` holding the contexts of the graphs around it, then its own.

    One context is written as itself, several as the list JSON-LD reads in
    order, a list among them spread into it. A node with no context of its
    own holds its graph's, the one list every such node of the graph shares:
    built for each, a graph of a thousand nodes had a thousand lists, and
    each was read afresh."""
    if not around:
        return node
    contexts = [*around, *_listed(node["@context"])] if "@context" in node else around
    held: dict[str, Any] = {"@context": contexts[0] if len(contexts) == 1 else contexts}
    held.update((key, item) for key, item in node.items() if key != "@context")
    return held


def _contexts(around: list[object], declared: object) -> list[object]:
    """The contexts inside a graph: those around it, then its own, spread,
    from the last ``null`` on and at most one past what ``Terms`` reads."""
    contexts = [*around, *_listed(declared)]
    last_null = max(
        (n for n, context in enumerate(contexts) if context is None), default=None
    )
    if last_null is not None:
        contexts = contexts[last_null:]
    first = 1 if contexts and contexts[0] is None else 0
    return contexts[: first + _MAX_CONTEXTS + 1]


def _listed(declared: object) -> list[object]:
    return declared if isinstance(declared, list) else [declared]


def _own_id(node: dict[str, Any]) -> frozenset[str]:
    identifier = node.get("@id")
    return frozenset({identifier}) if isinstance(identifier, str) else frozenset()


def _definitions(
    nodes: list[dict[str, Any]], places: list[Place]
) -> tuple[dict[str, dict[str, Any]], dict[str, Place]]:
    """Every node on the page that defines an ``@id``, first definition first.

    A definition says something besides its identity; ``{"@id": ...}`` alone is
    a reference, and a reference is not what it refers to. Beside the index,
    where each definition sits.
    """
    index: dict[str, dict[str, Any]] = {}
    defined_at: dict[str, Place] = {}
    # A stack pushed in reverse, so nodes are met in document order and the
    # first definition of an ``@id`` is the one kept.
    pending: list[tuple[object, Place]] = list(
        reversed(list(zip(nodes, places, strict=True)))
    )
    while pending:
        value, chain = pending.pop()
        if isinstance(value, list):
            pending.extend(
                (item, (chain, n)) for n, item in reversed(list(enumerate(value)))
            )
        elif isinstance(value, dict):
            identifier = value.get("@id")
            if (
                isinstance(identifier, str)
                and not _is_reference(value)
                and identifier not in index
            ):
                index[identifier] = value
                defined_at[identifier] = chain
            # A context defines terms, never a node: ``{"@id": ...}`` there is a
            # term's address.
            pending.extend(
                (item, (chain, key))
                for key, item in reversed(list(value.items()))
                if key != "@context"
            )
    return index, defined_at


def _is_reference(value: dict[str, Any]) -> bool:
    return isinstance(value.get("@id"), str) and all(
        key.startswith("@") and key != "@value" for key in value
    )


class _Walk:
    """Reference resolution for one page: its definitions, and its budget."""

    def __init__(
        self,
        index: dict[str, dict[str, Any]],
        budget: list[int],
        defined_at: dict[str, Place],
    ) -> None:
        self.index = index
        self.budget = budget
        self.defined_at = defined_at
        self.sizes: dict[str, int] = {}

    def resolve(
        self, value: Any, path: frozenset[str], hops: int, depth: int = 0
    ) -> Any:
        """``value`` with every reference it holds replaced by what it names.

        Below ``_MAX_DEPTH`` a value is returned as it is: nothing reads that
        deep, and a block nested nearly as far as the JSON parser allows would
        otherwise take this walk past Python's own recursion limit.
        """
        if depth > _MAX_DEPTH:
            return value
        if isinstance(value, list):
            return [self.resolve(item, path, hops, depth + 1) for item in value]
        if not isinstance(value, dict):
            return value
        if _is_reference(value):
            identifier = value["@id"]
            target = self.index.get(identifier)
            if target is None or identifier in path or hops >= MAX_REFERENCE_HOPS:
                return value
            # Not ``setdefault``: its default is evaluated on every call, and
            # sizing the same large node once per reference was the whole cost.
            size = self.sizes.get(identifier)
            if size is None:
                size = self.sizes[identifier] = _size(target)
            if size > self.budget[0]:
                return value
            self.budget[0] -= size
            # What a reference is replaced by was declared at its definition.
            return Located(
                self.resolve(target, path | {identifier}, hops + 1, depth + 1),
                self.defined_at[identifier],
            )
        # A context is carried as the page wrote it, and shared, not copied:
        # a term it defines as ``{"@id": ...}`` names an address, not a node.
        return {
            key: item
            if key == "@context"
            else self.resolve(item, path | _own_id(value), hops, depth + 1)
            for key, item in value.items()
        }


def _size(value: Any) -> int:
    """What a copy of ``value`` costs, counted without recursing.

    One for every value, itself included, and one for every character of its
    text and of its keys. Counting values alone priced a node holding one long
    string at three, so four hundred references to a 4,000-character name were
    copied in full: 1.6 MB of JSON from a 10 KB page. A ``@context`` costs
    nothing: it is shared, never copied.
    """
    count = 0
    pending = [value]
    while pending:
        item = pending.pop()
        count += 1
        if isinstance(item, str):
            count += len(item)
        elif isinstance(item, dict):
            count += sum(len(key) for key in item if key != "@context")
            pending.extend(held for key, held in item.items() if key != "@context")
        elif isinstance(item, list):
            pending.extend(item)
    return count


# --- the names a context gives ------------------------------------------------

# schema.org's namespace, however a context writes it: without its slash too,
# which one real page's ``@vocab`` leaves off, or with a fragment's ``#``.
_SCHEMA_NAMESPACE = re.compile(r"(?i)https?://(?:www\.)?schema\.org/?#?")
# The addresses a block names schema.org's own context by.
_SCHEMA_CONTEXT = re.compile(
    r"(?i)https?://(?:www\.)?schema\.org(?:/(?:docs/jsonldcontext\.jsonld?)?)?"
)
_SCHEMA = "http://schema.org/"
# What no address holds (RFC 3987): a word with one is no term of any vocabulary.
_NOT_IN_AN_IRI = re.compile(r'[\s<>"{}|\\^`]')
# An address: a scheme, then its colon.
_ABSOLUTE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
# What an address must end in for its word to be a prefix, in JSON-LD 1.1.
_GEN_DELIMS = (":", "/", "?", "#", "[", "]", "@")
# The most contexts one word is named through: real blocks nest two or three.
# Each is a layer a word is looked up in, and a block of ten thousand contexts
# listed or nested would make every word under them ten thousand lookups. A
# context not read here, one named by an address elsewhere, counts too.
_MAX_CONTEXTS = 32


class Terms:
    """The names a JSON-LD context gives the words written under it.

    A record names a property or a type as every reader does: a schema.org
    word by its own name, ``name``, however the block wrote it --
    ``schema:name``, ``http://schema.org/name``, a bare ``name`` under
    schema.org's context -- and a word of any other vocabulary by its full
    address, so that a FOAF ``name`` a context defines is never taken for
    schema.org's. A word the context says nothing about is kept as written,
    as it always was: most blocks name schema.org's context, and a block with
    no context, or one naming a context elsewhere, gives no other name to go
    by. Nothing is fetched.

    What is read of a context: its ``@vocab``, its terms, simple or expanded,
    and which of them are prefixes, as JSON-LD 1.1 reads them; and
    schema.org's own context, known by its address. A definition that names
    no address -- a keyword, a reversed property, ``null``, a word the context
    does not define (one real page maps two words to "Text") -- leaves its
    word as written, and so does a context elsewhere, whose words are not
    known here. Scoped contexts and ``@base`` are not read.

    Each context read is a layer over the terms it was read in, holding what
    it defines and nothing else: a context is never copied, so a thousand
    nodes each with a context of their own cost their thousand contexts,
    not a thousand copies of every term around them. Each context is read
    once for the terms it is read in. A word is looked up layer by layer,
    so at most ``_MAX_CONTEXTS`` are read since the last ``null``, outermost
    first. Past them the words are named as if no context had been read, as
    under a context elsewhere, until a ``null`` clears them all: through the
    contexts that were read, a word one past them defines again would have
    been named as it is not.
    """

    def __init__(
        self,
        vocab: str | None = None,
        iris: dict[str, str | _Undefined | None] | None = None,
        prefixes: dict[str, str | None] | None = None,
        outer: Terms | None = None,
        *,
        past_the_most: bool = False,
    ) -> None:
        self.vocab = vocab
        # The words this layer's context defines: each one's address, None
        # where its word stays as written, _UNDEFINED where it is left to the
        # vocabulary as a word no context defines.
        self.iris = iris or {}
        # The same words as prefixes: an address, or None where it is none.
        self.prefixes = prefixes or {}
        self.outer = outer
        self.depth: int = 0 if outer is None else outer.depth + 1
        # Terms under more contexts than are read: they read none but a null.
        self.past_the_most = past_the_most
        # The terms inside each context declared under these, read once: one
        # graph's thousand nodes share one context. A string is known by its
        # text, anything else by itself.
        self._inside: dict[object, tuple[object, Terms]] = {}

    def within(self, declared: object) -> Terms:
        """The terms in force inside a node whose ``@context`` is ``declared``."""
        if not isinstance(declared, list):
            return self._through(declared)
        held = self._inside.get(id(declared))
        if held is not None and held[0] is declared:
            return held[1]
        terms = self
        for context in declared:
            terms = terms._through(context)
        self._inside[id(declared)] = (declared, terms)
        return terms

    def _through(self, context: object) -> Terms:
        """The terms in force inside one context, read once."""
        key = context if isinstance(context, str) else id(context)
        held = self._inside.get(key)
        if held is not None and (held[0] is context or isinstance(context, str)):
            return held[1]
        if context is None:
            terms = self._read(context)
        elif self.past_the_most:
            terms = self
        elif self.depth >= _MAX_CONTEXTS:
            terms = Terms(past_the_most=True)
        else:
            terms = self._read(context)
        self._inside[key] = (context, terms)
        return terms

    def name(self, word: str) -> str:
        """``word``, a property or a type, as a record names it.

        A word no address can hold -- ``JW Videos``, a key written with a
        trailing space -- is kept as written, and so is a bare word under
        schema.org's vocabulary, which is its own name there."""
        if word.startswith("@") or _NOT_IN_AN_IRI.search(word):
            return word
        iri = self._iri(word)
        if iri is None:
            return word
        prefix, _, suffix = word.partition(":")
        if iri is word and not suffix.startswith("//") and self._defines(prefix):
            # ``schema:Product`` is schema.org's only where the context leaves
            # ``schema`` alone: one it defines as no prefix makes it an
            # address of its own, as JSON-LD reads it.
            return word
        schema_org = _SCHEMA_ORG.fullmatch(iri)
        return schema_org.group(1) if schema_org else iri

    def type(self, word: str) -> str | None:
        """A declared type as records fold on it, or None for a blank one."""
        token = word.strip()
        return self.name(token) if token else None

    def _iri(self, word: str) -> str | None:
        """``word``'s address, or None where it has none to be named by. A
        word with a colon that no prefix expands is an address already."""
        found = self._term(word)
        if not isinstance(found, _Undefined):
            return found
        prefix, colon, suffix = word.partition(":")
        if colon:
            base = self._prefix(prefix)
            if base is not None and not suffix.startswith("//"):
                return base + suffix
            return None if prefix == "_" else word
        if self.vocab is None or self.vocab == _SCHEMA:
            return None
        return self.vocab + word

    def _term(self, word: str) -> str | _Undefined | None:
        """What the innermost layer defining ``word`` says it is."""
        layer: Terms | None = self
        while layer is not None:
            if word in layer.iris:
                return layer.iris[word]
            layer = layer.outer
        return _UNDEFINED

    def _defines(self, word: str) -> bool:
        """Whether a context in force defines ``word``, to anything."""
        layer: Terms | None = self
        while layer is not None:
            if word in layer.iris:
                return True
            layer = layer.outer
        return False

    def _prefix(self, word: str) -> str | None:
        """The address ``word`` expands as a prefix, or None if it is none."""
        layer: Terms | None = self
        while layer is not None:
            if word in layer.prefixes:
                return layer.prefixes[word]
            layer = layer.outer
        return None

    def _read(self, context: object) -> Terms:
        if context is None:
            return Terms()
        if isinstance(context, str):
            if _SCHEMA_CONTEXT.fullmatch(context.strip()):
                return Terms(_SCHEMA, None, {"schema": _SCHEMA}, self)
            # A layer that defines nothing, so that it counts as one read.
            return Terms(self.vocab, None, None, self)
        if not isinstance(context, dict):
            return Terms(self.vocab, None, None, self)
        # Every term the context names hides what outer contexts said of it,
        # even one it leaves undefined.
        iris: dict[str, str | _Undefined | None] = {}
        prefixes: dict[str, str | None] = {}
        reading = _Reading(self)
        for term, definition in context.items():
            if not isinstance(term, str) or term.startswith("@"):
                continue
            iris[term] = _UNDEFINED
            prefixes[term] = None
            reading.define(term, definition)
        for term, iri in reading.addresses().items():
            iris[term] = iri
            if reading.is_prefix(term, iri):
                assert iri is not None
                prefixes[term] = _SCHEMA if _SCHEMA_NAMESPACE.fullmatch(iri) else iri
        # Where an undefined word's address would begin. JSON-LD 1.1 reads
        # @vocab before the terms beside it, so it may be written through a
        # prefix or a term of the contexts around, never of its own.
        vocab = self.vocab
        if "@vocab" in context:
            declared = context["@vocab"]
            vocab = self._iri(declared) if isinstance(declared, str) else None
            if vocab is not None and _SCHEMA_NAMESPACE.fullmatch(vocab):
                vocab = _SCHEMA
        return Terms(vocab, iris, prefixes, self)


class _Undefined:
    """What a layer holds for a word it leaves to the vocabulary."""


_UNDEFINED = _Undefined()


# How many rounds one context's terms are read in: a term defined through
# another is read the round after it, so a chain of definitions longer than
# this names no address. Real contexts chain one or two; five thousand terms
# each defined through the one before would otherwise be read to their end.
_ROUNDS = 8


class _Wait:
    """What a definition is read to while it needs a term not read yet."""


_WAIT = _Wait()


class _Reading:
    """One context's term definitions, read to their addresses in rounds.

    Each round reads a term from what earlier rounds read, never from the
    same round's, so which address a term gets does not depend on the order
    the context lists them in, and a cycle simply never ends.
    """

    def __init__(self, outer: Terms) -> None:
        self.outer = outer
        # What each term's definition writes as its address; None where it
        # writes none (a keyword, ``null``, a reversed property).
        self.targets: dict[str, str | None] = {}
        # JSON-LD 1.1's prefix flag: a simple definition's term is a prefix
        # when its address ends in a delimiter, an expanded one's when it
        # says ``"@prefix": true``.
        self.simple: set[str] = set()
        self.flagged: set[str] = set()
        self.read: dict[str, str | None] = {}

    def define(self, term: str, definition: object) -> None:
        if isinstance(definition, dict):
            if "@reverse" in definition:
                self.targets[term] = None
                return
            if "@id" not in definition:
                # Its address is the vocabulary's word, as an undefined one's.
                return
            if definition.get("@prefix") is True:
                self.flagged.add(term)
            definition = definition["@id"]
        elif isinstance(definition, str) and ":" not in term and "/" not in term:
            self.simple.add(term)
        written = definition if isinstance(definition, str) else None
        self.targets[term] = None if written is None or written[:1] == "@" else written

    def addresses(self) -> dict[str, str | None]:
        """Every defined term's address, or None."""
        pending = {term: t for term, t in self.targets.items() if t is not None}
        self.read = {term: None for term, t in self.targets.items() if t is None}
        for _ in range(_ROUNDS):
            found = {
                term: step
                for term, target in pending.items()
                if not isinstance(step := self.expand(target), _Wait)
            }
            if not found:
                break
            self.read.update(found)
            pending = {term: t for term, t in pending.items() if term not in found}
        self.read.update(dict.fromkeys(pending))
        return self.read

    def is_prefix(self, term: str, iri: str | None) -> bool:
        """Whether ``term``, read to ``iri``, expands the words it prefixes."""
        if iri is None:
            return False
        return term in self.flagged or (
            term in self.simple and iri.endswith(_GEN_DELIMS)
        )

    def expand(self, written: str) -> str | _Wait | None:
        """An address as a definition writes it -- whole, through a prefix, or
        as another term -- from the terms read so far; ``_WAIT`` when it needs
        one not read yet, None when it names none."""
        prefix, colon, suffix = written.partition(":")
        if colon:
            if prefix == "_":
                return None
            if suffix.startswith("//"):
                return written
            if prefix in self.targets:
                if prefix not in self.read:
                    return _WAIT
                base = self.read[prefix]
                if self.is_prefix(prefix, base):
                    assert base is not None
                    return base + suffix
            elif (outer := self.outer._prefix(prefix)) is not None:
                return outer + suffix
            return written if _ABSOLUTE.match(written) else None
        if written in self.targets:
            return self.read.get(written, _WAIT)
        found = self.outer._term(written)
        return None if isinstance(found, _Undefined) else found
