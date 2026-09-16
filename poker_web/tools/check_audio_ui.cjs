// Browser audio regression: real gestures, default autoplay, real audio and isolated game fixtures.
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
localStorage.removeItem('poker-sound:v1:me');window.commands=[];window.audioPlayed=[];
const startAudio=AudioBufferSourceNode.prototype.start;
AudioBufferSourceNode.prototype.start=function(...args){const data=this.buffer?.getChannelData(0);let sum=0;if(data)for(const x of data)sum+=x*x;audioPlayed.push({duration:this.buffer?.duration,rms:data?Math.sqrt(sum/data.length):0});return startAudio.apply(this,args);};
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
 chrome=spawn(process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--no-first-run','--remote-debugging-port=19372','--user-data-dir='+path.join(root,'tmp/table-cleanup-chrome'),'about:blank'],{windowsHide:true,stdio:'ignore'});
 let pages;for(let i=0;i<60;i++){try{pages=await(await fetch('http://127.0.0.1:19372/json')).json();break;}catch{await delay(100);}}assert(pages,'Chrome ready');
 ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
 let seq=0;const pending=new Map(),errors=[];
 ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.method==='Runtime.exceptionThrown')errors.push(d.params.exceptionDetails.text);if(d.id){const p=pending.get(d.id);pending.delete(d.id);d.error?p.reject(d.error):p.resolve(d.result);}};
 const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
 const run=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
 const until=async expression=>{const end=Date.now()+10000;while(Date.now()<end){if(await run(expression))return;await delay(60);}throw Error(expression);};
 const click=async label=>{const q=`[...document.querySelectorAll('button')].find(b=>(b.textContent===${JSON.stringify(label)}||b.getAttribute('aria-label')===${JSON.stringify(label)})&&!b.disabled)`;await until(`Boolean(${q})`);await run(`${q}.scrollIntoView({block:'center'})`);const r=await run(`(()=>{const r=${q}.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);await call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...r});await call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...r});};
 const geometry=()=>run(`['.table-scene','.board .cards','.hero-seat','.seat.n'].map(q=>{const r=document.querySelector(q).getBoundingClientRect();return [r.x,r.y,r.width,r.height];})`);
 const publish=async code=>{await run(code+';publish()');await run('new Promise(requestAnimationFrame)');await run('new Promise(requestAnimationFrame)');};
 await call('Runtime.enable');await call('Page.enable');await call('Page.addScriptToEvaluateOnNewDocument',{source:fixture});
 await call('Page.navigate',{url:'http://127.0.0.1:18972/'});await click('返回目前牌桌');await until("Boolean(document.querySelector('.own-avatar'))");
 await click('個人設定');
 for(const label of ['御姊','少女','貓娘','試聽動作語音','試聽回合提醒','試聽牌局籌碼','試聽結算勝利','試聽介面提示']) {
   const before=await run('audioPlayed.length'); await click(label);
   await until(`audioPlayed.length===${before+1}`);
   assert(await run('audioPlayed.at(-1).rms>0.0001'),'non-silent decoded audio '+label);
 }
 await click('關閉');
 const before=await run('audioPlayed.length');
 await publish("snapshot.event_seq=1;snapshot.events=[{id:'a1',seq:1,kind:'action',hand_id:'h1',user:'npc:1',action:'call',amount:'50',at:Date.now()/1000}]");
 await until(`audioPlayed.length===${before+2}`);
 await publish("snapshot.event_seq=2;snapshot.events.push({id:'a2',seq:2,kind:'board',hand_id:'h1',street:'turn',at:Date.now()/1000})");
 await until(`audioPlayed.length===${before+3}`);
 await publish("snapshot.event_seq=3;snapshot.events.push({id:'a3',seq:3,kind:'turn',hand_id:'h1',user:'me',at:Date.now()/1000})");
 await until(`audioPlayed.length===${before+4}`);
 assert(await run('audioPlayed.every(a=>a.rms>0.0001)'));
 await click('關閉音效');
 const muted=await run('audioPlayed.length');
 await publish("snapshot.event_seq=4;snapshot.events.push({id:'a4',seq:4,kind:'action',hand_id:'h1',user:'npc:1',action:'bet',amount:'50',at:Date.now()/1000})");
 await run('new Promise(resolve=>setTimeout(resolve,500))');assert.equal(await run('audioPlayed.length'),muted);
 assert.deepEqual(errors,[]);console.log('PASS: trusted browser gestures, all 3 voice packs and 5 category previews, non-silent decoded audio, live action voice/chips/board/turn cues, mute respected.');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{ws?.close();chrome?.kill();server.close();});
