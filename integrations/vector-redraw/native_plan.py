from pathlib import Path
import json
import math
import re
from xml.etree.ElementTree import Element, SubElement, ElementTree

def number(value,limit=20000):
    n=float(value)
    if not math.isfinite(n) or abs(n)>limit: raise ValueError("Invalid vector coordinate")
    return round(n,3)

def color(value):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}|none",value): raise ValueError("Invalid fill or stroke")
    return value

def make_svg(plan,output):
    w,h=number(plan['width']),number(plan['height'])
    if min(w,h)<1 or max(w,h)>4096: raise ValueError("Invalid artboard")
    root=Element("svg",xmlns="http://www.w3.org/2000/svg",width=str(w),height=str(h),viewBox=f"0 0 {w} {h}")
    paths=plan['paths']
    if not 1<=len(paths)<=700: raise ValueError("Invalid artwork")
    for shape in paths:
        d=shape['d']
        if len(d)>2000000 or not re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz0-9eE.,+\s-]+',d): raise ValueError("Invalid path data")
        SubElement(root,"path",d=d,fill=color(shape["fill"]),stroke=color(shape.get("stroke","none")),attrib={'stroke-width':str(number(shape.get('strokeWidth',1))),'stroke-linecap':'round','stroke-linejoin':'round','fill-rule':'evenodd'})
    texts=plan['texts']
    if len(texts)>1000: raise ValueError("Too many text blocks")
    for t in texts:
        if not isinstance(t['value'],str) or not 1<=len(t['value'])<=500 or not 0<number(t['size'])<=2000 or not 0<number(t['width'])<=8192: raise ValueError("Invalid editable lettering")
        for k in ('x','y','curve'):number(t[k])
        color(t['fill'])
    ElementTree(root).write(output,encoding='utf-8',xml_declaration=True)
