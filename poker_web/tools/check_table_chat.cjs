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
 // Chat runs outside the poker snapshot and keeps the game geometry unchanged.
 await resize(1920,1080);
 await run(`window.chatRequests=[];window.chatFail=false;window.chatSeq=0;const oldChatFetch=window.fetch;window.fetch=async(url,opts)=>{if(String(url).endsWith('/api/table/chat')){const p=JSON.parse(opts.body);chatRequests.push(p);if(chatFail)throw Error('lost acknowledgement');return new Response(JSON.stringify({receipt:{id:'sent',sequence:++chatSeq,table_id:p.table_id}}),{status:200});}return oldChatFetch(url,opts);};window.feedChat=(messages,initial=false)=>socket.onmessage({data:JSON.stringify({type:'chat',table_id:'main',sequence:messages.at(-1)?.sequence??0,messages,initial,closed:false})});window.chatMessage=n=>({id:'chat'+n,sequence:n,author:{id:'peer',display_name:'同桌玩家'},created_at:0,text:n===1?'<img src=x onerror=alert(1)> https://example.com':'訊息 '+n,client_message_id:'chat'+n});window.feedChat([chatMessage(1)],true);`);
 await until("document.querySelector('.chat-preview-lines')?.textContent.includes('<img')");
 assert.equal(await run("document.querySelectorAll('.chat-preview-lines img,.chat-preview-lines a').length"),0,'chat remains plain text');
 const gameBefore=await run("JSON.stringify([document.querySelector('.felt').getBoundingClientRect().toJSON(),document.querySelector('.hero-seat').getBoundingClientRect().toJSON()])");
 await run("feedChat([chatMessage(2),chatMessage(3),chatMessage(4)])");
 await until("document.querySelector('.table-chat-preview b')?.textContent==='3'");
 assert.equal(await run("JSON.stringify([document.querySelector('.felt').getBoundingClientRect().toJSON(),document.querySelector('.hero-seat').getBoundingClientRect().toJSON()])"),gameBefore,'chat does not resize table');
 for(const [w,h] of [[1920,1080],[1280,580],[853,480],[320,568],[360,780],[390,844],[430,932]]){
  await resize(w,h);
  const bounds=await run(`(()=>{const e=document.querySelector('.table-chat-preview'),a=e.getBoundingClientRect(),b=document.querySelector('.table-action-slot').getBoundingClientRect(),hero=document.querySelector('.hero-seat .seat-info').getBoundingClientRect();return {visible:a.x>=0&&a.y>=0&&a.right<=innerWidth&&a.bottom<=innerHeight,overlap:Math.min(a.right,b.right)>Math.max(a.left,b.left)&&Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top)};})()`);
  assert(bounds.visible,'chat in viewport '+w);assert(!bounds.overlap,'chat avoids betting dock '+w);
  assert.equal(await run("document.querySelectorAll('.chat-preview-lines>span').length"),3,'three preview rows');
  await shot('chat-'+w);
  if(w<900||h<=650){await run("document.querySelector('.table-chat-preview').click()");await until("document.querySelector('dialog.table-chat-dialog[open]')");assert(await run("document.querySelector('.chat-compose input').getBoundingClientRect().width>150"),'readable input '+w);await shot('chat-expanded-'+w);await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await until("!document.querySelector('dialog[open]')");}
 }
 await resize(390,844);await run("document.querySelector('.table-chat-preview').focus();document.querySelector('.table-chat-preview').click()");
 await run("feedChat(Array.from({length:100},(_,i)=>chatMessage(i+3)))");
 await until("document.querySelectorAll('.chat-messages p').length===100");
 await run("document.querySelector('.chat-messages').scrollTop=0;document.querySelector('.chat-messages').dispatchEvent(new Event('scroll',{bubbles:true}))");
 await run("feedChat([chatMessage(103)])");await until("document.querySelector('.chat-new')");
 assert(await run("document.querySelector('.chat-messages').scrollTop<50"),'reading old messages does not jump');
 await run("document.querySelector('.chat-new').click()");
 await until("!document.querySelector('.chat-new')");
 await call('Input.dispatchMouseEvent',{type:'mousePressed',x:3,y:200,button:'left',clickCount:1});
 await call('Input.dispatchMouseEvent',{type:'mouseReleased',x:3,y:200,button:'left',clickCount:1});
 await until("!document.querySelector('dialog[open]')");
 assert(await run("document.activeElement===document.querySelector('.table-chat-preview')"),'focus returns to chat button');
 await run("document.querySelector('.table-chat-preview').click()");
 await run(`const input=document.querySelector('[aria-label="聊天訊息"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'草稿 😀');input.dispatchEvent(new Event('input',{bubbles:true}));`);
 await until("document.querySelector('[aria-label=\"聊天訊息\"]').value==='草稿 😀'");
 assert(await run(`(()=>{const e=new KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true,cancelable:true});document.querySelector('[aria-label="聊天訊息"]').dispatchEvent(e);return e.defaultPrevented;})()`),'IME Enter prevented');
 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await run("document.querySelector('.table-chat-preview').click()");
 assert.equal(await run("document.querySelector('[aria-label=\"聊天訊息\"]').value"),'草稿 😀','draft survives closing');
 await run("chatFail=true;document.querySelector('.chat-compose').requestSubmit()");
 await until("document.querySelector('.chat-error')?.textContent.includes('尚未確認')");
 await run("chatFail=false;document.querySelector('.chat-compose').requestSubmit()");
 await until("document.querySelector('[aria-label=\"聊天訊息\"]').value===''");
 assert.equal(await run('chatRequests.length'),2);
 assert(await run('chatRequests[0].client_message_id===chatRequests[1].client_message_id'),'retry same id');
 await resize(390,380);await until("document.querySelector('.chat-compose button').getBoundingClientRect().bottom<=innerHeight");await shot('chat-keyboard');
 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 console.log('PASS chat plain text, unread, unchanged table, dock bounds, IME, draft, retry id, mobile keyboard');

 assert.deepEqual(errors,[]);
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{ws?.close();chrome?.kill();server.close();});
