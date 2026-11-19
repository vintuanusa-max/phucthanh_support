"""Convert measured internal artwork anchors to full-bleed placement."""
import math


def inset_offsets(box, width, height, rotation, alignment, anchor):
    if (len(box) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
            or not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1):
        raise ValueError('Vùng canh cữ trong artwork không hợp lệ')
    l, t, r, b = box
    if rotation == 180:
        l, t, r, b = 1-r, 1-b, 1-l, 1-t
    elif rotation != 0:
        raise ValueError('Unsupported rotation')
    if alignment not in ('left', 'right') or anchor not in ('top', 'bottom'):
        raise ValueError('Vùng cữ cần mép trái/phải và trên/dưới xác định')
    return ((l if alignment == 'left' else 1-r)*width,
            (t if anchor == 'top' else 1-b)*height)


def native_anchor(component, candidates):
    """Resolve a nested measurement object without replacing export artwork."""
    ref_id = component.get('vertical_reference_object_id')
    if not ref_id:
        return
    ids = component['object_ids']
    known = {o['id']: o for o in candidates}
    if ref_id not in known or not any(ref_id.startswith(i + '.') for i in ids):
        raise ValueError('Mốc cữ phải là object con của group xuất')
    if not component.get('vertical_reference_evidence'):
        raise ValueError('Thiếu bằng chứng mốc cữ bên trong')
    bs = [known[i]['bounds'] for i in ids]
    outer = [min(b[0] for b in bs),max(b[1] for b in bs),max(b[2] for b in bs),min(b[3] for b in bs)]
    inner = known[ref_id]['bounds']
    delta = (outer[1] - inner[1]) * 2.54 / 72
    if delta < 0 or delta >= (outer[1]-outer[3])*2.54/72:
        raise ValueError('Mốc cữ nằm ngoài group xuất')
    if component.get('rotation',0) not in (0,180):
        raise ValueError('Góc xoay mốc cữ chưa hỗ trợ')
    if (component.get('rotation',0),component.get('vertical_anchor','top')) not in ((0,'top'),(180,'bottom')):
        raise ValueError('Hướng mốc cữ không tương ứng mặt in')
    component['native_vertical_inset_cm'] = delta
    component['native_reference'] = {'id':ref_id,'bounds':inner,'outer_bounds':outer,'axis':'vertical'}
    component['preserve_source_bleed'] = True


def native_frame(component, candidates):
    frame_id=component.get('reference_frame_object_id')
    if not frame_id:return
    known={o['id']:o for o in candidates}
    frame=known.get(frame_id)
    if not frame or frame['kind']!='PathItem' or not component.get('reference_frame_evidence'):
        raise ValueError('Khung maket chưa xác minh')
    q=frame['bounds'];bs=[known[i]['bounds'] for i in component['object_ids']]
    l=min(b[0] for b in bs);t=max(b[1] for b in bs);rr=max(b[2] for b in bs);bb=min(b[3] for b in bs)
    if min(rr,q[2])<=max(l,q[0]) or min(t,q[1])<=max(bb,q[3]):
        # Same artwork can be reused on both sides. Resolve its own equivalent
        # source frame, never measure the distant second mockup against this logo.
        matches=[]
        if component.get('horizontal_alignment')=='center' and component.get('horizontal_symmetry') is True:
            for candidate in candidates:
                b=candidate['bounds']
                if candidate['kind']!='PathItem':continue
                if abs((b[2]-b[0])-(q[2]-q[0]))>.1 or abs((b[1]-b[3])-(q[1]-q[3]))>.1:continue
                if b[0]<=l and b[2]>=rr and b[1]>=t and b[3]<=bb and abs((b[0]+b[2]-l-rr)/2)<.1:
                    if not any(max(abs(a-z) for a,z in zip(old['bounds'],b))<.001 for old in matches):matches.append(candidate)
        if len(matches)!=1:raise ValueError('Khung không giao artwork; không có khung tương đương duy nhất')
        frame=matches[0]
        component['frame_resolution']={'previous_id':frame_id,'resolved_id':frame['id'],'method':'unique_equal_size_centered_source_frame'}
        frame_id=frame['id'];q=frame['bounds']
        component['reference_frame_object_id']=frame_id
    inner=component.get('native_reference',{}).get('bounds')
    if inner:
        measured=(q[1]-inner[1])*2.54/72
        if abs(measured-component['maket_top_cm'])>.1:
            # Resolve only a unique child at an actual vertical dimension endpoint.
            # This is geometric evidence, never nearest-logo guessing.
            cm=2.54/72;target=component['maket_top_cm'];matches={}
            lines=[o['bounds'] for o in candidates if o['kind']=='PathItem'
                   and (o['bounds'][2]-o['bounds'][0])*cm<.06
                   and abs((o['bounds'][1]-o['bounds'][3])*cm-target)<.06
                   and abs((o['bounds'][1]-q[1])*cm)<.06]
            for o in candidates:
                if not any(o['id'].startswith(i+'.') for i in component['object_ids']):continue
                b=o['bounds']
                if abs((q[1]-b[1])*cm-target)>.06:continue
                if any(b[0] <= (line[0]+line[2])/2 <= b[2] and abs((line[3]-b[1])*cm)<.06 for line in lines):matches[o['id']]=o
            # If an ancestor and descendant have identical endpoint, keep the deepest.
            for key in list(matches):
                if any(other.startswith(key+'.') for other in matches):matches.pop(key,None)
            if len(matches)!=1:raise ValueError('Object con không khớp cữ đo trên khung maket: %.3f cm'%measured)
            resolved=next(iter(matches.values()))
            component['reference_resolution']={'previous_id':component['vertical_reference_object_id'],'resolved_id':resolved['id'],'method':'unique_native_dimension_endpoint'}
            component['vertical_reference_object_id']=resolved['id']
            component['vertical_reference_evidence']='Object con tại đầu đường đo native, khớp chiều dài đường đo và khung maket.'
            native_anchor(component,candidates)
    component['native_frame_registration']={'id':frame_id,'bounds':q,'width_cm':(q[2]-q[0])*2.54/72,'art_left_relative_cm':(l-q[0])*2.54/72}
    component.pop('alignment_reference_box',None)
    component.pop('alignment_reference_evidence',None)
    component['preserve_source_bleed']=True


def mouth_allowance(component):
    """Owner policy: blank mouth allowance on the slip defaults to 5 cm."""
    state=component.get('mouth_allowance_source')
    if state=='blank':
        component['mouth_allowance_cm']=5
        component['mouth_allowance_policy']='owner_default_blank_5cm_20261026'
    elif state=='not_applicable':
        component['mouth_allowance_cm']=0
    elif state=='unclear':
        raise ValueError('Miệng túi không đọc rõ; không coi số mờ là để trống')
    value=component.get('mouth_allowance_cm')
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:
        raise ValueError('Số cộng miệng túi không hợp lệ')
    return value

