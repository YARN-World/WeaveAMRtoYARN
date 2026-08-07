"""Penman-level dereification of ``-91`` predicates.

The GRS has a ``dereify`` package that handles embedded reifications. This pass
covers what it does not: the ``have-org-role-91`` / ``have-rel-role-91`` frames,
and root-level binary reifications, where the rewrite has to move the graph top.

Off by default (see :class:`~weave_amr2yarn.config.ConversionConfig`).
"""

from __future__ import annotations

import penman

from ..errors import AmrParseError

# concept -> (which ARG becomes the new top, the relation, which ARG it targets)
DEREIFY_MAP: dict[str, tuple[str, str, str]] = {
    "have-mod-91": ("ARG2", "domain", "ARG1"),
    "have-part-91": ("ARG2", "part-of", "ARG1"),
    "be-temporally-at-91": ("ARG1", "time", "ARG2"),
}

_ROLE_FRAMES = {"have-org-role-91", "have-rel-role-91"}


def _dereifyRoleFrames(graph: penman.Graph):
    """Collapse role-91 frames::

        (h / have-org-role-91 :ARG0 X :ARG1 U :ARG2 R)  ->  (X :role (R :mod U))
        (h / have-rel-role-91 :ARG0 X :ARG2 R)          ->  (X :role R)

    Returns ``(triples, top)``, or ``(None, None)`` when nothing applies. For
    have-rel-role-91 the ARG1 -> :mod mapping is an approximation; the common
    bare ARG0 + ARG2 case is exact.
    """
    instances = {t[0]: t[2] for t in graph.triples if t[1] == ":instance"}
    candidates = {
        node for node, concept in instances.items() if concept in _ROLE_FRAMES
    }
    if not candidates:
        return None, None

    rewrites: dict[str, tuple[str, str, str | None]] = {}
    for node in candidates:
        args: dict[str, str] = {}
        for source, role, target in graph.triples:
            if source == node and role in (":ARG0", ":ARG1", ":ARG2"):
                args[role] = target
        holder, role_, org = args.get(":ARG0"), args.get(":ARG2"), args.get(":ARG1")
        if holder and role_:
            rewrites[node] = (holder, role_, org)

    if not rewrites:
        return None, None

    # Drop every triple sourced at a rewritten node: its :instance and its ARGs.
    triples = [
        penman.Triple(s, r, t) for s, r, t in graph.triples if s not in rewrites
    ]
    for holder, role_, org in rewrites.values():
        triples.append(penman.Triple(holder, ":role", role_))
        if org:
            triples.append(penman.Triple(role_, ":mod", org))

    top = rewrites[graph.top][0] if graph.top in rewrites else graph.top
    return triples, top


def dereify(amrString: str, *, sentenceId: str | None = None) -> str:
    """Return *amrString* with ``-91`` predicates dereified.

    Raises :class:`AmrParseError` on undecodable input. The original returned
    the string ``"(parse error: ...)"``, which then decoded as a one-node graph
    and was counted as a successful conversion.
    """
    try:
        graph = penman.decode(amrString)
    except Exception as exc:
        raise AmrParseError(str(exc), sentenceId=sentenceId) from exc

    metadata = dict(graph.metadata)

    triples, top = _dereifyRoleFrames(graph)
    if triples is not None:
        try:
            graph = penman.Graph(triples, top=top)
        except Exception:
            pass  # leave the graph as it was if the rewrite does not hold

    graph.metadata = metadata

    instances = {t[0]: t[2] for t in graph.triples if t[1] == ":instance"}
    mapping = DEREIFY_MAP.get(instances.get(graph.top, ""))
    if mapping is None:
        return penman.encode(graph, indent=3)

    fromTop = {
        t[1].lstrip(":"): t[2]
        for t in graph.triples
        if t[0] == graph.top and t[1] != ":instance"
    }
    newTopArg, relation, otherArg = mapping
    newTop, other = fromTop.get(newTopArg), fromTop.get(otherArg)
    if not newTop or not other:
        return penman.encode(graph, indent=3)

    triples = [t for t in graph.triples if t[0] != graph.top]
    triples.append(penman.Triple(newTop, f":{relation}", other))
    try:
        rewritten = penman.Graph(triples, top=newTop)
        rewritten.metadata = metadata
        return penman.encode(rewritten, indent=3)
    except Exception:
        return penman.encode(graph, indent=3)