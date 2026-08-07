# Installing

```bash
pip install /path/to/WeaveAMRtoYARN
weave doctor
```

`weave doctor` reports what is present and what is missing, with the command to
fix each one.

## grewpy

The rewriting is done by [grewpy](https://grew.fr/usage/python/). It needs more
than `pip install` — the engine it drives is a separate program — so follow the
official guide rather than installing it from here. `weave doctor` tells you
whether it worked.

POSIX only; on Windows, use WSL.

## Stanza (optional)

Only needed when UD is not supplied as CoNLL-U and has to be parsed from the
sentence. It is an extra so the common case does not pull in torch:

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
