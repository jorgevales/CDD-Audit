# User Guide

## What the application does

The CDD Document Review Workflow joins the existing case preparation, PDF conversion, Microsoft 365 Copilot, and master-workbook tools behind one local browser interface. The primary workflow runs preparation, merge, and Copilot in order. Master-workbook creation remains a separate action.

## Setup screen

Use **Browse...** rather than typing paths where possible.

- **Project root**: the user's operational workflow root.
- **Batch source root**: folders named `Batch_#####_to_#####`.
- **Temporary case workspace**: copied `Change_<ID>_Interested_Party_<ID>` folders.
- **Merged PDF folder**: generated multipart PDFs and merge-status JSON.
- **Working/source-cases CSV**: the browser queue updated during preparation.
- **Source-copy CSV**: authoritative rows copied into the working CSV.
- **Completed-ID CSV**: the existing allow-list used by the browser engine.
- **Sent/result log**: durable send and result statuses.
- **Review instructions**: the Markdown file attached to Copilot.
- **Completed analysis folder**: Excel results made available by the team's background process and consumed by the master stage.
- **Case-size output folder**: generated case-size CSVs.
- **Diagnostics folder**: run logs and state.
- **Microsoft Edge executable**: optional explicit Edge path.
- **Dedicated Edge profile**: per-user profile retaining the approved Microsoft 365 sign-in.

**Restore defaults** restores current-user defaults; it does not prove those paths exist. Select **Save settings** after changes.

## Preflight screen

Preflight checks required engine/resource files, configured input paths, working-CSV columns, write/rename/delete access in generated-output folders, Python packages, Edge, the debugging port, and document-conversion availability.

- `OK`: the check passed.
- `WARNING`: processing may still work, but review the detail.
- `ERROR`: the primary workflow will not start.

Preflight permission probes create and remove only a dedicated `cdd_probe_*` directory inside the selected output folder.

## Run controls

- **First batch ID** must be the first ID in a 100-ID batch: 1, 101, 201, and so on.
- **100-ID batches** accepts 1 through 10.
- **Cases this run** limits browser processing for this run.
- **Browser tabs** accepts 1 through 6.
- **Default review model** applies to every case and retry. GPT-6 Sol is the initial default. Choose from the six GPT and Claude options; your Copilot tenant must expose the chosen option. **Processing flow** retains the existing browser-engine choices.
- **Diagnostic output** shows detailed wake-cycle output. Normal mode suppresses repetitive wake messages in the UI while retaining them in the Copilot stage log.
- **Remove out-of-range temporary cases/PDFs** enables the existing scoped cleanup. You must type `DELETE` exactly.

## Progress and attention states

The display shows stage changes, important messages, errors, and available remaining/completed/active-tab messages. Copilot timing is not presented as a percentage because it cannot be predicted reliably.

Toast notifications are best effort. Corporate VDI policy may suppress them, so always rely on the final status shown in the application and the saved run state.

Copilot may require visible Edge activation. You may perform other work, but Edge can temporarily take focus. Do not use the dedicated automation tabs for unrelated work.

## Safe stopping

**Stop after safe stage** records a request; it does not kill conversion, Office, Edge, or Python processes. The request is observed after preparation and after merge. Once Copilot processing has started, the current version does not stop it mid-stage. Closing the application window while work is running is not a safe stop.

## Master stage

The master stage is intentionally separate. It scans the completed-analysis folder, reports missing cases, and processes only complete groups of exactly 100 Change IDs. It selects the preferred duplicate workbook variant without deleting alternatives and may replace an existing master for a complete batch. Review the confirmation before starting and ensure the folder is backed up or synchronized as required by team policy.

## Common problems

- **Mapped drive unavailable**: reconnect it in Windows, rerun preflight, and start again.
- **CSV schema error**: select the correct working CSV; do not manually rename its columns.
- **Edge not found**: browse to `msedge.exe` on Setup.
- **Debugging port already in use**: close an unintended process using the configured port. If the dedicated Edge session is already running, review the warning rather than closing it blindly.
- **Copilot sign-in required**: sign in through the dedicated visible Edge profile, then retry. Never put credentials in configuration.
- **Files locked or still synchronizing**: close the relevant workbook/document, allow OneDrive or the network drive to finish, then rerun.
- **Master reports missing files**: wait for the established background movement process and run the separate master stage later.
- **Toast missing**: check the application's final status and diagnostics; toast delivery is not proof of completion.

## What not to share

Operational logs can contain local paths and case identifiers. Follow `SUPPORT_BUNDLE_GUIDE.md` before sending diagnostics outside the approved team.
