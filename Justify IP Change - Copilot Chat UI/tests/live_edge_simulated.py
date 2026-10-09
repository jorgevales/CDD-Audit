r"""Opt-in real-Edge smoke test against a synthetic Copilot-like page.

Run with: .venv\Scripts\python.exe tests\live_edge_simulated.py
No tenant, real case files, or Send to Microsoft is involved.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from justify_ip_change_copilot_chat_ui.copilot_ui import COPILOT_URL, EDITOR_SELECTORS, PlaywrightCopilotAdapter
from justify_ip_change_copilot_chat_ui.edge_session import find_edge
from justify_ip_change_copilot_chat_ui.models import AttachmentPlan, BatchInfo, CaseRecord, QueueItem


PAGE = r"""<!doctype html><html><body>
<input id="feedback-image" type="file" accept="image/png" hidden>
<div id="m365-chat-editor-target-element" role="textbox" contenteditable="true"></div>
<button id="add" aria-label="Add">Add</button>
<div aria-label="Attachments" id="attachments"></div>
<div id="busy" aria-busy="true" style="display:none">Uploading</div>
<button id="send" aria-label="Send" disabled>Send</button>
<script>
const editor = document.querySelector('[contenteditable]');
const send = document.querySelector('#send');
let uploaded = false;
function update() { send.disabled = !uploaded || !editor.innerText.trim(); }
editor.addEventListener('input', update);
document.querySelector('#add').addEventListener('click', () => {
    window.addClicks = (window.addClicks || 0) + 1;
    setTimeout(() => {
        if (document.querySelector('#case-attachments')) return;
        const input = document.createElement('input');
        input.id = 'case-attachments';
        input.type = 'file';
        input.multiple = true;
        input.accept = '.pdf,.md,application/pdf,text/markdown';
        input.hidden = true;
        document.body.append(input);
        input.addEventListener('change', () => {
            window.lastUploadStarted = performance.now();
            uploaded = false; update();
            const files = [...input.files];
            document.querySelector('#busy').style.display = 'block';
            setTimeout(() => {
                const parent = document.querySelector('#attachments');
                for (const file of files) {
                    const chip = document.createElement('button');
                    chip.setAttribute('aria-label', 'Remove attachment ' + file.name);
                    chip.textContent = file.name;
                    parent.append(chip);
                }
                document.querySelector('#busy').style.display = 'none';
                window.lastUploadCompleted = performance.now();
                uploaded = true; update();
            }, 1200);
        });
    }, 250);
});
send.addEventListener('click', () => {
    window.sentAt = performance.now();
    const prompt = editor.innerText;
    editor.innerText = '';
    const user = document.createElement('div');
    user.dataset.testid = 'chatQuestion';
    user.innerText = prompt;
    document.body.append(user);
    setTimeout(() => {
        const reply = document.createElement('div');
        reply.dataset.testid = 'markdown-reply';
        const match = prompt.match(/Case (\d+)/);
        reply.innerText = 'Case result: ' + (match ? match[1] : 'unknown') + ' | successful';
        document.body.append(reply);
    }, 500);
});
</script></body></html>"""
SINGLE_PAGE = PAGE.replace("input.multiple = true;", "input.multiple = false;")


async def main() -> None:
    tab_count = 1 if "--single-only" in sys.argv else 6
    with TemporaryDirectory(prefix="copilot-synthetic-") as temp:
        directory = Path(temp)
        paths = []
        for name in ("synthetic-review.pdf", "synthetic-evidence.md"):
            path = directory / name
            path.write_bytes(b"Synthetic local test only.\n")
            paths.append(path)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=str(find_edge()), headless="--visible" not in sys.argv,
                args=["--no-first-run", "--no-default-browser-check"],
            )
            try:
                if "--real-readiness" in sys.argv:
                    real_page = await browser.new_page()
                    try:
                        response = await real_page.goto(COPILOT_URL, wait_until="commit", timeout=15000)
                        await real_page.wait_for_timeout(5000)
                        editor_count = sum([await real_page.locator(selector).count() for selector in EDITOR_SELECTORS])
                        category = PlaywrightCopilotAdapter._page_category(real_page)
                        print(f"REAL COPILOT READINESS: category={category}, status={response.status if response else 'none'}, editor_candidates={editor_count}", flush=True)
                    except Exception as exc:
                        print(f"REAL COPILOT READINESS: navigation failed ({type(exc).__name__})", flush=True)
                    return
                context = await browser.new_context()
                await context.route("**/chat", lambda route: route.fulfill(status=200, content_type="text/html", body=PAGE))
                page = await context.new_page()
                adapter = PlaywrightCopilotAdapter(edge=None, tab_count=tab_count, response_timeout=10)
                adapter.browser, adapter.context, adapter.page = browser, context, page
                await page.goto(COPILOT_URL)
                started = time.monotonic()
                await adapter._prepare_parallel_tabs()
                assert adapter.parallelism == tab_count, adapter.parallelism
                batch = BatchInfo(directory, 1, tab_count)
                items = [QueueItem(
                    batch=batch,
                    case=CaseRecord(str(number), str(number), {}),
                    case_folder=directory,
                    attachments=AttachmentPlan(tuple(paths), (), ()),
                    prompt=(f"Case {number}: synthetic validation only\n\n"
                            "REVIEW INSTRUCTIONS\nCheck both documents.\n\n"
                            "EVIDENCE\n- synthetic review\n- synthetic evidence\n\n"
                            "MANDATORY RESULT\nAll files were exposed: Yes\n"
                            f"Case result: {number} | successful"),
                ) for number in range(1, tab_count + 1)]
                try:
                    outcomes = await asyncio.gather(*(adapter.process(item) for item in items))
                except Exception:
                    for index, tab in enumerate(context.pages):
                        state = await tab.evaluate("""() => ({inputs: [...document.querySelectorAll('input[type=file]')].map(x => ({id:x.id, multiple:x.multiple, accept:x.accept, disabled:x.disabled})), add: !!document.querySelector('#add'), addClicks:window.addClicks || 0, editorInnerText: document.querySelector('[contenteditable]').innerText, editorTextContent: document.querySelector('[contenteditable]').textContent})""")
                        print(f"Synthetic tab {index + 1} picker state: {state}", flush=True)
                    raise
                assert all(outcome.status == "successful" for outcome in outcomes), outcomes
                for index, tab in enumerate(context.pages):
                    state = await tab.evaluate("""() => ({
                        feedbackFiles: document.querySelector('#feedback-image').files.length,
                        caseFiles: document.querySelector('#case-attachments').files.length,
                        addClicks: window.addClicks || 0,
                        uploadStarted: window.lastUploadStarted,
                        uploadCompleted: window.lastUploadCompleted,
                        sentAt: window.sentAt
                    })""")
                    assert state["feedbackFiles"] == 0, (index, state)
                    assert state["caseFiles"] == 2, (index, state)
                    assert state["sentAt"] - state["uploadCompleted"] >= 500, (index, state)
                    print(f"Synthetic tab {index + 1}: picker clicks={state['addClicks']}, post-upload wait={state['sentAt'] - state['uploadCompleted']:.0f}ms", flush=True)
                elapsed = time.monotonic() - started
                assert elapsed >= 1.7, f"Upload returned too soon: {elapsed:.2f}s"
                print(f"LIVE EDGE SYNTHETIC PASS: {tab_count} tab(s), {tab_count} case(s), 2 files each, {elapsed:.2f}s", flush=True)
                if "--multi-only" in sys.argv:
                    return
                single = await context.new_page()
                await single.set_content('<input id="single" type="file" accept=".pdf,.md">')
                session = await context.new_cdp_session(single)
                try:
                    document = await session.send("DOM.getDocument", {"depth": -1})
                    found = await session.send("DOM.querySelector", {
                        "nodeId": document["root"]["nodeId"], "selector": "#single",
                    })
                    try:
                        await session.send("DOM.setFileInputFiles", {
                            "files": [str(path) for path in paths], "nodeId": found["nodeId"],
                        })
                        count = await single.locator("#single").evaluate("node => node.files.length")
                        print(f"CDP single-input multi-file compatibility: {count} assigned", flush=True)
                    except Exception as exc:
                        print(f"CDP single-input multi-file compatibility: {type(exc).__name__}", flush=True)
                finally:
                    await session.detach()
                single_context = await browser.new_context()
                await single_context.route(
                    "**/chat", lambda route: route.fulfill(status=200, content_type="text/html", body=SINGLE_PAGE)
                )
                single_page = await single_context.new_page()
                single_adapter = PlaywrightCopilotAdapter(edge=None, tab_count=1, response_timeout=10)
                single_adapter.page = single_page
                await single_page.goto(COPILOT_URL)
                single_outcome = await single_adapter.process(items[0])
                assert single_outcome.status == "successful", single_outcome
                single_state = await single_page.evaluate("""() => ({
                    chips: document.querySelectorAll('button[aria-label^="Remove attachment "]').length,
                    files: document.querySelector('#case-attachments').files.length,
                    sentAt: window.sentAt,
                    uploadCompleted: window.lastUploadCompleted
                })""")
                assert single_state["chips"] == 2, single_state
                assert single_state["files"] == 1, single_state
                assert single_state["sentAt"] - single_state["uploadCompleted"] >= 500, single_state
                print("LIVE EDGE SYNTHETIC PASS: single-file picker uploaded 2 files sequentially", flush=True)
            finally:
                await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
