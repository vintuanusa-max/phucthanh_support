"""Bounded, read-only raster/OOXML inputs; no Office automation or macro execution."""
import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree
from PIL import Image

EXTENSIONS = ('.pdf', '.ai', '.docx', '.xlsx', '.pptx', '.png', '.jpg', '.jpeg', '.webp', '.jxl')


def inspect_input(path, output, name, pdf_reader):
    suffix = Path(name).suffix.lower()
    if suffix in ('.pdf', '.ai'):
        return pdf_reader(path, output, name)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    media, texts, missing = [], [], []
    if suffix in ('.docx', '.xlsx', '.pptx'):
        prefix = {'.docx': 'word/', '.xlsx': 'xl/', '.pptx': 'ppt/'}[suffix]
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 3000 or sum(x.file_size for x in entries) > 80_000_000:
                raise ValueError('Office archive exceeds inspection limit')
            for entry in entries:
                if not entry.filename.startswith(prefix):
                    continue
                if '/media/' in entry.filename:
                    if len(media) >= 12:
                        missing.append('Còn ảnh Office chưa đọc do giới hạn 12 ảnh.')
                        continue
                    media.append((entry.filename, archive.read(entry)))
                elif entry.filename.endswith('.xml') and entry.file_size < 2_000_000 and sum(map(len, texts)) < 18000:
                    raw = archive.read(entry)
                    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                        raise ValueError('Unsupported XML declaration')
                    node = ElementTree.fromstring(raw)
                    texts.append(entry.filename + ': ' + ' '.join(x.text or '' for x in node.iter() if x.tag.rsplit('}', 1)[-1] in ('t', 'v'))[:4000])
        missing.append('Ảnh nhúng là ứng viên; chưa tái hiện bố cục Office, crop, quan hệ trang/slide và ảnh liên kết ngoài.')
    else:
        media = [(name, Path(path).read_bytes())]
    objects, previews = [], []
    for member, raw in media:
        try:
            with Image.open(io.BytesIO(raw)) as im:
                if im.width * im.height > 25_000_000:
                    raise ValueError('Image exceeds pixel limit')
                size = im.size
                im = im.convert('RGB')
                im.thumbnail((1400, 1400))
                target = output / ('input-' + str(len(objects)+1) + '.png')
                im.save(target)
            objects.append({'id': 'asset-' + str(len(objects)+1), 'kind': 'image', 'page': len(objects)+1,
                            'member': member, 'pixel_width': size[0], 'pixel_height': size[1],
                            'width_cm': None, 'height_cm': None})
            previews.append(str(target))
        except (OSError, ValueError, Image.DecompressionBombError):
            missing.append('Chưa đọc được ảnh nhúng: ' + member)
    return {'state': 'parsed' if objects else 'unsupported', 'reason': 'Không có ảnh đọc được; cần nhân viên kiểm tra.',
            'file_kind': suffix.lstrip('.'), 'text': '\n'.join(texts)[:18000], 'previews': previews,
            'object_inventory': {'objects': objects, 'truncated': bool(missing), 'production_scale_verified': False},
            'limitations': list(dict.fromkeys(missing + ['Pixel ảnh không xác định kích thước in thật.']))}
