"""Opt-in visible Copilot attachment probe; never clicks Send.

The operator completes Microsoft sign-in directly in the retained Edge window.
Only two generated, non-confidential files are selected for upload.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from justify_ip_change_copilot_chat_ui.copilot_ui import EDITOR_SELECTORS, PlaywrightCopilotAdapter
from justify_ip_change_copilot_chat_ui.edge_session import EdgeSession
from justify_ip_change_copilot_chat_ui.models import AttachmentPlan, BatchInfo, CaseRecord, QueueItem
from justify_ip_change_copilot_chat_ui.profile_storage import default_edge_profile


def synthetic_pdf() -> bytes:
    stream = b"BT /F1 12 Tf 72 720 Td (Synthetic attachment check only) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    startxref = len(result)
    result += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        result += f"{offset:010d} 00000 n \n".encode()
    result += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n".encode()
    return bytes(result)


async def safe_page_state(adapter: PlaywrightCopilotAdapter) -> dict[str, object]:
    try:
        return await adapter.page.evaluate("""() => ({
            fileInputs: [...document.querySelectorAll('input[type="file"]')].slice(0, 12).map(node => ({
                multiple: node.multiple, disabled: node.disabled,
                acceptPdf: /pdf/i.test(node.accept), acceptMarkdown: /(?:\\.md|markdown)/i.test(node.accept),
                unrestricted: !node.accept
            })),
            attachmentButtons: document.querySelectorAll('#plus-menu-container button, button[data-testid="chat-input-attach-button"], button[aria-label="Add"]').length,
            removeButtons: document.querySelectorAll('button[aria-label^="Remove attachment "]').length,
            attachmentContainers: document.querySelectorAll('[aria-label="Attachments"]').length,
            progressBars: document.querySelectorAll('[role="progressbar"]').length,
            busyNodes: document.querySelectorAll('[aria-busy="true"]').length
        })""")
    except Exception as exc:
        return {"state_error_type": type(exc).__name__}


async def attach_via_cdp(adapter: PlaywrightCopilotAdapter, files: tuple[Path, ...]) -> None:
    await adapter._ensure_attachment_input(files)
    session = await adapter.context.new_cdp_session(adapter.page)
    try:
        document = await session.send("DOM.getDocument", {"depth": -1, "pierce": True})
        found = await session.send("DOM.querySelectorAll", {
            "nodeId": document["root"]["nodeId"], "selector": "input[type=file]",
        })
        selected = None
        for node_id in found.get("nodeIds", []):
            details = await session.send("DOM.describeNode", {"nodeId": node_id})
            attrs = details.get("node", {}).get("attributes", [])
            attributes = {attrs[index]: attrs[index + 1] for index in range(0, len(attrs) - 1, 2)}
            if "multiple" in attributes and ".pdf" in attributes.get("accept", ""):
                selected = node_id
                break
        if selected is None:
            raise RuntimeError("No multi-file Copilot document input was found for CDP assignment.")
        await session.send("DOM.setFileInputFiles", {
            "files": [str(path) for path in files], "nodeId": selected,
        })
    finally:
        await session.detach()
    expected = [path.name.casefold() for path in files]
    deadline = time.monotonic() + 120
    stable_since = None
    last_notice = time.monotonic()
    while time.monotonic() < deadline:
        state = await adapter._attachment_state(expected)
        complete = (state["chip_count"] >= len(expected) and state["matched_count"] == len(expected)
                    and not state["active"] and not state["upload_error"] and state["send_enabled"])
        if complete:
            stable_since = stable_since or time.monotonic()
            if time.monotonic() - stable_since >= 0.55:
                return
        else:
            stable_since = None
        if time.monotonic() - last_notice >= 10:
            print(f"CDP upload progress: {state['matched_count']}/{len(expected)} attachment chips", flush=True)
            last_notice = time.monotonic()
        await asyncio.sleep(0.25)
    raise RuntimeError("CDP-assigned files did not reach a stable attachment state in the live probe.")


async def main() -> None:
    count = next((int(arg.split("=", 1)[1]) for arg in sys.argv[1:] if arg.startswith("--count=")), 2)
    if not 2 <= count <= 20:
        raise ValueError("--count must be between 2 and 20")
    edge = EdgeSession(default_edge_profile())
    if "--inspect-accept" in sys.argv:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(edge.endpoint)
            for page in browser.contexts[0].pages:
                try:
                    inputs = await page.locator("input[type='file']").evaluate_all(
                        "nodes => nodes.slice(0, 12).map(node => ({multiple: node.multiple, fileCount: node.files.length, extensions: node.accept.split(',').map(x => x.trim()).filter(x => x.startsWith('.'))}))"
                    )
                    if inputs:
                        print(f"Live Copilot file-picker capabilities: {inputs}", flush=True)
                except Exception:
                    continue
        return
    adapter = PlaywrightCopilotAdapter(edge, tab_count=1, startup_timeout=420)
    with TemporaryDirectory(prefix="copilot-live-upload-") as directory:
        root = Path(directory)
        pdfs = [root / f"synthetic-review-{index:02d}.pdf" for index in range(1, count)]
        markdown = root / "synthetic-instructions.md"
        for pdf in pdfs:
            pdf.write_bytes(synthetic_pdf())
        markdown.write_text("# Synthetic attachment check\nNo real case data.\n", encoding="utf-8")
        files = tuple([*pdfs, markdown])
        try:
            print("Opening the real Copilot page in visible Edge; sign in there if prompted.", flush=True)
            await adapter.start()
            await adapter._fresh_chat()
            editor = await adapter._first_visible(EDITOR_SELECTORS, 10)
            if editor is None:
                raise RuntimeError("Copilot composer is unavailable after readiness.")
            await editor.fill("Synthetic attachment upload check only. Do not send this draft.")
            item = QueueItem(
                BatchInfo(root, 1, 1), CaseRecord("1", "1", {}), root,
                AttachmentPlan(files, (), ()), "Synthetic attachment upload check only.",
            )
            print(f"Composer ready; selecting {count - 1} synthetic PDFs and one synthetic Markdown file. Send will not be clicked.", flush=True)
            if "--cdp" in sys.argv:
                await attach_via_cdp(adapter, files)
            else:
                await adapter._attach(item)
            print(f"LIVE COPILOT ATTACHMENT PASS: all {count} synthetic files are visible and transfer is ready; Send was not clicked.", flush=True)
            print(f"Safe UI state: {await safe_page_state(adapter)}", flush=True)
        except Exception as exc:
            print(f"LIVE COPILOT ATTACHMENT FAILURE: {type(exc).__name__}; phase={adapter.case_diagnostics.get('phase')}", flush=True)
            print(f"Safe UI state: {await safe_page_state(adapter)}", flush=True)
            raise
        finally:
            await adapter.close()
            print("Automation disconnected. The visible Edge session remains open for inspection.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
