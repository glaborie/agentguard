"""CLI command: benchmark — run the NorthstarCRM benchmark suite."""

from argparse import Namespace


def register(sub) -> None:
    p = sub.add_parser(
        "benchmark",
        help="Run the NorthstarCRM benchmark against the RAG pipeline",
    )
    p.add_argument(
        "--mode",
        choices=["full", "no-guardrails", "direct"],
        default="full",
        help="Run mode (default: full). Ignored when --compare is set.",
    )
    p.add_argument(
        "--compare",
        action="store_true",
        help="Run all three modes (full, no-guardrails, direct) and show side-by-side results",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of benchmark items (useful for quick smoke-tests)",
    )
    p.add_argument(
        "--no-llm-judge",
        action="store_true",
        help="Skip the LLM-as-judge metrics (policy violation, helpfulness) — faster",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Override the LLM model used for generation",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the summary table, not per-question details",
    )
    p.set_defaults(func=cmd_benchmark)


def cmd_benchmark(args: Namespace) -> None:
    from app.eval.benchmark import (
        load_benchmark_items,
        load_retrieval_labels,
        print_results,
        run_benchmark,
    )

    modes = ["full", "no-guardrails", "direct"] if args.compare else [args.mode]

    print(f"Loading benchmark items...")
    items = load_benchmark_items()
    labels = load_retrieval_labels()
    n = min(len(items), args.limit) if args.limit else len(items)
    print(f"  {n} items  |  modes: {', '.join(modes)}")

    print("Running benchmark...")
    results = run_benchmark(
        items=items,
        retrieval_labels=labels,
        modes=modes,
        model=args.model,
        llm_judge=not args.no_llm_judge,
        limit=args.limit,
        verbose=not args.quiet,
    )

    print_results(results, modes=modes, show_per_question=not args.quiet)
