import fs from 'node:fs';
export async function evaluate(expression){
 const pages=await (await fetch('http://127.0.0.1:54329/json/list',{signal:AbortSignal.timeout(5000)})).json();
 const page=pages.find(p=>p.type==='page' && p.url?.startsWith('https://web.whatsapp.com/'));
 if(!page)throw new Error('WhatsApp Desktop target missing');
 const endpoint=new URL(page.webSocketDebuggerUrl);
 if(!['127.0.0.1','localhost'].includes(endpoint.hostname)||endpoint.port!=='54329')throw new Error('Unexpected endpoint');
 const ws=new WebSocket(endpoint);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
 try{return await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(new Error('CDP timeout; outcome unknown')),45000);
  ws.onmessage=e=>{const r=JSON.parse(e.data);if(r.id!==1)return;clearTimeout(timer);if(r.error||r.result?.exceptionDetails)reject(new Error('Desktop evaluation failed'));else resolve(r.result.result.value);};
  ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{expression,awaitPromise:true,returnByValue:true}}));
 });}finally{ws.close();}
}
if(process.argv[1]?.endsWith('wa-cdp.mjs'))console.log(JSON.stringify(await evaluate(fs.readFileSync(process.argv[2],'utf8'))));
