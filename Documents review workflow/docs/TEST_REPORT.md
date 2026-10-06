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

## Browser interface migration - 6 October 2026

The HTML/CSS/vanilla-JavaScript interface replaces the Tk application on the default launch path. The Python document engines remain in use. No additional runtime packages were introduced.

The baseline suite passed 39 tests before migration. The final full suite passed **53 tests, 0 failures, 0 skips**, in 136.670 seconds; the original browser engine self-tests also passed. The added backend suite covers real HTTP token/origin/host checks, async preflight and model checks, busy-operation exclusion, configuration readiness invalidation, cleanup boundaries, safe stop, bounded events and idle service shutdown. Model regressions cover all six requested values, initial GPT-6 Sol, exact version/mode matching and preservation through case sizes and retries with no automatic fallback.

The real Edge headless acceptance script `tests/browser_smoke.py` passed: six model choices and default, persistence across reloads and pages, all six pages, normal/compact sizing, reduced motion, no page errors, stale readiness blocked after a settings edit, Escape cancellation of cleanup, lowercase delete rejection and exact DELETE accepted into an explicitly simulated workflow. This test sends no files or messages. Screenshots and the machine-readable report are under `diagnostics/web_acceptance`.

After these navigation and confirmation checks, a ten-second idle sample recorded 0 API requests, 0 measured Python CPU seconds, about 0.0016 renderer task seconds and 4.91 MB JavaScript heap. Polling occurs every 15 seconds idle/background and every 1.5 seconds during active work. This is an interface-only sample, not a benchmark of six active Copilot tabs or target VDI conversion throughput. The browser and Python process also have memory overhead beyond the JavaScript heap.

The service stops after a closed interface has been inactive for 120 seconds while idle. It preserves an active workflow; the explicit Close action is blocked during work. Safe stop remains a stage-boundary request.

Live model checking uses one temporary Copilot tab, exact checked radio verification and per-model elapsed times, with no attachments or sends. Current availability and account evidence are in `diagnostics/model_checks.json`. Model access depends on the signed-in tenant and plan; results must be read in that account context. An on-demand Check model availability action is available in the new interface. Production case processing, complete six-tab throughput and remote-session behavior were not tested as part of this interface migration.

The live check on 6 October used the signed-in Valcer work account with M365 Copilot (Basic). Its picker offered only GPT-5.6 Sol Quick response and Think deeper; both exact radio selections passed in 397 ms and 465 ms. GPT-6 Sol and the three versioned Claude choices were not offered in that account. This earlier Basic-account result did not establish FNZ availability; the subsequent FNZ sign-in and successful verification are recorded below. No documents or chat messages were sent during these checks.

After resource isolation, all 11 backend tests passed again. On-demand model checks run in a short-lived subprocess, so the long-lived service does not retain Playwright or browser-engine imports. The real Start Demo.cmd launcher passed its per-user environment checks, and a visible Document Review browser window was verified on the signed-in Windows desktop.

### Final FNZ model verification

After the user completed FNZ sign-in, all six requested models were selected and verified through their exact versioned menu radios. The current report is status verified with the FNZ work-account session using Copilot Chat. The checker restored GPT-6 Sol and closed its temporary tab without attachments or messages.

| Model | Verified selection time |
|---|---:|
| GPT 5.6 Sol Quick response | 444 ms |
| GPT 5.6 Sol Think deeper | 606 ms |
| GPT-6 Sol | 422 ms |
| Sonnet 5.5 | 411 ms |
| Opus 5.5 | 425 ms |
| Sonnet 5 | 416 ms |

Evidence is in diagnostics/model_checks.json. Claude 5.5 uses generic Sonnet/Opus checkmark IDs in this UI with explicit versioned radio labels; selection verifies those labels rather than treating an unversioned name as sufficient. All nine model/browser regression tests passed after reconciling the observed metadata. No sign-in or model-access blocker remains for this session.
