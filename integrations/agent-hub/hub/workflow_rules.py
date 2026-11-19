"""Explicit product rules, separate from ERP intake."""
import re
import unicodedata


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn').replace('đ','d')

def pet_profile(brief):
    # Only requirements for this design; archive/group names are not product evidence.
    data = brief.get('brief', {})
    text = normalize(' '.join(r.get('quote','') for r in data.get('requirements', [])))
    bag = bool(brief.get('bag_print')) or bool(re.search(r'\btui\b', text))
    hat = bool(re.search(r'\b(non|mu|ket)\b', text))
    if bag and hat:
        raise ValueError('PRODUCT_AMBIGUOUS: cùng hồ sơ có nón và túi; cần tách mẫu')
    return {'id': 'pet_bag' if bag else ('pet_hat' if hat else 'pet_general'),
            'height_cap_cm': 6.5 if hat else None, 'shrink_cm': [0,0],
            'white_contract_px': 0, 'color_contract_px': 1, 'version': 1}

def jpg_size(
    width: float,
    height: float,
    basis: str,
    kind: str,
    product_type: str = "bag",
    material: str = "canvas",
    shrink_compensation: float = 0.0,
) -> tuple[float, float]:
    """Tính kích thước Artboard xuất file JPG, ủy quyền sang hub.shrinkage_config.

    Giữ tương thích ngược 100% với chữ ký 4 tham số cũ, đồng thời hỗ trợ tra cứu
    theo loại sản phẩm, chất liệu và bù trừ co rút theo Requirement R3.
    """
    from hub.shrinkage_config import calculate_artboard_size
    return calculate_artboard_size(
        width=width,
        height=height,
        basis=basis,
        kind=kind,
        product_type=product_type,
        material=material,
        shrink_compensation=shrink_compensation,
    )



def hat_face_policy(face, profile):
    """Apply owner defaults only to an evidenced hat position with no customer size."""
    face['height_cap_cm'] = None
    if face.get('dimensions_basis') != 'owner_hat_default':
        # Customer measurements win. Preserve legacy source-layout cap only.
        if face.get('dimensions_basis') == 'source_layout':
            face['height_cap_cm'] = profile.get('height_cap_cm')
        return
    if face.get('product_kind') != 'hat' or profile.get('id') == 'pet_bag':
        raise ValueError('Chưa xác định sản phẩm nón để dùng kích thước mặc định')
    if face.get('side') in ('front', 'font', 'label'):
        face['owner_default_axis'] = 'height'
        face['owner_default_cm'] = 6.5
    elif face.get('side') in ('left', 'right'):
        face['owner_default_axis'] = 'width'
        face['owner_default_cm'] = 7.0
    else:
        raise ValueError('Vị trí nón chưa có kích thước mặc định; cần kiểm tra')
    face['width_cm'], face['height_cm'] = 1.0, 0.0
    face['dimension_policy'] = 'hat-position-defaults-v2'


def hat_default_size(face, width, height):
    if face.get('dimensions_basis') != 'owner_hat_default':
        return width, height
    value = face['owner_default_cm']
    # Use visible artwork ratio, never the whole mockup/page.
    if face['owner_default_axis'] == 'height':
        return value * width / height, value
    return value, value * height / width
