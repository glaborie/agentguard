"""Argument parser and main entry point for the AgentGuard CLI."""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from app.cli.commands import agent, dataset, evaluate, experiment, ingest, query, regression  # noqa: E402

_MODULES = [ingest, query, agent, evaluate, experiment, dataset, regression]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentGuard CLI")
    sub = parser.add_subparsers(dest="command")
    for mod in _MODULES:
        mod.register(sub)
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
