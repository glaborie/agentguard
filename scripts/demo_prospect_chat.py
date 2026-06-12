"""Playwright demo: prospect chatting with the AgentGuard RAG chatbot in Open WebUI.

Simulates a realistic B2B SaaS sales conversation that exercises plan/pricing
retrieval, feature confirmation, trial policy, and discount approval tiers.

Usage:
    python -m scripts.demo_prospect_chat                      # headed (watch it run)
    python -m scripts.demo_prospect_chat --headless           # CI / no window
    python -m scripts.demo_prospect_chat --screenshot-dir docs/assets/screenshots # save screenshots
    python -m scripts.demo_prospect_chat --slow 500           # slower for live demos

Requirements:
    pip install playwright
    playwright install chromium
"""

import argparse
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

OPENWEBUI_URL = "http://localhost:3100"
EMAIL = "playwright@local.dev"
PASSWORD = "playwright"
MODEL = "agentguard-rag"

QUESTIONS = [
    (
        "Hi! We're a 200-person B2B SaaS company evaluating CRMs. "
        "Can you give me an overview of NorthstarCRM's main plans and pricing?"
    ),
    (
        "We need Salesforce integration and SSO for our security team. "
        "Do both come with the Business plan, or do we need Enterprise?"
    ),
    "Perfect. Is there a free trial so we can test it before committing to a Business plan contract?",
    (
        "We're hoping to sign before end of quarter. "
        "If we commit to an annual Business plan for 200 users today, "
        "is there any discount you can offer?"
    ),
]


# ── Browser helpers ────────────────────────────────────────────────────────────

def _login(page: Page) -> None:
    page.goto(OPENWEBUI_URL)
    page.wait_for_load_state("networkidle")
    if "/auth" not in page.url:
        print("  Already logged in.")
        return
    page.locator('input[autocomplete="email"], input[type="email"]').fill(EMAIL)
    page.locator('input[type="password"]').fill(PASSWORD)
    page.locator('button[type="submit"]').click()
    page.wait_for_url(f"{OPENWEBUI_URL}/**", timeout=15_000)
    print(f"  Logged in as {EMAIL}.")


def _new_chat(page: Page) -> None:
    page.goto(f"{OPENWEBUI_URL}/")
    page.wait_for_load_state("networkidle")
    new_btn = page.locator('button:has-text("New Chat")').first
    if new_btn.is_visible():
        new_btn.click()
        page.wait_for_load_state("networkidle")


def _select_model(page: Page) -> None:
    # Already correct model?
    if page.locator(f'button:has-text("{MODEL}")').is_visible():
        print(f"  Model: {MODEL} (already selected).")
        return

    # Open model picker — the button at the top of the chat area
    picker = page.locator(
        '[id*="model"], [class*="model-selector"], button[class*="model"],'
        'button[aria-label*="model" i]'
    ).first
    picker.click()

    # Search box inside the dropdown
    search = page.locator('input[placeholder*="earch"]').first
    if search.is_visible(timeout=2_000):
        search.fill(MODEL)

    # Click matching option
    page.locator(
        f'[role="option"]:has-text("{MODEL}"), li:has-text("{MODEL}")'
    ).first.click()
    print(f"  Model selected: {MODEL}.")


def _send(page: Page, text: str) -> None:
    page.evaluate(
        """(text) => {
            const el = document.querySelector('#chat-input');
            el.focus();
            el.textContent = text;
            el.dispatchEvent(new Event('input', {bubbles: true}));
        }""",
        text,
    )
    time.sleep(0.3)
    # Submit button scoped to the input's parent form
    page.evaluate("""() => {
        const el = document.querySelector('#chat-input');
        const form = el.closest('form')
            ?? el.parentElement?.parentElement;
        form.querySelector('button[type="submit"]').click();
    }""")


def _wait_for_response(page: Page, timeout: int = 120) -> str:
    """Poll until the last message text stops changing (streaming complete)."""
    deadline = time.time() + timeout
    prev, stable = "", 0
    while time.time() < deadline:
        cur = page.evaluate("""() => {
            const all = Array.from(document.querySelectorAll('[class*="message"]'))
                .map(el => el.innerText?.trim())
                .filter(t => t && t.length > 10);
            return all.at(-1) ?? '';
        }""")
        if cur and cur == prev:
            stable += 1
            if stable >= 4:   # unchanged for 2 s
                return cur
        else:
            stable, prev = 0, cur
        time.sleep(0.5)
    return prev


# ── Main demo ─────────────────────────────────────────────────────────────────

def run_demo(
    headed: bool = True,
    slow_mo: int = 150,
    screenshot_dir: Path | None = None,
) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, slow_mo=slow_mo if headed else 0)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        print("\n── Login ─────────────────────────────")
        _login(page)

        print("── New chat ──────────────────────────")
        _new_chat(page)

        print("── Select model ──────────────────────")
        _select_model(page)

        for i, question in enumerate(QUESTIONS, 1):
            print(f"\n── Q{i} {'─'*40}")
            print(f"  {question}")
            _send(page, question)
            response = _wait_for_response(page)
            # Strip model-name header that Open WebUI prepends
            clean = response.replace(MODEL, "").strip()
            print(f"  → {clean[:400]}")

            if screenshot_dir:
                path = screenshot_dir / f"demo_q{i}.png"
                page.screenshot(path=str(path), full_page=False)
                print(f"  Screenshot: {path}")

            time.sleep(1)

        print("\n── Done ──────────────────────────────")
        if headed:
            input("Press Enter to close the browser…")
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prospect demo in Open WebUI")
    parser.add_argument("--headless", action="store_true",
                        help="Run without a visible browser window")
    parser.add_argument("--slow", type=int, default=150,
                        help="Slow-mo delay in ms (headed mode only, default: 150)")
    parser.add_argument("--screenshot-dir", default=None,
                        help="Directory to save per-question screenshots")
    args = parser.parse_args()

    shot_dir = Path(args.screenshot_dir) if args.screenshot_dir else None
    if shot_dir:
        shot_dir.mkdir(parents=True, exist_ok=True)

    run_demo(headed=not args.headless, slow_mo=args.slow, screenshot_dir=shot_dir)


if __name__ == "__main__":
    main()
