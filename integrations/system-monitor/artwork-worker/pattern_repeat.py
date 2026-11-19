"""Read an unscaled, axis-aligned native PDF tiling period; never guess from pixels."""
import hashlib
import json
import math
import re

def periods(source):
    import pymupdf as fitz
    result = {}
    with fitz.open(source) as doc:
        for page in doc:
            typ, value = doc.xref_get_key(page.xref, 'Resources/Pattern')
            if typ == 'xref':
                value = doc.xref_object(int(value.split()[0]))
            refs = [int(x) for x in re.findall(r'(\d+)\s+0\s+R', value)]
            tiles = {}
            for x in refs:
                def number(key):
                    return float(doc.xref_get_key(x, key)[1])
                if number('PatternType') != 1:
                    raise ValueError('Non-tiling pattern needs review')
                matrix = [float(v) for v in re.findall(r'-?\d+(?:\.\d+)?', doc.xref_get_key(x, 'Matrix')[1])]
                if len(matrix) != 6 or any(abs(a-b)>1e-6 for a,b in zip(matrix[:4],[1,0,0,1])):
                    raise ValueError('Rotated/scaled PDF pattern needs native transform verification')
                w,h = number('XStep'),number('YStep')
                if not all(math.isfinite(v) and v>0 for v in (w,h)):
                    raise ValueError('Invalid pattern period')
                digest = hashlib.sha256(doc.xref_stream(x)).hexdigest()
                tiles[(digest,w,h)] = {'tile_sha256':digest,'width_pt':w,'height_pt':h,
                    'width_cm':w*2.54/72,'height_cm':h*2.54/72,'method':'native_pdf_tiling_identity_transform'}
            if len(tiles) == 1:
                result[page.number+1] = next(iter(tiles.values()))
    return result


def enrich(native, source):
    if hashlib.sha256(__import__('pathlib').Path(source).read_bytes()).hexdigest()!=native['source_sha256']:
        raise ValueError('Pattern/source hash mismatch')
    repeat=periods(source)
    for o in native['objects']:
        same={x['pattern'] for x in native['objects'] if x['page']==o['page']}
        if len(same)==1 and o['page'] in repeat:
            o['repeat']=repeat[o['page']]
    return native
