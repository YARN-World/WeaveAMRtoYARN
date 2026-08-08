# The browser app

A front end for looking at a conversion: the graphs at each stage, what each rule
package changed, and the anchors that were used.

```bash
pip install 'weave-amr2yarn[ui]'
weave-ui                       # http://127.0.0.1:5010
```

It exists because the interesting failures are not exceptions. A conversion that
produces a graph is not necessarily a conversion that produced the right one, and the
usual question — *which rule did this, and what did the graph look like before it?* —
cannot be answered from the output alone.

| | |
|---|---|
| `--host`, `--port` | default `127.0.0.1:5010` |
| `--grs`, `--strat` | rule set and strategy (default: the bundled rules, `eval`) |
| `--amr-model` | amrlib model for parsing typed-in text, or `WEAVE_AMR_MODEL` |
| `--spring-endpoint` | parsing service, used when no model is given |
| `--editor-url` | where the YARN editor lives (default: the released one) |
| `--debug` | Flask debug mode |

## What it shows

**A single conversion.** Paste an AMR, or type a sentence and have it parsed. The page
renders the AMR, the UD tree, the anchored graph, the rewritten graph and the YARN —
the same stages as [pipeline.md](pipeline.md), each as a drawing.

**The step trace.** One button per rule package in the strategy, with the graph after
it and a summary of what changed — nodes and edges added and removed. This is how you
find the package responsible for something, since the engine exposes no firing trace of
its own.

The trace is reconstructed by running the strategy's first *n* steps for increasing
*n*, always from the original graph, and diffing consecutive results
([`tracing.py`](../src/weave_ui/tracing.py)). Restarting each time is deliberate: the
rules can leave an intermediate graph holding the same edge twice, which the engine
carries happily inside one run but which cannot be rebuilt from JSON. Restarting from a
graph that was valid on entry keeps every intermediate inside the engine, so the trace
agrees with a real run instead of dying part-way through it.

The step list is parsed out of the rule set itself rather than kept by hand — a
hand-kept list drifts, and the one this replaced had silently lost four steps.

**Rule eligibility.** Each step can also report which of its rules matched the graph
going in. That is eligibility, not firing: it says a rule *could* have applied, not
that it did. Still the fastest way to see why an expected rule did nothing.

**Anchors.** The anchored graph view shows which AMR variable went to which token.
Since rewriting consumes the anchor edges, this is the only place the correspondence is
visible.

**A corpus run.** Point it at a corpus and convert the whole thing, then browse the
results. From there, `export` packages the run for the external editor, and a single
graph can be opened in the editor directly.

## Endpoints

| | |
|---|---|
| `GET /` | the page |
| `GET /info` | what the server was started with |
| `POST /run` | convert, and return the stages |
| `POST /step_svg` | one step's graph |
| `POST /yarn_svg` | the YARN drawing |
| `POST /sentence_info` | a corpus sentence's AMR, UD and anchors |
| `POST /spring_parse` | parse typed text into AMR |
| `POST /export_zip` | package a run for the editor |

## Layout

| | |
|---|---|
| [`app.py`](../src/weave_ui/app.py) | the Flask app and its endpoints |
| [`conversion.py`](../src/weave_ui/conversion.py) | turns what the page sends into the graphs it wants back |
| [`tracing.py`](../src/weave_ui/tracing.py) | runs the rule set a step at a time; `TraceStep`, `loadSteps`, `difference` |
| [`stepsview.py`](../src/weave_ui/stepsview.py) | renders the step navigator |
| `static/js/` | eleven ES modules, entered at `main.js` |

Drawings come from [`render/`](../src/weave_amr2yarn/render), which is part of the
library rather than the app — the same renderers work from a script.

Steps are rendered server-side because each carries an SVG, and shipping fifty of them
as JSON for the page to assemble gains nothing. They sit in `<template>` elements so
the browser parses them once and swaps them in on demand.

## Limits

The app keeps the current trace in process memory, so it assumes one worker and one
user. It is a development and inspection tool, not a service: run it locally, against
data you already have.
