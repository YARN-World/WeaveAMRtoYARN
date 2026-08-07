"""leamr_compat — run against a stock LEAMR checkout, and say so when you cannot.

The LEAMR aligner is not pip-installable: it is a GitHub checkout (which does
carry the ~660 MB of trained pickles) plus a *second* repository that has to be
cloned inside it. On top of that, the copy this project developed against
carries local edits. A caller who clones LEAMR fresh therefore hits three
different classes of problem, and they need different answers:

  missing pieces        amr_utils (a separate repo), or a partial clone that
                        omitted the pickles → cannot run; say what to fetch
  robustness gaps       a crash upstream has but our copy patched → shim it here at
                        runtime, so nobody has to edit their checkout
  behavioural edits     rule changes that alter which tokens get aligned → cannot be
                        shimmed honestly; report that alignments will differ and
                        ship the diff for anyone who wants to reproduce our numbers

`doctor()` reports all three. `installRuntimeShims()` fixes only the second.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

AMR_UTILS_REPO = "https://github.com/ablodge/amr-utils"
LEAMR_REPO = "https://github.com/ablodge/leamr"
MODEL_FILES = ("subgraph_params.pkl", "relation_params.pkl", "reentrancy_params.pkl")

# Marker of the alignment-rule edits this project developed against. Present in a
# patched checkout, absent from a stock one; see leamr_local.patch.
BEHAVIOUR_MARKER = ("rstrip('.,;:!?')", "rule_based/subgraph_rules.py")


@dataclass
class Finding:
    level: str          # "error" | "warning" | "ok"
    what: str
    detail: str = ""

    def __str__(self) -> str:
        mark = {"error": "✗", "warning": "!", "ok": "✓"}[self.level]
        return f"{mark} {self.what}" + (f"\n    {self.detail}" if self.detail else "")


def modelPrefixes(leamrDir: Path) -> list[str]:
    """Trained model sets present, by their shared filename prefix."""
    return sorted({p.name.rsplit(".", 2)[0]
                   for p in leamrDir.glob("*.subgraph_params.pkl")})


def doctor(leamrDir: str | Path) -> list[Finding]:
    """Everything that decides whether this checkout can align a sentence."""
    leamr = Path(leamrDir).expanduser()
    out: list[Finding] = []

    if not leamr.exists():
        return [Finding("error", f"no LEAMR checkout at {leamr}",
                        f"git clone {LEAMR_REPO}")]
    out.append(Finding("ok", f"LEAMR checkout at {leamr}"))

    if not (leamr / "models" / "subgraph_model.py").exists():
        out.append(Finding("error", "the checkout has no models/ directory",
                           "a sparse or partial clone must include models/, "
                           "rule_based/ and evaluate/"))

    # amr_utils is a *second* repository, cloned inside the first one
    if (leamr / "amr_utils" / "amr_utils" / "amr_readers.py").exists():
        out.append(Finding("ok", "amr_utils present"))
    else:
        out.append(Finding(
            "error", "amr_utils is missing",
            f"it is a separate repository, not part of LEAMR:\n"
            f"    cd {leamr} && git clone {AMR_UTILS_REPO} amr_utils"))

    prefixes = modelPrefixes(leamr)
    if prefixes:
        complete = [p for p in prefixes
                    if all((leamr / f"{p}.{f}").exists() for f in MODEL_FILES)]
        if complete:
            out.append(Finding("ok", f"trained models: {', '.join(complete)}"))
        else:
            out.append(Finding("error", f"model set '{prefixes[0]}' is incomplete",
                               f"needs all of: {', '.join(MODEL_FILES)}"))
    else:
        out.append(Finding(
            "error", "no trained models (*_params.pkl)",
            "they ship in the LEAMR repository itself (~660 MB), so this is "
            "usually a partial clone: re-clone without --filter, or copy the "
            "pickles in from another checkout"))

    marker, relative = BEHAVIOUR_MARKER
    rules = leamr / relative
    if rules.exists() and marker not in rules.read_text(encoding="utf-8", errors="ignore"):
        out.append(Finding(
            "warning", "stock alignment rules — copular -91 frames WILL differ",
            "this project's checkout patches "
            f"{relative} with rules that anchor 'be-located-at-91' and "
            "'be-from-91' to the copula (is/are/was); stock LEAMR anchors them "
            "to the locative preposition or adverb instead (at/from/on/here). "
            "Measured: 9 of 19 such frames differ, while 25/25 sentences "
            "*without* them are identical. Anything that depends on copular "
            "anchoring — tense placement in particular — needs "
            "align2anchor/leamr_local.patch applied:\n"
            "    cd <leamr> && git apply <this package>/leamr_local.patch"))
    elif rules.exists():
        out.append(Finding("ok", "alignment rules carry this project's edits"))

    for module, why in (("stanza", "sentence annotation"), ("penman", "AMR parsing")):
        try:
            __import__(module)
            out.append(Finding("ok", f"{module} importable"))
        except ImportError:
            out.append(Finding("error", f"{module} is not installed ({why})",
                               f"pip install {module}"))
    return out


def usable(leamrDir: str | Path) -> bool:
    return not any(f.level == "error" for f in doctor(leamrDir))


def report(leamrDir: str | Path) -> str:
    return "\n".join(str(f) for f in doctor(leamrDir))


# ---------------------------------------------------------------------------
# runtime shims
# ---------------------------------------------------------------------------

_shimmed = False


def installRuntimeShims() -> list[str]:
    """Patch upstream crashes in memory. Idempotent; returns what was applied.

    Only defects that make LEAMR *crash* are shimmed here — never anything that
    changes which tokens get aligned, because a silent behavioural difference
    between checkouts is exactly what makes results irreproducible.

    Must be called after LEAMR is importable (i.e. after LeamrResources has put
    it on sys.path).
    """
    global _shimmed
    if _shimmed:
        return []
    applied: list[str] = []

    # Relation_Model.coverage divides by the number of external edges. A single
    # sentence whose every edge is internal to one aligned subgraph has none, so
    # aligning one short sentence raises ZeroDivisionError on a stock checkout.
    try:
        from models.relation_model import Relation_Model

        original = Relation_Model.coverage

        def coverage(self, amrs, alignments):
            try:
                return original(self, amrs, alignments)
            except ZeroDivisionError:
                return "100.00%"      # no external edges: vacuously covered

        if getattr(original, "__name__", "") != "coverage_shimmed":
            coverage.__name__ = "coverage_shimmed"
            Relation_Model.coverage = coverage
            applied.append("Relation_Model.coverage: survive zero external edges")
    except Exception:                 # noqa: BLE001 — a shim must never be fatal
        pass

    _shimmed = True
    return applied
