# NorthstarCRM Mock Corpus

A synthetic B2B SaaS sales chatbot dataset for retrieval, grounding, escalation, and business-process benchmarking.

## Purpose
This corpus simulates a realistic company knowledge base for a classic sales chatbot. It is designed to test:
- Retrieval quality
- Policy adherence
- Commercial accuracy
- Safe escalation
- FAQ handling
- Objection handling

## Structure
- `01_company/`: company profile and glossary
- `02_products/`: pricing, features, integrations, implementation
- `03_sales_process/`: qualification, demo, proposal, procurement, renewal
- `04_policies/`: discounts, approvals, security, data handling, SLA, refunds
- `05_support/`: FAQs
- `06_conversations/`: conversational examples in JSONL
- `07_benchmark/`: benchmark questions, expected outputs, retrieval labels

## Notes
- This dataset is synthetic and intended for benchmarking only.
- JSONL is line-delimited JSON, a common format for evaluation datasets and benchmark inputs.
