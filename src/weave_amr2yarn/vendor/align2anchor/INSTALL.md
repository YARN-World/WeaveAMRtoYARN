# Installing against a fresh LEAMR

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

## What the library patches

`leamr_compat.installRuntimeShims()` runs automatically when the models load and
fixes, in memory, upstream defects that would otherwise crash a *single-sentence*
run. Currently one:

- `Relation_Model.coverage` divides by the number of external edges. A short
  sentence whose edges all fall inside one aligned subgraph has none, so aligning
  it raises `ZeroDivisionError` on a stock checkout.

Shims cover crashes only. Nothing that changes *which* tokens get aligned is
patched silently — a hidden behavioural difference between checkouts is precisely
what makes results irreproducible.

## Verified

A copy of this package, on a path of its own, against a clone made straight from
GitHub (plus `amr_utils`), aligned `(w / want-01 :ARG0 (b / boy) :ARG1 (g / go-01
:ARG0 b))` to `{'b': '2', 'w': '3', 'g': '5'}` — *boy*, *wants*, *go* — with no
edits to the checkout.
