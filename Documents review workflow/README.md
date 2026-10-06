# CDD Document Review Workflow

Double-click **Start Workflow.cmd** to open the local HTML, CSS and JavaScript interface in Microsoft Edge. **Start Demo.cmd** opens the isolated fictional configuration. Run **Setup.cmd** once per Windows user to install the document-processing dependencies.

The interface provides source and output settings, review instructions, run preferences, setup checks, live activity, and separate master-workbook creation. Settings are retained across pages and stored per user. The selected **Default review model** applies to every case; the initial default is **GPT-6 Sol**. Choices are GPT 5.6 Sol Quick response, GPT 5.6 Sol Think deeper, GPT-6 Sol, Sonnet 5.5, Opus 5.5, and Sonnet 5. Tenant availability is checked through the Copilot UI; a dropdown choice alone does not prove access.

The frontend is plain JavaScript with local assets, short CSS transitions and reduced-motion support. A small Python service retains filesystem access and the existing processing engines. No Node server, frontend build, CDN, background animation loop, or extra framework is required. The interface opens separately from the dedicated Copilot browser profile and its up to six processing tabs. Activity is bounded rather than allowed to accumulate indefinitely.

See [QUICK_START.md](docs/QUICK_START.md) for operation and [TECHNICAL_DESIGN.md](docs/TECHNICAL_DESIGN.md) for architecture. Optional cleanup still requires typed DELETE and master creation still requires separate confirmation. Safe stop is observed between stages; it cannot interrupt Copilot mid-stage. Workbook movement remains external.

Setup and startup use a per-user environment beneath `%LOCALAPPDATA%\CDD Audit\DocumentsReviewWorkflow\envs`, with bootstrap logs in the adjacent logs folder. Python 3.10 or newer is required. An approved interpreter can be configured in `python_path.txt` beside Setup.cmd or through `CDD_AUDIT_PYTHON`. Corporate package-source, proxy, certificate and PowerShell policy settings are preserved. No administrator privileges or font download are required for the browser interface.

Normal settings remain at `%LOCALAPPDATA%\CDDReviewWorkflow\config.json`; `--config` supports an alternate configuration. Authentication stays inside the dedicated Edge profile. Keep the VDI unlocked and connected while the visible Copilot automation runs. Logs can contain case identifiers and local paths; follow [SUPPORT_BUNDLE_GUIDE.md](docs/SUPPORT_BUNDLE_GUIDE.md) when sharing them.

The former Tk interface remains in `workflow/ui.py` for reference. `app.py` starts the browser interface. The reference document engines, prompts, tests and resources remain together in this self-contained project folder.
