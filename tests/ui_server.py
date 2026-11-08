"""浏览器集成测试的临时服务：真实 HTTP/SQLite/plist，模拟全部 launchctl。"""
import json
import os
import plistlib
import signal
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
fixture = tempfile.TemporaryDirectory(prefix='mini-ui-')
os.environ['TASK_MONITOR_DATA'] = str(Path(fixture.name) / 'data')

import collector
import ai_scripts
import launchd_config
import server
import store
import taskctl
from fake_launchd import FakeLaunchd

agents = Path(fixture.name) / 'LaunchAgents'
agents.mkdir()
ai_api_enabled = True
ai_api_requests = 0
launchd = FakeLaunchd()
examples = [
    {'Label': 'com.example.timer', 'ProgramArguments': ['/usr/bin/printf', '任务参数 with spaces'],
     'StartInterval': 3600, 'WorkingDirectory': '/tmp', 'Nice': 5,
     'EnvironmentVariables': {'PATH': '/usr/bin:/bin', 'API_TOKEN': 'fixture-private-value'}},
    {'Label': 'com.example.service', 'ProgramArguments': ['/usr/bin/printf', 'service'],
     'KeepAlive': True, 'RunAtLoad': True}
]
for definition in examples:
    (agents / (definition['Label'] + '.plist')).write_bytes(plistlib.dumps(definition))
    launchd.loaded[definition['Label']] = None
collector.AGENTS = launchd_config.AGENTS = agents
launchd_config.ctl = launchd

real_ai_test = ai_scripts.test
real_subprocess_run = ai_scripts.subprocess.run

def fake_ai_test(script_id):
    def run(command, **kwargs):
        if '--output-last-message' in command:
            Path(command[command.index('--output-last-message') + 1]).write_text("print('generated from prompt')\n")
            return __import__('subprocess').CompletedProcess(command, 0, '', '')
        return real_subprocess_run(command, **kwargs)
    with patch.object(ai_scripts.subprocess, 'run', side_effect=run):
        return real_ai_test(script_id)

ai_scripts.test = fake_ai_test
collector.gui_states = lambda: {label: {'loaded': True, 'pid': pid, 'last_exit_code': 0} for label, pid in launchd.loaded.items()}

class FixtureHandler(server.Handler):
    def do_GET(self):
        global ai_api_enabled, ai_api_requests
        if self.path == '/_test/state':
            self.respond(200, {'definitions': [plistlib.loads(path.read_bytes()) for path in agents.glob('*.plist')],
                               'calls': launchd.calls, 'loaded': launchd.loaded,
                               'configurations': store.get_task_configs(), 'ai_scripts': store.get_ai_scripts(),
                               'ai_api_requests': ai_api_requests,
                               'python_path': sys.executable,
                               'ai_output_path': str(Path(fixture.name) / 'generated.py'),
                               'generated_script': (Path(fixture.name) / 'generated.py').read_text() if (Path(fixture.name) / 'generated.py').exists() else None})
        elif self.path == '/_test/disable-ai-api':
            ai_api_enabled = False
            self.respond(200, {'ok': True})
        elif self.path == '/_test/enable-ai-api':
            ai_api_enabled = True
            self.respond(200, {'ok': True})
        elif self.path.startswith('/_test/use-script/'):
            taskctl.select_ai_script('com.example.timer', self.path.rsplit('/', 1)[-1])
            self.respond(200, {'ok': True})
        elif self.path == '/_test/clear-script':
            taskctl.clear_ai_script('com.example.timer')
            self.respond(200, {'ok': True})
        else:
            if self.path == '/api/ai-scripts':
                ai_api_requests += 1
                if not ai_api_enabled:
                    self.respond(404, {'error': '页面不存在'})
                    return
            if self.path.startswith('/api/overview'):
                collector.collect()
            super().do_GET()

    def do_POST(self):
        if self.path == '/_test/failure':
            data = server.read_json_body(self)
            launchd.failures['bootstrap'] = [data.get('code', 5), 0]
            self.respond(200, {'ok': True})
        else:
            super().do_POST()

store.initialize()
collector.collect()
http = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
http.allowed_hosts = {'127.0.0.1'}
signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=http.shutdown, daemon=True).start())
print(json.dumps({'base': 'http://127.0.0.1:' + str(http.server_port)}), flush=True)
try:
    http.serve_forever(poll_interval=0.1)
finally:
    http.server_close()
    fixture.cleanup()
