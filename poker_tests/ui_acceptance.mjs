import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn, execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';

const directory = fs.mkdtempSync(path.resolve('backups/poker/ui-acceptance-'));
const output = path.resolve('backups/poker/ui-reference'); fs.mkdirSync(output, { recursive: true });
const base = 'http://127.0.0.1:8874';
const service = spawn(path.resolve('poker/.venv-deploy/Scripts/python.exe'), ['-m', 'poker_tests.browser_server', '--data-dir', path.join(directory, 'data')], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
let serverOutput = '';
service.stderr.on('data', chunk => { serverOutput = (serverOutput + chunk).slice(-4000); });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const processes = [];
const pages = [];
async function ready(fn, label, timeout = 15000) { const end = Date.now() + timeout; while (Date.now() < end) { if (await fn()) return; await delay(100); } throw Error('Timed out: ' + label); }
async function observeSockets(page) {
  await page.run(`if (!window.WebSocket.pokerObserved) { window.pokerSockets=[]; const Native=window.WebSocket; window.WebSocket=class extends Native { constructor(...args){super(...args);window.pokerSockets.push(this);} }; window.WebSocket.pokerObserved=true; }`);
}
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
  const a = await browser(0, 1600, 1000);
  await a.call('Page.navigate', { url: base + '/auth/login?identity=111111111111111111' });
  await a.until("!!document.querySelector('.lobby')"); await observeSockets(a);
  await a.click('開新桌'); await a.input('dialog input:not([type=checkbox])', '朋友小聚'); await a.click('確認帶入');
  await a.until("document.querySelector('.connection')?.textContent.includes('此視窗可操作')");
  await a.click('牌桌選項');
  await a.run("document.querySelector('.host-tools').open=true");
  for(let i=0;i<5;i++) { await ready(async()=>{ if(await a.run(`document.querySelectorAll('.seat:not(.empty)').length === ${i+2}`))return true;await a.run("[...document.querySelectorAll('button')].find(b=>b.textContent==='新增固定 NPC'&&!b.disabled)?.click()");return false;},'add NPC'); }
  await a.click('關閉');
  await a.until("!!document.querySelector('.action-buttons button:not(:disabled)')");
  await a.input('input[aria-label="加注至"]', '999999');
  assert(await a.run("document.querySelector('.action-buttons button:last-child').disabled"));
  await a.run("document.querySelector('.pot-presets button:last-child').click()");
  const preset=await a.run("document.querySelector('input[aria-label=\"加注至\"]').value");
  const state=await a.api(); assert(BigInt(preset)<=BigInt(state.hand.legal.max_raise_to));
  await a.input('input[aria-label="加注至"]', state.hand.legal.max_raise_to);
  await a.run("document.querySelector('.action-buttons button:last-child').click()");
  await a.until("document.querySelector('dialog')?.textContent.includes('確認全下')");
  assert.equal((await a.api()).hand.turn, state.hand.turn); await a.click('取消');
  await a.run(`window.audioStarts=[];const NativeAudio=window.AudioContext;window.AudioContext=class extends NativeAudio{createBufferSource(){const s=super.createBufferSource();const start=s.start.bind(s);s.start=(...args)=>{window.audioStarts.push(performance.now());return start(...args)};return s;}};`);
  await a.call('Input.dispatchMouseEvent',{type:'mousePressed',x:20,y:20,button:'left',clickCount:1});
  await a.call('Input.dispatchMouseEvent',{type:'mouseReleased',x:20,y:20,button:'left',clickCount:1});
  await a.run("document.querySelector('.pot-presets button:not(:disabled)').click()");
  await a.until('window.audioStarts.length > 0');
  const decoded=await a.run(`(async()=>{const c=new AudioContext();const durations={};for(const name of ['deal','chips','fold','settle','click','turn','tick','bank']) { const r=await fetch('/assets/audio/'+name+'.ogg'); if(!r.ok)throw Error(name); const b=await c.decodeAudioData(await r.arrayBuffer());durations[name]=b.duration;}await c.close();return durations;})()`);
  await a.run("document.querySelector('[aria-label=\"關閉音效\"]').click()");
  assert.equal(await a.run("localStorage.getItem('poker-muted')"),'true');
  await a.run("document.querySelector('[aria-label=\"開啟音效\"]').click()");
  for (const theme of ['classic_walnut','midnight_oak','burgundy_leather']) {
    await a.run(`document.documentElement.dataset.theme='${theme}'`); await a.screenshot('desktop-'+theme);
  }
  for (const width of [390,320]) {
    await a.call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:true});
    await a.until('document.documentElement.scrollWidth <= innerWidth');
    await a.screenshot('mobile-'+width);
  }
  assert.deepEqual(a.errors,[]);
  console.log(JSON.stringify({sixSeats:true,illegalRaiseBlocked:true,allInConfirmation:true,presetClamped:true,muteStored:true,actualAudioPlayback:true,audioDurations:decoded,mobileWidths:[390,320],pageErrors:a.errors,output}));
} catch(error) { console.error(error.stack ?? String(error));console.error(serverOutput);for(const page of pages){await page.screenshot('failure').catch(()=>{});console.error(await page.run('document.body.innerText.slice(-1600)').catch(()=>''));}process.exitCode=1; }
finally { for(const page of pages){await page.call('Browser.close').catch(()=>{});page.socket.close();}for(const child of [...processes,service]){try{execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});}catch{}} }
