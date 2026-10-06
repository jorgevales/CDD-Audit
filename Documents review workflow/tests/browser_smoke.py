"""Manual browser acceptance checks; never sends documents to Copilot."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow.config import WorkflowConfig
from workflow.models import MODEL_OPTIONS
from workflow.web_server import LocalServer, WorkflowService


def main():
    output = Path(__file__).resolve().parents[1] / 'diagnostics' / 'web_acceptance'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        config_path = Path(folder) / 'config.json'
        WorkflowConfig.defaults().save(config_path)
        service = WorkflowService(config_path)
        server = LocalServer(('127.0.0.1', 0), service)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        errors = []
        requests = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: requests.append(request.url))
                page.goto(server.origin, wait_until='networkidle')
                page.locator('#default-model option').last.wait_for(state='attached')
                assert page.locator('#default-model option').count() == 6
                assert page.locator('#default-model').input_value() == 'GPT-6 Sol'
                page.screenshot(path=str(output / 'source.png'), full_page=True)
                page.locator('#default-model').select_option(label='Sonnet 5.5')
                page.locator('#save').click()
                page.wait_for_timeout(350)
                assert WorkflowConfig.load(config_path).default_model == 'Sonnet 5.5'
                for step in range(6):
                    page.locator('.nav-step').nth(step).click()
                    page.wait_for_timeout(220)
                    assert page.locator('#default-model').input_value() == 'Sonnet 5.5'
                    assert page.locator('body').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(output / 'activity.png'), full_page=True)
                page.locator('#master-nav').click()
                page.wait_for_timeout(220)
                page.screenshot(path=str(output / 'master.png'), full_page=True)
                page.reload(wait_until='networkidle')
                assert page.locator('#default-model').input_value() == 'Sonnet 5.5'
                # Exercise the real confirmation flow without document processing.
                service.ready_config = asdict(service.config)
                page.reload(wait_until='networkidle')
                page.locator('.nav-step').nth(5).click()
                assert page.locator('#start').is_enabled()
                page.locator('#default-model').select_option(label='Opus 5.5')
                page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
                page.wait_for_timeout(350)
                assert page.locator('#start').is_disabled(), 'Polling must not revive stale readiness'
                page.locator('#save').click()
                page.wait_for_timeout(250)
                service.ready_config = asdict(service.config)
                page.reload(wait_until='networkidle')
                page.locator('.nav-step').nth(3).click()
                page.locator('#cleanup').check()
                page.locator('.nav-step').nth(5).click()
                page.locator('#start').click()
                page.locator('#modal-confirm').click()
                page.locator('#confirm-text').wait_for()
                assert page.locator('#modal-confirm').is_disabled()
                page.keyboard.press('Escape')
                page.wait_for_timeout(200)
                assert not service.busy and service.orchestrator is None, 'Escape must cancel cleanup'
                calls = []
                class SimulatedOrchestrator:
                    def __init__(self, config, emit):
                        self.state = SimpleNamespace(status='created')
                        self.emit = emit
                    def run_primary(self, cleanup):
                        calls.append(cleanup)
                        self.state.status = 'complete'
                        self.emit('complete', 'SIMULATED workflow: browser confirmation test only')
                with patch('workflow.web_server.WorkflowOrchestrator', SimulatedOrchestrator):
                    page.locator('#start').click()
                    page.locator('#modal-confirm').click()
                    page.locator('#confirm-text').fill('delete')
                    assert page.locator('#modal-confirm').is_disabled()
                    page.locator('#confirm-text').fill('DELETE')
                    assert page.locator('#modal-confirm').is_enabled()
                    page.locator('#modal-confirm').click()
                    expect(page.locator('#run-status')).to_contain_text('SIMULATED')
                    assert calls == [True]
                model_report = {'status': 'partial', 'account_context': ['Fictional Work account'],
                                'copilot_plan': 'M365 Copilot (Basic)',
                                'models': [{**option, 'selected': index < 2, 'selection_ms': 200}
                                           for index, option in enumerate(MODEL_OPTIONS)]}
                with patch('workflow.web_server.run_model_check', return_value=model_report):
                    page.locator('#check-models').click()
                    expect(page.locator('#model-availability')).to_contain_text('Fictional Work account', timeout=5000)
                    assert page.locator('.model-check-row').count() == 6
                    assert page.locator('.model-check-row .warning').count() == 4
                page.locator('#default-model').select_option(label='Sonnet 5')
                assert page.locator('#model-availability').is_hidden(), 'Edits must hide stale model reports'
                page.locator('#save').click()
                page.wait_for_timeout(250)
                page.set_viewport_size({'width': 900, 'height': 700})
                page.wait_for_timeout(220)
                assert page.locator('body').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(output / 'compact.png'), full_page=True)
                page.emulate_media(reduced_motion='reduce')
                page.locator('.nav-step').nth(1).click()
                page.wait_for_timeout(100)
                animations = page.evaluate('document.getAnimations().length')
                assert animations == 0
                session = page.context.new_cdp_session(page)
                session.send('Performance.enable')
                initial = {x['name']: x['value'] for x in session.send('Performance.getMetrics')['metrics']}
                requests.clear()
                cpu_before = time.process_time()
                page.wait_for_timeout(10000)
                cpu_seconds = time.process_time() - cpu_before
                final = {x['name']: x['value'] for x in session.send('Performance.getMetrics')['metrics']}
                assert not errors, errors
                assert all(url.startswith(server.origin) for url in requests), requests
                report = {'passed': True, 'models': 6, 'default': 'GPT-6 Sol', 'persistence': True,
                          'navigation': 6, 'reduced_motion_animations': animations, 'page_errors': errors,
                          'stale_readiness_blocked': True, 'cleanup_escape_cancelled': True,
                          'typed_cleanup_confirmed_simulated_run': True,
                          'model_check_report_rendered': True,
                          'idle_seconds': 10, 'idle_requests': len(requests),
                          'python_cpu_seconds': cpu_seconds,
                          'renderer_task_seconds': final['TaskDuration'] - initial['TaskDuration'],
                          'js_heap_bytes': final['JSHeapUsedSize'], 'nodes': final['Nodes'],
                          'note': 'Local interface smoke test only; no Copilot sends or six-tab workload.'}
                (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                print(json.dumps(report, indent=2))
                browser.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
