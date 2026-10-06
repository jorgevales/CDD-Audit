#!/usr/bin/env python3
"""Open Microsoft 365 Copilot tabs and process up to three cases per tab.

V41 non-terminal upload-failure queue-tail deferral, V40 persistent WebSocket-first CDP recovery and playwright-bulk quarantine, V39 permanent password-protected evidence exclusion, V38 strong attachment-transfer completion with adaptive multi-signal verification and ranked recovery, V35 immediate wake-loop handoff with cancellable background wake probes, V34 high-count upload stabilization, native Try-again recovery, no duplicate partial re-assignment, and phase-aware retries, V33 independently identifiable collision aliases with mandatory separate-file analysis, V32 15-character selective naming with protected Audit History and email files, V31 password-required exclusion and selective original-name staging, V30 work-conserving type-agnostic queue with immediate free-tab reuse for normal and final-attempt workloads, V29 run-global Opus availability circuit breaker and startup large-model choice, V28 adaptive technique scoring, generic-title reasoning-complete gate, New Chat regeneration, and Opus fallback, V27 CDP-gated visible wake traversal with foreground-verified title reads and lossless reuse queue recovery, V26 durable CDP recovery with target-identity rebinding and in-memory state preservation, V25 complete visible wake-wave traversal, assignment-token title-gated capture, early latest-status eligibility, and V18 strict send-proof and fresh-chat multi-route tab recovery, V17 Edge stability cleanup and resource monitoring, V16 collapsed GPT Think selector recognition, V15 immediate visible post-send handoff, one-selection bulk attachment, multi-signal fast validation, safe partial recovery, and V14 non-destructive post-send verification, bounded next-tab attachment prefetch, validated UI handle cache, run-level filesystem and plan caches, hidden-window restoration, final unsent-message recovery, failed-tab wake exclusion, stronger server wake, selectable sequential full-tab flow, continuous completed-tab wake, medium-plus-complete-small packing, stop-safe send control, interrupted-response regeneration, all-port pending-tab wake, concise tab and attachment reporting, multi-strategy parallel send arbitration, upload-safe retained staging, single-assignment V30 attachment control, clean structured logging, six-second readiness wake, and exact CDP target acquisition with dynamic case-size batching with safe preflight cleanup, confirmation gate, small-case priority, one-large-case reservation, category-specific models, duplicate-filename support, and no-skip workflow. Each tab receives the Markdown methodology plus one
case-specific merged PDF per case. When CASES_PER_TAB is 1, up to 18 original
case files are also attached as fallback context, prioritizing files recorded as failed
in the case-specific merge-status JSON before filling remaining slots by file size. Each file path is assigned exactly once per tab using a fast CDP call. Delayed
confirmation never triggers assignment of the same path again,
preventing a hidden 21st upload attempt at the 20-file limit.
Large local files are assigned directly to
Edge through Chrome DevTools Protocol DOM.setFileInputFiles, avoiding
Playwright's 50 MB remote file-transfer ceiling.
"""

from __future__ import annotations
from .prompt_resources import load_base_message

import argparse
from dataclasses import dataclass
import csv
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
import threading
import urllib.error
import urllib.request
import traceback
import gc
import tempfile
import stat
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from html import unescape
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence

# Every existing print call receives total-run and previous-log elapsed times.
_PROCESS_STARTED_AT = time.perf_counter()
_LAST_LOG_AT = _PROCESS_STARTED_AT
_BUILTIN_PRINT = print

def print(*values: object, **kwargs: Any) -> None:
    """Print clean timestamped lines with elapsed time."""
    global _LAST_LOG_AT
    now = time.perf_counter()
    total = now - _PROCESS_STARTED_AT
    step = now - _LAST_LOG_AT
    _LAST_LOG_AT = now
    destination = kwargs.pop("file", sys.stdout)
    flush = kwargs.pop("flush", True)
    message = " ".join(str(value) for value in values)
    lines = message.splitlines() or [""]
    for line in lines:
        prefix = f"[{time.strftime('%H:%M:%S')}] [{total:7.2f}s] [+{step:6.2f}s]"
        _BUILTIN_PRINT(prefix, line, file=destination, flush=flush, **kwargs)


def stage_heading(title: str) -> None:
    line = "=" * 78
    print("")
    print(line)
    print(title)
    print(line)


def step_heading(title: str) -> None:
    print("")
    print(f"--- {title} ---")


if TYPE_CHECKING:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        Locator,
        Page,
    )


class MissingDependencyError(RuntimeError):
    """Raised when the local Playwright package is unavailable."""
class FreshChatRequiredError(RuntimeError):
    """A composer/upload failure that requires a brand-new chat and route."""
class CDPConnectionLostError(RuntimeError):
    """Transient dedicated-CDP outage; workload and route state must be preserved."""
class TabStartFreshChatRequiredError(FreshChatRequiredError):
    """The selected renderer cannot expose Copilot controls and must be replaced."""



class _UninitializedPlaywrightError(Exception):
    """Placeholder replaced by Playwright's error type before automation runs."""


PlaywrightError: type[Exception] = _UninitializedPlaywrightError
PlaywrightTimeoutError: type[Exception] = TimeoutError
async_playwright: Any = None


DEFAULT_CDP_PORT = 9223
DEFAULT_COPILOT_URL = "https://m365.cloud.microsoft/chat"
DEFAULT_TAB_COUNT = 6
CASES_PER_TAB = 1
DEFAULT_CASE_COUNT = 1000
MAXIMUM_TAB_COUNT = 6
CONTINUOUS_QUEUE_BUILD = "2026-09-11-password-protected-exclusion-v39"
DEFAULT_TABS_VISIBLE = True
DEFAULT_DWELL_SECONDS = 0.45
DEFAULT_WAKE_MAX_ROUNDS = 0  # 0 = keep waking until all generic Chat Copilot titles change
DEFAULT_SMALL_CASE_MODEL_NAME = "GPT 5.6 Think Deeper"
DEFAULT_MEDIUM_CASE_MODEL_NAME = "GPT 5.6 Think Deeper"
DEFAULT_LARGE_CASE_MODEL_NAME = "Opus"
DEFAULT_LARGE_CASE_MODEL_FALLBACK = "GPT 5.6 Think Deeper"
GPT_6_SOL_MODEL_NAME = "GPT 6.0 Sol"
_OPUS_GLOBALLY_DISABLED = False
_OPUS_DISABLE_REASON = ""
DEFAULT_REQUIRE_SEND_CONFIRMATION = True
DEFAULT_SAFE_EDGE_CLEANUP = True
DEFAULT_CDP_HEALTH_ATTEMPTS = 3
DEFAULT_CDP_HEALTH_DELAY_SECONDS = 0.10
DEFAULT_INTER_TAB_COOLDOWN_SECONDS = 2.0
ADAPTIVE_MODEL_SWITCH_GENERATION = 3
ADAPTIVE_SINGLE_CASE_GENERATION = 5
MALFORMED_CAPTURE_CONFIRMATION_PASSES = 3
_CURRENT_RETRY_GENERATION = 0
DEFAULT_INITIAL_READINESS_BUDGET_SECONDS = 6.0
DEFAULT_INITIAL_WAKE_DWELL_SECONDS = 0.22
PREPARED_COHORT_URL_RECHECKS = 4
PREPARED_COHORT_URL_RECHECK_DELAY_SECONDS = 0.05
PREPARED_COHORT_MAX_UNRESOLVED_PAGES = 1
ATTACHMENT_STALL_RECOVERY_SECONDS = 1.25
ATTACHMENT_RECOVERY_ATTEMPTS = 8
ATTACHMENT_BETWEEN_FILES_SECONDS = 0.12
ATTACHMENT_CHIP_STABLE_SECONDS = 0.30
ATTACHMENT_FINAL_SETTLE_SECONDS = 1.00
UPLOAD_ERROR_TEXT = "An error occurred while uploading your file. Please try again."
UPLOAD_ERROR_PATTERN = re.compile(
    r"an\s+error\s+occurred\s+while\s+uploading(?:\s+your\s+file)?[.,]?\s+please\s+try\s+again[.]?",
    re.IGNORECASE,
)
# playwright_bulk is quarantined because it can destabilise the browser-level CDP endpoint.
ATTACHMENT_RECOVERY_ROUTES = ("bulk_cdp", "sequential_cdp")
MAX_FRESH_CHAT_RECOVERY_ROUNDS = len(ATTACHMENT_RECOVERY_ROUTES)
_ATTACHMENT_ROUTE_BY_PAGE: dict[int, str] = {}
_ATTACHMENT_FAILED_ROUTES_BY_PAGE: dict[int, set[str]] = {}

@dataclass
class TechniqueScore:
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    latency_ema: float = 0.0

    @property
    def value(self) -> float:
        # Bayesian prior prevents one early success from permanently dominating.
        reliability = (self.successes + 1.0) / (self.successes + self.failures + 2.0)
        failure_penalty = min(0.35, self.consecutive_failures * 0.08)
        latency_penalty = min(0.20, self.latency_ema / 120.0)
        return reliability - failure_penalty - latency_penalty

_TECHNIQUE_SCORES: dict[str, dict[str, TechniqueScore]] = {}
_TECHNIQUE_SCORE_LOCK = threading.RLock()

def technique_rank(domain: str, techniques: Sequence[str]) -> list[str]:
    if domain == "attachment":
        techniques = tuple(name for name in techniques if name != "playwright_bulk")
    with _TECHNIQUE_SCORE_LOCK:
        table = _TECHNIQUE_SCORES.setdefault(domain, {})
        indexed = list(enumerate(techniques))
        return [name for _, name in sorted(
            indexed, key=lambda item: (-table.setdefault(item[1], TechniqueScore()).value, item[0])
        )]

def reward_technique(domain: str, technique: str, success: bool, elapsed: float = 0.0) -> None:
    with _TECHNIQUE_SCORE_LOCK:
        score = _TECHNIQUE_SCORES.setdefault(domain, {}).setdefault(technique, TechniqueScore())
        if success:
            score.successes += 1
            score.consecutive_failures = 0
        else:
            score.failures += 1
            score.consecutive_failures += 1
        if elapsed > 0:
            score.latency_ema = elapsed if score.latency_ema <= 0 else score.latency_ema * 0.8 + elapsed * 0.2

def technique_summary(domain: str) -> str:
    with _TECHNIQUE_SCORE_LOCK:
        table = _TECHNIQUE_SCORES.get(domain, {})
        ranked = sorted(table.items(), key=lambda item: -item[1].value)
        return ", ".join(f"{name}:{score.successes}/{score.successes+score.failures}" for name, score in ranked)
SEND_PARALLEL_ROUNDS = 12
SEND_ROUND_OBSERVE_SECONDS = 0.45
SEND_STRATEGY_STAGGER_SECONDS = 0.035
TERMINAL_WHITE_ON_YELLOW = "\033[37;43m"
TERMINAL_STYLE_RESET = "\033[0m"
_RETAINED_ATTACHMENT_STAGES: list[Path] = []
_LAST_WAKE_STATUS: tuple[int, int, int] | None = None
_WAKE_INITIAL_REMAINING = 0
COPILOT_ATTACHMENT_LIMIT = 20
SINGLE_CASE_EXTRA_ATTACHMENT_LIMIT = COPILOT_ATTACHMENT_LIMIT - 2
BASE_MESSAGE = load_base_message()
AUDIT_OVERALL_LABEL = "All files for all cases were exposed:"
AUDIT_ALLOWED_STATUSES = {"successful", "failed", "inconclusive_review_needed"}
AUDIT_PENDING_TITLE = "Chat | Microsoft Copilot"
AUDIT_RESPONSE_ATTEMPTS = 12
AUDIT_RESPONSE_RETRY_SECONDS = 0.50
FAILED_RESULT_EARLY_PROBE_SECONDS = 0.45
FAILED_RESULT_STABILITY_PASSES = 2
DEFAULT_DATA_ROOT = Path.home() / "CopilotCaseAutomation" / "data"
DEFAULT_RESOURCES_ROOT = Path.home() / "CopilotCaseAutomation" / "resources"
DEFAULT_CSV_PATH = DEFAULT_DATA_ROOT / "source_cases.csv"
DEFAULT_COMPLETED_PATH = DEFAULT_DATA_ROOT / "completed_change_ids.csv"
DEFAULT_LOG_PATH = DEFAULT_DATA_ROOT / "fully_sent_change_ids_log.csv"
DEFAULT_INSTRUCTIONS_PATH = DEFAULT_RESOURCES_ROOT / "review_instructions.md"
DEFAULT_CASE_FILES_ROOT = DEFAULT_DATA_ROOT / "case_files"
DEFAULT_MERGED_PDFS_ROOT = DEFAULT_CASE_FILES_ROOT / "Merged_PDFs"
DEFAULT_CASE_SIZE_OUTPUT_ROOT = DEFAULT_DATA_ROOT / "outputs"
REQUIRED_COLUMNS = [
    "change_id", "InterestedPartyId", "InterestedPartyCurrentName",
    "Date_of_birth", "Status", "ActionDateTime", "ActionUserId",
    "ActionUserName", "ActionUserTeam", "ChangedSections", "ChangedFields",
    "PreviousValues", "NewValues", "FieldChangeCount",
]

DEFAULT_PAGE_TIMEOUT_SECONDS = 6
DEFAULT_LOGIN_TIMEOUT_SECONDS = 12
DEFAULT_PARALLEL_LOADS = 1
DEFAULT_ANALYSIS_WORKERS = max(2, min(12, os.cpu_count() or 4))
FAST_ATTACH_MAX_DEPTH = 40
FAST_ATTACH_ASSIGN_TIMEOUT_SECONDS = 3.0
FAST_ATTACH_CONFIRM_SLICE_SECONDS = 0.18
FAST_ATTACH_POLL_SECONDS = 0.025
ATTACHMENT_WARNING_RECHECK_SECONDS = 0.35
ATTACHMENT_INPUT_READY_TIMEOUT_SECONDS = 2.0
ATTACHMENT_CONFIRM_DIAGNOSTIC_SECONDS = 8.0
DIAGNOSTIC_FOLDER_NAME = "Copilot_Automation_Diagnostics"
VERBOSE_FILE_INPUT_DETAILS = False
TAB_OPERATION_ATTEMPTS = 5
TAB_ACTIVE_READY_SECONDS = 6.0
TAB_RELOAD_TIMEOUT_MS = 5_000
TARGET_DISCOVERY_TIMEOUT_SECONDS = 1.25
TARGET_CREATE_TIMEOUT_SECONDS = 2.0
TARGET_FALLBACK_TIMEOUT_SECONDS = 3.0
FAST_SINGLE_FILE_DEADLINE_SECONDS = 20.0
SINGLE_CASE_FILE_CONFIRM_SECONDS = 75.0
FAST_TAB_ATTACH_DEADLINE_SECONDS = 90.0
SINGLE_CASE_TAB_ATTACH_DEADLINE_SECONDS = 900.0
SINGLE_CASE_UPLOAD_FINISH_TIMEOUT_MS = 600_000
SINGLE_CASE_SEND_TIMEOUT_MS = 45_000
ATTACHMENT_ASSIGN_RETRIES = 1
FAST_NAVIGATION_TIMEOUT_MS = 2500
FAST_UI_READY_TIMEOUT_MS = 6000
FAST_UI_RECHECKS = 120
FAST_UI_RECHECK_DELAY_SECONDS = 0.050
FAST_MESSAGE_TIMEOUT_MS = 3500
FAST_MODEL_TIMEOUT_MS = 3500
FAST_SEND_TIMEOUT_MS = 5000
CDP_CONNECT_ATTEMPTS = 20
CDP_CONNECT_TIMEOUT_MS = 30000
CDP_CONNECT_RETRY_DELAY_SECONDS = 0.08
CDP_STABLE_SUCCESS_CHECKS = 2
CDP_HANDSHAKE_TIMEOUT_LADDER_MS = (3000, 6000, 12000, 20000, 30000)
CDP_HANDSHAKE_ROUTES = ("websocket", "http")
CDP_ENDPOINT_PROBE_TIMEOUT_SECONDS = 1.25
CDP_CONNECT_STATUS_FAST_SECONDS = 5.0
CDP_CONNECT_STATUS_SLOW_SECONDS = 15.0
CDP_OUTAGE_RECOVERY_ATTEMPTS = 40
CDP_OUTAGE_RECOVERY_DELAY_SECONDS = 0.25
CDP_OPERATION_RETRIES = 4
POST_SEND_ACTIVATION_ROUNDS = 3
POST_SEND_ACTIVE_DWELL_SECONDS = 0.80
POST_SEND_RESPONSE_PROBE_SECONDS = 2.50
POST_SEND_HANDOFF_TOTAL_TIMEOUT_SECONDS = 1.50
POST_SEND_HANDOFF_ROUTE_TIMEOUT_SECONDS = 0.35
POST_SEND_COMMIT_TIMEOUT_SECONDS = 5.0
POST_SEND_PROGRESS_WATCHDOG_SECONDS = 8.0
TAB_ACTIVATION_TOTAL_TIMEOUT_SECONDS = 2.25
TAB_ACTIVATION_ROUTE_TIMEOUT_SECONDS = 0.45
TAB_START_PROGRESS_TIMEOUT_SECONDS = 5.0
TAB_START_RECOVERY_ATTEMPTS = 2
TAB_START_REPLACEMENT_ATTEMPTS = 2
TAB_START_FRESH_PAGE_CREATE_TIMEOUT_SECONDS = 3.0
TAB_START_FRESH_NAVIGATION_TIMEOUT_SECONDS = 5.0
TAB_START_FRESH_READY_TIMEOUT_SECONDS = 6.0
TAB_START_OLD_PAGE_CLOSE_TIMEOUT_SECONDS = 0.40
LEGACY_DROP_ASSIGN_TIMEOUT_SECONDS = 5.0
LEGACY_DROP_ERROR_PROBE_SECONDS = 0.35
LEGACY_DROP_START_CONFIRM_SECONDS = 2.50
LEGACY_DROP_ZERO_RETRY_CONFIRM_SECONDS = 4.00
LEGACY_DROP_START_POLL_SECONDS = 0.05
LEGACY_PREP_TRANSFER_PROBE_SECONDS = 0.30
LEGACY_PENDING_ROUND_DELAY_SECONDS = 0.08
LEGACY_PENDING_MAX_STAGNANT_ROUNDS = 12
LEGACY_REUSE_CAPTURE_DRAIN_DELAY_SECONDS = 0.02
LEGACY_REUSE_PREP_SWEEP_DELAY_SECONDS = 0.06
LEGACY_REUSE_MAX_STAGNANT_SWEEPS = 10
LEGACY_IMMEDIATE_SEND_PROBE_TIMEOUT_SECONDS = 0.65
LEGACY_FORCE_TRANSFER_MIN_INTERVAL_SECONDS = 0.30
LEGACY_FORCE_TRANSFER_ROUTE_TIMEOUT_SECONDS = 0.45
LEGACY_FORCE_TRANSFER_SETTLE_SECONDS = 0.05
UPLOAD_ACCELERATOR_PULSE_SECONDS = 0.15
UPLOAD_ACCELERATOR_COMMAND_TIMEOUT_SECONDS = 0.30
UPLOAD_ACCELERATOR_STALL_SECONDS = 1.25
UPLOAD_ACCELERATOR_FOREGROUND_STALL_SECONDS = 3.50
UPLOAD_ACCELERATOR_LOG_SECONDS = 2.00
STRONG_WAKE_INTERVAL_SECONDS = 0.12
BACKGROUND_WAKE_SHUTDOWN_TIMEOUT_SECONDS = 0.75
BACKGROUND_WAKE_PROBE_TIMEOUT_SECONDS = 0.40
STRONG_WAKE_FOREGROUND_EVERY_ROUNDS = 5
FINAL_SEND_VERIFY_PREFIX_LENGTH = 120
_RUNTIME_EDGE_PORT: Optional[int] = None
_RUNTIME_TABS_HIDDEN = False
NEXT_TAB_PREFETCH_MAX_CONCURRENCY = 1
NEXT_TAB_PREFETCH_START_DELAY_SECONDS = 0.20
BULK_ATTACH_ASSIGN_TIMEOUT_SECONDS = 4.0
BULK_ATTACH_FAST_CONFIRM_SECONDS = 2.25
BULK_ATTACH_GRACE_CONFIRM_SECONDS = 7.50
BULK_ATTACH_STABLE_SECONDS = 0.20
HIGH_COUNT_ATTACHMENT_THRESHOLD = 15
HIGH_COUNT_BULK_GRACE_SECONDS = 18.0
UPLOAD_TRY_AGAIN_ATTEMPTS = 4
UPLOAD_TRY_AGAIN_SETTLE_SECONDS = 2.0
POST_ATTACHMENT_OPERATION_ATTEMPTS = 4
TRANSFER_VERIFY_FAST_SECONDS = 3.0
TRANSFER_VERIFY_RECOVERY_SECONDS = 9.0
TRANSFER_QUIET_STABLE_SECONDS = 0.55
TRANSFER_RECOVERY_ATTEMPTS = 6
TRANSFER_ACTIVITY_POLL_SECONDS = 0.06
FIRST_BULK_TRANSFER_TIMEOUT_SECONDS = 160.0
RETRY_TRANSFER_TIMEOUT_SECONDS = 180.0
CACHED_LOCATOR_FAST_TIMEOUT_MS = 120
RESOURCE_MONITOR_INTERVAL_SECONDS = 5.0
RESOURCE_LOG_INTERVAL_SECONDS = 30.0
RESOURCE_CRITICAL_MEMORY_PERCENT = 92.0
RESOURCE_LOW_DISK_GB = 5.0
RESOURCE_CRITICAL_DISK_GB = 2.0
STALE_SCRIPT_TEMP_MAX_AGE_HOURS = 12.0
EDGE_CACHE_MAX_AGE_DAYS = 7.0
RESOURCE_CLEANUP_COOLDOWN_SECONDS = 60.0
USER_TEMP_PATH = Path.home() / "Temp"
USER_TEMP_CLEANUP_INTERVAL_SECONDS = 60.0
_CASE_FILES_CACHE: dict[tuple[str,str], tuple[Path,...]] = {}
_FAILED_FILES_CACHE: dict[tuple[str,str,str], tuple[Path,...]] = {}
_UNUSABLE_FILES_CACHE: dict[tuple[str,str,str], tuple[Path,...]] = {}
_MERGED_PDF_CACHE: dict[tuple[str,str], tuple[Path,...]] = {}
_ATTACHMENT_PLAN_CACHE: dict[tuple[tuple[str,...],str,str,str,str], tuple[tuple[Path,...],dict[str,int],int]] = {}
_PAGE_UI_CACHE: dict[int, dict[str,Any]] = {}
_RUN_BATCHES: list[dict[str, Any]] = []
_PREPARED_COPILOT_PAGE_IDS: set[int] = set()
_LEGACY_STAGED_NAMES_BY_PAGE: dict[int, tuple[str, ...]] = {}
_LEGACY_STAGED_PATHS_BY_PAGE: dict[int, tuple[Path, ...]] = {}
_LEGACY_FORCE_TRANSFER_LAST_AT: dict[int, float] = {}
_LEGACY_FORCE_TRANSFER_ROUND: dict[int, int] = {}
_UPLOAD_ACCELERATOR: Any = None
_UPLOAD_PROGRESS_BY_PAGE: dict[int, dict[str, Any]] = {}
_FULL_BATCH_PLAN: list[dict[str, Any]] = []
_DEFERRED_BATCH_QUEUE: list[dict[str, Any]] = []



def _safe_remove_path(path: Path) -> int:
    """Remove one non-current cache/temp path and return bytes released when known."""
    try:
        if not path.exists() and not path.is_symlink():
            return 0
        size = 0
        if path.is_file() or path.is_symlink():
            try: size = path.stat().st_size
            except OSError: pass
            path.unlink(missing_ok=True)
            return size
        for item in path.rglob('*'):
            try:
                if item.is_file(): size += item.stat().st_size
            except OSError:
                pass
        shutil.rmtree(path, ignore_errors=True)
        return size
    except OSError:
        return 0


def _path_age_seconds(path: Path) -> float:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return 0.0


def clean_stale_script_temp_files(max_age_hours: float = STALE_SCRIPT_TEMP_MAX_AGE_HOURS) -> tuple[int, int]:
    """Clean only this script's abandoned attachment staging directories."""
    root = Path(tempfile.gettempdir())
    threshold = max_age_hours * 3600.0
    removed = released = 0
    try:
        candidates = list(root.glob('copilot_case_attachments_*'))
    except OSError:
        candidates = []
    for path in candidates:
        if _path_age_seconds(path) < threshold:
            continue
        released += _safe_remove_path(path)
        if not path.exists(): removed += 1
    return removed, released


def clean_safe_edge_cache(profile_directory: Path) -> tuple[int, int]:
    """Clean recreatable cache data only; never touch sessions, cookies or tabs."""
    profile = profile_directory.expanduser().resolve()
    names = {'Cache', 'Code Cache', 'GPUCache', 'DawnCache', 'GrShaderCache', 'ShaderCache'}
    removed = released = 0
    if not profile.exists():
        return removed, released
    for candidate in profile.rglob('*'):
        try:
            if not candidate.is_dir() or candidate.name not in names:
                continue
            released += _safe_remove_path(candidate)
            if not candidate.exists(): removed += 1
        except OSError:
            continue
    return removed, released


def system_resource_snapshot(path: Path) -> dict[str, float]:
    """Return physical-memory and disk health without requiring psutil."""
    snapshot = {'memory_percent': 0.0, 'available_memory_gb': 0.0, 'free_disk_gb': 0.0}
    try:
        usage = shutil.disk_usage(path)
        snapshot['free_disk_gb'] = usage.free / (1024 ** 3)
    except OSError:
        pass
    if os.name == 'nt':
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
                ]
            status = MEMORYSTATUSEX(); status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                snapshot['memory_percent'] = float(status.dwMemoryLoad)
                snapshot['available_memory_gb'] = status.ullAvailPhys / (1024 ** 3)
        except Exception:
            pass
    else:
        try:
            values = {}
            for line in Path('/proc/meminfo').read_text(encoding='ascii').splitlines():
                key, _, value = line.partition(':')
                values[key] = float(value.strip().split()[0]) * 1024
            total = values.get('MemTotal', 0.0); available = values.get('MemAvailable', 0.0)
            if total:
                snapshot['memory_percent'] = 100.0 * (1.0 - available / total)
                snapshot['available_memory_gb'] = available / (1024 ** 3)
        except (OSError, ValueError):
            pass
    return snapshot


def clean_user_temp_path(*, protect_active_stages: bool = True) -> tuple[int, int, int]:
    """Permanently delete best-effort contents of the configured Windows Temp path.

    Locked/in-use files are skipped immediately. During a live run, active attachment
    staging directories are protected so Edge can continue reading queued files.
    Returns (removed_items, skipped_items, released_bytes).
    """
    root = USER_TEMP_PATH
    if os.name != "nt" or not root.exists() or not root.is_dir():
        return 0, 0, 0
    protected: set[str] = set()
    if protect_active_stages:
        for stage in list(_RETAINED_ATTACHMENT_STAGES):
            try:
                protected.add(os.path.normcase(os.path.normpath(str(stage.resolve()))))
            except OSError:
                continue
    try:
        entries = list(root.iterdir())
    except OSError:
        return 0, 1, 0
    removed = skipped = released = 0
    for entry in entries:
        try:
            key = os.path.normcase(os.path.normpath(str(entry.resolve())))
        except OSError:
            key = os.path.normcase(os.path.normpath(str(entry)))
        if key in protected:
            skipped += 1
            continue
        existed = entry.exists() or entry.is_symlink()
        released += _safe_remove_path(entry)
        if existed and not entry.exists() and not entry.is_symlink():
            removed += 1
        elif existed:
            skipped += 1
    return removed, skipped, released

def startup_edge_stability_cleanup(profile_directory: Path, endpoint_available: bool) -> None:
    """Run a bounded safe cleanup before browser automation begins."""
    stage_heading('STARTUP EDGE STABILITY CLEANUP')
    temp_removed, temp_skipped, temp_released = clean_user_temp_path(protect_active_stages=False)
    print(f"WINDOWS TEMP: permanently removed {temp_removed} item(s), skipped {temp_skipped} locked/in-use item(s); released approximately {temp_released / (1024 ** 2):.1f} MB")
    removed, released = clean_stale_script_temp_files()
    print(f"SCRIPT TEMP: removed {removed} stale staging item(s); released approximately {released / (1024 ** 2):.1f} MB")
    if endpoint_available:
        print('EDGE CACHE: active port detected; cache cleanup skipped to protect live tabs and profile state')
    else:
        count, cache_bytes = clean_safe_edge_cache(profile_directory)
        print(f"EDGE CACHE: removed {count} recreatable cache folder(s); released approximately {cache_bytes / (1024 ** 2):.1f} MB")
    gc.collect()
    snapshot = system_resource_snapshot(profile_directory.parent if profile_directory.parent.exists() else Path.cwd())
    print(f"RESOURCES: RAM {snapshot['memory_percent']:.1f}% used, {snapshot['available_memory_gb']:.2f} GB available; disk {snapshot['free_disk_gb']:.2f} GB free")
    if snapshot['free_disk_gb'] and snapshot['free_disk_gb'] < RESOURCE_CRITICAL_DISK_GB:
        raise RuntimeError(f"Critical disk pressure: only {snapshot['free_disk_gb']:.2f} GB free. Edge launch blocked to avoid profile corruption or abrupt termination.")


async def edge_resource_stability_monitor(
    endpoint: str,
    profile_directory: Path,
    stop_event: asyncio.Event,
) -> None:
    """Monitor resources and CDP health while cleaning only safe script-owned data."""
    last_log = 0.0
    last_cleanup = 0.0
    last_user_temp_cleanup = 0.0
    consecutive_cdp_failures = 0
    disk_root = profile_directory.parent if profile_directory.parent.exists() else Path.cwd()
    while not stop_event.is_set():
        now = time.monotonic()
        snapshot = await asyncio.to_thread(system_resource_snapshot, disk_root)
        payload = await _async_cdp_endpoint_healthy(endpoint)
        if not payload:
            consecutive_cdp_failures += 1
            if consecutive_cdp_failures == 1 or consecutive_cdp_failures % 3 == 0:
                print(f"STABILITY WARNING: Edge CDP unavailable ({consecutive_cdp_failures} consecutive check(s)); existing page operations are preserved", file=sys.stderr)
        else:
            if consecutive_cdp_failures:
                print(f"STABILITY: Edge CDP endpoint responded after {consecutive_cdp_failures} failed check(s); operational rebind will independently require stable checks")
            consecutive_cdp_failures = 0
        pressure = (
            snapshot['memory_percent'] >= RESOURCE_CRITICAL_MEMORY_PERCENT
            or (snapshot['free_disk_gb'] and snapshot['free_disk_gb'] < RESOURCE_LOW_DISK_GB)
        )
        if now - last_user_temp_cleanup >= USER_TEMP_CLEANUP_INTERVAL_SECONDS:
            removed_temp, skipped_temp, released_temp = await asyncio.to_thread(
                clean_user_temp_path, protect_active_stages=True
            )
            if removed_temp or skipped_temp:
                print(f"TEMP MAINTENANCE: permanently removed {removed_temp} item(s), skipped {skipped_temp} locked/active item(s); released approximately {released_temp / (1024 ** 2):.1f} MB")
            last_user_temp_cleanup = now
        if pressure and now - last_cleanup >= RESOURCE_CLEANUP_COOLDOWN_SECONDS:
            removed, released = await asyncio.to_thread(clean_stale_script_temp_files, 0.25)
            gc.collect()
            print(f"STABILITY CLEANUP: resource pressure detected; removed {removed} stale script temp item(s), approximately {released / (1024 ** 2):.1f} MB; live Edge cache and processes untouched")
            last_cleanup = now
        if now - last_log >= RESOURCE_LOG_INTERVAL_SECONDS:
            print(f"STABILITY MONITOR: RAM {snapshot['memory_percent']:.1f}% used, {snapshot['available_memory_gb']:.2f} GB available; disk {snapshot['free_disk_gb']:.2f} GB free; CDP {'healthy' if payload else 'unavailable'}")
            last_log = now
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=RESOURCE_MONITOR_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass


def _run_hidden_command(command: Sequence[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    """Run a Windows inspection command without opening a console window."""
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )


def _pid_from_netstat_output(output: str, port: int) -> Optional[int]:
    """Extract the PID of a TCP listener from locale-independent netstat output."""
    target_port = str(port)
    for raw_line in output.splitlines():
        columns = raw_line.split()
        if len(columns) < 4 or columns[0].upper() != "TCP":
            continue
        local_address = columns[1]
        state = columns[-2].upper()
        pid_text = columns[-1]
        if state != "LISTENING" or not pid_text.isdigit():
            continue
        # Handles 127.0.0.1:9223, 0.0.0.0:9223 and [::1]:9223.
        if local_address.rsplit(":", 1)[-1] == target_port:
            return int(pid_text)
    return None


def windows_port_owner_pid(port: int, attempts: int = 3) -> Optional[int]:
    """Return the Windows PID listening on a local TCP port.

    Get-NetTCPConnection can return no data on locked-down company devices even
    while the CDP endpoint is responding. Retry briefly, then use netstat -ano,
    which does not require administrator rights and is available on Windows.
    """
    if os.name != "nt":
        return None

    powershell_command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        (
            "$c = Get-NetTCPConnection -State Listen -LocalPort "
            f"{int(port)} -ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if ($null -ne $c) { [Console]::Out.Write($c.OwningProcess) }"
        ),
    ]
    netstat_command = ["netstat.exe", "-ano", "-p", "tcp"]

    for attempt in range(max(1, attempts)):
        try:
            result = _run_hidden_command(powershell_command)
            value = result.stdout.strip()
            if value.isdigit() and int(value) > 0:
                return int(value)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass

        try:
            result = _run_hidden_command(netstat_command)
            pid = _pid_from_netstat_output(result.stdout, port)
            if pid is not None and pid > 0:
                return pid
        except (OSError, subprocess.SubprocessError, ValueError):
            pass

        if attempt + 1 < max(1, attempts):
            time.sleep(0.05)
    return None


def windows_process_command_line(pid: int) -> str:
    """Read a Windows process command line using several non-admin fallbacks."""
    if os.name != "nt" or pid <= 0:
        return ""

    escaped_pid = int(pid)
    powershell_queries = [
        (
            f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId={escaped_pid}\" "
            "-ErrorAction SilentlyContinue; "
            "if ($null -ne $p) { [Console]::Out.Write($p.CommandLine) }"
        ),
        (
            f"$p = Get-WmiObject Win32_Process -Filter \"ProcessId={escaped_pid}\" "
            "-ErrorAction SilentlyContinue; "
            "if ($null -ne $p) { [Console]::Out.Write($p.CommandLine) }"
        ),
    ]
    for query in powershell_queries:
        try:
            result = _run_hidden_command([
                "powershell.exe", "-NoProfile", "-NonInteractive", "-Command", query
            ])
            command_line = result.stdout.strip()
            if command_line:
                return command_line
        except (OSError, subprocess.SubprocessError):
            pass

    # WMIC is absent on some newer Windows builds, but remains a useful fallback
    # on managed devices where CIM cmdlets are restricted.
    try:
        result = _run_hidden_command([
            "wmic.exe", "process", "where", f"ProcessId={escaped_pid}",
            "get", "CommandLine", "/value",
        ])
        for line in result.stdout.splitlines():
            if line.startswith("CommandLine="):
                return line.partition("=")[2].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def validate_port_profile_ownership(port: int, profile_directory: Path) -> None:
    """Validate the exact CDP port, tolerating hidden Windows process metadata."""
    if os.name != "nt":
        return
    endpoint = cdp_endpoint(port)
    payload = get_cdp_version(endpoint)
    if payload is None:
        raise RuntimeError(f"Port {port} is not exposing a usable Edge debugging endpoint.")
    pid = windows_port_owner_pid(port, attempts=1)
    if pid is None:
        print(f"Port {port}: CDP verified; Windows hid the listener PID, continuing.")
        return
    command_line = windows_process_command_line(pid)
    if not command_line:
        print(f"Port {port}: CDP verified; Windows hid the command line, continuing.")
        return
    expected_profile = os.path.normcase(os.path.normpath(str(profile_directory.expanduser().resolve())))
    normalized = os.path.normcase(os.path.normpath(command_line.replace('"', '')))
    if not any(flag in command_line for flag in (f"--remote-debugging-port={port}", f"--remote-debugging-port {port}")):
        raise RuntimeError(f"The process on port {port} does not advertise that debugging port.")
    match = re.search(r'--user-data-dir(?:=|\s+)(?:"([^"]+)"|([^\s]+))', command_line, re.I)
    if match:
        actual = os.path.normcase(os.path.normpath(match.group(1) or match.group(2)))
        if actual != expected_profile and expected_profile not in normalized:
            raise RuntimeError(f"Port {port} belongs to a different Edge profile. Use another --port value.")

def windows_descendant_pids(root_pid: int) -> set[int]:
    """Return a process tree using only built-in Windows Toolhelp APIs."""
    if os.name != "nt" or root_pid <= 0:
        return set()
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return {root_pid}
    parents: dict[int, int] = {}
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    try:
        if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)

    result = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent in parents.items():
            if parent in result and pid not in result:
                result.add(pid)
                changed = True
    return result


class EdgeFocusProtector:
    """Keep only the dedicated port Edge windows visible but non-activating.

    This never minimizes, moves, resizes, raises, activates, or restores a
    window. It only applies WS_EX_NOACTIVATE to top-level windows owned by the
    verified Edge process tree listening on this automation's exact CDP port.
    """

    def __init__(self, port: int):
        self.port = port
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if os.name != "nt":
            return
        self.thread = threading.Thread(
            target=self._run,
            name=f"EdgeFocusProtector-{self.port}",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000

        if ctypes.sizeof(ctypes.c_void_p) == 8:
            get_window_long = user32.GetWindowLongPtrW
            set_window_long = user32.SetWindowLongPtrW
        else:
            get_window_long = user32.GetWindowLongW
            set_window_long = user32.SetWindowLongW

        WNDENUMPROC = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        while not self.stop_event.is_set():
            root_pid = windows_port_owner_pid(self.port)
            protected_pids = windows_descendant_pids(root_pid or -1)

            @WNDENUMPROC
            def protect_window(hwnd, _lparam):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if int(pid.value) not in protected_pids:
                    return True
                if not user32.IsWindowVisible(hwnd):
                    return True
                style = int(get_window_long(hwnd, GWL_EXSTYLE))
                if not style & WS_EX_NOACTIVATE:
                    set_window_long(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)
                return True

            user32.EnumWindows(protect_window, 0)
            self.stop_event.wait(0.10)


def restore_edge_windows_visible(port: int) -> None:
    """Show and activate the dedicated Edge windows after hidden operation."""
    if os.name != "nt" or port <= 0:
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32=ctypes.windll.user32
        root_pid=windows_port_owner_pid(port)
        protected=windows_descendant_pids(root_pid or -1)
        SW_RESTORE=9
        SW_SHOW=5
        GWL_EXSTYLE=-20
        WS_EX_NOACTIVATE=0x08000000
        if ctypes.sizeof(ctypes.c_void_p)==8:
            get_style=user32.GetWindowLongPtrW; set_style=user32.SetWindowLongPtrW
        else:
            get_style=user32.GetWindowLongW; set_style=user32.SetWindowLongW
        callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        handles=[]
        @callback_type
        def collect(hwnd,_):
            pid=wintypes.DWORD(); user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if int(pid.value) in protected:
                style=int(get_style(hwnd,GWL_EXSTYLE))
                if style & WS_EX_NOACTIVATE:
                    set_style(hwnd,GWL_EXSTYLE,style & ~WS_EX_NOACTIVATE)
                user32.ShowWindow(hwnd,SW_SHOW)
                user32.ShowWindow(hwnd,SW_RESTORE)
                handles.append(hwnd)
            return True
        user32.EnumWindows(collect,0)
        if handles:
            user32.SetForegroundWindow(handles[-1])
            print(f"TAB VISIBILITY: restored {len(handles)} Edge window(s) for review")
    except Exception as exc:
        print(f"TAB VISIBILITY WARNING: could not restore Edge windows: {exc}",file=sys.stderr)


def process_is_running(pid: int) -> bool:
    """Return True only when a process with this PID still exists."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def port_lock_path(profile_directory: Path, port: int) -> Path:
    """Keep one controller per dedicated Edge profile and CDP port."""
    return profile_directory.expanduser().resolve() / f"automation_port_{port}.lock"


@contextmanager
def exclusive_port_controller(profile_directory: Path, port: int):
    """Prevent two copies of this automation from driving port 9223 together."""
    lock_path = port_lock_path(profile_directory, port)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            descriptor = os.open(
                str(lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            try:
                existing_pid = int(lock_path.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                existing_pid = -1

            if process_is_running(existing_pid):
                raise RuntimeError(
                    f"Another copy of this automation is already controlling "
                    f"dedicated port {port} (PID {existing_pid})."
                )
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            continue

        try:
            with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                handle.write(str(os.getpid()))
                handle.flush()
                os.fsync(handle.fileno())
            yield
        finally:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
        return


def validate_dedicated_endpoint(endpoint: str, port: int) -> dict[str, object]:
    """Verify that CDP resolves only to the requested local port."""
    expected = f"http://127.0.0.1:{port}"
    if endpoint != expected:
        raise RuntimeError(
            f"Refusing to connect outside the dedicated endpoint {expected}."
        )
    payload = get_cdp_version(endpoint)
    if payload is None:
        raise RuntimeError(
            f"The dedicated Edge debugging endpoint on port {port} is unavailable."
        )
    websocket_url = str(payload.get("webSocketDebuggerUrl", ""))
    allowed_prefixes = (
        f"ws://127.0.0.1:{port}/",
        f"ws://localhost:{port}/",
    )
    if not websocket_url.startswith(allowed_prefixes):
        raise RuntimeError(
            "The debugging endpoint returned a WebSocket address outside the "
            f"dedicated local port {port}; refusing to connect."
        )
    return payload


def load_playwright() -> None:
    """Load Playwright after command-line parsing so --help always works."""
    global PlaywrightError, PlaywrightTimeoutError, async_playwright

    try:
        from playwright.async_api import (
            Error as ImportedPlaywrightError,
            TimeoutError as ImportedPlaywrightTimeoutError,
            async_playwright as imported_async_playwright,
        )
    except ImportError as exc:
        raise MissingDependencyError(
            "Playwright is required.\n"
            "Install it, then run this script again:\n"
            "  py -m pip install --upgrade playwright\n"
            "(Use python3 instead of py on macOS or Linux.)"
        ) from exc

    PlaywrightError = ImportedPlaywrightError
    PlaywrightTimeoutError = ImportedPlaywrightTimeoutError
    async_playwright = imported_async_playwright


def positive_int(value: str) -> int:
    """Parse a command-line value that must be a positive integer."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def default_profile_directory() -> Path:
    """Return a persistent, dedicated Edge profile directory."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return base / "CopilotTabAutomation" / "EdgeProfile"
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "CopilotTabAutomation"
            / "EdgeProfile"
        )
    return Path.home() / ".config" / "copilot-tab-automation" / "edge-profile"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Open one Microsoft 365 Copilot chat in Edge, select a model, "
            "send prompts in separate retained tabs, with up to three previously unlogged CSV change cases per prompt."
        )
    )
    parser.add_argument(
        "--tabs",
        type=positive_int,
        default=DEFAULT_TAB_COUNT,
        help=f"number of new Copilot tabs to open (default: {DEFAULT_TAB_COUNT})",
    )
    parser.add_argument("--default-model", default=None,
        choices=("GPT 5.6 Sol Quick response", "GPT 5.6 Sol Think deeper", "GPT-6 Sol", "Sonnet 5.5", "Opus 5.5", "Sonnet 5"),
        help="One selected model for every case size and every retry; no automatic model fallback.")
    parser.add_argument("--small-model", default=DEFAULT_SMALL_CASE_MODEL_NAME,
        help=f"model for Small cases (default: {DEFAULT_SMALL_CASE_MODEL_NAME!r})")
    parser.add_argument("--medium-model", default=DEFAULT_MEDIUM_CASE_MODEL_NAME,
        help=f"model for Medium cases (default: {DEFAULT_MEDIUM_CASE_MODEL_NAME!r})")
    parser.add_argument("--large-model", default=DEFAULT_LARGE_CASE_MODEL_NAME,
        help=f"model for Large cases (default: {DEFAULT_LARGE_CASE_MODEL_NAME!r})")
    confirmation = parser.add_mutually_exclusive_group()
    confirmation.add_argument("--confirm-send", dest="confirm_send", action="store_true")
    confirmation.add_argument("--no-confirm-send", dest="confirm_send", action="store_false")
    parser.set_defaults(confirm_send=DEFAULT_REQUIRE_SEND_CONFIRMATION)
    cleanup = parser.add_mutually_exclusive_group()
    cleanup.add_argument("--safe-edge-cleanup", dest="safe_edge_cleanup", action="store_true")
    cleanup.add_argument("--no-safe-edge-cleanup", dest="safe_edge_cleanup", action="store_false")
    parser.set_defaults(safe_edge_cleanup=DEFAULT_SAFE_EDGE_CLEANUP)
    parser.add_argument(
        "--message",
        default=None,
        help="override the automatically built CSV-row prompt",
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help=f"source CSV queue (default: {DEFAULT_CSV_PATH})",
    )
    parser.add_argument(
        "--completed-path",
        type=Path,
        default=DEFAULT_COMPLETED_PATH,
        help=f"completed change ID allow-list (default: {DEFAULT_COMPLETED_PATH})",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help=f"fully-sent change ID log (default: {DEFAULT_LOG_PATH})",
    )
    parser.add_argument(
        "--instructions-path",
        type=Path,
        default=DEFAULT_INSTRUCTIONS_PATH,
        help=f"mandatory Markdown instructions attachment (default: {DEFAULT_INSTRUCTIONS_PATH})",
    )
    parser.add_argument(
        "--case-files-root",
        type=Path,
        default=DEFAULT_CASE_FILES_ROOT,
        help=(
            "local parent folder containing the exact "
            "Change_{change_id}_Interested_Party_{InterestedPartyId} folders "
            f"(default: {DEFAULT_CASE_FILES_ROOT})"
        ),
    )
    parser.add_argument(
        "--merged-pdfs-root",
        type=Path,
        default=DEFAULT_MERGED_PDFS_ROOT,
        help=f"folder containing one merged PDF per case (default: {DEFAULT_MERGED_PDFS_ROOT})",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_COPILOT_URL,
        help=f"Copilot URL (default: {DEFAULT_COPILOT_URL})",
    )
    parser.add_argument(
        "--port",
        type=positive_int,
        default=DEFAULT_CDP_PORT,
        help=f"local Edge debugging port (default: {DEFAULT_CDP_PORT})",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=default_profile_directory(),
        help="dedicated Edge profile directory used to retain Microsoft 365 sign-in",
    )
    parser.add_argument(
        "--edge-path",
        type=Path,
        help="path to the Microsoft Edge executable, if it is not found automatically",
    )
    parser.add_argument(
        "--attach-only",
        action="store_true",
        help="only attach to an Edge debugging session that is already running",
    )
    parser.add_argument(
        "--analysis-workers",
        type=positive_int,
        default=DEFAULT_ANALYSIS_WORKERS,
        help=f"workers for initial case analysis (default: {DEFAULT_ANALYSIS_WORKERS})",
    )
    parser.add_argument(
        "--parallel-loads",
        type=positive_int,
        default=DEFAULT_PARALLEL_LOADS,
        help=(
            "maximum number of Copilot pages loaded together "
            f"(default: {DEFAULT_PARALLEL_LOADS})"
        ),
    )
    parser.add_argument(
        "--page-timeout",
        type=positive_int,
        default=DEFAULT_PAGE_TIMEOUT_SECONDS,
        help=(
            "seconds allowed for each Copilot page to become ready "
            f"(default: {DEFAULT_PAGE_TIMEOUT_SECONDS})"
        ),
    )
    parser.add_argument(
        "--login-timeout",
        type=positive_int,
        default=DEFAULT_LOGIN_TIMEOUT_SECONDS,
        help=(
            "seconds allowed for first-run Microsoft 365 sign-in "
            f"(default: {DEFAULT_LOGIN_TIMEOUT_SECONDS})"
        ),
    )
    parser.add_argument(
        "--cases",
        type=positive_int,
        default=DEFAULT_CASE_COUNT,
        help=f"maximum cases to process (default: {DEFAULT_CASE_COUNT})",
    )
    parser.add_argument(
        "--max-tabs",
        type=positive_int,
        default=MAXIMUM_TAB_COUNT,
        help=f"maximum tabs available to this run (hard maximum: {MAXIMUM_TAB_COUNT})",
    )
    parser.add_argument(
        "--case-size-output-root",
        type=Path,
        default=DEFAULT_CASE_SIZE_OUTPUT_ROOT,
        help=f"case-size CSV output folder (default: {DEFAULT_CASE_SIZE_OUTPUT_ROOT})",
    )
    visibility = parser.add_mutually_exclusive_group()
    visibility.add_argument("--tabs-visible", dest="tabs_visible", action="store_true")
    visibility.add_argument("--tabs-hidden", dest="tabs_visible", action="store_false")
    parser.set_defaults(tabs_visible=DEFAULT_TABS_VISIBLE)
    parser.add_argument(
        "--wake-max-rounds",
        type=int,
        default=DEFAULT_WAKE_MAX_ROUNDS,
        help="wake rounds after sending; 0 keeps waking until generic Chat Copilot titles change",
    )
    return parser.parse_args(argv)


def canonical_change_id(value: str) -> str:
    """Normalize numeric IDs so values such as 00004 and 4 match."""
    text = (value or "").strip()
    if re.fullmatch(r"[+-]?\d+", text):
        return str(int(text))
    return text.casefold()


def read_change_ids(path: Path, label: str) -> set[str]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} CSV was not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "change_id" not in reader.fieldnames:
            raise RuntimeError(f"{label} CSV has no change_id column: {path}")
        return {
            canonical_change_id(row.get("change_id") or "")
            for row in reader
            if (row.get("change_id") or "").strip()
        }


def read_logged_change_ids(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    return read_change_ids(log_path, "Sent log")


def next_unlogged_rows(
    csv_path: Path,
    completed_path: Path,
    log_path: Path,
    limit: int = 10,
) -> list[dict[str, str]]:
    """Use file 06 only as allow-list, then retrieve complete rows from file 07."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"Source CSV was not found: {csv_path}")
    eligible_ids = read_change_ids(completed_path, "Completed change IDs") - read_logged_change_ids(log_path)
    selected: list[dict[str, str]] = []
    selected_ids: set[str] = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        missing = [column for column in REQUIRED_COLUMNS if column not in fields]
        if missing:
            raise RuntimeError("Source CSV is missing required columns: " + ", ".join(missing))
        for raw_row in reader:
            row = {column: (raw_row.get(column) or "") for column in fields}
            change_id = canonical_change_id(row.get("change_id", ""))
            if not change_id or change_id not in eligible_ids or change_id in selected_ids:
                continue
            selected.append(row)
            selected_ids.add(change_id)
            if len(selected) >= limit:
                break
    return selected

def display_value(value: str) -> str:
    """Keep multiline values readable and make genuinely empty fields explicit."""
    text = (value or "").strip()
    return text if text else "[blank]"


def exact_case_folder_name(row: dict[str, str]) -> str:
    """Construct the required local case-folder name without normalizing IDs."""
    change_id = (row.get("change_id") or "").strip()
    interested_party_id = (row.get("InterestedPartyId") or "").strip()
    if not change_id or not interested_party_id:
        raise RuntimeError(
            "Cannot construct a case folder because change_id or "
            "InterestedPartyId is blank."
        )
    return f"Change_{change_id}_Interested_Party_{interested_party_id}"


def local_case_files(
    row: dict[str, str],
    case_files_root: Path,
) -> list[Path]:
    """Return direct files from the exact case folder, sorted by filename."""
    case_key=exact_case_folder_name(row)
    cache_key=(str(case_files_root.expanduser().resolve()),case_key.casefold())
    cached=_CASE_FILES_CACHE.get(cache_key)
    if cached is not None and all(path.is_file() for path in cached):
        return list(cached)
    case_folder = case_files_root.expanduser() / case_key
    if not case_folder.is_dir():
        raise FileNotFoundError(
            f"Required local case folder was not found: {case_folder}"
        )
    files = sorted(
        (item.resolve() for item in case_folder.iterdir() if item.is_file()),
        key=lambda item: (item.name.casefold(), item.name),
    )
    if not files:
        raise RuntimeError(
            f"Required local case folder contains no direct files: {case_folder}"
        )
    _CASE_FILES_CACHE[cache_key]=tuple(files)
    return list(files)

def numeric_change_id(row: dict[str, str]) -> int:
    """Return the integer change ID used to select its 100-case status batch."""
    raw=(row.get("change_id") or "").strip()
    match=re.search(r"\d+",raw)
    if match is None:
        raise RuntimeError(f"Cannot derive a numeric change_id from {raw!r}.")
    value=int(match.group(0))
    if value < 1:
        raise RuntimeError(f"change_id must be positive, received {raw!r}.")
    return value

def resolve_merge_status_json(low: int, high: int, merged_pdfs_root: Path) -> Path:
    """Prefer an exact status file, otherwise the narrowest covering range.

    Only filenames with valid numeric bounds are considered. The JSON's declared
    range is checked before it is used, so a stale or misnamed file cannot silently
    supply another batch's merge results.
    """
    root = merged_pdfs_root.expanduser().resolve()
    exact = root / f"merge_status_{low}_{high}.json"
    if exact.is_file():
        candidates = [exact]
    else:
        candidates = []
        for path in root.glob("merge_status_*_*.json"):
            match = re.fullmatch(r"merge_status_(\d+)_(\d+)\.json", path.name)
            if match and int(match.group(1)) <= low <= high <= int(match.group(2)):
                candidates.append(path)
        candidates.sort(key=lambda path: (
            int(path.stem.rsplit("_", 2)[2]) - int(path.stem.rsplit("_", 2)[1]),
            path.name,
        ))
    if not candidates:
        raise FileNotFoundError(
            f"No merge-status JSON covers Change IDs {low}-{high} in {root}. "
            f"Expected {exact.name} or a covering multi-batch file."
        )
    path = candidates[0]
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read merge-status JSON {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise RuntimeError(f"Merge-status JSON has no valid results list: {path}")
    if (type(payload.get("range_from")) is not int or
            type(payload.get("range_to")) is not int or
            payload["range_from"] > low or payload["range_to"] < high):
        raise RuntimeError(f"Merge-status JSON declares a range that does not cover {low}-{high}: {path}")
    return path


def merge_status_json_path(row: dict[str, str], merged_pdfs_root: Path) -> Path:
    """Resolve the status file covering this case's 100-ID batch."""
    change_number = numeric_change_id(row)
    range_from = ((change_number - 1) // 100) * 100 + 1
    return resolve_merge_status_json(range_from, range_from + 99, merged_pdfs_root)

PASSWORD_REQUIRED_STATUS_TOKENS = {
    "password_required", "password_protected", "password-protected",
    "encrypted_password_required", "encrypted_requires_password",
}

def _failed_item_is_password_required(item: dict[str, Any]) -> bool:
    """Recognize password-protected merge failures across status/error schemas."""
    values = [
        item.get("status"), item.get("reason"), item.get("error"),
        item.get("message"), item.get("failure_reason"), item.get("detail"),
    ]
    text = " ".join(str(value or "") for value in values).strip().casefold()
    normalized = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return (
        any(token in normalized for token in PASSWORD_REQUIRED_STATUS_TOKENS)
        or ("password" in normalized and any(word in normalized for word in ("required", "protected", "encrypted", "locked")))
    )

def _failed_item_path_values(item: dict[str, Any]) -> list[str]:
    """Return every path/name identifier carried by one failed-file record."""
    values: list[str] = []
    for field in ("file_path", "relative_path", "file_name", "path", "name", "source_path"):
        value = str(item.get(field, "") or "").strip()
        if value and value not in values:
            values.append(value)
    return values

def case_unusable_file_paths(
    row: dict[str, str],
    case_files_root: Path,
    merged_pdfs_root: Path,
) -> list[Path]:
    """Resolve password-protected source files that must never reach Copilot.

    These files are excluded from direct attachments, manifests, size-based fills,
    case-size counts, and complete-small add-ons. The merge-status JSON is the
    authority; a password-required item is matched by full path and filename.
    """
    cache_key = (
        str(case_files_root.expanduser().resolve()),
        str(merged_pdfs_root.expanduser().resolve()),
        exact_case_folder_name(row).casefold(),
    )
    cached = _UNUSABLE_FILES_CACHE.get(cache_key)
    if cached is not None and all(path.is_file() for path in cached):
        return list(cached)
    status_path = merge_status_json_path(row, merged_pdfs_root)
    if not status_path.is_file():
        _UNUSABLE_FILES_CACHE[cache_key] = tuple()
        return []
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read merge-status JSON {status_path}: {exc}") from exc
    results = payload.get("results", [])
    expected = exact_case_folder_name(row).casefold()
    matches = [item for item in results if isinstance(item, dict) and str(item.get("case", "")).strip().casefold() == expected] if isinstance(results, list) else []
    if len(matches) != 1:
        _UNUSABLE_FILES_CACHE[cache_key] = tuple()
        return []
    failed_items = matches[0].get("failed_files", [])
    if not isinstance(failed_items, list):
        failed_items = []
    identifiers: set[str] = set()
    names: set[str] = set()
    for item in failed_items:
        if not isinstance(item, dict) or not _failed_item_is_password_required(item):
            continue
        for value in _failed_item_path_values(item):
            identifiers.add(os.path.normcase(os.path.normpath(value)))
            names.add(Path(value).name.casefold())
    if not identifiers and not names:
        _UNUSABLE_FILES_CACHE[cache_key] = tuple()
        return []
    resolved: list[Path] = []
    for path in local_case_files(row, case_files_root):
        path_keys = {
            norm_path(path),
            os.path.normcase(os.path.normpath(str(path))),
            path.name.casefold(),
        }
        if path_keys & identifiers or path.name.casefold() in names:
            resolved.append(path)
    unresolved_names = sorted(name for name in names if not any(path.name.casefold() == name for path in resolved))
    if unresolved_names:
        print(f"  PASSWORD_REQUIRED warning: {len(unresolved_names)} unusable filename(s) recorded but not found locally for {exact_case_folder_name(row)}: " + " | ".join(unresolved_names))
    _UNUSABLE_FILES_CACHE[cache_key] = tuple(resolved)
    return list(resolved)

def usable_local_case_files(
    row: dict[str, str],
    case_files_root: Path,
    merged_pdfs_root: Path,
) -> list[Path]:
    """Return local evidence after permanently removing password-required files."""
    files = local_case_files(row, case_files_root)
    blocked = {norm_path(path) for path in case_unusable_file_paths(row, case_files_root, merged_pdfs_root)}
    return [path for path in files if norm_path(path) not in blocked]

def case_failed_file_paths(
    row: dict[str, str],
    case_files_root: Path,
    merged_pdfs_root: Path,
) -> list[Path]:
    """Return existing failed merge inputs for the exact change/IP case.

    Matching requires the exact normalized case key, so a change ID can never
    borrow failed files from another interested party. Missing status JSON or an
    empty failed_file_paths list safely falls back to the normal size ordering.
    """
    cache_key=(str(case_files_root.expanduser().resolve()),str(merged_pdfs_root.expanduser().resolve()),exact_case_folder_name(row).casefold())
    cached=_FAILED_FILES_CACHE.get(cache_key)
    if cached is not None and all(path.is_file() for path in cached):
        return list(cached)
    status_path=merge_status_json_path(row,merged_pdfs_root)
    if not status_path.is_file():
        print(f"  Merge-status JSON not found; using size ordering: {status_path}")
        return []
    try:
        payload=json.loads(status_path.read_text(encoding='utf-8-sig'))
    except (OSError,UnicodeDecodeError,json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read merge-status JSON {status_path}: {exc}") from exc
    results=payload.get('results',[])
    if not isinstance(results,list):
        raise RuntimeError(f"Merge-status JSON has no valid results list: {status_path}")
    expected=exact_case_folder_name(row).casefold()
    matches=[item for item in results if isinstance(item,dict) and str(item.get('case','')).strip().casefold()==expected]
    if len(matches)>1:
        raise RuntimeError(f"Merge-status JSON contains multiple entries for {exact_case_folder_name(row)!r}: {status_path}")
    if not matches:
        print(f"  Exact case not found in merge-status JSON; using size ordering: {exact_case_folder_name(row)}")
        return []
    match=matches[0]
    raw_failed=match.get('failed_files',[])
    raw_paths=match.get('failed_file_paths',[])
    if not isinstance(raw_failed,list):
        raw_failed=[]
    if not isinstance(raw_paths,list):
        raise RuntimeError(f"failed_file_paths is not a list for {exact_case_folder_name(row)!r} in {status_path}")
    password_required_keys: set[str]=set()
    for item in raw_failed:
        if not isinstance(item,dict) or not _failed_item_is_password_required(item):
            continue
        for value in _failed_item_path_values(item):
            password_required_keys.add(os.path.normcase(os.path.normpath(value)))
            password_required_keys.add(Path(value).name.casefold())
    filtered_paths=[]
    skipped_password=0
    for value in raw_paths:
        text=str(value or '').strip()
        keys={os.path.normcase(os.path.normpath(text)),Path(text).name.casefold()} if text else set()
        if keys & password_required_keys:
            skipped_password+=1
            continue
        filtered_paths.append(value)
    # Some status files expose structured failed_files without mirroring every
    # usable path in failed_file_paths. Include those entries, except passwords.
    known={os.path.normcase(os.path.normpath(str(value or '').strip())) for value in filtered_paths}
    for item in raw_failed:
        if not isinstance(item,dict) or _failed_item_is_password_required(item):
            continue
        values=_failed_item_path_values(item)
        value=values[0] if values else ''
        key=os.path.normcase(os.path.normpath(value))
        if value and key not in known:
            filtered_paths.append(value); known.add(key)
    raw_paths=filtered_paths
    if skipped_password:
        print(f"  PASSWORD_REQUIRED exclusion: skipped {skipped_password} unusable failed file(s) for {exact_case_folder_name(row)}")
    if not raw_paths:
        _FAILED_FILES_CACHE[cache_key]=tuple()
        return []
    case_folder=case_files_root.expanduser().resolve()/exact_case_folder_name(row)
    local_files=usable_local_case_files(row,case_files_root,merged_pdfs_root)
    by_name: dict[str,list[Path]]={}
    for item in local_files:
        by_name.setdefault(item.name.casefold(),[]).append(item)
    resolved: list[Path]=[]
    seen: set[str]=set()
    missing: list[str]=[]
    for value in raw_paths:
        text=str(value or '').strip()
        if not text:
            continue
        candidate=Path(text).expanduser()
        if candidate.is_file():
            chosen=candidate.resolve()
        else:
            same_name=by_name.get(candidate.name.casefold(),[])
            if len(same_name)==1:
                chosen=same_name[0]
            else:
                direct=case_folder/candidate.name
                if direct.is_file():
                    chosen=direct.resolve()
                else:
                    missing.append(text)
                    continue
        key=os.path.normcase(os.path.normpath(str(chosen)))
        if key not in seen:
            resolved.append(chosen); seen.add(key)
    if missing:
        print(f"  WARNING: {len(missing)} failed merge file path(s) could not be resolved for {exact_case_folder_name(row)}: "+" | ".join(missing))
    _FAILED_FILES_CACHE[cache_key]=tuple(resolved)
    return list(resolved)

def single_case_extra_attachment_paths(
    row: dict[str, str],
    case_files_root: Path,
    merged_pdfs_root: Path,
) -> tuple[list[Path], int]:
    """Prioritize merge failures, then fill remaining fallback slots by size."""
    files=usable_local_case_files(row,case_files_root,merged_pdfs_root)
    total=len(files)
    failed=case_failed_file_paths(row,case_files_root,merged_pdfs_root)
    failed_keys={os.path.normcase(os.path.normpath(str(path))) for path in failed}
    remaining=[path for path in files if os.path.normcase(os.path.normpath(str(path))) not in failed_keys]
    failed_sorted=sorted(failed,key=lambda item:(-item.stat().st_size,item.name.casefold(),item.name))
    remaining_sorted=sorted(remaining,key=lambda item:(-item.stat().st_size,item.name.casefold(),item.name))
    selected=(failed_sorted+remaining_sorted)[:SINGLE_CASE_EXTRA_ATTACHMENT_LIMIT]
    if failed:
        included=sum(1 for path in selected if os.path.normcase(os.path.normpath(str(path))) in failed_keys)
        print(f"  Fallback priority for {exact_case_folder_name(row)}: {included}/{len(failed)} failed merge file(s) selected first; {len(selected)-included} slot(s) filled by size")
    return selected,total

def local_case_file_names(
    row: dict[str, str],
    case_files_root: Path,
    merged_pdfs_root: Optional[Path] = None,
) -> list[str]:
    """Return usable direct filenames; password-required files are never manifested."""
    files = (usable_local_case_files(row, case_files_root, merged_pdfs_root)
             if merged_pdfs_root is not None else local_case_files(row, case_files_root))
    return [item.name for item in files]

def related_document_paths(row: dict[str, str], merged_pdfs_root: Path) -> list[Path]:
    """Resolve and validate every continuous PDF part in results[].related_documents."""
    root=merged_pdfs_root.expanduser().resolve(); case=exact_case_folder_name(row)
    key=(str(root),case.casefold()); cached=_MERGED_PDF_CACHE.get(key)
    if cached is not None and cached and all(x.is_file() for x in cached): return list(cached)
    status_path=merge_status_json_path(row,root)
    if not status_path.is_file(): raise FileNotFoundError(f"Merge-status JSON was not found: {status_path}")
    try: payload=json.loads(status_path.read_text(encoding="utf-8-sig"))
    except (OSError,UnicodeDecodeError,json.JSONDecodeError) as exc: raise RuntimeError(f"Could not read merge-status JSON {status_path}: {exc}") from exc
    results=payload.get("results",[])
    matches=[x for x in results if isinstance(x,dict) and str(x.get("case","")).strip().casefold()==case.casefold()] if isinstance(results,list) else []
    if len(matches)!=1: raise RuntimeError(f"Expected one results entry for {case!r} in {status_path}; found {len(matches)}.")
    docs=matches[0].get("related_documents",[])
    if not isinstance(docs,list) or not docs: raise RuntimeError(f"No related_documents for {case!r} in {status_path}.")
    parts=[]; seen=set()
    for doc in docs:
        if not isinstance(doc,dict): raise RuntimeError(f"Invalid related_documents entry for {case!r}.")
        raw=str(doc.get("file_path","") or "").strip(); name=str(doc.get("file_name","") or "").strip()
        candidate=Path(raw).expanduser() if raw else root/name
        if not candidate.is_file() and name: candidate=root/name
        if not candidate.is_file(): raise FileNotFoundError(f"Related merged PDF not found: {candidate}")
        candidate=candidate.resolve(); m=re.search(r"_part_(\d+)\.pdf$",candidate.name,re.I)
        if not m: raise RuntimeError(f"Invalid related PDF part name: {candidate.name}")
        k=os.path.normcase(os.path.normpath(str(candidate)))
        if k in seen: raise RuntimeError(f"Duplicate related PDF for {case!r}: {candidate}")
        seen.add(k); parts.append((int(m.group(1)),candidate))
    parts.sort(); actual=[n for n,_ in parts]; expected=list(range(1,len(parts)+1))
    if actual!=expected: raise RuntimeError(f"Non-continuous PDF parts for {case!r}: {actual}; expected {expected}.")
    value=tuple(path for _,path in parts); _MERGED_PDF_CACHE[key]=value; return list(value)

def merged_pdf_path(row: dict[str, str], merged_pdfs_root: Path) -> Path:
    return related_document_paths(row,merged_pdfs_root)[0]

def format_case_block(row: dict[str, str], case_number: int, total_cases: int, case_file_names: Sequence[str]) -> str:
    change_id = display_value(row.get("change_id", ""))
    ip_id = display_value(row.get("InterestedPartyId", ""))
    lines = [
        "=" * 78, f"CASE {case_number} OF {total_cases}",
        f"CASE KEY: change_id {change_id} | InterestedPartyId {ip_id}", "=" * 78, "",
        "IDENTITY AND CURRENT RECORD", f"- change_id: {change_id}", f"- InterestedPartyId: {ip_id}",
        f"- InterestedPartyCurrentName: {display_value(row.get('InterestedPartyCurrentName', ''))}",
        f"- Date_of_birth: {display_value(row.get('Date_of_birth', ''))}", f"- Status: {display_value(row.get('Status', ''))}", "",
        "CHANGE EVENT", f"- ActionDateTime: {display_value(row.get('ActionDateTime', ''))}",
        f"- ActionUserId: {display_value(row.get('ActionUserId', ''))}", f"- ActionUserName: {display_value(row.get('ActionUserName', ''))}",
        f"- ActionUserTeam: {display_value(row.get('ActionUserTeam', ''))}", "", "CHANGE DETAILS",
        f"- ChangedSections: {display_value(row.get('ChangedSections', ''))}", f"- ChangedFields: {display_value(row.get('ChangedFields', ''))}",
        f"- PreviousValues: {display_value(row.get('PreviousValues', ''))}", f"- NewValues: {display_value(row.get('NewValues', ''))}",
        f"- FieldChangeCount: {display_value(row.get('FieldChangeCount', ''))}", "", "ATTACHED MERGED PDF",
        f'- "{exact_case_folder_name(row)}.pdf"', "Use this attached PDF only for this case's documents and evidence.", "",
        "COMPLETE ORIGINAL FILENAME MANIFEST",
        "These are the original local filenames represented in the attached merged PDF. Use them only to identify source documents inside that PDF. Do not search SharePoint or treat a filename alone as evidence.",
        f"- Expected readable/usable original filename count: {len(case_file_names)}",
        "- Files recorded by the merge-status process as password-required are deliberately excluded from attachments and this manifest. They are unusable inputs and MUST NOT cause this case, its exposure result, or its analysis to fail.",
    ]
    lines.extend(f'- "{name}"' for name in case_file_names)
    standard = {"change_id","InterestedPartyId","InterestedPartyCurrentName","Date_of_birth","Status","ActionDateTime","ActionUserId","ActionUserName","ActionUserTeam","ChangedSections","ChangedFields","PreviousValues","NewValues","FieldChangeCount"}
    extra = [field for field in row if field not in standard]
    if extra:
        lines.extend(["", "ADDITIONAL SOURCE FIELDS"])
        lines.extend(f"- {field}: {display_value(row.get(field, ''))}" for field in extra)
    lines.extend(["", f"END OF CASE {case_number} | change_id {change_id} | InterestedPartyId {ip_id}", "=" * 78])
    return "\n".join(lines)

def build_message(rows: Sequence[dict[str, str]], case_files_root: Path, merged_pdfs_root: Path) -> str:
    if not rows or len(rows) > CASES_PER_TAB:
        raise ValueError(f"A prompt requires 1 to {CASES_PER_TAB} cases.")
    count = len(rows)
    manifest = "\n".join(f"- Case {i}: change_id {display_value(r.get('change_id',''))} | InterestedPartyId {display_value(r.get('InterestedPartyId',''))} | attached PDF {exact_case_folder_name(r)}.pdf" for i,r in enumerate(rows,1))
    names = [local_case_file_names(r, case_files_root, merged_pdfs_root) for r in rows]
    blocks = "\n\n".join(format_case_block(r,i,count,names[i-1]) for i,r in enumerate(rows,1))
    fallback_note = ""
    if CASES_PER_TAB == 1 and count == 1:
        selected, total_original = single_case_extra_attachment_paths(rows[0], case_files_root, merged_pdfs_root)
        failed_selected = case_failed_file_paths(rows[0], case_files_root, merged_pdfs_root)
        selected_keys = {os.path.normcase(os.path.normpath(str(path))) for path in selected}
        included_failed = [path for path in failed_selected if os.path.normcase(os.path.normpath(str(path))) in selected_keys]
        fallback_note = (
            "\n\nSINGLE-CASE INDIVIDUAL ATTACHMENT FALLBACK\n"
            f"- {len(selected)} individual case file(s) are attached within the overall 20-attachment limit.\n"
            f"- {len(included_failed)} file(s) recorded in the case's merge-status JSON as failed during merged-PDF creation are attached first as direct fallback sources.\n"
            "- Any remaining fallback slots are filled with the largest other individual case files by file size.\n"
            "- A directly attached failed-merge file that is successfully read counts as exposed and must be included in the case's full exposure and analysis count.\n"
            "- Use every successfully readable direct attachment only for this same case and never mix it with another case.\n"
        )
        if total_original > len(selected):
            fallback_note += (
                f"- The case contains {total_original} individual files, so the {len(selected)} directly attached fallbacks are a prioritized subset; rely on the merged PDF for the remaining successfully merged documents.\n"
            )
    return (BASE_MESSAGE + fallback_note + "\n\nBATCH CONTROL\n" + f"- Total cases supplied: {count}\n"
        + f"- Required result: {count} separate completed review output file(s), one per case.\n"
        + "- Finish each case before starting the next and never mix case evidence.\n"
        + "- Each case has one attached merged PDF matching its case key. Use only that PDF for that case.\n"
        + "- Do not search SharePoint, follow a folder link, or use an unattached source.\n"
        + "- Verify every Excel text reference exactly against the relevant source document in the active case's merged PDF.\n"
        + "- Cite the source document's own page number, not the merged PDF's global sequential page number. Never infer or invent a page number.\n\n"
        + "CASE MANIFEST\n" + manifest + "\n\nCASE DATA\n\n" + blocks)

def append_fully_sent_log(log_path: Path, row: dict[str, str]) -> None:
    """Append one ID only after strict UI proof, never duplicating an existing ID."""
    from datetime import datetime
    canonical=canonical_change_id(row.get("change_id", ""))
    if log_path.exists():
        try:
            if canonical in read_logged_change_ids(log_path):
                return
        except (OSError,RuntimeError,UnicodeDecodeError):
            pass
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exists = log_path.exists() and log_path.stat().st_size > 0
    with log_path.open("a", encoding="utf-8-sig", newline="") as handle:
        fields = ["change_id", "InterestedPartyId", "fully_sent_at_local"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow({
            "change_id": row["change_id"],
            "InterestedPartyId": row["InterestedPartyId"],
            "fully_sent_at_local": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        handle.flush()
        os.fsync(handle.fileno())


def cdp_endpoint(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def get_cdp_version(endpoint: str) -> Optional[dict[str, object]]:
    """Return the remote-debugging version payload when Edge is ready."""
    try:
        with urllib.request.urlopen(
            f"{endpoint}/json/version", timeout=0.35
        ) as response:
            if response.status != 200:
                return None
            payload = json.loads(response.read().decode("utf-8"))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ):
        return None

    if not isinstance(payload, dict) or not payload.get("webSocketDebuggerUrl"):
        return None
    return payload


def find_edge_executable(explicit_path: Optional[Path]) -> Path:
    """Find Microsoft Edge on Windows, macOS, or Linux."""
    if explicit_path is not None:
        resolved = explicit_path.expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(
                f"Microsoft Edge was not found at the supplied path: {resolved}"
            )
        return resolved

    candidates: list[Path] = []
    if os.name == "nt":
        for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            root = os.environ.get(variable)
            if root:
                candidates.append(
                    Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
                )
    elif sys.platform == "darwin":
        candidates.append(
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")
        )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    for command in (
        "msedge",
        "microsoft-edge",
        "microsoft-edge-stable",
        "microsoft-edge-beta",
        "microsoft-edge-dev",
    ):
        discovered = shutil.which(command)
        if discovered:
            return Path(discovered).resolve()

    raise FileNotFoundError(
        "Microsoft Edge could not be found. Install Edge or pass "
        "--edge-path with the full executable path."
    )


def launch_edge(
    edge_path: Path,
    endpoint: str,
    port: int,
    profile_directory: Path,
    startup_timeout_seconds: int = 30,
    tabs_visible: bool = DEFAULT_TABS_VISIBLE,
) -> subprocess.Popen[bytes]:
    """Launch a detached, visible, profile-isolated Edge process with CDP enabled."""
    profile_directory = profile_directory.expanduser().resolve()
    profile_directory.mkdir(parents=True, exist_ok=True)

    command = [
        str(edge_path),
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile_directory}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=msEdgeFirstRunExperience",
        "--disable-session-crashed-bubble",
        "--new-window",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
        "--disable-features=msEdgeFirstRunExperience,CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
        "--enable-precise-memory-info",
        "--no-pings",
        "about:blank",
    ]

    process_options: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        process_options["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        process_options["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **process_options)
    except OSError as exc:
        raise RuntimeError(f"Microsoft Edge could not be started: {exc}") from exc

    deadline = time.monotonic() + startup_timeout_seconds
    while time.monotonic() < deadline:
        if get_cdp_version(endpoint) is not None:
            return process
        time.sleep(0.05)

    raise RuntimeError(
        "Edge started, but its local debugging connection did not become ready. "
        f"Make sure port {port} is not being used by another program."
    )


def _is_cdp_disconnect_error(error: BaseException | str) -> bool:
    text = str(error or "").casefold()
    return any(token in text for token in (
        "target closed", "browser has been closed", "connection closed",
        "connection reset", "websocket", "cdp session", "frame was detached",
        "net::err_aborted", "object has been collected", "page.reload",
        "most likely the page has been closed", "protocol error",
    ))

_CDP_ENDPOINT_CACHE: dict[str, tuple[float, bool]] = {}
_CDP_ENDPOINT_INFLIGHT: dict[str, asyncio.Task] = {}
_CDP_ENDPOINT_CACHE_TTL_SECONDS = 2.0

def _consume_background_task(task: asyncio.Task) -> asyncio.Task:
    """Prevent abandoned Playwright futures from producing unretrieved exceptions."""
    def _done(done: asyncio.Task) -> None:
        try:
            done.exception()
        except (asyncio.CancelledError, Exception):
            pass
    task.add_done_callback(_done)
    return task

async def _async_cdp_endpoint_healthy(endpoint: str, *, force: bool = False) -> bool:
    """Cheap, deduplicated endpoint observation; blocking urllib never runs on the loop."""
    now = time.monotonic()
    cached = _CDP_ENDPOINT_CACHE.get(endpoint)
    if not force and cached and now - cached[0] <= _CDP_ENDPOINT_CACHE_TTL_SECONDS:
        return cached[1]
    task = _CDP_ENDPOINT_INFLIGHT.get(endpoint)
    if task is None or task.done():
        task = asyncio.create_task(asyncio.to_thread(get_cdp_version, endpoint))
        _CDP_ENDPOINT_INFLIGHT[endpoint] = task
    try:
        payload = await asyncio.wait_for(asyncio.shield(task), timeout=1.5)
        healthy = payload is not None
        _CDP_ENDPOINT_CACHE[endpoint] = (time.monotonic(), healthy)
        return healthy
    except (asyncio.TimeoutError, OSError):
        return False
    finally:
        if task.done():
            _CDP_ENDPOINT_INFLIGHT.pop(endpoint, None)
            try:
                task.exception()
            except (asyncio.CancelledError, Exception):
                pass

async def wait_for_stable_cdp(endpoint: str, label: str = "CDP recovery") -> None:
    """Bounded adaptive endpoint confirmation; never treats one failed sample as an outage."""
    stable = 0
    delay = 0.12
    attempts = max(20, CDP_OUTAGE_RECOVERY_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        if await _async_cdp_endpoint_healthy(endpoint, force=attempt > 1):
            stable += 1
            if stable >= 2:
                print(f"{label}: endpoint recovered after {attempt} bounded observations")
                return
        else:
            stable = 0
        if attempt in (1, 4, 8, 12, 20, 30, 45) or attempt == attempts:
            print(f"{label}: endpoint not yet confirmed ({attempt}/{attempts}); workload retained", file=sys.stderr)
        await asyncio.sleep(delay)
        delay = min(2.0, delay * 1.28)
    print(f"{label}: bounded observation window ended; escalating to indefinite reconnect without discarding workload", file=sys.stderr)
    return

async def page_target_id(page: Any) -> str:
    session = None
    try:
        session = await page.context.new_cdp_session(page)
        info = await session.send("Target.getTargetInfo")
        return str(info.get("targetInfo", {}).get("targetId", ""))
    except Exception:
        return ""
    finally:
        if session is not None:
            try:
                await session.detach()
            except Exception:
                pass

async def _fresh_cdp_version_payload(endpoint: str) -> Optional[dict[str, object]]:
    """Read a fresh CDP version payload without the shared health cache."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(get_cdp_version, endpoint),
            timeout=CDP_ENDPOINT_PROBE_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, OSError):
        return None


def _cdp_handshake_targets(
    endpoint: str,
    payload: Optional[dict[str, object]],
    prefer_http: bool,
) -> list[tuple[str, str]]:
    """Build independent CDP routes, alternating priority after each failed cycle."""
    routes: list[tuple[str, str]] = []
    websocket = str((payload or {}).get("webSocketDebuggerUrl", "")).strip()
    if websocket:
        routes.append(("websocket", websocket))
    routes.append(("http", endpoint))
    if prefer_http:
        routes.sort(key=lambda item: 0 if item[0] == "http" else 1)
    return routes


async def _connect_one_cdp_route(
    pw: Any,
    route: str,
    target: str,
    timeout_ms: int,
) -> tuple[Optional[Browser], Optional[BaseException], float]:
    """Perform one fully-owned Playwright CDP handshake with a realistic timeout."""
    started = time.monotonic()
    try:
        browser = await pw.chromium.connect_over_cdp(target, timeout=timeout_ms)
        if browser.is_connected():
            return browser, None, time.monotonic() - started
        try:
            await browser.close()
        except Exception:
            pass
        return None, RuntimeError(f"{route} returned a disconnected browser"), time.monotonic() - started
    except (PlaywrightError, PlaywrightTimeoutError, RuntimeError, asyncio.TimeoutError) as exc:
        return None, exc, time.monotonic() - started


async def connect_existing_edge_with_retry(pw: Any, endpoint: str) -> Browser:
    """Persistently attach to Edge using escalating, alternating CDP handshakes.

    A responsive /json/version endpoint does not prove that Playwright can finish
    the browser-wide target enumeration handshake. With many open tabs Edge can
    legitimately need substantially longer than the old 1.2 second cap. This
    connector therefore escalates from 3 to 30 seconds, alternates direct
    WebSocket and HTTP discovery, refreshes the advertised WebSocket before every
    cycle, and never discards queued work or starts overlapping transports.
    """
    started_all = time.monotonic()
    cycle = probes = handshakes = 0
    next_status = 0.0
    last_error: Optional[BaseException] = None
    while True:
        cycle += 1
        probes += 1
        payload = await _fresh_cdp_version_payload(endpoint)
        timeout_ms = CDP_HANDSHAKE_TIMEOUT_LADDER_MS[
            min(cycle - 1, len(CDP_HANDSHAKE_TIMEOUT_LADDER_MS) - 1)
        ]
        targets = _cdp_handshake_targets(endpoint, payload, prefer_http=(cycle % 2 == 0))
        if payload is None:
            last_error = RuntimeError("CDP version endpoint temporarily unavailable")
        else:
            print(
                f"CDP CONNECT cycle={cycle}: endpoint responsive; "
                f"routes={','.join(route for route, _ in targets)}; "
                f"handshake timeout={timeout_ms/1000:.0f}s"
            )
        for route, target in targets:
            handshakes += 1
            browser, error, elapsed = await _connect_one_cdp_route(
                pw, route, target, timeout_ms
            )
            if browser is not None:
                reward_technique("cdp", route, True, elapsed)
                _CDP_ENDPOINT_CACHE[endpoint] = (time.monotonic(), True)
                print(
                    f"CDP connection established cycle={cycle} probe={probes} "
                    f"handshake={handshakes} route={route} elapsed={elapsed:.2f}s "
                    f"total={time.monotonic()-started_all:.2f}s"
                )
                return browser
            last_error = error
            reward_technique("cdp", route, False, elapsed)
            print(
                f"CDP CONNECT route {route} did not complete in cycle {cycle} "
                f"after {elapsed:.2f}s: {concise_error(error or 'unknown')}",
                file=sys.stderr,
            )
            await asyncio.sleep(0.05)
        now = time.monotonic()
        elapsed_total = now - started_all
        if now >= next_status:
            detail = concise_error(last_error or "no endpoint response")
            print(
                f"CDP PERSISTENT CONNECT {elapsed_total:.0f}s; cycles={cycle}; "
                f"probes={probes}; handshakes={handshakes}; next timeout up to "
                f"{CDP_HANDSHAKE_TIMEOUT_LADDER_MS[min(cycle, len(CDP_HANDSHAKE_TIMEOUT_LADDER_MS)-1)]/1000:.0f}s; "
                f"workload retained; last={detail}",
                file=sys.stderr,
            )
            next_status = now + (
                CDP_CONNECT_STATUS_FAST_SECONDS
                if elapsed_total < 60
                else CDP_CONNECT_STATUS_SLOW_SECONDS
            )
        await asyncio.sleep(
            CDP_CONNECT_RETRY_DELAY_SECONDS if payload is not None else min(0.50, 0.08 * cycle)
        )

async def get_existing_context(browser: Browser) -> BrowserContext:
    """Return the persistent browser context exposed by Edge."""
    if not browser.contexts:
        raise RuntimeError(
            "Connected to Edge, but no browser context was available."
        )
    return browser.contexts[0]


async def cached_visible(page: Page,key: str,timeout_ms: int = CACHED_LOCATOR_FAST_TIMEOUT_MS) -> Optional[Locator]:
    """Validate a cached Locator briefly; callers fall back to normal discovery."""
    locator=_PAGE_UI_CACHE.get(id(page),{}).get(key)
    if locator is None:
        return None
    deadline=time.monotonic()+max(0,timeout_ms)/1000
    while True:
        try:
            if await locator.count() and await locator.is_visible():
                return locator
        except PlaywrightError:
            break
        if time.monotonic()>=deadline:
            break
        await asyncio.sleep(0.010)
    _PAGE_UI_CACHE.get(id(page),{}).pop(key,None)
    return None


def cache_page_locator(page: Page,key: str,locator: Optional[Locator]) -> Optional[Locator]:
    if locator is not None:
        _PAGE_UI_CACHE.setdefault(id(page),{})[key]=locator
    return locator


async def cached_first_visible(page: Page,key: str,locators: Sequence[Locator],timeout_ms: int) -> Optional[Locator]:
    cached=await cached_visible(page,key)
    if cached is not None:
        return cached
    return cache_page_locator(page,key,await first_visible(locators,timeout_ms))


async def first_visible(
    locators: Sequence[Locator], timeout_ms: int, poll_interval_seconds: float = 0.008,
) -> Optional[Locator]:
    """Return the first visible match while probing locator strategies concurrently."""
    async def probe(locator: Locator) -> Optional[Locator]:
        try:
            count = min(await locator.count(), 12)
            for index in range(count):
                candidate = locator.nth(index)
                if await candidate.is_visible():
                    return candidate
        except PlaywrightError:
            return None
        return None
    deadline = time.monotonic() + max(timeout_ms, 0) / 1000
    while True:
        for result in await asyncio.gather(*(probe(locator) for locator in locators)):
            if result is not None:
                return result
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(poll_interval_seconds)

async def visible_candidates(
    locators: Sequence[Locator],
    timeout_ms: int,
    maximum: int = 40,
) -> list[Locator]:
    """Return visible, de-duplicated elements from several locator strategies."""
    deadline = time.monotonic() + max(timeout_ms, 0) / 1000

    while True:
        candidates: list[Locator] = []
        seen_boxes: set[tuple[int, int, int, int]] = set()
        for locator in locators:
            try:
                count = min(await locator.count(), maximum)
                for index in range(count):
                    candidate = locator.nth(index)
                    if not await candidate.is_visible():
                        continue
                    box = await candidate.bounding_box()
                    if box is not None:
                        box_key = (
                            round(box["x"]),
                            round(box["y"]),
                            round(box["width"]),
                            round(box["height"]),
                        )
                        if box_key in seen_boxes:
                            continue
                        seen_boxes.add(box_key)
                    candidates.append(candidate)
                    if len(candidates) >= maximum:
                        return candidates
            except PlaywrightError:
                continue

        if candidates or time.monotonic() >= deadline:
            return candidates
        await asyncio.sleep(0.015)


def editor_locators(page: Page) -> list[Locator]:
    """Return editor locators from most specific to most general."""
    return [
        page.locator("#m365-chat-editor-target-element"),
        page.locator(
            "[data-testid*='chat-editor' i] [contenteditable='true']"
        ),
        page.locator(
            "[data-test-id*='chat-editor' i] [contenteditable='true']"
        ),
        page.locator(
            "[role='textbox'][contenteditable='true'][aria-label*='Copilot' i]"
        ),
        page.locator("[role='textbox'][aria-label*='Message' i]"),
        page.locator("textarea[aria-label*='Copilot' i]"),
        page.locator("textarea[placeholder*='message' i]"),
        page.locator("main [contenteditable='true'][role='textbox']"),
    ]


def model_switcher_locators(page: Page) -> list[Locator]:
    """Return known and accessible model-switcher locators."""
    return [
        page.locator("#gptModeSwitcher"),
        page.locator("[data-testid*='gptModeSwitcher' i]"),
        page.locator("[data-test-id*='gptModeSwitcher' i]"),
        page.get_by_role(
            "button",
            name=re.compile(
                r"Quick response|Think(?:ing)? deeper|Deep response|"
                r"Auto|Instant|Smart|GPT(?:[-\s]?\d)?",
                re.IGNORECASE,
            ),
        ),
        page.locator("button[aria-label*='response mode' i]"),
        page.locator("button[aria-label*='mode selector' i]"),
        page.locator("button[aria-label*='model selector' i]"),
        page.locator("button[aria-label*='GPT' i][aria-haspopup]"),
        page.locator("button[title*='model' i]"),
    ]


async def page_looks_like_sign_in(page: Page) -> bool:
    """Identify common Microsoft sign-in states without relying on one URL."""
    current_url = page.url.lower()
    if any(
        marker in current_url
        for marker in (
            "login.microsoftonline.com",
            "login.live.com",
            "signin",
        )
    ):
        return True

    sign_in = await first_visible(
        [
            page.get_by_role("button", name=re.compile(r"^sign in$", re.IGNORECASE)),
            page.get_by_role("link", name=re.compile(r"^sign in$", re.IGNORECASE)),
        ],
        timeout_ms=0,
    )
    return sign_in is not None


async def wait_for_copilot_ui(
    page: Page,
    timeout_ms: int,
    allow_interactive_login: bool,
) -> None:
    """Wait for the editor or model switcher, allowing a first-run sign-in."""
    deadline = time.monotonic() + timeout_ms / 1000
    sign_in_notice_printed = False

    while time.monotonic() < deadline:
        ready = await first_visible(
            [*editor_locators(page), *model_switcher_locators(page)],
            timeout_ms=0,
        )
        if ready is not None:
            return

        if allow_interactive_login and not sign_in_notice_printed:
            if await page_looks_like_sign_in(page):
                print(
                    "\nMicrosoft 365 sign-in is required in the Edge window. "
                    "Complete it there; this script will continue automatically."
                )
                sign_in_notice_printed = True

        await asyncio.sleep(0.03)

    if sign_in_notice_printed:
        raise RuntimeError(
            "Microsoft 365 sign-in was not completed before the login timeout."
        )
    raise RuntimeError(
        "The Copilot editor did not become ready before the page timeout."
    )


def model_aliases(model_name: str) -> list[str]:
    """Build equivalent labels used by different Copilot UI versions."""
    aliases = [model_name.strip()]
    without_version = re.sub(
        r"^GPT[\s-]*\d+(?:\.\d+)*\s*",
        "",
        model_name,
        flags=re.IGNORECASE,
    ).strip(" -")
    if without_version:
        aliases.append(without_version)

    if "think deeper" in model_name.lower():
        aliases.extend(["Think deeper", "Thinking deeper", "Deep response"])
    elif "thinking deeper" in model_name.lower():
        aliases.extend(["Thinking deeper", "Think deeper", "Deep response"])
    elif "deep response" in model_name.lower():
        aliases.extend(["Deep response", "Think deeper", "Thinking deeper"])

    unique: list[str] = []
    for alias in aliases:
        if alias and alias.casefold() not in {item.casefold() for item in unique}:
            unique.append(alias)
    return unique


def model_name_pattern(model_name: str) -> re.Pattern[str]:
    alternatives = "|".join(
        re.escape(alias) for alias in sorted(model_aliases(model_name), key=len, reverse=True)
    )
    return re.compile(alternatives, re.IGNORECASE)


def model_version_aliases(model_name: str) -> list[str]:
    """Return common spacing and hyphen variants for a requested GPT version."""
    match = re.search(
        r"\bGPT[\s-]*(\d+(?:\.\d+)*)",
        model_name,
        flags=re.IGNORECASE,
    )
    if match is None:
        return []
    version = match.group(1)
    return [f"GPT {version}", f"GPT-{version}", f"GPT{version}"]


def normalize_ui_text(value: str) -> str:
    """Normalize whitespace and dash variants used in accessible UI labels."""
    return re.sub(
        r"\s+",
        " ",
        value.replace("\u00a0", " ").replace("\u2011", "-").replace("\u2013", "-"),
    ).strip().casefold()


async def locator_description(locator: Locator) -> str:
    """Read the visible and accessible text exposed by a control."""
    try:
        value = await locator.evaluate(
            """
            element => [
                element.innerText,
                element.textContent,
                element.getAttribute('aria-label'),
                element.getAttribute('title')
            ].filter(Boolean).join(' ')
            """
        )
    except PlaywrightError:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def description_matches_model(description: str, model_name: str) -> bool:
    normalized = normalize_ui_text(description)
    return any(
        normalize_ui_text(alias) in normalized
        for alias in model_aliases(model_name)
    )


def model_option_locators(page: Page, model_name: str) -> list[Locator]:
    pattern = model_name_pattern(model_name)
    return [
        page.get_by_role("menuitem", name=pattern),
        page.get_by_role("option", name=pattern),
        page.get_by_role("radio", name=pattern),
        page.get_by_role("button", name=pattern),
        page.locator(
            "button, [role='button'], [role='menuitem'], [role='option'], "
            "[role='radio'], [role='treeitem'], [tabindex='0'], "
            "[data-testid*='model' i], [data-test-id*='model' i]"
        ).filter(has_text=pattern),
        page.get_by_text(pattern, exact=False),
    ]


async def find_model_option(
    page: Page,
    model_name: str,
    timeout_ms: int,
) -> Optional[Locator]:
    """Find a model option by role, text, or normalized accessible label."""
    deadline = time.monotonic() + max(timeout_ms, 0) / 1000

    while True:
        direct = await first_visible(
            model_option_locators(page, model_name),
            timeout_ms=0,
        )
        if direct is not None:
            return direct

        controls = await visible_candidates(
            [
                page.locator(
                    "button, [role='button'], [role='menuitem'], "
                    "[role='option'], [role='radio'], [role='treeitem'], "
                    "[tabindex='0']"
                )
            ],
            timeout_ms=0,
            maximum=100,
        )
        for control in controls:
            if description_matches_model(
                await locator_description(control), model_name
            ):
                return control

        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(0.015)


def submenu_locators(page: Page, model_name: str) -> list[Locator]:
    """Return provider/version controls that may reveal the desired model."""
    submenu_terms = [
        *model_version_aliases(model_name),
        "OpenAI",
        "Models",
        "More models",
        "Advanced",
    ]
    pattern = re.compile(
        "|".join(re.escape(term) for term in submenu_terms),
        re.IGNORECASE,
    )
    return [
        page.locator("[data-test-id='gptSubMenuModelTrigger-OpenAI']"),
        page.locator("[data-testid='gptSubMenuModelTrigger-OpenAI']"),
        page.get_by_role("menuitem", name=pattern),
        page.locator(
            "[role='menuitem'], [role='treeitem'], [aria-haspopup='menu'], "
            "[aria-haspopup='listbox']"
        ).filter(has_text=pattern),
    ]


async def active_element_description(page: Page) -> str:
    value = await page.evaluate(
        """
        () => {
            const element = document.activeElement;
            if (!element) return '';
            return [
                element.innerText,
                element.textContent,
                element.getAttribute('aria-label'),
                element.getAttribute('title')
            ].filter(Boolean).join(' ');
        }
        """
    )
    return re.sub(r"\s+", " ", str(value)).strip()


async def select_model_with_keyboard(page: Page, model_name: str) -> bool:
    """Use accessible menu navigation when the picker hides its text structure."""
    await page.keyboard.press("Home")
    for _ in range(30):
        description = await active_element_description(page)
        if description_matches_model(description, model_name):
            clicked = await page.evaluate(
                """
                () => {
                    const element = document.activeElement;
                    if (!element || typeof element.click !== 'function') return false;
                    element.click();
                    return true;
                }
                """
            )
            return bool(clicked)

        normalized = normalize_ui_text(description)
        if any(
            normalize_ui_text(term) in normalized
            for term in [
                *model_version_aliases(model_name),
                "OpenAI",
                "Models",
                "More models",
            ]
        ):
            await page.keyboard.press("ArrowRight")
            option = await find_model_option(page, model_name, 750)
            if option is not None:
                await option.click()
                return True

        await page.keyboard.press("ArrowDown")
    return False


async def visible_interactive_labels(page: Page, limit: int = 20) -> list[str]:
    """Collect concise visible control labels for actionable failure output."""
    controls = await visible_candidates(
        [
            page.locator(
                "button, [role='button'], [role='menuitem'], [role='option'], "
                "[role='radio'], [role='treeitem']"
            )
        ],
        timeout_ms=0,
        maximum=100,
    )
    labels: list[str] = []
    for control in controls:
        description = await locator_description(control)
        description = re.sub(r"\s+", " ", description).strip()
        if not description or description in labels:
            continue
        labels.append(description[:120])
        if len(labels) >= limit:
            break
    return labels


async def select_from_open_model_picker(
    page: Page,
    model_name: str,
) -> bool:
    """Select the requested model from an already opened picker."""
    option = await find_model_option(page, model_name, 2_500)
    if option is not None:
        await option.click()
        return True

    submenus = await visible_candidates(
        submenu_locators(page, model_name),
        timeout_ms=2_000,
        maximum=20,
    )
    for submenu in submenus:
        try:
            await submenu.hover()
            option = await find_model_option(page, model_name, 750)
            if option is not None:
                await option.click()
                return True

            await submenu.click()
            option = await find_model_option(page, model_name, 2_500)
            if option is not None:
                await option.click()
                return True

            await page.keyboard.press("ArrowRight")
            option = await find_model_option(page, model_name, 750)
            if option is not None:
                await option.click()
                return True
        except PlaywrightError:
            continue

    return await select_model_with_keyboard(page, model_name)


async def model_selection_state(page: Page, model_name: str) -> str:
    """Inspect, open, or select the requested model in one browser-side pass."""
    aliases = [normalize_ui_text(value) for value in model_aliases(model_name)]
    return str(await page.evaluate(r"""
        aliases => {
            const norm = value => (value || '').replace(/[\u2011\u2013]/g, '-').replace(/\s+/g, ' ').trim().toLowerCase();
            const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const desc = el => norm([el?.innerText, el?.textContent, el?.getAttribute?.('aria-label'), el?.getAttribute?.('title'), el?.getAttribute?.('data-testid'), el?.getAttribute?.('data-test-id')].filter(Boolean).join(' '));
            const matches = el => aliases.some(alias => alias && desc(el).includes(alias));
            const controls = [...document.querySelectorAll('button,[role="button"],[role="menuitem"],[role="option"],[role="radio"],[role="treeitem"],[aria-haspopup="menu"],[aria-haspopup="listbox"],[data-testid*="model" i],[data-test-id*="model" i]')].filter(visible);
            const switchers = [document.querySelector('#gptModeSwitcher'), document.querySelector('[data-testid*="gptModeSwitcher" i]'), document.querySelector('[data-test-id*="gptModeSwitcher" i]'), ...controls.filter(el => el.hasAttribute('aria-haspopup') && /model|mode|gpt|quick response|think|deep response|auto|instant/.test(desc(el)))].filter((el,i,a)=>visible(el)&&a.indexOf(el)===i);
            for (const sw of switchers) if (matches(sw)) return 'selected';
            const option = controls.find(el => matches(el) && !el.hasAttribute('aria-haspopup') && el.id !== 'gptModeSwitcher');
            if (option) { option.click(); return 'option-clicked'; }
            if (switchers[0]) { switchers[0].click(); return 'switcher-clicked'; }
            return 'waiting';
        }
    """, aliases))

# App selections retain their exact version and response mode across all retries.
GLOBAL_MODEL_SPECS = {
    "GPT 5.6 Sol Quick response": ("OpenAI", "checkmark-Gpt_5_6_Chat", ["GPT 5.6 Sol Quick response", "GPT 5.6 Quick response", "GPT 5.6 Sol Quick"]),
    "GPT 5.6 Sol Think deeper": ("OpenAI", "checkmark-Gpt_5_6_Reasoning", ["GPT 5.6 Sol Think deeper", "GPT 5.6 Think deeper", "GPT 5.6 Sol Think", "GPT 5.6 Think"]),
    "GPT-6 Sol": ("OpenAI", "checkmark-Gpt_6_Sol_Reasoning", ["GPT-6 Sol", "GPT 6 Sol", "GPT 6.0 Sol", "GPT-6.0 Sol"]),
    "Sonnet 5.5": ("Claude", "checkmark-Claude_Sonnet", ["Sonnet 5.5", "Claude Sonnet 5.5"]),
    "Opus 5.5": ("Claude", "checkmark-Claude_Opus", ["Opus 5.5", "Claude Opus 5.5"]),
    "Sonnet 5": ("Claude", "checkmark-Claude_Sonnet_5", ["Sonnet 5", "Sonnet 5.0", "Claude Sonnet 5", "Claude Sonnet 5.0"]),
}


def exact_global_model_pattern(model_name: str) -> re.Pattern[str]:
    aliases = GLOBAL_MODEL_SPECS[model_name][2]
    labels = [re.escape(value).replace(r"GPT\ ", r"GPT[\s\u2011\u2013-]*").replace(r"GPT\-", r"GPT[\s\u2011\u2013-]*") for value in aliases]
    return re.compile(r"(?:" + "|".join(labels) + r")(?![\w.])", re.I)


def exact_model_checkmark(model_name: str) -> tuple[str, str]:
    """Return the exact radio identifier for the requested model."""
    if model_name in GLOBAL_MODEL_SPECS:
        provider, test_id, _ = GLOBAL_MODEL_SPECS[model_name]
        return provider, test_id
    normalized = normalize_ui_text(model_name)
    if normalized == "sonnet":
        return "Claude", "checkmark-Claude_Sonnet"
    if normalized == "opus":
        return "Claude", "checkmark-Claude_Opus"
    if normalized == normalize_ui_text(GPT_6_SOL_MODEL_NAME):
        return "OpenAI", "checkmark-Gpt_6_Sol_Reasoning"
    match = re.search(r"\bGPT[\s-]*(\d+(?:\.\d+)*)", model_name, re.IGNORECASE)
    if match is None:
        raise RuntimeError(f"Unsupported nested model: {model_name!r}")
    return "OpenAI", f"checkmark-Gpt_{match.group(1).replace('.', '_')}_Reasoning"


async def exact_nested_model_locator(page: Page, model_name: str) -> Locator:
    """Locate only the real nested GPT/Claude model radio."""
    if model_name in GLOBAL_MODEL_SPECS:
        # Versioned Claude IDs differ by tenant/UI rollout; visible exact labels
        # are authoritative and never accept an unversioned Claude fallback.
        return page.get_by_role("menuitemradio", name=exact_global_model_pattern(model_name)).first
    _, test_id = exact_model_checkmark(model_name)
    return page.locator(
        f"[role='menuitemradio']:has(svg[data-testid='{test_id}']), "
        f"[role='menuitemradio']:has(svg[data-test-id='{test_id}'])"
    ).first


def collapsed_model_selector_aliases(model_name: str) -> list[str]:
    """Return trusted collapsed-selector labels for an exact requested model.

    Copilot shortens the selected GPT 5.6 Think Deeper label to GPT 5.6 Think
    after the picker closes. This alias is accepted only for the corresponding
    exact GPT version and reasoning mode, preventing a generic Think label from
    satisfying a different requested model.
    """
    if model_name in GLOBAL_MODEL_SPECS:
        return GLOBAL_MODEL_SPECS[model_name][2]
    normalized = normalize_ui_text(model_name)
    if normalized == normalize_ui_text(GPT_6_SOL_MODEL_NAME):
        return ["gpt 6.0 sol", "gpt-6.0 sol", "gpt6.0 sol"]
    match = re.search(r"\bgpt\s*-?\s*(\d+(?:\.\d+)*)", normalized, re.IGNORECASE)
    if match is None or not any(
        term in normalized
        for term in ("think deeper", "thinking deeper", "deep response")
    ):
        return []
    version = match.group(1)
    return [
        f"gpt {version} think",
        f"gpt-{version} think",
        f"gpt{version} think",
    ]


async def collapsed_model_selector_is_selected(
    page: Page,
    model_name: str,
) -> bool:
    """Accept Copilot's shortened visible selector label as selected state."""
    if model_name in GLOBAL_MODEL_SPECS:
        return bool(await page.evaluate(r"""pattern => {
            const sw = document.querySelector('#gptModeSwitcher,[data-testid*="gptModeSwitcher" i],[data-test-id*="gptModeSwitcher" i]');
            if (!sw) return false;
            const text = [sw.innerText, sw.getAttribute('aria-label')].filter(Boolean).join(' ').replace(/\s+/g, ' ');
            return new RegExp(pattern, 'i').test(text);
        }""", exact_global_model_pattern(model_name).pattern))
    aliases = [
        normalize_ui_text(value)
        for value in collapsed_model_selector_aliases(model_name)
    ]
    if not aliases:
        return False
    try:
        return bool(await page.evaluate(
            r"""
            aliases => {
                const norm = value => String(value || '')
                    .replace(/[\u2011\u2013]/g, '-')
                    .replace(/\s+/g, ' ')
                    .trim()
                    .toLowerCase();
                const visible = element => !!(
                    element && (
                        element.offsetWidth ||
                        element.offsetHeight ||
                        element.getClientRects().length
                    )
                );
                const selectors = [
                    '#gptModeSwitcher',
                    '[data-testid*="gptModeSwitcher" i]',
                    '[data-test-id*="gptModeSwitcher" i]',
                    'button[aria-label*="Model Selector" i]',
                    'button[aria-label*="GPT" i][aria-haspopup]'
                ];
                const controls = [];
                for (const selector of selectors) {
                    for (const element of document.querySelectorAll(selector)) {
                        if (visible(element) && !controls.includes(element)) {
                            controls.push(element);
                        }
                    }
                }
                return controls.some(element => {
                    const description = norm([
                        element.innerText,
                        element.textContent,
                        element.getAttribute('aria-label'),
                        element.getAttribute('title')
                    ].filter(Boolean).join(' '));
                    return aliases.some(alias => description.includes(alias));
                });
            }
            """,
            aliases,
        ))
    except PlaywrightError:
        return False


async def model_is_selected(page: Page, model_name: str) -> bool:
    """Confirm selection from the exact radio or trusted collapsed selector."""
    try:
        item = await exact_nested_model_locator(page, model_name)
        if (
            await item.count()
            and (await item.get_attribute("aria-checked") or "").casefold()
            == "true"
        ):
            return True
    except (PlaywrightError, RuntimeError):
        pass
    return await collapsed_model_selector_is_selected(page, model_name)


async def click_global_model_option(page: Page, model_name: str, timeout_ms: int, verbose: bool = True) -> None:
    """Select by versioned radio label and confirm the checked radio in the UI."""
    provider, _, aliases = GLOBAL_MODEL_SPECS[model_name]
    pattern = exact_global_model_pattern(model_name)
    deadline = time.monotonic() + max(0.4, timeout_ms / 1000)
    clicked = False
    last_state = "model picker unavailable"
    while time.monotonic() < deadline:
        try:
            state = await page.evaluate(r"""payload => {
                const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
                const norm = value => String(value || '').replace(/[\u2011\u2013]/g, '-').replace(/\s+/g, ' ').trim();
                const regex = new RegExp(payload.pattern, 'i');
                const radios = [...document.querySelectorAll('[role="menuitemradio"]')];
                const exact = radios.find(el => regex.test(norm([el.innerText, el.getAttribute('aria-label')].filter(Boolean).join(' '))));
                if (exact && visible(exact)) {
                    if (exact.getAttribute('aria-checked') === 'true') return 'verified';
                    if (!payload.clicked && exact.getAttribute('aria-disabled') !== 'true' && !exact.disabled) { exact.click(); return 'clicked'; }
                }
                const providerNames = payload.provider === "Claude" ? ["Claude", "Anthropic"] : [payload.provider];
                const provider = providerNames.map(name => document.querySelector(`[data-test-id="gptSubMenuModelTrigger-${name}"],[data-testid="gptSubMenuModelTrigger-${name}"]`)).find(visible);
                if (provider && visible(provider)) {
                    if (provider.getAttribute('aria-expanded') !== 'true') provider.click();
                    return 'provider opened';
                }
                const sw = document.querySelector('#gptModeSwitcher,[data-testid*="gptModeSwitcher" i],[data-test-id*="gptModeSwitcher" i],button[aria-label*="Model Selector" i]');
                if (sw && visible(sw)) {
                    if (sw.getAttribute('aria-expanded') !== 'true') sw.click();
                    return 'picker opened';
                }
                return 'model picker unavailable';
            }""", {"provider": provider, "pattern": pattern.pattern, "clicked": clicked})
            last_state = str(state)
            if state == "verified":
                await page.keyboard.press("Escape")
                await page.keyboard.press("Escape")
                if verbose:
                    print(f"MODEL VERIFIED: {model_name}; exact version and mode radio is checked")
                return
            if state == "clicked":
                clicked = True
            await asyncio.sleep(0.025)
        except PlaywrightError as exc:
            last_state = concise_error(exc)
            await asyncio.sleep(0.025)
    raise RuntimeError(f"Selected model {model_name!r} is unavailable or could not be verified in Copilot Chat ({last_state}). No alternative model was used. Sign in to the review profile and check your model access.")


async def click_model_option(page: Page, model_name: str, timeout_ms: int, verbose: bool = True) -> None:
    """Select the exact nested model immediately through one browser-side transaction.

    The fast path opens the visible switcher/provider and clicks only the exact
    menuitemradio identified by its model checkmark. It never clicks the generic
    top-level Think deeper item and never re-clicks an already selected radio.
    """
    if model_name in GLOBAL_MODEL_SPECS:
        await click_global_model_option(page, model_name, timeout_ms, verbose)
        return
    provider_id, test_id = exact_model_checkmark(model_name)

    aliases = [normalize_ui_text(value) for value in collapsed_model_selector_aliases(model_name)]
    deadline = time.monotonic() + max(0.40, timeout_ms / 1000)
    attempts = 0
    last_state = "waiting"
    while time.monotonic() < deadline:
        attempts += 1
        try:
            state = str(await page.evaluate(r"""
                payload => {
                    const {providerId, testId, collapsedAliases} = payload;
                    const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
                    const norm = value => String(value || '').replace(/[\u2011\u2013]/g, '-').replace(/\s+/g, ' ').trim().toLowerCase();
                    const desc = el => norm([el?.innerText, el?.textContent, el?.getAttribute?.('aria-label'), el?.getAttribute?.('title')].filter(Boolean).join(' '));
                    const switcherSelectors = [
                        '#gptModeSwitcher',
                        '[data-testid*="gptModeSwitcher" i]',
                        '[data-test-id*="gptModeSwitcher" i]',
                        'button[aria-label*="Model Selector" i]',
                        'button[aria-label*="GPT" i][aria-haspopup]'
                    ];
                    const switcher = switcherSelectors.map(s => document.querySelector(s)).find(visible);
                    if (switcher && collapsedAliases.some(alias => alias && desc(switcher).includes(alias))) return 'selected-collapsed';

                    const exact = [...document.querySelectorAll('[role="menuitemradio"]')].find(item =>
                        item.querySelector(`svg[data-testid="${testId}"],svg[data-test-id="${testId}"]`)
                    );
                    if (exact) {
                        if ((exact.getAttribute('aria-checked') || '').toLowerCase() === 'true') return 'selected-radio';
                        if (visible(exact)) { exact.click(); return 'exact-clicked'; }
                    }

                    const provider = document.querySelector(
                        `[data-test-id="gptSubMenuModelTrigger-${providerId}"],` +
                        `[data-testid="gptSubMenuModelTrigger-${providerId}"]`
                    );
                    if (provider && visible(provider)) {
                        if (provider.getAttribute('aria-expanded') !== 'true') provider.click();
                        return 'provider-opened';
                    }
                    if (switcher) {
                        if (switcher.getAttribute('aria-expanded') !== 'true') switcher.click();
                        return 'switcher-opened';
                    }
                    return 'waiting';
                }
            """, {"providerId": provider_id, "testId": test_id, "collapsedAliases": aliases}))
            last_state = state
            if state in {"selected-collapsed", "selected-radio"}:
                if verbose:
                    print(f"Exact nested model already selected: {model_name}")
                return
            if state == "exact-clicked":
                # One exact click is enough. Verify rapidly without reopening or
                # issuing another click that could toggle the menu state.
                verify_until = min(deadline, time.monotonic() + 0.45)
                while time.monotonic() < verify_until:
                    if await model_is_selected(page, model_name):
                        if verbose:
                            print(f"Exact nested model selected immediately: {model_name}")
                        return
                    await asyncio.sleep(0.015)
                # Copilot commonly removes the exact radio as the picker closes.
                # A closed picker immediately after the exact click is accepted.
                expanded = await page.evaluate(r"""() => {
                    const sw=document.querySelector('#gptModeSwitcher,[data-testid*="gptModeSwitcher" i],[data-test-id*="gptModeSwitcher" i]');
                    return !!(sw && sw.getAttribute('aria-expanded') === 'true');
                }""")
                if not expanded and (
                    normalize_ui_text(model_name) != normalize_ui_text(GPT_6_SOL_MODEL_NAME)
                    or await model_is_selected(page, model_name)
                ):
                    if verbose:
                        print(f"Exact nested model selected immediately: {model_name}")
                    return
            await asyncio.sleep(0.025)
        except PlaywrightError as exc:
            last_state = concise_error(exc)
            await asyncio.sleep(0.025)

    # Keep the established locator implementation as one bounded compatibility
    # fallback, but with enough click time to avoid the observed 200 ms false fail.
    try:
        switcher = await first_visible(model_switcher_locators(page), timeout_ms=250)
        if switcher is not None and await switcher.get_attribute("aria-expanded") != "true":
            await switcher.click(timeout=750, no_wait_after=True)
        provider = page.locator(
            f"[data-test-id='gptSubMenuModelTrigger-{provider_id}'], "
            f"[data-testid='gptSubMenuModelTrigger-{provider_id}']"
        ).first
        if await provider.count() and await provider.is_visible() and await provider.get_attribute("aria-expanded") != "true":
            await provider.click(timeout=750, no_wait_after=True)
        exact = await exact_nested_model_locator(page, model_name)
        if await exact.count():
            if (await exact.get_attribute("aria-checked") or "").casefold() != "true":
                await exact.click(timeout=750, no_wait_after=True)
            if normalize_ui_text(model_name) == normalize_ui_text(GPT_6_SOL_MODEL_NAME):
                if not await model_is_selected(page, model_name):
                    raise RuntimeError("GPT 6.0 Sol click was not confirmed by its radio or collapsed selector")
            if verbose:
                print(f"Exact nested model selected by bounded compatibility fallback: {model_name}")
            return
    except PlaywrightError as exc:
        last_state = concise_error(exc)
    raise RuntimeError(
        f"Exact nested model {model_name!r} was not selected after {attempts} immediate browser-side checks. Last state: {last_state}."
    )
async def editor_text(editor: Locator) -> str:
    value = await editor.evaluate(
        """
        element => {
            if ('value' in element) {
                return element.value || '';
            }
            return element.innerText || element.textContent || '';
        }
        """
    )
    return str(value)


async def make_urls_clickable(editor: Locator, message: str) -> None:
    """Turn URL text in the contenteditable editor into clickable links."""
    await editor.evaluate(
        r"""
        (element, originalMessage) => {
            const pattern = /https:\/\/[^\s<]+/g;
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
            const nodes = [];
            while (walker.nextNode()) nodes.push(walker.currentNode);
            for (const node of nodes) {
                const value = node.nodeValue || '';
                pattern.lastIndex = 0;
                if (!pattern.test(value)) continue;
                pattern.lastIndex = 0;
                const fragment = document.createDocumentFragment();
                let cursor = 0;
                for (const match of value.matchAll(pattern)) {
                    const url = match[0];
                    const index = match.index || 0;
                    if (index > cursor) fragment.appendChild(document.createTextNode(value.slice(cursor, index)));
                    const link = document.createElement('a');
                    link.href = url;
                    link.textContent = url;
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    fragment.appendChild(link);
                    cursor = index + url.length;
                }
                if (cursor < value.length) fragment.appendChild(document.createTextNode(value.slice(cursor)));
                node.parentNode.replaceChild(fragment, node);
            }
            element.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: originalMessage}));
            element.dispatchEvent(new Event('change', {bubbles: true}));
        }
        """,
        message,
    )


async def add_text_to_editor(
    page: Page,
    message: str,
    timeout_ms: int,
) -> None:
    """Place text in the Copilot editor without triggering submission."""
    editor = await cached_first_visible(page,"editor",editor_locators(page),timeout_ms)
    if editor is None:
        raise RuntimeError("The Copilot message editor was not found.")

    await editor.click()
    try:
        await editor.fill(message)
    except PlaywrightError:
        select_all = "Meta+A" if sys.platform == "darwin" else "Control+A"
        await editor.press(select_all)
        await editor.press("Backspace")
        # insert_text emits text input only; it cannot submit the prompt through
        # an Enter key event.
        await page.keyboard.insert_text(message)

    # Ensure the visible SharePoint URL is a real hyperlink, not only plain text.
    try:
        await make_urls_clickable(editor, message)
    except PlaywrightError:
        # Keep the full URL visible if this Copilot UI build blocks rich HTML.
        pass

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            actual = await editor_text(editor)
        except PlaywrightError:
            actual = ""
        if message in actual:
            return
        await asyncio.sleep(0.015)

    raise RuntimeError("The test message could not be confirmed in the editor.")


def attachment_input_locators(page: Page) -> list[Locator]:
    """Known file-input controls used by Microsoft 365 Copilot."""
    return [
        page.locator("input[type='file'][accept*='.md' i]"),
        page.locator("input[type='file'][accept*='text' i]"),
        page.locator("input[type='file']"),
    ]


def diagnostic_directory() -> Path:
    folder=Path(__file__).resolve().parent/DIAGNOSTIC_FOLDER_NAME
    folder.mkdir(parents=True,exist_ok=True)
    return folder

async def capture_attachment_diagnostics(page: Page,tab_number: int,stage: str,error: BaseException|str,planned_names: Sequence[str]=()) -> Path:
    stamp=datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    base=diagnostic_directory()/f"tab_{tab_number}_{stage}_{stamp}"
    report=base.with_suffix('.txt'); html=base.with_suffix('.html'); shot=base.with_suffix('.png')
    try:
        state=await page.evaluate(r"""() => {
          const visible=e=>!!(e&&(e.offsetWidth||e.offsetHeight||e.getClientRects().length));
          const d=e=>({tag:e.tagName,id:e.id||'',type:e.getAttribute('type')||'',accept:e.getAttribute('accept')||'',testid:e.getAttribute('data-testid')||e.getAttribute('data-test-id')||'',aria:e.getAttribute('aria-label')||'',expanded:e.getAttribute('aria-expanded')||'',visible:visible(e),connected:e.isConnected,html:e.outerHTML.slice(0,1500)});
          return {url:location.href,title:document.title,
            buttons:[...document.querySelectorAll('#plus-menu-container button,button[data-testid="PlusMenuButton"],button[data-testid="chat-input-attach-button"],button[data-test-id="chat-input-attach-button"],button[aria-label="Add"][aria-haspopup="menu"]')].map(d),
            inputs:[...document.querySelectorAll('input[type="file"]')].map(d),
            chips:[...document.querySelectorAll('[aria-label="Attachments"] [data-overflow-item="true"][aria-label],button[aria-label^="Remove attachment "]')].map(e=>e.getAttribute('aria-label')||'').filter(Boolean),
            menus:[...document.querySelectorAll('[role="menu"],[data-popper-placement]')].filter(visible).map(e=>(e.innerText||e.textContent||'').slice(0,2000))};
        }""")
    except Exception as exc: state={'evaluation_error':repr(exc)}
    try: html.write_text(await page.content(),encoding='utf-8')
    except Exception as exc: state['html_error']=repr(exc)
    try: await page.screenshot(path=str(shot),full_page=False)
    except Exception as exc: state['screenshot_error']=repr(exc)
    report.write_text('\n'.join([
      'COPILOT AUTOMATION ATTACHMENT FAILURE REPORT',
      f"Timestamp: {datetime.now().astimezone().isoformat(timespec='seconds')}",f'Tab: {tab_number}',f'Stage: {stage}',f'Error: {error}',
      f'Planned count: {len(planned_names)}','Planned names:',*[f'- {n}' for n in planned_names],'',
      'DOM STATE JSON:',json.dumps(state,indent=2,ensure_ascii=False),'',f'HTML: {html}',f'Screenshot: {shot}']),encoding='utf-8')
    return report

def attachment_button_locators(page: Page) -> list[Locator]:
    """Only genuine composer attachment controls; never quick-action buttons."""
    return [
        page.locator("#plus-menu-container button[data-testid='PlusMenuButton']"),
        page.locator("button[data-testid='PlusMenuButton'][aria-label='Add and manage sources']"),
        page.locator("button[data-testid='chat-input-attach-button']"),
        page.locator("button[data-test-id='chat-input-attach-button']"),
        page.locator("button[aria-label='Add'][aria-haspopup='menu']"),
    ]

async def composer_attachment_count(page: Page) -> int:
    """Count all composer attachments, including overflow-hidden chips.

    Copilot sets display:none on overflowed attachment chips and shows a +N
    button. Visibility must therefore never be required for attachment counting.
    """
    try:
        return int(await page.evaluate(
            r"""() => {
                const roots = new Set();
                const selectors = [
                    '[aria-label="Attachments"] > [data-overflow-item="true"]',
                    '[aria-label="Attachments"] > div[id^="SPO_"]',
                    'button[aria-label^="Remove attachment "]'
                ];
                for (const selector of selectors) {
                    for (const element of document.querySelectorAll(selector)) {
                        const root = element.matches('[data-overflow-item="true"], div[id^="SPO_"]')
                            ? element
                            : element.closest('[data-overflow-item="true"], div[id^="SPO_"]') || element;
                        roots.add(root);
                    }
                }
                return roots.size;
            }"""
        ))
    except (PlaywrightError, TypeError, ValueError):
        return 0


async def attachment_is_visible(page: Page, file_name: str) -> bool:
    """Detect an attachment in the DOM, including overflow-hidden chips."""
    try:
        return bool(await page.evaluate(
            r"""name => {
                const target = String(name || '').toLocaleLowerCase();
                const selectors = [
                    '[aria-label="Attachments"] [data-overflow-item="true"][aria-label]',
                    '[aria-label="Attachments"] div[id^="SPO_"][aria-label]',
                    'button[aria-label^="Remove attachment "]'
                ];
                for (const element of document.querySelectorAll(selectors.join(','))) {
                    const value = [
                        element.getAttribute('aria-label'), element.getAttribute('title'),
                        element.innerText, element.textContent
                    ].filter(Boolean).join(' ').toLocaleLowerCase();
                    if (value.includes(target)) return true;
                }
                return false;
            }""",
            file_name,
        ))
    except PlaywrightError:
        return False

async def visible_attachment_names(page: Page, expected_names: Sequence[str]) -> set[str]:
    """Return only expected filenames currently represented in the composer."""
    states = await asyncio.gather(
        *(attachment_is_visible(page, name) for name in expected_names)
    )
    return {name for name, visible in zip(expected_names, states) if visible}

async def ensure_attachment_input(page: Page) -> None:
    """Expose a live file input using independent UI, DOM and coordinate routes.

    The Copilot home screen can show a valid Add button while no input exists.
    That state is not a failed tab. Each pass reacquires the current React nodes
    and tries a different activation technique before declaring the picker unusable.
    """
    async def input_exists() -> bool:
        try:
            return bool(await page.locator("input[type='file']").count())
        except PlaywrightError:
            return False

    if await input_exists():
        return
    deadline = time.monotonic() + max(5.0, ATTACHMENT_INPUT_READY_TIMEOUT_SECONDS)
    last_error: Optional[BaseException] = None
    technique = 0
    while time.monotonic() < deadline:
        if await input_exists():
            return
        technique += 1
        route = technique % 6
        try:
            button = await first_visible(attachment_button_locators(page), timeout_ms=180)
            if route == 1:
                # Native DOM click on the exact visible Add/attachment button.
                await page.evaluate(r"""() => {
                    const selectors=['button[data-testid="chat-input-attach-button"]','button[data-test-id="chat-input-attach-button"]','#plus-menu-container button','button[aria-label="Add"]'];
                    const b=selectors.map(s=>document.querySelector(s)).find(x=>x && !x.disabled && x.getAttribute('aria-disabled')!=='true');
                    if(!b) return false; b.click(); return true;
                }""")
            elif route == 2 and button is not None:
                await button.click(timeout=300, force=True, no_wait_after=True)
            elif route == 3 and button is not None:
                await button.focus(timeout=250)
                await page.keyboard.press("Enter")
            elif route == 4 and button is not None:
                box = await button.bounding_box()
                if box:
                    await page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
            elif route == 5:
                await page.evaluate(r"""() => {
                    const b=document.querySelector('button[data-testid="chat-input-attach-button"],button[data-test-id="chat-input-attach-button"],button[aria-label="Add"]');
                    if(!b) return false;
                    for(const type of ['pointerdown','mousedown','pointerup','mouseup','click']) b.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window}));
                    return true;
                }""")
            else:
                await activate_page_like_manual_selection(page, 0, "attachment picker recovery", verbose=False)
            # Some builds create the input directly; others first expose an
            # Upload/Browse menu item. Activate that item through both DOM and UI.
            await asyncio.sleep(0.035)
            if await input_exists():
                return
            clicked = await page.evaluate(r"""() => {
                const rx=/upload|from (?:this )?device|computer|browse files/i;
                const el=[...document.querySelectorAll('[role="menuitem"],[role="button"],button')].find(x=>rx.test([x.innerText,x.textContent,x.getAttribute('aria-label')].filter(Boolean).join(' ')) && !x.disabled);
                if(!el) return false; el.click(); return true;
            }""")
            if not clicked:
                item = await first_visible([
                    page.get_by_role("menuitem", name=re.compile(r"upload|device|computer|browse", re.I)),
                    page.get_by_role("button", name=re.compile(r"upload|device|computer|browse", re.I)),
                ], timeout_ms=120)
                if item is not None:
                    await item.click(timeout=250, force=True, no_wait_after=True)
            if await input_exists():
                return
        except (PlaywrightError, RuntimeError) as exc:
            last_error = exc
        await asyncio.sleep(0.035)
    raise RuntimeError(
        "Copilot displayed an attachment button but no live file input appeared "
        f"after {technique} independent activation attempts. Last UI error: {concise_error(last_error or 'none')}"
    )

async def _best_attachment_input_node(page: Page) -> tuple[Any, int]:
    """Open Copilot's picker and return one live CDP session plus its best file input."""
    await ensure_attachment_input(page)
    session=await page.context.new_cdp_session(page)
    try:
        doc=await session.send('DOM.getDocument',{'depth':-1,'pierce':True})
        root=doc['root']['nodeId']
        result=await session.send('DOM.querySelectorAll',{'nodeId':root,'selector':'input[type=file]'})
        ids=result.get('nodeIds',[])
        if not ids:
            raise RuntimeError('Attachment picker opened, but CDP found no file input.')
        candidates=[]
        for node_id in ids:
            try:
                described=await session.send('DOM.describeNode',{'nodeId':node_id,'depth':1})
                node=described.get('node',{})
                attrs=node.get('attributes',[])
                a={str(attrs[i]):str(attrs[i+1]) for i in range(0,len(attrs)-1,2)}
                accept=a.get('accept','').lower(); score=10
                if '.pdf' in accept or 'application/pdf' in accept: score+=40
                if '.md' in accept or 'text/markdown' in accept: score+=30
                if a.get('disabled') is None: score+=5
                candidates.append((score,int(node_id),accept))
            except Exception:
                candidates.append((0,int(node_id),''))
        candidates.sort(reverse=True)
        score,selected,accept=candidates[0]
        if VERBOSE_FILE_INPUT_DETAILS:
            print(f"    Attachment input: score={score}, candidates={len(candidates)}, accept={accept!r}")
        return session,selected
    except Exception:
        await session.detach()
        raise

async def browser_local_set_input_files(page: Page,resolved: Path) -> None:
    """Assign one browser-local path through Copilot's best live file input."""
    session,selected=await _best_attachment_input_node(page)
    try:
        await session.send('DOM.setFileInputFiles',{'files':[str(resolved)],'nodeId':selected})
    finally:
        await session.detach()

async def browser_local_set_input_files_bulk(page: Page, paths: Sequence[Path]) -> None:
    """Replicate one drag/drop selection by assigning the complete file list once."""
    resolved=[str(path.expanduser().resolve()) for path in paths]
    if not resolved:
        return
    session,selected=await _best_attachment_input_node(page)
    try:
        await session.send('DOM.setFileInputFiles',{'files':resolved,'nodeId':selected})
    finally:
        await session.detach()
async def playwright_local_set_input_files_bulk(page: Page, paths: Sequence[Path]) -> None:
    """Alternative attachment route using Playwright's live file-input handle."""
    resolved=[str(path.expanduser().resolve()) for path in paths]
    if not resolved:
        return
    await ensure_attachment_input(page)
    inputs=page.locator("input[type='file']")
    count=await inputs.count()
    if not count:
        raise RuntimeError("Playwright route found no live file input.")
    last_error: Optional[BaseException]=None
    for index in range(count-1,-1,-1):
        candidate=inputs.nth(index)
        try:
            await candidate.set_input_files(resolved,timeout=max(5000,FAST_ATTACH_ASSIGN_TIMEOUT_SECONDS*1000))
            return
        except (PlaywrightError,PlaywrightTimeoutError) as exc:
            last_error=exc
    raise RuntimeError(f"Playwright file-input route failed: {last_error}")

def attachment_route_for_page(page: Page) -> str:
    return _ATTACHMENT_ROUTE_BY_PAGE.get(id(page),ATTACHMENT_RECOVERY_ROUTES[0])

def record_failed_attachment_route(page: Page, route: str) -> None:
    _ATTACHMENT_FAILED_ROUTES_BY_PAGE.setdefault(id(page),set()).add(route)

def next_unused_attachment_route(page: Page) -> Optional[str]:
    failed=_ATTACHMENT_FAILED_ROUTES_BY_PAGE.get(id(page),set())
    ranked=technique_rank("attachment", ATTACHMENT_RECOVERY_ROUTES)
    return next((route for route in ranked if route not in failed),None)

async def attachment_validation_snapshot(page: Page, expected_names: Sequence[str]) -> dict[str, Any]:
    """Read count, expected names, upload errors and limit warnings in one DOM pass."""
    try:
        return dict(await page.evaluate(r"""names => {
            const norm=v=>String(v||'').trim().toLocaleLowerCase();
            const roots=new Set();
            const texts=[];
            for (const selector of [
                '[aria-label="Attachments"] > [data-overflow-item="true"]',
                '[aria-label="Attachments"] > div[id^="SPO_"]',
                'button[aria-label^="Remove attachment "]'
            ]) {
                for (const element of document.querySelectorAll(selector)) {
                    const root=element.matches('[data-overflow-item="true"],div[id^="SPO_"]')
                        ? element : element.closest('[data-overflow-item="true"],div[id^="SPO_"]') || element;
                    roots.add(root);
                    texts.push(norm([element.getAttribute('aria-label'),element.getAttribute('title'),element.innerText,element.textContent].filter(Boolean).join(' ')));
                }
            }
            const matched=names.filter(name=>texts.some(text=>text.includes(norm(name))));
            const visible=e=>!!(e&&(e.offsetWidth||e.offsetHeight||e.getClientRects().length));
            let error=''; let warning='';
            for (const el of document.querySelectorAll('[role="alert"],[aria-live="assertive"],[class*="toast" i],[class*="messagebar" i],[role="dialog"]')) {
                if (!visible(el)) continue;
                const text=(el.innerText||el.textContent||'').trim();
                if (!error && /error occurred while uploading|error while uploading|upload failed|could not upload|try again/i.test(text)) error=text.slice(0,500);
                if (!warning && /maximum(?:\s+of)?\s+20|up\s+to\s+20\s+files|20\s+file\s+limit|too\s+many\s+files|remove\s+(?:a|one)\s+file/i.test(text)) warning=text.slice(0,500);
            }
            return {count:roots.size,matched,error,warning};
        }""", list(expected_names)))
    except (PlaywrightError,TypeError,ValueError):
        return {'count':0,'matched':[],'error':'','warning':''}

async def dismiss_or_retry_upload_error(page: Page, expected_count: int) -> bool:
    """Use Copilot's native Try again control without assigning any file twice."""
    if not await upload_error_message(page): return True
    for attempt in range(1,UPLOAD_TRY_AGAIN_ATTEMPTS+1):
        count=await composer_attachment_count(page)
        button=await first_visible([page.get_by_role("button",name=re.compile(r"^Try again$",re.I)),page.locator("button").filter(has_text=re.compile(r"^Try again$",re.I))],180)
        if button is None: break
        try:
            await button.click(timeout=350,force=True,no_wait_after=True)
            print(f"  Native upload recovery {attempt}/{UPLOAD_TRY_AGAIN_ATTEMPTS}: Try again clicked with {count}/{expected_count} chips; no files reassigned")
        except PlaywrightError: break
        until=time.monotonic()+UPLOAD_TRY_AGAIN_SETTLE_SECONDS
        while time.monotonic()<until:
            await asyncio.sleep(0.10)
            if not await upload_error_message(page): return True
    return not bool(await upload_error_message(page))

async def stable_attachment_count(page: Page, seconds: float = 0.60) -> int:
    deadline=time.monotonic()+max(0.20,seconds); last=-1; stable=time.monotonic()
    while time.monotonic()<deadline:
        current=await composer_attachment_count(page)
        if current!=last: last=current; stable=time.monotonic()
        elif time.monotonic()-stable>=0.25: return current
        await asyncio.sleep(0.05)
    return max(0,last)

async def wait_for_bulk_attachment_confirmation(page: Page, expected_names: Sequence[str], deadline: float) -> dict[str, Any]:
    """Use count plus filename evidence, with a short stability gate."""
    expected=len(expected_names)
    stable_since: Optional[float]=None
    best={'count':0,'matched':[],'error':'','warning':''}
    while time.monotonic()<deadline:
        state=await attachment_validation_snapshot(page,expected_names)
        best=state if int(state.get('count',0))>=int(best.get('count',0)) else best
        if state.get('error'):
            recovered=await dismiss_or_retry_upload_error(page,expected)
            if recovered:
                stable_since=None; continue
            count=await stable_attachment_count(page,0.50)
            if count>=expected:
                await asyncio.sleep(0.20); continue
            raise FreshChatRequiredError(f"Copilot reported an unrecovered upload error with {count}/{expected} chips: {state['error']}")
        if state.get('warning'):
            raise RuntimeError(f"Copilot reported an attachment-limit warning: {state['warning']}")
        count=int(state.get('count',0)); matched=len(state.get('matched',[]))
        complete=count>=expected and (matched>=len(set(expected_names)) or count==expected)
        if complete:
            if stable_since is None: stable_since=time.monotonic()
            elif time.monotonic()-stable_since>=BULK_ATTACH_STABLE_SECONDS: return state
        else:
            stable_since=None
        await asyncio.sleep(FAST_ATTACH_POLL_SECONDS)
    return best

async def attachment_limit_warning(page: Page) -> Optional[str]:
    """Read only likely visible warning containers; never scan the full page."""
    try:
        value = await page.evaluate(
            r"""() => {
                const visible = el => !!(
                    el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length)
                );
                const pattern = /maximum(?:\s+of)?\s+20|up\s+to\s+20\s+files|20\s+file\s+limit|too\s+many\s+files|remove\s+(?:a|one)\s+file/i;
                const selectors = [
                    '[role="alert"]', '[role="dialog"]', '[aria-live="assertive"]',
                    '[class*="toast" i]', '[class*="messagebar" i]'
                ];
                for (const node of document.querySelectorAll(selectors.join(','))) {
                    if (!visible(node)) continue;
                    const text = (node.innerText || node.textContent || '').trim();
                    if (text && pattern.test(text)) return text.slice(0, 500);
                }
                return '';
            }"""
        )
        return str(value).strip() or None
    except PlaywrightError:
        return None


async def upload_error_message(page: Page) -> Optional[str]:
    """Return a visible Copilot upload error without confusing other alerts."""
    try:
        value = await page.evaluate(r"""() => {
            const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const wanted = /an error occurred while uploading|error while uploading|upload failed|could not upload|try again/i;
            for (const el of document.querySelectorAll('[role="alert"],[aria-live="assertive"],[class*="toast" i],[class*="messagebar" i]')) {
                if (!visible(el)) continue;
                const text=(el.innerText || el.textContent || '').trim();
                if (wanted.test(text)) return text.slice(0,500);
            }
            return '';
        }""")
        return str(value).strip() or None
    except PlaywrightError:
        return None


async def wait_for_stable_attachment_increment(page: Page, before_count: int, deadline: float) -> int:
    """Accept one assignment only after its increased chip count remains stable."""
    observed = before_count
    stable_since: Optional[float] = None
    while time.monotonic() < deadline:
        error = await upload_error_message(page)
        if error:
            raise FreshChatRequiredError(f"Copilot reported an upload error: {error}")
        current = await composer_attachment_count(page)
        if current > before_count:
            if current != observed:
                observed = current
                stable_since = time.monotonic()
            elif stable_since is not None and time.monotonic() - stable_since >= ATTACHMENT_CHIP_STABLE_SECONDS:
                return current
        else:
            observed = current
            stable_since = None
        await asyncio.sleep(FAST_ATTACH_POLL_SECONDS)
    return observed


async def _attach_file_recursive(
    page: Page,
    resolved: Path,
    deadline: float,
    depth: int = 1,
    last_error: Optional[BaseException] = None,
) -> None:
    """Use V30 CDP assignment exactly once; never over-upload after uncertainty."""
    del depth, last_error
    before_count = await composer_attachment_count(page)
    if before_count >= COPILOT_ATTACHMENT_LIMIT:
        raise RuntimeError(f"Composer already contains {before_count} attachments; blocked {resolved.name!r} to prevent attachment 21.")
    existing_error = await upload_error_message(page)
    if existing_error:
        raise FreshChatRequiredError(f"Existing Copilot upload error requires a fresh chat: {existing_error}")
    warning = await attachment_limit_warning(page)
    if warning:
        raise RuntimeError(f"Copilot attachment-limit warning before {resolved.name!r}: {warning}")
    assignment_uncertain = False
    try:
        await asyncio.wait_for(
            browser_local_set_input_files(page, resolved),
            timeout=FAST_ATTACH_ASSIGN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        assignment_uncertain = True
    except (PlaywrightError, RuntimeError) as exc:
        raise RuntimeError(f"Could not assign {resolved.name!r}: {exc}") from exc
    observed = await wait_for_stable_attachment_increment(
        page,
        before_count,
        min(deadline, time.monotonic() + ATTACHMENT_CONFIRM_DIAGNOSTIC_SECONDS),
    )
    if observed > before_count:
        return
    # Critical invariant: never assign the same planned position twice. A delayed
    # browser upload can still complete after the CDP call or its timeout.
    state = "timed out with uncertain outcome" if assignment_uncertain else "completed without a confirmed chip"
    raise RuntimeError(
        f"Attachment {resolved.name!r} assignment {state}; composer stayed at {before_count}. "
        "The file was NOT assigned again, preventing an accidental extra upload."
    )


async def attach_instructions_file(
    page: Page,
    instructions_path: Path,
    timeout_ms: int,
) -> None:
    """Attach one file using one browser-local CDP assignment and bounded observation."""
    resolved = instructions_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Required attachment was not found: {resolved}")
    if await attachment_is_visible(page, resolved.name):
        return

    allowed_seconds = max(1.0, timeout_ms / 1000)
    await _attach_file_recursive(
        page,
        resolved,
        time.monotonic() + allowed_seconds,
    )

def send_button_locators(page: Page) -> list[Locator]:
    """Return only controls explicitly identified as Send, never Stop generating."""
    safe_selector = (
        'button[aria-label="Send"], '
        'button[aria-label^="Send "]:not([aria-label*="stop" i]), '
        'button[type="submit"][aria-label*="send" i]:not([aria-label*="stop" i])'
    )
    return [
        page.locator(safe_selector),
        page.get_by_role("button", name=re.compile(r"^Send(?:\s|$)", re.IGNORECASE)),
    ]


async def stop_button_present(page: Page) -> bool:
    """Detect generation state. This control must never be clicked by send code."""
    try:
        return bool(await page.evaluate(r"""() => {
            const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            return [...document.querySelectorAll('button')].some(button => {
                const label=(button.getAttribute('aria-label') || '').trim().toLowerCase();
                return visible(button) && (label === 'stop generating' || label === 'stop' || label.startsWith('stop responding'));
            });
        }"""))
    except PlaywrightError:
        return False


async def stopped_generation_message_present(page: Page) -> bool:
    try:
        return bool(await page.evaluate(r"""() => {
            const text=(document.querySelector('[data-testid="lastChatMessage"]')?.innerText || document.body.innerText || '').toLowerCase();
            return text.includes("ok, i've stopped generating the response") || text.includes('stopped generating the response');
        }"""))
    except PlaywrightError:
        return False


async def click_regenerate_after_accidental_stop(page: Page) -> bool:
    """Recover only when the explicit stopped-response message is present."""
    if not await stopped_generation_message_present(page):
        return False
    button=await first_visible([
        page.get_by_role('button',name=re.compile(r'^Regenerate$',re.IGNORECASE)),
        page.locator('button').filter(has_text=re.compile(r'^Regenerate$',re.IGNORECASE)),
    ],timeout_ms=1000)
    if button is None:
        raise RuntimeError("Copilot reports that generation stopped, but Regenerate was not found.")
    await button.click(timeout=500,no_wait_after=True)
    print("Stopped response detected: Regenerate pressed safely.")
    return True


async def all_attachments_visible(page: Page, names: Sequence[str]) -> bool:
    """Confirm the complete plan by DOM count, including hidden overflow chips."""
    return await composer_attachment_count(page) >= len(names)

async def send_control_state(page: Page, file_names: Sequence[str]) -> tuple[bool, bool, Optional[Locator]]:
    attached, button = await asyncio.gather(all_attachments_visible(page, file_names), cached_first_visible(page,"send",send_button_locators(page),timeout_ms=0))
    enabled = False
    if button is not None:
        try:
            enabled = await button.is_enabled() and await button.get_attribute("aria-disabled") != "true" and await button.get_attribute("disabled") is None
        except PlaywrightError:
            pass
    return attached, enabled, button

async def attachment_transfer_snapshot(page: Page, expected_names: Sequence[str]) -> dict[str, Any]:
    """Read attachment presence plus live transfer indicators in one browser pass."""
    try:
        return dict(await page.evaluate(r"""names => {
            const visible=e=>!!(e&&(e.offsetWidth||e.offsetHeight||e.getClientRects().length));
            const norm=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
            const roots=new Set(); const texts=[];
            for(const selector of ['[aria-label="Attachments"] > [data-overflow-item="true"]','[aria-label="Attachments"] > div[id^="SPO_"]','button[aria-label^="Remove attachment "]']) {
              for(const element of document.querySelectorAll(selector)) {
                const root=element.matches('[data-overflow-item="true"],div[id^="SPO_"]')?element:(element.closest('[data-overflow-item="true"],div[id^="SPO_"]')||element);
                roots.add(root); texts.push(norm([root.innerText,root.textContent,root.getAttribute('aria-label'),root.getAttribute('title')].filter(Boolean).join(' ')));
              }
            }
            const transferRx=/uploading|processing|attaching|scanning|loading|preparing|transferring|pending|in progress/i;
            const spinnerSelectors=['[aria-busy="true"]','[role="progressbar"]','[data-testid*="progress" i]','[data-testid*="upload" i] [class*="spinner" i]','[class*="upload" i] [class*="spinner" i]','[class*="attachment" i] [class*="spinner" i]'];
            const active=[];
            for(const selector of spinnerSelectors) for(const element of document.querySelectorAll(selector)) if(visible(element)) active.push(selector+':'+norm(element.getAttribute('aria-label')||element.innerText||element.textContent).slice(0,120));
            roots.forEach(root=>{ const text=norm([root.innerText,root.textContent,root.getAttribute('aria-label'),root.getAttribute('title')].filter(Boolean).join(' ')); if(transferRx.test(text)) active.push('chip:'+text.slice(0,120)); });
            const send=[...document.querySelectorAll('button')].find(b=>{const label=norm(b.getAttribute('aria-label'));return visible(b)&&(label==='send'||label.startsWith('send '))&&!label.includes('stop');});
            const matched=names.filter(name=>texts.some(text=>text.includes(norm(name))));
            return {count:roots.size, matched, active:[...new Set(active)], sendEnabled:!!(send&&!send.disabled&&send.getAttribute('aria-disabled')!=='true')};
        }""",list(expected_names)))
    except (PlaywrightError,TypeError,ValueError):
        return {'count':0,'matched':[],'active':['snapshot-error'],'sendEnabled':False}

async def verify_transfer_dom_quiet(page: Page, names: Sequence[str], deadline: float) -> bool:
    """Require every chip and no visible per-file transfer activity."""
    stable_since: Optional[float]=None
    while time.monotonic()<deadline:
        if await upload_error_message(page): return False
        state=await attachment_transfer_snapshot(page,names)
        complete=int(state.get('count',0))>=len(names)
        quiet=not state.get('active')
        if complete and quiet:
            if stable_since is None: stable_since=time.monotonic()
            elif time.monotonic()-stable_since>=TRANSFER_QUIET_STABLE_SECONDS: return True
        else:
            stable_since=None
            await accelerate_upload_if_stalled(page, names, reason='dom-quiet verification')
        await asyncio.sleep(TRANSFER_ACTIVITY_POLL_SECONDS)
    return False

async def verify_transfer_send_gate(page: Page, names: Sequence[str], deadline: float) -> bool:
    """Independent confirmation: complete chips and a continuously enabled Send control."""
    stable_since: Optional[float]=None
    while time.monotonic()<deadline:
        if await upload_error_message(page): return False
        state=await attachment_transfer_snapshot(page,names)
        ready=int(state.get('count',0))>=len(names) and bool(state.get('sendEnabled')) and not state.get('active')
        if ready:
            if stable_since is None: stable_since=time.monotonic()
            elif time.monotonic()-stable_since>=TRANSFER_QUIET_STABLE_SECONDS: return True
        else:
            stable_since=None
            await accelerate_upload_if_stalled(page, names, reason='send-gate verification')
        await asyncio.sleep(TRANSFER_ACTIVITY_POLL_SECONDS)
    return False

async def recover_stalled_attachment_transfer(page: Page, names: Sequence[str], technique: str) -> bool:
    """Recover an existing transfer without adding the same local paths again."""
    started=time.monotonic()
    try:
        if technique=='native_try_again':
            success=await dismiss_or_retry_upload_error(page,len(names))
        elif technique=='renderer_wake':
            success=await background_wake_page(page)
        elif technique=='foreground_wake':
            await activate_page_like_manual_selection(page,0,'attachment transfer recovery',verbose=False); success=True
        elif technique=='input_change_nudge':
            success=bool(await page.evaluate(r"""() => { const input=[...document.querySelectorAll('input[type=file]')].pop(); if(!input)return false; input.dispatchEvent(new Event('change',{bubbles:true})); return true; }"""))
        else: success=False
    except (PlaywrightError,RuntimeError): success=False
    reward_technique('transfer_recovery',technique,success,time.monotonic()-started)
    return success

async def wait_until_attachments_upload_finished(page: Page, names: Sequence[str], timeout_ms: int) -> None:
    """Strongly prove all attachment data finished transferring before send.

    Chip count alone is never accepted. Fast independent verification routes are
    ranked by their observed reliability. Stalls trigger non-duplicating recovery
    techniques; the original files are never blindly assigned again.
    """
    overall_deadline=time.monotonic()+timeout_ms/1000
    verification={'dom_quiet':verify_transfer_dom_quiet,'send_gate':verify_transfer_send_gate}
    recovery=('native_try_again','renderer_wake','foreground_wake')
    last_state: dict[str,Any]={}
    for attempt in range(1,TRANSFER_RECOVERY_ATTEMPTS+1):
        for name in technique_rank('transfer_verify',tuple(verification)):
            started=time.monotonic()
            slice_deadline=min(overall_deadline,time.monotonic()+(TRANSFER_VERIFY_FAST_SECONDS if attempt==1 else TRANSFER_VERIFY_RECOVERY_SECONDS))
            ok=await verification[name](page,names,slice_deadline)
            reward_technique('transfer_verify',name,ok,time.monotonic()-started)
            if ok:
                print(f"  Attachment transfer complete: {len(names)}/{len(names)}; verifier={name}; adaptive={technique_summary('transfer_verify')}")
                return
        last_state=await attachment_transfer_snapshot(page,names)
        error=await upload_error_message(page)
        if error:
            recovered=await dismiss_or_retry_upload_error(page,len(names))
            if not recovered and attempt>=TRANSFER_RECOVERY_ATTEMPTS:
                raise FreshChatRequiredError(f"Attachment transfer failed after native retries: {error}")
        if time.monotonic()>=overall_deadline: break
        ranked=technique_rank('transfer_recovery',recovery)
        technique=ranked[(attempt-1)%len(ranked)]
        print(f"  Attachment transfer still active: chips={last_state.get('count',0)}/{len(names)}, indicators={len(last_state.get('active',[]))}; recovery {attempt}/{TRANSFER_RECOVERY_ATTEMPTS}={technique}")
        await recover_stalled_attachment_transfer(page,names,technique)
        await asyncio.sleep(0.12)
    last_state=await attachment_transfer_snapshot(page,names)
    raise FreshChatRequiredError(
        f"Attachments did not reach a fully transferred, quiet state after {TRANSFER_RECOVERY_ATTEMPTS} adaptive recovery attempts; "
        f"chips={last_state.get('count',0)}/{len(names)}, active indicators={last_state.get('active',[])[:5]}. Send and logging were blocked."
    )

async def editor_is_empty(page: Page) -> bool:
    editor=await cached_first_visible(page,"editor",editor_locators(page),timeout_ms=0)
    if editor is None: return False
    try: return not (await editor_text(editor)).strip()
    except PlaywrightError: return False

async def dom_click_enabled_send(page: Page) -> bool:
    """Click only a button whose live accessible label is Send."""
    try:
        return bool(await page.evaluate(r"""() => {
            const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            for (const button of document.querySelectorAll('button')) {
                const label=(button.getAttribute('aria-label') || '').trim().toLowerCase();
                const isSend = label === 'send' || label.startsWith('send ');
                const isStop = label.includes('stop') || button.querySelector('.fai-SendButton__stopBackground,.fai-SendButton__stopIcon');
                if (isSend && !isStop && visible(button) && !button.disabled && button.getAttribute('aria-disabled') !== 'true') {
                    button.click(); return true;
                }
            }
            return false;
        }"""))
    except PlaywrightError:
        return False


async def send_was_accepted(page: Page) -> bool:
    """Accept sending only when the live Send control becomes Stop generating."""
    return await stop_button_present(page)
async def _send_strategy_locator_click(page: Page, force: bool) -> bool:
    if await stop_button_present(page):
        return False
    button=await cached_first_visible(page,"send",send_button_locators(page),timeout_ms=120)
    if button is None:
        return False
    label=(await button.get_attribute("aria-label") or "").strip().casefold()
    if not (label == "send" or label.startswith("send ")) or "stop" in label:
        return False
    await button.click(timeout=250,force=force,no_wait_after=True)
    return True


async def _send_strategy_dom(page: Page) -> bool:
    return await dom_click_enabled_send(page)


async def _send_strategy_keyboard(page: Page, chord: str) -> bool:
    if await stop_button_present(page):
        return False
    editor=await cached_first_visible(page,"editor",editor_locators(page),timeout_ms=120)
    if editor is None:
        return False
    await editor.click(timeout=200,no_wait_after=True)
    await editor.press(chord,timeout=250)
    return True


async def _send_strategy_form(page: Page) -> bool:
    if await stop_button_present(page):
        return False
    try:
        return bool(await page.evaluate(r"""() => {
            const send=[...document.querySelectorAll('button')].find(b => {
                const label=(b.getAttribute('aria-label') || '').trim().toLowerCase();
                return (label === 'send' || label.startsWith('send ')) && !label.includes('stop');
            });
            if (!send) return false;
            const editor=document.querySelector('#m365-chat-editor-target-element,[data-testid*="chat-editor" i] [contenteditable="true"],[role="textbox"][contenteditable="true"]');
            const form=editor?.closest('form');
            if (!form) return false;
            if (typeof form.requestSubmit === 'function') { form.requestSubmit(); return true; }
            form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})); return true;
        }"""))
    except PlaywrightError:
        return False


async def parallel_send_round(page: Page) -> None:
    """Try independent send routes one at a time with a Stop-state gate before each."""
    strategies=[
        lambda:_send_strategy_locator_click(page,False),
        lambda:_send_strategy_dom(page),
        lambda:_send_strategy_locator_click(page,True),
        lambda:_send_strategy_keyboard(page,"Enter"),
        lambda:_send_strategy_keyboard(page,"Control+Enter"),
        lambda:_send_strategy_form(page),
    ]
    for strategy in strategies:
        if await send_was_accepted(page) or await stop_button_present(page):
            return
        try:
            await strategy()
        except (PlaywrightError,RuntimeError,asyncio.TimeoutError):
            pass
        # Allow immediate Send -> Stop transition to be observed before another route.
        for _ in range(6):
            if await send_was_accepted(page) or await stop_button_present(page):
                return
            await asyncio.sleep(SEND_STRATEGY_STAGGER_SECONDS)


async def send_and_confirm(page: Page, message: str, attachment_names: Sequence[str], timeout_ms: int) -> None:
    deadline=time.monotonic()+timeout_ms/1000
    rounds=0
    while time.monotonic() < deadline and rounds < SEND_PARALLEL_ROUNDS:
        if await strict_send_transaction_accepted(page,message):
            return
        upload_error=await upload_error_message(page)
        if upload_error:
            raise FreshChatRequiredError(f"Send blocked by upload error; fresh chat required: {upload_error}")
        if await stopped_generation_message_present(page):
            await click_regenerate_after_accidental_stop(page)
            return
        if await stop_button_present(page):
            return
        attached,enabled,_=await send_control_state(page,attachment_names)
        if not attached:
            raise RuntimeError("Send blocked because the complete attachment set is no longer present.")
        if not enabled:
            await activate_page_like_manual_selection(page,rounds+1,"send control wake")
            await asyncio.sleep(0.10)
            continue
        rounds+=1
        await parallel_send_round(page)
        observe_until=min(deadline,time.monotonic()+SEND_ROUND_OBSERVE_SECONDS)
        while time.monotonic() < observe_until:
            if await strict_send_transaction_accepted(page,message):
                return
            await asyncio.sleep(0.03)
    raise RuntimeError(f"Message was not accepted after {rounds} multi-strategy send rounds. Attachments remained protected and nothing was logged.")


async def message_prefix_outside_editor(page: Page, message: str) -> bool:
    """Check likely user-message containers only; never inspect broad main text."""
    prefix=re.sub(r"\s+"," ",message).strip()[:FINAL_SEND_VERIFY_PREFIX_LENGTH].casefold()
    if not prefix:
        return False
    try:
        return bool(await page.evaluate(r"""prefix => {
            const norm=value => String(value || '').replace(/\s+/g,' ').trim().toLowerCase();
            const editor=document.querySelector('#m365-chat-editor-target-element,[role="textbox"][contenteditable="true"]');
            const editorText=norm(editor?.innerText || editor?.textContent || '');
            if (editorText.includes(prefix)) return false;
            const selectors=[
                '[data-testid*="userChatMessage" i]',
                '[data-testid*="user-message" i]',
                '[data-testid*="chatMessage"] [data-author="user"]',
                '[role="article"][aria-label*="you" i]',
                '[role="article"][data-author="user"]'
            ];
            for (const selector of selectors) {
                for (const node of document.querySelectorAll(selector)) {
                    if (!editor?.contains(node) && norm(node.innerText || node.textContent).includes(prefix)) return true;
                }
            }
            return false;
        }""",prefix))
    except PlaywrightError:
        return False


async def strict_send_transaction_accepted(page: Page, message: str) -> bool:
    """The only reliable proof is the Send button becoming Stop generating."""
    del message
    return await stop_button_present(page)

async def final_verify_or_resend_fresh(
    page: Page,args: argparse.Namespace,batch: dict[str,Any],tab_number: int
) -> None:
    """Non-destructive post-send check. A sent/working tab is never reloaded."""
    del args, tab_number
    message=build_dynamic_message(batch["rows"],batch["category"],args,batch["counts"],batch["failed_total"],batch["paths"]) if False else ""
    # V11's accepted-send signals are authoritative: Stop/streaming, response
    # activity, or an empty composer. The optional external-prefix probe is only
    # affirmative evidence; its absence is never permission to navigate.
    if await stop_button_present(page) or await response_activity_detected(page):
        return
    if message and await message_prefix_outside_editor(page,message):
        return
    raise RuntimeError("Post-send verification still shows text in the composer and no response activity. The page was preserved without reload.")


def invalidate_page_ui_cache(page: Page) -> None:
    _PAGE_UI_CACHE.pop(id(page),None)


async def navigate_page(
    page: Page,
    url: str,
    semaphore: asyncio.Semaphore,
    page_timeout_ms: int,
) -> Optional[str]:
    """Start navigation with a hard short cap; live UI checks decide readiness."""
    async with semaphore:
        try:
            await page.goto(
                url,
                wait_until="commit",
                timeout=min(page_timeout_ms, FAST_NAVIGATION_TIMEOUT_MS),
            )
        except PlaywrightTimeoutError:
            return None
        except PlaywrightError as exc:
            return str(exc).strip().replace("\n", " ")
    return None

def concise_error(error: BaseException | str) -> str:
    text=str(error or "").strip()
    text=re.split(r"\n(?:Call log:|\s*\. Visible controls:)",text,maxsplit=1)[0]
    return re.sub(r"\s+"," ",text).strip()[:300]

async def retry_async(
    label: str,
    operation: Any,
    attempts: int = 5,
    delay_seconds: float = 0.08,
    verbose: bool = True,
) -> Any:
    """Retry a UI operation while retaining detailed diagnostics off-console."""
    last_error: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except (PlaywrightError, RuntimeError, FileNotFoundError) as exc:
            last_error = exc
            if attempt < attempts:
                await asyncio.sleep(min(delay_seconds, 0.08))
    if verbose:
        print(f"  {label}: {attempts} quick attempts failed ({concise_error(last_error or 'unknown error')}).")
    raise RuntimeError(f"{label} failed after {attempts} attempts: {concise_error(last_error or 'unknown error')}")

async def ensure_run_page(
    page: Page,
    args: argparse.Namespace,
    allow_login: bool,
) -> bool:
    """Probe readiness for at most six seconds, then defer to active-tab recovery."""
    del args
    deadline=time.monotonic()+TAB_ACTIVE_READY_SECONDS
    sign_in_seen=False
    checks=0
    while time.monotonic()<deadline and checks<FAST_UI_RECHECKS:
        checks+=1
        ready=await first_visible([*editor_locators(page),*model_switcher_locators(page)],timeout_ms=0)
        if ready is not None:
            return True
        if allow_login and checks%10==0:
            sign_in_seen=await page_looks_like_sign_in(page)
        await asyncio.sleep(FAST_UI_RECHECK_DELAY_SECONDS)
    if sign_in_seen:
        print("Microsoft 365 sign-in may still be required; deferring this tab to active recovery.")
    return False


async def recover_active_tab(page: Page,args: argparse.Namespace,tab_number: int,reason: str) -> None:
    """Bring a tab forward and use several bounded recovery actions."""
    last_error: Optional[BaseException]=None
    for attempt in range(1,TAB_OPERATION_ATTEMPTS+1):
        started=time.perf_counter()
        print(f"Tab {tab_number} recovery {attempt}/{TAB_OPERATION_ATTEMPTS}: {reason}")
        try:
            await page.bring_to_front()
            if attempt==2:
                await page.evaluate("() => window.focus()")
            elif attempt==3:
                try: await page.reload(wait_until='commit',timeout=TAB_RELOAD_TIMEOUT_MS)
                except PlaywrightTimeoutError: pass
            elif attempt==4:
                try: await page.goto(args.url,wait_until='commit',timeout=TAB_RELOAD_TIMEOUT_MS)
                except PlaywrightTimeoutError: pass
            elif attempt==5:
                try:
                    await page.evaluate("() => { window.stop(); location.reload(); }")
                except PlaywrightError:
                    pass
            ready=await ensure_run_page(page,args,False)
            if ready:
                print(f"Tab {tab_number} recovery {attempt} succeeded in {time.perf_counter()-started:.2f}s")
                return
            last_error=RuntimeError('Copilot controls still not detected after active six-second probe')
        except (PlaywrightError,RuntimeError) as exc:
            last_error=exc
        print(f"Tab {tab_number} recovery {attempt} did not complete in {time.perf_counter()-started:.2f}s")
    raise RuntimeError(f"Tab {tab_number} did not recover after {TAB_OPERATION_ATTEMPTS} active attempts: {last_error}")


async def run_tab_operation_with_recovery(page: Page,args: argparse.Namespace,tab_number: int,label: str,operation: Any) -> None:
    """Never abandon a tab after one failure; recover/reload and retry."""
    last_error: Optional[BaseException]=None
    for attempt in range(1,TAB_OPERATION_ATTEMPTS+1):
        try:
            await activate_page_like_manual_selection(page,tab_number,f"{label} active phase")
            quick_ready = await first_visible([*editor_locators(page),*model_switcher_locators(page)],timeout_ms=500)
            if quick_ready is None:
                await recover_active_tab(page,args,tab_number,f'{label} UI readiness')
            await operation()
            return
        except (PlaywrightError,RuntimeError,FileNotFoundError) as exc:
            last_error=exc
            print(f"Tab {tab_number} {label} attempt {attempt}/{TAB_OPERATION_ATTEMPTS} failed: {exc}",file=sys.stderr)
            if attempt<TAB_OPERATION_ATTEMPTS:
                await recover_active_tab(page,args,tab_number,f'{label} retry after failure')
    raise RuntimeError(f"Tab {tab_number} {label} failed after {TAB_OPERATION_ATTEMPTS} attempts: {last_error}")


def required_attachment_paths(args: argparse.Namespace, rows: Sequence[dict[str, str]]) -> list[Path]:
    paths = [args.instructions_path]
    paths.extend(path for row in rows for path in related_document_paths(row,args.merged_pdfs_root))
    if CASES_PER_TAB == 1 and len(rows) == 1:
        extras, _ = single_case_extra_attachment_paths(rows[0], args.case_files_root, args.merged_pdfs_root)
        paths.extend(extras)
    resolved = [path.expanduser().resolve() for path in paths]
    if len(resolved) > COPILOT_ATTACHMENT_LIMIT:
        raise RuntimeError(
            f"Internal attachment-plan error: {len(resolved)} files were selected; "
            f"the hard limit is {COPILOT_ATTACHMENT_LIMIT}. Nothing was attached."
        )
    # Duplicate names across different case folders are valid. Full paths and
    # change IDs preserve ownership; upload confirmation is count-based.
    return resolved

def is_protected_attachment_name(path: Path) -> bool:
    """Markdown instructions and merged PDF evidence always retain original names."""
    name=path.name
    return name.casefold().endswith('.md') or bool(re.search(r'_part_\d+\.pdf$',name,re.I))


def original_filename_component(path: Path) -> str:
    """Return the original_filename component after client_id and document_id."""
    stem=path.stem
    match=re.match(r'^[^_]+_[^_]+_(.+)$',stem)
    return match.group(1) if match else stem


def protected_additional_filename(path: Path) -> bool:
    """Preserve important Audit History and email filenames in every variation."""
    normalized=re.sub(r"[^a-z0-9]+", "", original_filename_component(path).casefold())
    return "audithistory" in normalized or "email" in normalized

def attachment_filename_length(path: Path) -> int:
    """Count every original-name character except underscores; exclude extension."""
    return len(original_filename_component(path).replace("_", ""))

def attachment_needs_short_name(path: Path) -> bool:
    """Shorten only unprotected additional names exceeding 15 non-underscore characters."""
    if is_protected_attachment_name(path) or protected_additional_filename(path):
        return False
    return attachment_filename_length(path) > 15


def staged_attachment_name(path: Path, position: int, duplicate: bool = False) -> str:
    """Preserve names unless a long additional filename requires a compact alias."""
    del duplicate
    if not attachment_needs_short_name(path):
        return path.name
    suffix=path.suffix.lower() or '.bin'
    return f"att_{position:02d}{suffix}"


def safe_alias_component(value: str, maximum: int = 24) -> str:
    """Create a readable filename component without losing identifier meaning."""
    cleaned=re.sub(r"[^A-Za-z0-9]+", "_", str(value or "")).strip("_")
    return cleaned[:maximum] or "file"

def path_case_identifier(path: Path) -> str:
    """Extract a stable case identifier from the source path when available."""
    for parent in path.parents:
        match=re.search(r"Change_(\d+)_Interested_Party_(\d+)",parent.name,re.I)
        if match:
            return f"C{match.group(1)}_IP{match.group(2)}"
    return ""

def source_document_identifiers(path: Path) -> tuple[str,str]:
    """Extract client_id and document_id from the standard filename structure."""
    match=re.match(r"^([^_]+)_([^_]+)_",path.stem)
    if match:
        return safe_alias_component(match.group(1),12),safe_alias_component(match.group(2),16)
    return "",""

def identifiable_collision_name(path: Path, position: int, used: set[str]) -> str:
    """Build a unique alias that identifies case, client, document and position."""
    suffix=path.suffix.lower() or '.bin'
    case_id=path_case_identifier(path)
    client_id,document_id=source_document_identifiers(path)
    original_hint=safe_alias_component(original_filename_component(path),18)
    components=[value for value in (case_id,client_id,document_id,original_hint,f"P{position:02d}") if value]
    proposed="_".join(components)+suffix
    counter=1
    while proposed.casefold() in used:
        counter+=1
        proposed="_".join(components+[f"N{counter}"])+suffix
    return proposed

def unique_staged_name(path: Path, position: int, used: set[str]) -> str:
    """Prevent collisions with meaningful independently identifiable aliases."""
    proposed=staged_attachment_name(path,position)
    key=proposed.casefold()
    if key not in used:
        used.add(key); return proposed
    proposed=identifiable_collision_name(path,position,used)
    used.add(proposed.casefold())
    return proposed


def prepare_duplicate_safe_paths(paths: Sequence[Path]) -> tuple[list[Path], Optional[Path]]:
    """Stage attachments selectively, preserving MD, merged PDFs and short originals."""
    resolved=[path.expanduser().resolve() for path in paths]
    stage=Path(tempfile.mkdtemp(prefix="copilot_case_attachments_"))
    staged=[]; used:set[str]=set()
    for position,path in enumerate(resolved,1):
        name=unique_staged_name(path,position,used)
        target=stage/name
        try:
            os.link(path,target)
        except OSError:
            shutil.copy2(path,target)
        staged.append(target.resolve())
    return staged,stage


def attachment_alias_mapping(paths: Sequence[Path], rows: Sequence[dict[str,str]]) -> str:
    """Map only renamed browser attachments and mandate original-name references."""
    case_keys=[((row.get('change_id') or '').strip(),exact_case_folder_name(row).casefold()) for row in rows]
    used:set[str]=set(); entries=[]
    for position,path in enumerate(paths,1):
        alias=unique_staged_name(path.expanduser().resolve(),position,used)
        normalized=str(path).casefold(); owner='shared instructions'
        for change_id,case_key in case_keys:
            if case_key in normalized:
                owner=f"change_id {change_id}"; break
        role=('mandatory methodology instructions' if path.name.casefold().endswith('.md')
              else 'merged PDF evidence part' if re.search(r'_part_\d+\.pdf$',path.name,re.I)
              else 'direct fallback/original attachment')
        if alias != path.name:
            entries.append(f'- browser alias "{alias}" -> ORIGINAL NAME "{path.name}" | owner: {owner} | role: {role}')
    lines=[
        'ATTACHMENT ORIGINAL-NAME CONTROL',
        'Markdown instructions, merged PDF parts, Audit History files, email files, and additional files whose original_filename component has 15 or fewer characters after excluding underscores retain their original filenames.',
        'Only longer additional files, or unavoidable same-name staging collisions, receive a browser alias. Collision aliases include available case, client, document, original-name hint, and attachment-position identifiers. They never use a generic dup label.',
        'In every analysis, citation, evidence reference, output filename discussion, and written report, ALWAYS use the ORIGINAL NAME. NEVER quote, cite, or present a browser alias as the document name.',
    ]
    if entries:
        lines.extend(['RENAMED ATTACHMENT MAPPING',*entries])
    else:
        lines.append('No attachment in this batch was renamed.')
    lines.extend([
        'MAPPING RULES',
        '- A browser alias and its ORIGINAL NAME identify the same attached file.',
        '- Two mappings with the same ORIGINAL NAME are still two independent attached files and may contain different evidence from different dates.',
        '- Analyze every mapped attachment separately. Never skip, merge, deduplicate, or treat one as already analyzed because another attachment has the same ORIGINAL NAME.',
        '- Resolve any browser alias silently, then refer only to the ORIGINAL NAME.',
        '- Analyze each attachment only under its mapped case.',
        '- Do not treat a filename or this mapping as evidence.',
    ])
    return '\n'.join(lines)

def cleanup_attachment_stage(stage: Optional[Path]) -> None:
    if stage is None:
        return
    try:
        shutil.rmtree(stage,ignore_errors=True)
    except OSError:
        pass


async def _attach_required_files_v30_engine(
    page: Page,
    paths: Sequence[Path],
    timeout_ms: int,
) -> None:
    """Attach the complete plan in one bulk selection, then recover without first-pass abandonment."""
    del timeout_ms
    if len(paths)>COPILOT_ATTACHMENT_LIMIT:
        raise RuntimeError(f"Refusing to attach {len(paths)} files; hard maximum is {COPILOT_ATTACHMENT_LIMIT}.")
    resolved=[path.expanduser().resolve() for path in paths]
    names=[path.name for path in resolved]
    initial=await attachment_validation_snapshot(page,names)
    initial_count=int(initial.get('count',0))
    if initial_count>len(resolved):
        raise RuntimeError(f"Composer contains {initial_count} attachments but this tab plans only {len(resolved)}; refusing to mix attachment sets.")
    if initial_count>=len(resolved):
        return
    if initial_count:
        print(f"  Composer already contains {initial_count}/{len(resolved)} attachment(s); completing safely.")
        # A previous uncertain bulk assignment may still be settling. Observe first,
        # and only fill missing positions after the grace window.
        state=await wait_for_bulk_attachment_confirmation(page,names,time.monotonic()+BULK_ATTACH_FAST_CONFIRM_SECONDS)
        if int(state.get('count',0))>=len(resolved):
            return
    else:
        print(f"  Bulk attaching {len(resolved)} files in one composer selection")
        assignment_error: Optional[BaseException]=None
        try:
            await asyncio.wait_for(browser_local_set_input_files_bulk(page,resolved),timeout=BULK_ATTACH_ASSIGN_TIMEOUT_SECONDS)
        except (asyncio.TimeoutError,PlaywrightError,RuntimeError) as exc:
            assignment_error=exc
        state=await wait_for_bulk_attachment_confirmation(page,names,time.monotonic()+BULK_ATTACH_FAST_CONFIRM_SECONDS)
        if int(state.get('count',0))>=len(resolved):
            print(f"  Bulk attachment confirmed: {len(resolved)}/{len(resolved)}")
            return
        # Do not declare a first-try failure or immediately assign the same list
        # again. A bulk CDP call can return before React renders all chips.
        state=await wait_for_bulk_attachment_confirmation(page,names,time.monotonic()+(HIGH_COUNT_BULK_GRACE_SECONDS if len(resolved)>HIGH_COUNT_ATTACHMENT_THRESHOLD else BULK_ATTACH_GRACE_CONFIRM_SECONDS))
        if int(state.get('count',0))>=len(resolved):
            print(f"  Bulk attachment confirmed after grace check: {len(resolved)}/{len(resolved)}")
            return
        if assignment_error is not None and int(state.get('count',0))==0:
            print(f"  Bulk assignment route did not start cleanly ({assignment_error}); using one safe recovery pass")
            # Zero stable composer evidence permits one fresh bulk attempt. This is
            # a new picker assignment, not a blind duplicate after partial upload.
            await ensure_attachment_input(page)
            await asyncio.wait_for(browser_local_set_input_files_bulk(page,resolved),timeout=BULK_ATTACH_ASSIGN_TIMEOUT_SECONDS)
            state=await wait_for_bulk_attachment_confirmation(page,names,time.monotonic()+(HIGH_COUNT_BULK_GRACE_SECONDS if len(resolved)>HIGH_COUNT_ATTACHMENT_THRESHOLD else BULK_ATTACH_GRACE_CONFIRM_SECONDS))
            if int(state.get('count',0))>=len(resolved):
                print(f"  Bulk recovery confirmed: {len(resolved)}/{len(resolved)}")
                return
    # A partial bulk result does not identify which exact paths failed. Copilot
    # reorders chips and can continue work asynchronously. Numeric-position refill
    # caused the duplicate original/alias chips shown in the diagnostics. Never
    # reassign individual paths after a partial bulk selection.
    current=await stable_attachment_count(page,1.0)
    if current>=len(resolved):
        recovered=await dismiss_or_retry_upload_error(page,len(resolved))
        if recovered and not await upload_error_message(page): return
    raise FreshChatRequiredError(f"Bulk selection stabilized at {current}/{len(resolved)} chips. Exact missing paths are unknowable, so no file was reassigned; a fresh-chat complete bulk retry is required.")

class CopilotUploadAccelerator:
    """Keep upload renderers active for both sequential and legacy flows.

    One persistent CDP session is retained per physical tab while files are being
    received by Copilot. This removes repeated session setup and avoids replaying
    file-input change events during normal transfer. The class never assigns files.
    """
    def __init__(self, pages: Sequence[Page], flow_name: str):
        self.pages = list(pages)
        self.flow_name = flow_name
        self.sessions: dict[int, Any] = {}
        self.stop_event = asyncio.Event()
        self.task: Optional[asyncio.Task[Any]] = None

    async def _open_session(self, page: Page) -> Optional[Any]:
        if page.is_closed():
            return None
        session = None
        try:
            session = await asyncio.wait_for(
                page.context.new_cdp_session(page),
                timeout=UPLOAD_ACCELERATOR_COMMAND_TIMEOUT_SECONDS,
            )
            await asyncio.wait_for(session.send('Page.enable'), UPLOAD_ACCELERATOR_COMMAND_TIMEOUT_SECONDS)
            await asyncio.wait_for(session.send('Runtime.enable'), UPLOAD_ACCELERATOR_COMMAND_TIMEOUT_SECONDS)
            await asyncio.wait_for(session.send('Network.enable', {
                'maxTotalBufferSize': 100000000,
                'maxResourceBufferSize': 50000000,
                'maxPostDataSize': 0,
            }), UPLOAD_ACCELERATOR_COMMAND_TIMEOUT_SECONDS)
            await asyncio.wait_for(
                session.send('Emulation.setFocusEmulationEnabled', {'enabled': True}),
                UPLOAD_ACCELERATOR_COMMAND_TIMEOUT_SECONDS,
            )
            await asyncio.wait_for(
                session.send('Page.setWebLifecycleState', {'state': 'active'}),
                UPLOAD_ACCELERATOR_COMMAND_TIMEOUT_SECONDS,
            )
            return session
        except (asyncio.TimeoutError, PlaywrightError):
            if session is not None:
                try: await session.detach()
                except PlaywrightError: pass
            return None

    async def start(self) -> None:
        for page in self.pages:
            session = await self._open_session(page)
            if session is not None:
                self.sessions[id(page)] = session
        self.task = asyncio.create_task(self._run())
        print(
            f"UPLOAD ACCELERATOR ({self.flow_name}): persistent renderer/network "
            f"activation armed for {len(self.sessions)}/{len(self.pages)} tab(s)"
        )

    async def replace_page(self, old_page: Page, new_page: Page) -> None:
        old = self.sessions.pop(id(old_page), None)
        if old is not None:
            try: await old.detach()
            except PlaywrightError: pass
        self.pages = [new_page if page is old_page else page for page in self.pages]
        session = await self._open_session(new_page)
        if session is not None:
            self.sessions[id(new_page)] = session

    async def pulse(self, page: Page, *, foreground: bool = False) -> list[str]:
        routes: list[str] = []
        session = self.sessions.get(id(page))
        if session is None:
            session = await self._open_session(page)
            if session is not None:
                self.sessions[id(page)] = session
        if session is not None:
            for method, params in (
                ('Page.setWebLifecycleState', {'state': 'active'}),
                ('Emulation.setFocusEmulationEnabled', {'enabled': True}),
                ('Runtime.evaluate', {
                    'expression': 'void(document.body && document.body.offsetHeight)',
                    'returnByValue': True,
                }),
            ):
                try:
                    await asyncio.wait_for(
                        session.send(method, params),
                        timeout=UPLOAD_ACCELERATOR_COMMAND_TIMEOUT_SECONDS,
                    )
                except (asyncio.TimeoutError, PlaywrightError):
                    continue
            routes.append('persistent-cdp')
        if foreground:
            try:
                await asyncio.wait_for(
                    page.bring_to_front(),
                    timeout=TAB_ACTIVATION_ROUTE_TIMEOUT_SECONDS,
                )
                routes.append('foreground')
            except (asyncio.TimeoutError, PlaywrightError):
                pass
        return routes

    async def _run(self) -> None:
        while not self.stop_event.is_set():
            for page in list(self.pages):
                if page.is_closed():
                    continue
                session = self.sessions.get(id(page))
                if session is None:
                    continue
                try:
                    await asyncio.wait_for(
                        session.send('Runtime.evaluate', {
                            'expression': 'void(document.body && document.body.offsetHeight)',
                            'returnByValue': True,
                        }),
                        timeout=UPLOAD_ACCELERATOR_COMMAND_TIMEOUT_SECONDS,
                    )
                except (asyncio.TimeoutError, PlaywrightError):
                    pass
            try:
                await asyncio.wait_for(
                    self.stop_event.wait(), timeout=UPLOAD_ACCELERATOR_PULSE_SECONDS
                )
            except asyncio.TimeoutError:
                pass

    async def close(self) -> None:
        self.stop_event.set()
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        for session in list(self.sessions.values()):
            try: await session.detach()
            except PlaywrightError: pass
        self.sessions.clear()
        print(f"UPLOAD ACCELERATOR ({self.flow_name}): persistent sessions released")


def update_upload_progress(page: Page, snapshot: dict[str, Any]) -> tuple[bool, float, bool]:
    """Track real UI transfer progress and return changed, stalled seconds, complete."""
    now = time.monotonic()
    signature = (
        int(snapshot.get('count', 0)),
        len(snapshot.get('active', [])),
        bool(snapshot.get('sendEnabled')),
    )
    key = id(page)
    state = _UPLOAD_PROGRESS_BY_PAGE.get(key)
    changed = state is None or signature != state.get('signature')
    if changed:
        _UPLOAD_PROGRESS_BY_PAGE[key] = {
            'signature': signature, 'changed_at': now, 'logged_at': 0.0
        }
        stalled = 0.0
    else:
        stalled = max(0.0, now - float(state.get('changed_at', now)))
    complete = bool(snapshot.get('sendEnabled')) and not snapshot.get('active')
    return changed, stalled, complete


async def accelerate_upload_if_stalled(
    page: Page,
    names: Sequence[str],
    *,
    tab_number: int = 0,
    reason: str = 'attachment transfer',
) -> dict[str, Any]:
    """Accelerate a measured stall without touching the FileList or duplicating files."""
    snapshot = await attachment_transfer_snapshot(page, names)
    changed, stalled, complete = update_upload_progress(page, snapshot)
    if complete or changed or stalled < UPLOAD_ACCELERATOR_STALL_SECONDS:
        return snapshot
    routes: list[str] = []
    error = await upload_error_message(page)
    if error and await dismiss_or_retry_upload_error(page, len(names)):
        routes.append('native-try-again')
    accelerator = _UPLOAD_ACCELERATOR
    if accelerator is not None:
        routes.extend(await accelerator.pulse(
            page, foreground=stalled >= UPLOAD_ACCELERATOR_FOREGROUND_STALL_SECONDS
        ))
    else:
        try:
            if await background_wake_page(page):
                routes.append('renderer-wake')
        except (PlaywrightError, RuntimeError):
            pass
    await asyncio.sleep(0.04)
    snapshot = await attachment_transfer_snapshot(page, names)
    update_upload_progress(page, snapshot)
    state = _UPLOAD_PROGRESS_BY_PAGE.get(id(page), {})
    now = time.monotonic()
    if tab_number and now - float(state.get('logged_at', 0.0)) >= UPLOAD_ACCELERATOR_LOG_SECONDS:
        state['logged_at'] = now
        print(
            f"UPLOAD ACCELERATION ({reason}): Tab {tab_number}; stalled={stalled:.2f}s; "
            f"chips={snapshot.get('count', 0)}/{len(names)}; "
            f"active={len(snapshot.get('active', []))}; "
            f"sendReady={'yes' if snapshot.get('sendEnabled') else 'no'}; "
            f"routes={','.join(routes) or 'persistent-session'}"
        )
    return snapshot


async def legacy_confirm_drop_started(
    page: Page,
    expected_names: Sequence[str],
    timeout_seconds: float,
    tab_number: int,
) -> dict[str, Any]:
    """Prove that Copilot accepted the Stage-1 file selection into its composer.

    This confirms chip creation only. It deliberately does not wait for transfer
    completion, quiet upload indicators, or Send readiness. A CDP assignment that
    returns successfully but leaves zero chips is not a successful drop.
    """
    deadline = time.monotonic() + max(0.25, timeout_seconds)
    best: dict[str, Any] = {'count': 0, 'matched': [], 'error': '', 'warning': ''}
    event_nudged = False
    while time.monotonic() < deadline:
        error = await upload_error_message(page)
        warning = await attachment_limit_warning(page)
        snapshot = await attachment_validation_snapshot(page, expected_names)
        snapshot['error'] = error or snapshot.get('error', '')
        snapshot['warning'] = warning or snapshot.get('warning', '')
        if int(snapshot.get('count', 0)) > int(best.get('count', 0)):
            best = snapshot
        if snapshot.get('warning'):
            raise RuntimeError(
                f"Legacy Stage-1 drop received an attachment-limit warning: {snapshot['warning']}"
            )
        if snapshot.get('error'):
            raise FreshChatRequiredError(
                f"Legacy Stage-1 drop received an upload error: {snapshot['error']}"
            )
        count = int(snapshot.get('count', 0))
        if count > 0:
            print(
                f"LEGACY DROP ACKNOWLEDGED: Tab {tab_number} displays {count}/"
                f"{len(expected_names)} attachment chip(s); transfer continues asynchronously"
            )
            return snapshot
        # Some Copilot builds need the normal input/change events after the CDP
        # FileList assignment. Dispatch them once, without assigning any path again.
        if not event_nudged:
            try:
                await page.evaluate(r"""() => {
                    const input = [...document.querySelectorAll('input[type=file]')].pop();
                    if (!input || !input.files || input.files.length === 0) return false;
                    input.dispatchEvent(new Event('input', {bubbles:true}));
                    input.dispatchEvent(new Event('change', {bubbles:true}));
                    return true;
                }""")
                event_nudged = True
            except PlaywrightError:
                pass
        await asyncio.sleep(LEGACY_DROP_START_POLL_SECONDS)
    return best


async def legacy_drop_attachment_plan(
    page: Page,
    paths: Sequence[Path],
    tab_number: int,
) -> tuple[str, ...]:
    """Bulk assign once, prove chip creation, then move on without transfer waiting.

    Stage 1 must distinguish a completed CDP command from a real Copilot drop. If
    the first assignment leaves zero chips, one clean retry is allowed because the
    composer contains no attachment evidence. Partial or complete chip evidence is
    never assigned again, preventing duplicates.
    """
    if len(paths) > COPILOT_ATTACHMENT_LIMIT:
        raise RuntimeError(
            f"Legacy drop refused {len(paths)} files; hard maximum is {COPILOT_ATTACHMENT_LIMIT}."
        )
    staged, stage = prepare_duplicate_safe_paths(paths)
    if stage is not None:
        _RETAINED_ATTACHMENT_STAGES.append(stage)
    names = tuple(path.name for path in staged)
    assignment_error: Optional[BaseException] = None
    try:
        await asyncio.wait_for(
            browser_local_set_input_files_bulk(page, staged),
            timeout=LEGACY_DROP_ASSIGN_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, PlaywrightError, RuntimeError) as exc:
        assignment_error = exc

    snapshot = await legacy_confirm_drop_started(
        page, names, LEGACY_DROP_START_CONFIRM_SECONDS, tab_number
    )
    count = int(snapshot.get('count', 0))
    if count == 0:
        # Zero chips means there is no partial plan to duplicate. Reopen/reacquire
        # the current file input and perform exactly one second bulk selection.
        print(
            f"LEGACY DROP ZERO-CHIP RETRY: Tab {tab_number} showed 0/{len(names)} "
            "chips after the first assignment; reacquiring the picker and retrying once",
            file=sys.stderr,
        )
        invalidate_page_ui_cache(page)
        try:
            await ensure_attachment_input(page)
            await asyncio.wait_for(
                browser_local_set_input_files_bulk(page, staged),
                timeout=LEGACY_DROP_ASSIGN_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, PlaywrightError, RuntimeError) as exc:
            assignment_error = exc
        snapshot = await legacy_confirm_drop_started(
            page, names, LEGACY_DROP_ZERO_RETRY_CONFIRM_SECONDS, tab_number
        )
        count = int(snapshot.get('count', 0))

    if count == 0:
        detail = concise_error(assignment_error or 'CDP assignment returned but Copilot created no chips')
        raise FreshChatRequiredError(
            f"Legacy Stage-1 bulk drop was not accepted by Copilot: 0/{len(names)} chips; {detail}"
        )

    _LEGACY_STAGED_NAMES_BY_PAGE[id(page)] = names
    _LEGACY_STAGED_PATHS_BY_PAGE[id(page)] = tuple(staged)
    print(
        f"LEGACY DROP: Tab {tab_number} genuinely accepted {count}/{len(staged)} "
        "attachment chip(s); remaining chip rendering/transfer continues asynchronously"
    )
    return names

async def legacy_force_attachment_transfer(
    page: Page,
    expected_names: Sequence[str],
    *,
    tab_number: int = 0,
    reason: str = "legacy attachment check",
) -> dict[str, Any]:
    """Use the shared stall-aware accelerator without reassigning attachments."""
    return await accelerate_upload_if_stalled(
        page, expected_names, tab_number=tab_number, reason=reason
    )

async def legacy_attachment_state(
    page: Page,
    expected_names: Sequence[str],
    *,
    force_transfer: bool = True,
    tab_number: int = 0,
    reason: str = "legacy attachment status",
) -> tuple[str, dict[str, Any]]:
    """Check status and actively drive incomplete legacy transfers forward."""
    error = await upload_error_message(page)
    snapshot = await attachment_transfer_snapshot(page, expected_names)
    snapshot['error'] = error or ''
    if error:
        # The force layer first tries Copilot's native retry. If the error remains,
        # stage 2/3 keeps its existing fresh-chat attachment recovery semantics.
        if force_transfer:
            snapshot = await legacy_force_attachment_transfer(
                page, expected_names, tab_number=tab_number, reason=reason
            )
            error = await upload_error_message(page)
            snapshot['error'] = error or ''
        if error:
            return 'error', snapshot
    count = int(snapshot.get('count', 0))
    complete = count >= len(expected_names)
    quiet = not snapshot.get('active')
    send_ready = bool(snapshot.get('sendEnabled'))
    if complete and quiet and send_ready:
        return 'ready', snapshot
    if force_transfer:
        snapshot = await legacy_force_attachment_transfer(
            page, expected_names, tab_number=tab_number, reason=reason
        )
        snapshot['error'] = (await upload_error_message(page)) or ''
        if snapshot['error']:
            return 'error', snapshot
        complete = int(snapshot.get('count', 0)) >= len(expected_names)
        quiet = not snapshot.get('active')
        send_ready = bool(snapshot.get('sendEnabled'))
        if complete and quiet and send_ready:
            return 'ready', snapshot
    return 'loading', snapshot


async def legacy_prepare_model_and_message(
    page: Page,
    batch: dict[str, Any],
    args: argparse.Namespace,
) -> str:
    """Idempotently select the model and place the exact base/case message."""
    message = build_dynamic_message(
        batch['rows'], batch['category'], args, batch['counts'],
        batch['failed_total'], batch['paths'],
    )
    await select_model_with_opus_fallback(page, batch['model'])
    editor = await cached_first_visible(page, 'editor', editor_locators(page), 500)
    existing = await editor_text(editor) if editor is not None else ''
    if message not in existing:
        await retry_async(
            'Legacy message insertion',
            lambda: add_text_to_editor(page, message, FAST_MESSAGE_TIMEOUT_MS),
            attempts=5,
            delay_seconds=0.015,
        )
    return message


async def legacy_composer_is_prepared(page: Page, message: str, model_name: str) -> bool:
    """Check the live DOM so a fresh-chat reset cannot leave a stale prepared flag."""
    if not message:
        return False
    try:
        editor = await cached_first_visible(page, 'editor', editor_locators(page), timeout_ms=250)
        if editor is None:
            return False
        current = await asyncio.wait_for(
            editor_text(editor), timeout=LEGACY_IMMEDIATE_SEND_PROBE_TIMEOUT_SECONDS
        )
        if message not in current:
            return False
        return await asyncio.wait_for(
            model_is_selected(page, effective_model_name(model_name)),
            timeout=LEGACY_IMMEDIATE_SEND_PROBE_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, PlaywrightError, RuntimeError):
        return False


async def legacy_recover_attachment_failure(
    page: Page,
    batch: dict[str, Any],
    args: argparse.Namespace,
    tab_number: int,
) -> tuple[str, ...]:
    """Recover only attachments, advancing to the next established attachment route."""
    current = attachment_route_for_page(page)
    record_failed_attachment_route(page, current)
    next_route = next_unused_attachment_route(page)
    if next_route is None:
        raise FreshChatRequiredError(
            f"Legacy attachment recovery exhausted after route {current}."
        )
    await reset_tab_to_fresh_chat(
        page, args, tab_number, f"legacy attachment route {current} failure"
    )
    _ATTACHMENT_ROUTE_BY_PAGE[id(page)] = next_route
    staged, stage = prepare_duplicate_safe_paths(batch['paths'])
    if stage is not None:
        _RETAINED_ATTACHMENT_STAGES.append(stage)
    names = tuple(path.name for path in staged)
    if next_route == 'bulk_cdp':
        await browser_local_set_input_files_bulk(page, staged)
    elif next_route == 'sequential_cdp':
        deadline = time.monotonic() + FAST_TAB_ATTACH_DEADLINE_SECONDS
        for path in staged:
            await _attach_file_recursive(
                page, path,
                min(deadline, time.monotonic() + FAST_SINGLE_FILE_DEADLINE_SECONDS),
            )
    else:
        raise RuntimeError(f"Unsupported legacy recovery route: {next_route}")
    _LEGACY_STAGED_NAMES_BY_PAGE[id(page)] = names
    _LEGACY_STAGED_PATHS_BY_PAGE[id(page)] = tuple(staged)
    print(
        f"LEGACY ATTACHMENT FALLBACK: Tab {tab_number} switched "
        f"{current} -> {next_route}; model/message phase may continue while loading"
    )
    return names


async def legacy_send_ready_tab(
    page: Page,
    batch: dict[str, Any],
    args: argparse.Namespace,
    tab_number: int,
    total_tabs: int,
    names: Sequence[str],
    message: str,
) -> None:
    """Send one already prepared legacy tab after a non-blocking ready check."""
    await retry_async(
        'Legacy Send and confirmation',
        lambda: send_and_confirm(
            page, message, names, SINGLE_CASE_SEND_TIMEOUT_MS
        ),
        attempts=3,
        delay_seconds=0.10,
    )
    if not await stop_button_present(page):
        raise RuntimeError('Legacy send was not confirmed by Stop generating.')
    for row in batch['rows']:
        append_fully_sent_log(args.log_path, row)
    print(
        f"{TERMINAL_WHITE_ON_YELLOW} LEGACY MESSAGE SENT: Tab {tab_number}/{total_tabs}; "
        "attachments ready, model/message prepared, Stop generating confirmed "
        f"{TERMINAL_STYLE_RESET}"
    )


async def legacy_send_if_ready_now(
    page: Page,
    batch: dict[str, Any],
    args: argparse.Namespace,
    tab_number: int,
    total_tabs: int,
    names: Sequence[str],
    message: str,
) -> tuple[bool, dict[str, Any]]:
    """Immediately send one fully prepared legacy tab during any checking sweep.

    This is deliberately local to the tab currently being inspected. It never
    waits for other tabs and never creates a separate send-all phase. The exact
    expected message must still be present, every expected attachment must be
    quiet/complete, and the Send control must be enabled before dispatch.
    """
    snapshot: dict[str, Any] = {}
    try:
        state, snapshot = await asyncio.wait_for(
            legacy_attachment_state(
                page,
                names,
                tab_number=tab_number,
                reason='legacy immediate-send check',
            ),
            timeout=max(
                LEGACY_IMMEDIATE_SEND_PROBE_TIMEOUT_SECONDS,
                LEGACY_FORCE_TRANSFER_ROUTE_TIMEOUT_SECONDS * 6,
            ),
        )
    except (asyncio.TimeoutError, PlaywrightError):
        return False, snapshot
    if state != 'ready':
        return False, snapshot
    editor = await cached_first_visible(page, 'editor', editor_locators(page), 180)
    if editor is None:
        return False, snapshot
    try:
        current_text = await asyncio.wait_for(
            editor_text(editor),
            timeout=LEGACY_IMMEDIATE_SEND_PROBE_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, PlaywrightError):
        return False, snapshot
    if message not in current_text:
        return False, snapshot
    await legacy_send_ready_tab(
        page, batch, args, tab_number, total_tabs, names, message
    )
    print(
        f"LEGACY IMMEDIATE DISPATCH: Tab {tab_number}/{total_tabs} was fully ready "
        "during the attachment sweep and was sent without waiting for any other tab"
    )
    return True, snapshot


async def attach_required_files(
    page: Page,
    paths: Sequence[Path],
    timeout_ms: int,
    *,
    wait_for_transfer: bool = True,
) -> None:
    staged,stage=prepare_duplicate_safe_paths(paths)
    if stage is not None:
        # Edge may continue reading the local file after the chip appears. Keep
        # aliases alive until the complete run has finished sending.
        _RETAINED_ATTACHMENT_STAGES.append(stage)
    route=attachment_route_for_page(page)
    print(f"  V18 attachment route: {route}")
    if route == "bulk_cdp":
        await _attach_required_files_v30_engine(page,staged,timeout_ms)
    elif route == "sequential_cdp":
        deadline=time.monotonic()+max(FAST_TAB_ATTACH_DEADLINE_SECONDS,timeout_ms/1000)
        for path in staged:
            if await upload_error_message(page):
                raise FreshChatRequiredError("Upload alert detected before sequential CDP assignment.")
            await _attach_file_recursive(page,path,min(deadline,time.monotonic()+FAST_SINGLE_FILE_DEADLINE_SECONDS))
    elif route == "playwright_bulk":
        oversized=[path for path in staged if path.stat().st_size>50*1024*1024]
        if oversized: raise RuntimeError(f"Playwright bulk incompatible with {len(oversized)} file(s) over 50 MB; CDP route required")
        names=[path.name for path in staged]
        before=await composer_attachment_count(page)
        if before:
            raise RuntimeError(f"Playwright bulk route requires an empty fresh composer; found {before} attachment(s).")
        await playwright_local_set_input_files_bulk(page,staged)
        state=await wait_for_bulk_attachment_confirmation(page,names,time.monotonic()+BULK_ATTACH_GRACE_CONFIRM_SECONDS)
        if int(state.get("count",0)) < len(staged):
            raise RuntimeError(f"Playwright bulk route confirmed {state.get('count',0)}/{len(staged)} attachments.")
    else:
        raise RuntimeError(f"Unknown V18 attachment route: {route}")
    # Normal callers keep the original strong transfer proof. The foreground
    # sending pipeline may defer only this final wait so it can select the model
    # and insert the base message while the already-added files continue loading.
    if wait_for_transfer:
        await wait_until_attachments_upload_finished(page,[path.name for path in staged],min(SINGLE_CASE_UPLOAD_FINISH_TIMEOUT_MS,max(30_000,timeout_ms*8)))


async def attach_run_page(page: Page, args: argparse.Namespace, rows: Sequence[dict[str,str]], number: int, total: int) -> None:
    paths=required_attachment_paths(args,rows)
    await attach_required_files(page,paths,args.page_timeout*1000)
    print(f"Attachments {number}/{total}: confirmed ({len(paths)} files)")

async def finish_run_page(page: Page, args: argparse.Namespace, rows: Sequence[dict[str,str]], number: int, total: int) -> None:
    paths=required_attachment_paths(args,rows); names=[p.name for p in paths]
    if not await all_attachments_visible(page,names):
        await attach_required_files(page,paths,args.page_timeout*1000)
    message=build_message(rows,args.case_files_root,args.merged_pdfs_root)
    await retry_async("Message insertion",lambda:add_text_to_editor(page,message,FAST_MESSAGE_TIMEOUT_MS),attempts=5,delay_seconds=0.015)
    async def model():
        await click_model_option(page, args.small_model, FAST_MODEL_TIMEOUT_MS)
    await retry_async("Exact model selection",model,attempts=5,delay_seconds=0.015)
    many_attachments = CASES_PER_TAB == 1 and len(paths) > 2
    upload_timeout_ms = (
        SINGLE_CASE_UPLOAD_FINISH_TIMEOUT_MS if many_attachments else FAST_SEND_TIMEOUT_MS
    )
    send_timeout_ms = (
        SINGLE_CASE_SEND_TIMEOUT_MS if many_attachments else FAST_SEND_TIMEOUT_MS
    )
    await wait_until_attachments_upload_finished(page,names,upload_timeout_ms)
    async def send():
        if not await editor_is_empty(page): await send_and_confirm(page,message,names,send_timeout_ms)
    await retry_async("Send and confirmation",send,attempts=10,delay_seconds=0.015)
    for row in rows: append_fully_sent_log(args.log_path,row)
    print(f"Send {number}/{total}: confirmed with all attachments and logged")

async def prepare_tab(
    page: Page,
    tab_number: int,
    total_tabs: int,
    args: argparse.Namespace,
    rows: Sequence[dict[str, str]],
    allow_interactive_login: bool,
    verbose: bool = True,
) -> None:
    """Prepare and send one tab containing up to three strictly isolated cases."""
    timeout_ms = (args.login_timeout if allow_interactive_login else args.page_timeout) * 1000

    async def recover_page() -> None:
        # navigate_page has already loaded this tab. Inspect the live SPA first
        # and reload only when the expected controls genuinely fail to appear.
        try:
            await wait_for_copilot_ui(
                page, min(timeout_ms, 700), allow_interactive_login
            )
            return
        except RuntimeError:
            pass
        try:
            await page.reload(wait_until="domcontentloaded", timeout=args.page_timeout * 1000)
        except PlaywrightTimeoutError:
            pass
        await wait_for_copilot_ui(page, timeout_ms, allow_interactive_login)

    await retry_async("Copilot UI readiness", recover_page, attempts=2, delay_seconds=0.08, verbose=verbose)

    async def select_model() -> None:
        await click_model_option(page, args.small_model, args.page_timeout * 1000, verbose=verbose)

    await select_model()
    message = build_message(rows, args.case_files_root, args.merged_pdfs_root)
    await retry_async(
        "Message insertion",
        lambda: add_text_to_editor(page, message, args.page_timeout * 1000),
        attempts=5,
        delay_seconds=0.08,
        verbose=verbose,
    )
    await retry_async(
        "Attachment",
        lambda: attach_required_files(page, required_attachment_paths(args, rows), args.page_timeout * 1000),
        attempts=5,
        delay_seconds=0.12,
        verbose=verbose,
    )

    async def send_once() -> None:
        if await editor_is_empty(page):
            return
        await send_and_confirm(page, message, [p.name for p in required_attachment_paths(args, rows)], args.page_timeout * 1000)

    await retry_async("Send and confirmation", send_once, attempts=5, delay_seconds=0.10, verbose=verbose)
    for row in rows:
        append_fully_sent_log(args.log_path, row)
    ids = ", ".join(row["change_id"] for row in rows)
    print(
        f"Tab {tab_number}/{total_tabs}: {len(rows)} cases [{ids}] "
        "fully sent, confirmed, and logged"
    )

def is_blank_or_new_tab_url(url: str) -> bool:
    """Identify only browser-generated blank and new-tab pages."""
    normalized = (url or "").strip().lower().rstrip("/")
    return normalized in {
        "", "about:blank", "edge://newtab", "edge://new-tab-page",
        "chrome://newtab", "chrome://new-tab-page",
    }


async def close_blank_or_new_tabs(
    context: BrowserContext,
    pages_to_keep: Sequence[Page] = (),
) -> int:
    """Close blank/new-tab pages only; never close Copilot or content tabs."""
    keep_ids = {id(page) for page in pages_to_keep}
    closed = 0
    for page in list(context.pages):
        if id(page) in keep_ids or not is_blank_or_new_tab_url(page.url):
            continue
        try:
            await page.close()
            closed += 1
        except PlaywrightError:
            continue
    return closed


async def close_launch_placeholders(
    context: BrowserContext,
    pages_to_keep: Sequence[Page],
) -> None:
    await close_blank_or_new_tabs(context, pages_to_keep)


async def acquire_run_page(
    context: BrowserContext,
    claimed_page_ids: set[int],
    attempts: int = 4,
    verbose: bool = True,
) -> Page:
    """Reuse an unclaimed blank target, or create a new tab with retries."""
    for candidate in list(context.pages):
        if id(candidate) in claimed_page_ids or candidate.is_closed():
            continue
        if is_blank_or_new_tab_url(candidate.url):
            claimed_page_ids.add(id(candidate))
            if verbose:
                print("  Reusing one existing blank/new-tab page for this run.")
            return candidate
    last_error: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            page = await context.new_page()
            claimed_page_ids.add(id(page))
            return page
        except PlaywrightError as exc:
            last_error = exc
            if verbose:
                print(f"  New page creation attempt {attempt}/{attempts} failed: {str(exc).strip()}")
            if attempt < attempts:
                await asyncio.sleep(1.5 * attempt)
    raise RuntimeError(f"Could not create a new Edge tab after {attempts} attempts: {last_error}")


def is_copilot_chat_url(url: str) -> bool:
    """Match the manually prepared Microsoft 365 Copilot Chat route.

    URL recognition is deliberately authoritative at startup. The Copilot landing
    page may render welcome cards using the same message containers as an existing
    conversation, so counting message-like DOM nodes creates false negatives.
    """
    value = (url or "").strip().lower()
    try:
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and parsed.netloc == "m365.cloud.microsoft"
            and parsed.path.rstrip("/") == "/chat"
        )
    except Exception:
        return value.rstrip("/").startswith(DEFAULT_COPILOT_URL.lower().rstrip("/"))


def register_prepared_copilot_page(page: Page) -> None:
    """Record startup provenance so later phases never navigate this page."""
    _PREPARED_COPILOT_PAGE_IDS.add(id(page))


def page_was_prepared_copilot(page: Page) -> bool:
    """Return the immutable startup classification for this physical page."""
    return id(page) in _PREPARED_COPILOT_PAGE_IDS


async def observed_page_url(page: Page) -> str:
    """Read a page URL from Playwright, then independently from its CDP target.

    During a heavy 25-tab attach, Playwright can briefly expose about:blank for one
    already loaded target. The browser target URL is used as an independent source
    without navigating, foregrounding, or waiting for UI controls.
    """
    direct = str(page.url or "").strip()
    if is_copilot_chat_url(direct):
        return direct
    session = None
    try:
        session = await page.context.new_cdp_session(page)
        info = await asyncio.wait_for(
            session.send("Target.getTargetInfo"),
            timeout=0.40,
        )
        target_url = str(info.get("targetInfo", {}).get("url", "")).strip()
        return target_url or direct
    except (asyncio.TimeoutError, PlaywrightError):
        return direct
    finally:
        if session is not None:
            try:
                await session.detach()
            except PlaywrightError:
                pass


async def classify_prepared_copilot_cohort(
    candidates: Sequence[Page],
    required_count: int,
) -> tuple[list[Page], list[Page]]:
    """Classify a complete manually prepared cohort without a readiness wave.

    Exact Copilot URLs are authoritative. If exactly one page in an otherwise
    complete requested cohort is transiently reported as blank, its URL is sampled
    again through Playwright/CDP. If it remains unresolved, it is conservatively
    promoted as the final member of the prepared cohort rather than being
    destructively navigated. This applies only when all requested pages already
    exist and every other page is confirmed as Copilot Chat.
    """
    live = [page for page in candidates if not page.is_closed()]
    urls = [await observed_page_url(page) for page in live]
    for _ in range(PREPARED_COHORT_URL_RECHECKS - 1):
        unresolved = [i for i, url in enumerate(urls) if not is_copilot_chat_url(url)]
        if not unresolved:
            break
        if len(unresolved) > PREPARED_COHORT_MAX_UNRESOLVED_PAGES:
            break
        await asyncio.sleep(PREPARED_COHORT_URL_RECHECK_DELAY_SECONDS)
        for index in unresolved:
            urls[index] = await observed_page_url(live[index])
    confirmed = [page for page, url in zip(live, urls) if is_copilot_chat_url(url)]
    unresolved = [page for page, url in zip(live, urls) if not is_copilot_chat_url(url)]
    complete_exact_cohort = (
        len(live) == required_count
        and len(confirmed) >= required_count - PREPARED_COHORT_MAX_UNRESOLVED_PAGES
        and len(unresolved) <= PREPARED_COHORT_MAX_UNRESOLVED_PAGES
    )
    prepared = list(live) if complete_exact_cohort else confirmed
    for page in prepared:
        register_prepared_copilot_page(page)
    if complete_exact_cohort and unresolved:
        print(
            f"PRELOADED COHORT RECOVERY: promoted {len(unresolved)} transiently blank/stale "
            f"target after {len(confirmed)}/{required_count} independent Copilot URL confirmations; "
            "no navigation or shared readiness wait will run"
        )
    return prepared, ([] if complete_exact_cohort else unresolved)


async def preloaded_copilot_tab_is_ready(page: Page) -> bool:
    """Single-page compatibility check using independent URL observation only."""
    if page.is_closed() or not is_copilot_chat_url(await observed_page_url(page)):
        return False
    register_prepared_copilot_page(page)
    return True


def partition_startup_pages(pages: Sequence[Page]) -> tuple[list[Page], list[Page]]:
    """Split selected pages by immutable acquisition provenance."""
    prepared = [page for page in pages if page_was_prepared_copilot(page)]
    unprepared = [page for page in pages if not page_was_prepared_copilot(page)]
    return prepared, unprepared

async def acquire_run_pages_fast(
    browser: Browser,
    context: BrowserContext,
    count: int,
) -> list[Page]:
    """Acquire exactly count usable tabs without leaking unclaimed CDP targets.

    Existing blank tabs are reused first. Every CDP-created target ID is tracked
    explicitly and resolved to its matching Playwright Page. A target that does
    not materialize is closed before a fallback page is created, preventing the
    orphan blank tabs observed when previous Copilot runs are still open.
    Existing non-blank Copilot tabs are never reused, navigated, or closed.
    """
    started = time.perf_counter()
    print(f"Creating {count} Copilot tab(s)...")
    selected: list[Page] = []
    selected_ids: set[int] = set()

    def add_page(page: Page, message: str) -> bool:
        if page.is_closed() or id(page) in selected_ids or len(selected) >= count:
            return False
        selected.append(page)
        selected_ids.add(id(page))
        del message
        return True

    # Classify the whole existing cohort before treating any transient about:blank
    # value as a genuinely blank tab. This prevents a 24/25 false negative.
    existing_live = [page for page in list(context.pages) if not page.is_closed()]
    prepared_cohort, unresolved_existing = await classify_prepared_copilot_cohort(
        existing_live, count
    )
    for page in prepared_cohort:
        add_page(page, "reused prepared Copilot Chat cohort tab")
        if len(selected) == count:
            print(
                f"PRELOADED COPILOT MODE: {count}/{count} existing targets retained as "
                "the prepared cohort; navigation and the initial six-second wake wave are skipped"
            )
            for selected_page, batch in zip(selected, _RUN_BATCHES):
                _RUN_ROWS[id(selected_page)] = batch["rows"]
            return selected
    # Only pages not belonging to a prepared cohort can be reused as true blanks.
    for page in unresolved_existing:
        if is_blank_or_new_tab_url(await observed_page_url(page)):
            add_page(page, "reused existing blank tab")
            if len(selected) == count:
                print(f"Tabs ready in {time.perf_counter() - started:.2f}s")
                for selected_page, batch in zip(selected, _RUN_BATCHES):
                    _RUN_ROWS[id(selected_page)] = batch["rows"]
                return selected
    missing = count - len(selected)
    created_target_ids: list[str] = []
    resolved_target_ids: set[str] = set()
    browser_session = None

    try:
        browser_session = await browser.new_browser_cdp_session()
        for number in range(1, missing + 1):
            one_started = time.perf_counter()
            result = await asyncio.wait_for(
                browser_session.send("Target.createTarget", {"url": "about:blank"}),
                timeout=TARGET_CREATE_TIMEOUT_SECONDS,
            )
            target_id = str(result.get("targetId", ""))
            if not target_id:
                raise RuntimeError("Target.createTarget returned no targetId")
            created_target_ids.append(target_id)

        discovery_deadline = time.monotonic() + TARGET_DISCOVERY_TIMEOUT_SECONDS
        while time.monotonic() < discovery_deadline and len(selected) < count:
            # Query the browser target list once per pass so association is based
            # on exact targetId, not page ordering or Python object timing.
            target_info = await browser_session.send("Target.getTargets")
            wanted_urls = {
                str(item.get("targetId")): str(item.get("url", ""))
                for item in target_info.get("targetInfos", [])
                if str(item.get("targetId")) in created_target_ids
            }
            for page in list(context.pages):
                if page.is_closed() or id(page) in selected_ids:
                    continue
                page_target_id = ""
                page_session = None
                try:
                    page_session = await context.new_cdp_session(page)
                    info = await page_session.send("Target.getTargetInfo")
                    page_target_id = str(info.get("targetInfo", {}).get("targetId", ""))
                except PlaywrightError:
                    continue
                finally:
                    if page_session is not None:
                        try:
                            await page_session.detach()
                        except PlaywrightError:
                            pass
                if page_target_id not in created_target_ids:
                    continue
                if not is_blank_or_new_tab_url(wanted_urls.get(page_target_id, page.url)):
                    continue
                if add_page(page, f"claimed exact CDP target {page_target_id[-8:]}"):
                    resolved_target_ids.add(page_target_id)
                    if len(selected) == count:
                        break
            if len(selected) < count:
                await asyncio.sleep(0.025)

        # Close only CDP targets created by this invocation that were not claimed.
        # This is the key orphan-tab fix. Existing tabs and claimed run pages are
        # never included in this cleanup.
        unresolved = [
            target_id for target_id in created_target_ids
            if target_id not in resolved_target_ids
        ]
        for target_id in unresolved:
            try:
                await browser_session.send("Target.closeTarget", {"targetId": target_id})
            except PlaywrightError as exc:
                print(
                    f"PHASE 1/3 cleanup warning for target {target_id[-8:]}: {exc}",
                    file=sys.stderr,
                )

    except (PlaywrightError, asyncio.TimeoutError, RuntimeError) as exc:
        print(f"PHASE 1/3 exact CDP acquisition fallback: {exc}", file=sys.stderr)
        if browser_session is not None:
            for target_id in created_target_ids:
                if target_id in resolved_target_ids:
                    continue
                try:
                    await browser_session.send(
                        "Target.closeTarget", {"targetId": target_id}
                    )
                except PlaywrightError:
                    pass
    finally:
        if browser_session is not None:
            try:
                await browser_session.detach()
            except PlaywrightError:
                pass

    # After orphan cleanup, create only the exact number still required.
    # Refuse a dead-context fallback so the caller receives the real CDP error
    # instead of unhandled Future/TargetClosedError noise.
    try:
        context_live = bool(browser.is_connected() and context.pages is not None)
    except PlaywrightError:
        context_live = False
    if len(selected) < count and not context_live:
        raise RuntimeError("V30 exact target acquisition lost the CDP connection; existing tabs were preserved. Re-run to reconnect cleanly.")
    while len(selected) < count:
        one_started = time.perf_counter()
        page = await asyncio.wait_for(
            context.new_page(), timeout=TARGET_FALLBACK_TIMEOUT_SECONDS
        )
        add_page(page, "fallback")
        print(f"Fallback created tab {len(selected)}/{count} in {time.perf_counter()-one_started:.2f}s")

    # Final invariant check. Extra blank pages created by this invocation cannot
    # survive because unresolved target IDs were closed before fallback.
    if len(selected) != count or len({id(page) for page in selected}) != count:
        raise RuntimeError(
            f"Tab acquisition invariant failed: expected {count} unique pages, "
            f"received {len(selected)}."
        )

    print(
        f"PHASE 1/3 page acquisition complete in "
        f"{time.perf_counter() - started:.2f}s"
    )
    for page, batch in zip(selected, _RUN_BATCHES):
        _RUN_ROWS[id(page)] = batch["rows"]
    return selected

async def response_activity_detected(page: Page) -> bool:
    """Detect visible signs that Copilot accepted and is processing/responding."""
    try:
        return bool(await page.evaluate(r"""() => {
            const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const selectors = [
                'button[aria-label="Stop"]',
                'button[aria-label*="Stop responding" i]',
                '[data-testid*="streaming" i]',
                '[data-test-id*="streaming" i]',
                '[aria-busy="true"]'
            ];
            return selectors.some(selector => [...document.querySelectorAll(selector)].some(visible));
        }"""))
    except PlaywrightError:
        return False

async def _bounded_activation_route(
    label: str,
    awaitable: Any,
    timeout_seconds: float = TAB_ACTIVATION_ROUTE_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Own and bound one activation route without allowing cancellation to stall."""
    task = asyncio.ensure_future(awaitable)
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=max(0.05, timeout_seconds))
        return True, label
    except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError) as exc:
        if not task.done():
            task.cancel()
        _consume_background_task(task)
        return False, f"{label}:{concise_error(exc)}"


async def activate_page_like_manual_selection(
    page: Page,
    tab_number: int,
    reason: str,
    verbose: bool = True,
) -> None:
    """Best-effort multi-route activation with a hard overall deadline.

    Activation is an optimisation, not a prerequisite for queue progression. Each
    Playwright/CDP route is independently bounded and the whole function returns
    quickly even when one target stops answering while browser-level CDP remains
    healthy. No reload or navigation is performed here.
    """
    if page.is_closed():
        raise RuntimeError(f"Tab {tab_number} is closed during {reason}")
    started = time.monotonic()
    successes: list[str] = []
    failures: list[str] = []
    session = None
    ok, detail = await _bounded_activation_route("playwright-front", page.bring_to_front())
    (successes if ok else failures).append(detail)
    try:
        session_task = asyncio.ensure_future(page.context.new_cdp_session(page))
        try:
            session = await asyncio.wait_for(
                asyncio.shield(session_task), TAB_ACTIVATION_ROUTE_TIMEOUT_SECONDS
            )
        except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError) as exc:
            if not session_task.done():
                session_task.cancel()
            _consume_background_task(session_task)
            failures.append(f"cdp-session:{concise_error(exc)}")
        if session is not None:
            for method, params in (
                ("Page.bringToFront", {}),
                ("Emulation.setFocusEmulationEnabled", {"enabled": True}),
                ("Page.setWebLifecycleState", {"state": "active"}),
            ):
                if time.monotonic() - started >= TAB_ACTIVATION_TOTAL_TIMEOUT_SECONDS:
                    break
                ok, detail = await _bounded_activation_route(
                    method,
                    session.send(method, params),
                )
                (successes if ok else failures).append(detail)
        if time.monotonic() - started < TAB_ACTIVATION_TOTAL_TIMEOUT_SECONDS:
            ok, detail = await _bounded_activation_route(
                "renderer-focus",
                page.evaluate(r"""() => {
                    try { window.focus(); } catch (_) {}
                    document.dispatchEvent(new Event('visibilitychange'));
                    window.dispatchEvent(new Event('focus'));
                    return true;
                }"""),
            )
            (successes if ok else failures).append(detail)
    finally:
        if session is not None:
            detach_task = asyncio.ensure_future(session.detach())
            try:
                await asyncio.wait_for(
                    asyncio.shield(detach_task), TAB_ACTIVATION_ROUTE_TIMEOUT_SECONDS
                )
            except (asyncio.TimeoutError, PlaywrightError):
                if not detach_task.done():
                    detach_task.cancel()
                _consume_background_task(detach_task)
    elapsed = time.monotonic() - started
    if verbose:
        if successes:
            print(
                f"Tab {tab_number}: actively foregrounded for {reason} in {elapsed:.2f}s "
                f"via {','.join(successes)}"
            )
        else:
            print(
                f"TAB ACTIVATION WATCHDOG: Tab {tab_number} did not acknowledge foreground "
                f"activation within {elapsed:.2f}s during {reason}; continuing with direct UI "
                f"probe; routes={'; '.join(failures) or 'no response'}",
                file=sys.stderr,
            )


async def ensure_tab_start_progress(
    page: Page,
    args: argparse.Namespace,
    tab_number: int,
    reason: str,
) -> None:
    """Quickly prove the tab can answer UI probes, then repair it locally if not."""
    for attempt in range(1, TAB_START_RECOVERY_ATTEMPTS + 1):
        try:
            await asyncio.wait_for(
                activate_page_like_manual_selection(
                    page, tab_number, reason, verbose=True
                ),
                timeout=TAB_ACTIVATION_TOTAL_TIMEOUT_SECONDS + 0.75,
            )
            ready = await asyncio.wait_for(
                first_visible(
                    [*editor_locators(page), *model_switcher_locators(page)],
                    timeout_ms=350,
                ),
                timeout=TAB_START_PROGRESS_TIMEOUT_SECONDS,
            )
            if ready is not None:
                if attempt > 1:
                    print(f"TAB START RECOVERY: Tab {tab_number} resumed on attempt {attempt}")
                return
        except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError, RuntimeError) as exc:
            detail = concise_error(exc) or type(exc).__name__
            print(
                f"TAB START WATCHDOG: Tab {tab_number} attempt {attempt}/"
                f"{TAB_START_RECOVERY_ATTEMPTS} stalled during {reason}: {detail}",
                file=sys.stderr,
            )
        invalidate_page_ui_cache(page)
        if attempt < TAB_START_RECOVERY_ATTEMPTS:
            try:
                await asyncio.wait_for(
                    background_wake_page(page),
                    timeout=TAB_ACTIVATION_TOTAL_TIMEOUT_SECONDS,
                )
            except (asyncio.TimeoutError, PlaywrightError):
                pass
            await asyncio.sleep(0.05)
    raise TabStartFreshChatRequiredError(
        f"Tab {tab_number} remained unresponsive after {TAB_START_RECOVERY_ATTEMPTS} "
        "bounded activation/UI checks; immediate fresh-target replacement is required."
    )

async def fast_post_send_handoff(page: Page, tab_number: int) -> bool:
    """Best-effort next-tab activation that can never block queue progression.

    Each Playwright/CDP route is separately bounded. A slow target, CDP session
    creation, Page.bringToFront call, evaluation, or detach is abandoned without
    affecting the already confirmed send or preventing the next tab from starting.
    """
    if page.is_closed():
        print(f"POST-SEND HANDOFF: Tab {tab_number} is closed; queue continues without waiting", file=sys.stderr)
        return False
    session = None
    started = time.monotonic()
    success = False
    try:
        try:
            await asyncio.wait_for(
                page.bring_to_front(), POST_SEND_HANDOFF_ROUTE_TIMEOUT_SECONDS
            )
            success = True
        except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError):
            pass
        try:
            session = await asyncio.wait_for(
                page.context.new_cdp_session(page),
                POST_SEND_HANDOFF_ROUTE_TIMEOUT_SECONDS,
            )
            await asyncio.wait_for(
                session.send("Page.bringToFront"),
                POST_SEND_HANDOFF_ROUTE_TIMEOUT_SECONDS,
            )
            success = True
        except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError):
            pass
        try:
            await asyncio.wait_for(
                page.evaluate("() => { try { window.focus(); } catch (_) {} }"),
                POST_SEND_HANDOFF_ROUTE_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError):
            pass
    finally:
        if session is not None:
            try:
                await asyncio.wait_for(
                    session.detach(), POST_SEND_HANDOFF_ROUTE_TIMEOUT_SECONDS
                )
            except (asyncio.TimeoutError, PlaywrightError):
                pass
    elapsed = time.monotonic() - started
    print(
        f"POST-SEND HANDOFF: Tab {tab_number} "
        f"{'activated' if success else 'activation inconclusive'} in {elapsed:.2f}s; "
        "queue progression is not blocked"
    )
    return success


async def commit_confirmed_send_state(
    page: Page,
    physical_slot: int,
    batch: dict[str, Any],
    args: argparse.Namespace,
    sent: set[int],
    wake_pages: list[Page],
    baseline_title: str,
) -> TabAssignmentState:
    """Durably record a confirmed send before any optional UI handoff work."""
    for row in batch["rows"]:
        await asyncio.wait_for(
            asyncio.to_thread(append_fully_sent_log, args.log_path, row),
            timeout=POST_SEND_COMMIT_TIMEOUT_SECONDS,
        )
    sent.add(physical_slot)
    if page not in wake_pages:
        wake_pages.append(page)
    return _new_assignment(page, physical_slot, batch["rows"], baseline_title)


async def accelerate_sent_copilot_tabs(pages: Sequence[Page], sent_indexes: set[int]) -> None:
    """Cycle sent tabs as real foreground tabs so server responses start promptly.

    No page is reloaded, no cookies/site data are cleared, and no signed-in
    profile files are removed. This preserves every submitted analysis.
    """
    pending={index for index in sent_indexes if index < len(pages) and not pages[index].is_closed()}
    if not pending:
        return
    print(f"POST-SEND ACCELERATOR: actively waking {len(pending)} sent Copilot tab(s)")
    for round_number in range(1,POST_SEND_ACTIVATION_ROUNDS+1):
        if not pending:
            break
        print(f"POST-SEND ACCELERATOR round {round_number}/{POST_SEND_ACTIVATION_ROUNDS}: {len(pending)} tab(s) to foreground")
        for index in sorted(tuple(pending)):
            page=pages[index]
            await activate_page_like_manual_selection(page,index+1,'response acceleration')
            deadline=time.monotonic()+POST_SEND_RESPONSE_PROBE_SECONDS
            while time.monotonic()<deadline:
                if await response_activity_detected(page):
                    print(f"Tab {index+1}: Copilot response activity detected")
                    pending.discard(index)
                    break
                await asyncio.sleep(0.10)
            if index in pending:
                await asyncio.sleep(POST_SEND_ACTIVE_DWELL_SECONDS)
    # One final foreground pass wakes any page whose response indicator is not
    # exposed by this Copilot UI build. Leave the last pending tab active.
    for index in sorted(pending):
        await activate_page_like_manual_selection(pages[index],index+1,'final wake pass')
        await asyncio.sleep(POST_SEND_ACTIVE_DWELL_SECONDS)
    print(f"POST-SEND ACCELERATOR complete: {len(sent_indexes)-len(pending)} activity-confirmed; {len(pending)} foreground-woken without reload")

def batch_bounds(change_id: int) -> tuple[int, int]:
    low = ((change_id - 1) // 100) * 100 + 1
    return low, low + 99


def source_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        missing = [name for name in REQUIRED_COLUMNS if name not in fields]
        if missing:
            raise RuntimeError("Source CSV is missing required columns: " + ", ".join(missing))
        return [{name: (raw.get(name) or "") for name in fields} for raw in reader]


def category_for_count(count: int) -> str:
    if count <= 10:
        return "Small"
    if count < 50:
        return "Medium"
    return "Large"


def norm_path(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.expanduser().resolve())))


def read_merge_status_for_batch(low: int, high: int, root: Path) -> dict[str, dict[str, Any]]:
    status_path = resolve_merge_status_json(low, high, root)
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read merge-status JSON {status_path}: {exc}") from exc
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise RuntimeError(f"Merge-status JSON has no valid results list: {status_path}")
    return {
        str(item.get("case", "")).strip().casefold(): item
        for item in results if isinstance(item, dict) and str(item.get("case", "")).strip()
    }


def build_or_load_case_size_csv(args: argparse.Namespace, low: int, high: int) -> tuple[Path, list[dict[str, str]]]:
    output=args.case_size_output_root.expanduser().resolve()/f"Case_sizes_batch_{low}_{high}.csv"
    if output.is_file():
        with output.open("r",encoding="utf-8-sig",newline="") as handle: rows=list(csv.DictReader(handle))
        if rows and {"related_document_count","related_documents"}.issubset(rows[0]):
            print(f"CASE SIZE FILE USED: {output}"); print(f"CASE SIZE FILE MODE: existing multi-part analysis loaded ({len(rows)} rows)"); return output,rows
        print("CASE SIZE FILE MODE: legacy analysis detected; rebuilding")
    batch_rows=[r for r in source_rows(args.csv_path) if low<=numeric_change_id(r)<=high]
    status=read_merge_status_for_batch(low,high,args.merged_pdfs_root)
    def analyze(row: dict[str,str]) -> dict[str,str]:
        files=usable_local_case_files(row,args.case_files_root,args.merged_pdfs_root); case=exact_case_folder_name(row); item=status.get(case.casefold(),{})
        raw_failed=item.get("failed_files",[]) if isinstance(item,dict) else []; raw_paths=item.get("failed_file_paths",[]) if isinstance(item,dict) else []
        if not isinstance(raw_failed,list): raw_failed=[]
        if not isinstance(raw_paths,list): raw_paths=[]
        failed=case_failed_file_paths(row,args.case_files_root,args.merged_pdfs_root)
        pdfs=related_document_paths(row,args.merged_pdfs_root); pc=len(pdfs)
        original=category_for_count(len(files)); pdf_category="Small" if pc==1 else "Medium" if pc==2 else "Large"
        rank={"Small":0,"Medium":1,"Large":2}; category=max((original,pdf_category),key=rank.__getitem__)
        return {"change_id":(row.get("change_id") or "").strip(),"InterestedPartyId":(row.get("InterestedPartyId") or "").strip(),"case":case,
            "case_folder":str(args.case_files_root.expanduser().resolve()/case),"file_count":str(len(files)),"related_document_count":str(pc),"case_size":category,
            "merged_pdf":str(pdfs[0]),"related_documents":json.dumps([str(x) for x in pdfs],ensure_ascii=False),
            "failed_file_count":str(max(len(raw_failed),len(raw_paths),len(failed))),"failed_files":json.dumps(raw_failed,ensure_ascii=False),
            "failed_file_paths":json.dumps(raw_paths,ensure_ascii=False),"resolved_failed_file_paths":json.dumps([str(x) for x in failed],ensure_ascii=False),"batch_failed_case_count":"0"}
    workers=min(max(1,args.analysis_workers),max(1,len(batch_rows))); print(f"INITIAL ANALYSIS: {len(batch_rows)} case(s) using {workers} worker(s)")
    ordered=[None]*len(batch_rows); failures=[]
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix="case-analysis") as pool:
        futures={pool.submit(analyze,row):(i,row) for i,row in enumerate(batch_rows)}
        done=0
        for future in as_completed(futures):
            i,row=futures[future]
            try: ordered[i]=future.result()
            except BaseException as exc: failures.append((i,exact_case_folder_name(row),exc))
            done+=1
            if done==len(batch_rows) or done%10==0: print(f"INITIAL ANALYSIS: {done}/{len(batch_rows)} completed")
    if failures:
        failures.sort(); details=" | ".join(f"{case}: {type(exc).__name__}: {exc}" for _,case,exc in failures)
        raise RuntimeError(f"Initial analysis failed for {len(failures)} case(s); no partial CSV written. {details}")
    analyzed=[x for x in ordered if x is not None]; failed_cases=sum(int(x["failed_file_count"])>0 for x in analyzed)
    for x in analyzed: x["batch_failed_case_count"]=str(failed_cases)
    output.parent.mkdir(parents=True,exist_ok=True)
    fields=list(analyzed[0]) if analyzed else ["change_id","InterestedPartyId","case","case_folder","file_count","related_document_count","case_size","merged_pdf","related_documents","failed_file_count","failed_files","failed_file_paths","resolved_failed_file_paths","batch_failed_case_count"]
    temp=output.with_suffix(output.suffix+".tmp")
    with temp.open("w",encoding="utf-8-sig",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,lineterminator="\n"); writer.writeheader(); writer.writerows(analyzed); handle.flush(); os.fsync(handle.fileno())
    os.replace(temp,output); print(f"CASE SIZE FILE USED: {output}"); print(f"CASE SIZE FILE MODE: parallel analysis created ({len(analyzed)} rows; {failed_cases} failed-merge cases)")
    return output,analyzed

def select_run_rows(args: argparse.Namespace) -> tuple[Path, list[dict[str, str]], dict[str, dict[str, str]]]:
    # Filter exact source/log keys before every count, range, plan, batch or queue.
    candidates = eligible_source_rows(args)
    print(f"ELIGIBLE RERUNNABLE CASES: {len(candidates)}")
    if not candidates:
        return Path(), [], {}
    low, high = batch_bounds(numeric_change_id(candidates[0]))
    size_path, size_rows = build_or_load_case_size_csv(args, low, high)
    size_map = {canonical_change_id(item.get("change_id", "")): item for item in size_rows}
    available = [row for row in candidates if low <= numeric_change_id(row) <= high and canonical_change_id(row.get("change_id", "")) in size_map]
    by = {"Small": [], "Medium": [], "Large": []}
    for row in available:
        category = size_map[canonical_change_id(row.get("change_id", ""))].get("case_size", "")
        if category in by:
            by[category].append(row)
    selected: list[dict[str, str]] = []
    # Reserve one slot for a Large case whenever one is available, then maximize
    # Small throughput, followed by Medium and any remaining Large cases.
    if by["Large"] and args.cases >= 1:
        selected.append(by["Large"].pop(0))
    remaining = max(0, args.cases - len(selected))
    for category in ("Small", "Medium", "Large"):
        take = min(remaining, len(by[category]))
        selected.extend(by[category][:take])
        remaining -= take
        if not remaining:
            break
    # Put Small batches first while retaining the reserved Large case in the run.
    selected.sort(key=lambda row: ({"Small": 0, "Medium": 1, "Large": 2}[size_map[canonical_change_id(row.get("change_id", ""))]["case_size"]], numeric_change_id(row)))
    return size_path, selected, size_map

def sorted_case_sources(row: dict[str, str], args: argparse.Namespace) -> tuple[list[Path], list[Path]]:
    files = usable_local_case_files(row, args.case_files_root, args.merged_pdfs_root)
    failed = case_failed_file_paths(row, args.case_files_root, args.merged_pdfs_root)
    failed_keys = {norm_path(p) for p in failed}
    failed_sorted = sorted(failed, key=lambda p: (-p.stat().st_size, p.name.casefold(), p.name))
    others = sorted((p for p in files if norm_path(p) not in failed_keys), key=lambda p: (-p.stat().st_size, p.name.casefold(), p.name))
    return failed_sorted, others


def mandatory_count(rows: Sequence[dict[str, str]], args: argparse.Namespace) -> int:
    return 1 + sum(len(related_document_paths(row,args.merged_pdfs_root)) for row in rows) + sum(len(sorted_case_sources(row,args)[0]) for row in rows)


def pack_category(rows: list[dict[str, str]], category: str, args: argparse.Namespace) -> list[list[dict[str, str]]]:
    maximum = {"Small": 5, "Medium": 3, "Large": 1}[category]
    preferred = 2 if category == "Medium" else maximum
    groups: list[list[dict[str, str]]] = []
    pending = list(rows)
    while pending:
        take = min(preferred, len(pending), maximum)
        if category == "Medium" and len(pending) == 3:
            take = 3
        while take > 0 and mandatory_count(pending[:take], args) > COPILOT_ATTACHMENT_LIMIT:
            take -= 1
        if take < 1:
            raise RuntimeError(f"{category} case {pending[0].get('change_id')} has too many mandatory failed-file attachments for one tab.")
        groups.append(pending[:take]); del pending[:take]
    return groups


def attachment_plan(rows: Sequence[dict[str, str]], category: str, args: argparse.Namespace) -> tuple[list[Path], dict[str, int], int]:
    row_ids=tuple(canonical_change_id(row.get("change_id","")) for row in rows)
    cache_key=(row_ids,category,str(args.instructions_path.expanduser().resolve()),str(args.case_files_root.expanduser().resolve()),str(args.merged_pdfs_root.expanduser().resolve()))
    cached=_ATTACHMENT_PLAN_CACHE.get(cache_key)
    if cached is not None:
        paths,counts,failed_total=cached
        return list(paths),dict(counts),failed_total

    selected: list[Path] = [args.instructions_path.expanduser().resolve()]
    selected.extend(path for row in rows for path in related_document_paths(row,args.merged_pdfs_root))
    per_case: dict[str, list[Path]] = {}
    failed_total = 0
    for row in rows:
        failed, others = sorted_case_sources(row, args)
        failed_total += len(failed)
        per_case[(row.get("change_id") or "").strip()] = list(failed)
        selected.extend(failed)
        per_case[(row.get("change_id") or "").strip() + "__remaining"] = others
    if len(selected) > COPILOT_ATTACHMENT_LIMIT:
        raise RuntimeError("Mandatory instructions, merged PDFs and failed files exceed the 20-attachment limit.")
    remaining_slots = COPILOT_ATTACHMENT_LIMIT - len(selected)
    if category == "Medium":
        for row in rows:
            key=(row.get("change_id") or "").strip(); candidates=per_case[key+"__remaining"][:5]
            take=min(len(candidates), remaining_slots)
            per_case[key].extend(candidates[:take]); selected.extend(candidates[:take]); remaining_slots-=take
        if remaining_slots:
            leftovers=[]
            for row in rows:
                key=(row.get("change_id") or "").strip()
                picked={norm_path(p) for p in per_case[key]}
                leftovers.extend(p for p in per_case[key+"__remaining"] if norm_path(p) not in picked)
            if leftovers:
                extra=max(leftovers,key=lambda p:(p.stat().st_size,p.name.casefold()))
                selected.append(extra)
                for row in rows:
                    key=(row.get("change_id") or "").strip()
                    if extra in per_case[key+"__remaining"]: per_case[key].append(extra); break
    else:
        while remaining_slots:
            progressed=False
            for row in rows:
                key=(row.get("change_id") or "").strip()
                picked={norm_path(p) for p in per_case[key]}
                candidate=next((p for p in per_case[key+"__remaining"] if norm_path(p) not in picked),None)
                if candidate is not None:
                    per_case[key].append(candidate); selected.append(candidate); remaining_slots-=1; progressed=True
                    if not remaining_slots: break
            if not progressed: break
    # Identical or similar filenames across cases are expected and retained.
    # Unique full paths and change_id ownership keep the evidence case-specific.
    counts={(row.get("change_id") or "").strip():len(per_case[(row.get("change_id") or "").strip()]) for row in rows}
    _ATTACHMENT_PLAN_CACHE[cache_key]=(tuple(selected),dict(counts),failed_total)
    return list(selected),dict(counts),failed_total


def build_dynamic_message(rows: Sequence[dict[str, str]], category: str, args: argparse.Namespace, counts: dict[str, int], failed_total: int, planned_paths: Optional[Sequence[Path]] = None) -> str:
    count=len(rows)
    category_intro={
        "Small":"This tab contains a compact multi-case batch. Complete every case independently.",
        "Medium":"This tab contains medium-sized cases. Use the merged PDFs as primary evidence and the selected direct files as prioritized fallback context.",
        "Medium+Small":"This tab contains medium-sized case(s) plus one complete Small case added to use spare attachment capacity. The complete Small case includes its merged PDF and every original file. Analyze every case independently and never mix their evidence.",
        "Large":"This tab contains one very large case. Take the time required, increase the available search and reasoning budget, and finish the task in this single-shot message without asking for follow-up input.",
    }[category]
    direct_lines="\n".join(f"- change_id {(row.get('change_id') or '').strip()}: {counts.get((row.get('change_id') or '').strip(),0)} directly attached original/fallback file(s)" for row in rows)
    names=[local_case_file_names(row,args.case_files_root,args.merged_pdfs_root) for row in rows]
    blocks="\n\n".join(format_case_block(row,i,count,names[i-1]) for i,row in enumerate(rows,1))
    manifest="\n".join(f"- Case {i}: change_id {display_value(row.get('change_id',''))} | InterestedPartyId {display_value(row.get('InterestedPartyId',''))} | merged PDF parts: {', '.join(p.name for p in related_document_paths(row,args.merged_pdfs_root))}" for i,row in enumerate(rows,1))
    ordered_ids = "\n".join(f"- {(row.get('change_id') or '').strip()}" for row in rows)
    response_contract = (
        "\n\nMANDATORY FINAL PLAIN-TEXT AUDIT RESULT\n"
        "Finish with the exact result lines below. The result may follow required workbook links or case details, but no further text may follow the result lines.\n"
        "The first result line must be exactly either:\nAll files for all cases were exposed: Yes\nor\nAll files for all cases were exposed: No\n"
        "Then include exactly one line for every submitted change ID in the ordered list below, using:\nCase result: <CHANGE_ID> | <STATUS>\n"
        "The only permitted statuses are successful and failed. If the overall result is Yes, every case must be successful. If it is No, identify every successful and failed case.\n"
        "ORDERED SUBMITTED CHANGE IDS\n" + ordered_ids
    )
    exact_paths=list(planned_paths) if planned_paths is not None else attachment_plan(rows,category,args)[0]
    alias_section="\n\n"+attachment_alias_mapping(exact_paths,rows)
    original_name_rule="\n\nORIGINAL DOCUMENT NAME RULE: If the browser displays a shortened alias, resolve it using the mapping and use only the original long filename in every response, citation, evidence reference, and generated output. Never write the shortened alias as a document name. Multiple attachments may share the same original filename but come from different dates or contain different evidence. Analyze every mapped attachment independently and never exclude one as a duplicate merely because its original filename matches another."
    return BASE_MESSAGE+response_contract+alias_section+original_name_rule+"\n\nMERGED PDF PART RULE: For each case, every PDF named in its CASE MANIFEST is part of one continuous evidence set. Analyze all parts in numeric order and omit none.\n"+f"\n{category.upper()} CASES BATCH\n{category_intro}\n- Cases sent: {count}\n- Direct fallback failed-merge files sent: {failed_total}. These are valid case-specific fallback evidence and count towards the exposure count when readable.\n- Different cases may contain attachments with identical or similar filenames. This is intentional. Associate every attachment only with its listed change_id and InterestedPartyId, and never combine evidence merely because filenames match.\n{direct_lines}\n- Required output: {count} separate completed downloadable review file(s), one per case.\n\nCASE MANIFEST\n{manifest}\n\nCASE DATA\n\n{blocks}"


def complete_small_addon_cost(row: dict[str, str], args: argparse.Namespace) -> int:
    """One merged PDF plus every original file for a complete Small add-on case."""
    return len(related_document_paths(row,args.merged_pdfs_root)) + len(usable_local_case_files(row,args.case_files_root,args.merged_pdfs_root))


def add_complete_small_to_medium_batch(
    batch: dict[str, Any],
    small_row: dict[str, str],
    args: argparse.Namespace,
) -> bool:
    """Add a Small case only when its merged PDF and every original file fit."""
    complete_files=usable_local_case_files(small_row,args.case_files_root,args.merged_pdfs_root)
    addition=[*related_document_paths(small_row,args.merged_pdfs_root),*complete_files]
    if len(batch["paths"])+len(addition)>COPILOT_ATTACHMENT_LIMIT:
        return False
    batch["rows"].append(small_row)
    batch["paths"].extend(addition)
    change_id=(small_row.get("change_id") or "").strip()
    batch["counts"][change_id]=len(complete_files)
    batch["category"]="Medium+Small"
    batch["model"]=effective_model_name(args.medium_model)
    batch["complete_small_addon_ids"]=[change_id]
    return True


def retry_batch_signature(batch: dict[str, Any]) -> tuple[str, ...]:
    return tuple(canonical_change_id((row.get("change_id") or "").strip()) for row in batch["rows"])


def enqueue_retry_batch(
    batch: dict[str, Any],
    reason: str,
    args: Optional[argparse.Namespace] = None,
) -> bool:
    """Queue failed work in the same global FIFO as every other workload.

    When runtime arguments are available, rebuild the retry immediately so the
    established final-attempt generation rules are applied before any free tab
    claims it. Queue ordering never depends on Small/Medium/Large or retry type.
    """
    signature=retry_batch_signature(batch)
    if not signature or any(retry_batch_signature(item)==signature for item in _DEFERRED_BATCH_QUEUE):
        return False
    generation=int(batch.get("retry_generation",_CURRENT_RETRY_GENERATION))+1
    if args is not None:
        retry=rebuild_retry_batch(list(batch["rows"]),args,generation)
    else:
        retry=dict(batch); retry["rows"]=list(batch["rows"]); retry["retry_generation"]=generation
    retry["retry_reason"]=reason
    retry["queue_kind"]="final_attempt"
    _DEFERRED_BATCH_QUEUE.append(retry)
    print(f"UNIVERSAL QUEUE: final-attempt batch appended at generation {generation}: {', '.join(signature)} | {reason}; queued={len(_DEFERRED_BATCH_QUEUE)}")
    return True

def dequeue_next_batch() -> Optional[dict[str, Any]]:
    """Claim the next FIFO workload without filtering by category or attempt type."""
    if not _DEFERRED_BATCH_QUEUE:
        return None
    batch=_DEFERRED_BATCH_QUEUE.pop(0)
    batch.setdefault("queue_kind","normal")
    return batch

def batch_queue_label(batch: dict[str, Any]) -> str:
    generation=int(batch.get("retry_generation",0))
    return f"final attempt generation {generation}" if generation > 0 else "normal queue"


def adaptive_retry_model(args: argparse.Namespace, generation: int, default_model: str) -> str:
    if getattr(args, "default_model", None):
        return args.default_model
    if getattr(args, "model_policy", "original") in {"sol_all", "sol_large"}:
        return effective_model_name(default_model)
    if generation < ADAPTIVE_MODEL_SWITCH_GENERATION:
        return effective_model_name(default_model)
    selected = args.large_model if generation % 2 else args.small_model
    return effective_model_name(selected)


def rebuild_retry_batch(rows: Sequence[dict[str,str]], args: argparse.Namespace, generation: int) -> dict[str,Any]:
    category=max((category_for_count(len(usable_local_case_files(row,args.case_files_root,args.merged_pdfs_root))) for row in rows),key={"Small":0,"Medium":1,"Large":2}.__getitem__)
    if getattr(args, "model_policy", "original") == "sol_large":
        # Retain the original size, including cases upgraded by PDF part count.
        size_by_id = getattr(args, "case_size_by_change_id", {})
        original_sizes = [size_by_id.get(canonical_change_id(row.get("change_id", ""))) for row in rows]
        if any(size in {"Small", "Medium", "Large"} for size in original_sizes):
            category = max((category, *(size for size in original_sizes if size in {"Small", "Medium", "Large"})),
                           key={"Small": 0, "Medium": 1, "Large": 2}.__getitem__)
    paths,counts,failed_total=attachment_plan(rows,category,args)
    default={"Small":args.small_model,"Medium":args.medium_model,"Large":args.large_model}[category]
    return {"category":category,"rows":list(rows),"paths":paths,"counts":counts,"failed_total":failed_total,
            "model":adaptive_retry_model(args,generation,default),"complete_small_addon_ids":[],"retry_generation":generation}


def adapt_batches_for_generation(batches: Sequence[dict[str,Any]], args: argparse.Namespace, generation: int) -> list[dict[str,Any]]:
    if generation <= 0:
        for batch in batches: batch.setdefault("retry_generation",0)
        return list(batches)
    maximum=1 if generation>=ADAPTIVE_SINGLE_CASE_GENERATION else 2
    adapted=[]
    for batch in batches:
        rows=list(batch["rows"])
        for start in range(0,len(rows),maximum):
            adapted.append(rebuild_retry_batch(rows[start:start+maximum],args,generation))
    return adapted


def make_batches(rows: list[dict[str, str]], size_map: dict[str, dict[str, str]], args: argparse.Namespace) -> list[dict[str, Any]]:
    by={"Small":[],"Medium":[],"Large":[]}
    for row in rows:
        category=size_map[canonical_change_id(row.get("change_id",""))].get("case_size","")
        if category not in by:
            raise RuntimeError(f"Invalid case_size {category!r} for change_id {row.get('change_id')}")
        by[category].append(row)
    batches=[]
    # Build Medium tabs first, then use genuine spare capacity for at most one
    # complete Small case. Complete means merged PDF plus every original file.
    for group in pack_category(by["Medium"],"Medium",args):
        paths,counts,failed_total=attachment_plan(group,"Medium",args)
        batch={"category":"Medium","rows":list(group),"paths":paths,"counts":counts,
               "failed_total":failed_total,"model":effective_model_name(args.medium_model),
               "complete_small_addon_ids":[]}
        for candidate in list(by["Small"]):
            if add_complete_small_to_medium_batch(batch,candidate,args):
                by["Small"].remove(candidate)
                break
        batches.append(batch)
    for category in ("Small","Large"):
        for group in pack_category(by[category],category,args):
            paths,counts,failed_total=attachment_plan(group,category,args)
            model=effective_model_name({"Small":args.small_model,"Large":args.large_model}[category])
            batches.append({"category":category,"rows":group,"paths":paths,"counts":counts,
                            "failed_total":failed_total,"model":model,
                            "complete_small_addon_ids":[]})
    # Preserve operational priority: Small, enriched Medium, then Large.
    order={"Small":0,"Medium":1,"Medium+Small":1,"Large":2}
    batches.sort(key=lambda batch:order[batch["category"]])
    # Return the complete logical plan. The caller performs the one and only
    # active/deferred split after adaptive retry transformations. Previously this
    # function returned only the first physical tab window, so the caller could
    # never see the remaining batches and printed "0 queued batch(es)".
    global _FULL_BATCH_PLAN
    _FULL_BATCH_PLAN=list(batches)
    return list(batches)


def print_distribution(size_path: Path, rows: Sequence[dict[str,str]], batches: Sequence[dict[str,Any]]) -> None:
    stage_heading("BATCH PLAN")
    print(f"Case-size CSV: {size_path}")
    print(f"Cases selected for this run: {len(rows)}")
    for number,batch in enumerate(batches,1):
        ids=", ".join((row.get("change_id") or "").strip() for row in batch["rows"])
        print(f"[{batch['category']}] Tab {number}: {len(batch['rows'])} change(s) | change_id(s): {ids} | attachments: {len(batch['paths'])}/20 | model: {batch['model']}")
    print("="*78)


async def collect_page_memory(page: Page) -> None:
    if page.is_closed(): return
    session=None
    try:
        session=await page.context.new_cdp_session(page)
        try:
            await session.send("HeapProfiler.enable")
            await session.send("HeapProfiler.collectGarbage")
        except PlaywrightError:
            pass
    except PlaywrightError: pass
    finally:
        if session is not None:
            try: await session.detach()
            except PlaywrightError: pass
    gc.collect()


def generic_chat_title(title: str) -> bool:
    """True for titles that are not independently sufficient completion evidence."""
    value=re.sub(r"[^a-z0-9]+"," ",(title or "").casefold()).strip()
    return value in {
        "chat microsoft copilot", "chat copilot", "copilot chat",
        "microsoft copilot", "new chat",
    }

async def reasoning_completed_signal(page: Any) -> tuple[bool, str]:
    """Detect Copilot's stable chain-of-thought completion header without reading its content."""
    try:
        value = await _bounded_probe(page.evaluate(r"""() => {
            const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const rx = /^Reasoning completed in \d+ steps?$/i;
            const nodes = [...document.querySelectorAll(
                'button[title^="Reasoning completed in " i], .scc-ChainOfThought__headerText, .scc-BebopChainOfThought__headerText'
            )];
            for (const node of nodes) {
                if (!visible(node)) continue;
                const text = String(node.getAttribute('title') || node.innerText || node.textContent || '').trim();
                if (rx.test(text)) return text;
            }
            return '';
        }"""), 0.45, "")
        text = str(value or "").strip()
        return bool(text), text
    except Exception:
        return False, ""

async def regenerate_if_available(page: Any, tab_number: int) -> bool:
    """Recover a failed New Chat response once; manual clicks remain compatible."""
    try:
        button = await first_visible([
            page.get_by_role("button", name=re.compile(r"^Regenerate$", re.I)),
            page.locator("button").filter(has_text=re.compile(r"^Regenerate$", re.I)),
        ], timeout_ms=180)
        if button is None:
            return False
        await button.click(timeout=350, no_wait_after=True)
        print(f"Tab {tab_number}: New Chat/failed response detected; Regenerate clicked")
        return True
    except PlaywrightError:
        return False


async def background_wake_page(page: Page) -> bool:
    """Wake a page through its renderer without selecting its visible Edge tab."""
    if page.is_closed():
        return False
    session=None
    try:
        session=await page.context.new_cdp_session(page)
        for method,params in (
            ('Page.enable',{}),
            ('Runtime.enable',{}),
            ('Network.enable',{}),
            ('Emulation.setFocusEmulationEnabled',{'enabled':True}),
            ('Page.setWebLifecycleState',{'state':'active'}),
            ('Runtime.evaluate',{'expression':'void(document.title); void(location.href);','returnByValue':True}),
        ):
            try:
                await session.send(method,params)
            except PlaywrightError:
                pass
        try:
            await page.evaluate(r"""() => {
                document.dispatchEvent(new Event('visibilitychange'));
                window.dispatchEvent(new Event('focus'));
                window.dispatchEvent(new Event('pageshow'));
            }""")
        except PlaywrightError:
            pass
        return True
    except PlaywrightError:
        return False
    finally:
        if session is not None:
            try: await session.detach()
            except PlaywrightError: pass


async def continuous_sent_tab_wake(
    pages: list[Page],
    stop_event: asyncio.Event,
) -> None:
    """Background-wake sent tabs without delaying the foreground wake loop.

    Every page title and renderer wake operation is bounded and cancellation is
    propagated immediately. This task is best-effort only and never owns result
    capture, assignment state, or the transition into the visible wake cycle.
    """
    while not stop_event.is_set():
        pending: list[Page] = []
        for page in list(pages):
            if stop_event.is_set():
                return
            if page.is_closed():
                continue
            try:
                title = await asyncio.wait_for(
                    page.title(), BACKGROUND_WAKE_PROBE_TIMEOUT_SECONDS
                )
            except asyncio.CancelledError:
                raise
            except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError):
                continue
            if generic_chat_title(str(title).strip()):
                pending.append(page)
        if pending and not stop_event.is_set():
            tasks = [asyncio.create_task(background_wake_page(page)) for page in pending]
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    BACKGROUND_WAKE_PROBE_TIMEOUT_SECONDS,
                )
            except asyncio.CancelledError:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            except asyncio.TimeoutError:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=STRONG_WAKE_INTERVAL_SECONDS
            )
        except asyncio.TimeoutError:
            pass

async def stop_background_wake_immediately(
    stop_event: asyncio.Event,
    task: Optional[asyncio.Task[Any]],
) -> None:
    """Stop best-effort background waking without blocking visible traversal."""
    stop_event.set()
    if task is None:
        return
    if not task.done():
        task.cancel()
    try:
        await asyncio.wait_for(
            asyncio.gather(task, return_exceptions=True),
            BACKGROUND_WAKE_SHUTDOWN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        print(
            "BACKGROUND WAKE: shutdown exceeded its short bound; visible wake loop is continuing immediately.",
            file=sys.stderr,
        )

async def wake_all_content_tabs(pages: Sequence[Page], dwell: float, max_rounds: int, excluded_page_ids: Optional[set[int]] = None) -> None:
    """Wake only tabs whose title is still generic; finished tabs leave permanently."""
    excluded_page_ids = excluded_page_ids or set()
    all_pages=[p for p in pages if id(p) not in excluded_page_ids and not p.is_closed() and not is_blank_or_new_tab_url(p.url)]
    pending={id(page):(number,page) for number,page in enumerate(all_pages,1) if generic_chat_title((await page.title()).strip())}
    completed=len(all_pages)-len(pending)
    if not pending:
        print(f"Wake complete: {len(all_pages)}/{len(all_pages)} tabs already have final titles.")
        return
    stage_heading(f"FINAL WAKE - {len(pending)} TAB(S) PENDING")
    rounds=0
    while pending:
        rounds+=1
        changed=[]
        # Background wake all pending renderers without visible tab switching.
        await asyncio.gather(*(background_wake_page(page) for _,page in pending.values()),return_exceptions=True)
        await asyncio.sleep(dwell)
        for key,(number,page) in list(pending.items()):
            if page.is_closed():
                pending.pop(key,None)
                continue
            title=(await page.title()).strip()
            if not generic_chat_title(title):
                changed.append(number)
                pending.pop(key,None)
                completed+=1
        if changed:
            print(f"Wake round {rounds}: completed tab(s) {', '.join(map(str,changed))}; {len(pending)} remaining")
        elif rounds == 1 or rounds % 10 == 0:
            print(f"Wake round {rounds}: {len(pending)} tab(s) still pending")
        if not pending:
            break
        if max_rounds>0 and rounds>=max_rounds:
            print(f"Wake limit reached: {len(pending)} tab(s) still have the generic title")
            return
        # Background renderer wake is preferred. Every tenth unchanged round,
        # foreground each still-pending tab once as a compatibility fallback.
        if rounds % STRONG_WAKE_FOREGROUND_EVERY_ROUNDS == 0:
            for number,page in list(pending.values()):
                if not page.is_closed():
                    await activate_page_like_manual_selection(page,number,"pending-tab wake fallback",verbose=False)
                    await asyncio.sleep(min(dwell,0.10))
    print(f"Wake complete: {completed}/{len(all_pages)} tabs have non-generic titles")


def ensure_result_log_schema(log_path: Path) -> None:
    '''Atomically add result columns while preserving every historical row.'''
    required = ["run_number", "change_id_status"]
    if not log_path.exists() or log_path.stat().st_size == 0:
        return
    with log_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle); fields = list(reader.fieldnames or []); rows = list(reader)
    if not fields or "change_id" not in fields:
        raise RuntimeError(f"Sent log has no change_id column: {log_path}")
    if all(name in fields for name in required):
        return
    new_fields = fields + [name for name in required if name not in fields]
    temp = log_path.with_suffix(log_path.suffix + ".schema.tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=new_fields, lineterminator="\n"); writer.writeheader()
        for row in rows: writer.writerow({name: row.get(name, "") for name in new_fields})
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temp, log_path)

def next_result_run_number(log_path: Path) -> int:
    ensure_result_log_schema(log_path); highest = 0
    if log_path.exists() and log_path.stat().st_size:
        with log_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                value = (row.get("run_number") or "").strip()
                if value.isdigit(): highest = max(highest, int(value))
    return highest + 1

def append_case_audit_results(log_path: Path, rows: Sequence[dict[str, str]], statuses: dict[str, str], run_number: int) -> None:
    ensure_result_log_schema(log_path); log_path.parent.mkdir(parents=True, exist_ok=True)
    exists = log_path.exists() and log_path.stat().st_size > 0
    fields = ["change_id", "InterestedPartyId", "fully_sent_at_local", "run_number", "change_id_status"]
    if exists:
        with log_path.open("r", encoding="utf-8-sig", newline="") as handle: fields = list(csv.DictReader(handle).fieldnames or fields)
    with log_path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        if not exists: writer.writeheader()
        for row in rows:
            change_id = (row.get("change_id") or "").strip(); status = statuses.get(change_id, "inconclusive_review_needed")
            if status not in AUDIT_ALLOWED_STATUSES: status = "inconclusive_review_needed"
            entry = {name: "" for name in fields}; entry.update({"change_id": change_id, "InterestedPartyId": (row.get("InterestedPartyId") or "").strip(), "fully_sent_at_local": datetime.now().astimezone().isoformat(timespec="seconds"), "run_number": str(run_number), "change_id_status": status})
            writer.writerow(entry)
        handle.flush(); os.fsync(handle.fileno())

def parse_audit_response(text: str, submitted_change_ids: Sequence[str]) -> tuple[str, dict[str, str]]:
    submitted = list(dict.fromkeys(str(value).strip() for value in submitted_change_ids if str(value).strip()))
    inconclusive = {change_id: "inconclusive_review_needed" for change_id in submitted}
    normalized_lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines()]
    overall_pattern = re.compile(r"^All files for all cases were exposed:\s*(Yes|No)\s*$")
    label_like = [line for line in normalized_lines if line.startswith(AUDIT_OVERALL_LABEL)]
    valid = [m.group(1) for line in label_like if (m := overall_pattern.fullmatch(line))]
    if len(label_like) != 1 or len(valid) != 1: return "inconclusive_review_needed", inconclusive
    overall = valid[0]
    if overall == "Yes": return overall, {change_id: "successful" for change_id in submitted}
    case_pattern = re.compile(r"^Case result:\s*([^|]+?)\s*\|\s*(successful|failed|inconclusive_review_needed)\s*$")
    collected: dict[str, list[str]] = {change_id: [] for change_id in submitted}
    for line in normalized_lines:
        match = case_pattern.fullmatch(line)
        if match and match.group(1).strip() in collected: collected[match.group(1).strip()].append(match.group(2))
    return overall, {change_id: values[0] if len(values) == 1 else "inconclusive_review_needed" for change_id, values in collected.items()}

def parse_complete_failed_or_mixed_result(
    text: str,
    submitted_change_ids: Sequence[str],
) -> tuple[str, dict[str, str], bool]:
    """Recognize a complete final contract including failed and mixed outcomes.

    Overall No is terminal only when every submitted case has exactly one explicit
    successful/failed line. This prevents a partial streamed response from freeing
    the tab early while allowing all-failed and mixed results to be captured before
    Copilot changes the page title.
    """
    submitted = list(dict.fromkeys(
        str(value).strip() for value in submitted_change_ids if str(value).strip()
    ))
    overall, statuses = parse_audit_response_v21(text, submitted)
    complete = (
        overall in {'Yes', 'No'}
        and len(statuses) == len(submitted)
        and all(statuses.get(change_id) in {'successful', 'failed'} for change_id in submitted)
    )
    if overall == 'Yes' and complete:
        complete = all(statuses[change_id] == 'successful' for change_id in submitted)
    if overall == 'No' and complete:
        complete = any(statuses[change_id] == 'failed' for change_id in submitted)
    return overall, statuses, complete


async def exact_terminal_audit_result(
    page: Any,
    submitted_change_ids: Sequence[str],
) -> tuple[str, dict[str, str], str]:
    """Return a stable complete success, mixed or failed result from live Copilot DOM."""
    ids = list(submitted_change_ids)
    text = await exact_final_contract_from_copilot(page, ids)
    if not text:
        text = await _bounded_probe(
            _fast_complete_status_text(page, ids),
            FAILED_RESULT_EARLY_PROBE_SECONDS,
            '',
        )
    if not text:
        return 'inconclusive_review_needed', {
            change_id: 'inconclusive_review_needed' for change_id in ids
        }, ''
    overall, statuses, complete = parse_complete_failed_or_mixed_result(text, ids)
    return overall, statuses, text if complete else ''


async def tab_finished_by_exact_title(page: Page) -> bool:
    if page.is_closed(): return False
    try: return (await page.title()).strip() != AUDIT_PENDING_TITLE
    except PlaywrightError: return False

async def latest_assistant_audit_response(page: Page, submitted_change_ids: Sequence[str]) -> str:
    '''Read final Chat replies from stable Copilot response containers; ignore user prompts and side panes.'''
    payload = await page.evaluate(r'''ids => {
        const label = 'All files for all cases were exposed:';
        const norm = value => String(value || '').replace(/\u00a0/g, ' ').replace(/\r\n?/g, '\n').trim();
        const textOf = node => norm(node?.innerText || node?.textContent || '');
        const isUser = node => !!node.closest('[data-testid="chatQuestion"], .fai-UserMessage, [aria-labelledby^="user-message-"]');
        const candidates = [], seen = new Set();
        const add = (node, priority) => {
            if (!node || seen.has(node) || isUser(node)) return;
            seen.add(node); const text = textOf(node); if (!text.includes(label)) return;
            const hits = ids.filter(id => text.includes(`Case result: ${id}`)).length;
            const exactChat = node.matches('[data-message-type="Chat"]') || !!node.querySelector('[data-message-type="Chat"]');
            candidates.push({text, score: priority + hits * 100 + (hits === ids.length ? 1000 : 0) + (exactChat ? 50 : 0)});
        };
        document.querySelectorAll('[data-testid="copilot-message-reply-div"] [data-message-type="Chat"][data-testid="markdown-reply"]').forEach(n => add(n, 800));
        document.querySelectorAll('[data-testid="copilot-message-div"] [data-message-type="Chat"]').forEach(n => add(n, 700));
        document.querySelectorAll('[data-testid="lastChatMessage"] [data-message-type="Chat"]').forEach(n => add(n, 650));
        document.querySelectorAll('[data-testid="copilot-message-reply-div"], [data-testid="copilot-message-div"], .fai-CopilotMessage__content').forEach(n => add(n, 450));
        document.querySelectorAll('[data-testid="lastChatMessage"]').forEach(n => add(n, 300));
        candidates.sort((a,b) => a.score - b.score);
        return candidates.length ? candidates[candidates.length - 1].text : '';
    }''', list(submitted_change_ids))
    return str(payload or "")

async def capture_completed_tab_result(page: Page, tab_number: int, rows: Sequence[dict[str, str]]) -> tuple[str, dict[str, str]]:
    submitted = [(row.get("change_id") or "").strip() for row in rows]; text = ""
    for attempt in range(1, AUDIT_RESPONSE_ATTEMPTS + 1):
        try: text = await latest_assistant_audit_response(page, submitted)
        except PlaywrightError as exc: print(f"Tab {tab_number}: audit response read attempt {attempt}/{AUDIT_RESPONSE_ATTEMPTS} failed: {exc}", file=sys.stderr)
        if text:
            overall, statuses = parse_audit_response(text, submitted)
            if overall != "inconclusive_review_needed": break
        if attempt < AUDIT_RESPONSE_ATTEMPTS:
            await background_wake_page(page); await asyncio.sleep(AUDIT_RESPONSE_RETRY_SECONDS)
    overall, statuses = parse_audit_response(text, submitted)
    print(f"Tab {tab_number}: overall result = {overall}")
    for change_id in submitted: print(f"Tab {tab_number}: change_id {change_id} = {statuses[change_id]}")
    return overall, statuses



# V24 result capture and rapid round-robin wake implementation.
SUCCESS_STATUS = "successful"

RETRY_STATUSES = {"failed", "inconclusive_review_needed"}

STATUS_COLUMNS = ("change_id_status", "status", "result", "case_status", "audit_status")

RESULT_CAPTURE_ATTEMPTS = 160

RESULT_CAPTURE_INTERVAL_SECONDS = 0.025

WAKE_OPERATION_TIMEOUT_SECONDS = 0.35

WAKE_FOREGROUND_DWELL_SECONDS = 0.12
WAKE_VISIBLE_ACTIVATION_TIMEOUT_SECONDS = 1.50
WAKE_TITLE_READ_TIMEOUT_SECONDS = 1.00
WAKE_CDP_RECOVERY_BACKOFF_SECONDS = 0.50

WAKE_CAPTURE_RETRY_SECONDS = 0.05

def _canonical(value: str) -> str:
    text=(value or "").strip()
    return str(int(text)) if text and text.lstrip("+-").isdigit() else text.casefold()

def _status(value: str) -> str:
    text=(value or "").strip().casefold().replace("-","_").replace(" ","_")
    return {"success":"successful","succeeded":"successful","complete":"successful","completed":"successful","successfull":"successful","failure":"failed","unsuccessful":"failed","inconclusive":"inconclusive_review_needed","review_needed":"inconclusive_review_needed"}.get(text,text)

def _column(fields: Iterable[str], names: Iterable[str]) -> str | None:
    lookup={(x or "").strip().casefold():x for x in fields}
    return next((lookup[x.casefold()] for x in names if x.casefold() in lookup),None)

def read_successfully_logged_change_ids(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size == 0: return set()
    with path.open("r",encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle); fields=list(reader.fieldnames or [])
        id_col=_column(fields,("change_id","change id","changeid")); status_col=_column(fields,STATUS_COLUMNS)
        if not id_col: raise RuntimeError(f"Sent log has no change_id column: {path}")
        if not status_col: raise RuntimeError(f"Sent log has no result-status column: {path}")
        latest={}
        for number,row in enumerate(reader,2):
            cid=_canonical(row.get(id_col) or ""); status=_status(row.get(status_col) or "")
            if not cid or not status: continue
            if status not in ({SUCCESS_STATUS}|RETRY_STATUSES):
                print(f"LOG WARNING: row {number} unsupported status {status!r}; ignored.",file=sys.stderr); continue
            latest[cid]=status
    successful={cid for cid,status in latest.items() if status==SUCCESS_STATUS}
    retry=sorted(cid for cid,status in latest.items() if status in RETRY_STATUSES)
    print(f"LOG ELIGIBILITY: {len(successful)} latest-successful excluded; {len(retry)} failed/inconclusive eligible for rerun.")
    if retry: print("LOG RETRY CASES: "+", ".join(retry))
    return successful

def parse_audit_response_v21(text: str, submitted_ids: Sequence[str]) -> tuple[str,dict[str,str]]:
    submitted=list(dict.fromkeys(str(x).strip() for x in submitted_ids if str(x).strip()))
    by_canonical={_canonical(x):x for x in submitted}
    inconclusive={x:"inconclusive_review_needed" for x in submitted}
    cleaned=unescape(text or "")
    cleaned=re.sub(r"<br\s*/?>","\n",cleaned,flags=re.I)
    cleaned=re.sub(r"</(?:p|div|li|section)\s*>","\n",cleaned,flags=re.I)
    cleaned=re.sub(r"<[^>]+>"," ",cleaned).replace("\u00a0"," ").replace("\r","\n")
    overall_hits=re.findall(r"(?im)^\s*All\s+files\s+for\s+all\s+cases\s+were\s+exposed\s*:\s*(Yes|No)\s*$",cleaned)
    if not overall_hits: return "inconclusive_review_needed",inconclusive
    overall=overall_hits[-1].title(); captured={}
    pattern=re.compile(r"(?im)^\s*Case\s+result\s*:\s*([^|\r\n<]+?)\s*\|\s*(successful|failed|inconclusive[\s_-]*review[\s_-]*needed)\s*$")
    for match in pattern.finditer(cleaned):
        key=_canonical(match.group(1))
        if key in by_canonical: captured[by_canonical[key]]=_status(match.group(2))
    statuses={x:captured.get(x,"inconclusive_review_needed") for x in submitted}
    if len(captured)!=len(submitted): return "inconclusive_review_needed",statuses
    if overall=="Yes" and any(x!="successful" for x in statuses.values()): return "inconclusive_review_needed",inconclusive
    return overall,statuses

async def latest_assistant_audit_response_v21(page: Any, submitted_ids: Sequence[str]) -> str:
    script = r"""ids => {
      const label='All files for all cases were exposed:';
      const norm=v=>String(v||'').replace(/\u00a0/g,' ').replace(/\r\n?/g,'\n').trim();
      const textOf=n=>norm(n?.innerText||n?.textContent||'');
      const isUser=n=>!!n.closest('[data-testid="chatQuestion"],.fai-UserMessage,[aria-labelledby^="user-message-"]');
      const wanted=new Set(ids.map(v=>String(v).trim().replace(/^0+(?=\d)/,'')));
      const rx=/Case\s+result\s*:\s*([^|\n]+?)\s*\|\s*(successful|failed|inconclusive[_ -]*review[_ -]*needed)/gi;
      const candidates=[],seen=new Set(); let order=0;
      const add=(n,priority)=>{ if(!n||seen.has(n)||isUser(n))return; seen.add(n); const text=textOf(n); if(!text.includes(label))return;
        const found=new Set(); for(const m of text.matchAll(rx))found.add(String(m[1]).trim().replace(/^0+(?=\d)/,''));
        const hits=[...wanted].filter(x=>found.has(x)).length; candidates.push({text,hits,score:priority+hits*1000+(++order)}); };
      document.querySelectorAll('[data-testid="lastChatMessage"] [data-testid="markdown-reply"]').forEach(n=>add(n,n.getAttribute('data-message-type')==='Progress'?0:9000));
      document.querySelectorAll('[data-testid="lastChatMessage"]').forEach(n=>add(n,8000));
      document.querySelectorAll('[data-testid="copilot-message-reply-div"] [data-testid="markdown-reply"],[data-testid="copilot-message-div"] [data-testid="markdown-reply"]').forEach(n=>add(n,n.getAttribute('data-message-type')==='Progress'?0:7000));
      document.querySelectorAll('.fai-CopilotMessage__content,[data-testid="copilot-message-reply-div"],[data-testid="copilot-message-div"]').forEach(n=>add(n,6000));
      candidates.sort((a,b)=>a.hits-b.hits||a.score-b.score); const complete=candidates.filter(x=>x.hits===wanted.size);
      return (complete.length?complete[complete.length-1]:candidates[candidates.length-1])?.text||'';
    }"""
    return str(await page.evaluate(script,list(submitted_ids)) or "")

async def capture_completed_tab_result_v21(page: Any, tab_number: int, rows: Sequence[dict[str,str]]) -> tuple[str,dict[str,str]]:
    submitted=[(row.get("change_id") or "").strip() for row in rows]
    best={x:"inconclusive_review_needed" for x in submitted}
    for attempt in range(1,RESULT_CAPTURE_ATTEMPTS+1):
        try:
            text=await latest_assistant_audit_response_v21(page,submitted)
            overall,statuses=parse_audit_response_v21(text,submitted) if text else ("inconclusive_review_needed",best)
            best=statuses
            if overall in {"Yes","No"} and all(v in {"successful","failed"} for v in statuses.values()):
                print(f"Tab {tab_number}: captured final audit result on check {attempt}")
                print(f"Tab {tab_number}: overall result = {overall}")
                for cid in submitted: print(f"Tab {tab_number}: change_id {cid} = {statuses[cid]}")
                return overall,statuses
        except Exception as exc:
            if attempt==1 or attempt%20==0: print(f"Tab {tab_number}: result read check {attempt} failed: {exc}",file=sys.stderr)
        if attempt<RESULT_CAPTURE_ATTEMPTS:
            try: await page.evaluate("() => { window.dispatchEvent(new Event('focus')); document.dispatchEvent(new Event('visibilitychange')); }")
            except Exception: pass
            await asyncio.sleep(RESULT_CAPTURE_INTERVAL_SECONDS)
    print(f"Tab {tab_number}: complete result block not captured; preserving inconclusive status.",file=sys.stderr)
    return "inconclusive_review_needed",best

async def tab_finished_for_capture_v21(page: Any) -> bool:
    try: return not page.is_closed()
    except Exception: return False

def self_test_v24() -> None:
    samples=[
      ("All files for all cases were exposed: Yes\nCase result: 02082 | successful\nCase result: 02088 | successful",["02082","02088"]),
      ("<p>All files for all cases were exposed: Yes<br>Case result: 02099 | successful<br>Case result: 02100 | successful</p>",["02099","02100"]),
      ("All files for all cases were exposed: Yes\nCase result: 02089 | successful",["02089"]),
      ("All files for all cases were exposed: Yes\nCase result: 02090 | successful",["02090"]),
    ]
    for text,ids in samples:
        overall,statuses=parse_audit_response_v21(text,ids)
        assert overall=="Yes" and statuses=={x:"successful" for x in ids},(overall,statuses)

async def _consume_probe_task(task: "asyncio.Task[Any]") -> None:
    """Consume a completed/cancelled probe exception so asyncio never reports it later."""
    try:
        task.exception()
    except (asyncio.CancelledError, Exception):
        pass


async def _bounded_probe(awaitable: Any, timeout_seconds: float, default: Any = None) -> Any:
    """Bound one probe and always retrieve its terminal exception.

    Playwright's locator text getters can leave an internal future whose timeout is
    reported later as 'Future exception was never retrieved'. This wrapper owns the
    task explicitly, cancels it on timeout, awaits cancellation, and consumes any
    terminal exception before returning the neutral default.
    """
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=max(0.05, timeout_seconds))
    except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError):
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return default
    except Exception:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return default
    finally:
        if task.done():
            await _consume_probe_task(task)
        else:
            task.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)


async def _fast_page_text_candidates(page: Any) -> list[str]:
    """Read candidate response text without short locator getter timeouts.

    The browser-side DOM snapshot already covers the last message, Markdown replies,
    main content, body text and full HTML. Avoiding 150 ms locator.inner_text() and
    locator.text_content() calls removes the non-actionable orphaned Playwright
    futures seen during long wake rotations.
    """
    javascript = r"""() => {
      const out=[]; const add=v=>{v=String(v||'').trim(); if(v&&!out.includes(v))out.push(v)};
      const selectors=[
        '[data-testid="lastChatMessage"]',
        '[data-testid="lastChatMessage"] [data-testid="markdown-reply"]',
        '[data-testid="markdown-reply"]:not([data-message-type="Progress"])',
        '[data-testid="copilot-message-reply-div"]',
        '[data-testid="copilot-message-div"]',
        '.fai-CopilotMessage__content',
        'main',
        'body'
      ];
      for(const sel of selectors) for(const n of document.querySelectorAll(sel)){
        add(n.innerText); add(n.textContent); add(n.getAttribute('aria-label'));
      }
      add(document.documentElement?.outerHTML);
      return out;
    }"""
    candidates: list[str] = []
    if page.is_closed():
        return candidates
    values = await _bounded_probe(page.evaluate(javascript), 0.50, [])
    if isinstance(values, list):
        candidates.extend(str(value) for value in values if value)
    # page.content() remains an independent source, but is explicitly task-owned
    # and bounded so a closed target or slow renderer cannot leak an exception.
    html = await _bounded_probe(page.content(), 0.50, "")
    if html:
        candidates.append(str(html))
    return candidates

async def _fast_complete_status_text(page: Any, submitted_ids: Sequence[str] | None = None) -> str:
    """Return the first complete final block found by any independent route."""
    ids=list(submitted_ids or [])
    for text in await _fast_page_text_candidates(page):
        if ids:
            overall,statuses=parse_audit_response_v21(text,ids)
            if overall in {'Yes','No'} and all(v in {'successful','failed'} for v in statuses.values()):
                return text
        elif re.search(r'All\s+files\s+for\s+all\s+cases\s+were\s+exposed\s*:\s*(?:Yes|No)',text,re.I) and re.search(r'Case\s+result\s*:',text,re.I):
            return text
    return ''

async def exact_final_contract_from_copilot(page: Any, submitted_ids: Sequence[str]) -> str:
    """Read the final contract from actual Copilot Chat nodes, never the user prompt.

    Supports both lastChatMessage/markdown-reply structures and the newer
    copilot-message-div structure. Progress nodes, user messages, attachment
    cards and opened workbook preview panes are excluded.
    """
    script=r"""ids => {
      const label=/All\s+files\s+for\s+all\s+cases\s+were\s+exposed\s*:\s*(Yes|No)/i;
      const canon=v=>String(v||'').trim().replace(/^0+(?=\d)/,'');
      const wanted=new Set(ids.map(canon));
      const resultRx=/Case\s+result\s*:\s*([^|\n<]+?)\s*\|\s*(successful|failed|inconclusive[_ -]*review[_ -]*needed)/gi;
      const user=n=>!!n.closest('[data-testid="chatQuestion"],.fai-UserMessage,[aria-labelledby^="user-message-"]');
      const preview=n=>!!n.closest('[role="dialog"],[data-testid*="preview" i],[class*="preview" i]');
      const nodes=[...document.querySelectorAll([
        '[data-testid="lastChatMessage"] [data-testid="markdown-reply"][data-message-type="Chat"]',
        '[data-testid="copilot-message-reply-div"] [data-testid="markdown-reply"][data-message-type="Chat"]',
        '[data-testid="copilot-message-div"] [data-testid="markdown-reply"][data-message-type="Chat"]',
        '[data-testid="copilot-message-reply-div"] .fai-CopilotMessage__content',
        '[data-testid="copilot-message-div"] .fai-CopilotMessage__content',
        '[role="article"] .fai-CopilotMessage__content'
      ].join(','))];
      const out=[];
      for(const n of nodes){
        if(user(n)||preview(n)||n.getAttribute('data-message-type')==='Progress') continue;
        const text=String(n.innerText||n.textContent||'').replace(/\u00a0/g,' ').trim();
        if(!label.test(text)) continue;
        const found=new Set(); let m; resultRx.lastIndex=0;
        while((m=resultRx.exec(text))) found.add(canon(m[1]));
        const hits=[...wanted].filter(x=>found.has(x)).length;
        if(hits===wanted.size) out.push({text,hits,index:out.length});
      }
      return out.length?out[out.length-1].text:'';
    }"""
    value=await _bounded_probe(page.evaluate(script,list(submitted_ids)),0.80,"")
    return str(value or "")


async def close_open_preview_if_present(page: Any) -> None:
    """Close an automatically opened workbook preview without touching the chat."""
    try:
        button=page.get_by_role("button",name=re.compile(r"^Close preview$",re.I)).first
        if await button.count() and await button.is_visible():
            await button.click(timeout=300,force=True,no_wait_after=True)
    except PlaywrightError:
        pass


async def capture_completed_tab_result_v22(page: Any, tab_number: int, rows: Sequence[dict[str,str]]) -> tuple[str,dict[str,str]]:
    submitted=[(row.get('change_id') or '').strip() for row in rows]
    fallback={x:'inconclusive_review_needed' for x in submitted}
    await activate_page_like_manual_selection(page,tab_number,"final result capture",verbose=True)
    await close_open_preview_if_present(page)
    for attempt in range(1,RESULT_CAPTURE_ATTEMPTS+1):
        # Route 1: exact Chat reply nodes shown in the supplied real DOM examples.
        exact=await exact_final_contract_from_copilot(page,submitted)
        if exact:
            overall,statuses=parse_audit_response_v21(exact,submitted)
            if overall in {'Yes','No'} and all(statuses.get(cid) in {'successful','failed','inconclusive_review_needed'} for cid in submitted):
                print(f"Tab {tab_number}: finalized results captured from exact Copilot Chat node on attempt {attempt}")
                for cid in submitted: print(f"CASE RESULT: change_id {cid} = {statuses[cid]}")
                return overall,statuses
        # Routes 2+: broad DOM/source/CDP fallbacks for future Copilot variants.
        candidates=await _fast_page_text_candidates(page)
        if attempt%8==0:
            session=None
            try:
                session=await page.context.new_cdp_session(page)
                snap=await session.send('DOMSnapshot.captureSnapshot',{'computedStyles':[],'includeDOMRects':False,'includePaintOrder':False})
                candidates.append('\n'.join(str(x) for x in snap.get('strings',[]) if x))
            except PlaywrightError: pass
            finally:
                if session is not None:
                    try: await session.detach()
                    except PlaywrightError: pass
        for text in candidates:
            overall,statuses=parse_audit_response_v21(unescape(str(text)),submitted)
            if overall in {'Yes','No'} and all(statuses.get(cid) in {'successful','failed','inconclusive_review_needed'} for cid in submitted):
                print(f"Tab {tab_number}: finalized results captured by fallback route on attempt {attempt}")
                for cid in submitted: print(f"CASE RESULT: change_id {cid} = {statuses[cid]}")
                return overall,statuses
        try:
            await page.bring_to_front()
            await close_open_preview_if_present(page)
            if attempt%3==0: await page.keyboard.press('End')
            elif attempt%3==1: await page.evaluate("() => window.scrollTo(0,document.body.scrollHeight)")
            else: await page.evaluate("() => {window.focus();document.dispatchEvent(new Event('visibilitychange'))}")
        except PlaywrightError: pass
        await asyncio.sleep(RESULT_CAPTURE_INTERVAL_SECONDS)
    print(f"Tab {tab_number}: result capture exhausted; cases are requeued instead of finalized.")
    for cid in submitted: print(f"CASE RESULT: change_id {cid} = requeued_for_processing")
    return 'inconclusive_review_needed',fallback

_CAPTURED_RESULTS = {}

_RUN_ROWS = {}

async def capture_completed_tab_result_v23(page, tab_number, rows):
    expected={(r.get("change_id") or "").strip() for r in rows}
    cached=_CAPTURED_RESULTS.get(id(page))
    if cached and set(cached[1])==expected:
        print(f"Tab {tab_number}: using status captured during paused wake loop")
        return cached
    result=await capture_completed_tab_result_v22(page,tab_number,rows)
    if result[0] in {"Yes","No"}: _CAPTURED_RESULTS[id(page)]=result
    return result

async def _bounded_v24(awaitable, timeout=WAKE_OPERATION_TIMEOUT_SECONDS, default=None):
    """Run one wake/probe shot with a hard cap; a timeout is never a negative result."""
    try:
        return await asyncio.wait_for(awaitable, timeout=max(0.05, timeout))
    except (asyncio.TimeoutError, Exception):
        return default

async def _fast_title_v24(page: Any) -> str:
    value = await _bounded_v24(page.title(), 0.20, "")
    return str(value or "").strip()

async def _rapid_foreground_shot_v24(page: Any) -> None:
    """Use independent Playwright, CDP and DOM wake routes, each briefly bounded."""
    if page.is_closed():
        return
    # Route 1: visible/manual-equivalent tab selection.
    await _bounded_v24(page.bring_to_front(), 0.25)
    # Route 2: direct renderer activation. A new short-lived session avoids stale handles.
    session = None
    try:
        session = await _bounded_v24(page.context.new_cdp_session(page), 0.20)
        if session is not None:
            for method, params in (
                ("Page.bringToFront", {}),
                ("Page.setWebLifecycleState", {"state": "active"}),
                ("Emulation.setFocusEmulationEnabled", {"enabled": True}),
                ("Runtime.evaluate", {"expression": "void(document.title);void(location.href)", "returnByValue": True}),
            ):
                await _bounded_v24(session.send(method, params), 0.12)
    finally:
        if session is not None:
            await _bounded_v24(session.detach(), 0.12)
    # Route 3: renderer events. Failure or timeout is inconclusive, never negative.
    await _bounded_v24(page.evaluate(r"""() => {
        try { window.focus(); } catch (_) {}
        document.dispatchEvent(new Event('visibilitychange'));
        window.dispatchEvent(new Event('focus'));
        window.dispatchEvent(new Event('pageshow'));
        return document.title;
    }"""), 0.18)

async def foreground_and_read_title_v27(page: Any, tab_number: int, dwell: float) -> tuple[str, bool, str]:
    """Visibly activate one exact target and read its title after activation."""
    if page.is_closed():
        raise CDPConnectionLostError(f"Tab {tab_number}: page closed during visible traversal")
    session = None
    try:
        await asyncio.wait_for(page.bring_to_front(), WAKE_VISIBLE_ACTIVATION_TIMEOUT_SECONDS)
        session = await asyncio.wait_for(page.context.new_cdp_session(page), WAKE_VISIBLE_ACTIVATION_TIMEOUT_SECONDS)
        await asyncio.wait_for(session.send("Page.bringToFront"), WAKE_VISIBLE_ACTIVATION_TIMEOUT_SECONDS)
        for method, params in (("Page.setWebLifecycleState", {"state":"active"}), ("Emulation.setFocusEmulationEnabled", {"enabled":True})):
            try:
                await asyncio.wait_for(session.send(method, params), WAKE_VISIBLE_ACTIVATION_TIMEOUT_SECONDS)
            except PlaywrightError:
                pass
        await asyncio.wait_for(page.evaluate(r"""() => { try { window.focus(); } catch (_) {} document.dispatchEvent(new Event('visibilitychange')); window.dispatchEvent(new Event('focus')); window.dispatchEvent(new Event('pageshow')); }"""), WAKE_TITLE_READ_TIMEOUT_SECONDS)
        await asyncio.sleep(min(max(dwell, 0.08), 0.35))
        state = await asyncio.wait_for(page.evaluate(r"""() => ({title:String(document.title||'').trim(), visibility:String(document.visibilityState||''), focused:Boolean(document.hasFocus())})"""), WAKE_TITLE_READ_TIMEOUT_SECONDS)
        title = str(state.get("title") or "").strip()
        if not title:
            raise CDPConnectionLostError(f"Tab {tab_number}: empty title after foreground activation")
        visibility = str(state.get("visibility") or "")
        return title, visibility.casefold()=="visible", f"visibility={visibility or 'unknown'}, focused={'yes' if state.get('focused') else 'no'}"
    except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError) as exc:
        raise CDPConnectionLostError(f"Tab {tab_number}: foreground/title operation failed: {concise_error(exc)}") from exc
    finally:
        if session is not None:
            try: await asyncio.wait_for(session.detach(), 0.50)
            except Exception: pass

async def wake_all_content_tabs_v24(pages, dwell, max_rounds, excluded_page_ids=None):
    """Rapidly cycle every pending sent tab while result capture runs independently.

    V23 stopped the wake rotation while it synchronously captured one completed tab.
    V24 keeps capture workers separate, performs several short wake routes per page,
    and foregrounds every still-generic tab on every round. Timeouts only trigger the
    next technique/attempt; they never classify a case as failed.
    """
    excluded_page_ids = excluded_page_ids or set()
    sent=[p for p in pages if id(p) in _RUN_ROWS and id(p) not in excluded_page_ids and not p.is_closed()]
    numbers={id(page): index for index,page in enumerate(sent,1)}
    pending={id(page):page for page in sent}
    capture_tasks={}
    rounds=0

    async def capture_worker(page):
        number=numbers[id(page)]
        rows=_RUN_ROWS[id(page)]
        attempt=0
        while not page.is_closed():
            cached = _CAPTURED_RESULTS.get(id(page))
            if cached is not None:
                overall, statuses = cached
                print(f"Capture worker complete: Tab {number} terminal result already captured (overall={overall})")
                for change_id in [((row.get('change_id') or '').strip()) for row in rows]:
                    print(f"CASE RESULT: change_id {change_id} = {statuses.get(change_id, 'inconclusive_review_needed')}")
                return
            attempt+=1
            result=await capture_completed_tab_result_v22(page,number,rows)
            if result[0] in {"Yes","No"}:
                _CAPTURED_RESULTS[id(page)]=result
                print(f"Capture worker complete: Tab {number} status captured")
                return
            if attempt==1 or attempt%10==0:
                print(f"Capture worker: Tab {number} result not complete yet; retrying without blocking wake rotation")
            await asyncio.sleep(WAKE_CAPTURE_RETRY_SECONDS)

    async def scan_all():
        probes=[]
        keys=[]
        for key,page in list(pending.items()):
            if page.is_closed():
                pending.pop(key,None)
                continue
            keys.append(key)
            probes.append(_fast_title_v24(page))
        titles=await asyncio.gather(*probes,return_exceptions=True)
        for key,title in zip(keys,titles):
            if key not in pending or isinstance(title,BaseException) or not title:
                continue
            page=pending[key]
            # A complete explicit result is also accepted as a completion trigger,
            # even if Copilot has not renamed the tab yet.
            rows=_RUN_ROWS[key]
            ids=[(row.get("change_id") or "").strip() for row in rows]
            direct_overall, direct_statuses, direct = await _bounded_v24(
                exact_terminal_audit_result(page, ids),
                FAILED_RESULT_EARLY_PROBE_SECONDS + 0.50,
                ('inconclusive_review_needed', {}, ''),
            )
            if not generic_chat_title(str(title)) or direct:
                pending.pop(key,None)
                if direct:
                    _CAPTURED_RESULTS[id(page)] = (direct_overall, direct_statuses)
                    print(
                        f"Wake rotation released Tab {numbers[key]} immediately from explicit "
                        f"terminal result: overall={direct_overall}; title={str(title)!r}"
                    )
                else:
                    print(f"Wake rotation released Tab {numbers[key]}: title={str(title)!r}; explicit_result=not-yet")
                capture_tasks[key]=asyncio.create_task(capture_worker(page))

    await scan_all()
    while pending:
        rounds+=1
        current=list(pending.values())
        # Shot A: wake all renderers concurrently. Individual caps prevent one tab
        # from delaying the rest of the round.
        await asyncio.gather(*(
            _bounded_v24(background_wake_page(page),0.35)
            for page in current
        ),return_exceptions=True)
        # Shots B/C/D: true round-robin foreground cycling through EVERY remaining
        # tab. This fixes the V23 behaviour where the loop effectively stayed on the
        # last selected tab after capture resumed.
        for page in current:
            if id(page) not in pending or page.is_closed():
                continue
            await _rapid_foreground_shot_v24(page)
            await asyncio.sleep(min(max(WAKE_FOREGROUND_DWELL_SECONDS,0.01),0.06))
        await scan_all()
        if rounds==1 or rounds%5==0:
            print(f"Wake round {rounds}: cycled all {len(pending)} unchanged-title sent tab(s); {len(capture_tasks)} capture worker(s) active/started")
        if max_rounds>0 and rounds>=max_rounds:
            print(f"Wake limit reached: {len(pending)} unchanged-title sent tab(s) remain; no timeout was classified as failed")
            break
        await asyncio.sleep(min(max(dwell,0.01),0.05))

    if capture_tasks:
        await asyncio.gather(*capture_tasks.values(),return_exceptions=True)
    print(f"Wake/capture complete: {len(_CAPTURED_RESULTS)}/{len(sent)} sent-tab statuses captured; final verification follows")

# Active V24 bindings formerly installed by the launcher at runtime.
read_logged_change_ids = read_successfully_logged_change_ids
parse_audit_response = parse_audit_response_v21
latest_assistant_audit_response = latest_assistant_audit_response_v21
capture_completed_tab_result = capture_completed_tab_result_v23
tab_finished_by_exact_title = tab_finished_for_capture_v21
wake_all_content_tabs = wake_all_content_tabs_v24

def current_logged_statuses(log_path: Path, rows: Sequence[dict[str, str]]) -> dict[str, str]:
    """Return the authoritative latest status for the exact current tab assignment."""
    records=CaseLogStore(log_path).load(compact=False)
    output={}
    for row in rows:
        cid=(row.get("change_id") or "").strip()
        ipid=(row.get("InterestedPartyId") or "").strip().casefold()
        record=records.get((canonical_change_id(cid),ipid))
        output[cid]=record.status if record is not None else ""
    return output


async def reconcile_current_tab_before_title_or_reset(
    page: Any,
    tab_number: int,
    batch: dict[str, Any],
    log_path: Path,
    run_number: int,
) -> tuple[str, Optional[tuple[str, dict[str, str]]]]:
    """Reconcile the live response with logs before title gating or destructive reuse.

    A generic title is never proof that a sent tab is empty. The exact current
    assignment IDs are searched first. If a live result exists and differs from
    the log, the live result wins and is persisted immediately. If no result is
    readable while any exact current case remains logged as sent, the tab remains
    pending and must not be navigated, reloaded or reassigned.
    """
    rows=batch["rows"]
    ids=[(row.get("change_id") or "").strip() for row in rows]
    logged=current_logged_statuses(log_path,rows)
    exact=await exact_final_contract_from_copilot(page,ids)
    if not exact:
        # Independent broad route handles a result rendered outside the known
        # Chat wrappers while still requiring all current assignment IDs.
        exact=await _bounded_probe(_fast_complete_status_text(page,ids),0.80,"")
    if exact:
        overall,statuses=parse_audit_response_v21(exact,ids)
        if overall in {"Yes","No"} and all(statuses.get(cid) in AUDIT_ALLOWED_STATUSES for cid in ids):
            mismatches=[cid for cid in ids if logged.get(cid)!=statuses[cid]]
            if mismatches:
                append_case_audit_results(log_path,rows,statuses,run_number)
                print(f"TAB {tab_number} RECONCILIATION: live result differed from the log; corrected {', '.join(mismatches)}.")
            else:
                print(f"TAB {tab_number} RECONCILIATION: live result matches the current log.")
            for cid in ids:
                print(f"CASE RESULT: tab {tab_number} | change_id {cid} | {statuses[cid]}")
            return "final",(overall,statuses)
    if any(logged.get(cid) in {"sent",""} for cid in ids):
        return "pending",None
    return "logged_final",None


def print_final_audit_summary(results: Sequence[dict[str, Any]]) -> None:
    stage_heading("FINAL AUDIT RESULT SUMMARY")
    for result in results:
        print(f"Tab {result['tab_number']}: overall result = {result['overall']}")
        for change_id, status in result["statuses"].items(): print(f"  change_id {change_id}: {status}")

def confirm_large_case_model(args: argparse.Namespace) -> None:
    """Choose one model policy for the run; retain the original default and No option."""
    global _OPUS_GLOBALLY_DISABLED, _OPUS_DISABLE_REASON
    print("=" * 78)
    if getattr(args, "default_model", None):
        args.model_policy = "selected_all"
        args.small_model = args.medium_model = args.large_model = args.default_model
        _OPUS_GLOBALLY_DISABLED = False
        _OPUS_DISABLE_REASON = ""
        print(f"MODEL POLICY: all cases and retries use {args.default_model}; automatic model fallback disabled")
        return
    print("MODEL SELECTION FOR THIS RUN")
    print("1 or Enter: GPT 5.6 for Small/Medium; Opus for Large (original default)")
    print("2: GPT 6.0 Sol for Small, Medium and Large")
    print("3: GPT 5.6 for Small/Medium; GPT 6.0 Sol for Large")
    print("N: GPT 5.6 for all cases (original No option)")
    print("=" * 78)
    try:
        answer = input("Choose model policy [1/2/3/N, default 1]: ").strip().casefold()
    except EOFError:
        answer = ""
    if answer in {"2", "sol", "all-sol"}:
        args.model_policy = "sol_all"
        args.small_model = GPT_6_SOL_MODEL_NAME
        args.medium_model = GPT_6_SOL_MODEL_NAME
        args.large_model = GPT_6_SOL_MODEL_NAME
        _OPUS_GLOBALLY_DISABLED = False
        _OPUS_DISABLE_REASON = ""
    elif answer in {"3", "sol-large", "large-sol"}:
        args.model_policy = "sol_large"
        args.small_model = DEFAULT_SMALL_CASE_MODEL_NAME
        args.medium_model = DEFAULT_MEDIUM_CASE_MODEL_NAME
        args.large_model = GPT_6_SOL_MODEL_NAME
        _OPUS_GLOBALLY_DISABLED = False
        _OPUS_DISABLE_REASON = ""
    elif answer in {"n", "no", "0", "false"}:
        args.model_policy = "gpt_56_all"
        args.large_model = DEFAULT_LARGE_CASE_MODEL_FALLBACK
        _OPUS_GLOBALLY_DISABLED = True
        _OPUS_DISABLE_REASON = "disabled by startup selection"
    elif answer in {"", "1", "y", "yes"}:
        args.model_policy = "original"
        args.large_model = DEFAULT_LARGE_CASE_MODEL_NAME
        _OPUS_GLOBALLY_DISABLED = False
        _OPUS_DISABLE_REASON = ""
    else:
        raise RuntimeError(f"Unknown model policy {answer!r}; no cases were sent.")
    print(f"MODEL POLICY: {args.model_policy}; Small={args.small_model}; Medium={args.medium_model}; Large={args.large_model}")


def effective_model_name(model_name: str) -> str:
    """Apply the run-global Opus circuit breaker to every model decision."""
    if normalize_ui_text(model_name) == "opus" and _OPUS_GLOBALLY_DISABLED:
        return DEFAULT_LARGE_CASE_MODEL_FALLBACK
    return model_name

def disable_opus_globally(reason: BaseException | str) -> None:
    """Disable Opus after its first unavailability and rewrite all queued plans."""
    global _OPUS_GLOBALLY_DISABLED, _OPUS_DISABLE_REASON
    if _OPUS_GLOBALLY_DISABLED:
        return
    _OPUS_GLOBALLY_DISABLED=True
    _OPUS_DISABLE_REASON=concise_error(reason)
    changed=0
    seen=set()
    for collection in (_FULL_BATCH_PLAN,_RUN_BATCHES,_DEFERRED_BATCH_QUEUE):
        for batch in collection:
            identity=id(batch)
            if identity in seen:
                continue
            seen.add(identity)
            if normalize_ui_text(str(batch.get("model", ""))) == "opus":
                batch["model"]=DEFAULT_LARGE_CASE_MODEL_FALLBACK
                changed+=1
    print(f"GLOBAL MODEL FALLBACK: Opus unavailable; disabled for all remaining queued/final-attempt work. Rewritten batches={changed}; fallback={DEFAULT_LARGE_CASE_MODEL_FALLBACK}",file=sys.stderr)

def confirm_batch_send(batches: Sequence[dict[str, Any]], required: bool) -> bool:
    if not required:
        print("CONFIRMATION GATE: bypassed by setting")
        return True
    print("=" * 78)
    print(f"READY TO CREATE AND SEND {len(batches)} TAB BATCH(ES).")
    print("Press Enter to continue (default), type Y, or type N to cancel safely.")
    print("=" * 78)
    try:
        answer = input("Send these batches? [Y/n]: ").strip().casefold()
    except EOFError:
        print("CONFIRMATION CANCELLED: interactive input was unavailable.")
        return False
    if answer in {"", "y", "yes"}:
        print("CONFIRMATION ACCEPTED: continuing.")
        return True
    print("CONFIRMATION DECLINED: no Edge tabs were created and nothing was sent.")
    return False


def confirm_processing_flow(required: bool) -> Optional[str]:
    """Second confirmation: choose sequential full-tab flow or legacy staged flow."""
    if not required:
        print("FLOW: sequential full-tab processing selected by default")
        return "sequential"
    print("=" * 78)
    print("SELECT PROCESSING FLOW")
    print("1 or Enter: Sequential full-tab flow (attach, model, message, send, then next tab)")
    print("2: Legacy staged flow (drop all, prepare/send-ready, then check/send)")
    print("N: Cancel safely")
    print("=" * 78)
    try:
        answer=input("Choose flow [1/2/N, default 1]: ").strip().casefold()
    except EOFError:
        print("FLOW CONFIRMATION CANCELLED: interactive input was unavailable.")
        return None
    if answer in {"", "1", "s", "sequential"}:
        print("FLOW SELECTED: sequential full-tab processing")
        return "sequential"
    if answer in {"2", "l", "legacy", "staged"}:
        print("FLOW SELECTED: legacy staged processing")
        return "staged"
    print("FLOW CONFIRMATION DECLINED: no Edge tabs were created and nothing was sent.")
    return None


async def verify_cdp_health(endpoint: str, attempts: int = DEFAULT_CDP_HEALTH_ATTEMPTS) -> None:
    last_error = "no response"
    for attempt in range(1, attempts + 1):
        payload = await asyncio.to_thread(get_cdp_version, endpoint)
        if payload is not None:
            print(f"CDP HEALTH: endpoint responsive on check {attempt}/{attempts}")
            return
        last_error = f"check {attempt}/{attempts} returned no usable version payload"
        await asyncio.sleep(DEFAULT_CDP_HEALTH_DELAY_SECONDS)
    raise RuntimeError(f"Edge CDP endpoint is unstable: {last_error}")


async def safe_preflight_edge_cleanup(context: BrowserContext) -> None:
    """Non-destructive preflight before V30 exact CDP target acquisition.

    Never close, navigate, reload, stop, or create a per-page CDP session here.
    V30 target creation must begin from a stable, unchanged browser target set.
    """
    live = [page for page in list(context.pages) if not page.is_closed()]
    blanks = sum(1 for page in live if is_blank_or_new_tab_url(page.url))
    content = len(live) - blanks
    gc.collect()
    print(f"EDGE STABILIZATION: non-destructive preflight complete; retained {len(live)} target(s) ({blanks} blank, {content} content)")
    print("EDGE STABILIZATION: no tab was closed, reloaded, navigated or given a cleanup CDP session")


async def stabilize_between_tabs(page: Page, endpoint: str) -> None:
    await collect_page_memory(page)
    try:
        await verify_cdp_health(endpoint, attempts=2)
    except RuntimeError as exc:
        print(f"CDP HEALTH WARNING: {exc}; continuing because the active page operation completed")
    await asyncio.sleep(DEFAULT_INTER_TAB_COOLDOWN_SECONDS)


async def ensure_live_browser_context(pw: Any, browser: Browser, context: BrowserContext, endpoint: str) -> tuple[Browser, BrowserContext]:
    """Return a live CDP browser/context, reconnecting once when Edge detached."""
    try:
        if browser.is_connected() and context.pages is not None:
            return browser, context
    except PlaywrightError:
        pass
    print("CDP RECOVERY: connection detached; reconnecting to the existing Edge session")
    await verify_cdp_health(endpoint, attempts=3)
    recovered_browser = await connect_existing_edge_with_retry(pw, endpoint)
    recovered_context = await get_existing_context(recovered_browser)
    return recovered_browser, recovered_context


async def initial_wake_and_readiness(pages: Sequence[Page], args: argparse.Namespace) -> list[bool]:
    """Wake all new tabs repeatedly for one shared six-second budget."""
    deadline=time.monotonic()+DEFAULT_INITIAL_READINESS_BUDGET_SECONDS
    ready=[False]*len(pages)
    round_number=0
    print(f"PHASE 1/3: waking all newly opened tabs for up to {DEFAULT_INITIAL_READINESS_BUDGET_SECONDS:.1f}s total")
    while time.monotonic() < deadline and not all(ready):
        round_number+=1
        for index,page in enumerate(pages):
            if page.is_closed():
                continue
            await activate_page_like_manual_selection(page,index+1,f"initial readiness wake round {round_number}")
            if not ready[index]:
                try:
                    ready[index]=(await first_visible([*editor_locators(page),*model_switcher_locators(page)],timeout_ms=0)) is not None
                except PlaywrightError:
                    ready[index]=False
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(DEFAULT_INITIAL_WAKE_DWELL_SECONDS)
    elapsed=DEFAULT_INITIAL_READINESS_BUDGET_SECONDS-max(0.0,deadline-time.monotonic())
    for index,state in enumerate(ready,1):
        print(f"PHASE 1/3 tab {index}/{len(pages)}: {'ready' if state else 'deferred to active phase'} within shared {elapsed:.2f}s readiness window")
    print("PHASE 1/3 readiness budget ended; continuing to active attachment phase without further global waiting")
    return ready


async def select_model_with_opus_fallback(page: Any, requested_model: str) -> str:
    """Use one run-global Opus attempt, then permanently use GPT after failure."""
    requested=requested_model.strip()
    effective=effective_model_name(requested)
    if effective != requested:
        await click_model_option(page,effective,FAST_MODEL_TIMEOUT_MS)
        print(f"GLOBAL MODEL FALLBACK ACTIVE: selected {effective} instead of {requested}")
        return effective
    if normalize_ui_text(requested) != "opus":
        await click_model_option(page,requested,FAST_MODEL_TIMEOUT_MS)
        return requested
    started=time.monotonic()
    try:
        await click_model_option(page,requested,min(FAST_MODEL_TIMEOUT_MS,1400))
        reward_technique("model","model:Opus",True,time.monotonic()-started)
        return requested
    except (PlaywrightError,RuntimeError) as exc:
        reward_technique("model","model:Opus",False,time.monotonic()-started)
        disable_opus_globally(exc)
        await click_model_option(page,DEFAULT_LARGE_CASE_MODEL_FALLBACK,FAST_MODEL_TIMEOUT_MS)
        reward_technique("model",f"model:{DEFAULT_LARGE_CASE_MODEL_FALLBACK}",True)
        print(f"MODEL FALLBACK: Opus unavailable once; selected {DEFAULT_LARGE_CASE_MODEL_FALLBACK} and disabled Opus globally")
        return DEFAULT_LARGE_CASE_MODEL_FALLBACK
async def reset_tab_to_fresh_chat(page: Page,args: argparse.Namespace,tab_number: int,reason: str) -> None:
    """Discard a poisoned unsent composer and reopen the base Copilot chat."""
    print(f"Tab {tab_number}: reloading into a fresh chat after {reason}",file=sys.stderr)
    invalidate_page_ui_cache(page)
    try:
        await page.goto(args.url,wait_until="commit",timeout=TAB_RELOAD_TIMEOUT_MS)
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        if _is_cdp_disconnect_error(exc):
            await wait_for_stable_cdp(cdp_endpoint(args.port), f"Tab {tab_number} fresh-chat navigation recovery")
        else:
            pass
    # Do not immediately reload after a committed goto. That double navigation
    # caused ERR_ABORTED/frame-detached failures on the final physical tab.
    await recover_active_tab(page,args,tab_number,"V18 fresh-chat recovery")
    count=await composer_attachment_count(page)
    error=await upload_error_message(page)
    if count or error:
        raise RuntimeError(f"Fresh chat validation failed: attachments={count}, upload_error={error!r}")

async def prefetch_next_tab_attachments(
    page: Page,batch: dict[str,Any],args: argparse.Namespace,tab_number: int
) -> None:
    """Attach exactly one next tab in the background with strict resource limits."""
    await asyncio.sleep(NEXT_TAB_PREFETCH_START_DELAY_SECONDS)
    if page.is_closed():
        raise RuntimeError(f"Next-tab prefetch could not use closed tab {tab_number}.")
    await background_wake_page(page)
    quick=await cached_first_visible(page,"editor",editor_locators(page),timeout_ms=350)
    if quick is None:
        # No reload here. Foreground recovery remains owned by the main flow.
        raise RuntimeError(f"Next-tab prefetch deferred because tab {tab_number} was not ready.")
    await attach_required_files(page,batch["paths"],args.page_timeout*1000)


@dataclass
class LegacyReloadPipelineState:
    """Exact slot/workload binding between result capture, drop-only and send."""
    physical_slot: int
    page_id: int
    batch: dict[str, Any]
    change_ids: tuple[str, ...]
    attachment_names: tuple[str, ...]
    message: str = ""
    prepared: bool = False
    dropped_at: float = 0.0

    def assert_current(self, page: Any, batch: dict[str, Any]) -> None:
        current_ids = tuple((row.get("change_id") or "").strip() for row in batch["rows"])
        if id(page) != self.page_id or batch is not self.batch or current_ids != self.change_ids:
            raise RuntimeError(
                f"Legacy slot {self.physical_slot + 1} workload binding changed; "
                "model/message insertion was blocked to prevent cross-tab mixing."
            )

@dataclass
class TabAssignmentState:
    """Mutable state for one immutable physical-page assignment generation."""
    page_id: int
    physical_slot: int
    generation: int
    token: str
    rows: tuple[dict[str, str], ...]
    change_ids: tuple[str, ...]
    baseline_title: str
    state: str = "SENT"
    title_changed_title: str = ""
    capture_task: Optional[asyncio.Task[Any]] = None

_ASSIGNMENTS: dict[int, TabAssignmentState] = {}
_ASSIGNMENT_GENERATIONS: dict[int, int] = {}
_WAKE_CYCLE_NUMBER = 0

def _normalized_title(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()

def _title_changed_from_assignment_baseline(state: TabAssignmentState, title: str) -> bool:
    current = _normalized_title(title)
    baseline = _normalized_title(state.baseline_title)
    if not current or current == baseline:
        return False
    # Any generic current title, including Chat | Microsoft Copilot, Microsoft
    # Copilot and New Chat, is never a real title-change completion signal.
    if generic_chat_title(title):
        return False
    return True

async def _cancel_assignment_capture(state: Optional[TabAssignmentState]) -> None:
    if state is None or state.capture_task is None:
        return
    task = state.capture_task
    state.capture_task = None
    if not task.done():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)

def _new_assignment(page: Any, physical_slot: int, rows: Sequence[dict[str, str]], baseline_title: str) -> TabAssignmentState:
    page_id = id(page)
    generation = _ASSIGNMENT_GENERATIONS.get(page_id, 0) + 1
    _ASSIGNMENT_GENERATIONS[page_id] = generation
    change_ids = tuple((row.get("change_id") or "").strip() for row in rows)
    token = f"{page_id}:{generation}:{'|'.join(change_ids)}"
    state = TabAssignmentState(page_id, physical_slot, generation, token, tuple(rows), change_ids, baseline_title or AUDIT_PENDING_TITLE, "WAITING_FOR_TITLE_CHANGE")
    _ASSIGNMENTS[page_id] = state
    _RUN_ROWS[page_id] = list(rows)
    return state

def _assignment_is_current(page: Any, token: str, change_ids: Sequence[str]) -> bool:
    current = _ASSIGNMENTS.get(id(page))
    return bool(current and current.token == token and current.change_ids == tuple(change_ids) and current.state not in {"REUSABLE", "REPLACED"})

def _latest_log_records_for_source(args: argparse.Namespace) -> tuple[list[dict[str, str]], dict[tuple[str, str], CaseLogRecord], set[str]]:
    rows = source_rows(args.csv_path)
    completed = read_change_ids(args.completed_path, "Completed change IDs")
    records = CaseLogStore(args.log_path).load(compact=False)
    return rows, records, completed

def eligible_source_rows(args: argparse.Namespace) -> list[dict[str, str]]:
    """Return source/allow-list intersection after exact-key latest-success exclusion."""
    rows, records, completed = _latest_log_records_for_source(args)
    selected: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        cid = canonical_change_id(row.get("change_id", ""))
        ipid = (row.get("InterestedPartyId") or "").strip().casefold()
        key = (cid, ipid)
        if not cid or cid not in completed or key in seen:
            continue
        seen.add(key)
        record = records.get(key)
        if record is not None and _status(record.status) == SUCCESS_STATUS:
            continue
        selected.append(row)
    return selected

async def _run_single_wave(args: argparse.Namespace) -> int:
    _PREPARED_COPILOT_PAGE_IDS.clear()
    _LEGACY_STAGED_NAMES_BY_PAGE.clear(); _LEGACY_STAGED_PATHS_BY_PAGE.clear()
    _LEGACY_FORCE_TRANSFER_LAST_AT.clear(); _LEGACY_FORCE_TRANSFER_ROUND.clear(); _UPLOAD_PROGRESS_BY_PAGE.clear()
    _CASE_FILES_CACHE.clear(); _FAILED_FILES_CACHE.clear(); _UNUSABLE_FILES_CACHE.clear(); _MERGED_PDF_CACHE.clear()
    _ATTACHMENT_PLAN_CACHE.clear(); _PAGE_UI_CACHE.clear(); _ATTACHMENT_ROUTE_BY_PAGE.clear(); _ATTACHMENT_FAILED_ROUTES_BY_PAGE.clear(); gc.collect()
    ensure_result_log_schema(args.log_path)
    result_run_number = next_result_run_number(args.log_path)
    size_path,rows,size_map=select_run_rows(args)
    args.case_size_by_change_id = {cid: entry.get("case_size", "") for cid, entry in size_map.items()}
    if not rows:
        print("No eligible change_id remains."); return 0
    batches=make_batches(rows,size_map,args)
    retry_generation=int(getattr(args,"retry_generation",0))
    batches=adapt_batches_for_generation(batches,args,retry_generation)
    global _RUN_BATCHES,_FULL_BATCH_PLAN,_DEFERRED_BATCH_QUEUE,_CURRENT_RETRY_GENERATION
    _CURRENT_RETRY_GENERATION=retry_generation
    limit=min(args.tabs,args.max_tabs,MAXIMUM_TAB_COUNT)
    _FULL_BATCH_PLAN=list(batches)
    _RUN_BATCHES=list(batches[:limit])
    _DEFERRED_BATCH_QUEUE=list(batches[limit:])
    for queued_batch in _DEFERRED_BATCH_QUEUE: queued_batch.setdefault("queue_kind","normal")
    batches=list(_RUN_BATCHES)
    print(f"WAVE CAPACITY: {len(_RUN_BATCHES)}/{len(_FULL_BATCH_PLAN)} batch(es) active; {len(_DEFERRED_BATCH_QUEUE)} batch(es) queued for immediate completed-tab reuse.")
    model_strategy = ("selected Sol policy" if getattr(args, "model_policy", "original") in {"sol_all", "sol_large"}
                      else "alternating GPT/Opus" if retry_generation>=ADAPTIVE_MODEL_SWITCH_GENERATION
                      else "category default")
    print(f"ADAPTIVE GENERATION {retry_generation}: max cases/tab={'1' if retry_generation>=ADAPTIVE_SINGLE_CASE_GENERATION else '2' if retry_generation else 'normal'}; model strategy={model_strategy}")
    if not getattr(args,"master_plan_printed",False):
        stage_heading("MASTER PLAN - ALL EXPECTED NORMAL RUNS")
        limit=min(args.tabs,args.max_tabs,MAXIMUM_TAB_COUNT)
        total=max(1,(len(_FULL_BATCH_PLAN)+limit-1)//limit)
        print(f"Expected normal runs: {total}; planned cases: {sum(len(x['rows']) for x in _FULL_BATCH_PLAN)}")
        for run_index in range(total):
            wave=_FULL_BATCH_PLAN[run_index*limit:(run_index+1)*limit]
            print(f"NORMAL RUN {run_index+1}/{total}: {len(wave)} tab(s), {sum(len(x['rows']) for x in wave)} case(s)")
            for tab_index,batch in enumerate(wave,1):
                ids=", ".join((row.get("change_id") or "").strip() for row in batch["rows"])
                print(f"  Tab {tab_index}: {batch['category']} | {ids} | {len(batch['paths'])}/20 | {batch['model']}")
        args.master_plan_printed=True
    rows=[row for batch in batches for row in batch["rows"]]
    print_distribution(size_path,rows,batches)
    if not confirm_batch_send(batches,args.confirm_send):
        return 0
    processing_flow=confirm_processing_flow(args.confirm_send)
    if processing_flow is None:
        return 0
    endpoint=cdp_endpoint(args.port)
    endpoint_available = get_cdp_version(endpoint) is not None
    startup_edge_stability_cleanup(args.profile_dir, endpoint_available)
    if not endpoint_available:
        if args.attach_only:
            print(f"ERROR: No Edge debugging session was found on port {args.port}.",file=sys.stderr); return 1
        launch_edge(find_edge_executable(args.edge_path),endpoint,args.port,args.profile_dir,tabs_visible=args.tabs_visible)
    else:
        validate_port_profile_ownership(args.port,args.profile_dir)
        print(f"TAB VISIBILITY: existing Edge session retained; requested visible={args.tabs_visible}")
    validate_dedicated_endpoint(endpoint,args.port)
    await verify_cdp_health(endpoint)
    terminal_failures:set[int]=set()
    async with async_playwright() as pw:
        browser=await connect_existing_edge_with_retry(pw,endpoint)
        context=await get_existing_context(browser); context.set_default_timeout(args.page_timeout*1000)
        stability_stop=asyncio.Event()
        stability_task=asyncio.create_task(
            edge_resource_stability_monitor(endpoint,args.profile_dir,stability_stop)
        )
        if args.safe_edge_cleanup:
            await safe_preflight_edge_cleanup(context)
        if not browser.is_connected():
            browser=await connect_existing_edge_with_retry(pw,endpoint)
            context=await get_existing_context(browser)
            context.set_default_timeout(args.page_timeout*1000)
        stage_heading(f"STAGE 1 - OPENING {len(batches)} COPILOT TABS")
        pages=await acquire_run_pages_fast(browser,context,len(batches))
        page_target_ids = [await page_target_id(page) for page in pages]
        recovery_lock = asyncio.Lock()
        cdp_recovery_generation = 0
        async def recover_cdp_and_rebind(reason: BaseException | str) -> None:
            """Reconnect once and mutate the existing page list without losing slot state."""
            nonlocal browser, context, cdp_recovery_generation
            async with recovery_lock:
                try:
                    already_healthy = browser.is_connected() and await _async_cdp_endpoint_healthy(endpoint)
                except PlaywrightError:
                    already_healthy = False
                if already_healthy:
                    try:
                        await asyncio.wait_for(get_existing_context(browser), timeout=1.0)
                        print("CDP REBIND: recovery avoided; browser and endpoint are healthy")
                        return
                    except Exception:
                        pass
                # Persistent sequential handshake retries without discarding workload.
                old_pages = list(pages)
                old_ids = [id(page) for page in old_pages]
                browser = await connect_existing_edge_with_retry(pw, endpoint)
                context = await get_existing_context(browser)
                context.set_default_timeout(args.page_timeout*1000)
                available = [page for page in list(context.pages) if not page.is_closed()]
                by_target = {}
                for candidate in available:
                    target = await page_target_id(candidate)
                    if target:
                        by_target[target] = candidate
                rebound = []
                used = set()
                for slot, target in enumerate(page_target_ids):
                    candidate = by_target.get(target)
                    if candidate is None:
                        old_url = old_pages[slot].url if slot < len(old_pages) else ""
                        candidate = next((p for p in available if id(p) not in used and p.url == old_url), None)
                    if candidate is None:
                        raise CDPConnectionLostError(f"CDP rebind could not recover physical slot {slot+1} target {target!r}")
                    rebound.append(candidate); used.add(id(candidate))
                for slot, (old_page, new_page) in enumerate(zip(old_pages, rebound)):
                    if id(old_page) == id(new_page):
                        continue
                    old_id=id(old_page); new_id=id(new_page)
                    if old_id in _RUN_ROWS: _RUN_ROWS[new_id]=_RUN_ROWS.pop(old_id)
                    if old_id in _CAPTURED_RESULTS: _CAPTURED_RESULTS[new_id]=_CAPTURED_RESULTS.pop(old_id)
                    if old_id in _ATTACHMENT_ROUTE_BY_PAGE: _ATTACHMENT_ROUTE_BY_PAGE[new_id]=_ATTACHMENT_ROUTE_BY_PAGE.pop(old_id)
                    if old_id in _ATTACHMENT_FAILED_ROUTES_BY_PAGE: _ATTACHMENT_FAILED_ROUTES_BY_PAGE[new_id]=_ATTACHMENT_FAILED_ROUTES_BY_PAGE.pop(old_id)
                    if old_id in _PAGE_UI_CACHE: _PAGE_UI_CACHE.pop(old_id, None)
                    state=_ASSIGNMENTS.pop(old_id, None)
                    if state is not None:
                        state.page_id=new_id; _ASSIGNMENTS[new_id]=state
                    if old_id in _ASSIGNMENT_GENERATIONS:
                        _ASSIGNMENT_GENERATIONS[new_id]=max(_ASSIGNMENT_GENERATIONS.get(new_id,0),_ASSIGNMENT_GENERATIONS.pop(old_id))
                pages[:] = rebound
                wake_pages[:] = [pages[state.physical_slot] for state in _ASSIGNMENTS.values() if state.physical_slot < len(pages)]
                cdp_recovery_generation += 1
                print(f"CDP REBIND COMPLETE generation {cdp_recovery_generation}: restored {len(pages)} physical slots; sent/assignment/queue/log state preserved")
        async def replace_unresponsive_slot_with_fresh_chat(
            slot_index: int,
            failed_page: Page,
            reason: BaseException | str,
        ) -> Page:
            """Replace one dead renderer at browser-context level, then continue same work.

            This bypasses page-local probes entirely. It is used immediately after the
            two bounded start checks fail, before attachment inspection, route scoring,
            or the older multi-step recovery can block fresh-chat recovery.
            """
            nonlocal context
            last_error: Optional[BaseException] = None
            for replacement_attempt in range(1, TAB_START_REPLACEMENT_ATTEMPTS + 1):
                fresh: Optional[Page] = None
                try:
                    print(
                        f"TAB START FRESH RECOVERY: slot {slot_index + 1} replacement "
                        f"{replacement_attempt}/{TAB_START_REPLACEMENT_ATTEMPTS} started; "
                        f"reason={concise_error(reason) or type(reason).__name__}",
                        file=sys.stderr,
                    )
                    fresh = await asyncio.wait_for(
                        context.new_page(),
                        timeout=TAB_START_FRESH_PAGE_CREATE_TIMEOUT_SECONDS,
                    )
                    try:
                        await fresh.goto(
                            args.url,
                            wait_until="commit",
                            timeout=int(TAB_START_FRESH_NAVIGATION_TIMEOUT_SECONDS * 1000),
                        )
                    except PlaywrightTimeoutError:
                        # A committed SPA navigation may outlive Playwright's load wait.
                        pass
                    await asyncio.wait_for(
                        wait_for_copilot_ui(
                            fresh,
                            int(TAB_START_FRESH_READY_TIMEOUT_SECONDS * 1000),
                            False,
                        ),
                        timeout=TAB_START_FRESH_READY_TIMEOUT_SECONDS + 0.50,
                    )
                    old_id = id(failed_page)
                    new_id = id(fresh)
                    invalidate_page_ui_cache(failed_page)
                    invalidate_page_ui_cache(fresh)
                    _ATTACHMENT_ROUTE_BY_PAGE.pop(old_id, None)
                    _ATTACHMENT_FAILED_ROUTES_BY_PAGE.pop(old_id, None)
                    _RUN_ROWS[new_id] = _RUN_ROWS.pop(old_id, batches[slot_index]["rows"])
                    old_state = _ASSIGNMENTS.pop(old_id, None)
                    if old_state is not None:
                        old_state.page_id = new_id
                        _ASSIGNMENTS[new_id] = old_state
                    pages[slot_index] = fresh
                    page_target_ids[slot_index] = await page_target_id(fresh)
                    if _UPLOAD_ACCELERATOR is not None:
                        await _UPLOAD_ACCELERATOR.replace_page(failed_page, fresh)
                    try:
                        await asyncio.wait_for(
                            failed_page.close(),
                            timeout=TAB_START_OLD_PAGE_CLOSE_TIMEOUT_SECONDS,
                        )
                    except (asyncio.TimeoutError, PlaywrightError):
                        pass
                    print(
                        f"TAB START FRESH RECOVERY: slot {slot_index + 1} replaced with "
                        f"a verified fresh Copilot chat on attempt {replacement_attempt}; "
                        "same workload and attachment route retained"
                    )
                    return fresh
                except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError, RuntimeError) as exc:
                    last_error = exc
                    if fresh is not None and fresh is not failed_page:
                        try:
                            await asyncio.wait_for(
                                fresh.close(), TAB_START_OLD_PAGE_CLOSE_TIMEOUT_SECONDS
                            )
                        except (asyncio.TimeoutError, PlaywrightError):
                            pass
                    print(
                        f"TAB START FRESH RECOVERY: slot {slot_index + 1} replacement "
                        f"{replacement_attempt} failed: {concise_error(exc) or type(exc).__name__}",
                        file=sys.stderr,
                    )
            raise RuntimeError(
                f"Slot {slot_index + 1} fresh-target replacement failed after "
                f"{TAB_START_REPLACEMENT_ATTEMPTS} attempts: "
                f"{concise_error(last_error or reason) or type(last_error or reason).__name__}"
            )

        async def legacy_reuse_drop_only(
            slot_index: int,
            replacement: dict[str, Any],
        ) -> LegacyReloadPipelineState:
            """Refresh one completed legacy slot and only drop its next attachments."""
            page = pages[slot_index]
            old_state = _ASSIGNMENTS.get(id(page))
            await _cancel_assignment_capture(old_state)
            await reset_tab_to_fresh_chat(
                page, args, slot_index + 1,
                "legacy captured-result recycle and drop-only refill",
            )
            _CAPTURED_RESULTS.pop(id(page), None)
            _ASSIGNMENTS.pop(id(page), None)
            invalidate_page_ui_cache(page)
            batches[slot_index] = replacement
            _RUN_ROWS[id(page)] = replacement["rows"]
            _ATTACHMENT_ROUTE_BY_PAGE[id(page)] = "bulk_cdp"
            _ATTACHMENT_FAILED_ROUTES_BY_PAGE.pop(id(page), None)
            names = await legacy_drop_attachment_plan(
                page, replacement["paths"], slot_index + 1
            )
            binding = LegacyReloadPipelineState(
                physical_slot=slot_index,
                page_id=id(page),
                batch=replacement,
                change_ids=tuple(
                    (row.get("change_id") or "").strip()
                    for row in replacement["rows"]
                ),
                attachment_names=tuple(names),
                dropped_at=time.monotonic(),
            )
            print(
                f"LEGACY RESULT-DRAIN REFILL: Tab {slot_index + 1} captured, refreshed, "
                f"and drop-only loaded for case(s) {', '.join(binding.change_ids)}; "
                "model/message deliberately deferred until every currently ready result is captured"
            )
            return binding

        async def legacy_prepare_and_send_refilled_slots(
            bindings: list[LegacyReloadPipelineState],
            active_slots: set[int],
            sent: set[int],
            wake_pages: list[Page],
        ) -> None:
            """After result draining, prepare exact bound workloads and send when ready."""
            pending = list(bindings)
            stagnant = 0
            previous_sent = -1
            sweep = 0
            while pending:
                sweep += 1
                completed_this_sweep = 0
                for binding in list(pending):
                    index = binding.physical_slot
                    page = pages[index]
                    batch = batches[index]
                    binding.assert_current(page, batch)
                    state, snapshot = await legacy_attachment_state(
                        page, binding.attachment_names, tab_number=index + 1,
                        reason='legacy refill sweep'
                    )
                    if state == "error":
                        binding.attachment_names = tuple(
                            await legacy_recover_attachment_failure(
                                page, batch, args, index + 1
                            )
                        )
                        binding.page_id = id(page)
                        binding.assert_current(page, batch)
                        state, snapshot = await legacy_attachment_state(
                            page, binding.attachment_names, tab_number=index + 1,
                            reason='legacy refill recovery sweep'
                        )
                    if not binding.prepared:
                        binding.message = await legacy_prepare_model_and_message(
                            page, batch, args
                        )
                        binding.prepared = True
                        binding.assert_current(page, batch)
                        print(
                            f"LEGACY REFILL PREPARED: Tab {index + 1}; exact case(s) "
                            f"{', '.join(binding.change_ids)}; attachments="
                            f"{snapshot.get('count', 0)}/{len(binding.attachment_names)}"
                        )
                        state, snapshot = await legacy_attachment_state(
                            page, binding.attachment_names, tab_number=index + 1,
                            reason='legacy refill recovery sweep'
                        )
                    dispatched, snapshot = await legacy_send_if_ready_now(
                        page, batch, args, index + 1, len(pages),
                        binding.attachment_names, binding.message,
                    )
                    if dispatched:
                        baseline = await _fast_title_v24(page) or AUDIT_PENDING_TITLE
                        assignment = _new_assignment(
                            page, index, batch["rows"], baseline
                        )
                        active_slots.add(index)
                        sent.add(index)
                        if page not in wake_pages:
                            wake_pages.append(page)
                        pending.remove(binding)
                        completed_this_sweep += 1
                        refill_remaining_cases = sum(
                            len(item.batch.get('rows', [])) for item in pending
                        ) + sum(len(item.get('rows', [])) for item in _DEFERRED_BATCH_QUEUE)
                        print(
                            f"LEGACY QUEUE PROGRESS: {refill_remaining_cases} case(s) remaining; "
                            f"refilled tabs pending={len(pending)}; queued batches={len(_DEFERRED_BATCH_QUEUE)}"
                        )
                        print(
                            f"LEGACY REFILL SENT: Tab {index + 1}; generation "
                            f"{assignment.generation}; binding verified; remaining="
                            f"{len(pending)}"
                        )
                    else:
                        print(
                            f"LEGACY REFILL LOADING: Tab {index + 1}; exact case(s) "
                            f"{', '.join(binding.change_ids)}; attachments="
                            f"{snapshot.get('count', 0)}/{len(binding.attachment_names)}; "
                            "moving to next refilled tab"
                        )
                sent_total = len(bindings) - len(pending)
                stagnant = stagnant + 1 if sent_total == previous_sent else 0
                previous_sent = sent_total
                if pending and stagnant >= LEGACY_REUSE_MAX_STAGNANT_SWEEPS:
                    for binding in pending:
                        binding.assert_current(pages[binding.physical_slot], batches[binding.physical_slot])
                        await recover_stalled_attachment_transfer(
                            pages[binding.physical_slot],
                            binding.attachment_names,
                            "foreground_wake",
                        )
                    stagnant = 0
                if pending:
                    await asyncio.sleep(LEGACY_REUSE_PREP_SWEEP_DELAY_SECONDS)

        prepared_pages, pages_requiring_navigation = partition_startup_pages(pages)
        prepared_count = len(prepared_pages)
        if not pages_requiring_navigation:
            warnings = [None] * len(pages)
            readiness = [True] * len(pages)
            print(
                f"PRELOADED COPILOT MODE: {prepared_count}/{len(pages)} selected tabs were "
                "already manually loaded at the Copilot Chat URL; navigation, SHARED "
                "READINESS WAIT and the initial activation wave are fully bypassed"
            )
        else:
            print(
                f"MIXED STARTUP MODE: preserving {prepared_count}/{len(pages)} manually "
                f"prepared Copilot tab(s); navigating only {len(pages_requiring_navigation)} "
                "blank/new tab(s)"
            )
            semaphore=asyncio.Semaphore(max(1,len(pages_requiring_navigation)))
            navigation_warnings=await asyncio.gather(*(
                navigate_page(page,args.url,semaphore,args.page_timeout*1000)
                for page in pages_requiring_navigation
            ))
            navigated_readiness=await initial_wake_and_readiness(pages_requiring_navigation,args)
            warnings=[]
            readiness=[]
            warning_by_id={id(page):warning for page,warning in zip(pages_requiring_navigation,navigation_warnings)}
            ready_by_id={id(page):ready for page,ready in zip(pages_requiring_navigation,navigated_readiness)}
            for page in pages:
                if page_was_prepared_copilot(page):
                    warnings.append(None); readiness.append(True)
                else:
                    warnings.append(warning_by_id.get(id(page))); readiness.append(ready_by_id.get(id(page),False))
            for index,warning in enumerate(warnings,1):
                if warning: print(f"Tab {index} navigation warning: {warning}")
            print(
                f"PHASE 1/3 complete: preserved {prepared_count} prepared tab(s); "
                f"{sum(navigated_readiness)}/{len(pages_requiring_navigation)} newly navigated tab(s) ready"
            )
        if getattr(args, "default_model", None):
            # Fail before the first attachment or message if this tenant cannot
            # select the user's exact model. Separate pages are safe to inspect
            # concurrently and no additional browser tabs are created.
            print(f"VERIFYING SELECTED MODEL BEFORE UPLOADS: {args.default_model}")
            await asyncio.gather(*(click_model_option(page, args.default_model, FAST_MODEL_TIMEOUT_MS)
                                   for page in pages))
        global _UPLOAD_ACCELERATOR
        _UPLOAD_ACCELERATOR = CopilotUploadAccelerator(
            pages, 'sequential option 1' if processing_flow == 'sequential' else 'legacy option 2'
        )
        await _UPLOAD_ACCELERATOR.start()
        attached:set[int]=set()
        sent:set[int]=set()
        wake_pages:list[Page]=[]
        wake_stop=asyncio.Event()
        wake_task:Optional[asyncio.Task[Any]]=None
        prefetched:set[int]=set()
        prefetch_task:Optional[asyncio.Task[Any]]=None
        prefetch_index:Optional[int]=None

        async def complete_one_tab(i: int,page: Page,batch: dict[str,Any]) -> None:
            ids=", ".join((row.get("change_id") or "").strip() for row in batch["rows"])
            step_heading(f"TAB {i}/{len(pages)} - {batch['category']} - changes {ids} - {len(batch['paths'])} files")
            print("  Instructions: 1 Markdown file")
            print(f"  Merged PDFs: {sum(len(related_document_paths(row,args.merged_pdfs_root)) for row in batch['rows'])}")
            for row in batch["rows"]:
                change_id=(row.get("change_id") or "").strip()
                suffix=" (complete Small add-on)" if change_id in batch.get("complete_small_addon_ids",[]) else ""
                print(f"    change_id {change_id}: {batch['counts'].get(change_id,0)} other file(s){suffix}")
            await ensure_tab_start_progress(page,args,i,"full-tab processing")
            baseline_title = await _fast_title_v24(page) or AUDIT_PENDING_TITLE
            message=build_dynamic_message(batch["rows"],batch["category"],args,batch["counts"],batch["failed_total"],batch["paths"])
            names=[p.name for p in batch["paths"]]

            # Preferred quick route: add the whole attachment plan in one bulk
            # selection, then immediately select the model and insert the base
            # message while the attached files continue transferring.
            if i-1 not in prefetched:
                await attach_required_files(
                    page,batch["paths"],args.page_timeout*1000,
                    wait_for_transfer=False,
                )
            attached.add(i-1)
            print(f"Attachments {i}/{len(pages)}: added in bulk ({len(batch['paths'])} files); model/message preparation started while files load")
            nonlocal prefetch_task,prefetch_index
            await select_model_with_opus_fallback(page,batch["model"])
            await retry_async("Message insertion",lambda:add_text_to_editor(page,message,FAST_MESSAGE_TIMEOUT_MS),attempts=5,delay_seconds=0.015)

            # Only the first bulk attempt uses the short 15-second window.
            # Every sequential or final-attempt retry gets a 50-second window.
            bulk_finished=False
            current_route=attachment_route_for_page(page)
            first_bulk_attempt=(
                current_route == "bulk_cdp"
                and int(batch.get("retry_generation",0)) == 0
                and "bulk_cdp" not in _ATTACHMENT_FAILED_ROUTES_BY_PAGE.get(id(page),set())
            )
            transfer_timeout_seconds=(
                FIRST_BULK_TRANSFER_TIMEOUT_SECONDS
                if first_bulk_attempt else RETRY_TRANSFER_TIMEOUT_SECONDS
            )
            try:
                await asyncio.wait_for(
                    wait_until_attachments_upload_finished(
                        page,names,int(transfer_timeout_seconds*1000)
                    ),
                    timeout=transfer_timeout_seconds+0.25,
                )
                bulk_finished=True
            except (asyncio.TimeoutError, FreshChatRequiredError) as upload_exc:
                direct_error=await upload_error_message(page)
                if direct_error:
                    raise FreshChatRequiredError(
                        f"{current_route} upload reported a direct error; refresh and sequential retry required: {direct_error}"
                    ) from upload_exc

            if not bulk_finished:
                print(
                    f"Tab {i}: {current_route} upload exceeded {transfer_timeout_seconds:.0f} seconds "
                    "without a direct error; refreshing and repeating the complete process sequentially"
                )
                invalidate_page_ui_cache(page)
                try:
                    await page.reload(wait_until="commit",timeout=TAB_RELOAD_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    pass
                await recover_active_tab(page,args,i,f"{transfer_timeout_seconds:.0f}-second transfer timeout sequential retry")
                # The retry is intentionally limited to this same case and tab.
                _ATTACHMENT_ROUTE_BY_PAGE[id(page)]="sequential_cdp"
                _ATTACHMENT_FAILED_ROUTES_BY_PAGE.setdefault(id(page),set()).add("bulk_cdp")
                await attach_required_files(
                    page,batch["paths"],args.page_timeout*1000,
                    wait_for_transfer=False,
                )
                print(f"Tab {i}: sequential retry attachments added ({len(batch['paths'])} files)")
                await select_model_with_opus_fallback(page,batch["model"])
                await retry_async("Sequential retry message insertion",lambda:add_text_to_editor(page,message,FAST_MESSAGE_TIMEOUT_MS),attempts=5,delay_seconds=0.015)
                print(f"Tab {i}: sequential retry model and base message prepared")

            # Remain visibly on this tab, waking it as required, until every file
            # is fully transferred and Send has changed to Stop generating.
            await activate_page_like_manual_selection(page,i,"foreground attachment completion and send")
            await wait_until_attachments_upload_finished(page,names,SINGLE_CASE_UPLOAD_FINISH_TIMEOUT_MS)
            await retry_async("Send and Stop-generating confirmation",lambda:send_and_confirm(page,message,names,SINGLE_CASE_SEND_TIMEOUT_MS),attempts=3,delay_seconds=0.10)
            if not await stop_button_present(page):
                raise RuntimeError("Send was not confirmed because Stop generating was not detected.")
            print(
                f"{TERMINAL_WHITE_ON_YELLOW} MESSAGE SENT: Tab {i} Send changed to Stop generating "
                f"{TERMINAL_STYLE_RESET}"
            )
            # Commit the confirmed send first. Optional next-tab foreground work
            # must never sit between Stop-generating proof and durable progression.
            assignment = await commit_confirmed_send_state(
                page, i-1, batch, args, sent, wake_pages, baseline_title
            )
            print(f"Tab {i}: assignment generation {assignment.generation} SENT -> WAITING_FOR_TITLE_CHANGE; baseline title={assignment.baseline_title!r}")
            print(f"Send {i}/{len(pages)}: confirmed by Stop generating and logged; background wake active")
            if processing_flow=="sequential" and i < len(pages):
                try:
                    await asyncio.wait_for(
                        fast_post_send_handoff(pages[i], i+1),
                        timeout=POST_SEND_HANDOFF_TOTAL_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    print(
                        f"POST-SEND HANDOFF WATCHDOG: Tab {i+1} activation exceeded "
                        f"{POST_SEND_HANDOFF_TOTAL_TIMEOUT_SECONDS:.1f}s; starting its workload immediately",
                        file=sys.stderr,
                    )
                print(f"Tab {i+1}/{len(pages)}: queue advanced immediately after tab {i} send")
        async def complete_one_tab_resilient(i: int,page: Page,batch: dict[str,Any]) -> None:
            """Make one tab useful for this workload using fresh independent routes.

            Route failures belong to one workload only. Reusing a physical tab must
            never inherit the exhausted-route set from the previous case batch.
            """
            _ATTACHMENT_ROUTE_BY_PAGE.pop(id(page), None)
            _ATTACHMENT_FAILED_ROUTES_BY_PAGE.pop(id(page), None)
            invalidate_page_ui_cache(page)
            last_error: Optional[BaseException]=None
            for recovery_round in range(1,MAX_FRESH_CHAT_RECOVERY_ROUNDS+CDP_OPERATION_RETRIES+1):
                route=next_unused_attachment_route(page)
                if route=="playwright_bulk" and any(path.stat().st_size>50*1024*1024 for path in batch["paths"]):
                    record_failed_attachment_route(page,route)
                    print(f"Tab {i}: skipping playwright_bulk because this workload contains file(s) over 50 MB")
                    route=next_unused_attachment_route(page)
                if route is None: break
                _ATTACHMENT_ROUTE_BY_PAGE[id(page)]=route
                route_started=time.monotonic()
                try:
                    await complete_one_tab(i,page,batch)
                    reward_technique("attachment",route,True,time.monotonic()-route_started)
                    print(f"ADAPTIVE attachment preferred order: {', '.join(technique_rank('attachment',ATTACHMENT_RECOVERY_ROUTES))}")
                    return
                except (FreshChatRequiredError,PlaywrightError,RuntimeError,FileNotFoundError,asyncio.TimeoutError) as exc:
                    last_error=exc
                    if isinstance(exc, TabStartFreshChatRequiredError):
                        # Critical fast path: do not inspect attachment chips or call
                        # page-local recovery on a renderer already proved unresponsive.
                        # Replace the target immediately and retry the same workload.
                        page = await replace_unresponsive_slot_with_fresh_chat(i-1, page, exc)
                        _ATTACHMENT_ROUTE_BY_PAGE[id(page)] = route
                        print(
                            f"Tab {i}: fresh-chat recovery completed immediately after "
                            f"two failed start checks; retrying route {route} now"
                        )
                        continue
                    if _is_cdp_disconnect_error(exc) or get_cdp_version(endpoint) is None:
                        print(f"Tab {i}: transient CDP loss detected; preserving workload, attachment route and durable status before reconnect", file=sys.stderr)
                        await recover_cdp_and_rebind(exc)
                        page = pages[i-1]
                        invalidate_page_ui_cache(page)
                        # Retry the same route after rebinding. Do not mark it failed,
                        # reset its route history, dequeue another case, or lose status.
                        continue
                    # Never use an empty composer as proof here. A fresh/reloaded
                    # chat is empty by definition and previously caused dangerous
                    # false-positive logging. Require transaction-specific evidence.
                    planned_count=len(batch["paths"]); observed_count=await stable_attachment_count(page,0.40)
                    if observed_count>=planned_count and not await upload_error_message(page):
                        reward_technique("attachment",route,True,time.monotonic()-route_started)
                        print(f"Tab {i}: post-attachment operation failed with {observed_count}/{planned_count} clean chips; preserving attachments ({concise_error(exc)})",file=sys.stderr)
                        for operation_attempt in range(1,POST_ATTACHMENT_OPERATION_ATTEMPTS+1):
                            try:
                                await activate_page_like_manual_selection(page,i,"post-attachment recovery")
                                recovery_message=build_dynamic_message(batch["rows"],batch["category"],args,batch["counts"],batch["failed_total"],batch["paths"])
                                await select_model_with_opus_fallback(page,batch["model"])
                                editor=await cached_first_visible(page,"editor",editor_locators(page),350)
                                if editor is not None and recovery_message not in await editor_text(editor): await add_text_to_editor(page,recovery_message,FAST_MESSAGE_TIMEOUT_MS)
                                names=[path.name for path in batch["paths"]]
                                await wait_until_attachments_upload_finished(page,names,SINGLE_CASE_UPLOAD_FINISH_TIMEOUT_MS)
                                await send_and_confirm(page,recovery_message,names,SINGLE_CASE_SEND_TIMEOUT_MS)
                                if not await stop_button_present(page):
                                    raise RuntimeError("Send recovery was not confirmed because Stop generating was not detected.")
                                print(
                                    f"{TERMINAL_WHITE_ON_YELLOW} MESSAGE SENT: Tab {i} Send changed to Stop generating "
                                    f"{TERMINAL_STYLE_RESET}"
                                )
                                for row in batch["rows"]: append_fully_sent_log(args.log_path,row)
                                sent.add(i-1); wake_pages.append(page)
                                assignment=_new_assignment(page,i-1,batch["rows"],await _fast_title_v24(page) or AUDIT_PENDING_TITLE)
                                print(f"Tab {i}: post-attachment recovery succeeded on attempt {operation_attempt}; generation {assignment.generation}")
                                return
                            except (PlaywrightError,RuntimeError,asyncio.TimeoutError) as recovery_exc:
                                last_error=recovery_exc
                                if await upload_error_message(page): break
                                await asyncio.sleep(0.10)
                    recovery_message=build_dynamic_message(
                        batch["rows"],batch["category"],args,
                        batch["counts"],batch["failed_total"],batch["paths"]
                    )
                    if await strict_send_transaction_accepted(page,recovery_message):
                        for row in batch["rows"]:
                            append_fully_sent_log(args.log_path,row)
                        sent.add(i-1); wake_pages.append(page)
                        print(f"Send {i}/{len(pages)}: exact prompt submission proved during recovery and logged")
                        return
                    reward_technique("attachment",route,False,time.monotonic()-route_started)
                    record_failed_attachment_route(page,route)
                    print(f"Tab {i}: route {route} failed; switching safely ({concise_error(exc)}); adaptive={technique_summary('attachment')}",file=sys.stderr)
                    if recovery_round < MAX_FRESH_CHAT_RECOVERY_ROUNDS:
                        await reset_tab_to_fresh_chat(page,args,i,f"route {route} failure")
            raise RuntimeError(f"Tab {i} exhausted all fresh-chat attachment routes for the current workload. Last error: {concise_error(last_error or 'no route executed; route state was reset defensively')}")

        if processing_flow=="sequential":
            stage_heading("STAGE 2 OF 2 - CONTINUOUS QUEUE")
            slot=0
            while slot<len(pages):
                page=pages[slot]; batch=batches[slot]; number=slot+1
                try:
                    await complete_one_tab_resilient(number,page,batch)
                    if wake_task is None:
                        wake_task=asyncio.create_task(continuous_sent_tab_wake(wake_pages,wake_stop))
                    slot+=1
                except (PlaywrightError,RuntimeError,FileNotFoundError) as exc:
                    if _is_cdp_disconnect_error(exc) or get_cdp_version(endpoint) is None:
                        await recover_cdp_and_rebind(exc)
                        print(f"TAB {number}: CDP rebound; retrying the same current batch without changing queue or status")
                        continue
                    failure_status="Failed_to_add_attachments" if any(x in str(exc).casefold() for x in ("attach","upload","file input","file-input")) else "inconclusive_review_needed"
                    for row in batch["rows"]:
                        CaseLogStore(args.log_path).upsert(row,failure_status,result_run_number)
                    report=await capture_attachment_diagnostics(page,number,"continuous_queue_failure",exc,[p.name for p in batch["paths"]])
                    # Claim older queued work before appending this failed batch.
                    # This prevents an empty queue from immediately returning the
                    # same poisoned workload to the same physical tab.
                    replacement=dequeue_next_batch() if not page.is_closed() else None
                    queued_retry=enqueue_retry_batch(batch, f"initial processing failure: {concise_error(exc)}", args)
                    print(f"TAB {number} MOVED TO FINAL ATTEMPTS: {concise_error(exc)}; queued={'yes' if queued_retry else 'already queued'}")
                    print(f"Diagnostic report: {report}")
                    # Continue with older queued work first. The failed workload is
                    # retained at the tail for a later adaptive generation/route.
                    if replacement is not None:
                        try:
                            await reset_tab_to_fresh_chat(page,args,number,"universal queue reassignment after failed processing")
                            batches[slot]=replacement
                            _RUN_ROWS[id(page)]=replacement["rows"]
                            ids=", ".join((r.get("change_id") or "").strip() for r in replacement["rows"])
                            print(f"TAB {number} REUSED IMMEDIATELY: {batch_queue_label(replacement)} | case(s) {ids} | category {replacement['category']}")
                            continue
                        except (PlaywrightError,RuntimeError) as reset_error:
                            # The claimed work is returned to the front. Another
                            # free tab may take it without changing its attempt state.
                            _DEFERRED_BATCH_QUEUE.insert(0,replacement)
                            print(f"TAB {number} LOCKED/UNAVAILABLE AFTER RESET: {concise_error(reset_error)}; claimed work returned to queue",file=sys.stderr)
                    terminal_failures.add(slot); slot+=1
        else:
            # Legacy flow is deliberately split into three strict stages:
            # 1) drop all attachment plans, 2) prepare every composer and dispatch
            # any tab already ready, 3) repeatedly check remaining prepared tabs.
            stage_heading("LEGACY STAGE 1 OF 3 - BULK DROP ATTACHMENTS INTO ALL TABS")
            legacy_names: dict[int, tuple[str, ...]] = {}
            legacy_messages: dict[int, str] = {}
            legacy_prepared: set[int] = set()
            legacy_pending: set[int] = set()
            legacy_failed: set[int] = set()
            legacy_sent: set[int] = set()

            def legacy_remaining_case_count() -> int:
                active_remaining = sum(
                    len(batches[slot]['rows'])
                    for slot in legacy_pending
                    if slot < len(batches)
                )
                queued_remaining = sum(
                    len(queued.get('rows', []))
                    for queued in _DEFERRED_BATCH_QUEUE
                )
                return active_remaining + queued_remaining

            def print_legacy_queue_progress(context: str) -> None:
                print(
                    f"LEGACY QUEUE PROGRESS: {legacy_remaining_case_count()} case(s) "
                    f"remaining after {context}; active tabs pending={len(legacy_pending)}; "
                    f"queued batches={len(_DEFERRED_BATCH_QUEUE)}"
                )

            async def legacy_record_sent(index: int, page: Page, batch: dict[str, Any]) -> None:
                legacy_pending.discard(index)
                legacy_sent.add(index)
                sent.add(index)
                if page not in wake_pages:
                    wake_pages.append(page)
                baseline = await _fast_title_v24(page) or AUDIT_PENDING_TITLE
                _new_assignment(page, index, batch['rows'], baseline)
                print_legacy_queue_progress(f"sending Tab {index + 1}")

            async def legacy_reload_drop_prepare(
                index: int,
                page: Page,
                batch: dict[str, Any],
                reason: str,
            ) -> tuple[tuple[str, ...], str, bool]:
                """Return one errored tab to stage 2: refresh, attach, prepare, send if ready."""
                number = index + 1
                print(
                    f"LEGACY STAGE-2 RECOVERY: Tab {number} attachment error detected; "
                    "refreshing, adding the complete plan, then restoring its exact model/message",
                    file=sys.stderr,
                )
                # Reset route history because this is a new composer. If the current
                # renderer cannot recreate any chips, replace this physical target.
                # A reload is insufficient when the file-input/upload pipeline itself
                # has become poisoned, as happened to Tab 2 in the v61 run.
                try:
                    await reset_tab_to_fresh_chat(page, args, number, reason)
                    _ATTACHMENT_ROUTE_BY_PAGE[id(page)] = 'bulk_cdp'
                    _ATTACHMENT_FAILED_ROUTES_BY_PAGE.pop(id(page), None)
                    names = await legacy_drop_attachment_plan(page, batch['paths'], number)
                except (FreshChatRequiredError, PlaywrightError, RuntimeError, asyncio.TimeoutError) as first_drop_error:
                    print(
                        f"LEGACY ZERO-CHIP TARGET REPLACEMENT: Tab {number} could not "
                        f"re-establish its attachment plan after refresh "
                        f"({concise_error(first_drop_error)}); replacing only this target",
                        file=sys.stderr,
                    )
                    page = await replace_unresponsive_slot_with_fresh_chat(index, page, first_drop_error)
                    pages[index] = page
                    _ATTACHMENT_ROUTE_BY_PAGE[id(page)] = 'bulk_cdp'
                    _ATTACHMENT_FAILED_ROUTES_BY_PAGE.pop(id(page), None)
                    names = await legacy_drop_attachment_plan(page, batch['paths'], number)
                confirmed = await stable_attachment_count(page, 0.75)
                if confirmed <= 0:
                    raise FreshChatRequiredError(
                        f"Tab {number} recovery returned without attachment chips."
                    )
                legacy_names[index] = tuple(names)
                legacy_prepared.discard(index)
                legacy_messages.pop(index, None)
                message = await legacy_prepare_model_and_message(page, batch, args)
                legacy_messages[index] = message
                legacy_prepared.add(index)
                if not await legacy_composer_is_prepared(page, message, batch['model']):
                    raise RuntimeError(
                        f"Tab {number} did not retain its exact model and base message after attachment recovery."
                    )
                dispatched, _ = await legacy_send_if_ready_now(
                    page, batch, args, number, len(pages), names, message
                )
                if dispatched:
                    await legacy_record_sent(index, page, batch)
                else:
                    legacy_pending.add(index)
                    print(
                        f"LEGACY STAGE-2 RECOVERY READY: Tab {number} model/message restored; "
                        "attachments are still loading, moving immediately to the next tab"
                    )
                return tuple(names), message, dispatched

            # STAGE 1: Drop only. Never prepare a model/message and never wait for
            # transfer completion. Every usable physical tab is visited once.
            for index, (page, batch) in enumerate(zip(pages, batches)):
                number = index + 1
                ids = ", ".join((row.get('change_id') or '').strip() for row in batch['rows'])
                step_heading(
                    f"LEGACY DROP TAB {number}/{len(pages)} - {batch['category']} - "
                    f"changes {ids} - {len(batch['paths'])} files"
                )
                try:
                    await ensure_tab_start_progress(page, args, number, 'legacy stage-1 attachment drop')
                    _ATTACHMENT_ROUTE_BY_PAGE[id(page)] = 'bulk_cdp'
                    names = await legacy_drop_attachment_plan(page, batch['paths'], number)
                    legacy_names[index] = tuple(names)
                    attached.add(index)
                    legacy_pending.add(index)
                except TabStartFreshChatRequiredError as exc:
                    try:
                        page = await replace_unresponsive_slot_with_fresh_chat(index, page, exc)
                        pages[index] = page
                        _ATTACHMENT_ROUTE_BY_PAGE[id(page)] = 'bulk_cdp'
                        names = await legacy_drop_attachment_plan(page, batch['paths'], number)
                        legacy_names[index] = tuple(names)
                        attached.add(index)
                        legacy_pending.add(index)
                    except Exception as recovery_exc:
                        legacy_failed.add(index); terminal_failures.add(index)
                        print(f"LEGACY STAGE-1 FAILURE - TAB {number}: {concise_error(recovery_exc)}", file=sys.stderr)
                except (FreshChatRequiredError, PlaywrightError, RuntimeError, FileNotFoundError, asyncio.TimeoutError) as exc:
                    # Stage 1 records the failure but does not prepare the composer.
                    # Stage 2 owns refresh/drop/prepare recovery as requested.
                    legacy_names[index] = tuple(path.name for path in batch['paths'])
                    legacy_pending.add(index)
                    print(
                        f"LEGACY STAGE-1 DROP WARNING - TAB {number}: {concise_error(exc)}; "
                        "stage 2 will refresh, reattach and prepare this tab",
                        file=sys.stderr,
                    )

            print_legacy_queue_progress("stage 1 attachment drops")
            stage_heading("LEGACY STAGE 2 OF 3 - PREPARE MODEL AND BASE MESSAGE")
            # STAGE 2: Visit every unsent tab exactly once. Attachment errors are
            # recovered before preparation. Clean loading tabs are prepared in place.
            for index in sorted(tuple(legacy_pending)):
                page = pages[index]
                batch = batches[index]
                number = index + 1
                names = legacy_names[index]
                try:
                    await ensure_tab_start_progress(page, args, number, 'legacy stage-2 preparation')
                    state, snapshot = await legacy_attachment_state(page, names, tab_number=number, reason='legacy stage sweep')
                    stage1_missing = int(snapshot.get('count', 0)) == 0 and bool(names)
                    if state == 'error' or stage1_missing:
                        reason = (
                            f"legacy stage-2 attachment error: {snapshot.get('error', '')}"
                            if state == 'error'
                            else "legacy stage-1 drop produced no attachment chips"
                        )
                        await legacy_reload_drop_prepare(index, page, batch, reason)
                        continue
                    message = await legacy_prepare_model_and_message(page, batch, args)
                    legacy_messages[index] = message
                    legacy_prepared.add(index)
                    if not await legacy_composer_is_prepared(page, message, batch['model']):
                        raise RuntimeError(
                            f"Tab {number} did not retain its exact live model and base message."
                        )
                    print(
                        f"LEGACY STAGE-2 PREPARED: Tab {number}; attachments="
                        f"{snapshot.get('count', 0)}/{len(names)}; state={state}"
                    )
                    # Recheck immediately because the upload may have completed while
                    # model selection and message insertion were happening.
                    dispatched, snapshot = await legacy_send_if_ready_now(
                        page, batch, args, number, len(pages), names, message
                    )
                    if dispatched:
                        await legacy_record_sent(index, page, batch)
                    else:
                        print(
                            f"LEGACY STAGE-2 CONTINUE: Tab {number} prepared but still loading "
                            f"({snapshot.get('count', 0)}/{len(names)}); moving to the next tab"
                        )
                except TabStartFreshChatRequiredError as exc:
                    try:
                        page = await replace_unresponsive_slot_with_fresh_chat(index, page, exc)
                        pages[index] = page
                        await legacy_reload_drop_prepare(
                            index, page, batch, 'legacy stage-2 unresponsive-tab replacement'
                        )
                    except Exception as recovery_exc:
                        legacy_pending.discard(index); legacy_failed.add(index); terminal_failures.add(index)
                        print(f"LEGACY STAGE-2 RECOVERY FAILURE - TAB {number}: {concise_error(recovery_exc)}", file=sys.stderr)
                except (FreshChatRequiredError, PlaywrightError, RuntimeError, FileNotFoundError, asyncio.TimeoutError) as exc:
                    # Any direct attachment alert returns to the same stage-2 recovery.
                    direct_error = await upload_error_message(page)
                    if direct_error:
                        try:
                            await legacy_reload_drop_prepare(
                                index, page, batch, f"legacy stage-2 direct upload error: {direct_error}"
                            )
                        except Exception as recovery_exc:
                            legacy_pending.discard(index); legacy_failed.add(index); terminal_failures.add(index)
                            print(f"LEGACY STAGE-2 RECOVERY FAILURE - TAB {number}: {concise_error(recovery_exc)}", file=sys.stderr)
                    else:
                        # Preparation itself failed without an attachment alert. Keep
                        # the tab pending, clear stale preparation state, and let stage
                        # 3 restore it before any send check.
                        legacy_prepared.discard(index)
                        legacy_messages.pop(index, None)
                        print(
                            f"LEGACY STAGE-2 PREPARATION RETRY - TAB {number}: {concise_error(exc)}; "
                            "stage 3 will restore this exact tab/case binding",
                            file=sys.stderr,
                        )

            stage_heading("LEGACY STAGE 3 OF 3 - CHECK PREPARED TABS AND SEND")
            stagnant_rounds = 0
            previous_sent_count = len(legacy_sent)
            check_round = 0
            while legacy_pending:
                check_round += 1
                print(
                    f"LEGACY CHECK {check_round}: pending={len(legacy_pending)}, "
                    f"prepared={len(legacy_prepared)}, sent={len(legacy_sent)}"
                )
                for index in sorted(tuple(legacy_pending)):
                    page = pages[index]
                    batch = batches[index]
                    number = index + 1
                    names = legacy_names[index]
                    try:
                        await ensure_tab_start_progress(page, args, number, 'legacy stage-3 check')
                        state, snapshot = await legacy_attachment_state(page, names, tab_number=number, reason='legacy stage sweep')
                        zero_chip_plan = int(snapshot.get('count', 0)) == 0 and bool(names)
                        if state == 'error' or zero_chip_plan:
                            recovery_reason = (
                                f"legacy stage-3 attachment error: {snapshot.get('error', '')}"
                                if state == 'error'
                                else "legacy stage-3 detected a lost complete attachment plan (0 chips)"
                            )
                            names, restored_message, dispatched = await legacy_reload_drop_prepare(
                                index, page, batch, recovery_reason,
                            )
                            page = pages[index]
                            legacy_names[index] = tuple(names)
                            legacy_messages[index] = restored_message
                            if dispatched:
                                continue
                            # Never continue polling a recovered tab with stale 0/N state.
                            continue
                        message = legacy_messages.get(index, '')
                        prepared_live = (
                            index in legacy_prepared
                            and await legacy_composer_is_prepared(page, message, batch['model'])
                        )
                        if not prepared_live:
                            # Return to stage 2 semantics for this one tab only.
                            print(
                                f"LEGACY STAGE-3 -> STAGE-2: Tab {number} is not fully prepared; "
                                "restoring its exact model and base message before checking send"
                            )
                            message = await legacy_prepare_model_and_message(page, batch, args)
                            legacy_messages[index] = message
                            legacy_prepared.add(index)
                            if not await legacy_composer_is_prepared(page, message, batch['model']):
                                raise RuntimeError(
                                    f"Tab {number} still lacks its exact model/base message after restoration."
                                )
                        dispatched, snapshot = await legacy_send_if_ready_now(
                            page, batch, args, number, len(pages), names, message
                        )
                        if dispatched:
                            await legacy_record_sent(index, page, batch)
                        else:
                            print(
                                f"LEGACY CHECK LOADING: Tab {number}; attachments="
                                f"{snapshot.get('count', 0)}/{len(names)}; moving on"
                            )
                    except TabStartFreshChatRequiredError as exc:
                        try:
                            page = await replace_unresponsive_slot_with_fresh_chat(index, page, exc)
                            pages[index] = page
                            await legacy_reload_drop_prepare(
                                index, page, batch, 'legacy stage-3 unresponsive-tab replacement'
                            )
                        except Exception as recovery_exc:
                            legacy_pending.discard(index); legacy_failed.add(index); terminal_failures.add(index)
                            print(f"LEGACY STAGE-3 RECOVERY FAILURE - TAB {number}: {concise_error(recovery_exc)}", file=sys.stderr)
                    except (FreshChatRequiredError, PlaywrightError, RuntimeError, FileNotFoundError, asyncio.TimeoutError) as exc:
                        direct_error = await upload_error_message(page)
                        if direct_error:
                            try:
                                await legacy_reload_drop_prepare(
                                    index, page, batch, f"legacy stage-3 direct upload error: {direct_error}"
                                )
                            except Exception as recovery_exc:
                                legacy_pending.discard(index); legacy_failed.add(index); terminal_failures.add(index)
                                print(f"LEGACY STAGE-3 RECOVERY FAILURE - TAB {number}: {concise_error(recovery_exc)}", file=sys.stderr)
                        else:
                            legacy_prepared.discard(index)
                            legacy_messages.pop(index, None)
                            print(
                                f"LEGACY CHECK RETRY - TAB {number}: {concise_error(exc)}; "
                                "exact composer state cleared for rapid stage-2 restoration",
                                file=sys.stderr,
                            )
                if len(legacy_sent) == previous_sent_count:
                    stagnant_rounds += 1
                else:
                    stagnant_rounds = 0
                previous_sent_count = len(legacy_sent)
                if legacy_pending and stagnant_rounds >= LEGACY_PENDING_MAX_STAGNANT_ROUNDS:
                    for index in sorted(legacy_pending):
                        await recover_stalled_attachment_transfer(
                            pages[index], legacy_names[index], 'foreground_wake'
                        )
                    stagnant_rounds = 0
                if legacy_pending:
                    await asyncio.sleep(LEGACY_PENDING_ROUND_DELAY_SECONDS)

            if legacy_sent and wake_task is None:
                wake_task = asyncio.create_task(
                    continuous_sent_tab_wake(wake_pages, wake_stop)
                )
            print(
                f"LEGACY PIPELINE COMPLETE: sent={len(legacy_sent)}/{len(pages)}, "
                f"failures={len(legacy_failed)}; entering the regular wake/result cycle"
            )
        if prefetch_task is not None:
            prefetch_task.cancel()
            await asyncio.gather(prefetch_task,return_exceptions=True)
        if _UPLOAD_ACCELERATOR is not None:
            await _UPLOAD_ACCELERATOR.close()
            _UPLOAD_ACCELERATOR = None
        # The visible wake loop has priority immediately after the final send.
        # Never wait for stale page.title(), evaluate(), or CDP wake probes from
        # the best-effort background task. Cancel and gather them within a short
        # hard bound, then enter cycle 1 in the same event-loop turn.
        last_send_handoff_started = time.monotonic()
        await stop_background_wake_immediately(wake_stop, wake_task)
        stage_heading("CONTINUOUS RESULT CAPTURE AND TAB REUSE")
        print(
            f"IMMEDIATE WAKE HANDOFF: visible cycle startup began "
            f"{time.monotonic()-last_send_handoff_started:.2f}s after background-wake shutdown started"
        )
        audit_results: list[dict[str, Any]] = []
        active_slots = {index for index in sent if index < len(pages)}
        wake_round = 0
        # Slots that fail before Send are not dead workers. They remain available
        # for older queued work after a short slot-local cooldown. Previously such
        # slots were removed from active_slots and never reconsidered, which left
        # only slots 3 and 5 cycling while a populated queue remained.
        idle_slot_retry_after: dict[int, float] = {}
        idle_slot_failures: dict[int, int] = {}
        while active_slots or _DEFERRED_BATCH_QUEUE:
            # Work-conserving reclamation: before another wake cycle, assign queued
            # work to every open physical slot that has no unresolved SENT assignment.
            # A failed slot is isolated and backed off; it cannot disable the other tabs.
            if _DEFERRED_BATCH_QUEUE:
                for idle_index, idle_page in enumerate(pages):
                    if not _DEFERRED_BATCH_QUEUE:
                        break
                    if idle_index in active_slots or idle_page.is_closed():
                        continue
                    idle_state = _ASSIGNMENTS.get(id(idle_page))
                    if idle_state is not None and idle_state.state not in {"REUSABLE", "REPLACED", "RESULT_PERSISTED"}:
                        continue
                    if time.monotonic() < idle_slot_retry_after.get(idle_index, 0.0):
                        continue
                    replacement = dequeue_next_batch()
                    if replacement is None:
                        break
                    try:
                        await _cancel_assignment_capture(idle_state)
                        await reset_tab_to_fresh_chat(
                            idle_page, args, idle_index + 1,
                            "idle-slot work-conserving queue reclamation",
                        )
                        _CAPTURED_RESULTS.pop(id(idle_page), None)
                        _ASSIGNMENTS.pop(id(idle_page), None)
                        batches[idle_index] = replacement
                        _RUN_ROWS[id(idle_page)] = replacement["rows"]
                        await complete_one_tab_resilient(
                            idle_index + 1, pages[idle_index], replacement)
                        active_slots.add(idle_index)
                        sent.add(idle_index)
                        terminal_failures.discard(idle_index)
                        idle_slot_failures.pop(idle_index, None)
                        idle_slot_retry_after.pop(idle_index, None)
                        current = _ASSIGNMENTS.get(id(pages[idle_index]))
                        ids = ", ".join(
                            (row.get("change_id") or "").strip()
                            for row in replacement["rows"]
                        )
                        print(
                            f"IDLE TAB {idle_index + 1} RECLAIMED: generation "
                            f"{current.generation if current else '?'}; cases {ids}; "
                            f"active={len(active_slots)}/{len(pages)}; "
                            f"queued={len(_DEFERRED_BATCH_QUEUE)}"
                        )
                    except (PlaywrightError, RuntimeError, FileNotFoundError) as exc:
                        # Return the exact claimed workload to the queue front. Do
                        # not advance its generation merely because this physical
                        # slot is temporarily unhealthy.
                        _DEFERRED_BATCH_QUEUE.insert(0, replacement)
                        failures = idle_slot_failures.get(idle_index, 0) + 1
                        idle_slot_failures[idle_index] = failures
                        idle_slot_retry_after[idle_index] = time.monotonic() + min(30.0, 2.0 ** min(failures, 4))
                        terminal_failures.add(idle_index)
                        print(
                            f"IDLE TAB {idle_index + 1} RECLAIM FAILED: "
                            f"{concise_error(exc)}; workload returned to queue; "
                            f"cooldown={idle_slot_retry_after[idle_index]-time.monotonic():.1f}s",
                            file=sys.stderr,
                        )
            if get_cdp_version(endpoint) is None:
                print("WAKE PAUSED: CDP unavailable; no tab counted visited and no empty title accepted.", file=sys.stderr)
                try: await recover_cdp_and_rebind("wake preflight")
                except CDPConnectionLostError as exc:
                    print(f"WAKE PAUSED: {concise_error(exc)}; all assignments and queue entries retained.", file=sys.stderr)
                    await asyncio.sleep(WAKE_CDP_RECOVERY_BACKOFF_SECONDS)
                continue
            wake_round += 1
            snapshot = [index for index in sorted(tuple(active_slots)) if index < len(pages)]
            # User-facing summary. The orchestration UI keeps the detailed lines
            # below in its diagnostic log and shows this compact line by default.
            global _LAST_WAKE_STATUS, _WAKE_INITIAL_REMAINING
            active_case_count = sum(
                len(state.change_ids) for state in (_ASSIGNMENTS.get(id(pages[index])) for index in snapshot)
                if state is not None and state.state != "REUSABLE"
            )
            queued_case_count = sum(len(batch.get("rows", ())) for batch in _DEFERRED_BATCH_QUEUE)
            remaining_case_count = active_case_count + queued_case_count
            _WAKE_INITIAL_REMAINING = max(_WAKE_INITIAL_REMAINING, remaining_case_count)
            wake_status = (remaining_case_count, len(snapshot), queued_case_count)
            if wake_status != _LAST_WAKE_STATUS:
                completed_case_count = max(0, _WAKE_INITIAL_REMAINING - remaining_case_count)
                print(
                    f"Remaining cases: {remaining_case_count} | Active tabs: {len(snapshot)} | "
                    f"Completed: {completed_case_count} | Queued cases: {queued_case_count}"
                )
                _LAST_WAKE_STATUS = wake_status
            print(f"WAKE CYCLE {wake_round}: starting visibly from tab 1; active snapshot size={len(snapshot)}; queued replacements={len(_DEFERRED_BATCH_QUEUE)}")
            capture_eligible: list[tuple[int, str]] = []
            visited = 0
            closed_slots: list[int] = []
            cycle_interrupted = False
            for physical_number, index in enumerate(snapshot, 1):
                page = pages[index]
                state = _ASSIGNMENTS.get(id(page))
                if page.is_closed():
                    closed_slots.append(index)
                    print(f"WAKE CYCLE {wake_round}: physical tab {physical_number}/{len(snapshot)} (slot {index+1}) closed; traversal continues")
                    continue
                if state is None or state.physical_slot != index:
                    print(f"WAKE CYCLE {wake_round}: physical tab {physical_number}/{len(snapshot)} (slot {index+1}) has no current sent assignment; skipped safely")
                    continue
                try:
                    title, visible, focus = await foreground_and_read_title_v27(page,index+1,float(args.__dict__.get('wake_dwell',WAKE_FOREGROUND_DWELL_SECONDS)))
                except CDPConnectionLostError as exc:
                    print(f"WAKE CYCLE {wake_round} INTERRUPTED at slot {index+1}: {concise_error(exc)}; no capture or reuse from this partial cycle.",file=sys.stderr)
                    try: await recover_cdp_and_rebind(exc)
                    except CDPConnectionLostError as recovery_exc:
                        print(f"WAKE PAUSED: {concise_error(recovery_exc)}; state retained.",file=sys.stderr)
                        await asyncio.sleep(WAKE_CDP_RECOVERY_BACKOFF_SECONDS)
                    cycle_interrupted=True
                    break
                visited += 1
                changed = _title_changed_from_assignment_baseline(state,title)
                reasoning_done, reasoning_label = await reasoning_completed_signal(page)
                generic = generic_chat_title(title)
                if _normalized_title(title) == "new chat":
                    regenerated = await regenerate_if_available(page,index+1)
                    if regenerated:
                        reasoning_done=False; reasoning_label=""
                # A complete explicit final contract is stronger than a title.
                # It can represent successful, mixed, or all-failed outcomes and
                # must release the physical tab even while the title stays generic.
                explicit_overall, explicit_statuses, explicit_text = await exact_terminal_audit_result(
                    page, state.change_ids
                )
                explicit_terminal = bool(explicit_text)
                if explicit_terminal:
                    _CAPTURED_RESULTS[id(page)] = (explicit_overall, explicit_statuses)
                # Reasoning completion remains a supporting readiness signal only
                # when no complete explicit contract has appeared yet.
                supporting_ready = generic and reasoning_done
                print(f"WAKE CYCLE {wake_round}: VISIBLY VISITED physical tab {physical_number}/{len(snapshot)} (slot {index+1}); title={title!r}; title_changed={'yes' if changed else 'no'}; generic={'yes' if generic else 'no'}; reasoning_complete={'yes' if reasoning_done else 'no'}; explicit_terminal={'yes' if explicit_terminal else 'no'}; explicit_overall={explicit_overall if explicit_terminal else 'pending'}; generation={state.generation}; visible={'yes' if visible else 'no'}; {focus}")
                if reasoning_label:
                    print(f"Tab {index+1}: supporting readiness signal detected: {reasoning_label}")
                if (changed or supporting_ready or explicit_terminal) and state.state == "WAITING_FOR_TITLE_CHANGE":
                    state.state="TITLE_CHANGED"; state.title_changed_title=title
                    capture_eligible.append((index,state.token))
                    reason=(
                        f"explicit terminal result ({explicit_overall})"
                        if explicit_terminal
                        else "non-generic title change" if changed
                        else "generic title plus reasoning-completed signal"
                    )
                    print(f"Tab {index+1}: eligible for one post-traversal capture probe ({reason})")
            if cycle_interrupted:
                continue
            print(f"WAKE CYCLE {wake_round} COMPLETE: visibly visited {visited}/{len(snapshot)} active snapshot tab(s); capture eligible={len(capture_eligible)}; queued replacements={len(_DEFERRED_BATCH_QUEUE)}")
            print("NEXT WAKE CYCLE: will restart visibly from tab 1 after capture/reuse processing.")
            for index in closed_slots:
                active_slots.discard(index); sent.discard(index); terminal_failures.add(index)
                state = _ASSIGNMENTS.get(id(pages[index]))
                if state is not None:
                    await _cancel_assignment_capture(state)
                    state.state = "REUSABLE"

            reusable_slots: list[int] = []
            legacy_refill_bindings: list[LegacyReloadPipelineState] = []
            for index, token in capture_eligible:
                page = pages[index]
                state = _ASSIGNMENTS.get(id(page))
                if state is None or state.token != token or state.state != "TITLE_CHANGED" or page.is_closed():
                    continue
                # Strictly foreground and re-read this exact title immediately before capture.
                try:
                    capture_title, _, _ = await foreground_and_read_title_v27(page,index+1,WAKE_FOREGROUND_DWELL_SECONDS)
                except CDPConnectionLostError as exc:
                    print(f"Tab {index+1}: capture paused by CDP loss; TITLE_CHANGED state retained ({concise_error(exc)})",file=sys.stderr)
                    try: await recover_cdp_and_rebind(exc)
                    except CDPConnectionLostError: pass
                    continue
                capture_title_changed=_title_changed_from_assignment_baseline(state,capture_title)
                capture_reasoning,_=await reasoning_completed_signal(page)
                cached_terminal = _CAPTURED_RESULTS.get(id(page))
                if not capture_title_changed and not cached_terminal and not (generic_chat_title(capture_title) and capture_reasoning):
                    state.state="WAITING_FOR_TITLE_CHANGE"
                    print(f"Tab {index+1}: generic/baseline title without reasoning-completed support; capture blocked and visual travel continues")
                    continue
                if not _assignment_is_current(page, token, state.change_ids):
                    print(f"Tab {index+1}: stale generation {state.generation} capture cancelled before read")
                    continue
                state.state = "TAB_FOREGROUNDED_FOR_CAPTURE"
                print(f"Tab {index+1}: foregrounded for result capture")
                try:
                    capture_started=time.monotonic()
                    state.capture_task = asyncio.create_task(capture_completed_tab_result(page,index+1,state.rows))
                    overall,statuses = await state.capture_task
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    overall="inconclusive_review_needed"
                    statuses={cid:"inconclusive_review_needed" for cid in state.change_ids}
                    print(f"Tab {index+1}: bounded result capture incomplete ({concise_error(exc)}); assignment remains pending")
                finally:
                    state.capture_task = None
                if not _assignment_is_current(page, token, state.change_ids):
                    print(f"Tab {index+1}: stale generation {state.generation} result discarded before persistence")
                    continue
                complete = overall in {"Yes","No"} and all(statuses.get(cid) in {"successful","failed"} for cid in state.change_ids)
                reward_technique("capture","exact_then_fallback",complete,time.monotonic()-capture_started)
                if not complete:
                    enqueue_retry_batch(batches[index], "incomplete capture after title change", args)
                    # The response has finished but its contract is unusable. The
                    # current assignment is safely queued as a final attempt, so
                    # this unlocked physical tab must immediately become reusable.
                    active_slots.discard(index); sent.discard(index)
                    state.state = "REUSABLE"
                    reusable_slots.append(index)
                    print(f"Tab {index+1}: capture incomplete; final attempt queued, no false result persisted, and tab released to the universal queue")
                    if processing_flow == "staged":
                        replacement = dequeue_next_batch()
                        if replacement is not None:
                            try:
                                legacy_refill_bindings.append(
                                    await legacy_reuse_drop_only(index, replacement)
                                )
                                reusable_slots.remove(index)
                            except Exception as refill_exc:
                                _DEFERRED_BATCH_QUEUE.insert(0, replacement)
                                print(f"LEGACY DROP-ONLY REFILL FAILED - TAB {index+1}: {concise_error(refill_exc)}; workload returned to queue", file=sys.stderr)
                    continue
                state.state = "RESULT_CAPTURED"
                print(f"Tab {index+1}: result captured for change IDs {list(state.change_ids)}")
                if not _assignment_is_current(page, token, state.change_ids):
                    continue
                append_case_audit_results(args.log_path,state.rows,statuses,result_run_number)
                failed_rows=[
                    row for row in state.rows
                    if statuses.get((row.get("change_id") or "").strip()) == "failed"
                ]
                if failed_rows:
                    failed_batch=dict(batches[index])
                    failed_batch["rows"]=list(failed_rows)
                    queued=enqueue_retry_batch(
                        failed_batch,
                        "failed result appended after remaining first-attempt work",
                        args,
                    )
                    failed_ids=", ".join((row.get("change_id") or "").strip() for row in failed_rows)
                    print(
                        f"UNIVERSAL QUEUE: failed result case(s) {failed_ids} "
                        f"{'appended to the shared queue tail' if queued else 'already present in the shared queue'}; "
                        f"queued={len(_DEFERRED_BATCH_QUEUE)}"
                    )
                state.state = "RESULT_PERSISTED"
                print(f"Tab {index+1}: results persisted")
                audit_results.append({"tab_number":index+1,"overall":overall,"statuses":statuses})
                active_slots.discard(index); sent.discard(index)
                state.state = "REUSABLE"
                reusable_slots.append(index)
                print(f"Tab {index+1}: eligible for reuse")
                if processing_flow == "staged":
                    replacement = dequeue_next_batch()
                    if replacement is not None:
                        try:
                            legacy_refill_bindings.append(
                                await legacy_reuse_drop_only(index, replacement)
                            )
                            reusable_slots.remove(index)
                        except Exception as refill_exc:
                            _DEFERRED_BATCH_QUEUE.insert(0, replacement)
                            print(f"LEGACY DROP-ONLY REFILL FAILED - TAB {index+1}: {concise_error(refill_exc)}; workload returned to queue", file=sys.stderr)
            # In legacy mode every ready result above was captured and drop-only
            # refilled before any new model or message work starts.
            if processing_flow == "staged" and legacy_refill_bindings:
                print(
                    f"LEGACY RESULT-DRAIN COMPLETE: {len(legacy_refill_bindings)} refilled "
                    "tab(s); returning to the first drop-only tab for exact model/message preparation"
                )
                await legacy_prepare_and_send_refilled_slots(
                    legacy_refill_bindings, active_slots, sent, wake_pages
                )
            # Reuse is deliberately deferred until every tab in the cycle snapshot was visited.
            for index in reusable_slots:
                if processing_flow == "staged":
                    continue
                if not _DEFERRED_BATCH_QUEUE or pages[index].is_closed(): continue
                page=pages[index]; old_state=_ASSIGNMENTS.get(id(page))
                await _cancel_assignment_capture(old_state)
                replacement=dequeue_next_batch()
                if replacement is None:
                    continue
                try:
                    await reset_tab_to_fresh_chat(page,args,index+1,"persisted workload cleanup and reuse")
                    _CAPTURED_RESULTS.pop(id(page),None); _ASSIGNMENTS.pop(id(page),None)
                    batches[index]=replacement
                    await complete_one_tab_resilient(index+1,pages[index],replacement)
                    active_slots.add(index); sent.add(index)
                    current=_ASSIGNMENTS.get(id(pages[index]))
                    print(f"TAB {index+1} REUSED: generation {current.generation if current else '?'} joined complete rotation; next cycle restarts from tab 1")
                except (PlaywrightError,RuntimeError,FileNotFoundError) as exc:
                    if _is_cdp_disconnect_error(exc) or get_cdp_version(endpoint) is None:
                        print(f"TAB {index+1} REUSE PAUSED BY CDP LOSS: {concise_error(exc)}; replacement remains queued.",file=sys.stderr)
                        _DEFERRED_BATCH_QUEUE.insert(0,replacement)
                        try: await recover_cdp_and_rebind(exc)
                        except CDPConnectionLostError: pass
                        active_slots.discard(index)
                        break
                    # Nothing was sent. Advance the retry generation and append
                    # this problematic workload to the tail. Other queued cases
                    # therefore continue before it is attempted with another route.
                    queued_retry=enqueue_retry_batch(
                        replacement,
                        f"reused-tab processing failure: {concise_error(exc)}",
                        args,
                    )
                    terminal_failures.add(index)
                    print(
                        f"TAB {index+1} REUSE DEFERRED TO QUEUE TAIL: {concise_error(exc)}; "
                        f"queued={'yes' if queued_retry else 'already queued'}"
                    )
            if active_slots:
                await asyncio.sleep(min(max(STRONG_WAKE_INTERVAL_SECONDS,0.03),0.12))
            elif _DEFERRED_BATCH_QUEUE:
                open_idle = [index for index, page in enumerate(pages) if not page.is_closed()]
                if not open_idle:
                    print(f"CONTINUOUS QUEUE PAUSED: {len(_DEFERRED_BATCH_QUEUE)} batch(es) remain and all physical tabs are closed. No queued work was discarded.",file=sys.stderr)
                    break
                next_retry = min((idle_slot_retry_after.get(index, time.monotonic()) for index in open_idle), default=time.monotonic())
                delay = max(0.10, min(2.0, next_retry - time.monotonic()))
                print(f"CONTINUOUS QUEUE: {len(_DEFERRED_BATCH_QUEUE)} batch(es) waiting; {len(open_idle)} open idle tab(s) will be reclaimed after {delay:.1f}s cooldown.")
                await asyncio.sleep(delay)
        print_final_audit_summary(audit_results)
        for stage in list(_RETAINED_ATTACHMENT_STAGES):
            cleanup_attachment_stage(stage)
        _RETAINED_ATTACHMENT_STAGES.clear()
        stability_stop.set()
        await asyncio.gather(stability_task,return_exceptions=True)
        stage_heading("RUN COMPLETE")
        print(f"Sent tabs: {len(sent)}/{len(batches)} | Failed tabs: {len(terminal_failures)}")
        return 0 if not terminal_failures else 2



# Target-driven persistence and orchestration overrides.
LOG_FIELDS = ["change_id", "InterestedPartyId", "fully_sent_at_local", "run_number", "change_id_status"]
FINAL_STATUSES = {"successful", "failed", "inconclusive_review_needed", "Failed_to_add_attachments"}
RETRY_STATUSES = {"sent", "failed", "inconclusive_review_needed", "Failed_to_add_attachments"}
_LOG_WRITE_LOCK = threading.RLock()
LOG_REPLACE_ATTEMPTS = 12
LOG_REPLACE_BASE_DELAY_SECONDS = 0.05

@dataclass(frozen=True)
class CaseLogRecord:
    change_id: str
    interested_party_id: str
    timestamp: str
    run_number: str
    status: str
    @property
    def key(self) -> tuple[str, str]:
        return canonical_change_id(self.change_id), self.interested_party_id.casefold()

class CaseLogStore:
    """One-logical-row store with retrying atomic replace and durable journal fallback."""
    def __init__(self, path: Path):
        self.path = path
        self.journal_path = path.with_name(path.name + ".pending-transitions.csv")

    @staticmethod
    def _choose(old: Optional[CaseLogRecord], new: CaseLogRecord) -> CaseLogRecord:
        if old is None or new.status == "successful":
            return new
        if old.status == "successful":
            return old
        if old.status in FINAL_STATUSES and new.status == "sent":
            return old
        if old.status != "inconclusive_review_needed" and new.status == "inconclusive_review_needed":
            return old
        return new

    def _read_file(self, path: Path) -> list[CaseLogRecord]:
        if not path.exists() or not path.stat().st_size:
            return []
        output = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if "change_id" not in (reader.fieldnames or []):
                raise RuntimeError(f"Case log has no change_id column: {path}")
            for number, row in enumerate(reader, 2):
                cid = (row.get("change_id") or "").strip()
                ipid = (row.get("InterestedPartyId") or "").strip()
                status = _status((row.get("change_id_status") or "").strip() or "sent")
                if status.casefold() == "failed_to_add_attachments":
                    status = "Failed_to_add_attachments"
                if not cid:
                    print(f"LOG WARNING: row {number} in {path.name} has no change_id; ignored.", file=sys.stderr)
                    continue
                if status not in FINAL_STATUSES | {"sent"}:
                    print(f"LOG WARNING: row {number} in {path.name} has unsupported status {status!r}; ignored.", file=sys.stderr)
                    continue
                output.append(CaseLogRecord(cid, ipid, (row.get("fully_sent_at_local") or "").strip(), (row.get("run_number") or "").strip(), status))
        return output

    def load(self, compact: bool = False) -> dict[tuple[str, str], CaseLogRecord]:
        records: dict[tuple[str, str], CaseLogRecord] = {}
        for record in self._read_file(self.path) + self._read_file(self.journal_path):
            records[record.key] = self._choose(records.get(record.key), record)
        if compact and records:
            self._commit(records.values(), allow_journal_fallback=False)
        return records

    def _write_csv(self, target: Path, records: Iterable[CaseLogRecord]) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS, lineterminator="\n")
            writer.writeheader()
            for record in records:
                writer.writerow(dict(zip(LOG_FIELDS, (record.change_id, record.interested_party_id, record.timestamp, record.run_number, record.status))))
            handle.flush(); os.fsync(handle.fileno())

    def _replace_with_retries(self, temporary: Path) -> bool:
        last_error: Optional[OSError] = None
        for attempt in range(1, LOG_REPLACE_ATTEMPTS + 1):
            try:
                os.replace(temporary, self.path)
                return True
            except PermissionError as exc:
                last_error = exc
            except OSError as exc:
                last_error = exc
                if getattr(exc, "winerror", None) not in {5, 32, 33}:
                    raise
            if attempt in {1, 4, 8}:
                print(f"LOG PERSISTENCE: destination temporarily locked; atomic replace retry {attempt}/{LOG_REPLACE_ATTEMPTS}.", file=sys.stderr)
            time.sleep(min(0.75, LOG_REPLACE_BASE_DELAY_SECONDS * (2 ** min(attempt - 1, 4))))
        print(f"LOG PERSISTENCE WARNING: main CSV remained locked ({last_error}); writing a durable transition journal.", file=sys.stderr)
        return False

    def _append_journal_atomically(self, records: Iterable[CaseLogRecord]) -> None:
        merged: dict[tuple[str, str], CaseLogRecord] = {}
        for record in self._read_file(self.journal_path):
            merged[record.key] = self._choose(merged.get(record.key), record)
        for record in records:
            merged[record.key] = self._choose(merged.get(record.key), record)
        temp = self.journal_path.with_name(self.journal_path.name + f".{os.getpid()}.{time.time_ns()}.tmp")
        self._write_csv(temp, merged.values())
        for attempt in range(1, LOG_REPLACE_ATTEMPTS + 1):
            try:
                os.replace(temp, self.journal_path)
                return
            except OSError:
                if attempt == LOG_REPLACE_ATTEMPTS:
                    raise
                time.sleep(min(0.5, LOG_REPLACE_BASE_DELAY_SECONDS * attempt))
        raise RuntimeError("Durable transition journal could not be committed.")

    def _commit(self, records: Iterable[CaseLogRecord], allow_journal_fallback: bool = True) -> None:
        snapshot = list(records)
        temp = self.path.with_name(self.path.name + f".{os.getpid()}.{time.time_ns()}.tmp")
        self._write_csv(temp, snapshot)
        try:
            if self._replace_with_retries(temp):
                try:
                    self.journal_path.unlink(missing_ok=True)
                except OSError:
                    pass
                return
            if allow_journal_fallback:
                self._append_journal_atomically(snapshot)
                print("LOG PERSISTENCE: transition safely journalled; automatic compaction will retry on the next log access.", file=sys.stderr)
                return
            print("LOG PERSISTENCE: compaction deferred because the main CSV is locked; journal remains authoritative.", file=sys.stderr)
        finally:
            temp.unlink(missing_ok=True)

    def upsert(self, row: dict[str, str], status: str, run_number: int | str = "") -> None:
        status = _status(status)
        if status.casefold() == "failed_to_add_attachments":
            status = "Failed_to_add_attachments"
        if status not in FINAL_STATUSES | {"sent"}:
            status = "inconclusive_review_needed"
        record = CaseLogRecord((row.get("change_id") or "").strip(), (row.get("InterestedPartyId") or "").strip(), datetime.now().astimezone().isoformat(timespec="seconds"), str(run_number or ""), status)
        if not record.change_id:
            raise ValueError("change_id is required for persistence")
        with _LOG_WRITE_LOCK:
            data = self.load(compact=False)
            data[record.key] = self._choose(data.get(record.key), record)
            self._commit(data.values(), allow_journal_fallback=True)

def read_successfully_logged_change_ids(path: Path, report: bool = False) -> set[str]:
    records = CaseLogStore(path).load(compact=False)
    successful = {canonical_change_id(record.change_id) for record in records.values() if record.status == "successful"}
    retry = [record.change_id for record in records.values() if record.status in RETRY_STATUSES]
    if report:
        print(f"LOG ELIGIBILITY: {len(successful)} latest-successful excluded; {len(retry)} retryable case(s).")
        if retry: print("LOG RETRY CASES: " + ", ".join(retry))
    return successful

def read_logged_change_ids(path: Path) -> set[str]:
    return read_successfully_logged_change_ids(path, report=False)

def append_fully_sent_log(log_path: Path, row: dict[str, str]) -> None:
    CaseLogStore(log_path).upsert(row, "sent")

def ensure_result_log_schema(log_path: Path) -> None:
    CaseLogStore(log_path).load(compact=True)

def next_result_run_number(log_path: Path) -> int:
    values = [int(record.run_number) for record in CaseLogStore(log_path).load().values() if record.run_number.isdigit()]
    return max(values, default=0) + 1

def append_case_audit_results(log_path: Path, rows: Sequence[dict[str, str]], statuses: dict[str, str], run_number: int) -> None:
    store = CaseLogStore(log_path)
    for row in rows:
        cid = (row.get("change_id") or "").strip()
        store.upsert(row, statuses.get(cid, "inconclusive_review_needed"), run_number)

async def initial_wake_and_readiness(pages: Sequence[Page], args: argparse.Namespace) -> list[bool]:
    del args
    ready = [False] * len(pages)
    stage_heading("INITIAL TAB READINESS")
    print(f"SHARED READINESS WAIT: up to {DEFAULT_INITIAL_READINESS_BUDGET_SECONDS:.1f}s")
    deadline = time.monotonic() + DEFAULT_INITIAL_READINESS_BUDGET_SECONDS
    while time.monotonic() < deadline and not all(ready):
        results = await asyncio.gather(*(first_visible([*editor_locators(page), *model_switcher_locators(page)], 0) if not page.is_closed() else asyncio.sleep(0, result=None) for page in pages), return_exceptions=True)
        ready = [old or (not isinstance(result, BaseException) and result is not None) for old, result in zip(ready, results)]
        if not all(ready): await asyncio.sleep(0.10)
    print("MANDATORY ALL-TAB WAKE TRAVERSAL: visiting every created tab once")
    for index, page in enumerate(pages):
        if not page.is_closed():
            await activate_page_like_manual_selection(page, index + 1, "mandatory post-wait wake traversal")
            ready[index] = (await first_visible([*editor_locators(page), *model_switcher_locators(page)], 0)) is not None
        print(f"PER-TAB READINESS: tab {index + 1}/{len(pages)} {'ready' if ready[index] else 'deferred'}")
    print(f"WAKE COMPLETION SUMMARY: visited {len(pages)}/{len(pages)}; ready {sum(ready)}; deferred {len(pages)-sum(ready)}")
    return ready

async def run(args: argparse.Namespace) -> int:
    loop=asyncio.get_running_loop()
    previous_handler=loop.get_exception_handler()
    def _owned_loop_exception_handler(active_loop: asyncio.AbstractEventLoop, context: dict[str,Any]) -> None:
        message=str(context.get("message") or "")
        exception=context.get("exception")
        if "Future exception was never retrieved" in message and isinstance(exception,(asyncio.TimeoutError,PlaywrightTimeoutError)):
            print(f"PLAYWRIGHT PROBE TIMEOUT CONSUMED: {concise_error(exception)}")
            return
        if previous_handler is not None: previous_handler(active_loop,context)
        else: active_loop.default_exception_handler(context)
    loop.set_exception_handler(_owned_loop_exception_handler)
    initial_candidates = eligible_source_rows(args)
    achievable = max(0, min(args.cases, len(initial_candidates)))
    target_keys = {
        (canonical_change_id(row.get("change_id", "")), (row.get("InterestedPartyId") or "").strip().casefold())
        for row in initial_candidates[:achievable]
    }
    stage_heading("TARGET EXECUTION PLAN")
    print(f"Requested successful target: {args.cases}")
    print(f"Eligible rerunnable cases: {len(initial_candidates)}")
    print(f"Achievable target: {achievable}")
    if achievable <= 0:
        print("No eligible change_id remains.")
        return 0
    original=args.cases; original_confirm=args.confirm_send; runs=0; no_progress=0
    while True:
        records=CaseLogStore(args.log_path).load(compact=False)
        successful={key for key in target_keys if key in records and _status(records[key].status)==SUCCESS_STATUS}
        if len(successful) >= achievable:
            break
        remaining_keys=target_keys-successful
        remaining_rows=[row for row in eligible_source_rows(args) if (canonical_change_id(row.get("change_id","")),(row.get("InterestedPartyId") or "").strip().casefold()) in remaining_keys]
        if not remaining_rows:
            raise RuntimeError("No-progress guard: target remains incomplete but no valid active, deferred, or retryable source work remains.")
        args.cases=min(len(remaining_rows),achievable-len(successful)); args.retry_generation=runs
        runs+=1; stage_heading(f"ADAPTIVE RUN {runs} | GENERATION {args.retry_generation}")
        before=len(successful)
        code=await _run_single_wave(args)
        if code==1:
            args.cases=original; args.confirm_send=original_confirm; return 1
        args.confirm_send=False
        records=CaseLogStore(args.log_path).load(compact=False)
        successful={key for key in target_keys if key in records and _status(records[key].status)==SUCCESS_STATUS}
        gained=len(successful)-before
        valid_queued=bool(_DEFERRED_BATCH_QUEUE)
        no_progress = no_progress + 1 if gained == 0 and not valid_queued else 0
        print(f"ADAPTIVE PROGRESS: {len(successful)}/{achievable} successful; {achievable-len(successful)} remain retryable.")
        if no_progress >= 2:
            raise RuntimeError("No-progress guard: two complete waves produced no new successful cases and no valid deferred work remains.")
        await asyncio.sleep(0.10)
    args.cases=original; args.confirm_send=original_confirm
    CaseLogStore(args.log_path).load(compact=True)
    stage_heading("FINAL TARGET SUMMARY")
    print(f"Successful: {achievable}/{achievable}; adaptive runs: {runs}; target success rate: 100%")
    return 0

def self_test_failed_and_mixed_result_capture() -> None:
    submitted = ['04512', '04513', '04503']
    mixed = (
        'All files for all cases were exposed: No\n'
        'Case result: 04512 | failed\n'
        'Case result: 04513 | failed\n'
        'Case result: 04503 | successful'
    )
    overall, statuses, complete = parse_complete_failed_or_mixed_result(mixed, submitted)
    assert complete and overall == 'No'
    assert statuses == {'04512':'failed','04513':'failed','04503':'successful'}
    all_failed = (
        'All files for all cases were exposed: No\n'
        'Case result: 04518 | failed\n'
        'Case result: 04519 | failed\n'
        'Case result: 04569 | failed'
    )
    overall, statuses, complete = parse_complete_failed_or_mixed_result(
        all_failed, ['04518','04519','04569']
    )
    assert complete and overall == 'No' and set(statuses.values()) == {'failed'}
    partial = 'All files for all cases were exposed: No\nCase result: 04518 | failed'
    _, _, complete = parse_complete_failed_or_mixed_result(
        partial, ['04518','04519','04569']
    )
    assert not complete

def self_test_target_orchestration() -> None:
    assert DEFAULT_CASE_COUNT == 1000 and DEFAULT_INTER_TAB_COOLDOWN_SECONDS >= 2
    assert DEFAULT_TAB_COUNT == DEFAULT_TAB_COUNT and MAXIMUM_TAB_COUNT == MAXIMUM_TAB_COUNT
    global _OPUS_GLOBALLY_DISABLED, _OPUS_DISABLE_REASON
    _OPUS_GLOBALLY_DISABLED=False; _OPUS_DISABLE_REASON=""
    probe=type("Probe",(),{"large_model":"Opus","small_model":"GPT"})()
    assert adaptive_retry_model(probe,3,"GPT")=="Opus"
    assert adaptive_retry_model(probe,4,"Opus")=="GPT"
    _OPUS_GLOBALLY_DISABLED=True
    assert adaptive_retry_model(probe,3,"GPT")==DEFAULT_LARGE_CASE_MODEL_FALLBACK
    assert effective_model_name("Opus")==DEFAULT_LARGE_CASE_MODEL_FALLBACK
    _OPUS_GLOBALLY_DISABLED=False
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "log.csv"; store = CaseLogStore(path); row = {"change_id":"0007", "InterestedPartyId":"9"}
        store.upsert(row, "sent", 1); store.upsert(row, "failed", 2); store.upsert(row, "successful", 3); store.upsert(row, "sent", 4)
        record = next(iter(store.load(compact=True).values()))
        assert record.change_id == "0007" and record.status == "successful" and len(store.load()) == 1
        # Adversarial Windows-lock simulation: main replace fails, journal succeeds.
        locked = Path(folder) / "locked.csv"; locked_store = CaseLogStore(locked)
        original_replace = locked_store._replace_with_retries
        locked_store._replace_with_retries = lambda temporary: False
        locked_store.upsert({"change_id":"0010", "InterestedPartyId":"22"}, "Failed_to_add_attachments", 5)
        assert locked_store.journal_path.exists()
        assert next(iter(locked_store.load().values())).status == "Failed_to_add_attachments"
        locked_store._replace_with_retries = original_replace


class _FakeWakePage:
    def __init__(self, number: int, changed: bool = False, closed: bool = False):
        self.number=number; self.changed=changed; self.closed=closed; self.calls=[]
    def is_closed(self): return self.closed
    async def title(self): self.calls.append("title"); return f"Result {self.number}" if self.changed else AUDIT_PENDING_TITLE
    async def bring_to_front(self): self.calls.append("front")

async def self_test_assignment_invariants() -> None:
    pages=[_FakeWakePage(i,changed=(i==6)) for i in range(1,11)]
    visited=[]; eligible=[]
    for index,page in enumerate(list(pages)):
        if page.is_closed(): continue
        await page.bring_to_front(); title=await page.title(); visited.append(page.number)
        state=TabAssignmentState(id(page),index,1,f"t{index}",tuple(),tuple(),AUDIT_PENDING_TITLE,"WAITING_FOR_TITLE_CHANGE")
        if _title_changed_from_assignment_baseline(state,title): eligible.append(page.number)
    assert visited==list(range(1,11)) and eligible==[6]
    # Restarted stable snapshot starts at physical tab one, including a reused six.
    pages[5]=_FakeWakePage(6,changed=False)
    restarted=[]
    for page in list(pages):
        await page.bring_to_front(); restarted.append(page.number)
    assert restarted==list(range(1,11))
    closed=[_FakeWakePage(1),_FakeWakePage(2,closed=True),_FakeWakePage(3)]
    later=[]
    for page in list(closed):
        if page.is_closed(): continue
        await page.bring_to_front(); later.append(page.number)
    assert later==[1,3]


async def self_test_immediate_wake_shutdown() -> None:
    stop=asyncio.Event()
    entered=asyncio.Event()
    async def blocked_worker() -> None:
        entered.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
    task=asyncio.create_task(blocked_worker())
    await entered.wait()
    started=time.monotonic()
    await stop_background_wake_immediately(stop,task)
    assert stop.is_set() and task.done()
    assert time.monotonic()-started < 1.50

def self_test_transfer_completion_policy() -> None:
    import inspect
    source=inspect.getsource(wait_until_attachments_upload_finished)
    route=inspect.getsource(attach_required_files)
    assert "Chip count alone is never accepted" in source
    assert "transfer_recovery" in source
    assert "wait_until_attachments_upload_finished" in route
    assert TRANSFER_RECOVERY_ATTEMPTS >= 4
    assert TRANSFER_QUIET_STABLE_SECONDS > 0

def self_test_high_count_attachment_policy() -> None:
    assert HIGH_COUNT_ATTACHMENT_THRESHOLD == 15
    assert HIGH_COUNT_BULK_GRACE_SECONDS > BULK_ATTACH_GRACE_CONFIRM_SECONDS
    import inspect
    engine=inspect.getsource(_attach_required_files_v30_engine)
    resilient=inspect.getsource(_run_single_wave)
    assert "safely completing" not in engine
    assert "Exact missing paths are unknowable" in engine
    assert "post-attachment operation failed" in resilient

def self_test_attachment_name_policy() -> None:
    assert not attachment_needs_short_name(Path('instructions.md'))
    assert not attachment_needs_short_name(Path('Change_02493_Interested_Party_159036_part_1.pdf'))
    assert attachment_filename_length(Path('44868_2460864_345e1776250709.pdf')) == 14
    assert not attachment_needs_short_name(Path('44868_2460864_345e1776250709.pdf'))
    assert not attachment_needs_short_name(Path('44868_2460866_Audit History.pdf'))
    assert not attachment_needs_short_name(Path('44868_2460866_AUDIT_HISTORY_RECORD.pdf'))
    assert not attachment_needs_short_name(Path('44868_2460866_E-mail correspondence long title.pdf'))
    assert not attachment_needs_short_name(Path('44868_2460866_customer_email_archive_long.pdf'))
    assert attachment_needs_short_name(Path('44868_2500329_BiggleswadeTownCouncilCouncilStaff.pdf'))
    assert not attachment_needs_short_name(Path('44868_2500329_123456789012345.pdf'))
    assert not attachment_needs_short_name(Path('44868_2500329_12345_67890_123.pdf'))
    assert attachment_needs_short_name(Path('44868_2500329_12345_67890_123456.pdf'))
    assert staged_attachment_name(Path('instructions.md'),1)=='instructions.md'
    assert staged_attachment_name(Path('44868_2460866_Audit History.pdf'),2)=='44868_2460866_Audit History.pdf'
    assert staged_attachment_name(Path('44868_2500329_BiggleswadeTownCouncilCouncilStaff.pdf'),3)=='att_03.pdf'
    used=set()
    first=Path(r'C:/root/Change_02493_Interested_Party_159036/44868_2500329_Audit History.pdf')
    second=Path(r'C:/root/Change_02494_Interested_Party_159037/44868_2500329_Audit History.pdf')
    first_name=unique_staged_name(first,1,used)
    second_name=unique_staged_name(second,2,used)
    assert first_name=='44868_2500329_Audit History.pdf'
    assert second_name!='44868_2500329_Audit History.pdf' and not second_name.casefold().startswith('dup')
    assert 'C02494_IP159037' in second_name and '44868' in second_name and '2500329' in second_name
    mapping=attachment_alias_mapping([first,second],[{'change_id':'02493','InterestedPartyId':'159036'},{'change_id':'02494','InterestedPartyId':'159037'}])
    assert 'Analyze every mapped attachment separately' in mapping
    assert 'same ORIGINAL NAME' in mapping

def self_test_password_required_exclusion_policy() -> None:
    assert _failed_item_is_password_required({"status":"PASSWORD_REQUIRED"})
    assert _failed_item_is_password_required({"error":"PDF is password protected"})
    assert _failed_item_is_password_required({"reason":"encrypted; password required"})
    assert not _failed_item_is_password_required({"status":"failed", "error":"corrupt stream"})
    import inspect
    assert "usable_local_case_files" in inspect.getsource(sorted_case_sources)
    assert "usable_local_case_files" in inspect.getsource(single_case_extra_attachment_paths)
    assert "password-required" in inspect.getsource(format_case_block)

def self_test_upload_failure_is_recoverable() -> None:
    """Upload exhaustion must enter normal recovery instead of escaping asyncio.run."""
    assert issubclass(FreshChatRequiredError, RuntimeError)
    caught = False
    try:
        raise FreshChatRequiredError("simulated stalled upload")
    except RuntimeError:
        caught = True
    assert caught


def self_test_universal_queue() -> None:
    global _DEFERRED_BATCH_QUEUE
    saved=list(_DEFERRED_BATCH_QUEUE)
    try:
        normal={"rows":[{"change_id":"1"}],"category":"Small","retry_generation":0}
        final={"rows":[{"change_id":"2"}],"category":"Large","retry_generation":4}
        _DEFERRED_BATCH_QUEUE=[normal,final]
        assert dequeue_next_batch() is normal
        assert dequeue_next_batch() is final
        assert dequeue_next_batch() is None
        assert batch_queue_label(normal)=="normal queue"
        assert "final attempt" in batch_queue_label(final)
    finally:
        _DEFERRED_BATCH_QUEUE=saved

def self_test_v28_readiness_and_adaptation() -> None:
    global _OPUS_GLOBALLY_DISABLED, _OPUS_DISABLE_REASON
    _OPUS_GLOBALLY_DISABLED=False; _OPUS_DISABLE_REASON=""
    generic_state=TabAssignmentState(1,0,1,"t",tuple(),tuple(),"Microsoft Copilot","WAITING_FOR_TITLE_CHANGE")
    assert not _title_changed_from_assignment_baseline(generic_state,"Chat | Microsoft Copilot")
    assert not _title_changed_from_assignment_baseline(generic_state,"New Chat")
    assert _title_changed_from_assignment_baseline(generic_state,"Audit Review Complete")
    _TECHNIQUE_SCORES.clear()
    reward_technique("test","a",False,1.0)
    reward_technique("test","b",True,0.2)
    assert technique_rank("test",("a","b"))[0] == "b"
    assert DEFAULT_LARGE_CASE_MODEL_NAME == "Opus"
    assert DEFAULT_LARGE_CASE_MODEL_FALLBACK == "GPT 5.6 Think Deeper"
def self_test_gpt_6_sol_policy() -> None:
    """Verify the exact Sol radio and both policies through adaptive retries."""
    from unittest.mock import patch
    assert exact_model_checkmark(GPT_6_SOL_MODEL_NAME) == ("OpenAI", "checkmark-Gpt_6_Sol_Reasoning")
    assert exact_model_checkmark(DEFAULT_SMALL_CASE_MODEL_NAME) == ("OpenAI", "checkmark-Gpt_5_6_Reasoning")
    assert "gpt 6.0 sol" in collapsed_model_selector_aliases(GPT_6_SOL_MODEL_NAME)
    assert "gpt 6.0 sol" not in collapsed_model_selector_aliases("GPT 6.0 Think Deeper")
    for answer, expected in (("2", (GPT_6_SOL_MODEL_NAME,) * 3),
                             ("3", (DEFAULT_SMALL_CASE_MODEL_NAME, DEFAULT_MEDIUM_CASE_MODEL_NAME, GPT_6_SOL_MODEL_NAME))):
        args = argparse.Namespace(small_model=DEFAULT_SMALL_CASE_MODEL_NAME,
                                  medium_model=DEFAULT_MEDIUM_CASE_MODEL_NAME,
                                  large_model=DEFAULT_LARGE_CASE_MODEL_NAME)
        with patch("builtins.input", return_value=answer):
            confirm_large_case_model(args)
        assert (args.small_model, args.medium_model, args.large_model) == expected
        for generation in (0, 1, 3, 4, 5, 6):
            for model in expected:
                assert adaptive_retry_model(args, generation, model) == model
    with patch("builtins.input", return_value=""):
        confirm_large_case_model(args)
    assert args.model_policy == "original" and args.large_model == "Opus"


def self_test_legacy_stage1_drop_ack_policy() -> None:
    import inspect
    confirm = inspect.getsource(legacy_confirm_drop_started)
    drop = inspect.getsource(legacy_drop_attachment_plan)
    wave = inspect.getsource(_run_single_wave)
    assert "if count > 0" in confirm
    assert "input.dispatchEvent(new Event('change'" in confirm
    assert 'LEGACY DROP ZERO-CHIP RETRY' in drop
    assert "if count == 0" in drop
    assert 'genuinely accepted' in drop
    assert 'wait_until_attachments_upload_finished' not in drop
    stage1 = wave[wave.index('# STAGE 1: Drop only.'):wave.index('LEGACY STAGE 2 OF 3')]
    assert 'legacy_drop_attachment_plan' in stage1

def self_test_legacy_forced_transfer_policy() -> None:
    import inspect
    accelerator = inspect.getsource(CopilotUploadAccelerator)
    force = inspect.getsource(legacy_force_attachment_transfer)
    verify = inspect.getsource(wait_until_attachments_upload_finished)
    wave = inspect.getsource(_run_single_wave)
    assert 'Network.enable' in accelerator
    assert 'maxTotalBufferSize' in accelerator
    assert 'persistent renderer/network' in accelerator
    assert 'accelerate_upload_if_stalled' in force
    assert "dispatchEvent(new Event('change'" not in force
    assert "input_change_nudge" not in verify
    assert "await _UPLOAD_ACCELERATOR.start()" in wave
    assert "await _UPLOAD_ACCELERATOR.close()" in wave
    assert "sequential option 1" in wave and "legacy option 2" in wave

def self_test_legacy_immediate_dispatch_policy() -> None:
    import inspect
    helper = inspect.getsource(legacy_send_if_ready_now)
    wave = inspect.getsource(_run_single_wave)
    assert "state != 'ready'" in helper
    assert 'message not in current_text' in helper
    assert 'legacy_send_ready_tab' in helper
    assert 'without waiting for any other tab' in helper
    assert 'tab_number=tab_number' in helper
    assert 'tab_number=number' not in helper
    compile(helper, '<legacy_send_if_ready_now>', 'exec')
    legacy = wave[wave.index('LEGACY STAGE 1 OF 3'):wave.index('if prefetch_task is not None:')]
    stage2 = legacy[legacy.index('LEGACY STAGE 2 OF 3'):legacy.index('LEGACY STAGE 3 OF 3')]
    stage3 = legacy[legacy.index('LEGACY STAGE 3 OF 3'):]
    assert 'legacy_send_if_ready_now' in stage2
    assert 'legacy_send_if_ready_now' in stage3
    assert 'legacy_record_sent' in stage2 and 'legacy_record_sent' in stage3

def self_test_legacy_result_drain_refill_policy() -> None:
    import inspect
    wave = inspect.getsource(_run_single_wave)
    # Continuous result reuse remains drop-only first, then exact preparation.
    assert 'legacy_reuse_drop_only' in wave
    assert 'legacy_prepare_and_send_refilled_slots' in wave
    recycle = wave[wave.index('async def legacy_reuse_drop_only'):wave.index('async def legacy_prepare_and_send_refilled_slots')]
    assert 'legacy_drop_attachment_plan' in recycle
    assert 'legacy_prepare_model_and_message' not in recycle
    capture = wave[wave.index('legacy_refill_bindings:'):wave.index('# Reuse is deliberately deferred')]
    assert capture.index('legacy_reuse_drop_only') < capture.index('legacy_prepare_and_send_refilled_slots')
    assert 'binding.assert_current' in wave
    assert 'processing_flow == "staged"' in capture

def self_test_pipelined_legacy_flow_policy() -> None:
    import inspect
    drop = inspect.getsource(legacy_drop_attachment_plan)
    wave = inspect.getsource(_run_single_wave)
    assert 'browser_local_set_input_files_bulk' in drop
    assert 'wait_until_attachments_upload_finished' not in drop
    legacy = wave[wave.index('LEGACY STAGE 1 OF 3'):wave.index('if prefetch_task is not None:')]
    stage1_heading = legacy.index('LEGACY STAGE 1 OF 3')
    stage1_runtime = legacy.index('# STAGE 1: Drop only.')
    stage2 = legacy.index('LEGACY STAGE 2 OF 3')
    stage3 = legacy.index('LEGACY STAGE 3 OF 3')
    assert stage1_heading < stage1_runtime < stage2 < stage3
    # Nested stage-2 recovery helpers are intentionally declared before the
    # stage-1 runtime loop. Validate only the executable stage-1 slice, rather
    # than treating helper source as work performed during stage 1.
    stage1_body = legacy[stage1_runtime:stage2]
    stage2_body = legacy[stage2:stage3]
    stage3_body = legacy[stage3:]
    assert 'legacy_drop_attachment_plan' in stage1_body
    assert 'legacy_prepare_model_and_message' not in stage1_body
    assert 'legacy_send_if_ready_now' not in stage1_body
    assert 'legacy_reload_drop_prepare' in legacy
    assert 'legacy_prepare_model_and_message' in stage2_body
    assert 'legacy_send_if_ready_now' in stage2_body
    assert 'legacy_send_if_ready_now' in stage3_body
    assert 'LEGACY STAGE-3 -> STAGE-2' in stage3_body
    assert 'entering the regular wake/result cycle' in stage3_body

def self_test_bounded_tab_activation_policy() -> None:
    import inspect
    activation = inspect.getsource(activate_page_like_manual_selection)
    start_guard = inspect.getsource(ensure_tab_start_progress)
    wave = inspect.getsource(_run_single_wave)
    assert 'TAB_ACTIVATION_ROUTE_TIMEOUT_SECONDS' in activation
    assert '_bounded_activation_route' in activation
    assert 'TAB ACTIVATION WATCHDOG' in activation
    assert TAB_START_RECOVERY_ATTEMPTS == 2
    assert 'TabStartFreshChatRequiredError' in start_guard
    assert 'replace_unresponsive_slot_with_fresh_chat' in wave
    assert 'isinstance(exc, TabStartFreshChatRequiredError)' in wave
    assert wave.index('isinstance(exc, TabStartFreshChatRequiredError)') < wave.index('observed_count=await stable_attachment_count')
    assert 'ensure_tab_start_progress(page,args,i,"full-tab processing")' in wave
    assert 'await activate_page_like_manual_selection(page,i,"full-tab processing")' not in wave

def self_test_nonblocking_post_send_policy() -> None:
    import inspect
    handoff = inspect.getsource(fast_post_send_handoff)
    commit = inspect.getsource(commit_confirmed_send_state)
    wave = inspect.getsource(_run_single_wave)
    assert 'asyncio.wait_for' in handoff
    assert 'POST_SEND_HANDOFF_ROUTE_TIMEOUT_SECONDS' in handoff
    assert 'asyncio.to_thread(append_fully_sent_log' in commit
    critical = wave[wave.index('MESSAGE SENT: Tab {i} Send changed to Stop generating'):wave.index('async def complete_one_tab_resilient')]
    assert critical.index('commit_confirmed_send_state') < critical.index('fast_post_send_handoff')
    assert 'POST-SEND HANDOFF WATCHDOG' in critical

def self_test_preloaded_startup_policy() -> None:
    import inspect
    observer = inspect.getsource(observed_page_url)
    classifier = inspect.getsource(classify_prepared_copilot_cohort)
    acquire = inspect.getsource(acquire_run_pages_fast)
    wave = inspect.getsource(_run_single_wave)
    assert 'Target.getTargetInfo' in observer
    assert 'complete_exact_cohort' in classifier
    assert 'required_count - PREPARED_COHORT_MAX_UNRESOLVED_PAGES' in classifier
    assert 'for page in prepared' in classifier
    assert 'classify_prepared_copilot_cohort' in acquire
    assert 'preloaded_copilot_tab_is_ready(page)' not in acquire
    prepared_branch = wave[wave.index('prepared_pages, pages_requiring_navigation'):wave.index('attached:set[int]=set()')]
    assert 'if not pages_requiring_navigation:' in prepared_branch
    assert 'initial_wake_and_readiness(pages_requiring_navigation,args)' in prepared_branch
    assert 'initial_wake_and_readiness(pages,args)' not in prepared_branch

def self_test_cdp_persistence_policy() -> None:
    import inspect
    connect_source = inspect.getsource(connect_existing_edge_with_retry)
    route_source = inspect.getsource(_connect_one_cdp_route)
    target_source = inspect.getsource(_cdp_handshake_targets)
    recover_source = inspect.getsource(_run_single_wave)
    # Connection orchestration and the individual Playwright handshake are
    # intentionally modular, so test each responsibility in its own function.
    assert 'CDP_HANDSHAKE_TIMEOUT_LADDER_MS' in connect_source
    assert 'while True:' in connect_source
    assert '_fresh_cdp_version_payload' in connect_source
    assert '_connect_one_cdp_route' in connect_source
    assert 'connect_over_cdp' in route_source
    assert 'websocket' in target_source and 'http' in target_source
    assert 'async with recovery_lock' in recover_source
    assert 'recovery avoided; browser and endpoint are healthy' in recover_source
    assert 'pages[:] = rebound' in recover_source
    assert ATTACHMENT_RECOVERY_ROUTES == ("bulk_cdp", "sequential_cdp")
    assert "playwright_bulk" not in technique_rank("attachment", ("bulk_cdp", "playwright_bulk"))

def main() -> int:
    global _RUNTIME_EDGE_PORT,_RUNTIME_TABS_HIDDEN
    args = parse_args()
    confirm_large_case_model(args)
    _RUNTIME_EDGE_PORT=args.port
    _RUNTIME_TABS_HIDDEN=not args.tabs_visible
    args.cases = max(1, args.cases)
    args.max_tabs = min(MAXIMUM_TAB_COUNT, max(1, args.max_tabs))
    args.parallel_loads = min(2, max(1, args.parallel_loads))
    args.analysis_workers = min(32, max(1, args.analysis_workers))
    try:
        self_test_v24()
        self_test_failed_and_mixed_result_capture()
        self_test_target_orchestration()
        self_test_high_count_attachment_policy()
        self_test_transfer_completion_policy()
        self_test_attachment_name_policy()
        self_test_password_required_exclusion_policy()
        self_test_upload_failure_is_recoverable()
        self_test_universal_queue()
        self_test_v28_readiness_and_adaptation()
        self_test_gpt_6_sol_policy()
        self_test_legacy_stage1_drop_ack_policy()
        self_test_legacy_forced_transfer_policy()
        self_test_legacy_immediate_dispatch_policy()
        self_test_legacy_result_drain_refill_policy()
        self_test_pipelined_legacy_flow_policy()
        self_test_bounded_tab_activation_policy()
        self_test_nonblocking_post_send_policy()
        self_test_preloaded_startup_policy()
        self_test_cdp_persistence_policy()
        asyncio.run(self_test_assignment_invariants())
        asyncio.run(self_test_immediate_wake_shutdown())
        load_playwright()
        protector=EdgeFocusProtector(args.port) if not args.tabs_visible else None
        if protector is not None:
            protector.start()
        try:
            with exclusive_port_controller(args.profile_dir,args.port):
                return asyncio.run(run(args))
        finally:
            if protector is not None:
                protector.stop()
    except KeyboardInterrupt:
        print("Interrupted. Edge has been left open.")
        return 130
    except (
        FileNotFoundError,
        MissingDependencyError,
        RuntimeError,
        PlaywrightError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if _RUNTIME_TABS_HIDDEN and _RUNTIME_EDGE_PORT:
            restore_edge_windows_visible(_RUNTIME_EDGE_PORT)
        for stage in list(_RETAINED_ATTACHMENT_STAGES):
            cleanup_attachment_stage(stage)
        _RETAINED_ATTACHMENT_STAGES.clear()


# V42 Edge-only run diagnostics and work-conserving idle-slot reclamation.
EDGE_ONLY_DIAGNOSTIC_BUILD = "2026-09-22-failed-mixed-result-reuse-v63"

class _DiagnosticTee:
    def __init__(self, primary: Any, mirror: Any, stream_name: str, diagnostics: "EdgeRunDiagnostics"):
        self.primary = primary; self.mirror = mirror
        self.stream_name = stream_name; self.diagnostics = diagnostics
        self._buffer = ""
    def write(self, value: str) -> int:
        text = str(value)
        self.primary.write(text); self.primary.flush()
        self.mirror.write(text); self.mirror.flush()
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip(): self.diagnostics.event("console_line", stream=self.stream_name, message=line[-2000:])
        return len(text)
    def flush(self) -> None:
        self.primary.flush(); self.mirror.flush()
    def isatty(self) -> bool:
        return bool(getattr(self.primary, "isatty", lambda: False)())
    def fileno(self) -> int:
        return self.primary.fileno()
    @property
    def encoding(self) -> str:
        return getattr(self.primary, "encoding", "utf-8")

class EdgeRunDiagnostics:
    def __init__(self) -> None:
        configured_root = os.environ.get("CDD_DIAGNOSTICS_DIR", "").strip()
        root = (Path(configured_root).expanduser().resolve() / "browser_runs" if configured_root
                else Path(__file__).resolve().parent / DIAGNOSTIC_FOLDER_NAME / "runs")
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
        token = f"run_{stamp}_{os.getpid()}"
        self.human_path = root / f"{token}.log"
        self.structured_path = root / f"{token}_structured.txt"
        self.report_path = root / f"{token}_LLM_REPORT.md"
        self.human = self.human_path.open("w", encoding="utf-8", buffering=1)
        self.structured = self.structured_path.open("w", encoding="utf-8", buffering=1)
        self.original_stdout = sys.stdout; self.original_stderr = sys.stderr
        self.started = datetime.now().astimezone()
        self.counts: dict[str, int] = {}
        self.closed = False
    def event(self, name: str, **payload: Any) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1
        record = {"timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"), "event": name, **payload}
        self.structured.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    def install(self) -> None:
        sys.stdout = _DiagnosticTee(self.original_stdout, self.human, "stdout", self)
        sys.stderr = _DiagnosticTee(self.original_stderr, self.human, "stderr", self)
        self.event("run_start", build=EDGE_ONLY_DIAGNOSTIC_BUILD, pid=os.getpid(), human_log=str(self.human_path), structured_txt=str(self.structured_path), llm_report=str(self.report_path))
        _BUILTIN_PRINT(f"RUN LOG: {self.human_path}", file=sys.stdout, flush=True)
        _BUILTIN_PRINT(f"STRUCTURED LOG: {self.structured_path}", file=sys.stdout, flush=True)
        _BUILTIN_PRINT(f"LLM REPORT: {self.report_path}", file=sys.stdout, flush=True)
    def close(self, outcome: str, exit_code: int) -> None:
        if self.closed: return
        self.event("run_finish", outcome=outcome, exit_code=exit_code)
        sys.stdout = self.original_stdout; sys.stderr = self.original_stderr
        report = [
            f"## LLM diagnostic report {self.started.strftime('%Y%m%d_%H%M%S')}", "",
            f"- Build: `{EDGE_ONLY_DIAGNOSTIC_BUILD}`",
            f"- Outcome: {outcome}", f"- Exit code: {exit_code}",
            f"- Human log: `{self.human_path.name}`",
            f"- Structured events: `{self.structured_path.name}`", "",
            "### Key event counts", "", "```json",
            json.dumps(self.counts, indent=2, sort_keys=True), "```", "",
            "### Operational note", "",
            "Idle or previously failed Edge slots are reconsidered while queued work remains. A slot-local failure returns the claimed workload to the queue and applies a bounded cooldown instead of permanently removing that slot from the run.",
        ]
        self.report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
        self.human.close(); self.structured.close(); self.closed = True

_original_edge_only_main_v42 = main

def main() -> int:
    diagnostics = EdgeRunDiagnostics()
    diagnostics.install()
    code = 1; outcome = "failed"
    try:
        code = _original_edge_only_main_v42()
        outcome = "completed" if code == 0 else "completed_with_errors"
        return code
    except BaseException as exc:
        outcome = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        diagnostics.event("uncaught_exception", error=concise_error(exc), traceback=traceback.format_exc())
        raise
    finally:
        diagnostics.close(outcome, code)

if __name__ == "__main__":
    raise SystemExit(main())
