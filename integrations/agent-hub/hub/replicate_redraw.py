"""Replicate redraw with durable at-most-once submission; no credentials in receipts."""
import base64,hashlib,io,json,os,re,time,unicodedata
from pathlib import Path
from urllib.parse import urlparse
import httpx
from PIL import Image
API='https://api.replicate.com/v1'
MODEL='black-forest-labs/flux-kontext-pro'

def normalized(text):return ' '.join(unicodedata.normalize('NFC',text).split())

def redraw(pet,raw,consent,folder,side,client=None,model=MODEL,parameters=None):
    if not consent or not consent.get('question_message_id') or not consent.get('answer_message_id'):raise ValueError('Thiếu xác nhận khách không có file')
    if not re.fullmatch('[a-z_0-9]+',side):raise ValueError('Invalid redraw side')
    folder=Path(folder);folder.mkdir(exist_ok=True)
    record=folder/(side+'.replicate.json');output=folder/(side+'.replicate.png')
    source_hash=hashlib.sha256(raw).hexdigest()
    if record.exists():
        old=json.loads(record.read_text())
        if old.get('state')=='verified' and old.get('source_sha256')==source_hash and output.exists() and hashlib.sha256(output.read_bytes()).hexdigest()==old.get('output_sha256'):return output.read_bytes()
        raise ValueError('Lần vẽ trước cần đối chiếu prediction ID; không tự gọi lại để tránh phí trùng')
    key_path=Path(os.getenv('REPLICATE_TOKEN_FILE','/data/secrets/replicate-token'))
    if not key_path.exists():raise ValueError('Chưa cấu hình khóa Replicate')
    token=key_path.read_text().strip().removeprefix('Bearer ').strip()
    if not token:raise ValueError('Chưa cấu hình khóa Replicate')
    image=Image.open(io.BytesIO(raw));image.verify()
    parts=[{'inline_data':{'mime_type':'image/png','data':base64.b64encode(raw).decode()}}]
    schema={'type':'object','required':['legible','lines','white_artwork','issues'],'properties':{'legible':{'type':'boolean'},'lines':{'type':'array','items':{'type':'string'}},'white_artwork':{'type':'boolean'},'issues':{'type':'array','items':{'type':'string'}}}}
    source=pet.ask('Đọc chính xác toàn bộ chữ/số/dấu logo theo từng dòng, giữ nguyên ký tự. Không đoán chữ mờ. Xác định có chi tiết trắng thuộc logo (không phải nền) không. Chỉ legible=true khi chắc chắn.',parts,schema)
    if not source['legible'] or source['issues'] or (source['white_artwork'] and model==MODEL):raise ValueError('Chữ chưa đọc rõ hoặc artwork trắng cần xử lý riêng trước vẽ lại')
    prompt='Restore this reference logo with crisp clean edges for print. Preserve exact artwork, color, layout, proportions, every letter, Vietnamese accent and digit. Do not mirror, add or remove elements. Solid pure white background, no shadows/textures. Exact text by lines: '+json.dumps(source['lines'],ensure_ascii=False)
    receipt={'state':'submitting','model':model,'source_sha256':source_hash,'consent':consent,'created':time.time(),'lines':source['lines']}
    with record.open('x') as f:json.dump(receipt,f,ensure_ascii=False)
    own=client is None;c=client or httpx.Client(timeout=60,follow_redirects=False,trust_env=False)
    try:
        inputs=parameters or {'prompt':prompt,'input_image':'data:image/png;base64,'+base64.b64encode(raw).decode(),'output_format':'png','aspect_ratio':'match_input_image','prompt_upsampling':False}
        versions={'men1scus/birefnet':'f74986db0355b58403ed20963af156525e2891ea3c2d499bfbfb2a28cd87c5d7','lucataco/sdxl-controlnet':'06d6fae3b75ab68a28cd2900afa6033166910dd09fd9751047043a5bbb4c184b'}
        endpoint=API+'/predictions' if model in versions else API+'/models/'+model+'/predictions'
        body={'input':inputs}
        if model in versions:body['version']=versions[model]
        r=c.post(endpoint,headers={'Authorization':'Bearer '+token,'Prefer':'wait=5'},json=body)
        if r.status_code>=400:raise ValueError('Replicate từ chối yêu cầu: HTTP '+str(r.status_code))
        job=r.json();pid=job.get('id','')
        if not re.fullmatch('[a-zA-Z0-9_-]+',pid):raise ValueError('Replicate thiếu prediction ID')
        receipt.update(state='submitted',prediction_id=pid);record.write_text(json.dumps(receipt,ensure_ascii=False))
        deadline=time.monotonic()+240
        while job.get('status') not in ('succeeded','failed','canceled'):
            if time.monotonic()>deadline:raise ValueError('Replicate quá thời gian, giữ ID để đối chiếu; không tạo lại')
            time.sleep(3);r=c.get(API+'/predictions/'+pid,headers={'Authorization':'Bearer '+token});r.raise_for_status();job=r.json()
        if job['status']!='succeeded':raise ValueError('Replicate chưa tạo được ảnh; kiểm tra prediction ID')
        url=job.get('output');url=url[0] if isinstance(url,list) and len(url)==1 else url;u=urlparse(url if isinstance(url,str) else '')
        if u.scheme!='https' or not ((u.hostname or '')=='replicate.delivery' or (u.hostname or '').endswith('.replicate.delivery')) or u.username or u.port not in (None,443):raise ValueError('Địa chỉ ảnh Replicate không hợp lệ')
        with c.stream('GET',url) as r:
            r.raise_for_status();data=bytearray()
            for chunk in r.iter_bytes():
                data.extend(chunk)
                if len(data)>16000000:raise ValueError('Ảnh đầu ra quá lớn')
        out=bytes(data)
        with Image.open(io.BytesIO(out)) as im:
            if im.width*im.height>16000000:raise ValueError('Ảnh đầu ra quá lớn')
            im.verify()
        output.write_bytes(out)
        verify=pet.ask('Đối chiếu logo ORIGINAL và RESTORED: đúng hình, màu, bố cục, không lật gương, không mất/thêm nét. Chép nguyên văn chữ/số của RESTORED theo dòng; không sao chép đáp án từ original. pass chỉ khi khớp và đủ rõ; riêng tách nền không bắt buộc tăng độ nét. Giữ các nét trắng, không mất phần logo.',[{'text':'ORIGINAL'},*parts,{'text':'RESTORED'},{'inline_data':{'mime_type':'image/png','data':base64.b64encode(out).decode()}}],{'type':'object','required':['pass','lines','issues'],'properties':{'pass':{'type':'boolean'},'lines':{'type':'array','items':{'type':'string'}},'issues':{'type':'array','items':{'type':'string'}}}})
        if not verify['pass'] or verify['issues'] or [normalized(x) for x in verify['lines']]!=[normalized(x) for x in source['lines']]:raise ValueError('Bản vẽ lại chưa khớp chữ/số/maket; giữ kiểm tra nội bộ, không xuất TIFF')
        receipt.update(state='verified',output_sha256=hashlib.sha256(out).hexdigest());record.write_text(json.dumps(receipt,ensure_ascii=False));return out
    except Exception as exc:
        receipt.update(state='review',error=type(exc).__name__);record.write_text(json.dumps(receipt,ensure_ascii=False));raise ValueError('Vẽ lại Replicate chưa được kiểm chứng; giữ hồ sơ để kiểm tra, không tự gọi lại') from None
    finally:
        if own:c.close()


