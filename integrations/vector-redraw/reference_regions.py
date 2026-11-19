import cv2
import numpy as np
from collections import Counter

def rgb(hexcolor):
    return tuple(bytes.fromhex(hexcolor[1:]))
def LAB(colors):
    return cv2.cvtColor(np.uint8([colors]),cv2.COLOR_RGB2LAB)[0].astype('float32')
def paths_from_mask(mask):
    rings,_=cv2.findContours(np.uint8(mask),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    result=[]
    for ring in rings:
        if abs(cv2.contourArea(ring))<9:continue
        pts=cv2.approxPolyDP(ring,1.05,True).reshape(-1,2)
        if len(pts)<3:continue
        mid=(pts+np.roll(pts,1,axis=0))/2
        result.append('M%.1f %.1f'%tuple(mid[0])+''.join('Q%d %d %.1f %.1f'%(*p,*mid[(i+1)%len(pts)]) for i,p in enumerate(pts))+'Z')
    return ''.join(result)
def ground(raw,plan):
    im=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
    im=cv2.cvtColor(cv2.medianBlur(im,5),cv2.COLOR_BGR2RGB)
    h,w=im.shape[:2];lab=cv2.cvtColor(im,cv2.COLOR_RGB2LAB).astype('float32')
    # Merge repeated shadow/highlight inks proposed by the model.
    votes=Counter(c.lower() for p in plan['paths'] for c in (p['fill'],p.get('stroke','none')) if c!='none')
    palette=[]
    for c,_ in votes.most_common():
        if all(np.linalg.norm(LAB([rgb(c)])[0]-LAB([rgb(v)])[0])>40 for v in palette):palette.append(c)
    if not palette:return plan
    edge=tuple(map(int,np.median(im[0],axis=0)));canvas='#%02x%02x%02x'%edge
    if canvas not in palette:palette.append(canvas)
    centers=LAB([rgb(c) for c in palette])
    labels=np.zeros((h,w),np.uint8);best=np.full((h,w),np.inf,np.float32)
    for i,c in enumerate(centers):
        delta=lab-c;delta[:,:,0]*=.85
        d=np.einsum('ijk,ijk->ij',delta,delta)
        labels[d<best]=i;np.minimum(best,d,out=best)
    labels=cv2.medianBlur(labels,5)
    def near(c):return int(np.argmin(np.linalg.norm(centers-LAB([rgb(c)])[0],axis=1)))
    for t in plan['texts']:
        ink=near(t['fill']);size=t['size'];span=t['width'];cx=t['x'];cy=t['y'];curve=t['curve']
        if size<8:continue
        mask=np.uint8(labels==ink)
        light=centers[ink,0]>182
        if light:mask=np.uint8((lab[:,:,0]>157)&(np.abs(lab[:,:,1]-128)<28)&(np.abs(lab[:,:,2]-128)<48))
        n,ids,stats,cent=cv2.connectedComponentsWithStats(mask)
        chosen=[]
        for i in range(1,n):
            x,y,b,hh,area=stats[i];mx,my=cent[i]
            u=2*(mx-cx)/max(span,1)
            if abs(u)>1.15 or abs(my-(cy+curve*u*u))>size*.64:continue
            if not .2*size<hh<1.55*size or b>max(1.6*size,span*.3) or area<max(4,.009*size**2):continue
            chosen.append(i)
        if not chosen:continue
        mask=np.uint8(np.isin(ids,chosen))
        r=max(2,round(size*.05))
        def dilate(m,r):return cv2.dilate(m,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*r+1,2*r+1)))
        a=dilate(mask,r);b=dilate(a,4);ring=labels[(b>0)&(a==0)]
        if not len(ring):continue
        bg=np.bincount(ring,minlength=len(palette));bg[ink]=0
        if bg.max()==0:continue
        labels[a>0]=bg.argmax()
        # Fit baseline and type scale when the full character sequence is measurable.
        nchar=sum(not c.isspace() for c in t['value'])
        if len(chosen)==nchar and nchar>=3:
            ix=sorted(chosen,key=lambda i:cent[i,0]);g=stats[ix];cx=(g[:,0].min()+(g[:,0]+g[:,2]).max())/2
            span=(g[:,0]+g[:,2]).max()-g[:,0].min()
            u=(cent[ix,0]-cx)*2/max(span,1);fit=np.polyfit(u,cent[ix,1],2)
            t.update(x=float(cx),width=float(span),y=float(fit[2]),curve=float(np.clip(fit[0],-size,size)),size=float(np.median(g[:,3])*1.26))
        if t.get('stroke')==t['fill']:t['stroke']='none'
    paths=[dict(d=f'M0 0H{w}V{h}H0Z',fill=canvas)]
    for i,c in enumerate(palette):
        if c==canvas:continue
        contour=paths_from_mask(cv2.GaussianBlur(np.uint8(labels==i)*255,(0,0),1.5)>115)
        if contour:paths.append(dict(d=contour,fill=c))
    return dict(plan,paths=paths)
