# Administrator Setup

## Supported operating model

The application is designed for a managed Windows VDI and uses:

- a local HTML/CSS/JavaScript interface served by a Python standard-library loopback service;
- Microsoft Edge controlled through Playwright and Chrome DevTools Protocol;
- the visible Microsoft 365 Copilot web interface, with no Copilot or Graph API;
- Microsoft Office COM automation and Python conversion fallbacks, with LibreOffice used where available by the preserved merger;
- local, mapped-drive, network, and OneDrive-backed paths selected per user.

Authentication remains inside the user's dedicated Edge profile. Do not deploy a pre-authenticated profile or copy one between users.

## Installation

1. Install an organization-approved Python version containing `tkinter` and `pip`.
2. Place the complete project folder in a user-readable location.
3. Run `Setup.cmd` as the user. It creates a per-user virtual environment under LOCALAPPDATA and installs the exact top-level versions in `requirements.txt`. No font download is required. The workflow controls the installed Microsoft Edge through CDP; it does not download a separate browser.
4. Run `Start Workflow.cmd` and configure paths through the UI.

Current pinned top-level packages are `openpyxl 3.1.5`, `Pillow 11.3.0`, `PyMuPDF 1.26.4`, `python-docx 1.2.0`, `pywin32 311` on Windows, `reportlab 4.4.3`, and `playwright 1.55.0`.

`requirements.txt` is not a fully hashed transitive lock file. For repeatable restricted deployment, validate these versions against the approved Python version, export an approved wheelhouse, and install from that internal/offline source. `Setup.cmd` requires access to the configured Python package source but isolates packages in a per-user virtual environment.

## Required access

The user needs:

- read access to source batches, source-copy CSV, instructions, and resources;
- create/write/rename access to the temporary workspace, merged-PDF folder, case-size output, completed-analysis folder, diagnostics, working CSV, and result log;
- delete access only where selected cleanup and atomic replacement require it;
- permission to launch Edge with a local debugging port;
- approved access to `https://m365.cloud.microsoft/chat`;
- Office automation permission or suitable converter fallbacks for source formats.

The configured debugging port defaults to `9223`. Restrict it to the local machine and ensure endpoint controls do not expose or proxy it externally.

## VDI considerations

- Session locking or disconnect can suspend or disrupt visible browser automation.
- Browser policy can disable debugging, file upload, model availability, toast notifications, or script-driven focus.
- OneDrive, antivirus, and mapped drives can introduce locks and delayed visibility.
- Conversion can launch isolated Office applications and can be affected by open or locked source files. The dormant termination helper is not called by the supplied merger; users are still warned to save unrelated work first.
- Keep sufficient disk space for copied sources, temporary conversions, and merged PDFs.
- Do not raise engine concurrency until production profiling proves it safe on the target VDI.

## Configuration and privacy

Per-user configuration is at `%LOCALAPPDATA%\CDDReviewWorkflow\config.json`. It is written through a temporary file and atomic replacement. It contains paths and operational choices but must never contain passwords, cookies, tokens, or document contents.

The dedicated profile defaults beneath `%LOCALAPPDATA%\CopilotTabAutomation\EdgeProfile`. Preserve Windows user boundaries and ACLs. Diagnostics may include identifiers and full local paths; retain them under approved access controls.

## Distribution

The current supported entry points are `Setup.cmd` and `Start Workflow.cmd`. No executable package has yet been verified. If packaging is required, prefer a PyInstaller one-folder build and validate COM imports, `tkinter`, dynamic engine loading, resources, Playwright, and Edge discovery on a clean VDI. Packaging does not remove the need for Edge, Office/converter, tenant policy, profile, drive, or Copilot validation.

## Target-VDI acceptance checks

Before rollout, execute and record:

1. clean-user setup without administrator rights;
2. mapped-drive and OneDrive input/output probes;
3. representative DOC/XLS/PPT/PDF/image conversion;
4. dedicated Edge launch, sign-in retention, CDP connection, uploads, model choice, send proof, wake behavior, and result detection;
5. session lock/disconnect behavior;
6. toast allowed and toast-suppressed behavior;
7. background workbook arrival followed by incomplete and complete master batches;
8. retry after locks, browser interruption, and transient drive loss;
9. security review of configuration, profile, logs, and deletion boundaries.
