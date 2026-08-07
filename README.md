# WeaveAMRtoYARN

Converts Abstract Meaning Representation graphs into YARN graphs, by anchoring
the AMR to a Universal Dependencies analysis of the same sentence and rewriting
the result with a GREW graph-rewriting system.

```
AMR (Penman) ─┐
              ├─► anchored graph ─► GREW rewriting ─► YARN
UD (CoNLL-U) ─┘
```

The rewriting runs on [grewpy](https://grew.fr/usage/python/), which needs more
setup than `pip install` — follow its official guide. Then see
[INSTALL.md](INSTALL.md) and run `weave doctor`.

## Command line

```bash
weave convert --amr corpus.txt --out out/            # Stanza parses the UD
weave convert --amr corpus.txt --out out/ \
              --ud corpus.conllu \                   # gold UD instead
              --anchors anchors.json                 # gold anchors instead

weave convert --amr corpus.txt --out out/ \
              --ud corpus.conllu \
              --anchorer leamr                       # align with LEAMR, then convert

weave doctor            # is this machine set up?
weave strats            # what strategies does the rule set declare?
```

Output goes to `out/grew/<id>.json` and `out/yarn/<id>.json`. Use
`--layout grouped` to put `fracas-001.premise_0` at
`fracas-001/premise_0.json`, and `--grew-only` to stop before YARN.

`python -m weave_amr2yarn ...` works identically if the script is not on PATH.

## From raw text

`weave run` parses sentences into AMR first, then converts as usual. Input is
one sentence per line.

```bash
pip install 'weave-amr2yarn[parse]'
# download a model from https://github.com/bjascob/amrlib-models and unpack it

weave run --text sentences.txt --out out/ \
          --amr-model /path/to/model_parse_xfm_bart_base-v0_1_0 \
          --save-amr parsed.amr.txt        # keep the AMR too
```

Models are not bundled — the smallest is around 500 MB. Point at one with
`--amr-model` or `WEAVE_AMR_MODEL`. The `parse_xfm` models load through the
standard transformers interfaces; `parse_spring` is also an amrlib model but
needs `transformers<5`.

Parsed text has no gold UD or anchors, so conversion falls back to Stanza and
Levenshtein.

**To use LEAMR anchors instead**, you need the AMR and the UD as files, since
LEAMR aligns files rather than in-memory graphs. Keep the parse with
`--save-amr`, and supply a CoNLL-U covering the same sentence ids:

```bash
weave run --text sentences.txt --out out/ --amr-model MODEL \
          --save-amr parsed.amr.txt --ud sentences.conllu --anchorer leamr
```

Or in two steps, which lets the dictionary be reused and inspected:

```bash
weave anchors --amr parsed.amr.txt --ud sentences.conllu \
              --out anchors.json 
weave convert --amr parsed.amr.txt --ud sentences.conllu \
              --anchors anchors.json --out out/
```

SPRING can also run as a service, which keeps its dependencies out of this
environment entirely:

```bash
weave run --text sentences.txt --out out/ --parser spring \
          --spring-endpoint http://localhost:8080/parse
```

A checkpoint from the original SPRING codebase only works this way — it
carries decoder pointer-attention weights that amrlib's port has no slots for,
so it cannot be loaded with `--parser amrlib`.

## LEAMR anchoring

`--anchorer leamr` aligns with LEAMR and converts in one go. Anchoring is a
corpus-level step, so the aligner runs once before conversion starts, and
sentences it does not cover fall back to Levenshtein.

```bash
weave convert --amr corpus.txt --ud corpus.conllu --anchorer leamr --out out/
```
To keep the dictionary as an artifact rather than realigning every run:

```bash
weave anchors --amr corpus.txt --ud corpus.conllu --out anchors.json \
weave convert --amr corpus.txt --ud corpus.conllu --anchors anchors.json --out out/
```

`--stages` selects what runs after the aligner (default `filter,repair`; pass
an empty value for the raw alignment), and `--source raw --raw FILE` feeds an
aligner's existing output through those stages instead of realigning.

## What a run records

Every conversion writes `manifest.json` beside its output: when it ran and for
how long, the inputs, the strategy, which providers were used, the counts, and
any failures. The rules are identified by a digest over the whole rule
directory rather than the entry file, since `main.grs` includes 43 siblings and
loads lexicons — hashing the entry alone would call two different rule sets
identical.

```json
{ "weave": "0.1.0",
  "startedAt": "2026-08-07T20:40:35.163Z", "durationSeconds": 1.331,
  "inputs": { "amr": "…", "ud": "…", "anchors": "…" },
  "rules": { "strategy": "eval", "sha256": "75f6dc03…" },
  "counts": { "sentences": 100, "converted": 100, "failed": 0 } }
```

`--stamp-meta` additionally records, in each graph's own metadata, the anchors
that were used and when it was converted:

```json
"meta": { "id": "n01118003", "snt": "Drop the mic.",
          "anchors": { "d": "1", "m": "3" },
          "converted_at": "2026-08-07T20:42:39.093Z" }
```

That is worth having because the rewriting turns anchors into edges that later
rules consume, so the output alone does not say what they were. It is off by
default because it changes the output, which would otherwise keep comparing
byte-for-byte against earlier runs.

Progress goes to stderr: a rewritten line on a terminal, a line per 10% when
redirected. `--quiet` turns it off, `--no-manifest` skips the manifest.

## Several corpora at once

Put the sweep in a config file rather than a shell loop — the file is then the
record of what was run.

```toml
# weave.toml
out_root = "results"

[defaults]
strat = "eval"
key_snt = "snt"

[corpus.pud]
amr = "input/pud_100_gold.txt"
ud = "input/en_pud-ud-test.conllu"
anchors = "input/anchor_dict_gold.json"

[corpus.fracas]
amr = "input/fracas_gold_subset.amr.txt"
anchors = "input/anchor_dict_rules.json"
layout = "grouped"
```

```bash
weave batch --config weave.toml
weave batch --config weave.toml --only fracas      # just one
weave batch --config weave.toml --out-root /tmp/x  # somewhere else
```

Each corpus writes to `<out_root>/<name>/{grew,yarn}`. `[defaults]` applies to
every corpus and each section overrides it. Any `convert` option works as a
key, in either `snake_case` or `camelCase`. Paths resolve relative to the
config file, so it travels with its data, and a corpus that fails is reported
without abandoning the rest of the sweep.

## Library

```python
from weave_amr2yarn import Converter, ConlluUd, PrecomputedAnchorer

converter = Converter(
    ud=ConlluUd.fromFile("corpus.conllu"),
    anchors=PrecomputedAnchorer.fromFile("anchors.json"),
)
yarn = converter.convert(amrPenmanString)
```

The rule set loads once, when the `Converter` is built, so reuse it across a
corpus rather than constructing one per sentence.

`converter.toGrew(...)` returns the rewritten GREW graph instead of YARN, and
`converter.anchored(...)` returns the merged AMR + UD graph before any
rewriting — the thing to look at when anchoring is suspect, since it is what
the rules actually see.

For a whole corpus:

```python
from weave_amr2yarn import AmrCorpus, BatchConverter

report = BatchConverter(converter).run(AmrCorpus.fromFile("corpus.txt"), "out/")
print(report.summary())          # "100 converted"
for sentenceId, message in report.failures:
    ...
```

## Choosing where the inputs come from

An AMR carries neither a UD analysis nor a mapping from its variables to
tokens. Both are supplied by a provider, so a new source is a new class rather
than an edit to the conversion.

| | providers |
|---|---|
| UD | `ConlluUd`, `StanzaUd`, `ChainedUd` |
| anchors | `PrecomputedAnchorer`, `LevenshteinAnchorer`, `ChainedAnchorer` |

The chained forms take the first provider that answers, which covers the usual
mixed case — gold data where it exists, computed elsewhere:

```python
from weave_amr2yarn import ChainedUd, ChainedAnchorer, LevenshteinAnchorer, StanzaUd

converter = Converter(
    ud=ChainedUd(ConlluUd.fromFile("gold.conllu"), StanzaUd()),
    anchors=ChainedAnchorer(PrecomputedAnchorer.fromFile("gold.json"),
                            LevenshteinAnchorer()),
)
```

This is what the CLI builds when given `--ud` and `--anchors`; pass
`--strict-ud` to fail sentences the CoNLL-U file does not cover instead of
parsing them.

Anything with a `graphFor(sentence)` or `anchorsFor(sentence, amr, ud)` method
qualifies — the protocols are structural, so a provider does not have to
subclass anything.

## Configuration

```python
from weave_amr2yarn import ConversionConfig, Converter

converter = Converter(ConversionConfig(strategy="main", sentenceKey="text"))
```

| | | |
|---|---|---|
| `grsPath` | the bundled rules | a `.grs` entry file |
| `strategy` | `eval` | validated on construction; `weave strats` lists them |
| `sentenceKey` | `snt` | metadata key holding the sentence; some corpora use `text` |
| `timeoutSeconds` | `30` | per graph, 0 to disable |
| `penmanDereify` | `False` | Penman-level `-91` dereification before rewriting |

## Layout

```
formats/     readers and writers      no grewpy, no parser
graph/       AMR transformations      no grewpy, no parser
providers/   where inputs come from
transform/   the rule engine and the conversion it drives
grs/         the rule set, as package data
```

The two lower layers are plain dicts in and dicts out, so most of the library
can be tested with no rule engine running.

## Development

```bash
pip install -e '.[dev]'
pytest                                      # unit tests, no backend needed
```