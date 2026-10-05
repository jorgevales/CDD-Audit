#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restartable, menu-driven CCLA IP batch preparation (1 to 10 batches)."""
from __future__ import annotations

import csv
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path.home() / "CopilotCaseAutomation"
TEMP_BATCH_DIR = PROJECT_ROOT / "IPs_Documents_Analysis" / "Temporary_100_batch_IP_files"
MERGED_PDFS_DIR = TEMP_BATCH_DIR / "Merged_PDFs"
SOURCE_DATA_DIR = PROJECT_ROOT / "source_data" / "data"
READY_FOR_AI_DIR = PROJECT_ROOT / "Copilot outputs" / "ready_for_AI"
WORKING_CSV = READY_FOR_AI_DIR / "07_Interested_Parties_Last_Changes_name_and_birth_15576.csv"
SOURCE_COPY_CSV = READY_FOR_AI_DIR / "07_Interested_Parties_Last_Changes_name_and_birth_15576 copy.csv"
MERGER_SCRIPT = PROJECT_ROOT / "auxiliary_scripts" / "07_merge_change_folders_to_pdf_v19_delayed_file_progress.py"

CHANGE_RE = re.compile(r"^Change_(\d+)(?:_|$)", re.I)
CHANGE_PDF_RE = re.compile(r"^Change_(\d+)(?:_|$).*\.pdf$", re.I)
BATCH_SIZE = 100
DELETE_RETRIES = 3
DELETE_WORKERS = min(16, max(4, (os.cpu_count() or 8)))
COPY_THREADS = 32
PDF_DELETE_WORKERS = min(16, max(4, (os.cpu_count() or 8)))


@dataclass(frozen=True)
class BatchPlan:
    start: int
    end: int
    source_folder: Path

    @property
    def label(self) -> str:
        return f"{self.start:05d}-{self.end:05d}"



def say(message: str = "") -> None:
    print(message, flush=True)


def confirm(prompt: str, destructive: bool = False) -> bool:
    expected = "DELETE" if destructive else "Y"
    instruction = "Type DELETE to confirm" if destructive else "Enter Y to continue"
    try:
        return input(f"\n{prompt}\n{instruction}: ").strip().upper() == expected
    except (EOFError, KeyboardInterrupt):
        say("\nCancelled.")
        return False


def require_path(path: Path, description: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{description} does not exist or is unavailable: {path}")


def continuous_ranges(values: Iterable[int]) -> list[tuple[int, int]]:
    values = sorted(set(values))
    if not values:
        return []
    result, start, previous = [], values[0], values[0]
    for value in values[1:]:
        if value != previous + 1:
            result.append((start, previous))
            start = value
        previous = value
    result.append((start, previous))
    return result


def batch_bounds(change_id: int) -> tuple[int, int]:
    start = ((change_id - 1) // BATCH_SIZE) * BATCH_SIZE + 1
    return start, start + BATCH_SIZE - 1


def scan_change_folders() -> list[tuple[int, Path]]:
    require_path(TEMP_BATCH_DIR, "Temporary batch folder")
    found = []
    for entry in TEMP_BATCH_DIR.iterdir():
        if not entry.is_dir() or entry.name.casefold() == "merged_pdfs":
            continue
        match = CHANGE_RE.match(entry.name)
        if match:
            found.append((int(match.group(1)), entry))
    return sorted(found, key=lambda item: (item[0], item[1].name.casefold()))


def present_existing_ranges(found: list[tuple[int, Path]]) -> None:
    ids = [change_id for change_id, _ in found]
    say("\nSTEP 1 - Existing temporary Change folders")
    if not found:
        say("No Change_* folders were found. Merged_PDFs remains protected.")
        return
    say(f"Detected {len(found)} folder(s), representing {len(set(ids))} unique Change ID(s).")
    say("Continuous range(s): " + ", ".join(
        f"{a:05d}" if a == b else f"{a:05d}-{b:05d}" for a, b in continuous_ranges(ids)
    ))
    grouped: dict[tuple[int, int], set[int]] = {}
    for change_id in set(ids):
        grouped.setdefault(batch_bounds(change_id), set()).add(change_id)
    for (start, end), present in sorted(grouped.items()):
        missing = BATCH_SIZE - len(present)
        status = "COMPLETE" if not missing else f"INCOMPLETE: {len(present)}/100 IDs present, {missing} missing"
        say(f"  Batch {start:05d}-{end:05d}: {status}")


def make_writable(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE | (stat.S_IEXEC if path.is_dir() else 0))
    except OSError:
        pass


def rmtree_error(function, path, exc_info) -> None:
    """Repair only the item that failed, avoiding a slow pre-scan of all files."""
    target = Path(path)
    make_writable(target)
    if os.name == "nt":
        subprocess.run(
            ["attrib", "-R", "-S", "-H", str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    try:
        function(path)
    except OSError:
        pass


def extended_windows_path(path: Path) -> Path:
    """Return a Windows extended-length path for long-path deletion."""
    absolute = os.path.abspath(str(path))
    slash = chr(92)
    prefix = slash * 2 + '?' + slash
    if absolute.startswith(prefix):
        return Path(absolute)
    if absolute.startswith(slash * 2):
        return Path(prefix + 'UNC' + slash + absolute[2:])
    return Path(prefix + absolute)


def force_delete_folder(folder: Path) -> tuple[bool, str]:
    """Three fast attempts. Automatically return failure so the caller can skip."""
    last_error = "Unknown deletion failure"
    for attempt in range(1, DELETE_RETRIES + 1):
        try:
            if not folder.exists():
                return True, ""
            if os.name == "nt":
                # Native rmdir is generally faster for very large Windows directory trees.
                completed = subprocess.run(
                    ["cmd", "/d", "/c", "rmdir", "/s", "/q", str(folder)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if not folder.exists():
                    return True, ""
                last_error = (completed.stderr or f"native rmdir exit code {completed.returncode}").strip()
            else:
                shutil.rmtree(folder, onerror=rmtree_error)
                if not folder.exists():
                    return True, ""
        except Exception as exc:
            last_error = str(exc)
        # Fallback repairs only encountered read-only items.
        try:
            shutil.rmtree(folder, onerror=rmtree_error)
            if not folder.exists():
                return True, ""
        except Exception as exc:
            last_error = str(exc)
        if attempt < DELETE_RETRIES:
            time.sleep(0.2 * attempt)
    if os.name == "nt" and folder.exists():
        # Extended-length paths can delete files that ordinary rmdir cannot reach.
        try:
            shutil.rmtree(extended_windows_path(folder), onerror=rmtree_error)
            if not folder.exists():
                return True, ""
            last_error = f"extended-length deletion left folder behind; {last_error}"
        except Exception as exc:
            last_error = f"extended-length deletion failed: {exc}; previous: {last_error}"
    return False, last_error


def delete_change_folders(found: list[tuple[int, Path]]) -> tuple[int, list[tuple[Path, str]]]:
    """Delete independent Change folders concurrently and auto-skip locked ones."""
    protected = MERGED_PDFS_DIR.resolve(strict=False)
    targets = []
    root = TEMP_BATCH_DIR.resolve(strict=False)
    for _, folder in found:
        if (folder.is_symlink() or folder.parent.resolve(strict=False) != root
                or folder.resolve(strict=False) == protected
                or not CHANGE_RE.match(folder.name)):
            raise RuntimeError(f"Safety stop: unsafe Change folder deletion target: {folder}")
        targets.append(folder)

    deleted = 0
    skipped: list[tuple[Path, str]] = []
    workers = min(DELETE_WORKERS, max(1, len(targets)))
    say(f"Fast deletion plan: {workers} parallel worker(s), {DELETE_RETRIES} attempt(s) per folder.")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(force_delete_folder, folder): folder for folder in targets}
        completed_count = 0
        for future in as_completed(futures):
            folder = futures[future]
            completed_count += 1
            try:
                success, reason = future.result()
            except Exception as exc:
                success, reason = False, str(exc)
            if success:
                deleted += 1
            else:
                skipped.append((folder, reason))
            if completed_count == len(targets) or completed_count % 10 == 0:
                say(f"Deletion progress: {completed_count}/{len(targets)} checked | {deleted} deleted | {len(skipped)} skipped")
    return deleted, sorted(skipped, key=lambda item: item[0].name.casefold())


def detect_encoding(path: Path) -> str:
    if path.read_bytes()[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    for encoding in ("utf-8", "cp1252"):
        try:
            path.read_text(encoding=encoding)
            return encoding
        except UnicodeDecodeError:
            pass
    return "utf-8"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]], csv.Dialect, str]:
    encoding = detect_encoding(path)
    with path.open("r", encoding=encoding, newline="") as handle:
        sample = handle.read(65536)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader.fieldnames), [dict(row) for row in reader], dialect, encoding


def id_column(fields: list[str]) -> str:
    for field in fields:
        if field.strip().casefold() == "change_id":
            return field
    raise KeyError("Required column 'change_id' was not found.")


def parse_id(value: object) -> int | None:
    match = re.search(r"\d+", "" if value is None else str(value).strip())
    return int(match.group()) if match else None


def unrelated_pdfs(plan: BatchPlan) -> list[Path]:
    if not MERGED_PDFS_DIR.exists():
        return []
    result = []
    for path in MERGED_PDFS_DIR.iterdir():
        if not path.is_file() or path.suffix.casefold() != ".pdf":
            continue
        match = CHANGE_PDF_RE.match(path.name)
        if match and not plan.start <= int(match.group(1)) <= plan.end:
            result.append(path)
    return sorted(result, key=lambda path: path.name.casefold())


def delete_pdfs(paths: list[Path]) -> str:
    def remove(path: Path) -> None:
        make_writable(path)
        path.unlink(missing_ok=True)
    workers = min(PDF_DELETE_WORKERS, max(1, len(paths)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(remove, paths))
    return f"Deleted {len(paths)} unrelated PDF(s) with {workers} worker(s). Folders and non-PDF files were preserved."


MENU = {
    1: 'Inspect current Change folders and batch status (read-only)',
    2: 'Delete out-of-range temporary Change folders (not archive)',
    3: 'Copy selected batch folders into the temporary directory',
    4: 'Add selected batch rows to the working CSV',
    5: 'Delete recognised merged PDFs outside the selected range',
    6: 'Generate merged PDFs for the selected range',
    7: 'Run complete workflow (steps 1-6)',
}


def choose_steps() -> list[int]:
    say('\nCCLA IP BATCH PREPARATION')
    for number, title in MENU.items():
        say(f'{number}. {title}')
    say('0. Exit')
    while True:
        raw = input('Select one option or comma-separated options: ').strip()
        if raw == '0':
            return []
        tokens = [x.strip() for x in raw.split(',')]
        if not tokens or any(not x.isdigit() or int(x) not in MENU for x in tokens):
            say('Enter menu numbers 1-7 separated by commas, or 0 to exit.')
            continue
        numbers = [int(x) for x in tokens]
        if 7 in numbers and len(numbers) != 1:
            say('Select 7 alone for the complete workflow.')
            continue
        if len(numbers) != len(set(numbers)):
            say('Do not repeat menu options.')
            continue
        return list(range(1, 7)) if numbers == [7] else sorted(numbers)


def choose_count() -> int:
    while True:
        raw = input('How many consecutive batches (1-10)? ').strip()
        if raw.isdecimal() and 1 <= int(raw) <= 10:
            return int(raw)
        say('Please enter a whole number from 1 to 10.')


def working_highest() -> int:
    require_path(WORKING_CSV, 'Working CSV')
    fields, rows, _, _ = read_csv(WORKING_CSV)
    column = id_column(fields)
    ids = [x for row in rows if (x := parse_id(row.get(column))) is not None]
    if not ids:
        raise ValueError('No valid change_id values in working CSV.')
    return max(ids)


def choose_start(steps: list[int], count: int) -> int:
    highest = working_highest()
    default = highest + 1
    if default < 1 or (default - 1) % BATCH_SIZE:
        say(f'WARNING: Working CSV highest ID {highest} is inside a batch; default is the next complete batch. Enter the original batch start to recover an incomplete CSV update.')
        default = batch_bounds(highest)[1] + 1
    existing = scan_change_folders() if TEMP_BATCH_DIR.exists() else []
    candidates = sorted({batch_bounds(n)[0] for n, _ in existing})
    say(f'Working CSV highest ID: {highest:05d}; default next start: {default:05d}.')
    if candidates:
        say('Existing temporary batch starts: ' + ', '.join(f'{n:05d}' for n in candidates))
    say('For recovery, enter the original first batch ID; Enter uses the next batch after the working CSV.')
    while True:
        raw = input(f'First Change ID [{default:05d}]: ').strip()
        if not raw:
            return default
        if raw.isdecimal() and int(raw) > 0 and (int(raw) - 1) % BATCH_SIZE == 0:
            return int(raw)
        say('Enter a positive first ID of a 100-ID batch (for example 05401).')


def make_plans(start: int, count: int) -> list[BatchPlan]:
    return [BatchPlan(start + i * BATCH_SIZE, start + (i + 1) * BATCH_SIZE - 1,
                      SOURCE_DATA_DIR / f'Batch_{start + i * BATCH_SIZE:05d}_to_{start + (i + 1) * BATCH_SIZE - 1:05d}')
            for i in range(count)]


def source_rows(plans: list[BatchPlan]) -> tuple[list[str], list[dict[str, str]], str]:
    require_path(SOURCE_COPY_CSV, 'Source copy CSV')
    fields, rows, _, _ = read_csv(SOURCE_COPY_CSV)
    column = id_column(fields)
    start, end = plans[0].start, plans[-1].end
    selected = [row for row in rows if (n := parse_id(row.get(column))) is not None and start <= n <= end]
    return fields, selected, column


def csv_report(plans: list[BatchPlan], strict: bool) -> tuple[list[dict[str, str]], str]:
    _, selected, column = source_rows(plans)
    problems = []
    for plan in plans:
        subset = [r for r in selected if plan.start <= parse_id(r.get(column)) <= plan.end]
        unique = {parse_id(r.get(column)) for r in subset}
        missing = sorted(set(range(plan.start, plan.end + 1)) - unique)
        say(f'  CSV batch {plan.label}: {len(subset)} row(s), {len(unique)}/100 unique IDs; missing {len(missing)}' +
            (f' (first: {", ".join(str(n) for n in missing[:8])})' if missing else ''))
        if missing or len(subset) != BATCH_SIZE:
            problems.append(plan.label)
    if strict and problems:
        raise ValueError('Incomplete or duplicate source CSV IDs in batch(es): ' + ', '.join(problems))
    return selected, column


def safe_target(source: Path, destination: Path) -> bool:
    if source.name.casefold() == 'merged_pdfs' or destination.name.casefold() == 'merged_pdfs':
        return False
    return True


def copy_one(source: Path, destination: Path) -> tuple[int, int, int]:
    """Incrementally copy missing/changed files; never remove destination content."""
    if not safe_target(source, destination):
        return 0, 1, 0
    if source.is_dir() and not source.is_symlink():
        if destination.exists() and not destination.is_dir():
            raise RuntimeError(f'Destination is not a directory: {destination}')
        destination.mkdir(parents=True, exist_ok=True)
        totals = [0, 0, 0]
        for child in source.iterdir():
            result = copy_one(child, destination / child.name)
            totals = [a + b for a, b in zip(totals, result)]
        return tuple(totals)
    if source.is_symlink():
        raise RuntimeError(f'Symbolic link not copied: {source}')
    if destination.exists() and not destination.is_file():
        raise RuntimeError(f'Destination is not a file: {destination}')
    if destination.exists():
        a, b = source.stat(), destination.stat()
        if a.st_size == b.st_size and abs(a.st_mtime_ns - b.st_mtime_ns) < 2_000_000_000:
            return 0, 1, 0
        if b.st_mtime_ns > a.st_mtime_ns + 2_000_000_000:
            raise RuntimeError(f'Destination is newer; refusing overwrite: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    updated = int(destination.exists())
    shutil.copy2(source, destination)
    return int(not updated), 0, updated


def copy_batch(plan: BatchPlan) -> str:
    require_path(plan.source_folder, f'Batch {plan.label} source folder')
    if not plan.source_folder.is_dir():
        raise ValueError(f'Batch {plan.label} source is not a directory')
    entries = [p for p in plan.source_folder.iterdir() if p.name.casefold() != 'merged_pdfs']
    for entry in entries:
        match = CHANGE_RE.match(entry.name)
        if match and not plan.start <= int(match.group(1)) <= plan.end:
            raise ValueError(f'Batch {plan.label} source contains out-of-range Change folder: {entry.name}')
    if not entries:
        raise ValueError(f'Batch {plan.label} source folder is empty')
    TEMP_BATCH_DIR.mkdir(parents=True, exist_ok=True)
    copied = skipped = updated = 0
    for entry in entries:
        target = TEMP_BATCH_DIR / entry.name
        if os.name == 'nt' and shutil.which('robocopy') and entry.is_dir() and not entry.is_symlink():
            # /XO protects newer destination files; /E resumes partial directory copies.
            # /XD excludes protected directories at every depth; no /MIR or /PURGE.
            if target.exists() and not target.is_dir():
                raise RuntimeError(f'Destination is not a directory: {target}')
            cmd = ['robocopy', str(entry), str(target), '/E', f'/MT:{COPY_THREADS}',
                   '/R:2', '/W:1', '/COPY:DAT', '/DCOPY:DAT', '/XO',
                   '/NP', '/NFL', '/NDL', '/NJH', '/NJS', '/XD', 'Merged_PDFs']
            done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, errors='replace',
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if done.returncode > 7:
                raise RuntimeError(f'Batch {plan.label} Robocopy exit {done.returncode}: {done.stdout[-2000:]}')
            say(f'  [{plan.label}] Robocopy {entry.name}: exit {done.returncode} (0 = already current)')
            if done.returncode == 0:
                skipped += 1
            else:
                updated += 1  # Robocopy reports changed top-level trees, not file counts.
        else:
            a, b, c = copy_one(entry, target)
            copied += a; skipped += b; updated += c
    return f'copied {copied}, skipped {skipped}, updated {updated} (Robocopy counts top-level trees)'


def update_csv(plans: list[BatchPlan]) -> str:
    selected, source_column = csv_report(plans, strict=True)
    fields, existing, dialect, encoding = read_csv(WORKING_CSV)
    target_column = id_column(fields)
    source_fields, _, _ = source_rows(plans)
    missing_fields = [f for f in fields if f != target_column and f not in source_fields]
    if missing_fields:
        raise ValueError('Source CSV lacks working columns: ' + ', '.join(missing_fields))
    existing_ids = {parse_id(r.get(target_column)) for r in existing}
    # Preserve the original line-ending convention, not only CSV dialect/encoding.
    with WORKING_CSV.open('rb') as original:
        sample = original.read(65536)
    newline = '\r\n' if b'\r\n' in sample else ('\n' if b'\n' in sample else dialect.lineterminator)
    seen = set(existing_ids)
    additions = []
    already = 0
    for row in selected:
        n = parse_id(row.get(source_column))
        if n in seen:
            already += 1
            continue
        seen.add(n)
        mapped = {f: row.get(f, '') for f in fields}
        mapped[target_column] = row[source_column]
        additions.append(mapped)
    counts = f'source rows {len(selected)}, unique IDs {len({parse_id(r.get(source_column)) for r in selected})}, already present {already}, newly added {len(additions)}'
    if not additions:
        return 'ALREADY COMPLETE; ' + counts
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup = WORKING_CSV.with_name(f'{WORKING_CSV.stem}_backup_{stamp}{WORKING_CSV.suffix}')
    fd, name = tempfile.mkstemp(prefix=WORKING_CSV.stem + '_', suffix='.tmp', dir=WORKING_CSV.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding=encoding, newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, dialect=dialect, extrasaction='ignore', lineterminator=newline)
            writer.writeheader(); writer.writerows(existing); writer.writerows(additions)
            handle.flush(); os.fsync(handle.fileno())
        shutil.copy2(WORKING_CSV, backup)
        os.replace(temporary, WORKING_CSV)
    finally:
        temporary.unlink(missing_ok=True)
    return counts + f'; backup {backup.name}'


def inspect(plans: list[BatchPlan]) -> str:
    found = scan_change_folders() if TEMP_BATCH_DIR.exists() else []
    if found:
        present_existing_ranges(found)
    else:
        say('No temporary Change folders (or temporary directory is missing).')
    for plan in plans:
        present = {n for n, _ in found if plan.start <= n <= plan.end}
        say(f'  [{plan.label}] temporary IDs: {len(present)}/100; source folder: {"present" if plan.source_folder.is_dir() else "MISSING"}')
    if SOURCE_COPY_CSV.is_file():
        csv_report(plans, strict=False)
    else:
        say(f'Source CSV missing: {SOURCE_COPY_CSV}')
    return 'read-only inspection complete'


def clean_folders(plans: list[BatchPlan]) -> str:
    found = [(n, p) for n, p in scan_change_folders() if not plans[0].start <= n <= plans[-1].end]
    if not found:
        return 'ALREADY COMPLETE; no out-of-range Change folders'
    say(f'{len(found)} out-of-range Change folders will be deleted; active range {plans[0].label} to {plans[-1].label} is protected.')
    for _, folder in found[:10]:
        say('  ' + str(folder))
    if not confirm('Delete these out-of-range Change folders? Merged_PDFs is protected.', destructive=True):
        return 'CANCELLED; no Change folders deleted'
    deleted, failures = delete_change_folders(found)
    if failures:
        say(f'WARNING: {len(failures)} folder(s) left behind for manual cleanup:')
        for folder, reason in failures:
            say(f'  LEFT BEHIND: {folder.name} | {reason}')
    return (f'deleted {deleted} out-of-range Change folders; '
            f'{len(failures)} left behind for manual cleanup (workflow continues)')


def clean_pdfs(plans: list[BatchPlan]) -> str:
    pdfs = unrelated_pdfs(BatchPlan(plans[0].start, plans[-1].end, SOURCE_DATA_DIR))
    say(f'Active PDF range: {plans[0].start:05d}-{plans[-1].end:05d}; recognised out-of-range PDFs: {len(pdfs)}')
    for path in pdfs[:10]:
        say('  ' + path.name)
    if len(pdfs) > 10:
        say(f'  ... and {len(pdfs)-10} more')
    if not pdfs:
        return 'ALREADY COMPLETE; no recognised out-of-range PDFs'
    if not confirm('Delete only these recognised out-of-range PDFs?', destructive=True):
        return 'CANCELLED; no PDFs deleted'
    return delete_pdfs(pdfs)


def merge_pdfs(plans: list[BatchPlan]) -> str:
    require_path(MERGER_SCRIPT, 'PDF merger script')
    require_path(TEMP_BATCH_DIR, 'Temporary batch folder')
    present = {n for n, _ in scan_change_folders()}
    missing = [n for n in range(plans[0].start, plans[-1].end + 1) if n not in present]
    if missing:
        raise ValueError(f'Merger prerequisite: {len(missing)} Change folders missing in active range; first IDs: {missing[:10]}')
    command = [sys.executable, str(MERGER_SCRIPT), '--from-id', str(plans[0].start),
               '--to-id', str(plans[-1].end), '--yes']
    say(f'Launching merger once for {plans[0].start:05d}-{plans[-1].end:05d} (existing valid PDFs are skipped by merger).')
    code = subprocess.run(command, cwd=str(MERGER_SCRIPT.parent)).returncode
    if code:
        raise RuntimeError(f'Merger failed with exit code {code}; inspect its status log for individual cases')
    return 'merger completed (including any already-valid PDFs skipped by merger)'


def show_plan(steps: list[int], plans: list[BatchPlan]) -> None:
    say(f'\nSelected {len(plans)} batch(es); overall range {plans[0].start:05d}-{plans[-1].end:05d}')
    for plan in plans:
        say(f'  Batch {plan.label}: source {plan.source_folder}' +
            (' [MISSING]' if not plan.source_folder.is_dir() else ''))
    say(f'Temporary destination: {TEMP_BATCH_DIR}\nProtected PDFs: {MERGED_PDFS_DIR}')
    say(f'Working CSV: {WORKING_CSV}\nSource CSV: {SOURCE_COPY_CSV}\nMerger: {MERGER_SCRIPT}')
    say('Selected operations: ' + ', '.join(f'{n} {MENU[n]}' for n in steps))
    if SOURCE_COPY_CSV.is_file() and (3 in steps or 4 in steps or 7 in steps):
        csv_report(plans, strict=False)
    if 5 in steps:
        say(f'Recognised out-of-range PDFs: {len(unrelated_pdfs(BatchPlan(plans[0].start, plans[-1].end, SOURCE_DATA_DIR)))}')


def preflight(steps: list[int], plans: list[BatchPlan]) -> None:
    if 3 in steps:
        for plan in plans:
            require_path(plan.source_folder, f'Batch {plan.label} source folder')
            if not plan.source_folder.is_dir() or not any(plan.source_folder.iterdir()):
                raise ValueError(f'Batch {plan.label} source folder is empty or invalid')
    if 4 in steps:
        # Validate all requested IDs before CSV modification (and before a full workflow starts).
        csv_report(plans, strict=True)
    if 4 in steps:
        require_path(WORKING_CSV, 'Working CSV')
    if 6 in steps:
        require_path(MERGER_SCRIPT, 'PDF merger script')


def main() -> int:
    results: list[tuple[str, str, str]] = []
    try:
        steps = choose_steps()
        if not steps:
            say('Exited without changes.'); return 0
        count = choose_count()
        start = choose_start(steps, count)
        plans = make_plans(start, count)
        show_plan(steps, plans)
        if not confirm('Run only the selected operations?'):
            say('Cancelled without changes.'); return 0
        preflight(steps, plans)
        for step in steps:
            label = f'{step} {MENU[step]}'
            say(f'\nSTEP {label}')
            try:
                if step == 1: message = inspect(plans)
                elif step == 2: message = clean_folders(plans)
                elif step == 3:
                    messages = []
                    for plan in plans:
                        try:
                            msg = copy_batch(plan)
                            say(f'  [{plan.label}] {msg}')
                            messages.append(f'{plan.label}: {msg}')
                        except Exception as exc:
                            raise RuntimeError(f'batch {plan.label} copy failed: {exc}') from exc
                    message = '; '.join(messages)
                elif step == 4: message = update_csv(plans)
                elif step == 5: message = clean_pdfs(plans)
                else: message = merge_pdfs(plans)
                status = 'SKIPPED' if message.startswith(('ALREADY COMPLETE', 'CANCELLED')) else 'SUCCESS'
                results.append((label, status, message))
                say(f'[{status}] {message}')
                if message.startswith('CANCELLED'):
                    say('Stopped after cancellation; later steps were not run.')
                    break
            except Exception as exc:
                results.append((label, 'FAILED', str(exc)))
                say(f'[FAILED] {label}: {exc}')
                break  # Stop on first failure; rerun only this step after resolving it.
    except (EOFError, KeyboardInterrupt):
        say('\nCancelled.'); return 0
    except Exception as exc:
        results.append(('planning/preflight', 'FAILED', str(exc)))
        say(f'FAILED before execution: {exc}')
    say('\nFINAL SUMMARY')
    for label, status, detail in results:
        say(f'  {status}: {label}: {detail}')
    say('Totals: ' + ', '.join(f'{status.lower()}={sum(x[1] == status for x in results)}'
                              for status in ('SUCCESS', 'SKIPPED', 'FAILED')))
    return 1 if any(x[1] == 'FAILED' for x in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
