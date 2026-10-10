from __future__ import annotations

import asyncio
from dataclasses import dataclass
import mimetypes
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Protocol
import unicodedata
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
SINGLE_CASE_UPLOAD_TIMEOUT_SECONDS = 600
SINGLE_CASE_FILE_ASSIGN_TIMEOUT_MS = 900_000
TRANSFER_QUIET_SECONDS = 0.55
BUFFER_UPLOAD_LIMIT_BYTES = 40 * 1024 * 1024
ATTACH_BUTTON_SELECTORS = (
    "#plus-menu-container button[data-testid='PlusMenuButton']",
    "#plus-menu-container button",
    "button[data-testid='chat-input-attach-button']",
    "button[data-test-id='chat-input-attach-button']",
    "button[aria-label='Add and manage sources']",
    "button[aria-label='Add']",
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

    def __init__(self, edge: EdgeSession, *, model: str | None = None, startup_timeout: float = 180, response_timeout: float = 1800, tab_count: int = 6) -> None:
        self.edge = edge
        self.model = model
        self.startup_timeout = startup_timeout
        self.response_timeout = response_timeout
        self.requested_tabs = max(1, min(6, tab_count))
        self.parallelism = 1
        self._tab_pool: asyncio.Queue[PlaywrightCopilotAdapter] | None = None
        self.manager = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.startup_diagnostics: dict[str, object] = {"phase": "not_started"}
        self.case_diagnostics: dict[str, object] = {"phase": "not_started"}
        self._reported_attachment_route = False

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
            await self._prepare_parallel_tabs()
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
        chat_pages = [
            page for page in self.context.pages
            if urlparse(page.url).hostname == "m365.cloud.microsoft"
            and urlparse(page.url).path.startswith("/chat")
        ]
        retained = None
        for page in chat_pages:
            try:
                if await asyncio.wait_for(page.evaluate("() => window.name"), timeout=1) == "JustifyIPChange-Worker":
                    retained = page
                    break
            except Exception:
                continue
        retained = retained or next(iter(chat_pages), None)
        self.startup_diagnostics.update(tab_reused=retained is not None, readiness_attempts=[], readiness_checks=0)
        self.startup_diagnostics["phase"] = "copilot_readiness"
        ready_start = time.monotonic()
        fast_deadline = ready_start + 30
        if retained is not None:
            self.page = retained
            await retained.bring_to_front()
            attempt_start = time.monotonic()
            if await self._wait_for_ready(retained, 2):
                if await self._page_is_empty(retained):
                    self._record_readiness_attempt("retained_tab", "composer_visible", attempt_start)
                    await self._finish_readiness("retained tab", "retained_tab")
                    return
                self._record_readiness_attempt("retained_tab", "draft_present", attempt_start)
            else:
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

    async def _page_is_empty(self, page) -> bool:
        self.page = page
        try:
            editor = await self._first_visible(EDITOR_SELECTORS)
            if editor is None or (await self._editor_text(editor)).strip():
                return False
            return not await page.locator("button[aria-label^='Remove attachment ']").count()
        except Exception:
            return False

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

    async def _prepare_parallel_tabs(self) -> None:
        """Keep one independent page per worker; reuse only marked, empty app tabs."""
        pool: asyncio.Queue[PlaywrightCopilotAdapter] = asyncio.Queue()
        pool.put_nowait(self)
        used = {id(self.page)}
        try:
            await self.page.evaluate("() => { window.name = 'JustifyIPChange-Worker'; }")
        except Exception:
            pass
        for number in range(2, self.requested_tabs + 1):
            slot = PlaywrightCopilotAdapter(
                self.edge, model=self.model, startup_timeout=self.startup_timeout,
                response_timeout=self.response_timeout, tab_count=1,
            )
            slot.browser = self.browser
            slot.context = self.context
            candidate = None
            for page in self.context.pages:
                if id(page) in used or self._page_category(page) != "copilot":
                    continue
                try:
                    marker = await asyncio.wait_for(page.evaluate("() => window.name"), timeout=1)
                    if marker != "JustifyIPChange-Worker":
                        continue
                    if await slot._wait_for_ready(page, 2):
                        editor = await slot._first_visible(EDITOR_SELECTORS)
                        attachments = await page.locator("button[aria-label^='Remove attachment ']").count()
                        if editor is not None and not (await slot._editor_text(editor)).strip() and not attachments:
                            candidate = page
                            break
                except Exception:
                    continue
            if candidate is None:
                try:
                    candidate = await asyncio.wait_for(self.context.new_page(), timeout=5)
                    await candidate.goto(COPILOT_URL, wait_until="commit", timeout=10000)
                    if not await slot._wait_for_ready(candidate, 10):
                        raise CopilotUIError("Parallel Copilot tab did not become ready.")
                    if self.model:
                        await slot._select_model(self.model)
                    await candidate.evaluate("() => { window.name = 'JustifyIPChange-Worker'; }")
                except Exception as exc:
                    print(f"WARNING: parallel tab {number} is unavailable ({type(exc).__name__}); continuing with ready tabs.", flush=True)
                    break
            slot.page = candidate
            used.add(id(candidate))
            pool.put_nowait(slot)
        self._tab_pool = pool
        self.parallelism = pool.qsize()
        print(f"Parallel Copilot tabs ready: {self.parallelism}/{self.requested_tabs}.", flush=True)

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
            if await existing.count():
                raise CopilotUIError("A fresh Copilot chat could not be proven; no case was sent.")
        editor = await self._first_visible(EDITOR_SELECTORS, 30)
        if editor is None:
            raise CopilotUIError("A fresh Copilot composer did not become available.")
        if (await self._editor_text(editor)).strip():
            raise CopilotUIError("The fresh Copilot composer is not empty.")

    async def _editor_text(self, editor) -> str:
        tag = str(await editor.evaluate("node => node.tagName || ''")).casefold()
        return await editor.input_value() if tag in {"textarea", "input"} else await editor.inner_text()

    @staticmethod
    def _comparable_prompt_text(value: str) -> str:
        """Ignore rich-editor blank-line expansion without ignoring missing text."""
        value = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
        value = value.replace("\u00a0", " ")
        return re.sub(r"\n{2,}", "\n\n", value.strip())

    async def _attach(self, item: QueueItem) -> None:
        paths = item.attachments.paths
        if len({path.name.casefold() for path in paths}) != len(paths):
            raise CopilotUIError("Attachment names must be unique to verify every document. Send was not clicked.")
        if self._requires_unc_bridge(paths):
            sizes = await asyncio.to_thread(self._attachment_sizes, paths)
            if sum(sizes) <= BUFFER_UPLOAD_LIMIT_BYTES:
                payloads = await asyncio.to_thread(self._file_payloads, paths, sizes)
                await self._attach_prepared(item, paths, payloads=payloads, route="playwright_buffer")
                return
            with tempfile.TemporaryDirectory(prefix="justify-ip-upload-") as directory:
                staged = await asyncio.to_thread(self._stage_files, paths, sizes, Path(directory))
                await self._attach_prepared(item, staged, route="local_staging")
            return
        await self._attach_prepared(item, paths)

    @staticmethod
    def _requires_unc_bridge(paths: tuple[Path, ...]) -> bool:
        return os.name == "nt" and any(str(path).startswith("\\\\") for path in paths)

    @staticmethod
    def _attachment_sizes(paths: tuple[Path, ...]) -> list[int]:
        sizes = []
        for path in paths:
            if not path.is_file():
                raise CopilotUIError("A selected document is no longer an accessible file. Send was not clicked.")
            sizes.append(path.stat().st_size)
        return sizes

    @staticmethod
    def _file_payloads(paths: tuple[Path, ...], sizes: list[int]) -> list[dict]:
        mime = {".pdf": "application/pdf", ".md": "text/markdown", ".txt": "text/plain"}
        payloads = []
        for path, size in zip(paths, sizes):
            data = path.read_bytes()
            if len(data) != size:
                raise CopilotUIError("A document changed while it was being prepared. Send was not clicked.")
            content_type = mime.get(path.suffix.casefold()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            payloads.append({"name": path.name, "mimeType": content_type, "buffer": data})
        return payloads

    @staticmethod
    def _stage_files(paths: tuple[Path, ...], sizes: list[int], directory: Path) -> tuple[Path, ...]:
        staged = []
        for path, size in zip(paths, sizes):
            target = directory / path.name
            shutil.copyfile(path, target)
            if target.stat().st_size != size:
                raise CopilotUIError("A document changed while it was being prepared. Send was not clicked.")
            staged.append(target)
        return tuple(staged)

    async def _attach_prepared(self, item: QueueItem, upload_paths: tuple[Path, ...], *,
                               payloads: list[dict] | None = None, route: str | None = None) -> None:
        paths = item.attachments.paths
        file_input = await self._ensure_attachment_input(paths)
        multiple = await file_input.get_attribute("multiple") is not None
        self.case_diagnostics["attachment_assignment_mode"] = "bulk" if multiple else "sequential"
        if multiple or len(paths) == 1:
            await self._assign_files(file_input, upload_paths, payloads=payloads, route=route)
        else:
            for index, path in enumerate(paths):
                if index:
                    file_input = await self._ensure_attachment_input((path,))
                await self._assign_files(file_input, (upload_paths[index],),
                                         payloads=payloads[index:index + 1] if payloads else None, route=route)
                await self._wait_for_attachment_chips(
                    [candidate.name.casefold() for candidate in paths[:index + 1]],
                    time.monotonic() + SINGLE_CASE_UPLOAD_TIMEOUT_SECONDS,
                )
        deadline = time.monotonic() + SINGLE_CASE_UPLOAD_TIMEOUT_SECONDS
        expected = [path.name.casefold() for path in paths]
        stable_since = None
        retry_count = 0
        last_notice = time.monotonic()
        while time.monotonic() < deadline:
            state = await self._attachment_state(expected)
            self.case_diagnostics.update(
                attachment_chips=state["chip_count"],
                attachment_matched=state["matched_count"],
                upload_active=state["active"],
                upload_retry_count=retry_count,
            )
            if state["upload_error"] and retry_count < 4:
                retry = self.page.get_by_role("button", name=re.compile(r"^Try again$", re.I))
                if await retry.count() and await retry.first.is_visible():
                    await retry.first.click()
                    retry_count += 1
                    stable_since = None
                    await asyncio.sleep(2)
                    continue
            complete = (state["chip_count"] == len(expected) and state["matched_count"] == len(expected)
                        and not state["active"] and not state["upload_error"] and state["send_enabled"])
            if complete:
                stable_since = stable_since or time.monotonic()
                if time.monotonic() - stable_since >= TRANSFER_QUIET_SECONDS:
                    return
            else:
                stable_since = None
            if time.monotonic() - last_notice >= 15:
                print(
                    f"Waiting for document transfer: {state['matched_count']}/{len(expected)} attachments visible; "
                    f"{'transfer active' if state['active'] else 'verifying readiness'}.",
                    flush=True,
                )
                last_notice = time.monotonic()
            await asyncio.sleep(0.25)
        raise CopilotUIError("Documents did not reach a stable, fully transferred state before the single-case timeout. Send was not clicked.")

    async def _assign_files(self, file_input, paths: tuple, *, payloads: list[dict] | None = None,
                            route: str | None = None) -> None:
        selected_route = route or "playwright_fallback"
        if payloads is not None:
            await file_input.set_input_files(payloads, timeout=SINGLE_CASE_FILE_ASSIGN_TIMEOUT_MS)
        elif route == "local_staging":
            await file_input.set_input_files(
                [str(path) for path in paths], timeout=SINGLE_CASE_FILE_ASSIGN_TIMEOUT_MS
            )
        elif self.context is not None and await self._assign_browser_local_files(paths):
            selected_route = "browser_local_cdp"
        else:
            await file_input.set_input_files(
                [str(path) for path in paths], timeout=SINGLE_CASE_FILE_ASSIGN_TIMEOUT_MS
            )
        self.case_diagnostics["attachment_assignment_route"] = selected_route
        if not self._reported_attachment_route:
            label = {"browser_local_cdp": "browser-local CDP", "playwright_buffer": "Playwright file contents",
                     "local_staging": "local staging", "playwright_fallback": "Playwright file paths"}[selected_route]
            print(f"\033[92mAttachment assignment method: {label}\033[0m", flush=True)
            self._reported_attachment_route = True

    async def _assign_browser_local_files(self, paths: tuple) -> bool:
        """Use the original Step 08 browser-local path route for large S:/UNC files.

        A pre-assignment discovery failure permits Playwright fallback. Once the
        CDP assignment call is attempted, its outcome may be ambiguous, so a
        failure must not silently reassign the same files.
        """
        try:
            session = await self.context.new_cdp_session(self.page)
        except Exception as exc:
            self.case_diagnostics["attachment_cdp_preflight_error_type"] = type(exc).__name__
            return False
        try:
            try:
                document = await session.send("DOM.getDocument", {"depth": -1, "pierce": True})
                found = await session.send("DOM.querySelectorAll", {
                    "nodeId": document["root"]["nodeId"], "selector": "input[type=file]",
                })
                candidates = []
                for node_id in found.get("nodeIds", [])[:30]:
                    details = await session.send("DOM.describeNode", {"nodeId": node_id})
                    attrs = details.get("node", {}).get("attributes", [])
                    attributes = {str(attrs[index]).casefold(): str(attrs[index + 1])
                                  for index in range(0, len(attrs) - 1, 2)}
                    multiple = "multiple" in attributes
                    accept = attributes.get("accept")
                    if "disabled" in attributes or (len(paths) > 1 and not multiple):
                        continue
                    if not self._accepts_documents(accept, paths):
                        continue
                    score = (40 if accept else 0) + (20 if multiple else 0)
                    candidates.append((score, int(node_id)))
                if not candidates:
                    self.case_diagnostics["attachment_cdp_preflight_error_type"] = "NoCompatibleInput"
                    return False
                selected = max(candidates)[1]
            except Exception as exc:
                self.case_diagnostics["attachment_cdp_preflight_error_type"] = type(exc).__name__
                return False
            try:
                await session.send("DOM.setFileInputFiles", {
                    "files": [str(path) for path in paths], "nodeId": selected,
                })
            except Exception as exc:
                self.case_diagnostics["attachment_cdp_assignment_error_type"] = type(exc).__name__
                raise CopilotUIError(
                    "Browser-local file assignment was attempted but not confirmed. Send was not clicked."
                ) from exc
            return True
        finally:
            try:
                await session.detach()
            except Exception:
                pass

    async def _wait_for_attachment_chips(self, expected: list[str], deadline: float) -> None:
        """In a single-file picker, let React accept each file before replacing it."""
        while time.monotonic() < deadline:
            state = await self._attachment_state(expected)
            self.case_diagnostics.update(
                attachment_chips=state["chip_count"], attachment_matched=state["matched_count"],
            )
            if state["chip_count"] >= len(expected) and state["matched_count"] == len(expected):
                return
            await asyncio.sleep(0.25)
        raise CopilotUIError("A document did not appear in the Copilot attachment list before the upload timeout. Send was not clicked.")

    @staticmethod
    def _accepts_documents(accept: str | None, paths: tuple) -> bool:
        if not accept:
            return True
        tokens = {part.strip().casefold() for part in accept.split(",")}
        if "*/*" in tokens or "*" in tokens:
            return True
        mime = {".pdf": "application/pdf", ".md": "text/markdown", ".txt": "text/plain"}
        return all(
            path.suffix.casefold() in tokens
            or (mime.get(path.suffix.casefold()) or mimetypes.guess_type(path.name)[0]) in tokens
            or ("application/*" in tokens and (mime.get(path.suffix.casefold()) or mimetypes.guess_type(path.name)[0] or "").startswith("application/"))
            or ("text/*" in tokens and (mime.get(path.suffix.casefold()) or mimetypes.guess_type(path.name)[0] or "").startswith("text/"))
            for path in paths
        )

    async def _best_attachment_input(self, paths: tuple, *, allow_single: bool = False):
        """Choose a live document input, not an unrelated feedback/image picker."""
        inputs = self.page.locator("input[type='file']")
        best = None
        best_score = -1
        for index in range(min(await inputs.count(), 30)):
            candidate = inputs.nth(index)
            try:
                if not await candidate.is_enabled():
                    continue
                multiple = await candidate.get_attribute("multiple") is not None
                if len(paths) > 1 and not multiple and not allow_single:
                    continue
                accept = await candidate.get_attribute("accept")
                if not self._accepts_documents(accept, paths):
                    continue
                parent = await candidate.evaluate(
                    "node => !!node.closest('#plus-menu-container,[aria-label=\"Attachments\"]')"
                )
                score = (40 if accept else 0) + (20 if multiple else 0) + (10 if parent else 0)
                if score >= best_score:
                    best, best_score = candidate, score
            except Exception:
                continue
        return best

    async def _ensure_attachment_input(self, paths: tuple = ()):
        """Wait for a document-capable React picker; Add may expose an Upload menu."""
        deadline = time.monotonic() + 10
        attempt = 0
        last_error_type = None
        while True:
            selected = await self._best_attachment_input(paths)
            if selected is not None:
                return selected
            if time.monotonic() >= deadline:
                break
            attempt += 1
            try:
                button = await self._first_visible(ATTACH_BUTTON_SELECTORS)
                if button is not None:
                    # DOM activation also works on background worker tabs. A
                    # Playwright pointer click can time out when several tabs
                    # are uploading concurrently.
                    try:
                        await button.evaluate("node => { if (!node.disabled) node.click(); }")
                    except Exception:
                        await button.click(timeout=700, force=True, no_wait_after=True)
                await asyncio.sleep(0.35)
                selected = await self._best_attachment_input(paths)
                if selected is not None:
                    return selected
                if attempt == 1 and len(paths) > 1:
                    selected = await self._best_attachment_input(paths, allow_single=True)
                    if selected is not None:
                        return selected
                upload = self.page.get_by_role(
                    "menuitem", name=re.compile(r"upload|device|computer|browse", re.I)
                )
                if await upload.count() and await upload.first.is_visible():
                    try:
                        await upload.first.evaluate("node => { if (!node.disabled) node.click(); }")
                    except Exception:
                        await upload.first.click(timeout=700, force=True, no_wait_after=True)
                    await asyncio.sleep(0.25)
                selected = await self._best_attachment_input(paths)
                if selected is not None:
                    return selected
                if len(paths) > 1:
                    selected = await self._best_attachment_input(paths, allow_single=True)
                    if selected is not None:
                        return selected
            except Exception as exc:
                last_error_type = type(exc).__name__
            await asyncio.sleep(0.15)
        self.case_diagnostics.update(
            attachment_picker_attempts=attempt,
            attachment_picker_error_type=last_error_type,
        )
        raise CopilotUIError("A compatible Copilot document input did not become available after bounded picker recovery. No case was sent.")

    async def _attachment_state(self, expected_names: list[str]) -> dict[str, object]:
        return await self.page.evaluate(r"""names => {
            const visible = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
            const norm = s => String(s || '').replace(/\s+/g, ' ').trim().toLowerCase();
            const roots = new Set();
            for (const selector of ['button[aria-label^="Remove attachment "]',
                '[aria-label="Attachments"] > [data-overflow-item="true"]',
                '[aria-label="Attachments"] > div[id^="SPO_"]']) {
                for (const node of document.querySelectorAll(selector)) {
                    roots.add(node.closest('[data-overflow-item="true"],div[id^="SPO_"]') || node);
                }
            }
            const labels = [...roots].map(e => norm([e.innerText, e.textContent,
                e.getAttribute('aria-label'), e.getAttribute('title')].filter(Boolean).join(' ')));
            const activeSelectors = ['[aria-busy="true"]', '[role="progressbar"]',
                '[data-testid*="progress" i]', '[data-testid*="upload" i] [class*="spinner" i]',
                '[class*="attachment" i] [class*="spinner" i]'];
            const active = activeSelectors.some(s => [...document.querySelectorAll(s)].some(visible)) ||
                labels.some(s => /uploading|processing|attaching|scanning|loading|preparing|transferring|pending|in progress/i.test(s));
            const alertText = [...document.querySelectorAll('[role="alert"]')]
                .filter(visible).map(e => norm(e.innerText || e.textContent)).join(' ');
            const uploadError = /error occurred while uploading|upload failed/i.test(alertText);
            const send = [...document.querySelectorAll('button')].find(e => {
                const label = norm(e.getAttribute('aria-label'));
                return visible(e) && (label === 'send' || label.startsWith('send ')) && !label.includes('stop');
            });
            return {chip_count: roots.size,
                matched_count: names.filter(n => labels.some(label => label.includes(norm(n)))).length,
                active, upload_error: uploadError,
                send_enabled: !!(send && !send.disabled && send.getAttribute('aria-disabled') !== 'true')};
        }""", expected_names)

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
        if self._tab_pool is None:
            return await self._process_one(item)
        slot = await self._tab_pool.get()
        try:
            return await slot._process_one(item)
        finally:
            self._tab_pool.put_nowait(slot)

    async def _process_one(self, item: QueueItem) -> CaseOutcome:
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
        self.case_diagnostics["phase"] = "composer_fill"
        editor = await self._first_visible(EDITOR_SELECTORS, 10)
        if editor is None:
            raise CopilotUIError("The Copilot composer disappeared before the prompt could be entered.")
        await editor.fill(item.prompt)
        actual = await self._editor_text(editor)
        expected_exact = item.prompt.replace("\r\n", "\n").strip()
        if self._comparable_prompt_text(actual) != self._comparable_prompt_text(item.prompt):
            # Rich editors may update their DOM after fill returns. Give that
            # render one brief chance to settle, but never Send a text mismatch.
            await asyncio.sleep(0.2)
            actual = await self._editor_text(editor)
        actual_exact = actual.replace("\r\n", "\n").strip()
        comparison = (
            "exact" if actual_exact == expected_exact else
            "rendered_blank_lines" if self._comparable_prompt_text(actual) == self._comparable_prompt_text(item.prompt)
            else "mismatch"
        )
        self.case_diagnostics.update(
            prompt_verification=comparison,
            prompt_expected_chars=len(item.prompt),
            prompt_observed_chars=len(actual),
        )
        if comparison == "mismatch":
            raise CopilotUIError("The Copilot composer did not preserve the complete prompt; Send was not clicked.")
        self.case_diagnostics["phase"] = "attachment_upload"
        await self._attach(item)
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
            self._tab_pool = None
            self.edge.close_owned()
