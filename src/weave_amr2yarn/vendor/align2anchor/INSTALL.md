# Installing against a fresh LEAMR

The library itself needs only `penman` (plus `flask` for the viewer and `stanza`
if you want to parse sentences). The aligner is the awkward part: **LEAMR is not
pip-installable**, and a naive clone is missing a piece.

Check any checkout before trusting it:

    python -m align2anchor doctor --leamr-dir /path/to/leamr

## The three-step install

    git clone https://github.com/ablodge/leamr
    cd leamr
    git clone https://github.com/ablodge/amr-utils amr_utils     # ← separate repo
    pip install stanza penman

Then point the library at it:

    LeamrService(leamrDir="/path/to/leamr")            # viewer
    LeamrAdapter(LeamrResources("/path/to/leamr"))     # library
    python -m alignment.align2anchor.viewer --leamr-dir /path/to/leamr

### Things that catch people out

**`amr_utils` is a second repository.** It is imported as a top-level module
(`from amr_utils.amr_readers import AMR_Reader`) but is *not* part of the LEAMR
repo — it has to be cloned inside it under exactly that name. Without it every
import of the aligner fails.

**The trained models do ship with the repo** (`*_params.pkl`, ~660 MB), so a full
clone is enough — but a `--filter=blob:none` or sparse clone will silently omit
them. `doctor` checks for all three.

**The clone is large** (~1.3 GB with the pickles). A sparse clone works if it
includes `models/`, `rule_based/`, `evaluate/` *and* the root files:

    git clone --filter=blob:none --sparse https://github.com/ablodge/leamr
    cd leamr && git sparse-checkout set models rule_based evaluate display scripts

**Never put `<repo>/alignment` on `sys.path`.** `alignment/evaluate.py` shadows
LEAMR's own `evaluate` package. `LeamrResources.wireImports()` strips that
directory when it loads for exactly this reason, which is why anything importing
this library must be launched from the repo root.

## What the library patches for you

`leamr_compat.installRuntimeShims()` runs automatically when the models load and
fixes, in memory, upstream defects that would otherwise crash a *single-sentence*
run. Currently one:

- `Relation_Model.coverage` divides by the number of external edges. A short
  sentence whose edges all fall inside one aligned subgraph has none, so aligning
  it raises `ZeroDivisionError` on a stock checkout.

Shims cover crashes only. Nothing that changes *which* tokens get aligned is
patched silently — a hidden behavioural difference between checkouts is precisely
what makes results irreproducible.

## Reproducing this project's numbers exactly

The checkout this project developed against carries alignment-rule edits
(`rule_based/subgraph_rules.py`), shipped here as `leamr_local.patch`:

    cd /path/to/leamr && git apply /path/to/align2anchor/leamr_local.patch

**Apply it if copular frames matter to you — they probably do.** The patch adds
explicit rules anchoring `be-located-at-91` and `be-from-91` to the **copula**;
stock LEAMR anchors them to the locative **preposition or adverb**. Measured
across every sentence in FraCaS, PUD and Little Prince containing such a frame:

| | stock | patched |
|---|---|---|
| fracas-076.premise_0 | `from` | `are` |
| fracas-089.premise_0 | `at` | `was` |
| lpp_1943.4 "Here is a copy…" | `Here` | `is` |
| lpp_1943.92 "…is inside" | `inside` | `is` |
| w02008055 | `on` | `were` |

**9 of 19 frames differ**; both checkouts anchor all 19, just to different
tokens. By contrast, 25/25 sentences *without* such a frame were identical, so
generic text is unaffected.

This matters beyond bit-exactness: the project's tense-placement analysis rests
on reified copular frames being anchored to the copula (a frame with no content
word of its own takes the copula as its exponent). On a stock checkout that
premise does not hold, and `temp` behaviour will differ accordingly. `doctor`
reports the patch's absence as a warning, not an error — the aligner runs fine
without it, it simply makes different choices exactly where this project cares
most.

## Verified

A copy of this package, on a path of its own, against a clone made straight from
GitHub (plus `amr_utils`), aligned `(w / want-01 :ARG0 (b / boy) :ARG1 (g / go-01
:ARG0 b))` to `{'b': '2', 'w': '3', 'g': '5'}` — *boy*, *wants*, *go* — with no
edits to the checkout.
