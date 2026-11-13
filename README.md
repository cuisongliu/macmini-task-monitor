# Mac mini 任务监控

本机监控网页。Python 标准库提供 HTTP、launchd 采集和 SQLite 记录；静态页面不依赖 CDN 或构建工具。任务页面可以管理当前用户的 launchd 定时任务和后台服务，AI 脚本也可在页面管理。

此仓库仅保存看板源码。运行数据库、日志、缓存和本机凭据不纳入版本控制；任务从当前用户的 launchd 自动发现。页面配置写入项目目录下的 SQLite，不需要编辑 Python 配置文件。

## 位置与入口

- 源码：本项目目录
- 数据库：`data/monitor.sqlite3`（WAL；仅当前用户可读）
- 服务：`com.yjl.macmini-task-monitor`，默认端口 `8765`
- 服务日志：`data/server.log`、`data/server.stderr.log`
- launchd 配置备份：`data/launchd-backups/`，修改前保存原始 plist；运行时配置由 macOS launchd 管理。
- 默认访问：`http://127.0.0.1:8765`。登录后由 LaunchAgent 自动启动。

安装监控服务（不会自动改写任何业务任务）：

```sh
cd /path/to/macmini-task-monitor
python3 install.py --bind 127.0.0.1
```

页面展示并管理自动发现的 launchd 定时任务与后台服务。任务配置可在页面新建、编辑、启用或停用；命令可以逐项手动填写，也可以选择 AI 脚本库中已保存的本机脚本。页面写入受同源 Origin 保护，服务端先校验 revision、备份 plist，再原子写入并重新加载。自动发现的系统任务可以修改和停用，删除仅对页面创建的托管任务开放；任务正在运行时默认拒绝修改，明确选择重启才会停止并重新加载。`taskctl.py` 仍提供安装、迁移、脚本关联和维护操作。

CLI 操作示例：

```sh
python3 taskctl.py list
python3 taskctl.py show com.example.daily-task
python3 taskctl.py use-ai-script com.example.daily-task daily-summary
python3 taskctl.py clear-ai-script com.example.daily-task
python3 taskctl.py delete local.mini-monitor.cli.example --revision REVISION
```

新建任务时把一次性 JSON 从标准输入传给 CLI，不需要把配置写进仓库。JSON 包含 `name`、`description`、`enabled` 和 `execution`；`execution` 至少包含 `program`、`arguments`、`working_directory`、`environment`、`stdout_path`、`stderr_path`、`run_at_load`、`keep_alive` 与 `schedule`。更新时先运行 `show`，在输出里保留 `id` 和 `revision` 再提交。使用 `execution.ai_script_id` 可以在同一份任务定义中关联 AI 脚本；`use-ai-script` / `clear-ai-script` 子命令也可单独切换，并会记录和恢复切换前的命令。

例如：

```sh
python3 taskctl.py apply --source launchd <<'JSON'
{
  "name": "每日摘要",
  "description": "运行本机摘要脚本",
  "enabled": true,
  "execution": {
    "program": "",
    "arguments": ["/usr/bin/python3", "/Users/用户名/scripts/daily.py"],
    "working_directory": "/Users/用户名",
    "environment": [],
    "stdout_path": "/Users/用户名/logs/daily.out",
    "stderr_path": "/Users/用户名/logs/daily.err",
    "run_at_load": false,
    "keep_alive": false,
    "schedule": {"type": "daily", "time": "09:00"}
  }
}
JSON
```

AI 脚本库与普通任务分开管理。脚本配置包含 AI 提供商、模型名、提示词、Python/Shell 类型和目标文件路径。点击“手动测试”会生成脚本源码、检查语法，并在系统临时目录执行副本；临时目录及捕获输出在测试结束后清理，不会覆盖正式文件。只有生成、语法检查和执行都成功且未超限的结果才可写入，服务端校验测试凭据与脚本配置一致后才原子替换目标脚本。普通定时任务或后台服务可以在“使用 AI 脚本”中选择已保存脚本。当前提供商为 Codex；后续增加 CC 时沿用 provider 维度，任务调度和数据库结构无需重做。

可重复添加 `--bind`，例如监听本机和当前 Tailscale 地址。只绑定显式指定的地址；新增域名需 `--allowed-host`。Tailscale 地址启动时不可用会自动重试绑定。

## 记录约定

- 已经通过 `runner.py` 接入的 launchd 任务透传退出码与停止信号。SQLite 不可用时原任务继续执行；通过 `taskctl.py` 修改 launchd 定义会改变实际运行配置。
- 新记录有真实开始/结束/退出码，保存脱敏后的末尾 24 KB 日志。运行中每 5 秒落库。
- 执行记录及总览最近活动默认隐藏“跳过”；结果筛选可选择“全部结果”或“已跳过”。统计仍保留全部记录。
- 结构化结果按任务自身输出解释；明确的空队列或空闲结果可以显示为跳过，缺少可靠结果时不会推断为空。
- 历史凭据可由兼容导入接口写入；缺失时间、退出码或耗时保留为空。
- 每 15 秒采集状态。进程不存在或 PID 已复用的运行记录标为中断，实际结束时间保持未知。
- 业务任务自动发现当前用户 LaunchAgents 中带 `StartInterval` 或 `StartCalendarInterval` 的任务，并展示带 `KeepAlive` 的常驻服务；不读取 root crontab。
- 日历任务显示计划时间；间隔任务根据最近启动时间估计，不能保证休眠、唤醒后的实际时刻。
- SQLite 当前保留全部记录，不自动删除历史。原业务日志仍由原脚本负责维护。

## 飞书通知

runner 支持在任务结束后按状态发送飞书和邮件通知。打开页面的“通知设置”保存渠道即可；配置写入监控自己的 SQLite，读取接口不会返回凭据。每个渠道可单独启用并选择触发状态，未设置触发状态时不发送；通知失败不会改变业务退出码，也不会重试。配置示例：

```text
TASK_MONITOR_FEISHU_EVENTS=failed
[{"id":"feishu","type":"feishu_webhook","enabled":true,"events":["failed"],"webhook_url":"https://open.feishu.cn/open-apis/bot/v2/hook/...","secret":"可选签名密钥"},{"id":"mail","type":"email","enabled":true,"events":["failed"],"smtp_host":"smtp.example.com","smtp_port":465,"security":"ssl","from":"monitor@example.com","to":["ops@example.com"],"username":"monitor","password":"SMTP 密码"}]
```

`events` 支持 `success`、`failed`、`interrupted`、`skipped`，多个状态直接写入数组。自定义机器人可配置签名密钥；传输层只接受飞书官方 HTTPS Webhook 域名。

每个渠道卡片上的测试按钮会立即向该渠道发送一条“Mac mini 任务监控测试通知”，使用当前表单内容但不会保存配置；测试失败会显示接口错误类别或 SMTP/网络错误类型。

飞书应用机器人渠道使用 `type: "feishu_app"`，并填写 `app_id`、`app_secret`、`receive_id`；接收方类型可设为 `open_id`（默认）、`user_id`、`union_id`、`email` 或 `chat_id`。应用需具备获取 tenant_access_token 与发送 IM 消息所需权限，并已能向目标接收方发消息。邮件支持 SMTP SSL、STARTTLS 和明文连接。

通知正文仅包含任务 ID、最终状态和执行摘要，不包含日志。为兼容旧任务，仍支持 `TASK_MONITOR_FEISHU_*` 环境变量；数据库有通知配置时优先使用数据库配置。凭据只保存在本机，诊断输出会脱敏；不要把真实凭据写入代码或提交到仓库。可用本仓库测试验证通知封装，但不要用真实任务验证发送。

任务是否通知在“本机任务”编辑表单中单独设置，默认关闭。推荐使用“故障合并”策略：首次失败或中断立即通知，连续故障按提醒间隔合并，恢复时只通知一次；默认冷却 30 分钟、持续故障提醒 4 小时、单任务每小时最多 3 条。监控全局每小时最多发送 20 条，超出的通知会记录为抑制，避免异常时通知风暴。通知状态和发送记录持久化在本机 SQLite，服务重启不会清空限流状态。

## 维护

局部验证（使用临时 SQLite，不执行真实业务或发送通知）：

```sh
python3 -m unittest discover -s tests -v
node --check web/app.js
```

交互集成检查：`node tests/frontend.cjs`。需要本机 Chrome 和 `agent-browser`；测试启动临时 HTTP 服务、临时 SQLite 和 launchd plist，并用模拟 Codex 与模拟 launchctl 验证任务页面 CRUD、手动命令、AI 脚本保存、测试预览和脚本关联，不连接本机看板或真实任务。

健康检查：`GET /api/health`。只读监控接口包括 `GET /api/overview`、`GET /api/runs`（分页/筛选）、`GET /api/runs/{id}`、`GET /api/tasks/{id}/logs` 和 `GET /api/configuration`；任务配置的写入只接受同源页面的 POST、PUT、DELETE。AI 脚本页面使用同源接口保存 SQLite 配置，并在手动测试成功后写入脚本文件。任务历史不随移除 launchd 定义而删除。每次 launchd 修改会留下带权限限制的 plist 备份，配置或 SQLite 保存失败时会尝试恢复原文件和加载状态。

恢复业务原调度入口（只处理仍由本监控包装的任务，不清空账本）：

```sh
python3 install.py --restore-tasks
```

恢复或安装遇到正在运行的业务时，不要强制停止。安装器会等待；恢复操作需等任务结束后重试。
