# Quick Start

## Before you begin

Use this workflow only inside the approved Windows VDI. You need access to the case folders, the two case CSV files, Microsoft Edge, Microsoft 365 Copilot, and the completed-analysis folder used by the existing background file-movement process.

Save unrelated Word, Excel, and PowerPoint work before starting. Conversion opens isolated Office instances where needed, and open or locked source files can interfere with conversion. The supplied merger contains no active call that terminates unrelated Office applications.

## First-time setup

1. Open the project folder.
2. Double-click `Setup.cmd`.
3. Wait for dependency installation to finish. No administrator access is normally required, but corporate package or browser policy can block installation.
4. Double-click `Start Workflow.cmd`.
5. Complete **Source files**, **Output folders**, **Review & browser**, and **Run preferences** using the file and folder selectors. **Continue** saves each page; **Back** preserves your selections.
6. Select a dedicated Edge profile folder. Do not select or copy another user's Edge profile. Edge itself can be detected automatically, or selected using `msedge.exe`.
7. On **Check setup**, select **Check setup**. Resolve every **Needs attention** result and review warnings. Select a result to read its full detail.

Settings are stored for the current user under `%LOCALAPPDATA%\CDDReviewWorkflow\config.json`. They do not contain passwords or Copilot authentication tokens.

## Run the primary workflow

1. Complete **Check setup** with no **Needs attention** results.
2. Select **Go to run** to open **Run workflow**.
3. Review the case range, case count, browser-tab count and models shown above the run controls.
4. To change these choices, return to **Run preferences**, then check setup again. Changes invalidate the previous readiness check.
5. Leave temporary cleanup selected only if out-of-range temporary case folders and recognised merged PDFs should be removed. This requires typing `DELETE`.
6. Select **Run document review**.
7. Read the Office-conversion warning, save other Office work, and select **OK** (or press Enter).

The application then prepares cases, creates merged PDFs, and operates Microsoft 365 Copilot through the visible Edge interface. Edge may come to the foreground when the existing automation requires it. Do not close the dedicated Edge session, sign out, lock or disconnect the VDI, or edit source documents while the workflow is active.

The status area and activity journal remain authoritative if Windows toast notifications are suppressed. Use **Stop after current stage** to request a stop at the next stage boundary; it is not an immediate cancel. Setup controls are locked during a run. **Open results** opens the completed-analysis folder; **Open logs** opens technical run diagnostics. Interface failures are recorded beside the user's settings under `logs/interface.log`.

## Run the separate master stage

Run this only after completed Copilot workbooks have appeared in the configured completed-analysis folder.

1. Select **Master workbooks** at the bottom of the blue navigation rail, then **Build master workbooks**. This stage remains available independently of the browser-readiness check.
2. Review the warning and select **OK**.

The stage lists missing workbooks and creates a master only for each complete, readable 100-ID group. Existing matching batch masters may be atomically replaced after revalidation. The application does not move downloaded workbooks; that is handled by the team's established background setup.

## Results and recovery

- Use **Open results** for completed-analysis workbooks.
- Use **Open logs** for the current run's logs and state.
- If a run stops or fails, correct the reported problem and start it again. Existing engine checkpoints and status logs are used to avoid repeating successfully recorded browser work.
- A safe-stop request takes effect after the current preparation or merge stage. During the Copilot stage it cannot interrupt the engine mid-stage.

