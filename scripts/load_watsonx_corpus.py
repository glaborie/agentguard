"""Download ibm-research/watsonxDocsQA and write unique contexts to data/docs/watsonx/.

Usage:
    python -m scripts.load_watsonx_corpus              # default split: train
    python -m scripts.load_watsonx_corpus --split all  # all splits
    python -m scripts.load_watsonx_corpus --dry-run    # print stats, write nothing
"""

import argparse
import hashlib
import json
import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

DATASET_REPO = "ibm-research/watsonxDocsQA"
OUT_DIR = Path("data/docs/watsonx")
QA_PAIRS_FILE = Path("data/watsonx_qa_pairs.jsonl")

# Candidate column names for context, question, answer fields
_CTX_COLS  = ("md_document", "document", "context", "contexts", "passage", "doc_text", "text")
_Q_COLS    = ("question", "query", "user_input")
_ANS_COLS  = ("correct_answer", "answer", "ground_truth", "reference", "expected_answer")
_DOCID_COLS = ("correct_answer_document_ids", "doc_id", "corpus_id", "document_id", "document_ids")


def _detect_column(cols: list[str], candidates: tuple[str, ...]) -> str | None:
    for c in candidates:
        if c in cols:
            return c
    return None


def _slug(text: str, max_len: int = 80) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_-]+", "_", s).strip("_")
    return s[:max_len]


def _sha8(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:8]


def load_and_write(splits: list[str], dry_run: bool) -> None:
    from datasets import load_dataset  # type: ignore

    # Load both configs separately — 'corpus' has docs, 'question_answers' has QA pairs
    log.info("Loading %s config=corpus …", DATASET_REPO)
    corpus_ds = load_dataset(DATASET_REPO, "corpus")
    log.info("Loading %s config=question_answers …", DATASET_REPO)
    qa_ds = load_dataset(DATASET_REPO, "question_answers")

    # ── Collect corpus rows ──────────────────────────────────────────────
    corpus_rows: list[dict] = []
    for split in (corpus_ds.keys() if "all" in splits else [s for s in splits if s in corpus_ds]):
        corpus_rows.extend(corpus_ds[split].to_list())
    if not corpus_rows and "train" in corpus_ds:
        corpus_rows = corpus_ds["train"].to_list()

    corpus_cols = list(corpus_rows[0].keys()) if corpus_rows else []
    log.info("Corpus columns: %s  (%d rows)", corpus_cols, len(corpus_rows))
    ctx_col = _detect_column(corpus_cols, _CTX_COLS) or (corpus_cols[0] if corpus_cols else None)
    if not ctx_col:
        raise ValueError(f"Cannot detect context column. Got: {corpus_cols}")

    # ── Collect QA rows ──────────────────────────────────────────────────
    qa_rows: list[dict] = []
    for split in (qa_ds.keys() if "all" in splits else [s for s in splits if s in qa_ds]):
        qa_rows.extend(qa_ds[split].to_list())
    if not qa_rows and "train" in qa_ds:
        qa_rows = qa_ds["train"].to_list()

    qa_cols = list(qa_rows[0].keys()) if qa_rows else []
    log.info("QA columns: %s  (%d rows)", qa_cols, len(qa_rows))
    q_col      = _detect_column(qa_cols, _Q_COLS)
    ans_col    = _detect_column(qa_cols, _ANS_COLS)
    doc_id_col = _detect_column(qa_cols, _DOCID_COLS)

    # ── Build context lookup by doc_id (if available) ────────────────────
    ctx_by_id: dict[str, str] = {}
    doc_id_col_corpus = _detect_column(corpus_cols, ("doc_id", "id", "corpus_id"))
    if doc_id_col_corpus:
        for row in corpus_rows:
            did = str(row.get(doc_id_col_corpus, ""))
            ctx = str(row.get(ctx_col, "")).strip()
            if did and ctx:
                ctx_by_id[did] = ctx

    log.info("Detected  ctx=%s  q=%s  ans=%s  qa_docid=%s  corpus_docid=%s",
             ctx_col, q_col, ans_col, doc_id_col, doc_id_col_corpus)

    # Deduplicate contexts by sha1
    seen: dict[str, str] = {}  # sha → text
    qa_pairs: list[dict] = []

    for row in corpus_rows:
        ctx = str(row.get(ctx_col, "")).strip()
        if ctx:
            seen[_sha8(ctx)] = ctx

    for row in qa_rows:
        q   = str(row.get(q_col or "question", "")).strip()
        ans = str(row.get(ans_col or "answer",  "")).strip()
        if not q or not ans:
            continue

        # correct_answer_document_ids is a list — take first matching context
        ctx_val = ""
        if doc_id_col:
            raw = row.get(doc_id_col, [])
            ids = raw if isinstance(raw, list) else [raw]
            for did in ids:
                ctx_val = ctx_by_id.get(str(did), "")
                if ctx_val:
                    break

        # fallback: ground_truths_contexts if present
        if not ctx_val:
            gt = row.get("ground_truths_contexts", "")
            if gt:
                ctx_val = str(gt)

        qa_pairs.append({"question": q, "answer": ans, "context": ctx_val})

    log.info("Unique contexts: %d  |  QA pairs: %d", len(seen), len(qa_pairs))

    if dry_run:
        log.info("Dry-run — nothing written.")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for sha, text in seen.items():
        fname = OUT_DIR / f"{sha}.txt"
        fname.write_text(text, encoding="utf-8")
    log.info("Wrote %d context files → %s", len(seen), OUT_DIR)

    if qa_pairs:
        QA_PAIRS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with QA_PAIRS_FILE.open("w", encoding="utf-8") as fh:
            for pair in qa_pairs:
                fh.write(json.dumps(pair, ensure_ascii=False) + "\n")
        log.info("Wrote %d QA pairs → %s", len(qa_pairs), QA_PAIRS_FILE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load watsonxDocsQA corpus")
    parser.add_argument("--split", default="train", help="Dataset split(s), comma-separated or 'all'")
    parser.add_argument("--dry-run", action="store_true", help="Print stats only, write nothing")
    args = parser.parse_args()

    splits = [s.strip() for s in args.split.split(",")]
    load_and_write(splits, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
