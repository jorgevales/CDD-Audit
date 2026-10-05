# Support Bundle Guide

## Where diagnostics are stored

Each run creates a timestamped directory under the configured diagnostics folder:

```text
diagnostics/
  runs/
    YYYYMMDD_HHMMSS/
      run_config.json
      run_state.json
      prepare.log
      merge.log
      copilot.log
      master.log
```

Only logs for stages that actually started will exist. The browser engine may also create its own diagnostic run files under its configured diagnostic/resource location.

## What to collect

For an internal authorized support request, collect only the affected run directory and note:

- application version shown in the title bar;
- approximate time of the problem;
- stage shown in the UI;
- whether the VDI was locked, disconnected, or under heavy load;
- whether Edge, Office, OneDrive, or a mapped drive showed an error;
- the action taken immediately before the problem.

Do not send source documents, merged PDFs, analysis workbooks, browser profiles, cookies, or credentials unless a separately approved secure process explicitly requires them.

## Sensitive content to redact

`run_config.json` and logs can contain:

- Windows usernames and profile paths;
- OneDrive, mapped-drive, network-share, project, and tenant-identifying paths;
- Change IDs and interested-party IDs;
- source filenames, workbook filenames, case ranges, and status details;
- exception text containing local paths;
- operational timestamps and machine/process information.

Before sharing beyond the approved operational team, replace these values consistently with placeholders such as `<USER>`, `<PROJECT_ROOT>`, `<NETWORK_SHARE>`, `<CHANGE_ID_1>`, and `<PARTY_ID_1>`. Preserve consistent mapping so support can follow one case through the log.

Never include:

- passwords, access tokens, cookies, session storage, or authentication headers;
- the dedicated Edge profile directory or its contents;
- document text or screenshots containing client data;
- actual case CSV rows or workbook cells;
- raw Copilot conversation content unless specifically approved and sanitized.

## Manual sanitized bundle procedure

1. Copy the affected run directory to a new, access-controlled working folder. Do not edit the operational original.
2. Remove unneeded stage logs.
3. Open copies of JSON and text logs in an approved text editor.
4. replace usernames, roots, share names, identifiers, and filenames with consistent placeholders.
5. Search the copy for known names, IDs, email addresses, drive/share names, `Users\`, `OneDrive`, and document extensions.
6. Review exception traces line by line for embedded paths or filenames.
7. Package only the sanitized copies using the organization's approved transfer method.
8. Delete the temporary bundle according to the team's retention policy after the support case closes.

The current application does not provide an automated redacted-bundle generator. Do not describe raw diagnostics as safe to share externally.

## Minimum useful bundle

When disclosure must be minimized, provide:

- a redacted `run_state.json`;
- the final 100-200 relevant lines from the affected stage log, redacted;
- the application version and preflight error/warning text;
- a plain-language reproduction description.

Keep the full operational logs locally until the issue is resolved, subject to organizational retention rules.

