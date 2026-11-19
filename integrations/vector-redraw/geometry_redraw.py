"""Validate model artwork against the source canvas before Illustrator rendering."""
import io
from PIL import Image

def reconstruct(raw,plan):
    width,height=Image.open(io.BytesIO(raw)).size
    if (plan.get("width"),plan.get("height"))!=(width,height):
        raise ValueError("Artwork dimensions do not match the reference")
    if not isinstance(plan.get("paths"),list) or not plan["paths"]:
        raise ValueError("Missing vector artwork")
    for text in plan["texts"]:
        text["arc"]=True
        text.setdefault("curve",0)
        text.setdefault("stroke","none")
    from reference_regions import ground
    return ground(raw,plan)
