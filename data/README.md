
  Workflow:
  # 1. Download corpus + write docs
  python -m scripts.load_watsonx_corpus

  # 2. Ingest into Qdrant (uses watsonx_docs collection)
  # Set RAG_COLLECTION=northstar_crm in .env or override via CLI

  # 3. Seed eval dataset
  python -m scripts.seed_watsonx_dataset --limit 200

  python -m app.main ragas-experiment --dataset watsonx-qa --models openrouter-gemini-flash --limit 10

  python -m app.main ragas-experiment --dataset watsonx-qa --models openrouter-gemini-flash
