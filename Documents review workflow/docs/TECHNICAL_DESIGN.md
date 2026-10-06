# Technical Design

The default entry point is `app.py`. It starts a standard-library loopback HTTP service in `workflow/web_server.py` and serves the local frontend under `workflow/web/`. The browser renders HTML, CSS and vanilla JavaScript; Python remains responsible for configuration, native path selection, preflight, filesystem operations and document engines. No frontend package installation or build is required.

The frontend handles navigation immediately with short CSS transitions and honours reduced-motion preferences. Activity retrieval is adaptive and histories are bounded to limit resources alongside six Copilot tabs. The interface runs separately from the dedicated Edge debugging profile. The local service binds only to loopback and authenticates API requests with a session token; request-origin and host checks protect local filesystem operations. Browser content does not receive Copilot cookies.

`WorkflowConfig` stores the existing paths, run size, processing flow and a default review model. Missing model selection defaults to GPT-6 Sol. The global selection is passed to the Copilot engine and applies to every case, including retries, instead of switching models by case size. The engine checks the selected radio option through the visible model menu and reports unavailable options without silently changing the requested choice.

Preflight still checks engine/resource files, input paths, working-CSV schema, output permission probes, dependencies, Edge and its debugging port. A successfully checked configuration must match the configuration being started. Settings edits invalidate readiness. Only one workflow or setup check can run at a time.

Primary processing preserves this sequence:

1. Office acknowledgement and optional scoped cleanup preview plus typed DELETE.
2. Batch preparation through `workflow.engine_runner`.
3. The existing PDF merger, with its required merge-status artifact.
4. The existing Copilot browser engine, attachment planning, send proof, queue, wake and result journalling.
5. Completion status, stage logs and saved run state.

Master workbook creation is separately confirmed and preserves complete 100-ID batches, missing-file reporting, duplicate handling and atomic output replacement. Copilot workbook movement remains external.

Each run records `run_config.json`, `run_state.json`, and stage logs under the configured diagnostics folder. Normal activity suppresses repetitive wake detail; raw logs retain it. These artifacts contain operational paths and potentially case identifiers and are not redacted support bundles.

Safe stop is checked after preparation and merge; it does not kill an active child or interrupt Copilot mid-stage. Closing a browser window is not a safe stop. Explicit service shutdown is blocked during active work. The former Tk implementation remains as reference code, outside the default launch path.

Bootstrap installs pinned document dependencies into a per-user environment under LOCALAPPDATA, preserves company package and script policies, and launches the local application hidden. Setup no longer downloads fonts. Deployment and actual resource usage should also be verified on the target VDI; tenant model access and device/browser policy are environment-dependent.
