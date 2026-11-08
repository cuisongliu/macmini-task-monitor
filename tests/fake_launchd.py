"""只用于测试：模拟 launchctl 状态机，不创建或执行业务子进程。"""
import plistlib
import subprocess
from pathlib import Path


class FakeLaunchd:
    def __init__(self):
        self.loaded = {}
        self.disabled = {}
        self.calls = []
        self.failures = {}

    def __call__(self, *args):
        self.calls.append(args)
        operation = args[0]
        failures = self.failures.get(operation, [])
        if failures:
            code = failures.pop(0)
            if code:
                return subprocess.CompletedProcess(args, code, '', 'simulated failure')
        if operation == 'print-disabled':
            values = '\n'.join('"' + key + '" => ' + str(value).lower() for key, value in self.disabled.items())
            return subprocess.CompletedProcess(args, 0, values, '')
        if operation == 'list':
            if args[1] not in self.loaded:
                return subprocess.CompletedProcess(args, 113, '', '')
            pid = self.loaded[args[1]]
            return subprocess.CompletedProcess(args, 0, ('"PID" = ' + str(pid) + ';') if pid else '{}', '')
        if operation == 'bootstrap':
            definition = plistlib.loads(Path(args[2]).read_bytes())
            label = definition['Label']
            if self.disabled.get(label) or label in self.loaded:
                return subprocess.CompletedProcess(args, 5, '', '')
            self.loaded[label] = None
        elif operation == 'bootout':
            label = args[1].split('/', 2)[2]
            if label not in self.loaded:
                return subprocess.CompletedProcess(args, 113, '', '')
            del self.loaded[label]
        elif operation in ('disable', 'enable'):
            self.disabled[args[1].split('/', 2)[2]] = operation == 'disable'
        else:
            raise AssertionError('Unexpected launchctl operation: ' + operation)
        return subprocess.CompletedProcess(args, 0, '', '')
