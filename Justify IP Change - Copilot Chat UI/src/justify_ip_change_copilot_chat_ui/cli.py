from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from .application import execute_queue
from .batch_discovery import describe_batch_ranges, discover_batches
from .case_discovery import match_batch_cases
from .config import load_last_workspace, save_last_workspace
from .copilot_ui import PlaywrightCopilotAdapter
from .edge_session import EdgeSession
from .error_reporting import write_error_report
from .errors import ApplicationError, BatchLockedError, WorkspaceError
from .identity import windows_account_name
from .logs import CaseLog, LOG_FILENAME, REVIEW_REQUIRED, SUCCESS, new_run_id
from .models import BatchInfo
from .paths import LocalSimulationResolver, WindowsSDriveResolver
from .profile_storage import default_edge_profile
from .queue_builder import build_preflight
from .resources import load_case_workbook, load_text_resource
from .workspace import validate_runtime_resources, validate_workspace


PROJECT_NAME = "Justify IP Change - Copilot Chat UI"
_LAST_WORKSPACE = None


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=PROJECT_NAME)
    parser.add_argument("--workspace", type=Path, help="Working Space\\Copilot resources folder on S: or its mapped UNC share")
    parser.add_argument("--batches", nargs="*", help="batch names or displayed numbers")
    parser.add_argument("--dry-run", action="store_true", help="validate and print the queue without opening Edge or writing the user log")
    parser.add_argument("--retry-review-required", action="store_true", help="explicitly requeue uncertain prior submissions after operator review")
    parser.add_argument("--port", type=int, default=9445)
    parser.add_argument("--tabs", type=int, default=6, help="parallel Copilot tabs to use (1-6; default: 6)")
    parser.add_argument("--edge-path", type=Path)
    parser.add_argument("--profile-dir", type=Path)
    parser.add_argument("--model", help="exact visible Copilot model label; retain the account's current choice when omitted")
    parser.add_argument("--simulation-root", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def _select_workspace(args: argparse.Namespace):
    global _LAST_WORKSPACE
    supplied = str(args.workspace) if args.workspace else ""
    remembered = load_last_workspace()
    reused_remembered = not supplied and bool(remembered)
    if not supplied:
        if remembered:
            supplied = remembered
            print(f"Using previously confirmed workspace: {remembered}")
        else:
            supplied = input("Paste the path to Working Space\\Copilot resources: ").strip()
    if not supplied:
        raise WorkspaceError("No workspace was selected.")
    resolver = LocalSimulationResolver(args.simulation_root) if args.simulation_root else WindowsSDriveResolver()
    workspace = validate_workspace(supplied, resolver)
    # Register the validated workspace before any remembered-config write can fail.
    _LAST_WORKSPACE = workspace
    if not args.simulation_root and not reused_remembered:
        try:
            save_last_workspace(workspace.selected)
        except OSError as exc:
            report_path = write_error_report(workspace, exc, stage="workspace_remember")
            print("WARNING: the confirmed workspace could not be remembered; continuing with this run.", file=sys.stderr)
            if report_path:
                print("Support error report saved under the workspace Error logs folder.", file=sys.stderr)
    return workspace


def _eligible_batches(batches: list[BatchInfo], records, latest):
    eligible = []
    completed = []
    no_runnable = []
    discovery_blocked = []
    for batch in batches:
        if batch.completed_by:
            completed.append(batch)
            continue
        matched, discovery_errors = match_batch_cases(batch, records)
        rows = [row for row, _ in matched]
        successful = sum(1 for row in rows if latest.get(row.canonical_key) and latest[row.canonical_key].status == SUCCESS)
        review = sum(1 for row in rows if latest.get(row.canonical_key) and latest[row.canonical_key].status in REVIEW_REQUIRED)
        remaining = len(rows) - successful
        if discovery_errors:
            discovery_blocked.append(batch)
        if rows and successful == len(rows):
            print(
                f"REQUIRES REVIEW {batch.name}: all {len(rows)} cases are successful in the user log, "
                "but no direct batch-root IPs workbook exists. It will not be rerun."
            )
            continue
        if remaining <= 0:
            no_runnable.append(batch)
            continue
        eligible.append((batch, len(rows), successful, review, remaining))
    if completed:
        print(describe_batch_ranges(completed, verb="are excluded because a completed Excel output exists"))
    if no_runnable:
        print(describe_batch_ranges(no_runnable, verb="are excluded because no automatically runnable cases remain"))
    if discovery_blocked:
        print(describe_batch_ranges(discovery_blocked, verb="have cases blocked by discovery errors"))
    return eligible


def _select_batches(args: argparse.Namespace, eligible) -> list[BatchInfo]:
    if not eligible:
        raise ApplicationError("No incomplete, non-completed batch is currently runnable.")
    print("\nRunnable batches:")
    for index, (batch, total, successful, review, remaining) in enumerate(eligible, 1):
        print(f"  {index}. {batch.name} — total {total}, successful {successful}, review {review}, remaining {remaining}")
    raw = args.batches
    if not raw:
        raw = [item.strip() for item in input("Select one or more batch numbers or names, separated by commas: ").split(",") if item.strip()]
    tokens = [piece.strip() for item in raw for piece in str(item).split(",") if piece.strip()]
    chosen: list[BatchInfo] = []
    by_name = {item[0].name.casefold(): item[0] for item in eligible}
    for token in tokens:
        if token.isdigit() and 1 <= int(token) <= len(eligible):
            batch = eligible[int(token) - 1][0]
        else:
            batch = by_name.get(token.casefold())
        if batch is None:
            raise ApplicationError(f"Unknown or unavailable batch selection: {token}")
        if batch not in chosen:
            chosen.append(batch)
    if not chosen:
        raise ApplicationError("No batches were selected.")
    return sorted(chosen, key=lambda batch: batch.sort_key)


def _print_preflight(workspace, user, log_path, report) -> None:
    print("\nPREFLIGHT SUMMARY")
    print("Selected batches: " + ", ".join(batch.name for batch in report.selected_batches))
    print(f"Total discovered cases: {report.total_discovered}")
    print(f"Already successful: {report.successful}")
    print(f"Remaining eligible cases: {report.remaining}")
    print(f"Cases blocked by validation: {len(report.blocked)}")
    for summary in report.summaries:
        for warning in summary.warnings:
            print(f"WARNING {summary.batch.name}: {warning}")
    if report.blocked:
        print("\nBlocked cases:")
        for message in report.blocked:
            print("- " + message)


def run_cli(args: argparse.Namespace) -> int:
    global _LAST_WORKSPACE
    if not 1 <= args.tabs <= 6:
        raise ApplicationError("--tabs must be between 1 and 6.")
    workspace = _select_workspace(args)
    _LAST_WORKSPACE = workspace
    resources = validate_runtime_resources(workspace)
    records = load_case_workbook(resources["07_Interested_Parties_Changes_15576.csv"])
    base_message = load_text_resource(resources["base_message.md"])
    # Validate the instructions as text before passing it to the visible UI.
    load_text_resource(resources["IP_Review_LLM_Instructions.md"])
    user = windows_account_name()
    user_folder = workspace.users / user
    log_path = user_folder / LOG_FILENAME
    log = CaseLog(log_path, user)
    latest = log.latest()
    batches = discover_batches(workspace.data_root)
    eligible = _eligible_batches(batches, records, latest)
    selected = _select_batches(args, eligible)
    report = build_preflight(
        selected,
        records,
        latest,
        merged_root=workspace.merged_pdfs,
        instructions_path=resources["IP_Review_LLM_Instructions.md"],
        base_message=base_message,
        retry_review_required=args.retry_review_required,
    )
    _print_preflight(workspace, user, log_path, report)
    if args.dry_run:
        print("\nDry run complete. Edge was not opened and no operational log was written.")
        return 0 if not report.blocked else 2
    if not report.queue:
        raise ApplicationError("No validated cases remain in the selected continuous queue.")
    answer = input("\nStart this visible Copilot run and lock the selected batches [y/N]? ").strip().casefold()
    if answer not in {"y", "yes"}:
        print("Run cancelled before Edge startup; no batch lock was retained.")
        return 0
    profile = args.profile_dir or default_edge_profile()
    user_folder.mkdir(parents=True, exist_ok=True)
    adapter = PlaywrightCopilotAdapter(
        EdgeSession(profile, args.port, args.edge_path), model=args.model,
        tab_count=min(args.tabs, len(report.queue)),
    )
    result = asyncio.run(execute_queue(report, workspace, log, adapter, user=user, run_id=new_run_id()))
    print(
        f"Run finished: processed {result.processed}, successful {result.successful}, "
        f"failed {result.failed}, requires review {result.review_required}."
    )
    return 0 if result.failed == 0 and result.review_required == 0 else 2


def main(argv=None) -> int:
    try:
        return run_cli(parse_args(argv))
    except KeyboardInterrupt:
        print("\nInterrupted. The active outcome was preserved where possible; remaining cases stay resumable.", file=sys.stderr)
        if _LAST_WORKSPACE:
            write_error_report(_LAST_WORKSPACE, KeyboardInterrupt(), stage="operator_interrupt")
        return 130
    except BatchLockedError as exc:
        report_path = write_error_report(_LAST_WORKSPACE, exc, stage="batch_lock")
        details = str(exc)
        try:
            payload = json.loads(details)
            locked = payload.get("batches", [])
            if locked:
                details = describe_batch_ranges(locked, verb="are locked")
                holder = payload.get("holder")
                if holder:
                    details += f" Current holder: {json.dumps(holder, ensure_ascii=False, sort_keys=True)}"
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        print(f"BATCH LOCKED: {details}", file=sys.stderr)
        if report_path:
            print("Support error report saved under the workspace Error logs folder.", file=sys.stderr)
        return 3
    except Exception as exc:
        report_path = write_error_report(_LAST_WORKSPACE, exc, stage="cli_failure")
        detail = str(exc) if isinstance(exc, ApplicationError) else f"{type(exc).__name__} during the run"
        print(f"ERROR: {detail}", file=sys.stderr)
        if report_path:
            print("Support error report saved under the workspace Error logs folder.", file=sys.stderr)
        return 1
