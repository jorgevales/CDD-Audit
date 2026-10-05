# Technical Design

## Scope and invariants

The portable layer wraps the supplied sanitized engines. It does not replace their case selection, batching, conversion, PDF packing, attachment planning, Copilot UI automation, model fallback, retries, result statuses, or workbook transformations. Production copies use the same script names without `_sanitized`; the portable project deliberately contains only the sanitized references.

The only presentation change applied by orchestration is suppression of repetitive wake-cycle lines from the normal UI. The complete subprocess output remains in the stage log, and diagnostic mode shows it in the UI.

## Project components

```text
Documents review workflow/
  app.py                         User entry point
  Start Workflow.cmd            Windows launcher
  Setup.cmd                     Dependency/bootstrap command
  requirements.txt              Pinned top-level dependencies
  workflow/
    config.py                   Per-user configuration
    ui.py                       tkinter/ttk interface
    preflight.py                Input, permission and dependency checks
    orchestrator.py             Ordered subprocess execution and logging
    engine_runner.py            Adapters for preparation and master engines
    state.py                    Atomic run-state persistence
    notify.py                   Best-effort Windows toast
  Initial sanitized reference files/
    07_...py                    PDF merge engine
    08_...py                    Original thin browser launcher reference
    09_...py                    Master-workbook engine
    10_...py                    Batch preparation engine
    resources/                  Browser implementation and prompt resources
  diagnostics/runs/<run_id>/    Generated configuration, state and stage logs
  docs/                         Operator, administrator and technical documents
```

## Data and control flow

```text
UI setup -> saved per-user configuration -> preflight
    -> Office warning and optional DELETE confirmation
    -> prepare adapter
         source Batch folders -> temporary Change folders
         source-copy CSV -> working/source-cases CSV
    -> PDF merge engine
         Change folders -> multipart PDFs + merge_status_<from>_<to>.json
    -> Copilot browser engine
         working CSV + merge status + PDFs + instructions
         -> visible Edge/Copilot interaction
         -> durable sent/result log + case-size CSV
    -> primary completion

Established external background movement
    -> completed-analysis XLSX folder
    -> separately confirmed master adapter
    -> master workbook for each complete 100-ID group
```

The workflow does not download or move Copilot workbooks. Their arrival in the completed-analysis folder is an established environmental behavior outside this program.

## Configuration model

`WorkflowConfig` contains:

- project, source, temporary, merged-PDF, analysis-output, case-size-output, and diagnostics roots;
- working, source-copy, completed-ID, result-log, and instructions files;
- Edge executable, dedicated profile, and debugging port;
- first batch, batch count, case count, tab count, model policy, processing flow, and diagnostic mode.

Defaults are derived from the current user's home and local application-data folders. `config.json` accepts spaces and normal Windows `Path` resolution. Configuration save uses write-to-temporary plus `os.replace`. A snapshot named `run_config.json` is stored with each run. It contains operational paths and must be protected accordingly.

## Stage orchestration

| Stage | Entry | Required evidence currently checked | Next action |
|---|---|---|---|
| Setup | UI | Configuration successfully saved | Preflight |
| Preflight | `run_preflight` | No checks with level `error` | User confirmations |
| Prepare | `workflow.engine_runner prepare` | Adapter exits zero | Merge |
| Merge | script 07 | Process exits zero and expected merge-status file exists | Copilot |
| Copilot | `resources.implementation_sanitized` | Process exits zero; engine owns status/journal reconciliation | Complete |
| Master | `workflow.engine_runner master` | Process exits zero | Separate completion |

Preparation uses script 10's existing `preflight`, inspection, batch copy, and working-CSV update functions. Optional cleanup reuses its scoped folder and PDF rules after the UI's typed `DELETE` gate. Merge is executed directly with `--yes` because the UI has already presented the run and Office warning. The browser engine receives all configured paths as arguments or environment values.

Script 09 remains separate. The UI warns about complete-batch processing and possible master replacement; its existing scan, missing-file reporting, duplicate selection, formatting, and atomic master save remain authoritative.

## Persisted state and recovery

Each orchestration run creates:

- `run_config.json`: the exact configuration snapshot;
- `run_state.json`: run ID, status, current/completed/failed stages, message, and timestamps;
- `<stage>.log`: complete merged stdout/stderr for each executed stage.

State writes use a temporary file and `os.replace`. Current statuses are `created`, `running`, `failed`, `complete`, and `cancelled_safe`. Safe stop is a stage-boundary request, observed after preparation or merge. It does not terminate a child process and is not currently observed inside the Copilot stage.

Engine-level artifacts remain the source of detailed case recovery: merge-status JSON, case-size CSV, result log, and the browser engine's pending-transition journal. Reruns should rely on those preserved engine rules rather than treating orchestrator state alone as proof of case success.

## Safety and destructive boundaries

- Temporary cleanup is limited by script 10's recognized Change-folder/PDF matching and active-range protection and requires typed `DELETE` in the UI.
- The Office warning requires OK/Enter before primary processing.
- Master creation is separately confirmed. The active master path selects the preferred duplicate analysis variant without deleting alternatives and can atomically replace a batch master.
- Permission probes operate only in a newly created `cdd_probe_*` folder.
- The application never stores credentials or copies an Edge profile.
- Browser automation remains visible and UI-driven; no Microsoft API is used.

## Notifications and diagnostics

`notify.py` invokes the Windows Runtime toast API through non-interactive PowerShell. Failure is non-fatal. The UI status and run-state file are always authoritative.

Normal output filters lines matching wake-cycle detail. Every line is still written to `copilot.log`. Diagnostic mode forwards detailed lines to the UI as well.

## Known design limitations

- Orchestrator stage success is partly process-exit based; preparation output completeness is not independently revalidated by the wrapper.
- Merge status existence is checked, but its full schema and selected-case coverage are not independently validated by the wrapper.
- Safe stop cannot interrupt the Copilot stage.
- A closed UI does not supervise or reconnect to an existing child process.
- The run snapshot and logs are operational, not a redacted support bundle.
- `Setup.cmd` installs into a project-local `.venv`; it does not yet provide a hashed transitive lock or offline wheelhouse.
- Live Copilot selectors, model availability, focus behavior, and VDI policy remain environment-dependent.

These limitations must not be described as tested or resolved until corresponding implementation and evidence exist.

