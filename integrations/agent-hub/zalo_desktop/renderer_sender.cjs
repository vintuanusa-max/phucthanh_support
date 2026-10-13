// Version-pinned adapter. Data arrives as an argument, never as JavaScript source.
async function rendererSender(input) {
  const blocked = detail => ({state:'blocked', detail});
  if (!['prepare','send'].includes(input.action)) return blocked('Invalid action');
  if (!/^g[0-9]+$/.test(input.thread_id) || !input.display_name) return blocked('Missing group mapping');
  if (typeof input.text !== 'string' || !input.text.trim() || input.text.length > 8000) return blocked('Unsupported text');
  const chunks = globalThis.webpackJsonp;
  if (!Array.isArray(chunks) || !Array.from(document.scripts).some(s =>
    /\/render\.b7bec208c4c8f73e09f8\.js(?:$|\?)/.test(s.src))) return blocked('Zalo build changed; adapter needs review');
  const marker='__pt_sender_'+Date.now(); let req;
  const item=[[],{[marker]:(m,e,r)=>{req=r}},[[marker]]];
  try {
    chunks.push(item);
    if (!req?.c?.fBUP || !req.c[13]) return blocked('Renderer modules unavailable');
    const api=req.c.fBUP.exports.default, group=req.c.Gm1y?.exports.default;
    if (String(req.c.DiYL?.exports.a.getUserId()) !== input.user_id) return blocked('Zalo account changed');
    const info=group?.getGroupByIdSync(input.thread_id);
    if (!info || info.userId !== input.thread_id || info.displayName !== input.display_name)
      return blocked('Group ID or name changed; refresh mapping');
    if (req.c.GpwQ.exports.a.instance().isOnE2ee(input.thread_id)) return blocked('E2EE group unsupported');
    if (group.getTypeVisibility(input.thread_id)!==0 || info.status!==0) return blocked('Group status unsupported');
    const utils=req.c.z0WU.exports.default;
    if (utils.getGroupIdFromConversationId(input.thread_id)!==input.thread_id.slice(1)) return blocked('Group ID mismatch');
    if (input.action==='prepare') return {state:'ready',client_id:String(req.c.NMlV.exports.a.next())};
    const cid=Number(input.client_id);
    if (!Number.isSafeInteger(cid) || Math.abs(Date.now()-cid)>300000) return blocked('Invalid or expired client ID');
    // No retries; any ambiguous error is reconciled through the independent reader.
    try {
      const response=await api.sendZText(input.thread_id,input.text,true,cid,0,undefined,null);
      if(response?.status!==200 || response?.data?.error_code!==0)
        return {state:'uncertain',detail:'Zalo did not acknowledge; do not resend'};
      let data=response.data.data;
      try{if(typeof data==='string')data=JSON.parse(utils.decodeAES(data));}catch{}
      const id=data?.msgId || data?.msg_id || data?.data?.msgId;
      return {state:'submitted',platform_message_id:id?String(id):'',detail:'Zalo API accepted; awaiting Desktop echo'};
    } catch { return {state:'uncertain',detail:'Send outcome unknown; do not resend'}; }
  } catch {
    return {state:'blocked',detail:'Renderer preflight failed'};
  } finally {
    if(req){delete req.c[marker];delete req.m[marker];req.s=13;}
    const index=chunks.indexOf(item);if(index>=0)chunks.splice(index,1);
  }
}
module.exports={rendererSender};
