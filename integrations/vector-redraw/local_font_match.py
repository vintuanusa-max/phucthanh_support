"""Match installed TrueType faces to visible source glyph silhouettes."""
from functools import lru_cache
from pathlib import Path
import struct
import cv2,numpy as np
from PIL import ImageFont

@lru_cache(maxsize=1)
def faces():
    fonts=[]
    for p in Path('C:/Windows/Fonts').iterdir():
        if p.suffix.lower() not in ('.otf','.ttf'):continue
        try:
            with p.open('rb') as f:
                header=f.read(12); entries=struct.unpack_from('>H',header,4)[0]
                directory=f.read(16*entries)
                record=next(struct.unpack_from('>4sIII',directory,j*16) for j in range(entries) if directory[j*16:j*16+4]==b'name')
                f.seek(record[2]); table=f.read(record[3])
                _,n,base=struct.unpack_from('>HHH',table)
                for j in range(n):
                    plat,enc,lang,key,length,start=struct.unpack_from('>6H',table,6+12*j)
                    if key==6 and plat in (0,3):
                        name=table[base+start:base+start+length].decode('utf-16be')
                        if name:fonts.append((name,str(p)));break
        except (ValueError,OSError,struct.error,StopIteration):continue
    return fonts

def shape(im):
    y,x=np.nonzero(im>32)
    if not len(x):return None
    crop=im[y.min():y.max()+1,x.min():x.max()+1]
    return cv2.resize(crop,(36,48),interpolation=cv2.INTER_AREA).astype('float32')/255

def features(mask):
    """Measure cap and foot bands separately from the body of the letter."""
    desc=[]
    for region in (mask[:10],mask[-10:],mask[10:-10]):
        desc.extend((region.mean(axis=0),region.mean(axis=1)))
    binary=np.uint8(mask>.5)
    distance=cv2.distanceTransform(np.pad(binary,1),cv2.DIST_L2,5)[1:-1,1:-1]
    thickness=np.percentile(distance[binary>0],[50,75,90])/12 if binary.any() else np.zeros(3)
    return np.concatenate(desc),thickness

@lru_cache(maxsize=18000)
def glyph(path,ch):
    try:
        ft=ImageFont.truetype(path,72);m=ft.getmask(ch,mode='L')
        raw=np.asarray(m,dtype=np.uint8).reshape(m.size[1],m.size[0])
        norm=shape(raw)
        if norm is None:return None
        x,y,X,Y=m.getbbox()
        return norm,*features(norm),(X-x)/max(1,Y-y)
    except (OSError,ValueError,cv2.error):return None

@lru_cache(maxsize=2048)
def serif_class(path):
    # PANOSE serif type from the OpenType OS/2 table, when supplied by the foundry.
    try:
        with open(path,'rb') as f:
            n=struct.unpack_from('>H',f.read(12),4)[0]
            for j in range(n):
                tag,_,offset,length=struct.unpack('>4sIII',f.read(16))
                if tag==b'OS/2' and length>=42:
                    f.seek(offset+32);pan=f.read(10)
                    return pan[1] if pan[0]==2 else 0
    except (OSError,struct.error):pass
    return 0

def identify(text,ids,selected,angles,style):
    samples={}
    for ch,idx,angle in zip(text,selected,angles):
        if not ch.isalnum():continue
        y,x=np.where(ids==idx)
        if not len(x):continue
        m=np.uint8(ids[y.min():y.max()+1,x.min():x.max()+1]==idx)*255
        m=cv2.copyMakeBorder(m,30,30,30,30,cv2.BORDER_CONSTANT)
        rot=cv2.getRotationMatrix2D((m.shape[1]/2,m.shape[0]/2),-float(angle),1)
        aligned=cv2.warpAffine(m,rot,(m.shape[1],m.shape[0]))
        s=shape(aligned)
        if s is not None:
            yy,xx=np.where(aligned>32)
            samples.setdefault(ch,[]).append((s,(np.ptp(xx)+1)/(np.ptp(yy)+1)))
    if not samples:return None
    evidence={}
    for ch,variants in samples.items():
        s=np.median([v[0] for v in variants],axis=0).astype('float32')
        evidence[ch]=(s,*features(s),np.median([v[1] for v in variants]))
    def score(face):
        scores=[];ratios=[]
        for ch,(src,edges,thick,aspect) in evidence.items():
            data=glyph(face[1],ch)
            if data is None:return 20.
            target,tedges,tthick,taspect=data
            # Compare endpoints at several depths: curved terminals recede much
            # faster than flat slab ends even if total glyph areas are similar.
            loss=np.abs(src-target)
            endpoint=.5*(loss[:9].mean()+loss[-9:].mean())
            scores.append(.35*loss.mean()+.8*endpoint+.5*np.abs(edges-tedges).mean()
                         +.42*np.abs(thick-tthick).mean()+.40*abs(src.mean()-target.mean()))
            ratios.append(np.log(taspect/aspect))
        sc=serif_class(face[1]);prior=0
        if style=='slab' and len(evidence)>=3:
            # Square/cove slabs; avoid rounded, tapered, or sans terminals.
            if sc in (5,6,7):prior=-.07
            elif sc in (8,9,10) or sc>=11:prior=.10
        return float(np.mean(scores)+.13*np.std(ratios)+.12*abs(np.median(ratios))+prior)
    ranking=sorted((score(face),face[0]) for face in faces())
    return ranking[0][1] if ranking else None
