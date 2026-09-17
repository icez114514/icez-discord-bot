// Local Windows Chrome smoke test against built assets and isolated API/WS fixtures.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'../..'),dist=path.join(root,'poker_web/dist');
const api={
 '/api/account':{user_id:'me',available:'50000',table:'1000',in_flight:'0',settled:'51000',subsidy:{eligible:false,amount:'0',reason:'assets_at_least_5000'}},
 '/api/environment':{environment:'test'},'/api/roles':{tables:true,funds:false},
 '/api/preferences':{theme:'classic_walnut'},'/api/tables':{tables:[],current_table:'table'},
 '/api/table/profiles':{table_id:'table',profiles:[{id:'me',display_name:'Me',avatar_url:'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2280%22 height=%2280%22%3E%3Crect width=%2280%22 height=%2280%22 fill=%22%23396077%22/%3E%3Ccircle cx=%2240%22 cy=%2228%22 r=%2215%22 fill=%22%23eccba0%22/%3E%3Cpath d=%22M12 80V68a28 28 0 0 1 56 0v12%22 fill=%22%23c47370%22/%3E%3C/svg%3E'}]}
};
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost');
 if(api[url.pathname]){res.setHeader('Content-Type','application/json');return res.end(JSON.stringify(api[url.pathname]));}
 const file=path.resolve(dist,'.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname));
 if(!file.startsWith(dist+path.sep)||!fs.existsSync(file)){res.writeHead(404);return res.end();}
 res.setHeader('Content-Type',({'.js':'text/javascript','.css':'text/css','.html':'text/html','.ogg':'audio/ogg'})[path.extname(file)]||'application/octet-stream');fs.createReadStream(file).pipe(res);
});
const fixture=`
window.commands=[];
window.snapshot={id:'table',name:'測試牌桌',rules:{small_blind:'50',big_blind:'100'},version:1,joined:true,closed:false,control:true,owner:'me',event_seq:0,events:[],time_bank:60,
 members:Array.from({length:6},(_,i)=>({id:i?'npc:'+i:'me',seat:i,mode:'active',sitout:false,connected:true,expires:null,stack:'1000',leaving:false,topup:null,notice:null,npc_failures:0})),
 hand:{id:'h1',button:1,street:'flop',turn:1,pot:'100',call_amount:'50',actor:1,deadline:Date.now()/1000+300,extensions:0,payouts:null,board:['As','Kd','7h'],legal:{},
 players:Array.from({length:6},(_,i)=>({id:i?'npc:'+i:'me',stack:'1000',bet:i?'50':'0',paid:'0',cards:i?[]:['Ah','Kh'],folded:false}))}};
window.publish=(patch={})=>{Object.assign(snapshot,patch);snapshot.version++;window.socket.onmessage?.({data:JSON.stringify({type:'state',state:snapshot})});};
window.WebSocket=class { static OPEN=1;readyState=1;constructor(){window.socket=this;setTimeout(()=>{this.onopen?.();this.onmessage?.({data:JSON.stringify({type:'ready',connection:'endpoint',state:snapshot})});},20);}send(){}close(){this.readyState=3;}};
const originalFetch=window.fetch;
window.fetch=(url,options)=>{if(url==='/api/table/commands'){commands.push(JSON.parse(options.body));return Promise.resolve(new Response(JSON.stringify({}),{status:200,headers:{'Content-Type':'application/json'}}));}return originalFetch(url,options);};
`;
const delay=ms=>new Promise(r=>setTimeout(r,ms));let chrome,ws;
(async()=>{
 await new Promise(r=>server.listen(18972,'127.0.0.1',r));
 chrome=spawn(process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--no-first-run','--autoplay-policy=no-user-gesture-required','--remote-debugging-port=19372','--user-data-dir='+path.join(root,'tmp/table-cleanup-chrome'),'about:blank'],{windowsHide:true,stdio:'ignore'});
 let pages;for(let i=0;i<60;i++){try{pages=await(await fetch('http://127.0.0.1:19372/json')).json();break;}catch{await delay(100);}}assert(pages,'Chrome ready');
 ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
 let seq=0;const pending=new Map(),errors=[];
 ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.method==='Runtime.exceptionThrown')errors.push(d.params.exceptionDetails.text);if(d.id){const p=pending.get(d.id);pending.delete(d.id);d.error?p.reject(d.error):p.resolve(d.result);}};
 const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
 const run=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
 const until=async expression=>{const end=Date.now()+10000;while(Date.now()<end){if(await run(expression))return;await delay(60);}throw Error(expression);};
 const click=async label=>{const q=`[...document.querySelectorAll('button')].find(b=>(b.textContent===${JSON.stringify(label)}||b.getAttribute('aria-label')===${JSON.stringify(label)})&&!b.disabled)`;await until(`Boolean(${q})`);await run(`${q}.focus();${q}.click()`);};
 const geometry=()=>run(`['.table-scene','.board .cards','.hero-seat','.seat.n'].map(q=>{const r=document.querySelector(q).getBoundingClientRect();return [r.x,r.y,r.width,r.height];})`);
 const publish=async code=>{await run(code+';publish()');await run('new Promise(requestAnimationFrame)');await run('new Promise(requestAnimationFrame)');};
 await call('Runtime.enable');await call('Page.enable');await call('Page.addScriptToEvaluateOnNewDocument',{source:fixture});
 await call('Page.navigate',{url:'http://127.0.0.1:18972/'});await click('返回目前牌桌');await until("Boolean(document.querySelector('.own-avatar'))");
 assert.equal(await run("document.body.innerText.includes('ICEZ POKER')||document.body.innerText.includes('等待下一手')"),false);
 assert.equal(await run("document.querySelector('.action-panel').inert"),true);
 assert.deepEqual(await run("[...document.querySelectorAll('.preselection button')].map(b=>b.textContent)"),['棄牌／過牌','跟任何注']);
 // BB is a table-wide display preference, never a money conversion.
 await run("document.querySelector('.own-stack').click()");
 assert(await run("[...document.querySelectorAll('.seat-stack,.seat-bet b')].every(e=>e.textContent.includes('BB'))"),'BB does not cover every player');
 assert(await run("document.querySelector('.pot b').textContent.includes('BB')"),'pot not in BB');
 await run("document.querySelector('.own-stack').click()");
 const originalHand=await run('JSON.stringify(snapshot.hand)');
 await publish("snapshot.hand.id='animation-test';snapshot.hand.board=[];snapshot.hand.pot='300';snapshot.hand.players.forEach(p=>p.bet='0')");
 assert(await run("document.querySelectorAll('.pot-chips .chip-pile').length>0"),'collected pot has no chips');
 async function revealBoard(cards) {
  await publish(`snapshot.hand.board=${JSON.stringify(cards)};snapshot.event_seq++;snapshot.events=[{id:'board:'+snapshot.event_seq,seq:snapshot.event_seq,at:Date.now()/1000,hand_id:snapshot.hand.id,kind:'board',board:${JSON.stringify(cards)}}]`);
  await until(`document.querySelectorAll('.board .casino-art').length===${cards.length}`);
 }
 await revealBoard(['As','Kd','7h']);
 assert.equal(await run("document.querySelectorAll('.board-deal').length"),3);
 assert.equal(await run("getComputedStyle(document.querySelector('.board-deal')).animationName"),'board-arrive');
 const firstCard=await run("document.querySelector('.board .card').outerHTML");
 await publish('');
 assert.equal(await run("document.querySelector('.board .card').outerHTML"),firstCard,'same snapshot retriggers deal');
 await revealBoard(['As','Kd','7h','2c']);
 assert.equal(await run("document.querySelectorAll('.board-deal').length"),1);
 await run("document.querySelector('.game').classList.add('reduced-motion')");
 await revealBoard(['As','Kd','7h','2c','9d']);
 assert.equal(await run("getComputedStyle(document.querySelector('.board-deal')).animationName"),'none');
 assert.equal(await run("getComputedStyle(document.querySelector('.deal-back')).display"),'none');
 await run("document.querySelector('.game').classList.remove('reduced-motion')");
 await publish("snapshot.hand.id='lost-event';snapshot.hand.board=[]");
 await revealBoard(['As','Kd','7h']);
 await publish("snapshot.hand.board=['As','Kd','7h','2c'];snapshot.event_seq+=2;snapshot.events=[]");
 await until("document.querySelectorAll('.board .casino-art').length===4");
 assert.equal(await run("document.querySelectorAll('.board-deal').length"),0,'gap must become silent baseline');
 await publish("snapshot.hand.board=['As','Kd','7h','2c','9d'];snapshot.event_seq++;snapshot.server_time=Date.now()/1000;snapshot.events=[{id:'late',seq:snapshot.event_seq,at:Date.now()/1000-10,kind:'board',hand_id:snapshot.hand.id,board:snapshot.hand.board}]");
 await until("document.querySelectorAll('.board .casino-art').length===5");
 assert.equal(await run("document.querySelectorAll('.board-deal').length"),0,'expired event must not freeze board');
 await publish("snapshot.hand.players[1].cards=['Qc','Qd']");
 assert(await run("[...document.querySelectorAll('.card-face')].every(e=>getComputedStyle(e).display!=='none'&&getComputedStyle(e).position==='static')"),'public card artwork hidden or offset');
 await publish("delete snapshot.server_time");
 await publish("snapshot.hand.id='next-hand';snapshot.hand.board=[];snapshot.event_seq+=3;snapshot.events=[{id:'newdeal',seq:snapshot.event_seq-2,at:Date.now()/1000,kind:'deal',hand_id:'next-hand'},{id:'newblind',seq:snapshot.event_seq-1,at:Date.now()/1000,kind:'action',hand_id:'next-hand',user:'me',action:'small_blind',amount:'50'},{id:'newturn',seq:snapshot.event_seq,at:Date.now()/1000,kind:'turn',hand_id:'next-hand',user:'me'}]");
 await until("document.querySelector('.hero-seat .action-label').textContent.includes('小盲')");

 await publish(`snapshot.hand=${originalHand}`);
 // Desktop controls stay visible without scrolling; the table scales uniformly.
 const savedHand=await run('JSON.stringify(snapshot.hand)');
 for(const [width,height] of [[844,540],[601,650],[699,650],[800,650],[1000,650],[1099,650],[1100,650],[1100,500],[1200,540],[1366,768],[1920,1080],[2560,1440],[3440,1440],[3840,2160],[900,1400]]){
  await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
  for(const large of [false,true]){
   await run(`document.querySelector('.game').classList.toggle('large-cards',${large})`);
  for(const idle of [true,false]){
   await publish(idle?'snapshot.hand=null':`snapshot.hand=${savedHand}`);
   assert(await run("[...document.querySelectorAll('.portrait')].every(p=>{const a=p.querySelector('.avatar').getBoundingClientRect(),r=p.getBoundingClientRect();return Math.abs(a.width-a.height)<1&&Math.abs(a.x+a.width/2-r.x-r.width/2)<1&&Math.abs(a.y+a.height/2-r.y-r.height/2)<1})"),`avatar frame misaligned ${width}x${height}`);
   assert(await run("(()=>{const i=document.querySelector('.avatar img'),a=i.closest('.avatar').getBoundingClientRect(),r=i.getBoundingClientRect();return Math.abs(a.x+a.width/2-r.x-r.width/2)<1&&Math.abs(a.y+a.height/2-r.y-r.height/2)<1})()"),'avatar image not centered');
   assert(await run("[...document.querySelectorAll('.seat-cards')].every(c=>{const a=c.closest('.seat').querySelector('.portrait').getBoundingClientRect(),b=c.getBoundingClientRect();return a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top})"),`cards do not overlap own portrait ${width}x${height}`);
   const layout=await run(`(()=>{const rect=q=>{const r=document.querySelector(q).getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}};return {board:rect('.board .cards'),hero:rect('.hero-seat'),scene:rect('.table-scene'),hole:document.querySelector('.hero-seat .seat-cards')?rect('.hero-seat .seat-cards'):null}})()`);
   assert(layout.board.bottom+12<=(layout.hole||layout.hero).y,`board overlaps hero at ${width}x${height}, idle=${idle}: ${JSON.stringify(layout)}`);
   assert(await run("(()=>{const a=document.querySelector('.table-scene').getBoundingClientRect(),b=document.querySelector('.table-stage').getBoundingClientRect();const portrait=document.querySelector('.game').classList.contains('portrait-table');return a.width<=b.width+1&&(portrait||a.height<=b.height+1)&&Math.abs(a.width/a.height-(portrait?390/620:1520/1024))<.001})()"),`table not uniformly fitted ${width}x${height}: ${JSON.stringify(layout)}`);
   assert(Math.abs(layout.scene.x+layout.scene.width/2-(await run("document.documentElement.clientWidth"))/2)<1,`table not centered at ${width}x${height}`);
   assert(layout.scene.x>=3.9&&layout.scene.right<=width-3.9,`missing side gutters ${width}x${height}`);
   assert(await run("(()=>{const b=document.querySelector('.table-action-slot').getBoundingClientRect();return [...document.querySelectorAll('.seat-plaque,.board .cards')].every(e=>{const a=e.getBoundingClientRect(),bottom=Math.min(a.bottom,document.querySelector('.table-viewport').getBoundingClientRect().bottom);return a.right<=b.left||b.right<=a.left||bottom<=b.top||b.bottom<=a.top})})()"),'table collides with controls');
   assert(await run("(()=>{const overlap=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;return [...document.querySelectorAll('.seat-cards')].every(c=>[...document.querySelectorAll('.seat-plaque')].every(p=>c.closest('.seat')===p.closest('.seat')||!overlap(c.getBoundingClientRect(),p.getBoundingClientRect())))})()"),`hand covers another player at ${width}x${height}, idle=${idle}`);
   if(!idle)assert(await run("[...document.querySelectorAll('.position-badge')].every(e=>{const r=e.getBoundingClientRect(),s=document.querySelector('.table-scene').getBoundingClientRect();return r.top>=s.top&&r.left>=0&&r.right<=innerWidth&&r.bottom<=s.bottom})"),`position badge outside viewport at ${width}x${height}`);
   if(!idle)assert(await run("[...document.querySelectorAll('.seat')].every(s=>{const p=s.querySelector('.position-badge'),c=s.querySelector('.seat-bet');if(!p||!c)return true;const a=p.getBoundingClientRect(),b=c.getBoundingClientRect();return a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top})"),`position badge overlaps bet ${width}x${height}`);
   if(!idle){
    await publish("snapshot.hand.payouts={me:'1000'};snapshot.hand.actor=null");
    assert(await run("(()=>{const s=document.querySelector('.settlement').getBoundingClientRect(),b=document.querySelector('.board-phase').getBoundingClientRect();return s.top>=b.top&&s.bottom<=b.bottom})()"),`settlement detached from board at ${width}x${height}, large=${large}`);
    await publish(`snapshot.hand=${savedHand};snapshot.hand.actor=0;snapshot.hand.legal={fold:true,check:true,raise:true,min_raise_to:'100',max_raise_to:'1000'}`);
    assert.equal(await run("document.querySelector('.action-panel').inert"),false);
    assert(await run("[...document.querySelectorAll('.action-buttons button')].filter(b=>b.getBoundingClientRect().width>0).every(b=>{const r=b.getBoundingClientRect();return r.width>=43.9&&r.height>=43.9})"),`small scene hit target ${width}x${height}`);

    if(width<900||height<600) await run("document.querySelector('.action-buttons').scrollIntoView({block:'center'})");
    assert(await run("(()=>{const r=document.querySelector('.action-buttons').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight})()"),`actions unavailable at ${width}x${height}`);
    await run('window.scrollTo(0,0)');
    if(width<900||height<600) await run("document.querySelector('.hero-seat').scrollIntoView({block:'center'})");
    assert(await run("(()=>{const r=document.querySelector('.hero-seat').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight})()"),`hero unreachable at ${width}x${height}`);
    await run("window.scrollTo(0,0)");
    await publish('snapshot.hand.button=0;snapshot.hand.players[0].bet="50"');
    assert(await run("(()=>{const a=document.querySelector('.hero-seat .dealer').getBoundingClientRect(),b=document.querySelector('.hero-seat .seat-bet').getBoundingClientRect();return a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top})()"),'dealer and bet overlap');
   }
  }
  }
 }
 await call('Emulation.setDeviceMetricsOverride',{width:844,height:390,deviceScaleFactor:1,mobile:false});
 await publish(`snapshot.hand=${savedHand};snapshot.hand.actor=0;snapshot.hand.legal={fold:true,call:'50',raise:true,min_raise_to:'100',max_raise_to:'1000'}`);
 await run("document.querySelector('.action-buttons').scrollIntoView({block:'center'})");
 assert(await run("(()=>{const r=document.querySelector('.action-buttons').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight})()"),'short landscape controls unavailable');
 await run('window.scrollTo(0,0)');
 assert(await run("(()=>{const a=document.querySelector('.n .position-badge').getBoundingClientRect(),b=document.querySelector('.table-stage').getBoundingClientRect();return a.top>=b.top&&a.bottom<=b.bottom})()"),'north badge clipped by scroll viewport');
 assert(await run("(()=>{window.scrollTo(0,document.documentElement.scrollHeight);return window.scrollY>0})()"),'short landscape table cannot scroll');
 await run("window.scrollTo(0,0)");
 await run("document.querySelector('.game').classList.remove('large-cards')");
 await call('Emulation.setDeviceMetricsOverride',{width:1200,height:540,deviceScaleFactor:1,mobile:false});
 await publish(`snapshot.hand=${savedHand};snapshot.hand.actor=0;snapshot.hand.button=0;snapshot.hand.players[0].bet='50';snapshot.hand.legal={fold:true,call:'50',raise:true,min_raise_to:'100',max_raise_to:'1000'}`);
 fs.writeFileSync(path.join(root,'tmp/table-docked-controls.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await publish(`snapshot.hand=${savedHand}`);
 fs.writeFileSync(path.join(root,'tmp/table-desktop-fixed.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 fs.writeFileSync(path.join(root,'tmp/table-portrait-desktop.jpg'),Buffer.from((await call('Page.captureScreenshot',{format:'jpeg',quality:75})).data,'base64'));
 const savedMembers=await run('JSON.stringify(snapshot.members)');
 for(const width of [800,1000,1200]){
  await call('Emulation.setDeviceMetricsOverride',{width,height:600,deviceScaleFactor:1,mobile:false});
  await publish(`snapshot.members=JSON.parse(${JSON.stringify(savedMembers)}).filter(m=>m.id==='me'||m.seat===5);snapshot.hand=${savedHand};snapshot.hand.players=snapshot.hand.players.filter(p=>p.id==='me'||p.id==='npc:5');snapshot.hand.actor=0;snapshot.hand.button=1;snapshot.hand.players[0].bet='100';snapshot.hand.players[1].bet='200';snapshot.hand.legal={fold:true,call:'100',raise:true,min_raise_to:'300',max_raise_to:'1000'}`);
  assert(await run("(()=>{const a=document.querySelector('.seat.n').getBoundingClientRect(),b=document.querySelector('.pot').getBoundingClientRect();return a.bottom+8<=b.top})()"),'north empty seat touches pot');
  assert(await run("(()=>{const a=document.querySelector('.board-phase .icon-button').getBoundingClientRect();return [...document.querySelectorAll('.seat-bet,.seat-plaque')].every(e=>{const b=e.getBoundingClientRect();return a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top})})()"),'info button overlaps a bet or player');
  assert(await run("(()=>{const a=document.querySelector('.board .cards').getBoundingClientRect(),b=document.querySelector('.hero-seat .seat-cards').getBoundingClientRect();return a.bottom+12<=b.top})()"),'heads-up board overlaps hole cards');
  await until("[...document.querySelectorAll('.casino-art')].every(i=>i instanceof SVGElement || i.complete&&i.naturalWidth>0)");
  if(width===1000)fs.writeFileSync(path.join(root,'tmp/table-heads-up-casino.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 }
 await run("document.querySelector('.game').classList.add('four-color')");
 await publish("snapshot.hand.board=['Ac','Ad','Ah','As','Tc']");
 await until("[...document.querySelectorAll('.board .casino-art')].every(i=>i instanceof SVGElement || i.complete&&i.naturalWidth>0)");
 assert(await run("['c','d'].every(s=>getComputedStyle(document.querySelector('.board [data-suit='+s+'] .casino-art')).fill===(s==='c'?'rgb(7, 128, 75)':'rgb(25, 91, 199)'))"),'four-color artwork tint missing');
 fs.writeFileSync(path.join(root,'tmp/table-casino-four-color.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await run("document.querySelector('.game').classList.remove('four-color')");
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await publish(`snapshot.members=${savedMembers};snapshot.hand=${savedHand}`);

 for(const [width,height] of [[1440,1000],[844,540],[320,1000]]){
  await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<600});
  for(const status of ["connected=false","sitout=true","leaving=true"]){
   await publish(`snapshot.members=${savedMembers};snapshot.members.forEach(m=>m.${status})`);
   assert(await run("[...document.querySelectorAll('.seat-status .icon-button')].every(e=>{const a=e.getBoundingClientRect(),s=e.closest('.seat');return [...s.querySelectorAll('.seat-cards,.portrait')].every(p=>{const b=p.getBoundingClientRect();return a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top})})"),`status covers cards or avatar ${width} ${status}`);
  }
 }
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await publish(`snapshot.members=${savedMembers}`);
 await publish('snapshot.hand=null;snapshot.members=snapshot.members.filter(m=>m.id==="me")');
 fs.writeFileSync(path.join(root,'tmp/table-desktop-idle-fixed.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await publish(`snapshot.hand=${savedHand};snapshot.members=${savedMembers}`);
 for(const width of [320,390,1440]){
  await call('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<600});
  for(const theme of ['classic_walnut','midnight_oak','burgundy_leather']){
   await run(`document.documentElement.dataset.theme=${JSON.stringify(theme)}`);
   let normalRankSize;
   for(const large of [false,true]){
    await run(`document.querySelector('.game').classList.toggle('large-cards',${large})`);
    await publish("snapshot.hand.actor=1;snapshot.hand.payouts=null;snapshot.hand.legal={};snapshot.hand.pot='0'");
    if(width>=601){
     const rank=await run("document.querySelector('.board .casino-art').getBoundingClientRect().width");
     if(!large)normalRankSize=rank;else assert(rank>normalRankSize,'large cards must enlarge casino artwork');
     assert(await run("(()=>{const s=document.querySelector('.raise-range');return !!s.textContent.trim()&&getComputedStyle(s).display!=='none'})()"),'range text vertically clipped');
    }
    assert(await run("(()=>{const a=document.querySelector('.board .cards').getBoundingClientRect();return [...document.querySelectorAll('.seat-cards')].every(e=>{const b=e.getBoundingClientRect();return a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top})})()"),`board overlaps player cards ${width}/${theme}/${large}`);
    assert(await run("(()=>{const ps=[...document.querySelectorAll('.seat-plaque')].map(e=>e.getBoundingClientRect());return ps.every((a,i)=>ps.slice(i+1).every(b=>a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top))})()"),`player plaques overlap ${width}/${theme}/${large}`);
    assert(await run("[...document.querySelectorAll('.seat-cards')].every(c=>{const a=c.closest('.seat').querySelector('.portrait').getBoundingClientRect(),b=c.getBoundingClientRect();return a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top})"),`cards must overlap own avatar ${width}/${theme}/${large}`);
    assert(await run("[...document.querySelectorAll('.board .card-face')].every(e=>getComputedStyle(e).display!=='none')"),`large mobile card artwork hidden ${width}/${large}`);
    const before=await geometry();
    assert(await run("Math.abs(document.querySelector('.preselection').getBoundingClientRect().top-document.querySelector('.action-panel').getBoundingClientRect().top)<1"),JSON.stringify({width,theme,large,rects:await run("['.preselection','.action-panel','.table-action-slot'].map(q=>{const e=document.querySelector(q),r=e.getBoundingClientRect(),s=getComputedStyle(e);return {q,top:r.top,height:r.height,align:s.alignSelf,margin:s.margin,position:s.position};})")}));
    await publish("snapshot.hand.actor=0;snapshot.hand.legal={fold:true,call:'50',raise:true,min_raise_to:'100',max_raise_to:'1000'};snapshot.hand.pot='999999999999999999999999999999'");
    assert.deepEqual(await geometry(),before,`geometry ${width}/${theme}/${large}`);
    assert.equal(await run("document.querySelector('.action-panel').inert"),false);
    assert(await run("document.documentElement.scrollWidth<=innerWidth"),`overflow ${width}/${theme}/${large}`);
    assert(await run("(()=>{const p=document.querySelector('.pot').getBoundingClientRect(),b=document.querySelector('.board').getBoundingClientRect();return Math.abs(p.x+p.width/2-b.x-b.width/2)<1})()"));
    await publish("snapshot.hand.payouts={me:'1000'}");assert.deepEqual(await geometry(),before);
   }
  }
 }
 await call('Emulation.setDeviceMetricsOverride',{width:320,height:700,deviceScaleFactor:1,mobile:true});
 await publish("snapshot.hand.payouts=null;snapshot.hand.button=0;snapshot.hand.players[0].bet='999999999999999999999999999999';snapshot.hand.actor=0;snapshot.hand.legal={fold:true,call:'50'}");
 assert(await run("document.documentElement.scrollWidth<=innerWidth"),'long mobile bet overflows');
 assert(await run("(()=>{const a=document.querySelector('.hero-seat .dealer').getBoundingClientRect(),b=document.querySelector('.hero-seat .seat-bet').getBoundingClientRect();return a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top})()"),'long mobile bet overlaps BTN');
 assert(await run("(()=>{const r=document.querySelector('.action-buttons').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight})()"),JSON.stringify(await run("['.table-action-slot','.action-panel','.turn-line','.action-buttons'].map(q=>{const r=document.querySelector(q).getBoundingClientRect();return {q,top:r.top,bottom:r.bottom,height:r.height}})")));
 await publish('snapshot.hand.players[0].bet="0";snapshot.hand.button=1');
 await run("document.querySelector('.game').classList.remove('large-cards')");
 await publish("snapshot.hand.actor=1;snapshot.hand.payouts=null;snapshot.hand.pot='100';snapshot.hand.legal={};snapshot.hand.call_amount='50'");
 await click('棄牌／過牌');await click('棄牌／過牌');assert.equal(await run("document.querySelector('.preselection button').getAttribute('aria-pressed')"),'false');
 await click('跟任何注');await publish("snapshot.hand.call_amount='250'");
 await publish("snapshot.hand.actor=0;snapshot.hand.legal={fold:true,call:'250'}");await until('commands.length===1');
 assert.equal(await run('commands[0].action'),'call');await publish('');assert.equal(await run('commands.length'),1);
 await publish("snapshot.hand.actor=1;snapshot.hand.legal={}");await click('棄牌／過牌');
 await publish("snapshot.hand.actor=0;snapshot.hand.legal={fold:true,call:'300'}");await until('commands.length===2');assert.equal(await run('commands[1].action'),'fold');
 await publish("snapshot.hand.actor=1;snapshot.hand.legal={}");await click('跟任何注');
 await publish("snapshot.hand.actor=0;snapshot.hand.legal={fold:true,call:'1000'}");await until("Boolean(document.querySelector('dialog[open]'))");assert.equal(await run('commands.length'),2);await click('取消');
 await click('我的座位選單');await until("document.querySelector('dialog[open]').innerText.includes('本手結束後離桌')");
 await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27,nativeVirtualKeyCode:27});await until("!document.querySelector('dialog[open]')");assert.equal(await run("document.activeElement.className"),'own-avatar');
 await click('我的座位選單');await click('本手結束後離桌');await until('commands.length===3');assert.equal(await run('commands[2].kind'),'leave');
 await publish("snapshot.members[0].leaving=true");await click('我的座位選單');assert(await run("[...document.querySelectorAll('dialog button')].some(b=>b.disabled&&b.textContent==='已排隊離桌')"));await click('關閉');
 await click('牌桌選項');assert.equal(await run("Boolean(document.querySelector('dialog .sound-settings'))"),false);await click('關閉');
 await click('個人設定');assert(await run("Boolean(document.querySelector('dialog .sound-settings'))"));await click('關閉');
 await run("document.querySelector('[aria-label=\"牌桌選項\"]').focus()");await until("Boolean(document.querySelector('[role=tooltip]'))");
 await run("document.activeElement.blur()");
 await run("(()=>{const b=document.querySelector('[aria-label=\"牌桌選項\"]');b.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,pointerType:'touch',clientX:10,clientY:10}));})()");
 await until("Boolean(document.querySelector('[role=tooltip]'))");
 await run("(()=>{const b=document.querySelector('[aria-label=\"牌桌選項\"]');b.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,pointerType:'touch'}));b.click();})()");
 assert.equal(await run("Boolean(document.querySelector('dialog[open]'))"),false);
 await run("document.querySelector('[aria-label=\"牌桌選項\"]').blur();document.querySelector('[aria-label=\"牌桌選項\"]').focus()");
 await until("Boolean(document.querySelector('[role=tooltip]'))");
 await click('我的座位選單');
 await run("(()=>{const d=document.querySelector('dialog[open]'),r=d.getBoundingClientRect();d.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:r.left+2,clientY:r.top+2}));})()");
 assert(await run("Boolean(document.querySelector('dialog[open]'))"),'inside padding stays open');
 await run("(()=>{const d=document.querySelector('dialog[open]'),r=d.getBoundingClientRect();d.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:r.left-5,clientY:r.top-5}));})()");
 await until("!document.querySelector('dialog[open]')");
 await run("(()=>{const b=document.querySelector('[aria-label=\"牌桌選項\"]');b.style.position='fixed';b.style.bottom='0';b.blur();b.focus();})()");
 await until("Boolean(document.querySelector('[role=tooltip]'))");
 assert(await run("document.querySelector('[role=tooltip]').getBoundingClientRect().bottom<=innerHeight"),'bottom tooltip visible');
 await run("document.querySelector('[aria-label=\"牌桌選項\"]').removeAttribute('style');document.activeElement.blur()");
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:1000,deviceScaleFactor:1,mobile:true});
 fs.writeFileSync(path.join(root,'tmp/table-cleanup-mobile.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await publish("snapshot.members[0].leaving=false;snapshot.members=snapshot.members.filter(m=>m.seat!==5)");
 assert.equal(await run("document.querySelector('.empty-seat-button strong').textContent"),'6');
 const botBefore=await run('commands.length');
 await click('在座位 6 加入 Bot');assert.equal(await run('commands.length'),botBefore);await click('取消');
 await click('在座位 6 加入 Bot');await click('確認加入 Bot');await until(`commands.length===${botBefore+1}`);
 assert.equal(await run('commands.at(-1).kind'),'add_npc');assert.equal(await run('commands.at(-1).seat'),5);
 await publish('');await click('在座位 6 加入 Bot');
 await publish("snapshot.members.push({id:'npc:new',seat:5,mode:'pending',stack:'1000',connected:true})");
 assert(await run("[...document.querySelectorAll('dialog button')].find(b=>b.textContent==='確認加入 Bot').disabled"));await click('取消');
 assert.equal(await run("document.querySelectorAll('.position-badge').length"),5);
 assert.equal(await run("document.querySelector('[data-player=\"me\"] .position-badge').textContent"),'CO');
 assert.equal(await run("document.querySelector('.dealer').textContent"),'BTN');
 await publish("snapshot.owner='someone-else';snapshot.members=snapshot.members.filter(m=>m.seat!==5)");
 assert.equal(await run("document.querySelectorAll('.empty-seat-button').length"),0);
 assert.equal(await run("document.querySelector('.empty-seat-number').textContent"),'6');
 assert.deepEqual(errors,[]);console.log('PASS: 15 tablet/desktop viewport sizes with idle/active overlap guards; 18 viewport/theme/font combinations, stable geometry, pot alignment, preselection single-send/all-in guard, avatar leave, settings deduplication, keyboard and long-press hints.');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{ws?.close();chrome?.kill();server.close();});
