"""OpenAI reference redraw: consent gate, one submission, durable usage, private export only."""
import base64,hashlib,io,json,time,unicodedata
from pathlib import Path
import httpx
from PIL import Image
MODEL='gpt-image-2.5-sunburst'
def cost(u):
 d=u.get('input_tokens_details',{})
 if not all(isinstance(d.get(k),int) for k in ('image_tokens','text_tokens')) or not isinstance(u.get('output_tokens'),int):return None
 return (d['image_tokens']*8+d['text_tokens']*5+u['output_tokens']*30)/1e6
def norm(s):return ' '.join(unicodedata.normalize('NFC',s).split())
def redraw(pet,raw,consent,folder,side,lines,client=None):
 if not consent or not consent.get('question_message_id') or not consent.get('answer_message_id'):raise ValueError('Chưa có xác nhận khách không có file')
 if side not in ('front','back','left','right','label','brim'):raise ValueError('Invalid side')
 folder=Path(folder);rec=folder/(side+'.openai.json');output=folder/(side+'.openai.png');sha=hashlib.sha256(raw).hexdigest()
 if rec.exists():
  prior=json.loads(rec.read_text())
  if prior.get('state')=='verified' and prior.get('source_sha256')==sha and output.exists() and hashlib.sha256(output.read_bytes()).hexdigest()==prior.get('output_sha256'):return output.read_bytes()
  raise ValueError('OpenAI đã có lượt trước; cần đối chiếu, không tự gọi lại')
 if not all(consent.get(k) for k in ('account','thread_id','sender_id','source_message_id')):raise ValueError('Thiếu liên kết ảnh và ngữ cảnh khách; chưa gọi OpenAI')
 local_rec,local_output=rec,output
 # Stable across brief IDs and duplicate webhook events. Do not include answer ID:
 # repeated confirmations must not buy the same reconstruction twice.
 identity=hashlib.sha256(json.dumps([MODEL,'reference-v1',consent['account'],consent['thread_id'],sha],ensure_ascii=False).encode()).hexdigest()
 shared=Path(pet.root)/'openai-receipts';shared.mkdir(parents=True,exist_ok=True)
 rec=shared/(identity+'.json');output=shared/(identity+'.png')
 if rec.exists():
  prior=json.loads(rec.read_text())
  if prior.get('state')=='verified' and prior.get('source_sha256')==sha and prior.get('prompt_lines')==list(map(norm,lines)) and output.exists() and hashlib.sha256(output.read_bytes()).hexdigest()==prior.get('output_sha256'):
   local_output.write_bytes(output.read_bytes());local_rec.write_text(json.dumps(prior,ensure_ascii=False),encoding='utf-8');return output.read_bytes()
  raise ValueError('Ảnh đã có lượt OpenAI ở hồ sơ khác; đối chiếu trước, không gọi lại')
 key=Path('/data/secrets/openai-api-key').read_text().strip()
 d={'state':'submitting','model':MODEL,'source_sha256':sha,'prompt_lines':list(map(norm,lines)),'consent':consent,'created':time.time()}
 with rec.open('x') as f:json.dump(d,f,ensure_ascii=False)
 def save():
  value=json.dumps(d,ensure_ascii=False)
  rec.write_text(value,encoding='utf-8');local_rec.write_text(value,encoding='utf-8')
 own=client is None;c=client or httpx.Client(timeout=600,trust_env=False,follow_redirects=False)
 try:
  prompt='Restore this exact reference artwork for printing. Preserve every shape, color, layout, proportions, letter, accent and digit. Clean crisp flat edges; remove compression noise/scratches. No shadows, bevel, textures, new elements or mirroring. Transparent background; complete artwork with small transparent margin. Exact text lines: '+json.dumps(lines,ensure_ascii=False)
  with Image.open(io.BytesIO(raw)) as im:size='1536x1024' if im.width>im.height else ('1024x1536' if im.height>im.width else '1024x1024')
  r=c.post('https://api.openai.com/v1/images/edits',headers={'Authorization':'Bearer '+key},data={'model':MODEL,'quality':'high','size':size,'background':'transparent','output_format':'png','n':'1','prompt':prompt},files={'image':('original.png',raw,'image/png')})
  d.update(http_status=r.status_code,request_id=r.headers.get('x-request-id'));save()
  if r.status_code!=200:raise ValueError('OpenAI HTTP '+str(r.status_code)+'; không tự thử lại')
  j=r.json();d.update(usage=j.get('usage',{}),computed_cost_usd=cost(j.get('usage',{})));save()
  out=base64.b64decode(j['data'][0]['b64_json'],validate=True)
  with Image.open(io.BytesIO(out)) as im:
   if 'A' not in im.getbands() or im.getchannel('A').getextrema()[0]==255:raise ValueError('OpenAI chưa có nền trong suốt')
   im.load()
  output.write_bytes(out);d['state']='generated';save()
  v=pet.ask('Đối chiếu ORIGINAL và RESTORED. Chép chữ/số RESTORED độc lập theo dòng. Chỉ pass khi đúng chữ, số, dấu, hình, bố cục, màu; không có nền hoặc quầng, không mất nét trắng, không lật gương. Đây là bản chờ duyệt nội bộ.',[{'text':'ORIGINAL'},{'inline_data':{'mime_type':'image/png','data':base64.b64encode(raw).decode()}},{'text':'RESTORED'},{'inline_data':{'mime_type':'image/png','data':base64.b64encode(out).decode()}}],{'type':'object','properties':{'pass':{'type':'boolean'},'lines':{'type':'array','items':{'type':'string'}},'issues':{'type':'array','items':{'type':'string'}}},'required':['pass','lines','issues']})
  if not v['pass'] or v['issues'] or list(map(norm,v['lines']))!=list(map(norm,lines)):raise ValueError('OpenAI chưa khớp artwork/chữ số; cần nhân viên xem')
  d.update(state='verified',output_sha256=hashlib.sha256(out).hexdigest());save();local_output.write_bytes(out);return out
 except Exception as ex:
  d.update(state='review_no_retry',error_type=type(ex).__name__);save();raise ValueError('OpenAI cần kiểm tra nội bộ; không tự gọi lại. Request '+str(d.get('request_id','unknown'))) from None
 finally:
  if own:c.close()

