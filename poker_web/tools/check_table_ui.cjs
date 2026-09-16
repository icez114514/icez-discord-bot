// Local Windows Chrome smoke test against built assets and isolated API/WS fixtures.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'../..'),dist=path.join(root,'poker_web/dist');
const api={
 '/api/account':{user_id:'me',available:'50000',table:'1000',in_flight:'0',settled:'51000',subsidy:{eligible:false,amount:'0',reason:'assets_at_least_5000'}},
 '/api/environment':{environment:'test'},'/api/roles':{tables:true,funds:false},
 '/api/preferences':{theme:'classic_walnut'},'/api/tables':{tables:[],current_table:'table'},
 '/api/table/profiles':{table_id:'table',profiles:[{id:'me',display_name:'Me',avatar_url:''}]}
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
 // Short desktop viewports must scroll instead of compressing the board into seats.
 const savedHand=await run('JSON.stringify(snapshot.hand)');
 for(const [width,height] of [[1100,500],[1200,540],[1366,768],[1920,1080],[2560,1440]]){
  await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
  for(const large of [false,true]){
   await run(`document.querySelector('.game').classList.toggle('large-cards',${large})`);
  for(const idle of [true,false]){
   await publish(idle?'snapshot.hand=null':`snapshot.hand=${savedHand}`);
   const layout=await run(`(()=>{const rect=q=>{const r=document.querySelector(q).getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}};return {board:rect('.board .cards'),hero:rect('.hero-seat'),scene:rect('.table-scene'),hole:document.querySelector('.hero-seat .seat-cards')?rect('.hero-seat .seat-cards'):null}})()`);
   assert(layout.board.bottom+12<=(layout.hole||layout.hero).y,`board overlaps hero at ${width}x${height}, idle=${idle}: ${JSON.stringify(layout)}`);
   assert(layout.scene.width/layout.scene.height<=2.6,`table too flat at ${width}x${height}`);
   if(!idle){
    await publish("snapshot.hand.payouts={me:'1000'};snapshot.hand.actor=null");
    assert(await run("(()=>{const s=document.querySelector('.settlement').getBoundingClientRect(),b=document.querySelector('.board-phase').getBoundingClientRect();return s.top>=b.top&&s.bottom<=b.bottom})()"),`settlement detached from board at ${width}x${height}, large=${large}`);
    await publish(`snapshot.hand=${savedHand};snapshot.hand.actor=0;snapshot.hand.legal={fold:true,check:true,raise:true,min_raise_to:'100',max_raise_to:'1000'}`);
    assert.equal(await run("document.querySelector('.action-panel').inert"),false);
    await run("document.querySelector('.action-buttons').scrollIntoView({block:'end'})");
    assert(await run("(()=>{const r=document.querySelector('.action-buttons').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight})()"),`actions unreachable at ${width}x${height}`);
    await run('scrollTo(0,0)');
   }
  }
  }
 }
 await run("document.querySelector('.game').classList.remove('large-cards')");
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await publish(`snapshot.hand=${savedHand}`);
 fs.writeFileSync(path.join(root,'tmp/table-desktop-fixed.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 const savedMembers=await run('JSON.stringify(snapshot.members)');
 await publish('snapshot.hand=null;snapshot.members=snapshot.members.filter(m=>m.id==="me")');
 fs.writeFileSync(path.join(root,'tmp/table-desktop-idle-fixed.png'),Buffer.from((await call('Page.captureScreenshot',{format:'png'})).data,'base64'));
 await publish(`snapshot.hand=${savedHand};snapshot.members=${savedMembers}`);
 for(const width of [320,390,1440]){
  await call('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<600});
  for(const theme of ['classic_walnut','midnight_oak','burgundy_leather']){
   await run(`document.documentElement.dataset.theme=${JSON.stringify(theme)}`);
   for(const large of [false,true]){
    await run(`document.querySelector('.game').classList.toggle('large-cards',${large})`);
    await publish("snapshot.hand.actor=1;snapshot.hand.payouts=null;snapshot.hand.legal={};snapshot.hand.pot='0'");
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
 assert.deepEqual(errors,[]);console.log('PASS: 5 desktop viewport sizes with idle/active overlap guards; 18 viewport/theme/font combinations, stable geometry, pot alignment, preselection single-send/all-in guard, avatar leave, settings deduplication, keyboard and long-press hints.');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{ws?.close();chrome?.kill();server.close();});
