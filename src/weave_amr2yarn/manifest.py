"""A record of what a run did, written beside its output.

Output directories outlive the command that made them. Without a manifest, a
directory of YARN files says nothing about which rules produced it, which
anchors were used, or when — which is exactly what you need months later when
two runs disagree.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_NAME = "manifest.json"


def timestamp() -> str:
    """Now, in UTC, to the millisecond."""
    moment = datetime.now(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def ruleSetDigest(grsPath: str | Path) -> str:
    """A digest over the whole rule directory, not just the entry file.

    ``main.grs`` includes 43 siblings and the rules load lexicons, so hashing
    the entry alone would call two different rule sets identical.
    """
    directory = Path(grsPath).parent
    digest = hashlib.sha256()
    # rglob, not glob: the rules live in subdirectories, and a digest that
    # silently covered only the top level would identify the wrong thing.
    files = sorted(directory.rglob("*.grs")) + sorted(directory.rglob("*.lex"))
    for path in files:
        # The path, so moving a file between folders changes the digest.
        digest.update(str(path.relative_to(directory)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


@dataclass
class RunManifest:
    """What was run, with what, and how it went."""

    weaveVersion: str
    startedAt: str
    finishedAt: str | None = None
    durationSeconds: float | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    rules: dict[str, Any] = field(default_factory=dict)
    providers: dict[str, Any] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    failures: list[dict[str, str]] = field(default_factory=list)

    def asDict(self) -> dict:
        return {
            "weave": self.weaveVersion,
            "startedAt": self.startedAt,
            "finishedAt": self.finishedAt,
            "durationSeconds": self.durationSeconds,
            "inputs": self.inputs,
            "rules": self.rules,
            "providers": self.providers,
            "counts": self.counts,
            "failures": self.failures,
        }

    def write(self, outDir: str | Path) -> Path:
        path = Path(outDir) / MANIFEST_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.asDict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return path