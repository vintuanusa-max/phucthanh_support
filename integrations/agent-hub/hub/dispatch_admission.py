"""Admission only: ERP evidence is not an automatic print/design request."""
import re,unicodedata
EXT=('.ai','.pdf','.psd','.cdr','.eps','.svg','.tif','.tiff')
def allowed(run,messages,policy=None):
 from hub.order_policy import quality_only
 channel={'zalo-personal-1':'zalo','whatsapp-personal-1':'whatsapp'}.get(run.get('account'))
 if quality_only(channel,run.get('thread_id')):return False
 if run.get('manual_dispatch') is True:return True
 if run.get('agent_admitted') is True:return True
 from hub.canavi_slip_policy import export_admitted
 if export_admitted(policy,run,messages):return True
 sources=[m for m in messages if not m.get('recalled') and not m.get('revision')]
 if run.get('raster_sample_consent') or run.get('standalone_raster_pet'):return True
 if not any(a.get('name','').lower().endswith(EXT) for m in sources for a in m.get('assets',[])):return False
 from hub.group_original_jpg import enabled as jpg_group_enabled
 if jpg_group_enabled(run.get('thread_id')) and any(a.get('name','').lower().endswith(('.ai','.pdf','.psd')) for m in sources for a in m.get('assets',[])):return True
 from hub.sample_file_policy import requested,pet_requested
 if requested(run.get('thread_id'),sources) or pet_requested(run.get('thread_id'),sources):return True
 for m in sources:
  if m.get('origin','customer')!='customer' or m.get('role') in ('staff','bot') or m.get('direction','incoming')!='incoming':continue
  text=''.join(c for c in unicodedata.normalize('NFD',m.get('text','').lower()) if not unicodedata.combining(c)).replace('đ','d')
  text=re.sub(r'\[(?:file|anh)[^\]]*\]','',text)
  for clause in re.split(r'[.!?;\n]',text):
   if re.search(r'\b(?:khong|ko|chua|dung|khoan|huy)\b',clause):continue
   if re.search(r'\b(?:lam mau|ve(?: mau| lai)?|thiet ke|len mau)\b',clause):return True
 return False
