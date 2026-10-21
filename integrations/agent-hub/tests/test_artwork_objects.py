import hashlib
import pytest
import pymupdf
from hub.artwork_objects import inventory, geometry


def test_physical_geometry_and_invalid_values():
    assert geometry([0,0,72,144])['width_cm']==2.54
    with pytest.raises(ValueError):geometry([0,0,float('nan'),10])


def test_mixed_objects_rotation_and_source_unchanged(tmp_path):
    path=tmp_path/'source.ai'
    doc=pymupdf.open();page=doc.new_page(width=300,height=400)
    page.insert_text((20,30),'Logo text')
    page.draw_rect(pymupdf.Rect(30,50,102,194))
    pix=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,4,4),False);pix.clear_with(128)
    page.insert_image(pymupdf.Rect(150,50,222,122),pixmap=pix)
    page.set_rotation(90);doc.save(path);doc.close()
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    result=inventory(path)
    assert {o['kind'] for o in result['objects']}=={'image','text','vector_path'}
    assert next(o for o in result['objects'] if o['kind']=='image')['width_cm']==2.54
    assert result['pages'][0]['rotation']==90
    assert not result['production_scale_verified'] and not result['execution_allowed']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    assert inventory(path,limit=1)['truncated']
