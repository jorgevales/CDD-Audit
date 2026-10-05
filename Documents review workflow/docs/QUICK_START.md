# Quick Start

## Before you begin

Use this workflow only inside the approved Windows VDI. You need access to the case folders, the two case CSV files, Microsoft Edge, Microsoft 365 Copilot, and the completed-analysis folder used by the existing background file-movement process.

Save unrelated Word, Excel, and PowerPoint work before starting. Conversion opens isolated Office instances where needed, and open or locked source files can interfere with conversion. The supplied merger contains no active call that terminates unrelated Office applications.

## First-time setup

1. Open the project folder.
2. Double-click `Setup.cmd`.
3. Wait for dependency installation to finish. No administrator access is normally required, but corporate package or browser policy can block installation.
4. Double-click `Start Workflow.cmd`.
5. On the **1 Setup** tab, use **Browse...** to select the locations for this Windows user.
6. Select a dedicated Edge profile folder. Do not select or copy another user's Edge profile.
7. Select **Save setup**.

Settings are stored for the current user under `%LOCALAPPDATA%\CDDReviewWorkflow\config.json`. They do not contain passwords or Copilot authentication tokens.

## Run the primary workflow

1. Open **2 Preflight** and select **Run preflight**.
2. Resolve every `ERROR`. Review warnings before continuing.
3. Open **3 Run**.
4. Select the first 100-ID batch, batch count, case limit, browser-tab count, model policy, processing flow, and normal or diagnostic output.
5. Leave temporary cleanup selected only if out-of-range temporary case folders and recognised merged PDFs should be removed. This requires typing `DELETE`.
6. Select **Start primary workflow**.
7. Read the Office-conversion warning, save other Office work, and select **OK** (or press Enter).

The application then prepares cases, creates merged PDFs, and operates Microsoft 365 Copilot through the visible Edge interface. Edge may come to the foreground when the existing automation requires it. Do not close the dedicated Edge session, sign out, lock or disconnect the VDI, or edit source documents while the workflow is active.

The status area remains authoritative if Windows toast notifications are suppressed. Use **Stop after safe stage** to request a stop at the next stage boundary; it is not an immediate cancel.

## Run the separate master stage

Run this only after completed Copilot workbooks have appeared in the configured completed-analysis folder.

1. Select **Run separate master stage**.
2. Review the warning and select **OK**.

The stage lists missing workbooks and creates a master only for each complete, readable 100-ID group. Existing matching batch masters may be atomically replaced after revalidation. The application does not move downloaded workbooks; that is handled by the team's established background setup.

## Results and recovery

- Use **Open output folder** for completed-analysis workbooks.
- Use **Open diagnostics** for the current run's logs and state.
- If a run stops or fails, correct the reported problem and start it again. Existing engine checkpoints and status logs are used to avoid repeating successfully recorded browser work.
- A safe-stop request takes effect after the current preparation or merge stage. During the Copilot stage it cannot interrupt the engine mid-stage.

