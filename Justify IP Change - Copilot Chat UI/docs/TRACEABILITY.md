# Sanitized Step 08 traceability

The supplied `sanitized_step_08.zip` was reviewed as a read-only reference and remains outside the project and Git history.

| Sanitized responsibility | New location | Adaptation |
| --- | --- | --- |
| Launcher and package-relative resources | `app.py`, `cli.py` | Runtime resources now come only from the selected operational workspace. |
| Source CSV and allow-list filtering | `resources.py`, `queue_builder.py` | The required `07_Interested_Parties_Changes_15576.csv` is authoritative; batch selection replaces the missing allow-list. |
| `Change_<id>_Interested_Party_<id>` matching | `models.py`, `queue_builder.py` | Preserved exactly, with case-insensitive Windows fallback and ambiguity rejection. |
| `_part_<n>.pdf` selection | `attachments.py` | Preserved and strengthened with duplicate/gap validation. |
| Prompt construction and base message | `prompting.py` | Base message and instruction attachment are loaded from `Copilot resources`; no real prompt is tracked. |
| 20-file attachment limit | `attachments.py` | Instructions and merged parts are mandatory; deterministic originals fill spare capacity. |
| Sent/result CSV | `logs.py` | Existing schema remains readable; append-only statuses add batch/run metadata without deleting history. |
| Successful-case resume filter | `logs.py`, `queue_builder.py` | Only latest success completes a case; every other latest status remains eligible for the next run. |
| 100-ID batch boundary | `batch_discovery.py` | Used only for discovery/order; execution is a single cross-batch queue. |
| Terminal progress | `progress.py` | Remaining count covers the entire selected queue and changes only after durable logging. |
| Edge/CDP and UI selectors | `edge_session.py`, `copilot_ui.py` | Isolated, visible, profile-validated, interactive-login capable; bounded startup retries cover the existing endpoint, alternate port, and fresh run profile with green method telemetry. |
| Inline self-tests | `tests/test_workflow.py` | Replaced by synthetic unit and integration-style tests. |
| Setup diagnostics | `.setup-logs/<Windows-account>` with `%TEMP%` fallback | Logging begins before interpreter discovery and captures native setup output. The ignored shared folder makes failures supportable without tracking logs. |

## Reviewed secondary reference

The current Copilot Local Agent supplied the VDI-confirmed shared setup method: shared-drive Python, project-local `.venv`, exclusive setup lock, hash-verified bundled `virtualenv.pyz`, exact transitive pins, and isolated Python flags. It also supplied the mapped-S:/UNC final-path pattern, visible Edge startup, loopback CDP validation, dedicated-profile ownership checks, interactive-login readiness, selector isolation, bounded waits, and the rule that an ambiguous send must not be replayed. This project automatically removes incomplete environments under the locked project root. No runtime dependency on the Local Agent project was introduced; the required bootstrap asset is bundled locally.

## Reviewed CDD Audit conventions

The project follows the existing repository's self-contained subproject pattern: root `app.py`, `.cmd` launchers, `Launcher.ps1`, exact dependency lock, bundled bootstrap, `src`, `tests`, `README.md`, and `docs`. Its environment is locked and shared within the `S:` project; setup diagnostics are separated by Windows account and ignored by Git.
