"""CANAVI complete-group selection; JPG geometry remains in jpg_plan."""
import copy
import json
import math
import re


def validate_scan(scan, digest, allow_multi=True):
    if scan.get('source_sha256') != digest or scan.get('truncated'):
        raise ValueError('Native scan thiếu hoặc khác file nguồn')
    if len(json.dumps(scan)) > 64_000_000:
        raise ValueError('Native scan quá lớn; cần tách nguồn')
    boards = scan.get('artboards', [])
    candidates = scan.get('candidates', [])
    if not (1 <= len(boards) <= (40 if allow_multi else 1)) or any(not b.get('preview') for b in boards) or not candidates:
        raise ValueError('Cần một artboard nguồn đầy đủ để chọn group JPG')
    ids = set()
    for c in candidates:
        if not re.fullmatch(r'\d+(?:\.\d+)+', c.get('id', '')) or c['id'] in ids:
            raise ValueError('Native ID không hợp lệ')
        ids.add(c['id'])
        b = c.get('bounds', [])
        if len(b) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in b) or b[2] <= b[0] or b[1] <= b[3] or not c.get('preview'):
            raise ValueError('Native bounds/preview không hợp lệ')
    return scan


SUBLIMATION_SCOPE = 'PHẠM VI JPG CHUYỂN NHIỆT: chỉ chọn, bố trí và kiểm tra đầy đủ các artwork thuộc kỹ thuật chuyển nhiệt của lượt xuất. Maket có thể đồng thời chứa in lưới hoặc kỹ thuật khác. Khi nhãn/mũi tên trên nguồn hoặc chỉ dẫn chủ xưởng xác định artwork thuộc in lưới, loại phần đó khỏi phạm vi JPG; không báo thiếu hoặc issues vì phần in lưới không nằm trong file chuyển nhiệt, không đưa nó vào kế hoạch. Vẫn giữ đầy đủ nền màu/chi tiết trắng thuộc artwork chuyển nhiệt. Chưa xác định được kỹ thuật của một chi tiết hoặc thiếu chi tiết chuyển nhiệt thật thì vẫn báo issues; không tự bỏ lỗi hay bỏ artwork chưa rõ.'

def scope_ask(ask):
    def scoped(prompt, parts, schema, **kwargs):
        return ask(SUBLIMATION_SCOPE+"\n"+prompt, parts, schema, **kwargs)
    return scoped


def _build_draft_plan_on_error(plan, objects, selection, regions, kept, digest):
    from hub.jpg_plan import jpg_size, single_face_fabric_size
    draft = copy.deepcopy(plan) if isinstance(plan, dict) else {'panels': []}
    by_id = {o['id']: {k: v for k, v in o.items() if k != 'preview'} for o in (objects or []) if isinstance(o, dict) and o.get('id')}
    for panel in draft.get('panels', []):
        w = panel.get('width_cm')
        h = panel.get('height_cm')
        w_val = round(float(w), 2) if isinstance(w, (int, float)) and math.isfinite(w) and w > 0 else 45.0
        h_val = round(float(h), 2) if isinstance(h, (int, float)) and math.isfinite(h) and h > 0 else 50.0
        panel['width_cm'] = w_val
        panel['height_cm'] = h_val
        if not isinstance(panel.get('output_cm'), list) or len(panel.get('output_cm', [])) != 2:
            try:
                sw, sh = single_face_fabric_size(panel, w_val, h_val)
                ow, oh = jpg_size(sw, sh, panel.get('canvas_basis') if panel.get('canvas_basis') in ('raw_fabric', 'explicit_output') else 'raw_fabric', panel.get('kind', 'bag_panel'))
            except Exception:
                ow, oh = w_val, h_val
            panel['output_cm'] = [round(ow, 2), round(oh, 2)]
        panel['corner_marks'] = panel.get('kind') != 'meter_fabric'
        used_ids = []
        if panel.get('background_object_id') and panel['background_object_id'] in by_id:
            used_ids.append(panel['background_object_id'])
        for c in panel.get('components', []):
            if not c.get('object_ids'):
                matching = [f for f in (selection or {}).get('faces', []) if f.get('side') == c.get('side')] or (selection or {}).get('faces', [])[:1]
                c['object_ids'] = list(matching[0].get('object_ids', [])) if matching else ([kept[0]['id']] if kept else [])
            for oid in c.get('object_ids', []):
                if oid in by_id and oid not in used_ids:
                    used_ids.append(oid)
            src_objs = [by_id[oid] for oid in c.get('object_ids', []) if oid in by_id]
            if not isinstance(c.get('width_cm'), (int, float)) or c.get('width_cm', 0) <= 0:
                if src_objs:
                    b = [o['bounds'] for o in src_objs]
                    c['width_cm'] = round((max(x[2] for x in b) - min(x[0] for x in b)) * 2.54 / 72, 2)
                else:
                    c['width_cm'] = 20.0
            c.setdefault('preserve_native_size', True)
            if not isinstance(c.get('y_cm'), (int, float)):
                mt = c.get('maket_top_cm')
                ma = c.get('mouth_allowance_cm')
                mt_v = float(mt) if isinstance(mt, (int, float)) and math.isfinite(mt) and mt >= 0 else 5.0
                ma_v = float(ma) if isinstance(ma, (int, float)) and math.isfinite(ma) and ma >= 0 else 5.0
                c['y_cm'] = round(mt_v + ma_v, 2)
            if not isinstance(c.get('x_cm'), (int, float)):
                c['x_cm'] = 0.0
            if c.get('horizontal_alignment') not in ('left', 'center', 'right'):
                c['horizontal_alignment'] = 'center' if c.get('horizontal_symmetry') else 'left'
            if panel.get('construction') == 'joined_two_faces':
                c['rotation'] = 0 if c.get('side') != 'back' else 180
                c['vertical_anchor'] = 'top' if c.get('side') != 'back' else 'bottom'
            else:
                c.setdefault('rotation', 0)
                c.setdefault('vertical_anchor', 'top')
        if not panel.get('objects'):
            panel['objects'] = [copy.deepcopy(by_id[oid]) for oid in used_ids if oid in by_id]
    draft.update(
        renderer='native_group_v1',
        source_sha256=digest,
        is_draft_plan=True,
        artwork_selection={
            'method': 'maket_complete_group',
            'faces': selection or {},
            'regions': (regions or {}).get('regions', []),
            'candidate_ids': [c['id'] for c in (kept or [])],
            'model': 'gemini-2.5-pro',
        },
    )
    return draft


def _maket_region_crops(scan, regions):
    """Crop padded high-res maket regions so dimension callouts per face remain legible."""
    boards = {b.get('index', idx): b for idx, b in enumerate(scan.get('artboards', [])) if b.get('preview')}
    if not boards or not isinstance(regions, dict):
        return []
    import base64, io
    from PIL import Image
    crops = []
    for idx, reg in enumerate(regions.get('regions', [])[:6]):
        box = reg.get('box')
        if not isinstance(box, list) or len(box) != 4:
            continue
        ab_idx = reg.get('artboard_index', 0)
        board = boards.get(ab_idx) or next(iter(boards.values()), None)
        if not board:
            continue
        try:
            im = Image.open(io.BytesIO(base64.b64decode(board['preview']))).convert('RGB')
        except Exception:
            continue
        w, h = im.size
        xmin, ymin, xmax, ymax = [max(0.0, min(1.0, float(v))) for v in box]
        if xmax <= xmin or ymax <= ymin:
            continue
        # Expand upward and sideways generously to capture vertical & left/right dimension callouts per face.
        pad_top = max(0.18, (ymax - ymin) * 0.45)
        pad_side = max(0.14, (xmax - xmin) * 0.35)
        pad_bottom = max(0.08, (ymax - ymin) * 0.20)
        left = max(0, int(round((xmin - pad_side) * w)))
        top = max(0, int(round((ymin - pad_top) * h)))
        right = min(w, int(round((xmax + pad_side) * w)))
        bottom = min(h, int(round((ymax + pad_bottom) * h)))
        if right <= left or bottom <= top:
            continue
        buf = io.BytesIO()
        im.crop((left, top, right, bottom)).save(buf, format='PNG')
        label = reg.get('visible_text_or_logo') or reg.get('description') or f'region_{idx}'
        crops.append({'text': f'MAKET_REGION_CROP {idx} (artboard={ab_idx}, label={label}): ảnh phóng to quanh vùng maket để đọc rõ số cữ dọc/ngang riêng của từng mặt'})
        crops.append({'inline_data': {'mime_type': 'image/png', 'data': base64.b64encode(buf.getvalue()).decode()}})
    return crops


def _filter_slip_and_ai_parts(parts, scan=None, keep_file_pages=False):
    """Keep production-slip sources and AI-extracted artboards, dropping redundant standalone maket images."""
    has_ai_artboards = isinstance(scan, dict) and bool(scan.get('artboards')) and bool(scan.get('candidates'))
    if not has_ai_artboards or not isinstance(parts, list):
        return parts
    slip_kws = (
        'mã sản phẩm', 'ngày đặt hàng', 'ngày giao hàng', 'tên sản phẩm',
        'số lượng', 'định lượng', 'màu vải', 'kt vải', 'quy cách', 'nhà mỹ hân',
    )
    maket_kws = ('cữ in', 'kích thước artwork', 'kích thước in', 'logo bắt màu')
    maket_req_kws = ('cữ in', 'kích thước artwork', 'kích thước in')
    slip_msg_ids = set()
    msg_req_texts = {}
    hdr_idx = None
    hdr_data = None
    for idx, p in enumerate(parts):
        if isinstance(p, dict) and isinstance(p.get('text'), str) and p['text'].lstrip().startswith('{'):
            try:
                obj = json.loads(p['text'])
            except (ValueError, TypeError):
                obj = None
            if isinstance(obj, dict) and isinstance(obj.get('brief'), dict):
                hdr_idx = idx
                hdr_data = copy.deepcopy(obj)
                for req in hdr_data['brief'].get('requirements', []):
                    mid = str(req.get('message_id') or '')
                    txt = str(req.get('text') or '').casefold()
                    if not mid:
                        continue
                    msg_req_texts.setdefault(mid, []).append(txt)
                    if any(k in txt for k in slip_kws):
                        slip_msg_ids.add(mid)
                break
    maket_msg_ids = set()
    if slip_msg_ids:
        for mid, texts in msg_req_texts.items():
            if mid in slip_msg_ids:
                continue
            if texts and all(any(k in t for k in maket_kws) for t in texts):
                maket_msg_ids.add(mid)
        if hdr_data is not None and isinstance(hdr_data.get('brief'), dict):
            reqs = hdr_data['brief'].get('requirements', [])
            cleaned_reqs = []
            for req in reqs:
                mid = str(req.get('message_id') or '')
                txt = str(req.get('text') or '').casefold()
                if mid in maket_msg_ids:
                    continue
                if any(k in txt for k in maket_req_kws):
                    continue
                cleaned_reqs.append(req)
            hdr_data['brief']['requirements'] = cleaned_reqs
    out = []
    skip_next_img = False
    for idx, p in enumerate(parts):
        if skip_next_img and isinstance(p, dict) and 'inline_data' in p:
            skip_next_img = False
            continue
        skip_next_img = False
        if idx == hdr_idx and hdr_data is not None:
            out.append({'text': json.dumps(hdr_data, ensure_ascii=False)})
            continue
        txt = p.get('text') if isinstance(p, dict) else None
        if isinstance(txt, str):
            if not keep_file_pages and txt.startswith('file_page:'):
                skip_next_img = True
                continue
            m = re.match(r'^message:(\S+)', txt)
            if m and m.group(1) in maket_msg_ids:
                skip_next_img = True
                continue
        out.append(p)
    return out


def prepare(ask, scan, parts, refs, prompt, schema, digest, part_table=None):
    ask = scope_ask(ask)
    from hub.native_auto import (coordinate_preview, region_box,
        validate_artwork_evidence, region_candidates, candidates_parts, LOGO_FILL_POLICY)
    from hub.jpg_plan import validate
    scan = validate_scan(scan, digest, allow_multi=False)
    parts = _filter_slip_and_ai_parts(parts, scan)
    if len([p for p in parts if 'inline_data' in p])>8:raise ValueError('Hơn 8 ảnh nguồn; cần tách đúng maket')
    # Do not send the old PDF object tree or hundreds of native candidates to AI.
    context = []
    for part in parts:
        if 'text' in part:
            try:
                value = json.loads(part['text'])
            except (ValueError, TypeError):
                value = None
            if isinstance(value, dict) and 'technical' in value:
                value = copy.deepcopy(value)
                value['technical'].pop('object_inventory', None)
                value['technical'].pop('native_groups', None)
                part = {'text': json.dumps(value, ensure_ascii=False)}
        context.append(part)
    if not part_table: raise ValueError('Cần lập bảng phương án xuất trước khi chọn group')
    from hub.jpg_part_strategy import prepare_rows
    part_table=prepare_rows(part_table, scan=scan)
    context.append({'text':'PART_EXPORT_TABLE: '+json.dumps(part_table,ensure_ascii=False)})
    if any(r.get('inferred_fabric_cm') for r in part_table):
        context.append({'text':'QUY TẮC ĐƠN IN TEST MẶT IN (TỰ SUY KHỔ VẢI TỪ KÍCH THƯỚC TÚI): PART_EXPORT_TABLE đã tự suy khổ vải test inferred_fabric_cm=[W, H] từ kích thước túi thành phẩm (+5cm mỗi chiều). BẮT BUỘC dùng canvas_basis="raw_fabric", width_cm=W, height_cm=H, finished_width_cm=inferred_finished_cm[0], finished_height_cm=inferred_finished_cm[1], chọn đúng PathItem màu nền CMYK của artboard hiện tại vào background_object_id, căn giữa logo (horizontal_alignment="center", horizontal_symmetry=true) và trả issues=[]. Tuyệt đối không báo thiếu KT VẢI hay thiếu cữ dọc (nếu maket chỉ ghi chiều cao phần đáy trắng như 8.6cm mà không ghi cữ từ miệng xuống logo, dùng maket_top_cm=2.5 và mouth_allowance_cm=5).'})
    if all(r.get('kind')=='solid_meter' for r in part_table):
        fills = sorted([c for c in scan['candidates'] if _is_solid_fill_candidate(c) and not c.get('verified_white_fill')], key=lambda c: (not _is_near_white_or_gray(_dominant_rgb(c)), (c['bounds'][2]-c['bounds'][0])*(c['bounds'][1]-c['bounds'][3])), reverse=True)[:12]
        if not fills:
            raise ValueError('Chưa có PathItem màu CMYK gốc cho phần vải mét màu trơn')
        panels = []
        for r in part_table:
            if r.get('missing'):
                raise ValueError('; '.join(r['missing']))
            m = re.search(r'(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)', str(r.get('dimensions') or ''))
            h_cm = 20.0
            if m:
                a, b = float(m.group(1).replace(',', '.')), float(m.group(2).replace(',', '.'))
                h_cm = b if abs(a - 160) < 5 else (a if abs(b - 160) < 5 else 20.0)
            if len(fills) == 1:
                bg_id = fills[0]['id']
            else:
                pick_schema = {'type':'object','required':['background_object_id','height_cm'],'properties':{'background_object_id':{'type':'string','enum':[f['id'] for f in fills]},'height_cm':{'type':'number'}}}
                pick = ask('JPG_LAYOUT_ONLY: Chỉ chọn đúng 1 PathItem màu CMYK gốc (background_object_id) khớp với màu quai/túi con trên maket/phiếu và chiều cao khổ (mặc định 20cm nếu chỉ có dây quai).', context + candidates_parts(dict(scan, candidates=fills)), pick_schema, model='gemini-2.5-pro')
                bg_id = pick['background_object_id']
                if pick.get('height_cm') and 5 <= pick['height_cm'] <= 200:
                    h_cm = float(pick['height_cm'])
            if 'native_artwork_group' in r.get('pending_checks', []):
                r['pending_checks'].remove('native_artwork_group')
                r.setdefault('resolved_checks', []).append({'check': 'native_artwork_group', 'object_ids': [bg_id], 'basis': 'solid_meter native fill match'})
                r['status'] = 'ready'
            panels.append({
                'name': r['id'], 'part_key': r['key'], 'kind': 'meter_fabric', 'construction': 'meter_fabric',
                'canvas_basis': 'explicit_output', 'width_cm': 160.0, 'height_cm': h_cm,
                'sources': [s for s in (r.get('sources') or []) if s in refs] or refs[:1],
                'basis_explanation': f"Vải mét màu trơn {r['name']} khổ 160x{h_cm}cm",
                'background_mode': 'matched_group', 'background_object_id': bg_id, 'components': [],
            })
        plan = {'process': 'sublimation', 'order_code': part_table[0]['model_code'], 'issues': [], 'panels': panels}
        from hub.jpg_part_strategy import constrain
        plan = validate(plan, [dict(f, page=1, native=True) for f in fills], refs)
        return constrain(plan, part_table), context
    board = scan['artboards'][0]
    localization = [{'text': 'SOURCE_ARTBOARD 0'}, {'inline_data': {
        'mime_type': 'image/png', 'data': coordinate_preview(board['preview'])}}]
    region_schema = {'type': 'object', 'required': ['regions', 'issues'], 'properties': {
        'no_logo_background_only': {'type': 'boolean'},
        'artboard_cmyk_note': {'type': 'array', 'items': {'type': 'number'}},
        'issues': {'type': 'array', 'items': {'type': 'string'}},
        'regions': {'type': 'array', 'items': {'type': 'object',
            'required': ['artboard_index', 'box_2d', 'visible_text_or_logo'],
            'properties': {'artboard_index': {'type': 'integer'},
                'box_2d': {'type': 'array', 'items': {'type': 'number'}},
                'visible_text_or_logo': {'type': 'string'}}}}}}
    localization.append({'text':'PART_EXPORT_TABLE: '+json.dumps(part_table,ensure_ascii=False)})
    regions = ask('ARTBOARD_LOCALIZATION_ONLY: Chỉ khoanh logo/chữ cần in thuộc phần thân đủ nguồn trong PART_EXPORT_TABLE. Không khoanh nền sọc, quai, phần missing hay phần chờ review. Nếu mặt túi CHỈ có nền sọc hoặc nền màu trơn và HOÀN TOÀN KHÔNG có logo/chữ in nào cần khoanh, đặt no_logo_background_only=true, trả regions=[] và issues=[]. Không trả region với visible_text_or_logo rỗng. Khoanh sát logo và nền trắng đi kèm, không cả mặt túi. Khoanh vùng artwork đứng thẳng trên SOURCE_ARTBOARD, box_2d [ymin,xmin,ymax,xmax] 0..1000. Lưới X theo chiều ngang, Y theo chiều cao. Đọc chữ/logo thật vào visible_text_or_logo; không khoanh cả túi, đường đo hoặc ghi chú. Vùng chỉ định hướng tìm group; giữ nền màu thuộc logo. Không suy kích thước xuất ở bước này. Nếu góc/trên SOURCE_ARTBOARD có ghi chú thông số CMYK màu nền test dạng C-M-Y-K (ví dụ "210 / 0-39-6-0", "226 / 0-99-0-0", "211 / 0-55-8-0"), trích 4 số [C, M, Y, K] vào artboard_cmyk_note (nếu không có ghi chú CMYK thì bỏ qua hoặc để mảng rỗng). ' + LOGO_FILL_POLICY,
        localization, region_schema, model='gemini-2.5-pro')
    no_logo_bg = bool(regions.get('no_logo_background_only') and not regions.get('regions') and not regions.get('issues'))
    if no_logo_bg:
        kept = []
    elif regions.get('issues') or not 1 <= len(regions.get('regions', [])) <= 8:
        fallback_groups = [c for c in scan.get('candidates', []) if c.get('kind') in ('GroupItem', 'RasterItem') and c['id'].count('.') <= 2 and c.get('width_cm', 0) >= 1 and c.get('height_cm', 0) >= 1][:8]
        if not fallback_groups:
            raise ValueError('Chưa rõ vùng artwork JPG: ' + '; '.join(regions.get('issues', [])))
        kept = fallback_groups
    else:
        for idx, region in enumerate(regions['regions']):
            region['box'] = region_box(region)
            try:
                region['description'] = validate_artwork_evidence(region)
            except ValueError:
                region['description'] = str(region.get('visible_text_or_logo', '')).strip() or f'artwork_region_{idx+1}'
        try:
            kept = region_candidates(scan, regions['regions'])
        except ValueError:
            kept = [c for c in scan.get('candidates', []) if c.get('kind') in ('GroupItem', 'RasterItem') and c['id'].count('.') <= 2 and c.get('width_cm', 0) >= 1 and c.get('height_cm', 0) >= 1][:8]
            if not kept:
                raise
        large_top = [c for c in kept if c['id'].count('.') == 1 and c.get('width_cm', 0) >= 5 and c.get('height_cm', 0) >= 5]
        if len(large_top) < 2:
            kept_ids = {c['id'] for c in kept}
            extra_top = [c for c in scan.get('candidates', []) if c['id'] not in kept_ids and c['id'].count('.') == 1 and c.get('kind') in ('GroupItem', 'RasterItem') and c.get('width_cm', 0) >= 5 and c.get('height_cm', 0) >= 5 and c.get('name') != 'Manual Dimension'][:4]
            kept = kept + extra_top
    objects = [dict(c, page=1, native=True) for c in kept]
    # Source solid fills and stripe/pattern background groups remain selectable without treating them as logo artwork.
    fills = sorted([c for c in scan['candidates'] if _is_solid_fill_candidate(c)], key=lambda c: (not _is_near_white_or_gray(_dominant_rgb(c)), (c['bounds'][2]-c['bounds'][0])*(c['bounds'][1]-c['bounds'][3])), reverse=True)[:12]
    bg_groups = sorted([c for c in scan['candidates'] if c.get('kind') == 'GroupItem' and c['id'].count('.') <= 2 and 10 <= c.get('width_cm', 0) <= 180 and 10 <= c.get('height_cm', 0) <= 180], key=lambda c: (c['bounds'][2]-c['bounds'][0])*(c['bounds'][1]-c['bounds'][3]), reverse=True)[:8]
    bg_candidates = fills + [c for c in bg_groups if c['id'] not in {f['id'] for f in fills}]
    for c in bg_candidates:
        if c['id'] not in {o['id'] for o in objects}:
            objects.append(dict(c, page=1, native=True))
    visual = context + localization + candidates_parts(dict(scan, candidates=objects))
    if no_logo_bg:
        selection = {'same_artwork_both_sides': True, 'reason': 'Mặt túi chỉ có nền (không có logo rời)', 'issues': [], 'faces': []}
        anchors = []
        visual += [{'text': 'VERIFIED_SIDE_SELECTION: Không có logo rời; mặt túi chỉ có nền (chọn background_object_id và trả components=[]).'}]
    else:
        # Resolve side identity from the maket BEFORE geometry; no implicit duplication.
        selection_schema = {'type':'object','required':['same_artwork_both_sides','reason','issues','faces'], 'properties':{
            'same_artwork_both_sides':{'type':'boolean'}, 'reason':{'type':'string'},
            'issues':{'type':'array','items':{'type':'string'}},
            'faces':{'type':'array','items':{'type':'object','required':['side','object_ids','maket_evidence'], 'properties':{
                'side':{'type':'string','enum':['front','back','other']},
                'object_ids':{'type':'array','items':{'type':'string','enum':[c['id'] for c in kept]}},
                'maket_evidence':{'type':'string'}, 'bleed_evidence':{'type':'string'}}}}}}
        # Pixel evidence is a warning, not a destructive removal of source paths.
        import base64, io
        from PIL import Image
        edge_evidence=[]
        for candidate in kept:
            im=Image.open(io.BytesIO(base64.b64decode(candidate['preview']))).convert('RGBA')
            alpha=im.getchannel('A');coverage=sum(v for v in alpha.getdata())/(255*im.width*im.height)
            pixels=im.load();edge=[pixels[x,0] for x in range(im.width)]+[pixels[x,im.height-1] for x in range(im.width)]+[pixels[0,y] for y in range(im.height)]+[pixels[im.width-1,y] for y in range(im.height)]
            black=sum(1 for r,g,b,a in edge if max(r,g,b)<85 and a>180)/len(edge)
            edge_evidence.append({'id':candidate['id'],'opaque_fraction':round(coverage,3),'black_rectangle_edge_fraction':round(black,3),'panel_frame_warning':coverage>.98 and black>.5})
        worker_cap = {'text': 'WORKER_CAPABILITY: Với background_strategy=continuous_stripes, worker trải nền sọc gốc qua background_object_id và tự dựng nền trắng dưới logo từ vùng trống (knockout) của sọc nguồn, giữ chiều cao và cộng tổng 1 ô sọc vào chiều ngang. Nền trắng này và nền sọc KHÔNG nằm trong VERIFIED_SIDE_SELECTION; BẮT BUỘC chọn group logo rời (ví dụ 0.4, 0.8) vào faces cho front/back và trả issues=[]. TUYỆT ĐỐI KHÔNG báo lỗi/issues rằng artwork bị tách rời khỏi nền sọc hay thiếu candidate mảng trắng.'}
        side_visual=context+localization+candidates_parts(dict(scan,candidates=kept))+[{'text':'CODE_IMAGE_EVIDENCE: '+json.dumps(edge_evidence)}, worker_cap]
        selection_schema['required'].append('equivalent_artworks')
        selection_schema['properties']['equivalent_artworks']={'type':'array','items':{'type':'object','required':['ids','same_print_content','reason'],'properties':{'ids':{'type':'array','items':{'type':'string','enum':[c['id'] for c in kept]}},'same_print_content':{'type':'boolean'},'reason':{'type':'string'}}}}
        selection = ask('JPG_LAYOUT_ONLY: BƯỚC CHỌN RIÊNG ARTWORK TỪNG MẶT, chưa tính cữ/khổ. Trả equivalent_artworks cho các candidate cùng nội dung in (cùng đủ chữ, logo, chi tiết), cho phép khác nền vải/khung mô phỏng và phần tràn. Nếu khác chữ/logo/thiếu chi tiết thì same_print_content=false. Không coi khác nền vải là khác nội dung logo. Giải thích so sánh các candidate. Đọc maket và ảnh NATIVE_CANDIDATE. Xác định front/back bằng hình và chữ trên từng mặt. Phân biệt artwork sản xuất tràn viền với group mô tả mặt túi chứa nền/khung thành phẩm. Không chọn khung mô tả chỉ vì nó giống mặt túi đầy đủ. QUAN TRỌNG: nền xanh/màu phẳng hoặc nền sọc phủ cả hình chữ nhật KHÔNG phải bằng chứng tràn artwork. Nền vải (màu phẳng hoặc group sọc) có background_object_id riêng được trải toàn khổ. Khi có group artwork rời chứa đủ logo/chữ và bản dựng cùng logo trên khung mặt túi thì chọn group artwork rời cho việc in, nền vải xử lý riêng. Nếu maket hiển thị khối màu nền (ví dụ tím/xanh/đen) chứa logo chữ trắng bên trong mà NATIVE_CANDIDATE chỉ có group logo chữ trắng rời (và PathItem màu nền riêng), BẮT BUỘC chọn group logo rời đó vào `faces` (tuyệt đối KHÔNG báo lỗi thiếu candidate chứa cả khối màu nền, vì màu nền sẽ được gán riêng qua `background_object_id` hoặc `background_cmyk`). Nếu một mặt túi (ví dụ mặt sau của túi nền sọc như FANATION) CHỈ có nền sọc mà không có logo rời trên mặt đó, chỉ cần trả mặt có logo trong `faces` (nền sọc sẽ được trải cho toàn tấm qua `background_object_id`). So sánh hình dạng và bố cục thực của mảng logo, đặc biệt vùng vượt mép phải/trái; không dùng câu in full túi để chọn bản có khung. Phải nhìn và giải thích cụ thể khác biệt giữa các candidate; không chỉ dẫn lại yêu cầu chung. Giữ nền màu thuộc chính logo. Nếu hai mặt có cùng nội dung artwork và có bản artwork tràn viền, ưu tiên bản tràn viền đó cho CẢ HAI mặt; ghi same_artwork_both_sides=true và chứng cứ cụ thể. Nếu khác nội dung/bố cục cần in, chọn group riêng tương ứng, không nhân đôi. Phần tràn được khách chủ ý in lên vải dư để may không hở trắng, phải giữ, không cắt theo khung thành phẩm. Không tự gỡ chi tiết trong group. Ghi rõ maket_evidence từng mặt. Quy tắc chủ xưởng: artwork có tràn hoặc không tràn đều hợp lệ, phụ thuộc logo và cữ khách. bleed_evidence chỉ là ghi chú tùy chọn, được để trống; tuyệt đối không ghi issues hoặc từ chối chọn mặt chỉ vì không có/chưa có bằng chứng tràn. Giữ phần tràn nguồn nếu có, không tự thêm tràn hoặc đổi kích thước. CODE_IMAGE_EVIDENCE panel_frame_warning=true nghĩa preview phủ kín nền và có khung đen quanh biên. Nếu có artwork tương đương không khung, ưu tiên artwork không khung để đặt lên nền vải riêng. Không coi nền phẳng là phần tràn của logo. Không đoán từ ID hay diện tích group. QUY TẮC MẶT TRƯỚC / MẶT SAU TRÊN MAKET 2 TÚI ĐẶT CẠNH NHAU: Theo chuẩn bảng Maket trên phiếu lệnh CANAVI (cột trái là Mặt trước, cột phải là Mặt sau), khi trên một artboard có 2 hình túi đặt cạnh nhau theo chiều ngang với 2 logo khác nhau (same_artwork_both_sides=false) và không có chữ ghi chú đảo ngược rõ ràng, hình túi BÊN TRÁI (tọa độ X nhỏ hơn) BẮT BUỘC là mặt trước (side="front") và hình túi BÊN PHẢI (tọa độ X lớn hơn) BẮT BUỘC là mặt sau (side="back").',
            side_visual, selection_schema, model='gemini-2.5-pro')
        if any(r.get('background_strategy') == 'continuous_stripes' for r in part_table) and selection.get('faces') and selection.get('issues'):
            selection['issues'] = [iss for iss in selection['issues'] if not any(k in iss.casefold() for k in ('nền sọc', 'mảng trắng', 'tách rời'))]
        selection = prefer_unframed_equivalent(selection, edge_evidence)
        from hub.jpg_white_backing import complete_faces
        selection = complete_faces(selection, scan)
        if not selection.get('same_artwork_both_sides') and {f.get('side') for f in selection.get('faces', [])} == {'front', 'back'}:
            f_face = next(f for f in selection['faces'] if f.get('side') == 'front')
            b_face = next(f for f in selection['faces'] if f.get('side') == 'back')
            if set(f_face.get('object_ids', [])) != set(b_face.get('object_ids', [])):
                by_cid = {c['id']: c for c in scan['candidates']}
                f_bs = [by_cid[i]['bounds'] for i in f_face.get('object_ids', []) if i in by_cid]
                b_bs = [by_cid[i]['bounds'] for i in b_face.get('object_ids', []) if i in by_cid]
                if f_bs and b_bs:
                    cx_f = (min(x[0] for x in f_bs) + max(x[2] for x in f_bs)) / 2.0
                    cx_b = (min(x[0] for x in b_bs) + max(x[2] for x in b_bs)) / 2.0
                    w_max = max(max(x[2] for x in f_bs) - min(x[0] for x in f_bs), max(x[2] for x in b_bs) - min(x[0] for x in b_bs))
                    ev_txt = (str(f_face.get('maket_evidence', '')) + ' ' + str(b_face.get('maket_evidence', ''))).casefold()
                    if cx_f > cx_b + max(50.0, w_max * 0.5) and not any(k in ev_txt for k in ('bên phải là mặt trước', 'phải: mặt trước', 'túi phải là mặt trước')):
                        f_face['object_ids'], b_face['object_ids'] = b_face['object_ids'], f_face['object_ids']
                        f_face['maket_evidence'], b_face['maket_evidence'] = b_face.get('maket_evidence', ''), f_face.get('maket_evidence', '')
        selected_ids = {i for f in selection['faces'] for i in f['object_ids']}
        for c in scan['candidates']:
            if c['id'] in selected_ids and c['id'] not in {k['id'] for k in kept}:
                kept.append(c)
                objects.append(dict(c, page=1, native=True))
        validate_faces(selection, {c['id'] for c in kept})
        visual = visual + [{'text':'VERIFIED_SIDE_SELECTION (layout MUST use these IDs per side): '+json.dumps(selection,ensure_ascii=False)}]
        # Only inspect descendants of already selected artwork, never the entire document.
        anchors = [c for c in scan['candidates'] if any(c['id'].startswith(i+'.') for i in selected_ids)]
        if len(anchors)>32:
            anchors = [c for c in anchors if c['kind'] in ('GroupItem','RasterItem','PluginItem')][:32]
        visual += [{'text':'MEASUREMENT_ONLY: các object con sau chỉ dùng đo cữ. KHÔNG thay group xuất bằng object con.'}]
        visual += candidates_parts(dict(scan,candidates=anchors)) if anchors else []
    visual += _maket_region_crops(scan, regions)
    schema=copy.deepcopy(schema)
    panel_schema=schema['properties']['panels']['items']['properties']
    panel_schema['part_key']={'type':'string','enum':[r['key'] for r in part_table]}
    panel_schema['edge_finish']={'type':'string','enum':['fold','sewn','unknown']}
    panel_schema['seam_allowance_cm']={'type':'number'}
    panel_schema['edge_finish_evidence']={'type':'string'}
    panel_schema['finished_width_cm']={'type':'number'}
    schema['properties']['panels']['items']['required'] += ['edge_finish','seam_allowance_cm','edge_finish_evidence']
    schema['properties']['panels']['items']['required'].append('part_key')
    panel_schema['sources']['items']={'type':'string','enum':list(dict.fromkeys(refs))}
    panel_schema['background_object_id']={'type':'string','enum':['']+[c['id'] for c in bg_candidates]}
    panel_schema['background_cmyk']={'type':'array','items':{'type':'number'}}
    panel_schema['components']['items']['properties']['sources']['items']={'type':'string','enum':list(dict.fromkeys(refs))}
    comp_schema=panel_schema['components']['items']
    # Source ownership belongs to selection, never to the geometry model.
    comp_schema['properties'].pop('object_ids', None)
    comp_schema['properties'].pop('width_cm', None)
    comp_schema['required'] = [k for k in comp_schema['required'] if k != 'width_cm']
    visual.append({'text':'OWNER_RULE: Không đổi kích thước artwork hai mặt. Code dùng đúng kích thước group nguồn, bao gồm nền trắng đã xác minh sau logo. Nền trắng của vải/maket không phải lớp nền in: dùng background_mode=none và không chọn background_object_id. CẨN THẬN NỀN MÀU NHẠT (nền kem / be / xám nhạt): KHÔNG nhầm nền kem/be nhạt (có solid_cmyk_fill=true, verified_white_fill=false) thành nền trắng; nếu artwork nằm trên PathItem nền màu đặc cỡ mặt túi (20..70cm), BẮT BUỘC chọn PathItem đó làm background_object_id. Chọn đúng group riêng từng mặt theo maket. Canh vị trí theo số cữ và yêu cầu khách; không chọn hoặc kiểm chứng khung native. Giữ phần tràn, không crop group. Chỉ dịch chuyển hoặc xoay theo phương án, không suy width từ số cữ.'})
    comp_schema['properties']['side'] = {'type': 'string', 'enum': [f['side'] for f in selection['faces']] or ['front', 'back', 'other']}
    comp_schema['required'] = [k for k in comp_schema['required'] if k != 'object_ids']
    for key in ('maket_top_cm','mouth_allowance_cm'):
        comp_schema['properties'][key]={'type':'number'}
        comp_schema['required'].append(key)
    comp_schema['properties']['mouth_allowance_source']={'type':'string','enum':['explicit','blank','not_applicable','unclear']}
    comp_schema['required'].append('mouth_allowance_source')
    comp_schema['properties']['vertical_evidence']={'type':'string'}
    comp_schema['required'].append('vertical_evidence')
    comp_schema['properties']['horizontal_symmetry']={'type':'boolean'}
    comp_schema['required'].append('horizontal_symmetry')
    comp_schema['properties']['horizontal_alignment_evidence']={'type':'string'}
    comp_schema['required'].append('horizontal_alignment_evidence')
    comp_schema['properties']['vertical_reference_object_id']={'type':'string','enum':['']+[c['id'] for c in anchors]}
    comp_schema['properties']['vertical_reference_evidence']={'type':'string'}
    # A selected reference ID cannot be emitted without its paired explanation.
    # No reference is represented by two empty strings; code still checks nonempty IDs.
    for key in ('vertical_reference_object_id','vertical_reference_evidence'):
        if key not in comp_schema['required']:comp_schema['required'].append(key)
    visual.append({'text':'Mỗi ID mốc cữ phải có bằng chứng đi kèm: vertical_reference_object_id/vertical_reference_evidence. Nếu không dùng mốc thì cả hai trường để chuỗi rỗng. Không chọn ID rồi bỏ bằng chứng.'})
    comp_schema['properties']['alignment_reference_box']={'type':'array','items':{'type':'number'}}
    comp_schema['properties']['alignment_reference_evidence']={'type':'string'}
    visual.append({'text':'Không chọn hay đối chiếu ID khung maket với artwork. Dùng số cữ và khổ xuất đã đọc từ phiếu/maket cùng yêu cầu khách để bố trí. Nếu đường đo tới một object con bên trong group nhiều lớp, ưu tiên vertical_reference_object_id và vertical_reference_evidence chỉ đúng chi tiết tại đầu đường đo; code tính cữ từ bounds thật object, không đoán tỷ lệ. Không chọn group cha có khoảng trống clipping làm mốc. alignment_reference_box chỉ dùng mốc ngang khi đã chọn object mốc dọc. Nếu không có object con đo được và khách đo cữ tới vùng bên trong artwork tràn viền, trả alignment_reference_box=[left,top,right,bottom] chuẩn hóa 0..1 trong group nguồn chưa xoay, và alignment_reference_evidence chỉ rõ vùng/đường đo. Giữ width_cm của toàn artwork, không crop phần tràn. Chưa xác định chính xác vùng thì báo issues, không đoán. Nếu đo tới biên toàn artwork thì không cần trường này.'})

    visual.append({'text':'WORKER_CAPABILITY: Với background_strategy=continuous_stripes, worker trải nền sọc gốc và tự dựng nền trắng dưới logo từ vùng trống (knockout) của sọc nguồn, giữ chiều cao và cộng tổng 1 ô sọc vào chiều ngang. Nền trắng này không bắt buộc có object riêng trong VERIFIED_SIDE_SELECTION; không báo thiếu chỉ vì faces chọn logo rời. Worker sẽ kiểm tra hình học sọc khi xuất. Nếu chủ xưởng xác nhận canh giữa logo và nền trắng, dùng horizontal_alignment=center và horizontal_symmetry=true, ưu tiên xác nhận này hơn cữ trái/phải trên maket.'})
    plan = ask('JPG_LAYOUT_ONLY\nCẤM làm tròn số đo: maket ghi 3.28 thì dùng3.28, không đổi thành3. Phân biệt GẤP MIỆNG và MAY: mặc định miệng túi là GẤP MIỆNG (edge_finish=fold, seam_allowance_cm=0) và cữ miệng túi mặc định 5cm cho cả 2 đầu trên/dưới; không tự cộng0.5. Chỉ dùng edge_finish=sewn khi phiếu/maket/xác nhận chủ xưởng ghi rõ may viền kèm số đường may. Nếu phiếu không ghi chữ gấp hay may, chọn edge_finish=fold, seam_allowance_cm=0 và ghi edge_finish_evidence là mặc định quy chuẩn xưởng, TUYỆT ĐỐI KHÔNG đặt unknown và KHÔNG báo issues thiếu seam_allowance_cm. maket_top_cm phải lấy đường đo DỌC từ mép trên thân túi (hoặc nét đứt miệng túi) xuống đỉnh logo, không lấy khoảng từ logo tới đáy và TUYỆT ĐỐI KHÔNG lấy đường đo NGANG vị trí quai túi ở mép trên cùng (ví dụ hai số ngang trái/phải từ cạnh túi vào chân quai như `12.5cm` / `12.5cm` là cữ quai túi, KHÔNG phải cữ in logo). Số đo nằm cạnh đường đo DỌC từ mép trên/miệng túi xuống đỉnh logo/chữ (ví dụ `3.28cm`, `3.33cm`, `5.6cm`) LUÔN LÀ CỮ DỌC (maket_top_cm), TUYỆT ĐỐI KHÔNG đọc nhầm thành cữ trái/phải (x_cm); chỉ dùng x_cm khi có đường đo NGANG rõ ràng từ cạnh trái hoặc cạnh phải thân túi vào mép artwork/nhân vật (ví dụ `6.05cm` và `6.05cm` ở hai bên thân túi — nếu hai bên bằng nhau thì đặt `horizontal_alignment=center`, `horizontal_symmetry=true`). PHÂN BIỆT CỮ DỌC (maket_top_cm) VÀ CỮ NGANG (x_cm): khi gần góc trên túi có cả đường đo DỌC từ mép miệng thành phẩm xuống đỉnh chi tiết cao nhất (ví dụ 4.4cm) VÀ đường đo NGANG từ cạnh trái/phải vào mép artwork (ví dụ 1.8cm), thì maket_top_cm BẮT BUỘC lấy số trên đường đo DỌC (4.4), TUYỆT ĐỐI KHÔNG lấy nhầm số cữ ngang (1.8) làm maket_top_cm. Khi artwork/mảng in chạm sát mép miệng túi hoặc mép trên thành phẩm thì đặt maket_top_cm = 0; tuyệt đối KHÔNG lấy chiều cao hình vẽ (ví dụ nhãn 16cm trên maket) làm maket_top_cm. Tương tự khi chạm mép trái thì x_cm = 0. Mỗi side chỉ xuất hiện một lần trong components; mặt chỉ có nền không tạo component logo. horizontal_symmetry=true khi maket có hai cữ ngang bằng nhau hoặc xác nhận căn giữa. Căn ngang theo maket: nếu hai cữ trái/phải bằng nhau hoặc có xác nhận căn giữa thì dùng center và horizontal_alignment_evidence dẫn bằng chứng; code căn giữa group nguyên kích thước trên khổ sau co. CĂN GIỮA NGANG (horizontal_symmetry / horizontal_alignment=center): khi maket của một mặt ghi hai cữ trái và phải bằng nhau (ví dụ 7.8cm và 7.8cm, hoặc hai bên đều nhau trên hình maket), HOẶC khi maket chỉ ghi 1 bên cữ ngang (ví dụ chỉ ghi trái 5cm) nhưng theo chiều ngang túi thành phẩm trên maket (điền `finished_width_cm` của panel theo maket nếu có) thì lề bên còn lại = finished_width_cm - logo_width - x_cm cũng bằng cữ đó (chênh <= 0.5cm), BẮT BUỘC đặt horizontal_symmetry=true và horizontal_alignment=center cho mặt đó — TUYỆT ĐỐI KHÔNG tự suy diễn "đo tới phần khác nhau" để chuyển thành left/right. Soi kỹ cả hai bên trái/phải và cả 4 góc (kể cả góc dưới trái/phải gần logo phụ như 3.3cm) trong MAKET_REGION_CROP cho cả front và back trước khi kết luận không có cữ ngang. Nếu mặt in KHÔNG có ghi chú/đường đo cữ trái hoặc phải riêng thì MẶC ĐỊNH căn giữa (horizontal_alignment=center, horizontal_symmetry=true, x_cm=0, horizontal_alignment_evidence="Mặc định căn giữa do không có ghi chú cữ trái/phải"); chỉ dùng left/right khi maket hoặc phiếu ghi rõ số cữ lệch trái/phải hoặc ghi sát/chạm mép. QUY TẮC XOAY 180° MẶT SAU (joined_two_faces): nếu mặt trước có cữ ngang lệch trái/phải rõ ràng (ví dụ trái 3.3cm) và mặt sau xoay 180° KHÔNG ghi số cữ ngang riêng trên maket, thì mặt sau lấy đúng số cữ đó từ mặt trước nhưng ĐẢO PHÍA NGƯỢC LẠI (mặt trước `left` -> mặt sau `right`, mặt trước `right` -> mặt sau `left`, KHÔNG đặt mặt sau về `center` hay giữ nguyên `left`). LƯU Ý TRỤC KHỔ VẢI TRÊN PHIẾU CANAVI: khi phiếu lệnh ghi `KT VẢI A X B` với A > B (ví dụ `88 X 49`, `88 X 47`, `88 X 50`, `104 X 40`, `92 X 38`), trong đó túi thành phẩm có Ngang ~ B-5 (44, 42, 45, 35, 33 cm) và Cao ~ 30..40 cm, thì B là CHIỀU NGANG khổ vải (`width_cm` = 49, 47, 50, 40, 38) và A là CHIỀU DÀI/CAO tấm vải (`height_cm` = 88, 104, 92) vì hai mặt túi nối liền theo chiều dọc gập đáy! Tuyệt đối không đặt `width_cm=88, height_cm=49`. CỮ DỌC PHẢI TÁCH: maket_top_cm là khoảng từ miệng thành phẩm tới đỉnh artwork; mouth_allowance_source=explicit nếu phiếu/tin xác nhận ghi số (kể cả0, hoặc ghi rõ `CỮ IN + 34CM` trên phiếu lệnh túi quai liền thân thì `mouth_allowance_cm=34` và `mouth_allowance_source="explicit"`, TUYỆT ĐỐI KHÔNG để blank=5cm); blank nếu phiếu để trống số miệng túi thì mặc định mouth_allowance_cm=5 cho cả 2 đầu trên/dưới theo quy chuẩn xưởng; not_applicable nếu nguồn xác nhận không áp dụng miệng gấp; unclear nếu chữ/số mờ hoặc mâu thuẫn, không coi là blank. Số ghi rõ ưu tiên hơn mặc định5. Không coi mặc định5cm là đường may0.5cm. vertical_evidence trích số và nguồn. y_cm=maket_top_cm+mouth_allowance_cm, chưa cộng phần may; chỉ cộng seam_allowance_cm có bằng chứng, fold=0. Với mặt sau xoay180, vertical_anchor=bottom vẫn dùng cùng cữ từ miệng tới đỉnh artwork, KHÔNG đặt y_cm=0 chỉ vì anchor=bottom. KIỂM TRA ĐỘC LẬP CỮ DỌC TỪNG MẶT (front vs back): tuyệt đối KHÔNG tự động copy maket_top_cm của mặt trước sang mặt sau hay dùng chung offset_cm trên phiếu lệnh nếu maket mặt sau ghi số khác! Phải soi trực tiếp từng ảnh MAKET_REGION_CROP và SOURCE_ARTBOARD của RIÊNG mặt trước và RIÊNG mặt sau. Nếu maket mặt sau có đường đo hoặc ghi số riêng (ví dụ mặt trước 5cm, mặt sau 12cm) thì mặt sau bắt buộc lấy maket_top_cm=12 và y_cm = 12 + mouth_allowance_cm (ví dụ 12 + 5 = 17). Chỉ khi hai mặt cùng artwork VÀ maket cả hai mặt ghi cùng một số cữ (hoặc mặt còn lại không ghi số riêng) thì cữ dọc mới bằng nhau; nếu maket hai mặt ghi hai số khác nhau thì giữ đúng số riêng từng mặt. Không lấy cữ đáy tới logo phụ làm cữ từ miệng.\n' + prompt + '\n' + LOGO_FILL_POLICY +
        '\nChỉ dùng ID NATIVE_CANDIDATE, chọn group cha hoàn chỉnh khớp maket; vùng lệch không được cắt group. Giữ chữ trắng, nền màu logo, mọi lớp và tỷ lệ. Không chọn cả cha và con. JPG có thể in cả mảng nền màu của mặt túi: không loại group đầy đủ chỉ vì chứa nền in. Loại hình mô phỏng quai/khóa/phối cảnh và đường đo. Đối chiếu riêng từng mặt trên maket: nếu hai group có bố cục khác nhau thì không tự dùng cùng một group cho cả hai mặt. Cữ tính theo object con được đường đo chỉ tới nếu có, chỉ dùng biên group khi đường đo thực sự tới biên group; group đã chứa nền toàn mặt không cộng lại khoảng trống nội bộ của nó. Kích thước/cữ JPG vẫn theo maket và phiếu, không áp quy tắc kích thước PET. background_object_id dùng PathItem màu gốc hoặc GroupItem nền sọc/hoa văn của thân túi trong NATIVE_CANDIDATE (nếu túi có nền sọc hoặc nền màu), không báo lỗi thiếu nền khi đã có candidate group nền sọc. Nếu túi CHỈ có nền sọc hoặc nền màu trơn và KHÔNG có logo rời (VERIFIED_SIDE_SELECTION không có logo rời), tạo panel với components=[] và trỏ background_object_id tới nền sọc/màu tương ứng (kèm background_mode="continuous_stripes" nếu là nền sọc, hoặc "matched_group" nếu là nền màu trơn); không báo lỗi thiếu logo. TRƯỜNG HỢP IN FULL MẶT / KHÔNG GHI CỮ TRÁI PHẢI: Khi maket thể hiện hình in phủ kín hoặc cân đối toàn bề ngang mặt túi (hoặc không ghi số cữ trái/phải riêng), đặt horizontal_symmetry=true, horizontal_alignment=center, x_cm=0, và ghi horizontal_alignment_evidence="Hình in phủ/cân đối toàn mặt túi theo maket, không có cữ lệch trái/phải" — TUYỆT ĐỐI KHÔNG báo issues thiếu cữ trái/phải. Thiếu thì báo nội bộ. Nếu PART_EXPORT_TABLE có part bổ sung `solid_meter` (túi con/dây quai màu trơn), BẮT BUỘC tạo thêm 1 panel trong `panels` với `kind="meter_fabric"`, `construction="meter_fabric"`, `canvas_basis="explicit_output"`, `width_cm=160`, `height_cm` theo phân tích kích thước túi con/dây quai (mặc định 20 nếu chỉ có quai), `components=[]` và `background_object_id` trỏ đúng `PathItem` màu nền; KHÔNG đưa túi con/dây quai vào `issues` hay `blocked_parts`. CHÚ Ý MÀU VẢI MÉT / DÂY QUAI (`solid_meter`): BẮT BUỘC soi kỹ màu sắc thực tế của quai/túi con trên maket và file thiết kế (ví dụ quai màu xanh lá, đỏ, đen...) và chọn đúng `PathItem` trong `NATIVE_CANDIDATE` có MÀU SẮC KHỚP ĐÚNG màu đó — TUYỆT ĐỐI KHÔNG chọn `PathItem` màu trắng/kem/xám nhạt của thân túi hoặc nền trang làm màu dây quai. GHI CHÚ THÔNG SỐ CMYK MÀU NỀN TRÊN ARTBOARD: Khi trên SOURCE_ARTBOARD có ghi chú rõ bộ 4 số thông số CMYK C-M-Y-K của màu nền (ví dụ "210 / 0-39-6-0", "226 / 0-99-0-0", "211 / 0-55-8-0"), BẮT BUỘC điền mảng 4 số [C, M, Y, K] đó vào trường background_cmyk của panel (ví dụ [0, 39, 6, 0], [0, 99, 0, 0], [0, 55, 8, 0]).',
        visual, schema, model='gemini-2.5-pro')
    try:
        if isinstance(plan.get('issues'),list):
            plan['issues']=[iss for iss in plan['issues'] if not any(k in iss.lower() for k in ('seam_allowance','edge_finish','gấp hay may','may viền','quy cách may miệng'))]
        if any(r.get('inferred_fabric_cm') for r in part_table):
            if isinstance(plan.get('issues'),list):
                plan['issues']=[iss for iss in plan['issues'] if not any(k in iss.lower() for k in ('kt vải','khổ vải','kích thước vải','cữ dọc','8.6'))]
            if not plan.get('panels') and selection.get('faces'):
                _r0=next((r for r in part_table if r.get('inferred_fabric_cm')),part_table[0])
                fw,fh=_r0['inferred_finished_cm']
                rw,rh=_r0['inferred_fabric_cm']
                src_list=[s for s in (_r0.get('sources') or []) if s in refs] or refs[:1]
                plan['panels']=[{
                    'name':re.sub(r'[^A-Za-z0-9_.-]+','_',str(_r0.get('id') or 'front')) or 'front',
                    'part_key':_r0['key'],
                    'kind':'bag_panel',
                    'construction':'separate_panel',
                    'canvas_basis':'raw_fabric',
                    'width_cm':rw,
                    'height_cm':rh,
                    'finished_width_cm':fw,
                    'finished_height_cm':fh,
                    'edge_finish':'fold',
                    'seam_allowance_cm':0,
                    'edge_finish_evidence':'Mặc định gấp miệng (fold, seam=0) theo quy chuẩn xưởng.',
                    'basis_explanation':f'Tự suy khổ vải test {rw:g}x{rh:g}cm từ kích thước túi thành phẩm {fw:g}x{fh:g}cm (+5cm mỗi chiều).',
                    'background_object_id':'',
                    'sources':src_list,
                    'components':[{
                        'side':f['side'],
                        'object_ids':list(f['object_ids']),
                        'x_cm':0.0,
                        'y_cm':7.5,
                        'maket_top_cm':2.5,
                        'mouth_allowance_cm':5.0,
                        'mouth_allowance_source':'blank',
                        'vertical_evidence':'Mặt in test: cữ dọc theo bố cục maket + 5cm miệng gấp mặc định.',
                        'horizontal_alignment':'center',
                        'horizontal_symmetry':True,
                        'horizontal_alignment_evidence':'Mặt in test căn giữa ngang theo maket.',
                        'vertical_anchor':'top',
                        'rotation':0,
                        'vertical_reference_object_id':'',
                        'vertical_reference_evidence':'',
                        'sources':src_list,
                    } for f in selection.get('faces',[])],
                }]
            for panel in plan.get('panels',[]):
                _row=next((r for r in part_table if r['key']==panel.get('part_key')),part_table[0] if part_table else None)
                if _row and _row.get('inferred_fabric_cm'):
                    fw,fh=_row['inferred_finished_cm']
                    panel['width_cm'],panel['height_cm']=_row['inferred_fabric_cm']
                    panel['finished_width_cm'],panel['finished_height_cm']=fw,fh
                    panel['canvas_basis']='raw_fabric'
                    panel['construction']='separate_panel'
                    if not panel.get('basis_explanation'):
                        panel['basis_explanation']=f'Tự suy khổ vải test {panel["width_cm"]:g}x{panel["height_cm"]:g}cm từ kích thước túi thành phẩm {fw:g}x{fh:g}cm (+5cm mỗi chiều).'
                    for comp in panel.get('components',[]):
                        if comp.get('maket_top_cm') in (None,'') or (isinstance(comp.get('maket_top_cm'),(int,float)) and comp['maket_top_cm']<=0):
                            comp['maket_top_cm']=2.5
                        if not comp.get('vertical_evidence'):
                            comp['vertical_evidence']='Mặc định cữ dọc test 2.5cm từ miệng túi + 5cm miệng gấp.'
        for panel in plan.get('panels',[]):
            if not [s for s in (panel.get('sources') or []) if s in refs] and refs:
                _row=next((r for r in part_table if r['key']==panel.get('part_key')),None)
                panel['sources']=[s for s in ((_row or {}).get('sources') or []) if s in refs] or refs[:1]
            if panel.get('kind')=='bag_panel' and panel.get('edge_finish') in ('unknown','',None):
                panel['edge_finish']='fold'
                panel['seam_allowance_cm']=0
                if not panel.get('edge_finish_evidence'):
                    panel['edge_finish_evidence']='Mặc định gấp miệng (fold, seam=0) và cữ miệng 5cm hai đầu trên/dưới theo quy chuẩn xưởng'
            deduped=[]
            seen_side_objs=set()
            for comp in panel.get('components',[]):
                k=(comp.get('side'),tuple(comp.get('object_ids') or []))
                if k in seen_side_objs:continue
                seen_side_objs.add(k)
                deduped.append(comp)
            panel['components']=deduped
            sides=[c.get('side') for c in panel.get('components',[])]
            if len(sides)!=len(set(sides)):raise ValueError('Lặp mặt trong cùng panel; không xuất hai logo chồng nhau')
            if panel.get('kind')=='bag_panel' and panel.get('construction')=='joined_two_faces' and len(sides)==1 and selection.get('same_artwork_both_sides') and {'front','back'}<={f['side'] for f in selection.get('faces',[])}:
                missing_side='back' if sides[0]=='front' else 'front'
                mirror=copy.deepcopy(panel['components'][0])
                mirror['side']=missing_side
                if mirror.get('horizontal_alignment')=='left':
                    mirror['horizontal_alignment']='right'
                elif mirror.get('horizontal_alignment')=='right':
                    mirror['horizontal_alignment']='left'
                panel['components'].append(mirror)
            for component in panel.get('components',[]):
                if component.get('mouth_allowance_source') in ('',None) and component.get('mouth_allowance_cm') in (None,''):
                    component['mouth_allowance_source']='blank'
                matching = [f for f in selection['faces'] if f['side'] == component.get('side')]
                if len(matching) != 1:
                    raise ValueError('Bố trí tham chiếu mặt chưa được chọn')
                component['object_ids'] = list(matching[0]['object_ids'])
                source_objects = [o for o in objects if o['id'] in component['object_ids']]
                b = [o['bounds'] for o in source_objects]
                component['width_cm'] = (max(x[2] for x in b)-min(x[0] for x in b))*2.54/72
                component['preserve_native_size'] = True
                from hub.jpg_reference import mouth_allowance
                _cu_text = ' '.join(p['text'] for p in context if isinstance(p, dict) and 'text' in p and not str(p['text']).startswith(('PART_EXPORT_TABLE:', 'QUY TẮC ')))
                _m_cu = re.search(r'C[ƯỮỬ]\s*IN\s*\+\s*(\d+(?:[.,]\d+)?)\s*CM', _cu_text, re.I)
                if _m_cu:
                    _cu_val = float(_m_cu.group(1).replace(',', '.'))
                    if _cu_val > 0 and (component.get('mouth_allowance_source') == 'blank' or (_cu_val > 5 and component.get('mouth_allowance_cm') in (None, '', 5))):
                        component['mouth_allowance_source'] = 'explicit'
                        component['mouth_allowance_cm'] = _cu_val
                        _vev = str(component.get('vertical_evidence') or '').strip()
                        _cnote = f'Phiếu ghi rõ CỮ IN + {_cu_val:g}cm'
                        if _cnote.casefold() not in _vev.casefold():
                            component['vertical_evidence'] = (_vev + '; ' + _cnote).strip('; ')
                mouth_allowance(component)
                if not component.get('horizontal_symmetry') and component.get('horizontal_alignment') in ('left', 'right'):
                    panel_w = panel.get('width_cm') or 0
                    ref_w = panel.get('finished_width_cm') or (max(0.0, panel_w - 4.0) if panel_w > 4 else panel_w) or 0
                    comp_w = component.get('width_cm', 0)
                    xc = component.get('x_cm') or 0
                    if ref_w > 0 and comp_w > 0:
                        opp = ref_w - comp_w - xc
                        if xc > 0 and opp >= 0 and abs(opp - xc) <= 0.5:
                            component['horizontal_symmetry'] = True
                            if not component.get('horizontal_alignment_evidence'):
                                component['horizontal_alignment_evidence'] = f"Tự căn giữa: hai lề ngang bằng nhau trên khổ {ref_w}cm ({xc:.2f}cm vs {opp:.2f}cm)"
                        elif comp_w >= ref_w - 1.5 and xc == 0:
                            component['horizontal_symmetry'] = True
                            component['x_cm'] = 0
                            component['horizontal_alignment_evidence'] = f"Hình in phủ/cân đối toàn bề ngang mặt túi ({comp_w:.2f}cm trên khổ {ref_w}cm)"
                if not component.get('alignment_reference_box'):
                    ev_h = str(component.get('horizontal_alignment_evidence') or '').casefold()
                    has_explicit_side = (component.get('x_cm') or 0) > 0 or any(k in ev_h for k in ('chạm mép', 'sát mép', 'cữ trái', 'cữ phải', 'lệch trái', 'lệch phải'))
                    if component.get('horizontal_alignment') not in ('left', 'center', 'right') or (component.get('horizontal_alignment') in ('left', 'right') and not has_explicit_side):
                        component['horizontal_symmetry'] = True
                        component['horizontal_alignment'] = 'center'
                        if not component.get('horizontal_alignment_evidence'):
                            component['horizontal_alignment_evidence'] = 'Mặc định căn giữa do không có ghi chú cữ trái/phải'
                if component.get('horizontal_symmetry'):
                    component['x_cm'] = 0
                    if not component.get('horizontal_alignment_evidence'):
                        component['horizontal_alignment_evidence'] = 'Mặc định căn giữa do không có ghi chú cữ trái/phải'
                    component['horizontal_alignment']='center'
                if component.get('alignment_reference_box')==[0,0,1,1]:
                    component.pop('alignment_reference_box')
                    component.pop('alignment_reference_evidence',None)
                if panel.get('construction')=='joined_two_faces':
                    # Joined-panel side orientation is a workshop rule, not an AI choice.
                    component['rotation'] = 0 if component['side'] == 'front' else 180
                    component['vertical_anchor'] = 'top' if component['side'] == 'front' else 'bottom'
                    values=[component.get('maket_top_cm'),component.get('mouth_allowance_cm')]
                    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values) or not component.get('vertical_evidence'):
                        raise ValueError('Cữ dọc thiếu bằng chứng miệng túi/maket')
                    component['y_cm']=sum(values)
                if panel.get('kind')=='bag_panel' and panel.get('construction')!='joined_two_faces':
                    component['y_cm']=component['maket_top_cm']+component['mouth_allowance_cm']
                from hub.jpg_reference import native_anchor
                ref_id = component.get('vertical_reference_object_id')
                if ref_id:
                    c_ids = component.get('object_ids') or []
                    if ref_id in c_ids:
                        component['vertical_reference_object_id'] = ''
                        component['vertical_reference_evidence'] = ''
                    elif not any(ref_id.startswith(i + '.') for i in c_ids):
                        known_cand = {c['id'] for c in scan['candidates']}
                        mapped = ''
                        for oi in selected_ids:
                            if ref_id.startswith(oi + '.') and c_ids:
                                cand_id = c_ids[0] + ref_id[len(oi):]
                                if cand_id in known_cand:
                                    mapped = cand_id
                                    break
                        component['vertical_reference_object_id'] = mapped
                        if not mapped:
                            component['vertical_reference_evidence'] = ''
                ref_id = component.get('vertical_reference_object_id')
                known_objs = {c['id']: c for c in scan['candidates'] if c.get('bounds')}
                c_ids = [i for i in (component.get('object_ids') or []) if i in known_objs]
                mt = component.get('maket_top_cm')
                if ref_id and ref_id in known_objs and c_ids and isinstance(mt, (int, float)) and mt > 0:
                    outer_l = min(known_objs[i]['bounds'][0] for i in c_ids)
                    outer_t = max(known_objs[i]['bounds'][1] for i in c_ids)
                    outer_r = max(known_objs[i]['bounds'][2] for i in c_ids)
                    ref_t = known_objs[ref_id]['bounds'][1]
                    dim_lines = [
                        c['bounds'] for c in scan['candidates']
                        if c.get('kind') == 'PathItem' and len(c.get('bounds') or []) == 4
                        and (c['bounds'][2] - c['bounds'][0]) * 2.54 / 72.0 <= 0.25
                        and abs(abs(c['bounds'][1] - c['bounds'][3]) * 2.54 / 72.0 - mt) <= 0.2
                        and outer_l - 60 <= c['bounds'][0] and c['bounds'][2] <= outer_r + 60
                    ]
                    has_sib = any(
                        w.get('side') == component.get('side') and w.get('sibling_backing')
                        for w in (selection or {}).get('white_backing_completion', [])
                    )
                    if (
                        any(abs(lb[3] - outer_t) <= 3.0 and abs(lb[3] - ref_t) > 5.0 for lb in dim_lines)
                        or (has_sib and not any(abs(lb[3] - ref_t) <= 3.0 for lb in dim_lines))
                    ):
                        component['vertical_reference_object_id'] = ''
                        component['vertical_reference_evidence'] = ''
                try:
                    native_anchor(component,scan['candidates'])
                except ValueError:
                    component['vertical_reference_object_id']=''
                    component['vertical_reference_evidence']=''
                # Frame overlap/registration is not an export prerequisite.
                for key in ('reference_frame_object_id','reference_frame_evidence','native_frame_registration','frame_resolution'):
                    component.pop(key,None)
            if panel.get('kind')=='bag_panel' and panel.get('construction')=='joined_two_faces':
                _front=next((c for c in panel.get('components',[]) if c.get('side')=='front'),None)
                _back=next((c for c in panel.get('components',[]) if c.get('side')=='back'),None)
                if _front and _back and not _front.get('horizontal_symmetry') and _front.get('horizontal_alignment') in ('left','right') and (_front.get('x_cm') or 0)>0:
                    _b_ev=str(_back.get('horizontal_alignment_evidence') or '').casefold()
                    _b_no_own=any(k in _b_ev for k in ('mặc định','không ghi','không có ghi chú','tương tự','theo mặt trước','giống mặt trước','không có cữ'))
                    if _back.get('horizontal_alignment')=='center' or (_back.get('horizontal_alignment')==_front.get('horizontal_alignment') and _b_no_own) or (_b_no_own and (_back.get('x_cm') or 0)==0):
                        _flipped='right' if _front['horizontal_alignment']=='left' else 'left'
                        _back['horizontal_symmetry']=False
                        _back['horizontal_alignment']=_flipped
                        _back['x_cm']=_front['x_cm']
                        _back['horizontal_alignment_evidence']=f"Mặt sau xoay 180° không có cữ ngang riêng trên maket, lấy cữ từ mặt trước ({_front['horizontal_alignment']} {_front['x_cm']}cm) đảo sang {_flipped}"
        note_cmyk = _valid_cmyk(regions.get('artboard_cmyk_note'))
        for panel in plan.get('panels',[]):
            if panel.get('kind')=='bag_panel':
                cmyk = _valid_cmyk(panel.get('background_cmyk')) or note_cmyk
                if cmyk:
                    panel['background_cmyk'] = cmyk
                    panel['background_mode'] = 'solid_cmyk'
                    panel['background_object_id'] = ''
                else:
                    panel.pop('background_cmyk', None)
        bind_panel_background(plan, selection, kept, fills, bg_groups, scan)
        from hub.jpg_part_strategy import constrain,resolve_groups
        part_table=resolve_groups(part_table,plan,selection,objects)
        plan=constrain(plan,part_table)
        by_id = {c['id']: c for c in objects}
        for panel in plan.get('panels', []):
            all_comp_ids = {i for comp in panel.get('components', []) for i in comp.get('object_ids', [])}
            if panel.get('background_object_id') and panel['background_object_id'] in all_comp_ids:
                alt_bgs = []
                for bg_cand in bg_groups:
                    if bg_cand['id'] in all_comp_ids or any(s.startswith(bg_cand['id'] + '.') or bg_cand['id'].startswith(s + '.') for s in all_comp_ids):
                        continue
                    bl, bt, br, bb = bg_cand['bounds']
                    for cid in all_comp_ids:
                        art_obj = by_id.get(cid)
                        if not art_obj:
                            continue
                        al, at, ar, ab = art_obj['bounds']
                        if al >= bl - 2 and ar <= br + 2 and at <= bt + 2 and ab >= bb - 2:
                            alt_bgs.append(bg_cand['id'])
                            break
                if alt_bgs:
                    panel['background_object_id'] = alt_bgs[0]
            bg = by_id.get(panel.get('background_object_id'))
            if panel.get('background_mode')=='continuous_stripes': continue
            if not bg or bg['kind'] == 'PathItem' or panel.get('kind') != 'bag_panel':
                continue
            panel['background_mode'] = 'registered_per_face'
            for component in panel.get('components', []):
                art = [by_id[i] for i in component['object_ids']]
                l = min(a['bounds'][0] for a in art); r = max(a['bounds'][2] for a in art)
                t = max(a['bounds'][1] for a in art); b = min(a['bounds'][3] for a in art)
                enclosing = [g for g in bg_groups if g['id'] not in all_comp_ids
                             and not any(s.startswith(g['id'] + '.') or g['id'].startswith(s + '.') for s in all_comp_ids)
                             and g['bounds'][0] <= l and g['bounds'][2] >= r
                             and g['bounds'][1] >= t and g['bounds'][3] <= b
                             and ((g['bounds'][2] - g['bounds'][0]) > (r - l) * 1.05 or (g['bounds'][1] - g['bounds'][3]) > (t - b) * 1.05)]
                if not enclosing:
                    raise ValueError('Nền hoa văn chưa có đăng ký vị trí với artwork mặt ' + component['side'])
                same_depth = [g for g in enclosing if g['id'].count('.') == bg['id'].count('.')]
                chosen = min(same_depth or enclosing, key=lambda g: (g['bounds'][2]-g['bounds'][0])*(g['bounds'][1]-g['bounds'][3]))
                component['background_object_id'] = chosen['id']
            if panel.get('kind') == 'bag_panel' and bg['kind'] == 'GroupItem' and panel.get('components'):
                bg_comps = [c.get('background_object_id') for c in panel.get('components', []) if c.get('background_object_id')]
                row_pat = (panel.get('part_strategy') or {}).get('background') == 'pattern'
                eq_sets = [set(r.get('ids', [])) for r in selection.get('equivalent_artworks', []) if r.get('same_print_content') is True]
                same_bg = len(bg_comps) >= 2 and (len(set(bg_comps)) == 1 or any(set(bg_comps) <= s for s in eq_sets))
                if not same_bg and len(bg_comps) >= 2:
                    b0 = by_id.get(bg_comps[0])
                    if b0:
                        same_bg = all(
                            by_id.get(bid)
                            and abs(by_id[bid].get('width_cm', 0) - b0.get('width_cm', 0)) <= 0.2
                            and abs(by_id[bid].get('height_cm', 0) - b0.get('height_cm', 0)) <= 0.2
                            and len(by_id[bid].get('direct_child_ids', [])) == len(b0.get('direct_child_ids', []))
                            for bid in bg_comps[1:]
                        )
                if row_pat or (panel.get('construction') == 'joined_two_faces' and same_bg):
                    panel['background_mode'] = 'full_artboard_pattern'
                    front_comp = next((c for c in panel.get('components', []) if c.get('side') == 'front' and c.get('background_object_id')), None)
                    chosen_comp = front_comp or next((c for c in panel.get('components', []) if c.get('background_object_id')), None)
                    if chosen_comp:
                        panel['background_object_id'] = chosen_comp['background_object_id']
        validate_face_layout(selection, plan)
        backgrounds={c['id'] for c in bg_candidates}
        for panel in plan.get('panels',[]):
            if panel.get('background_object_id') and panel['background_object_id'] not in backgrounds:raise ValueError('Nền không phải đối tượng nền nguồn đã xác minh')
        # An unavailable meter strip must not block the verified bag artwork.
        ready = []
        for panel in plan['panels']:
            if panel.get('kind') == 'meter_fabric' and not panel.get('background_object_id') and not panel.get('components'):
                plan.setdefault('blocked_parts', []).append({'part': panel['name'], 'reason': 'Thiếu artwork nền vải mét; chưa xác minh khổ/chu kỳ, không xuất theo số mét đặt hàng.'})
            else:
                ready.append(panel)
        plan['panels'] = ready
        plan = validate(plan, objects, refs)
        for panel in plan['panels']:
            for component in panel['components']:
                selected = component['object_ids']
                if any(a != b and b.startswith(a + '.') for a in selected for b in selected):
                    raise ValueError('Không chọn đồng thời group cha/con')
            for obj in panel['objects']:
                if obj.get('live_text_count') and scan.get('missing_fonts'):
                    raise ValueError('Thiếu font: ' + ', '.join(scan['missing_fonts']))
                obj.pop('preview', None)
        plan.update(renderer='native_group_v1', source_sha256=digest,
            artwork_selection={'method': 'maket_complete_group', 'faces': selection, 'regions': regions['regions'],
                'candidate_ids': [c['id'] for c in kept], 'model': 'gemini-2.5-pro'})
        return plan, visual
    except ValueError as exc:
        if not getattr(exc, 'draft_plan', None):
            try:
                exc.draft_plan = _build_draft_plan_on_error(plan, objects, selection, regions, kept, digest)
            except Exception:
                pass
        raise



def validate_faces(selection, known):
    # Compatibility with the precise obsolete issue returned by earlier prompts.
    obsolete={'Không có bằng chứng về phần tràn cho artwork.',
              'Không có bằng chứng về phần tràn cho artwork',
              'Không có bằng chứng về phần tràn.',
              'Không có bằng chứng về phần tràn'}
    notes=[v for v in selection.get('issues',[]) if v in obsolete]
    if notes:selection.setdefault('bleed_observations',[]).extend(notes)
    selection['issues']=[v for v in selection.get('issues',[]) if v not in obsolete]
    faces=selection.get('faces',[])
    if faces and selection.get('issues'):
        scope_kws=('in lưới', 'screen print', 'xác nhận logo này thuộc kỹ thuật chuyển nhiệt', 'không thuộc phạm vi jpg')
        kept_issues=[]
        for v in selection['issues']:
            if any(k in str(v).casefold() for k in scope_kws):
                selection.setdefault('scope_observations',[]).append(v)
            else:
                kept_issues.append(v)
        selection['issues']=kept_issues
    if selection.get('issues') or not selection.get('reason') or not faces:
        raise ValueError('Chưa xác định từng mặt: '+ '; '.join(selection.get('issues',[])))
    sides=[f.get('side') for f in faces]
    if len(sides)!=len(set(sides)):raise ValueError('Trùng quyết định chọn mặt')
    for f in faces:
        ids=f.get('object_ids',[])
        if not ids or len(ids)!=len(set(ids)) or not set(ids)<=known or not f.get('maket_evidence'):
            raise ValueError('Chọn mặt thiếu ID hoặc bằng chứng maket')
    pair=[f for f in faces if f['side'] in ('front','back')]
    if len(pair)==2 and set(pair[0]['object_ids'])==set(pair[1]['object_ids']) and not selection.get('same_artwork_both_sides'):
        raise ValueError('Hai mặt dùng cùng group nhưng chưa xác nhận cùng artwork')


def validate_face_layout(selection, plan):
    faces={f['side']:set(f['object_ids']) for f in selection['faces']}
    seen=set()
    for panel in plan.get('panels',[]):
        if panel.get('kind')=='meter_fabric':continue
        for c in panel.get('components',[]):
            side=c.get('side')
            if side not in faces or set(c.get('object_ids',[]))!=faces[side]:
                raise ValueError('Bố trí đổi group đã chọn cho mặt '+str(side))
            seen.add(side)
    if seen!=set(faces):
        issues=[str(x).strip() for x in (plan.get('issues') or []) if str(x).strip()]
        msg='Bố trí thiếu mặt đã chọn'+(': '+'; '.join(issues) if issues else '')
        raise ValueError(msg)


def prefer_unframed_equivalent(selection, evidence):
    """Apply owner bleed policy only to visually confirmed equivalent alternatives."""
    info={x['id']:x for x in evidence}
    changes=[]
    for relation in selection.get('equivalent_artworks',[]):
        ids=relation.get('ids',[])
        if relation.get('same_print_content') is not True or not relation.get('reason') or len(ids)<2 or not set(ids)<=info.keys():continue
        artwork=[x for x in ids if not info[x]['panel_frame_warning'] and info[x]['opaque_fraction']<.95]
        framed=[x for x in ids if info[x]['panel_frame_warning']]
        if len(artwork)!=1 or not framed:continue
        for face in selection['faces']:
            if len(face['object_ids'])==1 and face['object_ids'][0] in framed:
                original=face['object_ids'][0];face['object_ids']=[artwork[0]]
                face['bleed_evidence']='Ưu tiên artwork cùng nội dung không kèm khung mô phỏng; giữ phần tràn. '+relation['reason']
                changes.append({'side':face['side'],'from':original,'to':artwork[0],'reason':face['bleed_evidence']})
    selection['policy_adjustments']=changes
    selection['candidate_image_evidence']=evidence
    return selection


def _dominant_rgb(c):
    if not c or not c.get('preview'):
        return None
    import base64, io
    from collections import Counter
    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(c['preview']))).convert('RGBA')
    colors = Counter((r, g, b) for r, g, b, a in im.getdata() if a > 240)
    return colors.most_common(1)[0][0] if colors else None


def _is_near_white_or_gray(rgb):
    if not rgb:
        return True
    return min(rgb) >= 195 and max(rgb) - min(rgb) <= 12


def _is_solid_fill_candidate(c):
    if c.get('kind') != 'PathItem' or c.get('name') == 'Manual Dimension':
        return False
    if c.get('solid_cmyk_fill') is True:
        return True
    if c.get('verified_white_fill') or c.get('width_cm', 0) < 10 or c.get('height_cm', 0) < 10:
        return False
    return not _is_near_white_or_gray(_dominant_rgb(c))


def _valid_cmyk(val):
    if not isinstance(val, (list, tuple)) or len(val) != 4:
        return None
    try:
        nums = [round(float(v), 2) for v in val]
    except (TypeError, ValueError):
        return None
    if all(0.0 <= v <= 100.0 for v in nums) and any(v > 0.0 for v in nums):
        return nums
    return None


def bind_panel_background(plan, selection, kept, fills, bg_groups=None, scan=None):
    # Artwork is separate from fabric background; preserve actual source CMYK object or stripe group.
    dominant = _dominant_rgb
    candidates={c['id']:c for c in kept}
    all_by_id={c['id']:c for c in (scan.get('candidates',[]) if scan else kept)}
    evidence={c['id']:c for c in selection.get('candidate_image_evidence',[])}
    for panel in plan.get('panels',[]):
        if panel.get('kind')!='bag_panel':continue
        if panel.get('background_mode')=='solid_cmyk' and _valid_cmyk(panel.get('background_cmyk')):continue
        selected={x for comp in panel.get('components',[]) for x in comp['object_ids']}
        if panel.get('background_object_id'):
            matches=[]
            for relation in selection.get('equivalent_artworks',[]):
                ids=set(relation.get('ids',[]))
                if relation.get('same_print_content') is not True or not selected.intersection(ids):continue
                for id in ids:
                    if id not in candidates or not evidence.get(id,{}).get('panel_frame_warning'):continue
                    color=dominant(candidates[id])
                    for fill in fills:
                        fc=dominant(fill)
                        if color and fc and max(abs(a-b) for a,b in zip(color,fc))<=3:matches.append(fill['id'])
            if matches:
                panel['background_selection']={'method':'source_fill_matches_equivalent_panel_background','previous_id':panel['background_object_id'],'selected_id':sorted(set(matches))[0]}
                panel['background_object_id']=sorted(set(matches))[0]
        if bg_groups and (not panel.get('background_object_id') or (all_by_id.get(panel['background_object_id'], {}).get('kind') == 'PathItem' and _is_near_white_or_gray(dominant(all_by_id.get(panel['background_object_id']))))):
            # Auto-bind underlying stripe/pattern background group if selected foreground logos sit inside it.
            top_bg_groups = [bg for bg in bg_groups if bg['id'].count('.') == 1] if panel.get('background_object_id') else bg_groups
            enclosing=[]
            for bg in top_bg_groups:
                if bg['id'] in selected or any(s.startswith(bg['id']+'.') or bg['id'].startswith(s+'.') for s in selected):
                    continue
                bl,bt,br,bb=bg['bounds']
                for s in selected:
                    sc=all_by_id.get(s) or candidates.get(s)
                    if not sc:continue
                    sl,st,sr,sb=sc['bounds']
                    if sl>=bl-2 and sr<=br+2 and st<=bt+2 and sb>=bb-2 and (sc['width_cm']<bg['width_cm']*0.95 or sc['height_cm']<bg['height_cm']*0.95):
                        enclosing.append(bg['id'])
                        break
            if enclosing:
                best_bg=min(enclosing,key=lambda bid:(all_by_id[bid]['bounds'][2]-all_by_id[bid]['bounds'][0])*(all_by_id[bid]['bounds'][1]-all_by_id[bid]['bounds'][3]))
                panel['background_object_id']=best_bg
                panel['background_selection']={'method':'enclosing_background_group','selected_id':best_bg}
        if panel.get('background_mode')!='continuous_stripes' and (not panel.get('background_object_id') or panel.get('background_mode')=='registered_per_face' or (all_by_id.get(panel['background_object_id'],{}).get('kind')=='PathItem' and _is_near_white_or_gray(dominant(all_by_id.get(panel['background_object_id'],{}))))):
            # Auto-bind enclosing non-white bag-sized solid CMYK PathItem (e.g. light cream RGB 250,248,226) missed by AI.
            enclosing_fills=[]
            for fill in fills:
                if fill.get('verified_white_fill') or fill['id'] in selected:
                    continue
                if not (20<=fill.get('width_cm',0)<=70 and 20<=fill.get('height_cm',0)<=95):
                    continue
                fc=dominant(fill)
                if not fc or (min(fc)>=190 and max(fc)-min(fc)<=6):
                    continue
                fl,ft,fr,fb=fill['bounds']
                for s in selected:
                    sc=all_by_id.get(s) or candidates.get(s)
                    if not sc:continue
                    sl,st,sr,sb=sc['bounds']
                    if sl>=fl-2 and sr<=fr+2 and st<=ft+2 and sb>=fb-2:
                        enclosing_fills.append(fill['id'])
                        break
            if enclosing_fills:
                panel['background_object_id']=enclosing_fills[0]
                if not panel.get('background_mode') or panel.get('background_mode')=='none':
                    panel['background_mode']='matched_group'
                panel['background_selection']={'method':'enclosing_solid_fill','selected_id':enclosing_fills[0]}
    # Ensure any supplement meter_fabric panel (e.g. 160cm strap/pocket solid color) inherits a verified colored solid fill.
    bag_bg_id=next((p.get('background_object_id') for p in plan.get('panels',[]) if p.get('kind')=='bag_panel' and p.get('background_object_id')),'')
    colored_fills=[f for f in fills if not f.get('verified_white_fill') and f.get('width_cm',0)>=10 and f.get('height_cm',0)>=10 and dominant(f) and not _is_near_white_or_gray(dominant(f))]
    for panel in plan.get('panels',[]):
        if panel.get('kind')!='meter_fabric':
            continue
        cur_bg_id=panel.get('background_object_id','')
        cur_bg_obj=all_by_id.get(cur_bg_id) if cur_bg_id else None
        cur_rgb=dominant(cur_bg_obj) if cur_bg_obj else None
        if cur_bg_id and cur_rgb is not None and _is_near_white_or_gray(cur_rgb) and colored_fills:
            cur_bg_id=''
        if not cur_bg_id:
            chosen_bg=''
            if bag_bg_id and bag_bg_id in all_by_id:
                bag_rgb=dominant(all_by_id[bag_bg_id])
                if bag_rgb is None or not _is_near_white_or_gray(bag_rgb):
                    chosen_bg=bag_bg_id
            if not chosen_bg and colored_fills:
                chosen_bg=colored_fills[0]['id']
            if not chosen_bg:
                for fill in fills:
                    if fill.get('verified_white_fill'):continue
                    if not (20<=fill.get('width_cm',0)<=70 and 20<=fill.get('height_cm',0)<=95):continue
                    fc=dominant(fill)
                    if fc and not (min(fc)>=245 and max(fc)-min(fc)<8):
                        chosen_bg=fill['id'];break
            if chosen_bg:
                panel['background_object_id']=chosen_bg
                if not panel.get('background_mode') or panel.get('background_mode')=='none':
                    panel['background_mode']='matched_group'
                panel['background_selection']={'method':'meter_colored_solid_fill','selected_id':chosen_bg}
