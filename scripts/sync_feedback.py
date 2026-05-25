"""
Sync Open WebUI thumbs-up/down ratings to Langfuse as user_feedback scores.

Open WebUI stores ratings internally (annotation.rating on each message).
This script polls the Open WebUI API, finds rated assistant messages, then
correlates each one to a Langfuse trace via timestamp + question-text matching.

Usage:
    python -m scripts.sync_feedback              # dry-run (print, no scoring)
    python -m scripts.sync_feedback --apply      # write scores to Langfuse
    python -m scripts.sync_feedback --apply --reset  # re-sync all (ignore seen cache)

State is persisted in .sync_feedback_state.json (list of already-synced message IDs).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from langfuse import Langfuse

from app.config import settings

STATE_FILE = Path(".sync_feedback_state.json")
TRACE_FETCH_LIMIT = 200  # how many recent traces to load for matching


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
    """Return list of (question, answer, rating, timestamp_utc) dicts."""
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

        # Build id → message map for parent lookup
        msg_map = {m["id"]: m for m in messages if "id" in m}

        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            annotation = msg.get("annotation") or {}
            rating = annotation.get("rating")
            if rating is None:
                continue

            # Get the user question from the parent message
            parent_id = msg.get("parentId")
            parent = msg_map.get(parent_id, {})
            question = parent.get("content", "")

            results.append(
                {
                    "message_id": msg["id"],
                    "question": question,
                    "answer": msg.get("content", ""),
                    "rating": int(rating),
                    "timestamp": int(msg.get("timestamp", 0)),
                }
            )
    return results


# ── Langfuse helpers ──────────────────────────────────────────────────────────

def _build_trace_index(lf: Langfuse) -> dict[str, list[tuple[str, int]]]:
    """Return {normalised_question: [(trace_id, trace_ts_unix), ...]} for recent RAG traces.

    Fetches RunnableSequence traces and skips Open WebUI's internal auto-tasks
    (title/tag/suggestion generation) which have inputs starting with '### Task:'.
    The Langfuse fromTimestamp filter is unreliable in this version, so we pull a
    recent batch and match by input text + closest timestamp.
    """
    index: dict[str, list[tuple[str, int]]] = {}
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
            # Skip Open WebUI internal auto-tasks
            if inp_str.lstrip().startswith("### Task:"):
                continue
            # Normalise: strip leading markdown bullets / whitespace
            q_norm = inp_str.lstrip("* \t\n").lower()
            if not q_norm:
                continue
            # Parse trace timestamp to unix int
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

            index.setdefault(q_norm, []).append((trace.id, trace_unix))

        fetched += len(traces)
        if len(traces) < 50:
            break
        page += 1

    return index


def _find_trace(index: dict[str, list[tuple[str, int]]], question: str, ow_ts: int) -> str | None:
    """Find the trace whose question matches and whose timestamp is closest to ow_ts.

    The Langfuse server may run with a UTC offset (e.g. UTC+2 on Windows Docker),
    so we check candidate offsets of -3h to +3h when looking for the closest match.
    """
    q_norm = question.lstrip("* \t\n").lower()

    # Find candidate list (exact then partial)
    candidates = index.get(q_norm)
    if not candidates:
        for key, cands in index.items():
            if q_norm[:80] in key or key[:80] in q_norm:
                candidates = cands
                break

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0][0]

    # Multiple traces for same question: pick the one closest to ow_ts
    # Try UTC offsets from -3h to +3h in 30-min steps
    best_id, best_diff = candidates[0][0], float("inf")
    for offset in range(-10800, 10801, 1800):
        for tid, trace_unix in candidates:
            diff = abs((trace_unix + offset) - ow_ts)
            if diff < best_diff:
                best_diff, best_id = diff, tid
    return best_id


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
    trace_index = _build_trace_index(lf)
    print(f"Indexed {len(trace_index)} RAG trace(s).")

    seen = set() if args.reset else _load_seen()
    new_seen: set[str] = set()
    synced = 0

    for item in rated:
        msg_id = item["message_id"]
        if msg_id in seen:
            continue

        ts = item["timestamp"]
        human_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        score_value = 1.0 if item["rating"] > 0 else 0.0
        label = "POSITIVE" if score_value == 1.0 else "NEGATIVE"

        print(f"\n[{human_time}] {label}  q={item['question'][:60]!r}")

        trace_id = _find_trace(trace_index, item["question"], item["timestamp"])
        if not trace_id:
            print("  -> no matching Langfuse trace found (outside time window or untraced query)")
            new_seen.add(msg_id)
            continue

        print(f"  -> trace {trace_id}")

        if args.apply:
            try:
                lf.create_score(
                    trace_id=trace_id,
                    name="user_feedback",
                    value=score_value,
                    data_type="BOOLEAN",
                    comment=f"from Open WebUI rating ({item['rating']:+d})",
                )
                print("  -> scored OK")
                synced += 1
            except Exception as exc:
                print(f"  -> scoring failed: {exc}")
        else:
            print("  -> (dry-run, use --apply to write)")
            synced += 1

        new_seen.add(msg_id)

    seen.update(new_seen)
    _save_seen(seen)

    if not args.apply:
        print(f"\nDry-run: {synced} score(s) would be written. Re-run with --apply.")
    else:
        print(f"\nDone: {synced} score(s) written to Langfuse.")


if __name__ == "__main__":
    main()
