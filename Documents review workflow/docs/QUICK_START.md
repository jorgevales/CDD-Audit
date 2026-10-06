# Quick Start

1. Run **Setup.cmd** once, then **Start Workflow.cmd**. The application opens in a local browser window. **Start Demo.cmd** uses fictional data and separate paths.
2. Complete **Source files**, **Output folders**, and **Review & browser**. Use Browse to select local or shared-drive paths, or paste full Windows paths.
3. In **Run preferences**, choose the case range, cases to process, and one to six Copilot tabs. Select the **Default review model** used for every case. GPT-6 Sol is selected initially; the choice is saved for later runs.
4. Use **Check model availability** to test all six choices in your dedicated, signed-in Copilot session without sending files. Save settings and run **Check setup**. Resolve errors and review warnings. Changing settings invalidates readiness and requires another check.
5. Open **Run activity**, review the summary, and start the document review. Save other Office work and acknowledge the conversion notice. Optional cleanup shows recognised out-of-range targets and requires typing DELETE.
6. Keep the dedicated Copilot session signed in and the VDI unlocked. The app prepares cases, merges PDFs, and sends them through the existing visible Copilot automation. Its window is separate from the processing tabs.
7. Use **Open results** and **Open logs** when finished. **Stop after safe stage** waits for preparation or merge to finish; during Copilot it waits for that stage to finish.
8. When completed analysis workbooks have arrived through the team's existing background process, open **Master workbooks** and confirm the separate build. Only complete, readable 100-ID groups are built. Existing matching masters may be replaced.

The selected model must be available in your Microsoft 365 Copilot tenant. Sign in through the dedicated Edge window if requested. The workflow must report an unavailable selection rather than silently use a different model.

Settings are stored in `%LOCALAPPDATA%\CDDReviewWorkflow\config.json`, with no passwords or authentication cookies. Use the app's Close action when idle to release its local service. Do not close or terminate processing tabs during a run. Closing an interface window is not a safe stop.

If setup fails, check shared-drive access, CSV selection, Edge detection and output permissions. If sending fails, check the dedicated Copilot sign-in, selected model access and diagnostics. Logs may contain case identifiers; follow SUPPORT_BUNDLE_GUIDE.md before sharing.
