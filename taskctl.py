#!/usr/bin/env python3
"""Read or apply current-user launchd task configuration from the local CLI."""

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

import launchd_config
import store

LABEL = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$')


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def read_document(source):
    if source == '-':
        raw = sys.stdin.read(1024 * 1024 + 1)
    else:
        raw = Path(source).read_text(encoding='utf-8')
    if len(raw.encode('utf-8')) > 1024 * 1024:
        raise ValueError('任务定义不能超过 1 MiB')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('任务定义必须是 JSON 对象')
    return value


def apply_document(document, source_override=None):
    body = dict(document)
    task_id = body.pop('id', '')
    existing = bool(task_id)
    source = body.pop('source', None)
    if existing:
        _, definition, _ = launchd_config.locate(task_id)
        actual_source = 'service' if definition.get('MiniMonitorKind') == 'service' or definition.get('KeepAlive') else 'launchd'
        if source_override and source_override != actual_source:
            raise ValueError('更新任务时不能更改任务来源')
        source = actual_source
    else:
        source = source_override or source
    if source not in ('launchd', 'service'):
        raise ValueError('任务来源必须是 launchd 或 service')
    if existing:
        if not LABEL.fullmatch(task_id):
            raise ValueError('任务标识格式无效')
        launchd_config.locate(task_id)
        body.pop('creating', None)
    else:
        task_id = 'local.mini-monitor.cli.' + uuid.uuid4().hex[:16]
        body['creating'] = True
    result = launchd_config.save(task_id, body, source)
    return {'id': task_id, **result}


def select_ai_script(task_id, script_id, restart_running=False):
    if script_id not in store.get_ai_scripts():
        raise ValueError('AI 脚本不存在；请先在 AI 脚本页面保存')
    return _set_ai_script(task_id, script_id, restart_running)


def clear_ai_script(task_id, restart_running=False):
    return _set_ai_script(task_id, None, restart_running)


def _set_ai_script(task_id, script_id, restart_running):
    item = next((item for item in launchd_config.list_configurations()['items'] if item['id'] == task_id), None)
    if not item or item.get('source') not in ('launchd', 'service'):
        raise ValueError('launchd 任务不存在')
    if script_id:
        item['execution']['ai_script_id'] = script_id
    else:
        item['execution'].pop('ai_script_id', None)
    result = launchd_config.save(task_id, {
        'name': item['name'], 'description': item.get('description', ''), 'enabled': item['enabled'],
        'revision': item['revision'], 'restart_running': restart_running,
        'execution': item['execution']}, item['source'])
    return {'id': task_id, 'ai_script_id': script_id, **result}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='列出实际 launchd 配置')
    show = commands.add_parser('show', help='输出单个任务的可编辑 JSON 定义')
    show.add_argument('task_id')
    apply = commands.add_parser('apply', help='从文件或 stdin 新建/应用任务定义')
    apply.add_argument('--file', default='-', help='JSON 文件路径；默认为 stdin')
    apply.add_argument('--source', choices=('launchd', 'service'), help='新任务来源或覆盖 JSON 来源')
    remove = commands.add_parser('delete', help='删除由本项目 CLI 创建的 launchd 任务')
    remove.add_argument('task_id')
    remove.add_argument('--revision', required=True, help='show 输出中的 revision')
    use_script = commands.add_parser('use-ai-script', help='让现有 launchd 任务运行脚本库中的本地脚本')
    use_script.add_argument('task_id')
    use_script.add_argument('script_id')
    use_script.add_argument('--restart-running', action='store_true', help='允许停止并重新加载正在运行的进程')
    clear_script = commands.add_parser('clear-ai-script', help='恢复关联 AI 脚本前保存的原命令')
    clear_script.add_argument('task_id')
    clear_script.add_argument('--restart-running', action='store_true', help='允许停止并重新加载正在运行的进程')
    return result


def main(argv=None):
    options = parser().parse_args(argv)
    store.initialize()
    if options.command == 'list':
        emit(launchd_config.list_configurations())
    elif options.command == 'show':
        item = next((item for item in launchd_config.list_configurations()['items'] if item['id'] == options.task_id), None)
        if not item:
            raise ValueError('任务不存在')
        emit(item)
    elif options.command == 'apply':
        emit(apply_document(read_document(options.file), options.source))
    elif options.command == 'delete':
        emit(launchd_config.remove(options.task_id, options.revision))
    elif options.command in ('use-ai-script', 'clear-ai-script'):
        if options.command == 'use-ai-script':
            emit(select_ai_script(options.task_id, options.script_id, options.restart_running))
        else:
            emit(clear_ai_script(options.task_id, options.restart_running))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print('taskctl: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
