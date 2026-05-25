"""Combined background worker daemon.

Runs two pollers in threads:
  - online_eval_worker: scores new RAG traces with code-based evaluators
  - sync_feedback:      syncs Open WebUI thumbs-up/down ratings to Langfuse

Launched automatically by the agentguard-worker Docker service.

Usage (manual):
    python -m scripts.worker
    python -m scripts.worker --eval-interval 30 --feedback-interval 60
"""

import argparse
import logging
import signal
import threading
import time

from dotenv import load_dotenv

load_dotenv()

import scripts.online_eval_worker as eval_worker
import scripts.sync_feedback as feedback_worker
from scripts.seed_score_configs import seed as seed_score_configs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("worker")

_stop = threading.Event()


def _eval_loop(interval: int, limit: int, config_ids: dict) -> None:
    logger.info("eval-worker started (interval: %ds, limit: %d)", interval, limit)
    while not _stop.is_set():
        try:
            eval_worker.run_once(limit=limit, config_ids=config_ids)
        except Exception as exc:
            logger.error("eval-worker error: %s", exc)
        _stop.wait(interval)


def _feedback_loop(interval: int, config_ids: dict) -> None:
    logger.info("feedback-worker started (interval: %ds)", interval)
    while not _stop.is_set():
        try:
            feedback_worker.run_once(apply=True, config_ids=config_ids)
        except Exception as exc:
            logger.error("feedback-worker error: %s", exc)
        _stop.wait(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentGuard background worker")
    parser.add_argument("--eval-interval", type=int, default=60, metavar="S",
                        help="Online eval poll interval in seconds (default: 60)")
    parser.add_argument("--feedback-interval", type=int, default=120, metavar="S",
                        help="Feedback sync poll interval in seconds (default: 120)")
    parser.add_argument("--limit", type=int, default=100, metavar="N",
                        help="Traces to fetch per eval pass (default: 100)")
    args = parser.parse_args()

    logger.info("Seeding score configs...")
    config_ids = seed_score_configs()

    threads = [
        threading.Thread(
            target=_eval_loop,
            args=(args.eval_interval, args.limit, config_ids),
            name="eval-worker",
            daemon=True,
        ),
        threading.Thread(
            target=_feedback_loop,
            args=(args.feedback_interval, config_ids),
            name="feedback-worker",
            daemon=True,
        ),
    ]

    for t in threads:
        t.start()

    def _shutdown(sig, _frame):
        logger.info("Shutting down (signal %d)...", sig)
        _stop.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Worker running. Ctrl+C or SIGTERM to stop.")
    _stop.wait()
    logger.info("Worker stopped.")


if __name__ == "__main__":
    main()
