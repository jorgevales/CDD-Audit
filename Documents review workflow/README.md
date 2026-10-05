# CDD Document Review Workflow

This folder contains the portable Windows application that coordinates batch preparation, PDF creation, Microsoft 365 Copilot browser processing, and the separately started master-workbook stage.

Start with [QUICK_START.md](docs/QUICK_START.md). The normal entry point is **Start Workflow.cmd**; first-time dependency setup uses **Setup.cmd**.

The files under `Initial sanitized reference files` remain the preserved business-logic engines and fictional schema references. Configuration, UI, orchestration, state and tests are isolated in `workflow` and `tests`.
