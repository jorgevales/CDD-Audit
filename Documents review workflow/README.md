# CDD Document Review Workflow

This folder contains the portable Windows application that coordinates batch preparation, PDF creation, Microsoft 365 Copilot browser processing, and the separately started master-workbook stage.

Start with [QUICK_START.md](docs/QUICK_START.md). The normal entry point is **Start Workflow.cmd**; first-time dependency setup uses **Setup.cmd**.

The files under `Initial sanitized reference files` remain the preserved business-logic engines and fictional schema references. Configuration, UI, orchestration, state and tests are isolated in `workflow` and `tests`.

**Start Demo.cmd** opens the isolated fictional test configuration. The verified live case and 100 merged PDFs are under `demo/live`; separately labelled simulated master results are under `demo/live/mock_results`. See [TEST_REPORT.md](docs/TEST_REPORT.md) for live evidence and the organisation's device-policy limitation.
