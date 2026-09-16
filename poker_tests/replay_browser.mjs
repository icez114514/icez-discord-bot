import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';

const root = process.cwd(), python = path.join(root, 'poker/.venv/Scripts/python.exe');
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'poker33-'));
const output = path.join(root, 'tmp/issue33-browser'); fs.mkdirSync(output, { recursive: true });
const base = 'http://127.0.0.1:8877';
const processes = [], pages = [];
fs.mkdirSync(path.join(directory, 'data'));
execFileSync(python, ['-m', 'poker_tests.replay_fixtures', path.join(directory, 'data/poker.db')], { windowsHide: true });
const service = spawn(python, ['-m', 'poker_tests.browser_server', '--data-dir', path.join(directory, 'data'), '--port', '8877'], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
processes.push(service);
let stderr = '';
service.stderr.on('data', b => { stderr = (stderr + b).slice(-2000); });
const delay = ms => new Promise(r => setTimeout(r, ms));
async function until(fn, label, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await fn()) return; await delay(40); }
  throw Error('Timed out: ' + label);
}
async function browser(index, slow = false) {
  const port = 19471 + index;
  const child = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--disable-gpu', '--no-first-run', '--remote-debugging-port=' + port, '--user-data-dir=' + path.join(directory, 'chrome' + index), 'about:blank'], { windowsHide: true, stdio: 'ignore' });
  processes.push(child);
  let list;
  await until(async () => { try { list = await (await fetch('http://127.0.0.1:' + port + '/json')).json(); return list.some(t => t.type === 'page'); } catch { return false; } }, 'Chrome');
  const socket = new WebSocket(list.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise(r => { socket.onopen = r; });
  let id = 0; const waiting = new Map(), errors = [];
  socket.onmessage = event => {
    const data = JSON.parse(event.data);
    if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.exception?.description ?? data.params.exceptionDetails.text);
    if (data.id) { const task = waiting.get(data.id); waiting.delete(data.id); data.error ? task.reject(data.error) : task.resolve(data.result); }
  };
  const call = (method, params = {}) => new Promise((resolve, reject) => { const n = ++id; waiting.set(n, { resolve, reject }); socket.send(JSON.stringify({ id: n, method, params })); });
  const run = async expression => {
    const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
    if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text);
    return result.result.value;
  };
  const wait = expr => until(() => run(expr), expr);
  const click = async text => { const selector = "[...document.querySelectorAll('button')].find(b=>b.textContent===" + JSON.stringify(text) + "&&!b.disabled)"; await wait('!!(' + selector + ')'); await run('(' + selector + ').scrollIntoView({block:"center"})'); const rect = await run('(()=>{const r=(' + selector + ').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()'); const hit = await run('(()=>{const e=document.elementFromPoint(' + rect.x + ',' + rect.y + ');return (' + selector + ').contains(e)?null:e?.outerHTML.slice(0,250)??"outside viewport";})()'); if (hit) throw Error('Click blocked: '+text+' by '+hit); await call('Input.dispatchMouseEvent', { type:'mousePressed', button:'left', clickCount:1, ...rect }); await call('Input.dispatchMouseEvent', { type:'mouseReleased', button:'left', clickCount:1, ...rect }); };
  const shot = async name => fs.writeFileSync(path.join(output, name + '.png'), Buffer.from((await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })).data, 'base64'));
  const page = { call, run, wait, click, shot, socket, errors }; pages.push(page);
  await call('Runtime.enable');
  await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await call('Page.addScriptToEvaluateOnNewDocument', { source: `
    window.commandCount=0; window.audioStarts=0; window.lastState=null; window.control=null;
    const nativeFetch=window.fetch;
    window.fetch=(...args)=> { if(String(args[0]).includes('/commands')) window.commandCount++; return nativeFetch(...args); };
    const NativeSocket=window.WebSocket;
    window.WebSocket=class extends NativeSocket { constructor(...args) { super(...args); window.liveSocket=this; this.addEventListener('message', e=> { const m=JSON.parse(e.data); if(m.state) window.lastState=m.state; if(m.connection) window.control=m.connection; }); } };
    const nativeStart=AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start=function(...args) { window.audioStarts++; return nativeStart.apply(this,args); };
  ` });
  return page;
}
const A='111111111111111111', B='222222222222222222', C='333333333333333333';
async function login(page,user) {
  await page.call('Page.navigate',{url:base+'/auth/login?identity='+user});
  await page.wait("document.body?.innerText.includes('上一手摘要與歷史回放')");
}
async function select(page,id) {
  await page.run(`(()=>{const s=document.querySelector('[aria-label="已結束手牌"]');s.value=${JSON.stringify(id)};s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await page.wait(`!document.body?.innerText.includes('正在讀取伺服器歷史')&&document.querySelector('[aria-label="已結束手牌"]').value===${JSON.stringify(id)}`);
}
try {
  await until(async()=>{try{return (await fetch(base+'/health')).ok;}catch{return false;}},'server');
  const page=await browser(0); await login(page,A);
  await page.click('上一手摘要與歷史回放');
  await page.wait("!!document.querySelector('.replay-summary')");
  assert.equal(await page.run("document.querySelector('[aria-label=已結束手牌]').value"),'archive-22');
  await page.run("document.querySelector('.settlement-details').open=true");
  const settlement=await page.run("document.querySelector('.settlement-details').innerText");
  assert(settlement.includes('邊池 1')&&settlement.includes('未跟注退款 2,000')&&settlement.includes('合計 10,000'));
  await page.shot('summary-desktop');
  const commands=await page.run('window.commandCount');
  await page.click('從頭回放');
  await page.wait("document.querySelector('.replay-step').textContent.includes('步驟 1 /')");
  assert.equal(await page.run("document.querySelector('[data-replay-player=\"222222222222222222\"] .cards').querySelectorAll('.back').length"),2);
  await page.click('下一步'); await page.wait("document.querySelector('.replay-step').textContent.includes('步驟 2 /')");
  await page.click('上一步'); await page.wait("document.querySelector('.replay-step').textContent.includes('步驟 1 /')");
  await page.click('翻牌'); assert.equal(await page.run("document.querySelector('.replay-board').querySelectorAll('.card:not(.blank)').length"),3);
  await page.click('轉牌'); assert.equal(await page.run("document.querySelector('.replay-board').querySelectorAll('.card:not(.blank)').length"),4);
  await page.click('河牌'); assert.equal(await page.run("document.querySelector('.replay-board').querySelectorAll('.card:not(.blank)').length"),5);
  assert.equal(await page.run("document.querySelector('[data-replay-player=\"222222222222222222\"] .cards').querySelectorAll('.back').length"),2);
  await page.click('最終結算');
  assert.equal(await page.run("document.querySelector('[data-replay-player=\"222222222222222222\"] .cards').querySelectorAll('.back').length"),0);
  await page.click('從頭回放'); await page.run('window.audioStarts=0');
  await page.click('播放'); await page.wait("!document.querySelector('.replay-step').textContent.includes('步驟 1 /')");
  await page.click('暫停');
  const paused=await page.run("document.querySelector('.replay-step').textContent");
  await delay(1100); // Deliberate observation window: paused playback must not advance.
  assert.equal(await page.run("document.querySelector('.replay-step').textContent"),paused);
  assert.equal(await page.run('window.audioStarts'),0);
  assert.equal(await page.run('window.commandCount'),commands);
  assert.equal(await page.run("document.querySelectorAll('.winner-badge').length"),0);
  for(const width of [390,320]) {
    await page.call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:true});
    assert(await page.run("document.querySelector('dialog').scrollWidth<=document.querySelector('dialog').clientWidth+1"));
    await page.shot('replay-'+width);
  }
  await page.call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await page.click('較舊一頁'); await page.wait("document.querySelector('[aria-label=已結束手牌]')?.value==='archive-02'");
  await select(page,'archive-00'); await page.wait("document.body?.innerText.includes('資料不完整、舊格式')");
  assert.equal(await page.run("document.querySelectorAll('[aria-label=回放控制]').length"),0);
  await page.click('較新一頁'); await page.wait("document.querySelector('[aria-label=已結束手牌]')?.value==='archive-22'");
  await select(page,'archive-21'); await page.click('最終結算');
  assert.equal(await page.run("document.querySelector('[data-replay-player=\"222222222222222222\"] .cards').querySelectorAll('.back').length"),2);
  const outsider=await browser(1); await login(outsider,C);
  assert.equal(await outsider.run("fetch('/api/hands/archive-21').then(r=>r.status)"),404);
  assert.equal(await outsider.run("fetch('/api/hands').then(r=>r.json()).then(d=>d.hands.length)"),1);
  await page.click('返回即時牌桌');
  await page.run("document.querySelector('[aria-label=返回大廳]').click()");
  await page.click('開新桌'); await page.click('確認帶入');
  await page.wait('window.lastState?.control===true');
  const opponent=await browser(2); await login(opponent,B);
  await opponent.click('帶入並入座'); await opponent.click('確認帶入');
  await page.wait('!!window.lastState?.hand?.legal?.fold');
  const deadline=await page.run('window.lastState.hand.deadline');
  await page.click('上一手／回放'); await page.wait("document.querySelector('.replay-live')?.textContent.includes('輪到你行動')");
  assert.equal(await page.run('window.lastState.hand.deadline'),deadline);
  await page.shot('live-turn-reminder');
  await page.click('返回即時牌桌'); await page.wait("!document.querySelector('dialog[open]')");
  await page.click('棄牌');
  await page.wait('!!window.lastState.hand.payouts');
  const liveId=await page.run('window.lastState.hand.id');
  await page.click('上一手／回放');
  await page.wait(`document.querySelector('[aria-label=已結束手牌]')?.value===${JSON.stringify(liveId)}`);
  await page.wait("!!document.querySelector('.replay-summary')");
  // A fresh page cannot have observed any prior WebSocket events, yet reads the durable hand.
  await page.call('Page.reload'); await page.wait("document.body?.innerText.includes('上一手摘要與歷史回放')");
  await page.click('上一手摘要與歷史回放');
  await page.wait(`document.querySelector('[aria-label=已結束手牌]')?.value===${JSON.stringify(liveId)}`);
  await page.wait("!!document.querySelector('.replay-summary')");
  for(const p of pages) assert.deepEqual(p.errors,[]);
  const report={durableOfflineHistory:true,nonparticipantDenied:true,departedParticipants:true,splitPotsAndRefunds:true,foldedCardsPrivate:true,revealTiming:true,steps:true,streetJumps:true,playPause:true,pagination:true,legacyNotice:true,noReplayCommandsOrAudio:true,liveTurnAndDeadline:true,returnToLive:true,reloadHistory:true,widths:[1440,390,320],pageErrors:[],output};
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(report,null,2)); console.log(JSON.stringify(report));
} catch(error) {
  console.error(error.stack??String(error)); console.error(stderr);
  for(let i=0;i<pages.length;i++){ await pages[i].shot('failure-'+i).catch(()=>{}); console.error(await pages[i].run('document.body.innerText.slice(-1800)').catch(()=>'')); }
  process.exitCode=1;
} finally {
  for(const p of pages) { await p.call('Browser.close').catch(()=>{}); p.socket.close(); }
  for(const child of processes) { try { execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'}); }catch{} }
}