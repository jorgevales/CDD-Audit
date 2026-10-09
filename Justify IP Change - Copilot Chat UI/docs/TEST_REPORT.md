# Offline validation report

The ordinary suite contains 35 synthetic and launcher-contract tests and must not open Edge or contact Microsoft 365. Run `Run Tests.cmd` or:

```powershell
python -m unittest discover -s tests -v
```

Validated scenarios include workspace derivation, deep paths and spaces, Windows path forms, aggregate missing-resource reporting, workbook schema and duplicate rejection, numeric batch sorting, root-only `IPs` completion, temporary lock files, 100-case and partial batches, PDF part gaps and ambiguity, continuous queue ordering, log compatibility and history, success filtering, failed/interrupted retry, uncertain-result review gates, contested locks, simulated processing, interruption, resume, bootstrap integrity, exact dependency pins, launcher setup safety markers, and `.cmd` launcher wiring.

The following are intentionally outside offline claims and require the real VDI: live S:/UNC redirection, Edge policy/CDP startup, Microsoft 365 login, current Copilot selectors and model picker, real attachment transfer, send commitment, response capture, two-user shared-lock behavior, and production-scale performance.
