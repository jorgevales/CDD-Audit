# CDD Document Review Workflow

This folder contains the portable Windows application that coordinates batch preparation, PDF creation, Microsoft 365 Copilot browser processing, and the separately started master-workbook stage.

Start with [QUICK_START.md](docs/QUICK_START.md). The normal entry point is **Start Workflow.cmd**; first-time dependency setup uses **Setup.cmd**.

The native Windows interface is titled **CDD Audit Remediation**, with a navy header, the detected Windows user, a small top stepper and centered, focused pages. The six steps cover source files, output folders, review and browser, run preferences, setup checks, and run activity. Settings are retained while navigating and saved with Continue or the save icon. Pages fade between selections. Text uses genuine Aptos with rounded native controls and inset content. Icon labels appear on hover or keyboard focus. The run action becomes available after setup checks pass; changes require another check. Office conversion, recognised-file cleanup confirmation, and the separately started master stage retain their existing behaviour.

### Aptos and VDI

Setup.cmd offers the official Microsoft Aptos licence and installs only the regular and bold faces for the current user. Install Aptos.cmd can repeat or repair that step independently of Python setup. The installer uses the existing Windows network and proxy settings, checks the official archive and font SHA-256 hashes, and stores fonts and diagnostic logs under `%LOCALAPPDATA%\CDDAuditRemediation\fonts`. It never writes to Windows Fonts, changes the registry, elevates privileges, or bypasses PowerShell policy. `-AcceptLicense` on AptosFont.ps1 is reserved for deployments where the licence has already been accepted.

Each app process loads its own verified faces using Windows private font resources; subsequent runs work offline. Installed Aptos is also supported. The cache is independent of project paths and Python environments, so moving the shared project does not require reinstalling fonts. Font files are not redistributed in this repository. Apple SF Pro is not used because its licence does not permit this Windows application use. Sources: [Microsoft Aptos download](https://www.microsoft.com/en-us/download/details.aspx?id=106087), [Apple font licence](https://developer.apple.com/fonts/).

In a non-persistent VDI, the font cache must be retained with the user profile or IT should deploy Aptos in the VDI image. If downloading, scripts, or private font loading are blocked, the application stays usable with a visible Windows-font warning; ask IT for an approved Aptos deployment. No startup download is attempted. Rounded controls use Tk's software-rendered images, not browser, GPU, transparency or extra-package effects. Actual remote-session rendering and organisation-specific policies still require a test in the target VDI.

On a shared drive, each colleague double-clicks **Setup.cmd** once, then **Start Workflow.cmd**. Packages are stored separately for each Windows user under `%LOCALAPPDATA%\CDD Audit\DocumentsReviewWorkflow\envs`, with diagnostic logs in the adjacent `logs` folder. Startup verifies and repairs that user's environment when needed. Moving the project creates a separate environment; the old one is left intact.

Support can create `python_path.txt` beside Setup.cmd containing the approved `python.exe` path. Relative paths are resolved from this project folder, so a shared-drive installation can use a relative path without a fixed drive letter. This configuration is ignored by Git. Alternatively, support can set the user environment variable `CDD_AUDIT_PYTHON`. Without configuration, setup checks the Windows Python launcher and PATH, then makes a bounded search of the project's drive. Python 3.10 or newer with `venv` is required; dependency compatibility is checked during installation.

Setup preserves pip package-source, proxy and certificate settings. A missing temporary wheel can trigger one retry using fresh user temporary files without pip cache. Company access restrictions or unavailable compatible packages require support. PowerShell must be allowed to run `WorkflowBootstrap.ps1`; if company policy blocks it, ask IT to approve or sign the helper. The launchers do not override execution policy or require administrator rights.

The files under `Initial sanitized reference files` remain the preserved business-logic engines and fictional schema references. Configuration, UI, orchestration, state and tests are isolated in `workflow` and `tests`.

**Start Demo.cmd** opens the isolated fictional test configuration. The verified live case and 100 merged PDFs are under `demo/live`; separately labelled simulated master results are under `demo/live/mock_results`. See [TEST_REPORT.md](docs/TEST_REPORT.md) for live evidence and the organisation's device-policy limitation.
