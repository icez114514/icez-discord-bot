import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';

const root = process.cwd(), python = path.join(root, 'poker/.venv/Scripts/python.exe');
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'poker32-'));
const output = path.join(root, 'tmp/issue32-browser'); fs.mkdirSync(output, { recursive: true });
const base = 'http://127.0.0.1:8878';
const processes = [], pages = [];
fs.mkdirSync(path.join(directory, 'data'));
execFileSync(python, ['-m', 'poker_tests.replay_fixtures', path.join(directory, 'data/poker.db')], { windowsHide: true });
const service = spawn(python, ['-m', 'poker_tests.browser_server', '--data-dir', path.join(directory, 'data'), '--port', '8878'], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
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
  const port = 19571 + index;
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

const A='111111111111111111', B='222222222222222222';
let version=100;
function state(own=false) {
  return {id:'main',version:++version,joined:true,closed:false,frozen:false,control:true,owner:A,
    rules:{small_blind:'50',big_blind:'100'},event_seq:0,events:[],server_time:Date.now()/1000,
    members:[{id:A,seat:0,mode:'active',stack:'1950',sitout:false,leaving:false,connected:true},{id:B,seat:1,mode:'active',stack:'1900',sitout:false,leaving:false,connected:true}],
    hand:{id:'h1',button:0,players:[{id:A,stack:'1950',bet:'50',paid:'50',cards:['Ac','Kd'],folded:false},{id:B,stack:'1900',bet:'100',paid:'100',cards:[],folded:false}],board:[],street:'preflop',actor:own?0:1,turn:own?4:3,pot:'150',deadline:Date.now()/1000+120,extensions:0,payouts:null,call_amount:'50',legal:own?{fold:true,check:false,call:'50',raise:true,min_raise_to:'200',max_raise_to:'2000'}:{}},
  };
}
async function feed(page,s) { await page.run('window.feed('+JSON.stringify(s)+')'); await page.wait('window.testState.version==='+s.version); await page.run('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true))))'); }
try {
  await until(async()=>{try{return (await fetch(base+'/health')).ok;}catch{return false;}},'server');
  const page=await browser(0);
  await page.call('Page.addScriptToEvaluateOnNewDocument',{source:`
    window.testState=${JSON.stringify(state())};window.commands=[];window.failNext=false;window.holdReady=false;
    const originalFetch=window.fetch;
    window.fetch=async(...args)=>{
      if(String(args[0])==='/api/table/commands') {
        const payload=JSON.parse(args[1].body);window.commands.push(payload);
        if(window.failNext){window.failNext=false;throw Error('response lost');}
        return new Response(JSON.stringify({result:{accepted:true},state:window.testState}),{headers:{'Content-Type':'application/json'}});
      }
      return originalFetch(...args);
    };
    window.WebSocket=class {
      static OPEN=1;readyState=1;
      constructor(){window.testSocket=this;setTimeout(()=>{this.onopen?.();if(!window.holdReady)window.ready();},0);}
      send(){} close(){this.readyState=3;}
    };
    window.ready=()=>window.testSocket.onmessage?.({data:JSON.stringify({type:'ready',connection:'tab',state:window.testState})});
    window.feed=s=>{window.testState=s;window.testSocket.onmessage?.({data:JSON.stringify({type:'state',state:s})});};
    window.drop=code=>{window.testSocket.readyState=3;window.testSocket.onclose?.({code});};
  `});
  await page.call('Page.navigate',{url:base+'/auth/login'});
  await page.wait("!!document.querySelector('.lobby')");
  // Enter through history: live state is supplied by the transport fixture.
  await page.click('上一手摘要與歷史回放');
  await page.run("document.querySelector('dialog button[aria-label=關閉對話框]').click()");
  await page.wait("document.querySelector('.connection')?.textContent.includes('已同步')");
  await page.click('跟注目前顯示金額 50');
  const normal=state();normal.hand.turn=4;await feed(page,normal);
  assert.equal(await page.run('window.commands.length'),0);
  const mine=state(true);mine.hand.turn=5;await feed(page,mine);
  await page.wait('window.commands.length===1');
  assert.equal(await page.run('window.commands[0].action'),'call');
  await feed(page,{...mine,version:++version});
  assert.equal(await page.run('window.commands.length'),1);
  await page.wait("!document.querySelector('.connection').textContent.includes('待確認')");
  await page.click('2.5 BB');
  assert.equal(await page.run("document.querySelector('[aria-label=加注至]').value"),'250');
  assert.equal(await page.run('window.commands.length'),1);
  // Exact large integers and unknown BB fallback, with no accounting requests.
  const huge=state(true);huge.members[0].stack='900719925474099312345';await feed(page,huge);
  await page.run("document.querySelector('.own-stack').click()");
  await page.wait("document.querySelector('.own-stack').textContent==='9007199254740993123.45 BB'");
  huge.version=++version;huge.rules.big_blind='0';await feed(page,huge);
  await page.wait("document.querySelector('.own-stack').textContent==='900,719,925,474,099,312,345'");
  assert(await page.run("[...document.querySelectorAll('.pot-presets button')].every(b=>b.disabled)"));
  assert.equal(await page.run('window.commands.length'),1);
  // Changed amount, street, hand, endpoint, sitout and own actions cancel.
  for(const change of [
    s=>s.hand.call_amount='75',s=>s.hand.street='flop',s=>s.hand.id='h2',
    s=>s.control=false,s=>s.members[0].sitout=true,
    s=>{s.event_seq=1;s.events=[{id:'acted',seq:1,at:Date.now()/1000,kind:'action',user:A,action:'check'}];}
  ]) {
    await feed(page,state());await page.click('跟注目前顯示金額 50');
    const changed=state();change(changed);await feed(page,changed);
    await page.wait("![...document.querySelectorAll('button')].some(b=>b.textContent==='取消預選')");
    assert.equal(await page.run('window.commands.length'),1);
  }
  // Preselected check survives other players' check and sends only on own turn.
  const check=state();check.hand.call_amount='0';await feed(page,check);
  await page.click('可過牌就過牌，否則取消');
  const checked=state(true);checked.hand.call_amount='0';checked.hand.legal.check=true;checked.hand.legal.call='0';await feed(page,checked);
  await page.wait('window.commands.length===2');
  assert.equal(await page.run('window.commands[1].action'),'check');
  // Fixed call turning all-in returns to manual confirmation without sending.
  await feed(page,state());await page.click('跟注目前顯示金額 50');
  const short=state(true);short.hand.players[0].stack='50';await feed(page,short);
  await page.wait("document.body.innerText.includes('預選已取消：跟注將全下')");
  assert.equal(await page.run('window.commands.length'),2);
  await page.run("document.querySelectorAll('.action-buttons button')[1].click()");
  await page.wait("document.querySelector('dialog')?.textContent.includes('確認全下')");
  await page.click('取消');
  // Lost response keeps original command id and original payload through reconnect.
  await feed(page,state(true));await page.run('window.failNext=true');
  await page.run("document.querySelectorAll('.action-buttons button')[1].click()");
  await page.wait("document.body.innerText.includes('結果待確認')");
  const lost=await page.run('window.commands.at(-1)');
  await page.run('window.holdReady=true;window.drop(1006)');
  await page.wait("document.querySelector('.connection').textContent.includes('恢復連線')");
  await page.wait("document.querySelector('.connection').textContent.includes('同步桌況')");
  assert(await page.run("[...document.querySelectorAll('.action-buttons button')].every(b=>b.disabled)"));
  await page.run('window.ready()');
  await page.wait("document.querySelector('.connection').textContent.includes('結果待確認')");
  await page.click('重送同一指令');
  await page.wait('window.commands.length===4');
  assert.deepEqual(await page.run('window.commands.at(-1)'),lost);
  // Replay entry clears preselection and never acts from live state updates.
  await feed(page,state());await page.click('跟注目前顯示金額 50');
  await page.click('上一手／回放');await feed(page,state(true));
  assert.equal(await page.run('window.commands.length'),4);
  await page.run("document.querySelector('dialog button[aria-label=關閉對話框]').click()");

  // Legal boundaries and pot sizing remain server-authoritative.
  const pot=state(true);pot.hand.street='flop';pot.hand.pot='300';pot.hand.legal.call='100';pot.hand.call_amount='100';pot.hand.players[0].bet='50';
  await feed(page,pot);await page.click('1×池');
  assert.equal(await page.run("document.querySelector('[aria-label=加注至]').value"),'550');
  pot.version=++version;pot.hand.legal.raise=false;await feed(page,pot);
  assert(await page.run("[...document.querySelectorAll('.pot-presets button')].every(b=>b.disabled)"));
  const expired=state(true);expired.hand.deadline=Date.now()/1000-1;await feed(page,expired);
  assert(await page.run("[...document.querySelectorAll('.action-buttons button')].every(b=>b.disabled)"));
  const shortRaise=state(true);shortRaise.hand.legal.min_raise_to='200';shortRaise.hand.legal.max_raise_to='150';await feed(page,shortRaise);
  await page.click('2.5 BB');
  assert.equal(await page.run("document.querySelector('[aria-label=加注至]').value"),'150');
  await page.run("document.querySelectorAll('.action-buttons button')[2].click()");
  await page.wait("document.querySelector('dialog')?.textContent.includes('確認全下')");
  await page.click('取消');
  const inactive=state();inactive.frozen=true;await feed(page,inactive);
  await page.wait("document.querySelector('.connection').textContent.includes('凍結')");
  inactive.version=++version;inactive.frozen=false;inactive.closed=true;await feed(page,inactive);
  await page.wait("document.querySelector('.connection').textContent.includes('已關閉')");
  inactive.version=++version;inactive.closed=false;inactive.joined=false;await feed(page,inactive);
  await page.wait("document.querySelector('.connection').textContent.includes('已離桌')");
  assert.equal(await page.run('window.commands.length'),4);
  await feed(page,state(true));

  const full=state(true);await feed(page,full);
  await page.run("{ const field=document.querySelector('[aria-label=加注至]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(field,'02000');field.dispatchEvent(new Event('input',{bubbles:true})); }");
  await page.wait("document.querySelector('.action-buttons button:last-child').textContent.includes('全下')");
  await page.run("document.querySelector('.action-buttons button:last-child').click()");
  await page.wait("document.querySelector('dialog')?.textContent.includes('確認全下')");
  assert.equal(await page.run('window.commands.length'),4);
  await page.click('取消');
  // Saved settings and shared four-color card styles across themes and widths.
  await feed(page,state(true));await page.click('牌桌選項');
  await page.run("const boxes=document.querySelectorAll('.personal-settings input[type=checkbox]');boxes[0].click();boxes[1].click()");
  await page.wait("document.querySelector('.game').classList.contains('large-cards')");
  await page.run("{ const field=document.querySelector('[aria-label=\"翻牌前 BB 倍數\"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(field,'2.25, 2.5, 3, 4, 6');field.dispatchEvent(new Event('input',{bubbles:true})); }");
  await page.click('儲存下注按鈕');
  await page.run("document.querySelector('dialog button[aria-label=關閉對話框]').click()");
  await page.click('2.25 BB');
  assert.equal(await page.run("document.querySelector('[aria-label=加注至]').value"),'225');
  assert.equal(await page.run('window.commands.length'),4);
  for(const width of [1440,390,320]) for(const theme of ['classic_walnut','midnight_oak','burgundy_leather']) {
    await page.call('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<600});
    await page.run('document.documentElement.dataset.theme='+JSON.stringify(theme));
    assert(await page.run('document.documentElement.scrollWidth<=innerWidth'), 'horizontal overflow '+width+' '+theme);
    assert.equal(await page.run("getComputedStyle(document.querySelector('.hero-seat [data-suit=c]')).color"),'rgb(8, 115, 68)');
    assert.equal(await page.run("getComputedStyle(document.querySelector('.hero-seat [data-suit=d]')).color"),'rgb(23, 87, 187)');
    await page.click('2.5 BB');
    await page.shot(width+'-'+theme);
  }
  await page.call('Page.reload');await page.wait("!!document.querySelector('.lobby')");await page.click('上一手摘要與歷史回放');await page.run("document.querySelector('dialog button[aria-label=關閉對話框]').click()");
  await page.wait("document.querySelector('.game')?.classList.contains('large-cards')");
  await page.wait("document.querySelector('.connection').textContent.includes('已同步')");
  await page.run('window.drop(4401)');
  await page.wait("document.querySelector('.connection').textContent.includes('登入已撤銷')");
  assert(!await page.run("document.querySelector('.connection').textContent.includes('恢復')"));
  assert.deepEqual(page.errors,[]);
  const result={amounts:true,presets:true,preselection:true,reconnect:true,exactRetry:true,replayIsolation:true,persistence:true,themes:3,widths:[1440,390,320],pageErrors:[],output};
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
} catch(error) {
  console.error(error.stack??String(error));console.error(stderr);
  for(const page of pages){await page.shot('failure').catch(()=>{});console.error(await page.run('document.body.innerText.slice(-1500)').catch(()=>''));}
  process.exitCode=1;
} finally {
  for(const page of pages){await page.call('Browser.close').catch(()=>{});page.socket.close();}
  for(const child of processes){try{execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});}catch{}}
}
