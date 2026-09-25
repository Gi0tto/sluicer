"""Selectors a person writes, CSS or XPath, and the values they give with their place.

Everything else in Sluicer finds its places itself: the readers where a page
declared a value, induction where it repeats one, an extractor where an
example was. A selector is the place a person names instead, in the two
languages people already write: CSS, with Scrapy's ``::text`` and
``::attr(name)`` to say what of an element is read, and XPath.

    >>> page = parse(html, url)
    >>> page.css("li.product span.price::text").getall()
    ['£51.77', '£53.74']
    >>> page.css("h1")[0].where
    '/html/body/h1[1]'

Every value carries ``where``, the XPath of its element, as every value the
readers give does (see ``sluicer.declared.located.xpath_of``). A value is read
as an extractor reads one: its spaces collapsed, an ``href`` or ``src``
resolved against the page's address. And a selector that cannot be read -- a
bracket left open, a pseudo-element Sluicer does not read, an XPath that
counts rather than selects -- is a ``SelectorError`` that names it, never a
selection of nothing, which is the one answer a broken selector must not give.

CSS is read by cssselect, the translator Scrapy's parsel and lxml's own
``cssselect`` use, into XPath 1.0, which lxml evaluates.
"""

from __future__ import annotations

import functools
import re
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import cssselect
from lxml import etree
from lxml.html import HtmlElement

from sluicer.declared.headers import charset, lowered
from sluicer.declared.located import Positions, xpath_of
from sluicer.document import Document, base_url, join, load

__all__ = [
    "Page",
    "Selected",
    "Selection",
    "Selector",
    "SelectorError",
    "parse",
    "selector",
]


class SelectorError(ValueError):
    """A selector that cannot be read, or asks for what is not on a page: the
    message names the selector and says why."""


# The beginnings an XPath has and a CSS selector never does: a path from the
# root or from here, a parenthesised expression, an attribute of here.
_XPATH_BEGINS = ("/", "./", "../", "(", "@")
# The attributes whose values are addresses, resolved as an extractor
# resolves them.
_ADDRESSES = frozenset({"href", "src"})


@dataclass(frozen=True)
class Selector:
    """A selector as written and as it is evaluated.

    ``kind`` is ``css`` or ``xpath``. For CSS, ``xpath`` is what the
    selector is evaluated as, and ``reads`` says what of each element is
    read: ``element`` its whole text, ``text`` its own text nodes (``::text``,
    which ``xpath`` then selects), ``attribute`` the one named by
    ``attribute`` (``::attr(name)``). An
    XPath reads what it selects, an element, a text or an attribute, and its
    ``reads`` is ``selected``.
    """

    text: str
    kind: str
    xpath: str
    reads: str
    attribute: str | None = None


def selector(text: str) -> Selector:
    """Read a selector in Sluicer's selector language.

    ``xpath:`` or ``css:`` before it says which it is. Otherwise one that
    begins as only an XPath can -- ``/``, ``./``, ``../``, ``(`` or ``@`` -- is
    an XPath, and anything else CSS: ``//h1`` and ``(//li)[1]`` are XPath,
    ``h1``, ``.price`` and ``li > a::attr(href)`` CSS.

    Raises:
        SelectorError: the text is empty, or not a selector of its kind.
    """
    written = text.strip()
    if written.startswith("xpath:"):
        return _xpath(written[len("xpath:") :].strip())
    if written.startswith("css:"):
        return _css(written[len("css:") :].strip())
    if written.startswith(_XPATH_BEGINS) or written in (".", ".."):
        return _xpath(written)
    return _css(written, guessed=True)


def _css(text: str, guessed: bool = False) -> Selector:
    try:
        return _translated(text)
    except SelectorError as broken:
        if not guessed:
            raise
        raise SelectorError(
            f"{broken}; an XPath begins with /, ./ or (, or is written after xpath:"
        ) from None


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


HAS_READ = _version(getattr(cssselect, "__version__", "0")) >= (1, 5)
"""Whether this cssselect translates ``:has()`` right: 1.2 to 1.4 wrote
``:has(b)`` as an XPath lxml refuses (``name() = 'b]'``), and Pyodide ships
1.4. Before 1.5 a selector with ``:has()`` is refused, never half read."""


def _uses_has(group: Any) -> bool:
    """Whether any selector of a parsed group has a ``:has()``, at any depth."""
    pending = [one.parsed_tree for one in group]
    while pending:
        node = pending.pop()
        if type(node).__name__ == "Relation" or (
            type(node).__name__ == "Function" and node.name == "has"
        ):
            return True
        pending.extend(
            value
            for value in vars(node).values()
            if hasattr(value, "__dict__")
            and type(value).__module__.startswith("cssselect")
        )
        for value in vars(node).values():
            if isinstance(value, list):
                pending.extend(
                    item
                    for item in value
                    if type(item).__module__.startswith("cssselect")
                )
    return False


@functools.lru_cache(maxsize=512)
def _translated(text: str) -> Selector:
    """A CSS selector, translated once: pages of one template ask the same."""
    if not text:
        raise SelectorError("a selector is empty")
    try:
        group = cssselect.parse(text)
    except cssselect.SelectorSyntaxError as why:
        raise SelectorError(f"{text!r} is not a CSS selector: {why}") from None
    reading = {_pseudo(text, one.pseudo_element) for one in group}
    if len(reading) > 1:
        raise SelectorError(
            f"{text!r} reads text in one of its selectors and not in another: "
            "every selector of a group must read the same thing"
        )
    reads, attribute = reading.pop()
    if not HAS_READ and _uses_has(group):
        raise SelectorError(
            f"{text!r} uses :has(), which cssselect {cssselect.__version__} "
            "translates to an XPath lxml rejects or one that selects the "
            "wrong elements; "
            "it needs cssselect 1.5 or later"
        )
    translator = cssselect.HTMLTranslator()
    try:
        paths = [
            _descendants(_pseudo_read(translator.selector_to_xpath(one), reads))
            for one in group
        ]
        # Compiled once here, so that what lxml refuses in the translation --
        # a NUL in an attribute's value -- is said when the selector is read.
        etree.XPath(" | ".join(paths))
    except (cssselect.ExpressionError, etree.XPathError, ValueError) as why:
        raise SelectorError(
            f"{text!r} is not a CSS selector Sluicer reads: {why}"
        ) from None
    return Selector(text, "css", " | ".join(paths), reads, attribute)


def _pseudo_read(path: str, reads: str) -> str:
    """The XPath of one CSS selector, with what its pseudo-element reads, as
    parsel -- Scrapy's selectors -- reads it.

    ``::text`` selects the text nodes, so they come in the page's order,
    nested elements' too. After a space, ``div ::text`` (``div *::text``) is
    every text node inside the element, not the text of the elements inside
    it, and ``div ::attr(class)`` the attribute of the element and of
    everything inside it: cssselect ends such a path with ``::*/*``, which
    parsel reads as ``descendant-or-self`` of the element, and so does this.
    """
    inside = path.endswith("::*/*")
    if reads == "text":
        return path[: -len("*/*")] + "text()" if inside else path + "/text()"
    if reads == "attribute" and inside:
        return path[: -len("/*")]
    return path


_ANY_DEPTH = "/descendant-or-self::*/"
# The name test of a step on the child axis: a tag, a namespaced tag, or *.
_NAME_TEST = re.compile(r"\*|[A-Za-z_][\w.\-]*(?::[A-Za-z_][\w.\-]*)?")
# What a predicate can say that makes it ask where its node stands among the
# step's nodes, not what the node is: position() and last() said at its own
# level, or a number.
_POSITIONAL = re.compile(r"\b(?:position|last)\s*\(")
_A_TEST = re.compile(
    r"[=<>]|\band\b|\bor\b|^\s*(?:@|\.(?!\d)|self::|descendant::|ancestor|not\(|"
    r"contains\(|starts-with\(|boolean\(|true\(|false\(|lang\()"
)


def _descendants(path: str) -> str:
    """``path`` with each ``/descendant-or-self::*/`` step before a tag read as
    ``/descendant::``, where the two select the same elements.

    cssselect writes CSS's descendant combinator, ``div a``, as
    ``descendant-or-self::div/descendant-or-self::*/a``: every element under
    every div, then the children of each, which libxml2 gathers and sorts div
    by div. On a real 390 KB page that was 3.3 seconds for ``div a`` and 8.4
    for ``div div div a``, and on a 5.3 MB page an honest ``div a`` ran past
    the 30 seconds a selector is given over MCP (``sluicer.isolated``).
    ``descendant-or-self::div/descendant::a`` is the same links, in the same
    order, in 26 ms.

    The two are the same set whenever the tag's predicates ask only what an
    element is -- a class, a count of its siblings, what it holds -- and not
    where it stands among the step's elements: ``a[1]`` is each parent's first
    link after ``descendant-or-self::*/``, and the first link of all after
    ``descendant::``. cssselect's own predicates never ask; any that says
    ``position()`` or ``last()`` at its own level, or is not plainly a test,
    is left as cssselect wrote it. Text inside a string is never read as a
    step: ``[@title = '/descendant-or-self::*/a']`` is a title.
    """
    out: list[str] = []
    start = 0
    at = 0
    quote = ""
    while at < len(path):
        char = path[at]
        if quote:
            if char == quote:
                quote = ""
            at += 1
            continue
        if char in "'\"":
            quote = char
            at += 1
            continue
        if path.startswith(_ANY_DEPTH, at):
            step = at + len(_ANY_DEPTH)
            name = _NAME_TEST.match(path, step)
            if name is not None and not path.startswith(("::", "("), name.end()):
                end = _after_predicates(path, name.end())
                if end is not None and all(
                    _not_positional(p) for p in _predicates(path[name.end() : end])
                ):
                    out.append(path[start:at])
                    out.append("/descendant::")
                    start = step
                    at = step
                    continue
            at = step
            continue
        at += 1
    out.append(path[start:])
    return "".join(out)


def _after_predicates(path: str, at: int) -> int | None:
    """Where the predicates of the step whose name test ends at ``at`` end,
    or None when a bracket or a quote is left open."""
    depth = 0
    quote = ""
    while at < len(path):
        char = path[at]
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth < 0:
                return None
        elif depth == 0:
            return at
        at += 1
    return at if depth == 0 and not quote else None


def _predicates(text: str) -> list[str]:
    """Each top-level predicate of ``text``, ``[a][b]``, as its own level
    reads it: what it nests in brackets and strings left out."""
    found: list[str] = []
    level: list[str] = []
    depth = 0
    quote = ""
    for char in text:
        if quote:
            quote = "" if char == quote else quote
            continue
        if char in "'\"":
            quote = char
            if depth == 1:
                level.append("''")
            continue
        if char == "[":
            depth += 1
            if depth == 2:
                level.append("[]")
            continue
        if char == "]":
            depth -= 1
            if depth == 0:
                found.append("".join(level))
                level = []
            continue
        if depth == 1:
            level.append(char)
    return found


def _not_positional(predicate: str) -> bool:
    """Whether a predicate, as its own level reads it, is a test of the
    element alone: no position() or last() at that level, and plainly true or
    false rather than a number."""
    return not _POSITIONAL.search(predicate) and bool(_A_TEST.search(predicate))


def _pseudo(text: str, pseudo: Any) -> tuple[str, str | None]:
    """What a CSS selector's pseudo-element says to read of each element."""
    if pseudo is None:
        return "element", None
    if isinstance(pseudo, cssselect.parser.FunctionalPseudoElement):
        if pseudo.name != "attr":
            raise _unread(text, f"::{pseudo.name}()")
        named = [a for a in pseudo.arguments if a.type != "S"]
        if len(named) != 1 or named[0].type not in ("IDENT", "STRING"):
            raise SelectorError(
                f"{text!r}: ::attr() takes one attribute's name, as ::attr(href)"
            )
        # HTML's attribute names are lowercase once parsed, however written.
        return "attribute", str(named[0].value).lower()
    if pseudo == "text":
        return "text", None
    raise _unread(text, f"::{pseudo}")


def _unread(text: str, pseudo: str) -> SelectorError:
    return SelectorError(
        f"{text!r}: {pseudo} is not a pseudo-element Sluicer reads; "
        "::text and ::attr(name) are"
    )


@functools.lru_cache(maxsize=512)
def _xpath(text: str) -> Selector:
    if not text:
        raise SelectorError("a selector is empty")
    try:
        # Asked of an empty page once, so what only evaluating tells -- a
        # prefix nothing binds, a function lxml does not know, an answer that
        # is a number rather than nodes -- is said when the selector is
        # written, not first on some page an extractor is run on.
        given = etree.XPath(text)(_EMPTY)
    except (etree.XPathError, ValueError) as why:
        # ValueError: lxml's own refusal of a NUL or a control character.
        raise SelectorError(f"{text!r} is not an XPath: {why}") from None
    if not isinstance(given, list):
        raise SelectorError(
            f"{text!r} gives {_what(given)}, not elements, their text or their "
            "attributes: a value with no place on the page"
        )
    return Selector(text, "xpath", text, "selected")


_EMPTY = etree.Element("html")


# lxml's compiled XPath is kept one per thread: the HTTP server answers two
# requests at once, and an evaluator is not to be shared between threads.
_compiled = threading.local()


def _evaluator(xpath: str) -> etree.XPath:
    kept: dict[str, etree.XPath] | None = getattr(_compiled, "kept", None)
    if kept is None:
        kept = _compiled.kept = {}
    found = kept.get(xpath)
    if found is None:
        if len(kept) > 512:
            kept.clear()
        found = kept[xpath] = etree.XPath(xpath)
    return found


class Selected:
    """One value a selector gave, and where it was: ``value``, the text or the
    attribute read, its spaces collapsed; ``where``, the XPath of its element.

    A value read from an element can be selected inside, as the page is, by
    ``css``, ``xpath`` and ``select``: the rows of a listing, then each row's
    fields. A text or an attribute has nothing inside it.
    """

    __slots__ = ("_attribute", "_node", "_page", "value", "where")

    def __init__(
        self,
        value: str,
        where: str,
        node: HtmlElement | None,
        page: Page,
        attribute: str | None = None,
    ) -> None:
        self.value = value
        self.where = where
        self._node = node
        self._page = page
        self._attribute = attribute

    def __repr__(self) -> str:
        return f"Selected(value={self.value!r}, where={self.where!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Selected):
            return NotImplemented
        return (self.value, self.where) == (other.value, other.where)

    def __hash__(self) -> int:
        return hash((self.value, self.where))

    def css(self, text: str) -> Selection:
        """What the CSS selector ``text`` gives inside this element."""
        return self._page._select(_css(text.strip()), [self._inside()])

    def xpath(self, text: str) -> Selection:
        """What the XPath ``text`` gives from this element: ``.//a`` inside
        it, ``//a`` anywhere on the page, as XPath reads them."""
        return self._page._select(_xpath(text.strip()), [self._inside()])

    def select(self, text: str) -> Selection:
        """What ``text``, CSS or XPath as ``selector`` tells them apart, gives
        inside this element."""
        return self._page._select(selector(text), [self._inside()])

    def _inside(self) -> HtmlElement:
        if self._node is None:
            raise SelectorError(
                f"{self.value!r} is a text or an attribute, not an element: "
                "there is nothing to select inside it"
            )
        return self._node


class Selection(tuple[Selected, ...]):
    """The values a selector gave, in the page's order, each a ``Selected``.

    A tuple, with ``get()`` for the first value, or a default when there is
    none, ``getall()`` for every value, and ``css``, ``xpath`` and ``select``
    to select inside each of its elements in turn.
    """

    __slots__ = ()

    def get(self, default: str | None = None) -> str | None:
        """The first value, or ``default`` when there is none."""
        return self[0].value if self else default

    def getall(self) -> list[str]:
        """Every value, in the page's order."""
        return [one.value for one in self]

    def css(self, text: str) -> Selection:
        """What the CSS selector ``text`` gives inside each element, in turn."""
        return self._each(lambda one: one.css(text))

    def xpath(self, text: str) -> Selection:
        """What the XPath ``text`` gives from each element, in turn."""
        return self._each(lambda one: one.xpath(text))

    def select(self, text: str) -> Selection:
        """What ``text``, CSS or XPath, gives inside each element, in turn."""
        return self._each(lambda one: one.select(text))

    def _each(self, select: Any) -> Selection:
        return Selection(found for one in self for found in select(one))


class Page:
    """A page parsed once, to select from as many times as needed.

    ``css(selector)`` and ``xpath(selector)`` give a ``Selection`` of the
    values a selector of that language gives, ``select(selector)`` of one in
    either, told apart as ``selector`` tells them. ``url`` is the address the
    page came from, which its links are resolved against. ``parse`` makes one.
    """

    def __init__(self, doc: Document) -> None:
        self._doc = doc
        self.url = doc.url
        # Each parent's children, counted once for every place spelt on the
        # page: four thousand rows among four thousand siblings stay linear.
        self._positions: Positions = {}

    def __repr__(self) -> str:
        return f"Page(url={self.url!r})"

    def css(self, text: str) -> Selection:
        """What the CSS selector ``text`` gives on the page.

        ``::text`` reads an element's own text nodes, each one a value, and
        ``::attr(name)`` its attribute, as Scrapy's parsel does: after a
        space, ``div ::text`` is every text node inside the element, and
        ``div ::attr(name)`` the attribute of the element and of everything
        inside it. Without either, the element's whole text is its value. A
        text node or an attribute of spaces alone, or an element without the
        attribute, gives no value; an element with no text gives an empty
        one, so every row of a listing is counted.

        Raises:
            SelectorError: ``text`` is not a CSS selector Sluicer reads.
        """
        return self._select(_css(text.strip()), [self._doc.tree])

    def xpath(self, text: str) -> Selection:
        """What the XPath ``text`` gives on the page: elements, their text
        nodes or their attributes, each with its element's place.

        Raises:
            SelectorError: ``text`` is not an XPath, or gives what has no
                place on the page -- a number, a text of its own such as
                ``string()``'s, true or false -- or selects a comment.
        """
        return self._select(_xpath(text.strip()), [self._doc.tree])

    def select(self, text: str) -> Selection:
        """What ``text`` gives on the page, CSS or XPath as ``selector`` tells
        them apart: the one language every place a person names is written in.

        Raises:
            SelectorError: ``text`` is neither.
        """
        return self._select(selector(text), [self._doc.tree])

    def _select(self, chosen: Selector, contexts: Iterable[HtmlElement]) -> Selection:
        """``chosen`` evaluated from each of ``contexts``, its values read."""
        found: list[Selected] = []
        evaluate = _evaluator(chosen.xpath)
        for context in contexts:
            try:
                nodes = evaluate(context)
            except etree.XPathError as why:
                raise SelectorError(f"{chosen.text!r} is not an XPath: {why}") from None
            if not isinstance(nodes, list):
                raise SelectorError(
                    f"{chosen.text!r} gives {_what(nodes)}, not elements, their "
                    "text or their attributes: a value with no place on the page"
                )
            for node in nodes:
                found.extend(self._read(chosen, node))
        return Selection(found)

    def _read(self, chosen: Selector, node: Any) -> Iterable[Selected]:
        if isinstance(node, HtmlElement):
            if chosen.reads == "attribute":
                assert chosen.attribute is not None
                value = self._attribute(chosen.attribute, node.get(chosen.attribute))
                if value:
                    yield self._selected(value, node, None, chosen.attribute)
            else:
                said = " ".join(node.text_content().split())
                yield self._selected(said, node, node)
            return
        if (
            isinstance(node, etree._ElementUnicodeResult)
            and (owner := node.getparent()) is not None
        ):
            if node.is_attribute:
                value = self._attribute(str(node.attrname), str(node))
                if value:
                    yield self._selected(value, owner, None, str(node.attrname))
                return
            # A text after an element, its tail, is the parent's text.
            if node.is_tail:
                owner = owner.getparent()
            said = " ".join(node.split())
            if said and owner is not None:
                yield self._selected(said, owner, None)
            return
        if isinstance(node, str):
            raise SelectorError(
                f"{chosen.text!r} gives a text of its own, not elements, their "
                "text or their attributes: a value with no place on the page"
            )
        raise SelectorError(
            f"{chosen.text!r} selects a comment or an instruction, not elements, "
            "their text or their attributes"
        )

    def _attribute(self, name: str, value: str | None) -> str:
        """An attribute's value as an extractor reads it: its spaces
        collapsed, an address resolved; empty when there is none."""
        if not value or not value.strip():
            return ""
        if name in _ADDRESSES:
            value = join(base_url(self._doc), value)
        return " ".join(value.split())

    def _selected(
        self,
        value: str,
        element: HtmlElement,
        node: HtmlElement | None,
        attribute: str | None = None,
    ) -> Selected:
        where = xpath_of(element, self._positions)
        return Selected(value, where, node, self, attribute)


def _what(result: Any) -> str:
    if isinstance(result, bool):
        return "true or false"
    if isinstance(result, float):
        return "a number"
    return "a text of its own"


def parse(
    html: str | bytes,
    url: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> Page:
    """Parse a page to select from, with ``css``, ``xpath`` and ``select``.

    Args:
        html: the page. Bytes are best: the page's own charset is then
            honoured, as ``extract`` honours it.
        url: the address the page came from, which its links resolve against.
        headers: the response's headers; their ``Content-Type`` charset
            decodes bytes, ahead of the page's own, as for ``extract``.

    Never raises: any input, however broken, is a page, if an empty one.
    """
    return Page(load(html, url=url, charset=charset(lowered(headers))))


def _an_address(one: Selected) -> bool:
    """Whether ``one`` is an ``href`` or ``src``, read from the attribute: an
    address, resolved against the page. A link's text is not one, however
    the selector that gave it names the link -- ``.//a[@href]``."""
    return one._attribute in _ADDRESSES


def _element_of(one: Selected) -> HtmlElement | None:
    """The element ``one`` is the whole text of, or None for a text or an
    attribute: what a listing's rows must be."""
    return one._node
