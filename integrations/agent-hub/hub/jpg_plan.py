"""Validated CANAVI JPEG plans; no implicit fabric axes or RGB conversion."""
import math,re
from hub.workflow_rules import jpg_size

def normalize_fabric_axes(panel, known=None):
    """Correct transposed raw_fabric width/height when slip writes Height X Width (e.g. 88 X 49 or 40 X 50).

    Applies FABRIC_AXIS_POLICY:
    - For joined_two_faces or vertical bags, larger number is height_cm and smaller is width_cm.
    - For horizontal separate_panel bags (max <= 70 cm and finished_width_cm > finished_height_cm or orientation == 'horizontal'),
      larger number is width_cm and smaller is height_cm.
    """
    if panel.get('kind') != 'bag_panel' or panel.get('canvas_basis') != 'raw_fabric':
        return
    w, h = panel.get('width_cm'), panel.get('height_cm')
    if type(w) not in (int, float) or type(h) not in (int, float):
        return
    fw, fh = panel.get('finished_width_cm'), panel.get('finished_height_cm')
    is_horizontal_separate = (
        panel.get('construction') != 'joined_two_faces'
        and max(w, h) <= 70
        and (
            (type(fw) in (int, float) and type(fh) in (int, float) and fw > fh)
            or (type(fw) in (int, float) and fw > min(w, h))
            or panel.get('part_strategy', {}).get('orientation') == 'horizontal'
        )
    )
    if is_horizontal_separate:
        if w < h:
            panel['width_cm'], panel['height_cm'] = h, w
            panel['axis_normalized_from'] = [w, h]
        return
    if w <= h:
        return
    if known and panel.get('construction') != 'joined_two_faces':
        bg_id = panel.get('background_object_id')
        bg = known.get(bg_id) if bg_id else None
        if bg and bg.get('width_cm', 0) > bg.get('height_cm', 0) * 1.02 and abs(bg['width_cm'] - w) <= abs(bg['width_cm'] - h):
            return
        if any(c.get('x_cm', 0) + c.get('width_cm', 0) > h - 2.0 for c in panel.get('components', []) if type(c.get('x_cm')) in (int, float) and type(c.get('width_cm')) in (int, float)):
            return
    panel['width_cm'], panel['height_cm'] = h, w
    panel['axis_normalized_from'] = [w, h]

normalize_joined_fabric_axes = normalize_fabric_axes

def single_face_fabric_size(panel, width, height):
    """Owner rule: halve raw fabric length >65 for a confirmed single face.

    Return effective dimensions without mutating source dimensions, so validation
    cannot halve a previously validated panel a second time.
    """
    if (panel.get('kind') == 'bag_panel'
            and panel.get('canvas_basis') == 'raw_fabric'
            and panel.get('construction') == 'separate_panel'
            and panel.get('part_strategy', {}).get('kind') == 'single_face'
            and height > 65):
        panel['single_face_fabric_rule'] = {
            'source_cm': [width, height], 'effective_raw_cm': [width, height / 2],
            'rule': 'single_face_raw_height_gt65_halve_before_shrink',
        }
        return width, height / 2
    panel.pop('single_face_fabric_rule', None)
    return width, height

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
        normalize_fabric_axes(p, known)
        w,h=p['width_cm'],p['height_cm']
        if any(type(v) not in (float,int) or not math.isfinite(v) or not 1<=v<=200 for v in (w,h)):raise ValueError('Khổ vải không hợp lệ')
        if p.get('part_strategy', {}).get('kind') == 'single_face':
            p['construction'] = 'separate_panel'
        w,h=single_face_fabric_size(p,w,h)
        w,h=jpg_size(w,h,p['canvas_basis'],p['kind'])
        if min(w,h)<=0 or w*h*(300/2.54)**2>90_000_000:raise ValueError('Khổ vượt giới hạn an toàn')
        if p['kind']=='meter_fabric' and (p['canvas_basis']!='explicit_output' or abs(w-160)>.01):raise ValueError('Vải mét cần khổ xuất ngang 160 và cao có căn cứ')
        total_pixels+=w*h*(300/2.54)**2
        if total_pixels>150_000_000:raise ValueError('Tổng khổ quá lớn; cần chia lô để kiểm tra')
        p['output_cm']=[w,h];p['corner_marks']=p['kind']!='meter_fabric'
        bg=p.get('background_object_id')
        if bg and (bg not in known or known[bg]['kind'] not in ('vector_path','PathItem','GroupItem','CompoundPathItem') or known[bg].get('page',1)<1):raise ValueError('Nền phải trỏ đối tượng màu gốc')
        comps=p.get('components',[])
        joined=p.get('construction')=='joined_two_faces'
        if p['kind']=='bag_panel' and p.get('edge_finish') not in ('fold','sewn'):raise ValueError('Chưa rõ gấp hay may; không tự cộng đường may')
        if p.get('edge_finish') in ('fold','sewn') and not p.get('edge_finish_evidence'):raise ValueError('Thiếu bằng chứng gấp/may')
        if p.get('construction')=='unknown':raise ValueError('Chưa rõ túi liền hay miếng riêng')
        if joined and (p['kind']!='bag_panel' or (comps and not {'front'}<=set(c.get('side') for c in comps)<=({'front','back'}))):raise ValueError('Túi liền cần đủ mặt in')
        if not comps and not bg:raise ValueError('Thiếu artwork')
        if p['kind']=='meter_fabric' and comps:raise ValueError('Vải mét hoa văn cần xác minh bước nối; chưa tự lặp')
        for c in comps:
            ids=c.get('object_ids',[])
            if not ids or len(ids)!=len(set(ids)) or not set(ids)<=known.keys():raise ValueError('Sai ID artwork')
            if any(known[x].get('page',1)<1 or known[x]['kind'] not in ('image','vector_path','GroupItem','RasterItem','PathItem','CompoundPathItem','TextFrame') for x in ids):raise ValueError('Nguồn nhiều trang/chữ sống cần kiểm tra')
            if not c.get('sources') or not set(c['sources'])<=set(refs):raise ValueError('Cữ thiếu nguồn')
            if c.get('vertical_anchor','top') not in ('top','bottom'):raise ValueError('Chưa rõ mép tính cữ dọc')
            if c.get('rotation') not in (0,180):raise ValueError('Góc xoay chưa xác định')
            for k in ('x_cm','y_cm','width_cm'):
                if type(c[k]) not in (int,float) or not math.isfinite(c[k]):raise ValueError('Cữ không hợp lệ')
            if joined:
                side=c.get('side');expected=(0,'top') if side=='front' else (180,'bottom')
                if (c.get('rotation'),c.get('vertical_anchor'))!=expected:raise ValueError('Sai hướng mặt túi liền')
                if c.get('horizontal_alignment') not in ('left','right','center'):raise ValueError('Túi liền cần cách căn theo maket')
                c['maket_offsets_before_seam_cm']=[c['x_cm'],c['y_cm']]
                allowance=p.get('seam_allowance_cm')
                if type(allowance) not in (int,float) or allowance<0 or allowance>2:raise ValueError('Đường may không hợp lệ')
                if p.get('edge_finish')=='fold' and allowance!=0:raise ValueError('Phần gấp không tự cộng đường may')
                c['x_cm']+=allowance;c['y_cm']+=allowance;c['seam_added_cm']=allowance
            align=c.get('horizontal_alignment','left')
            if c.get('alignment_reference_box'):
                from hub.jpg_reference import inset_offsets
                if not c.get('alignment_reference_evidence'):
                    raise ValueError('Vùng canh cữ phía trong thiếu bằng chứng maket')
                if not (0 <= c['x_cm'] < w and 0 <= c['y_cm'] < h and c['width_cm'] > 0):
                    raise ValueError('Cữ vùng phía trong nằm ngoài khổ')
                bounds = [known[i]['bounds'] for i in ids]
                bw = max(b[2] for b in bounds)-min(b[0] for b in bounds)
                bh = max(b[1] for b in bounds)-min(b[3] for b in bounds)
                dx,dy = inset_offsets(c['alignment_reference_box'],c['width_cm'],bh/bw*c['width_cm'],c['rotation'],align,c.get('vertical_anchor','top'))
                c['reference_offsets_before_inset_cm']=[c['x_cm'],c['y_cm']]
                c['x_cm']-=dx
                if 'native_vertical_inset_cm' not in c:c['y_cm']-=dy
                c['preserve_source_bleed']=True
            if 'native_vertical_inset_cm' in c:
                inset=c['native_vertical_inset_cm']
                if type(inset) not in (int,float) or not math.isfinite(inset) or inset<0 or not c.get('native_reference'):
                    raise ValueError('Mốc native chưa xác minh')
                c['reference_top_before_native_inset_cm']=c['y_cm']
                if c['y_cm']-inset>=0:c['y_cm']-=inset
                else:
                    for k in ('native_vertical_inset_cm','vertical_reference_object_id','vertical_reference_evidence','native_reference','reference_top_before_native_inset_cm'):
                        c.pop(k,None)
            if align in ('left','right') and (c.get('x_cm') or 0)>0:
                ref_w=p.get('finished_width_cm') or w
                opp=ref_w-c['width_cm']-c['x_cm']
                if opp>=0 and abs(opp-c['x_cm'])<=0.5:
                    align='center'
                    c['horizontal_alignment']='center'
                    c['horizontal_symmetry']=True
                    if not c.get('horizontal_alignment_evidence'):
                        c['horizontal_alignment_evidence']=f"Tự căn giữa: hai lề ngang bằng nhau trên khổ {ref_w}cm ({c['x_cm']:.2f}cm vs {opp:.2f}cm)"
            if align in ('left','right') and (c.get('x_cm') or 0)>0 and p.get('kind')=='bag_panel' and p.get('canvas_basis')=='raw_fabric' and not c.get('seam_added_cm') and not c.get('side_seam_added_cm'):
                c['x_cm']+=1.0;c['side_seam_added_cm']=1.0
            if align=='center':
                if not c.get('horizontal_alignment_evidence'):raise ValueError('Căn giữa cần bằng chứng maket/xác nhận')
                if c.get('alignment_reference_box'):raise ValueError('Căn giữa vùng con cần kiểm tra riêng')
                c['x_cm']=(w-c['width_cm'])/2
            elif align=='right':c['x_cm']=w-c['width_cm']-c['x_cm']
            elif align!='left':raise ValueError('Chưa rõ căn ngang')
            if c.get('native_frame_registration'):
                frame=c['native_frame_registration']
                x=(w-frame['width_cm'])/2+frame['art_left_relative_cm']
                c['x_cm']=x if c['rotation']==0 else w-c['width_cm']-x
            if c.get('preserve_source_bleed') and (c['x_cm']>=w or c['x_cm']+c['width_cm']<=0):
                raise ValueError('Artwork tràn không giao với khổ xuất')
            if c.get('native_reference') and not p.get('background_object_id') and p.get('kind')=='bag_panel' and c['width_cm']<w-1.0:
                ob=c['native_reference'].get('outer_bounds')
                art_h_cm=((ob[1]-ob[3])*2.54/72) if isinstance(ob,(list,tuple)) and len(ob)==4 else 0.0
                if c['x_cm']<-0.5 or c['x_cm']+c['width_cm']>w+0.5:
                    raise ValueError('Artwork ngoài khổ')
                if p.get('construction')!='joined_two_faces' and c.get('vertical_anchor','top')=='top' and 0<art_h_cm<=h and c['y_cm']+art_h_cm>h+1.5:
                    raise ValueError('Artwork ngoài khổ')
            c_b=[known[i]['bounds'] for i in ids if i in known and isinstance(known[i].get('bounds'),(list,tuple)) and len(known[i]['bounds'])==4]
            c_h_cm=((max(max(b[1],b[3]) for b in c_b)-min(min(b[1],b[3]) for b in c_b))*2.54/72) if c_b else 0.0
            v_over=(c['y_cm']+c_h_cm-h) if (0<=c['y_cm']<h and c_h_cm>0 and h<c['y_cm']+c_h_cm<=h+1.5 and c['x_cm']>=-1.5 and c['x_cm']+c['width_cm']<=w+1.5) else 0.0
            h_over=(0<=c['y_cm']<h and c['x_cm']>=-1.5 and c['x_cm']+c['width_cm']<=w+1.5 and (c['x_cm']<0 or c['x_cm']+c['width_cm']>w))
            if not c.get('preserve_source_bleed') and c['width_cm']>0 and (h_over or v_over>0):
                c['preserve_source_bleed']=True
                c['bleed_tolerance_cm']=round(max(-c['x_cm'],c['x_cm']+c['width_cm']-w,v_over,0),3)
            if not c.get('preserve_source_bleed') and (c['x_cm']<0 or c['y_cm']<0 or c['width_cm']<=0 or c['x_cm']+c['width_cm']>w or c['y_cm']>=h):raise ValueError('Artwork ngoài khổ')
        component_backgrounds = {c['background_object_id'] for c in comps if c.get('background_object_id')}
        if not component_backgrounds <= known.keys():
            raise ValueError('Nguồn nền từng mặt không tồn tại')
        p['objects']=[known[x] for x in sorted({x for c in comps for x in c['object_ids']}|({bg} if bg else set())|component_backgrounds)]
    return plan
