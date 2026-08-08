# Command reference

Seven commands under `weave`. `python -m weave_amr2yarn …` is identical if the script
is not on `PATH`. For worked examples see [use-cases.md](use-cases.md).

```
weave convert   an AMR corpus to YARN
weave run       raw text to YARN, parsing the AMR first
weave anchors   build an anchor dictionary
weave batch     several corpora from one config file
weave export    YARN output packaged for the external editor
weave doctor    check this machine is set up
weave strats    list the strategies a rule set declares
```

## weave convert

```bash
weave convert --amr CORPUS --out DIR [options]
```

Writes `DIR/grew/<id>.json` and `DIR/yarn/<id>.json`, plus `manifest.json`.

**Inputs**

| | |
|---|---|
| `--amr` | AMR corpus in Penman format (required) |
| `--out` | output directory (required) |
| `--ud` | CoNLL-U file. Without it, Stanza parses the sentence |
| `--anchors` | anchor dictionary JSON. Sentences it misses are anchored by `--anchorer` |
| `--key-snt` | metadata key holding the sentence (default `snt`) |
| `--strict-ud` | fail sentences missing from `--ud` rather than parsing them |
| `--lang` | parser language (default `en`) |

**Anchoring**

| | |
|---|---|
| `--anchorer` | `levenshtein` (default) or `leamr` |
| `--anchor-threshold` | Levenshtein similarity floor (default `0.7`) |
| `--stages` | align2anchor stages, comma separated (default `filter,repair`; empty for the raw alignment) |
| `--leamr-dir` | LEAMR checkout, too large to bundle |
| `--span-resolution` | how a multi-token span collapses to one token: `first` (default), `head`, `head-common` |

**Rules and output**

| | |
|---|---|
| `--grs` | rule set entry file (default: the bundled rules) |
| `--strat` | strategy (default `eval`); `weave strats` lists them |
| `--timeout` | per-sentence seconds, `0` disables (default `30`) |
| `--layout` | `flat` (default) or `grouped`, which puts `a.b` at `a/b.json` |
| `--grew-only` | stop before YARN |
| `--stamp-meta` | record the anchors used and the conversion time in each graph's metadata. **Changes the output** |
| `--penman-dereify` | an optional pre-pass on the Penman text; the rule set does this work itself |
| `--quiet`, `--no-manifest` | suppress progress; skip `manifest.json` |

## weave run

Parses sentences into AMR, then converts. Takes every `convert` option above, plus:

| | |
|---|---|
| `--text` | one sentence per line (required) |
| `--parser` | `amrlib` in this process (default), or `spring` against a service |
| `--amr-model` | amrlib model directory, or set `WEAVE_AMR_MODEL` |
| `--spring-endpoint` | SPRING service URL (default `http://localhost:8080/parse`) |
| `--device` | torch device for amrlib, e.g. `cpu` or `cuda:0` |
| `--save-amr` | also write the parsed AMR corpus here |

Keep the parse with `--save-amr` if you want LEAMR anchoring: the aligner works on
files, not in-memory graphs.

## weave anchors

Builds an anchor dictionary as a reusable artifact, so a corpus is not realigned on
every run.

| | |
|---|---|
| `--amr`, `--ud`, `--out` | corpus, CoNLL-U, dictionary to write (all required) |
| `--source` | `leamr` runs the aligner (default); `raw` reads its output |
| `--raw` | the aligner's output, required by `--source raw` |
| `--audit` | write the filter's decisions to this TSV |
| `--stages`, `--leamr-dir`, `--span-resolution` | as for `convert` |

`--source raw` feeds an existing alignment through the stages without realigning —
useful for comparing what the stages do.

## weave batch

```bash
weave batch --config weave.toml [--only NAME …] [--out-root DIR]
```

| | |
|---|---|
| `--config` | TOML config file (required) |
| `--only` | run only these corpora |
| `--out-root` | write under here instead of the config's `out_root` |
| `--quiet`, `--no-manifest` | as for `convert` |

Config format and semantics are in [use-cases.md](use-cases.md#several-corpora).

## weave export

```bash
weave export --yarn DIR --out sample.zip [--name NAME] [--jsonl]
```

Packages a directory of YARN output for the external editor: files renamed to
`.yarn.json`, with the metadata the editor expects. `--jsonl` writes one `.jsonl`
instead of a file per graph. `--name` sets the sample name, defaulting to the
directory's.

## weave doctor

```bash
weave doctor [--lang LANG]
```

Reports what is present and what is missing, with the command to fix each. Worth
running first: two dependencies are not a `pip install`.

## weave strats

```bash
weave strats [--grs GRS]
```

Lists the strategies a rule set declares, top-level and in-package. This is the check
that catches a broken package reference — a bad one loads cleanly and fails only when a
strategy runs.

## Progress and exit

Progress goes to stderr: a rewritten line on a terminal, a line per 10% when
redirected. `--quiet` turns it off.

A sentence that fails does not stop the run. Failures are counted, listed at the end,
and recorded in `manifest.json`.
