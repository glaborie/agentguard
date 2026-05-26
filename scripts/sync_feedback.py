"""
Sync Open WebUI ratings to Langfuse as user_feedback scores.

Open WebUI stores ratings in annotation.rating on each assistant message.
Correlation to Langfuse traces uses the message_id injected by the
Langfuse Session Linker filter (metadata.message_id on each trace).
Falls back to question-text + timestamp matching for older traces that
predate the filter.

Scores written per rated message:
  user_feedback        BOOLEAN  1.0 (thumbs-up) or 0.0 (thumbs-down)
  user_feedback_rating NUMERIC  1–10 from annotation.details.rating (if present)

Usage:
    python -m scripts.sync_feedback              # dry-run (print, no scoring)
    python -m scripts.sync_feedback --apply      # single pass, write scores
    python -m scripts.sync_feedback --apply --interval 120  # continuous daemon
    python -m scripts.sync_feedback --apply --reset         # re-sync all

State is persisted in .sync_feedback_state.json (list of already-synced message IDs).
"""

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from langfuse import Langfuse

from app.config import settings
from scripts.utils import HTTP_TIMEOUT, TRACE_PAGE_SIZE, langfuse_basic_auth, load_state, save_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# /api/public/scores stores configId correctly; the SDK batch endpoint ignores it.
_AUTH = langfuse_basic_auth()

STATE_FILE = Path(".sync_feedback_state.json")
TRACE_FETCH_LIMIT = 200


# ── Open WebUI helpers ────────────────────────────────────────────────────────

def _owui_token(base_url: str, email: str, password: str) -> str:
    r = httpx.post(
        f"{base_url}/api/v1/auths/signin",
        json={"email": email, "password": password},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    token = r.json().get("token")
    if not token:
        raise RuntimeError(f"Auth failed: {r.text}")
    return token


def _get_rated_messages(base_url: str, token: str) -> list[dict]:
    """Return list of rated assistant message dicts from all chats."""
    headers = {"Authorization": f"Bearer {token}"}
    r = httpx.get(f"{base_url}/api/v1/chats/", headers=headers, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    chats = r.json()

    results = []
    for chat_meta in chats:
        chat_id = chat_meta["id"]
        r2 = httpx.get(
            f"{base_url}/api/v1/chats/{chat_id}",
            headers=headers,
            timeout=HTTP_TIMEOUT,
        )
        r2.raise_for_status()
        chat = r2.json().get("chat", {})
        # history.messages (dict) has the full annotation (reason, comment, details.rating).
        # chat.messages (list) only carries rating + tags — use history when available.
        history = chat.get("history", {}).get("messages", {})
        messages = list(history.values()) if history else chat.get("messages", [])

        msg_map = {m["id"]: m for m in messages if "id" in m}

        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            annotation = msg.get("annotation") or {}
            rating = annotation.get("rating")
            if rating is None:
                continue

            parent = msg_map.get(msg.get("parentId"), {})
            results.append({
                "message_id": msg["id"],
                "question": parent.get("content", ""),
                "answer": msg.get("content", ""),
                "rating": int(rating),
                "numeric_rating": (annotation.get("details") or {}).get("rating"),
                "tags": annotation.get("tags") or [],
                "reason": annotation.get("reason") or "",
                "comment": annotation.get("comment") or "",
                "timestamp": int(msg.get("timestamp", 0)),
            })
    return results


# ── Langfuse trace index ──────────────────────────────────────────────────────

def _to_unix(ts) -> int:
    """Convert a Langfuse trace timestamp to a Unix epoch integer."""
    if ts is None:
        return 0
    if hasattr(ts, "timestamp"):
        return int(ts.timestamp())
    try:
        return int(datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return 0


def _build_trace_index(lf: Langfuse) -> tuple[dict[str, str], dict[str, list[tuple[str, int]]]]:
    """Build two indices from recent RunnableSequence traces:
      - by_message_id: {message_id → trace_id}  (exact, from filter metadata)
      - by_question:   {normalised_question → [(trace_id, unix_ts), ...]}  (fallback)
    """
    by_message_id: dict[str, str] = {}
    by_question: dict[str, list[tuple[str, int]]] = {}
    page = 1
    fetched = 0

    while fetched < TRACE_FETCH_LIMIT:
        try:
            resp = lf.api.trace.list(name="RunnableSequence", limit=TRACE_PAGE_SIZE, page=page)
            traces = resp.data if hasattr(resp, "data") else []
        except Exception as exc:
            logger.warning("Langfuse trace list page %d failed: %s", page, exc)
            break
        if not traces:
            break

        for trace in traces:
            inp = trace.input
            if not inp:
                continue
            inp_str = inp if isinstance(inp, str) else json.dumps(inp)
            if inp_str.lstrip().startswith("### Task:"):
                continue

            meta = trace.metadata or {}
            if mid := meta.get("message_id"):
                by_message_id[mid] = trace.id

            q_norm = inp_str.lstrip("* \t\n").lower()
            if q_norm:
                by_question.setdefault(q_norm, []).append((trace.id, _to_unix(trace.timestamp)))

        fetched += len(traces)
        if len(traces) < TRACE_PAGE_SIZE:
            break
        page += 1

    return by_message_id, by_question


def _find_trace(
    by_message_id: dict[str, str],
    by_question: dict[str, list[tuple[str, int]]],
    item: dict,
) -> tuple[str | None, str]:
    """Return (trace_id, method) where method is 'message_id' or 'text_match'."""
    if tid := by_message_id.get(item["message_id"]):
        return tid, "message_id"

    q_norm = item["question"].lstrip("* \t\n").lower()
    candidates = by_question.get(q_norm)
    if not candidates:
        for key, cands in by_question.items():
            if q_norm[:80] in key or key[:80] in q_norm:
                candidates = cands
                break
    if not candidates:
        return None, "no_match"
    if len(candidates) == 1:
        return candidates[0][0], "text_match"

    ow_ts = item["timestamp"]
    best_id, best_diff = candidates[0][0], float("inf")
    for offset in range(-10800, 10801, 1800):
        for tid, trace_unix in candidates:
            diff = abs((trace_unix + offset) - ow_ts)
            if diff < best_diff:
                best_diff, best_id = diff, tid
    return best_id, "text_match"


# ── Score posting ─────────────────────────────────────────────────────────────

def _post_score(
    trace_id: str,
    name: str,
    value: float,
    data_type: str,
    comment: str | None,
    config_ids: dict[str, str],
) -> None:
    payload: dict = {
        "traceId": trace_id,
        "name": name,
        "value": value,
        "dataType": data_type,
    }
    if config_ids.get(name):
        payload["configId"] = config_ids[name]
    if comment:
        payload["comment"] = comment
    resp = httpx.post(
        f"{settings.langfuse_base_url}/api/public/scores",
        json=payload,
        headers={"Authorization": f"Basic {_AUTH}", "Content-Type": "application/json"},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()


# ── State helpers ─────────────────────────────────────────────────────────────

def _load_seen() -> set[str]:
    return load_state(STATE_FILE)


def _save_seen(seen: set[str]) -> None:
    save_state(STATE_FILE, seen)


# ── Core pass ────────────────────────────────────────────────────────────────

def run_once(apply: bool = True, reset: bool = False, config_ids: dict[str, str] | None = None) -> int:
    """Fetch rated messages from Open WebUI and sync unseen ones to Langfuse.

    Returns the number of scores written this pass.
    """
    lf = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
        timeout=HTTP_TIMEOUT,
    )

    try:
        token = _owui_token(settings.openwebui_base_url, settings.openwebui_email, settings.openwebui_password)
    except httpx.HTTPStatusError as exc:
        logger.error("Open WebUI auth failed (HTTP %s): %s", exc.response.status_code, exc)
        return 0
    except httpx.RequestError as exc:
        logger.error("Open WebUI unreachable during auth: %s", exc)
        return 0

    try:
        rated = _get_rated_messages(settings.openwebui_base_url, token)
    except httpx.HTTPStatusError as exc:
        logger.error("Failed to fetch rated messages (HTTP %s): %s", exc.response.status_code, exc)
        return 0
    except httpx.RequestError as exc:
        logger.error("Open WebUI unreachable while fetching messages: %s", exc)
        return 0

    if not rated:
        logger.info("No rated messages found.")
        return 0

    by_message_id, by_question = _build_trace_index(lf)

    seen = set() if reset else _load_seen()
    synced = 0

    for item in rated:
        msg_id = item["message_id"]
        if msg_id in seen:
            continue

        score_value = 1.0 if item["rating"] > 0 else 0.0
        label = "POSITIVE" if score_value == 1.0 else "NEGATIVE"

        trace_id, method = _find_trace(by_message_id, by_question, item)
        if not trace_id:
            logger.warning("[%s] no matching trace — skipping", msg_id[:8])
            seen.add(msg_id)
            continue

        comment_parts = [p for p in [item["reason"], ", ".join(item["tags"]), item["comment"]] if p]
        comment = " | ".join(comment_parts) or None

        if apply:
            try:
                _post_score(trace_id, "user_feedback", score_value, "BOOLEAN", comment, config_ids or {})
                if item["numeric_rating"] is not None:
                    _post_score(trace_id, "user_feedback_rating", float(item["numeric_rating"]), "NUMERIC", comment, config_ids or {})
                logger.info(
                    "[%s] %s  trace=%s  [%s]  rating=%s  comment=%s",
                    msg_id[:8], label, trace_id[:12], method,
                    item["numeric_rating"], comment,
                )
                synced += 1
            except Exception as exc:
                logger.error("[%s] scoring failed: %s", msg_id[:8], exc)
        else:
            logger.info(
                "[%s] %s  trace=%s  [%s]  (dry-run)",
                msg_id[:8], label, trace_id[:12], method,
            )
            synced += 1

        seen.add(msg_id)

    _save_seen(seen)
    logger.info("Done. %d feedback score(s) written this pass.", synced)
    return synced


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Open WebUI feedback to Langfuse")
    parser.add_argument("--apply", action="store_true", help="Write scores (default: dry-run)")
    parser.add_argument("--reset", action="store_true", help="Ignore seen cache, re-sync all")
    parser.add_argument("--once", action="store_true", help="Single pass and exit")
    parser.add_argument("--interval", type=int, default=None, metavar="SECONDS",
                        help="Poll continuously every N seconds (implies --apply)")
    args = parser.parse_args()

    from scripts.seed_score_configs import seed as seed_score_configs
    config_ids = seed_score_configs()

    apply = args.apply or (args.interval is not None)

    if args.interval is None or args.once:
        run_once(apply=apply, reset=args.reset, config_ids=config_ids)
        return

    logger.info("Feedback sync worker started (interval: %ds).", args.interval)
    while True:
        try:
            run_once(apply=True, config_ids=config_ids)
        except Exception as exc:
            logger.error("Poll error: %s", exc)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
