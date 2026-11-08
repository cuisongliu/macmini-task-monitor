"""通过本地 CLI 将任务定义应用到当前用户 launchd；不执行任务测试或 kickstart。"""

import copy
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import collector
import store
from config import AGENTS, DATA, ROOT, redact

LOCK = threading.RLock()
MASK = '[已隐藏，保持不变]'
SECRET_NAME = re.compile(r'token|secret|password|authorization|api.?key|webhook|credential', re.I)


class ConfigurationError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def ctl(*args):
    try:
        return subprocess.run(['/bin/launchctl', *args], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        raise ConfigurationError('无法连接当前用户 launchd，配置未应用', 503)


def checked(*args):
    result = ctl(*args)
    if result.returncode:
        # launchctl 的 stderr 可能包含业务命令/凭据，不回传。
        raise ConfigurationError('launchd ' + args[0] + ' 失败（退出码 ' + str(result.returncode) + '）', 503)
    return result


def domain():
    return 'gui/' + str(os.getuid())


def runtime_state(label):
    result = ctl('list', label)
    pid = re.search(r'"PID"\s*=\s*(\d+)', result.stdout) if result.returncode == 0 else None
    return {'loaded': result.returncode == 0, 'pid': int(pid[1]) if pid else None}


def disabled_states():
    result = checked('print-disabled', domain())
    return {label: value == 'true' for label, value in re.findall(r'"([^"\n]+)"\s*=>\s*(true|false)', result.stdout)}


def revision(raw, disabled):
    return hashlib.sha256(raw + str(disabled).encode()).hexdigest()


def display_arguments(arguments):
    result, hide_next = [], False
    for argument in arguments:
        hide = hide_next or redact(argument) != argument
        hide_next = argument.startswith('-') and bool(SECRET_NAME.search(argument)) and '=' not in argument
        result.append(MASK if hide or (SECRET_NAME.search(argument.split('=', 1)[0]) and '=' in argument) else argument)
    return result


def schedule_from_definition(definition):
    interval, calendar = definition.get('StartInterval'), definition.get('StartCalendarInterval')
    if interval and not calendar:
        return {'type': 'interval', 'seconds': interval}
    if calendar and not interval:
        rules = calendar if isinstance(calendar, list) else [calendar]
        if len(rules) == 1 and set(rules[0]) <= {'Hour', 'Minute'} and 'Hour' in rules[0]:
            return {'type': 'daily', 'time': f"{rules[0]['Hour']:02d}:{rules[0].get('Minute', 0):02d}"}
        if rules and all(set(rule) <= {'Hour', 'Minute', 'Weekday'} and 'Hour' in rule and 'Weekday' in rule for rule in rules):
            times = {(rule['Hour'], rule.get('Minute', 0)) for rule in rules}
            if len(times) == 1:
                hour, minute = next(iter(times))
                return {'type': 'weekly', 'time': f'{hour:02d}:{minute:02d}', 'weekdays': sorted({rule['Weekday'] % 7 for rule in rules})}
        return {'type': 'calendar', 'rules': calendar}
    if interval and calendar:
        return {'type': 'combined', 'seconds': interval, 'rules': calendar}
    return {'type': 'manual'}


def definition_view(path, definition, raw, state, disabled, metadata):
    arguments = definition.get('ProgramArguments', [])
    env = definition.get('EnvironmentVariables', {})
    source = 'service' if definition.get('MiniMonitorKind') == 'service' or definition.get('KeepAlive') else 'launchd'
    return {'id': definition['Label'], 'source': source,
            'name': metadata.get('name') or definition.get('Name') or definition['Label'],
            'description': metadata.get('description', ''), 'enabled': not disabled,
            'loaded': state['loaded'], 'pid': state['pid'], 'revision': revision(raw, disabled),
            'definition_path': str(path), 'managed': metadata.get('managed', False),
            'ai_script_id': metadata.get('ai_script_id'),
            'execution': {'program': redact(definition.get('Program', '')), 'arguments': display_arguments(arguments),
                          'ai_script_id': metadata.get('ai_script_id'),
                          'working_directory': redact(definition.get('WorkingDirectory', '')),
                          'environment': [{'key': key, 'value': '', 'retained': True} for key in sorted(env)],
                          'stdout_path': redact(definition.get('StandardOutPath', '')),
                          'stderr_path': redact(definition.get('StandardErrorPath', '')),
                          'run_at_load': definition.get('RunAtLoad', False),
                          'keep_alive': definition.get('KeepAlive', False),
                          'schedule': schedule_from_definition(definition)}}


def locate(task_id):
    # 只操作发现目录内的普通 plist，不使用来自 URL 的文件路径。
    for path in sorted(AGENTS.glob('*.plist')):
        if path.is_symlink():
            continue
        try:
            raw = path.read_bytes()
            definition = plistlib.loads(raw)
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue
        if isinstance(definition, dict) and definition.get('Label') == task_id and not collector.is_monitor_definition(definition):
            return path, definition, raw
    raise ConfigurationError('launchd 定义不存在，请刷新配置列表', 404)


def list_configurations():
    saved = store.get_task_configs()
    tasks, services = collector.read_definitions()
    overrides = disabled_states()
    items = []
    for task in [*tasks, *services]:
        path, definition, raw = locate(task['id'])
        disabled = overrides.get(task['id'], bool(definition.get('Disabled')))
        items.append(definition_view(path, definition, raw, runtime_state(task['id']), disabled, saved.get(task['id'], {})))
    for task_id, config in saved.items():
        if config.get('source') == 'external':
            items.append({'id': task_id, **config})
    return {'items': items}


def string(value, label, maximum=4096):
    if not isinstance(value, str) or '\0' in value or len(value) > maximum:
        raise ConfigurationError(label + '格式无效')
    return value


def absolute_path(value, label):
    value = string(value, label)
    if value and not Path(value).is_absolute():
        raise ConfigurationError(label + '必须是绝对路径')
    return value


def integer(value, minimum, maximum, label):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ConfigurationError(label + '超出允许范围')
    return value


def calendar_rules(value):
    rules = value if isinstance(value, list) else [value]
    if not rules or len(rules) > 100:
        raise ConfigurationError('日历规则需要 1–100 条')
    limits = {'Minute': (0, 59), 'Hour': (0, 23), 'Day': (1, 31), 'Weekday': (0, 7), 'Month': (1, 12)}
    for rule in rules:
        if not isinstance(rule, dict) or not rule or set(rule) - set(limits):
            raise ConfigurationError('日历规则仅支持 Minute、Hour、Day、Weekday、Month')
        for key, number in rule.items():
            integer(number, *limits[key], '日历 ' + key)
    return copy.deepcopy(value)


def apply_schedule(definition, schedule):
    if not isinstance(schedule, dict):
        raise ConfigurationError('请选择真实调度规则')
    kind = schedule.get('type')
    definition.pop('StartInterval', None)
    definition.pop('StartCalendarInterval', None)
    if kind in ('interval', 'combined'):
        definition['StartInterval'] = integer(schedule.get('seconds'), 1, 2147483647, '执行间隔（秒）')
    if kind in ('daily', 'weekly'):
        value = schedule.get('time', '')
        if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
            raise ConfigurationError('执行时间需要 HH:MM 格式')
        hour, minute = map(int, value.split(':'))
        if kind == 'daily':
            definition['StartCalendarInterval'] = {'Hour': hour, 'Minute': minute}
        else:
            weekdays = schedule.get('weekdays')
            if not isinstance(weekdays, list) or not weekdays or len(weekdays) > 7:
                raise ConfigurationError('请至少选择一个执行星期')
            days = sorted({integer(day, 0, 6, '星期') for day in weekdays})
            definition['StartCalendarInterval'] = [{'Weekday': day, 'Hour': hour, 'Minute': minute} for day in days]
    elif kind in ('calendar', 'combined'):
        definition['StartCalendarInterval'] = calendar_rules(schedule.get('rules'))
    elif kind not in ('interval', 'manual'):
        raise ConfigurationError('不支持的调度类型')


def build_definition(body, original, task_id, source):
    execution = body.get('execution')
    if not isinstance(execution, dict):
        raise ConfigurationError('缺少真实执行配置，请刷新页面后重新编辑')
    definition = copy.deepcopy(original)
    definition['Label'] = task_id
    script_id = execution.get('ai_script_id')
    if script_id:
        scripts = store.get_ai_scripts()
        script = scripts.get(script_id)
        if not script:
            raise ConfigurationError('请选择存在的 AI 脚本')
        execution = copy.deepcopy(execution)
        execution['arguments'] = ([sys.executable, script['output_path']] if script['script_type'] == 'python'
                                  else ['/bin/bash', script['output_path']])
        execution['program'] = ''
    if not original or ('KeepAlive' in original and execution.get('keep_alive') != original['KeepAlive']):
        definition['MiniMonitorKind'] = 'service' if source == 'service' else 'timer'
    arguments = execution.get('arguments')
    old_arguments = original.get('ProgramArguments', [])
    old_display = display_arguments(old_arguments)
    arguments_unchanged = arguments == old_display
    if not isinstance(arguments, list) or len(arguments) > 256:
        raise ConfigurationError('命令参数需要数组，最多 256 项')
    if arguments_unchanged:
        arguments = old_arguments
    elif MASK in arguments:
        raise ConfigurationError('命令含隐藏凭据；修改命令时请填写完整参数，或保留原命令不变')
    arguments = [string(value, '命令参数', 16384) for value in arguments]
    program_value = string(execution.get('program', ''), '可执行文件')
    old_program = original.get('Program', '')
    program_unchanged = program_value == redact(old_program)
    program = old_program if program_unchanged else absolute_path(program_value, '可执行文件')
    if not arguments and not program:
        raise ConfigurationError('请填写可执行文件或完整命令参数')
    if not program and (not arguments or not arguments[0]):
        raise ConfigurationError('命令第一项必须是可执行文件绝对路径')
    if not program and not (arguments_unchanged or (old_arguments and arguments[0] == old_arguments[0])) and not Path(arguments[0]).is_absolute():
        raise ConfigurationError('修改命令入口时必须使用可执行文件绝对路径')
    for key, value in [('Program', program), ('ProgramArguments', arguments),
                       ('WorkingDirectory', absolute_path(execution.get('working_directory', ''), '工作目录')),
                       ('StandardOutPath', absolute_path(execution.get('stdout_path', ''), '标准输出日志路径')),
                       ('StandardErrorPath', absolute_path(execution.get('stderr_path', ''), '错误日志路径'))]:
        if value:
            definition[key] = value
        else:
            definition.pop(key, None)
    environment = execution.get('environment', [])
    if not isinstance(environment, list) or len(environment) > 100:
        raise ConfigurationError('环境变量最多 100 项')
    env = {}
    for entry in environment:
        if not isinstance(entry, dict):
            raise ConfigurationError('环境变量格式无效')
        key = entry.get('key')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or key in env:
            raise ConfigurationError('环境变量名称无效或重复')
        if entry.get('retained') and entry.get('value', '') == '' and key in original.get('EnvironmentVariables', {}):
            env[key] = original['EnvironmentVariables'][key]
        else:
            env[key] = string(entry.get('value', ''), '环境变量值', 16384)
    if env:
        definition['EnvironmentVariables'] = env
    else:
        definition.pop('EnvironmentVariables', None)
    run_at_load = execution.get('run_at_load', False)
    keep_alive = execution.get('keep_alive', False)
    if not isinstance(run_at_load, bool) or not isinstance(keep_alive, (bool, dict)):
        raise ConfigurationError('启动规则格式无效')
    if isinstance(keep_alive, dict):
        if keep_alive != original.get('KeepAlive'):
            raise ConfigurationError('复杂 KeepAlive 条件请保持原值，或改为开启/关闭')
    for key, value in [('RunAtLoad', run_at_load), ('KeepAlive', keep_alive)]:
        if value or key in original:
            definition[key] = value
    # 无修改时逐字保留复杂原规则（含星期日 7、缺省字段和规则顺序）。
    if execution.get('schedule') != schedule_from_definition(original):
        apply_schedule(definition, execution.get('schedule'))
    if not body['enabled'] or 'Disabled' in original:
        definition['Disabled'] = not body['enabled']
    return definition


def atomic_write(path, raw, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def backup_definition(task_id, raw):
    path = DATA / 'launchd-backups' / (hashlib.sha256(task_id.encode()).hexdigest()[:16] + '-' + str(time.time_ns()) + '.plist')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(path, raw)
    return str(path)


def metadata(body, source, original=None):
    value = dict(original or {})
    value.update({'source': source, 'name': redact(string(body.get('name', ''), '任务名称', 120).strip()),
                  'description': redact(string(body.get('description', ''), '任务说明', 1000).strip()),
                  'enabled': body.get('enabled')})
    if not value['name'] or not isinstance(value['enabled'], bool):
        raise ConfigurationError('任务名称和启用状态不能为空')
    execution = body.get('execution', {})
    if isinstance(execution, dict) and execution.get('ai_script_id'):
        script_id = execution['ai_script_id']
        if script_id not in store.get_ai_scripts():
            raise ConfigurationError('请选择存在的 AI 脚本')
        value['ai_script_id'] = script_id
    else:
        value.pop('ai_script_id', None)
    return value


def save(task_id, body, source):
    """先验证、备份，再应用调度器；任何一步失败都不谎报成功。"""
    with LOCK:
        previous = store.get_task_configs().get(task_id)
        info = metadata(body, source, previous)
        creating = previous is None and body.get('creating') is True
        if creating:
            path, original, raw = AGENTS / (task_id + '.plist'), {}, None
            if path.exists() or path.is_symlink():
                raise ConfigurationError('任务标识已存在', 409)
            state = {'loaded': False, 'pid': None}
            disabled = True
        else:
            path, original, raw = locate(task_id)
            disabled = disabled_states().get(task_id, bool(original.get('Disabled')))
            if body.get('revision') != revision(raw, disabled):
                raise ConfigurationError('配置已被其他进程修改，请刷新后重试', 409)
            state = runtime_state(task_id)
        execution = body.get('execution', {})
        script_id = execution.get('ai_script_id') if isinstance(execution, dict) else None
        if script_id and not (previous or {}).get('ai_script_id'):
            info['ai_script_original'] = {
                'Program': original.get('Program') if not creating else execution.get('program') or None,
                'ProgramArguments': copy.deepcopy(original.get('ProgramArguments', []) if not creating
                                                  else execution.get('arguments', []))}
        elif not script_id and (previous or {}).get('ai_script_id'):
            baseline = previous.get('ai_script_original')
            if not isinstance(baseline, dict):
                raise ConfigurationError('缺少切换前命令，无法安全移除 AI 脚本引用', 409)
            body = copy.deepcopy(body)
            body['execution']['program'] = baseline.get('Program') or ''
            body['execution']['arguments'] = baseline.get('ProgramArguments', [])
            info.pop('ai_script_original', None)
        definition = build_definition(body, original, task_id, source)
        enabled_before = not disabled
        changed = creating or definition != original or body['enabled'] != enabled_before
        if not changed:
            store.save_task_config(task_id, info)
            return {'id': task_id, 'ok': True, 'applied': True, 'reloaded': False}
        if state['pid'] and body.get('restart_running') is not True:
            raise ConfigurationError('任务或服务正在运行；请等它结束，或明确选择“允许停止当前进程并重新加载”', 409)
        backup = backup_definition(task_id, raw) if raw is not None else None
        mode = path.stat().st_mode & 0o777 if raw is not None else 0o600
        encoded = plistlib.dumps(definition, sort_keys=False)
        stopped, wrote, bootstrapped = False, False, False
        bootstrap_attempted = False
        target = domain() + '/' + task_id
        try:
            if state['loaded']:
                if runtime_state(task_id)['pid'] and body.get('restart_running') is not True:
                    raise ConfigurationError('任务刚开始运行，请等待结束后重试', 409)
                checked('bootout', target)
                stopped = True
            # 检查在备份后是否有外部写入；不覆盖并发更新。
            if raw is not None and path.read_bytes() != raw:
                raise ConfigurationError('原定义在保存期间改变，请刷新重试', 409)
            atomic_write(path, encoded, mode)
            wrote = True
            checked('enable' if body['enabled'] else 'disable', target)
            if body['enabled']:
                bootstrap_attempted = True
                checked('bootstrap', domain(), str(path))
                bootstrapped = True
            info.update({'managed': creating or info.get('managed', False), 'definition_path': str(path),
                         'definition': definition, 'backup_path': backup, 'applied_at': time.time()})
            store.save_task_config(task_id, info)
        except Exception as error:
            if not stopped and not wrote:
                raise
            try:
                if bootstrapped or (bootstrap_attempted and runtime_state(task_id)['loaded']):
                    checked('bootout', target)
                if wrote:
                    if raw is None:
                        path.unlink(missing_ok=True)
                    else:
                        atomic_write(path, raw, mode)
                checked('disable' if disabled else 'enable', target)
                if stopped:
                    checked('bootstrap', domain(), str(path))
            except Exception:
                raise ConfigurationError('应用失败且自动恢复未完成；原定义已备份，请通过本机维护检查', 503) from None
            if isinstance(error, ConfigurationError):
                raise
            raise ConfigurationError('配置保存失败，已恢复原 launchd 定义', 503) from None
        return {'id': task_id, 'ok': True, 'applied': True, 'reloaded': body['enabled'], 'backup_path': backup}


def remove(task_id, expected_revision):
    with LOCK:
        config = store.get_task_configs().get(task_id, {})
        if not config.get('managed'):
            raise ConfigurationError('自动发现的系统任务请使用停用；仅能删除本页面创建的任务')
        path, definition, raw = locate(task_id)
        disabled = disabled_states().get(task_id, bool(definition.get('Disabled')))
        if expected_revision != revision(raw, disabled):
            raise ConfigurationError('配置已变更，请刷新后重试', 409)
        state = runtime_state(task_id)
        if state['pid']:
            raise ConfigurationError('任务正在运行，请先停用并等待进程退出', 409)
        backup_definition(task_id, raw)
        target = domain() + '/' + task_id
        try:
            if state['loaded']:
                checked('bootout', target)
            checked('disable', target)
            path.unlink()
            store.delete_task_config(task_id)
        except Exception:
            try:
                atomic_write(path, raw)
                checked('disable' if disabled else 'enable', target)
                if state['loaded']:
                    checked('bootstrap', domain(), str(path))
            except Exception:
                raise ConfigurationError('删除失败且自动恢复未完成；原定义已备份', 503) from None
            raise ConfigurationError('删除失败，已恢复原定义', 503) from None
        return {'ok': True}
