"""extruct's ``uniform=True``: every syntax as a list of ``{"@context", "@type"}``.

These are extruct's own reshapings, followed exactly, quirks included, since a
caller of ``uniform`` wrote code against them: a microdata item without a type
keeps its ``properties`` unflattened; an ``og:type`` is the OpenGraph object's
``@type`` and, without ``with_og_array``, a repeated property keeps its first
non-empty value; a Dublin Core element any of whose attribute values ends in
``type`` gives the object its ``@type`` and leaves ``elements``, and the
element after it is then not looked at, as extruct's loop skips it.

One thing is not followed: nothing here raises. extruct fails on a type
``urlparse`` refuses and on a ``<link rel="DC.type">``, which has no
``content``; the first keeps its type as written, the second is left among
the elements.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

from sluicer.compat.extruct.dublincore import local_name


def _uopengraph(
    extracted: list[dict[str, Any]], with_og_array: bool = False
) -> list[dict[str, Any]]:
    out = []
    for obj in extracted:
        flattened: dict[str, Any] = {}
        for key, value in obj["properties"]:
            if key not in flattened:
                flattened[key] = value
            elif value and value.strip():
                held = flattened[key]
                if not with_og_array:
                    if not held or not held.strip():
                        flattened[key] = value
                elif isinstance(held, list):
                    held.append(value)
                elif held and held.strip():
                    flattened[key] = [held, value]
                else:
                    flattened[key] = value
        declared_type = flattened.pop("og:type", None)
        if declared_type:
            flattened["@type"] = declared_type
        flattened["@context"] = obj["namespace"]
        out.append(flattened)
    return out


def _umicrodata_microformat(extracted: Any, schema_context: str) -> list[Any]:
    if isinstance(extracted, list):
        return [flatten_dict(obj, schema_context, True) for obj in extracted]
    if isinstance(extracted, dict):
        return [flatten_dict(extracted, schema_context, False)]
    return []


def _udublincore(extracted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for original in extracted:
        obj: dict[str, Any] = {
            key: _copy(value) for key, value in original.items() if key != "namespaces"
        }
        obj["@context"] = _copy(original.get("namespaces"))
        elements: list[dict[str, str]] = obj["elements"]
        # Walked by position while it shrinks, as extruct's for loop walks it.
        index = 0
        while index < len(elements):
            element = elements[index]
            index += 1
            for value in element.values():
                if local_name(value) == "type":
                    if "content" in element:
                        obj["@type"] = element["content"]
                        elements.remove(element)
                    break
        out.append(obj)
    return out


def _copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_copy(inner) for inner in value]
    return value


def _flatten(element: Any, schema_context: str) -> Any:
    if isinstance(element, dict):
        return flatten_dict(element, schema_context, False)
    if isinstance(element, list):
        return [
            flatten_dict(item, schema_context, False)
            if isinstance(item, dict)
            else item
            for item in element
        ]
    return element


def flatten_dict(d: dict[str, Any], schema_context: str, add_context: bool) -> Any:
    out = dict(d)
    declared = out.pop("type", None)
    if not declared:
        return d
    if isinstance(declared, list):
        out["@type"] = declared
        context = schema_context
    else:
        context, out["@type"] = infer_context(declared, schema_context)
    if add_context:
        out["@context"] = context
    for name, value in out.pop("properties", {}).items():
        out[name] = _flatten(value, schema_context)
    children = out.pop("children", [])
    if children:
        out["children"] = [_flatten(child, schema_context) for child in children]
    return out


def infer_context(typ: str, context: str = "http://schema.org") -> tuple[str, str]:
    """A type's vocabulary and name: ``https://schema.org/Product`` is both."""
    try:
        parsed = urlparse(typ)
    except ValueError:
        return context, typ
    if parsed.netloc:
        base = "".join([parsed.scheme, "://", parsed.netloc])
        if parsed.path and parsed.fragment:
            context = urljoin(base, parsed.path)
            typ = parsed.fragment.strip("/")
        elif parsed.path:
            context = base
            typ = parsed.path.strip("/")
    return context, typ
