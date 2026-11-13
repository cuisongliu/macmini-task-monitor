'use strict';

const paths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  history: '<path d="M3 11a9 9 0 1 1 3 7"/><path d="M3 4v7h7M12 7v5l3 2"/>',
  server: '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M16 6.5h2M16 17.5h2"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 6.1a8 8 0 0 1 13 2.9M4.9 15a8 8 0 0 0 13 2.9"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  radar: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="m12 12 6-6"/><circle cx="12" cy="12" r="1"/>',
  workflow: '<rect x="3" y="8" width="6" height="8" rx="1.5"/><rect x="15" y="2" width="6" height="6" rx="1.5"/><rect x="15" y="16" width="6" height="6" rx="1.5"/><path d="M9 12h3V5h3M12 12v7h3"/>',
  report: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 4 16 4 16 0V5M4 12v7c0 4 16 4 16 0v-7"/>',
  wallet: '<path d="M20 8V5a2 2 0 0 0-2-2H6a3 3 0 0 0-3 3v12a2 2 0 0 0 2 2h15V8H6a2 2 0 0 1-3-2"/><path d="M20 12h-5v4h5M16.5 14h.01"/>',
  arrow: '<path d="m9 5 7 7-7 7"/>', back: '<path d="m15 5-7 7 7 7"/>',
  check: '<path d="m5 12 4 4L19 6"/>', close: '<path d="m6 6 12 12M6 18 18 6"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M7 3v4M17 3v4M8 14h2M14 14h2M8 17h2"/>',
  pulse: '<path d="M2 12h5l3-8 4 16 3-8h5"/>',
  alert: '<path d="m10.3 3.8-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3.2l-8-14a2 2 0 0 0-3.4 0ZM12 9v4M12 17h.01"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.6a8 8 0 0 1-1.6.9l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.6-.9l-1.7.6-1.4-2.4 1.4-1.1a7 7 0 0 1 0-1.9l-1.4-1.1 1.4-2.4 1.7.6a8 8 0 0 1 1.6-.9l.3-1.8h2.8l.3 1.8a8 8 0 0 1 1.6.9l1.7-.6 1.4 2.4-1.4 1.1a7 7 0 0 1 0 1.8Z"/>'
};
const icon = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] ?? paths.clock}</svg>`;
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const labels = { ready: '等待调度', running: '运行中', success: '成功', failed: '失败', skipped: '已跳过', interrupted: '已中断', unknown: '待确认', attention: '需关注', overdue: '记录逾期', disabled: '未加载', stopped: '未运行' };
const badge = (status) => `<span class="badge ${esc(status)}">${esc(labels[status] ?? status)}</span>`;
const number = (value) => value === null || value === undefined ? '—' : new Intl.NumberFormat('en-US').format(value);
const tokens = (value) => value === null || value === undefined ? '未知' : value >= 1000000 ? `${(value / 1000000).toFixed(2).replace(/\.?0+$/, '')}M` : value >= 1000 ? `${(value / 1000).toFixed(2).replace(/\.?0+$/, '')}K` : number(value);
const bytes = (value) => value === null || value === undefined ? '—' : value >= 1073741824 ? `${(value / 1073741824).toFixed(2)} GB` : value >= 1048576 ? `${(value / 1048576).toFixed(1)} MB` : `${number(value)} B`;
const dateFormat = (value, options) => value === null || value === undefined ? '—' : new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false, ...options }).format(new Date(value * 1000));
const dateTime = (value) => dateFormat(value, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
const fullTime = (value) => dateFormat(value, { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
const shortTime = (value) => dateFormat(value, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const duration = (value) => value === null || value === undefined ? '未知' : value < 1 ? '< 1 秒' : value < 60 ? `${value.toFixed(1)} 秒` : value < 3600 ? `${Math.floor(value / 60)} 分 ${Math.floor(value % 60)} 秒` : `${Math.floor(value / 3600)} 小时 ${Math.floor(value % 3600 / 60)} 分`;
const sourceLabel = (run) => run.kind === 'history' ? '历史凭据' : '实时采集';
const taskName = (id) => state.data?.tasks.find((task) => task.id === id)?.name ?? id;
const taskHref = (id) => `#task/${encodeURIComponent(id)}`;
const state = { data: null, route: '', taskSearch: '', filters: { task_id: '', status: 'non_skipped', kind: '', days: '7', search: '' }, offset: 0, history: null, historyTicket: 0, logs: new Map(), shownLogs: new Set(), loading: false, dialogRun: null, configItems: null, aiScripts: [], aiProviders: [], notificationChannels: [], configLoading: false, configError: '' };
const main = document.querySelector('#main');
const dialog = document.querySelector('#run-dialog');
const configDialog = document.querySelector('#config-dialog');
let searchTimer;
let configurationRequest = null;

/** 显示内容转义；launchd 配置保存会应用到真实调度器。 */
async function api(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', signal: AbortSignal.timeout(12000), ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? `请求失败 (${response.status})`);
  return data;
}

function toast(message) {
  const node = document.querySelector('#toast');
  node.textContent = message;
  node.hidden = false;
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => { node.hidden = true; }, 3500);
}

function empty(text) {
  return `<div class="empty">${icon('history')}${esc(text)}</div>`;
}

function heading(title, subtitle, eyebrow = 'MAC MINI / OPERATIONS') {
  return `<div class="page-heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p class="subtitle">${esc(subtitle)}</p></div><div class="date-label">${icon('calendar')}${dateFormat(Date.now() / 1000, { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' })}</div></div>`;
}

function taskRows(tasks) {
  return tasks.map((task) => {
    const last = task.last_run;
    const origin = task.source === 'external' ? '旧版外部登记' : task.instrumented ? 'launchd · 已接入执行记录' : 'launchd · 自动发现';
    return `<tr class="clickable" data-task="${esc(task.id)}"><td><div class="task-name"><span class="task-icon">${icon(task.icon)}</span><a class="task-link" href="${taskHref(task.id)}"><strong>${esc(task.name)}</strong><small>${origin}</small></a></div></td><td>${badge(task.state)}</td><td><span class="schedule-text">${esc(task.schedule.text)}</span><span class="secondary">北京时间</span></td><td class="time">${last ? dateTime(last.created_at) : '暂无记录'}<span class="secondary">${last ? (last.status === 'running' ? '执行中' : labels[last.status]) + ' · ' + sourceLabel(last) : '等待首次采集'}</span></td><td class="time">${task.next_at ? dateTime(task.next_at) : task.state === 'running' ? '当前正在执行' : '由调度器决定'}<span class="secondary">${task.next_at ? task.next_estimated ? '间隔估计' : '计划时间' : ''}</span></td><td class="arrow">${icon('arrow')}</td></tr>`;
  }).join('');
}

function taskTable(tasks) {
  return `<div class="table-wrap"><table class="task-table"><thead><tr><th>任务名称</th><th>当前状态</th><th>执行计划</th><th>最近记录</th><th>下次执行</th><th></th></tr></thead><tbody id="task-rows">${taskRows(tasks)}</tbody></table></div>${tasks.length ? '' : empty('没有匹配的任务')}`;
}

function activityRows(records) {
  return records.slice(0, 5).map((run) => `<div class="activity-row clickable" data-run="${esc(run.id)}" tabindex="0"><span class="activity-status ${esc(run.status)}">${icon(run.status === 'failed' || run.status === 'interrupted' ? 'close' : run.status === 'running' ? 'pulse' : run.status === 'skipped' ? 'clock' : 'check')}</span><div><div class="activity-title">${esc(taskName(run.task_id))} · ${esc(run.summary)}</div><div class="activity-sub">${esc(sourceLabel(run))} · ${run.duration === null ? '耗时未知' : duration(run.duration)}</div></div><span class="activity-time">${shortTime(run.created_at)}</span></div>`).join('') || empty('尚无执行记录');
}

function chart() {
  const days = state.data.daily;
  const totals = days.map((day) => Object.values(day.counts).reduce((sum, count) => sum + count, 0));
  const maximum = Math.max(1, ...totals);
  return `<div class="chart">${days.map((day, index) => {
    const total = totals[index];
    const success = day.counts.success ?? 0;
    const failed = (day.counts.failed ?? 0) + (day.counts.interrupted ?? 0);
    const skipped = total - success - failed;
    return `<div class="chart-col" title="${esc(day.date)}：${total} 条记录，${failed} 条失败或中断"><div class="bar-label">${total || '—'}</div><div class="bar-stack" style="height:${Math.max(2, total / maximum * 115)}px"><div class="bar-success" style="height:${total ? success / total * 100 : 0}%"></div><div class="bar-failed" style="height:${total ? failed / total * 100 : 0}%"></div><div class="bar-skipped" style="height:${total ? skipped / total * 100 : 0}%"></div></div></div>`;
  }).join('')}</div><div class="chart-dates">${days.map((day, index) => `<span>${index === days.length - 1 ? '今天' : esc(day.date.slice(5).replace('-', '/'))}</span>`).join('')}</div><div class="legend"><span><i></i>成功</span><span><i class="fail"></i>失败 / 中断</span><span><i class="skip"></i>跳过 / 其他</span></div><div class="chart-note">历史凭据与接入后的执行记录 · 无记录不代表未执行</div>`;
}

function overview() {
  const data = state.data;
  const stats = data.stats;
  const tasks = data.tasks.filter((task) => task.category === 'work');
  const filtered = tasks.filter((task) => (task.name + task.description).toLowerCase().includes(state.taskSearch.toLowerCase()));
  return `${heading('任务总览', '掌握每一次运行，让定时任务有迹可循。')}
    ${data.collector.errors?.length ? `<div class="notice">部分数据源暂时无法读取：${esc(data.collector.errors.join('；'))}。页面保留已采集记录。</div>` : ''}
    <section class="stats" aria-label="任务概况"><div class="stat"><div class="stat-label">监控任务${icon('grid')}</div><div class="stat-value">${stats.tasks}<small>个任务</small></div><div class="stat-note">${tasks.filter((task) => task.instrumented).length} 个完整记录 · ${tasks.filter((task) => task.source === 'external').length} 个页面登记</div></div><div class="stat"><div class="stat-label">今日记录${icon('history')}</div><div class="stat-value">${number(stats.today)}<small>条</small></div><div class="stat-note">${stats.counts.success ?? 0} 次成功 · ${stats.counts.skipped ?? 0} 次跳过</div></div><div class="stat"><div class="stat-label">正在运行${icon('pulse')}</div><div class="stat-value healthy">${stats.running}<small>个任务</small></div><div class="stat-note">${stats.running ? '任务正在执行中' : '当前等待下一次调度'}</div></div><div class="stat"><div class="stat-label">需要关注${icon('alert')}</div><div class="stat-value ${stats.attention ? 'problem' : 'healthy'}">${stats.attention}<small>个任务</small></div><div class="stat-note">${stats.attention ? '查看异常、逾期或缺失记录' : '任务状态正常'}</div></div></section>
    <section class="panel"><div class="panel-heading"><div><h2>定时任务<span class="count-pill">${tasks.length}</span></h2><p class="panel-description">执行计划、运行状态与最近结果</p></div><label class="search-box">${icon('search')}<input id="task-search" type="search" aria-label="搜索任务" placeholder="搜索任务…" value="${esc(state.taskSearch)}" /></label></div>${taskTable(filtered)}<div class="panel-foot">${icon('info')}点击任务查看详情。间隔任务的下次时间为估计；历史记录保留原有精度。</div></section>
    <div class="lower-grid"><section class="panel"><div class="panel-heading"><div><h2>最近活动</h2><p class="panel-description">最新的执行与结果记录</p></div><a href="#history" class="text-link">全部记录${icon('arrow')}</a></div><div class="activity">${activityRows(data.recent)}</div></section><section class="panel"><div class="panel-heading"><div><h2>运行记录趋势</h2><p class="panel-description">最近 7 天</p></div><span class="count-pill">7 DAYS</span></div>${chart()}</section></div>`;
}

function options(items, selected) {
  return items.map(([value, text]) => `<option value="${esc(value)}"${String(value) === String(selected) ? ' selected' : ''}>${esc(text)}</option>`).join('');
}

function historyFilters(taskId) {
  return `<div class="filters">${taskId ? '' : `<select data-filter="task_id" aria-label="按任务筛选">${options([['', '全部任务'], ...state.data.tasks.map((task) => [task.id, task.name])], state.filters.task_id)}</select>`}<select data-filter="status" aria-label="按执行结果筛选">${options([['non_skipped', '隐藏跳过'], ['', '全部结果'], ...['success', 'failed', 'running', 'skipped', 'interrupted', 'unknown'].map((key) => [key, labels[key]])], state.filters.status)}</select><select data-filter="kind" aria-label="按记录来源筛选">${options([['', '全部来源'], ['execution', '实时采集'], ['history', '历史凭据']], state.filters.kind)}</select><select data-filter="days" aria-label="按时间筛选">${options([['1', '今天'], ['7', '最近 7 天'], ['30', '最近 30 天'], ['0', '全部时间']], state.filters.days)}</select></div>`;
}

function historyPanel(taskId = '') {
  return `<section class="panel"><div class="panel-heading"><div><h2>执行记录</h2><p class="panel-description">默认隐藏跳过记录；可通过结果筛选查看全部</p></div>${historyFilters(taskId)}</div><div id="history-content" aria-live="polite">${empty('正在读取执行记录…')}</div><div class="panel-foot">${icon('info')}历史凭据不是完整执行历史。没有可靠时间的记录显示“未知”，不会补成零耗时。</div></section>`;
}

const notificationTypes = [['feishu_webhook', '飞书自定义机器人'], ['feishu_app', '飞书应用机器人'], ['email', '邮件（SMTP）']];
const notificationEvents = [['success', '成功'], ['failed', '失败'], ['interrupted', '中断'], ['skipped', '跳过']];
function notificationChannel(item = {}, index = 0) {
  const type = item.type ?? 'feishu_webhook';
  const checked = (event) => (item.events ?? ['failed']).includes(event) ? ' checked' : '';
  const secretHint = (key) => item[key + '_configured'] ? '已配置，留空保留' : '请输入';
  return `<fieldset class="notification-channel" data-notification-channel><legend>通知渠道 ${index + 1}</legend><div class="notification-top"><label>渠道名称<input data-field="id" required maxlength="80" value="${esc(item.id ?? '')}" placeholder="例如：值班群"></label><label>通知方式<select data-field="type">${options(notificationTypes, type)}</select></label><label class="config-check"><input data-field="enabled" type="checkbox"${item.enabled === false ? '' : ' checked'}>启用</label><button type="button" class="icon-button" data-notification-test aria-label="测试通知渠道" title="发送测试通知">${icon('pulse')}</button><button type="button" class="icon-button" data-notification-remove aria-label="删除通知渠道" title="删除通知渠道">${icon('close')}</button></div><div class="notification-events"><span class="form-label">触发通知</span>${notificationEvents.map(([value, text]) => `<label><input data-event="${value}" type="checkbox"${checked(value)}> ${text}</label>`).join('')}</div><div data-notification-kind="feishu_webhook"><p class="form-help">飞书群聊：群设置 → 群机器人 → 添加自定义机器人，然后复制 Webhook 地址。</p><label>Webhook 地址<input data-field="webhook_url" type="url" value="" placeholder="${secretHint('webhook_url')}"></label><label>签名密钥（可选）<input data-field="secret" type="password" value="" autocomplete="new-password" placeholder="${secretHint('secret')}"></label></div><div data-notification-kind="feishu_app"><p class="form-help">应用机器人需要飞书开放平台的 App ID、App Secret，并配置发送消息权限。</p><label>App ID<input data-field="app_id" value="${esc(item.app_id ?? '')}" placeholder="cli_xxx"></label><label>App Secret<input data-field="app_secret" type="password" value="" autocomplete="new-password" placeholder="${secretHint('app_secret')}"></label><label>接收方 ID<input data-field="receive_id" value="${esc(item.receive_id ?? '')}" placeholder="用户 open_id 或群 chat_id"></label><label>接收方类型<select data-field="receive_id_type">${options([['open_id', 'open_id'], ['user_id', 'user_id'], ['union_id', 'union_id'], ['email', 'email'], ['chat_id', 'chat_id']], item.receive_id_type ?? 'open_id')}</select></label></div><div data-notification-kind="email"><p class="form-help">填写邮件服务商提供的 SMTP 主机、端口和安全方式；常见服务商通常要求 SSL 或 STARTTLS。</p><label>SMTP 主机<input data-field="smtp_host" value="${esc(item.smtp_host ?? '')}" placeholder="smtp.example.com"></label><div class="form-grid"><label>端口<input data-field="smtp_port" type="number" min="1" max="65535" value="${esc(item.smtp_port ?? 465)}"></label><label>安全方式<select data-field="security">${options([['ssl', 'SSL'], ['starttls', 'STARTTLS'], ['plain', '明文（不推荐）']], item.security ?? 'ssl')}</select></label></div><label>发件人<input data-field="from" type="email" value="${esc(item.from ?? '')}" placeholder="monitor@example.com"></label><label>收件人（多个用逗号分隔）<input data-field="to" value="${esc((item.to ?? []).join(', '))}" placeholder="ops@example.com"></label><label>SMTP 用户名（可选）<input data-field="username" value="${esc(item.username ?? '')}"></label><label>SMTP 密码<input data-field="password" type="password" value="" autocomplete="new-password" placeholder="${secretHint('password')}"></label><label>邮件标题<input data-field="subject" value="${esc(item.subject ?? 'Mac mini 任务通知')}"></label></div></fieldset>`;
}

function updateNotificationKinds(channel) {
  const type = channel.querySelector('[data-field="type"]')?.value;
  channel.querySelectorAll('[data-notification-kind]').forEach((node) => { node.hidden = node.dataset.notificationKind !== type; });
}

function notificationsPage() {
  return `${heading('通知设置', '用表单配置飞书和邮件通知', 'NOTIFICATIONS')}<section class="panel"><form id="notifications-form" class="config-form"><div class="panel-heading"><div><h2>通知渠道</h2><p class="panel-description">选择通知方式和触发事件。凭据不会回显，敏感字段留空会保留已保存值。</p></div><button type="button" class="button" data-notification-add>添加渠道</button></div><div id="notification-channels" class="config-body"><div class="empty">正在读取通知配置…</div></div><p id="notification-error" class="form-error" role="alert" hidden></p><div class="config-actions"><button type="submit" class="button primary">保存通知配置</button></div></form></section>`;
}

async function loadNotifications() {
  try {
    const config = await api('/api/notifications');
    const target = document.querySelector('#notification-channels');
    if (!target) return;
    target.innerHTML = config.channels.length ? config.channels.map(notificationChannel).join('') : '<div class="empty">还没有通知渠道，点击“添加渠道”开始配置。</div>';
    target.querySelectorAll('[data-notification-channel]').forEach(updateNotificationKinds);
  } catch (error) { toast(error.message); }
}

function notificationPayload(form) {
  return [...form.querySelectorAll('[data-notification-channel]')].map((channel) => {
    const value = (name) => channel.querySelector(`[data-field="${name}"]`)?.value ?? '';
    const item = { id: value('id').trim(), type: value('type'), enabled: channel.querySelector('[data-field="enabled"]').checked,
      events: [...channel.querySelectorAll('[data-event]:checked')].map((node) => node.dataset.event) };
    channel.querySelectorAll('[data-field]').forEach((field) => {
      if (field.dataset.field !== 'id' && field.dataset.field !== 'type' && field.dataset.field !== 'enabled') item[field.dataset.field] = field.dataset.field === 'smtp_port' ? Number(field.value) : field.value.trim();
    });
    if (item.type === 'email') item.to = item.to.split(',').map((entry) => entry.trim()).filter(Boolean);
    return item;
  });
}

async function testNotificationChannel(channel) {
  const payload = notificationPayload({ querySelectorAll: () => [channel] });
  const button = channel.querySelector('[data-notification-test]');
  button.disabled = true;
  try {
    await api('/api/notifications/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload[0]) });
    toast('测试通知已发送');
  } catch (error) {
    toast('测试通知失败：' + error.message);
  } finally {
    button.disabled = false;
  }
}

async function saveNotifications(form) {
  const errorNode = form.querySelector('#notification-error');
  try {
    const channels = notificationPayload(form);
    await api('/api/notifications', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channels }) });
    toast('通知配置已保存');
    await loadNotifications();
  } catch (error) {
    errorNode.textContent = error.message;
    errorNode.hidden = false;
  }
}

function runTable(result, taskId) {
  if (!result.items.length) return empty('当前筛选下没有执行记录');
  return `<div class="table-wrap"><table class="task-table"><thead><tr><th>${taskId ? '执行摘要' : '任务 / 执行摘要'}</th><th>结果</th><th>开始 / 记录时间</th><th>耗时</th><th>来源</th><th></th></tr></thead><tbody>${result.items.map((run) => `<tr class="clickable" data-run="${esc(run.id)}" tabindex="0"><td class="summary-cell"><strong style="font-weight:500">${esc(taskId ? run.summary : taskName(run.task_id))}</strong>${taskId ? '' : `<span class="secondary" title="${esc(run.summary)}">${esc(run.summary)}</span>`}</td><td>${badge(run.status)}</td><td class="time">${dateTime(run.created_at)}<span class="secondary">${run.started_at === null ? '原有记录时间' : '开始时间'}</span></td><td class="time">${run.status === 'running' ? '执行中' : duration(run.duration)}</td><td><span class="secondary" style="margin-top:0">${sourceLabel(run)}</span></td><td class="arrow">${icon('arrow')}</td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>共 ${number(result.total)} 条 · 当前 ${result.offset + 1}–${result.offset + result.items.length}</span><div><button class="button" data-page="prev"${result.offset === 0 ? ' disabled' : ''}>上一页</button><button class="button" data-page="next"${result.offset + result.items.length >= result.total ? ' disabled' : ''}>下一页</button></div></div>`;
}

async function loadHistory(taskId = '') {
  const ticket = ++state.historyTicket;
  const filters = { ...state.filters, task_id: taskId || state.filters.task_id, limit: '30', offset: String(state.offset) };
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== ''));
  try {
    const result = await api('/api/runs?' + query);
    if (ticket !== state.historyTicket) return;
    state.history = result;
    const target = document.querySelector('#history-content');
    if (target) target.innerHTML = runTable(result, taskId);
  } catch (error) {
    if (ticket !== state.historyTicket) return;
    const target = document.querySelector('#history-content');
    if (target) target.innerHTML = empty('记录读取失败：' + error.message);
  }
}

function infoRow(label, content, mono = false) {
  return `<div class="info-row"><dt>${esc(label)}</dt><dd${mono ? ' class="mono"' : ''}>${content}</dd></div>`;
}

function renderLogs(taskId) {
  const result = state.logs.get(taskId);
  if (!result) return empty('正在读取日志…');
  return result.items.map((item) => `<div class="log-panel"><div class="log-title">${esc(item.path)}${item.truncated ? ' · 仅显示末尾 48 KB' : ''}</div><pre>${esc(item.text || '日志为空')}</pre></div>`).join('');
}

async function loadLogs(taskId) {
  try {
    const result = await api('/api/tasks/' + encodeURIComponent(taskId) + '/logs');
    state.logs.set(taskId, result);
    const target = document.querySelector('#task-logs');
    if (target && currentTaskId() === taskId) target.innerHTML = renderLogs(taskId);
  } catch (error) {
    toast('日志读取失败：' + error.message);
  }
}

function detail(task) {
  const origin = task.source === 'external' ? '旧版外部登记' : '当前用户的 launchd';
  return `<a href="#overview" class="back-link">${icon('back')}返回任务总览</a><div class="page-heading"><div><div class="detail-heading"><span class="task-icon">${icon(task.icon)}</span><div><div class="eyebrow">TASK DETAILS</div><h1>${esc(task.name)}</h1></div>${badge(task.state)}</div><p class="subtitle detail-description">${esc(task.description || '暂无说明')}</p></div></div><section class="panel"><div class="panel-heading"><h2>任务信息</h2><span class="count-pill">只读快照</span></div><dl class="info-list">${infoRow('任务来源', origin)}${infoRow('执行计划', esc(task.schedule.text) + ' · 北京时间')}${infoRow('下次执行', task.next_at ? fullTime(task.next_at) + (task.next_estimated ? '（估计）' : '（计划）') : '由调度器决定')}${infoRow('记录方式', task.instrumented ? '已接入执行入口 · 开始 / 结束 / 退出码 / 日志' : '当前状态自动采集')}${infoRow('入口脚本', esc(task.script || '未登记'), true)}${infoRow('最近退出码', esc(task.last_exit_code ?? '暂无调度器凭据'))}</dl></section>${historyPanel(task.id)}<section class="panel"><div class="panel-heading"><div><h2>现有日志</h2><p class="panel-description">按需读取已登记日志路径；敏感凭据会隐藏。</p></div><button class="button" data-logs="${esc(task.id)}">${icon('history')}${state.shownLogs.has(task.id) ? '刷新日志' : '查看日志'}</button></div><div class="logs-area" id="task-logs">${state.shownLogs.has(task.id) ? renderLogs(task.id) : '<p class="notes">点击“查看日志”后读取。</p>'}</div></section>`;
}

function services() {
  const items = state.data.collector.services ?? [];
  const tasks = state.data.tasks.filter((task) => task.category === 'system');
  return `${heading('后台服务', '观察常驻服务的运行情况，与业务定时任务分开展示。')}<div class="service-grid">${items.map((service) => `<section class="service-card"><div class="service-top"><h2>${esc(service.name)}</h2>${badge(service.state)}</div><p>${esc(service.description)}</p><div class="service-meta"><span>PID<strong>${service.pid ?? '—'}</strong></span><span>最近退出码<strong>${service.last_exit_code ?? '—'}</strong></span><span>加载<strong>${service.loaded ? '是' : '否'}</strong></span></div><div class="service-actions"><span class="secondary mono">${esc(service.label)}</span></div></section>`).join('')}</div>${tasks.length ? `<h2 class="system-heading">其他系统定时任务</h2><section class="panel">${taskTable(tasks)}</section>` : ''}<p class="notes" style="margin-top:20px">常驻服务的最近退出码是历史退出结果，当前是否运行以进程状态为准。</p>`;
}

function configurationPage() {
  const items = state.configItems ?? [];
  const sourceText = { launchd: 'launchd 定时任务', service: 'launchd 后台服务', external: '旧版登记任务' };
  return `${heading('本机任务', '管理当前用户 launchd 定时任务和后台服务；命令可手动填写，也可选择 AI 脚本。', 'LOCAL / TASKS')}
    <section class="panel"><div class="panel-heading"><div><h2>launchd 配置<span class="count-pill">${items.length}</span></h2><p class="panel-description">保存会备份原定义并应用到 launchd。运行中的任务不会默认被停止。</p></div><div class="management-buttons"><button class="button primary" data-config-create="launchd">新建定时任务</button><button class="button" data-config-create="service">新建后台服务</button><button class="button" data-config-retry>刷新</button><a class="button" href="#ai-scripts">AI 脚本库</a></div></div>
    ${state.configError ? `<div class="notice">${esc(state.configError)} <button class="button" data-config-retry>重试</button></div>` : items.length ? `<div class="table-wrap"><table class="task-table config-table"><thead><tr><th>任务</th><th>来源</th><th>实际状态</th><th>命令 / 执行计划</th><th>管理</th></tr></thead><tbody>${items.map((item) => {
      const execution = item.execution;
      const schedule = execution?.schedule;
      const plan = schedule ? ({ interval: `每 ${schedule.seconds} 秒`, daily: `每天 ${schedule.time}`, weekly: `每周 ${(schedule.weekdays ?? []).map((day) => '日一二三四五六'[day % 7]).join('、')} ${schedule.time}`, manual: '手动或事件触发', calendar: '日历规则', combined: '间隔与日历规则' })[schedule.type] : item.schedule;
      const command = execution ? execution.program || execution.arguments?.[0] : item.script;
      return `<tr><td><strong>${esc(item.name)}</strong><span class="secondary mono">${esc(item.id)}</span></td><td>${sourceText[item.source] ?? esc(item.source)}</td><td><span class="badge ${item.enabled ? 'ready' : 'unknown'}">${item.source === 'external' ? item.enabled ? '展示中' : '已隐藏' : item.enabled ? '已启用' : '已停用 / 未加载'}</span>${item.pid ? `<span class="secondary">运行中 · PID ${item.pid}</span>` : ''}</td><td><span>${esc(plan || (item.source === 'service' ? '常驻服务' : '历史外部调度'))}</span><span class="secondary mono">${esc(command || '未设置命令')}</span></td><td>${item.source === 'external' ? '<span class="secondary">旧登记</span>' : `<button class="button" data-config-edit="${esc(item.id)}">编辑</button>`}${item.managed ? ` <button class="button danger" data-config-delete="${esc(item.id)}">删除</button>` : ''}</td></tr>`;
    }).join('')}</tbody></table></div>` : empty(state.configItems === null ? '正在读取实际任务配置…' : '暂无本机任务，可以在页面新建任务')}
    <div class="panel-foot">${icon('info')}自动发现的系统任务可编辑和停用；删除仅对本页面创建的托管任务开放。启用 RunAtLoad 或 KeepAlive 可能立即启动任务。</div></section>`;
}

function aiScriptsPage() {
  return `${heading('AI 脚本库', '选择 AI 提供商和模型，用提示词生成可复用脚本；任务可引用已保存的脚本。', 'AI / REUSABLE SCRIPTS')}
    <section class="panel"><div class="panel-heading"><div><h2>可复用脚本<span class="count-pill">${state.aiScripts.length}</span></h2><p class="panel-description">测试会执行临时脚本副本并展示输出；临时目录在测试后删除，不会覆盖正式脚本。</p></div><button class="button primary" data-ai-script-create>新建 AI 脚本</button></div>
    ${state.aiScripts.length ? `<div class="table-wrap"><table class="task-table"><thead><tr><th>脚本</th><th>提供商 / 模型</th><th>脚本文件</th><th>管理</th></tr></thead><tbody>${state.aiScripts.map((script) => `<tr><td><strong>${esc(script.name)}</strong><span class="secondary mono">${esc(script.id)}</span></td><td>${esc(script.provider)} · ${esc(script.model)}</td><td class="mono">${esc(script.output_path)}</td><td><button class="button" data-ai-script-edit="${esc(script.id)}">编辑</button> <button class="button" data-ai-script-test="${esc(script.id)}">测试</button> <button class="button danger" data-ai-script-delete="${esc(script.id)}">删除</button></td></tr>`).join('')}</tbody></table></div>` : empty('还没有 AI 脚本')}<div class="panel-foot">将脚本关联到现有任务：<code>python3 taskctl.py use-ai-script &lt;launchd-label&gt; &lt;script-id&gt;</code>；解除关联并恢复原命令：<code>python3 taskctl.py clear-ai-script &lt;launchd-label&gt;</code>。</div></section>`;
}

function editAiScript(script = {}) {
  const providers = state.aiProviders.length ? state.aiProviders : [{ id: 'codex', name: 'Codex', model_hint: 'gpt-6.1-sol' }];
  const defaultProvider = providers[0];
  const item = { id: '', name: '', provider: defaultProvider.id, model: defaultProvider.model_hint, script_type: 'python', prompt: '', output_path: '', max_output_bytes: 1048576, timeout_seconds: 3600, ...script };
  state.scriptTestOutput = null;
  const provider = providers.find((candidate) => candidate.id === item.provider) ?? defaultProvider;
  document.querySelector('#config-content').innerHTML = `<form id="ai-script-form" class="config-form" data-source="ai-script"><div class="dialog-heading"><div><div class="eyebrow">AI SCRIPT / PROVIDER</div><h2 id="config-title">${item.id ? '编辑 AI 脚本' : '新建 AI 脚本'}</h2></div><button type="button" class="icon-button" data-config-close aria-label="关闭">${icon('close')}</button></div><input type="hidden" name="id" value="${esc(item.id)}"><div class="config-body"><label>脚本名称<input name="name" required maxlength="120" value="${esc(item.name)}"></label><label>脚本 ID<input name="script_id" required maxlength="80" pattern="[a-z0-9][a-z0-9._-]{1,79}" value="${esc(item.id)}" placeholder="例如 daily-summary"${item.id ? ' readonly' : ''}></label><label>AI 提供商<select name="provider">${options(providers.map((candidate) => [candidate.id, candidate.name]), item.provider)}</select></label><label>模型名称<input name="model" required value="${esc(item.model)}" placeholder="${esc(provider.model_hint)}"></label><label>生成脚本类型<select name="script_type">${options([['python', 'Python'], ['shell', 'Shell']], item.script_type)}</select></label><label>生成脚本保存路径<input name="output_path" required value="${esc(item.output_path)}" placeholder="/Users/用户名/任务脚本/daily.py"></label><label>提示词<textarea name="prompt" rows="12" required maxlength="100000" placeholder="描述要生成的脚本及其输入、输出、错误处理要求">${esc(item.prompt)}</textarea></label><label>测试命令超时秒数<input name="timeout_seconds" type="number" min="1" max="86400" value="${item.timeout_seconds}"></label><label>最大生成字节数<input name="max_output_bytes" type="number" min="1" max="10485760" value="${item.max_output_bytes}"></label><div class="ai-test-result" id="ai-test-result" hidden></div></div><div class="config-actions"><button type="button" class="button" data-config-close>关闭</button><button type="button" class="button" data-ai-test-current>手动测试</button><button type="button" class="button" data-ai-save-output disabled>写入脚本文件</button><button type="submit" class="button primary">保存配置</button></div></form>`;
  document.querySelector('#config-dialog').showModal();
  document.querySelector('[name=name]').focus();
}

async function loadConfiguration() {
  if (state.configLoading) return configurationRequest;
  state.configLoading = true;
  state.configError = '';
  configurationRequest = (async () => {
    try {
      const result = await api('/api/configuration');
      state.configItems = result.items;
    } catch (error) {
      state.configError = '读取实际配置失败：' + error.message;
      toast(state.configError);
    } finally {
      state.configLoading = false;
      configurationRequest = null;
      if (location.hash === '#configuration') main.innerHTML = configurationPage();
    }
  })();
  return configurationRequest;
}

function argumentRow(value = '') {
  return `<div class="argument-row"><textarea data-argument rows="1" aria-label="命令参数" spellcheck="false">${esc(value)}</textarea><button type="button" class="icon-button" data-argument-remove aria-label="删除此参数">${icon('close')}</button></div>`;
}

function environmentRow(entry = {}) {
  return `<div class="environment-row" data-retained="${entry.retained ? 'true' : 'false'}" data-original-key="${esc(entry.key ?? '')}"><input data-env-key aria-label="环境变量名" value="${esc(entry.key ?? '')}" placeholder="变量名" spellcheck="false"><input type="password" data-env-value aria-label="环境变量值" value="" autocomplete="new-password" placeholder="${entry.retained ? '已设置，留空保留原值' : '变量值'}"><button type="button" class="icon-button" data-env-remove aria-label="删除此环境变量">${icon('close')}</button></div>`;
}

function executionFields(item, source) {
  const execution = item?.execution ?? { program: '', arguments: [''], working_directory: '', environment: [], stdout_path: '', stderr_path: '', run_at_load: false, keep_alive: source === 'service', schedule: { type: source === 'service' ? 'manual' : 'interval', seconds: 3600 } };
  const schedule = execution.schedule;
  const complexKeepAlive = typeof execution.keep_alive === 'object';
  const commandRows = (execution.arguments?.length ? execution.arguments : ['']).map(argumentRow).join('');
  const commandField = `<fieldset><legend>执行脚本</legend><label>选择 AI 脚本（可留空，手动填写下方命令）<select name="ai_script_id" data-ai-script-select>${options([['', '手动输入命令'], ...state.aiScripts.map((script) => [script.id, `${script.name} · ${script.provider} / ${script.model}`])], execution.ai_script_id ?? item?.ai_script_id ?? '')}</select></label><p class="form-help">手动模式直接编辑可执行文件和参数；选择 AI 脚本后使用脚本库中的本机文件。</p><div data-manual-command-fields><div class="form-label">命令参数</div><p class="form-help">每一行是一个参数，第一行为可执行文件绝对路径；保留空格和多行参数。</p><div id="argument-rows">${commandRows}</div><button type="button" class="button" data-argument-add>添加参数</button><label>可执行文件覆盖（Program，可选）<input name="program" value="${esc(execution.program)}" placeholder="留空时使用命令第一项" spellcheck="false"></label><label>工作目录<input name="working_directory" value="${esc(execution.working_directory)}" placeholder="本机绝对目录路径" spellcheck="false"></label></div></fieldset>`;
  return `${commandField}
    <fieldset><legend>实际调度规则</legend><label>调度方式<select name="schedule_type">${options([['interval', '固定间隔'], ['daily', '每天'], ['weekly', '每周 / 工作日'], ['calendar', '自定义日历规则'], ['combined', '间隔与日历共同触发'], ['manual', '手动或事件触发']], schedule.type)}</select></label><label data-schedule-field="interval combined">间隔秒数<input name="interval_seconds" type="number" min="1" max="2147483647" step="1" value="${esc(schedule.seconds ?? 3600)}"></label><label data-schedule-field="daily weekly">本机执行时间<input name="schedule_time" type="time" value="${esc(schedule.time ?? '09:00')}"></label><div class="weekday-choices" data-schedule-field="weekly" role="group" aria-label="执行星期">${[1,2,3,4,5,6,0].map((day) => `<label><input type="checkbox" name="weekday" value="${day}"${(schedule.weekdays ?? [1,2,3,4,5]).includes(day) ? ' checked' : ''}>周${'日一二三四五六'[day]}</label>`).join('')}</div><label data-schedule-field="calendar combined">StartCalendarInterval 日历规则<textarea name="calendar_rules" rows="5" spellcheck="false">${esc(JSON.stringify(schedule.rules ?? [{ Hour: 9, Minute: 0 }], null, 2))}</textarea><span class="form-help">支持 Minute、Hour、Day、Weekday、Month。复杂原规则会完整保留。</span></label><label class="config-check"><input type="checkbox" name="run_at_load"${execution.run_at_load ? ' checked' : ''}>加载时执行一次（RunAtLoad）</label><label>进程保活（KeepAlive）<select name="keep_alive">${options([['false', '关闭，按调度或事件启动'], ['true', '开启，进程退出后自动重新启动'], ...(complexKeepAlive ? [['preserve', '保留现有条件规则']] : [])], complexKeepAlive ? 'preserve' : String(execution.keep_alive))}</select></label></fieldset>
    <fieldset><legend>环境与日志</legend><p class="form-help">已有环境变量不回显值，留空保留；移除一行会删除该变量。</p><div id="environment-rows">${execution.environment.map(environmentRow).join('')}</div><button type="button" class="button" data-env-add>添加环境变量</button><label>标准输出日志（StandardOutPath）<input name="stdout_path" value="${esc(execution.stdout_path)}" placeholder="本机日志绝对路径，可留空" spellcheck="false"></label><label>标准错误日志（StandardErrorPath）<input name="stderr_path" value="${esc(execution.stderr_path)}" placeholder="本机日志绝对路径，可留空" spellcheck="false"></label></fieldset>`;
}

function scheduleVisibility(form) {
  const type = form.elements.schedule_type?.value;
  form.querySelectorAll('[data-schedule-field]').forEach((node) => {
    node.hidden = !node.dataset.scheduleField.split(' ').includes(type);
    node.querySelectorAll('input,textarea').forEach((field) => { field.disabled = node.hidden; });
  });
}

function updateScriptSelection(form) {
  const selected = Boolean(form.elements.ai_script_id?.value);
  const fields = form.querySelector('[data-manual-command-fields]');
  if (fields) {
    fields.classList.toggle('muted-fields', selected);
    fields.querySelectorAll('input,textarea,button').forEach((control) => { control.disabled = selected; });
  }
}

function taskNotificationFields(item) {
  const rule = { enabled: false, channels: [], events: ['failed', 'interrupted'], mode: 'incident', cooldown_seconds: 1800,
    reminder_seconds: 14400, notify_recovery: true, max_per_hour: 3, ...(item?.notification ?? {}) };
  return `<fieldset><legend>任务通知策略</legend><label class="config-check"><input name="notify_enabled" type="checkbox"${rule.enabled ? ' checked' : ''}>为此任务启用通知</label><div data-notify-settings${rule.enabled ? '' : ' hidden'}><p class="form-help">故障首次发生时立即通知；连续故障会合并，持续故障按提醒间隔通知，恢复时发送一次恢复消息。</p><label>通知渠道</label><div class="weekday-choices">${state.notificationChannels.filter((channel) => channel.enabled !== false).map((channel) => `<label><input name="notify_channel" type="checkbox" value="${esc(channel.id)}"${rule.channels.includes(channel.id) ? ' checked' : ''}>${esc(channel.id)}</label>`).join('') || '<span class="form-help">还没有已启用的通知渠道。先到“通知设置”添加并保存渠道。</span>'}</div><div class="weekday-choices" aria-label="通知事件">${notificationEvents.map(([value, label]) => `<label><input name="notify_event" type="checkbox" value="${value}"${rule.events.includes(value) ? ' checked' : ''}>${label}</label>`).join('')}</div><label>通知频率<select name="notify_mode">${options([['incident', '故障合并（推荐）'], ['every_run', '每次匹配运行']], rule.mode)}</select></label><div class="form-grid"><label>重复故障冷却分钟<input name="notify_cooldown" type="number" min="1" max="10080" value="${Math.ceil(rule.cooldown_seconds / 60)}"></label><label>持续故障提醒小时<input name="notify_reminder" type="number" min="1" max="720" value="${Math.ceil(rule.reminder_seconds / 3600)}"></label></div><label class="config-check"><input name="notify_recovery" type="checkbox"${rule.notify_recovery ? ' checked' : ''}>故障恢复后通知一次</label><label>每小时最多通知<input name="notify_max_hour" type="number" min="1" max="20" value="${rule.max_per_hour}"></label><p class="form-help">全局另有每小时 20 条上限；超出会合并抑制，避免通知风暴。</p></div></fieldset>`;
}

function editConfiguration(taskId = '', source = 'launchd') {
  const item = state.configItems?.find((entry) => entry.id === taskId);
  if (taskId && !item) { toast('该任务已变更，请刷新配置列表'); return; }
  if (item?.source === 'external') { toast('旧版外部登记不能修改实际 launchd 配置'); return; }
  source = item?.source ?? source;
  const content = document.querySelector('#config-content');
  content.innerHTML = `<form id="task-config-form" class="config-form" data-source="${source}"><div class="dialog-heading"><div><div class="eyebrow">LAUNCHD CONFIGURATION</div><h2 id="config-title">${item ? '编辑实际任务配置' : source === 'service' ? '新建后台服务' : '新建定时任务'}</h2></div><button type="button" class="icon-button" data-config-close aria-label="关闭">${icon('close')}</button></div><input type="hidden" name="id" value="${esc(item?.id ?? '')}"><input type="hidden" name="revision" value="${esc(item?.revision ?? '')}"><div class="config-body"><label>名称<input name="name" maxlength="120" required value="${esc(item?.name ?? '')}" placeholder="任务名称"></label><label>说明<textarea name="description" maxlength="1000" rows="2">${esc(item?.description ?? '')}</textarea></label>${executionFields(item, source)}${taskNotificationFields(item)}<label class="config-check"><input type="checkbox" name="enabled"${item?.enabled === false ? '' : ' checked'}>启用实际 launchd 任务</label>${item?.pid ? `<div class="notice">当前进程 PID ${item.pid} 正在运行。保存配置不会默认停止它；如确需重启，请明确勾选。<label class="config-check"><input type="checkbox" name="restart_running">允许停止当前进程并重新加载</label></div>` : ''}${item?.definition_path ? `<p class="form-help mono">实际定义：${esc(item.definition_path)}</p>` : ''}<p id="config-error" class="form-error" role="alert" hidden></p></div><div class="panel-foot">保存会备份原定义、修改实际 plist 并重新加载；执行记录不会删除。</div><div class="config-actions"><button type="button" class="button" data-config-close>取消</button><button type="submit" class="button primary">${item ? '保存并应用' : '创建并应用'}</button></div></form>`;
  const form = content.querySelector('form');
  scheduleVisibility(form);
  updateScriptSelection(form);
  configDialog.showModal();
  form.querySelector('[name="name"]').focus();
}

async function openConfigurationForm(taskId = '', source = 'launchd') {
  if (state.aiScriptsLoaded !== true) await loadAiScripts();
  if (!state.notificationChannels.length) {
    try { state.notificationChannels = (await api('/api/notifications')).channels; } catch { state.notificationChannels = []; }
  }
  editConfiguration(taskId, source);
}

async function saveConfiguration(form) {
  const button = form.querySelector('[type="submit"]');
  const errorNode = form.querySelector('#config-error');
  if (button.disabled) return;
  errorNode.hidden = true;
  try {
    const fields = form.elements;
    const id = fields.id.value;
    const source = form.dataset.source;
    const schedule = { type: fields.schedule_type.value };
    if (['interval', 'combined'].includes(schedule.type)) schedule.seconds = Number(fields.interval_seconds.value);
    if (['daily', 'weekly'].includes(schedule.type)) schedule.time = fields.schedule_time.value;
    if (schedule.type === 'weekly') schedule.weekdays = [...form.querySelectorAll('[name="weekday"]:checked')].map((node) => Number(node.value));
    if (['calendar', 'combined'].includes(schedule.type)) {
      try { schedule.rules = JSON.parse(fields.calendar_rules.value); } catch { throw new Error('日历规则不是有效 JSON，请检查格式'); }
    }
    const original = state.configItems?.find((item) => item.id === id);
    const execution = { program: fields.program.value, ai_script_id: fields.ai_script_id.value || '',
      arguments: [...form.querySelectorAll('[data-argument]')].map((node) => node.value), working_directory: fields.working_directory.value,
      stdout_path: fields.stdout_path.value, stderr_path: fields.stderr_path.value,
      environment: [...form.querySelectorAll('.environment-row')].map((row) => ({ key: row.querySelector('[data-env-key]').value,
        value: row.querySelector('[data-env-value]').value, retained: row.dataset.retained === 'true' && row.dataset.originalKey === row.querySelector('[data-env-key]').value })),
      run_at_load: fields.run_at_load.checked, keep_alive: fields.keep_alive.value === 'preserve' ? original?.execution.keep_alive : fields.keep_alive.value === 'true', schedule };
    const notifyEnabled = fields.notify_enabled?.checked ?? false;
    const notification = { enabled: notifyEnabled,
      channels: [...form.querySelectorAll('[name="notify_channel"]:checked')].map((node) => node.value),
      events: [...form.querySelectorAll('[name="notify_event"]:checked')].map((node) => node.value),
      mode: fields.notify_mode?.value ?? 'incident', cooldown_seconds: Number(fields.notify_cooldown?.value ?? 30) * 60,
      reminder_seconds: Number(fields.notify_reminder?.value ?? 4) * 3600, notify_recovery: fields.notify_recovery?.checked ?? true,
      max_per_hour: Number(fields.notify_max_hour?.value ?? 3) };
    const body = { source, name: fields.name.value, description: fields.description.value, enabled: fields.enabled.checked,
      revision: fields.revision.value, restart_running: fields.restart_running?.checked ?? false, execution, notification };
    button.disabled = true;
    button.textContent = id ? '正在应用…' : '正在创建…';
    const result = await api('/api/configuration' + (id ? '/' + encodeURIComponent(id) : ''), {
      method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: AbortSignal.timeout(60000) });
    configDialog.close();
    state.configItems = null;
    await loadConfiguration();
    await refresh();
    toast(result.applied ? '实际配置已应用到 launchd' : '配置已保存');
  } catch (error) {
    errorNode.textContent = error.message;
    errorNode.hidden = false;
    errorNode.scrollIntoView?.({ block: 'nearest' });
  } finally {
    button.disabled = false;
    button.textContent = form.elements.id.value ? '保存并应用' : '创建并应用';
  }
}

async function loadAiScripts() {
  try {
    const result = await api('/api/ai-scripts');
    state.aiScripts = result.items;
    state.aiProviders = result.providers;
    state.aiScriptsLoaded = true;
    if (location.hash === '#ai-scripts') main.innerHTML = aiScriptsPage();
  } catch (error) { toast('AI 脚本读取失败：' + error.message); }
}

function aiScriptPayload(form) {
  const fields = form.elements;
  return { id: fields.script_id.value.trim(), name: fields.name.value.trim(), provider: fields.provider.value,
    model: fields.model.value.trim(), script_type: fields.script_type.value, output_path: fields.output_path.value.trim(),
    prompt: fields.prompt.value, timeout_seconds: Number(fields.timeout_seconds.value),
    max_output_bytes: Number(fields.max_output_bytes.value) };
}

async function saveAiScriptConfig(form) {
  try {
    const result = await api('/api/ai-scripts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(aiScriptPayload(form)) });
    form.elements.id.value = result.id;
    state.aiScriptsLoaded = false;
    await loadAiScripts();
    toast('AI 脚本配置已保存');
    return true;
  } catch (error) { toast('保存 AI 脚本失败：' + error.message); return false; }
}

async function testAiScriptForm(form) {
  if (!await saveAiScriptConfig(form)) return;
  const id = form.elements.id.value;
  const resultNode = form.querySelector('#ai-test-result');
  resultNode.hidden = false;
  const provider = state.aiProviders.find((item) => item.id === form.elements.provider.value);
  resultNode.textContent = `正在运行 ${provider?.name ?? 'AI'} 测试…`;
  const saveButton = form.querySelector('[data-ai-save-output]');
  saveButton.disabled = true;
  try {
    const timeout = (Number(form.elements.timeout_seconds.value) + 30) * 1000;
    const result = await api('/api/ai-scripts/' + encodeURIComponent(id) + '/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', signal: AbortSignal.timeout(timeout) });
    state.scriptTestOutput = result.output;
    state.scriptTestId = result.test_id;
    const executionOutput = result.execution_output || result.execution_stderr || '脚本没有输出';
    const executionSummary = result.execution_exit_code === null || result.execution_exit_code === undefined ? '' : `<div class="execution-result"><strong>脚本执行 · ${result.execution_timed_out ? '超时' : result.execution_exit_code === 0 ? '成功' : '失败'} · 退出码 ${result.execution_exit_code}${result.execution_output_truncated ? ' · 输出超限' : ''}</strong><pre>${esc(executionOutput)}</pre></div>`;
    resultNode.innerHTML = `<strong>${result.ok ? '测试完成' : '测试失败'} · 生成退出码 ${result.generation_exit_code ?? result.exit_code}${result.output_truncated ? ' · 源码超限，不能保存' : ''}</strong>${result.validation_error ? `<p>${esc(result.validation_error)}</p>` : ''}<div class="generated-source"><strong>生成源码</strong><pre>${esc(result.output || '没有生成源码')}</pre></div>${executionSummary}${result.stderr ? `<details><summary>生成阶段标准错误</summary><pre>${esc(result.stderr)}</pre></details>` : ''}`;
    saveButton.disabled = !result.test_id;
  } catch (error) {
    state.scriptTestOutput = null;
    resultNode.textContent = '测试失败：' + error.message;
  }
}

async function saveAiScriptOutput(form) {
  if (!state.scriptTestOutput) return;
  try {
    const id = form.elements.id.value;
    const result = await api('/api/ai-scripts/' + encodeURIComponent(id) + '/save-output', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ test_id: state.scriptTestId }) });
    state.aiScriptsLoaded = false;
    await loadAiScripts();
    toast('脚本已写入 ' + result.path);
  } catch (error) { toast('写入脚本失败：' + error.message); }
}

function currentTaskId() {
  return location.hash.startsWith('#task/') ? decodeURIComponent(location.hash.slice(6)) : '';
}

/** 自动刷新时恢复输入焦点和光标，避免搜索与筛选被刷新打断。 */
function render() {
  if (!state.data) return;
  const focused = document.activeElement;
  const focusId = focused?.id;
  const selection = focused instanceof HTMLInputElement ? [focused.selectionStart, focused.selectionEnd] : null;
  const taskId = currentTaskId();
  const route = taskId ? 'task' : location.hash.slice(1) || 'overview';
  document.querySelectorAll('[data-nav]').forEach((node) => node.classList.toggle('active', node.dataset.nav === (route === 'task' ? 'overview' : route)));
  document.querySelector('#breadcrumb').textContent = route === 'task' ? taskName(taskId) : ({ overview: '任务总览', history: '执行记录', services: '后台服务', configuration: '本机任务', 'ai-scripts': 'AI 脚本', notifications: '通知设置' })[route] ?? '任务总览';
  if (route === 'history') main.innerHTML = heading('执行记录', '每一次运行的结果，都有据可查。', 'MAC MINI / RUN HISTORY') + historyPanel();
  else if (route === 'services') main.innerHTML = services();
  else if (route === 'configuration') { main.innerHTML = configurationPage(); if (state.configItems === null) loadConfiguration(); }
  else if (route === 'ai-scripts') { main.innerHTML = aiScriptsPage(); if (state.aiScriptsLoaded !== true) loadAiScripts(); }
  else if (route === 'notifications') { main.innerHTML = notificationsPage(); loadNotifications(); }
  else if (route === 'task') {
    const task = state.data.tasks.find((item) => item.id === taskId);
    main.innerHTML = task ? detail(task) : heading('任务不存在', '该任务可能已移除，返回总览查看当前任务。') + '<a class="button" href="#overview">返回总览</a>';
  } else main.innerHTML = overview();
  if (route === 'history' || route === 'task') {
    if (state.history && state.route === location.hash) document.querySelector('#history-content')?.replaceChildren();
    loadHistory(taskId);
    if (taskId && state.shownLogs.has(taskId)) loadLogs(taskId);
  }
  state.route = location.hash;
  if (focusId) {
    const replacement = document.getElementById(focusId);
    replacement?.focus({ preventScroll: true });
    if (selection && replacement instanceof HTMLInputElement) replacement.setSelectionRange(...selection);
  }
}

async function refresh(manual = false) {
  if (state.loading) return;
  state.loading = true;
  const button = document.querySelector('#refresh');
  button.disabled = true;
  try {
    state.data = await api('/api/overview');
    const checked = state.data.collector.checked_at;
    const stale = Date.now() / 1000 - (checked ?? 0) > 60;
    const status = document.querySelector('#sync-status');
    status.classList.toggle('error', stale);
    status.innerHTML = `<i class="live-dot"></i>${stale ? '采集心跳已延迟' : '已同步 ' + shortTime(checked)}`;
    document.querySelector('#host-name').textContent = state.data.collector.hostname ?? 'Mac mini';
    document.querySelector('#history-count').textContent = number(state.data.stats.total_records);
    document.querySelector('#footer-info').textContent = `${state.data.stats.execution_records} 条实时采集 · 每 15 秒同步`;
    render();
    if (manual) toast('数据已同步');
  } catch (error) {
    const status = document.querySelector('#sync-status');
    status.className = 'error';
    status.innerHTML = '<i class="live-dot"></i>连接暂时中断';
    if (!state.data) main.innerHTML = `<div class="error-page"><h1>暂时无法读取监控数据</h1><p>${esc(error.message)}</p><button class="button" id="retry">重新连接</button></div>`;
    if (manual) toast('同步失败：' + error.message);
  } finally {
    state.loading = false;
    button.disabled = false;
  }
}

async function showRun(id, reopen = true) {
  try {
    const run = await api('/api/runs/' + encodeURIComponent(id));
    state.dialogRun = id;
    document.querySelector('#dialog-content').innerHTML = `<div class="dialog-heading"><div><div class="eyebrow">RUN DETAILS</div><h2 id="dialog-title">${esc(taskName(run.task_id))}</h2></div><button class="icon-button" id="close-dialog" aria-label="关闭详情">${icon('close')}</button></div><div class="dialog-body">${badge(run.status)}<p class="dialog-summary">${esc(run.summary)}</p><dl class="info-list">${infoRow('记录来源', sourceLabel(run))}${infoRow(run.started_at === null ? '记录时间' : '开始时间', fullTime(run.started_at ?? run.created_at))}${infoRow('结束时间', fullTime(run.finished_at))}${infoRow('执行耗时', run.status === 'running' ? '执行中' : duration(run.duration))}${infoRow('退出码', esc(run.exit_code ?? '无原始凭据'))}${Object.entries(run.details).filter(([, value]) => value !== null && value !== undefined).map(([key, value]) => infoRow(key, esc(typeof value === 'boolean' ? value ? '是' : '否' : typeof value === 'object' ? JSON.stringify(value) : value))).join('')}</dl>${run.kind === 'history' ? '<div class="dialog-source">这是已有文件中的历史凭据。缺失的时间与退出码保持未知，不代表零耗时或完整执行历史。</div>' : `<div class="panel-heading" style="padding:18px 0 0"><h2 style="font-size:12px">本次执行日志</h2><button class="button" id="refresh-dialog">${icon('refresh')}刷新记录</button></div><div class="log-panel"><pre>${esc(run.log_tail || (run.status === 'running' ? '任务已开始，等待输出…' : '本次执行没有控制台输出'))}</pre></div><p class="dialog-source">保存脱敏后的末尾 24 KB 日志；原始日志仍位于任务自己的日志文件中。</p>`}</div>`;
    if (reopen && !dialog.open) dialog.showModal();
  } catch (error) {
    toast('记录读取失败：' + error.message);
  }
}

document.querySelectorAll('[data-icon]').forEach((node) => { node.innerHTML = icon(node.dataset.icon); });
document.querySelector('#refresh').addEventListener('click', () => refresh(true));
window.addEventListener('hashchange', () => { state.offset = 0; state.history = null; render(); window.scrollTo(0, 0); });
document.addEventListener('click', (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (target.closest('#retry')) { refresh(true); return; }
  if (target.closest('#close-dialog')) { dialog.close(); return; }
  if (target.closest('#refresh-dialog')) { showRun(state.dialogRun, false); return; }
  if (target.closest('[data-config-close]')) { configDialog.close(); return; }
  if (target.closest('[data-ai-script-create]')) { editAiScript(); return; }
  const scriptEdit = target.closest('[data-ai-script-edit]');
  if (scriptEdit) { api('/api/ai-scripts/' + encodeURIComponent(scriptEdit.dataset.aiScriptEdit)).then(editAiScript).catch((error) => toast(error.message)); return; }
  const scriptTest = target.closest('[data-ai-script-test]');
  if (scriptTest) { api('/api/ai-scripts/' + encodeURIComponent(scriptTest.dataset.aiScriptTest)).then((script) => { editAiScript(script); setTimeout(() => testAiScriptForm(document.querySelector('#ai-script-form')), 0); }).catch((error) => toast(error.message)); return; }
  const scriptDelete = target.closest('[data-ai-script-delete]');
  if (scriptDelete && window.confirm('删除这个 AI 脚本？引用它的任务将无法继续执行。')) { api('/api/ai-scripts/' + encodeURIComponent(scriptDelete.dataset.aiScriptDelete), { method: 'DELETE' }).then(() => { state.aiScriptsLoaded = false; loadAiScripts(); toast('AI 脚本已删除'); }).catch((error) => toast(error.message)); return; }
  if (target.closest('[data-ai-test-current]')) { testAiScriptForm(target.closest('form')); return; }
  if (target.closest('[data-ai-save-output]')) { saveAiScriptOutput(target.closest('form')); return; }
  if (target.closest('[data-notification-add]')) {
    const container = document.querySelector('#notification-channels');
    if (container.querySelector('.empty')) container.innerHTML = '';
    container.insertAdjacentHTML('beforeend', notificationChannel({ type: 'feishu_webhook', enabled: true, events: ['failed'] }, container.querySelectorAll('[data-notification-channel]').length));
    updateNotificationKinds(container.lastElementChild);
    container.lastElementChild.querySelector('[data-field="id"]').focus();
    return;
  }
  if (target.closest('[data-notification-remove]')) {
    target.closest('[data-notification-channel]').remove();
    return;
  }
  if (target.closest('[data-notification-test]')) { testNotificationChannel(target.closest('[data-notification-channel]')); return; }
  if (target.closest('[data-config-retry]')) { state.configItems = null; loadConfiguration(); return; }
  const create = target.closest('[data-config-create]');
  if (create) { openConfigurationForm('', create.dataset.configCreate); return; }
  const edit = target.closest('[data-config-edit]');
  if (edit) { openConfigurationForm(edit.dataset.configEdit); return; }
  const remove = target.closest('[data-config-delete]');
  if (remove) {
    const item = state.configItems?.find((entry) => entry.id === remove.dataset.configDelete);
    if (!item || !window.confirm('删除此页面创建的 launchd 任务并卸载调度？执行历史保留。')) return;
    api('/api/configuration/' + encodeURIComponent(item.id) + '?revision=' + encodeURIComponent(item.revision), { method: 'DELETE' })
      .then(async () => { state.configItems = null; await loadConfiguration(); await refresh(); toast('任务已删除，执行历史保留'); })
      .catch((error) => toast('删除失败：' + error.message));
    return;
  }
  if (target.closest('[data-argument-add]')) { document.querySelector('#argument-rows').insertAdjacentHTML('beforeend', argumentRow()); return; }
  if (target.closest('[data-argument-remove]')) { target.closest('.argument-row').remove(); return; }
  if (target.closest('[data-env-add]')) { document.querySelector('#environment-rows').insertAdjacentHTML('beforeend', environmentRow()); return; }
  if (target.closest('[data-env-remove]')) { target.closest('.environment-row').remove(); return; }
  const run = target.closest('[data-run]');
  if (run) { showRun(run.dataset.run); return; }
  const task = target.closest('[data-task]');
  if (task && !target.closest('a')) { location.hash = taskHref(task.dataset.task).slice(1); return; }
  const logs = target.closest('[data-logs]');
  if (logs) { state.shownLogs.add(logs.dataset.logs); logs.innerHTML = icon('refresh') + '刷新日志'; loadLogs(logs.dataset.logs); return; }
  const page = target.closest('[data-page]');
  if (page && !page.disabled) { state.offset = Math.max(0, state.offset + (page.dataset.page === 'next' ? 30 : -30)); loadHistory(currentTaskId()); }
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && configDialog.open) { configDialog.close(); return; }
  if ((event.key === 'Enter' || event.key === ' ') && event.target instanceof Element && event.target.matches('[data-run]')) {
    event.preventDefault(); showRun(event.target.dataset.run);
  }
});
document.addEventListener('change', (event) => {
  const target = event.target;
  if (target.matches('[data-field="type"]')) updateNotificationKinds(target.closest('[data-notification-channel]'));
  if (target.name === 'notify_enabled') {
    const settings = target.form.querySelector('[data-notify-settings]');
    if (settings) settings.hidden = !target.checked;
  }
  if (target.name === 'schedule_type') scheduleVisibility(target.form);
  if (target.matches('[data-ai-script-select]')) updateScriptSelection(target.form);
  if (target.name === 'provider') {
    const provider = state.aiProviders.find((item) => item.id === target.value);
    if (provider && target.form?.elements.model) target.form.elements.model.placeholder = provider.model_hint;
    if (target.form?.id === 'ai-script-form' && state.scriptTestId) {
      state.scriptTestId = null;
      state.scriptTestOutput = null;
      target.form.querySelector('[data-ai-save-output]').disabled = true;
      target.form.querySelector('#ai-test-result').textContent = '配置已修改，请重新手动测试。';
    }
  }
  if (target instanceof HTMLSelectElement && target.dataset.filter) { state.filters[target.dataset.filter] = target.value; state.offset = 0; loadHistory(currentTaskId()); }
});
document.addEventListener('submit', (event) => {
  if (event.target instanceof HTMLFormElement && event.target.id === 'notifications-form') { event.preventDefault(); saveNotifications(event.target); return; }
  if (event.target instanceof HTMLFormElement && event.target.getAttribute('id') === 'ai-script-form') { event.preventDefault(); saveAiScriptConfig(event.target); return; }
  if (event.target instanceof HTMLFormElement && event.target.getAttribute('id') === 'task-config-form') { event.preventDefault(); saveConfiguration(event.target); return; }
});
document.addEventListener('input', (event) => {
  if (event.target.closest?.('#ai-script-form') && state.scriptTestId) {
    state.scriptTestOutput = null;
    state.scriptTestId = null;
    const save = document.querySelector('[data-ai-save-output]');
    if (save) save.disabled = true;
    const result = document.querySelector('#ai-test-result');
    if (result) result.textContent = '配置已修改，请重新手动测试。';
  }
  if (event.target.id === 'task-search') {
    state.taskSearch = event.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const table = document.querySelector('#task-rows');
      if (table) table.innerHTML = taskRows(state.data.tasks.filter((task) => task.category === 'work' && (task.name + task.description).toLowerCase().includes(state.taskSearch.toLowerCase())));
    }, 120);
  }
});
dialog.addEventListener('click', (event) => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close(); } });
configDialog.addEventListener('click', (event) => { if (event.target === configDialog) { const box = configDialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) configDialog.close(); } });
refresh();
setInterval(() => { if (!document.hidden) refresh(); }, 15000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
