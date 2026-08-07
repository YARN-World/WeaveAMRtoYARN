"""Running several corpora from one config file.

A sweep is usually the same conversion over a handful of corpora that differ
only in their inputs. Writing that as a table beats writing it as a shell loop:
the table is the record of what was run.

    [defaults]
    strat = "eval"

    [corpus.pud]
    amr = "input/pud_100_gold.txt"
    ud = "input/en_pud-ud-test.conllu"
    anchors = "input/anchor_dict_gold_improved.json"

    [corpus.fracas]
    amr = "input/fracas_gold_subset.amr.txt"
    anchorer = "leamr"
    layout = "grouped"

Paths are taken relative to the config file, not to the working directory, so
a config travels with its data.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from .errors import WeaveError

#: Keys naming a file, resolved relative to the config file.
_PATH_KEYS = ("amr", "ud", "anchors", "grs", "leamrDir")


def _loadToml(path: Path) -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError as exc:
            raise WeaveError(
                "reading a config file needs tomllib (Python 3.11+) or tomli:\n"
                "  pip install tomli"
            ) from exc
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except OSError as exc:
        raise WeaveError(f"could not read {path}: {exc}") from exc
    except Exception as exc:
        raise WeaveError(f"{path} is not valid TOML: {exc}") from exc


@dataclass
class RunSpec:
    """One corpus to convert, with everything needed to do it."""

    name: str
    amr: str

    ud: str | None = None
    anchors: str | None = None
    anchorer: str = "levenshtein"
    grs: str | None = None
    strat: str = "eval"
    keySnt: str = "snt"
    lang: str = "en"
    layout: str = "flat"
    timeout: int = 30
    anchorThreshold: float = 0.7
    penmanDereify: bool = False
    strictUd: bool = False
    grewOnly: bool = False
    stages: str = "filter,repair"
    leamrDir: str | None = None
    spanResolution: str = "first"
    out: str | None = None

    def outputDir(self, root: Path) -> Path:
        """Where this corpus writes. Explicit ``out`` wins over the root."""
        return Path(self.out) if self.out else root / self.name


# TOML is written in the shell's idiom, so accept snake_case for the fields
# whose names are camelCase in Python.
_ALIASES = {
    "key_snt": "keySnt",
    "anchor_threshold": "anchorThreshold",
    "penman_dereify": "penmanDereify",
    "strict_ud": "strictUd",
    "grew_only": "grewOnly",
    "leamr_dir": "leamrDir",
    "span_resolution": "spanResolution",
}

_KNOWN = {item.name for item in fields(RunSpec)} - {"name"}


def _normalise(settings: dict[str, Any], where: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in settings.items():
        key = _ALIASES.get(key, key)
        if key not in _KNOWN:
            raise WeaveError(
                f"{where}: unknown setting {key!r}. "
                f"Known: {', '.join(sorted(_KNOWN))}"
            )
        result[key] = value
    return result


@dataclass
class BatchPlan:
    """Everything a config file asks for."""

    specs: list[RunSpec] = field(default_factory=list)
    outRoot: Path = Path("runs")
    source: Path | None = None

    def select(self, names: list[str] | None) -> list[RunSpec]:
        if not names:
            return self.specs
        known = {spec.name: spec for spec in self.specs}
        missing = [name for name in names if name not in known]
        if missing:
            raise WeaveError(
                f"no corpus named {', '.join(missing)} in {self.source}. "
                f"Available: {', '.join(known)}"
            )
        return [known[name] for name in names]


def loadPlan(path: str | Path) -> BatchPlan:
    """Read a config file into a plan, with paths already resolved."""
    path = Path(path)
    document = _loadToml(path)
    base = path.parent

    corpora = document.get("corpus")
    if not corpora:
        raise WeaveError(
            f"{path} defines no corpora. Each needs a [corpus.<name>] section."
        )

    defaults = _normalise(document.get("defaults", {}), f"{path} [defaults]")

    specs = []
    for name, settings in corpora.items():
        if not isinstance(settings, dict):
            raise WeaveError(f"{path}: [corpus.{name}] must be a table")
        merged = {**defaults, **_normalise(settings, f"{path} [corpus.{name}]")}
        if "amr" not in merged:
            raise WeaveError(f"{path}: [corpus.{name}] has no 'amr'")

        # Resolve paths against the config file so it can be moved with its data.
        for key in _PATH_KEYS:
            if merged.get(key):
                merged[key] = str((base / merged[key]).resolve())

        specs.append(RunSpec(name=name, **merged))

    outRoot = document.get("out_root") or document.get("outRoot") or "runs"
    return BatchPlan(specs=specs, outRoot=(base / outRoot).resolve(), source=path)