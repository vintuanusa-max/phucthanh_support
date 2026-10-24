"""Conservative source-object renderer. Never invent or erase pixels by color."""
import hashlib
import math
import re
from pathlib import Path
from PIL import Image
import pymupdf as fitz
from hub.artwork_objects import inventory
from hub.workflow_rules import hat_default_size


def capped_size(width,height,cap=None):
    scale=min(1.0,cap/height) if cap is not None else 1.0
    return width*scale,height*scale,scale


def code_name(code):
    if not isinstance(code, str) or not code.strip() or len(code) > 100:
        raise ValueError('Thiếu mã đơn PET')
    name = re.sub(r'[^\w-]', '', code, flags=re.UNICODE)
    if not name or name.upper() in {'CON', 'PRN', 'AUX', 'NUL'} or re.fullmatch(r'(COM|LPT)[0-9]', name, re.I):
        raise ValueError('Mã đơn không dùng được làm tên file')
    return name


def validate_plan(plan, objects, refs):
    if plan.get('is_pet') is not True or plan.get('issues'):
        raise ValueError('; '.join(plan.get('issues', [])) or 'Chưa xác nhận in PET')
    code_name(plan.get('order_code'))
    faces = plan.get('faces', [])
    if not 1 <= len(faces) <= 8 or len({f['side'] for f in faces}) != len(faces):
        raise ValueError('Chưa xác định riêng mặt trước/sau')
    known = {o['id']: o for o in objects}
    for face in faces:
        if face.get('side') not in ('font','front','back','left','right','brim','label',*[f'position_{i}' for i in range(1,9)]):
            raise ValueError('Mặt in chưa hỗ trợ')
        ids = face.get('object_ids', [])
        if not ids or len(ids) != len(set(ids)) or not set(ids) <= known.keys():
            raise ValueError('Cụm artwork thiếu hoặc sai ID')
        if len({known[x]['page'] for x in ids}) != 1:
            raise ValueError('Cụm artwork nằm trên nhiều trang')
        dims = [face.get('width_cm'), face.get('height_cm')]
        if face.get('dimensions_basis')=='source_layout' and dims==[0,0]:dims=[1,1]
        if any(type(x) not in (int,float) or not math.isfinite(x) for x in dims) or not .1<=dims[0]<=160 or not (dims[1]==0 or .1<=dims[1]<=160):
            raise ValueError('Thiếu kích thước in thật từng mặt')
        if dims[0] * dims[1] * (300 / 2.54)**2 > 45_000_000:
            raise ValueError('Khổ PET vượt giới hạn 45 triệu pixel; cần kiểm tra')
        if not face.get('dimension_refs') or not set(face['dimension_refs']) <= set(refs):
            raise ValueError('Kích thước thiếu bằng chứng phiếu/maket')
        if face.get('dimensions_basis') not in ('explicit_measurement', 'maket_ratio_confirmed','source_layout','owner_hat_default'):
            raise ValueError('Chưa có căn cứ kích thước')
        if not face.get('dimension_explanation'):
            raise ValueError('Thiếu giải thích kích thước')
    return faces


def render_face(source, sha, face, target):
    source = Path(source)
    if hashlib.sha256(source.read_bytes()).hexdigest() != sha:
        raise ValueError('File nguồn đã thay đổi')
    inv = inventory(source)
    if inv['truncated']:
        raise ValueError('Inventory chưa đầy đủ')
    selected = [o for o in inv['objects'] if o['id'] in face['object_ids']]
    if len(selected) != len(face['object_ids']):
        raise ValueError('Đối tượng nguồn không còn khớp')
    with fitz.open(source) as doc:
        page = doc[selected[0]['page'] - 1]
        if page.rotation:
            raise ValueError('Trang xoay cần kiểm tra riêng')
        kinds = {x['kind'] for x in selected}
        box = fitz.Rect()
        for x in selected:
            box |= fitz.Rect(x['bbox_pt'])
        if box.is_empty:
            raise ValueError('Artwork rỗng')
        source_width_cm=box.width*2.54/72;source_height_cm=box.height*2.54/72
        if face.get('dimensions_basis')=='source_layout':face['width_cm']=source_width_cm;face['height_cm']=0
        ratio = face['width_cm'] / (face['height_cm'] or (face['width_cm']*box.height/box.width))
        if kinds != {'image'} and abs(ratio / (box.width / box.height) - 1) > .025:
            raise ValueError('Tỷ lệ kích thước và artwork lệch quá 2,5%; không kéo méo')
        out = fitz.open()
        canvas = out.new_page(width=page.rect.width, height=page.rect.height)
        if kinds == {'vector_path'}:
            for clip in page.get_drawings(extended=True):
                if clip['type'] == 'group':
                    raise ValueError('Transparency group cần kiểm tra riêng')
                if clip['type'] == 'clip' and (len(clip['items']) != 1 or clip['items'][0][0] != 're' or not fitz.Rect(clip['scissor']).contains(box)):
                    raise ValueError('Clipping phức tạp cần kiểm tra riêng')
            page_objects = [x for x in inv['objects'] if x['page'] == selected[0]['page'] and x['kind'] == 'vector_path']
            chosen = set(face['object_ids'])
            for obj, path in zip(page_objects, page.get_drawings()):
                if obj['id'] not in chosen:
                    continue
                shape = canvas.new_shape()
                for seg in path['items']:
                    if seg[0] == 'l': shape.draw_line(seg[1], seg[2])
                    elif seg[0] == 'c': shape.draw_bezier(*seg[1:])
                    elif seg[0] == 're': shape.draw_rect(seg[1])
                    elif seg[0] == 'qu': shape.draw_quad(seg[1])
                    else: raise ValueError('Nét vector chưa hỗ trợ')
                shape.finish(fill=path.get('fill'), color=path.get('color'),
                             width=path.get('width') or 0, dashes=path.get('dashes'),
                             lineCap=max(path.get('lineCap') or (0,)), lineJoin=path.get('lineJoin') or 0,
                             closePath=path.get('closePath', False), even_odd=path.get('even_odd', False),
                             fill_opacity=path.get('fill_opacity') if path.get('fill_opacity') is not None else 1,
                             stroke_opacity=path.get('stroke_opacity') if path.get('stroke_opacity') is not None else 1)
                shape.commit()
        elif kinds == {'image'} and len(selected) > 1:
            # Preserve PDF clipping and relative placement of a complete embedded-image cluster.
            page_images=[x for x in inv['objects'] if x['page']==selected[0]['page'] and x['kind']=='image']
            if {x['id'] for x in selected}!={x['id'] for x in page_images}:
                raise ValueError('Cụm ảnh chỉ lấy một phần trang: cần kiểm tra clip riêng')
            masks={x[0]:x[1] for x in page.get_images()}
            if any(not x['xref'] or not masks.get(x['xref']) for x in page.get_image_info(xrefs=True)):
                raise ValueError('Cụm ảnh có nền chưa trong suốt; cần duyệt')
            out.close();out=fitz.open();out.insert_pdf(doc,from_page=selected[0]['page']-1,to_page=selected[0]['page']-1)
            canvas=out[0]
            # Remove only page text/vectors; image masks and PDF clip operators remain intact.
            canvas.add_redact_annot(canvas.rect,fill=False,cross_out=False)
            canvas.apply_redactions(images=0,graphics=2,text=0)
            probe=canvas.get_pixmap(matrix=fitz.Matrix(2,2),alpha=True)
            import io
            rgba=Image.open(io.BytesIO(probe.tobytes('png'))).convert('RGBA')
            crop=rgba.getchannel('A').point(lambda v:0 if v<=1 else v).getbbox()
            if not crop:raise ValueError('Cụm ảnh không có artwork sau clipping')
            box=fitz.Rect(*(v/2 for v in crop))
            source_width_cm=box.width*2.54/72;source_height_cm=box.height*2.54/72
        elif kinds == {'image'} and len(selected) == 1:
            infos = page.get_image_info(xrefs=True)
            page_images = [x for x in inv['objects'] if x['page'] == selected[0]['page'] and x['kind'] == 'image']
            info = infos[next(i for i, x in enumerate(page_images) if x['id'] == selected[0]['id'])]
            a, b, c, d, _, _ = info['transform']
            if b or c or a <= 0 or d <= 0 or not info['xref']:
                raise ValueError('Ảnh xoay/lật/inline cần kiểm tra riêng')
            image = fitz.Pixmap(doc, info['xref'])
            masks = {x[0]: x[1] for x in page.get_images()}
            mask = masks.get(info['xref'])
            if not mask:
                raise ValueError('Ảnh nhúng chưa có nền trong suốt; cần tách nền và duyệt')
            if image.colorspace.n != 3:
                image = fitz.Pixmap(fitz.csRGB, image)
            image = fitz.Pixmap(image, fitz.Pixmap(doc, mask))
            # Trim only alpha noise <=1/255; never erase artwork by its color.
            import io
            rgba=Image.open(io.BytesIO(image.tobytes('png'))).convert('RGBA')
            alpha=rgba.getchannel('A').point(lambda v:0 if v<=1 else v)
            crop=alpha.getbbox()
            if not crop:raise ValueError('Ảnh không có artwork')
            if abs((source_width_cm/source_height_cm)/(rgba.width/rgba.height)-1)>.025:raise ValueError('Ảnh nguồn đã kéo méo; cần kiểm tra kích thước bố trí')
            source_width_cm*= (crop[2]-crop[0])/rgba.width;source_height_cm*= (crop[3]-crop[1])/rgba.height
            rgba.putalpha(alpha);rgba=rgba.crop(crop)
            box=fitz.Rect(0,0,rgba.width,rgba.height)
            out.close();out=fitz.open();canvas=out.new_page(width=box.width,height=box.height)
            buf=io.BytesIO();rgba.save(buf,format='PNG');canvas.insert_image(box,stream=buf.getvalue())
        else:
            raise ValueError('Cụm chữ sống/ảnh-vector trộn cần kiểm tra riêng để giữ đúng hình')
        if face.get('dimensions_basis')=='source_layout':face['width_cm']=source_width_cm;face['height_cm']=0
        if face.get('manual_height_cm') is not None:
            height=float(face['manual_height_cm'])
            if not math.isfinite(height) or not .1<=height<=160:raise ValueError('Chiều cao thủ công không hợp lệ')
            face['height_cm']=height;face['width_cm']=height*box.width/box.height
            face['dimensions_basis']='explicit_measurement'
        expected_height=face['width_cm']*box.height/box.width
        if not face['height_cm']:face['height_cm']=expected_height
        elif abs(face['height_cm']/expected_height-1)>.025:raise ValueError('Kích thước làm méo artwork sau trim alpha')
        face['before_height_cap_cm']=[face['width_cm'],face['height_cm']]
        face['width_cm'],face['height_cm']=hat_default_size(face,face['width_cm'],face['height_cm'])
        face['width_cm'],face['height_cm'],face['height_cap_scale']=capped_size(face['width_cm'],face['height_cm'],face.get('height_cap_cm'))
        if face['width_cm']*face['height_cm']*(300/2.54)**2>45_000_000:raise ValueError('Khổ PET vượt giới hạn')
        final = fitz.open()
        dest = final.new_page(width=face['width_cm'] * 72/2.54, height=face['height_cm'] * 72/2.54)
        dest.show_pdf_page(dest.rect, out, 0, clip=box, keep_proportion=True)
        pix = dest.get_pixmap(dpi=300, alpha=True, colorspace=fitz.csRGB)
        target = Path(target)
        im = Image.frombytes('RGBA', (pix.width, pix.height), pix.samples)
        # MuPDF alpha is premultiplied; PNG encoder in MuPDF correctly unpremultiplies.
        pix.save(target)
        with Image.open(target) as check:
            alpha = check.getchannel('A')
            lo, hi = alpha.getextrema()
            if lo != 0 or hi == 0:
                raise ValueError('Artwork thiếu vùng trong suốt hoặc không có mực')
        preview = target.with_suffix('.preview.png')
        with Image.open(target) as check:
            check.thumbnail((1200,1200))
            review=Image.new('RGB',(check.width*2,check.height),'white')
            for index,color in enumerate(('white','#303030')):
                bg=Image.new('RGBA',check.size,color);bg.alpha_composite(check.convert('RGBA'));review.paste(bg.convert('RGB'),(index*check.width,0))
            review.save(preview)
        final.close(); out.close()
    return {'name': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'pixels': [pix.width, pix.height], 'width_cm': face['width_cm'], 'height_cm': face['height_cm'], 'before_height_cap_cm':face['before_height_cap_cm'],'height_cap_scale':face['height_cap_scale']}
