"""Raster-only PET proposals; no ERP mutations and no public delivery."""
import base64, hashlib, io, json, time
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter, ImageDraw


def remove_exterior_white(raw):
    """Remove only near-white pixels connected to the canvas edge; retain enclosed whites."""
    im=Image.open(io.BytesIO(raw)).convert('RGBA')
    if im.width*im.height>16000000:raise ValueError('Ảnh quá lớn cần kiểm tra')
    if im.getchannel('A').getextrema()[0]<255:return raw
    mask=Image.new('L',(im.width+2,im.height+2),255)
    inside=Image.new('L',im.size)
    inside.putdata([255 if min(r,g,b)>=245 else 0 for r,g,b,a in im.getdata()])
    mask.paste(inside,(1,1));ImageDraw.floodfill(mask,(0,0),128,thresh=0)
    exterior=mask.crop((1,1,im.width+1,im.height+1))
    im.putalpha(exterior.point(lambda p:0 if p==128 else 255))
    out=io.BytesIO();im.save(out,format='PNG');return out.getvalue()
from hub.store import event_key
from hub.pet_render import code_name
from hub.workflow_rules import hat_face_policy,hat_default_size


def cut_background(raw,mode,white_artwork):
    im=Image.open(io.BytesIO(raw)).convert('RGBA')
    if im.width*im.height>16000000:raise ValueError('Ảnh quá lớn cần kiểm tra')
    if mode=='alpha':
        if im.getchannel('A').getextrema()[0]==255:raise ValueError('Nguồn không có alpha')
    elif mode=='white' and white_artwork is False:
        # Remove an explicitly confirmed white matte, never arbitrary white artwork.
        out=[]
        for r,g,b,a in im.getdata():
            alpha=255-min(r,g,b)
            if alpha<6:out.append((0,0,0,0));continue
            out.append(tuple(max(0,min(255,round((c-255+alpha)*255/alpha))) for c in (r,g,b))+(round(alpha*a/255),))
        im.putdata(out)
    else:raise ValueError('Nền phức tạp hoặc chi tiết trắng chưa tách biệt; cần kiểm tra')
    box=im.getchannel('A').getbbox()
    if not box:raise ValueError('Artwork rỗng')
    return im.crop(box)


def render(raw,face,target):
    im=cut_background(raw,face['background'],face['white_artwork'])
    if face.get('restore_edges_confirmed'):
        # Pixel-only edge cleanup: never synthesize text or fill internal holes.
        alpha=im.getchannel('A');alpha=alpha.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.GaussianBlur(.35))
        im.putalpha(alpha)
    hat_face_policy(face,{'id':'pet_hat' if face['product_kind']=='hat' else 'pet_general','height_cap_cm':None})
    if face['dimensions_basis']=='owner_hat_default':w,h=hat_default_size(face,im.width,im.height)
    else:
        w,h=face['width_cm'],face['height_cm']
        if not w and h:w=h*im.width/im.height
        if not h and w:h=w*im.height/im.width
        if not w or not h or abs(w/h/(im.width/im.height)-1)>.025:raise ValueError('Thiếu kích thước hoặc tỷ lệ bị méo')
    if min(w,h)<=0 or max(w,h)>160:raise ValueError('Khổ ngoài giới hạn')
    pixels=(round(w/2.54*300),round(h/2.54*300))
    if min(pixels)<1 or pixels[0]*pixels[1]>45000000:raise ValueError('Khổ quá lớn')
    im=im.resize(pixels,Image.Resampling.LANCZOS);im.save(target,dpi=(300,300))
    small=im.copy();small.thumbnail((1000,700));preview=Image.new('RGB',(small.width*2,small.height))
    for n,color in enumerate(('white','#303030')):
        bg=Image.new('RGBA',small.size,color);bg.alpha_composite(small);preview.paste(bg.convert('RGB'),(n*small.width,0))
    preview.save(target.with_suffix('.preview.png'))
    return {'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'pixels':list(pixels),'width_cm':w,'height_cm':h}


def discover(checks,row,brief,force=False):
    pet=checks.pet
    marker=pet.root/'raster-enabled-at'
    if not marker.exists():
        try:
            with marker.open('x') as f:f.write(str(time.time()))
        except FileExistsError:pass
    if not force and row['created']<float(marker.read_text()):return
    sources=brief.get('sources',[])
    if not any(s.get('images') for s in sources):return
    if any(a.get('name','').lower().endswith(('.pdf','.ai')) for s in sources for a in s.get('assets',[])):return
    identity=event_key('raster-pet-v1',row['id'])
    payload={'brief_id':row['id'],'conversation':brief['conversation_id'],'private':True,'auto_rip':False,'mirror':False}
    with checks.store.db() as d:
        old=d.execute('select state,payload from pet_exports where id=?',(identity,)).fetchone()
    if old:
        # Only continue a review explicitly waiting for file consent. Never revive
        # archived, completed, uncertain, or already paid jobs.
        oldp=json.loads(old['payload'])
        if old['state']!='review' or not (oldp.get('awaiting_file_consent') or 'hỏi file' in oldp.get('review_reason','')):return identity
        follow=pet.root/'openai-followup-enabled-at'
        if not follow.exists():
            try:
                with follow.open('x') as f:f.write(str(time.time()))
            except FileExistsError:pass
        with checks.store.db() as d:
            recent=d.execute("select payload from captures where account=? and thread_id=? and json_extract(payload,'$.timestamp')>? order by json_extract(payload,'$.timestamp') desc limit 30",(brief['account'],brief['thread_id'],max(float(follow.read_text()),time.time()-1800))).fetchall()
        from hub.raster_consent import restoration_consent
        for entry in recent:
            m=json.loads(entry['payload'])
            if m.get('revision') or m.get('recalled'):continue
            context=checks.e.order_intake.context_gate.build({'account':brief['account'],'thread_id':brief['thread_id'],'id':row['id']},[m])
            consent=restoration_consent(context)
            if not consent or not set(consent['source_message_ids']).intersection(s['message_id'] for s in sources):continue
            identity=event_key('raster-followup-v1',brief['account'],brief['thread_id'],consent['answer_message_id'],consent['source_message_ids'])
            payload['followup_message_id']=consent['answer_message_id']
            break
        else:return identity
    with checks.store.db() as d:
        inserted=d.execute('insert or ignore into pet_exports values(?,?,?,?,?)',(identity,brief['account'],'scheduled',json.dumps(payload),time.time())).rowcount
        if inserted:d.execute("insert or ignore into jobs(id,kind,payload,created) values(?,'raster_pet',?,?)",('raster:'+identity,json.dumps({'id':identity}),time.time()))
    return identity


def process(engine,identity):
    pet=engine.artwork_checks.pet
    with engine.store.db() as d:
        row=d.execute("select * from pet_exports where id=? and state='scheduled'",(identity,)).fetchone()
        if not row:return
        p=json.loads(row['payload']);brief=json.loads(d.execute('select payload from design_briefs where id=?',(p['brief_id'],)).fetchone()[0])
        d.execute("update pet_exports set state='planning' where id=? and state='scheduled'",(identity,))
    try:
        # Recheck live group policy. Excluded groups must never produce jobs.
        from hub.order_policy import capture_allowed
        mapping=engine.store.thread(account=row['account'],thread_id=brief['thread_id'])
        policy=engine.order_intake.policy(row['account'])
        if not mapping or not policy or not capture_allowed(policy,engine.settings.inboxes[row['account']]['channel'],brief['thread_id'],mapping['display_name']):raise ValueError('Nhóm không được phép xuất')
        brief_view=dict(brief.get('brief') or {})
        if p.get('owner_instruction'):brief_view['owner_instruction']=p['owner_instruction']
        if p.get('manual_export'):
            brief_view['missing_fields']=[] # Old design-intake questions do not govern explicit export.
        images={};parts=[{'text':json.dumps({'brief':brief_view,'owner_dimension_policy':brief.get('owner_dimension_policy')},ensure_ascii=False)}]
        for src in brief['sources']:
            for mid in src.get('images',[]):
                values=engine.store.images([mid]);images[mid]=(values[0],src)
                parts.extend([{'text':'IMAGE_ID '+mid+'; message '+src['message_id']},{'inline_data':values[0]}])
        if not 1<=len(images)<=8:raise ValueError('Số ảnh cần kiểm tra riêng')
        props={'image_id':{'type':'string','enum':list(images)},'side':{'type':'string','enum':['front','back','left','right','label','brim']},'product_kind':{'type':'string','enum':['hat','other']},'background':{'type':'string','enum':['white','alpha','complex']},'white_artwork':{'type':'boolean'},'dimensions_basis':{'type':'string','enum':['owner_hat_default','explicit_measurement']},'width_cm':{'type':'number'},'height_cm':{'type':'number'},'reason':{'type':'string'}}
        schema={'type':'object','properties':{'order_code':{'type':'string'},'issues':{'type':'array','items':{'type':'string'}},'faces':{'type':'array','items':{'type':'object','properties':props,'required':list(props)}}},'required':['order_code','issues','faces']}
        from hub.raster_consent import restoration_consent
        raw_messages=[]
        with engine.store.db() as d:
            run=d.execute('select * from intake_runs where id=?',(brief.get('run_id',''),)).fetchone()
            lookup=list(brief['sources'])
            if p.get('followup_message_id'):lookup.append({'message_id':p['followup_message_id']})
            for src in lookup:
                found=d.execute('select payload from captures where account=? and thread_id=? and message_id=? order by revision desc limit 1',(row['account'],brief['thread_id'],src['message_id'])).fetchone()
                if found:raw_messages.append(json.loads(found[0]))
        consent=None
        if raw_messages:
            context=engine.order_intake.context_gate.build({'account':row['account'],'thread_id':brief['thread_id'],'id':p['brief_id']},raw_messages)
            consent=restoration_consent(context)
            parts.append({'text':'SOURCE_DIALOGUE '+json.dumps(context,ensure_ascii=False)})
        p['restoration_consent']=consent
        if p.get('manual_export'):
            consent=None # Manual export is not authorization to buy a redraw.
            parts.append({'text':'ERP OWNER EXPORT SETTINGS (not missing): '+json.dumps(p['manual_export'])+' product_kind=hat, height_cm as provided, width_cm=0 preserve ratio; dimensions_basis=explicit_measurement. Use the specified side, one artwork only. Export PNG transparent and TIFF white ink, KEEP ORIGINAL COLORS and all original text/details, no mirror. This is export of existing artwork, NOT a new design request. Previous missing color/format questions are resolved by these settings. Do not ask for a file already attached. Check actual source ambiguity only.'})
        if consent:parts.append({'text':'CONSENT '+json.dumps(consent,ensure_ascii=False)+' Khách xác nhận không có file chỉ cho cụm ảnh này. Nếu cụm có nhiều mẫu khác nhau và không rõ khách đang trả lời cho mẫu nào, bắt buộc issues, không chọn đoán. Có thể chọn logo riêng độ phân giải thấp; vẫn phải đọc chắc chữ/số. Không lấy nguyên ảnh sản phẩm.'})
        plan=pet.ask('Đọc TẤT CẢ ảnh/maket và lời khách, chọn ảnh ARTWORK RIÊNG tương ứng logo trên maket. Không chọn toàn ảnh sản phẩm/maket, không đoán/cắt phần logo trong ảnh sản phẩm ở bước này. Mỗi vị trí in một face; các góc nhìn cùng vị trí không nhân đôi. Chọn ảnh logo riêng đủ nét; nếu đã có xác nhận không file thì cho chọn logo riêng độ phân giải thấp nhưng chữ/số phải đọc được để vẽ lại trước xuất. Nếu thiếu artwork riêng thì issues. Nền phức tạp sẽ được bộ tách nền kiểm tra riêng. Xác minh chữ trắng có thuộc artwork không: nền trắng và white_artwork=true chuyển bộ tách nền, không xóa trắng hàng loạt. Ảnh alpha giữ chi tiết trắng. Chưa có kích thước khách: nón mặt trước/mạc cao6.5cm, hông ngang7cm, dimensions_basis=owner_hat_default. Khách ghi một chiều thì explicit_measurement, chiều còn lại0, giữ tỷ lệ. Vị trí khác không có mặc định. Không lật gương, không RIP/gửi khách. Không xuất nếu yêu cầu rõ công nghệ khác PET. Tên order_code từ tên mẫu/brief, không đoán mã đơn ERP.',parts,schema)
        p['plan']=plan
        if p.get('manual_export') and plan.get('faces'):
            if len(plan['faces'])!=1:raise ValueError('Nhiều vị trí: cần chọn kích thước riêng từng vị trí')
            face=plan['faces'][0];face.update(height_cm=p['manual_export']['height_cm'],width_cm=0,dimensions_basis='explicit_measurement',side=p['manual_export']['side'])
        if plan['issues'] or not plan['faces']:raise ValueError('; '.join(plan['issues']) or 'Chưa chọn được artwork riêng')
        if len({f['side'] for f in plan['faces']})!=len(plan['faces']):raise ValueError('Trùng vị trí')
        folder=pet.root/identity;folder.mkdir(exist_ok=True);files=[];verify=list(parts)
        for f in plan['faces']:
            value,src=images[f['image_id']]
            raw=base64.b64decode(value['data'])
            with Image.open(io.BytesIO(raw)) as original:
                buf=io.BytesIO();original.save(buf,format='PNG');raw=buf.getvalue()
            from hub.raster_router import route
            bound_consent=dict(consent,source_message_id=src['message_id']) if consent and src['message_id'] in consent.get('source_message_ids',[]) else None
            if p.get('manual_export') and f['background'] in ('white','alpha'):
                # Explicit export of supplied artwork is not permission for paid redraw.
                # Keep the source pixels, including white details inside closed logos.
                if f['background']=='white':raw=remove_exterior_white(raw)
                f['background']='alpha'
                p['render_method']='original_pixels_private_review'
            else:
                raw=route(pet,raw,bound_consent,folder,f['side'],f)
            f['restore_edges_confirmed']=False
            target=folder/(code_name(plan['order_code'])+'_'+f['side']+'.png')
            files.append(render(raw,f,target))
            verify.extend([{'text':'EXPORTED '+json.dumps(f,ensure_ascii=False)},{'inline_data':{'mime_type':'image/png','data':base64.b64encode(target.with_suffix('.preview.png').read_bytes()).decode()}}])
        v=pet.ask('Kiểm tra bản tách trên nền trắng/tối so với TẤT CẢ ảnh gốc và maket. Đúng toàn bộ chữ, số, dấu, màu và logo, không có nền sản phẩm, không mất chi tiết hay nét lạ. Chấp nhận kích thước mặc định chủ xưởng 6.5cm cao mặt trước,7cm ngang hông khi khách không ghi. Không lật gương. Chỉ pass nếu đủ rõ để đưa chủ xưởng duyệt; không đòi vector nếu ảnh riêng rõ. Nêu issues nếu mất nét hoặc chọn nhầm.',verify,{'type':'object','properties':{'pass':{'type':'boolean'},'issues':{'type':'array','items':{'type':'string'}}},'required':['pass','issues']})
        if v['pass'] is not True or v['issues']:raise ValueError('; '.join(v['issues']) or 'Bản tách cần kiểm tra')
        _,src=images[plan['faces'][0]['image_id']]
        asset=next((a for a in src.get('assets',[]) if a.get('relative_path')),None)
        if not asset:raise ValueError('Thiếu đường dẫn NAS nguồn')
        group=asset['relative_path'].replace('\\','/').split('/')[0]
        if not group or group in ('.','..') or any(c in group for c in '/\\:'):raise ValueError('Invalid archive group')
        p.update(files=files,verification=v,archive_folder=group,archive_model=code_name(plan['order_code']),source={'source_message_id':src['message_id'],'asset':asset},source_image_ids=list(images))
        pet.save(identity,p,'queued')
    except Exception as exc:
        if isinstance(exc,ValueError) and 'hỏi file' in str(exc):p['awaiting_file_consent']=True
        p.setdefault('source',{'asset':{'name':'Raster source images'}})
        pet.review(identity,p,str(exc)[:1200] if isinstance(exc,ValueError) else 'Raster export failed: '+type(exc).__name__)


