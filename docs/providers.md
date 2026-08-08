# Providers

Where the three inputs come from, and how to add a source of your own.

An AMR graph carries neither a UD analysis nor a mapping from its variables to tokens.
Both have to come from somewhere, and there is more than one reasonable answer: gold
data, a parser, a computed alignment. The rules take only the finished anchored graph,
so how it was assembled changes nothing about them — which is what makes the input side
substitutable and the rule side fixed.

Each input is behind a `Protocol`. The protocols are **structural**: anything with the
right method qualifies, and a provider subclasses nothing.

| supplies | protocol | method |
|---|---|---|
| the UD analysis | `UdProvider` | `graphFor(sentence) -> dict \| None` |
| the anchors | `AnchorProvider` | `anchorsFor(sentence, amr, ud) -> dict[str, str] \| None` |
| the AMR itself | `AmrParser` | `parse(sentences) -> list[str]` |

Returning `None` means *I have nothing for this sentence* — not an error. It is what
lets providers be chained.

## UD providers

[`providers/ud.py`](../src/weave_amr2yarn/providers/ud.py)

| | |
|---|---|
| `ConlluUd` | reads a CoNLL-U file, matched by sentence identifier. `ConlluUd.fromFile(path)` |
| `StanzaUd` | parses the surface sentence with Stanza, reading it from the AMR's metadata |
| `ChainedUd` | tries each in turn, taking the first that answers |

`StanzaUd` builds its pipeline on first use rather than on import, so a caller who
supplies CoNLL-U and never parses pays nothing — and does not need the models
installed at all.

## Anchor providers

[`providers/anchors.py`](../src/weave_amr2yarn/providers/anchors.py),
[`providers/align2anchor.py`](../src/weave_amr2yarn/providers/align2anchor.py)

| | |
|---|---|
| `PrecomputedAnchorer` | looks the sentence up in an anchor dictionary. `PrecomputedAnchorer.fromFile(path)` |
| `LevenshteinAnchorer` | matches each AMR variable to the most similar token by edit distance. The default, and needs nothing installed |
| `Align2AnchorAnchorer` | anchors from a LEAMR alignment |
| `ChainedAnchorer` | tries each in turn |

`LevenshteinAnchorer` takes a similarity threshold (0.7 by default). It is crude and
deliberately so: it needs no model, works on any sentence, and is a reasonable floor
under the better methods.

`Align2AnchorAnchorer` is corpus-level — the aligner runs once over the whole corpus
before conversion begins, rather than per sentence. Sentences it does not cover fall
back to whatever follows it in the chain. Its post-processing stages (`filter`,
`repair` by default) can be selected individually; see [cli.md](cli.md).

## AMR parsers

[`providers/parser.py`](../src/weave_amr2yarn/providers/parser.py)

| | |
|---|---|
| `AmrlibParser` | an amrlib model loaded in-process |
| `SpringParser` | a parsing service over HTTP, which keeps its dependencies out of this environment |

Models are not bundled — the smallest is around 500 MB.

## Chaining

The chained forms cover the normal mixed case — gold data where it exists, computed
elsewhere:

```python
from weave_amr2yarn import (Converter, ChainedUd, ConlluUd, StanzaUd,
                           ChainedAnchorer, PrecomputedAnchorer, LevenshteinAnchorer)

converter = Converter(
    ud=ChainedUd(ConlluUd.fromFile("gold.conllu"), StanzaUd()),
    anchors=ChainedAnchorer(PrecomputedAnchorer.fromFile("gold.json"),
                            LevenshteinAnchorer()),
)
```

This is what the CLI builds when given `--ud` and `--anchors`. Pass `--strict-ud` to
fail the sentences a CoNLL-U file does not cover instead of parsing them — worth doing
when you expect full coverage, since silently parsing a sentence you meant to supply is
hard to notice.

## Writing one

Implement the method. No base class, no registration:

```python
class TreebankUd:
    """UD from an in-memory treebank, keyed by whatever the corpus calls it."""

    def __init__(self, graphs: dict[str, dict]) -> None:
        self._graphs = graphs

    def graphFor(self, sentence):
        return self._graphs.get(sentence.metadata().get("doc_id"))

converter = Converter(ud=TreebankUd(myGraphs), anchors=LevenshteinAnchorer())
```

The return value must be the working representation — the `{"nodes": …, "edges": …}`
dict described in [data-model.md](data-model.md). `readConllu` produces it from
CoNLL-U text if that is a convenient starting point.

An anchor provider returns `{amrVariable: tokenId}`, where the token identifiers are
those of the UD graph it was handed. It receives the AMR and the UD, so it can compute
rather than look up:

```python
class HeadAnchorer:
    def anchorsFor(self, sentence, amr, ud):
        return {var: token for var, token in myAlignment(amr, ud).items()}
```

Two things to respect. Return `None` rather than `{}` when you have nothing for a
sentence, so a chain can fall through to the next provider — an empty dict means *this
sentence genuinely has no anchors* and stops the chain. And do not mutate the graphs
you are given; the caller still needs them.
