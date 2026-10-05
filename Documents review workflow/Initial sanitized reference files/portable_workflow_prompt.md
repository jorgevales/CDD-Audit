You are acting as a senior Python automation architect, Windows/VDI engineer, QA lead, browser-automation specialist, and non-technical-user experience designer.
Your task is to turn the supplied working Python scripts into one clean, portable, continuous, end-to-end workflow that another user with no technical expertise can operate successfully.
IMPORTANT: Do not begin implementation immediately.
============================================================
PHASE 0: QUESTIONS AND RESOURCE REQUESTS
============================================================
Before changing or creating anything:
1. Inspect every supplied file in full and identify:
   - The purpose of each script.
   - The expected execution order.
   - Every input and output.
   - Every dependency between scripts.
   - Every folder and filename convention.
   - Every persisted status, checkpoint, retry, and recovery mechanism.
   - Every browser, Microsoft Edge, Microsoft 365 Copilot, Excel, Word, PowerPoint, LibreOffice, OneDrive, network-drive, or VDI dependency.
   - Every destructive action such as deleting, replacing, renaming, or cleaning files.
   - Every user confirmation currently required.
2. Ask me for any additional files, schemas, screenshots, logs, folder examples, package lists, instructions, or environmental details that are genuinely required to preserve behavior and test the workflow.
3. Ask concise questions where required to confirm:
   - The intended end-to-end execution order.
   - Which existing prompts and confirmations must remain.
   - Which actions may run automatically.
   - Which destructive actions must retain explicit confirmation.
   - The actual production folder-selection requirements.
   - How notifications should be delivered inside the VDI.
   - Whether users may have different mapped-drive letters or OneDrive locations.
   - The intended behavior after partial failure, interruption, VDI disconnect, browser failure, or machine restart.
   - Which Copilot processing flow is the production default.
   - Whether the final master-workbook stage should run automatically after the browser-analysis stage.
   - Any aspect of functionality, design, flow, or output that cannot be proven from the supplied files.
4. Ask questions in a structured numbered list, grouped into:
   - Blocking questions.
   - Optional design preferences.
   - Additional resources requested.
5. Do not ask me to repeat information already established in the supplied files or this prompt.
6. Do not start modifying code until I have answered the blocking questions. After I answer them, proceed through all later phases without repeatedly pausing for confirmation, except where an actual destructive runtime action requires user approval.
============================================================
PRIMARY OBJECTIVES
============================================================
Create a production-ready workflow with these two primary objectives:
1. Make all supplied scripts execute continuously, correctly, and in the required order as one clean process.
2. Make the workflow fully usable by another user with no programming, command-line, Python, browser-automation, or technical expertise.
The finished workflow must be suitable for processing more than 18,000 cases, so throughput, restartability, correctness, resilience, and low operator effort are essential.
============================================================
NON-NEGOTIABLE FUNCTIONALITY FREEZE
============================================================
The existing scripts already work correctly when manually executed one after another.
Treat all existing business logic and runtime behavior as frozen unless this prompt explicitly permits a change.
You MUST preserve:
- Data-selection rules.
- Case eligibility rules.
- Case ordering and batching.
- Batch sizes.
- Folder and filename matching semantics.
- PDF conversion and merging behavior.
- PDF page limits and multipart behavior.
- Source-file handling.
- Failed-file handling.
- Password-protected-file treatment.
- Attachment prioritization.
- Attachment limits.
- Browser UI automation.
- Model-selection behavior.
- Retry, recovery, and fallback behavior.
- Queue ordering.
- Logging and persistence semantics.
- Status classifications.
- Workbook content, layout, formatting, and column transformations.
- Duplicate-file behavior.
- Existing safety checks.
- Existing confirmation gates unless I explicitly approve their consolidation.
- Existing success and failure criteria.
- Existing outputs and schemas.
- Anything else that affects the resulting files, selected cases, Copilot prompts, browser interactions, or final analysis.
Do not simplify, rewrite, re-architect, optimize, or “clean up” working internal logic merely because another implementation looks more elegant.
Do not silently remove apparently unused code, constants, fallbacks, retries, self-tests, safeguards, or diagnostic paths. First prove that removal cannot change runtime behavior. When in doubt, retain it.
Use wrappers, adapters, configuration files, launchers, orchestration modules, and user-interface layers around the proven scripts instead of rewriting their internals.
The scripts ending in “sanitized” are the portable working references that may be modified carefully. The non-sanitized originals are not supplied and must not be requested, reconstructed, or assumed. Never introduce any user-specific path from an original/non-sanitized environment.
============================================================
ONLY EXPRESSLY PERMITTED BEHAVIORAL CHANGE
============================================================
The only existing runtime behavior that you are expressly authorized to change without separate approval is the terminal printing of repetitive Wake Cycle details.
The current output repeatedly prints detailed lines such as:
- WAKE CYCLE N: starting visibly...
- WAKE CYCLE N: VISIBLY VISITED...
- WAKE CYCLE N COMPLETE...
- NEXT WAKE CYCLE...
Do not change the wake-cycle logic, timing, browser activation, result detection, capture eligibility, queue behavior, retry behavior, or tab traversal.
Change only the amount and presentation of terminal output.
During wake processing, the default user-facing terminal should show only a concise, continuously updated indication of the remaining queued cases or cases still awaiting processing.
Requirements:
- Preserve the detailed Wake Cycle information in a diagnostic log.
- Do not flood the terminal with per-cycle or per-tab messages.
- Show a stable concise line or small status area, for example:
  “Remaining cases: 327 | Active tabs: 6 | Completed: 173”
- Update it only when values change or at a sensible throttled interval.
- Ensure redirected output and non-interactive terminals still receive readable periodic status lines.
- Keep errors, warnings, user actions, major stage changes, and final summaries visible.
- Provide a verbose/debug option that restores detailed Wake Cycle terminal output.
- Prove through tests that this logging-only change does not alter wake-cycle functionality.
No other existing functional behavior may change without:
1. Identifying the proposed change.
2. Explaining why it is needed.
3. Showing the behavioral risk.
4. Obtaining my explicit approval.
============================================================
UI-FIRST, NO-API REQUIREMENT
============================================================
The Microsoft 365 Copilot portion must continue to use browser UI automation.
No Copilot API, Microsoft Graph API, private API, unofficial service endpoint, direct backend request, or API-based replacement is available or permitted.
The browser/UI approach is mandatory because that is how the current workflow is structured.
You may use the established local browser-automation mechanisms already present, including Microsoft Edge, Playwright, and Chrome DevTools Protocol, but you must preserve the user-visible Copilot interaction and all existing safety controls.
Do not attempt to bypass:
- Authentication.
- Tenant controls.
- File-upload limits.
- Model availability.
- Browser security.
- Microsoft 365 UI restrictions.
- Organizational policies.
If the live Copilot UI cannot be exercised in your environment, implement and run every test that can be completed with mocks, fixtures, deterministic browser-page simulations, and local test pages. Clearly separate:
- Actually executed tests.
- Mocked or simulated tests.
- Tests requiring the target VDI and authenticated Copilot session.
Never claim that a live browser test passed unless it was actually executed successfully.
============================================================
PORTABILITY AND NON-TECHNICAL USER EXPERIENCE
============================================================
The workflow must be runnable by a new non-technical user inside a Windows VDI.
The user must not need to:
- Edit Python.
- Edit paths in source files.
- Install packages manually one by one.
- Know command-line arguments.
- Understand virtual environments.
- Understand mapped drives.
- Move files into hidden technical folders.
- Diagnose tracebacks.
- Run scripts individually.
- Know which script runs next.
Create a simple UI-driven launch experience. Prefer a small native Windows desktop UI or another dependable local UI suitable for a managed VDI. Do not require a remotely hosted web application.
At minimum, the UI must provide:
1. A guided first-run setup wizard.
2. Folder and file picker controls instead of manually typed paths.
3. Automatic discovery of sensible locations where safe.
4. Clear validation beside each selected location.
5. A preflight-check screen.
6. A clear selection of:
   - Batch range or starting batch.
   - Number of batches/cases.
   - Processing flow where relevant.
   - Model policy where relevant.
   - Normal or diagnostic mode.
7. A review screen before any destructive operation.
8. A single obvious Start button.
9. A clear progress screen showing:
   - Current stage.
   - Completed cases.
   - Remaining cases.
   - Failed or deferred cases.
   - Active browser tabs.
   - Current batch.
   - Overall progress where it can be calculated reliably.
10. Pause/cancel behavior only where it is safe and does not corrupt state.
11. A completion screen explaining:
   - What succeeded.
   - What failed.
   - Where outputs were written.
   - Which cases require attention.
   - How to resume.
12. A button to open the output folder.
13. A button to open the diagnostic folder.
14. Plain-English errors with actionable remediation.
15. An advanced-details section so technical diagnostics do not overwhelm ordinary users.
Do not fake progress percentages. Use counts or stage progress when total duration cannot be known.
The workflow must finish without requiring the user to continuously watch it. The user will perform other work while it runs.
Provide completion and attention-required notifications suitable for a VDI, using dependable Windows-local mechanisms. Notifications must cover:
- Full completion.
- Completion with warnings.
- Failure requiring user action.
- A paused state requiring authentication or confirmation.
Also retain visible final status in the UI in case toast notifications are suppressed by VDI policy.
Do not steal focus unnecessarily. Browser foreground activation required by the existing UI automation may continue, but minimize unrelated focus changes and clearly explain this limitation to the user.
============================================================
CONFIGURATION AND PATHS
============================================================
Remove user-specific hard-coded paths from the portable solution without changing processing logic.
Use a single validated configuration mechanism for:
- Project root.
- Source data root.
- Temporary batch directory.
- Merged PDF directory.
- Ready-for-AI directory.
- Working CSV.
- Source-copy CSV.
- Completed-ID CSV.
- Sent/result log.
- Instructions Markdown.
- Analysis output directory.
- Final completed-analysis directory.
- Diagnostic directory.
- Edge executable, profile, and debugging port where required.
Requirements:
- Store configuration outside the business-logic scripts.
- Support paths containing spaces and long Windows paths.
- Support OneDrive-synced folders and mapped/network drives.
- Detect unavailable mapped drives and explain how to reconnect them.
- Do not expose one user’s local paths to another user.
- Do not put secrets, authentication tokens, cookies, or personal data in configuration.
- Do not copy an authenticated Edge profile between users.
- Validate read/write/delete permissions before starting.
- Clearly distinguish required paths from generated paths.
- Provide safe defaults based on the current user profile only where appropriate.
- Provide an easy way to update paths later through the UI.
- Redact sensitive values from diagnostics where appropriate.
============================================================
CLEAN END-TO-END ORCHESTRATION
============================================================
Build one explicit state-driven orchestration layer connecting the supplied scripts in their correct sequence.
You may create new files where needed, including:
- Main launcher.
- UI application.
- Configuration loader.
- Environment/preflight checker.
- Dependency installer or bootstrapper.
- Workflow orchestrator.
- State/checkpoint manager.
- Notification helper.
- Test-data generator.
- Test runner.
- Packaging/build scripts.
- Diagnostic/reporting utilities.
- Migration or compatibility adapters.
Do not combine all working code into one enormous script unless there is a proven need. Prefer clearly bounded modules that invoke or import the existing working scripts.
The orchestrator must:
- Know the prerequisites of each stage.
- Validate each stage’s outputs before starting the next stage.
- Stop safely on blocking failures.
- Continue through explicitly recoverable case-level failures where the existing logic already permits it.
- Preserve successful outputs.
- Resume without reprocessing successful cases unless overwrite is explicitly selected.
- Prevent duplicate processing.
- Prevent a partially completed stage from being mistaken for success.
- Use atomic writes where the scripts already do so.
- Preserve or strengthen checkpointing without changing case outcomes.
- Record a machine-readable workflow state.
- Record a human-readable run summary.
- Support safe reruns after interruption, VDI disconnect, OneDrive lock, browser failure, or user cancellation.
- Never delete or overwrite unrelated files.
- Require explicit typed confirmation for destructive operations unless I approve another design.
Map the complete workflow before coding. Produce a dependency graph and state-transition table showing exactly when each script runs and what proves that its stage succeeded.
============================================================
VDI REQUIREMENTS
============================================================
Assume the workflow runs inside a managed Windows VDI with potential constraints:
- Limited CPU and RAM.
- Restricted installation rights.
- Session disconnect or lock.
- OneDrive synchronization delays.
- Mapped-drive availability changes.
- Antivirus scanning.
- File locks.
- Long paths.
- Browser throttling.
- Suppressed desktop notifications.
- Intermittent UI-rendering or CDP delays.
- No administrator privileges.
- Corporate proxy or browser policy.
- Multiple users having different Windows profile paths.
The solution must:
- Detect major VDI constraints during preflight.
- Avoid requiring administrator rights unless genuinely unavoidable.
- Report missing policy permissions clearly.
- Tune concurrency conservatively based on available resources.
- Preserve the scripts’ caps and safety constraints.
- Avoid starting excessive Office processes.
- Avoid exhausting memory, disk, browser tabs, or file handles.
- Continue using the existing browser UI behavior and dedicated Edge-profile safeguards.
- Recover cleanly from transient file locks and sync delays.
- Leave enough diagnostic evidence to distinguish code errors from VDI restrictions.
============================================================
PERFORMANCE REQUIREMENTS
============================================================
The workflow will process more than 18,000 cases. Prioritize processing speed without reducing correctness, safety, evidence completeness, or restartability.
First establish a correctness baseline. Then profile the flow to identify actual bottlenecks.
Focus especially on the supplied implementation module and browser-processing stage.
For every proposed optimization:
1. Identify the tested bottleneck.
2. Provide baseline measurements.
3. Describe the proposed optimization.
4. Explain whether it changes behavior.
5. If behavior could change, do not implement it without approval.
6. Benchmark it using representative small simulated workloads.
7. Compare CPU, memory, disk I/O, browser stability, and throughput.
8. Retain the original behavior if the optimization cannot be proven equivalent.
Permitted recommendations may include:
- Reducing repeated filesystem scans through safe caching.
- Avoiding redundant parsing.
- Reusing validated configuration.
- Improving pipeline overlap where the current logic already allows it.
- Tuning worker counts dynamically for VDI resources.
- Reducing terminal/logging overhead.
- Improving checkpoint lookup.
- Avoiding unnecessary repeated Office or browser setup.
- Improving testable queue bookkeeping.
- Safely preparing the next stage while the current stage is running.
Do not:
- Skip files.
- Skip cases.
- Reduce verification.
- Reduce upload-completion proof.
- Remove retries.
- Increase concurrency beyond safe script/VDI limits.
- Replace the UI flow with an API.
- Infer successful completion.
- Batch cases differently unless explicitly approved.
- Change outputs merely to improve speed.
Provide a separate “Performance recommendations not implemented” section for ideas that may be beneficial but could change behavior or require production profiling.
============================================================
TEST DATA GENERATION
============================================================
Create a compact, fully synthetic test-data generator.
Do not use real client, employee, customer, investor, interested-party, or production information.
Generate only the minimum data necessary to exercise the workflow and keep test size, token use, disk use, and execution cost low.
The generator should create a small representative project layout containing:
- A small working CSV.
- A source-copy CSV.
- Completed-ID and sent/result logs where required.
- Complete and incomplete 100-ID batch fixtures where needed for validation.
- Case folders using the required naming convention.
- A few synthetic cases representing Small, Medium, and Large classifications.
- Multiple PDF parts for at least one case.
- A merge-status JSON.
- Successful, partial, failed, acceptable-source-error, and password-required examples.
- Duplicate filename examples.
- Long filename and long path examples.
- Missing and locked-file simulations where possible.
- Representative text, CSV, XLSX, DOCX, image, and PDF sources using tiny content.
- At least one tiny multipage input to test PDF splitting/packing.
- Minimal output workbooks expected by the master-consolidation stage.
- Mock browser states for pending, uploading, sent, completed, failed, mixed-result, disconnected, and retry outcomes.
Keep generated files tiny. For example:
- One or two pages per test PDF unless more pages are specifically required to test the page-cap logic.
- A few rows per spreadsheet.
- Very small images.
- Minimal case counts except where a full 100-ID fixture is logically required.
Clearly label everything as synthetic test data.
============================================================
FULL TESTING REQUIREMENTS
============================================================
Create and execute an end-to-end test strategy.
Use subagents where available and useful to improve speed and precision. Suitable parallel assignments include:
- Script dependency and data-flow analysis.
- Functionality-freeze comparison.
- Windows/VDI portability review.
- Browser automation review.
- Security and destructive-operation review.
- Unit-test development.
- Integration-test development.
- UI usability review.
- Performance review.
- Documentation review.
Subagents must not modify overlapping files simultaneously. Assign clear ownership, then perform a final integration review.
At minimum, implement:
1. Static validation
   - Python syntax compilation.
   - Import validation.
   - Missing dependency detection.
   - Path/configuration validation.
   - Detection of remaining personal hard-coded paths.
   - Detection of accidental real identifiers in fixtures.
2. Unit tests
   - ID parsing.
   - Batch boundaries.
   - Filename matching.
   - Path resolution.
   - Configuration migration.
   - Queue behavior.
   - Retry selection.
   - Success/failure persistence.
   - Multipart PDF discovery.
   - Password-required exclusions.
   - Attachment planning.
   - Workbook header transformations.
   - Duplicate selection logic.
   - Wake-cycle output suppression.
   - Notification decisions.
3. Integration tests
   - Batch preparation to PDF merge.
   - Merge-status JSON to case-size CSV.
   - Case-size planning to browser-batch planning.
   - Synthetic Copilot result capture to status log.
   - Analysis workbook discovery to master workbook creation.
   - Interruption and resume.
   - Rerun without duplicating successful cases.
   - Locked-file handling.
   - OneDrive-style temporary file handling.
   - Long-path handling.
   - Missing mapped drive.
   - Configuration belonging to another Windows user.
   - Partial and failed batches.
   - Destructive-operation boundaries.
4. Browser/UI tests
   - Use authenticated live Microsoft 365 Copilot UI only when the environment permits.
   - Otherwise use deterministic mocks/local fixtures for UI states.
   - Test attachment limits.
   - Multi-part attachments.
   - Upload delay.
   - Upload failure.
   - Fresh-chat recovery.
   - Model-selection fallback.
   - Send confirmation.
   - Generic title.
   - Explicit terminal result.
   - Mixed success/failure result.
   - CDP disconnection and rebinding.
   - Tab reuse.
   - Queue exhaustion.
   - Wake-cycle concise output.
   - User working on side tasks while automation runs.
   - Browser focus requirements and notification behavior.
5. End-to-end tests
   - Fresh installation/setup.
   - First-run configuration.
   - Preflight.
   - Synthetic batch preparation.
   - PDF generation.
   - Browser phase with mock or live UI.
   - Result persistence.
   - Output workbook generation.
   - Completion notification.
   - Resume after forced interruption.
   - Second-user simulation using a different home directory and different selected folders.
   - Clean uninstall or removal of generated test assets without touching user data.
6. Regression testing
   Compare the original sanitized scripts against the integrated workflow using identical synthetic inputs.
   Prove equivalence for:
   - Selected cases.
   - Generated filenames.
   - Output schemas.
   - PDF counts and page counts.
   - Merge statuses.
   - Queue decisions.
   - Result statuses.
   - Workbook values and formatting.
   - Exit codes.
   - Retry and resume decisions.
   The only expected difference should be:
   - Portable/configured paths.
   - New orchestration/UI files.
   - Concise default Wake Cycle terminal output.
   - Additional diagnostics, notifications, and test infrastructure that do not alter business results.
7. Performance testing
   - Small smoke run.
   - Representative batch.
   - Scaled synthetic queue with lightweight files.
   - Resource-constrained VDI-like configuration.
   - Memory-growth check.
   - File-handle and Office-process cleanup.
   - Browser-tab stability.
   - Throughput comparison.
   - Logging overhead comparison.
Do not state “all tests passed” unless all claimed tests were actually executed. Supply exact commands, results, failures, skipped tests, and reasons.
============================================================
USER DOCUMENTATION AND DISTRIBUTION
============================================================
Create documentation for a non-technical user.
Include:
1. QUICK_START.md
   - Installation/setup using plain language.
   - First-run wizard instructions.
   - How to start.
   - What the user will see.
   - What they may do while it runs.
   - What not to close or disconnect.
   - How completion is reported.
   - How to resume.
2. USER_GUIDE.md
   - Screens and controls.
   - Inputs and outputs.
   - Safe cancellation.
   - Common notifications.
   - Plain-English troubleshooting.
   - How to gather diagnostics without exposing confidential data.
3. ADMIN_SETUP.md
   - Dependencies.
   - VDI requirements.
   - Microsoft Edge and Playwright setup.
   - Office/LibreOffice behavior.
   - Permissions.
   - Mapped-drive considerations.
   - Packaging and deployment.
4. TECHNICAL_DESIGN.md
   - Existing script responsibilities.
   - Orchestration flow.
   - Data-flow diagram.
   - State machine.
   - Configuration model.
   - Checkpoint and recovery model.
   - Security boundaries.
   - Performance design.
   - Test architecture.
5. CHANGE_CONTROL.md
   - Exact list of modified files.
   - Exact changes to each file.
   - Why each change was required.
   - Proof that functionality was preserved.
   - Any approved behavioral changes.
   - Known limitations.
6. TEST_REPORT.md
   - Tests executed.
   - Environment.
   - Results.
   - Skipped tests.
   - Known gaps.
   - Performance measurements.
   - Regression comparison.
7. SUPPORT_BUNDLE_GUIDE.md
   - Which logs are safe to share.
   - Which paths/identifiers must be redacted.
   - How to generate a sanitized diagnostic bundle.
Provide:
- A single obvious user entry point.
- A setup/bootstrap entry point.
- A diagnostic mode.
- A test mode using synthetic data.
- A clean project folder structure.
- Dependency locking or an equivalent repeatable installation method.
- A version identifier displayed in the UI and logs.
If packaging as an executable is practical in the VDI, provide the build configuration and document limitations. Do not assume an executable solves browser, Office, or policy dependencies.
============================================================
SECURITY, PRIVACY, AND RESPONSIBLE HANDLING
============================================================
- Never include real production records in tests.
- Never upload synthetic or real data anywhere except the explicitly configured authorized Copilot UI workflow.
- Never log full document contents unnecessarily.
- Redact sensitive paths, IDs, names, and document text from support diagnostics where possible.
- Never store passwords, tokens, cookies, or credentials.
- Never copy another user’s Edge profile.
- Preserve tenant authentication boundaries.
- Never silently delete user data.
- Require explicit confirmation for destructive actions.
- Restrict deletion to validated, expected, in-scope paths.
- Protect output and merged-PDF directories from broad cleanup.
- Explain all privacy-sensitive behavior in the technical documentation.
============================================================
IMPLEMENTATION PROCESS
============================================================
After receiving my answers to the blocking questions:
Phase 1: Analysis
- Produce a complete inventory.
- Produce the current and proposed flow diagrams.
- Produce the dependency map.
- Produce the invariants/functionality-freeze checklist.
- Identify risks and unknowns.
Phase 2: Design
- Propose the architecture.
- Identify new files.
- Identify minimal edits to existing files.
- Define configuration.
- Define UI.
- Define state/checkpoint behavior.
- Define notifications.
- Define test strategy.
- Define packaging strategy.
Phase 3: Implementation
- Work incrementally.
- Keep existing behavior intact.
- Use small, reviewable modifications.
- Add automated tests alongside each integration change.
- Use subagents for independent reviews where useful.
- Do not leave placeholders, TODO-only implementations, or pseudocode in production files.
Phase 4: Verification
- Run static checks.
- Run unit tests.
- Run integration tests.
- Run end-to-end synthetic tests.
- Run regression comparisons.
- Run browser tests where possible.
- Run performance tests.
- Perform a second independent consistency review of outputs and test evidence.
Phase 5: Delivery
- Present the final project tree.
- Provide every complete modified or new file.
- Do not provide partial snippets where a complete file is required.
- Provide setup and run instructions.
- Provide test evidence.
- Provide known limitations.
- Provide recommendations not implemented.
- Provide an explicit statement of functionality preserved.
- Provide an explicit list of any remaining environment-specific validations the user must perform in the target VDI.
============================================================
FINAL ACCEPTANCE CRITERIA
============================================================
The work is not complete unless all of the following are satisfied:
 
- One clear user entry point exists.
- A non-technical user can configure and run it without editing code.
- No user-specific hard-coded production path remains.
- All scripts execute continuously in the required order.
- Existing business logic and outputs are preserved.
- The Copilot stage remains entirely UI-driven with no API dependency.
- The workflow is restartable and does not duplicate successful work.
- Destructive operations are tightly scoped and confirmed.
- Wake Cycle terminal spam is replaced by concise remaining-case progress.
- Detailed Wake Cycle diagnostics remain available in logs/debug mode.
- Completion and failure notifications work or have a documented VDI fallback.
- Synthetic test files are compact and fully fictional.
- End-to-end tests and regression comparisons have actually been executed where the environment permits.
- Any unexecuted live-Copilot tests are clearly identified rather than claimed as successful.
- The final documentation serves non-technical users, administrators, developers, and support staff.
- Performance improvements are evidence-based and do not compromise correctness.
- The implementation can support progression toward more than 18,000 cases without requiring the user to run scripts manually one at a time.
 
Begin now with PHASE 0 only: inspect all supplied files, then provide the blocking questions, optional design questions, and additional-resource requests. Do not start implementation yet.