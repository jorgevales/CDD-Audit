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
  -> fresh chat per case
  -> durable outcome append
  -> remaining-count update
  -> release locks
```

Queue items retain their source batch. UI code never decides eligibility or persistence. A UI send ambiguity becomes `requires_review`, which is deliberately distinct from retryable failure.

## Concurrency boundary

Batch locks prevent cooperating instances from working on the same selected batch concurrently. They are create-exclusive files shared through `Working Space`. Acquisition is sorted and all-or-nothing, preventing partial ownership and deadlock. Per-user log writes use a separate exclusive lock and durable flush. This does not protect against a non-cooperating external program that ignores the lock files.

## Browser safety boundary

The app uses a visible, dedicated machine-scoped Edge profile in personal OneDrive storage and a loopback CDP endpoint. Startup checks profile/port ownership, launches Edge detached to `about:blank`, then validates an existing endpoint or tries the requested port, an alternate port, and a fresh dedicated run profile in bounded time slices. Playwright connects with bounded retries before Copilot navigation; the listener's profile ownership is rechecked before use. The successful method is reported in a short green terminal line. Send confirmation requires two independent UI observations. An ambiguous committed operation is logged as review-required and remains eligible for the next run, so no non-successful case is silently lost. Playwright disconnects without closing the retained Edge process so the operator can inspect uncertain UI state.

## Privacy boundary

Tracked source contains only synthetic test values. Runtime prompts, workbook values, filenames, case identifiers, and document contents stay in the operational workspace. Logs contain identifiers, status, source batch, counts, run ID, and a bounded content-free error summary; they never contain prompt or document bodies.
