"""Playwright demo: prospect chatting with the AgentGuard RAG chatbot in Open WebUI.

Simulates a realistic B2B SaaS sales conversation that exercises plan/pricing
retrieval, feature confirmation, trial policy, and discount approval tiers.

Usage:
    python -m scripts.demo_prospect_chat                      # headed (watch it run)
    python -m scripts.demo_prospect_chat --headless           # CI / no window
    python -m scripts.demo_prospect_chat --url http://localhost:3100 --model agentguard-rag
    python -m scripts.demo_prospect_chat --email user@acme.com
    python -m scripts.demo_prospect_chat --screenshot-dir docs/assets/screenshots # save screenshots
    python -m scripts.demo_prospect_chat --slow 500           # slower for live demos

Environment variable overrides:
    OPENWEBUI_URL, OPENWEBUI_EMAIL, OPENWEBUI_PASSWORD, OPENWEBUI_MODEL

Security note:
    Prefer OPENWEBUI_PASSWORD env var (or interactive prompt) over --password
    to avoid exposing credentials in shell history or process listings.

Requirements:
    pip install playwright
    playwright install chromium
"""

import argparse
import getpass
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright

DEFAULT_OPENWEBUI_URL = os.getenv("OPENWEBUI_URL", "http://localhost:3100")
DEFAULT_EMAIL = os.getenv("OPENWEBUI_EMAIL", "playwright@local.dev")
DEFAULT_PASSWORD = os.getenv("OPENWEBUI_PASSWORD", "")
DEFAULT_MODEL = os.getenv("OPENWEBUI_MODEL", "agentguard-rag")

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

def _login(page: Page, openwebui_url: str, email: str, password: str) -> None:
    page.goto(openwebui_url)
    page.wait_for_load_state("networkidle")
    if "/auth" not in page.url:
        print("  Already logged in.")
        return
    page.locator('input[autocomplete="email"], input[type="email"]').fill(email)
    page.locator('input[type="password"]').fill(password)
    page.locator('button[type="submit"]').click()
    page.wait_for_url(f"{openwebui_url}/**", timeout=15_000)
    print(f"  Logged in as {email}.")


def _new_chat(page: Page, openwebui_url: str) -> None:
    page.goto(f"{openwebui_url}/")
    page.wait_for_load_state("networkidle")
    new_btn = page.locator('button:has-text("New Chat")').first
    if new_btn.is_visible():
        new_btn.click()
        page.wait_for_load_state("networkidle")


def _select_model(page: Page, model: str) -> None:
    # Already correct model?
    if page.locator(f'button:has-text("{model}")').is_visible():
        print(f"  Model: {model} (already selected).")
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
        search.fill(model)

    # Click matching option
    page.locator(
        f'[role="option"]:has-text("{model}"), li:has-text("{model}")'
    ).first.click()
    print(f"  Model selected: {model}.")


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
    openwebui_url: str,
    email: str,
    password: str,
    model: str,
    headed: bool = True,
    slow_mo: int = 150,
    screenshot_dir: Path | None = None,
) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, slow_mo=slow_mo if headed else 0)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        print("\n── Login ─────────────────────────────")
        _login(page, openwebui_url=openwebui_url, email=email, password=password)

        print("── New chat ──────────────────────────")
        _new_chat(page, openwebui_url=openwebui_url)

        print("── Select model ──────────────────────")
        _select_model(page, model=model)

        for i, question in enumerate(QUESTIONS, 1):
            print(f"\n── Q{i} {'─'*40}")
            print(f"  {question}")
            _send(page, question)
            response = _wait_for_response(page)
            # Strip model-name header that Open WebUI prepends
            clean = response.replace(model, "").strip()
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
    parser.add_argument("--url", default=DEFAULT_OPENWEBUI_URL,
                        help=f"Open WebUI base URL (default: {DEFAULT_OPENWEBUI_URL})")
    parser.add_argument("--email", default=DEFAULT_EMAIL,
                        help=f"Open WebUI login email (default: {DEFAULT_EMAIL})")
    parser.add_argument("--password", default=None,
                        help="Open WebUI login password (prefer OPENWEBUI_PASSWORD env var)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Open WebUI model to select (default: {DEFAULT_MODEL})")
    parser.add_argument("--headless", action="store_true",
                        help="Run without a visible browser window")
    parser.add_argument("--slow", type=int, default=150,
                        help="Slow-mo delay in ms (headed mode only, default: 150)")
    parser.add_argument("--screenshot-dir", default=None,
                        help="Directory to save per-question screenshots")
    args = parser.parse_args()

    parsed_url = urlparse(args.url)
    if not parsed_url.scheme or not parsed_url.netloc:
        parser.error(f"Invalid --url value: {args.url!r}. Expected absolute URL, e.g. http://localhost:3100")

    password = args.password or DEFAULT_PASSWORD
    if not password:
        password = getpass.getpass("Open WebUI password: ")

    shot_dir = Path(args.screenshot_dir) if args.screenshot_dir else None
    if shot_dir:
        shot_dir.mkdir(parents=True, exist_ok=True)

    run_demo(
        openwebui_url=args.url,
        email=args.email,
        password=password,
        model=args.model,
        headed=not args.headless,
        slow_mo=args.slow,
        screenshot_dir=shot_dir,
    )


if __name__ == "__main__":
    main()
