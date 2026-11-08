#!/usr/bin/env python3
"""本机任务监控、launchd 配置管理与可配置的 AI 脚本库。"""

import argparse
import datetime as dt
import json
import signal
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import collector
import ai_scripts
import launchd_config
import store
from config import DB_PATH, ROOT, ZONE, redact


def snapshot():
    """返回一次一致的账本视图；统计中的“记录”包括明确标识来源的历史凭据。"""
    today = dt.datetime.now(ZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    with store.connect() as db:
        tasks = [json.loads(row['snapshot']) for row in db.execute('SELECT snapshot FROM tasks ORDER BY rowid')]
        counts = {row['status']: row['total'] for row in db.execute('SELECT status,count(*) AS total FROM runs WHERE created_at>=? GROUP BY status', (today.timestamp(),))}
        daily = []
        for offset in range(6, -1, -1):
            day = today - dt.timedelta(days=offset)
            values = {row['status']: row['total'] for row in db.execute('SELECT status,count(*) AS total FROM runs WHERE created_at>=? AND created_at<? GROUP BY status', (day.timestamp(), (day + dt.timedelta(days=1)).timestamp()))}
            daily.append({'date': day.date().isoformat(), 'counts': values})
        total = db.execute('SELECT count(*) FROM runs').fetchone()[0]
        execution_count = db.execute("SELECT count(*) FROM runs WHERE kind='execution'").fetchone()[0]
    metadata = store.get_meta('collector', {})
    work = [task for task in tasks if task['category'] == 'work']
    return {'tasks': tasks, 'collector': metadata, 'now': time.time(), 'timezone': 'Asia/Shanghai',
            'stats': {'tasks': len(work), 'running': sum(task['state'] == 'running' for task in work),
                      'attention': sum(task['state'] in ('attention', 'overdue', 'disabled', 'unknown') for task in work),
                      'today': sum(counts.values()), 'counts': counts, 'total_records': total, 'execution_records': execution_count},
            'daily': daily, 'recent': store.list_runs({'limit': 8, 'status': 'non_skipped'})['items'], 'recording_since': store.get_meta('created_at')}


def log_tail(path):
    """仅由注册表提供路径；读取固定上限的尾部，不接受客户端传入文件路径。"""
    source = Path(path)
    if not source.is_file():
        return {'path': str(source), 'text': '尚无日志文件', 'available': False}
    with source.open('rb') as stream:
        size = source.stat().st_size
        stream.seek(max(0, size - 48000))
        text = stream.read(48000).decode('utf-8', errors='replace')
    return {'path': str(source), 'text': redact(text), 'available': True, 'truncated': size > 48000}


def configuration_snapshot():
    return launchd_config.list_configurations()


def read_json_body(handler):
    content_type = handler.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
    length = int(handler.headers.get('Content-Length', '0'))
    if content_type != 'application/json' or length <= 0 or length > 12 * 1024 * 1024:
        raise ValueError('配置请求格式无效')
    try:
        body = json.loads(handler.rfile.read(length))
    except (ValueError, UnicodeDecodeError):
        raise ValueError('配置 JSON 无效')
    if not isinstance(body, dict):
        raise ValueError('配置内容必须是对象')
    return body


class Handler(BaseHTTPRequestHandler):
    """只读监控接口与受 Origin 保护的本地任务、AI 脚本配置接口。"""

    def log_message(self, _format, *_args):
        pass

    def respond(self, status, body, mime='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        for key, value in {'Content-Type': mime, 'Content-Length': str(len(body)), 'Cache-Control': 'no-store',
                           'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer',
                           'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"}.items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorize_request(self, require_origin=False):
        host = urlparse('//' + self.headers.get('Host', '')).hostname
        if host not in self.server.allowed_hosts:
            self.respond(403, {'error': '不允许的访问主机'})
            return False
        origin = self.headers.get('Origin')
        if require_origin and not origin:
            self.respond(403, {'error': '配置修改仅允许从监控页面提交'})
            return False
        if origin:
            try:
                origin_url = urlparse(origin)
                request_url = urlparse('//' + self.headers.get('Host', ''))
                if origin_url.scheme not in ('http', 'https'):
                    raise ValueError('origin scheme mismatch')
                origin_port = origin_url.port or (443 if origin_url.scheme == 'https' else 80)
                request_port = request_url.port or self.server.server_port
                if origin_url.hostname != request_url.hostname or origin_port != request_port:
                    raise ValueError('origin mismatch')
            except ValueError:
                self.respond(403, {'error': '不允许跨站访问'})
                return False
        return True

    def do_GET(self):
        if not self.authorize_request():
            return
        url = urlparse(self.path)
        path = unquote(url.path)
        try:
            if path == '/api/overview':
                self.respond(200, snapshot())
            elif path == '/api/configuration':
                self.respond(200, configuration_snapshot())
            elif path == '/api/ai-scripts':
                self.respond(200, ai_scripts.list_scripts())
            elif path.startswith('/api/ai-scripts/'):
                script_id = unquote(path[len('/api/ai-scripts/'):])
                self.respond(200, {'id': script_id, **ai_scripts.get(script_id)})
            elif path == '/api/health':
                with store.connect() as db:
                    db.execute('SELECT 1').fetchone()
                state = store.get_meta('collector', {})
                healthy = time.time() - state.get('checked_at', 0) < 60
                self.respond(200 if healthy else 503, {'ok': healthy, 'collector': state.get('checked_at'), 'database': 'ok'})
            elif path == '/api/runs':
                query = parse_qs(url.query)
                filters = {key: query[key][0] for key in ('task_id', 'status', 'kind', 'search') if query.get(key)}
                for key, default, maximum in [('limit', 50, 100), ('offset', 0, 10000000), ('days', 0, 3650)]:
                    value = int(query.get(key, [default])[0])
                    if value < (1 if key == 'limit' else 0) or value > maximum:
                        raise ValueError('分页或日期范围无效')
                    filters[key] = value
                if filters.get('status') and filters['status'] not in ('non_skipped', 'success', 'failed', 'running', 'skipped', 'interrupted', 'unknown'):
                    raise ValueError('执行状态无效')
                if filters.get('kind') and filters['kind'] not in ('history', 'execution'):
                    raise ValueError('记录来源无效')
                if filters['days']:
                    filters['since'] = (dt.datetime.now(ZONE).replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=filters['days'] - 1)).timestamp()
                self.respond(200, store.list_runs(filters))
            elif path.startswith('/api/runs/'):
                record = store.read_run(path.removeprefix('/api/runs/'))
                self.respond(200, record) if record else self.respond(404, {'error': '记录不存在'})
            elif path.startswith('/api/tasks/') and path.endswith('/logs'):
                task_id = path[len('/api/tasks/'):-len('/logs')]
                with store.connect() as db:
                    row = db.execute('SELECT snapshot FROM tasks WHERE id=?', (task_id,)).fetchone()
                if not row:
                    self.respond(404, {'error': '任务不存在'})
                    return
                task = json.loads(row['snapshot'])
                paths = task.get('log_paths', [])
                self.respond(200, {'items': [log_tail(path) for path in dict.fromkeys(paths)]})
            elif path in ('/', '/index.html', '/app.js', '/styles.css', '/favicon.svg'):
                asset = ROOT / 'web' / ('index.html' if path == '/' else path.lstrip('/'))
                mime = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml'}[asset.suffix]
                self.respond(200, asset.read_bytes(), mime)
            else:
                self.respond(404, {'error': '页面不存在'})
        except launchd_config.ConfigurationError as error:
            self.respond(error.status, {'error': str(error)})
        except ValueError as error:
            self.respond(400, {'error': str(error)[:200]})
        except Exception as error:
            print('http_error:', redact(error), flush=True)
            self.respond(500, {'error': '读取暂时失败，请稍后刷新'})

    def configuration_error(self, error):
        if isinstance(error, (launchd_config.ConfigurationError, ai_scripts.ScriptError)):
            self.respond(error.status, {'error': str(error)})
        elif isinstance(error, ValueError):
            self.respond(400, {'error': str(error)[:200]})
        else:
            # 不能把业务参数或环境凭据写入 HTTP 错误/服务日志。
            self.respond(503, {'error': '配置保存失败，请刷新并检查本机调度器状态'})

    def do_POST(self):
        request_path = urlparse(self.path).path
        if request_path.startswith('/api/ai-scripts/') and request_path.endswith('/test'):
            if not self.authorize_request(require_origin=True):
                return
            try:
                script_id = unquote(request_path[len('/api/ai-scripts/'):-len('/test')])
                self.respond(200, ai_scripts.test(script_id))
            except Exception as error:
                self.configuration_error(error)
            return
        if request_path.startswith('/api/ai-scripts/') and request_path.endswith('/save-output'):
            if not self.authorize_request(require_origin=True):
                return
            try:
                script_id = unquote(request_path[len('/api/ai-scripts/'):-len('/save-output')])
                body = read_json_body(self)
                self.respond(200, ai_scripts.write_tested_script(script_id, body.get('test_id')))
            except Exception as error:
                self.configuration_error(error)
            return
        if request_path == '/api/ai-scripts':
            if not self.authorize_request(require_origin=True):
                return
            try:
                body = read_json_body(self)
                script_id = body.pop('id', '')
                config = ai_scripts.validate(script_id, body)
                existing = store.get_ai_scripts().get(script_id)
                references = [task_id for task_id, task in store.get_task_configs().items()
                             if task.get('ai_script_id') == script_id]
                if existing and references and existing['output_path'] != config['output_path']:
                    raise ai_scripts.ScriptError('任务正在引用该脚本；请先改派任务，再修改脚本路径', 409)
                store.save_ai_script(script_id, config)
                self.respond(201, {'id': script_id, 'ok': True})
            except Exception as error:
                self.configuration_error(error)
            return
        if request_path != '/api/configuration':
            self.respond(405, {'error': '只允许通过本机配置页面管理任务'})
            return
        if not self.authorize_request(require_origin=True):
            return
        try:
            body = read_json_body(self)
            source = body.get('source')
            if source not in ('launchd', 'service'):
                raise ValueError('任务来源必须是 launchd 定时任务或后台服务')
            task_id = 'local.mini-monitor.' + uuid.uuid4().hex[:16]
            self.respond(201, launchd_config.save(task_id, {**body, 'creating': True}, source))
        except Exception as error:
            self.configuration_error(error)

    def do_PUT(self):
        path = unquote(urlparse(self.path).path)
        prefix = '/api/configuration/'
        if not path.startswith(prefix):
            self.respond(405, {'error': '只允许通过本机配置页面管理任务'})
            return
        if not self.authorize_request(require_origin=True):
            return
        task_id = path[len(prefix):]
        try:
            body = read_json_body(self)
            _, definition, _ = launchd_config.locate(task_id)
            source = 'service' if definition.get('MiniMonitorKind') == 'service' or definition.get('KeepAlive') else 'launchd'
            body.pop('creating', None)
            self.respond(200, launchd_config.save(task_id, body, source))
        except Exception as error:
            self.configuration_error(error)

    do_PATCH = do_PUT

    def do_DELETE(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        if path.startswith('/api/ai-scripts/'):
            if not self.authorize_request(require_origin=True):
                return
            try:
                script_id = path[len('/api/ai-scripts/'):]
                if any(task.get('ai_script_id') == script_id for task in store.get_task_configs().values()):
                    raise ai_scripts.ScriptError('任务仍引用该脚本，请先在任务配置中解除引用', 409)
                store.delete_ai_script(script_id)
                self.respond(200, {'ok': True})
            except Exception as error:
                self.configuration_error(error)
            return
        prefix = '/api/configuration/'
        if not path.startswith(prefix):
            self.respond(405, {'error': '只允许通过本机配置页面管理任务'})
            return
        if not self.authorize_request(require_origin=True):
            return
        task_id = path[len(prefix):]
        try:
            revision = parse_qs(url.query).get('revision', [''])[0]
            self.respond(200, launchd_config.remove(task_id, revision))
        except Exception as error:
            self.configuration_error(error)


def serve(options):
    """分别监听回环和显式指定的地址；Tailscale 暂不可用时保留本机访问并重试绑定。"""
    store.initialize()
    stop = threading.Event()
    servers = []
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    collector.collect()
    threading.Thread(target=collector.loop, args=(stop,), daemon=True).start()

    def bind(address):
        while not stop.is_set():
            try:
                server = ThreadingHTTPServer((address, options.port), Handler)
                server.daemon_threads = True
                server.allowed_hosts = {'localhost', '127.0.0.1', socket.gethostname().lower(), address, *options.allowed_host}
                servers.append(server)
                print(f'Task monitor: http://{address}:{options.port} · SQLite: {DB_PATH}', flush=True)
                server.serve_forever(poll_interval=0.5)
                server.server_close()
                return
            except OSError as error:
                print('bind_retry:', address, redact(error), flush=True)
                stop.wait(15)

    for address in dict.fromkeys(options.bind or ['127.0.0.1']):
        threading.Thread(target=bind, args=(address,), daemon=True).start()
    stop.wait()
    for server in servers:
        server.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', action='append')
    parser.add_argument('--allowed-host', action='append', default=[])
    parser.add_argument('--port', type=int, default=8765)
    serve(parser.parse_args())
