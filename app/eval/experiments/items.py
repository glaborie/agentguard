"""Experiment result data class."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ItemResult:
    question: str
    model: str
    output: str
    scores: dict[str, float] = field(default_factory=dict)
    trace_id: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
