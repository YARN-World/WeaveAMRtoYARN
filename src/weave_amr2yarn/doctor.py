"""Environment checks.

Two of the things this library needs are not a pip install: grewpy drives a
separate engine, and Stanza's models are downloaded on their own. Both fail at
a distance, so it is worth being able to ask.
"""

from __future__ import annotations

import shutil

import sys
from dataclasses import dataclass

# The version grewpy itself requires of its backend.
MINIMUM_BACKEND = "0.6.0"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    hint: str = ""
    required: bool = True

    def line(self) -> str:
        mark = "ok  " if self.ok else ("MISS" if self.required else "----")
        text = f"  {mark}  {self.name:<16} {self.detail}"
        if not self.ok and self.hint:
            text += f"\n{'':>24}{self.hint}"
        return text


def _checkPython() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    ok = sys.version_info >= (3, 10)
    return Check("python", ok, version, "needs 3.10 or newer")


def _backendVersion() -> str | None:
    """Ask the running backend its version, the way grewpy does.

    There is no ``--version`` flag; the version comes back over the socket, so
    this connects rather than shelling out.
    """
    try:
        import grewpy  # noqa: F401  (importing starts the backend)
        from grewpy.network import send_and_receive

        return str(send_and_receive({"command": "get_version"}))
    except Exception:
        return None


def _checkBackend() -> Check:
    path = shutil.which("grewpy_backend")
    hint = "see https://grew.fr/usage/python/ — it is not a pip install"
    if not path:
        return Check("grewpy_backend", False, "not on PATH", hint)

    version = _backendVersion()
    if version is None:
        return Check(
            "grewpy_backend", False, f"found at {path} but would not respond", hint
        )

    number = version.split("-")[0]
    if _isOlder(number, MINIMUM_BACKEND):
        return Check(
            "grewpy_backend",
            False,
            f"{version} is older than {MINIMUM_BACKEND}",
            "see https://grew.fr/usage/python/",
        )
    return Check("grewpy_backend", True, f"{version}  {path}")


def _isOlder(found: str, minimum: str) -> bool:
    def parts(value: str) -> list[int]:
        return [int(piece) if piece.isdigit() else 0 for piece in value.split(".")]

    left, right = parts(found), parts(minimum)
    left += [0] * (len(right) - len(left))
    right += [0] * (len(left) - len(right))
    return left < right


def _checkImport(name: str, label: str, hint: str, required: bool = True) -> Check:
    try:
        module = __import__(name)
    except Exception as exc:
        return Check(label, False, str(exc).splitlines()[0], hint, required)
    return Check(label, True, getattr(module, "__version__", "installed"))


def _checkRules() -> Check:
    from .resources import bundledGrsDir

    try:
        directory = bundledGrsDir()
    except Exception as exc:
        return Check("rules", False, str(exc))
    rules = len(list(directory.rglob("*.grs")))
    lexicons = len(list(directory.rglob("*.lex")))
    return Check("rules", True, f"{rules} .grs, {lexicons} .lex  {directory}")


def _checkLeamr() -> Check:
    """LEAMR is optional and external: too large to bundle, unlike align2anchor."""
    from .providers.align2anchor import LEAMR_VARIABLE, resolveLeamrDir

    try:
        directory = resolveLeamrDir()
    except Exception:
        return Check(
            "LEAMR checkout",
            False,
            "not found",
            "only needed for --anchorer leamr:\n"
            f"{'':>24}  pass --leamr-dir, or set {LEAMR_VARIABLE}",
            required=False,
        )
    models = directory / "models"
    detail = str(directory)
    if not models.is_dir():
        detail += "  (no models/ — the aligner will not run)"
    return Check("LEAMR checkout", True, detail, required=False)


def _checkStanzaModels(language: str = "en") -> Check:
    from pathlib import Path

    hint = (
        "only needed when UD is not supplied as CoNLL-U:\n"
        f"{'':>24}  python -c \"import stanza; stanza.download('{language}')\""
    )
    try:
        import stanza  # noqa: F401
    except ImportError:
        return Check(
            f"stanza models ({language})",
            False,
            "stanza not installed",
            hint,
            required=False,
        )
    directory = Path.home() / "stanza_resources" / language
    if not directory.is_dir():
        return Check(
            f"stanza models ({language})", False, "not downloaded", hint, required=False
        )
    return Check(f"stanza models ({language})", True, str(directory), required=False)


def _rendererChecks() -> list[Check]:
    """One line per renderer, naming what each is missing.

    Drawing is optional throughout, so these never make a run "not ready".
    """
    from .render import rendererFor, rendererNames

    checks = []
    for name in rendererNames():
        renderer = rendererFor(name)
        if renderer.available():
            checks.append(Check(f"render {name}", True, "ok", required=False))
            continue
        missing = renderer.missing()
        hints = "; ".join(item.hint for item in missing if item.hint)
        checks.append(
            Check(
                f"render {name}",
                False,
                "missing " + ", ".join(item.name for item in missing),
                hints,
                required=False,
            )
        )
    return checks


def runChecks(language: str = "en") -> list[Check]:
    return [
        _checkPython(),
        _checkRules(),
        _checkBackend(),
        _checkImport("grewpy", "grewpy", "pip install grewpy"),
        _checkImport("penman", "penman", "pip install penman"),
        _checkImport("Levenshtein", "Levenshtein", "pip install python-Levenshtein"),
        _checkImport(
            "yarn_utils",
            "yarn_utils",
            "pip install 'yarn_utils @ git+https://gitlab.inria.fr/semagramme/"
            "yarn/yarn_utils@fb6f6f88134f89e45866ff2eacd4880ec1f2c764"
            "#subdirectory=utils'",
        ),
        _checkImport(
            "stanza", "stanza", "pip install 'weave-amr2yarn[stanza]'", required=False
        ),
        _checkStanzaModels(language),
        _checkLeamr(),
        *_rendererChecks(),
    ]


def report(language: str = "en") -> tuple[str, bool]:
    """Return the printable report and whether everything required is present."""
    checks = runChecks(language)
    healthy = all(check.ok for check in checks if check.required)

    lines = ["weave doctor", ""]
    lines.extend(check.line() for check in checks)
    lines.append("")
    if healthy:
        optional = [c for c in checks if not c.required and not c.ok]
        lines.append(
            "Ready to convert."
            + (
                f" ({len(optional)} optional item(s) missing — only needed to parse "
                "UD from raw text.)"
                if optional
                else ""
            )
        )
    else:
        lines.append("Not ready — see the hints above.")
    return "\n".join(lines), healthy