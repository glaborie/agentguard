"""Build a Langfuse dataset from positively rated RAG traces.

Queries Langfuse for traces that received a thumbs-up (user_feedback=1.0),
then upserts them as items in a named dataset.  The dataset grows
automatically as users rate responses, giving you a gold set for
experiments and regression testing.

Dataset item format:
  input           {"question": "<user question>"}
  expected_output {"answer": "<RAG response>"}
  source_trace_id  linked back to the original Langfuse trace

Usage:
    python -m scripts.build_dataset                          # append new items
    python -m scripts.build_dataset --dataset my-dataset     # custom name
    python -m scripts.build_dataset --reset                  # rebuild from scratch
    python -m scripts.build_dataset --dry-run                # print, no writes

State is persisted in .build_dataset_state.json (set of already-added trace IDs).
"""

import argparse
import json
import logging
from pathlib import Path

import httpx

from dotenv import load_dotenv

load_dotenv()

from langfuse.api.commons.types.score_data_type import ScoreDataType

from app.core.config import settings
from app.core.tracing import get_langfuse_client
from scripts.utils import SCORE_PAGE_SIZE, load_state, save_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

STATE_FILE = Path(".build_dataset_state.json")
DEFAULT_DATASET = "rag-golden-set"


def _load_seen() -> set[str]:
    return load_state(STATE_FILE)


def _save_seen(seen: set[str]) -> None:
    save_state(STATE_FILE, seen)


def _ensure_dataset(lf, name: str) -> None:
    try:
        lf.api.datasets.get(name)
    except Exception:
        lf.create_dataset(
            name=name,
            description=(
                "Gold set built automatically from positively rated Open WebUI responses. "
                "Use for experiments and regression testing."
            ),
        )
        logger.info("Created dataset '%s'", name)


def _extract_question(trace) -> str | None:
    inp = trace.input
    if not inp:
        return None
    if isinstance(inp, str):
        return inp.strip()
    if isinstance(inp, dict):
        return (inp.get("question") or inp.get("input") or inp.get("query") or "").strip() or None
    return str(inp).strip() or None


def _extract_answer(trace) -> str | None:
    out = trace.output
    if not out:
        return None
    if isinstance(out, str):
        return out.strip()
    if isinstance(out, dict):
        return (out.get("output") or out.get("answer") or out.get("text") or "").strip() or None
    return str(out).strip() or None


def run_once(
    dataset_name: str = DEFAULT_DATASET,
    dry_run: bool = False,
    reset: bool = False,
) -> int:
    """Fetch positive-feedback traces and add new ones to the dataset.

    Returns the number of items added this pass.
    """
    lf = get_langfuse_client()

    # Fetch all positive user_feedback scores (paginate if needed)
    positive_trace_ids: set[str] = set()
    page = 1
    while True:
        try:
            resp = lf.api.scores.get_many(
                name="user_feedback",
                value=1.0,
                data_type=ScoreDataType.BOOLEAN,
                limit=SCORE_PAGE_SIZE,
                page=page,
            )
            scores = resp.data or []
        except httpx.HTTPStatusError as exc:
            logger.error("Langfuse returned HTTP %s fetching scores (page %d): %s", exc.response.status_code, page, exc)
            break
        except Exception as exc:
            logger.error("Unexpected error fetching scores (page %d): %s", page, exc)
            break

        for s in scores:
            if s.trace_id:
                positive_trace_ids.add(s.trace_id)

        if len(scores) < SCORE_PAGE_SIZE:
            break
        page += 1

    if not positive_trace_ids:
        logger.info("No positively rated traces found.")
        return 0

    logger.info("Found %d positively rated trace(s).", len(positive_trace_ids))

    seen = set() if reset else _load_seen()
    new_ids = positive_trace_ids - seen

    if not new_ids:
        logger.info("No new traces to add to dataset '%s'.", dataset_name)
        return 0

    if not dry_run:
        _ensure_dataset(lf, dataset_name)

    added = 0
    for trace_id in new_ids:
        try:
            trace = lf.api.trace.get(trace_id)
        except Exception as exc:
            logger.warning("Could not fetch trace %s: %s", trace_id[:12], exc)
            seen.add(trace_id)
            continue

        question = _extract_question(trace)
        answer = _extract_answer(trace)

        if not question or not answer:
            logger.warning(
                "Trace %s has no extractable input/output — skipping.", trace_id[:12]
            )
            seen.add(trace_id)
            continue

        if dry_run:
            logger.info(
                "[dry-run] would add trace=%s  q=%s...", trace_id[:12], question[:60]
            )
            added += 1
            seen.add(trace_id)
            continue

        try:
            lf.api.dataset_items.create(
                dataset_name=dataset_name,
                input={"question": question},
                expected_output={"answer": answer},
                source_trace_id=trace_id,
            )
            logger.info(
                "Added trace=%s  q=%s...", trace_id[:12], question[:60]
            )
            added += 1
        except Exception as exc:
            logger.error("Failed to add trace %s: %s", trace_id[:12], exc)

        seen.add(trace_id)

    if not dry_run:
        _save_seen(seen)
    logger.info("Done. %d item(s) added to dataset '%s' this pass.", added, dataset_name)
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Langfuse dataset from positive feedback")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, metavar="NAME",
                        help=f"Dataset name (default: {DEFAULT_DATASET})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be added without writing")
    parser.add_argument("--reset", action="store_true",
                        help="Ignore seen cache, re-add all positive traces")
    args = parser.parse_args()

    run_once(dataset_name=args.dataset, dry_run=args.dry_run, reset=args.reset)


if __name__ == "__main__":
    main()
