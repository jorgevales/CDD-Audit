"""One-shot Copilot picker checks: one temporary tab, no messages or uploads."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import sys
import time

from .config import APP_DIR, WorkflowConfig
from .models import MODEL_OPTIONS


async def check_models(config: WorkflowConfig) -> dict:
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "blocked", "models": []}
    try:
        from playwright.async_api import async_playwright
        refs = APP_DIR / "Initial sanitized reference files"
        if str(refs) not in sys.path:
            sys.path.insert(0, str(refs))
        os.environ["COPILOT_BASE_MESSAGE_PATH"] = str(refs / "resources" / "base_message_sanitized.md")
        engine = importlib.import_module("resources.implementation_sanitized")
        engine.load_playwright()
        endpoint = f"http://127.0.0.1:{int(config.edge_debug_port)}"
        if await asyncio.to_thread(engine.get_cdp_version, endpoint) is None:
            edge_path = engine.find_edge_executable(Path(config.edge_executable) if config.edge_executable else None)
            await asyncio.to_thread(engine.launch_edge, edge_path, endpoint, int(config.edge_debug_port),
                                    config.path("edge_profile_dir"), 15, False)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(endpoint, timeout=5000)
            if not browser.contexts:
                raise RuntimeError("The dedicated Edge review browser has no available context.")
            page = await browser.contexts[0].new_page()
            picker_ready = False
            try:
                await page.goto("https://m365.cloud.microsoft/chat", wait_until="domcontentloaded", timeout=20000)
                try:
                    await page.locator("#gptModeSwitcher,button[aria-label*='Model Selector' i]").first.wait_for(state="visible", timeout=10000)
                except Exception:
                    if "login.microsoftonline.com" in page.url:
                        raise RuntimeError("Sign in to Microsoft 365 in the dedicated Edge review profile, then check models again.")
                    raise RuntimeError("Copilot Chat's model picker is unavailable. Open Copilot in the dedicated review profile and check account access.")
                picker_ready = True
                report["account_context"] = await page.get_by_role("button").evaluate_all(
                    "nodes => nodes.map(n => n.getAttribute('aria-label') || '').filter(t => /(?:Work|Personal) account/i.test(t))"
                )
                report["copilot_plan"] = await page.get_by_text("M365 Copilot (Basic)", exact=True).count() > 0 and "M365 Copilot (Basic)" or "Copilot Chat"
                available = []
                await page.locator("#gptModeSwitcher,button[aria-label*='Model Selector' i]").first.click()
                await page.wait_for_timeout(250)
                for provider in ("OpenAI", "Claude", "Anthropic"):
                    trigger = page.locator(f"[data-test-id='gptSubMenuModelTrigger-{provider}'],[data-testid='gptSubMenuModelTrigger-{provider}']").first
                    if await trigger.count() and await trigger.is_visible():
                        await trigger.click()
                        await page.wait_for_timeout(200)
                        available.extend(await page.get_by_role("menuitemradio").evaluate_all(
                            "nodes => nodes.filter(n => n.offsetWidth || n.offsetHeight).map(n => ({label:n.innerText,checked:n.getAttribute('aria-checked'),model_test_ids:[...n.querySelectorAll('svg[data-testid],svg[data-test-id]')].map(s => s.getAttribute('data-testid') || s.getAttribute('data-test-id'))}))"
                        ))
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(100)
                report["available_radios"] = available
                await page.keyboard.press("Escape")
                await page.keyboard.press("Escape")
                for option in MODEL_OPTIONS:
                    started = time.perf_counter()
                    result = {**option, "selected": False}
                    try:
                        await engine.click_model_option(page, option["value"], engine.FAST_MODEL_TIMEOUT_MS, verbose=False)
                        result["selected"] = True
                    except Exception as exc:
                        result["error"] = str(exc)[:500]
                        await page.keyboard.press("Escape")
                        await page.keyboard.press("Escape")
                    result["selection_ms"] = round((time.perf_counter() - started) * 1000)
                    report["models"].append(result)
                report["status"] = "verified" if all(item["selected"] for item in report["models"]) else "partial"
            finally:
                if picker_ready:
                    try:
                        await engine.click_model_option(page, config.default_model, engine.FAST_MODEL_TIMEOUT_MS, verbose=False)
                        report["preferred_model_restored"] = True
                    except Exception:
                        report["preferred_model_restored"] = False
                await page.close()
    except Exception as exc:
        report["error"] = str(exc)[:600]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config = WorkflowConfig.load(args.config) if args.config else WorkflowConfig.load()
    if args.port:
        config.edge_debug_port = args.port
    report = asyncio.run(check_models(config))
    serialized = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
