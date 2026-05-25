"""Register Langfuse score configs for all evaluators used in this project.

Score configs tell Langfuse the data type and display metadata for each score name.
Without them, scores created via the SDK are stored but don't appear in the Scores
dashboard or trace score tabs in the Langfuse UI.

Run once (or re-run safely — existing configs are skipped):
    python -m scripts.seed_score_configs
"""

from dotenv import load_dotenv

load_dotenv()

from langfuse.api.commons.types.score_config_data_type import ScoreConfigDataType

from app.tracing import get_langfuse_client

# All score configs used in this project.
# (name, data_type, description)
SCORE_CONFIGS = [
    # Online eval — code-based, fires on every production RAG trace
    ("online_has_citation", ScoreConfigDataType.BOOLEAN,
     "Response references a source (according to / based on / from the)"),
    ("online_within_length", ScoreConfigDataType.BOOLEAN,
     "Response is within 500 words"),
    ("online_no_hallucination_markers", ScoreConfigDataType.BOOLEAN,
     "Response contains no hedging phrases (I think, probably, I'm not sure)"),

    # Human feedback — synced from Open WebUI thumbs-up/down
    ("user_feedback", ScoreConfigDataType.BOOLEAN,
     "Thumbs-up (1) or thumbs-down (0) from Open WebUI, synced by scripts/sync_feedback.py"),
    ("user_feedback_rating", ScoreConfigDataType.NUMERIC,
     "1–10 numeric rating from Open WebUI annotation.details.rating, synced by scripts/sync_feedback.py"),
]


def seed(dry_run: bool = False) -> dict[str, str]:
    """Create any missing score configs and return a name → config_id mapping."""
    client = get_langfuse_client()

    existing_resp = client.api.score_configs.get()
    existing = {c.name: c.id for c in (existing_resp.data or [])}

    created = 0
    skipped = 0
    for name, data_type, description in SCORE_CONFIGS:
        if name in existing:
            print(f"  skip  {name} (already exists)")
            skipped += 1
            continue
        if dry_run:
            print(f"  would create  {name} ({data_type.value})")
            continue
        cfg = client.api.score_configs.create(
            name=name,
            data_type=data_type,
            description=description,
        )
        existing[name] = cfg.id
        print(f"  created  {name} ({data_type.value})")
        created += 1

    print(f"\nDone: {created} created, {skipped} skipped.")
    return existing


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Seed Langfuse score configs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without writing")
    args = parser.parse_args()

    print("Seeding Langfuse score configs...")
    seed(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
