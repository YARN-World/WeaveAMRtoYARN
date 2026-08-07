
from __future__ import annotations

import re

_ENGINE_ID = re.compile(r"_.*_")


def _naturalKey(value) -> tuple:
    """Sort key where "d2" precedes "d10" and missing values sort last.

    Every element is a ``(isNumber, value)`` pair so that mixed digit/text
    segments and the missing-value sentinel always compare — comparing an int
    against a str would raise.
    """
    if not value:
        value = "~~missing~~"
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part)
        for part in re.findall(r"\d+|\D+", str(value))
    )


def renameSNodes(data: dict) -> dict:
    """Number every S node S1..Sn by the natural order of its ``core``.

    ``core`` is the AMR node the event node was made for, stamped by every
    creator — ``splitEvents`` and the GRS rules alike. Ordering by it rather
    than by engine id is what makes the numbering reproducible. event nodes with
    no core (implicit reference event nodes, placeholders) sort last, tie-broken
    by node id.
    """
    sIds = [
        nodeId for nodeId, node in data["nodes"].items() if node.get("type") == "S"
    ]
    sIds.sort(key=lambda nodeId: (_naturalKey(data["nodes"][nodeId].get("core")), nodeId))
    for position, nodeId in enumerate(sIds, 1):
        data["nodes"][nodeId]["event"] = f"S{position}"
    return data


def canonicalizeIds(data: dict) -> dict:
    """Rename engine-allocated ids so they depend on content, not allocation.

    S nodes take their canonical event name; every other ``_N_`` id is
    renumbered in the order of a structural signature (type, feature, value,
    relation, and the sorted names of its neighbours). Identical twins fall
    back to the previous id order, which is a rare and documented residue.

    Runs before ``addVariables`` so that created V nodes get canonical vars.
    """
    nodes, edges = data["nodes"], data["edges"]

    def nameOf(nodeId: str) -> str:
        node = nodes.get(nodeId, {})
        return str(
            node.get("var")
            or node.get("event")
            or node.get("concept")
            or node.get("pred")
            or node.get("value")
            or ""
        )

    def signature(nodeId: str) -> tuple:
        node = nodes[nodeId]
        outgoing = sorted(
            (str(e["label"]), nameOf(e["tar"])) for e in edges if e["src"] == nodeId
        )
        incoming = sorted(
            (str(e["label"]), nameOf(e["src"])) for e in edges if e["tar"] == nodeId
        )
        return (
            node.get("type", ""),
            node.get("feat", ""),
            str(node.get("value", "")),
            node.get("rel", ""),
            node.get("event", ""),
            tuple(outgoing),
            tuple(incoming),
            nodeId,
        )

    mapping = {
        nodeId: node["event"]
        for nodeId, node in nodes.items()
        if node.get("type") == "S" and node.get("event") and nodeId != node["event"]
    }
    dirty = sorted(
        (
            nodeId
            for nodeId in nodes
            if nodeId not in mapping
            and _ENGINE_ID.fullmatch(nodeId)
            and nodes[nodeId].get("type") != "S"
        ),
        key=signature,
    )
    for position, nodeId in enumerate(dirty, 1):
        if nodeId != f"_{position}_":
            mapping[nodeId] = f"_{position}_"

    if not mapping:
        return data

    def rename(renaming: dict[str, str]) -> None:
        for edge in edges:
            edge["src"] = renaming.get(edge["src"], edge["src"])
            edge["tar"] = renaming.get(edge["tar"], edge["tar"])
        data["nodes"] = {renaming.get(k, k): v for k, v in data["nodes"].items()}

    # Two phases, because a target name may collide with an id still in use.
    temporary = {old: f"__tmp_{index}__" for index, old in enumerate(mapping)}
    rename(temporary)
    rename({temporary[old]: new for old, new in mapping.items()})
    return data


def addVariables(data: dict) -> dict:
    """Give every node a ``var``, defaulting to its own id."""
    for nodeId, node in data["nodes"].items():
        node.setdefault("var", nodeId)
    return data


def canonicalize(data: dict) -> dict:
    """Run the three passes in their required order."""
    return addVariables(canonicalizeIds(renameSNodes(data)))