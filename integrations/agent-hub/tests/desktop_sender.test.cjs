const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {rendererSender}=require('../zalo_desktop/renderer_sender.cjs');
function fixture({name='Trial',user='123',e2ee=false,fail=false}={}){
 const calls=[];
 const req={s:13,m:{},c:{13:{},fBUP:{exports:{default:{sendZText:async(...a)=>{calls.push(a);if(fail)throw Error('timeout');return {status:200,data:{error_code:0,data:{msgId:'42'}}}}}}},
  Gm1y:{exports:{default:{getGroupByIdSync:()=>({userId:'g123',displayName:name,status:0}),getTypeVisibility:()=>0}}},
  DiYL:{exports:{a:{getUserId:()=>user}}},GpwQ:{exports:{a:{instance:()=>({isOnE2ee:()=>e2ee})}}},
  z0WU:{exports:{default:{getGroupIdFromConversationId:s=>s.slice(1)}}},NMlV:{exports:{a:{next:()=>Date.now()}}}}};
 const chunks=[];chunks.push=function(item){Array.prototype.push.call(this,item);const id=Object.keys(item[1])[0];req.m[id]=item[1][id];req.c[id]={};req.s=id;item[1][id](null,null,req)};
 return {calls,req,chunks,run:input=>vm.runInNewContext('('+rendererSender.toString()+')('+JSON.stringify(input)+')',
  {webpackJsonp:chunks,document:{scripts:[{src:'file:///render.b7bec208c4c8f73e09f8.js'}]}})};
}
const input=()=>({action:'send',thread_id:'g123',display_name:'Trial',user_id:'123',text:'` ${globalThis.attack=true} \\ tiếng Việt\n',client_id:String(Date.now())});
test('exact text argument and group, retry=0, cleanup',async()=>{
 const f=fixture(),p=input(),r=await f.run(p);
 assert.equal(r.state,'submitted');assert.equal(f.calls.length,1);assert.equal(f.calls[0][1],p.text);
 assert.equal(f.calls[0][0],'g123');assert.equal(f.calls[0][4],0);assert.equal(f.chunks.length,0);
 assert.equal(Object.keys(f.req.m).length,0);assert.equal(f.req.s,13);
});
test('renamed group, changed account and E2EE do not send',async()=>{
 for(const options of [{name:'Wrong'},{user:'456'},{e2ee:true}]){
  const f=fixture(options);assert.equal((await f.run(input())).state,'blocked');assert.equal(f.calls.length,0);
 }
});
test('prepare does not send; timeout is uncertain with one call',async()=>{
 const f=fixture();assert.equal((await f.run({...input(),action:'prepare'})).state,'ready');assert.equal(f.calls.length,0);
 const g=fixture({fail:true});assert.equal((await g.run(input())).state,'uncertain');assert.equal(g.calls.length,1);
});
