from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

from .application import execute_queue
from .batch_discovery import discover_batches
from .case_discovery import match_batch_cases
from .config import load_last_workspace, save_last_workspace
from .copilot_ui import PlaywrightCopilotAdapter
from .edge_session import EdgeSession
from .errors import ApplicationError, BatchLockedError, WorkspaceError
from .identity import windows_account_name
from .logs import CaseLog, LOG_FILENAME, REVIEW_REQUIRED, SUCCESS, new_run_id
from .models import BatchInfo
from .paths import LocalSimulationResolver, WindowsSDriveResolver
from .queue_builder import build_preflight
from .resources import load_case_workbook, load_text_resource
from .workspace import validate_runtime_resources, validate_workspace


PROJECT_NAME = "Justify IP Change - Copilot Chat UI"


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=PROJECT_NAME)
    parser.add_argument("--workspace", type=Path, help="Working Space\\Copilot resources folder on S: or its mapped UNC share")
    parser.add_argument("--batches", nargs="*", help="batch names or displayed numbers")
    parser.add_argument("--dry-run", action="store_true", help="validate and print the queue without opening Edge or writing the user log")
    parser.add_argument("--retry-review-required", action="store_true", help="explicitly requeue uncertain prior submissions after operator review")
    parser.add_argument("--port", type=int, default=9445)
    parser.add_argument("--edge-path", type=Path)
    parser.add_argument("--profile-dir", type=Path)
    parser.add_argument("--model", help="exact visible Copilot model label; retain the account's current choice when omitted")
    parser.add_argument("--simulation-root", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def _select_workspace(args: argparse.Namespace):
    supplied = str(args.workspace) if args.workspace else ""
    remembered = load_last_workspace()
    if not supplied:
        if remembered:
            print(f"Last workspace: {remembered}")
        supplied = input("Paste the path to Working Space\\Copilot resources" + (" or press Enter to reuse it" if remembered else "") + ": ").strip() or remembered
    if not supplied:
        raise WorkspaceError("No workspace was selected.")
    resolver = LocalSimulationResolver(args.simulation_root) if args.simulation_root else WindowsSDriveResolver()
    workspace = validate_workspace(supplied, resolver)
    if not args.simulation_root:
        save_last_workspace(workspace.selected)
    return workspace


def _eligible_batches(batches: list[BatchInfo], records, latest):
    eligible = []
    for batch in batches:
        if batch.completed_by:
            print(f"Excluded {batch.name}: completed by {batch.completed_by.name}")
            continue
        matched, discovery_errors = match_batch_cases(batch, records)
        rows = [row for row, _ in matched]
        successful = sum(1 for row in rows if latest.get(row.canonical_key) and latest[row.canonical_key].status == SUCCESS)
        review = sum(1 for row in rows if latest.get(row.canonical_key) and latest[row.canonical_key].status in REVIEW_REQUIRED)
        remaining = len(rows) - successful - review
        if discovery_errors:
            print(f"WARNING {batch.name}: {len(discovery_errors)} case folder(s) are blocked by discovery errors.")
        if rows and successful == len(rows):
            print(
                f"REQUIRES REVIEW {batch.name}: all {len(rows)} cases are successful in the user log, "
                "but no direct batch-root IPs workbook exists. It will not be rerun."
            )
            continue
        if remaining <= 0:
            print(f"Excluded {batch.name}: no automatically runnable cases ({successful} successful, {review} require review).")
            continue
        eligible.append((batch, len(rows), successful, review, remaining))
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
    print(f"Selected workspace: {workspace.selected}")
    print(f"Copilot resources: {workspace.copilot_resources}")
    print(f"Users folder: {workspace.users}")
    print(f"Windows account: {user}")
    print(f"User log: {log_path}")
    print("Selected batches: " + ", ".join(batch.name for batch in report.selected_batches))
    print(f"Total discovered cases: {report.total_discovered}")
    print(f"Already successful: {report.successful}")
    print(f"Remaining eligible cases: {report.remaining}")
    print(f"Cases blocked by validation: {len(report.blocked)}")
    print(f"Expected attachment operations: {report.attachment_count}")
    for summary in report.summaries:
        for warning in summary.warnings:
            print(f"WARNING {summary.batch.name}: {warning}")
    if report.blocked:
        print("\nBlocked cases:")
        for message in report.blocked:
            print("- " + message)


def run_cli(args: argparse.Namespace) -> int:
    workspace = _select_workspace(args)
    resources = validate_runtime_resources(workspace)
    records = load_case_workbook(resources["07_Interested_Parties_Changes_15576.xlsx"])
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
    local_base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    profile = args.profile_dir or local_base / "CDD Audit" / "JustifyIPChangeCopilotChatUI" / "EdgeProfile"
    user_folder.mkdir(parents=True, exist_ok=True)
    adapter = PlaywrightCopilotAdapter(EdgeSession(profile, args.port, args.edge_path), model=args.model)
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
        return 130
    except BatchLockedError as exc:
        print(f"BATCH LOCKED: {exc}", file=sys.stderr)
        return 3
    except (ApplicationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
