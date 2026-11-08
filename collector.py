"""只读取当前用户的 launchd plist 和进程状态，不触发被监控任务。"""

import datetime as dt
import hashlib
import json
import os
import plistlib
import re
import socket
import subprocess
import time
from pathlib import Path

import store
from config import AGENTS, ROOT, ZONE, redact
from outcomes import scan_result_from_log


SCRIPT_SUFFIXES = {'.py', '.sh', '.js', '.mjs', '.ts'}


def command(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=8, env={**os.environ, 'LC_ALL': 'C'})


def gui_states():
    """launchctl list 的 PID 为 '-' 表示等待，不把已注册任务误判为正在运行。"""
    result = command(['launchctl', 'list'])
    if result.returncode:
        raise RuntimeError('无法读取当前用户的 launchd 状态')
    states = {}
    for line in result.stdout.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) == 3:
            pid, exit_code, label = parts
            states[label] = {'loaded': True, 'pid': int(pid) if pid.isdigit() else None,
                             'last_exit_code': int(exit_code) if re.fullmatch(r'-?\d+', exit_code) else None}
    return states


def is_monitor_definition(definition):
    """避免把本看板自己的 KeepAlive LaunchAgent 展示成被监控任务。"""
    for part in definition.get('ProgramArguments', []):
        path = Path(part)
        if path.is_absolute() and path.resolve() == ROOT / 'server.py':
            return True
    return False


def script_path(definition):
    arguments = definition.get('ProgramArguments') or []
    candidates = [*arguments, definition.get('Program', '')]
    for value in candidates:
        if not isinstance(value, str) or not value.startswith('/'):
            continue
        path = Path(value)
        if path.suffix.lower() in SCRIPT_SUFFIXES:
            return value
    return definition.get('Program', '')


def read_definitions(directory=None):
    """从当前用户的 LaunchAgents 目录发现定时任务与常驻服务。"""
    directory = Path(directory or AGENTS)
    tasks, services = [], []
    try:
        plist_paths = sorted(directory.glob('*.plist'))
    except OSError:
        return tasks, services
    for path in plist_paths:
        try:
            definition = plistlib.loads(path.read_bytes())
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue
        if not isinstance(definition, dict) or is_monitor_definition(definition):
            continue
        label = definition.get('Label') or path.stem
        logs = [definition[key] for key in ('StandardOutPath', 'StandardErrorPath')
                if isinstance(definition.get(key), str)]
        common = {'id': label, 'label': label, 'name': definition.get('Name') or label,
                  'description': '从当前用户的 LaunchAgents 自动发现。',
                  'source': 'launchd', 'definition_path': str(path), 'log_paths': logs}
        if definition.get('MiniMonitorKind') == 'timer' or definition.get('StartInterval') or definition.get('StartCalendarInterval'):
            tasks.append({**common, 'icon': 'clock', 'category': 'work',
                          'script': script_path(definition), 'source': 'launchd'})
        elif definition.get('MiniMonitorKind') == 'service' or definition.get('KeepAlive'):
            services.append({**common, 'domain': 'gui', 'description': '当前用户的 launchd 常驻服务。',
                             'script': script_path(definition)})
    return tasks, services


def definitions(directory=None):
    """兼容调用方，只返回定时任务定义。"""
    return read_definitions(directory)[0]


def import_record(data):
    """以稳定外部键导入已有凭据；不会执行来源任务。"""
    key = data['external_key']
    store.insert_run({'id': 'h-' + hashlib.sha256(key.encode()).hexdigest()[:24], 'kind': 'history', **data})


def needs_receipt(task_id, event_time):
    """仅在同一时刻没有实时执行覆盖时允许导入一条外部凭据。"""
    with store.connect() as db:
        row = db.execute("SELECT 1 FROM runs WHERE task_id=? AND kind='execution' AND started_at<=? AND (finished_at>=? OR (status='running' AND heartbeat_at>=?)) LIMIT 1",
                         (task_id, event_time, event_time, event_time - 30)).fetchone()
    return row is None


def scan_log_tail():
    config = store.get_task_configs().get('pr-scan', {})
    with store.connect() as db:
        row = db.execute('SELECT snapshot FROM tasks WHERE id=?', ('pr-scan',)).fetchone()
    task = json.loads(row['snapshot']) if row else {}
    paths = config.get('log_paths', task.get('log_paths', []))
    contents = []
    for value in paths:
        path = Path(value)
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 48000))
            contents.append(stream.read(48000).decode('utf-8', errors='replace'))
    return '\n'.join(contents)


def normalize_empty_scans():
    """将明确记录空队列的成功扫描归类为跳过，保留失败和未知结果。"""
    key = 'empty_scan_classification_v1'
    previous = store.get_meta(key)
    since = time.time() - 86400 if previous and previous.get('history_normalized') else 0
    with store.connect() as db:
        rows = db.execute("SELECT id,kind,external_key,log_tail FROM runs WHERE task_id='pr-scan' AND status='success' AND ((kind='execution' AND exit_code=0) OR (kind='history' AND external_key LIKE 'scan:%')) AND created_at>=?", (since,)).fetchall()
    updates, original_log = [], None
    for row in rows:
        if row['kind'] == 'history':
            if original_log is None:
                original_log = scan_log_tail()
            result = scan_result_from_log(original_log, row['external_key'].removeprefix('scan:'))
        else:
            result = scan_result_from_log(row['log_tail'])
        if result is not None and result[0] == 'skipped':
            updates.append((row['id'], result[1]))
    if updates:
        store.backup_database('monitor-before-empty-scan-v1.sqlite3')
        with store.connect() as db:
            db.executemany("UPDATE runs SET status='skipped',summary=? WHERE id=? AND status='success' AND (exit_code=0 OR (kind='history' AND external_key LIKE 'scan:%'))", [(summary, run_id) for run_id, summary in updates])
    if updates or previous is None or not previous.get('history_normalized'):
        store.set_meta(key, {'applied_at': (previous or {}).get('applied_at', time.time()),
                             'reclassified': (previous or {}).get('reclassified', 0) + len(updates), 'history_normalized': True})
    return len(updates)


def automation_calendar(rule):
    """将简单的每日/每周规则转换成 launchd 日历规则；复杂规则保持未知。"""
    values = dict(part.split('=', 1) for part in rule.removeprefix('RRULE:').split(';') if '=' in part)
    if set(values) - {'FREQ', 'INTERVAL', 'BYDAY', 'BYHOUR', 'BYMINUTE'} or values.get('INTERVAL', '1') != '1':
        return None
    if values.get('FREQ') not in ('DAILY', 'WEEKLY') or not values.get('BYHOUR'):
        return None
    mapping = {'SU': 0, 'MO': 1, 'TU': 2, 'WE': 3, 'TH': 4, 'FR': 5, 'SA': 6}
    days = values.get('BYDAY', '').split(',') if values.get('BYDAY') else []
    if days and not set(days).issubset(mapping):
        return None
    if values['FREQ'] == 'WEEKLY' and not days:
        return None
    weekdays = [None] if not days or len(set(days)) == 7 else [mapping[day] for day in days]
    result = []
    for hour in map(int, values['BYHOUR'].split(',')):
        for minute in map(int, values.get('BYMINUTE', '0').split(',')):
            if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                return None
            for day in weekdays:
                result.append({'Hour': hour, 'Minute': minute, **({'Weekday': day} if day is not None else {})})
    return result


def schedule_info(task, definition, now):
    """日历任务给出下一计划时间；间隔任务标注估计，避免声称掌握 launchd 内部计时器。"""
    interval = definition.get('StartInterval')
    calendar = definition.get('StartCalendarInterval')
    if interval:
        task['schedule'] = {'type': 'interval', 'seconds': interval,
                            'text': f'每 {interval // 60} 分钟' if interval % 60 == 0 else f'每 {interval} 秒'}
        reference = (task.get('last_run') or {}).get('started_at')
        task['next_at'] = reference + (int((now - reference) // interval) + 1) * interval if reference and not task.get('pid') else None
        task['next_estimated'] = True
    elif calendar:
        calendars = calendar if isinstance(calendar, list) else [calendar]
        candidates, previous, labels = [], [], []
        for rule in calendars:
            local = dt.datetime.fromtimestamp(now, ZONE)
            if set(rule) == {'Minute'} and 0 <= rule['Minute'] <= 59:
                next_date = local.replace(minute=rule['Minute'], second=0, microsecond=0)
                if next_date.timestamp() <= now:
                    next_date += dt.timedelta(hours=1)
                candidates.append(next_date.timestamp())
                previous.append((next_date - dt.timedelta(hours=1)).timestamp())
                labels.append('每小时整点' if rule['Minute'] == 0 else f"每小时 {rule['Minute']:02d} 分")
            elif set(rule).issubset({'Hour', 'Minute', 'Weekday'}) and 'Hour' in rule:
                next_date = local.replace(hour=rule['Hour'], minute=rule.get('Minute', 0), second=0, microsecond=0)
                weekday = rule.get('Weekday')
                period = 7 if weekday is not None else 1
                if weekday is not None:
                    next_date += dt.timedelta(days=(weekday % 7 - (local.weekday() + 1) % 7) % 7)
                if next_date.timestamp() <= now:
                    next_date += dt.timedelta(days=period)
                candidates.append(next_date.timestamp())
                previous.append((next_date - dt.timedelta(days=period)).timestamp())
                prefix = f'每周{"日一二三四五六"[weekday % 7]}' if weekday is not None else '每天'
                labels.append(f'{prefix} {rule["Hour"]:02d}:{rule.get("Minute", 0):02d}')
        task['schedule'] = {'type': 'calendar', 'rules': calendars,
                            'text': '、'.join(labels) if candidates and len(candidates) == len(calendars)
                            else '日历规则：' + str(calendar)}
        task['next_at'] = min(candidates) if candidates else None
        task['previous_at'] = max(previous) if previous else None
        task['next_estimated'] = False
    else:
        task['schedule'] = {'type': 'manual', 'text': '手动或事件触发'}
        task['next_at'] = None
    return task


def recover_orphans():
    """进程消失时标记中断，但不把观察时间误记成实际结束时间。"""
    with store.connect() as db:
        rows = db.execute('SELECT id,pid,process_start,started_at FROM runs WHERE status=?', ('running',)).fetchall()
    for row in rows:
        if row['started_at'] is not None and time.time() - row['started_at'] < 30:
            continue
        result = command(['ps', '-p', str(row['pid']), '-o', 'lstart='])
        if result.returncode or (row['process_start'] and result.stdout.strip() != row['process_start']):
            store.update_run(row['id'], status='interrupted', summary='记录进程已退出，未收到正常结束凭据；实际结束时间未知')


def collect():
    """更新自动发现任务与服务的状态快照；不访问任务业务数据或调用任务。"""
    now = time.time()
    errors = []
    normalize_empty_scans()
    detected, services = read_definitions()
    configurations = store.get_task_configs()
    ai_scripts = store.get_ai_scripts()
    tasks = []
    for task in detected:
        settings = configurations.get(task['id'], {})
        task['name'] = settings.get('name') or task['name']
        task['description'] = settings.get('description', task['description'])
        task['log_paths'] = list(task.get('log_paths', []))
        ai_script = ai_scripts.get(settings.get('ai_script_id'), {})
        ai_output = ai_script.get('output_path')
        if ai_output and ai_output not in task['log_paths']:
            task['log_paths'].append(ai_output)
        tasks.append(task)
    for task_id, settings in configurations.items():
        if settings.get('source') != 'external' or settings.get('enabled') is False:
            continue
        tasks.append({'id': task_id, 'label': None, 'name': settings['name'],
                      'description': settings.get('description', ''), 'source': 'external',
                      'category': 'work', 'icon': 'clock', 'script': settings.get('script', ''),
                      'log_paths': settings.get('log_paths', []), 'external_schedule': settings.get('schedule', '')})
    try:
        states = gui_states()
        launchd_available = True
    except Exception as error:
        states, launchd_available = {}, False
        errors.append(redact(error))

    seen = []
    for task in tasks:
        label = task['label']
        if task['source'] == 'external':
            with store.connect() as db:
                row = db.execute('SELECT * FROM runs WHERE task_id=? ORDER BY created_at DESC LIMIT 1', (task['id'],)).fetchone()
            task['last_run'] = store.decode_run(row)
            if task['last_run']:
                task['last_run'].pop('log_tail', None)
            task['loaded'] = True
            task['pid'] = None
            task['last_exit_code'] = None
            task['instrumented'] = False
            task['state'] = 'unknown'
            task['schedule'] = {'type': 'external', 'text': task.pop('external_schedule') or '外部调度'}
            task['next_at'] = None
            task['next_estimated'] = False
            task['updated_at'] = now
            store.save_task(task)
            seen.append(task['id'])
            continue
        definition = {}
        try:
            definition = plistlib.loads(Path(task['definition_path']).read_bytes())
        except (OSError, ValueError, plistlib.InvalidFileException) as error:
            errors.append(label + ': ' + redact(error))
        task.update(states.get(label, {'loaded': False, 'pid': None, 'last_exit_code': None}))
        task['instrumented'] = str(ROOT / 'runner.py') in definition.get('ProgramArguments', [])
        with store.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE task_id=? ORDER BY created_at DESC LIMIT 1', (label,)).fetchone()
        task['last_run'] = store.decode_run(row)
        if task['last_run']:
            task['last_run'].pop('log_tail', None)
        last = task['last_run'] or {}
        task['state'] = 'running' if task['pid'] or last.get('status') == 'running' else 'ready'
        if not launchd_available:
            task['state'] = 'unknown'
        elif not task['loaded']:
            task['state'] = 'disabled'
        elif task['state'] != 'running':
            if last.get('status') in ('failed', 'interrupted', 'unknown') or task.get('last_exit_code') not in (None, 0):
                task['state'] = 'attention'
        schedule_info(task, definition, now)
        if not task['loaded']:
            task['next_at'] = None
        if task['schedule']['type'] == 'calendar' and task.get('next_at') and task['state'] == 'ready':
            previous = task.get('previous_at')
            if previous is not None and now > previous + 1800 and last.get('created_at', 0) < previous:
                task['state'] = 'overdue'
        if task['instrumented'] and task['schedule']['type'] == 'interval' and task['state'] == 'ready':
            installation = store.get_meta('installation:' + label, {})
            reference = max(installation.get('installed_at', 0), last.get('finished_at') or last.get('created_at', 0))
            if reference and now - reference > task['schedule']['seconds'] * 2 + 60:
                task['state'] = 'overdue'
        task['updated_at'] = now
        store.save_task(task)
        seen.append(label)

    with store.connect() as db:
        if seen:
            placeholders = ','.join('?' for _ in seen)
            db.execute('DELETE FROM tasks WHERE id NOT IN (' + placeholders + ')', seen)
        else:
            db.execute('DELETE FROM tasks')

    service_snapshots = []
    for service in services:
        settings = configurations.get(service['id'], {})
        service['name'] = settings.get('name') or service['name']
        service['description'] = settings.get('description', service['description'])
        service['log_paths'] = service.get('log_paths', [])
        service.update(states.get(service['label'], {'loaded': False, 'pid': None, 'last_exit_code': None}))
        service['state'] = ('unknown' if not launchd_available else 'disabled' if not service['loaded'] else 'running' if service['pid']
                            else 'attention' if service.get('last_exit_code') not in (None, 0) else 'stopped')
        service_snapshots.append(service)
    store.set_meta('collector', {'checked_at': now, 'errors': errors, 'hostname': socket.gethostname(),
                                'services': service_snapshots})
    recover_orphans()


def loop(stop):
    """持续更新状态，采集失败时保留上一轮快照并稍后重试。"""
    while not stop.is_set():
        try:
            collect()
        except Exception as error:
            print('collector_error:', redact(error), flush=True)
        stop.wait(15)
