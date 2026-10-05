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

Latest clean run: **11 tests passed, 0 failed, 0 skipped** in 16.919 seconds.

Covered configuration migration/atomic persistence, state transitions, 100-ID boundaries, preparation copy and CSV rerun deduplication, complete and incomplete master batches, browser CLI/config handoff, result-log/journal precedence, and wake-output visibility filtering.

### Browser-engine offline self-tests

All 22 `self_test_*` functions in `implementation_sanitized.py` were executed. Coroutine tests were explicitly awaited with `asyncio.run`. Result: **22 passed**.

These cover target orchestration, failed/mixed capture, assignment invariants, wake shutdown, upload completion policies, attachment naming/collision/password rules, recoverable upload failure, universal queue behavior, model policies, legacy staged flow, tab activation, nonblocking send handoff, preloaded startup, and CDP persistence policy.

### Synthetic PDF merge

Three fictional Change folders containing tiny text evidence were merged with two workers.

Result: **exit 0**, three valid multipart-named PDFs, three successful cases, and a parseable `merge_status_1_3.json`. The generated temporary directory was deleted after verification.

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

- Authenticated Microsoft 365 Copilot interaction, current tenant selectors/models, real uploads, result detection, and Edge focus behavior.
- Power Automate timing or file movement; movement is intentionally outside application scope.
- Microsoft Office COM/LibreOffice conversion across the production format corpus.
- OneDrive locks, mapped-drive loss/reconnect, VDI disconnect/lock, proxy, antivirus, notification policy, or another real Windows user.
- Full direct-versus-wrapper golden regression over production-representative documents.
- 18,000-case soak, throughput, memory, handle, Office-process, and browser-tab stability measurements.

These must be validated in the approved target VDI before production acceptance. No live-Copilot success is claimed.

## Known gaps

- The sanitized references are the only available equivalence baseline; unsupplied production originals were neither requested nor reconstructed.
- The UI safe-stop request acts between primary stages. It does not interrupt the Copilot engine mid-stage.
- Top-level dependencies are pinned, but transitive dependency hashes and an offline wheelhouse are not yet supplied.
- A zero subprocess exit is combined with selected artifact checks, but a complete golden-output regression corpus is still required for formal behavioral equivalence.
