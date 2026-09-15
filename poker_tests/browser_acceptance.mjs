import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn, execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';

const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'poker24-'));
const output = path.resolve('tmp/issue24-browser'); fs.mkdirSync(output, { recursive: true });
const base = 'http://127.0.0.1:8874';
const service = spawn(path.resolve('poker/.venv/Scripts/python.exe'), ['-m', 'poker_tests.browser_server', '--data-dir', path.join(directory, 'data')], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
let serverOutput = '';
service.stderr.on('data', chunk => { serverOutput = (serverOutput + chunk).slice(-4000); });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const processes = [];
const pages = [];
async function ready(fn, label, timeout = 15000) { const end = Date.now() + timeout; while (Date.now() < end) { if (await fn()) return; await delay(100); } throw Error('Timed out: ' + label); }
async function browser(index, width = 1440, height = 1100) {
  const port = 19340 + index;
  const child = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--disable-gpu', '--no-first-run', `--remote-debugging-port=${port}`, '--user-data-dir=' + path.join(directory, 'chrome' + index), 'about:blank'], { windowsHide: true, stdio: 'ignore' });
  processes.push(child);
  let list;
  await ready(async () => { try { list = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); return list.some(t => t.type === 'page'); } catch { return false; } }, 'Chrome');
  const socket = new WebSocket(list.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => { socket.onopen = resolve; });
  let seq = 0; const pending = new Map(); const errors = []; const projections = [];
  socket.onmessage = event => {
    const data = JSON.parse(event.data);
    if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text);
    if (data.method === 'Network.webSocketFrameReceived') { try { const msg = JSON.parse(data.params.response.payloadData); if (msg.state) projections.push(msg.state); } catch {} }
    if (data.method === 'Fetch.requestPaused') void call('Fetch.fulfillRequest', { requestId: data.params.requestId, responseCode: 503, body: Buffer.from('{}').toString('base64') });
    if (data.id) { const task = pending.get(data.id); pending.delete(data.id); data.error ? task.reject(data.error) : task.resolve(data.result); }
  };
  const call = (method, params = {}) => new Promise((resolve, reject) => { const id = ++seq; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params })); });
  const run = async expression => { const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text); return result.result.value; };
  const until = expression => ready(() => run(expression), expression);
  const click = async text => { const selector = `[...document.querySelectorAll('button')].find(b => b.textContent === ${JSON.stringify(text)} && !b.disabled)`; await until(`Boolean(${selector})`); await run(`${selector}.click()`); };
  const input = async (selector, value) => { await until(`!!document.querySelector(${JSON.stringify(selector)})`); await run(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, ${JSON.stringify(value)}); e.dispatchEvent(new Event('input', {bubbles:true})); })()`); };
  const api = (url = '/api/table') => run(`fetch(${JSON.stringify(url)}).then(r=>r.json())`);
  const screenshot = async name => fs.writeFileSync(path.join(output, name + '.png'), Buffer.from((await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })).data, 'base64'));
  await call('Runtime.enable'); await call('Network.enable');
  await call('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 600 });
  const page = { call, run, until, click, input, api, screenshot, errors, projections, socket }; pages.push(page); return page;
}
try {
  await ready(async () => { try { return (await fetch(base + '/health')).ok; } catch { return false; } }, 'server');
  const a = await browser(0); const b = await browser(1, 390, 844);
  for (const [page, identity] of [[a, '111111111111111111'], [b, '222222222222222222']]) {
    await page.call('Page.navigate', { url: base + '/auth/login?identity=' + identity });
    await page.until("!!document.querySelector('.lobby')");
  }
  await a.click('開新桌'); await a.input('dialog input:not([type=checkbox])', '週末牌桌'); await a.click('確認帶入');
  await a.until("document.querySelector('.connection')?.textContent.includes('此視窗可操作')");
  await b.until("!!document.querySelector('.room')"); await b.click('帶入並入座'); await b.click('確認帶入');
  await b.until("document.querySelector('.connection')?.textContent.includes('此視窗可操作')");
  await a.until("!!document.querySelector('.action-buttons')");
  const first = await a.api();
  await a.input('input[aria-label="加注至"]', '700');
  await a.run("document.querySelector('.game button').click()");
  await a.until("!!document.querySelector('dialog')");
  for (const [id, name] of [['classic_walnut','典藏胡桃'], ['midnight_oak','墨藍橡木'], ['burgundy_leather','酒紅皮革']]) {
    await a.run(`[...document.querySelectorAll('.theme-option')].find(b=>b.textContent.includes('${name}')).click()`);
    await a.until(`document.documentElement.dataset.theme === '${id}'`);
    assert.equal((await a.api()).hand.id, first.hand.id);
    assert.equal((await a.api()).hand.deadline, first.hand.deadline);
    assert.equal(await a.run("document.querySelector('input[aria-label=\"加注至\"]').value"), '700');
    await a.click('關閉');
    await a.screenshot('desktop-' + id);
    await a.run("document.querySelector('.game button').click()");
    await a.until("!!document.querySelector('dialog')");
  }
  assert.equal(await b.run('document.documentElement.dataset.theme'), 'classic_walnut');
  await a.click('關閉');
  await a.click('全下');
  await a.until("document.querySelector('dialog')?.textContent.includes('確認全下')");
  assert.equal((await a.api()).hand.turn, first.hand.turn);
  await a.click('取消');
  const finished = new Set();
  const end = Date.now() + 70000;
  while (Date.now() < end && finished.size < 3) {
    for (const page of [a, b]) {
      const state = await page.api();
      if (state.hand?.payouts) { finished.add(state.hand.id); continue; }
      await page.run("(() => { const b = [...document.querySelectorAll('button')].find(b => !b.disabled && (b.textContent === '過牌' || b.textContent.startsWith('跟注 '))); if(b) b.click(); })()");
      if (await page.run("!!document.querySelector('dialog')")) await page.click('確認全下');
    }
    await delay(120);
  }
  assert.equal(finished.size, 3, 'three real settled hands');
  await b.screenshot('mobile-classic_walnut');
  await b.run("document.querySelector('.game button').click()");
  for (const [id, name] of [['midnight_oak','墨藍橡木'], ['burgundy_leather','酒紅皮革']]) {
    await b.run(`[...document.querySelectorAll('.theme-option')].find(b=>b.textContent.includes('${name}')).click()`);
    await b.until(`document.documentElement.dataset.theme === '${id}'`);
    await b.click('關閉');
    await b.screenshot('mobile-' + id);
    await b.run("document.querySelector('.game button').click()");
    await b.until("!!document.querySelector('dialog')");
  }
  await b.click('關閉');
  assert.equal(await b.run('document.documentElement.scrollWidth <= innerWidth'), true, 'mobile no horizontal overflow');

  // Failed preference persistence keeps the current display and game connection.
  await a.call('Fetch.enable', { patterns: [{ urlPattern: '*/api/preferences', requestStage: 'Request' }] });
  await a.run("document.querySelector('.game button').click()");
  await a.run("[...document.querySelectorAll('.theme-option')].find(b=>b.textContent.includes('墨藍橡木')).click()");
  await a.until("document.body.innerText.includes('但未儲存')");
  assert.equal(await a.run('document.documentElement.dataset.theme'), 'midnight_oak');
  await a.call('Fetch.disable'); await a.click('關閉');
  // A failed topup is visible and never changes the bankroll.
  const balance = (await a.api('/api/account')).available;
  await a.input('.table-controls input', '100000'); await a.click('申請手後補碼');
  await a.until("document.body.innerText.includes('待補碼') || document.body.innerText.includes('補碼失敗') || !!document.querySelector('[role=alert]')");
  if (await a.run("document.querySelector('[role=alert]')?.textContent.includes('桌況已更新')")) {
    await a.click('申請手後補碼');
    await a.until("document.body.innerText.includes('待補碼') || document.body.innerText.includes('補碼失敗')");
  }
  await ready(async () => {
    for (const page of [a,b]) await page.run("[...document.querySelectorAll('button')].find(b=>b.textContent==='棄牌'&&!b.disabled)?.click()");
    return await a.run("document.body.innerText.includes('補碼失敗')");
  }, 'failed queued topup');
  assert.equal((await a.api('/api/account')).available, balance);
  // A real navigation/reconnect preserves the current hand and deadline.
  await ready(async () => (await a.api()).hand?.payouts === null, 'active hand before reconnect');
  const reconnect = await a.api();
  await a.call('Page.reload'); await a.until("!!document.querySelector('.lobby')");
  await a.click('返回目前牌桌');
  await a.until("document.querySelector('.connection')?.textContent.includes('此視窗可操作')");
  const resumed = await a.api();
  assert.equal(resumed.hand.id, reconnect.hand.id); assert.equal(resumed.hand.deadline, reconnect.hand.deadline);
  // Six occupied seats and visible cards at both 390 and 320 pixels.
  await a.run("document.querySelector('summary').click()");
  for (let count=3; count<=6; count++) {
    await a.click('新增固定 NPC');
    await ready(async () => (await a.api()).members.length === count, 'NPC seat');
  }
  for (const width of [390, 320]) {
    await b.call('Emulation.setDeviceMetricsOverride', { width, height: 844, deviceScaleFactor: 1, mobile: true });
    await b.until("document.querySelectorAll('.seat:not(.empty)').length === 6");
    assert.equal(await b.run(`(() => {
      const cards=document.querySelector('.board .cards').getBoundingClientRect();
      return [...document.querySelectorAll('.seat')].every(e=>{const r=e.getBoundingClientRect();return r.right<=cards.left||r.left>=cards.right||r.bottom<=cards.top||r.top>=cards.bottom;});
    })()`), true, 'seats must not cover board');
    assert.equal(await b.run('document.documentElement.scrollWidth <= innerWidth'), true);
    await b.screenshot('mobile-six-seats-' + width);
  }
  // Close the public table through its real queued command, then create a private table.
  await a.click('手後關桌');
  await ready(async () => {
    for (const page of [a,b]) await page.run("[...document.querySelectorAll('button')].find(b=>b.textContent==='棄牌'&&!b.disabled)?.click()");
    return !(await a.api()).joined;
  }, 'public table closes', 45000);
  for (const page of [a,b]) { await page.click('回到大廳'); await page.until("!!document.querySelector('.lobby')"); }
  await a.click('開新桌'); await a.input('dialog input:not([type=checkbox])', '好友私人桌');
  await a.run("document.querySelector('dialog input[type=checkbox]').click()"); await a.click('確認帶入');
  await a.until("document.querySelector('.connection')?.textContent.includes('此視窗可操作')");
  assert.equal((await b.api('/api/tables')).tables.length, 0);
  await a.run("document.querySelector('summary').click()"); await a.click('私人桌邀請');
  await a.until("!!document.querySelector('dialog input')");
  const oldLink = await a.run("document.querySelector('dialog input').value");
  await a.click('重設邀請'); await a.until(`document.querySelector('dialog input').value !== ${JSON.stringify(oldLink)}`);
  const currentLink = await a.run("document.querySelector('dialog input').value"); await a.click('關閉');
  await b.click('使用私人桌邀請'); await b.input('dialog input[type=url]', oldLink); await b.click('確認帶入');
  await b.until("document.querySelector('[role=alert]')?.textContent.includes('邀請已失效')");
  await b.input('dialog input[type=url]', currentLink); await b.click('確認帶入');
  await b.until("document.querySelector('.connection')?.textContent.includes('此視窗可操作')");
  await a.until("!!document.querySelector('.action-buttons')");
  await a.click('全下'); await a.click('確認全下');
  await b.until("[...document.querySelectorAll('button')].some(b=>b.textContent.startsWith('跟注 ')&&!b.disabled)");
  await b.run("[...document.querySelectorAll('button')].find(b=>b.textContent.startsWith('跟注 ')&&!b.disabled).click()");
  await b.click('確認全下');
  await ready(async () => !!(await a.api()).hand?.payouts, 'all-in settlement');
  const state = await a.api();
  const bankrupt = state.members.find(m=>m.stack==='0');
  if (bankrupt) {
    const page = bankrupt.id === '111111111111111111' ? a : b;
    await page.until("document.body.innerText.includes('重新坐入')");
    await page.click('重新坐入'); await page.until("!!document.querySelector('[role=alert]')");
    await page.input('.table-controls input', '2000'); await page.click('申請手後補碼');
    await ready(async () => (await page.api()).members.find(m=>m.id===bankrupt.id).mode==='active', 'bankrupt player tops up and returns');
  }
  await a.screenshot('private-table');
  for (const [page, identity] of [[a,'111111111111111111'],[b,'222222222222222222']]) {
    assert.deepEqual(page.errors, []);
    for (const state of page.projections) {
      assert.equal('invitation' in state, false);
      if (state.hand) {
        assert.equal('deck' in state.hand, false);
        for (const player of state.hand.players) if (player.id !== identity && !state.hand.payouts) assert.deepEqual(player.cards, []);
      }
    }
  }
  console.log(JSON.stringify({ settledHands: finished.size, independentBrowsers: 2, themes: 3, mobileWidths: [390,320], privateInvitations: 'rotated and old rejected', topupFailure: true, allInConfirmed: true, reconnectPreserved: true, sixSeats: true, horizontalOverflow: false, privateCardsProtected: true, pageErrors: [], output }));
} catch(error) { console.error(String(error)); console.error(serverOutput); for (let i=0;i<pages.length;i++) { await pages[i].screenshot('failure-'+i).catch(()=>{}); console.error(await pages[i].run('document.body.innerText.slice(-2200)').catch(()=>'')); } process.exitCode = 1; }
finally {
  for (const page of pages) { await page.call('Browser.close').catch(()=>{}); page.socket.close(); }
  for (const child of [...processes, service]) { try { execFileSync('taskkill', ['/PID',String(child.pid),'/T','/F'], { windowsHide: true, stdio: 'ignore' }); } catch {} }
}
