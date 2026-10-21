"""Validated CANAVI JPEG plans; no implicit fabric axes or RGB conversion."""
import math,re

def validate(plan, objects, refs):
    if plan.get('issues') or plan.get('process')!='sublimation':
        raise ValueError('; '.join(plan.get('issues',[])) or 'Chưa xác nhận in chuyển nhiệt')
    code=plan.get('order_code','')
    if not re.fullmatch(r'[\w .-]{1,100}',code) or code in ('.','..'):raise ValueError('Thiếu mã mẫu hợp lệ')
    known={o['id']:o for o in objects};panels=plan.get('panels',[])
    total_pixels=0
    if not 1<=len(panels)<=8:raise ValueError('Chưa đủ các tấm cần in')
    if len({p['name'] for p in panels})!=len(panels):raise ValueError('Trùng tên artboard')
    for p in panels:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',p['name']):raise ValueError('Tên artboard không hợp lệ')
        if p['kind'] not in ('bag_panel','meter_fabric'):raise ValueError('Loại tấm chưa rõ')
        if not p.get('sources') or not set(p['sources'])<=set(refs) or not p.get('basis_explanation'):raise ValueError('Thiếu bằng chứng khổ/cữ')
        w,h=p['width_cm'],p['height_cm']
        if any(type(v) not in (float,int) or not math.isfinite(v) or not 1<=v<=200 for v in (w,h)):raise ValueError('Khổ vải không hợp lệ')
        if p['canvas_basis']=='raw_fabric':w-=2;h-=5 if h>=70 else 2.5
        elif p['canvas_basis']!='explicit_output':raise ValueError('Chưa rõ khổ trước/sau co')
        if min(w,h)<=0 or w*h*(300/2.54)**2>90_000_000:raise ValueError('Khổ vượt giới hạn an toàn')
        if p['kind']=='meter_fabric' and (p['canvas_basis']!='explicit_output' or abs(w-160)>.01):raise ValueError('Vải mét cần khổ xuất ngang 160 và cao có căn cứ')
        total_pixels+=w*h*(300/2.54)**2
        if total_pixels>150_000_000:raise ValueError('Tổng khổ quá lớn; cần chia lô để kiểm tra')
        p['output_cm']=[w,h];p['corner_marks']=p['kind']!='meter_fabric'
        bg=p.get('background_object_id')
        if bg and (bg not in known or known[bg]['kind']!='vector_path' or known[bg]['page']!=1):raise ValueError('Nền phải trỏ đối tượng màu gốc')
        comps=p.get('components',[])
        joined=p.get('construction')=='joined_two_faces'
        if p.get('construction')=='unknown':raise ValueError('Chưa rõ túi liền hay miếng riêng')
        if joined and (p['kind']!='bag_panel' or {c.get('side') for c in comps}!={'front','back'}):raise ValueError('Túi liền cần đủ hai mặt')
        if not comps and (not bg or p['kind']!='meter_fabric'):raise ValueError('Thiếu artwork')
        if p['kind']=='meter_fabric' and comps:raise ValueError('Vải mét hoa văn cần xác minh bước nối; chưa tự lặp')
        for c in comps:
            ids=c.get('object_ids',[])
            if not ids or len(ids)!=len(set(ids)) or not set(ids)<=known.keys():raise ValueError('Sai ID artwork')
            if any(known[x]['page']!=1 or known[x]['kind'] not in ('image','vector_path') for x in ids):raise ValueError('Nguồn nhiều trang/chữ sống cần kiểm tra')
            if not c.get('sources') or not set(c['sources'])<=set(refs):raise ValueError('Cữ thiếu nguồn')
            if c.get('vertical_anchor','top') not in ('top','bottom'):raise ValueError('Chưa rõ mép tính cữ dọc')
            if c.get('rotation') not in (0,180):raise ValueError('Góc xoay chưa xác định')
            for k in ('x_cm','y_cm','width_cm'):
                if type(c[k]) not in (int,float) or not math.isfinite(c[k]):raise ValueError('Cữ không hợp lệ')
            if joined:
                side=c.get('side');expected=(0,'top') if side=='front' else (180,'bottom')
                if (c.get('rotation'),c.get('vertical_anchor'))!=expected:raise ValueError('Sai hướng mặt túi liền')
                if c.get('horizontal_alignment') not in ('left','right'):raise ValueError('Túi liền cần cữ mép theo maket')
                c['maket_offsets_before_seam_cm']=[c['x_cm'],c['y_cm']]
                c['x_cm']+=0.5;c['y_cm']+=0.5;c['seam_added_cm']=0.5
            align=c.get('horizontal_alignment','left')
            if align=='center':c['x_cm']=(w-c['width_cm'])/2
            elif align=='right':c['x_cm']=w-c['width_cm']-c['x_cm']
            elif align!='left':raise ValueError('Chưa rõ căn ngang')
            if c['x_cm']<0 or c['y_cm']<0 or c['width_cm']<=0 or c['x_cm']+c['width_cm']>w or c['y_cm']>=h:raise ValueError('Artwork ngoài khổ')
        p['objects']=[known[x] for x in sorted({x for c in comps for x in c['object_ids']}|({bg} if bg else set()))]
    return plan
