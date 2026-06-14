"""Argument parser and main entry point for the AgentGuard CLI."""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from app.cli.commands import agent, benchmark, dataset, drift, evaluate, experiment, ingest, query, red_team, regression, retrieval_debug  # noqa: E402

_MODULES = [ingest, query, agent, evaluate, experiment, dataset, regression, benchmark, red_team, retrieval_debug, drift]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentGuard CLI")
    sub = parser.add_subparsers(dest="command")
    for mod in _MODULES:
        mod.register(sub)
    return parser


def main() -> None:
    from app.core.logging import configure_logging
    from app.core.telemetry import init_telemetry

    configure_logging()
    init_telemetry()
    parser = _build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
