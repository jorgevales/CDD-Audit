from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
import time
from typing import Protocol
from urllib.parse import urlparse

from .edge_session import EdgeSession, get_cdp_version, validate_existing_profile
from .errors import CopilotUIError, PostSendCancelledError, SubmissionUncertainError
from .models import QueueItem


COPILOT_URL = "https://m365.cloud.microsoft/chat"
EDITOR_SELECTORS = (
    "#m365-chat-editor-target-element",
    "[data-testid*='chat-editor' i] [contenteditable='true']",
    "[data-test-id*='chat-editor' i] [contenteditable='true']",
    "[role='textbox'][contenteditable='true'][aria-label*='Copilot' i]",
    "[role='textbox'][aria-label*='Message' i]",
    "textarea[aria-label*='Copilot' i]",
    "main [contenteditable='true'][role='textbox']",
    "div[contenteditable='true'][role='textbox']",
    "textarea[placeholder*='message' i]",
    "textarea[aria-label*='message' i]",
)
ATTACH_SELECTORS = (
    "input[type='file']",
    "#plus-menu-container input[type='file']",
)
SEND_SELECTORS = (
    "button[aria-label='Send']",
    "button[aria-label^='Send ']:not([aria-label*='stop' i])",
    "button[data-testid='submit-button']",
    "button[type='submit'][aria-label*='send' i]:not([aria-label*='stop' i])",
)
ATTACH_BUTTON_SELECTORS = (
    "#plus-menu-container button[data-testid='PlusMenuButton']",
    "button[data-testid='chat-input-attach-button']",
    "button[data-test-id='chat-input-attach-button']",
    "button[aria-label='Add and manage sources']",
)
MODEL_PICKER_SELECTORS = (
    "#gptModeSwitcher",
    "button[aria-label*='Model Selector' i]",
    "button[aria-label*='mode selector' i]",
)


@dataclass(frozen=True)
class CaseOutcome:
    status: str
    detail: str = ""


class CopilotAdapter(Protocol):
    async def start(self) -> None: ...
    async def process(self, item: QueueItem) -> CaseOutcome: ...
    async def close(self) -> None: ...


class SimulationAdapter:
    def __init__(self, outcomes: dict[tuple[str, str], str] | None = None) -> None:
        self.outcomes = outcomes or {}
        self.processed: list[tuple[str, str]] = []

    async def start(self) -> None:
        return

    async def process(self, item: QueueItem) -> CaseOutcome:
        self.processed.append(item.key)
        return CaseOutcome(self.outcomes.get(item.key, "successful"), "synthetic simulation")

    async def close(self) -> None:
        return


class PlaywrightCopilotAdapter:
    """Visible, bounded Microsoft 365 Copilot Chat adapter.

    A new chat is used per case. Send is committed only when both the composer
    clears and a matching user turn appears. Any ambiguous post-click state is
    raised as requiring manual review and is never resent automatically.
    """

    def __init__(self, edge: EdgeSession, *, model: str | None = None, startup_timeout: float = 180, response_timeout: float = 1800) -> None:
        self.edge = edge
        self.model = model
        self.startup_timeout = startup_timeout
        self.response_timeout = response_timeout
        self.manager = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.startup_diagnostics: dict[str, object] = {"phase": "not_started"}
        self.case_diagnostics: dict[str, object] = {"phase": "not_started"}

    @staticmethod
    def _ready_for_queue(editor_visible: bool, picker_visible: bool | None, model_requested: bool) -> bool:
        return editor_visible and (not model_requested or bool(picker_visible))

    async def _first_visible(self, selectors: tuple[str, ...], timeout: float = 0):
        deadline = time.monotonic() + timeout
        while True:
            for selector in selectors:
                locator = self.page.locator(selector)
                for index in range(min(await locator.count(), 20)):
                    item = locator.nth(index)
                    if await item.is_visible():
                        return item
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(0.15)

    async def start(self) -> None:
        self.startup_diagnostics = {"phase": "edge_startup", "cdp_connect_attempts": 0}
        try:
            await self._start_impl()
        except Exception as exc:
            if not getattr(exc, "diagnostic_stage", None):
                exc.diagnostic_stage = "copilot_startup"
            diagnostics = getattr(exc, "diagnostics", {})
            exc.diagnostics = {**diagnostics, "copilot": self.startup_diagnostics}
            raise

    async def _start_impl(self) -> None:
        self.edge.ensure_started(timeout=min(self.startup_timeout, 120))
        self.startup_diagnostics.update(phase="playwright_start", edge_attempts=self.edge.startup_trace)
        print("Edge endpoint ready; connecting automation.", flush=True)
        from playwright.async_api import async_playwright

        self.manager = async_playwright()
        self.playwright = await self.manager.start()
        self.startup_diagnostics["phase"] = "cdp_connect"
        deadline = time.monotonic() + min(self.startup_timeout, 45)
        attempts = 0
        while time.monotonic() < deadline:
            payload = await asyncio.to_thread(get_cdp_version, self.edge.endpoint)
            if payload:
                route = payload["webSocketDebuggerUrl"] if attempts % 2 == 0 else self.edge.endpoint
                budget = min((5, 10, 20)[min(attempts, 2)], deadline - time.monotonic())
                if budget > 0:
                    attempts += 1
                    self.startup_diagnostics["cdp_connect_attempts"] = attempts
                    try:
                        browser = await asyncio.wait_for(
                            self.playwright.chromium.connect_over_cdp(route, timeout=max(1000, int(budget * 1000))),
                            timeout=budget + 0.25,
                        )
                        if browser.is_connected() and browser.contexts:
                            self.browser = browser
                            self.startup_diagnostics["cdp_context_count"] = len(browser.contexts)
                            break
                    except Exception as exc:
                        self.startup_diagnostics["last_cdp_error_type"] = type(exc).__name__
            await asyncio.sleep(min(0.25, max(0, deadline - time.monotonic())))
        if self.browser is None:
            raise CopilotUIError("Edge opened its local endpoint, but Playwright could not connect within the startup limit.")
        await self._activate_copilot()

    async def _activate_copilot(self) -> None:
        self.startup_diagnostics["phase"] = "profile_ownership"
        print("Automation connected; checking the Edge profile.", flush=True)
        await asyncio.to_thread(validate_existing_profile, self.edge.port, self.edge.profile)
        self.startup_diagnostics["phase"] = "copilot_navigation"
        print("Edge profile verified; opening Copilot.", flush=True)
        self.context = self.browser.contexts[0]
        retained = next(
            (
                page for page in self.context.pages
                if urlparse(page.url).hostname == "m365.cloud.microsoft"
                and urlparse(page.url).path.startswith("/chat")
            ),
            None,
        )
        self.startup_diagnostics.update(tab_reused=retained is not None, readiness_attempts=[], readiness_checks=0)
        self.startup_diagnostics["phase"] = "copilot_readiness"
        ready_start = time.monotonic()
        fast_deadline = ready_start + 30
        if retained is not None:
            self.page = retained
            await retained.bring_to_front()
            attempt_start = time.monotonic()
            if await self._wait_for_ready(retained, 2):
                self._record_readiness_attempt("retained_tab", "composer_visible", attempt_start)
                await self._finish_readiness("retained tab", "retained_tab")
                return
            self._record_readiness_attempt("retained_tab", "not_ready", attempt_start)
            # The old tab may contain an unsent draft. Never reload or navigate it.
        self.page = await asyncio.wait_for(self.context.new_page(), timeout=5)
        await self.page.bring_to_front()
        print("Checking a new Copilot tab in the verified Edge session.", flush=True)
        attempt_start = time.monotonic()
        await self._navigate_owned_tab(fast_deadline)
        if await self._wait_for_ready(self.page, min(8, max(0, fast_deadline - time.monotonic()))):
            self._record_readiness_attempt("new_tab", "composer_visible", attempt_start)
            await self._finish_readiness("new tab", "new_tab")
            return
        category = self._page_category(self.page)
        self._record_readiness_attempt("new_tab", "auth_required" if category == "login" else "not_ready", attempt_start)
        if category == "login":
            await self._wait_for_sign_in()
            return
        print("Copilot composer is still unavailable; retrying navigation in the new tab.", flush=True)
        attempt_start = time.monotonic()
        await self._navigate_owned_tab(fast_deadline)
        if await self._wait_for_ready(self.page, max(0, fast_deadline - time.monotonic())):
            self._record_readiness_attempt("new_tab_navigation_retry", "composer_visible", attempt_start)
            await self._finish_readiness("new tab navigation retry", "new_tab_navigation_retry")
            return
        category = self._page_category(self.page)
        self._record_readiness_attempt("new_tab_navigation_retry", "auth_required" if category == "login" else "not_ready", attempt_start)
        if category == "login":
            await self._wait_for_sign_in()
            return
        await self._capture_readiness_state()
        self.startup_diagnostics["readiness_elapsed_ms"] = round((time.monotonic() - ready_start) * 1000)
        raise CopilotUIError("Copilot did not expose a usable composer after bounded new-tab recovery. No case was sent.")

    @staticmethod
    def _page_category(page) -> str:
        login_hosts = {"login.microsoftonline.com", "login.live.com", "account.microsoft.com"}
        host = urlparse(page.url).hostname or ""
        if host in login_hosts or any(
            (urlparse(frame.url).hostname or "") in login_hosts
            for frame in getattr(page, "frames", [])[1:8]
        ):
            return "login"
        return "copilot" if host == "m365.cloud.microsoft" else "other"

    def _record_readiness_attempt(self, method: str, result: str, started_at: float) -> None:
        self.startup_diagnostics["readiness_attempts"].append({
            "method": method,
            "result": result,
            "elapsed_ms": round((time.monotonic() - started_at) * 1000),
        })

    async def _navigate_owned_tab(self, deadline: float) -> None:
        remaining = min(10, max(0.1, deadline - time.monotonic()))
        try:
            response = await self.page.goto(COPILOT_URL, wait_until="commit", timeout=int(remaining * 1000))
            status = response.status if response is not None else None
            outcome = "auth" if status == 401 else "forbidden" if status == 403 else "success" if status is not None else "no_response"
            self.startup_diagnostics["navigation_outcome"] = outcome
            self.startup_diagnostics["access_denied_indicator"] = status == 403
        except Exception as exc:
            self.startup_diagnostics["navigation_outcome"] = "timeout" if type(exc).__name__ == "TimeoutError" else "error"
            self.startup_diagnostics["last_navigation_error_type"] = type(exc).__name__

    async def _wait_for_ready(self, page, timeout: float) -> bool:
        self.page = page
        deadline = time.monotonic() + max(0, timeout)
        while True:
            self.startup_diagnostics["readiness_checks"] = int(self.startup_diagnostics.get("readiness_checks", 0)) + 1
            try:
                editor_ready = bool(await self._first_visible(EDITOR_SELECTORS))
                picker_ready = bool(await self._first_visible(MODEL_PICKER_SELECTORS)) if self.model else None
                self.startup_diagnostics.update(editor_visible=editor_ready, model_picker_visible=picker_ready)
                if self._ready_for_queue(editor_ready, picker_ready, bool(self.model)):
                    return True
            except Exception as exc:
                self.startup_diagnostics["last_readiness_error_type"] = type(exc).__name__
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(min(0.2, max(0, deadline - time.monotonic())))

    async def _wait_for_sign_in(self) -> None:
        print("Microsoft sign-in is visible; complete it in Edge.", flush=True)
        attempt_start = time.monotonic()
        if await self._wait_for_ready(self.page, self.startup_timeout):
            self._record_readiness_attempt("sign_in_completed", "composer_visible", attempt_start)
            await self._finish_readiness("sign-in completed", "sign_in_completed")
            return
        self._record_readiness_attempt("sign_in_completed", "not_ready", attempt_start)
        await self._capture_readiness_state()
        self.startup_diagnostics["readiness_elapsed_ms"] = sum(
            int(attempt["elapsed_ms"]) for attempt in self.startup_diagnostics["readiness_attempts"]
        )
        raise CopilotUIError("Copilot sign-in did not reach a usable composer before the timeout. No case was sent.")

    async def _finish_readiness(self, label: str, method: str) -> None:
        if self.model:
            self.startup_diagnostics["phase"] = "model_selection"
            await self._select_model(self.model)
        self.startup_diagnostics.update(phase="ready", readiness_method=method)
        print(f"\033[92mCopilot readiness method: {label}\033[0m", flush=True)
        print("Copilot composer ready; starting the case queue.", flush=True)

    async def _capture_readiness_state(self) -> None:
        page = self.page
        self.startup_diagnostics["page_category"] = self._page_category(page)
        self.startup_diagnostics["login_indicator"] = self._page_category(page) == "login"
        selectors = {
            "primary_editor": "#m365-chat-editor-target-element",
            "testid_editor": "[data-testid*='chat-editor' i] [contenteditable='true'],[data-test-id*='chat-editor' i] [contenteditable='true']",
            "role_textbox": "[role='textbox'][contenteditable='true']",
            "message_textarea": "textarea[placeholder*='message' i],textarea[aria-label*='message' i]",
        }
        counts = {}
        for label, selector in selectors.items():
            try:
                counts[label] = min(100, await asyncio.wait_for(page.locator(selector).count(), timeout=1))
            except Exception:
                counts[label] = 0
        self.startup_diagnostics["editor_selector_counts"] = counts
        frames = getattr(page, "frames", [])
        self.startup_diagnostics["frame_count"] = max(0, len(frames) - 1)
        self.startup_diagnostics["editor_in_frame"] = False
        for frame in frames[1:6]:
            try:
                if await asyncio.wait_for(frame.locator("#m365-chat-editor-target-element").count(), timeout=0.5):
                    self.startup_diagnostics["editor_in_frame"] = True
                    break
            except Exception:
                continue
        try:
            state = await asyncio.wait_for(page.evaluate("() => document.readyState"), timeout=1)
        except Exception:
            state = "unknown"
        self.startup_diagnostics["document_state"] = state if state in {"loading", "interactive", "complete"} else "unknown"

    async def _fresh_chat(self) -> None:
        await self.page.goto(COPILOT_URL, wait_until="commit", timeout=30000)
        existing = self.page.locator("[data-testid='chatQuestion'],.fai-UserMessage")
        if await existing.count():
            controls = self.page.locator("button[aria-label*='New chat' i],a[aria-label*='New chat' i]")
            if await controls.count() and await controls.first.is_visible():
                await controls.first.click()
                deadline = time.monotonic() + 10
                while await existing.count() and time.monotonic() < deadline:
                    await asyncio.sleep(0.1)
        editor = await self._first_visible(EDITOR_SELECTORS, 30)
        if editor is None:
            raise CopilotUIError("A fresh Copilot composer did not become available.")
        if (await self._editor_text(editor)).strip():
            raise CopilotUIError("The fresh Copilot composer is not empty.")

    async def _editor_text(self, editor) -> str:
        tag = str(await editor.evaluate("node => node.tagName || ''")).casefold()
        return await editor.input_value() if tag in {"textarea", "input"} else await editor.inner_text()

    async def _attach(self, item: QueueItem) -> None:
        inputs = self.page.locator(",".join(ATTACH_SELECTORS))
        if not await inputs.count():
            # Reveal the file input through the visible attachment control.
            button = self.page.locator(",".join(ATTACH_BUTTON_SELECTORS)).first
            if not await button.is_visible():
                raise CopilotUIError("The Copilot attachment control is unavailable.")
            await button.click()
            inputs = self.page.locator(",".join(ATTACH_SELECTORS))
        if not await inputs.count():
            raise CopilotUIError("The Copilot file input did not become available.")
        await inputs.first.set_input_files([str(path) for path in item.attachments.paths])
        expected = {path.name.casefold() for path in item.attachments.paths}
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            names = await self.page.locator("button[aria-label^='Remove attachment ']").evaluate_all(
                "nodes => nodes.map(n => (n.getAttribute('aria-label') || '').replace(/^Remove attachment /i, ''))"
            )
            if expected <= {str(name).casefold() for name in names}:
                send = await self._first_visible(SEND_SELECTORS)
                if send is not None and await send.is_enabled():
                    return
            await asyncio.sleep(0.25)
        raise CopilotUIError("Attachments did not finish loading before the bounded timeout.")

    async def _select_model(self, label: str) -> None:
        picker = await self._first_visible(MODEL_PICKER_SELECTORS, 10)
        if picker is None:
            raise CopilotUIError("The Copilot model picker is unavailable.")
        await picker.click()
        pattern = re.compile(rf"^{re.escape(label)}$", re.IGNORECASE)
        options = self.page.get_by_role("radio", name=pattern).or_(
            self.page.get_by_role("menuitemradio", name=pattern)
        )
        if not await options.count():
            options = self.page.get_by_text(pattern, exact=True)
        for index in range(await options.count()):
            option = options.nth(index)
            if await option.is_visible():
                await option.click()
                return
        raise CopilotUIError(f"The requested Copilot model is not available in the visible picker: {label}")

    async def _response_text(self) -> str:
        selectors = (
            "[data-testid='copilot-message-reply-div'] [data-message-type='Chat']",
            "[data-testid='markdown-reply']",
            ".fai-CopilotMessage__content",
        )
        candidates = []
        for selector in selectors:
            locator = self.page.locator(selector)
            for index in range(await locator.count()):
                item = locator.nth(index)
                if await item.is_visible():
                    candidates.append(await item.inner_text())
        return candidates[-1] if candidates else ""

    async def process(self, item: QueueItem) -> CaseOutcome:
        self.case_diagnostics = {"phase": "fresh_chat", "attachment_count": len(item.attachments.paths), "send_attempted": False}
        try:
            return await self._process_impl(item)
        except Exception as exc:
            if not getattr(exc, "diagnostic_stage", None):
                exc.diagnostic_stage = "case_processing"
            exc.diagnostics = {**getattr(exc, "diagnostics", {}), "case": self.case_diagnostics}
            raise

    async def _process_impl(self, item: QueueItem) -> CaseOutcome:
        await self._fresh_chat()
        self.case_diagnostics["phase"] = "attachment_upload"
        await self._attach(item)
        self.case_diagnostics["phase"] = "composer_fill"
        editor = await self._first_visible(EDITOR_SELECTORS, 10)
        if editor is None:
            raise CopilotUIError("The Copilot composer disappeared before the prompt could be entered.")
        await editor.fill(item.prompt)
        actual = (await self._editor_text(editor)).replace("\r\n", "\n").strip()
        if actual != item.prompt.strip():
            raise CopilotUIError("The Copilot composer did not preserve the complete prompt; Send was not clicked.")
        send = await self._first_visible(SEND_SELECTORS, 10)
        if send is None or not await send.is_enabled():
            raise CopilotUIError("The Copilot Send control is not ready.")
        try:
            self.case_diagnostics.update(phase="send_confirmation", send_attempted=True)
            # From this point onward, every failure is potentially post-send and
            # must never be treated as an automatically retryable ordinary error.
            await send.click(no_wait_after=True)
            commit_deadline = time.monotonic() + 20
            committed = False
            while time.monotonic() < commit_deadline:
                composer_empty = not (await self._editor_text(editor)).strip()
                user_text = await self.page.locator("[data-testid='chatQuestion'],.fai-UserMessage").all_inner_texts()
                if composer_empty and any(item.case.change_id in text for text in user_text):
                    committed = True
                    break
                await asyncio.sleep(0.2)
            if not committed:
                raise SubmissionUncertainError("Send was attempted, but a cleared composer and matching user turn were not both observed.")
            self.case_diagnostics["phase"] = "response_capture"
            deadline = time.monotonic() + self.response_timeout
            stable_text = ""
            stable = 0
            while time.monotonic() < deadline:
                text = await self._response_text()
                status_match = re.search(
                    rf"^Case result:\s*{re.escape(item.case.change_id)}\s*\|\s*(successful|failed)\s*$",
                    text,
                    re.IGNORECASE | re.MULTILINE,
                )
                if status_match:
                    stable = stable + 1 if text == stable_text else 1
                    stable_text = text
                    if stable >= 3:
                        return CaseOutcome(status_match.group(1).casefold(), "exact final audit result captured")
                await asyncio.sleep(0.5)
            raise SubmissionUncertainError("The request was submitted, but no stable exact final audit result was captured before timeout.")
        except SubmissionUncertainError:
            raise
        except asyncio.CancelledError as exc:
            raise PostSendCancelledError() from exc
        except Exception as exc:
            raise SubmissionUncertainError(
                f"An error occurred after Send was attempted ({type(exc).__name__}); inspect the visible chat before retrying."
            ) from exc

    async def close(self) -> None:
        # Stopping Playwright disconnects CDP without closing the retained,
        # visible, signed-in Edge process or its tabs.
        try:
            if self.playwright is not None:
                await self.playwright.stop()
        finally:
            self.playwright = None
            self.manager = None
            self.browser = None
            self.context = None
            self.page = None
            self.edge.close_owned()
