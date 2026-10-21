"""Read-only PDF object inventory. Measurements describe file space, never print approval."""
import json
import math
import sys
from pathlib import Path


def geometry(bbox):
    box = [float(v) for v in bbox]
    if len(box) != 4 or not all(math.isfinite(v) for v in box):
        raise ValueError('Invalid object geometry')
    x0, y0, x1, y1 = box
    return {'bbox_pt': box, 'width_cm': round(abs(x1-x0)*2.54/72, 4),
            'height_cm': round(abs(y1-y0)*2.54/72, 4)}


def inventory(path, max_pages=4, limit=600):
    import pymupdf
    objects = []
    pages = []
    truncated = False
    with pymupdf.open(path) as doc:
        if not doc.is_pdf or doc.needs_pass:
            raise ValueError('Only unlocked PDF-compatible files are supported')
        for n in range(min(len(doc), max_pages)):
            page = doc[n]
            pages.append({'page': n+1, 'rotation': page.rotation,
                          'cropbox_pt': list(page.cropbox), 'mediabox_pt': list(page.mediabox)})
            entries = []
            for block in page.get_text('dict', flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)['blocks']:
                for line in block.get('lines', []):
                    for span in line.get('spans', []):
                        entries.append({'kind': 'text', **geometry(span['bbox']),
                                        'text': span['text'][:1000], 'font': span['font'],
                                        'font_size_pt': span['size'], 'direction': list(line['dir'])})
            for image in page.get_image_info():
                entries.append({'kind': 'image', **geometry(image['bbox']),
                                'pixel_width': image['width'], 'pixel_height': image['height'],
                                'transform': list(image['transform'])})
            drawings = page.get_drawings()
            # Each path can be part of an outlined letter/logo, not a complete semantic object.
            for drawing in drawings:
                entries.append({'kind': 'vector_path', **geometry(drawing['rect']),
                                'path_type': drawing['type'], 'segments': len(drawing['items'])})
            for i, item in enumerate(entries):
                if len(objects) >= limit:
                    truncated = True
                    break
                objects.append({'id': f'p{n+1}-o{i+1}', 'page': n+1, **item})
            pages[-1]['object_count_before_limit'] = len(entries)
        return {'schema_version': 1, 'objects': objects, 'pages': pages,
                'truncated': truncated or len(doc) > max_pages,
                'coordinate_system': 'unrotated PDF page, origin top-left, points; 72pt=2.54cm',
                'production_scale_verified': False, 'execution_allowed': False,
                'limitations': ['Bounds are in file space, not verified production dimensions.',
                    'Vector paths may be outlined letters or fragments; logo identity requires visual review.',
                    'Bounds are not guaranteed visible ink bounds after clipping, masks or transparency.',
                    'Native Illustrator layers and editability are not validated.']}


if __name__ == '__main__':
    # Separate process allows caller timeout without leaving the service parser stuck.
    result = inventory(Path(sys.argv[1]))
    print(json.dumps(result, ensure_ascii=False))
