"""Reusable AI script definitions and explicit manual tests."""

import copy
import ast
import hashlib
import json
import os
import re
import secrets
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import store
from config import redact

SCRIPT_ID = re.compile(r'^[a-z0-9][a-z0-9._-]{1,79}$')


def codex_command(config, output_path=None):
    """Codex-specific CLI adapter; other providers can supply their own adapter."""
    args = [PROVIDERS['codex']['binary'], 'exec', '--ephemeral', '--sandbox', 'read-only',
            '--skip-git-repo-check', '--model', config['model']]
    if output_path:
        args.extend(['--output-last-message', output_path])
    instruction = (f"生成一个完整可直接执行的 {config.get('script_type', 'python')} 脚本。只输出源代码，不要 Markdown 代码围栏或解释文字。\n\n"
                   + config['prompt'])
    args.extend(['-C', str(Path(config['output_path']).expanduser().parent), instruction])
    return args


PROVIDERS = {'codex': {'name': 'Codex', 'binary': shutil.which('codex') or 'codex',
                       'model_hint': 'gpt-6.1-sol', 'build_command': codex_command}}
TEST_RESULTS = {}
TEST_LOCK = threading.Lock()


class ScriptError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def validate(script_id, body):
    if not isinstance(script_id, str) or not SCRIPT_ID.fullmatch(script_id):
        raise ScriptError('AI 脚本标识只能使用小写字母、数字、点、下划线和短横线')
    if not isinstance(body, dict):
        raise ScriptError('AI 脚本配置必须是对象')
    provider = body.get('provider', 'codex')
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise ScriptError('暂不支持该 AI 提供商')
    name = body.get('name', '').strip() if isinstance(body.get('name'), str) else ''
    model = body.get('model', '').strip() if isinstance(body.get('model'), str) else ''
    prompt = body.get('prompt') if isinstance(body.get('prompt'), str) else None
    output_path = body.get('output_path', '')
    if not name or len(name) > 120 or not model or len(model) > 120 or prompt is None or not prompt.strip() or len(prompt) > 100000:
        raise ScriptError('名称、模型和提示词不能为空')
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,120}', model):
        raise ScriptError('模型名称格式无效')
    if not isinstance(output_path, str) or output_path and not os.path.isabs(output_path):
        raise ScriptError('输出文件必须是绝对路径')
    script_type = body.get('script_type', 'python')
    if script_type not in ('python', 'shell'):
        raise ScriptError('脚本类型只能是 Python 或 Shell')
    if not output_path:
        raise ScriptError('请填写生成脚本保存路径')
    if script_type == 'python' and Path(output_path).suffix.lower() != '.py':
        raise ScriptError('Python 脚本路径需要 .py 扩展名')
    if script_type == 'shell' and Path(output_path).suffix.lower() not in ('.sh', '.bash'):
        raise ScriptError('Shell 脚本路径需要 .sh 或 .bash 扩展名')
    maximum = body.get('max_output_bytes', 1048576)
    timeout = body.get('timeout_seconds', 3600)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 10 * 1024 * 1024:
        raise ScriptError('输出上限无效')
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 86400:
        raise ScriptError('超时时间无效')
    return {'name': redact(name), 'provider': provider, 'model': model, 'prompt': prompt,
            'output_path': output_path, 'script_type': script_type, 'max_output_bytes': maximum,
            'timeout_seconds': timeout}


def list_scripts():
    return {'providers': [{'id': provider_id, 'name': provider['name'], 'model_hint': provider['model_hint']}
                          for provider_id, provider in PROVIDERS.items()],
            'items': [{'id': script_id, **{key: value for key, value in config.items() if key != 'prompt'},
                       'prompt_length': len(config.get('prompt', '')),
                       'command': ([sys.executable, config['output_path']] if config['script_type'] == 'python' else ['/bin/bash', config['output_path']])}
                      for script_id, config in store.get_ai_scripts().items()]}


def get(script_id):
    config = store.get_ai_scripts().get(script_id)
    if not config:
        raise ScriptError('AI 脚本不存在', 404)
    return config


def command(config, output_path=None):
    provider = PROVIDERS.get(config['provider'])
    if not provider:
        raise ScriptError('暂不支持该 AI 提供商')
    return provider['build_command'](config, output_path)


def _drain_capped(stream, maximum, result, key):
    """Drain a child pipe without retaining more than maximum + 1 bytes."""
    data = bytearray()
    total = 0
    while True:
        chunk = stream.read(8192)
        if not chunk:
            break
        total += len(chunk)
        if len(data) <= maximum:
            data.extend(chunk[:maximum + 1 - len(data)])
    result[key] = (bytes(data), total > maximum)


def _signal_process_group(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def execute_source(config, source):
    """Execute generated source only inside a disposable directory and cap its output."""
    suffix = '.py' if config['script_type'] == 'python' else '.sh'
    with tempfile.TemporaryDirectory(prefix='ai-script-run-') as directory:
        root = Path(directory)
        script = root / ('script' + suffix)
        script.write_text(source, encoding='utf-8')
        os.chmod(script, 0o700)
        run_command = ([sys.executable, str(script)] if config['script_type'] == 'python'
                       else ['/bin/bash', str(script)])
        safe_env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ') if key in os.environ}
        safe_env.update({'HOME': directory, 'TMPDIR': directory, 'TMP': directory, 'TEMP': directory})
        timed_out = False
        try:
            process = subprocess.Popen(run_command, cwd=directory, env=safe_env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            captured = {}
            readers = [threading.Thread(target=_drain_capped, args=(process.stdout, config['max_output_bytes'], captured, 'stdout'), daemon=True),
                       threading.Thread(target=_drain_capped, args=(process.stderr, 8000, captured, 'stderr'), daemon=True)]
            for reader in readers:
                reader.start()
            try:
                exit_code = process.wait(timeout=config['timeout_seconds'])
            except subprocess.TimeoutExpired:
                timed_out = True
                _signal_process_group(process, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    _signal_process_group(process, signal.SIGKILL)
                    process.wait()
            finally:
                # Do not leave child processes holding pipes under the directory being removed.
                _signal_process_group(process, signal.SIGTERM)
            for reader in readers:
                reader.join(timeout=2)
            process.stdout.close()
            process.stderr.close()
            output_bytes, output_truncated = captured.get('stdout', (b'', False))
            error_bytes, error_truncated = captured.get('stderr', (b'', False))
            output = redact(output_bytes.decode('utf-8', errors='replace'))
            error = redact(error_bytes.decode('utf-8', errors='replace'))
            return {'exit_code': 124 if timed_out else exit_code, 'output': output, 'stderr': error,
                    'output_truncated': output_truncated, 'stderr_truncated': error_truncated,
                    'timed_out': timed_out}
        except FileNotFoundError:
            return {'exit_code': 127, 'output': '', 'stderr': '找不到脚本执行环境',
                    'output_truncated': False, 'stderr_truncated': False, 'timed_out': False}


def test(script_id):
    config = copy.deepcopy(get(script_id))
    with TEST_LOCK:
        TEST_RESULTS.pop(script_id, None)
    output_path = None
    temporary = None
    try:
        temporary = tempfile.NamedTemporaryFile(prefix='ai-test-', suffix='.txt', delete=False)
        temporary.close()
        output_path = temporary.name
        result = subprocess.run(command(config, output_path), cwd=str(Path.home()), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                timeout=config['timeout_seconds'])
        output_file = Path(output_path)
        output = output_file.read_bytes() if output_file.exists() else b''
        truncated = len(output) > config['max_output_bytes']
        clipped = redact(output[:config['max_output_bytes']].decode('utf-8', errors='replace'))
        validation_error = (validate_source(config['script_type'], clipped) if clipped.strip() else '没有生成脚本源码') if result.returncode == 0 and not truncated else None
        execution = None
        if result.returncode == 0 and not truncated and clipped.strip() and not validation_error:
            execution = execute_source(config, clipped)
        execution_ok = execution is not None and execution['exit_code'] == 0 and not execution['timed_out']
        test_id = secrets.token_urlsafe(24) if execution_ok else None
        if test_id:
            fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            with TEST_LOCK:
                TEST_RESULTS[script_id] = {'id': test_id, 'created_at': time.time(), 'fingerprint': fingerprint, 'output': clipped}
        return {'ok': result.returncode == 0 and not truncated and bool(clipped.strip()) and not validation_error and execution_ok,
                'exit_code': execution['exit_code'] if execution else result.returncode,
                'generation_exit_code': result.returncode,
                'output': clipped, 'output_truncated': truncated, 'test_id': test_id,
                'stderr': redact(result.stderr or '')[-8000:], 'validation_error': validation_error,
                'execution_exit_code': execution['exit_code'] if execution else None,
                'execution_output': execution['output'] if execution else '',
                'execution_stderr': execution['stderr'] if execution else '',
                'execution_output_truncated': execution['output_truncated'] if execution else False,
                'execution_timed_out': execution['timed_out'] if execution else False}
    except FileNotFoundError:
        raise ScriptError('找不到 ' + PROVIDERS[config['provider']]['name'] + ' CLI，请先安装或修正本机路径', 503)
    except subprocess.TimeoutExpired:
        return {'ok': False, 'exit_code': 124, 'output': '', 'stderr': 'AI 脚本测试超时'}
    finally:
        if temporary:
            Path(temporary.name).unlink(missing_ok=True)


def validate_source(script_type, output):
    if script_type == 'python':
        try:
            ast.parse(output)
        except SyntaxError as error:
            return f'生成结果不是有效 Python：第 {error.lineno} 行语法错误'
    elif script_type == 'shell':
        check = subprocess.run(['/bin/bash', '-n'], input=output, capture_output=True, text=True, timeout=10)
        if check.returncode:
            return '生成结果未通过 bash -n 语法检查'
    return None


def write_script(script_id, output):
    config = get(script_id)
    if not isinstance(output, str) or not output.strip() or len(output.encode('utf-8')) > config['max_output_bytes']:
        raise ScriptError('测试输出为空或超过输出上限')
    path = Path(config['output_path']).expanduser()
    if path.suffix.lower() not in ('.py', '.sh', '.bash'):
        raise ScriptError('生成脚本路径请使用 .py、.sh 或 .bash 扩展名')
    error = validate_source(config['script_type'], output)
    if error:
        raise ScriptError(error)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        os.fchmod(fd, 0o700)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {'path': str(path), 'bytes': path.stat().st_size}


def write_tested_script(script_id, test_id):
    config = get(script_id)
    with TEST_LOCK:
        result = TEST_RESULTS.get(script_id)
        if not result or result.get('id') != test_id or time.time() - result['created_at'] > 3600:
            raise ScriptError('测试结果已过期，请重新手动测试后再写入', 409)
        fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if result['fingerprint'] != fingerprint:
            TEST_RESULTS.pop(script_id, None)
            raise ScriptError('AI 脚本配置已变更，请重新手动测试', 409)
        output = result['output']
        TEST_RESULTS.pop(script_id, None)
    return write_script(script_id, output)
