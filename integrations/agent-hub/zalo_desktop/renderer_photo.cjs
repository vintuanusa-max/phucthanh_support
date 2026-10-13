async function rendererSender(input) {
  const blocked=detail=>({state:'blocked',detail});
  if(!['prepare','send'].includes(input.action)||input.thread_id!=='g3307527274697028144')return blocked('Invalid destination');
  const chunks=globalThis.webpackJsonp,marker='__pt_print_'+Date.now();let req,blob;
  const item=[[],{[marker]:(m,e,r)=>{req=r}},[[marker]]];
  try {
    chunks.push(item);
    if(String(req.c.DiYL.exports.a.getUserId())!==input.user_id)return blocked('Account changed');
    const groups=req.c.Gm1y.exports.default,group=groups.getGroupByIdSync(input.thread_id);
    if(!group||group.userId!==input.thread_id||group.status!==0||groups.getTypeVisibility(input.thread_id)!==0)return blocked('Group unavailable');
    if(req.c.GpwQ.exports.a.instance().isOnE2ee(input.thread_id))return blocked('E2EE unsupported');
    const def=req('Mf3M').a,processor=req('jDHv').ModuleContainer.resolve(def.IPhotoMessageProcessorDef);
    if(input.action==='prepare'&&!input.image_base64)return {state:'ready'};
    if(typeof input.image_base64!=='string'||input.image_base64.length>7000000||!input.image_base64.startsWith('iVBOR'))return blocked('Invalid PNG');
    const cid=req.c.NMlV.exports.a.next();
    const bytes=Uint8Array.from(atob(input.image_base64),c=>c.charCodeAt(0));
    const file=new File([bytes],'CHOT-IN.png',{type:'image/png'});
    const photo=await processor.process(file,{clientId:cid,shouldEncodeJxl:false,photoResolutionMode:def.PHOTO_RESOLUTION_MODE.ORIGINAL});
    blob=photo.blobUrl;
    if(input.action==='prepare')return {state:'ready',width:photo.width,height:photo.height,size:photo.file.size};
    if(typeof input.caption!=='string'||input.caption.length>4000)return blocked('Invalid caption');
    const content={...photo,img:blob,name:photo.file.name,title:input.caption,jxlStatus:0,photoResolutionMode:def.PHOTO_RESOLUTION_MODE.ORIGINAL};
    const message=new (req('4HQc').c)(input.user_id,input.thread_id,cid,cid,2,true,{photos:[content]});
    try {
      const result=await req('dThN').default.sendMsgObject(message,null,null,0,true);
      const id=result?.msgId||result?.msg_id||result?.data?.msgId;
      return {state:id?'confirmed':'submitted',message_id:id?String(id):'',client_id:String(cid)};
    }catch{return {state:'uncertain',client_id:String(cid)};}
  }catch{return blocked('Photo preparation failed');}
  finally {
    if(blob?.startsWith('blob:'))URL.revokeObjectURL(blob);
    if(req){delete req.c[marker];delete req.m[marker];req.s=13;}
    const i=chunks.indexOf(item);if(i>=0)chunks.splice(i,1);
  }
}
module.exports={rendererSender};
