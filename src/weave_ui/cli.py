"""Starting the browser app."""

from __future__ import annotations

import argparse
import sys

DEFAULT_PORT = 5010


def buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weave-ui", description="Browser front end for weave_amr2yarn"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--grs", help="GRS entry file (default: the bundled rules)")
    parser.add_argument("--strat", default="eval", help="strategy (default: eval)")
    parser.add_argument("--debug", action="store_true", help="Flask debug mode")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = buildParser().parse_args(argv)
    try:
        from .app import createApp
    except ImportError as exc:
        print(
            f"weave-ui: {exc}\nThe browser app needs Flask:\n"
            "  pip install 'weave-amr2yarn[ui]'",
            file=sys.stderr,
        )
        return 1

    from weave_amr2yarn.errors import WeaveError

    try:
        app = createApp(grsPath=args.grs, strategy=args.strat)
    except WeaveError as exc:
        print(f"weave-ui: {exc}", file=sys.stderr)
        return 1

    print(f"weave-ui on http://{args.host}:{args.port}", file=sys.stderr)
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())