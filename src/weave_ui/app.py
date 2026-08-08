"""The browser app.

A thin layer over the library: read the request, call the library, render.
Anything that is really conversion belongs in weave_amr2yarn, not here.

URL paths match the tool this replaces so the page's JavaScript is unchanged.
"""

from __future__ import annotations

import html
import traceback

from flask import Flask, jsonify, render_template, request

from weave_amr2yarn import ConversionConfig, GrsSession, __version__
from weave_amr2yarn.errors import WeaveError
from weave_amr2yarn.formats.yarn import toYarn
from weave_amr2yarn.graph import canonicalize
from weave_amr2yarn.render import RenderError, availability, rendererFor
from weave_amr2yarn.resources import bundledGrs

from .conversion import InputError, anchorTable, buildAnchored
from .stepsview import renderSteps
from .tracing import StepTracer, loadSteps


def _draw(kind: str, graph, prefix: str, **options) -> str:
    """Render, or return a note saying why not.

    Renderers deliberately raise instead of producing markup; turning that into
    something displayable is this layer's job, and only here.
    """
    try:
        return rendererFor(kind).render(graph, prefix=prefix, **options)
    except RenderError as exc:
        return f'<p class="render-note">{html.escape(str(exc))}</p>'
    except Exception as exc:  # a real bug, not a missing tool
        message = f"{type(exc).__name__}: {exc}"
        return f'<p class="render-error">{html.escape(message)}</p>'


def createApp(grsPath=None, strategy: str = "eval") -> Flask:
    app = Flask(__name__)

    config = ConversionConfig(grsPath=grsPath or bundledGrs(), strategy=strategy)
    # Loaded once for the life of the process, not once per request.
    session = GrsSession(config.grsPath, config.strategy)
    steps = loadSteps(config.grsPath, config.strategy)
    tracer = StepTracer(session, steps)

    # The last trace, so a highlight request can redraw a step without
    # recomputing the whole run. Single-user tool; one slot is enough.
    state: dict = {"trace": []}

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            version=__version__,
            strategy=config.strategy,
            stepCount=len(steps),
            renderers=availability(),
        )

    @app.get("/info")
    def info():
        return jsonify(
            version=__version__,
            grs=str(config.grsPath),
            strategy=config.strategy,
            steps=steps,
            renderers=availability(),
        )

    @app.post("/run")
    def run():
        try:
            data = request.get_json(force=True) or {}
            anchored = buildAnchored(
                data.get("amr", ""),
                udSource=data.get("ud_src", "stanza"),
                conlluText=data.get("conllu", ""),
                anchorSource=data.get("anc_src", "levenshtein"),
                anchorJson=data.get("anchor_json", ""),
            )

            result = {
                "snt": anchored.text,
                "anchor_dict": anchored.anchors,
                "anchor_data": anchorTable(anchored),
                "amr_svg": _draw("amr", anchored.penman, "amr")
                if anchored.penman
                else '<p class="render-note">No AMR</p>',
                "ud_svg": _draw("ud", anchored.udGraph, "ud"),
            }

            if data.get("batch"):
                final = canonicalize(
                    session.apply(anchored.graph, timeoutSeconds=config.timeoutSeconds)
                )
                yarn, error = _toYarn(final)
                return jsonify(
                    anchor_dict=anchored.anchors, yarn_grs=yarn, yarn_grs_error=error
                )

            trace = tracer.trace(
                anchored.graph, withRules=bool(data.get("rules", True))
            )
            state["trace"] = trace
            for position, step in enumerate(trace):
                step.svg = _draw("grew", step.graph, f"grs_s{position}")

            result["steps_grs"] = renderSteps(trace, "grs")
            final = canonicalize(trace[-1].graph)
            yarn, error = _toYarn(final)
            result["yarn_grs_json"] = yarn
            result["yarn_grs"] = (
                _draw("yarn", yarn, "yarn_grs")
                if yarn
                else f'<p class="render-note">{html.escape(error or "no YARN")}</p>'
            )
            result["pipeline"] = "grs"
            return jsonify(result)

        except InputError as exc:
            return jsonify(error=str(exc))
        except WeaveError as exc:
            return jsonify(error=str(exc))
        except Exception:
            return jsonify(error=traceback.format_exc())

    @app.post("/step_svg")
    def stepSvg():
        """Redraw one traced step with some of its nodes ringed."""
        try:
            data = request.get_json(force=True) or {}
            trace = state.get("trace") or []
            position = int(data.get("step", 0))
            if not 0 <= position < len(trace):
                return jsonify(error="No such step; run the pipeline first.")
            nodes = {str(item) for item in data.get("nodes", []) if item}
            return jsonify(
                svg=_draw(
                    "grew",
                    trace[position].graph,
                    f"grs_s{position}",
                    highlight=nodes,
                )
            )
        except Exception:
            return jsonify(error=traceback.format_exc())

    @app.post("/yarn_svg")
    def yarnSvg():
        """Redraw a YARN graph the page already holds, after an edit."""
        try:
            data = request.get_json(force=True) or {}
            graph = data.get("yarn")
            if not graph:
                return jsonify(error="No YARN graph supplied.")
            return jsonify(svg=_draw("yarn", graph, data.get("prefix", "yarn")))
        except Exception:
            return jsonify(error=traceback.format_exc())

    @app.post("/sentence_info")
    def sentenceInfo():
        """UD and anchors without running the rules — for the editor sidebar."""
        try:
            data = request.get_json(force=True) or {}
            anchored = buildAnchored(
                data.get("amr", ""),
                udSource=data.get("ud_src", "stanza"),
                conlluText=data.get("conllu", ""),
                anchorSource="manual" if data.get("anchor_json") else "levenshtein",
                anchorJson=data.get("anchor_json", ""),
            )
            return jsonify(
                snt=anchored.text,
                ud_svg=_draw("ud", anchored.udGraph, "udinfo"),
                anchor_data=anchorTable(anchored),
            )
        except InputError as exc:
            return jsonify(error=str(exc))
        except Exception:
            return jsonify(error=traceback.format_exc())

    @app.post("/spring_parse")
    def springParse():
        """Parse sentences into AMR, through whichever parser is configured."""
        try:
            data = request.get_json(force=True) or {}
            sentences = data.get("sentences") or (
                [data["sentence"]] if data.get("sentence") else []
            )
            sentences = [s.strip() for s in sentences if s and s.strip()]
            if not sentences:
                return jsonify(error="No sentence supplied.")

            parser = _parserFrom(data)
            graphs = parser.parse(sentences)
            if len(graphs) == 1 and not data.get("sentences"):
                return jsonify(amr=graphs[0])
            return jsonify(amrs=graphs)
        except WeaveError as exc:
            return jsonify(error=str(exc))
        except Exception:
            return jsonify(error=traceback.format_exc())

    return app


def _parserFrom(data: dict):
    """The AMR parser the request asked for."""
    from weave_amr2yarn.providers.parser import AmrlibParser, SpringParser

    if data.get("parser") == "amrlib" or data.get("amr_model"):
        return AmrlibParser(data.get("amr_model"), device=data.get("device"))
    return SpringParser(data.get("endpoint") or "http://localhost:8080/parse")


def _toYarn(grew: dict) -> tuple[dict | None, str | None]:
    try:
        yarn = toYarn(grew)
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not yarn.get("s"):
        return yarn, "no event node"
    return yarn, None