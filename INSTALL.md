# Installing

```bash
pip install /path/to/WeaveAMRtoYARN
weave doctor
```

`weave doctor` reports what is present and what is missing, with the command to
fix each one.

## grewpy

The rewriting uses [grewpy](https://grew.fr/usage/python/). Install it by
following its own guide.

## Stanza

Stanza parses the UD analysis from the sentence. It is needed for any sentence
you do not supply as CoNLL-U:

```bash
pip install 'weave-amr2yarn[stanza]'
python -c "import stanza; stanza.download('en')"
```

The models are a separate download, which is why `weave doctor` checks for both.

## Checking it worked

```bash
weave doctor
weave strats                     # should list eval, main, and four others
```

The rule set ships inside the package, so a conversion needs no checkout and can
run from anywhere:

```bash
weave convert --amr /path/to/corpus.txt --ud /path/to/corpus.conllu --out out/
```

Python 3.10 or newer.
