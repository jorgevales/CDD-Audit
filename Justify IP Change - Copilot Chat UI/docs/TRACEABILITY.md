# Sanitized Step 08 traceability

The supplied `sanitized_step_08.zip` was reviewed as a read-only reference and remains outside the project and Git history.

| Sanitized responsibility | New location | Adaptation |
| --- | --- | --- |
| Launcher and package-relative resources | `app.py`, `cli.py` | Runtime resources now come only from the selected operational workspace. |
| Source CSV and allow-list filtering | `resources.py`, `queue_builder.py` | The required XLSX is authoritative; batch selection replaces the missing allow-list. |
| `Change_<id>_Interested_Party_<id>` matching | `models.py`, `queue_builder.py` | Preserved exactly, with case-insensitive Windows fallback and ambiguity rejection. |
| `_part_<n>.pdf` selection | `attachments.py` | Preserved and strengthened with duplicate/gap validation. |
| Prompt construction and base message | `prompting.py` | Base message and instruction attachment are loaded from `Copilot resources`; no real prompt is tracked. |
| 20-file attachment limit | `attachments.py` | Instructions and merged parts are mandatory; deterministic originals fill spare capacity. |
| Sent/result CSV | `logs.py` | Existing schema remains readable; append-only statuses add batch/run metadata without deleting history. |
| Successful-case resume filter | `logs.py`, `queue_builder.py` | Only latest success completes a case; uncertainty requires explicit operator review. |
| 100-ID batch boundary | `batch_discovery.py` | Used only for discovery/order; execution is a single cross-batch queue. |
| Terminal progress | `progress.py` | Remaining count covers the entire selected queue and changes only after durable logging. |
| Edge/CDP and UI selectors | `edge_session.py`, `copilot_ui.py` | Isolated, visible, bounded, profile-validated, interactive-login capable. |
| Inline self-tests | `tests/test_workflow.py` | Replaced by synthetic unit and integration-style tests. |
| Runtime diagnostic folder beside source | per-user bootstrap logs and operational log | No runtime output is written into the source repository. |

## Reviewed secondary reference

The current Copilot Local Agent supplied the mapped-S:/UNC final-path pattern, visible Edge startup, loopback CDP validation, dedicated-profile ownership checks, interactive-login readiness, selector isolation, bounded waits, and the rule that an ambiguous send must not be replayed. No runtime dependency on that project was introduced.

## Reviewed CDD Audit conventions

The project follows the existing repository's self-contained subproject pattern: root `app.py`, `.cmd` launchers, a PowerShell bootstrap, `requirements.txt`, `src`, `tests`, `README.md`, and `docs`. Its virtual environment and diagnostics are per user under `%LOCALAPPDATA%`, not shared in the repository.
