# WeaveAMRtoYARN

Converts Abstract Meaning Representation graphs into YARN. It takes three things — an
AMR graph, a Universal Dependencies analysis of the same sentence, and anchors linking
the AMR variables to the tokens that realise them — and rewrites the combination with a
GREW rule set.

```
AMR (Penman) ─┐
UD (CoNLL-U) ─┼─► anchored AMR–UD graph ─► GREW rewriting ─► YARN
anchors ──────┘
```

The UD analysis and the anchors can be supplied, or computed. The rules see only the
combined graph, so where each part came from makes no difference to them.

It uses [grewpy](https://grew.fr/usage/python/) for the rewriting. Setup is in
[INSTALL.md](INSTALL.md); `weave doctor` reports what a machine is missing.

## Quick start

```bash
weave convert --amr corpus.txt --out out/            # Stanza parses the UD
weave convert --amr corpus.txt --out out/ \
              --ud corpus.conllu \                   # supplied UD
              --anchors anchors.json                 # supplied anchors

weave doctor            # is this machine set up?
weave strats            # what strategies does the rule set declare?
```

Output goes to `out/grew/<id>.json` and `out/yarn/<id>.json`, with a `manifest.json`
recording what the run did. `python -m weave_amr2yarn …` works identically if the
script is not on `PATH`.

There is also a browser app for inspecting a conversion:

```bash
pip install 'weave-amr2yarn[ui]'
weave-ui
```

## Library

```python
from weave_amr2yarn import Converter, ConlluUd, PrecomputedAnchorer

converter = Converter(
    ud=ConlluUd.fromFile("corpus.conllu"),
    anchors=PrecomputedAnchorer.fromFile("anchors.json"),
)
yarn = converter.convert(amrPenmanString)
```

The rule set loads when the `Converter` is built, so reuse one across a corpus rather
than constructing one per sentence.

## Documentation

| | |
|---|---|
| [docs/](docs/) | index, and how the parts fit together |
| [architecture.md](docs/architecture.md) | layers, modules, dependencies |
| [data-model.md](docs/data-model.md) | the representations and the YARN vocabulary |
| [pipeline.md](docs/pipeline.md) | the conversion stage by stage |
| [providers.md](docs/providers.md) | where the inputs come from, and adding your own |
| [use-cases.md](docs/use-cases.md) | end-to-end recipes |
| [cli.md](docs/cli.md) | every command and flag |
| [embedding.md](docs/embedding.md) | using the library inside something larger |
| [browser-app.md](docs/browser-app.md) | the inspection front end |

## Development

```bash
pip install -e '.[dev]'
pytest                                      # unit tests, no backend needed
```