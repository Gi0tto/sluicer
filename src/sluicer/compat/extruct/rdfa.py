"""RDFa in extruct's shape: the page's graph as expanded JSON-LD, a node per subject.

extruct hands the page to pyRdfa and serialises the graph with rdflib: a list
of ``{"@id", "@type", <property IRI>: [values]}``, each value ``{"@id"}`` or
``{"@value"}`` with a ``@language`` or a ``@type`` beside it. This is an RDFa
processor of its own, in the ``lxml`` sluicer already carries, that answers
what that pair answers, and it follows pyRdfa as extruct configures it rather
than as RDFa for HTML is written: extruct never tells pyRdfa the page is HTML,
so pyRdfa reads it as RDFa Core, the XML host language. That is why ``lang``
never gives a literal a language (``xml:lang`` does), why ``<base href>`` is
not read, and why a ``<time>`` is not typed. Those are kept, since a caller of
extruct has every one of its literals in that shape; so are pyRdfa's
``role`` attribute and its reading of RDFa 1.0 when the root's ``version``
says so. Every OpenGraph tag is a property to RDFa, and so is every
``role="..."`` on the page, which is most of what real pages yield here.

Two things differ, both because extruct's answer changes from one run to the
next. Its blank nodes are named at random, and its nodes and values come in
the order of rdflib's hash sets, which Python seeds per process. Here a blank
node is ``_:b0``, ``_:b1`` in the order it first appears, nodes are in the
order their subjects first appear, and values in document order. The graph is
the same; ``bench/extruct_compat.py`` compares it as a graph.

And nothing raises. Under extruct, pyRdfa fails on an ``xml:lang`` rdflib
refuses (``en_US``), on an address ``urljoin`` or ``urlsplit`` refuses (an
unfilled template's ``https://[domain]/``), and on ``about="[]"``, the empty
safe CURIE, which it removes with a DOM method extruct's elements lack; each
of those is read here as pyRdfa means it. The walk does not recurse, so a page
nested deeper than libxml2's default of 256 levels, which extruct's parser
cuts off, is read to the bottom. A page that would copy more than its budget
-- properties nested in properties, each holding all the text below it --
gets the start of its graph in document order.
"""

from __future__ import annotations

import contextlib
import copy
import re
import xml.dom.minidom
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urljoin, urlparse, urlsplit, urlunparse
from xml.parsers.expat import ExpatError

import lxml.etree
from lxml.html import HtmlElement

from sluicer.compat.extruct.page import Budget, Page, of_tree, read_page
from sluicer.compat.extruct.text import literal

XHTML = "http://www.w3.org/1999/xhtml/vocab#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_RDF_TYPE = RDF + "type"
_XML_LITERAL = RDF + "XMLLiteral"
_HTML_LITERAL = RDF + "HTML"
_USES_VOCABULARY = "http://www.w3.org/ns/rdfa#usesVocabulary"
_PATTERN = "http://www.w3.org/ns/rdfa#Pattern"
_COPY = "http://www.w3.org/ns/rdfa#copy"
_XSD = "http://www.w3.org/2001/XMLSchema#"

# RDFa 1.1's initial context, as pyRdfa carries it, with the prefixes extruct
# adds to it before reading any page.
INITIAL_PREFIXES = {
    "as": "https://www.w3.org/ns/activitystreams#",
    "csvw": "http://www.w3.org/ns/csvw#",
    "dcat": "http://www.w3.org/ns/dcat#",
    "dqv": "http://www.w3.org/ns/dqv#",
    "duv": "https://www.w3.org/ns/duv#",
    "qb": "http://purl.org/linked-data/cube#",
    "org": "http://www.w3.org/ns/org#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "gr": "http://purl.org/goodrelations/v1#",
    "ctag": "http://commontag.org/ns#",
    "cc": "http://creativecommons.org/ns#",
    "grddl": "http://www.w3.org/2003/g/data-view#",
    "jsonld": "http://www.w3.org/ns/json-ld#",
    "ldp": "http://www.w3.org/ns/ldp#",
    "oa": "http://www.w3.org/ns/oa#",
    "rif": "http://www.w3.org/2007/rif#",
    "sioc": "http://rdfs.org/sioc/ns#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "xml": "http://www.w3.org/XML/1998/namespace",
    "rr": "http://www.w3.org/ns/r2rml#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "rev": "http://purl.org/stuff/rev#",
    "rdfa": "http://www.w3.org/ns/rdfa#",
    "dc": "http://purl.org/dc/terms/",
    "dcterms": "http://purl.org/dc/terms/",
    "dc11": "http://purl.org/dc/elements/1.1/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "void": "http://rdfs.org/ns/void#",
    "ical": "http://www.w3.org/2002/12/cal/icaltzd#",
    "vcard": "http://www.w3.org/2006/vcard/ns#",
    "wdrs": "http://www.w3.org/2007/05/powder-s#",
    "og": "http://ogp.me/ns#",
    "wdr": "http://www.w3.org/2007/05/powder#",
    "rdf": RDF,
    "xhv": XHTML,
    "xsd": _XSD,
    "v": "http://rdf.data-vocabulary.org/#",
    "skosxl": "http://www.w3.org/2008/05/skos-xl#",
    "schema": "http://schema.org/",
    "ssn": "http://www.w3.org/ns/ssn/",
    "sosa": "http://www.w3.org/ns/sosa/",
    "time": "http://www.w3.org/2006/time#",
    "ma": "http://www.w3.org/ns/ma-ont#",
    "sd": "http://www.w3.org/ns/sparql-service-description#",
    "prov": "http://www.w3.org/ns/prov#",
    "odrl": "http://www.w3.org/ns/odrl/2/",
    # extruct's own.
    "twitter": "https://dev.twitter.com/cards#",
    "fb": "http://ogp.me/ns/fb#",
    "music": "http://ogp.me/ns/music#",
    "video": "http://ogp.me/ns/video#",
    "article": "http://ogp.me/ns/article#",
    "book": "http://ogp.me/ns/book#",
    "profile": "http://ogp.me/ns/profile#",
}
_TERMS_1_1 = {
    "describedby": "http://www.w3.org/2007/05/powder-s#describedby",
    "role": XHTML + "role",
    "license": XHTML + "license",
}
_TERMS_1_0 = {
    name: XHTML + name
    for name in (
        "alternate",
        "appendix",
        "cite",
        "bookmark",
        "chapter",
        "contents",
        "copyright",
        "glossary",
        "help",
        "icon",
        "index",
        "meta",
        "next",
        "p3pv1",
        "prev",
        "previous",
        "role",
        "section",
        "subsection",
        "start",
        "license",
        "up",
        "last",
        "stylesheet",
        "first",
        "top",
    )
}
_RDFA_ATTRIBUTES_1_1 = (
    "href",
    "resource",
    "about",
    "property",
    "rel",
    "rev",
    "typeof",
    "src",
    "vocab",
    "prefix",
)
_RDFA_ATTRIBUTES_1_0 = _RDFA_ATTRIBUTES_1_1[:-2]
_NCNAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_TERM = re.compile(r"^[A-Za-z]([A-Za-z0-9._-]|/)*$")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
# The literal types rdflib writes as JSON's own values rather than as text.
_NATIVE = frozenset({_XSD + "boolean", _XSD + "integer", _XSD + "double"})


@dataclass(frozen=True)
class IRI:
    value: str


@dataclass(frozen=True)
class BNode:
    number: int


@dataclass(frozen=True)
class Literal:
    value: str
    language: str | None = None
    datatype: str | None = None


Resource = IRI | BNode
Term = IRI | BNode | Literal


class _Spent(Exception):
    """The page's budget ran out; the triples gathered before it are the answer."""


class RDFaExtractor:
    """extruct's RDFa extractor.

    Only the expanded form extruct answers by default is written;
    ``expanded=False``, rdflib's compaction, is refused.
    """

    def extract(
        self,
        htmlstring: str | bytes,
        base_url: str | None = None,
        encoding: str = "UTF-8",
        expanded: bool = True,
    ) -> list[dict[str, Any]]:
        return self.read(read_page(htmlstring, base_url, encoding), expanded)

    def extract_items(
        self,
        document: HtmlElement,
        base_url: str | None = None,
        expanded: bool = True,
    ) -> list[dict[str, Any]]:
        return self.read(of_tree(document, base_url), expanded)

    def read(self, page: Page, expanded: bool = True) -> list[dict[str, Any]]:
        if not expanded:
            raise ValueError(
                "only the expanded form is written: rdflib's compaction is not "
                "reproduced"
            )
        graph = _Graph(page.budget())
        # A spent budget ends the walk; what was stated before it is the answer.
        with contextlib.suppress(_Spent):
            _Processor(page, graph).run()
        graph.copy_patterns()
        return graph.json_ld()


# --- the graph ---------------------------------------------------------------


class _Graph:
    """A set of triples, kept in the order they were first stated."""

    def __init__(self, budget: Budget) -> None:
        self.budget = budget
        self.triples: dict[tuple[Resource, IRI, Term], None] = {}
        self.blanks = 0

    def blank(self) -> BNode:
        self.blanks += 1
        return BNode(self.blanks)

    def add(self, subject: Resource | None, predicate: IRI, obj: Term | None) -> None:
        if subject is None or obj is None:
            return
        triple = (subject, predicate, obj)
        if triple in self.triples:
            return
        cost = 3 + len(predicate.value) + _length(subject) + _length(obj)
        if not self.budget.pay(cost):
            raise _Spent
        self.triples[triple] = None

    def copy_patterns(self) -> None:
        """rdfa:copy, as pyRdfa applies it once the page is read.

        A resource that copies a pattern -- a subject typed ``rdfa:Pattern`` --
        gets the pattern's statements, and the pattern and the copying are
        removed.
        """
        patterns = {
            triple[0]
            for triple in self.triples
            if triple[1].value == _RDF_TYPE and triple[2] == IRI(_PATTERN)
        }
        removed: set[tuple[Resource, IRI, Term]] = set()
        added: list[tuple[Resource, IRI, Term]] = []
        for subject, predicate, obj in list(self.triples):
            if predicate.value != _COPY or obj not in patterns:
                continue
            removed.add((subject, predicate, obj))
            for pattern_subject, pattern_predicate, pattern_obj in list(self.triples):
                if pattern_subject != obj:
                    continue
                statement = (pattern_subject, pattern_predicate, pattern_obj)
                if pattern_predicate.value == _RDF_TYPE and pattern_obj == IRI(
                    _PATTERN
                ):
                    removed.add(statement)
                    continue
                added.append((subject, pattern_predicate, pattern_obj))
                removed.add(statement)
        for triple in added:
            self.triples.setdefault(triple, None)
        for triple in removed:
            self.triples.pop(triple, None)

    def json_ld(self) -> list[dict[str, Any]]:
        """The graph as rdflib writes it for extruct: expanded, keys sorted."""
        by_subject: dict[Resource, list[tuple[IRI, Term]]] = {}
        referenced: set[BNode] = set()
        for subject, predicate, obj in self.triples:
            by_subject.setdefault(subject, []).append((predicate, obj))
            if isinstance(obj, BNode):
                referenced.add(obj)
        writer = _Writer(by_subject)
        for subject in by_subject:
            # Where rdflib starts: every named subject, and every blank one
            # nothing points at. The rest are written when first pointed at.
            if isinstance(subject, IRI) or subject not in referenced:
                writer.node(subject)
        return [
            {key: node[key] for key in sorted(node)} for node in writer.nodes.values()
        ]


def _length(term: Term) -> int:
    if isinstance(term, BNode):
        return 4
    return len(term.value)


class _Writer:
    def __init__(self, by_subject: dict[Resource, list[tuple[IRI, Term]]]) -> None:
        self.by_subject = by_subject
        self.nodes: dict[str, dict[str, Any]] = {}
        self.labels: dict[BNode, str] = {}

    def name(self, resource: Resource) -> str:
        if isinstance(resource, IRI):
            return resource.value
        if resource not in self.labels:
            self.labels[resource] = f"_:b{len(self.labels)}"
        return self.labels[resource]

    def node(self, subject: Resource) -> None:
        identifier = self.name(subject)
        if identifier in self.nodes:
            return
        node: dict[str, Any] = {"@id": identifier}
        self.nodes[identifier] = node
        for predicate, obj in self.by_subject.get(subject, ()):
            if predicate.value == _RDF_TYPE:
                # rdflib writes a type under @type, by its address when it has one.
                typed = obj.value if isinstance(obj, IRI) else self.value(obj)
                node.setdefault("@type", []).append(typed)
                continue
            node.setdefault(predicate.value, []).append(self.value(obj))

    def value(self, obj: Term) -> Any:
        if isinstance(obj, Literal):
            return _literal(obj)
        items = self.collection(obj)
        if items is not None:
            return {"@list": [self.value(item) for item in items]}
        if isinstance(obj, BNode):
            self.node(obj)
        return {"@id": self.name(obj)}

    def collection(self, head: Resource) -> list[Term] | None:
        """The members of an RDF list starting at ``head``, or None if it is not one.

        rdflib's rule: every node blank, holding one ``rdf:first``, one
        ``rdf:rest`` and nothing else but ``rdf:type rdf:List``.
        """
        if head == IRI(RDF + "nil"):
            return []
        members: list[Term] = []
        node: Term = head
        seen: set[Term] = {head}
        while node != IRI(RDF + "nil"):
            if not isinstance(node, BNode):
                return None
            first: Term | None = None
            rest: Term | None = None
            for predicate, obj in self.by_subject.get(node, ()):
                if first is None and predicate.value == RDF + "first":
                    first = obj
                elif rest is None and predicate.value == RDF + "rest":
                    rest = obj
                elif predicate.value != _RDF_TYPE or obj != IRI(RDF + "List"):
                    return None
            if first is None:
                return None
            members.append(first)
            if rest is None or rest in seen:
                return None
            seen.add(rest)
            node = rest
        return members


def _literal(obj: Literal) -> dict[str, Any]:
    if obj.datatype is not None:
        return {"@type": obj.datatype, "@value": _native(obj.value, obj.datatype)}
    if obj.language is not None:
        return {"@language": obj.language, "@value": obj.value}
    return {"@value": obj.value}


def _native(value: str, datatype: str) -> Any:
    """A typed literal's value as rdflib writes it: JSON's own for three types."""
    if datatype not in _NATIVE:
        return value
    if datatype == _XSD + "boolean":
        return value.lower() in ("1", "true")
    try:
        return int(value) if datatype == _XSD + "integer" else float(value)
    except ValueError:
        return value


# --- the processor -----------------------------------------------------------


@dataclass
class _Lists:
    """The lists ``inlist`` is building, and the subject they will hang from."""

    mapping: dict[IRI, list[Term] | None] = field(default_factory=dict)
    origin: Resource | None = None


class _Context:
    """What is in force at one element: pyRdfa's execution context.

    Built from the element and its parent's context, in pyRdfa's order: the
    base, then prefixes and vocabulary, then the language.
    """

    version: str
    base: str
    lists: _Lists
    new_list: bool
    vocabulary: str | None
    terms: dict[str, str]
    defaults: dict[str, str]
    ns: dict[str, str]
    xmlns: dict[str, str]
    lang: str | None
    default_ns: str | None

    def __init__(
        self,
        processor: _Processor,
        element: HtmlElement,
        parent: _Context | None,
        base: str = "",
        version: str = "1.1",
    ) -> None:
        self.processor = processor
        self.element = element
        if parent is None:
            self.version = version
            self.lists = _Lists()
            self.new_list = True
            self.base = _without_fragment(element.get("xml:base") or "") or base
        else:
            self.version = parent.version
            self.base = parent.base
            self.lists = parent.lists
            self.new_list = False
            declared_base = element.get("xml:base")
            if declared_base is not None:
                self.base = _without_fragment(declared_base)
        self.base_has_scheme = bool(_scheme(self.base))
        self._vocabulary(parent)
        self._prefixes(parent)
        self.lang = None if parent is None else parent.lang
        declared_lang = element.get("xml:lang")
        if declared_lang is not None:
            self.lang = declared_lang.lower() or None
        declared_ns = element.get("xmlns")
        if declared_ns is not None:
            self.default_ns = declared_ns
        else:
            self.default_ns = None if parent is None else parent.default_ns

    def _vocabulary(self, parent: _Context | None) -> None:
        """``vocab``, which RDFa 1.0 does not have, and the terms in force."""
        modern = self.version >= "1.1"
        if parent is None:
            self.terms = dict(_TERMS_1_1 if modern else _TERMS_1_0)
            self.defaults = dict(INITIAL_PREFIXES) if modern else {}
            self.vocabulary = None
        else:
            self.terms = parent.terms
            self.defaults = parent.defaults
            self.vocabulary = parent.vocabulary
        declared = self.element.get("vocab")
        if not modern or declared is None:
            return
        if declared == "":
            self.vocabulary = None
            return
        vocabulary = self.uri(declared.strip())
        if vocabulary is not None and vocabulary.value:
            self.vocabulary = vocabulary.value
            self.processor.graph.add(IRI(self.base), IRI(_USES_VOCABULARY), vocabulary)

    def _prefixes(self, parent: _Context | None) -> None:
        """The prefixes ``xmlns:`` and, in RDFa 1.1, ``prefix`` declare."""
        element = self.element
        modern = self.version >= "1.1"
        declared: dict[str, str] = {}
        xmlns: dict[str, str] = {}
        for name, value in element.attrib.items():
            if not name.startswith("xmlns:"):
                continue
            prefix = name[len("xmlns:") :]
            if not prefix or prefix == "_" or ":" in prefix:
                continue
            key = prefix.lower() if modern else prefix
            declared[key] = xmlns[key] = _quote(value)
        if modern and element.get("prefix") is not None:
            tokens = (element.get("prefix") or "").strip().split()
            # pyRdfa reads the pairs from the end, so for a prefix declared
            # twice the first declaration is the one left standing.
            for index in range(len(tokens) - 2, -1, -2):
                prefix, value = tokens[index], tokens[index + 1]
                if not prefix.endswith(":") or prefix == ":":
                    continue
                prefix = prefix[:-1]
                if prefix != "_" and _NCNAME.match(prefix):
                    declared[prefix.lower()] = _quote(value)
        inherited: dict[str, str] = {} if parent is None else parent.ns
        self.ns = {**inherited, **declared} if declared else inherited
        inherited_xmlns: dict[str, str] = {} if parent is None else parent.xmlns
        self.xmlns = {**inherited_xmlns, **xmlns} if xmlns else inherited_xmlns

    # -- attribute values, as pyRdfa reads each kind --------------------------

    def uri(self, value: str) -> IRI | None:
        """An ``href``, ``src`` or ``vocab``: an address, resolved."""
        if value == "":
            return IRI(self.base)
        if not self.base_has_scheme:
            if not _scheme(value):
                return IRI(_join(self.base, value).strip())
            return IRI(value.strip())
        return IRI(_join(self.base, value).strip())

    def curie_or_uri(self, value: str) -> Resource | None:
        """An ``about`` or ``resource``: a CURIE, a safe CURIE, or an address."""
        if value == "":
            return IRI(self.base)
        safe = False
        if value.startswith("["):
            if not value.endswith("]"):
                return None
            value, safe = value[1:-1], True
        if self.version >= "1.1":
            found = self.curie(value)
            if found is None:
                return None if safe else self.uri(value)
            if isinstance(found, IRI) and not _scheme(found.value):
                return IRI(self.base + found.value)
            return found
        return self.curie(value) if safe else self.uri(value)

    def term_curie_or_absolute(self, value: str) -> Resource | None:
        """A ``rel``, ``rev``, ``property``, ``typeof``, ``datatype`` or ``role``."""
        if value == "":
            return None
        if _TERM.match(value):
            return self.term(value)
        found = self.curie(value)
        if found is not None:
            return found
        if self.version >= "1.1" and _scheme(value):
            return IRI(value)
        return None

    def curie(self, value: str) -> Resource | None:
        if value == "":
            return None
        if value == ":":
            return IRI(XHTML)
        prefix, colon, reference = value.partition(":")
        if not colon:
            return None
        if self.version >= "1.1":
            prefix = prefix.lower()
        if not prefix:
            return IRI(XHTML + reference) if self._reference(reference) else None
        if prefix == "_":
            return self.processor.named_blank(reference)
        if not _NCNAME.match(prefix):
            return None
        namespace = self.ns.get(prefix)
        if namespace is None:
            namespace = self.defaults.get(prefix)
        if namespace is None or not self._reference(reference):
            return None
        return IRI(namespace + reference)

    def _reference(self, reference: str) -> bool:
        """pyRdfa's test of a CURIE's reference: no authority, no stray brackets."""
        try:
            parts = urlsplit("http:" + reference)
        except ValueError:
            return False
        if parts.netloc and self.version >= "1.1":
            return False
        return not any(
            c in part for part in (parts.query, parts.fragment) for c in "#[]"
        )

    def term(self, value: str) -> IRI | None:
        if self.vocabulary is not None:
            return IRI(self.vocabulary + value)
        if value in self.terms:
            return IRI(self.terms[value])
        for defined, address in self.terms.items():
            if defined.lower() == value.lower():
                return IRI(address)
        return None

    def get(self, attribute: str) -> Resource | None:
        """One attribute that names one resource, read by its kind, or None."""
        value = self.processor.attribute(self.element, attribute)
        if value is None:
            return None
        if attribute in ("href", "src", "vocab"):
            return self.uri(value.strip())
        if attribute in ("about", "resource"):
            return self.curie_or_uri(value.strip())
        return self.term_curie_or_absolute(value.strip())

    def get_all(self, attribute: str) -> list[Resource]:
        """One attribute that names a list of terms: ``rel``, ``typeof``..."""
        value = self.processor.attribute(self.element, attribute)
        return [
            found
            for token in (value or "").strip().split()
            if (found := self.term_curie_or_absolute(token)) is not None
        ]

    def resource(self, *attributes: str) -> Resource | None:
        """The first of ``attributes`` that gives a resource."""
        for attribute in attributes:
            found = self.get(attribute)
            if found is not None:
                return found
        return None

    def reset_lists(self, origin: Resource | None) -> None:
        self.lists = _Lists(origin=origin)
        self.new_list = True

    def add_to_list(self, prop: IRI, value: Term | None) -> None:
        held = self.lists.mapping
        if prop in held:
            if value is not None:
                members = held[prop]
                if members is None:
                    held[prop] = [value]
                else:
                    members.append(value)
        else:
            held[prop] = None if value is None else [value]


_Incomplete = tuple[Resource | None, IRI, Resource | None]


@dataclass
class _Frame:
    """What an element still has to do once its children are read."""

    context: _Context
    parent: _Context
    subject: Resource | None
    completes: list[_Incomplete]


class _Processor:
    """One page's RDFa: its tree, its graph, and its named blank nodes."""

    def __init__(self, page: Page, graph: _Graph) -> None:
        self.page = page
        self.graph = graph
        self.root = page.tree.getroottree().getroot()
        self.named: dict[str, BNode] = {}
        self.empty_blank: BNode | None = None

    def named_blank(self, label: str) -> BNode:
        if not label:
            if self.empty_blank is None:
                self.empty_blank = self.graph.blank()
            return self.empty_blank
        if label not in self.named:
            self.named[label] = self.graph.blank()
        return self.named[label]

    def attribute(self, element: HtmlElement, name: str) -> str | None:
        """An attribute as pyRdfa sees it once its own transforms have run.

        An ``about`` or ``resource`` that is the empty safe CURIE ``[]`` is
        removed; the root gets ``about=""`` unless it names a subject some
        other way; every term in a ``role`` becomes an XHTML vocabulary IRI.
        """
        value: str | None = element.get(name)
        if name in ("about", "resource") and value == "[]":
            value = None
        if name == "about" and value is None and element is self.root:
            if self.attribute(element, "resource") is None and not any(
                element.get(other) is not None for other in ("href", "src")
            ):
                return ""
            if any(
                element.get(other) is not None for other in ("rel", "rev", "property")
            ):
                return ""
        if name == "role" and value is not None:
            value = " ".join(
                XHTML + token if _TERM.match(token) else token
                for token in value.strip().split()
            )
        return value

    def has(self, element: HtmlElement, *names: str) -> bool:
        return any(self.attribute(element, name) is not None for name in names)

    def run(self) -> None:
        root = self.root
        version = "1.1"
        declared = root.get("version") or ""
        if "RDFa 1.0" in declared or "RDFa1.0" in declared:
            version = "1.0"
        elif "RDFa 1.1" in declared or "RDFa1.1" in declared:
            version = "1.1"
        top = _Context(self, root, None, base=self.page.base_url or "", version=version)
        # pyRdfa builds the root's context twice: once to start from, and once
        # as the root is read, from the first.
        pending: list[
            tuple[HtmlElement, Resource | None, _Context, list[_Incomplete]] | _Frame
        ] = [(root, None, top, [])]
        while pending:
            step = pending.pop()
            if isinstance(step, _Frame):
                self.finish(step)
                continue
            element, parent_object, parent, completes = step
            if not self.graph.budget.pay(1):
                raise _Spent
            if version >= "1.1":
                children = self.enter_1_1(element, parent_object, parent, completes)
            else:
                children = self.enter_1_0(element, parent_object, parent, completes)
            frame, child_object, child_context, child_completes = children
            if frame is not None:
                pending.append(frame)
            pending.extend(
                (child, child_object, child_context, child_completes)
                for child in reversed(_elements(element))
            )

    def role(self, element: HtmlElement, context: _Context) -> None:
        if self.attribute(element, "role") is None:
            return
        identifier = element.get("id")
        subject: Resource = (
            IRI(context.base + "#" + identifier.strip())
            if identifier is not None
            else self.graph.blank()
        )
        for value in context.get_all("role"):
            self.graph.add(subject, IRI(XHTML + "role"), value)

    def enter_1_1(
        self,
        element: HtmlElement,
        parent_object: Resource | None,
        parent: _Context,
        completes: list[_Incomplete],
    ) -> tuple[_Frame | None, Resource | None, _Context, list[_Incomplete]]:
        """RDFa 1.1's processing of one element, up to its children."""
        context = _Context(self, element, parent)
        self.role(element, context)
        if not self.has(element, *_RDFA_ATTRIBUTES_1_1):
            return None, parent_object, context, completes
        graph = self.graph
        has = self.has
        subject: Resource | None = None
        obj: Resource | None = None
        typed: Resource | None = None
        if has(element, "rel", "rev"):
            if has(element, "about"):
                subject = context.get("about")
                if has(element, "typeof"):
                    typed = subject
            if subject is None:
                subject = parent_object
            else:
                context.reset_lists(subject)
            obj = context.resource("resource", "href", "src")
            if has(element, "typeof") and not has(element, "about"):
                if obj is None:
                    obj = graph.blank()
                typed = obj
            if not has(element, "inlist") and obj is not None:
                context.reset_lists(obj)
        elif has(element, "property") and not has(element, "content", "datatype"):
            if has(element, "about"):
                subject = context.get("about")
                if has(element, "typeof"):
                    typed = subject
            if subject is None:
                subject = parent_object
            else:
                context.reset_lists(subject)
            if typed is None and has(element, "typeof"):
                typed = context.resource("resource", "href", "src")
                if typed is None:
                    typed = graph.blank()
                obj = typed
            else:
                obj = subject
        else:
            subject = context.resource("about", "resource", "href", "src")
            if subject is None:
                if has(element, "typeof"):
                    subject = graph.blank()
                    context.reset_lists(subject)
                else:
                    subject = parent_object
            else:
                context.reset_lists(subject)
            obj = subject
            if has(element, "typeof"):
                typed = subject
        if typed is not None and _truthy(typed):
            for declared in context.get_all("typeof"):
                graph.add(typed, IRI(_RDF_TYPE), declared)
        incomplete: list[_Incomplete] = []
        for prop in context.get_all("rel"):
            if isinstance(prop, BNode):
                continue
            if has(element, "inlist"):
                context.add_to_list(prop, obj)
                if obj is None:
                    incomplete.append((None, prop, None))
            elif obj is not None:
                graph.add(subject, prop, obj)
            else:
                incomplete.append((subject, prop, None))
        for prop in context.get_all("rev"):
            if isinstance(prop, BNode):
                continue
            if obj is not None:
                graph.add(obj, prop, subject)
            else:
                incomplete.append((None, prop, subject))
        if has(element, "property"):
            self.property_1_1(element, context, subject, typed)
        child_object = obj if obj is not None else graph.blank()
        frame = _Frame(context, parent, subject, completes)
        return frame, child_object, context, incomplete

    def enter_1_0(
        self,
        element: HtmlElement,
        parent_object: Resource | None,
        parent: _Context,
        completes: list[_Incomplete],
    ) -> tuple[_Frame | None, Resource | None, _Context, list[_Incomplete]]:
        """RDFa 1.0's processing of one element, as pyRdfa does it.

        pyRdfa's 1.0 path never uses the blank node it makes for a ``typeof``
        without a subject: the type goes to the parent's object, and so it
        does here.
        """
        context = _Context(self, element, parent)
        self.role(element, context)
        if not self.has(element, *_RDFA_ATTRIBUTES_1_0):
            return None, parent_object, context, completes
        graph = self.graph
        subject: Resource | None
        obj: Resource | None
        if self.has(element, "rel", "rev"):
            subject = context.resource("about", "src")
            if subject is None:
                subject = (
                    graph.blank() if self.has(element, "typeof") else parent_object
                )
            else:
                context.reset_lists(subject)
            obj = context.resource("resource", "href")
        else:
            subject = context.resource("about", "src", "resource", "href")
            if subject is None:
                subject = parent_object
            else:
                context.reset_lists(subject)
            obj = subject
        for declared in context.get_all("typeof"):
            graph.add(subject, IRI(_RDF_TYPE), declared)
        incomplete: list[_Incomplete] = []
        for prop in context.get_all("rel"):
            if isinstance(prop, BNode):
                continue
            if obj is not None:
                graph.add(subject, prop, obj)
            else:
                incomplete.append((subject, prop, None))
        for prop in context.get_all("rev"):
            if isinstance(prop, BNode):
                continue
            if obj is not None:
                graph.add(obj, prop, subject)
            else:
                incomplete.append((None, prop, subject))
        if self.has(element, "property"):
            self.property_1_0(element, context, subject)
        child_object = obj if obj is not None else graph.blank()
        frame = _Frame(context, parent, subject, completes)
        return frame, child_object, context, incomplete

    def finish(self, frame: _Frame) -> None:
        """What an element does once its children are read.

        It completes the triples its parent left without an object, and if it
        started lists, writes them.
        """
        graph = self.graph
        subject = frame.subject
        for incomplete_subject, prop, incomplete_object in frame.completes:
            if incomplete_subject is None and incomplete_object is None:
                frame.parent.add_to_list(prop, subject)
                continue
            graph.add(
                incomplete_subject if incomplete_subject is not None else subject,
                prop,
                incomplete_object if incomplete_object is not None else subject,
            )
        context = frame.context
        if not context.new_list or not context.lists.mapping:
            return
        origin = context.lists.origin
        nil = IRI(RDF + "nil")
        for prop, members in context.lists.mapping.items():
            if members is None:
                graph.add(origin, prop, nil)
                continue
            heads: list[Resource] = [graph.blank() for _member in members]
            links: list[Resource] = [*heads, nil]
            for index, member in enumerate(members):
                graph.add(heads[index], IRI(RDF + "first"), member)
                graph.add(heads[index], IRI(RDF + "rest"), links[index + 1])
            graph.add(origin, prop, heads[0])

    # -- properties -----------------------------------------------------------

    def property_1_1(
        self,
        element: HtmlElement,
        context: _Context,
        subject: Resource | None,
        typed: Resource | None,
    ) -> None:
        has = self.has
        value: Term | None
        if has(element, "resource", "href", "src") and not has(
            element, "content", "datatype", "rel", "rev"
        ):
            value = context.resource("resource", "href", "src")
        elif (
            has(element, "typeof")
            and not has(element, "content", "datatype", "rel", "rev", "about")
            and element.get("about") != "[]"
            and typed is not None
        ):
            value = typed
        else:
            value = self.literal(element, context, spot_markup=False)
        if value is None:
            return
        for prop in context.get_all("property"):
            if isinstance(prop, BNode):
                continue
            if has(element, "inlist"):
                context.add_to_list(prop, value)
            else:
                self.graph.add(subject, prop, value)

    def property_1_0(
        self, element: HtmlElement, context: _Context, subject: Resource | None
    ) -> None:
        value = self.literal(element, context, spot_markup=True)
        for prop in context.get_all("property"):
            if not isinstance(prop, BNode):
                self.graph.add(subject, prop, value)

    def literal(
        self, element: HtmlElement, context: _Context, spot_markup: bool
    ) -> Literal:
        """The literal a property element declares.

        ``content`` as written, else the element's text; typed by ``datatype``,
        and in RDFa 1.0 an XML literal when the element holds markup.
        """
        datatype: str | None = None
        typed = element.get("datatype") is not None
        if typed and element.get("datatype") != "":
            found = context.get("datatype")
            datatype = found.value if isinstance(found, IRI) else None
        language = context.lang
        content = element.get("content")
        if content is not None:
            return self.paid(_typed(content, datatype if typed else None, language))
        if typed and datatype == _XML_LITERAL:
            return self.paid(_xml_literal(self.markup(element, context)))
        if typed and datatype == _HTML_LITERAL:
            return self.paid(
                Literal(
                    self.markup(element, context, xmlns=False), datatype=_HTML_LITERAL
                )
            )
        if not typed and spot_markup and len(element):
            return self.paid(_xml_literal(self.markup(element, context)))
        text = literal(element, self.graph.budget)
        if text is None:
            raise _Spent
        return _typed(text, datatype if typed else None, language)

    def paid(self, value: Literal) -> Literal:
        if not self.graph.budget.pay(len(value.value)):
            raise _Spent
        return value

    def markup(
        self, element: HtmlElement, context: _Context, xmlns: bool = True
    ) -> str:
        """An element's content as XML, as pyRdfa writes an XML literal.

        Each child element is written with the prefixes in force declared on
        it, and, as pyRdfa's copy carries it, with its trailing text; the
        trailing text is then written again as the text that follows.
        """
        parts = [_escape(element.text or "")]
        for child in element:
            if not self.graph.budget.pay(1):
                raise _Spent
            clone = copy.deepcopy(child)
            if xmlns and isinstance(clone.tag, str):
                for prefix, namespace in context.xmlns.items():
                    if clone.get("xmlns:" + prefix) is None:
                        clone.set("xmlns:" + prefix, namespace)
                if not clone.get("xmlns") and context.default_ns is not None:
                    clone.set("xmlns", context.default_ns)
            parts.append(lxml.etree.tostring(clone, encoding="unicode"))
            parts.append(_escape(child.tail or ""))
        return "".join(parts)


def _xml_literal(markup: str) -> Literal:
    """An XML literal as rdflib stores it: parsed, and written again.

    rdflib reads the markup with the standard library's minidom inside a
    wrapper element and writes it back, which puts namespace declarations
    ahead of other attributes, writes an empty element as ``<x/>`` and a quote
    in text as ``&quot;``. Markup minidom cannot read stays as it was, as it
    does in rdflib. The markup is lxml's serialisation of the page's own
    elements, so it declares no entity for minidom to expand.
    """
    try:
        document = xml.dom.minidom.parseString(
            f"<rdflibtoplevelelement>{markup}</rdflibtoplevelelement>"
        )
    except (ExpatError, ValueError):
        return Literal(markup, datatype=_XML_LITERAL)
    document.normalize()
    # minidom writes the declaration, then the wrapper, empty or around it all.
    written = document.toxml("utf-8").decode("utf-8")
    written = written.removeprefix('<?xml version="1.0" encoding="utf-8"?>')
    if written == "<rdflibtoplevelelement/>":
        return Literal("", datatype=_XML_LITERAL)
    inner = written.removeprefix("<rdflibtoplevelelement>")
    return Literal(
        inner.removesuffix("</rdflibtoplevelelement>"), datatype=_XML_LITERAL
    )


def _typed(value: str, datatype: str | None, language: str | None) -> Literal:
    if datatype:
        return Literal(value, datatype=datatype)
    return Literal(value, language=language or None)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _elements(element: HtmlElement) -> list[HtmlElement]:
    """The children pyRdfa walks into: every node, comments included, which
    it reads as elements carrying no attribute and holding nothing."""
    return [child for child in element if isinstance(child.tag, str)]


def _truthy(resource: Resource) -> bool:
    """rdflib's truth of a resource: an empty address is false."""
    return isinstance(resource, BNode) or bool(resource.value)


def _scheme(value: str) -> str:
    """The scheme ``urlsplit`` would find, without the checks that make it raise."""
    cleaned = (
        value.lstrip("".join(chr(c) for c in range(0x21)))
        .replace("\t", "")
        .replace("\r", "")
        .replace("\n", "")
    )
    match = _SCHEME.match(cleaned)
    if match is None or not cleaned[0].isascii():
        return ""
    return match.group()[:-1].lower()


def _join(base: str, value: str) -> str:
    """pyRdfa's join: ``urljoin``, keeping a trailing ``#`` or ``?`` it swallowed."""
    try:
        joined = urljoin(base, value)
    except ValueError:
        return value
    if value and joined and value[-1] != joined[-1] and value[-1] in "#?":
        return joined + value[-1]
    return joined


def _without_fragment(address: str) -> str:
    try:
        parts = urlparse(address)
        return urlunparse((*parts[:5], ""))
    except ValueError:
        return address


def _quote(address: str) -> str:
    """A namespace as pyRdfa stores it: percent-encoded but for ``:/?=#~``."""
    return quote(address.strip(), ":/?=#~")
