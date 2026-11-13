"""飞书通知传输。

通知是任务的旁路能力：配置缺失或发送失败都不应改变业务任务结果。
支持自定义机器人 Webhook 和飞书应用机器人 IM API；调用方负责决定何时发送。
"""

import base64
import hashlib
import hmac
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class FeishuError(RuntimeError):
    """可安全显示给本机日志的通知错误。"""


def _json_request(url, payload, headers=None, timeout=10, opener=urlopen):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = Request(url, data=body, headers={
        'Content-Type': 'application/json; charset=utf-8',
        'User-Agent': 'macmini-task-monitor/1',
        **(headers or {}),
    }, method='POST')
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read(1024 * 1024)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise FeishuError(f'飞书请求失败：{type(error).__name__}') from error
    try:
        result = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as error:
        raise FeishuError('飞书响应不是有效 JSON') from error
    if not isinstance(result, dict) or result.get('code', 0) not in (0, None):
        raise FeishuError('飞书接口返回失败')
    return result


def _check_webhook_url(url):
    parsed = urlparse(str(url))
    if parsed.scheme != 'https' or parsed.hostname not in ('open.feishu.cn', 'open.larksuite.com'):
        raise FeishuError('飞书 Webhook 地址无效')
    if '/open-apis/bot/' not in parsed.path:
        raise FeishuError('飞书 Webhook 地址无效')


def send_webhook(text, webhook_url, secret=None, *, timeout=10, opener=urlopen):
    """通过自定义机器人发送文本；secret 存在时按飞书规则签名。"""
    _check_webhook_url(webhook_url)
    payload = {'msg_type': 'text', 'content': {'text': str(text)[:30000]}}
    if secret:
        timestamp = str(int(time.time()))
        digest = hmac.new(f'{timestamp}\n{secret}'.encode('utf-8'), digestmod=hashlib.sha256).digest()
        payload.update({'timestamp': timestamp, 'sign': base64.b64encode(digest).decode('ascii')})
    return _json_request(webhook_url, payload, timeout=timeout, opener=opener)


def _tenant_token(app_id, app_secret, *, timeout=10, opener=urlopen):
    result = _json_request('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                           {'app_id': app_id, 'app_secret': app_secret}, timeout=timeout, opener=opener)
    token = result.get('tenant_access_token')
    if not token:
        raise FeishuError('飞书应用未返回租户令牌')
    return token


def send_app(text, app_id, app_secret, receive_id, receive_id_type='open_id', *, timeout=10, opener=urlopen):
    """通过飞书应用机器人给一个接收方发送文本。"""
    if not all((app_id, app_secret, receive_id)):
        raise FeishuError('飞书应用配置不完整')
    if receive_id_type not in ('open_id', 'user_id', 'union_id', 'email', 'chat_id'):
        raise FeishuError('飞书接收方类型无效')
    token = _tenant_token(app_id, app_secret, timeout=timeout, opener=opener)
    query = urlencode({'receive_id_type': receive_id_type})
    return _json_request('https://open.feishu.cn/open-apis/im/v1/messages?' + query,
                         {'receive_id': receive_id, 'msg_type': 'text', 'content': json.dumps({'text': str(text)[:30000]}, ensure_ascii=False)},
                         headers={'Authorization': 'Bearer ' + token}, timeout=timeout, opener=opener)


def send(text, *, webhook_url='', webhook_secret='', app_id='', app_secret='', receive_id='', receive_id_type='open_id', timeout=10, opener=urlopen):
    """根据配置选择唯一发送通道；没有配置时返回 False。"""
    if webhook_url:
        send_webhook(text, webhook_url, webhook_secret, timeout=timeout, opener=opener)
        return True
    if app_id or app_secret or receive_id:
        send_app(text, app_id, app_secret, receive_id, receive_id_type, timeout=timeout, opener=opener)
        return True
    return False
