# Test Report

## Environment

- Date: 5 October 2026
- Host: Windows workspace, Python 3.14.2
- Isolated environment: project `.venv`
- Installed pinned packages: openpyxl 3.1.5, Pillow 11.3.0, PyMuPDF 1.26.4, python-docx 1.2.0, pywin32 311, ReportLab 4.4.3, Playwright 1.55.0

## Executed tests

### Automated suite

Command:

```text
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Latest clean run: **13 tests passed, 0 failed, 0 skipped** in 37.813 seconds.

Covered configuration migration/atomic persistence, state transitions, 100-ID boundaries, preparation copy and CSV rerun deduplication, complete and incomplete master batches, browser CLI/config handoff, result-log/journal precedence, and wake-output visibility filtering.

### Browser-engine offline self-tests

All 22 `self_test_*` functions in `implementation_sanitized.py` were executed. Coroutine tests were explicitly awaited with `asyncio.run`. Result: **22 passed**.

These cover target orchestration, failed/mixed capture, assignment invariants, wake shutdown, upload completion policies, attachment naming/collision/password rules, recoverable upload failure, universal queue behavior, model policies, legacy staged flow, tab activation, nonblocking send handoff, preloaded startup, and CDP persistence policy.

### Synthetic PDF merge

100 fictional Change folders were prepared and merged with two workers. Case 09001 contains PDF, DOCX and XLSX source documents and produces an actual seven-page merged PDF. All 100 output PDFs were readable. Rerunning preserved existing PDFs byte-for-byte. A separate simulated complete set of 100 result workbooks produced a master with 100 data rows; an incomplete 99-case set was not accepted.

Persistent demonstration files are under `demo/live`. `Start Demo.cmd` opens their isolated configuration. No production case files were used. The earlier sandbox-owned `demo` files are not the authoritative live-test set.

### Authenticated Copilot UI test

After the user completed sign-in/MFA in the dedicated Edge test profile, the existing browser engine completed one synthetic case through the real Microsoft 365 Copilot UI:

- Base message and case-specific text sent.
- Five attachments confirmed uploaded: methodology, seven-page merged PDF, original PDF, DOCX and XLSX.
- GPT 5.6 Think Deeper selected; response UI identified GPT-5.6 Sol Think deeper.
- Separate no-send UI checks confirmed exact model radio `aria-checked=true` for GPT 5.6 Think Deeper, GPT 6.0 Sol and Opus. Evidence: `demo/live/model_checks.json`. This verifies selection, not completed responses from all three models.
- Case 09001/IP09001 returned `successful`; persisted to `demo/live/results.csv`; final engine summary 1/1 successful and process exit 0.
- Generated `Change_09001_IP_IP09001_documents_analysed.xlsx` was visible in the actual chat and Excel preview. Evidence: `demo/live/chat_evidence.json` and `copilot_result.png`.

The Excel preview displayed an organisation policy prohibiting download/print/sync on this device and requiring a domain-joined device. No download or policy bypass was attempted. Consequently live workbook delivery by Power Automate and a master built from live Copilot results were **not verified** here. The simulated master test is explicitly separate. Continue that acceptance test on the approved VDI.

Testing exposed and fixed pythonw subprocess selection, Tk variable access from a worker, and transient checkpoint replacement locks. Real uploads failed when the automation sandbox created files unreadable by the signed-in Windows user; the successful test regenerated fictional files and ran under the same real user as Edge, rather than weakening filesystem permissions.

### Launcher/resource smoke test

The supplied sanitized script 08 launcher was executed with `--help` through the installed environment and portable resource root. It loaded the resource package and displayed the complete browser CLI successfully without starting Edge. Generated smoke-test diagnostics were removed afterward.

### Windows UI and preflight smoke tests

- The real Tkinter `App` initialized successfully in the Windows desktop session as version 1.0.0 and was then closed without starting a workflow.
- A fully fictional configured environment passed every preflight item with **0 errors**. This included all installed imports, CSV schema, write/rename/delete probes, Edge discovery, and port availability. Its temporary files were removed afterward.

### Static checks

- All project Python sources parsed successfully with `ast.parse`.
- Core UI modules imported successfully.
- A scan found no embedded current-user production path in project source or documentation outside `.venv` and diagnostics.

## Not executed or not claimable here

- Full 100-case live Copilot batch and live legacy staged flow. The live test used one synthetic case in the primary flow.
- Power Automate timing or file movement; movement is intentionally outside application scope.
- Microsoft Office COM/LibreOffice conversion across the production format corpus.
- OneDrive locks, mapped-drive loss/reconnect, VDI disconnect/lock, proxy, antivirus, notification policy, or another real Windows user.
- Full direct-versus-wrapper golden regression over production-representative documents.
- 18,000-case soak, throughput, memory, handle, Office-process, and browser-tab stability measurements.

These must be validated in the approved target VDI before production acceptance. The single-case live success above does not establish production acceptance or validate the compliance judgment itself.

## Known gaps

- The sanitized references are the only available equivalence baseline; unsupplied production originals were neither requested nor reconstructed.
- The UI safe-stop request acts between primary stages. It does not interrupt the Copilot engine mid-stage.
- Top-level dependencies are pinned, but transitive dependency hashes and an offline wheelhouse are not yet supplied.
- A zero subprocess exit is combined with selected artifact checks, but a complete golden-output regression corpus is still required for formal behavioral equivalence.
