"""
Seed the RAG system prompt into Langfuse Prompt Registry.

Run once after the stack is up:
    python -m scripts.seed_langfuse_prompt

Idempotent — skips creation if the prompt already exists in the registry.
To force a new version (e.g. after editing the prompt), pass --force:
    python -m scripts.seed_langfuse_prompt --force
"""

import sys

from langfuse import Langfuse

from app.core.config import settings
from app.rag.chain import LANGFUSE_PROMPT_MESSAGES

PROMPT_NAME = "rag-system-prompt"


def main(force: bool = False) -> None:
    lf = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
    )

    if not force:
        try:
            existing = lf.get_prompt(PROMPT_NAME, type="chat")
            print(
                f"Prompt '{PROMPT_NAME}' already exists "
                f"(version {existing.version}, labels: {existing.labels}) — skipping.\n"
                f"Use --force to create a new version."
            )
            return
        except Exception:
            pass

    lf.create_prompt(
        name=PROMPT_NAME,
        type="chat",
        prompt=LANGFUSE_PROMPT_MESSAGES,
        labels=["production"],
        config={"model": "openrouter-mistral", "temperature": 0.5},
        commit_message="Initial RAG system prompt" if not force else "Updated RAG system prompt",
    )
    print(f"Created prompt '{PROMPT_NAME}' in Langfuse with label 'production'.")
    print(f"Edit it at http://localhost:3200 > Prompts > {PROMPT_NAME}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
