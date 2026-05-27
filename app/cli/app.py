"""Argument parser and main entry point for the AgentGuard CLI."""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from app.cli.commands import (  # noqa: E402
    cmd_agent,
    cmd_agent_chat,
    cmd_chat,
    cmd_evaluate,
    cmd_experiment,
    cmd_ingest,
    cmd_online_eval,
    cmd_query,
    cmd_regression_gate,
    cmd_seed_dataset,
)

_COMMANDS = {
    "ingest": cmd_ingest,
    "query": cmd_query,
    "chat": cmd_chat,
    "agent": cmd_agent,
    "agent-chat": cmd_agent_chat,
    "evaluate": cmd_evaluate,
    "experiment": cmd_experiment,
    "seed-dataset": cmd_seed_dataset,
    "online-eval": cmd_online_eval,
    "regression-gate": cmd_regression_gate,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentGuard CLI")
    sub = parser.add_subparsers(dest="command")

    # ingest
    p = sub.add_parser("ingest", help="Ingest Langfuse docs into Qdrant")
    p.add_argument("--chunk-size", type=int, default=800)
    p.add_argument("--chunk-overlap", type=int, default=200)

    # query
    p = sub.add_parser("query", help="Ask a single question (RAG chain)")
    p.add_argument("question", help="The question to ask")
    p.add_argument("--model", default=None, help="LLM model name")
    p.add_argument("--session", default=None)
    p.add_argument("--user", default=None)

    # chat
    p = sub.add_parser("chat", help="Interactive RAG chat session")
    p.add_argument("--model", default=None, help="LLM model name")
    p.add_argument("--session", default=None)
    p.add_argument("--user", default=None)

    # agent
    p = sub.add_parser("agent", help="Ask a single question (ReAct agent)")
    p.add_argument("question", help="The question to ask")
    p.add_argument("--model", default=None, help="LLM model name")
    p.add_argument("--verbose", action="store_true", help="Show tool calls")

    # agent-chat
    p = sub.add_parser("agent-chat", help="Interactive agent chat with memory")
    p.add_argument("--model", default=None, help="LLM model name")
    p.add_argument("--session", default=None, help="Session ID for conversation memory")

    # evaluate
    p = sub.add_parser("evaluate", help="Run DeepEval metrics against a dataset")
    p.add_argument("--dataset", required=True, help="Langfuse dataset name")
    p.add_argument("--metrics", default=None, help="Comma-separated metric names (default: all)")
    p.add_argument("--model", default=None, help="LLM model for judge metrics")

    # experiment
    p = sub.add_parser("experiment", help="Compare multiple models against a dataset")
    p.add_argument("--dataset", required=True, help="Langfuse dataset name")
    p.add_argument("--models", required=True, help="Comma-separated model names to compare")
    p.add_argument("--metrics", default=None, help="Comma-separated DeepEval metric names (default: all)")
    p.add_argument("--judge-model", default=None, help="Model for DeepEval judge (default: deepeval_model setting)")
    p.add_argument("--run-prefix", default="experiment", help="Prefix for Langfuse run names (default: experiment)")
    p.add_argument("--limit", type=int, default=None, help="Max dataset items to evaluate (default: all)")

    # seed-dataset
    sub.add_parser("seed-dataset", help="Create the rag-eval-v1 dataset in Langfuse")

    # online-eval
    p = sub.add_parser("online-eval", help="Continuous eval worker: score new RAG traces automatically")
    p.add_argument("--once", action="store_true", help="Run one pass and exit")
    p.add_argument("--reset", action="store_true", help="Clear state and re-score all recent traces")
    p.add_argument("--interval", type=int, default=30, help="Poll interval in seconds (default: 30)")
    p.add_argument("--limit", type=int, default=50, help="Traces to fetch per poll (default: 50)")

    # regression-gate
    p = sub.add_parser("regression-gate", help="Run golden dataset through RAG and fail if metrics drop")
    p.add_argument("--dataset", default="rag-golden-set", help="Langfuse dataset name (default: rag-golden-set)")
    p.add_argument("--model", default=None, help="RAG model (default: settings.default_model)")
    p.add_argument("--metrics", default=None, help="Comma-separated metric names (default: all)")
    p.add_argument("--judge-model", default=None, help="DeepEval judge model (default: settings.deepeval_model)")
    p.add_argument("--limit", type=int, default=None, help="Max dataset items (default: all)")
    p.add_argument("--thresholds", default=None, help='JSON overrides e.g. \'{"FaithfulnessMetric":0.85}\'')
    p.add_argument("--run-prefix", default="regression-gate", help="Langfuse run name prefix (default: regression-gate)")
    p.add_argument("--no-push", action="store_true", help="Skip pushing scores to Langfuse")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    _COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
