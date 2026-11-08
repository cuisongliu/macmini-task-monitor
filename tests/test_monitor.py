"""只用临时账本和无业务副作用的子进程验证记录边界。"""

import datetime as dt
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_suite = tempfile.TemporaryDirectory(prefix='mini-monitor-test-')
os.environ['TASK_MONITOR_DATA'] = _suite.name

import collector
import config
import install
import ai_scripts
import launchd_config
import taskctl
from fake_launchd import FakeLaunchd
import server
import store
from http.server import ThreadingHTTPServer


class MonitorTests(unittest.TestCase):
    def setUp(self):
        with store.connect() as db:
            db.executescript('DROP TABLE IF EXISTS runs;DROP TABLE IF EXISTS tasks;DROP TABLE IF EXISTS metadata;DROP TABLE IF EXISTS task_configs;DROP TABLE IF EXISTS ai_scripts;')
        store.initialize()
        self.agent_directory = tempfile.TemporaryDirectory(prefix='test-launchagents-')
        self.addCleanup(self.agent_directory.cleanup)
        self.agents = Path(self.agent_directory.name)
        self.launchd = FakeLaunchd()
        for owner in (collector, launchd_config):
            replacement = patch.object(owner, 'AGENTS', self.agents)
            replacement.start()
            self.addCleanup(replacement.stop)
        replacement = patch.object(launchd_config, 'ctl', side_effect=self.launchd)
        replacement.start()
        self.addCleanup(replacement.stop)


    def runner(self, code, task_id='test', **kwargs):
        return subprocess.run([sys.executable, str(ROOT / 'runner.py'), '--task-id', task_id, '--', sys.executable, '-c', code],
                              capture_output=True, text=True, timeout=15, **kwargs)

    def latest(self, task_id='test'):
        return store.list_runs({'task_id': task_id})['items'][0]

    def test_exit_code_and_unicode_and_redaction(self):
        result = self.runner('import sys;print("运行完成 中文");print("Authorization: Bearer fake-test-value-123456789",file=sys.stderr);sys.exit(7)')
        self.assertEqual(result.returncode, 7)
        self.assertIn('fake-test-value', result.stderr)  # 原业务输出保留；仅记录副本脱敏。
        row = store.read_run(self.latest()['id'])
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['exit_code'], 7)
        self.assertGreaterEqual(row['duration'], 0)
        self.assertIn('运行完成 中文', row['log_tail'])
        self.assertNotIn('fake-test-value', row['log_tail'])

    def test_worker_result_is_not_overwritten_by_idle(self):
        result = self.runner('print(\'{"event":"worker_finished","pr":123,"code":0,"status":"processed"}\');print(\'{"event":"worker_idle"}\')')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.latest()['status'], 'success')
        self.assertIn('1 个 PR', self.latest()['summary'])

    def test_business_failure_is_visible_even_when_worker_exits_zero(self):
        self.runner('print(\'{"event":"worker_finished","pr":123,"code":1,"status":"error"}\');print(\'{"event":"worker_idle"}\')')
        self.assertEqual(self.latest()['status'], 'failed')
        self.assertEqual(self.latest()['exit_code'], 0)

    def test_idle_is_skipped(self):
        self.runner('print(\'{"event":"worker_idle"}\')')
        self.assertEqual(self.latest()['status'], 'skipped')

    def test_empty_scan_is_skipped_even_with_later_output(self):
        result = self.runner('print(\'{"event":"scan","scan_id":9,"queued":[]}\');print("x"*30000)', task_id='pr-scan')
        self.assertEqual(result.returncode, 0)
        row = self.latest('pr-scan')
        self.assertEqual(row['status'], 'skipped')
        self.assertIn('未发现待执行任务', row['summary'])

    def test_scan_with_tasks_is_successful(self):
        result = self.runner('print(\'{"event":"scan","scan_id":10,"queued":[123]}\')', task_id='pr-scan')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.latest('pr-scan')['status'], 'success')

    def test_empty_scan_failure_is_not_skipped(self):
        result = self.runner('import sys;print(\'{"event":"scan","scan_id":11,"queued":[]}\');sys.exit(7)', task_id='pr-scan')
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.latest('pr-scan')['status'], 'failed')

    def test_scan_missing_queue_is_not_inferred_empty(self):
        for event in [{'event': 'scan', 'scan_id': 12}, {'event': 'scan', 'scan_id': 13, 'queued': None}]:
            self.runner('print(' + repr(json.dumps(event)) + ')', task_id='pr-scan')
            row = self.latest('pr-scan')
            self.assertEqual(row['status'], 'success')
            self.assertIn('队列未知', row['summary'])

    def test_existing_empty_scans_are_normalized_without_losing_evidence(self):
        backup = config.DATA / 'backups/monitor-before-empty-scan-v1.sqlite3'
        if backup.exists():
            backup.unlink()  # 仅清理本测试进程临时目录里上一测例的备份。
        examples = [
            ('empty', 'execution', 'success', 0, {'event': 'scan', 'queued': []}),
            ('has-tasks', 'execution', 'success', 0, {'event': 'scan', 'queued': [123]}),
            ('failed', 'execution', 'failed', 1, {'event': 'scan', 'queued': []}),
            ('unknown', 'execution', 'success', 0, {'event': 'scan'}),
            ('history', 'history', 'success', None, {'event': 'scan', 'queued': []})
        ]
        for run_id, kind, status, code, event in examples:
            store.insert_run({'id': run_id, 'external_key': run_id, 'task_id': 'pr-scan', 'kind': kind,
                              'status': status, 'exit_code': code, 'created_at': time.time(), 'started_at': 1000,
                              'finished_at': 1010, 'summary': 'original', 'log_tail': json.dumps(event)})
        self.assertEqual(collector.normalize_empty_scans(), 1)
        self.assertEqual(collector.normalize_empty_scans(), 0)
        self.assertEqual(store.list_runs({})['total'], 5)
        row = store.read_run('empty')
        self.assertEqual(row['status'], 'skipped')
        self.assertEqual(row['duration'], 10)
        self.assertEqual(json.loads(row['log_tail'])['queued'], [])
        for run_id, _, status, _, _ in examples[1:]:
            self.assertEqual(store.read_run(run_id)['status'], status)
        import sqlite3
        connection = sqlite3.connect(backup.as_uri() + '?mode=ro', uri=True)
        try:
            self.assertEqual(connection.execute("SELECT status FROM runs WHERE id='empty'").fetchone()[0], 'success')
        finally:
            connection.close()

    def test_late_scan_completion_is_normalized(self):
        store.insert_run({'id': 'late', 'external_key': 'late', 'task_id': 'pr-scan', 'kind': 'execution',
                          'status': 'running', 'created_at': time.time(), 'started_at': time.time()})
        self.assertEqual(collector.normalize_empty_scans(), 0)
        store.update_run('late', status='success', exit_code=0, log_tail='{"event":"scan","queued":[]}')
        self.assertEqual(collector.normalize_empty_scans(), 1)
        self.assertEqual(store.read_run('late')['status'], 'skipped')

    def test_imported_scan_uses_its_own_original_event(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'pr-poll.log').write_text('{"event":"scan","scan_id":55,"queued":[]}\n{"event":"scan","scan_id":56,"queued":[123]}\n')
            store.insert_run({'id': 'legacy-scan', 'external_key': 'scan:55', 'task_id': 'pr-scan', 'kind': 'history',
                              'status': 'success', 'created_at': time.time(), 'summary': '原扫描凭据'})
            store.save_task_config('pr-scan', {'source': 'launchd', 'log_paths': [str(root / 'pr-poll.log')]})
            self.assertEqual(collector.normalize_empty_scans(), 1)
            row = store.read_run('legacy-scan')
            self.assertEqual(row['status'], 'skipped')
            self.assertIn('#55', row['summary'])
            self.assertIsNone(row['exit_code'])
            self.assertIsNone(row['duration'])

    def test_non_skipped_filter_applies_before_count_and_pagination(self):
        statuses = ['success', 'skipped', 'failed', 'running', 'interrupted', 'unknown']
        for index, status in enumerate(statuses):
            store.insert_run({'id': str(index), 'external_key': str(index), 'task_id': 'test', 'kind': 'execution',
                              'status': status, 'created_at': index})
        result = store.list_runs({'status': 'non_skipped', 'limit': 2, 'offset': 2})
        self.assertEqual(result['total'], 5)
        self.assertEqual(len(result['items']), 2)
        self.assertTrue(all(row['status'] != 'skipped' for row in result['items']))
        self.assertEqual(store.list_runs({'status': 'skipped'})['total'], 1)
        self.assertEqual(store.list_runs({})['total'], 6)

    def test_database_failure_does_not_block_business(self):
        with tempfile.TemporaryDirectory() as temp:
            invalid = Path(temp) / 'file'
            invalid.write_text('not a directory')
            env = {**os.environ, 'TASK_MONITOR_DATA': str(invalid)}
            result = self.runner('print("business completed")', env=env)
            self.assertEqual(result.returncode, 0)
            self.assertIn('business completed', result.stdout)
            self.assertIn('原任务继续执行', result.stderr)

    def test_signal_forwarding(self):
        process = subprocess.Popen([sys.executable, str(ROOT / 'runner.py'), '--task-id', 'signal-test', '--', sys.executable, '-c',
                                    'import time;print("ready",flush=True);time.sleep(60)'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'ready')
            process.send_signal(signal.SIGTERM)
            process.communicate(timeout=10)
            self.assertEqual(process.returncode, 143)
            self.assertEqual(self.latest('signal-test')['status'], 'interrupted')
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_launchd_bootstrap_retries_transient_removal(self):
        failed = subprocess.CompletedProcess([], 5, '', 'Bootstrap failed: 5: Input/output error')
        ready = subprocess.CompletedProcess([], 0, '', '')
        with patch.object(install, 'launchctl', side_effect=[failed, ready]) as operation, patch.object(install.time, 'sleep'):
            install.bootstrap(Path('/tmp/fixture.plist'))
        self.assertEqual(operation.call_count, 2)

    def test_history_dedup_and_missing_duration_and_resolution(self):
        data = {'task_id': 'pr-report', 'external_key': 'test-receipt', 'created_at': 1000, 'finished_at': 1000,
                'status': 'unknown', 'summary': '等待确认', 'details': {}}
        collector.import_record(data)
        collector.import_record({**data, 'status': 'success', 'summary': '已发送'})
        result = store.list_runs({})
        self.assertEqual(result['total'], 1)
        self.assertIsNone(result['items'][0]['duration'])
        self.assertEqual(result['items'][0]['status'], 'success')

    def test_receipt_covered_by_execution_is_not_duplicated(self):
        store.insert_run({'id': 'real', 'task_id': 'pr-report', 'external_key': 'real', 'kind': 'execution',
                          'status': 'success', 'created_at': 1000, 'started_at': 1000, 'finished_at': 1020})
        self.assertFalse(collector.needs_receipt('pr-report', 1010))
        self.assertTrue(collector.needs_receipt('pr-report', 1030))

    def test_orphan_finish_time_remains_unknown(self):
        store.insert_run({'id': 'orphan', 'task_id': 'test', 'kind': 'execution', 'external_key': 'orphan',
                          'status': 'running', 'pid': 99999999, 'created_at': time.time()-100, 'started_at': time.time()-100})
        collector.recover_orphans()
        row = store.read_run('orphan')
        self.assertEqual(row['status'], 'interrupted')
        self.assertIsNone(row['finished_at'])
        self.assertIsNone(row['duration'])

    def test_hourly_calendar_crosses_midnight(self):
        now = dt.datetime(2026, 11, 2, 23, 59, tzinfo=config.ZONE).timestamp()
        task = collector.schedule_info({'id':'release-docs'}, {'StartCalendarInterval':{'Minute':0}}, now)
        self.assertEqual(task['next_at'], dt.datetime(2026, 11, 3, 0, 0, tzinfo=config.ZONE).timestamp())
        self.assertEqual(task['previous_at'], dt.datetime(2026, 11, 2, 23, 0, tzinfo=config.ZONE).timestamp())
        self.assertEqual(task['schedule']['text'], '每小时整点')
        self.assertFalse(task['next_estimated'])

    def test_document_outcome_preserves_idle_and_errors(self):
        from outcomes import docs_result
        self.assertEqual(docs_result({'event':'docs_idle'})[0], 'skipped')
        self.assertEqual(docs_result({'event':'docs_retry_limit'})[0], 'failed')
        self.assertIsNone(docs_result({'event':'docs_progress'}))
        result = self.runner('import json;print(json.dumps({"event":"docs_idle"}))', task_id='release-docs')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.latest('release-docs')['status'], 'skipped')

    def test_schedule_uses_shanghai_and_estimates_only_intervals(self):
        now = dt.datetime(2026, 10, 31, 11, 0, tzinfo=config.ZONE).timestamp()
        task = collector.schedule_info({'id': 'test', 'source': 'launchd'}, {'StartCalendarInterval': {'Hour': 1, 'Minute': 0}}, now)
        expected = dt.datetime(2026, 11, 1, 1, 0, tzinfo=config.ZONE).timestamp()
        self.assertEqual(task['next_at'], expected)
        self.assertFalse(task['next_estimated'])
        task = collector.schedule_info({'id': 'test', 'source': 'launchd', 'last_run': {'started_at': now-60}}, {'StartInterval': 300}, now)
        self.assertEqual(task['next_at'], now+240)
        self.assertTrue(task['next_estimated'])

    def test_weekly_schedule_and_automation_changes(self):
        rules = collector.automation_calendar('RRULE:FREQ=WEEKLY;BYHOUR=9;BYMINUTE=30;BYDAY=MO')
        now = dt.datetime(2026, 10, 31, 11, 0, tzinfo=config.ZONE).timestamp()
        task = collector.schedule_info({'id': 'test', 'source': 'codex-script'}, {'StartCalendarInterval': rules}, now)
        self.assertEqual(task['schedule']['text'], '每周一 09:30')
        self.assertEqual(task['next_at'], dt.datetime(2026, 11, 2, 9, 30, tzinfo=config.ZONE).timestamp())
        self.assertEqual(task['previous_at'], dt.datetime(2026, 10, 26, 9, 30, tzinfo=config.ZONE).timestamp())
        self.assertIsNone(collector.automation_calendar('RRULE:FREQ=MONTHLY;BYHOUR=10'))
        self.assertEqual(collector.automation_calendar('RRULE:FREQ=WEEKLY;BYHOUR=11;BYMINUTE=5;BYDAY=SU,MO,TU,WE,TH,FR,SA'), [{'Hour': 11, 'Minute': 5}])

    def test_log_storage_is_bounded(self):
        self.runner('print("x"*120000)')
        self.assertLessEqual(len(store.read_run(self.latest()['id'])['log_tail']), 24000)

    def test_http_read_only_host_and_pagination_validation(self):
        http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        http.allowed_hosts = {'127.0.0.1'}
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(http.server_port)
        try:
            with urlopen(base + '/api/runs?limit=10') as response:
                self.assertEqual(json.load(response)['total'], 0)
            with urlopen(base + '/api/runs?status=non_skipped') as response:
                self.assertEqual(json.load(response)['total'], 0)
            for path, status in [('/api/runs?limit=-1', 400), ('/api/runs?offset=invalid', 400), ('/../../etc/passwd', 404)]:
                with self.assertRaises(HTTPError) as context:
                    urlopen(base + path)
                self.assertEqual(context.exception.code, status)
                context.exception.close()
            with self.assertRaises(HTTPError) as context:
                urlopen(Request(base + '/api/overview', headers={'Host': 'untrusted.example'}))
            self.assertEqual(context.exception.code, 403)
            context.exception.close()
            with self.assertRaises(HTTPError) as context:
                urlopen(Request(base + '/api/overview', method='POST', data=b''))
            self.assertEqual(context.exception.code, 405)
            context.exception.close()
        finally:
            http.shutdown()
            http.server_close()
            thread.join()

    def test_page_configuration_is_stored_and_external_task_is_discovered(self):
        store.save_task_config('manual-test', {'source': 'external', 'name': '页面任务', 'description': '外部调度',
                                               'script': '/tmp/example.sh', 'schedule': '每天 09:00',
                                               'enabled': True, 'log_paths': []})
        with patch.object(collector, 'gui_states', return_value={}):
            with patch.object(collector, 'read_definitions', return_value=([], [])):
                collector.collect()
        with store.connect() as db:
            row = db.execute('SELECT snapshot FROM tasks WHERE id=?', ('manual-test',)).fetchone()
        self.assertIsNotNone(row)
        snapshot = json.loads(row['snapshot'])
        self.assertEqual(snapshot['source'], 'external')
        self.assertEqual(snapshot['schedule']['text'], '每天 09:00')

    def test_launchd_discovery_uses_plists_without_label_allowlist(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            fixtures = {
                'com.example.timer': {'Label': 'com.example.timer', 'ProgramArguments': ['/usr/bin/python3', '/tmp/job.py'],
                                      'StartInterval': 300, 'StandardOutPath': str(directory / 'job.log')},
                'com.example.service': {'Label': 'com.example.service', 'ProgramArguments': ['/usr/bin/example'], 'KeepAlive': True},
                'com.example.once': {'Label': 'com.example.once', 'ProgramArguments': ['/usr/bin/example'], 'RunAtLoad': True},
                'com.example.monitor': {'Label': 'com.example.monitor', 'ProgramArguments': [sys.executable, str(ROOT / 'server.py')],
                                        'StartInterval': 60, 'KeepAlive': True},
            }
            for label, fixture in fixtures.items():
                (directory / (label + '.plist')).write_bytes(__import__('plistlib').dumps(fixture))
            tasks, services = collector.read_definitions(directory)
        self.assertEqual([task['id'] for task in tasks], ['com.example.timer'])
        self.assertEqual(tasks[0]['script'], '/tmp/job.py')
        self.assertEqual([service['id'] for service in services], ['com.example.service'])

    def test_launchd_configuration_http_api_manages_tasks_with_origin_and_revision_checks(self):
        path = self.write_agent('com.example.discovered', {'ProgramArguments': ['/usr/bin/printf', 'unchanged'],
                                                           'StartInterval': 600})
        http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        http.allowed_hosts = {'127.0.0.1'}
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(http.server_port)
        headers = {'Host': '127.0.0.1', 'Origin': base, 'Content-Type': 'application/json'}
        try:
            with urlopen(base + '/api/configuration') as response:
                self.assertEqual(json.load(response)['items'][0]['id'], 'com.example.discovered')

            payload = {'source': 'launchd', 'name': '页面创建任务', 'description': '手动输入命令', 'enabled': True,
                       'execution': {'program': '', 'arguments': ['/usr/bin/printf', 'hello world'],
                                     'working_directory': '', 'environment': [], 'stdout_path': '', 'stderr_path': '',
                                     'run_at_load': False, 'keep_alive': False,
                                     'schedule': {'type': 'interval', 'seconds': 3600}}}
            request = Request(base + '/api/configuration', method='POST', data=json.dumps(payload).encode(), headers=headers)
            with urlopen(request) as response:
                created = json.load(response)
            task_id = created['id']
            self.assertTrue(task_id.startswith('local.mini-monitor.'))
            self.assertEqual(launchd_config.locate(task_id)[1]['ProgramArguments'], ['/usr/bin/printf', 'hello world'])
            self.assertTrue(store.get_task_configs()[task_id]['managed'])
            with urlopen(base + '/api/configuration') as response:
                created_view = next(item for item in json.load(response)['items'] if item['id'] == task_id)

            payload.update({'name': '页面修改任务', 'revision': created_view['revision'],
                            'execution': {**payload['execution'], 'arguments': ['/usr/bin/printf', 'changed']}})
            request = Request(base + '/api/configuration/' + task_id, method='PUT', data=json.dumps(payload).encode(), headers=headers)
            with urlopen(request) as response:
                updated = json.load(response)
            self.assertEqual(store.get_task_configs()[task_id]['name'], '页面修改任务')
            with urlopen(base + '/api/configuration') as response:
                updated_view = next(item for item in json.load(response)['items'] if item['id'] == task_id)
            with self.assertRaises(HTTPError) as context:
                urlopen(Request(base + '/api/configuration/' + task_id, method='PUT', data=json.dumps(payload).encode(), headers=headers))
            self.assertEqual(context.exception.code, 409)
            context.exception.close()

            discovered = next(item for item in launchd_config.list_configurations()['items'] if item['id'] == 'com.example.discovered')
            with self.assertRaises(HTTPError) as context:
                urlopen(Request(base + '/api/configuration/com.example.discovered?revision=' + discovered['revision'], method='DELETE', headers=headers))
            self.assertEqual(context.exception.code, 400)
            context.exception.close()

            request = Request(base + '/api/configuration/' + task_id + '?revision=' + updated_view['revision'], method='DELETE', headers=headers)
            with urlopen(request) as response:
                self.assertTrue(json.load(response)['ok'])
            self.assertFalse(path.with_name(task_id + '.plist').exists())
            self.assertNotIn(task_id, store.get_task_configs())

            with self.assertRaises(HTTPError) as context:
                urlopen(Request(base + '/api/configuration', method='POST', data=json.dumps(payload).encode(),
                                headers={'Host': '127.0.0.1', 'Content-Type': 'application/json'}))
            self.assertEqual(context.exception.code, 403)
            context.exception.close()
        finally:
            http.shutdown()
            http.server_close()
            thread.join()

    def test_cli_configuration_can_manage_discovered_launchd_services(self):
        self.write_agent('com.example.service', {'ProgramArguments': ['/usr/bin/printf', 'service'], 'KeepAlive': True})
        item = launchd_config.list_configurations()['items'][0]
        item['name'] = '整理后的服务名'
        item['enabled'] = False
        result = taskctl.apply_document(item)
        self.assertTrue(result['applied'])
        self.assertNotIn(item['id'], self.launchd.loaded)
        self.assertTrue(self.launchd.disabled[item['id']])
        definition = __import__('plistlib').loads((self.agents / (item['id'] + '.plist')).read_bytes())
        self.assertTrue(definition['Disabled'])
        self.assertEqual(store.get_task_configs()[item['id']]['name'], '整理后的服务名')

    def test_saved_settings_apply_to_discovered_tasks_and_services_only(self):
        with tempfile.TemporaryDirectory() as folder:
            plist = Path(folder) / 'com.example.timer.plist'
            plist.write_bytes(__import__('plistlib').dumps({'Label': 'com.example.timer',
                                                             'ProgramArguments': ['/usr/bin/python3', '/tmp/task.py'],
                                                             'StartInterval': 600}))
            task = {'id': 'com.example.timer', 'label': 'com.example.timer', 'name': '原名称',
                    'description': '自动发现', 'source': 'launchd', 'category': 'work', 'icon': 'clock',
                    'definition_path': str(plist), 'script': '/tmp/task.py', 'log_paths': []}
            service = {'id': 'com.example.service', 'label': 'com.example.service', 'name': '原服务名',
                       'description': '常驻服务', 'source': 'service', 'log_paths': [], 'script': ''}
            store.save_task_config('com.example.timer', {'source': 'launchd', 'name': '页面任务名',
                                                         'description': '页面说明', 'schedule': '错误备注',
                                                         'enabled': True, 'log_paths': []})
            store.save_task_config('com.example.service', {'source': 'service', 'name': '页面服务名',
                                                           'description': '服务说明', 'enabled': True,
                                                           'log_paths': []})
            states = {'com.example.timer': {'loaded': True, 'pid': None, 'last_exit_code': 0},
                      'com.example.service': {'loaded': True, 'pid': None, 'last_exit_code': 0}}
            with patch.object(collector, 'read_definitions', return_value=([task], [service])), \
                    patch.object(collector, 'gui_states', return_value=states):
                collector.collect()
                with store.connect() as db:
                    snapshot = json.loads(db.execute('SELECT snapshot FROM tasks WHERE id=?', (task['id'],)).fetchone()['snapshot'])
                metadata = store.get_meta('collector')
                self.assertEqual(snapshot['name'], '页面任务名')
                self.assertEqual(snapshot['schedule']['text'], '每 10 分钟')
                self.assertEqual(metadata['services'][0]['name'], '页面服务名')

                store.save_task_config('com.example.timer', {'source': 'launchd', 'name': '页面任务名', 'enabled': False})
                store.save_task_config('com.example.service', {'source': 'service', 'name': '页面服务名', 'enabled': False})
                states['com.example.timer']['loaded'] = False
                states['com.example.service']['loaded'] = False
                collector.collect()
                with store.connect() as db:
                    disabled = json.loads(db.execute('SELECT snapshot FROM tasks WHERE id=?', (task['id'],)).fetchone()['snapshot'])
                self.assertEqual(disabled['state'], 'disabled')
                self.assertEqual(store.get_meta('collector')['services'][0]['state'], 'disabled')

    def write_agent(self, label='com.example.timer', definition=None, loaded=True):
        data = {'Label': label, **(definition or {'ProgramArguments': ['/usr/bin/printf', 'test'], 'StartInterval': 3600})}
        path = self.agents / (label + '.plist')
        path.write_bytes(__import__('plistlib').dumps(data))
        if loaded:
            self.launchd.loaded[label] = None
        return path

    def test_real_configuration_roundtrip_preserves_arguments_environment_and_unknown_keys(self):
        definition = {'ProgramArguments': ['/usr/bin/python3', str(ROOT / 'runner.py'), '--task-id', 'existing', '--',
                                          '/usr/bin/printf', 'a b', '', 'line1\nline2', '--token', 'fake-sensitive-value'],
                      'StartInterval': 3600, 'EnvironmentVariables': {'PATH': '/usr/bin:/bin', 'API_KEY': 'private-test-value'},
                      'WorkingDirectory': '/tmp', 'Nice': 7, 'ThrottleInterval': 60}
        path = self.write_agent(definition=definition)
        original = path.read_bytes()
        item = launchd_config.list_configurations()['items'][0]
        self.assertNotIn('private-test-value', json.dumps(item))
        self.assertNotIn('fake-sensitive-value', json.dumps(item))
        item['execution']['schedule'] = {'type': 'weekly', 'time': '09:30', 'weekdays': [1, 3, 5]}
        result = launchd_config.save(item['id'], item, item['source'])
        actual = __import__('plistlib').loads(path.read_bytes())
        self.assertEqual(actual['ProgramArguments'], definition['ProgramArguments'])
        self.assertEqual(actual['EnvironmentVariables'], definition['EnvironmentVariables'])
        self.assertEqual(actual['Nice'], 7)
        self.assertEqual(actual['ThrottleInterval'], 60)
        self.assertNotIn('StartInterval', actual)
        self.assertEqual(actual['StartCalendarInterval'], [{'Hour': 9, 'Minute': 30, 'Weekday': day} for day in [1, 3, 5]])
        self.assertEqual(Path(result['backup_path']).read_bytes(), original)
        self.assertEqual(store.get_task_configs()[item['id']]['definition'], actual)
        self.assertEqual([call[0] for call in self.launchd.calls if call[0] not in ('list', 'print-disabled')], ['bootout', 'enable', 'bootstrap'])

    def test_noop_save_does_not_restart_running_service(self):
        self.write_agent('com.example.service', {'ProgramArguments': ['/usr/bin/printf', 'test'], 'KeepAlive': {'SuccessfulExit': False},
                                                'EnvironmentVariables': {'PATH': '/usr/bin'}})
        self.launchd.loaded['com.example.service'] = 123
        item = launchd_config.list_configurations()['items'][0]
        self.launchd.calls.clear()
        item['name'] = '仅改名称'
        self.assertFalse(launchd_config.save(item['id'], item, item['source'])['reloaded'])
        self.assertTrue(all(call[0] in ('list', 'print-disabled') for call in self.launchd.calls))

    def test_enabled_but_unloaded_job_stays_enabled_without_being_started_on_metadata_edit(self):
        path = self.write_agent(loaded=False)
        item = launchd_config.list_configurations()['items'][0]
        self.assertTrue(item['enabled'])
        self.assertFalse(item['loaded'])
        self.launchd.calls.clear()
        item['name'] = '只改显示名称'
        result = launchd_config.save(item['id'], item, item['source'])
        self.assertFalse(result['reloaded'])
        self.assertFalse(self.launchd.loaded)
        self.assertTrue(all(call[0] in ('list', 'print-disabled') for call in self.launchd.calls))
        self.assertEqual(__import__('plistlib').loads(path.read_bytes())['StartInterval'], 3600)

    def test_existing_relative_program_arguments_survive_unrelated_schedule_edit(self):
        path = self.write_agent(definition={'ProgramArguments': ['python3', 'worker.py', '--mode', 'daily'],
                                            'WorkingDirectory': '/tmp', 'StartInterval': 3600})
        item = launchd_config.list_configurations()['items'][0]
        item['execution']['schedule'] = {'type': 'daily', 'time': '08:15'}
        launchd_config.save(item['id'], item, item['source'])
        actual = __import__('plistlib').loads(path.read_bytes())
        self.assertEqual(actual['ProgramArguments'], ['python3', 'worker.py', '--mode', 'daily'])
        self.assertEqual(actual['StartCalendarInterval'], {'Hour': 8, 'Minute': 15})

    def test_configuration_busy_and_conflict_reject_before_mutation(self):
        path = self.write_agent()
        item = launchd_config.list_configurations()['items'][0]
        original = path.read_bytes()
        self.launchd.loaded[item['id']] = 123
        item['execution']['schedule']['seconds'] = 1800
        with self.assertRaises(launchd_config.ConfigurationError) as context:
            launchd_config.save(item['id'], item, item['source'])
        self.assertEqual(context.exception.status, 409)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.launchd.loaded[item['id']], 123)
        item['revision'] = 'stale'
        with self.assertRaises(launchd_config.ConfigurationError) as context:
            launchd_config.save(item['id'], item, item['source'])
        self.assertEqual(context.exception.status, 409)
        self.assertTrue(all(call[0] in ('list', 'print-disabled') for call in self.launchd.calls))

    def test_explicit_restart_allows_applying_busy_service(self):
        self.write_agent('com.example.service', {'ProgramArguments': ['/usr/bin/printf', 'service'], 'KeepAlive': True})
        self.launchd.loaded['com.example.service'] = 123
        item = launchd_config.list_configurations()['items'][0]
        item['restart_running'] = True
        item['execution']['arguments'][1] = 'changed'
        self.assertTrue(launchd_config.save(item['id'], item, item['source'])['applied'])
        self.assertIn('com.example.service', self.launchd.loaded)

    def test_bootstrap_failure_rolls_back_plist_and_scheduler_without_saving_success(self):
        path = self.write_agent()
        original = path.read_bytes()
        item = launchd_config.list_configurations()['items'][0]
        item['execution']['schedule'] = {'type': 'daily', 'time': '10:00'}
        self.launchd.failures['bootstrap'] = [5, 0]
        with self.assertRaises(launchd_config.ConfigurationError):
            launchd_config.save(item['id'], item, item['source'])
        self.assertEqual(path.read_bytes(), original)
        self.assertIn(item['id'], self.launchd.loaded)
        self.assertNotIn(item['id'], store.get_task_configs())

    def test_database_failure_rolls_back_applied_configuration(self):
        path = self.write_agent()
        original = path.read_bytes()
        item = launchd_config.list_configurations()['items'][0]
        item['execution']['schedule']['seconds'] = 900
        with patch.object(store, 'save_task_config', side_effect=OSError('simulated disk full')):
            with self.assertRaises(launchd_config.ConfigurationError):
                launchd_config.save(item['id'], item, item['source'])
        self.assertEqual(path.read_bytes(), original)
        self.assertIn(item['id'], self.launchd.loaded)

    def test_new_launchd_task_can_be_enabled_disabled_and_removed_with_history_retained(self):
        body = {'name': '新任务', 'description': '', 'enabled': True, 'creating': True,
                'execution': {'program': '', 'arguments': ['/usr/bin/printf', 'test'], 'working_directory': '/tmp',
                              'environment': [], 'stdout_path': '', 'stderr_path': '', 'run_at_load': False,
                              'keep_alive': False, 'schedule': {'type': 'interval', 'seconds': 1200}}}
        task_id = 'local.mini-monitor.test'
        launchd_config.save(task_id, body, 'launchd')
        path = self.agents / (task_id + '.plist')
        self.assertTrue(path.exists())
        self.assertIn(task_id, self.launchd.loaded)
        item = launchd_config.list_configurations()['items'][0]
        self.assertTrue(item['managed'])
        self.assertEqual(item['execution']['schedule']['seconds'], 1200)
        item['enabled'] = False
        launchd_config.save(task_id, item, 'launchd')
        self.assertNotIn(task_id, self.launchd.loaded)
        self.assertTrue(self.launchd.disabled[task_id])
        item = launchd_config.list_configurations()['items'][0]
        self.assertFalse(item['enabled'])
        store.insert_run({'id': 'preserved', 'task_id': task_id, 'external_key': 'preserved', 'kind': 'history',
                          'status': 'success', 'created_at': time.time()})
        launchd_config.remove(task_id, item['revision'])
        self.assertFalse(path.exists())
        self.assertNotIn(task_id, store.get_task_configs())
        self.assertEqual(store.list_runs({'task_id': task_id})['total'], 1)

    def test_ai_script_test_previews_without_overwriting_then_saves_script(self):
        output = Path(self.agent_directory.name) / 'generated.py'
        output.write_text('existing script')
        config = ai_scripts.validate('daily-summary', {'name': '日报脚本', 'provider': 'codex',
            'model': 'gpt-6.1-sol', 'script_type': 'python', 'prompt': '生成脚本内容',
            'output_path': str(output), 'max_output_bytes': 1000, 'timeout_seconds': 30})
        store.save_ai_script('daily-summary', config)

        real_run = subprocess.run
        real_popen = subprocess.Popen
        execution_directories = []
        def fake_codex(command, **kwargs):
            if '--output-last-message' in command:
                Path(command[command.index('--output-last-message') + 1]).write_text('print("generated")\n')
                return subprocess.CompletedProcess(command, 0, None, '')
            return real_run(command, **kwargs)

        def tracking_popen(command, **kwargs):
            execution_directories.append(Path(kwargs['cwd']))
            return real_popen(command, **kwargs)

        with patch.object(ai_scripts.subprocess, 'run', side_effect=fake_codex) as invoke, \
             patch.object(ai_scripts.subprocess, 'Popen', side_effect=tracking_popen):
            result = ai_scripts.test('daily-summary')
        self.assertTrue(result['ok'])
        self.assertIn('print("generated")', result['output'])
        self.assertEqual(result['execution_exit_code'], 0)
        self.assertIn('generated', result['execution_output'])
        self.assertEqual(len(execution_directories), 1)
        self.assertFalse(execution_directories[0].exists())
        self.assertTrue(result['test_id'])
        self.assertEqual(output.read_text(), 'existing script')
        self.assertIn('--model', invoke.call_args.args[0])
        self.assertIn('--skip-git-repo-check', invoke.call_args.args[0])
        self.assertIs(invoke.call_args.kwargs['stdin'], subprocess.DEVNULL)
        ai_scripts.write_tested_script('daily-summary', result['test_id'])
        self.assertEqual(output.read_text(), 'print("generated")\n')
        with self.assertRaises(ai_scripts.ScriptError):
            ai_scripts.write_tested_script('daily-summary', result['test_id'])

    def test_ai_script_manual_test_rejects_invalid_source_without_saving(self):
        output = Path(self.agent_directory.name) / 'invalid.py'
        config = ai_scripts.validate('invalid-source', {'name': '无效脚本', 'provider': 'codex',
            'model': 'gpt-6.1-sol', 'script_type': 'python', 'prompt': '生成错误脚本',
            'output_path': str(output), 'max_output_bytes': 1000, 'timeout_seconds': 30})
        store.save_ai_script('invalid-source', config)

        def fake_codex(command, **kwargs):
            Path(command[command.index('--output-last-message') + 1]).write_text('def broken(:\n')
            return subprocess.CompletedProcess(command, 0, None, '')

        with patch.object(ai_scripts.subprocess, 'run', side_effect=fake_codex):
            result = ai_scripts.test('invalid-source')
        self.assertFalse(result['ok'])
        self.assertIsNone(result['test_id'])
        self.assertIn('有效 Python', result['validation_error'])
        self.assertFalse(output.exists())

    def test_ai_script_execution_failure_is_reported_and_temporary_directory_removed(self):
        output = Path(self.agent_directory.name) / 'failure.py'
        config = ai_scripts.validate('execution-failure', {'name': '执行失败脚本', 'provider': 'codex',
            'model': 'gpt-6.1-sol', 'script_type': 'python', 'prompt': '执行失败测试',
            'output_path': str(output), 'max_output_bytes': 1000, 'timeout_seconds': 30})
        store.save_ai_script('execution-failure', config)
        real_run = subprocess.run
        real_popen = subprocess.Popen
        execution_directories = []

        def fake_codex(command, **kwargs):
            if '--output-last-message' in command:
                Path(command[command.index('--output-last-message') + 1]).write_text('import sys\nprint("failed run")\nsys.exit(7)\n')
                return subprocess.CompletedProcess(command, 0, None, '')
            return real_run(command, **kwargs)

        def tracking_popen(command, **kwargs):
            execution_directories.append(Path(kwargs['cwd']))
            return real_popen(command, **kwargs)

        with patch.object(ai_scripts.subprocess, 'run', side_effect=fake_codex), \
             patch.object(ai_scripts.subprocess, 'Popen', side_effect=tracking_popen):
            result = ai_scripts.test('execution-failure')
        self.assertFalse(result['ok'])
        self.assertEqual(result['generation_exit_code'], 0)
        self.assertEqual(result['execution_exit_code'], 7)
        self.assertIn('failed run', result['execution_output'])
        self.assertIsNone(result['test_id'])
        self.assertEqual(len(execution_directories), 1)
        self.assertFalse(execution_directories[0].exists())

    def test_ai_script_execution_timeout_cleans_temporary_directory(self):
        output = Path(self.agent_directory.name) / 'timeout.py'
        config = ai_scripts.validate('execution-timeout', {'name': '执行超时脚本', 'provider': 'codex',
            'model': 'gpt-6.1-sol', 'script_type': 'python', 'prompt': '执行超时测试',
            'output_path': str(output), 'max_output_bytes': 1000, 'timeout_seconds': 1})
        store.save_ai_script('execution-timeout', config)
        real_run = subprocess.run
        real_popen = subprocess.Popen
        execution_directories = []

        def fake_codex(command, **kwargs):
            if '--output-last-message' in command:
                Path(command[command.index('--output-last-message') + 1]).write_text('import time\ntime.sleep(30)\n')
                return subprocess.CompletedProcess(command, 0, None, '')
            return real_run(command, **kwargs)

        def tracking_popen(command, **kwargs):
            execution_directories.append(Path(kwargs['cwd']))
            return real_popen(command, **kwargs)

        with patch.object(ai_scripts.subprocess, 'run', side_effect=fake_codex), \
             patch.object(ai_scripts.subprocess, 'Popen', side_effect=tracking_popen):
            result = ai_scripts.test('execution-timeout')
        self.assertFalse(result['ok'])
        self.assertTrue(result['execution_timed_out'])
        self.assertEqual(result['execution_exit_code'], 124)
        self.assertIsNone(result['test_id'])
        self.assertEqual(len(execution_directories), 1)
        self.assertFalse(execution_directories[0].exists())

    def test_cli_can_select_and_clear_saved_ai_script_as_task_command(self):
        output = Path(self.agent_directory.name) / 'generated.py'
        output.write_text('print("generated")\n')
        store.save_ai_script('daily-summary', {'name': '日报脚本', 'provider': 'codex', 'model': 'gpt-6.1-sol',
            'script_type': 'python', 'prompt': 'prompt', 'output_path': str(output), 'output_mode': 'replace',
            'max_output_bytes': 1000, 'timeout_seconds': 30})
        body = {'name': '每日摘要', 'description': '', 'enabled': True, 'creating': True,
                'execution': {'program': '', 'arguments': ['/usr/bin/printf'], 'ai_script_id': 'daily-summary',
                    'working_directory': '', 'environment': [], 'stdout_path': '', 'stderr_path': '',
                    'run_at_load': False, 'keep_alive': False, 'schedule': {'type': 'interval', 'seconds': 3600}}}
        task_id = 'local.mini-monitor.selected-script'
        result = taskctl.apply_document(body, 'launchd')
        task_id = result['id']
        definition = __import__('plistlib').loads((self.agents / (task_id + '.plist')).read_bytes())
        self.assertEqual(definition['ProgramArguments'], [sys.executable, str(output)])
        self.assertEqual(store.get_task_configs()[task_id]['ai_script_id'], 'daily-summary')
        taskctl.clear_ai_script(task_id)
        restored = __import__('plistlib').loads((self.agents / (task_id + '.plist')).read_bytes())
        self.assertEqual(restored['ProgramArguments'], ['/usr/bin/printf'])
        self.assertIsNone(store.get_task_configs()[task_id].get('ai_script_id'))

        secret_task = 'com.example.secret-command'
        secret_value = 'very-secret-test-value'
        secret_path = self.write_agent(secret_task, {'ProgramArguments': ['/usr/bin/printf', '--api-key', secret_value],
                                                     'StartInterval': 300})
        view = next(item for item in launchd_config.list_configurations()['items'] if item['id'] == secret_task)
        self.assertNotIn(secret_value, json.dumps(view))
        taskctl.select_ai_script(secret_task, 'daily-summary')
        taskctl.clear_ai_script(secret_task)
        restored_secret_command = __import__('plistlib').loads(secret_path.read_bytes())
        self.assertEqual(restored_secret_command['ProgramArguments'], ['/usr/bin/printf', '--api-key', secret_value])

    def test_invalid_real_schedule_does_not_write_or_call_mutating_launchctl(self):
        path = self.write_agent()
        item = launchd_config.list_configurations()['items'][0]
        original = path.read_bytes()
        for schedule in [{'type': 'interval', 'seconds': 0}, {'type': 'daily', 'time': '25:00'},
                         {'type': 'weekly', 'time': '09:00', 'weekdays': []},
                         {'type': 'calendar', 'rules': {'Month': 13}}, {'type': 'unknown'}]:
            item['execution']['schedule'] = schedule
            with self.assertRaises(launchd_config.ConfigurationError):
                launchd_config.save(item['id'], item, 'launchd')
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(all(call[0] in ('list', 'print-disabled') for call in self.launchd.calls))

    def test_combined_schedule_and_custom_calendar_roundtrip(self):
        definition = {'ProgramArguments': ['/usr/bin/printf', 'test'], 'StartInterval': 1200,
                      'StartCalendarInterval': [{'Month': 2, 'Day': 1, 'Hour': 9}, {'Minute': 30}]}
        self.write_agent(definition=definition)
        item = launchd_config.list_configurations()['items'][0]
        self.assertEqual(item['execution']['schedule']['type'], 'combined')
        rebuilt = launchd_config.build_definition(item, {'Label': item['id'], **definition}, item['id'], 'launchd')
        self.assertEqual(rebuilt['StartCalendarInterval'], definition['StartCalendarInterval'])
        self.assertEqual(rebuilt['StartInterval'], 1200)


if __name__ == '__main__':
    unittest.main()
