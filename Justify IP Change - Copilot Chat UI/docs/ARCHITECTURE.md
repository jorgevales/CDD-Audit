# Architecture

The application keeps the six required concerns separate:

1. `paths.py` and `workspace.py` resolve S:/UNC identity and derive the workspace.
2. `batch_discovery.py`, `resources.py`, `attachments.py`, and `queue_builder.py` implement deterministic business rules.
3. `logs.py` provides append-only outcomes and cross-user batch locks.
4. `edge_session.py` and `copilot_ui.py` isolate visible Edge/CDP and mutable UI selectors.
5. `cli.py`, `application.py`, and `progress.py` provide operator interaction, orchestration, interruption, and status.
6. `tests/` creates synthetic filesystems and workbooks with no company systems or real data.

## Control flow

```text
workspace selection
  -> live S:/UNC identity validation
  -> resource and workbook validation
  -> numeric batch discovery
  -> user-log filtering
  -> attachment preflight
  -> one deterministic continuous queue
  -> acquire every selected batch lock
  -> visible Edge/Copilot session
  -> up to six independent Copilot tab workers
  -> fresh chat and verified upload per case
  -> durable outcome append
  -> remaining-count update
  -> release locks
```

Queue items retain their source batch. UI code never decides eligibility or persistence. A UI send ambiguity becomes `requires_review`, which is deliberately distinct from retryable failure.

The adapter keeps one page per worker, reuses only marked app tabs with empty composers, and opens new tabs when needed. A freed worker takes the next case from the shared queue. The workspace resolver yields UNC paths for S: documents. For UNC batches up to 40 MiB, Python reads the files and Playwright assigns their bytes to Copilot's selected document input; larger batches are copied into a per-run local temporary folder and assigned from there, with cleanup after transfer verification. Local paths retain the browser-local CDP route and its Playwright fallback. File assignment has the original single-case 900-second allowance; transfer verification starts a separate 600-second limit after assignment and requires the exact expected attachment count and names, no active upload indicators, and an enabled Send control to stay stable. Prompt entry happens before that Send-gate check. No case is submitted merely because file chips appeared.

## Concurrency boundary

Batch locks prevent cooperating instances from working on the same selected batch concurrently. They are create-exclusive files shared through `Working Space`. Acquisition is sorted and all-or-nothing, preventing partial ownership and deadlock. Per-user log writes use a separate exclusive lock and durable flush. This does not protect against a non-cooperating external program that ignores the lock files.

## Browser safety boundary

The app uses a visible, dedicated machine-scoped Edge profile in personal OneDrive storage and a loopback CDP endpoint. Startup first reuses a validated retained endpoint. Otherwise, the VDI-confirmed dedicated-profile/requested-port route is the primary launch method with a six-second failure bound; alternate port and fresh profile are recovery only. New Edge launches detached to `about:blank`. Playwright connects with bounded retries and rechecks listener ownership. It checks a retained Copilot tab for a visible editor using the working agent's selector variants, then quickly falls back to a newly owned tab in the same verified context if needed. Only the newly owned tab may be re-navigated during recovery; a pre-existing tab and its draft are preserved. A short green line reports the Edge startup method and a separate green line reports the Copilot readiness method that actually succeeded. Failed readiness attempts contribute only bounded, sanitized UI-state categories, timings, and outcomes to the support report; no URL, DOM, title, account text, or message content is retained. Send confirmation requires two independent UI observations. An ambiguous committed operation is logged as review-required and remains eligible for the next run, so no non-successful case is silently lost. Playwright disconnects without closing the retained Edge process, profile, port, or tabs, enabling direct reuse on the next run.

## Privacy boundary

Tracked source contains only synthetic test values. Runtime prompts, workbook values, filenames, case identifiers, and document contents stay in the operational workspace. Logs contain identifiers, status, source batch, counts, run ID, and a bounded content-free error summary; they never contain prompt or document bodies.
