"""Group-scoped source gate. Never deletes captures or changes sender roles."""
from copy import deepcopy

def filter_messages(policy, account, messages):
 rules=(policy or {}).get('group_intake_rules',{})
 output=[]
 for original in messages:
  m=deepcopy(original)
  rule=rules.get(account,{}).get(m.get('thread_id'),{})
  if rule.get('mode')=='primary_slip_sender' and str(m.get('sender_id') or '')!=rule.get('primary_sender_id'):
   had_images=bool(m.get('images')) or any(a.get('kind')=='image' for a in m.get('assets',[]))
   m['images']=[]
   m['assets']=[a for a in m.get('assets',[]) if a.get('kind')!='image']
   if had_images:
    m['images_ignored_by_group_rule']=True
    if m.get('text','').startswith('['):m['text']='[Ảnh không thuộc người gửi phiếu chính; chỉ lưu lịch sử]'
    m['attachments']=[a for a in m.get('attachments',[]) if a!='whatsapp-desktop:caption-unverified']
  output.append(m)
 return output

def only_ignored_images(messages):
 return bool(messages) and any(m.get('images_ignored_by_group_rule') for m in messages) and all(not m.get('images') and not m.get('assets') and (not m.get('text','').strip() or m.get('text','').startswith('[')) for m in messages)
