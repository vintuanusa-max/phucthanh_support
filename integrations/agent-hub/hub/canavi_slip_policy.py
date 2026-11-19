"""Image-reading exception for the two owner-authorized CANAVI slip groups."""
import json
import re
import unicodedata

GROUPS = frozenset(('g1790239230897256718', 'g2671966061008128194'))

READING_POLICY = (
    'Riêng túi chuyển nhiệt CANAVI: đọc nguyên văn KT VẢI vào ghi chú từng dòng túi. '
    'Phân biệt chiều cao tấm vải với chiều cao túi thành phẩm, khổ hình và cữ miệng. '
    'Nếu ghi KT VẢI A x B không có nhãn trục, cạnh lớn là cao. Cao vải >70 cm là túi liền: '
    'hai mặt chung MỘT dòng TUI, số lượng bằng số túi trên phiếu. Dòng “Quy cách phiếu: ” '
    'ghi túi chuyển nhiệt 2 mặt. Không tạo hai dòng TUI1MAT cho hai mặt túi liền. '
    'Nếu cao vải <=70 cm, hai mặt in chuyển nhiệt rời là hai dòng TUI1MAT, mỗi dòng giữ số túi. '
    'Nếu chưa rõ chiều cao vải, không mặc định là túi rời hoặc liền. Giữ riêng các kỹ thuật khác. '
    'Phiếu CANAVI/CANAVI HCM2: ưu tiên các ô có nhãn Mã Sản phẩm, Ngày đặt hàng, '
    'Ngày giao hàng, Số lượng (chiếc), Số màu/mặt và các dòng chỉ dẫn IN ở cuối phiếu. '
    'Đọc theo nhãn, không cần ảnh thực tế có khung đỏ. Mã sản phẩm là tên/mã mẫu khách, '
    'không tự coi là mã hàng ERP. Số lượng lấy từ ô Số lượng (chiếc); số màu không phải '
    'số lượng hay số vị trí. Đọc ô Số màu/mặt và chỉ dẫn cuối phiếu để phân biệt kỹ thuật '
    'và mặt/vị trí in; không tự nhân tổng số lượng theo số màu. Kích thước/quy cách túi, '
    'quai, mô tả may và hình maket chỉ là tham khảo; không lấy kích thước túi làm kích thước in. '
    'Chỉ dẫn cuối phiếu ghi rõ kích thước in/vải in thì giữ đúng ý, không nhầm hai loại. '
    'Áp dụng FABRIC_AXIS_POLICY: khi phiếu ghi KT VẢI A X B mà A > B thì A là chiều dài/cao tấm vải (height_cm) '
    'và B là chiều ngang khổ vải (width_cm). '
    'Dòng "CỮ IN + MIỆNG ... CM" (hoặc "CỮ IN + MIỆNG CM") trên phiếu lệnh xác nhận cữ may gập miệng túi '
    '(edge_finish="fold", seam_allowance_cm=0). '
    'Với mỗi dòng đề xuất, ghi vào ghi_chu_mau_do một dòng bắt đầu bằng “Quy cách phiếu: ”, theo sau là kỹ thuật, số màu, số mặt, loại sản phẩm và khổ in của riêng dòng đó, đúng theo ô Số màu/mặt và chỉ dẫn in. Giữ dấu + của khổ PET. Không lấy kích thước túi làm khổ PET, không lấy số mặt hoặc số màu của kỹ thuật khác. Thiếu thông tin thì chỉ ghi phần đọc được. '
    'Ngày đặt và ngày giao phải phân biệt, giữ đúng ngày đọc được; thiếu/mờ/mâu thuẫn thì '
    'nêu điểm vướng, không tự sửa năm hoặc suy đoán. Không tạo thêm đơn từ maket.'
)


def _fold(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.casefold())
                   if not unicodedata.combining(c)).replace('đ', 'd')


def fabric_height_cm(note):
    number = r'(\d+(?:[.,]\d+)?)'
    label = r'\b(?:kt|kich thuoc|kho)\s+vai(?:\s+in)?\s*[:=]?\s*'
    text = _fold(note)
    heights = set()
    for match in re.finditer(label + r'(?:(cao|ngang|rong)\s*[:=]?\s*)?' + number
                             + r'\s*(cm|mm|m)?\s*[x×*]\s*(?:(cao|ngang|rong)\s*[:=]?\s*)?'
                             + number + r'\s*(cm|mm|m)?(?![\w.,]\d)', text):
        axis_a, a, unit_a, axis_b, b, unit_b = match.groups()
        factors = {'cm': 1, 'mm': 0.1, 'm': 100}
        a = float(a.replace(',', '.')) * factors[unit_a or unit_b or 'cm']
        b = float(b.replace(',', '.')) * factors[unit_b or unit_a or 'cm']
        if axis_a and axis_b and (axis_a == 'cao') == (axis_b == 'cao'):
            return None
        if axis_a == 'cao' or axis_b in ('ngang', 'rong'):
            heights.add(a)
        elif axis_b == 'cao' or axis_a in ('ngang', 'rong'):
            heights.add(b)
        else:
            heights.add(max(a, b))
    return heights.pop() if len(heights) == 1 else None


def continuous_bags(items):
    """One physical panel per bag. Work on copies before independent image verification."""
    result, groups = [], {}
    for original in items:
        item = dict(original)
        note = item.get('ghi_chu_mau_do') or ''
        title = item.get('ten_mau') or ''
        text = _fold(title + ' ' + note)
        height = fabric_height_cm(note)
        if (height is None or height <= 70 or not re.search(r'\btui\b', text)
                or not re.search(r'\b(?:chuyen nhiet|cn)\b', text)
                or re.search(r'\b(?:pet|lua|luoi|quai roi)\b', _fold(title))):
            result.append(item)
            continue
        spec = next((s for s in note.splitlines() if s.casefold().startswith('quy cách phiếu:')), '')
        if re.search(r'\b(?:pet|lua|luoi)\b', _fold(spec or note)):
            result.append(item)
            continue
        design = item.get('ten_don_hang') or ''
        previous_code = item.get('ma_san_pham')
        if not design and previous_code and previous_code.upper() not in ('TUI', 'TUI1MAT'):
            design = item['ten_don_hang'] = previous_code
        stem = re.sub(r'\s*[-–:(]?\s*mặt (?:trước|sau)\s*\)?$', '', title, flags=re.I)
        key = (design, stem.casefold(), item.get('print_position_group'), height)
        detail = [s if s != spec else 'Trên phiếu: ' + s.partition(':')[2].strip()
                  for s in note.splitlines()]
        side = re.search(r'mặt (trước|sau)\s*\)?$', title, re.I)
        side = side.group(1).casefold() if side else None
        if key in groups:
            first, first_side = groups[key]
            if (first['so_luong'] != item['so_luong'] or not (design or stem)
                    or {first_side, side} != {'trước', 'sau'}):
                raise ValueError('Cần đối chiếu số lượng và mã mẫu của hai mặt túi liền.')
            groups[key] = first, None
            for line in detail:
                if line not in first['ghi_chu_mau_do'].splitlines():
                    first['ghi_chu_mau_do'] += '\n' + line
            continue
        item.update(ma_san_pham='TUI', ten_mau=stem or title,
                    ghi_chu_mau_do='\n'.join(['Quy cách phiếu: Túi chuyển nhiệt 2 mặt', *detail]))
        groups[key] = item, side
        result.append(item)
    return result


def sender_id(policy, run):
    if run.get('account') != 'zalo-personal-1' or run.get('thread_id') not in GROUPS:
        return None
    rule = (policy or {}).get('group_intake_rules', {}).get(run['account'], {}).get(run['thread_id'], {})
    if rule.get('mode') != 'primary_slip_sender':
        return None
    return str(rule.get('primary_sender_id') or '') or None


def selected(policy, run, messages):
    sender = sender_id(policy, run)
    if not sender:
        return []
    return [m for m in messages if m.get('account') == run['account'] and m.get('thread_id') == run['thread_id']
            and str(m.get('sender_id')) == sender and m.get('origin') == 'customer'
            and m.get('direction') == 'incoming' and m.get('images')
            and not m.get('revision') and not m.get('recalled')]


def export_admitted(policy, run, messages):
    """Admission to source matching, not permission to export an unverified file."""
    if not sender_id(policy, run):
        return False
    return bool(selected(policy, run, messages)) or any(
        m.get('account') == run['account'] and m.get('thread_id') == run['thread_id']
        and not m.get('revision') and not m.get('recalled') and m.get('role') != 'bot'
        and any(a.get('name', '').lower().endswith(('.ai','.pdf','.psd','.cdr','.eps','.svg','.tif','.tiff'))
                for a in m.get('assets', [])) for m in messages)


def export_sources(intake, run, messages):
    """A later file may refer to primary-sender slips from the same receipt day.

    These are candidates, never automatically matched by date/proximity.
    """
    policy = intake.policy(run['account'])
    result = {m['message_id']:m for m in messages}
    if not selected(policy, run, messages):
        from hub.receipt_match import day_bounds
        with intake.store.db() as db:
            for start,end in {day_bounds(m['timestamp']) for m in messages}:
                rows=db.execute("SELECT payload FROM captures WHERE account=? AND thread_id=? AND CAST(json_extract(payload,'$.timestamp') AS REAL)>=? AND CAST(json_extract(payload,'$.timestamp') AS REAL)<? ORDER BY revision DESC",(run['account'],run['thread_id'],start,end)).fetchall()
                latest={}
                for row in rows:
                    m=json.loads(row[0]);latest.setdefault(m['message_id'],m)
                for m in selected(policy,run,list(latest.values())):
                    result.setdefault(m['message_id'],m)
    return sorted(result.values(),key=lambda m:m['timestamp'])


EXPORT_POLICY = (
    'NGOẠI LỆ CANAVI/CANAVI HCM2: phiếu lệnh là yêu cầu xuất file, không cần câu làm mẫu. '
    'Tạo print_export từ phiếu và file thiết kế liên quan. Giữ ảnh phiếu làm nguồn thông số. '
    'Đọc theo READING_POLICY; phân biệt mã mẫu, PET/chuyển nhiệt, kích thước artwork, cữ và khổ vải. '
    'Áp dụng FABRIC_AXIS_POLICY cho trục khổ vải và nhận diện "CỮ IN + MIỆNG ... CM" là edge_finish="fold". '
    'Nguồn cùng ngày chỉ là ứng viên: phải đối chiếu mã mẫu, phiên bản, nội dung phiếu/maket và file. '
    'Không tự ghép vì gần thời gian; chưa có phiếu/file hoặc chưa khớp thì giữ hồ sơ chờ/kiểm tra. '
    'Tái bản file tháng cũ chỉ hợp lệ khi có căn cứ rõ trên phiếu/tin; ghi căn cứ và vẫn kiểm chứng nội dung. '
    'Không lấy kích thước túi làm kích thước artwork. Không tạo ERP hoặc gửi khách từ nhánh file.'
)


def agent_images(intake, run, messages):
    """Reload exact source IDs: cleaned Agent context deliberately omits image IDs."""
    policy = intake.policy(run['account'])
    if not sender_id(policy, run) or len(messages) != 1:
        return []
    if messages[0].get('role', 'customer') != 'customer':
        return []
    with intake.store.db() as db:
        row = db.execute('SELECT account,thread_id,payload FROM intake_runs WHERE id=?', (run['id'],)).fetchone()
        if not row or row['account'] != run['account'] or row['thread_id'] != run['thread_id']:
            return []
        payload = json.loads(row['payload'])
        ids = [m['message_id'] for m in messages]
        if not payload.get('individual_slip') or payload.get('individual_slip_rules') != 2 or payload.get('messages') != ids:
            return []
        capture = db.execute('SELECT payload FROM captures WHERE account=? AND thread_id=? AND message_id=? ORDER BY revision DESC LIMIT 1',
                             (run['account'], run['thread_id'], ids[0])).fetchone()
    if not capture:
        return []
    source = json.loads(capture['payload'])
    if not selected(policy, run, [source]) or not intake.accepts(source) or len(source['images']) != 1:
        return []
    return intake.store.images(source['images'])
