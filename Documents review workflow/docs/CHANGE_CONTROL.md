# Browser interface migration - 6 October 2026

The default app.py entry point now starts a loopback service and local HTML/CSS/vanilla-JavaScript interface. The old Tk code is retained for reference. Launchers continue to use the existing per-user bootstrap; Setup no longer downloads fonts. The default review model is a saved user choice, initially GPT-6 Sol, applied to all cases and retries. Copilot menu selection verifies the requested option and fails clearly if unavailable. Document conversion, batch preparation, attachment planning, result journalling and the separate master stage are retained.

The historical wrapper notes below describe the earlier delivery. Current architecture and operation are documented in TECHNICAL_DESIGN.md and QUICK_START.md; current verification evidence is appended to TEST_REPORT.md.

---
# Change Control

## Delivery scope

This document records the portable wrapper project visible at the time of documentation. The supplied sanitized reference engines and prompt files are retained under `Initial sanitized reference files`. This documentation task did not modify those engines, application code, or tests.

## New portable application files

| File | Purpose | Behavioral effect |
|---|---|---|
| `app.py` | Starts the native UI | Adds one user entry point |
| `Start Workflow.cmd` | Starts `app.py` from the project folder | Removes the need for command-line use |
| `Setup.cmd` | Creates a project-local virtual environment and installs requirements | Adds an isolated guided bootstrap command |
| `requirements.txt` | Pins top-level Python packages | Documents repeatable top-level versions |
| `workflow/config.py` | Loads, validates access to, and atomically saves per-user settings | Replaces portable-wrapper hard-coded operational paths |
| `workflow/ui.py` | Setup, preflight, run, confirmation, status, folder-open, and safe-stop controls | Adds the non-technical-user interface |
| `workflow/preflight.py` | Checks files, paths, CSV columns, permissions, dependencies, Edge, port, and converters | Prevents starts with detected blocking errors |
| `workflow/orchestrator.py` | Runs primary stages in order, filters UI noise, writes logs/state, and notifies | Adds continuous primary orchestration |
| `workflow/engine_runner.py` | Configures and invokes preparation and master engines | Adapts existing module globals to selected paths |
| `workflow/state.py` | Atomically persists run status | Adds stage-level recovery evidence |
| `workflow/notify.py` | Sends best-effort local Windows toast notifications | Adds non-authoritative completion/attention alerts |
| `workflow/__init__.py` | Package marker and version `1.0.0` | Displays a version in the UI |

## Documentation files

This delivery adds `QUICK_START.md`, `USER_GUIDE.md`, `ADMIN_SETUP.md`, `TECHNICAL_DESIGN.md`, `CHANGE_CONTROL.md`, `TEST_REPORT.md`, and `SUPPORT_BUNDLE_GUIDE.md` under `docs`.

## Minimal sanitized-engine integration edits

- `07...sanitized.py`: accepts configured temporary and merged-PDF folders through environment variables; conversion and merge rules are unchanged.
- `08...sanitized.py` and `resources/configuration.py`: accept the portable reference root and sanitized resource names.
- `resources/implementation_sanitized.py`: sends diagnostics to the configured folder and emits a concise wake status only when counts change; detailed wake lines remain in the raw stage log.
- `resources/__init__.py` and `resources/implementation.py`: provide the package/alias expected by the existing launcher.

## Preserved behavior

The wrapper is intended to preserve:

- 100-ID case boundaries and existing selection/order rules;
- source folder and filename matching;
- document conversion, failed/password-protected source handling, multipart packing, and page limits;
- browser attachment limits, prioritization, send proof, model policy, retries, wake logic, queue logic, and result statuses;
- sent/result log and pending-transition behavior;
- incomplete-batch reporting, duplicate selection, workbook transformations, formatting, and atomic master save.

The only approved engine-output presentation difference is concise normal wake-cycle output in the UI. Detailed output is retained in the stage log and available in diagnostic mode.

## Confirmed operating decisions

- The long-named working CSV and `source_cases.csv` represent the same logical queue.
- Completed Copilot workbook movement is external and must not be added to the application.
- Existing browser statuses and retry behavior remain unchanged.
- Master creation remains a separate action.
- The operator receives an Office-process warning and confirms with OK/Enter.
- No Power Automate confirmation appears in the operator workflow.
- Windows toast notifications are best effort with persistent UI status as fallback.

## Review-required risks

- The active master path selects the preferred duplicate workbook variant without deleting the alternatives.
- Optional cleanup confirmation is performed by the UI and the adapter then bypasses the engine's second confirmation.
- The dormant `kill_office` helper remains unused; no new code activates it.
- Stage-level exit success is not a complete independent artifact-equivalence proof.
- Dependency installation is isolated in `.venv`; top-level packages are version-pinned, while transitive hashes are not locked.

## Verification status

Offline unit, integration, merger and engine self-tests plus one authenticated synthetic Copilot case were executed; see `TEST_REPORT.md`. Live delivery is blocked by this device's organisation policy. Target-VDI behavior, full regression equivalence and production performance remain unverified.

Wrapper fixes select console Python for child processes launched from pythonw, capture Tk variables on the UI thread, and retry transient atomic-replacement locks. The application also supports an explicit configuration path. Business review/retry rules and external Power Automate movement remain unchanged.
