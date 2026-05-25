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
    python -m scripts.sync_feedback --apply      # write scores to Langfuse
    python -m scripts.sync_feedback --apply --reset  # re-sync all (ignore seen cache)

State is persisted in .sync_feedback_state.json (list of already-synced message IDs).
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from langfuse import Langfuse

from app.config import settings

STATE_FILE = Path(".sync_feedback_state.json")
TRACE_FETCH_LIMIT = 200


# ── Open WebUI helpers ────────────────────────────────────────────────────────

def _owui_token(base_url: str, email: str, password: str) -> str:
    r = httpx.post(
        f"{base_url}/api/v1/auths/signin",
        json={"email": email, "password": password},
        timeout=10,
    )
    r.raise_for_status()
    token = r.json().get("token")
    if not token:
        raise RuntimeError(f"Auth failed: {r.text}")
    return token


def _get_rated_messages(base_url: str, token: str) -> list[dict]:
    """Return list of rated assistant message dicts from all chats."""
    headers = {"Authorization": f"Bearer {token}"}
    r = httpx.get(f"{base_url}/api/v1/chats/", headers=headers, timeout=15)
    r.raise_for_status()
    chats = r.json()

    results = []
    for chat_meta in chats:
        chat_id = chat_meta["id"]
        r2 = httpx.get(
            f"{base_url}/api/v1/chats/{chat_id}",
            headers=headers,
            timeout=15,
        )
        r2.raise_for_status()
        messages = r2.json().get("chat", {}).get("messages", [])
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
            resp = lf.api.trace.list(name="RunnableSequence", limit=50, page=page)
            traces = resp.data if hasattr(resp, "data") else []
        except Exception as exc:
            print(f"  [warn] Langfuse trace list page {page} failed: {exc}")
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

            # Direct correlation via injected message_id
            meta = trace.metadata or {}
            if mid := meta.get("message_id"):
                by_message_id[mid] = trace.id

            # Fallback: text index
            q_norm = inp_str.lstrip("* \t\n").lower()
            if q_norm:
                ts = trace.timestamp
                if ts is None:
                    trace_unix = 0
                elif hasattr(ts, "timestamp"):
                    trace_unix = int(ts.timestamp())
                else:
                    try:
                        from datetime import datetime as dt
                        trace_unix = int(dt.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp())
                    except Exception:
                        trace_unix = 0
                by_question.setdefault(q_norm, []).append((trace.id, trace_unix))

        fetched += len(traces)
        if len(traces) < 50:
            break
        page += 1

    return by_message_id, by_question


def _find_trace(
    by_message_id: dict[str, str],
    by_question: dict[str, list[tuple[str, int]]],
    item: dict,
) -> tuple[str | None, str]:
    """Return (trace_id, method) where method is 'message_id' or 'text_match'."""
    # Primary: exact message_id match
    if tid := by_message_id.get(item["message_id"]):
        return tid, "message_id"

    # Fallback: question-text + timestamp (for pre-filter traces)
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


# ── State helpers ─────────────────────────────────────────────────────────────

def _load_seen() -> set[str]:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def _save_seen(seen: set[str]) -> None:
    STATE_FILE.write_text(json.dumps(sorted(seen)))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write scores to Langfuse")
    parser.add_argument("--reset", action="store_true", help="Ignore seen cache, re-sync all")
    args = parser.parse_args()

    owui_base = getattr(settings, "openwebui_base_url", "http://localhost:3001")
    owui_email = getattr(settings, "openwebui_email", "glaborie@gmail.com")
    owui_password = getattr(settings, "openwebui_password", "admin")

    lf = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
    )

    print("Authenticating with Open WebUI...")
    token = _owui_token(owui_base, owui_email, owui_password)

    print("Fetching rated messages...")
    rated = _get_rated_messages(owui_base, token)
    print(f"Found {len(rated)} rated message(s).")

    print("Building Langfuse trace index...")
    by_message_id, by_question = _build_trace_index(lf)
    print(f"  {len(by_message_id)} trace(s) indexed by message_id (direct)")
    print(f"  {len(by_question)} trace(s) indexed by question text (fallback)")

    seen = set() if args.reset else _load_seen()
    synced = 0

    for item in rated:
        msg_id = item["message_id"]
        if msg_id in seen:
            continue

        human_time = datetime.fromtimestamp(item["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        score_value = 1.0 if item["rating"] > 0 else 0.0
        label = "POSITIVE" if score_value == 1.0 else "NEGATIVE"

        print(f"\n[{human_time}] {label}  q={item['question'][:60]!r}")

        trace_id, method = _find_trace(by_message_id, by_question, item)
        if not trace_id:
            print("  -> no matching Langfuse trace found")
            seen.add(msg_id)
            continue

        print(f"  -> trace {trace_id}  [{method}]")

        # Build comment from rich annotation fields
        comment_parts = []
        if item["reason"]:
            comment_parts.append(item["reason"])
        if item["tags"]:
            comment_parts.append("tags: " + ", ".join(item["tags"]))
        if item["comment"]:
            comment_parts.append(item["comment"])
        comment = " | ".join(comment_parts) or None

        if args.apply:
            try:
                lf.create_score(
                    trace_id=trace_id,
                    name="user_feedback",
                    value=score_value,
                    data_type="BOOLEAN",
                    comment=comment,
                )
                if item["numeric_rating"] is not None:
                    lf.create_score(
                        trace_id=trace_id,
                        name="user_feedback_rating",
                        value=float(item["numeric_rating"]),
                        data_type="NUMERIC",
                        comment=comment,
                    )
                print(f"  -> scored OK (numeric_rating={item['numeric_rating']})")
                synced += 1
            except Exception as exc:
                print(f"  -> scoring failed: {exc}")
        else:
            print(f"  -> (dry-run) would write user_feedback={score_value}"
                  + (f", user_feedback_rating={item['numeric_rating']}" if item["numeric_rating"] is not None else "")
                  + (f", comment={comment!r}" if comment else ""))
            synced += 1

        seen.add(msg_id)

    _save_seen(seen)

    if not args.apply:
        print(f"\nDry-run: {synced} score(s) would be written. Re-run with --apply.")
    else:
        print(f"\nDone: {synced} score(s) written to Langfuse.")


if __name__ == "__main__":
    main()
