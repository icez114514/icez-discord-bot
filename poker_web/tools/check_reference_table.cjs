// Built-client acceptance: isolated API/WS, real engine recordings, headless Chrome.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),os=require('node:os'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..'),dist=path.join(root,'poker_web/dist'),output=path.join(root,'tmp/reference-table');
fs.mkdirSync(output,{recursive:true});
const recordings=JSON.parse(execFileSync(path.join(root,'poker/.venv/Scripts/python.exe'),['-m','poker_tests.presentation_fixtures'],{cwd:root,encoding:'utf8',windowsHide:true}));
const user='111111111111111111',temp=fs.mkdtempSync(path.join(os.tmpdir(),'poker-reference-'));
const api={
 '/api/account':{user_id:user,available:'50000',table:'1000',in_flight:'0',settled:'51000',subsidy:{eligible:false,amount:'0',reason:'assets_at_least_5000'}},
 '/api/environment':{environment:'test'},'/api/roles':{tables:true,funds:false},
 '/api/preferences':{theme:'classic_walnut'},'/api/tables':{tables:[],current_table:'main'},
 '/api/table/profiles':{table_id:'main',profiles:[{id:user,display_name:'Me',avatar_url:'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2280%22 height=%2280%22%3E%3Crect width=%2280%22 height=%2280%22 fill=%22%23396077%22/%3E%3Ccircle cx=%2240%22 cy=%2228%22 r=%2215%22 fill=%22%23eccba0%22/%3E%3Cpath d=%22M12 80V68a28 28 0 0 1 56 0v12%22 fill=%22%23c47370%22/%3E%3C/svg%3E'}]}
};
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost');
 if(api[url.pathname]){res.setHeader('Content-Type','application/json');return res.end(JSON.stringify(api[url.pathname]));}
 const file=path.resolve(dist,'.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname));
 if(!file.startsWith(dist+path.sep)||!fs.existsSync(file)){res.writeHead(404);return res.end();}
 res.setHeader('Content-Type',({'.js':'text/javascript','.css':'text/css','.html':'text/html','.ogg':'audio/ogg','.png':'image/png'})[path.extname(file)]||'application/octet-stream');fs.createReadStream(file).pipe(res);
});
const fixture=`
window.snapshot={id:'main',name:'Demo proportions',rules:{small_blind:'50',big_blind:'100'},version:1,joined:true,closed:false,control:true,owner:'${user}',event_seq:0,events:[],time_bank:60,
 members:Array.from({length:6},(_,i)=>({id:i?'npc:'+i:'${user}',seat:i,mode:'active',sitout:false,connected:true,stack:'1000',leaving:false,topup:null,notice:null,npc_failures:0})),
 hand:{id:'geometry',button:1,street:'flop',turn:1,pot:'600',call_amount:'0',actor:0,deadline:Date.now()/1000+300,extensions:0,payouts:null,board:['As','Kd','7h'],legal:{check:true,fold:true,raise:true,min_raise_to:'100',max_raise_to:'1000'},
 players:Array.from({length:6},(_,i)=>({id:i?'npc:'+i:'${user}',stack:'1000',bet:'50',paid:'100',cards:i?[]:['Ah','Kh'],folded:false}))}};
window.feed=(s,baseline=false)=>{window.snapshot=structuredClone(s);window.socket.onmessage?.({data:JSON.stringify({type:baseline?'ready':'state',connection:'endpoint',state:window.snapshot})});};
window.WebSocket=class {static OPEN=1;readyState=1;constructor(){window.socket=this;setTimeout(()=>{this.onopen?.();this.onmessage?.({data:JSON.stringify({type:'ready',connection:'endpoint',state:snapshot})});},20);}send(){}close(){this.readyState=3;}};
`;
const delay=ms=>new Promise(r=>setTimeout(r,ms));let chrome,ws;
(async()=>{
 await new Promise(r=>server.listen(18979,'127.0.0.1',r));
 chrome=spawn(process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--no-first-run','--remote-debugging-port=19379','--user-data-dir='+temp,'about:blank'],{windowsHide:true,stdio:'ignore'});
 let list;
 for(let i=0;i<100;i++){try{list=await(await fetch('http://127.0.0.1:19379/json')).json();break;}catch{await delay(100);}}
 assert(list,'Chrome ready');
 ws=new WebSocket(list.find(p=>p.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
 let seq=0;const pending=new Map(),errors=[];
 ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.method==='Runtime.exceptionThrown')errors.push(d.params.exceptionDetails.exception?.description??d.params.exceptionDetails.text);if(d.id){const p=pending.get(d.id);pending.delete(d.id);d.error?p.reject(d.error):p.resolve(d.result);}};
 const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
 const run=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description??JSON.stringify(r.exceptionDetails));return r.result.value;};
 const until=async(expression,timeout=12000)=>{const end=Date.now()+timeout;while(Date.now()<end){if(await run('Boolean('+expression+')'))return;await delay(30);}throw Error('Timed out: '+expression);};
 const shot=async name=>fs.writeFileSync(path.join(output,name+'.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true})).data,'base64'));
 const resize=async(width,height)=>{await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await run('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');};
 await call('Runtime.enable');await call('Page.enable');await call('Page.addScriptToEvaluateOnNewDocument',{source:fixture});await resize(1920,1080);
 await call('Page.navigate',{url:'http://127.0.0.1:18979/'});
 await until("[...document.querySelectorAll('button')].some(b=>b.textContent==='返回目前牌桌')");
 await run("[...document.querySelectorAll('button')].find(b=>b.textContent==='返回目前牌桌').click()");
 await until("document.querySelectorAll('.seat:not(.empty)').length===6");
 await until("[...document.images].filter(i=>i.classList.contains('casino-art')).every(i=>i.complete&&i.naturalWidth>0)");
 await run('window.geometry=structuredClone(snapshot)');
 const sizes=[];
 for(const [width,height] of [[1920,1080],[1440,900],[1280,720],[1200,800],[1399,900],[900,600],[390,844]]) {
  await resize(width,height);
  const result=await run(`(()=>{
   const rect=q=>{const r=document.querySelector(q).getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};};
   const intersects=(a,b)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
   const avatar=rect('.portrait'),card=rect('.board .card'),name=rect('.seat-info'),board=rect('.board > .cards'),panel=rect('.table-action-slot');
   const seats=[...document.querySelectorAll('.seat-plaque')].map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};});
   const fan=q=>{const rs=[...document.querySelectorAll(q+' .seat-cards .card')].map(e=>e.getBoundingClientRect());return Math.max(...rs.map(r=>r.right))-Math.min(...rs.map(r=>r.left));};
   return {avatar,card,name,board,panel,hiddenFan:fan('.seat.n'),openFan:fan('.hero-seat'),boardOverlap:seats.some(s=>intersects(s,board)),panelOverlap:seats.some(s=>intersects(s,panel)),overflow:document.documentElement.scrollWidth>innerWidth,buttons:[...document.querySelectorAll('.action-buttons button')].map(e=>e.getBoundingClientRect().height)};
  })()`);
  assert(Math.abs(result.card.w/result.avatar.w-112/160)<.01,'card/avatar ratio '+width);
  assert(Math.abs(result.card.h/result.avatar.h-158/160)<.01,'card height ratio '+width);
  assert(Math.abs(result.name.w/result.avatar.w-190/160)<.01,'name/avatar ratio '+width);
  assert(Math.abs(result.hiddenFan/result.avatar.w-82/160)<.03*(82/160),'hidden fan ratio '+width);
  assert(Math.abs(result.openFan/result.avatar.w-178/160)<.03*(178/160),'open fan ratio '+width);
  assert(!result.boardOverlap,'board overlaps seat '+width);assert(!result.panelOverlap,'panel overlaps seat '+width);
  assert(!result.overflow,'horizontal overflow '+width); if(width>=900) assert(await run('document.documentElement.scrollHeight<=innerHeight+1'),'vertical overflow '+width);assert(result.buttons.every(h=>h>=43.9),'button hit height');
  sizes.push({width,height,...result});await shot('table-'+width);
 }
 await resize(1440,900);
 await run("window.savedCard=document.querySelector('.board .card');window.savedFace=window.savedCard.querySelector('.casino-art');true");
 assert.equal(await run("document.querySelectorAll('.countdown-ring,.avatar-countdown').length"),0,'portrait not obscured by clock');
 assert.equal(await run("document.querySelectorAll('.turn-progress').length"),1,'actor has green timer');
 const progressStart=await run("getComputedStyle(document.querySelector('.turn-progress > span')).transform");
 await call('Performance.enable');
 const metric=async()=>Object.fromEntries((await call('Performance.getMetrics')).metrics.map(m=>[m.name,m.value]));
 const before=await metric();
 await run(`new Promise(resolve=>{let count=0;const click=()=>{document.querySelector('.own-stack').click();if(++count===30)resolve();else requestAnimationFrame(click);};requestAnimationFrame(click);})`);
 assert(await run("savedCard===document.querySelector('.board .card')&&savedFace===document.querySelector('.board .casino-art')"),'controls must not remount cards');
 const after=await metric();
 const perf=Object.fromEntries(['TaskDuration','ScriptDuration','LayoutDuration','RecalcStyleDuration','LayoutCount','RecalcStyleCount'].map(k=>[k,after[k]-before[k]]));
 assert.notEqual(await run("getComputedStyle(document.querySelector('.turn-progress > span')).transform"),progressStart,'green timer animates');
 console.log('Interaction performance',JSON.stringify(perf));
 fs.writeFileSync(path.join(output,'performance.json'),JSON.stringify(perf,null,2));
 const rec=structuredClone(recordings);rec.forEach(s=>{s.rules={small_blind:'50',big_blind:'100'};s.server_time=Date.now()/1000;s.events.forEach(e=>e.at=s.server_time);});
 // New hand: two card flights per player, then the owner's face is visible.
 await run('window.feed('+JSON.stringify(rec[0])+',true);window.feed('+JSON.stringify(rec[1])+')');
 await until("document.querySelectorAll('.deal-card').length===8");
 await shot('dealing');
 const landing=await run(`(()=>[...document.querySelectorAll('.deal-card')].map(e=>{const animation=e.getAnimations()[0],timing=animation.effect.getTiming();animation.pause();animation.currentTime=Number(timing.delay)+Number(timing.duration);const a=e.getBoundingClientRect(),b=document.querySelector(e.dataset.target).getBoundingClientRect();animation.play();return Math.max(Math.abs(a.x-b.x),Math.abs(a.y-b.y),Math.abs(a.width-b.width),Math.abs(a.height-b.height));}))()`);
 assert(landing.every(error=>error<1),'deal flight matches final anchor: '+landing);

 await until("document.querySelectorAll('.deal-card').length===0 && document.querySelector('.hero-seat.open-cards')");
 assert.equal(await run("document.querySelectorAll('.seat.open-cards').length"),1,'only own cards known at deal');
 // Baseline immediately before the last call: only the public prefix is visible.
 await run('window.feed('+JSON.stringify(rec.at(-2))+',true)');
 await until("document.querySelectorAll('.board .card:not(.blank)').length===0");
 await run(`window.observed=[];window.capture=()=>window.observed.push({board:[...document.querySelectorAll('.board .card:not(.blank)')].map(e=>e.getAttribute('aria-label')),settled:!!document.querySelector('.settlement'),cards:[...document.querySelectorAll('.seat.open-cards')].map(e=>e.dataset.player),wins:document.querySelectorAll('.winner-badge').length,shares:[...document.querySelectorAll('.equity-label')].map(e=>e.textContent)});window.observer=new MutationObserver(window.capture);observer.observe(document.querySelector('.table-scene'),{subtree:true,childList:true,attributes:true,characterData:true});`);
 await run('window.feed('+JSON.stringify(rec.at(-1))+')');
 await until("document.querySelectorAll('.seat.open-cards').length===4");
 assert.equal(await run("document.querySelectorAll('.board .card:not(.blank)').length"),0,'all-in cards must precede runout');
 await shot('all-in-reveal');
 await until("document.querySelectorAll('.board .card:not(.blank)').length===3");
 await shot('all-in-flop');
 await until("document.querySelector('.settlement') && [...document.querySelectorAll('.equity-label')].some(e=>e.textContent.includes('%'))");
 const observed=await run('window.observer.disconnect();window.observed');
 assert(observed.some(v=>v.board.length===3),'flop observed');assert(observed.some(v=>v.board.length===4),'turn observed');
 assert(observed.filter(v=>v.board.length<5).every(v=>!v.settled&&v.wins===0),'no premature result');
 const totals=await run("[...document.querySelectorAll('.seat-stack')].map(e=>e.textContent)");
 const expected=rec.at(-1).members.map(m=>Number(m.stack).toLocaleString('zh-TW'));
 assert.deepEqual(totals,expected,'final stacks match server');
 await until("document.querySelectorAll('.board-deal,.board .deal-back').length===0");
 assert(await run("[...document.querySelectorAll('.board .casino-art')].every(e=>e instanceof SVGElement&&getComputedStyle(e).mixBlendMode==='normal'&&getComputedStyle(e).filter==='none')"),'clean vector faces without tint filters');
 assert(await run(`(()=>{const a=document.querySelector('.hero-seat .equity-label').getBoundingClientRect(),b=document.querySelector('.hero-seat .winner-badge').getBoundingClientRect();return b.top>=a.bottom;})()`),'winner and equity do not overlap');
 await shot('settlement');
 await run('window.feed('+JSON.stringify(rec.at(-1))+')');
 assert.equal(await run("document.querySelectorAll('.chip-flight').length"),0,'duplicate does not replay');
 // Reconnect uses a silent, final baseline and clears queued effects.
 await run('window.feed('+JSON.stringify(rec.at(-2))+',true);window.feed('+JSON.stringify(rec.at(-1))+');window.feed('+JSON.stringify(rec.at(-1))+',true)');
 await until("document.querySelectorAll('.board .card:not(.blank)').length===5");
 assert.equal(await run("document.querySelectorAll('.chip-flight,.deal-card').length"),0);
 assert.equal(await run("document.querySelectorAll('.winner-badge').length"),0,'baseline must not celebrate');
 // Missing event range becomes a silent authoritative snapshot, never a partial runout.
 const missing=structuredClone(rec.at(-1));missing.event_seq+=2;missing.events=missing.events.slice(-1);
 await run('window.feed('+JSON.stringify(rec.at(-2))+',true);window.feed('+JSON.stringify(missing)+')');
 await until("document.querySelectorAll('.board .card:not(.blank)').length===5");
 assert.equal(await run("document.querySelectorAll('.chip-flight,.deal-card,.winner-badge').length"),0);
 // Switching tables invalidates old animation and worker results.
 await run('window.feed('+JSON.stringify(rec.at(-2))+',true);window.feed('+JSON.stringify(rec.at(-1))+');geometry.id="other";window.feed(geometry)');
 await until("document.querySelectorAll('.seat:not(.empty)').length===6");
 assert.equal(await run("document.querySelectorAll('.board .card:not(.blank)').length"),3);
 assert.equal(await run("document.querySelectorAll('.equity-label,.chip-flight,.deal-card').length"),0);
 await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
 await run('window.feed('+JSON.stringify(rec.at(-2))+',true);window.feed('+JSON.stringify(rec.at(-1))+')');
 await until("document.querySelector('.settlement')");
 assert.equal(await run("document.querySelectorAll('.chip-flight,.deal-card').length"),0,'reduced motion skips queued effects');
 assert.deepEqual(errors,[]);
 assert(observed.some(v=>v.board.length===0&&v.shares.some(s=>s.includes('%'))),'preflop worker equity visible before flop');
 fs.writeFileSync(path.join(output,'measurements.json'),JSON.stringify({sizes,observed},null,2));
 console.log('PASS reference ratios, seven viewports, responsive controls, clean faces, timer, all-in equity/runout, payouts, duplicates, reconnect, reduced motion');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{ws?.close();chrome?.kill();server.close();});
