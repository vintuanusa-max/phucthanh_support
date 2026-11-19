"""Auto white ink, RGB/CMYK. Standalone manual tool and pure worker helper.

No Hub, ERP, queue or network access. All manual exports use a new directory.
"""
import io
import json
import hashlib
import sys
from pathlib import Path
from PIL import Image, ImageCms, ImageChops, ImageFilter, ImageOps

POLICY = 'adaptive-rgb-cmyk-white100-black40-v4'

def dependencies():
    vendor = Path.home() / 'AppData/Local/PhucThanh/ArtworkInspector/spot-deps'
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))

def legacy_geometry(alpha, white):
    padded = ImageOps.expand(alpha, border=1, fill=0)
    eroded = padded.filter(ImageFilter.MinFilter(3)).crop((1,1,alpha.width+1,alpha.height+1))
    return ImageChops.lighter(ImageChops.multiply(white,alpha), eroded)

def geometry(alpha, white):
    # Adaptive local choke; artwork colors and source alpha are unchanged.
    # Opening removes 1-2px features from the broad-region map, not the output.
    def morph(image, radius, opening=False):
        p=ImageOps.expand(image,border=radius,fill=0)
        p=p.filter(ImageFilter.MinFilter(radius*2+1))
        if opening:p=p.filter(ImageFilter.MaxFilter(radius*2+1))
        return p.crop((radius,radius,alpha.width+radius,alpha.height+radius))
    binary=alpha.point(lambda v:255 if v>=16 else 0)
    opened3=morph(binary,1,True)
    broad=morph(binary,2,True)
    weight=broad.filter(ImageFilter.GaussianBlur(1.5))
    eroded=morph(alpha,1)
    blended=Image.composite(eroded,alpha,weight)
    # Restore thin strokes even when attached to a larger shape.
    thin=ImageChops.multiply(alpha,ImageOps.invert(opened3))
    result=ImageChops.lighter(blended,thin)
    result=ImageChops.lighter(result,ImageChops.multiply(white,alpha))
    return ImageChops.darker(result,alpha)

def rgb_coverage(image, adaptive=True):
    """Owner-approved density; adaptive choke, with v3 verification support."""
    rgba=image.convert('RGBA');r,g,b,alpha=rgba.split()
    white=ImageChops.darker(ImageChops.darker(r,g),b).point(lambda v:255 if v>=250 else 0)
    dose=rgba.convert('RGB').convert('L').point(lambda v:102+round(153*v/255))
    return ImageChops.multiply((geometry if adaptive else legacy_geometry)(alpha,white),ImageChops.lighter(dose,white))

def cmyk_coverage(cmyk, alpha, icc=None):
    """Read actual CMYK separations; no conversion of original artwork."""
    dependencies()
    import numpy as np
    fallback=Path(r'C:\Windows\System32\spool\drivers\color\USWebCoatedSWOP.icc')
    dst=ImageCms.ImageCmsProfile(io.BytesIO(icc)) if icc else ImageCms.getOpenProfile(str(fallback))
    transform=ImageCms.buildTransformFromOpenProfiles(ImageCms.createProfile('sRGB'),dst,'RGB','CMYK',renderingIntent=1)
    black=ImageCms.applyTransform(Image.new('RGB',(1,1),(0,0,0)),transform).getpixel((0,0))
    reference=sum(black)
    if reference<=0:raise ValueError('Invalid CMYK black reference')
    total=np.asarray(cmyk,dtype=np.float32).sum(axis=2)
    dose=Image.fromarray(np.rint(255*(1-.6*np.minimum(total/reference,1))).astype('uint8'))
    white=Image.fromarray(np.where(np.asarray(cmyk).max(axis=2)<=5,255,0).astype('uint8'))
    mask=ImageChops.multiply(geometry(Image.fromarray(alpha),white),ImageChops.lighter(dose,white))
    return mask,{'basis':'actual C+M+Y+K / profile black total','profile':ImageCms.getProfileDescription(dst).strip(),'profile_source':'embedded' if icc else str(fallback),'black_CMYK_8bit':black,'black_total_percent':reference/255*100}

def read_source(path):
    dependencies()
    import numpy as np
    import tifffile
    path=Path(path)
    if path.suffix.lower()=='.png':
        with Image.open(path) as image:
            size=image.size;dpi=image.info.get('dpi',(72,72))
            rgba=np.asarray(image.convert('RGBA'))
            return {'mode':'RGB','base':rgba[:,:,:3],'alpha':rgba[:,:,3],'icc':image.info.get('icc_profile'),'size':size,'dpi':dpi,'mask':rgb_coverage(image),'meta':{'basis':'RGB luma 0.299R+0.587G+0.114B'}}
    with tifffile.TiffFile(path) as file:
        page=file.pages[0];raw=page.asarray()
        def resolution(tag):
            value=page.tags.get(tag)
            if not value:return 72.0
            num,den=value.value
            return num/den
        factor=2.54 if int(page.tags.get('ResolutionUnit').value if page.tags.get('ResolutionUnit') else 2)==3 else 1
        dpi=(resolution('XResolution')*factor,resolution('YResolution')*factor)
        if page.planarconfig==2:raw=np.moveaxis(raw,0,-1)
        if raw.dtype!=np.uint8:raise ValueError('Ban nay ho tro TIFF 8 bit/channel; khong tu doi 16/32 bit.')
        photo=int(page.photometric)
        if photo not in (2,5):raise ValueError('Can TIFF RGB hoac CMYK.')
        n=3 if photo==2 else 4;mode='RGB' if n==3 else 'CMYK'
        if raw.ndim!=3 or raw.shape[2]<n:raise ValueError('Invalid TIFF channels')
        alpha=np.full(raw.shape[:2],255,dtype='uint8');associated=False
        for i,kind in enumerate(page.extrasamples):
            if int(kind) in (1,2):
                alpha=raw[:,:,n+i];associated=int(kind)==1;break
        base=raw[:,:,:n].copy()
        if associated:
            base=np.rint(np.clip(base.astype(float)*255/np.maximum(alpha[:,:,None],1),0,255)).astype('uint8')
        tag=page.tags.get(34675);icc=tag.value if tag else None
        # No spot channel is used as artwork or mistaken for transparency.
        if mode=='RGB':
            rgba=Image.fromarray(np.dstack([base,alpha]))
            mask=rgb_coverage(rgba);meta={'basis':'RGB luma 0.299R+0.587G+0.114B'}
        else:mask,meta=cmyk_coverage(base,alpha,icc)
        return {'mode':mode,'base':base,'alpha':alpha,'icc':icc,'size':(raw.shape[1],raw.shape[0]),'dpi':dpi,'mask':mask,'meta':meta}

JSX=r'''(function(){
var c=__CONFIG__,old=app.displayDialogs,prev=app.documents.length?app.activeDocument:null,d=null,m=null;
try{
 app.displayDialogs=DialogModes.NO;
 var target=new File(c.output);if(target.exists)throw new Error('Output already exists');
 d=app.open(new File(c.source));
 var w=d.width.as('px'),h=d.height.as('px'),dpi=d.resolution,mode=d.mode;
 if(mode!=DocumentMode.RGB && mode!=DocumentMode.CMYK)throw new Error('RGB/CMYK only');
 if(d.bitsPerChannel!=BitsPerChannelType.EIGHT)throw new Error('8 bit/channel only');
 m=app.open(new File(c.mask));var spot=m.channels[0].duplicate(d);m.close(SaveOptions.DONOTSAVECHANGES);m=null;
 app.activeDocument=d;
 for(var i=d.channels.length-1;i>=0;i--){if(d.channels[i].name=='spot_1')d.channels[i].remove();}
 spot.name='spot_1';spot.kind=ChannelType.SPOTCOLOR;
 var color=new SolidColor();color.rgb.red=255;color.rgb.green=255;color.rgb.blue=255;
 spot.color=color;spot.opacity=100;
 var opt=new TiffSaveOptions();opt.transparency=true;opt.alphaChannels=true;opt.spotColors=true;opt.layers=false;opt.embedColorProfile=true;opt.imageCompression=TIFFEncoding.TIFFLZW;
 d.saveAs(target,opt,true,Extension.LOWERCASE);d.close(SaveOptions.DONOTSAVECHANGES);d=null;
 if(!target.exists){var alt=new File(c.output.replace(/\.tiff$/,'.tif'));if(alt.exists)alt.rename(target.name);}
 d=app.open(target);
 if(d.mode!=mode||d.width.as('px')!=w||d.height.as('px')!=h||Math.abs(d.resolution-dpi)>.01)throw new Error('Mode/size/DPI changed');
 var found=false;for(var j=0;j<d.channels.length;j++){if(d.channels[j].name=='spot_1'&&d.channels[j].kind==ChannelType.SPOTCOLOR)found=true;}
 if(!found)throw new Error('Missing spot_1');
 return 'verified';
}finally{
 if(m)m.close(SaveOptions.DONOTSAVECHANGES);if(d)d.close(SaveOptions.DONOTSAVECHANGES);
 app.displayDialogs=old;if(prev){try{app.activeDocument=prev;}catch(e){}}
}
})()'''

def export(source, output_dir):
    import subprocess
    dependencies()
    import numpy as np
    import tifffile
    source=Path(source).resolve();folder=Path(output_dir).resolve()
    data=read_source(source)
    folder.mkdir(parents=True,exist_ok=False)
    output=folder/(source.stem+'_WHITE_AUTO_'+data['mode']+'.tiff')
    mask=folder/'white-mask.png';ImageOps.invert(data['mask']).save(mask,dpi=data['dpi'])
    config={'source':str(source),'mask':str(mask),'output':str(output)}
    script=folder/'export.jsx';script.write_text(JSX.replace('__CONFIG__',json.dumps(config)),encoding='utf-8')
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    command="$ErrorActionPreference='Stop'; $app=New-Object -ComObject Photoshop.Application; $app.DoJavaScript([IO.File]::ReadAllText((Join-Path (Get-Location) 'export.jsx')))"
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],cwd=folder,capture_output=True,timeout=360)
    if result.returncode or result.stdout.decode(errors='replace').strip()!='verified':
        raise RuntimeError('Photoshop export failed: '+(result.stderr or result.stdout).decode(errors='replace')[-1500:])
    # Validate mask from TIFF channel data, not a composite preview.
    with tifffile.TiffFile(output) as tf:
        page=tf.pages[0];raw=page.asarray()
        if page.planarconfig==2:raw=np.moveaxis(raw,0,-1)
        n=3 if data['mode']=='RGB' else 4
        expected_photo=2 if n==3 else 5
        if int(page.photometric)!=expected_photo:raise ValueError('Color mode changed')
        # Photoshop writes transparency before spot channels. Locate spot_1 by
        # matching Photoshop resource channel names, rather than assuming last
        # channel when the input already contains other extra channels.
        names=[];resources=page.tags.get(34377)
        if resources:
            import struct
            blob=resources.value;pos=0
            while pos+12<=len(blob):
                if blob[pos:pos+4]!=b'8BIM':break
                rid=int.from_bytes(blob[pos+4:pos+6],'big');pos+=6
                length=blob[pos];pos+=1+length
                if (1+length)%2:pos+=1
                count=int.from_bytes(blob[pos:pos+4],'big');pos+=4
                body=blob[pos:pos+count];pos+=count+(count%2)
                if rid==1006:
                    at=0
                    while at<len(body):
                        length=body[at];at+=1;names.append(body[at:at+length].decode('latin1'));at+=length
        alpha=np.full(raw.shape[:2],255,dtype='uint8');associated=False
        extras=list(page.extrasamples)
        for i,kind in enumerate(extras):
            if int(kind) in (1,2):alpha=raw[:,:,n+i];associated=int(kind)==1;break
        # Alpha names resource may omit TIFF's transparency channel.
        unnamed_alpha=sum(int(k) in (1,2) for k in extras)
        offset=len(extras)-len(names)
        if 'spot_1' not in names or offset not in (0,unnamed_alpha):raise ValueError('Cannot identify spot_1 in saved TIFF')
        idx=n+offset+names.index('spot_1')
        if not np.array_equal(255-raw[:,:,idx],np.asarray(data['mask'])):raise ValueError('White mask differs')
        if not np.array_equal(alpha,data['alpha']):raise ValueError('Transparency differs')
        expected=data['base'].astype(float)
        if associated:expected=expected*alpha[:,:,None]/255
        visible=alpha>0
        delta=np.abs(raw[:,:,:n].astype(float)-np.rint(expected))
        if delta[visible].max(initial=0)>1:raise ValueError('Artwork colors changed')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=before:raise ValueError('Source changed')
    report={'policy':POLICY,'mode':data['mode'],**data['meta'],'source':str(source),'source_sha256':before,'output':str(output),'solidity':100,'alpha_verified':True,'spot_verified':True,'color_verified':True,'white_contract_px':0,'color_contract_px':'adaptive 0..1','thin_features':'preserve 1-2px','transition_blur_px':1.5}
    (folder/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return output

def main():
    import tkinter as tk
    from tkinter import filedialog,messagebox
    from datetime import datetime
    root=tk.Tk();root.withdraw()
    try:
        source=filedialog.askopenfilename(title='Chon TIFF/PNG — tu nhan RGB hoac CMYK',filetypes=[('TIFF / PNG','*.tif *.tiff *.png')])
        if not source:return
        dependencies()
        folder=Path(source).parent/('WHITE_AUTO_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        output=export(source,folder)
        messagebox.showinfo('Da xuat va kiem tra',str(output))
    except Exception as exc:
        messagebox.showerror('Khong hoan tat',str(exc));raise
    finally:root.destroy()

if __name__=='__main__':main()
