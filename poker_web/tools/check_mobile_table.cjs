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

 const original=await run('structuredClone(snapshot)');
 const visible=async()=>await run(`(()=>{const v=document.querySelector('.table-viewport'),r=v.getBoundingClientRect(),errors=[];for(const e of document.querySelectorAll('.seat-cards,.seat-plaque,.seat-feedback,.board>.cards,.winner-badge')){const b=e.getBoundingClientRect();if(b.top<r.top-.5||b.bottom>r.bottom+.5||b.left<r.left-.5||b.right>r.right+.5)errors.push(e.parentElement.className+' '+e.className+' outside '+JSON.stringify(b.toJSON()));}if(v.scrollHeight>v.clientHeight+1||v.scrollWidth>v.clientWidth+1||document.documentElement.scrollHeight>innerHeight+1)errors.push('scrollable');return errors;})()`);
 for(const [w,h] of [[320,568],[360,640],[360,780],[390,844],[430,932]]){
  await resize(w,h);
  for(const opened of [false,true])for(const large of [false,true]){
   await run(`var s=structuredClone(${JSON.stringify(original)});if(${opened})s.hand.players.forEach((p,i)=>p.cards=[['Ah','Kh'],['2c','3c'],['4c','5c'],['6c','7c'],['8c','9c'],['Tc','Jc']][i]);feed(s,true);`);
   await until("document.querySelectorAll('.seat:not(.empty)').length===6");
   await run(`document.querySelector('.game').classList.toggle('large-cards',${large});`);
   assert.deepEqual(await visible(),[],'all visible '+w+' opened='+opened+' large='+large);
   const collisions=await run(`(()=>{const errors=[],overlap=(a,b)=>a.left<b.right-.8&&a.right>b.left+.8&&a.top<b.bottom-.8&&a.bottom>b.top+.8;for(const card of document.querySelectorAll('.seat-cards'))for(const other of document.querySelectorAll('.seat-plaque,.board>.cards,.pot'))if(overlap(card.getBoundingClientRect(),other.getBoundingClientRect()))errors.push(card.parentElement.className+' card overlaps '+other.parentElement.className+' '+other.className);return errors;})()`);
   assert.deepEqual(collisions,[],'cards clear '+w);
   await run("document.querySelectorAll('.seat-info strong').forEach(e=>e.textContent='很長的玩家名字 Long Player');document.querySelectorAll('.seat-feedback').forEach(e=>{e.innerHTML='<span class=equity-label>勝率 100.0%</span><span class=winner-badge>WINNER<small>派彩 1,000</small></span>';})");
   assert.deepEqual(await visible(),[],'results visible '+w);
   const resultCollisions=await run(`(()=>{const errors=[],overlap=(a,b)=>a.left<b.right-.8&&a.right>b.left+.8&&a.top<b.bottom-.8&&a.bottom>b.top+.8;for(const winner of document.querySelectorAll('.winner-badge'))for(const other of document.querySelectorAll('.seat-cards,.portrait,.seat-info,.pot,.board>.cards,.seat-bet'))if(overlap(winner.getBoundingClientRect(),other.getBoundingClientRect()))errors.push(winner.parentElement.parentElement.className+' winner overlaps '+other.parentElement.className+' '+other.className);return errors;})()`);
   if(resultCollisions.length){await shot('mobile-fit-failure');console.log(await run(`[...document.querySelectorAll('.seat-feedback,.winner-badge')].map(e=>({c:e.className,r:e.getBoundingClientRect().toJSON(),top:getComputedStyle(e).top,bottom:getComputedStyle(e).bottom}))`));}
   assert.deepEqual(resultCollisions,[],'results do not overlap '+w);
   await shot('mobile-fit-'+w+(opened?'-showdown':'-hidden')+(large?'-large':''));
   await run("document.querySelector('.table-viewport').scrollTop=100;window.scrollTo(0,100)");
   assert(await run("window.scrollY===0&&document.querySelector('.table-viewport').scrollTop===0"),'cannot scroll');
  }
 }
 // Fresh route prevents direct DOM test fixtures from interfering with React reconciliation.
 await call('Page.navigate',{url:'http://127.0.0.1:18979/'});await until("!!document.querySelector('.home-return')");await run("document.querySelector('.home-return').click()");await until("document.querySelector('.own-avatar')");
 await run("document.querySelector('.hero-seat .own-avatar').click()");await until("document.querySelector('.seat-details')?.textContent.includes('牌型')");assert(await run("document.querySelector('dialog').textContent.includes('啟用託管')"),'own actions retained');
 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await run("document.querySelector('.seat.n .own-avatar').click()");await until("document.querySelector('.seat-details')");assert.equal(await run("document.querySelectorAll('.seat-details .card').length"),0,'private opponents stay hidden');
 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await resize(844,390);assert(await run("!document.querySelector('.portrait-table')&&!!document.querySelector('.table-chat-toggle')"),'landscape compact chat');
 await resize(390,844);assert.deepEqual(await visible(),[],'rotation restores fit');
 assert.deepEqual(errors,[]);console.log('PASS mobile all seats, public/private cards, results, long names, large mode, no scrolling, details and rotation');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{ws?.close();chrome?.kill();server.close();});
