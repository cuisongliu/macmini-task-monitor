"""进程级设置。任务定义由当前用户的 launchd plist 自动发现。"""

import datetime as dt
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('TASK_MONITOR_DATA', ROOT / 'data')).resolve()
DB_PATH = DATA / 'monitor.sqlite3'
ZONE = ZoneInfo('Asia/Shanghai')
AGENTS = Path.home() / 'Library' / 'LaunchAgents'


def redact(value):
    """在入库和 HTTP 输出两处脱敏；不修改原任务的标准输出及原始日志。"""
    text = str(value)
    text = re.sub(r'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----', '[PRIVATE KEY 已隐藏]', text)
    text = re.sub(r'https://(?:open\.)?(?:feishu|larksuite)\.cn/open-apis/bot/[^\s\"\'<>]+', '[飞书 Webhook 已隐藏]', text, flags=re.I)
    text = re.sub(r'(?i)(Bearer\s+)[\w.\-]+', r'\1[REDACTED]', text)
    text = re.sub(r'\b(?:sk-[\w-]{12,}|gh[pousr]_[\w]{15,}|github_pat_[\w]+)\b', '[REDACTED]', text)
    text = re.sub(r'(?i)([\"\']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization)[\"\']?\s*[:=]\s*)[\"\']?[^\s,\"\'}]+[\"\']?', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)([?&](?:key|token|secret|api_key)=)[^&\s]+', r'\1[REDACTED]', text)
    return text


def timestamp(value):
    """接受现有清单里的 ISO 时间或 Unix 秒；缺失时间保持缺失。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return dt.datetime.fromisoformat(str(value)).timestamp()
