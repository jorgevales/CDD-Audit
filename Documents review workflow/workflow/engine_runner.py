from __future__ import annotations

import argparse
import builtins
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

from .config import APP_DIR, WorkflowConfig


REFS = APP_DIR / "Initial sanitized reference files"


def load_file(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load engine: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def configure_prepare(module: ModuleType, config: WorkflowConfig) -> None:
    module.PROJECT_ROOT = config.path("project_root")
    module.TEMP_BATCH_DIR = config.path("temporary_batch_dir")
    module.MERGED_PDFS_DIR = config.path("merged_pdf_dir")
    module.SOURCE_DATA_DIR = config.path("source_data_root")
    module.WORKING_CSV = config.path("working_csv")
    module.SOURCE_COPY_CSV = config.path("source_copy_csv")
    module.MERGER_SCRIPT = REFS / "07_merge_change_folders_to_pdf_v19_delayed_file_progress_sanitized.py"


def plans(module: ModuleType, config: WorkflowConfig):
    return module.make_plans(int(config.start_batch), int(config.batch_count))


def prepare(config: WorkflowConfig, cleanup: bool) -> int:
    module = load_file("cdd_prepare_engine", REFS / "10_prepare_next_ip_batches_long_path_cleanup_sanitized.py")
    configure_prepare(module, config)
    selected = plans(module, config)
    module.preflight([3, 4], selected)
    print(module.inspect(selected), flush=True)
    if cleanup:
        module.confirm = lambda prompt, destructive=False: True
        print(module.clean_folders(selected), flush=True)
    for plan in selected:
        print(module.copy_batch(plan), flush=True)
    print(module.update_csv(selected), flush=True)
    if cleanup:
        print(module.clean_pdfs(selected), flush=True)
    return 0


def master(config: WorkflowConfig) -> int:
    module = load_file("cdd_master_engine", REFS / "09_append_ip_analysis_to_master_100_case_batches_sanitized.py")
    folder = config.path("analysis_output_dir")
    module.SOURCE_FOLDER = folder
    module.MASTER_PATH = folder / module.MASTER_FILENAME
    module.ERROR_LOG_PATH = folder / module.ERROR_LOG_FILENAME
    original_input = builtins.input
    try:
        builtins.input = lambda prompt="": ""
        module.main()
    finally:
        builtins.input = original_input
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "master"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    config = WorkflowConfig(**json.loads(args.config.read_text(encoding="utf-8")))
    return prepare(config, args.cleanup) if args.stage == "prepare" else master(config)


if __name__ == "__main__":
    raise SystemExit(main())
