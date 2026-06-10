"""Config dashboard and REST API for runtime feature flags."""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.feature_flags import AVAILABLE_MODELS, get_flags, reset_flags, update_flags

router = APIRouter()

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentGuard — Control Panel</title>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d27; --surface2: #22263a;
    --border: #2e3350; --accent: #6366f1; --accent-hover: #818cf8;
    --green: #22c55e; --red: #ef4444; --yellow: #f59e0b;
    --text: #e2e8f0; --muted: #8892b0; --radius: 10px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 32px 16px; min-height: 100vh; }
  .container { max-width: 860px; margin: 0 auto; }
  header { display: flex; align-items: center; gap: 12px; margin-bottom: 32px; }
  header h1 { font-size: 1.5rem; font-weight: 700; }
  header .badge { background: var(--accent); color: #fff; font-size: 0.7rem; padding: 2px 8px; border-radius: 999px; font-weight: 600; letter-spacing: 0.05em; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
  .card.full { grid-column: 1 / -1; }
  .card-title { font-size: 0.75rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
  .card-title .dot { width: 8px; height: 8px; border-radius: 50%; }
  .dot-green { background: var(--green); }
  .dot-yellow { background: var(--yellow); }
  .dot-blue { background: #38bdf8; }
  .dot-purple { background: #a78bfa; }
  .row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border); }
  .row:last-child { border-bottom: none; padding-bottom: 0; }
  .row:first-child { padding-top: 0; }
  .row-label { font-size: 0.875rem; color: var(--text); }
  .row-label small { display: block; color: var(--muted); font-size: 0.75rem; margin-top: 2px; }
  .toggle { position: relative; display: inline-block; width: 44px; height: 24px; flex-shrink: 0; }
  .toggle input { opacity: 0; width: 0; height: 0; }
  .slider { position: absolute; cursor: pointer; inset: 0; background: var(--surface2); border-radius: 24px; transition: background 0.2s; border: 1px solid var(--border); }
  .slider:before { content: ''; position: absolute; width: 16px; height: 16px; left: 3px; top: 3px; background: var(--muted); border-radius: 50%; transition: 0.2s; }
  input:checked + .slider { background: var(--accent); border-color: var(--accent); }
  input:checked + .slider:before { transform: translateX(20px); background: #fff; }
  input:disabled + .slider { opacity: 0.4; cursor: not-allowed; }
  .num-input { background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 5px 10px; font-size: 0.875rem; width: 90px; text-align: right; }
  .num-input:focus { outline: none; border-color: var(--accent); }
  select { background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 5px 10px; font-size: 0.875rem; cursor: pointer; }
  select:focus { outline: none; border-color: var(--accent); }
  .status-bar { display: flex; align-items: center; justify-content: space-between; margin-top: 24px; padding: 12px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .status-text { font-size: 0.8rem; color: var(--muted); }
  .btn { background: var(--accent); color: #fff; border: none; border-radius: 6px; padding: 8px 18px; font-size: 0.875rem; font-weight: 600; cursor: pointer; transition: background 0.2s; }
  .btn:hover { background: var(--accent-hover); }
  .btn-ghost { background: transparent; color: var(--muted); border: 1px solid var(--border); }
  .btn-ghost:hover { color: var(--text); border-color: var(--text); background: transparent; }
  .toast { position: fixed; bottom: 24px; right: 24px; background: var(--surface2); border: 1px solid var(--border); color: var(--text); padding: 10px 18px; border-radius: 8px; font-size: 0.875rem; opacity: 0; transform: translateY(8px); transition: opacity 0.2s, transform 0.2s; pointer-events: none; z-index: 999; }
  .toast.show { opacity: 1; transform: translateY(0); }
  .toast.ok { border-color: var(--green); color: var(--green); }
  .toast.err { border-color: var(--red); color: var(--red); }
  .always-on { display: inline-flex; align-items: center; gap: 4px; font-size: 0.75rem; color: var(--muted); background: var(--surface2); border: 1px solid var(--border); border-radius: 4px; padding: 2px 8px; }
  .section-note { font-size: 0.75rem; color: var(--yellow); margin-bottom: 12px; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>AgentGuard</h1>
    <span class="badge">Control Panel</span>
  </header>

  <div class="grid">

    <!-- Guardrails -->
    <div class="card">
      <div class="card-title"><span class="dot dot-green"></span>Guardrails</div>

      <div class="row">
        <div class="row-label">Prompt Injection<small>Regex (always active)</small></div>
        <span class="always-on">Always On</span>
      </div>
      <div class="row">
        <div class="row-label">PII Masking<small>Post-call redaction (always active)</small></div>
        <span class="always-on">Always On</span>
      </div>
      <div class="row">
        <div class="row-label">Semantic Guard<small>LLM-judge injection check</small></div>
        <label class="toggle">
          <input type="checkbox" id="semantic_guard_enabled" onchange="save('semantic_guard_enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
      <div class="row">
        <div class="row-label">Toxicity Guard<small>LLM-judge abuse check</small></div>
        <label class="toggle">
          <input type="checkbox" id="toxicity_guard_enabled" onchange="save('toxicity_guard_enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
    </div>

    <!-- Guard Settings -->
    <div class="card">
      <div class="card-title"><span class="dot dot-yellow"></span>Guard Settings</div>
      <div class="row">
        <div class="row-label">Semantic model</div>
        <select id="semantic_guard_model" onchange="save('semantic_guard_model', this.value)">
          __MODEL_OPTIONS__
        </select>
      </div>
      <div class="row">
        <div class="row-label">Semantic timeout<small>seconds</small></div>
        <input type="number" class="num-input" id="semantic_guard_timeout" min="1" max="30" step="0.5" onchange="save('semantic_guard_timeout', parseFloat(this.value))">
      </div>
      <div class="row">
        <div class="row-label">Toxicity model</div>
        <select id="toxicity_guard_model" onchange="save('toxicity_guard_model', this.value)">
          __MODEL_OPTIONS__
        </select>
      </div>
      <div class="row">
        <div class="row-label">Toxicity timeout<small>seconds</small></div>
        <input type="number" class="num-input" id="toxicity_guard_timeout" min="1" max="30" step="0.5" onchange="save('toxicity_guard_timeout', parseFloat(this.value))">
      </div>
    </div>

    <!-- Semantic Cache -->
    <div class="card">
      <div class="card-title"><span class="dot dot-blue"></span>Semantic Cache</div>
      <div class="row">
        <div class="row-label">Enabled</div>
        <label class="toggle">
          <input type="checkbox" id="semantic_cache_enabled" onchange="save('semantic_cache_enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
      <div class="row">
        <div class="row-label">Similarity threshold<small>0.0 – 1.0 (higher = stricter match)</small></div>
        <input type="number" class="num-input" id="semantic_cache_threshold" min="0" max="1" step="0.01" onchange="save('semantic_cache_threshold', parseFloat(this.value))">
      </div>
      <div class="row">
        <div class="row-label">TTL<small>seconds</small></div>
        <input type="number" class="num-input" id="semantic_cache_ttl" min="60" max="86400" step="60" onchange="save('semantic_cache_ttl', parseInt(this.value))">
      </div>
    </div>

    <!-- Hybrid Search -->
    <div class="card">
      <div class="card-title"><span class="dot dot-blue"></span>Hybrid Search</div>
      <div class="row">
        <div class="row-label">Enabled<small>BM25 + vector RRF fusion</small></div>
        <label class="toggle">
          <input type="checkbox" id="hybrid_search_enabled" onchange="save('hybrid_search_enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
      <div class="row">
        <div class="row-label">Vector weight<small>0.0 – 1.0</small></div>
        <input type="number" class="num-input" id="hybrid_search_vector_weight" min="0" max="1" step="0.05" onchange="save('hybrid_search_vector_weight', parseFloat(this.value))">
      </div>
      <div class="row">
        <div class="row-label">BM25 weight<small>0.0 – 1.0</small></div>
        <input type="number" class="num-input" id="hybrid_search_bm25_weight" min="0" max="1" step="0.05" onchange="save('hybrid_search_bm25_weight', parseFloat(this.value))">
      </div>
      <div class="row">
        <div class="row-label">RRF constant<small>rank fusion smoothing (default 60)</small></div>
        <input type="number" class="num-input" id="hybrid_search_rrf_c" min="1" max="200" step="1" onchange="save('hybrid_search_rrf_c', parseInt(this.value))">
      </div>
    </div>

    <!-- LLM & Observability -->
    <div class="card">
      <div class="card-title"><span class="dot dot-purple"></span>LLM &amp; Observability</div>
      <div class="row">
        <div class="row-label">Default model</div>
        <select id="default_model" onchange="save('default_model', this.value)">
          __MODEL_OPTIONS__
        </select>
      </div>
      <div class="row">
        <div class="row-label">Agent model</div>
        <select id="agent_model" onchange="save('agent_model', this.value)">
          __MODEL_OPTIONS__
        </select>
      </div>
      <div class="row">
        <div class="row-label">Langfuse tracing<small>LangChain callback traces</small></div>
        <label class="toggle">
          <input type="checkbox" id="langfuse_tracing_enabled" onchange="save('langfuse_tracing_enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
      <div class="row">
        <div class="row-label">OpenTelemetry<small>Restart API server to apply</small></div>
        <label class="toggle">
          <input type="checkbox" id="otel_enabled" onchange="save('otel_enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
    </div>

  </div><!-- /grid -->

  <div class="status-bar">
    <span class="status-text" id="status-text">Loading…</span>
    <button class="btn btn-ghost" onclick="resetAll()">Reset to defaults</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const BOOL_KEYS = ['semantic_guard_enabled','toxicity_guard_enabled','semantic_cache_enabled','otel_enabled','hybrid_search_enabled'];

function showToast(msg, type='ok') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show ' + type;
  setTimeout(() => t.className = 'toast', 2000);
}

async function load() {
  const res = await fetch('/api/config');
  const cfg = await res.json();
  for (const [k, v] of Object.entries(cfg)) {
    const el = document.getElementById(k);
    if (!el) continue;
    if (el.type === 'checkbox') el.checked = !!v;
    else el.value = v;
  }
  document.getElementById('status-text').textContent =
    'Last loaded: ' + new Date().toLocaleTimeString();
}

async function save(key, value) {
  try {
    const res = await fetch('/api/config', {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({[key]: value})
    });
    if (!res.ok) throw new Error(await res.text());
    showToast('Saved', 'ok');
    document.getElementById('status-text').textContent =
      'Saved: ' + new Date().toLocaleTimeString();
  } catch(e) {
    showToast('Error: ' + e.message, 'err');
  }
}

async function resetAll() {
  if (!confirm('Reset all flags to defaults?')) return;
  await fetch('/api/config/reset', {method: 'POST'});
  await load();
  showToast('Reset to defaults', 'ok');
}

load();
</script>
</body>
</html>
"""


def _build_model_options(models: list[str]) -> str:
    return "".join(f'<option value="{m}">{m}</option>' for m in models)


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard() -> HTMLResponse:
    html = _DASHBOARD_HTML.replace(
        "__MODEL_OPTIONS__", _build_model_options(AVAILABLE_MODELS)
    )
    return HTMLResponse(content=html)


@router.get("/api/config")
async def get_config() -> dict[str, Any]:
    return get_flags()


@router.patch("/api/config")
async def patch_config(updates: dict[str, Any]) -> dict[str, Any]:
    return update_flags(updates)


@router.post("/api/config/reset")
async def reset_config() -> dict[str, Any]:
    return reset_flags()
