import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';

const root = process.cwd(), python = path.join(root, 'poker/.venv/Scripts/python.exe');
const recordings = JSON.parse(execFileSync(python, ['-m', 'poker_tests.presentation_fixtures'], { windowsHide: true, encoding: 'utf8' }));
const sweep = JSON.parse(execFileSync(python, ['-m', 'poker_tests.presentation_fixtures', '--sweep'], { windowsHide: true, encoding: 'utf8' }));
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'poker31-'));
const output = path.join(root, 'tmp/issue31-browser'); fs.mkdirSync(output, { recursive: true });
const base = 'http://127.0.0.1:8875';
const processes = [], pages = [];
const service = spawn(python, ['-m', 'poker_tests.browser_server', '--data-dir', path.join(directory, 'data'), '--port', '8875'], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
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
  const port = 19371 + index;
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
  // Browser-only transport fixture: production receives the exact same public JSON shape.
  await call('Page.addScriptToEvaluateOnNewDocument', { source: `
    window.testState = ${JSON.stringify(recordings[0])};
    window.audioStarts = []; window.audioData = new WeakMap(); window.audioBuffers = new WeakMap(); window.commandCount = 0; window.seenWins = []; window.seenFlights = [];
    const NativeFetch = window.fetch;
    window.fetch = async (...args) => {
      const url = String(args[0]);
      if (url.includes('/assets/audio/') && ${slow}) await new Promise(r => setTimeout(r, 1000));
      if (url === '/api/table/commands' && args[1]?.body && JSON.parse(args[1].body).kind === 'act') {
        window.commandCount++; return new Response(JSON.stringify({ result: { accepted: true }, state: window.testState }), { headers: { 'Content-Type':'application/json' } });
      }
      const response = await NativeFetch(...args);
      if (url.includes('/assets/audio/')) {
        const read = response.arrayBuffer.bind(response);
        response.arrayBuffer = async () => { const data = await read(); window.audioData.set(data, url); return data; };
      }
      return response;
    };
    const decode = AudioContext.prototype.decodeAudioData;
    AudioContext.prototype.decodeAudioData = async function(data, ...args) { const name = window.audioData.get(data); const buffer = await decode.call(this, data, ...args); window.audioBuffers.set(buffer, name); return buffer; };
    const create = AudioContext.prototype.createBufferSource;
    AudioContext.prototype.createBufferSource = function() { const source = create.call(this), start = source.start; source.start = function(...args) { window.audioStarts.push({ at: performance.now(), rate: source.playbackRate.value, file: window.audioBuffers.get(source.buffer) }); return start.apply(this,args); }; return source; };
    window.WebSocket = class extends EventTarget {
      static OPEN = 1; readyState = 1;
      constructor() { super(); window.testSocket = this; setTimeout(() => this.onmessage?.({ data: JSON.stringify({type:'ready',connection:'test',state:window.testState}) }), 0); }
      send() {} close() { this.readyState=3; }
    };
    window.feed = (state, type='state') => { window.testState=state; window.testSocket.onmessage({data:JSON.stringify({type,state,connection:'test'})}); };
    window.observe = () => {
      const wins = new WeakSet(), flights = new WeakSet();
      new MutationObserver(() => {
        for (const el of document.querySelectorAll('.winner-badge')) if (!wins.has(el)) { wins.add(el); window.seenWins.push({user:el.closest('[data-player]').dataset.player,text:el.textContent}); }
        for (const el of document.querySelectorAll('.chip-flight')) if (!flights.has(el)) { flights.add(el); window.seenFlights.push({kind:el.className,text:el.textContent,animation:getComputedStyle(el).animationName}); }
      }).observe(document.body,{subtree:true,childList:true});
    };
  ` });
  await call('Page.navigate', { url: base + '/auth/login' });
  await wait("!!document.querySelector('.lobby')");
  const join = await run(`(async()=>{const s=await fetch('/api/table').then(r=>r.json());if(s.joined)return true; const r=await fetch('/api/table/commands',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command_id:crypto.randomUUID(),table_id:'main',version:s.version,kind:'join',amount:'2000',control:null})});return r.ok;})()`);
  assert(join);
  await call('Page.navigate', { url: base });
  await click('返回目前牌桌');
  await wait("document.querySelectorAll('.seat:not(.empty)').length===4");
  await run('window.observe()');
  return page;
}
let version = 10, seq = 0, hand = 0;
function fresh(source = recordings) {
  const suffix = '-' + ++hand, offset = seq;
  const batch = structuredClone(source);
  for (const state of batch) {
    state.version = ++version; state.event_seq += offset; state.server_time = Date.now() / 1000;
    if (state.hand) {
      state.hand.id += suffix; state.hand.deadline = Date.now()/1000 + 20;
      if (state.hand.settlement) for (const pot of state.hand.settlement.pots) pot.id += suffix;
    }
    for (const e of state.events) { e.seq += offset; e.id = state.id + ':' + e.seq; e.at = state.server_time; if(e.hand_id)e.hand_id += suffix; if(e.pot_id)e.pot_id += suffix; }
  }
  seq = batch.at(-1).event_seq; return batch;
}
async function feed(page, state, type = 'state') { await page.run('window.feed(' + JSON.stringify(state) + ',' + JSON.stringify(type) + ')'); }
async function finish(page, batch, winners = 3) {
  for (const state of batch) await feed(page, state);
  await page.wait("document.body.innerText.includes('結算明細')");
  await page.wait("window.seenWins.length>=" + winners);
  const transfers = batch.at(-1).events.filter(e => e.kind === 'payout' || e.kind === 'refund').length;
  await page.wait("window.seenFlights.filter(f=>f.kind.includes('payout')||f.kind.includes('refund')).length>=" + transfers);
  await page.wait("!document.querySelector('.chip-flight')&&!document.querySelector('.winner-badge')");
}
try {
  await until(async () => { try { return (await fetch(base + '/health')).ok; } catch { return false; } }, 'server');
  const page = await browser(0);
  const batch = fresh();
  for (const state of batch.slice(0, -1)) await feed(page, state);
  await page.wait("window.seenFlights.filter(f=>f.kind.includes('action')).length===5&&!document.querySelector('.action-label:not(.empty-label)')");
  await page.run('window.audioStarts=[]');
  await finish(page, [batch.at(-1)]);
  const wins = await page.run('window.seenWins');
  assert.deepEqual(wins.map(w=>w.user).sort(), ['111111111111111111','222222222222222222','333333333333333333']);
  assert.equal(wins.length, 3);
  const flights = await page.run('window.seenFlights');
  assert(flights.some(f => f.kind.includes('collect')));
  assert(flights.some(f => f.kind.includes('refund') && f.text.includes('200')));
  assert(flights.some(f => f.kind.includes('payout') && f.text.includes('404')));
  const combinedAudio = await page.run('window.audioStarts');
  fs.writeFileSync(path.join(output, 'audio-starts.json'), JSON.stringify(combinedAudio, null, 2));
  assert(combinedAudio.some(cue => cue.file?.endsWith('/deal.ogg')), 'combined snapshot must play the board');
  assert(combinedAudio.some(cue => cue.file?.endsWith('/settle.ogg')), 'combined snapshot must play settlement');
  assert(combinedAudio.some(cue => Math.abs(cue.rate - 1.2) < 0.001 && cue.file?.endsWith('/chips.ogg')), 'combined snapshot must play refund');
  await feed(page, batch.at(-1));
  await page.click('結算明細');
  await page.wait("!!document.querySelector('.settlement-details')");
  await page.run("document.querySelector('.settlement-details').open=true");
  assert((await page.run("document.querySelector('.settlement-details').innerText")).includes('合計 1,104'));
  await page.shot('settlement-details');
  await page.click('關閉');
  assert.equal(await page.run('window.seenWins.length'), 3);
  // Every theme and mobile size, including reduced motion.
  await page.click('牌桌選項');
  await page.wait("!!document.querySelector('.sound-settings')");
  await page.run("[...document.querySelectorAll('.sound-settings label')].find(e=>e.textContent.includes('減少動態')).querySelector('input').click()");
  assert(await page.run("document.querySelector('.game').classList.contains('reduced-motion')"));
  const commands = await page.run('window.commandCount');
  await page.run("document.querySelector('[aria-label=試聽牌局籌碼]').click()");
  assert.equal(await page.run('window.commandCount'), commands);
  await page.run("document.querySelector('.sound-settings input[type=checkbox]').click()");
  const mutedAt = await page.run('window.audioStarts.length');
  await page.run("document.querySelector('[aria-label=試聽回合提醒]').click()");
  await page.wait("document.querySelector('.sound-settings [role=status]').textContent.includes('靜音')");
  assert.equal(await page.run('window.audioStarts.length'), mutedAt);
  await page.shot('sound-settings');
  await page.click('關閉');
  for (const width of [1440, 390, 320]) {
    await page.call('Emulation.setDeviceMetricsOverride', { width, height: width > 600 ? 1000 : 900, deviceScaleFactor: 1, mobile: width < 600 });
    for (const theme of ['classic_walnut','midnight_oak','burgundy_leather']) {
      await page.run('document.documentElement.dataset.theme=' + JSON.stringify(theme));
      await page.wait('document.documentElement.scrollWidth<=window.innerWidth+1');
      await page.run('window.seenWins=[];window.seenFlights=[]');
      const live = fresh();
      for (const state of live.slice(0, 3)) await feed(page, state);
      await page.wait("[...document.querySelectorAll('[data-player]')].find(e=>e.dataset.player==='444444444444444444')?.querySelector('.action-label')?.textContent.includes('全下')");
      await page.shot(theme + '-' + width + '-action');
      for (const state of live.slice(3)) await feed(page, state);
      await page.wait("!!document.querySelector('.winner-badge')");
      await page.shot(theme + '-' + width);
      await page.wait("window.seenWins.length>=3");
      await page.wait("!document.querySelector('.winner-badge')&&!document.querySelector('.chip-flight')");
      assert(await page.run("[...document.querySelectorAll('.action-buttons button')].every(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1;})"));
    }
  }
  await page.run('window.seenWins=[];window.seenFlights=[]');
  await finish(page, fresh());
  assert.equal(await page.run('window.audioStarts.length'), mutedAt);
  assert((await page.run('window.seenFlights')).every(f => f.animation === 'none'));
  await page.run('window.seenWins=[];window.seenFlights=[]');
  await finish(page, fresh(sweep), 1);
  assert.equal(await page.run('window.seenWins.length'), 1);
  assert.equal(await page.run("window.seenFlights.filter(f=>f.kind.includes('payout')).length"), 3);
  // Reconnection and visibility rebaseline with a fully settled recording.
  await page.run('window.seenWins=[];window.seenFlights=[]');
  const recovered = fresh();
  await feed(page, recovered.at(-1), 'ready');
  await page.run("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))");
  const background = fresh(); await feed(page, background[1]);
  await page.run("Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'))");
  await feed(page, background.at(-1));
  assert.equal(await page.run('window.seenWins.length'), 0);
  assert.equal(await page.run('window.seenFlights.length'), 0);
  await page.call('Page.reload');
  await page.wait("!!document.querySelector('.lobby') && document.readyState==='complete'");
  await page.click('返回目前牌桌');
  await page.wait("document.querySelector('.game')?.classList.contains('reduced-motion')");
  assert(await page.run("document.querySelector('[aria-label=開啟音效]')!==null"));
  assert.deepEqual(page.errors, []);
  // Separate browser has cold audio buffers, so a slow load can be exercised.
  const slow = await browser(1, true);
  await slow.click('牌桌選項');
  await slow.run("document.querySelector('[aria-label=試聽回合提醒]').click()");
  await slow.wait("document.querySelector('.sound-settings [role=status]').textContent.includes('過慢')");
  assert.equal(await slow.run('window.audioStarts.length'), 0);
  assert.deepEqual(slow.errors, []);
  const report = { publicEngineRecordings: true, combinedBoardSettlementRefundAudio: true, winners: wins, refundOnlyWinnerEffects: false, repeatedMessagesSilent: true, themes: 3, widths:[1440,390,320], reducedMotion:true, mutedPreview:true, accountPreferencesPersist:true, reconnectAndBackgroundSilent:true, slowLoadsExpire:true, pageErrors:[], output };
  fs.writeFileSync(path.join(output,'results.json'), JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
} catch (error) {
  fs.writeFileSync(path.join(output,'failure.txt'), error.stack ?? String(error));
  console.error(error.stack ?? String(error)); console.error(stderr);
  for (let i=0;i<pages.length;i++) { await pages[i].shot('failure-' + i).catch(()=>{}); console.error(await pages[i].run('document.body.innerText.slice(-1800)').catch(()=>'')); }
  process.exitCode = 1;
} finally {
  for (const page of pages) { await page.call('Browser.close').catch(()=>{}); page.socket.close(); }
  for (const child of processes) { try { execFileSync('taskkill', ['/PID',String(child.pid),'/T','/F'], { windowsHide:true, stdio:'ignore' }); } catch {} }
}
