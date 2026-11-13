/** 真浏览器 + 真实 Handler/SQLite/plist；launchctl 全部模拟，不连接业务任务。 */
const assert = require('node:assert/strict');
const { spawn, execFileSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');
const session = `mini-config-${process.pid}`;
const screenshotDirectory = path.join(root, '.context');
fs.mkdirSync(screenshotDirectory, { recursive: true });
const chrome = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const browser = (args) => execFileSync('agent-browser', ['--session', session, ...args], { cwd: root, encoding: 'utf8', timeout: 45000, maxBuffer: 4 * 1024 * 1024 });
const evaluate = (code) => browser(['eval', code]);
const wait = (code) => browser(['wait', '--fn', code]);
const fill = (selector, text) => browser(['fill', selector, text]);
const click = (selector) => browser(['click', selector]);
const select = (selector, value) => browser(['select', selector, value]);
const http = spawn(process.env.PYTHON || 'python3', ['tests/ui_server.py'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let stderr = '';
http.stderr.on('data', (value) => { stderr += value; });
const ready = new Promise((resolve, reject) => {
  let output = '';
  const timeout = setTimeout(() => reject(new Error('测试服务未就绪：' + stderr)), 10000);
  http.stdout.on('data', (chunk) => {
    output += chunk;
    if (!output.includes('\n')) return;
    clearTimeout(timeout);
    try { resolve(JSON.parse(output.split('\n')[0]).base); } catch (error) { reject(error); }
  });
  http.on('exit', (code) => { clearTimeout(timeout); if (code) reject(new Error('测试服务退出：' + stderr)); });
});

(async () => {
  try {
    const base = await ready;
    await fetch(base + '/_test/disable-ai-api');
    browser(['--executable-path', chrome, 'open', base + '/#configuration']);
    wait("document.querySelector('#main').textContent.includes('com.example.timer')");
    evaluate("if(!document.querySelector('[data-config-create=launchd]') || !document.querySelector('[data-config-edit]')) throw new Error('launchd 配置页缺少管理入口'); if(!document.body.textContent.includes('手动填写') || !document.body.textContent.includes('AI 脚本')) throw new Error('任务管理说明未显示')");
    evaluate("if(document.querySelector('#main').textContent.includes('读取实际配置失败')) throw new Error('任务列表不应依赖 AI 脚本接口')");
    let state = await (await fetch(base + '/_test/state')).json();
    assert.equal(state.ai_api_requests, 0);
    assert(!state.calls.some((call) => ['bootstrap', 'bootout', 'enable', 'disable'].includes(call[0])));

    // AI 接口暂不可用时仍可创建普通任务，命令逐项手动填写。
    evaluate("document.querySelector('[data-config-create=launchd]').click()");
    wait("document.querySelector('#task-config-form')", 5000);
    fill('[name=name]', '页面手动任务');
    fill('[data-argument]', '/usr/bin/printf');
    evaluate("document.querySelector('[data-argument-add]').click(); document.querySelectorAll('[data-argument]')[1].value='created from page'");
    click('#task-config-form [type=submit]');
    wait("document.querySelector('#main').textContent.includes('页面手动任务')", 5000);
    state = await (await fetch(base + '/_test/state')).json();
    const manualTask = Object.keys(state.configurations).find((id) => state.configurations[id].name === '页面手动任务');
    assert(manualTask);
    let manualDefinition = state.definitions.find((item) => item.Label === manualTask);
    assert.deepEqual(manualDefinition.ProgramArguments, ['/usr/bin/printf', 'created from page']);
    assert(state.calls.some((call) => call[0] === 'bootstrap' && call[2].endsWith(manualTask + '.plist')));

    // 创建的托管任务可以从页面删除，历史记录之外的临时定义不会残留。
    evaluate("window.confirm=()=>true; document.querySelector('[data-config-delete=" + JSON.stringify(manualTask) + "]').click()");
    wait("!document.querySelector('[data-config-delete=" + JSON.stringify(manualTask) + "]')", 5000);
    state = await (await fetch(base + '/_test/state')).json();
    assert(!state.definitions.some((item) => item.Label === manualTask));

    await fetch(base + '/_test/enable-ai-api');
    click('a[href="#ai-scripts"]');
    wait("document.querySelector('[data-ai-script-create]')");
    evaluate("document.querySelector('[data-ai-script-create]').click()");
    wait("document.querySelector('#ai-script-form')", 5000);
    fill('[name=name]', '页面 Codex 脚本');
    fill('[name=script_id]', 'page-codex');
    fill('[name=model]', 'gpt-6.1-sol');
    fill('[name=output_path]', state.ai_output_path);
    fill('[name=prompt]', '只生成测试脚本');
    evaluate("window.__aiTimeouts=[]; const originalTimeout=AbortSignal.timeout.bind(AbortSignal); AbortSignal.timeout=(ms)=>{window.__aiTimeouts.push(ms);return originalTimeout(ms)}");
    click('[data-ai-test-current]');
    wait("document.querySelector('#ai-test-result').textContent.includes('测试完成')");
    evaluate("if(!window.__aiTimeouts.includes(3630000)) throw new Error('AI 测试请求超时未跟随脚本配置')");
    evaluate("if(!document.querySelector('#ai-test-result').textContent.includes('脚本执行 · 成功')) throw new Error('生成脚本未实际执行或未显示执行结果')");
    click('[data-ai-save-output]');
    wait("document.querySelector('#toast').textContent.includes('脚本已写入')");
    state = await (await fetch(base + '/_test/state')).json();
    assert.equal(state.generated_script, "print('generated from prompt')\n");
    browser(['screenshot', path.join(screenshotDirectory, 'ai-script-library.png')]);
    click('[data-config-close]');

    // 已保存的脚本可以在任务表单中直接选择，后端把本机脚本作为入口写入 plist。
    browser(['open', base + '/#configuration']);
    wait("document.querySelector('[data-config-edit=\"com.example.timer\"]')", 5000);
    click('[data-config-edit="com.example.timer"]');
    wait("document.querySelector('#task-config-form')", 5000);
    select('[name=ai_script_id]', 'page-codex');
    browser(['screenshot', path.join(screenshotDirectory, 'task-management.png')]);
    click('#task-config-form [type=submit]');
    wait("document.querySelector('#main').textContent.includes('com.example.timer')", 5000);
    state = await (await fetch(base + '/_test/state')).json();
    let task = state.definitions.find((item) => item.Label === 'com.example.timer');
    assert.deepEqual(task.ProgramArguments, [state.python_path, state.ai_output_path]);
    assert.equal(state.configurations['com.example.timer'].ai_script_id, 'page-codex');
    const cleared = await fetch(base + '/_test/clear-script');
    assert.equal(cleared.status, 200);
    state = await (await fetch(base + '/_test/state')).json();
    task = state.definitions.find((item) => item.Label === 'com.example.timer');
    assert.deepEqual(task.ProgramArguments, ['/usr/bin/printf', '任务参数 with spaces']);
    assert(!state.configurations['com.example.timer'].ai_script_id);
    console.log('PASS 任务页面新建/删除、手动命令和 AI 脚本关联、AI 脚本配置/模拟测试/文件写入、原命令恢复；仅临时 SQLite/plist 和模拟工具。');
  } catch (error) {
    try { console.error(evaluate("JSON.stringify({error:document.querySelector('#config-error')?.textContent,dialog:document.querySelector('#config-dialog')?.open,title:document.querySelector('h1')?.textContent,form:!!document.querySelector('#ai-script-form'),result:document.querySelector('#ai-test-result')?.textContent,toast:document.querySelector('#toast')?.textContent,html:document.querySelector('#main')?.innerText?.slice(0,300)})")); } catch {}
    throw error;
  } finally {
    try { browser(['close']); } catch {}
    http.kill('SIGTERM');
  }
})().catch((error) => { console.error(error.message); process.exitCode = 1; });
