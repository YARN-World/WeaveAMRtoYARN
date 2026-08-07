"""The rule engine handle."""

from __future__ import annotations

import signal
import threading
from contextlib import contextmanager
from pathlib import Path

from ..errors import ConversionTimeout, GrewBackendError, GrsError


@contextmanager
def timeLimit(seconds: int):
    """Abort the enclosed block after *seconds*, where the platform allows it.

    SIGALRM is main-thread and POSIX only, so this degrades to no limit rather
    than failing. The original armed the alarm inline in the batch loop, which
    also clobbered any handler the calling program had installed.
    """
    usable = (
        seconds > 0
        and hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )
    if not usable:
        yield
        return

    def onAlarm(signum, frame):
        raise ConversionTimeout(f"exceeded {seconds}s")

    previous = signal.signal(signal.SIGALRM, onAlarm)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _looksLikeBackendFailure(exc: Exception) -> bool:
    """grewpy reports a lost socket as a bare exception carrying a message."""
    text = str(exc).lower()
    return "socket" in text or "grewpy_backend" in text


class GrsSession:
    """A loaded rule set, reused across graphs.

    The rule set is loaded once and kept. The original constructed a ``GRS``
    inside the per-sentence conversion, recompiling all 43 rule packages for
    every input graph.
    """

    def __init__(self, grsPath: str | Path, strategy: str = "eval") -> None:
        self.grsPath = Path(grsPath)
        if not self.grsPath.is_file():
            raise GrsError(f"no such GRS file: {self.grsPath}")
        self.strategy = strategy
        self._grs = None
        self._validateStrategy()

    def _load(self):
        from grewpy import GRS

        try:
            return GRS(str(self.grsPath))
        except Exception as exc:
            raise GrsError(f"could not load {self.grsPath}: {exc}") from exc

    @property
    def grs(self):
        if self._grs is None:
            self._grs = self._load()
        return self._grs

    def declarations(self) -> dict:
        return self.grs.json().get("decls", {})

    def strategies(self) -> list[str]:
        """Top-level strategy names.

        A GRS declares both strategies and packages; the packages carry a
        nested structure while a strategy is just its body text.
        """
        return sorted(
            name
            for name, body in self.declarations().items()
            if isinstance(body, str)
        )

    def packages(self) -> list[str]:
        return sorted(
            name
            for name, body in self.declarations().items()
            if not isinstance(body, str)
        )

    def qualifiedStrategies(self) -> list[str]:
        """Strategies declared inside a package, addressed as ``package.name``."""
        found = []
        for name, body in self.declarations().items():
            if isinstance(body, dict):
                for inner, innerBody in body.get("decls", {}).items():
                    if isinstance(innerBody, str):
                        found.append(f"{name}.{inner}")
        return sorted(found)

    def _validateStrategy(self) -> None:
        """Fail now, with the alternatives, rather than once per graph later."""
        available = set(self.strategies()) | set(self.qualifiedStrategies())
        if self.strategy in available or self.strategy in set(self.packages()):
            return
        raise GrsError(
            f"{self.strategy!r} is not a strategy in {self.grsPath.name}. "
            f"Available: {', '.join(self.strategies())}"
        )

    def restart(self):
        """Restart the backend and reload the rule set.

        Reaches into grewpy's process-global connection state, which is the
        only way back from a lost socket.
        """
        try:
            import grewpy.network as network

            network.caml_pid = None
            network.init()
        except Exception as exc:
            raise GrewBackendError(f"could not restart the GREW backend: {exc}") from exc
        self._grs = None
        return self.grs

    def apply(self, graph: dict, *, timeoutSeconds: int = 0) -> dict:
        """Rewrite *graph* with the configured strategy."""
        from grewpy import Graph

        try:
            with timeLimit(timeoutSeconds):
                rewritten = self.grs.apply(Graph(graph), strat=self.strategy)
        except ConversionTimeout:
            raise
        except Exception as exc:
            if _looksLikeBackendFailure(exc):
                raise GrewBackendError(str(exc)) from exc
            raise

        return rewritten if isinstance(rewritten, dict) else rewritten.json_data()