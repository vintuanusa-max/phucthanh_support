"""Independent LLM step that binds explicit customer size messages to already-selected PET faces."""
import copy
import json
import math
import re

from hub.export_routing import CANAVI_GROUPS, JPG_GROUPS


def collect_customer_messages(brief_payload):
    """Collect customer-authored text messages (with stable message:<id> refs) from brief sources."""
    sources = (brief_payload or {}).get('sources') or []
    by_id = {}
    ordered = []

    def _clean(text):
        cleaned = re.sub(r'\[(?:File|Ảnh)[^\]]*\]', ' ', str(text or ''))
        return re.sub(r'\s+', ' ', cleaned).strip()

    for s in sources:
        if not isinstance(s, dict):
            continue
        if s.get('recalled') or s.get('revision'):
            continue
        if s.get('origin') in ('staff', 'legacy_bot', 'erp') or s.get('role') in ('staff', 'internal', 'bot'):
            continue
        if s.get('direction') == 'outgoing':
            continue
        mid = str(s.get('message_id') or '').strip()
        if not mid:
            continue
        text = _clean(s.get('text', ''))
        if not text:
            continue
        ref = f'message:{mid}'
        if ref not in by_id:
            item = {'ref': ref, 'message_id': mid, 'text': text}
            by_id[ref] = item
            ordered.append(item)

    brief_reqs = ((brief_payload or {}).get('brief') or {}).get('requirements') or []
    for req in brief_reqs:
        if not isinstance(req, dict) or req.get('basis') != 'text':
            continue
        mid = str(req.get('message_id') or '').strip()
        if not mid:
            continue
        ref = f'message:{mid}'
        src = next((s for s in sources if isinstance(s, dict) and str(s.get('message_id') or '').strip() == mid), None)
        if src and (src.get('origin') in ('staff', 'legacy_bot', 'erp') or src.get('role') in ('staff', 'internal', 'bot') or src.get('direction') == 'outgoing'):
            continue
        text = _clean(req.get('quote') or req.get('text') or '')
        if not text:
            continue
        if ref not in by_id:
            item = {'ref': ref, 'message_id': mid, 'text': text}
            by_id[ref] = item
            ordered.append(item)

    return ordered


def apply_adjustment_math(faces, ai_result, valid_refs):
    """Apply validated aspect-preserving customer dimension overrides to selected PET faces."""
    updated = [copy.deepcopy(f) for f in (faces or [])]
    by_side = {f.get('side'): f for f in updated if isinstance(f, dict) and f.get('side')}
    valid = set(valid_refs or [])
    notes = []
    warnings = []

    if not isinstance(ai_result, dict):
        return updated, notes, warnings

    for u in ai_result.get('unmatched_requests') or []:
        if isinstance(u, str) and u.strip():
            warnings.append('Yêu cầu kích thước chưa khớp vị trí: ' + u.strip())

    for adj in ai_result.get('adjustments') or []:
        if not isinstance(adj, dict):
            continue
        side = str(adj.get('side') or '').strip()
        face = by_side.get(side)
        if not face or adj.get('action') != 'resize':
            continue
        refs = [str(r) for r in (adj.get('dimension_refs') or []) if str(r) in valid]
        if not refs:
            warnings.append(f'Bỏ qua chỉnh kích thước {side}: thiếu bằng chứng tin khách hợp lệ')
            continue

        orig_w = float(face.get('source_width_cm') or face.get('width_cm') or 0.0)
        orig_h = float(face.get('source_height_cm') or face.get('height_cm') or 0.0)
        if orig_w <= 0 or orig_h <= 0 or not (math.isfinite(orig_w) and math.isfinite(orig_h)):
            warnings.append(f'Bỏ qua chỉnh kích thước {side}: kích thước gốc không hợp lệ')
            continue

        axis = adj.get('axis')
        w_val = adj.get('width_cm')
        h_val = adj.get('height_cm')
        new_w = None
        new_h = None

        if axis == 'width' and isinstance(w_val, (int, float)) and math.isfinite(w_val) and 0.5 <= float(w_val) <= 160.0:
            new_w = float(w_val)
            new_h = new_w * orig_h / orig_w
        elif axis == 'height' and isinstance(h_val, (int, float)) and math.isfinite(h_val) and 0.5 <= float(h_val) <= 160.0:
            new_h = float(h_val)
            new_w = new_h * orig_w / orig_h
        elif (
            axis == 'both'
            and isinstance(w_val, (int, float))
            and isinstance(h_val, (int, float))
            and math.isfinite(w_val)
            and math.isfinite(h_val)
            and 0.5 <= float(w_val) <= 160.0
            and 0.5 <= float(h_val) <= 160.0
        ):
            w_f = float(w_val)
            h_f = float(h_val)
            target_ratio = w_f / h_f
            orig_ratio = orig_w / orig_h
            if abs(target_ratio / orig_ratio - 1.0) > 0.05:
                warnings.append(
                    f'{side}: kích thước khách {w_f:g}×{h_f:g}cm lệch tỷ lệ artwork gốc '
                    f'({orig_w:.2f}×{orig_h:.2f}cm >5%); giữ nguyên khổ gốc để không kéo méo'
                )
                continue
            new_w = w_f
            new_h = new_w * orig_h / orig_w
        else:
            warnings.append(f'Bỏ qua chỉnh kích thước {side}: số đo hoặc trục không hợp lệ ({axis})')
            continue

        if not (0.1 <= new_w <= 160.0 and 0.1 <= new_h <= 160.0):
            warnings.append(f'{side}: khổ sau tính ({new_w:.2f}×{new_h:.2f}cm) vượt giới hạn 0.1–160cm')
            continue

        reason = str(adj.get('reason') or '').strip()
        face['source_width_cm'] = round(orig_w, 4)
        face['source_height_cm'] = round(orig_h, 4)
        face['basis'] = 'explicit'
        face['width_cm'] = round(new_w, 4)
        face['height_cm'] = round(new_h, 4)
        face['dimension_refs'] = refs
        face['dimension_explanation'] = reason or f'Khách yêu cầu chỉnh kích thước theo {", ".join(refs)}'
        face['customer_size_note'] = reason or f'Theo {", ".join(refs)}'
        notes.append(
            f"{side}: {orig_w:.2f}×{orig_h:.2f}cm → {new_w:.2f}×{new_h:.2f}cm ({', '.join(refs)})"
        )

    return updated, notes, warnings


def _face_preview_parts(faces, scan):
    parts = []
    cand_map = {
        c['id']: c
        for c in ((scan or {}).get('candidates') or [])
        if isinstance(c, dict) and c.get('id')
    }
    for f in faces:
        side = f.get('side', '')
        for cid in (f.get('candidate_ids') or [])[:2]:
            preview = (cand_map.get(cid) or {}).get('preview')
            if preview:
                parts.extend([
                    {'text': f'SELECTED_FACE_PREVIEW side={side} candidate={cid}'},
                    {'inline_data': {'mime_type': 'image/png', 'data': preview}},
                ])
    return parts


def apply_customer_dimensions(e, r, p, context, faces, thread_id, brief_payload, scan=None):
    """Run an isolated post-selection LLM check to bind customer-specified cm sizes to PET faces."""
    if not thread_id or thread_id in (JPG_GROUPS | CANAVI_GROUPS) or not faces:
        return faces, [], []

    cust_msgs = collect_customer_messages(brief_payload)
    if not cust_msgs:
        return faces, [], []

    valid_refs = [m['ref'] for m in cust_msgs]
    sides = [f['side'] for f in faces if isinstance(f, dict) and f.get('side')]
    if not sides:
        return faces, [], []

    faces_summary = [
        {
            'side': f['side'],
            'source_width_cm': round(float(f.get('source_width_cm') or f.get('width_cm') or 0.0), 3),
            'source_height_cm': round(float(f.get('source_height_cm') or f.get('height_cm') or 0.0), 3),
            'usages': f.get('usages', []),
            'explanation': f.get('explanation', ''),
        }
        for f in faces
    ]

    schema = {
        'type': 'object',
        'required': ['adjustments', 'unmatched_requests'],
        'properties': {
            'adjustments': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'required': ['side', 'action', 'axis', 'width_cm', 'height_cm', 'dimension_refs', 'reason'],
                    'properties': {
                        'side': {'type': 'string', 'enum': sides},
                        'action': {'type': 'string', 'enum': ['resize', 'keep_source']},
                        'axis': {'type': 'string', 'enum': ['width', 'height', 'both', 'none']},
                        'width_cm': {'type': 'number'},
                        'height_cm': {'type': 'number'},
                        'dimension_refs': {'type': 'array', 'items': {'type': 'string', 'enum': valid_refs}},
                        'reason': {'type': 'string'},
                    },
                },
            },
            'unmatched_requests': {'type': 'array', 'items': {'type': 'string'}},
        },
    }

    prompt = (
        'CUSTOMER_DIMENSIONS_STEP: Nhiệm vụ duy nhất ở bước này là đối chiếu các tin nhắn của KHÁCH HÀNG (CUSTOMER_MESSAGES) '
        'với danh sách mặt artwork PET ĐÃ CHỌN (SELECTED_FACES) và xác định mặt nào cần đổi kích thước theo yêu cầu khách.\n'
        'QUY TẮC:\n'
        '1. Đọc hiểu ngữ cảnh tự nhiên: Ví dụ khách nhắn "mạc ngang 7 cm", "mặt trước rộng 8cm", "logo trán cao 6.5cm", "đuôi ngang 7 cm", '
        '"sau gáy 5cm", "hông trái ngang 4cm"... hãy khớp đúng vào side tương ứng (front/label cho mạc-mặt trước-trán, back cho đuôi-mặt sau-gáy, '
        'left/right cho hông, brim cho vành) dựa vào `side`, `usages` và `SELECTED_FACE_PREVIEW`.\n'
        '2. Khi khách chỉ ghi một chiều:\n'
        '   - "ngang X cm" / "rộng X cm" -> action="resize", axis="width", width_cm=X, height_cm=0.\n'
        '   - "cao X cm" -> action="resize", axis="height", width_cm=0, height_cm=X.\n'
        '   - Nếu khách chỉ ghi "mạc 7cm" (một số đơn lẻ không ghi ngang/cao) cho mạc/logo nằm ngang, hoặc ngữ cảnh nón/tem nhãn chuẩn, hãy xem hình dáng artwork trong preview để chọn trục hợp lý hoặc ghi rõ trong reason.\n'
        '3. Phân biệt KÍCH THƯỚC LOGO CẦN IN với SỐ LƯỢNG (ví dụ "200c", "1.000c"), KHỔ SẢN PHẨM (ví dụ "túi 35x45"), hay CỮ KHOẢNG CÁCH ÉP NHIỆT (ví dụ "cách miệng 5cm", "cách đáy 2cm"). Không lấy số lượng hoặc cữ ép làm kích thước logo.\n'
        '4. Nếu mặt nào khách KHÔNG yêu cầu kích thước cụ thể -> action="keep_source", axis="none", width_cm=0, height_cm=0.\n'
        '5. Mọi adjustment có action="resize" BẮT BUỘC dẫn dimension_refs trỏ tới đúng `message:<id>` trong CUSTOMER_MESSAGES.\n'
        '6. Nếu khách có yêu cầu kích thước rõ ràng cho một vị trí in nhưng vị trí đó KHÔNG có trong SELECTED_FACES -> ghi ngắn gọn vào `unmatched_requests`, không gán nhầm sang mặt khác.'
    )

    parts = [
        {'text': 'CUSTOMER_MESSAGES ' + json.dumps(cust_msgs, ensure_ascii=False)},
        {'text': 'SELECTED_FACES ' + json.dumps(faces_summary, ensure_ascii=False)},
    ] + _face_preview_parts(faces, scan)

    from hub.native_auto import ask_once, save
    ai_result = ask_once(e, r, p, 'customer_dimensions_v1', prompt, parts, schema)
    updated_faces, notes, warnings = apply_adjustment_math(faces, ai_result, valid_refs)
    p['customer_dimension_plan'] = {
        'customer_messages': cust_msgs,
        'ai_result': ai_result,
        'applied_notes': notes,
        'warnings': warnings,
    }
    save(e, r, p)
    return updated_faces, notes, warnings
