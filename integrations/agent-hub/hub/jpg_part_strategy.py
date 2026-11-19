"""Catalog is an executable constraint before group selection."""
import copy

# Earlier catalogs mixed a pending native check with genuinely missing source.
GROUP_CHECK_NOTES = {
    'Cần xác minh group artwork trên file AI.',
    'Cần xác minh artwork là group vector hoàn chỉnh trong file AI.',
    'Cần xác minh artwork là group vector để tách khỏi nền maket.',
    'Cần xác minh group artwork trên maket có phải là file vector gốc không',
    'Cần xác minh group artwork trên maket có phải là file vector gốc không.',
}

def prepare_rows(rows, scan=None):
    import re
    result=copy.deepcopy(rows)
    fabric_miss_kws=('kích thước vải', 'kt vải', 'khổ vải', 'vải cắt thực tế')
    for row in result:
        dim_str=str(row.get('dimensions') or '')
        m=re.search(r'(\d+(?:[.,]\d+)?)\s*[xX×*]\s*(\d+(?:[.,]\d+)?)', dim_str)
        deferred=[]
        inferred_from_bag=False
        for x in row.get('missing',[]):
            low=str(x).lower()
            if x in GROUP_CHECK_NOTES or (dim_str and ('cữ trái/phải' in low or ('cữ' in low and 'canh giữa' in low))):
                deferred.append(x)
            elif any(k in low for k in fabric_miss_kws) and (m or (scan and scan.get('candidates'))):
                deferred.append(x)
                inferred_from_bag=True
        row['missing']=[x for x in row.get('missing',[]) if x not in deferred]
        if inferred_from_bag and row.get('kind') in ('single_face','separate_faces'):
            fw=fh=None
            if m:
                a=float(m.group(1).replace(',','.'))
                b=float(m.group(2).replace(',','.'))
                low_dim=dim_str.lower()
                cao_i=low_dim.find('cao');ngang_i=low_dim.find('ngang')
                if cao_i>=0 and ngang_i>=0 and cao_i<ngang_i:
                    fh,fw=a,b
                else:
                    fw,fh=a,b
            elif scan and scan.get('candidates'):
                bag_paths=[c for c in scan['candidates'] if c.get('kind')=='PathItem' and 20<=c.get('width_cm',0)<=55 and 20<=c.get('height_cm',0)<=55]
                if bag_paths:
                    best=max(bag_paths, key=lambda c: c.get('width_cm',0)*c.get('height_cm',0))
                    fw=float(round(best['width_cm']))
                    fh=float(round(best['height_cm']))
            if fw is not None and fh is not None and 10<=fw<=60 and 10<=fh<=60:
                raw_w=round(fw+5.0,2)
                raw_h=round(fh+5.0,2)
                row['inferred_fabric_cm']=[raw_w,raw_h]
                row['inferred_finished_cm']=[fw,fh]
                row['dimensions']=f"{raw_w:g}x{raw_h:g}cm (KT vải test tự suy từ túi {fw:g}x{fh:g}cm)"
        row['pending_checks']=list(row.get('pending_checks',[]))
        if deferred and 'native_artwork_group' not in row['pending_checks']:
            row['pending_checks'].append('native_artwork_group')
        row['deferred_group_notes']=deferred
        if not row['missing'] and 'native_artwork_group' in row['pending_checks']:
            row['status']='awaiting_native_selection'
    return result

def resolve_groups(rows, plan, selection, objects):
    """Only resolve for the specific part backed by verified native face IDs."""
    known={o['id']:o for o in objects}
    faces={f['side']:set(f['object_ids']) for f in selection.get('faces',[]) if f.get('maket_evidence')}
    for row in rows:
        panels=[p for p in plan.get('panels',[]) if p.get('part_key')==row['key']]
        if row.get('kind')=='solid_meter' and panels and all(p.get('kind')=='meter_fabric' and p.get('background_object_id') in known and known[p['background_object_id']].get('native') for p in panels):
            if 'native_artwork_group' in row.get('pending_checks',[]):
                row['pending_checks'].remove('native_artwork_group')
                row.setdefault('resolved_checks',[]).append({'check':'native_artwork_group',
                    'object_ids':sorted({p['background_object_id'] for p in panels}),
                    'basis':'native scan + verified solid_meter background fill'})
            continue
        components=[c for p in panels for c in p.get('components',[])]
        if not components:
            if not faces and panels and all(p.get('background_object_id') in known and known[p['background_object_id']].get('native') for p in panels):
                if 'native_artwork_group' in row.get('pending_checks',[]):
                    row['pending_checks'].remove('native_artwork_group')
                    row.setdefault('resolved_checks',[]).append({'check':'native_artwork_group',
                        'object_ids':sorted({p['background_object_id'] for p in panels}),
                        'basis':'native scan + verified background-only panel'})
            continue
        valid=all(c.get('object_ids') and set(c['object_ids'])==faces.get(c.get('side'))
                  and all(i in known and known[i].get('native') for i in c['object_ids'])
                  for c in components)
        if not valid:continue
        if 'native_artwork_group' in row.get('pending_checks',[]):
            row['pending_checks'].remove('native_artwork_group')
            row.setdefault('resolved_checks',[]).append({'check':'native_artwork_group',
                'object_ids':sorted({i for c in components for i in c['object_ids']}),
                'basis':'native scan + validated face selection + bound panel components'})
    return rows

def table(catalog, page=1):
    rows=[]
    for model in catalog['models']:
        for p in model['parts']:
            if page not in p.get('boards',[]):continue
            row=copy.deepcopy(p);row['model_code']=model['code']
            row['key']=model['code']+':'+p['id']
            row['part_role']='supplement_meter' if row['kind'] in ('solid_meter','pattern_meter') else 'main_bag'
            row['parent_model_code']=model['code']
            rows.append(row)
    if not rows:raise ValueError('Chưa có phương án phần in cho trang nguồn')
    return rows

def constrain(plan, rows):
    bykey={r['key']:r for r in rows};seen=set();ready=[]
    for panel in plan['panels']:
        key=panel.get('part_key');row=bykey.get(key)
        if row is None:raise ValueError('Panel không thuộc bảng phương án đã lập')
        seen.add(key)
        if row['missing'] or row.get('pending_checks') or row['kind'] in ('unknown','pattern_meter','ready_layout'):
            plan.setdefault('blocked_parts',[]).append({'part':row['name'],'reason':'; '.join(row['missing']+row.get('pending_checks',[])) or 'Kiểu dàn cần bộ xử lý riêng/kiểm tra chu kỳ.'});continue
        expected='joined_two_faces' if row['kind']=='joined_faces' else 'meter_fabric' if row['kind']=='solid_meter' else 'separate_panel'
        if panel['construction']!=expected:raise ValueError('Bố trí khác phân loại: '+key)
        if (panel['kind']=='meter_fabric') != (row['kind']=='solid_meter'):raise ValueError('Sai loại tấm so với phương án')
        panel['part_strategy']=row
        if row['background_strategy']=='none' and panel.get('background_selection', {}).get('method') != 'enclosing_solid_fill' and panel.get('background_mode') != 'solid_cmyk':
            panel['background_object_id']=''
            panel['background_mode']='none'
            for c in panel.get('components',[]):c.pop('background_object_id',None)
        if row['background_strategy']=='continuous_stripes':
            if not panel.get('background_object_id'):raise ValueError('Thiếu group nền sọc liền')
            panel['background_mode']='continuous_stripes'
        ready.append(panel)
    for key,row in bykey.items():
        if key not in seen:plan.setdefault('blocked_parts',[]).append({'part':row['name'],'reason':'; '.join(row['missing']) or 'Chưa có panel tương ứng trong phương án xuất.'})
    plan['panels']=ready;plan['part_table']=rows
    return plan
