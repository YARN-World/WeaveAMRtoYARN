"""A browser front end for weave_amr2yarn.

Kept beside the library rather than inside it: the library has no web
dependencies, and installing it should not pull in a web framework.

    pip install 'weave-amr2yarn[ui]'
    weave-ui
"""

from __future__ import annotations

__all__ = ["createApp", "main"]


def createApp(*args, **kwargs):
    """Build the Flask app. Imported lazily so Flask is only needed here."""
    from .app import createApp as build

    return build(*args, **kwargs)


def main(argv: list[str] | None = None) -> int:
    from .cli import main as run

    return run(argv)