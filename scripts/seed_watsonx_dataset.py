"""Seed Langfuse dataset 'watsonx-qa' from ibm-research/watsonxDocsQA.

Each item: input={"question": ...}, expected_output=answer, metadata={"context": ...}

Usage:
    python -m scripts.seed_watsonx_dataset                    # seed from HF (default: train split)
    python -m scripts.seed_watsonx_dataset --from-file        # seed from data/watsonx_qa_pairs.jsonl
    python -m scripts.seed_watsonx_dataset --limit 100        # cap item count
    python -m scripts.seed_watsonx_dataset --dry-run          # print without writing
    python -m scripts.seed_watsonx_dataset --reset            # recreate dataset from scratch
"""

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

DATASET_REPO  = "ibm-research/watsonxDocsQA"
DATASET_NAME  = "watsonx-qa"
QA_PAIRS_FILE = Path("data/watsonx_qa_pairs.jsonl")

_CTX_COLS = ("context", "contexts", "passage", "document", "doc_text", "text")
_Q_COLS   = ("question", "query", "user_input")
_ANS_COLS = ("correct_answer", "answer", "ground_truth", "reference", "expected_answer")


def _detect(cols: list[str], candidates: tuple) -> str | None:
    return next((c for c in candidates if c in cols), None)


def _pairs_from_hf(split: str = "train") -> list[dict]:
    """Load QA pairs from watsonxDocsQA — recommend using --from-file after load_watsonx_corpus."""
    from datasets import load_dataset  # type: ignore

    qa_ds     = load_dataset(DATASET_REPO, "question_answers")
    corpus_ds = load_dataset(DATASET_REPO, "corpus")

    rows = qa_ds[split].to_list() if split != "all" else [r for s in qa_ds.values() for r in s.to_list()]
    if not rows:
        return []

    cols   = list(rows[0].keys())
    q_col  = _detect(cols, _Q_COLS)
    a_col  = _detect(cols, _ANS_COLS)

    # Build doc_id → md_document lookup for context resolution
    ctx_by_id: dict[str, str] = {}
    for s in corpus_ds.values():
        for row in s.to_list():
            did = str(row.get("doc_id", ""))
            txt = str(row.get("md_document", row.get("document", ""))).strip()
            if did and txt:
                ctx_by_id[did] = txt

    pairs = []
    for row in rows:
        q   = str(row.get(q_col or "question",       "")).strip()
        ans = str(row.get(a_col or "correct_answer",  "")).strip()
        if not q or not ans:
            continue
        raw_ids = row.get("correct_answer_document_ids", [])
        ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
        ctx = next((ctx_by_id[str(d)] for d in ids if str(d) in ctx_by_id), "")
        if not ctx:
            ctx = str(row.get("ground_truths_contexts", ""))
        pairs.append({"question": q, "answer": ans, "context": ctx})
    return pairs


def _pairs_from_file() -> list[dict]:
    if not QA_PAIRS_FILE.exists():
        raise FileNotFoundError(
            f"{QA_PAIRS_FILE} not found — run `python -m scripts.load_watsonx_corpus` first"
        )
    pairs = []
    for line in QA_PAIRS_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            pairs.append(json.loads(line))
    return pairs


def seed(pairs: list[dict], dry_run: bool, reset: bool) -> None:
    from app.tracing import get_langfuse_client

    client = get_langfuse_client()

    if reset:
        try:
            client.api.datasets.delete(dataset_name=DATASET_NAME)
            log.info("Deleted existing dataset %r", DATASET_NAME)
        except Exception:
            pass

    try:
        client.create_dataset(name=DATASET_NAME, description="ibm-research/watsonxDocsQA QA pairs")
        log.info("Created dataset %r", DATASET_NAME)
    except Exception:
        log.info("Dataset %r already exists — upserting items", DATASET_NAME)

    log.info("Seeding %d items …", len(pairs))
    if dry_run:
        for i, p in enumerate(pairs[:3]):
            log.info("  [%d] q=%s …", i, p["question"][:80])
        log.info("  … dry-run, nothing written")
        return

    for i, pair in enumerate(pairs):
        client.create_dataset_item(
            dataset_name=DATASET_NAME,
            input={"question": pair["question"]},
            expected_output=pair["answer"],
            metadata={"context": pair["context"]} if pair.get("context") else {},
        )
        if (i + 1) % 50 == 0:
            log.info("  %d / %d", i + 1, len(pairs))

    client.flush()
    log.info("Done — %d items in dataset %r", len(pairs), DATASET_NAME)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Langfuse watsonx-qa dataset")
    parser.add_argument("--from-file", action="store_true", help="Load from data/watsonx_qa_pairs.jsonl")
    parser.add_argument("--split", default="train", help="HF split to use (default: train)")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of items")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate dataset")
    args = parser.parse_args()

    pairs = _pairs_from_file() if args.from_file else _pairs_from_hf(args.split)
    if args.limit:
        pairs = pairs[: args.limit]

    log.info("Loaded %d pairs", len(pairs))
    seed(pairs, dry_run=args.dry_run, reset=args.reset)


if __name__ == "__main__":
    main()
