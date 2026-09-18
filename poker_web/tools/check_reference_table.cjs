// Built-client acceptance: isolated API/WS, real engine recordings, headless Chrome.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),os=require('node:os'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..'),dist=path.resolve(process.env.POKER_WEB_DIST||path.join(root,'poker_web/dist')),output=path.join(root,'tmp/reference-table');
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
window.commands=[];
const nativeFetch=window.fetch;
window.fetch=async(url,options)=>{if(String(url).endsWith('/api/table/commands')){window.commands.push(JSON.parse(options.body));return new Response(JSON.stringify({result:{}}),{status:200,headers:{'Content-Type':'application/json'}});}return nativeFetch(url,options);};
window.snapshot={id:'main',name:'Demo proportions',rules:{small_blind:'50',big_blind:'100'},version:1,joined:true,closed:false,control:true,owner:'${user}',event_seq:0,events:[],time_bank:60,
 members:Array.from({length:6},(_,i)=>({id:i?'npc:'+i:'${user}',seat:i,mode:'active',sitout:false,connected:true,stack:'1000',leaving:false,topup:null,notice:null,npc_failures:0})),
 hand:{id:'geometry',button:1,street:'flop',turn:1,pot:'600',call_amount:'0',actor:0,deadline:Date.now()/1000+300,extensions:0,payouts:null,board:['As','Kd','7h'],legal:{check:true,fold:true,raise:true,min_raise_to:'100',max_raise_to:'1000'},
 players:Array.from({length:6},(_,i)=>({id:i?'npc:'+i:'${user}',stack:'1000',bet:'50',paid:'100',cards:i?[]:['Ah','Kh'],folded:false}))}};
window.feed=(s,baseline=false)=>{const version=Math.max(s.version??0,(window.snapshot?.version??0)+1);window.snapshot=structuredClone(s);window.snapshot.version=version;window.socket.onmessage?.({data:JSON.stringify({type:baseline?'ready':'state',connection:'endpoint',state:window.snapshot})});};
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
 await until("!!document.querySelector('.home-return')");
 await run("document.querySelector('.home-return').click()");
 await until("document.querySelectorAll('.seat:not(.empty)').length===6");
 await until("[...document.images].filter(i=>i.classList.contains('casino-art')).every(i=>i.complete&&i.naturalWidth>0)");
 await run("document.querySelector('[aria-label=\"個人設定\"]').click()");
 await until("document.querySelector('dialog[open] input[aria-label=\"總音量\"]')");
 const volume=await run(`(()=>{const e=document.querySelector('input[aria-label="總音量"]'),r=e.getBoundingClientRect();return {x:r.left+r.width*.25,y:r.top+r.height/2,before:e.value,hit:document.elementFromPoint(r.left+r.width*.25,r.top+r.height/2)===e};})()`);
 assert(volume.hit,'in-game volume slider receives pointer input');
 await call('Input.dispatchMouseEvent',{type:'mousePressed',x:volume.x,y:volume.y,button:'left',clickCount:1});
 await call('Input.dispatchMouseEvent',{type:'mouseReleased',x:volume.x,y:volume.y,button:'left',clickCount:1});
 assert.notEqual(await run("document.querySelector('input[aria-label=\"總音量\"]').value"),volume.before,'volume changes through mouse input');
 await run("document.querySelector('[aria-label=\"關閉對話框\"]').click()");
 await run('window.geometry=structuredClone(snapshot)');
 // Browser zoom changes CSS viewport dimensions, but must not switch table height allocation.
 await resize(1280,580);
 const normalZoomWidth=await run("document.querySelector('.felt').getBoundingClientRect().width");
 await resize(1707,773);
 const zoomedWidth=await run("document.querySelector('.felt').getBoundingClientRect().width");
 assert(zoomedWidth*.75<=normalZoomWidth*1.12,'75% zoom must not unexpectedly enlarge the table: '+normalZoomWidth+' -> '+zoomedWidth*.75);
 console.log('Zoom regression: physical table width at 100% / 75%',normalZoomWidth,zoomedWidth*.75);
 await resize(1280,580);
 await run("document.querySelector('.action-raise').click()");
 await until("document.querySelector('dialog.mobile-raise-dialog[open]')");
 assert.equal(await run('commands.length'),0,'short desktop opening raise must not submit');
 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await until("!document.querySelector('dialog[open]')");
 assert.equal(await run('commands.length'),0,'closing short desktop raise must not submit');
 const sizes=[];
 for(const [width,height] of [[1920,1080],[1591,793],[1440,900],[1366,768],[1280,580],[1024,576],[853,480],[1280,720],[1200,800],[1399,900],[900,600],[320,568],[360,780],[390,844],[430,932]]) {
  await resize(width,height);
  const result=await run(`(()=>{
   const rect=q=>{const r=document.querySelector(q).getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};};
   const intersects=(a,b)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
   const avatar=rect('.portrait'),card=rect('.board .card'),name=rect('.seat-info'),board=rect('.board > .cards'),panel=rect('.table-action-slot');
   const seats=[...document.querySelectorAll('.seat-plaque')].map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};});
   const fan=q=>{const rs=[...document.querySelectorAll(q+' .seat-cards .card')].map(e=>e.getBoundingClientRect());return Math.max(...rs.map(r=>r.right))-Math.min(...rs.map(r=>r.left));};
   return {avatar,card,name,board,panel,hiddenFan:fan('.seat.n'),openFan:fan('.hero-seat'),boardOverlap:seats.some(s=>intersects(s,board)),panelOverlap:seats.some(s=>intersects({...s,h:Math.min(s.h,document.querySelector('.table-viewport').getBoundingClientRect().bottom-s.y)},panel)),overflow:document.documentElement.scrollWidth>innerWidth,buttons:[...document.querySelectorAll('.action-buttons button')].map(e=>e.getBoundingClientRect().height)};
  })()`);
  if(width>=900||width>height){
  assert(Math.abs(result.card.w/result.avatar.w-112/(143*1.18))<.01,'card/avatar ratio '+width);
  assert(Math.abs(result.card.h/result.avatar.h-158/(143*1.18))<.01,'card height ratio '+width);
  assert(Math.abs(result.name.w/result.avatar.w-314/(143*1.18))<.01,'name/avatar ratio '+width);
  assert(Math.abs(result.hiddenFan/result.avatar.w-100/(143*1.18))<.03*(100/(143*1.18)),'hidden fan ratio '+width);
  assert(Math.abs(result.openFan/result.avatar.w-261.6/(143*1.18))<.03*(261.6/(143*1.18)),'open fan ratio '+width);
  } else {
   assert(Math.abs(result.card.w/result.avatar.w-48/(70*1.18))<.01,'portrait card ratio');
   assert(Math.abs(result.name.w/result.avatar.w-144/(70*1.18))<.01,'portrait plaque ratio');
   assert(await run(`document.querySelector('.table-scene').offsetWidth===390&&document.querySelector('.table-scene').offsetHeight===1030`),'portrait canvas');
   assert(await run(`[...document.querySelectorAll('.seat-info strong,.seat-stack')].every(e=>parseFloat(getComputedStyle(e).fontSize)*document.querySelector('.table-scene').getBoundingClientRect().width/390>=11.99)`),'readable mobile names');
   assert(await run(`parseFloat(getComputedStyle(document.querySelector('.own-stack'),'::after').height)*document.querySelector('.table-scene').getBoundingClientRect().width/390>=43.9`),'BB touch height');
   assert(await run(`(()=>{const a=document.querySelector('.hero-seat .seat-plaque').getBoundingClientRect(),b=document.querySelector('.table-viewport').getBoundingClientRect();return a.top>=b.top&&a.bottom<=b.bottom;})()`),'hero initially visible in portrait '+width);
  }
  assert(await run(`(()=>{const pot=document.querySelector('.pot').getBoundingClientRect(),icon=document.querySelector('.pot-tools .icon-button').getBoundingClientRect();return icon.right<pot.left&&Math.abs(icon.top+icon.height/2-pot.top-pot.height/2)<1&&icon.width>=27.9&&icon.width<29;})()`),'pot information icon anchored to bar '+width);
  assert(await run(`(()=>{const seat=document.querySelector('.hero-seat'),avatar=seat.querySelector('.portrait').getBoundingClientRect(),info=seat.querySelector('.seat-info').getBoundingClientRect();return avatar.right>info.left&&avatar.right<info.left+info.width/4;})()`),'avatar overlaps information frame edge '+width);
  assert(!result.boardOverlap,'board overlaps seat '+width);assert(!result.panelOverlap,'panel overlaps seat '+width);
  assert(!result.overflow,'horizontal overflow '+width); if(width>=320) assert(await run('document.documentElement.scrollHeight<=innerHeight+1'),'vertical overflow '+width);assert(result.buttons.every(h=>h>=43.9),'button hit height');
  assert(await run(`(()=>{const seat=document.querySelector('.hero-seat'),plaque=seat.querySelector('.seat-info').getBoundingClientRect();return [...seat.querySelectorAll('.seat-cards .casino-art')].every(e=>e.getBoundingClientRect().bottom<plaque.top);})()`),'both ranks and suits clear of plaque '+width);
  if(width>=900||width>height){
   assert(await run(`(()=>{const visible=r=>r.left>=-.5&&r.top>=-.5&&r.right<=innerWidth+.5&&r.bottom<=innerHeight+.5;const panel=document.querySelector('.table-action-slot').getBoundingClientRect();const parts=[...document.querySelectorAll('.hero-seat .seat-cards,.hero-seat .seat-plaque,.hero-seat .seat-feedback')];return visible(panel)&&[...document.querySelectorAll('.action-buttons button')].every(e=>visible(e.getBoundingClientRect())&&e.getBoundingClientRect().height>=44)&&parts.every(e=>{const r=e.getBoundingClientRect();return visible(r)&&(r.bottom<=panel.top||r.right<=panel.left||r.left>=panel.right);});})()`),'desktop controls and hero visible '+width+'x'+height);
   const before=await run("document.querySelector('.table-action-slot').getBoundingClientRect().y");
   await run('window.otherTurn=structuredClone(geometry);otherTurn.hand.actor=1;window.feed(otherTurn,true)');
   await until("!document.querySelector('.preselection').classList.contains('preselection-idle')");
   assert.equal(await run("document.querySelector('.table-action-slot').getBoundingClientRect().y"),before,'preselection keeps dock position');
   await run('window.feed(geometry,true)');
  }
  if(width>=1100 && height>=600 && width/height<=2) assert(await run("document.querySelector('.felt').getBoundingClientRect().width/innerWidth>=.85"),'desktop table must fill at least 85% of viewport width '+width+'x'+height);
  sizes.push({width,height,...result});await shot('table-'+width);
 }
 // Mobile action drawer sends nothing until an explicit confirmation.
 await resize(390,844);
 const openRaise=async()=>{await run('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');await until("!document.querySelector('.action-raise').disabled");await run("document.querySelector('.action-raise').focus();document.querySelector('.action-raise').click()");await until("document.querySelector('dialog.mobile-raise-dialog[open]')");};
 await openRaise();assert.equal(await run('commands.length'),0,'opening drawer never submits');
 await run(`(()=>{const e=document.querySelector('.mobile-raise-dialog [aria-label="加注至"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'');e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
 await until("document.querySelector('.confirm-raise').disabled");
 await run("document.querySelector('.mobile-raise-dialog [aria-label=\"關閉對話框\"]').click()");
 await until("!document.querySelector('dialog[open]')");await openRaise();
 await run(`(()=>{const e=document.querySelector('.mobile-raise-dialog [aria-label="加注至"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'100');e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
 await until("!document.querySelector('.confirm-raise').disabled");

 await run("document.querySelector('.mobile-raise-dialog [aria-label=\"增加下注\"]').click()");
 await until("document.querySelector('.mobile-raise-dialog [aria-label=\"加注至\"]').value==='150'");
 await shot('mobile-raise');
 await run("Object.defineProperty(visualViewport,'height',{configurable:true,value:320});visualViewport.dispatchEvent(new Event('resize'))");
 await until("document.querySelector('.mobile-raise-dialog').getBoundingClientRect().bottom<=320.5");
 await run("document.querySelector('.confirm-raise').scrollIntoView({block:'nearest'})");
 assert(await run("document.querySelector('.confirm-raise').getBoundingClientRect().bottom<=320.5"),'keyboard leaves confirmation reachable');
 await run("delete visualViewport.height;visualViewport.dispatchEvent(new Event('resize'))");

 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await until("!document.querySelector('dialog[open]')");
 assert.equal(await run("document.activeElement.classList.contains('action-raise')"),true,'drawer returns focus');
 await openRaise();assert.equal(await run("document.querySelector('.mobile-raise-dialog [aria-label=\"加注至\"]').value"),'150','draft retained');
 await run("document.querySelector('.confirm-raise').click();document.querySelector('.confirm-raise')?.click()");
 await until('commands.length===1');await until("!document.querySelector('dialog[open]')&&!document.querySelector('.action-raise').disabled");
 assert.equal(await run('commands[0].amount'),'150');assert.equal(await run('commands.length'),1,'double activation submits once');
 await openRaise();await run("snapshot.hand.turn++;snapshot.hand.legal.min_raise_to='300';window.feed(snapshot)");
 await until("!document.querySelector('dialog[open]')");await openRaise();assert.equal(await run("document.querySelector('.mobile-raise-dialog [aria-label=\"加注至\"]').value"),'300','new turn resets minimum');
 await run("document.querySelector('.mobile-raise-dialog [aria-label=\"關閉對話框\"]').click()");
 await run("snapshot.hand.turn++;snapshot.hand.legal.min_raise_to='1000';window.feed(snapshot)");await openRaise();
 await run("document.querySelector('.confirm-raise').click()");await until("document.querySelector('dialog[open]')?.textContent.includes('確認全下')");
 assert.equal(await run('commands.length'),1,'all-in needs second confirmation');
 await run("[...document.querySelectorAll('dialog button')].find(b=>b.textContent==='取消').click()");
 await run("snapshot.hand.turn++;snapshot.hand.legal.min_raise_to='100';window.feed(snapshot)");await openRaise();
 await run("snapshot.control=false;window.feed(snapshot)");await until("!document.querySelector('dialog[open]')");
 assert.equal(await run('commands.length'),1,'control loss never submits');
 // Every seat count uses portrait anchors, including halfway rotation.
 for(let count=2;count<=6;count++){
  await run(`window.mobileDeal=structuredClone(geometry);mobileDeal.members=mobileDeal.members.slice(0,${count});mobileDeal.hand.players=mobileDeal.hand.players.slice(0,${count});mobileDeal.hand.id='mobile-${count}';mobileDeal.hand.board=[];mobileDeal.hand.street='preflop';mobileDeal.events=[];mobileDeal.event_seq=0;window.feed(mobileDeal,true)`);
  await until(`document.querySelectorAll('.seat:not(.empty)').length===${count}`);
  await run(`mobileDeal.event_seq=1;mobileDeal.events=[{id:'deal-${count}',hand_id:mobileDeal.hand.id,seq:1,kind:'deal',at:Date.now()/1000}];window.feed(mobileDeal)`);
  await until(`document.querySelectorAll('.deal-card').length===${count*2}`);
  if(count===6)await shot('mobile-dealing');
  const errors=await run(`(()=>[...document.querySelectorAll('.deal-card')].map(e=>{const a=e.getAnimations()[0],t=a.effect.getTiming();a.pause();a.currentTime=Number(t.delay)+Number(t.duration);const x=e.getBoundingClientRect(),y=document.querySelector(e.dataset.target).getBoundingClientRect();a.play();return Math.max(Math.abs(x.x-y.x),Math.abs(x.y-y.y));}))()`);
  assert(errors.every(e=>e<1),'portrait landing '+count+': '+errors);
  if(count===6){await resize(844,390);assert.equal(await run("document.querySelectorAll('.deal-card,.chip-flight,.hole-arrival').length"),0,'rotation cancels movement');assert.equal(await run("document.querySelectorAll('.board .card:not(.blank)').length"),0,'rotation preserves shown board');await resize(390,844);}
  else await until("document.querySelectorAll('.deal-card').length===0");
 }
 await run('window.feed(geometry,true)');
 await resize(844,390);assert(await run("document.querySelector('.table-scene').offsetWidth>=1520"),'landscape restored');
 await resize(1440,900);
 await run("window.savedCard=document.querySelector('.board .card');window.savedFace=window.savedCard.querySelector('.casino-art');true");
 assert.equal(await run("document.querySelectorAll('.timer-ring').length"),1,'actor has an avatar ring');
 assert.equal(await run("document.querySelectorAll('.turn-progress').length"),1,'actor has green timer');
 const progressStart=await run("getComputedStyle(document.querySelector('.timer-ring')).strokeDashoffset");
 await call('Performance.enable');
 const metric=async()=>Object.fromEntries((await call('Performance.getMetrics')).metrics.map(m=>[m.name,m.value]));
 const before=await metric();
 await run(`new Promise(resolve=>{let count=0;const click=()=>{document.querySelector('.own-stack').click();if(++count===30)resolve();else requestAnimationFrame(click);};requestAnimationFrame(click);})`);
 assert(await run("savedCard===document.querySelector('.board .card')&&savedFace===document.querySelector('.board .casino-art')"),'controls must not remount cards');
 const after=await metric();
 const perf=Object.fromEntries(['TaskDuration','ScriptDuration','LayoutDuration','RecalcStyleDuration','LayoutCount','RecalcStyleCount'].map(k=>[k,after[k]-before[k]]));
 assert.notEqual(await run("getComputedStyle(document.querySelector('.timer-ring')).strokeDashoffset"),progressStart,'green timer animates');
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
 assert.equal(await run("document.querySelectorAll('.current-hand-rank').length"),1,'only viewer sees live private hand category');
 // Baseline immediately before the last call: only the public prefix is visible.
 await run('window.feed('+JSON.stringify(rec.at(-2))+',true)');
 await until("document.querySelectorAll('.board .card:not(.blank)').length===0");
 await run(`window.observed=[];window.capture=()=>window.observed.push({board:[...document.querySelectorAll('.board .card:not(.blank)')].map(e=>e.getAttribute('aria-label')),settled:!!document.querySelector('.seat.won,.seat.lost'),cards:[...document.querySelectorAll('.seat.open-cards')].map(e=>e.dataset.player),wins:document.querySelectorAll('.winner-badge').length,shares:[...document.querySelectorAll('.equity-label')].map(e=>e.textContent)});window.observer=new MutationObserver(window.capture);observer.observe(document.querySelector('.table-scene'),{subtree:true,childList:true,attributes:true,characterData:true});`);
 await run('window.feed('+JSON.stringify(rec.at(-1))+')');
 await until("document.querySelectorAll('.seat.open-cards').length===4");
 assert.equal(await run("document.querySelectorAll('.board .card:not(.blank)').length"),0,'all-in cards must precede runout');
 assert(await run("[...document.querySelectorAll('.current-hand-rank')].every(e=>e.textContent==='一對')"),'preflop ranks cannot use future board');
 await shot('all-in-reveal');
 await until("document.querySelectorAll('.board .card:not(.blank)').length===3");
 assert.equal(await run("getComputedStyle(document.querySelector('.board .card')).getPropertyValue('--flip-duration')"),'1300ms','all-in street uses 2000ms without compression');
 await shot('all-in-flop');
 const expected=rec.at(-1).members.map(m=>Number(m.stack).toLocaleString('zh-TW'));
 await until("document.querySelector('.winner-badge') && !document.querySelector('.chip-flight') && JSON.stringify([...document.querySelectorAll('.seat-stack')].map(e=>e.textContent))==="+JSON.stringify(JSON.stringify(expected)));
 assert.equal(await run("document.querySelectorAll('.settlement').length"),0,'table payout summary removed');
 const observed=await run('window.observer.disconnect();window.observed');
 assert(observed.some(v=>v.board.length===3),'flop observed');assert(observed.some(v=>v.board.length===4),'turn observed');
 assert(observed.filter(v=>v.board.length<5).every(v=>!v.settled&&v.wins===0),'no premature result');
 const totals=await run("[...document.querySelectorAll('.seat-stack')].map(e=>e.textContent)");

 assert.deepEqual(totals,expected,'final stacks match server');
 await until("document.querySelectorAll('.board-deal,.board .deal-back').length===0");
 assert(await run("[...document.querySelectorAll('.board .casino-art')].every(e=>e instanceof HTMLImageElement&&e.complete&&e.naturalWidth>0&&new URL(e.src).pathname.startsWith('/assets/cards/casino/')&&getComputedStyle(e).mixBlendMode==='normal'&&getComputedStyle(e).filter==='none')"),'original casino images without tint filters');
 assert(await run(`(()=>{const a=document.querySelector('.hero-seat .equity-label').getBoundingClientRect(),b=document.querySelector('.hero-seat .winner-badge').getBoundingClientRect();return b.top>=a.bottom;})()`),'winner and equity do not overlap');
 await shot('settlement');
 const holdStarted=await run('performance.now()');
 await until("document.querySelectorAll('.winner-badge').length===0");
 const held=(await run('performance.now()'))-holdStarted;
 assert(held>=4000&&held<=4700,'result hold is 4400ms after awards: '+held);
 console.log('Result hold measured after screenshot',Math.round(held),'ms');
 await run('window.feed('+JSON.stringify(rec.at(-1))+')');
 assert.equal(await run("document.querySelectorAll('.chip-flight').length"),0,'duplicate does not replay');
 // Portrait runout, rotation halfway through, and all side-pot outcomes.
 await resize(390,844);
 await run('window.feed('+JSON.stringify(rec.at(-2))+',true);window.feed('+JSON.stringify(rec.at(-1))+')');
 await until("document.querySelectorAll('.seat.open-cards').length===4");
 assert.equal(await run("document.querySelectorAll('.board .card:not(.blank)').length"),0,'portrait reveal precedes board');
 await shot('mobile-equity');
 await until("document.querySelectorAll('.board .card:not(.blank)').length===3");
 await resize(844,390);
 assert.equal(await run("document.querySelectorAll('.board .card:not(.blank)').length"),3,'rotation does not expose river');
 assert.equal(await run("document.querySelectorAll('.winner-badge').length"),0,'rotation does not expose payouts');
 await resize(390,844);
 await until("document.querySelector('.seat.won,.seat.lost')&&document.querySelector('.hero-seat .winner-badge')");
 await until("document.querySelectorAll('.board-deal').length===0");
 assert(await run(`(()=>{const a=document.querySelector('.hero-seat .equity-label').getBoundingClientRect(),b=document.querySelector('.hero-seat .winner-badge').getBoundingClientRect(),v=document.querySelector('.table-viewport').getBoundingClientRect();return b.top>=a.bottom&&b.bottom<=v.bottom;})()`),'portrait winner fits without covering equity');
 await shot('mobile-settlement');
 assert(await run(`(()=>{const board=document.querySelector('.board>.cards').getBoundingClientRect();return [...document.querySelectorAll('.seat-feedback')].every(e=>{const r=e.getBoundingClientRect();return !(r.left<board.right&&r.right>board.left&&r.top<board.bottom&&r.bottom>board.top);});})()`),'result stacks do not cover community cards');

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
 await until("document.querySelector('.seat.won,.seat.lost')");
 assert.equal(await run("document.querySelectorAll('.chip-flight,.deal-card').length"),0,'reduced motion skips queued effects');
 // All six public hands must retain the exact community face, including large mode.
 const six=await run(`(()=>{const s=structuredClone(geometry);s.hand.players.forEach((p,i)=>{p.cards=[['Ah','Kh'],['2c','3c'],['4c','5c'],['6c','7c'],['8c','9c'],['Tc','Jc']][i];});s.hand.payouts={};s.hand.settlement={void:false,pots:[],refunds:{}};return s;})()`);
 for(const [w,h] of [[1920,1080],[1440,900],[1280,720],[1280,580],[320,568],[390,844],[430,932]]){
  await resize(w,h);await run('window.feed('+JSON.stringify(six)+',true)');await until("document.querySelectorAll('.seat.open-cards').length===6 && [...document.querySelectorAll('.seat.open-cards img.casino-art')].every(i=>i.complete&&i.naturalWidth>0)");
  for(const large of [false,true]){
   await run(`document.querySelector('.game').classList.toggle('large-cards',${large})`);
   const failures=await run(`(()=>{const errors=[],board=document.querySelector('.board .card'),bw=board.getBoundingClientRect().width,bh=board.getBoundingClientRect().height;const overlap=(a,b)=>a.left<b.right-.5&&a.right>b.left+.5&&a.top<b.bottom-.5&&a.bottom>b.top+.5;for(const seat of document.querySelectorAll('.seat.open-cards')){const cards=[...seat.querySelectorAll('.seat-cards .card')],rects=cards.map(c=>c.getBoundingClientRect()),plaque=seat.querySelector('.seat-plaque').getBoundingClientRect(),factor=seat.classList.contains('hero-seat')?1.15:1;if(overlap(rects[0],rects[1]))errors.push('overlapping cards '+seat.className);for(const [i,c] of cards.entries()){const art=c.querySelector('img.casino-art');if(!art||!art.complete||!art.naturalWidth||!new URL(art.src).pathname.startsWith('/assets/cards/casino/'))errors.push('missing casino artwork');if(Math.abs(rects[i].width/bw-factor)>.01||Math.abs(rects[i].height/bh-factor)>.01)errors.push('card scale');if(overlap(rects[i],plaque))errors.push('card/plaque overlap');if(!document.querySelector('.portrait-table'))for(const label of document.querySelectorAll('.seat-feedback,.position-badge,.board-phase'))if(overlap(rects[i],label.getBoundingClientRect()))errors.push('card/info overlap '+label.className);if(!document.querySelector('.portrait-table'))for(const button of document.querySelectorAll('.game-toolbar button'))if(overlap(rects[i],button.getBoundingClientRect()))errors.push('card/toolbar overlap');}}return errors;})()`);
   assert.deepEqual(failures,[],'six-player visible cards '+w+' large='+large);
   const anchorErrors=await run(`(()=>{const errors=[],mobile=!!document.querySelector('.portrait-table'),scale=document.querySelector('.table-scene').getBoundingClientRect().width/document.querySelector('.table-scene').offsetWidth;for(const seat of document.querySelectorAll('.seat:not(.empty)')){const avatar=seat.querySelector('.portrait').getBoundingClientRect(),info=seat.querySelector('.seat-info').getBoundingClientRect(),badge=seat.querySelector('.position-badge'),rank=seat.querySelector('.current-hand-rank');if(!mobile&&seat.classList.contains('n')){const felt=document.querySelector('.felt').getBoundingClientRect();if(Math.abs(avatar.top+avatar.height/2-felt.top)>1)errors.push('occupied north rail anchor');}if(badge){const b=badge.getBoundingClientRect();if(Math.abs(b.x+b.width/2-avatar.x-avatar.width/2)>1||b.top>=avatar.bottom||b.bottom<=avatar.bottom)errors.push('position badge anchor');}if(rank){rank.textContent='皇家同花順';const r=rank.getBoundingClientRect();for(const other of document.querySelectorAll('.seat-cards,.seat-feedback,.board,.board-phase')){const o=other.getBoundingClientRect();if(r.left<o.right-.5&&r.right>o.left+.5&&r.top<o.bottom-.5&&r.bottom>o.top+.5)errors.push('rank overlaps '+seat.className+' / '+other.parentElement.className+' / '+other.className);}if(r.bottom>avatar.top||Math.abs(r.x+r.width/2-avatar.x-avatar.width/2)>1)errors.push('rank anchor');if(parseFloat(getComputedStyle(rank).fontSize)*scale<(mobile?11.9:15.9)||rank.scrollHeight>rank.clientHeight+1)errors.push('rank readability');}for(const label of seat.querySelectorAll('.equity-label,.action-label:not(.empty-label)')){if(getComputedStyle(label).display==='none'||getComputedStyle(label).visibility==='hidden')continue;const l=label.getBoundingClientRect();if(Math.abs(l.left-info.left)>1||Math.abs(l.width-info.width)>1||l.top<info.bottom)errors.push('status anchor');if(parseFloat(getComputedStyle(label).fontSize)*scale<(mobile?11.9:15.9))errors.push('status readability');}}return errors;})()`);
   assert.deepEqual(anchorErrors,[],'shared seat anchors '+w+' large='+large);
   const resultErrors=await run(`(()=>{const errors=[];for(const feedback of document.querySelectorAll('.seat-feedback')){let winner=feedback.querySelector('.winner-badge');if(!winner){winner=document.createElement('span');winner.className='winner-badge';winner.innerHTML='WINNER<small>派彩 1,000</small>';feedback.append(winner);}const r=winner.getBoundingClientRect();for(const other of document.querySelectorAll('.board>.cards,.pot,.seat-cards,.portrait,.seat-info,.seat-bet,.board-phase')){const o=other.getBoundingClientRect();if(r.left<o.right-.5&&r.right>o.left+.5&&r.top<o.bottom-.5&&r.bottom>o.top+.5)errors.push(feedback.parentElement.className+' result overlaps '+other.className);}}return errors;})()`);
   assert.deepEqual(resultErrors,[],'reserved results '+w+' large='+large);
   await shot('six-'+w+(large?'-large':''));
  }
 }
 // Match the reported idle table: only the viewer seated, north seat on the rail.
 await resize(1591,793);
 await run("document.querySelector('.game').classList.remove('large-cards');const idle=structuredClone(geometry);idle.hand=null;idle.members=idle.members.filter(m=>m.id==='111111111111111111');window.feed(idle,true)");
 await until("document.querySelector('.seat.n.empty')");
 assert(await run(`(()=>{const r=document.querySelector('.seat.n .empty-seat-button').getBoundingClientRect(),f=document.querySelector('.felt').getBoundingClientRect(),p=document.querySelector('.pot').getBoundingClientRect();return Math.abs(r.top+r.height/2-f.top)<1&&r.bottom<p.top&&f.width/innerWidth>=.85;})()`),'idle north seat sits on rail without covering pot');
 await shot('desktop-idle-expanded');

 // Remove synthetic winner labels inserted by the geometry-only assertions above.
 await run("document.querySelectorAll('.winner-badge').forEach(e=>e.remove())");
 // Persistent autoplay uses explicit acknowledged commands; leaving keeps terminal motion.
 await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
 for(const [w,h] of [[1920,1080],[320,568],[390,844]]){
  await resize(w,h);await run('window.feed(geometry,true)');
  await until("document.querySelector('.hero-seat .portrait')");
  await run("document.querySelector('.hero-seat .own-avatar').click()");
  await until("document.querySelector('dialog[open]')");
  await run("[...document.querySelectorAll('dialog button')].find(b=>b.textContent.includes('啟用託管')).click()");
  await until("commands.at(-1)?.kind==='set_autoplay'&&commands.at(-1)?.enabled===true");
  await run("window.auto=structuredClone(geometry);auto.members.find(m=>m.id==='111111111111111111').autoplay=true;window.feed(auto)");
  await until("document.querySelector('.autoplay-panel button:not(:disabled)')");
  assert(await run(`(()=>{const r=document.querySelector('.autoplay-panel button').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight&&r.height>=44;})()`),'autoplay cancel visible '+w);
  await shot('autoplay-'+w);
  await run("document.querySelector('.autoplay-panel button').click()");
  await until("commands.at(-1)?.kind==='set_autoplay'&&commands.at(-1)?.enabled===false");
  assert.equal(await run("!!document.querySelector('.autoplay-panel')"),true,'no optimistic cancellation');
  await run('window.feed(geometry)');
  await until("!document.querySelector('.autoplay-panel')");
 }
 const departed=structuredClone(rec.at(-1));departed.departure=structuredClone(departed);departed.joined=false;departed.control=false;departed.role='spectator';departed.members=departed.members.filter(m=>m.id!==user);
 for(const [w,h] of [[1920,1080],[390,844]]){
  await resize(w,h);await run('window.feed('+JSON.stringify(rec.at(-2))+',true);window.feed('+JSON.stringify(departed)+')');
  await until("document.querySelectorAll('.seat.open-cards').length===4");
  assert.equal(await run("!!document.querySelector('.spectator-panel')"),false,'leave must retain last hand');
  await until("document.querySelector('.hero-seat.won .winner-badge') && !document.querySelector('.chip-flight') && JSON.stringify([...document.querySelectorAll('.seat-stack')].map(e=>e.textContent))==="+JSON.stringify(JSON.stringify(expected)),16000);
  const start=Date.now();
  assert.equal(await run("!!document.querySelector('.spectator-panel')"),false,'payout must finish before spectator');
  await shot('departing-result-'+w);
  await until("document.querySelector('.spectator-panel')",6000);
  assert(Date.now()-start>=4200,'full result hold before spectator');
  assert.equal(await run("document.querySelectorAll('.hero-seat:not(.empty)').length"),0,'released seat is gone');
  await shot('spectator-'+w);
  await run('window.feed('+JSON.stringify(departed)+')');
  assert.equal(await run("document.querySelectorAll('.chip-flight,.winner-badge').length"),0,'departure duplicate stays silent');
 }


 // A showdown dims exactly the hole cards outside that player's best five.
 for(const [cards,board,unused] of [
  [['4d','2d'],['3h','6h','5h','7d','2h'],['2♦']],
  [['2d','2s'],['3h','4h','5d','6s','7c'],['2♦','2♠']],
  [['As','Ah'],['Ad','Ac','7h','4c','2s'],[]]
 ]){
  const example=await run('structuredClone(geometry)');example.hand.players[0].cards=cards;example.hand.board=board;example.hand.payouts={[user]:'600'};example.hand.settlement={void:false,pots:[{id:'main',amount:'600',winners:[user],awards:{[user]:'600'}}],refunds:{}};
  for(const [width,height] of [[1920,1080],[390,844]]){
   await resize(width,height);await run('window.feed('+JSON.stringify(example)+',true)');
   await until("document.querySelector('.hero-seat .seat-cards .card')?.getAttribute('aria-label')==="+JSON.stringify(cards[0][0]+({d:'♦',s:'♠',h:'♥',c:'♣'})[cards[0][1]]));
   assert.deepEqual(await run("[...document.querySelectorAll('.hero-seat .seat-cards .card.unused')].map(e=>e.getAttribute('aria-label'))"),unused,'unused hole cards '+width);
   if(cards[0]==='4d')await shot('unused-hole-cards-'+width);
  }
 }

 for(const [width,height] of [[1920,1080],[390,844]]) {
  await resize(width,height);
  const j=await run('structuredClone(geometry)');j.game_mode='double_joker';j.hand.game_mode='double_joker';j.hand.players[0].cards=['Xr','2d'];j.hand.board=['Xb','Js','Qs','Ks','3h'];
  [['2c','3c'],['4d','5d'],['6h','7h'],['8c','9c'],['2s','3s']].forEach((cards,i)=>{j.hand.players[i+1].cards=cards;});j.hand.payouts={[user]:'600'};j.hand.settlement={void:false,pots:[{id:'main',amount:'600',winners:[user],awards:{[user]:'600'}}],refunds:{}};
  await run('window.feed('+JSON.stringify(j)+',true)');
  await until("document.querySelector('.hero-seat .card[aria-label=紅鬼牌] img')?.naturalWidth>0");
  assert.equal(await run("document.querySelector('.hero-seat .card[aria-label=紅鬼牌]').classList.contains('unused')"),false);
  assert.equal(await run(`document.querySelector('.hero-seat .card[aria-label="2♦"]').classList.contains('unused')`),true);
  await until("document.querySelector('.board .card[aria-label=黑鬼牌] img')?.naturalWidth>0");
  await until("document.querySelector('.hero-seat .equity-label')?.textContent.includes('100.0%')");
  await shot('joker-showdown-'+width);
  await run("document.querySelector('.pot-tools button').click()");
  await until("document.querySelector('.hand-info')?.textContent.includes('紅鬼牌 → A♠')");
  assert(await run("document.querySelector('.hand-info').textContent.includes('雙鬼牌德州')"));
  await shot('joker-details-'+width);
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await until("!document.querySelector('dialog[open]')");
 }
 assert.deepEqual(errors,[]);
 assert(observed.some(v=>v.board.length===0&&v.shares.some(s=>s.includes('%'))),'preflop worker equity visible before flop');
 fs.writeFileSync(path.join(output,'measurements.json'),JSON.stringify({sizes,observed},null,2));
 console.log('PASS desktop/portrait ratios, ten viewports, mobile drawer/keyboard/invalid drafts, 2-6 player landing and rotation, responsive controls, clean faces, timer, all-in equity/runout, payouts, duplicates, reconnect, reduced motion');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{ws?.close();chrome?.kill();server.close();});
