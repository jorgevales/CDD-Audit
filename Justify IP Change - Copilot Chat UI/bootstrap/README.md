# Bundled environment bootstrap

`virtualenv.pyz` is the offline-capable bootstrap used by `Launcher.ps1` when the approved shared Python has neither `venv` nor `pip`.

- Required SHA-256: `9096EFA6E3A8457CC3EC56E749A2D1E17505B756EE3CB2B7E889526367EFC187`
- Invocation forbids downloads and periodic updates.
- The launcher stops before executing the archive if the hash differs.
- The asset was reused from the VDI-confirmed Copilot Local Agent setup.

Do not replace the archive without deliberately updating the pinned hash, validating it in an isolated environment, and re-running target-VDI setup acceptance.
