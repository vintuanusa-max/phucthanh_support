"""Versioned proposals only. No design/export/customer-send capabilities."""
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

SELECTION_PROMPT = '''
Bổ sung selections: danh sách đề xuất cụm artwork cần làm mẫu, mỗi cụm có label, object_ids (ID thô từ object_inventory), reason, method (reuse_vector|reuse_image|redraw_review|unresolved).
Chỉ chọn cụm liên quan yêu cầu khách và ảnh maket. Không chọn hình sản phẩm/nền/chữ chú thích làm artwork. Nếu ảnh phẳng chứa mockup thì dùng redraw_review, không tuyên bố tách được logo. Không đủ căn cứ để chọn thì để selections rỗng và ghi missing_fields. Vector gồm nhiều nét phải chọn đủ ID thành phần; chưa đủ thì unresolved. Đây chỉ là đề xuất cho người duyệt, không phải artwork đã tái tạo.
'''

CANAVI_RULES = {
    'version': '2026-10-19-source-cmyk-editable-v4', 'format': 'JPEG', 'color_mode': 'CMYK', 'dpi': 300,
    'shrink_rule': {'basis': 'raw_fabric_height_cm', 'threshold_cm': 70,
                    'width_loss_cm': 2, 'height_loss_below_cm': 2.5,
                    'height_loss_at_or_above_cm': 5},
    'canvas_basis': 'post_shrink', 'scale_artwork_for_shrink': False, 'mirror': False,
    'corner_marks': {'shape': 'L', 'count': 4, 'arm_cm': 1, 'line_mm': 0.25, 'exclude_panel_types': ['meter_fabric']},
    'delivery': 'chatwoot_private_review_only', 'customer_send_allowed': False,
    'icc_default': None, 'icc_policy': 'preserve_source; missing or mixed profiles require review', 'preserve_source_cmyk': True, 'rgb_roundtrip_allowed': False, 'editable_ai_required': True, 'rip_allowed': False,
    'per_job_required': ['Khổ vải sau co hoặc khổ trước co và tổng co từng chiều',
        'Số mặt, cấu tạo tấm vải, hông/đáy/quai cần in',
        'Cữ từng artwork và mốc đo, chừa may/phần dư mỗi bên',
        'Kích thước artwork hoặc tỷ lệ maket đã xác nhận',
        'Đúng phiên bản nguồn và cụm đối tượng đã kiểm tra bằng render riêng'],
    'copy_previous_job_dimensions': False,
}


def post_shrink_canvas(raw_width_cm, raw_height_cm):
    """Explicit fabric axes in cm; never use bag height or longest edge."""
    try:
        width, height = (Decimal(str(x)) for x in (raw_width_cm, raw_height_cm))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Cần chiều ngang/cao vải trước co, đơn vị cm') from exc
    if not all(x.is_finite() and x > 0 for x in (width, height)):
        raise ValueError('Kích thước vải không hợp lệ')
    loss_h = Decimal('5') if height >= Decimal('70') else Decimal('2.5')
    after_w, after_h = width - 2, height - loss_h
    if after_w <= 0 or after_h <= 0:
        raise ValueError('Khổ sau co phải lớn hơn 0')
    return {'rule_version': CANAVI_RULES['version'],
            'raw_width_cm': float(width), 'raw_height_cm': float(height),
            'width_loss_cm': 2, 'height_loss_cm': float(loss_h),
            'width_cm': float(after_w), 'height_cm': float(after_h),
            'scale_artwork_for_shrink': False}


def canavi_policy(source):
    folder = source.get('asset', {}).get('relative_path', '').replace('\\', '/').split('/')[0].upper().strip()
    if folder not in ('CANAVI', 'CANAVI HCM2'):
        return None
    if re.search(r'\bPET\b', source.get('asset', {}).get('name', ''), re.I):
        return {'version':'2026-10-19-pet','format':'PNG+TIFF','dpi':300,
                'canvas_basis':'confirmed_artwork_dimensions','mirror':False,
                'naming':'{order_code}_font.tiff / {order_code}_back.tiff',
                'transparent_background':True,'white_channel':'spot_1',
                'white_channel_type':'SPOTCOLOR','photoshop_action':'IN_PHUC_THANH_ACTIONS/WHITE_1',
                'save_options':{'transparency':True,'alphaChannels':True,'spotColors':True},
                'delivery':'chatwoot_private_review_only','customer_send_allowed':False,'auto_rip':False,
                'per_job_required':['Xác nhận loại in PET theo phiếu, không chỉ theo tên file',
                    'Mã đơn và mặt in; không dùng mã mẫu cũ',
                    'Kích thước riêng từng mặt, giải quyết mâu thuẫn A4/maket',
                    'Vùng nền túi phải trong suốt; phân biệt với chi tiết trắng cần in',
                    'Mở lại TIFF kiểm tra alpha, spot_1 có dữ liệu, DPI và kích thước trước gửi'],
                'copy_previous_job_dimensions':False}
    return dict(CANAVI_RULES)


def validate_selections(value, refs):
    selections = value.get('selections', [])
    if not isinstance(selections, list) or len(selections) > 20:
        raise ValueError('Invalid designer selections')
    allowed = {r[7:] for r in refs if r.startswith('object:')}
    for item in selections:
        if not isinstance(item, dict) or item.get('method') not in ('reuse_vector', 'reuse_image', 'redraw_review', 'unresolved'):
            raise ValueError('Invalid designer method')
        ids = item.get('object_ids')
        if not isinstance(ids, list) or not ids or len(ids) > 600 or not all(isinstance(x, str) and x in allowed for x in ids):
            raise ValueError('Designer selection references unknown object')
        if any(not isinstance(item.get(k), str) or not item[k] or len(item[k]) > 1500 for k in ('label', 'reason')):
            raise ValueError('Invalid designer explanation')
    return selections


def build_proposal(identity, source, result):
    comparison = result.get('comparison', {})
    tech = result.get('technical', {})
    objects = {o['id']: o for o in tech.get('object_inventory', {}).get('objects', [])}
    selections = validate_selections(comparison, ['object:' + x for x in objects])
    blocked = comparison.get('same_design') != 'proposed'
    selected = []
    for item in selections:
        selection = {**item, 'objects': [objects[x] for x in item['object_ids']]}
        if blocked:
            selection['method'] = 'unresolved'
        if selection['method'] == 'reuse_vector' and any(objects[x]['kind'] not in ('text', 'vector_path') for x in item['object_ids']):
            selection['method'] = 'unresolved'
        selected.append(selection)
    missing = list(comparison.get('missing_fields', [])) + list(result.get('errors', []))
    missing += list(tech.get('limitations', []))
    if not selected:
        missing.append('Chưa xác định chắc chắn cụm ảnh/vector cần làm mẫu.')
    if blocked:
        missing.append('Chưa xác nhận file đúng mẫu/phiên bản khách yêu cầu.')
    missing.append('Cần duyệt cụm artwork, kích thước in, vị trí/cữ và số mặt trước bước thiết kế.')
    return {'schema_version': 1, 'id': identity, 'status': 'needs_staff_review',
            'export_policy': canavi_policy(source),
            'source': source, 'selections': selected, 'missing_fields': list(dict.fromkeys(missing)),
            'findings': comparison.get('findings', []), 'preview_paths': tech.get('previews', []),
            'execution_allowed': False, 'production_export_allowed': False, 'customer_send_allowed': False}


def save_proposal(folder, proposal):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (proposal['id'] + '.json')
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(target)


def proposal_note(proposal):
    lines = ['ĐỀ XUẤT MẪU DESIGNER — CHỜ DUYỆT NỘI BỘ', 'File: ' + proposal['source']['asset']['name'],
             'Tin nguồn: ' + proposal['source']['source_message_id'], 'Hồ sơ: ' + proposal['id']]
    if proposal.get('export_policy',{} ) and proposal['export_policy']['format']=='PNG+TIFF':
        lines += ['QUY TẮC PET: PNG trong suốt → WHITE_1 → TIFF giữ alpha + spot_1/SPOTCOLOR,300dpi.',
                  'Tên theo mã đơn: {mã}_font.tiff / {mã}_back.tiff. Không ghi AUTO RIP, không gửi khách; xuất xong chỉ ghi chú nội bộ chờ duyệt.',
                  'Trước xuất cần xác nhận: ' + '; '.join(proposal['export_policy']['per_job_required'])]
    elif proposal.get('export_policy'):
        lines += ['QUY TẮC CANAVI: JPG CMYK, 300dpi, khổ SAU CO; không phóng bù co, chưa lật gương. Mặt túi: bốn góc L1cm; vải mét: không định vị. Giữ CMYK/ICC gốc, không qua RGB. Lưu AI thật đủ artboard và màu nền dùng chung để sửa sau. Chỉ ghi chú nội bộ, chưa RIP/gửi khách.',
                  'Theo chiều CAO VẢI TRƯỚC CO: dưới70cm trừ cao2,5cm; từ70cm trừ cao5cm. Ngang luôn trừ2cm. Không chọn theo cạnh dài nhất hoặc chiều cao túi.',
                  'Không dùng lại khổ44,5×44 hoặc cữ9cm của mẫu trước cho mẫu mới. Thiếu chiều vải/mốc cữ thì cần kiểm tra.',
                  'Trước xuất cần xác nhận: ' + '; '.join(proposal['export_policy']['per_job_required']),
                  'Bộ xuất cho mẫu mới chưa tự chạy: cần xác minh logo/render và thông số riêng của phiếu.']
    for item in proposal['selections']:
        lines += [item['label'] + ' — ' + item['method'], 'Đối tượng: ' + ', '.join(item['object_ids']), item['reason']]
    lines += ['Cần kiểm tra: ' + x for x in proposal['missing_fields']]
    lines += ['Chưa sửa file, chưa xuất in, chưa gửi khách. Ảnh kèm là bản xem nguồn, chưa phải mẫu in.']
    return '\n'.join(lines)
