"""Making SVGs safe to embed side by side in one page."""

from __future__ import annotations

import base64
import re

_XML_DECLARATION = re.compile(r"<\?xml[^>]*\?>")
_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>")


def stripPrologue(svg: str) -> str:
    """Drop the XML declaration and doctype, which cannot appear mid-document."""
    return _DOCTYPE.sub("", _XML_DECLARATION.sub("", svg)).strip()


def uniquifyIds(svg: str, prefix: str) -> str:
    """Prefix every id and every reference to one.

    Ids are document-global, so two SVGs on the same page silently share
    gradients, markers and glyph definitions — the second one's arrowheads
    come out of the first one's definitions. Prefixing keeps them apart.

    A plain ``href`` is added beside each ``xlink:href`` because HTML parsers
    do not honour the xlink namespace and drop it, which breaks the ``<use>``
    references that graphviz emits for text glyphs.
    """
    svg = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{prefix}-{m.group(1)}"', svg)
    svg = re.sub(
        r'\bxlink:href="#([^"]+)"',
        lambda m: f'xlink:href="#{prefix}-{m.group(1)}"',
        svg,
    )
    # The lookbehinds keep this from matching the xlink:href just rewritten.
    svg = re.sub(
        r'(?<!:)(?<![a-zA-Z])href="#([^"]+)"',
        lambda m: f'href="#{prefix}-{m.group(1)}"',
        svg,
    )
    svg = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{prefix}-{m.group(1)})", svg)
    svg = re.sub(
        r'\bxlink:href="(#[^"]+)"',
        lambda m: f'xlink:href="{m.group(1)}" href="{m.group(1)}"',
        svg,
    )
    return svg


def toDataUri(svg: str) -> str:
    """Base64 data URI, for an ``<img src=...>`` or a stylesheet."""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
