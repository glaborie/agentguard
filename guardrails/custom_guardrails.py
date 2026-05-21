"""Custom guardrails for the Langfuse RAG POC LiteLLM proxy.

Two guardrails that run fully locally with no external API dependencies:
  - PromptInjectionGuard: blocks adversarial prompt patterns (pre_call)
  - PIIMaskingGuard: redacts PII from LLM responses (post_call)
"""

import re
from typing import Optional

from litellm._logging import verbose_proxy_logger
from litellm.exceptions import BadRequestError
from litellm.integrations.custom_guardrail import CustomGuardrail


# ── Prompt Injection Detection ─────────────────────────────────────

INJECTION_PATTERNS = [
    r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts|rules)",
    r"disregard (?:all |any )?(?:previous|prior|above)",
    r"forget (?:all |any )?(?:previous|prior|your)",
    r"you are now (?:a |an )?",
    r"pretend (?:to be|you(?:'re| are))",
    r"new (?:instructions|rules|persona|role)\s*:",
    r"(?:give|show|reveal|print|display|output|repeat|tell)\b.*\b(?:system\s*prompt|instructions|rules)",
    r"system\s*(?:prompt|message)\s*(?:override|update)",
    r"jailbreak",
    r"do anything now",
    r"developer mode",
    r"(?-i:DAN)\b",
]


class PromptInjectionGuard(CustomGuardrail):
    """Scans user messages for common prompt injection patterns and blocks the request."""

    def __init__(self, **kwargs):
        self._compiled = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]
        super().__init__(**kwargs)

    async def async_pre_call_hook(
        self,
        user_api_key_dict,
        cache,
        data: dict,
        call_type: str,
    ) -> Optional[dict]:
        for msg in data.get("messages", []):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            for pattern in self._compiled:
                match = pattern.search(content)
                if match:
                    verbose_proxy_logger.warning(
                        "Prompt injection blocked: '%s'", match.group()
                    )
                    raise BadRequestError(
                        message="Request blocked: potential prompt injection detected.",
                        model=data.get("model", ""),
                        llm_provider="custom_guardrail",
                    )
        return data


# ── PII Masking ────────────────────────────────────────────────────

PII_RULES = [
    # email
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL_REDACTED]"),
    # US SSN (xxx-xx-xxxx)
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REDACTED]"),
    # credit card (4 groups of 4 digits)
    (r"\b(?:\d{4}[-\s]?){3}\d{4}\b", "[CARD_REDACTED]"),
    # US/CA phone numbers
    (r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE_REDACTED]"),
]


class PIIMaskingGuard(CustomGuardrail):
    """Scans LLM output and replaces PII patterns with redaction tokens."""

    def __init__(self, **kwargs):
        self._compiled = [(re.compile(p), repl) for p, repl in PII_RULES]
        super().__init__(**kwargs)

    async def async_post_call_success_hook(
        self,
        data: dict,
        user_api_key_dict,
        response,
    ):
        if not hasattr(response, "choices"):
            return response
        for choice in response.choices:
            content = getattr(getattr(choice, "message", None), "content", None)
            if not content:
                continue
            original = content
            for pattern, replacement in self._compiled:
                content = pattern.sub(replacement, content)
            if content != original:
                choice.message.content = content
                verbose_proxy_logger.info("PII masked in response")
        return response
