# Embedding the library

Using the conversion as one stage inside something larger, rather than as a command.

The library is built so the conversion is a function over data: give a `Converter` an
AMR and it returns YARN, with everything variable — where the UD comes from, where the
anchors come from, which rules run — set once when you construct it. That makes it
straightforward to drop into a pipeline that does other things before and after.

## The one rule that matters

**Build a `Converter` once and reuse it.** The rule set is loaded, parsed and validated
when the converter is constructed. Constructing one per sentence pays that cost every
time.

```python
from weave_amr2yarn import Converter, ConlluUd, PrecomputedAnchorer

converter = Converter(
    ud=ConlluUd.fromFile("corpus.conllu"),
    anchors=PrecomputedAnchorer.fromFile("anchors.json"),
)

for sentence in corpus:
    yarn = converter.convert(sentence)
```

A converter holds an engine connection, so treat it as a resource: one per process, and
not shared across threads.

## The three outputs

Each stage of the conversion is reachable, which is what you want when something
downstream disagrees with what you expected:

```python
converter.anchored(sentence)   # the merged AMR + UD graph, before any rewriting
converter.toGrew(sentence)     # the rewritten graph, still in the working form
converter.convert(sentence)    # YARN
```

`anchored()` is the one to reach for when anchoring is suspect — it shows exactly what
the rules will see, including which variables got anchors and which did not.
`toGrew()` is the one to keep if a later stage of your own pipeline wants the typed
graph rather than the YARN document.

## Composing the inputs

The three inputs are independent, so a pipeline can mix supplied and computed data
freely. Gold where it exists, computed elsewhere:

```python
from weave_amr2yarn import (Converter, ChainedUd, ConlluUd, StanzaUd,
                           ChainedAnchorer, PrecomputedAnchorer, LevenshteinAnchorer)

converter = Converter(
    ud=ChainedUd(ConlluUd.fromFile("gold.conllu"), StanzaUd()),
    anchors=ChainedAnchorer(PrecomputedAnchorer.fromFile("gold.json"),
                            LevenshteinAnchorer()),
)
```

Anything with the right method is a provider — no base class, no registration — so a
source of your own slots in the same way. See [providers.md](providers.md).

## Configuration

```python
from weave_amr2yarn import ConversionConfig, Converter

converter = Converter(
    ConversionConfig(strategy="main", sentenceKey="text", timeoutSeconds=60),
    ud=…, anchors=…,
)
```

The strategy is validated when the converter is built, so a typo fails immediately
rather than on the first sentence. Fields are listed in
[pipeline.md](pipeline.md#configuration).

To run a rule set of your own, point `grsPath` at its entry file. The bundled one is
`bundledGrs()`.

## A corpus

`BatchConverter` runs a converter over a corpus, writes the output, and reports:

```python
from weave_amr2yarn import AmrCorpus, BatchConverter

report = BatchConverter(converter).run(AmrCorpus.fromFile("corpus.txt"), "out/")

print(report.summary())          # "100 converted, 2 failed, 12.4s"
for sentenceId, message in report.failures:
    log.warning("%s: %s", sentenceId, message)
```

`BatchReport` carries `converted`, `failures` as `(id, message)` pairs, `skipped`,
`startedAt`, `finishedAt` and `durationSeconds`.

## Handling failure

Everything raises a subclass of `WeaveError`, so one `except` covers the library:

```python
from weave_amr2yarn import WeaveError, ConversionTimeout

try:
    yarn = converter.convert(sentence)
except ConversionTimeout:
    ...                      # this graph was too slow; the rest are fine
except WeaveError as exc:
    ...                      # anything else the conversion could not do
```

Failures are per sentence, not per corpus. A pipeline should record the identifier and
carry on — which is what `BatchConverter` does, and why its report has a failure list
rather than raising.

Distinguish these two: `MissingDependency` and `GrsError` are almost always
environmental and will affect every sentence, so there is no point continuing.
`AmrParseError`, `ConversionTimeout` and `GrewBackendError` are usually about one
graph.

## Reading the output back

The YARN document is JSON, described in [data-model.md](data-model.md#4-yarn--the-output).
For a directory of previous output:

```python
from weave_amr2yarn.formats.editor import readYarnDirectory

graphs = readYarnDirectory("out/yarn")     # {sentenceId: yarn}
```

Anchors can be kept as their own artifact and reused, compared, or diffed against
another method:

```python
from weave_amr2yarn import AnchorDictionary

mine = AnchorDictionary.fromFile("mine.json")
gold = AnchorDictionary.fromFile("gold.json")
agreement = len(mine.triples() & gold.triples()) / len(gold.triples())
```

## What travels with the library

The rule set ships inside the package and is found through `resources.py`, so an
embedded conversion needs no checkout and no working directory:

```python
from weave_amr2yarn import bundledGrs
bundledGrs()          # …/site-packages/weave_amr2yarn/grs/main.grs
```

What does not travel: the engine, which is a separate program
([grewpy](https://grew.fr/usage/python/)), and any parser models. `weave doctor` — or
`weave_amr2yarn.doctor` — reports what a machine is missing, which is worth calling
from your own start-up check rather than discovering it on the first sentence.
