"""
Idempotent bootstrap script for LiteLLM database-backed configuration.

Provisions the resources that would otherwise require manual setup via the
LiteLLM UI. Safe to run on every `docker compose up` — skips anything that
already exists.

Resources managed:
  - Models:    nomic-embed-text, openrouter-gemini-flash, openrouter-mistral (DB-registered so UI shows them)
  - Budget:    SampleBudget ($10 max, 600 TPM, 4 RPM, rolling 7-day window)
  - Team:      DevSecOps (access to all models)
  - Key:       AdminKey  (access to all team models)
  - Guardrail: Harmful Violence (litellm_content_filter, pre_call, DB-stored)

Note: the two custom Python guardrails (prompt-injection, pii-masking) are
defined in litellm_config.yaml and loaded at container start — they do not
need to be provisioned here.

Environment variables (with defaults matching docker-compose.yml):
  LITELLM_URL         http://localhost:4000
  LITELLM_MASTER_KEY  sk-litellm-dev-key
  LITELLM_ADMIN_KEY   (optional) stable key value for AdminKey
"""

import os
import sys
import time

import requests

BASE_URL = os.getenv("LITELLM_URL", "http://localhost:4000").rstrip("/")
MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-litellm-dev-key")
ADMIN_KEY = os.getenv("LITELLM_ADMIN_KEY", "")
HEADERS = {"Authorization": f"Bearer {MASTER_KEY}", "Content-Type": "application/json"}


# ── Desired state ──────────────────────────────────────────────────────────────

# Models are registered in the DB so they appear in the LiteLLM UI.
# Without DB registration they are API-accessible (from litellm_config.yaml)
# but invisible in the UI's Models tab.
MODELS = [
    {
        "model_name": "nomic-embed-text",
        "litellm_params": {
            "model": "ollama/nomic-embed-text",
            "api_base": "http://ollama:11434",
        },
    },
    {
        "model_name": "openrouter-gemini-flash",
        "litellm_params": {
            "model": "openai/google/gemini-2.5-flash-lite",
            "api_base": "https://openrouter.ai/api/v1",
            "api_key": os.environ.get("OPENROUTER_API_KEY", "os.environ/OPENROUTER_API_KEY"),
        },
    },
    {
        "model_name": "openrouter-mistral",
        "litellm_params": {
            "model": "openai/mistralai/mistral-nemo",
            "api_base": "https://openrouter.ai/api/v1",
            "api_key": os.environ.get("OPENROUTER_API_KEY", "os.environ/OPENROUTER_API_KEY"),
        },
    },
]

BUDGET = {
    "budget_id": "SampleBudget",
    "max_budget": 10.0,
    "tpm_limit": 600,
    "rpm_limit": 4,
    "budget_duration": "7d",
}

TEAM = {
    "team_alias": "DevSecOps",
    "models": ["all-proxy-models"],
    "members_with_roles": [{"user_id": "default_user_id", "role": "admin"}],
}

KEY = {
    "key_alias": "AdminKey",
    "models": ["all-team-models"],
    **({"key": ADMIN_KEY} if ADMIN_KEY else {}),
}

HARMFUL_VIOLENCE_GUARDRAIL = {
    "guardrail_name": "Harmful Violence",
    "litellm_params": {
        "guardrail": "litellm_content_filter",
        "mode": "pre_call",
        "default_on": True,
        "fail_on_error": True,
        "patterns": [
            {"pattern_type": "prebuilt", "pattern_name": "violence_threats", "name": "violence_threats", "action": "MASK"},
        ],
        "categories": [
            {"category": "harmful_violence",        "enabled": True, "action": "BLOCK", "severity_threshold": "medium"},
            {"category": "age_discrimination",      "enabled": True, "action": "BLOCK", "severity_threshold": "medium"},
            {"category": "bias_racial",             "enabled": True, "action": "BLOCK", "severity_threshold": "medium"},
            {"category": "bias_sexual_orientation", "enabled": True, "action": "BLOCK", "severity_threshold": "medium"},
        ],
    },
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def wait_for_litellm(timeout: int = 120) -> None:
    deadline = time.time() + timeout
    print(f"Waiting for LiteLLM at {BASE_URL} ...", flush=True)
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/health/liveliness", timeout=5)
            if r.status_code == 200:
                print("LiteLLM is up.", flush=True)
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(3)
    print("ERROR: LiteLLM did not become healthy in time.", file=sys.stderr)
    sys.exit(1)


def get(path: str) -> list | dict:
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def post(path: str, payload: dict) -> dict:
    r = requests.post(f"{BASE_URL}{path}", headers=HEADERS, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


# ── Provisioning ───────────────────────────────────────────────────────────────

def ensure_models() -> None:
    try:
        existing = get("/v2/model/info")
        db_models = {
            m["model_name"]: m
            for m in existing.get("data", [])
            if m.get("model_info", {}).get("db_model", False)
        }
    except Exception:
        db_models = {}

    for model in MODELS:
        name = model["model_name"]
        desired_backend = model["litellm_params"]["model"]

        if name in db_models:
            current_backend = db_models[name].get("litellm_params", {}).get("model", "")
            if current_backend == desired_backend:
                print(f"  model '{name}' already in DB — skipping")
                continue
            # Backend changed — delete stale entry so we can recreate it.
            model_id = db_models[name].get("model_info", {}).get("id")
            if model_id:
                post("/model/delete", {"id": model_id})
            print(f"  model '{name}' updated ({current_backend} → {desired_backend})")

        post("/model/new", model)
        print(f"  model '{name}' registered in DB")


def ensure_budget() -> None:
    existing = get("/budget/list")
    ids = {b["budget_id"] for b in existing}
    if BUDGET["budget_id"] in ids:
        print(f"  budget '{BUDGET['budget_id']}' already exists — skipping")
        return
    post("/budget/new", BUDGET)
    print(f"  budget '{BUDGET['budget_id']}' created")


def ensure_team() -> str:
    existing = get("/team/list")
    for team in existing:
        if team["team_alias"] == TEAM["team_alias"]:
            print(f"  team '{TEAM['team_alias']}' already exists — skipping")
            return team["team_id"]
    result = post("/team/new", TEAM)
    team_id = result["team_id"]
    print(f"  team '{TEAM['team_alias']}' created (id={team_id})")
    return team_id


def ensure_guardrail(guardrail: dict) -> None:
    name = guardrail["guardrail_name"]
    existing = get("/v2/guardrails/list").get("guardrails", [])
    for g in existing:
        if g.get("guardrail_name") == name and g.get("guardrail_definition_location") == "db":
            print(f"  guardrail '{name}' already exists — skipping")
            return
    try:
        post("/guardrails/register", guardrail)
        print(f"  guardrail '{name}' created")
    except requests.exceptions.HTTPError as exc:
        print(f"  WARNING: guardrail '{name}' registration failed ({exc}) — skipping", file=sys.stderr)


def ensure_key() -> None:
    existing = get("/key/list")
    # /key/list returns hashed keys; use /key/info to find by alias
    for hashed_key in existing.get("keys", []):
        info = get(f"/key/info?key={hashed_key}")
        if info.get("info", {}).get("key_alias") == KEY["key_alias"]:
            print(f"  key '{KEY['key_alias']}' already exists — skipping")
            return
    result = post("/key/generate", KEY)
    # Print the generated key once so it can be captured and added to .env
    print(f"  key '{KEY['key_alias']}' created: {result.get('key', '(not returned)')}")


# ── Schema patches ─────────────────────────────────────────────────────────────

# Columns added by newer LiteLLM image versions that may be missing when using
# a pre-existing volume with an older schema.  Each entry is (table, column, type).
_MISSING_COLUMNS = [
    ("LiteLLM_MCPServerTable", "source_url",       "TEXT"),
    ("LiteLLM_MCPServerTable", "approval_status",   "TEXT DEFAULT 'approved'"),
    ("LiteLLM_MCPServerTable", "submitted_by",      "TEXT"),
    ("LiteLLM_MCPServerTable", "submitted_at",      "TIMESTAMP(3)"),
    ("LiteLLM_MCPServerTable", "reviewed_at",       "TIMESTAMP(3)"),
    ("LiteLLM_MCPServerTable", "review_notes",      "TEXT"),
]


def apply_schema_patches() -> None:
    """Add any columns that the current LiteLLM image expects but Prisma didn't create.

    Uses the same DATABASE_URL that LiteLLM uses so it works inside the Docker
    network without extra configuration.
    """
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@postgres:5432/litellm",
    )
    try:
        import psycopg2  # type: ignore
    except ImportError:
        print("  [schema] psycopg2 not available — skipping schema patches", file=sys.stderr)
        return

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        for table, column, col_type in _MISSING_COLUMNS:
            cur.execute(
                f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {col_type};'
            )
        cur.close()
        conn.close()
        print("  schema patches applied (missing columns added idempotently)")
    except Exception as exc:
        # Non-fatal: LiteLLM works fine even if some columns are temporarily missing;
        # the error just pollutes postgres logs every 30 s.
        print(f"  [schema] patch failed: {exc}", file=sys.stderr)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    wait_for_litellm()
    print("Provisioning LiteLLM resources ...")
    apply_schema_patches()
    ensure_models()
    ensure_budget()
    ensure_team()
    ensure_key()
    ensure_guardrail(HARMFUL_VIOLENCE_GUARDRAIL)
    print("Done.")


if __name__ == "__main__":
    main()
