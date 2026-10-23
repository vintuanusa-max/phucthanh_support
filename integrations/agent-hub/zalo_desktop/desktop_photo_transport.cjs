const net=require('node:net');
const {rendererSender}=require('./renderer_photo.cjs');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const open=()=>new Promise(resolve=>{const s=net.connect({host:'127.0.0.1',port:9229});
  s.setTimeout(300);s.on('connect',()=>{s.destroy();resolve(true)});
  s.on('error',()=>resolve(false));s.on('timeout',()=>{s.destroy();resolve(false)});});
async function run(input){
  let ws,seq=0,activated=false,result={state:'uncertain',detail:'Transport interrupted'};
  const pending=new Map();
  const call=(method,params)=>new Promise((resolve,reject)=>{
    const id=++seq,timer=setTimeout(()=>{pending.delete(id);reject(Error('timeout'))},45000);
    pending.set(id,m=>{clearTimeout(timer);m.error?reject(Error('protocol')):resolve(m.result)});
    ws.send(JSON.stringify({id,method,params}));
  });
  try{
    if(await open()) return {state:'blocked',detail:'Inspector port busy',cleanup:true};
    if(!Number.isSafeInteger(input.pid)||input.pid<1) return {state:'blocked',detail:'Invalid process',cleanup:true};
    process._debugProcess(input.pid);activated=true;
    for(let i=0;i<20 && !(await open());i++)await delay(200);
    const list=await(await fetch('http://127.0.0.1:9229/json/list',{signal:AbortSignal.timeout(3000)})).json();
    if(list.length!==1)throw Error('target');
    const url=new URL(list[0].webSocketDebuggerUrl);
    if(url.hostname!=='127.0.0.1'||url.port!=='9229')throw Error('host');
    ws=new WebSocket(url);
    ws.onmessage=e=>{const m=JSON.parse(e.data);if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};
    await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('connect')),3000);
      ws.onopen=()=>{clearTimeout(timer);resolve()};ws.onerror=()=>{clearTimeout(timer);reject(Error('connect'))};});
    const identity=await call('Runtime.evaluate',{expression:'({pid:process.pid,exe:process.execPath,electron:process.versions.electron})',returnByValue:true});
    const who=identity.result?.value;
    if(who?.pid!==input.pid || who.exe.toLowerCase()!==input.zalo_exe.toLowerCase() || who.electron!=='22.3.9')throw Error('identity');
    // Failsafe cleanup even if the transport process disappears.
    await call('Runtime.evaluate',{expression:"globalThis.__ptInspectorWatchdog=setTimeout(()=>{delete globalThis.__ptInspectorWatchdog;process.mainModule.require('inspector').close()},60000);globalThis.__ptInspectorWatchdog.unref(); true",returnByValue:true});
    const renderer='('+rendererSender.toString()+')('+JSON.stringify(input)+')';
    const selector="Array.from(document.scripts).some(s=>s.src.split('?')[0].endsWith('/render.f32c58b63b6f4273a8a4.js'))";
    const expr="(async()=>{const all=process.mainModule.require('electron').webContents.getAllWebContents();let chosen=null;for(const w of all){const yes=await w.executeJavaScript("+JSON.stringify(selector)+");if(yes){if(chosen)throw Error('Multiple renderers');chosen=w;}}if(!chosen)return {state:'blocked',detail:'Main renderer unavailable'};return chosen.executeJavaScript("+JSON.stringify(renderer)+");})()";
    const r=await call('Runtime.evaluate',{expression:expr,returnByValue:true,awaitPromise:true});
    if(!r.exceptionDetails && r.result?.value)result=r.result.value;
    else if(r.exceptionDetails)result={state:input.action==='prepare'?'blocked':'uncertain',detail:'Renderer evaluation failed'};
  }catch{result={state:input.action==='prepare'?'blocked':'uncertain',detail:'Desktop transport failed; no automatic retry'};}
  finally{
    if(ws?.readyState===WebSocket.OPEN){
      try{await call('Runtime.evaluate',{expression:"clearTimeout(globalThis.__ptInspectorWatchdog);delete globalThis.__ptInspectorWatchdog;setTimeout(()=>process.mainModule.require('inspector').close(),150); true",returnByValue:true})}catch{}
      ws.close();
    }
    if(activated){await delay(400);result.cleanup=!(await open());}
  }
  return result;
}
if(require.main===module){
  let raw='';process.stdin.setEncoding('utf8');process.stdin.on('data',s=>{raw+=s;if(raw.length>7500000)process.exit(2)});
  process.stdin.on('end',async()=>{try{console.log(JSON.stringify(await run(JSON.parse(raw))))}catch{console.log(JSON.stringify({state:'uncertain',detail:'Invalid transport request',cleanup:false}))}});
}
module.exports={run};
