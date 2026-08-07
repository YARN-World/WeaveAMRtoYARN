"""Drawing a YARN graph.

Three hops: ``yarn2tikz.js`` turns the graph into TikZ, LaTeX compiles that to
PDF, and pdf2svg converts it. The layout logic lives in yarn_utils' JavaScript,
so this is a pipeline rather than a drawing routine.

That makes it the expensive renderer — a first compile is around a second — so
results are cached on disk under a digest of the TikZ.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .base import BaseRenderer, RenderError, binaryRequirement, packageRequirement
from .svgtools import stripPrologue, uniquifyIds

#: Points at the yarn_utils ``js/`` directory when it is not importable.
JS_VARIABLE = "YARN_UTILS_JS"

_DOCUMENT = "\\documentclass[border=2bp]{standalone}\n%s\n"

#: Tried in order; the first that produces a PDF wins. tectonic needs no TeX
#: installation, which is why it is worth keeping both.
_LATEX_COMMANDS = (
    ["pdflatex", "--interaction=nonstopmode"],
    ["tectonic"],
)


def findJsDir() -> Path | None:
    """Locate ``yarn2tikz.js``: the override first, then the package."""
    override = os.environ.get(JS_VARIABLE)
    if override and (Path(override) / "yarn2tikz.js").is_file():
        return Path(override)
    try:
        import yarn_utils

        candidate = Path(yarn_utils.__file__).parent / "js"
        if (candidate / "yarn2tikz.js").is_file():
            return candidate
    except ImportError:
        pass
    return None


class YarnRenderer(BaseRenderer):
    """A YARN graph, drawn through yarn_utils' TikZ layout."""

    name = "yarn"

    def __init__(self, cacheDir: str | Path | None = None) -> None:
        self.cacheDir = Path(cacheDir) if cacheDir else None

    def requirements(self):
        return [
            packageRequirement("yarn_utils"),
            binaryRequirement("node", "brew install node"),
            binaryRequirement("pdf2svg", "brew install pdf2svg"),
            binaryRequirement("tectonic", "brew install tectonic (or use pdflatex)"),
        ]

    def available(self) -> bool:
        """LaTeX is satisfied by either engine, so the base rule is too strict."""
        needed = {item.name: item.present for item in self.requirements()}
        latex = needed.get("tectonic") or binaryRequirement("pdflatex").present
        return (
            needed.get("yarn_utils", False)
            and needed.get("node", False)
            and needed.get("pdf2svg", False)
            and latex
            and findJsDir() is not None
        )

    def _cacheRoot(self) -> Path:
        return self.cacheDir or Path(tempfile.gettempdir()) / "weave-yarn-svg"

    def _toTikz(self, yarn: dict) -> str:
        jsDir = findJsDir()
        if jsDir is None:
            raise RenderError(
                "yarn: yarn2tikz.js not found; set "
                f"{JS_VARIABLE} to the yarn_utils js/ directory"
            )
        # The script takes a path; writing one avoids a large stdin write.
        handle = tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False, encoding="utf-8"
        )
        try:
            json.dump(yarn, handle)
            handle.close()
            result = subprocess.run(
                ["node", str(jsDir / "yarn2tikz.js"), handle.name],
                capture_output=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError("yarn: yarn2tikz.js timed out") from exc
        finally:
            Path(handle.name).unlink(missing_ok=True)

        if result.returncode != 0:
            raise RenderError(f"yarn: yarn2tikz.js: {result.stderr.decode().strip()}")
        return result.stdout.decode("utf-8")

    def _toPdf(self, tikz: str) -> Path:
        digest = hashlib.sha1(tikz.encode("utf-8")).hexdigest()[:16]
        directory = self._cacheRoot() / digest
        directory.mkdir(parents=True, exist_ok=True)
        source, pdf = directory / "input.tex", directory / "input.pdf"
        if pdf.exists():
            return pdf

        source.write_text(_DOCUMENT % tikz, encoding="utf-8")
        for command in _LATEX_COMMANDS:
            try:
                result = subprocess.run(
                    [*command, str(source)],
                    capture_output=True,
                    cwd=directory,
                    timeout=120,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            if result.returncode == 0 and pdf.exists():
                return pdf
        raise RenderError("yarn: neither pdflatex nor tectonic produced a PDF")

    def render(self, graph: dict, prefix: str = "yarn") -> str:
        if not graph.get("s"):
            # Without an event node there is no spine to draw along.
            raise RenderError("yarn: no event node in the graph")

        pdf = self._toPdf(self._toTikz(graph))
        svg = pdf.with_suffix(".svg")
        if not svg.exists():
            try:
                result = subprocess.run(
                    ["pdf2svg", str(pdf), str(svg)], capture_output=True, timeout=30
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                raise RenderError("yarn: pdf2svg is missing or timed out") from exc
            if result.returncode != 0:
                raise RenderError(f"yarn: pdf2svg: {result.stderr.decode().strip()}")

        return uniquifyIds(stripPrologue(svg.read_text(encoding="utf-8")), prefix)