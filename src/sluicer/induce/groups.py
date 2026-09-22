"""Finding the siblings a page repeats.

A listing page is a parent whose children are the same shape over and over. We
look for exactly that, and rank what we find by how much each candidate
promises: many members, each with many parts. Two of a kind is a coincidence,
so the floor is three.
"""

from __future__ import annotations

from collections import defaultdict

from lxml.html import HtmlElement

from sluicer.induce.shape import signature


def repeating_groups(
    tree: HtmlElement, minimum: int = 3
) -> list[list[HtmlElement]]:
    """Return groups of same-shaped siblings, the most promising first."""
    found: list[tuple[int, int, list[HtmlElement]]] = []
    for order, parent in enumerate(tree.iter()):
        if not isinstance(parent.tag, str):
            continue
        by_shape: dict[str, list[HtmlElement]] = defaultdict(list)
        for child in parent:
            if isinstance(child.tag, str):
                by_shape[signature(child)].append(child)
        for members in by_shape.values():
            if len(members) >= minimum:
                parts = max(len(list(member)) for member in members)
                found.append((len(members) * max(parts, 1), order, members))
    found.sort(key=lambda item: (-item[0], item[1]))
    return [members for _, _, members in found]
