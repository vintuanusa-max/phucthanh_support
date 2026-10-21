"""Read-only PDF-compatible artwork inspection using sandboxed Poppler subprocesses."""
import hashlib
import json
import sys
import re
import subprocess
from pathlib import Path

MAX_BYTES=32*1024*1024

def command(args,timeout=35):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    if p.returncode:raise ValueError('Document parser rejected input')
    return p.stdout.decode('utf-8',errors='replace')

def parse_info(text):
    pages=re.search(r'^Pages:\s+(\d+)',text,re.M)
    result={'page_count':int(pages.group(1)) if pages else None,'pdf_pages':[]}
    sizes=re.findall(r'^Page\s+(\d+)\s+size:\s*([\d.]+)\s+x\s+([\d.]+)\s+pts',text,re.M)
    if not sizes:
        one=re.search(r'^Page size:\s*([\d.]+)\s+x\s+([\d.]+)\s+pts',text,re.M)
        if one:sizes=[('1',*one.groups())]
    for page,w,h in sizes:
        result['pdf_pages'].append({'page':int(page),'width_cm':round(float(w)*2.54/72,4),'height_cm':round(float(h)*2.54/72,4)})
    result['boxes_text']='\n'.join(line for line in text.splitlines() if any(x in line for x in ['Box:',' rot:','Encrypted:','Page size:',' size:','Page rot:']))[:6000]
    return result

def inspect_document(path,output,name):
    path=Path(path);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if path.stat().st_size>MAX_BYTES:raise ValueError('File exceeds read limit')
    with path.open('rb') as f:header=f.read(1024)
    if not header.lstrip().startswith(b'%PDF-'):
        return {'state':'unsupported','reason':'AI không có phần PDF tương thích hoặc file không phải PDF; cần bản PDF tương thích để đối chiếu. Không chạy PostScript.','previews':[]}
    info=command(['pdfinfo','-box',str(path)])
    count=parse_info(info)['page_count']
    if not count or count>200:return {'state':'review','reason':'Số trang vượt giới hạn kiểm tra','previews':[]}
    last=min(count,4)
    detail=command(['pdfinfo','-f','1','-l',str(last),'-box',str(path)])
    text=command(['pdftotext','-f','1','-l',str(last),'-layout','-enc','UTF-8',str(path),'-'])[:18000]
    fonts=command(['pdffonts','-f','1','-l',str(last),str(path)])[:6000]
    command(['pdftoppm','-f','1','-l',str(last),'-scale-to','1400','-png',str(path),str(output/'page')],timeout=50)
    previews=[str(p) for p in sorted(output.glob('page-*.png'))[:last]]
    result=parse_info(detail)
    try:
        result['object_inventory']=json.loads(command([sys.executable,'-m','hub.artwork_objects',str(path)],timeout=45))
    except (ValueError,subprocess.TimeoutExpired):
        result['object_inventory']={'objects':[],'error':'Không hoàn tất đọc đối tượng; cần kiểm tra nội bộ.','production_scale_verified':False}
    result.update({'state':'parsed','file_kind':'pdf_compatible_ai' if name.lower().endswith('.ai') else 'pdf','page_count':count,'inspected_pages':last,'all_pages_inspected':count<=4,'text':text,'fonts_report':fonts,'previews':previews,
        'limitations':['Kích thước là trang/box PDF, chưa khẳng định artboard AI native.','Không xác minh layer, linked assets, font chỉnh sửa hoặc profile máy in.','Ảnh preview phục vụ đối chiếu, không phải file xuất in.']})
    return result
