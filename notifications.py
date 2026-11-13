"""通用通知配置与发送层。

配置保存在监控自己的 SQLite 中，凭据只在发送时读取；HTTP 展示始终脱敏。
"""

import json
import os
import smtplib
import ssl
import time
from email.message import EmailMessage

import feishu_notifications

EVENTS = {'success', 'failed', 'interrupted', 'skipped'}
TYPES = {'feishu_webhook', 'feishu_app', 'email'}
SECRET_FIELDS = {'webhook_url', 'secret', 'app_secret', 'password'}
DEFAULT_TASK_RULE = {'enabled': False, 'channels': [], 'events': ['failed', 'interrupted'], 'mode': 'incident',
                     'cooldown_seconds': 1800, 'reminder_seconds': 14400, 'notify_recovery': True, 'max_per_hour': 3}
GLOBAL_MAX_PER_HOUR = 20


class NotificationError(ValueError):
    pass


def validate_task_rule(value=None):
    rule = {**DEFAULT_TASK_RULE, **(value or {})}
    if not isinstance(rule.get('enabled'), bool) or not isinstance(rule.get('notify_recovery'), bool):
        raise NotificationError('任务通知开关必须为布尔值')
    if not isinstance(rule.get('channels'), list) or not all(isinstance(item, str) and item for item in rule['channels']):
        raise NotificationError('任务通知渠道无效')
    if not isinstance(rule.get('events'), list) or not rule['events'] or not set(rule['events']).issubset(EVENTS):
        raise NotificationError('任务通知事件无效')
    if rule.get('mode') not in ('incident', 'every_run'):
        raise NotificationError('任务通知模式无效')
    for field, maximum in (('cooldown_seconds', 604800), ('reminder_seconds', 2592000), ('max_per_hour', 20)):
        try:
            rule[field] = int(rule[field])
        except (TypeError, ValueError):
            raise NotificationError(f'{field} 必须是整数')
        if rule[field] < (1 if field != 'max_per_hour' else 1) or rule[field] > maximum:
            raise NotificationError(f'{field} 超出允许范围')
    return rule


def validate(config, existing=None):
    if not isinstance(config, dict) or not isinstance(config.get('channels'), list):
        raise NotificationError('通知配置必须包含 channels 数组')
    old = {item.get('id'): item for item in (existing or {}).get('channels', []) if isinstance(item, dict)}
    result = []
    for item in config['channels']:
        if not isinstance(item, dict):
            raise NotificationError('通知渠道必须是对象')
        channel = dict(item)
        channel_id = str(channel.get('id', '')).strip()
        kind = channel.get('type')
        if not channel_id or len(channel_id) > 80 or kind not in TYPES:
            raise NotificationError('通知渠道 ID 或类型无效')
        if any(row.get('id') == channel_id for row in result):
            raise NotificationError('通知渠道 ID 不能重复')
        events = channel.get('events', [])
        if not isinstance(events, list) or not events or not set(events).issubset(EVENTS):
            raise NotificationError('通知事件必须是 success、failed、interrupted 或 skipped')
        channel['id'] = channel_id
        channel['enabled'] = bool(channel.get('enabled', True))
        channel['events'] = list(dict.fromkeys(events))
        previous = old.get(channel_id, {})
        for key in SECRET_FIELDS:
            if not channel.get(key) and previous.get(key):
                channel[key] = previous[key]
        if kind == 'feishu_webhook':
            if not channel.get('webhook_url'):
                raise NotificationError(f'渠道 {channel_id} 缺少 Webhook 地址')
            feishu_notifications._check_webhook_url(channel['webhook_url'])
        elif kind == 'feishu_app':
            for key in ('app_id', 'app_secret', 'receive_id'):
                if not channel.get(key):
                    raise NotificationError(f'渠道 {channel_id} 缺少 {key}')
            if channel.get('receive_id_type', 'open_id') not in ('open_id', 'user_id', 'union_id', 'email', 'chat_id'):
                raise NotificationError('飞书接收方类型无效')
            channel['receive_id_type'] = channel.get('receive_id_type', 'open_id')
        else:
            required = ('smtp_host', 'from', 'to')
            if any(not channel.get(key) for key in required) or not isinstance(channel['to'], list) or not channel['to']:
                raise NotificationError(f'渠道 {channel_id} 的邮件配置不完整')
            try:
                channel['smtp_port'] = int(channel.get('smtp_port', 465))
            except (TypeError, ValueError):
                raise NotificationError('SMTP 端口无效')
            if channel['smtp_port'] < 1 or channel['smtp_port'] > 65535:
                raise NotificationError('SMTP 端口无效')
            if channel.get('security', 'ssl') not in ('ssl', 'starttls', 'plain'):
                raise NotificationError('SMTP 安全方式无效')
            channel['security'] = channel.get('security', 'ssl')
        result.append(channel)
    return {'channels': result}


def public(config):
    """返回可供页面编辑的脱敏配置；空敏感字段表示保留原值。"""
    output = {'channels': []}
    for item in (config or {}).get('channels', []):
        row = {key: value for key, value in item.items() if key not in SECRET_FIELDS}
        for key in SECRET_FIELDS:
            if item.get(key):
                row[key] = ''
                row[key + '_configured'] = True
        output['channels'].append(row)
    return output


def send_channel(channel, text, timeout=10):
    kind = channel['type']
    if kind == 'feishu_webhook':
        return feishu_notifications.send_webhook(text, channel['webhook_url'], channel.get('secret', ''), timeout=timeout)
    if kind == 'feishu_app':
        return feishu_notifications.send_app(text, channel['app_id'], channel['app_secret'], channel['receive_id'], channel.get('receive_id_type', 'open_id'), timeout=timeout)
    message = EmailMessage()
    message['Subject'] = channel.get('subject', 'Mac mini 任务通知')
    message['From'] = channel['from']
    message['To'] = ', '.join(channel['to'])
    message.set_content(str(text)[:30000])
    security = channel.get('security', 'ssl')
    if security == 'ssl':
        client = smtplib.SMTP_SSL(channel['smtp_host'], channel.get('smtp_port', 465), timeout=timeout)
    else:
        client = smtplib.SMTP(channel['smtp_host'], channel.get('smtp_port', 587), timeout=timeout)
    try:
        if security == 'starttls':
            client.starttls(context=ssl.create_default_context())
        if channel.get('username'):
            client.login(channel['username'], channel.get('password', ''))
        client.send_message(message)
    finally:
        try:
            client.quit()
        except OSError:
            client.close()
    return True


def send_for_event(config, event, text):
    sent = 0
    errors = []
    for channel in (config or {}).get('channels', []):
        if channel.get('enabled', True) and event in channel.get('events', []):
            try:
                send_channel(channel, text)
                sent += 1
            except Exception as error:
                errors.append(f"{channel.get('id', 'unknown')}: {type(error).__name__}")
    return sent, errors


def notify_task(task_id, rule_value, channel_config, event, summary, now=None):
    """Apply incident merging, reminders, recovery, and durable per-task/global limits."""
    import store

    now = time.time() if now is None else now
    rule = validate_task_rule(rule_value)
    if not rule['enabled']:
        return 0, []
    selected = set(rule['channels'])
    channels = [item for item in (channel_config or {}).get('channels', [])
                if item.get('id') in selected and item.get('enabled', True)]
    state = store.get_notification_state(task_id)
    active = bool(state.get('active'))
    should_send = False
    message_event = event
    if event in ('failed', 'interrupted') and event in rule['events']:
        state['failure_count'] = int(state.get('failure_count', 0)) + 1
        state.setdefault('incident_started_at', now)
        if not active:
            state['active'] = True
            should_send = True
        elif rule['mode'] == 'every_run' and now - state.get('last_sent_at', 0) >= rule['cooldown_seconds']:
            should_send = True
        elif rule['mode'] == 'incident' and now - state.get('last_sent_at', 0) >= rule['reminder_seconds']:
            should_send = True
            message_event = 'reminder'
        else:
            state['suppressed_count'] = int(state.get('suppressed_count', 0)) + 1
    elif event == 'success' and active:
        should_send = bool(rule['notify_recovery'])
        message_event = 'recovered'
        state.update({'active': False, 'recovered_at': now, 'failure_count': 0})
    elif event in rule['events'] and rule['mode'] == 'every_run':
        should_send = True
    if not should_send:
        store.save_notification_state(task_id, state)
        return 0, []

    message = f'任务通知\n任务：{task_id}\n事件：{message_event}\n摘要：{summary}'
    if message_event == 'reminder':
        message += f"\n已连续故障 {state.get('failure_count', 1)} 次"
    if message_event == 'recovered' and state.get('suppressed_count'):
        message += f"\n故障期间合并了 {state['suppressed_count']} 次通知"
    sent, errors = 0, []
    for channel in channels:
        if message_event not in ('recovered', 'reminder') and event not in channel.get('events', []):
            continue
        # Recovery/reminder are lifecycle messages for an incident; honor channel's failure subscription.
        if message_event in ('recovered', 'reminder') and not ({'failed', 'interrupted'} & set(channel.get('events', []))):
            continue
        if not store.reserve_notification_delivery(task_id, channel['id'], message_event, now,
                                                   rule['max_per_hour'], GLOBAL_MAX_PER_HOUR):
            state['suppressed_count'] = int(state.get('suppressed_count', 0)) + 1
            continue
        try:
            send_channel(channel, message)
            sent += 1
        except Exception as error:
            errors.append(f"{channel.get('id', 'unknown')}: {type(error).__name__}")
    if sent:
        state['last_sent_at'] = now
    else:
        state['suppressed_count'] = int(state.get('suppressed_count', 0)) + 1
    store.save_notification_state(task_id, state)
    return sent, errors


def environment_config():
    """兼容旧版显式环境变量配置；数据库有配置时由调用方优先使用数据库。"""
    events = [item.strip() for item in os.environ.get('TASK_MONITOR_FEISHU_EVENTS', '').split(',') if item.strip()]
    webhook = os.environ.get('TASK_MONITOR_FEISHU_WEBHOOK', '')
    if webhook:
        return {'channels': [{'id': 'environment-feishu', 'type': 'feishu_webhook', 'enabled': True,
                              'events': events, 'webhook_url': webhook,
                              'secret': os.environ.get('TASK_MONITOR_FEISHU_SECRET', '')}]}
    if os.environ.get('TASK_MONITOR_FEISHU_APP_ID'):
        return {'channels': [{'id': 'environment-feishu-app', 'type': 'feishu_app', 'enabled': True,
                              'events': events, 'app_id': os.environ.get('TASK_MONITOR_FEISHU_APP_ID'),
                              'app_secret': os.environ.get('TASK_MONITOR_FEISHU_APP_SECRET', ''),
                              'receive_id': os.environ.get('TASK_MONITOR_FEISHU_RECEIVE_ID', ''),
                              'receive_id_type': os.environ.get('TASK_MONITOR_FEISHU_RECEIVE_ID_TYPE', 'open_id')}]}
    return {'channels': []}
