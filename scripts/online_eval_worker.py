"""Online evaluation worker.

Polls Langfuse for new RAG traces (RunnableSequence) and runs the
code-based evaluators on each one automatically, pushing scores back.

This demonstrates the "continuous eval" pattern: every production query
gets quality scores without manual batch runs.

Usage:
    python -m scripts.online_eval_worker            # poll every 30 s
    python -m scripts.online_eval_worker --once     # single pass, exit
    python -m scripts.online_eval_worker --interval 60 --limit 100
    python -m scripts.online_eval_worker --reset    # clear state, re-score all
"""

import argparse
import json
import logging
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

from app.core.config import settings
from app.utils import extract_trace_output, truncate
from scripts.utils import HTTP_TIMEOUT, langfuse_basic_auth, load_state, save_state
from app.eval.evaluators import (
    contains_no_hallucination_markers,
    has_source_citation,
    is_within_length,
)
from app.core.tracing import get_langfuse_client
from scripts.seed_score_configs import seed as seed_score_configs

_AUTH = langfuse_basic_auth()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

STATE_FILE = Path(".online_eval_state.json")
RAG_TRACE_NAME = "RunnableSequence"

# Open WebUI auto-generates system calls for titles, tags, follow-up suggestions.
# These go through the RAG chain but are not real user queries — skip them.
_OPENWEBUI_SYSTEM_PREFIXES = ("### Task:", "### Rules:")


# Score names pushed to Langfuse — prefixed online_ to distinguish from batch eval
EVALUATORS = {
    "online_has_citation": has_source_citation,
    "online_within_length": is_within_length,
    "online_no_hallucination_markers": contains_no_hallucination_markers,
}





def _score_trace(trace, config_ids: dict[str, str]) -> dict[str, float]:
    """Evaluate a trace and POST scores directly to the Langfuse ingestion API."""
    output = extract_trace_output(trace)
    if not output:
        return {}

    scores: dict[str, float] = {}
    for name, fn in EVALUATORS.items():
        value = 1.0 if fn(output) else 0.0
        payload: dict = {
            "traceId": trace.id,
            "name": name,
            "value": value,
            "dataType": "BOOLEAN",
        }
        if config_ids.get(name):
            payload["configId"] = config_ids[name]
        resp = httpx.post(
            f"{settings.langfuse_base_url}/api/public/scores",
            json=payload,
            headers={"Authorization": f"Basic {_AUTH}", "Content-Type": "application/json"},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        scores[name] = value

    return scores


def run_once(limit: int = 50, config_ids: dict[str, str] | None = None) -> int:
    """Fetch recent traces, evaluate any that haven't been scored yet.

    Returns the number of traces evaluated this pass.
    """
    seen = load_state(STATE_FILE)

    response = get_langfuse_client().api.trace.list(limit=limit)
    traces = response.data or []

    def _is_user_query(t) -> bool:
        if t.name != RAG_TRACE_NAME:
            return False
        input_str = str(t.input or "")
        return not any(input_str.startswith(p) for p in _OPENWEBUI_SYSTEM_PREFIXES)

    new_traces = [t for t in traces if t.id not in seen and _is_user_query(t)]

    if not new_traces:
        logger.info("No new RAG traces to evaluate.")
        return 0

    logger.info("Evaluating %d new trace(s)...", len(new_traces))
    evaluated = 0

    for trace in new_traces:
        try:
            scores = _score_trace(trace, config_ids or {})
            if scores:
                passed = sum(1 for v in scores.values() if v == 1.0)
                input_preview = truncate(str(trace.input or ""), 70)
                logger.info(
                    "[%s] %d/%d checks passed | %s",
                    trace.id[:12],
                    passed,
                    len(scores),
                    input_preview,
                )
                evaluated += 1
            else:
                logger.warning("[%s] No output to evaluate, skipping.", trace.id[:12])
        except Exception as exc:
            logger.error("[%s] Evaluation failed: %s", trace.id[:12], exc)
        finally:
            seen.add(trace.id)

    save_state(STATE_FILE, seen)
    logger.info("Done. %d trace(s) evaluated this pass.", evaluated)
    return evaluated


def main() -> None:
    parser = argparse.ArgumentParser(description="Online evaluation worker for AgentGuard")
    parser.add_argument("--once", action="store_true", help="Run one pass and exit")
    parser.add_argument("--interval", type=int, default=30, metavar="SECONDS",
                        help="Poll interval in seconds (default: 30)")
    parser.add_argument("--limit", type=int, default=50, metavar="N",
                        help="Traces to fetch per poll (default: 50)")
    parser.add_argument("--reset", action="store_true",
                        help="Clear seen-trace state so all recent traces are re-scored")
    args = parser.parse_args()

    if args.reset:
        STATE_FILE.unlink(missing_ok=True)
        logger.info("State cleared — all recent traces will be re-scored.")

    # Ensure score configs exist and get name → config_id mapping.
    config_ids = seed_score_configs()

    if args.once:
        run_once(limit=args.limit, config_ids=config_ids)
        return

    logger.info(
        "Online eval worker started (interval: %ds, limit: %d per poll).",
        args.interval,
        args.limit,
    )
    while True:
        try:
            run_once(limit=args.limit, config_ids=config_ids)
        except Exception as exc:
            logger.error("Poll error: %s", exc)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
