"""Dependency-free, loopback-only interface for the existing workflow engines."""
from __future__ import annotations

import hmac
import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from collections import deque
from dataclasses import asdict, fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .config import APP_DIR, CONFIG_PATH, WorkflowConfig
from .orchestrator import WorkflowOrchestrator
from .preflight import Check, has_errors, run_preflight
from .setup_form import FIELD_SPECS, GROUPS, validate_field, validate_run

WEB_DIR = Path(__file__).parent / "web"
NUMBERS = {"edge_debug_port", "start_batch", "batch_count", "cases_to_process", "browser_tabs"}


def run_model_check(config_path: Path) -> dict:
    """Release Playwright and the browser engine when the one-shot check finishes."""
    python = str(Path(sys.executable).with_name("python.exe")) if Path(sys.executable).name.lower() == "pythonw.exe" else sys.executable
    with tempfile.TemporaryDirectory(prefix="cdd_model_check_") as temporary:
        output = Path(temporary) / "report.json"
        result = subprocess.run(
            [python, "-m", "workflow.model_check", "--config", str(config_path.resolve()), "--output", str(output)],
            cwd=str(APP_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if output.is_file() and output.stat().st_size <= 262144:
            report = json.loads(output.read_text(encoding="utf-8"))
            if isinstance(report, dict) and report.get("status") in {"verified", "partial", "blocked"} and isinstance(report.get("models"), list):
                return report
        raise RuntimeError(f"The model check produced no valid report (exit code {result.returncode}).")


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class WorkflowService:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.lock = threading.RLock()
        self.picker_lock = threading.Lock()
        self.warning = ""
        try:
            self.config = WorkflowConfig.load(config_path)
        except (OSError, ValueError, TypeError, AttributeError):
            self.config = WorkflowConfig.defaults()
            self.warning = "Saved settings could not be read. Review the defaults before continuing."
        self.events = deque(maxlen=300)
        self.cursor = 0
        self.ready_config = None
        self.checks = []
        self.busy = False
        self.checking = False
        self.mode = ""
        self.status = "Ready to configure"
        self.orchestrator = None
        self.worker = None
        self.stop_requested = False
        self.stage = ""
        self.model_checks = None

    def emit(self, kind, message):
        with self.lock:
            if kind == "log" and not self.config.diagnostic_mode:
                return
            self.cursor += 1
            self.events.append({"id": self.cursor, "kind": kind, "message": str(message), "time": time.time()})
            if kind == "stage":
                self.stage = message
                self.status = {"prepare": "Preparing cases", "merge": "Creating PDFs", "copilot": "Reviewing in Copilot", "master": "Building master workbooks"}.get(message, message)
            elif kind in {"progress", "complete", "warning", "error"}:
                self.status = str(message)[:220]
            if kind == "error":
                self.ready_config = None

    def state(self, after=0):
        with self.lock:
            return {"status": self.status, "busy": self.busy, "checking": self.checking,
                    "running": self.busy and not self.checking, "ready": self.ready_config is not None,
                    "mode": self.mode, "checks": self.checks, "cursor": self.cursor,
                    "stage": self.stage, "stop_requested": self.stop_requested,
                    "model_checks": self.model_checks,
                    "events": [e for e in self.events if e["id"] > after], "warning": self.warning,
                    "run_status": self.orchestrator.state.status if self.orchestrator else "idle"}

    def collect(self, values):
        if not isinstance(values, dict):
            raise ApiError("Settings must be an object.")
        data = asdict(self.config)
        allowed = {f.name for f in fields(WorkflowConfig)}
        if set(values) - allowed:
            raise ApiError("Unknown settings field.")
        data.update(values)
        for key, value in data.items():
            if key in NUMBERS:
                if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
                    raise ApiError(f"{key.replace('_', ' ')} must be a whole number.")
                data[key] = int(value)
            elif key == "diagnostic_mode":
                if not isinstance(value, bool):
                    raise ApiError("Diagnostic mode must be true or false.")
            elif not isinstance(value, str) or len(value) > 32768:
                raise ApiError(f"Invalid {key.replace('_', ' ')}.")
        if not 1024 <= data["edge_debug_port"] <= 65535:
            raise ApiError("Choose a debugging port between 1024 and 65535.")
        message = validate_run(data)
        if message:
            raise ApiError(message)
        return WorkflowConfig(**data)

    def _idle(self):
        if self.busy:
            raise ApiError("Wait for the active operation to finish.", 409)

    def save(self, config):
        config.save(self.config_path)
        if asdict(config) != asdict(self.config):
            self.ready_config = None
            self.checks = []
            self.model_checks = None
        self.config = config

    def check_models(self, config):
        with self.lock:
            self._idle()
            self.save(config)
            self.model_checks = None
            self.busy = self.checking = True
            self.mode = "model_check"
            self.status = "Checking the six models in your Copilot browser…"
        def work():
            try:
                report = run_model_check(self.config_path)
            except Exception:
                self.log_exception("Copilot model check failed")
                report = {"status": "blocked", "models": [], "error": "The model check could not finish. Check browser access and diagnostic logs."}
            with self.lock:
                self.model_checks = report
                self.busy = self.checking = False
                if report["status"] == "verified":
                    self.emit("progress", "All six models were selected successfully in the Copilot Chat picker.")
                elif report["status"] == "partial":
                    self.emit("warning", "Some models could not be selected. Review the availability results before running.")
                else:
                    self.emit("warning", report.get("error", "Open and sign in to your dedicated Copilot browser, then check models again."))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def preflight(self, config):
        with self.lock:
            self._idle()
            self.save(config)
            self.ready_config = None
            self.checks = []
            self.busy = self.checking = True
            self.status = "Checking setup…"
        def work():
            try:
                invalid = [Check("error", FIELD_SPECS[key][1], detail) for key in FIELD_SPECS
                           for valid, detail in [validate_field(key, getattr(config, key))] if not valid]
                checks = invalid or run_preflight(config)
            except Exception:
                self.log_exception("Setup check failed")
                checks = [Check("error", "Setup check", "Setup check failed. Review locations and diagnostic logs.")]
            with self.lock:
                self.checks = [asdict(c) for c in checks]
                self.ready_config = asdict(config) if checks and not has_errors(checks) else None
                self.busy = self.checking = False
                self.emit("progress", "Ready to run" if self.ready_config else "Setup needs attention")
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def cleanup_preview(self, config):
        start = config.start_batch
        end = start + config.batch_count * 100 - 1
        targets = []
        for key, directory in (("temporary_batch_dir", True), ("merged_pdf_dir", False)):
            folder = config.path(key)
            if not folder.is_dir():
                continue
            for path in folder.iterdir():
                pattern = r"^Change_(\d+)(?:_|$)" if directory else r"^Change_(\d+)(?:_|$).*\.pdf$"
                match = re.match(pattern, path.name, re.I)
                if match and (path.is_dir() if directory else path.is_file()) and not start <= int(match[1]) <= end:
                    targets.append(str(path))
        return {"count": len(targets), "targets": targets[:100], "truncated": len(targets) > 100}

    def start(self, config, data):
        with self.lock:
            self._idle()
            mode = data.get("mode", "primary")
            if mode not in {"primary", "master"}:
                raise ApiError("Unknown run mode.")
            cleanup = data.get("cleanup", False)
            if not isinstance(cleanup, bool):
                raise ApiError("Cleanup must be true or false.")
            if mode == "primary":
                if self.ready_config != asdict(config):
                    raise ApiError("Check this setup successfully before starting.", 409)
                if data.get("office_acknowledged") is not True:
                    raise ApiError("Save your Office work and acknowledge the conversion notice.")
                if cleanup and data.get("cleanup_confirmation") != "DELETE":
                    raise ApiError("Confirm the cleanup preview by typing DELETE.")
            else:
                valid, detail = validate_field("analysis_output_dir", config.analysis_output_dir)
                if not valid:
                    raise ApiError(detail)
                if data.get("master_confirmed") is not True:
                    raise ApiError("Confirm building master workbooks and replacing existing masters.")
            self.save(config)
            self.orchestrator = WorkflowOrchestrator(config, self.emit)
            orchestrator = self.orchestrator
            self.busy = True
            self.mode = mode
            self.stop_requested = False
            self.stage = ""
            self.status = "Starting document review…" if mode == "primary" else "Building master workbooks…"
            def work():
                try:
                    orchestrator.run_primary(cleanup) if mode == "primary" else orchestrator.run_master()
                except Exception:
                    self.log_exception("Run failed")
                    self.emit("error", "Run failed. Open diagnostic logs for details.")
                finally:
                    with self.lock:
                        self.busy = False
            self.worker = threading.Thread(target=work, daemon=True)
            self.worker.start()

    def log_exception(self, message):
        try:
            folder = self.config_path.parent / "logs"
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / "interface.log").open("a", encoding="utf-8") as handle:
                handle.write(message + "\n" + traceback.format_exc() + "\n")
        except OSError:
            pass

    def browse(self, key, current):
        if key not in FIELD_SPECS:
            raise ApiError("Unknown location field.")
        with self.lock:
            self._idle()
        if not self.picker_lock.acquire(blocking=False):
            raise ApiError("A location picker is already open.", 409)
        try:
            # Tk exists only in this short-lived picker process, never in the application.
            script = '''import json,sys,tkinter as tk
from tkinter import filedialog
d=json.loads(sys.argv[1]); r=tk.Tk(); r.withdraw(); r.attributes('-topmost',True)
o={'parent':r,'title':d['title']}
if d['initial']: o['initialdir']=d['initial']
k=d['kind']
if 'dir' in k: p=filedialog.askdirectory(**o,mustexist=k=='input_dir')
else:
 e='.csv' if 'csv' in k else '.md' if k=='markdown' else '.exe'
 o['filetypes']=[(e+' files','*'+e)]
 p=filedialog.asksaveasfilename(**o,defaultextension=e) if k=='output_csv' else filedialog.askopenfilename(**o)
print(json.dumps({'path':p})); r.destroy()
'''
            path = Path(current).expanduser() if current else None
            initial = path if path and path.is_dir() else path.parent if path else None
            python = str(Path(sys.executable).with_name("python.exe")) if Path(sys.executable).name.lower() == "pythonw.exe" else sys.executable
            result = subprocess.run([python, "-c", script, json.dumps({"kind": FIELD_SPECS[key][2], "title": FIELD_SPECS[key][1], "initial": str(initial) if initial and initial.is_dir() else ""})], capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise ApiError("The location picker could not open. Enter or paste the path directly.")
            return json.loads(result.stdout)
        finally:
            self.picker_lock.release()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, service):
        super().__init__(address, Handler)
        self.service = service
        self.token = secrets.token_urlsafe(32)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.last_contact = time.monotonic()
        self.closed = threading.Event()

    def watch_lease(self, timeout=120, interval=5):
        while not self.closed.wait(interval):
            with self.service.lock:
                expired = not self.service.busy and time.monotonic() - self.last_contact > timeout
            if expired:
                self.shutdown()
                return

    def server_close(self):
        self.closed.set()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def authorised(self, api=False):
        if self.headers.get("Host") != self.server.origin.removeprefix("http://"):
            raise ApiError("Invalid local host.", 403)
        origin = self.headers.get("Origin")
        if origin and origin != self.server.origin:
            raise ApiError("External origins cannot access this interface.", 403)
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise ApiError("Cross-site access is blocked.", 403)
        if api and not hmac.compare_digest(self.headers.get("X-Workflow-Token", ""), self.server.token):
            raise ApiError("Invalid interface token.", 403)
        if api:
            self.server.last_contact = time.monotonic()

    def do_GET(self):
        try:
            parsed = urlsplit(self.path)
            self.authorised(parsed.path.startswith("/api/"))
            service = self.server.service
            if parsed.path == "/api/bootstrap":
                from .models import MODEL_OPTIONS
                models = [{**m, "id": m["value"], "provider": m["group"]} for m in MODEL_OPTIONS]
                groups = [{"title": title, "description": description, "fields": [dict(zip(("key", "label", "kind", "guidance"), f)) for f in group]} for title, description, group in GROUPS]
                self.reply(200, {"config": asdict(service.config), "defaults": asdict(WorkflowConfig.defaults()), "groups": groups, "models": models, "state": service.state(), "version": __version__, "demo": "demo" in service.config_path.parts})
            elif parsed.path == "/api/state":
                after = int(parse_qs(parsed.query).get("after", ["0"])[0])
                self.reply(200, service.state(after))
            elif parsed.path in {"/", "/index.html", "/app.js", "/styles.css"}:
                path = WEB_DIR / ("index.html" if parsed.path == "/" else parsed.path[1:])
                body = path.read_bytes()
                if path.suffix == ".html":
                    body = body.replace(b"__WORKFLOW_TOKEN__", self.server.token.encode("ascii"))
                self.reply(200, body, (mimetypes.guess_type(str(path))[0] or "application/octet-stream") + "; charset=utf-8")
            else:
                raise ApiError("Not found.", 404)
        except ApiError as exc:
            self.reply(exc.status, {"error": str(exc)})
        except (ValueError, OSError):
            self.reply(400, {"error": "Invalid request or interface file unavailable."})

    def do_POST(self):
        try:
            self.authorised(True)
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 262144 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ApiError("Send a JSON request smaller than 256 KB.")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ApiError("Request must be an object.")
            service = self.server.service
            path = urlsplit(self.path).path
            if path == "/api/browse":
                self.reply(200, service.browse(data.get("key"), data.get("current", "")))
                return
            if path == "/api/cleanup-preview":
                self.reply(200, service.cleanup_preview(service.collect(data.get("config", {}))))
                return
            if path == "/api/preflight":
                service.preflight(service.collect(data.get("config", {})))
            elif path == "/api/check-models":
                service.check_models(service.collect(data.get("config", {})))
            elif path == "/api/start":
                service.start(service.collect(data.get("config", {})), data)
            elif path == "/api/config":
                with service.lock:
                    service._idle()
                    service.save(service.collect(data.get("config", {})))
            elif path == "/api/stop":
                with service.lock:
                    if not service.busy or service.checking or service.mode != "primary":
                        raise ApiError("There is no active review to stop.", 409)
                    service.orchestrator.request_stop()
                    service.stop_requested = True
            elif path == "/api/open":
                key = data.get("key")
                if key not in {"analysis_output_dir", "diagnostics_dir", "merged_pdf_dir", "case_size_output_dir", "temporary_batch_dir"}:
                    raise ApiError("Unknown output folder.")
                folder = service.config.path(key)
                if not folder.is_dir():
                    raise ApiError("This folder is unavailable. Check setup or complete a run first.")
                os.startfile(folder)
            elif path == "/api/shutdown":
                with service.lock:
                    service._idle()
                self.reply(200, {"closed": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            else:
                raise ApiError("Not found.", 404)
            self.reply(200, {"state": service.state(), "config": asdict(service.config)})
        except ApiError as exc:
            self.reply(exc.status, {"error": str(exc)})
        except (ValueError, TypeError, OSError, AttributeError) as exc:
            self.reply(400, {"error": str(exc)})
        except Exception:
            self.server.service.log_exception("Interface request failed")
            self.reply(500, {"error": "The operation could not finish. Review diagnostic logs."})


def run_app(config_path: Path = CONFIG_PATH, *, port=0, open_browser=True):
    server = LocalServer(("127.0.0.1", port), WorkflowService(config_path))
    if sys.stdout:
        print(f"Document Review Workflow: {server.origin}", flush=True)
    if open_browser:
        edge = next((Path(os.path.expandvars(p)) for p in (
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        ) if Path(os.path.expandvars(p)).is_file()), None)
        try:
            if edge:
                # The interface shares regular Edge resources, never the automation CDP profile.
                subprocess.Popen([str(edge), "--app=" + server.origin, "--no-first-run"],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            elif not webbrowser.open(server.origin):
                raise OSError("No default browser could open the local interface.")
        except OSError:
            server.service.log_exception("Could not open the interface browser")
            try:
                webbrowser.open(server.origin)
            except OSError:
                server.service.log_exception("Fallback browser launch failed")
    threading.Thread(target=server.watch_lease, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        if server.service.busy:
            if server.service.orchestrator:
                server.service.orchestrator.request_stop()
            if server.service.worker:
                server.service.worker.join()
    finally:
        server.server_close()
