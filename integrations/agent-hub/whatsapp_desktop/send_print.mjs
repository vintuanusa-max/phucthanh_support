import {evaluate} from './cdp.mjs';
let input='';for await(const chunk of process.stdin){input+=chunk;if(input.length>7000000)throw Error('Size limit');}
const job=JSON.parse(input);
if(job.thread_id!=='120363407119559834@g.us'||!job.caption||job.image_base64.length>5592408)throw Error('Invalid delivery');
const result=await evaluate(`(async()=>{
 const chat=require('WAWebCollections').Chat.get(${JSON.stringify(job.thread_id)});
 if(!chat||chat.id._serialized!==${JSON.stringify(job.thread_id)})throw Error('Destination mismatch');
 const bytes=Uint8Array.from(atob(${JSON.stringify(job.image_base64)}),c=>c.charCodeAt(0));
 const file=new File([bytes],'chot-in.png',{type:'image/png'});
 const opaque=await require('WAWebMediaOpaqueData').createFromData(file,file.type);
 const prep=require('WAWebPrepRawMedia').prepRawMedia(opaque,{asDocument:false});await prep.waitForPrep();
 const sent=await prep.sendToChat({chat,options:{caption:${JSON.stringify(job.caption)}}});
 const msg=sent?.msg;
 return {state:msg?.ack>=1?'confirmed':'submitted',message_id:msg?.id?.toString?.()||'',ack:msg?.ack??0};
})()`);
console.log(JSON.stringify(result));
