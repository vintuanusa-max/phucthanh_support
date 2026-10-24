"""Owner-approved AN NGUYEN original PDF artboards, internal review only."""
import re,unicodedata
from pathlib import PurePosixPath
THREAD='g5402324928935037742'
def filename(name):
 name=PurePosixPath(name.replace('\\','/')).stem
 name=re.sub(r'^[a-f0-9]{12}__','',name)
 name=''.join(c for c in unicodedata.normalize('NFD',name) if not unicodedata.combining(c)).replace('đ','d').replace('Đ','D')
 name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name).strip(' .')
 if not name or len(name)>180:raise ValueError('Invalid source filename')
 if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:name='FILE_'+name
 return name

def plan(source,payload,comparison):
 import pymupdf as f
 from hub.export_routing import original_jpg_allowed
 if not original_jpg_allowed(comparison):raise ValueError('Chưa có bằng chứng chuyển nhiệt và artwork đúng mẫu')
 is_ai=payload['asset']['name'].lower().endswith('.ai')
 if not payload['asset']['name'].lower().endswith(('.pdf','.ai')):raise ValueError('Cần PDF hoặc AI')
 if is_ai and not __import__('pathlib').Path(source).read_bytes().startswith(b'%PDF-'):raise ValueError('AI chưa có PDF-compatible; cần lưu lại từ Illustrator để đối chiếu artwork')
 if comparison.get('file_role')!='artwork' or comparison.get('same_design')!='proposed':raise ValueError('Chưa xác định PDF là artwork đúng mẫu')
 if any(x.get('kind')=='conflict' for x in comparison.get('findings',[])):raise ValueError('Nguồn mâu thuẫn: cần kiểm tra trước xuất')
 with f.open(source) as d:
  if d.needs_pass or not 1<=len(d)<=8:raise ValueError('PDF khóa hoặc số trang vượt giới hạn')
  panels=[]
  for n,page in enumerate(d):
   w,h=page.rect.width,page.rect.height
   if min(w,h)<=0 or w*h*(300/72)**2>350_000_000:raise ValueError('Khổ PDF vượt giới hạn xuất')
   panels.append(dict(name='page_'+str(n+1),output_cm=[w*2.54/72,h*2.54/72],corner_marks=False))
 return dict(renderer='original_pdf_v1',order_code=filename(payload['asset']['name']),panels=panels,source_kind='ai' if is_ai else 'pdf')
