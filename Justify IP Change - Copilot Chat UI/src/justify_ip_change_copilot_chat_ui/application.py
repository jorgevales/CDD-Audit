from __future__ import annotations

import asyncio
from dataclasses import dataclass
import sys

from .copilot_ui import CopilotAdapter
from .errors import CopilotUIError, PostSendCancelledError, SubmissionUncertainError
from .error_reporting import write_error_report
from .logs import BatchLockSet, CaseLog
from .models import PreflightReport, WorkspacePaths
from .progress import ProgressDisplay


@dataclass(frozen=True)
class RunResult:
    processed: int
    successful: int
    failed: int
    review_required: int
    interrupted: bool = False


async def execute_queue(
    report: PreflightReport,
    workspace: WorkspacePaths,
    log: CaseLog,
    adapter: CopilotAdapter,
    *,
    user: str,
    run_id: str,
) -> RunResult:
    progress = ProgressDisplay(len(report.queue))
    progress.show("continuous queue ready")
    processed = successful = failed = review = 0
    run_number = log.next_run_number()
    locks = BatchLockSet(workspace.working_space, [batch.name for batch in report.selected_batches], user, run_id)
    with locks:
        try:
            await adapter.start()
            async def handle_item(item):
                nonlocal processed, successful, failed, review
                print(f"Processing {item.batch.name}: change_id {item.case.change_id}")
                try:
                    outcome = await adapter.process(item)
                    status = outcome.status
                    detail = outcome.detail
                except SubmissionUncertainError as exc:
                    status = "requires_review"
                    detail = str(exc)
                except CopilotUIError as exc:
                    status = "failed"
                    detail = str(exc)
                    write_error_report(workspace, exc, stage="case_processing", batch=item.batch.name, case_key=item.key, run_id=run_id)
                except Exception as exc:
                    status = "failed"
                    detail = f"{type(exc).__name__}: {exc}"
                    write_error_report(workspace, exc, stage="case_processing", batch=item.batch.name, case_key=item.key, run_id=run_id)
                except PostSendCancelledError:
                    log.append(
                        item.case,
                        "requires_review",
                        batch=item.batch.name,
                        attachment_count=len(item.attachments.paths),
                        run_id=run_id,
                        run_number=run_number,
                        detail="operator interruption after Send was attempted; inspect the visible chat before retrying",
                    )
                    progress.recorded("post-send interruption requires review")
                    raise
                except asyncio.CancelledError:
                    log.append(
                        item.case,
                        "interrupted",
                        batch=item.batch.name,
                        attachment_count=len(item.attachments.paths),
                        run_id=run_id,
                        run_number=run_number,
                        detail="operator interruption before a terminal result",
                    )
                    progress.recorded("interrupted and durably logged")
                    raise
                log.append(
                    item.case,
                    status,
                    batch=item.batch.name,
                    attachment_count=len(item.attachments.paths),
                    run_id=run_id,
                    run_number=run_number,
                    detail=detail,
                )
                processed += 1
                successful += status == "successful"
                failed += status == "failed"
                review += status in {"requires_review", "inconclusive_review_needed"}
                progress.recorded(f"last outcome: {status}")
            pending: asyncio.Queue = asyncio.Queue()
            for item in report.queue:
                pending.put_nowait(item)
            async def worker() -> None:
                while True:
                    try:
                        item = pending.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    try:
                        await handle_item(item)
                    finally:
                        pending.task_done()
            workers = [asyncio.create_task(worker()) for _ in range(min(len(report.queue), max(1, int(getattr(adapter, "parallelism", 1)))))]
            try:
                await asyncio.gather(*workers)
            finally:
                for task in workers:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
        finally:
            pending_error = sys.exc_info()[1]
            try:
                await adapter.close()
            except Exception as close_error:
                close_error.diagnostic_stage = "copilot_shutdown"
                write_error_report(workspace, close_error, stage="copilot_shutdown", run_id=run_id)
                if pending_error is None:
                    raise
    return RunResult(processed, successful, failed, review)
