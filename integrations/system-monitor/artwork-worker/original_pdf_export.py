import base64,hashlib,shutil
from pathlib import Path
from PIL import Image

def export(job,src,folder):
 import pymupdf as f
 from fleet_paths import ascii_file_code
 Image.MAX_IMAGE_PIXELS=350_000_000
 plan=job['plan'];panels=[];previews=[];order_stem=ascii_file_code(plan['order_code'])
 is_ai=plan.get('source_kind')=='ai'
 native=None
 if is_ai:
  from original_ai_verify import verify
  native=verify(src,plan['panels'],folder)
 copy=folder/(order_stem+('_SOURCE.ai' if is_ai else '_SOURCE.pdf'));shutil.copyfile(src,copy)
 with f.open(src) as d:
  profiles={}
  non_cmyk_profiles=False
  for x in range(1,d.xref_length()):
   if d.xref_is_stream(x):
    n=d.xref_get_key(x,'N')[1]
    b=d.xref_stream(x)
    if len(b)>128 and b[36:40]==b'acsp':
     if n=='4':profiles[hashlib.sha256(b).hexdigest()]=b
     else:non_cmyk_profiles=True
  if len(profiles)>1:raise ValueError('Nhiều ICC CMYK; cần duyệt profile')
  if not profiles:
   if non_cmyk_profiles:raise ValueError('Nguồn PDF không phải CMYK thuần; cần duyệt profile')
   for page in d:
    for im in page.get_images(full=True):
     pix=f.Pixmap(d,im[0])
     if not pix.colorspace or pix.colorspace.n!=4:
      raise ValueError('Nguồn PDF không phải CMYK thuần; cần duyệt profile')
   icc=None
  else:
   icc=next(iter(profiles.values()))
  if len(d)!=len(plan['panels']):raise ValueError('Page count changed')
  for i,p in enumerate(plan['panels']):
   page=d[i];size=[page.rect.width*2.54/72,page.rect.height*2.54/72]
   if any(abs(a-b)>.001 for a,b in zip(size,p['output_cm'])):raise ValueError('Artboard changed')
   pixels=page.rect.width*page.rect.height*(300/72)**2
   if pixels>350_000_000:raise ValueError('Page too large')
   pix=page.get_pixmap(dpi=300,colorspace=f.csCMYK,alpha=False)
   name=order_stem+('' if len(d)==1 else '_'+p['name'])+'.jpg';out=folder/name
   save_kw={'quality':100,'subsampling':0,'dpi':(300,300)}
   if icc is not None:save_kw['icc_profile']=icc
   Image.frombytes('CMYK',(pix.width,pix.height),pix.samples).save(out,**save_kw)
   with Image.open(out) as im:
    if im.mode!='CMYK' or (icc is not None and im.info.get('icc_profile')!=icc) or (icc is None and im.info.get('icc_profile') is not None):raise ValueError('CMYK validation failed')
   scale=1000/max(page.rect.width,page.rect.height);preview=page.get_pixmap(matrix=f.Matrix(scale,scale),alpha=False).tobytes('png')
   (folder/(p['name']+'_preview.png')).write_bytes(preview)
   previews.append(dict(mime_type='image/png',data=base64.b64encode(preview).decode()))
   panels.append(dict(name=p['name'],size_cm=p['output_cm'],corner_marks=False,mode='CMYK',dpi=300,source_icc_preserved=bool(icc),untagged_source=icc is None,file=name,sha256=hashlib.sha256(out.read_bytes()).hexdigest()))
 return dict(report=dict(source_sha256=hashlib.sha256(Path(src).read_bytes()).hexdigest(),panels=panels,original_pdf_verified=True,native_ai_artboards=native,source_copy_file=copy.name,source_copy_sha256=hashlib.sha256(copy.read_bytes()).hexdigest(),icc_sha256=hashlib.sha256(icc).hexdigest() if icc else None,archive_relative=job['archive_relative']),previews=previews)
