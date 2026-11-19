"""Replace visible ink with editable Illustrator text, retaining original pixels as an embedded background."""
import base64,json,os,re,subprocess,tempfile
from pathlib import Path
import cv2,numpy as np
from vector_redraw_export import CANAVI_THREADS

def color(s):
    if not re.fullmatch('#[0-9a-fA-F]{6}',s):raise ValueError('Invalid ink color')
    return list(bytes.fromhex(s[1:]))
def clean(raw,plan):
    original=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_UNCHANGED)
    alpha=original[:,:,3] if original.ndim==3 and original.shape[2]==4 else None
    bgr=cv2.cvtColor(original,cv2.COLOR_GRAY2BGR) if original.ndim==2 else original[:,:,:3].copy()
    h,w=bgr.shape[:2];mask=np.zeros((h,w),np.uint8);lines=[]
    for line in plan['texts']:
        chars=''.join(line['source'].split());boxes=line['glyphs']
        if not chars or len(chars)!=len(boxes) or len(chars)>250:raise ValueError('Unreadable or incomplete glyph map: '+line['source'][:50])
        inks=[color(line['fill'])]
        if line.get('stroke','none')!='none':inks.append(color(line['stroke']))
        refs=cv2.cvtColor(np.uint8([inks+[color(line['background'])]]),cv2.COLOR_RGB2LAB)[0].astype('float32')
        from scipy.optimize import linear_sum_assignment
        smooth=cv2.cvtColor(cv2.medianBlur(bgr,3),cv2.COLOR_BGR2LAB).astype('float32')
        def distance(v):
            delta=smooth-v
            return np.einsum('ijk,ijk->ij',delta,delta)
        inkdist=distance(refs[0])
        for v in refs[1:-1]:np.minimum(inkdist,distance(v),out=inkdist)
        ink=np.uint8(inkdist<distance(refs[-1])*.80)
        if len(chars)==1:
            x,y,X,Y=map(int,boxes[0]);pad=3
            local=np.zeros_like(ink);local[max(0,y-pad):min(h,Y+pad),max(0,x-pad):min(w,X+pad)]=1
            region=cv2.dilate(ink*local,np.ones((3,3),np.uint8))
            if region.any():
                mask|=region;lines.append({**line,'bounds':[boxes[0]]});continue
        n,ids,stats,cent=cv2.connectedComponentsWithStats(ink)
        B=np.array(boxes,dtype=float);bw=np.maximum(1,B[:,2]-B[:,0]);bh=np.maximum(1,B[:,3]-B[:,1])
        candidates=[i for i in range(1,n) if .25*min(bw)<stats[i,2]<2.4*max(bw) and .42*min(bh)<stats[i,3]<1.9*max(bh) and stats[i,4]>.025*min(bh)*min(bw)]
        if len(candidates)<len(chars):raise ValueError("Insufficient glyph candidates: "+line['source'])
        st=stats[candidates];xy=cent[candidates]
        cost=((xy[None,:,0]-(B[:,0]+bw*.5)[:,None])/bw[:,None])**2+((xy[None,:,1]-(B[:,1]+bh*.5)[:,None])/bh[:,None])**2
        cost+=1.3*np.abs(np.log(st[None,:,3]/bh[:,None]))+.5*np.abs(np.log(st[None,:,2]/bw[:,None]))
        cost+=np.where((st[None,:,2]/np.maximum(1,st[None,:,3])>2.6)&(bw[:,None]/bh[:,None]<1.4),20,0)
        _,cols=linear_sum_assignment(cost)
        selected=sorted([candidates[i] for i in cols],key=lambda i:cent[i,0]) if np.all(np.diff(B[:,0])>=0) else [candidates[i] for i in cols]
        if cost[np.arange(len(cols)),cols].max()>15:raise ValueError("Uncertain lettering position: "+line['source'])
        region=np.uint8(np.isin(ids,selected))
        r=max(2,int(np.median(bh)*.035))
        region=cv2.dilate(region,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*r+1,2*r+1)))
        mask|=region
        bounds=[[x,y,x+ww,y+hh] for x,y,ww,hh,_ in stats[selected]]
        b=np.array(bounds,dtype=float)
        cx=(b[:,0]+b[:,2])/2;bottom=b[:,3];offset=cx.mean()
        fit=np.polyfit(cx-offset,bottom,min(len(cx)-1,2))
        smooth=np.polyval(fit,cx-offset)
        angles=-np.degrees(np.arctan(np.polyval(np.polyder(fit),cx-offset))) if len(cx)>1 else np.zeros(1)
        from local_font_match import identify
        font=identify(chars,ids,selected,angles,line.get("font","sans"))
        # Recover the baseline of an inclined glyph from its bottom bounding corner.
        adjusted=bottom-.5*(b[:,2]-b[:,0])*np.abs(np.sin(np.radians(angles)))
        fit=np.polyfit(cx-offset,adjusted,min(len(cx)-1,2))
        if len(cx)>=6:
            # Exclude punctuation or neighboring decorations mismatched near a line end.
            candidates=[]
            for skip in range(len(cx)):
                keep=np.arange(len(cx))!=skip
                model=np.polyfit(cx[keep]-offset,adjusted[keep],2)
                residual=np.abs(np.polyval(model,cx-offset)-adjusted)
                candidates.append((np.sort(residual)[:max(4,len(cx)-2)].mean(),model))
            fit=min(candidates,key=lambda entry:entry[0])[1]
        if len(cx)>=4 and np.percentile(adjusted,80)-np.percentile(adjusted,20)<np.median(b[:,3]-b[:,1])*.17:
            fit=np.array([0.,0.,np.median(adjusted)])
        left=float(b[:,0].min());right=float(b[:,2].max());width=right-left
        derivative=np.polyder(fit)
        def y(x):return float(np.polyval(fit,x-offset))
        def slope(x):return float(np.polyval(derivative,x-offset))
        curve=[[left,y(left)],[left+width/3,y(left)+slope(left)*width/3],
               [right-width/3,y(right)-slope(right)*width/3],[right,y(right)]]
        # Short, horizontal lines retain ordinary point type.
        curved=len(cx)>=3 and max(abs(slope(left)),abs(slope(right)))>.075
        from type_metrics import fit_type
        metrics=fit_type(line['source'],font,ids,selected,angles) if font else None
        lines.append({**line,'metrics':metrics,'bounds':b.tolist(),'matchedFont':font,'curvePath':curve if curved else None,
                      'baselines':smooth.tolist(),'angles':angles.clip(-45,45).tolist()})
    if not lines:raise ValueError('No editable text identified')
    result=cv2.inpaint(bgr,mask,5,cv2.INPAINT_TELEA);result[mask==0]=bgr[mask==0]
    if alpha is not None:result=np.dstack((result,alpha))
    return result,lines,mask

def export(raw,plan,root,group,thread,job,detail=None):
    root=Path(root).resolve(strict=True);customer=(root/group).resolve(strict=True)
    if customer.parent!=root or group!=customer.name or thread in CANAVI_THREADS or not thread or group.upper() in ('CANAVI','CANAVI HCM2') or not re.fullmatch(r'[\w-]{1,80}',job):raise ValueError('Invalid destination')
    dest=(customer/'DESIGNER').resolve()
    if dest.parent!=customer:raise ValueError('Invalid folder')
    dest.mkdir(exist_ok=True);ai=dest/('Mau-'+job+'.ai');png=ai.with_suffix('.png')
    if ai.exists() or png.exists():raise FileExistsError(job)
    result,lines,mask=clean(raw,plan)
    with tempfile.TemporaryDirectory(dir=dest) as tmp:
        p=Path(tmp);bg=p/'background.png';bg.write_bytes(cv2.imencode('.png',result)[1].tobytes())
        jsx=(Path(__file__).parent/'live_text_render.jsx').read_text(encoding='utf-8-sig')
        spec=dict(w=result.shape[1],h=result.shape[0],lines=lines,bg=bg.as_posix(),ai=(p/ai.name).as_posix(),png=(p/png.name).as_posix())
        if detail is not None:
            ref=p/'api-detail.png';ref.write_bytes(detail)
            spec['detail']=ref.as_posix()
        script=p/'render.jsx';script.write_text('var spec='+json.dumps(spec,ensure_ascii=True)+';\n'+jsx,encoding='utf8')
        cmd="$ErrorActionPreference='Stop';$a=New-Object -ComObject Illustrator.Application;$a.DoJavaScriptFile($env:PT_REDRAW_JSX)"
        subprocess.run(['powershell','-NoProfile','-Command',cmd],env={**os.environ,'PT_REDRAW_JSX':str(script)},creationflags=subprocess.CREATE_NO_WINDOW,check=True,timeout=180)
        for f in (ai,png):
            if not (p/f.name).stat().st_size:raise ValueError('Missing export')
        (p/ai.name).rename(ai)
        try:(p/png.name).rename(png)
        except OSError:ai.unlink();raise
    return ai,png
