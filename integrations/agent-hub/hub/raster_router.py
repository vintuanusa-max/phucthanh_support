"""Cost-conscious routing with deterministic effective-DPI check; no generative redraw without consent."""
import base64
import io
import json
from pathlib import Path
from PIL import Image, ImageChops
from hub.replicate_redraw import redraw
from hub.workflow_rules import hat_default_size

AUTO_KEEP_MIN_DPI = 250.0
AUTO_UPSCALE_MIN_DPI = 150.0


def effective_dpi(raw: bytes, face: dict) -> dict:
    """Measure effective source DPI over the non-white/non-transparent artwork bounding box."""
    with Image.open(io.BytesIO(raw)) as im:
        rgba = im.convert('RGBA')
        w, h = rgba.size
        alpha = rgba.getchannel('A')
        has_alpha = alpha.getextrema()[0] < 255
        white_pct = 0.0
        if has_alpha:
            bb = alpha.getbbox()
        else:
            rgb = rgba.convert('RGB')
            border = (
                [rgb.getpixel((x, 0)) for x in range(0, w, max(1, w // 40))]
                + [rgb.getpixel((x, h - 1)) for x in range(0, w, max(1, w // 40))]
                + [rgb.getpixel((0, y)) for y in range(0, h, max(1, h // 40))]
                + [rgb.getpixel((w - 1, y)) for y in range(0, h, max(1, h // 40))]
            )
            white_pct = sum(1 for r, g, b in border if min(r, g, b) >= 245) / max(1, len(border))
            if white_pct >= 0.5:
                r_ch, g_ch, b_ch = rgb.split()
                min_ch = ImageChops.darker(ImageChops.darker(r_ch, g_ch), b_ch)
                bb = min_ch.point(lambda v: 255 if v < 245 else 0).getbbox()
            else:
                bb = (0, 0, w, h)
        if not bb:
            bb = (0, 0, w, h)
        art_w_px = max(1, bb[2] - bb[0])
        art_h_px = max(1, bb[3] - bb[1])

    basis = face.get('dimensions_basis')
    if basis == 'owner_hat_default':
        w_cm, h_cm = hat_default_size(face, art_w_px, art_h_px)
    else:
        w_cm = float(face.get('width_cm') or 0)
        h_cm = float(face.get('height_cm') or 0)
        if not w_cm and h_cm:
            w_cm = h_cm * art_w_px / art_h_px
        elif not h_cm and w_cm:
            h_cm = w_cm * art_h_px / art_w_px

    dpis = []
    if w_cm > 0:
        dpis.append(art_w_px / (w_cm / 2.54))
    if h_cm > 0:
        dpis.append(art_h_px / (h_cm / 2.54))
    eff = round(min(dpis), 1) if dpis else None
    return {
        'art_px': [art_w_px, art_h_px],
        'target_cm': [round(w_cm, 2), round(h_cm, 2)],
        'effective_dpi': eff,
        'has_alpha': has_alpha,
        'border_white_pct': round(white_pct, 3),
    }


def route(pet, raw, consent, folder, side, face):
    folder = Path(folder)
    folder.mkdir(exist_ok=True)
    dpi_info = effective_dpi(raw, face)
    face['dpi_check'] = dpi_info
    parts = [
        {'inline_data': {'mime_type': 'image/png', 'data': base64.b64encode(raw).decode()}},
        {'text': json.dumps({'face': face, 'dpi_check': dpi_info}, ensure_ascii=False)},
    ]
    props = {
        'action': {'type': 'string', 'enum': ['keep', 'upscale', 'redraw', 'review']},
        'reason': {'type': 'string'},
        'lines': {'type': 'array', 'items': {'type': 'string'}},
        'legible': {'type': 'boolean'},
        'background': {'type': 'string', 'enum': ['white', 'alpha', 'complex']},
        'white_artwork': {'type': 'boolean'},
        'blocking_issues': {'type': 'array', 'items': {'type': 'string'}},
    }
    plan = pet.ask(
        'Chọn cách ít tốn phí nhất để xử lý LOGO RIÊNG đã đối chiếu maket. '
        'keep nếu đủ nét ở kích thước in (dpi_check.effective_dpi >= 250); '
        'upscale chỉ khi ảnh sạch chỉ thiếu pixel (150 <= effective_dpi < 250); '
        'redraw cho logo/chữ/hình có nhiễu, xước, méo nét hoặc quá mờ cần phục dựng, kể cả khi vẫn đọc được chữ; '
        'review nếu chữ/số không đọc chắc, mất nét hoặc lẫn sản phẩm. Không sáng tạo mới. Đọc nguyên văn từng dòng. '
        'Phân biệt chi tiết trắng hoặc vùng sáng trắng 3D thuộc artwork và nền: nếu logo có chi tiết/viền/highlight trắng trên nền trắng hoặc nền màu đặc/phức tạp, đặt white_artwork=true để tách nền giữ chi tiết trắng. '
        'Dựa theo dpi_check.has_alpha: CHỈ đặt background="alpha" khi has_alpha=true; nếu has_alpha=false và nền viền trắng thì đặt background="white". '
        'white_artwork CHỈ xét trên ảnh gốc đầu vào trước khi áp color_overlay. '
        'Tách nền không phải vẽ lại. blocking_issues chỉ là vấn đề KHÔNG THỂ xử lý theo action đã chọn, ví dụ sai nguồn/chữ không rõ. Răng cưa/thiếu độ phân giải xử lý được bằng upscale không phải blocking_issues.',
        parts,
        {'type': 'object', 'properties': props, 'required': list(props)},
    )
    if dpi_info.get('has_alpha'):
        plan['background'] = 'alpha'
    elif plan['background'] == 'alpha':
        plan['background'] = 'white' if (dpi_info.get('border_white_pct') or 0) >= 0.5 else 'complex'
    spec = face.get('instructions')
    if spec and spec.get('mode') == 'edit':
        if not consent:
            raise ValueError('Chỉnh ảnh thiếu xác nhận nguồn khách')
        if plan['blocking_issues'] or not plan['legible']:
            raise ValueError('Nguồn chỉnh ảnh chưa đọc rõ: ' + plan['reason'])
        plan.update(action='redraw', lines=spec['expected_lines'])

    eff_dpi = dpi_info.get('effective_dpi')
    if (
        (not spec or spec.get('mode') != 'edit')
        and not plan['blocking_issues']
        and plan['legible']
        and plan['action'] != 'review'
        and eff_dpi is not None
    ):
        if eff_dpi >= AUTO_KEEP_MIN_DPI and plan['action'] == 'upscale':
            plan['action'] = 'keep'
            plan['reason'] = (plan.get('reason', '') + f' [DPI={eff_dpi}>={AUTO_KEEP_MIN_DPI:.0f}: giữ nguyên nét gốc]').strip()
        elif AUTO_UPSCALE_MIN_DPI <= eff_dpi < AUTO_KEEP_MIN_DPI and plan['action'] == 'keep':
            plan['action'] = 'upscale'
            plan['reason'] = (plan.get('reason', '') + f' [DPI={eff_dpi} trong khoảng 150-250: tự động upscale Real-ESRGAN 2x]').strip()
        elif eff_dpi < AUTO_UPSCALE_MIN_DPI and plan['action'] in ('keep', 'upscale'):
            plan['action'] = 'redraw' if consent else 'review'
            plan['reason'] = (plan.get('reason', '') + f' [DPI={eff_dpi}<{AUTO_UPSCALE_MIN_DPI:.0f}: quá thấp để chỉ upscale]').strip()

    if consent and consent.get('enhance_only') and plan['action'] == 'redraw':
        plan['original_action'] = 'redraw'
        plan['action'] = 'upscale'
        plan['owner_limit'] = 'Enhance existing pixels only; no generative redraw'
    (folder / (side + '.route.json')).write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
    if plan['blocking_issues'] or not plan['legible'] or plan['action'] == 'review':
        raise ValueError('Router cần nhân viên: ' + plan['reason'])
    if plan['action'] == 'redraw' and not consent:
        raise ValueError('Cần nhân viên hỏi file và khách xác nhận không có trước phục dựng')

    # Non-generative segmentation and clean 2x upscale are permitted without generative-redraw consent.
    seg_permission = consent or {
        'question_message_id': 'segmentation-only',
        'answer_message_id': 'existing-artwork',
        'method': 'non-generative-background-removal',
    }
    upscale_permission = consent or {
        'question_message_id': 'auto-upscale',
        'answer_message_id': 'clean-low-res-artwork',
        'method': 'non-generative-upscale',
    }

    def uri(data):
        return 'data:image/png;base64,' + base64.b64encode(data).decode()

    result = raw
    if plan['action'] == 'upscale':
        result = redraw(
            pet,
            result,
            upscale_permission,
            folder,
            side + '_upscale',
            model='nightmareai/real-esrgan',
            parameters={'image': uri(result), 'scale': 2, 'face_enhance': False},
        )
    elif plan['action'] == 'redraw':
        from hub.openai_redraw import redraw as openai_redraw
        result = openai_redraw(pet, result, consent, folder, side, plan['lines'], instructions=spec)
        face['background'] = 'alpha'
        face['white_artwork'] = plan['white_artwork']
        face['router'] = plan
        face['redraw_provider'] = 'openai/gpt-image-2.5-sunburst'
        face['openai_usage'] = json.loads((folder / (side + '.openai.json')).read_text()).get('usage', {})
        return result

    solid_overlay = (face.get('color_overlay') or {}).get('mode') == 'solid_color'
    if plan['background'] == 'alpha':
        face['background'] = 'alpha'
    elif plan['background'] == 'white' and (not plan['white_artwork'] or solid_overlay):
        # Strip exterior & enclosed white matte and duplicate layer 2x to restore opacity (ideal before solid Color Overlay too).
        face['background'] = 'white'
        plan['white_artwork'] = False
    elif plan['background'] == 'complex' or (plan['background'] == 'white' and plan['white_artwork']):
        result = redraw(pet, result, seg_permission, folder, side + '_background', model='men1scus/birefnet', parameters={'image': uri(result)})
        with Image.open(io.BytesIO(result)) as im:
            if 'A' not in im.getbands() or im.getchannel('A').getextrema()[0] == 255:
                raise ValueError('BiRefNet chưa tạo nền trong suốt')
        face['background'] = 'alpha'
    else:
        face['background'] = plan['background']

    face['white_artwork'] = plan['white_artwork']
    face['router'] = plan
    return result
