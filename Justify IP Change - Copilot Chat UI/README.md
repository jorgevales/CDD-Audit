# Justify IP Change - Copilot Chat UI

This self-contained Step 08 application submits one continuous queue of eligible interested-party change cases to the visible Microsoft 365 Copilot Chat UI. It supports multiple selected batches, durable per-user results, shared batch locking, safe interruption, and later resume.

The source project and operational workspace are separate. The source can live anywhere beneath the shared CDD Audit checkout. Operational prompts, workbooks, case documents, PDFs, locks, and user logs always remain in the selected shared workspace and are never written into this repository.

## Supported environment

- Windows VDI with Python 3.10 or newer.
- Microsoft Edge and access to `https://m365.cloud.microsoft/chat`.
- A connected `S:` drive redirected to its live UNC share.
- Interactive Microsoft 365 login/MFA when required.
- A terminal that remains open while the visible automation runs.

Offline tests do not require `S:`, Edge, a Microsoft account, real documents, or network access.

## One-time setup and startup

1. From the shared `S:` project folder, double-click `Setup.cmd` once after deployment or dependency changes. It creates or repairs one locked project environment at `.venv` for all VDI users. If another setup owns the lock, the launcher says `SETUP LOCKED` and makes no competing changes.
2. Double-click `Start Justify IP Change.cmd`.
3. On the first run, paste the operational `...\Working Space\Copilot resources` path. After it is confirmed, later runs reuse that validated workspace automatically; an explicit `--workspace` value can still override it.
4. Select one or more displayed eligible batches.
5. Review the preflight summary and enter `y` to lock the batches and start visible Edge automation.

`python_path.txt` beside `Setup.cmd` may contain one approved full `python.exe` path when automatic Python discovery is unsuitable. In an `S:` deployment, the complete base Python installation must resolve to `S:` or the same UNC share currently mapped as `S:`. The launcher uses isolated `-B -E -s` flags, verifies the bundled environment bootstrap by SHA-256, uses the VDI-confirmed direct pip seeder, installs only exact versions from `requirements.lock.txt`, and automatically removes failed or obsolete incomplete environments while holding the setup lock.

Before Python discovery, the launcher performs a safe project-owned cleanup of stale incomplete environments, generated `__pycache__` folders, and setup logs older than 14 days; it never touches operational batches, documents, user logs, locks, or Edge profiles. Runtime error reports are sanitized JSON files under `Working Space\Error logs`; they contain UTC timing, stage, error type, hashed user/device/workspace references, and redacted technical detail, never direct system paths or personal identifiers.

## Workspace contract

The selected folder must have this shape at any depth below the live `S:` mapping:

```text
<data-root>\
  Batch_00001_to_00100\
    Change_00001_Interested_Party_700001\
      synthetic-document.pdf
  Working Space\
    Copilot resources\
      IP_Review_LLM_Instructions.md
      base_message.md
      07_Interested_Parties_Changes_15576.csv
      Temporary merged pdfs\
        Change_00001_Interested_Party_700001_part_1.pdf
    Users\
```

The program validates the selected final folder name, its `Working Space` parent, the `Users` sibling, every required resource, and the merged-PDF directory. It derives the data root and related locations from that validated structure.

`S:` paths and UNC paths are accepted only when Windows resolves them to the same live share. The program resolves the real final path; it never guesses a UNC prefix or replaces `S:` text naively. A remembered workspace is validated again at every launch and can always be replaced.

## Workbook and case discovery

The runtime CSV must be UTF-8 (a BOM is accepted) and contain the established 14 Step 08 columns as its header. Between 1 and 1,000 rows are supported. Blank or duplicate case identifiers are rejected.

Only direct data-root folders matching `Batch_<number>_to_<number>` are treated as batches. Ranges are parsed and sorted numerically. Each case folder is matched from both `change_id` and `InterestedPartyId` using:

```text
Change_<change_id>_Interested_Party_<InterestedPartyId>
```

The final batch may contain fewer than 100 cases.

## Completed batches

A batch is unavailable when its root directly contains a non-temporary Excel file whose name begins with `IPs` (case-insensitive). Supported extensions are `.xlsx`, `.xlsm`, `.xls`, and `.xlsb`. Files within case subfolders and `~$` Excel lock files do not complete a batch. The preflight output names the file that caused exclusion.

If every workbook case in a batch is already successful in the user's log but the root-level `IPs` workbook is absent, the application prints a prominent review warning and does not resend the batch.

## Continuous queue and attachments

Selected batches are sorted by numeric range. Cases are sorted by numeric `change_id` and `InterestedPartyId`. Duplicate canonical cases are omitted. Successful log entries are removed before attachment validation, and every remaining case from every selected batch is placed into one continuous queue. Crossing a 100-case boundary does not stop or reset processing.

For each case, merged PDFs are matched exactly by both identifiers. `_part_<n>.pdf` files must start at part 1 and remain continuous. Duplicate part numbers or gaps block that case. The instruction Markdown and all merged parts are mandatory; direct case documents fill the remaining Copilot attachment slots deterministically, up to the 20-file limit. Merged PDFs remain the primary evidence and direct originals are fallback context. The prompt contains an original-document manifest but logs never contain prompt or document content.

## User log, locks, and resume

The Windows account name determines the user folder:

```text
<Working Space>\Users\<Windows-account>\07_Copilot_Fully_Sent_Change_IDs_Log_15576.csv
```

The CSV is append-only and is flushed and synced after every terminal case outcome. Existing five-column sanitized Step 08 logs remain readable and are upgraded without deleting history when a new row is added. Only the latest `successful` state excludes a case automatically. `failed` and `interrupted` cases remain eligible.

An outcome whose send state or final Copilot result is uncertain is recorded as `requires_review` and remains eligible for the next run. Every latest status other than `successful` (`sent`, `failed`, `interrupted`, `skipped`, and review-required outcomes) is automatically included in later queues. The legacy `--retry-review-required` option remains accepted for compatibility but is no longer required.

Every selected batch is locked before Edge starts. All locks are acquired as one transaction: if any batch is already locked, the application releases the locks it acquired and reports the locked batch ranges without leading zeroes, followed by the current holder metadata. For example, contiguous folders from `Batch_01001_to_01100` through `Batch_03001_to_03100` are reported as `Batches 1001 to 3100 are locked.` Lock files are stored under `Working Space\.justify-ip-change-locks`. The program releases its locks on normal completion and interruption. A lock left by a crashed machine is not silently stolen; support should verify the owner is no longer running before removing that one exact lock file.

## Interruption

Press `Ctrl+C` once. The application stops taking new cases, records an active pre-send case as `interrupted`, flushes the log, disconnects Playwright, releases batch locks, and exits with code 130. If Send had already been attempted, the case is instead recorded as `requires_review` to prevent an automatic duplicate. Edge is left visible for inspection. On the next run, select the batches again; successes are filtered and retryable outcomes form a new continuous queue.

The highlighted label is updated only after the outcome has been durably written:

```text
[ REMAINING: 237 ]  completed 4/241
```

Terminals without colour receive the same plain-text label.

## Authentication and safe UI behaviour

Edge always runs visibly with a dedicated per-user, machine-scoped profile under the user's available OneDrive folder, following the working Copilot Local Agent layout. The launcher checks profile and loopback-port ownership, opens `about:blank`, connects Playwright, verifies the profile owner, and only then navigates to Copilot. `--profile-dir` can select a different writable personal profile location. The operator completes login and MFA directly in Edge. Startup waits for both the Copilot editor and model picker. Selectors are isolated in `copilot_ui.py`.

Each case uses a fresh chat. The program validates the exact composer text and attached filenames before Send. After clicking Send, it requires both a cleared composer and a matching user turn. If these cannot both be proved, the case becomes `requires_review`; it is never resent automatically. A successful/failed result is accepted only after the exact final response contract is stable across repeated observations.

## Dry run and tests

Validate a real workspace without opening Edge or writing the operational log:

```powershell
python app.py --workspace "S:\synthetic\data\Working Space\Copilot resources" --batches Batch_00001_to_00100 --dry-run
```

Run the entirely synthetic offline suite:

```powershell
Run Tests.cmd
```

The suite covers deep paths with spaces, simulated drive resolution, required resources, exactly 100 cases, a short final batch, completed-batch rules, continuous multi-batch ordering, successful/failed/interrupted/uncertain states, all-success-without-output warnings, merged-PDF ambiguity and sequences, append-only logs, contested batch locks, interruption, and resume.

## VDI deployment

1. Pull the existing CDD Audit repository beneath the approved shared-drive source location.
2. Confirm the operational workspace is separate and has the required structure.
3. Run `Setup.cmd` once from the shared project. Repeat only to repair or update the shared environment.
4. Run `Run Tests.cmd` once on the VDI.
5. Perform a dry run against synthetic workspace data.
6. Perform one visible synthetic Copilot submission after interactive login.
7. Confirm the VDI's S:/UNC identity, batch locking between two accounts, real attachment upload, exact final response capture, interruption, and resume before production use.

## Troubleshooting

- **Setup did not finish:** copy the exact diagnostic log path printed at launcher startup. Logs exist before Python discovery begins.
- **Support error reports:** inspect `Working Space\Error logs`. Correlate `occurred_at_utc`, `user_ref`, and `device_ref` to identify the VDI run without exposing account names or system paths.
- **`Error 28` / no space left:** the confirmed workspace is registered before local settings are written; the report writer retries atomically after pruning only old error reports. Check its `free_space_bytes` labels to distinguish workspace-share, local-temp, and local-appdata capacity.
- **`SETUP LOCKED`:** another user is setting up the shared project, or the project is not writable. Wait for that setup to finish and retry.
- **Python rejected on S:** use a complete Python 3.10+ installation on `S:`; a local interpreter is deliberately rejected for shared deployment.
- **Invalid workspace:** select `Working Space\Copilot resources`, not the data root or source folder.
- **S: unavailable or UNC rejected:** reconnect `S:`. The UNC path must resolve inside the share currently mapped to `S:`.
- **Missing resources:** the preflight reports all missing required paths together.
- **Batch locked:** read the reported holder details. Do not delete a live user's lock.
- **Ambiguous attachment:** correct duplicate/gapped `_part_<n>.pdf` files; the application will not guess.
- **Copilot login:** complete login/MFA in visible Edge and restart if readiness times out.
- **Edge debugging endpoint timeout:** startup checks the effective Edge debugging policy, gives the requested port at most 12 seconds, then tries an alternate port and a fresh dedicated profile. Failures identify the observed condition for each attempt. A successful method is printed as a short green terminal line.
- **Edge cannot write profile data:** close only a stale CDD Audit Edge window if present and retry. The launcher now detects an owned profile/port before launch and uses a machine-scoped detached profile to avoid collisions with ordinary Edge.
- **Selector failure:** retain the terminal error and per-user bootstrap diagnostic path; do not repeatedly submit the case manually without checking its log state.
- **Log lock:** close another run using the same Windows account. The batch lock prevents cross-user work, while the user-log lock prevents same-account corruption.
- **Edge port/profile mismatch:** close the other dedicated app Edge session or select another approved port. The application never attaches to an unverified profile.

## Known limitations

- Live Edge, tenant, model availability, S:/UNC redirection, VDI lifecycle, real workbook content, and real attachments require target-VDI acceptance.
- A crashed remote VDI can leave a batch lock requiring verified manual recovery.
- Direct source documents beyond the remaining 20-file capacity are represented in the manifest but not attached individually; merged PDFs remain mandatory primary evidence.
- The first release is terminal-based.

No credentials, cookies, browser profile, runtime prompt content, real workbook, real case document, PDF, operational log, or environment-specific private path belongs in Git.
