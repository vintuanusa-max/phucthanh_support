"""Fit an already selected font to measured glyph ink and advances in source pixels."""
import cv2
import numpy as np
from PIL import ImageFont
from local_font_match import faces

def fit_type(source, selected_font, ids, selected, angles):
    path=dict(faces()).get(selected_font)
    if not path:return None
    face=ImageFont.truetype(path,128)
    measures=[]
    for ch,idx,angle in zip(source.replace(' ',''),selected,angles):
        y,x=np.where(ids==idx)
        if not len(x):return None
        patch=np.uint8(ids[y.min():y.max()+1,x.min():x.max()+1]==idx)*255
        border=max(patch.shape)
        patch=cv2.copyMakeBorder(patch,border,border,border,border,cv2.BORDER_CONSTANT)
        rot=cv2.getRotationMatrix2D((patch.shape[1]/2,patch.shape[0]/2),-float(angle),1)
        patch=cv2.warpAffine(patch,rot,(patch.shape[1],patch.shape[0]))
        xx,yy,bw,bh=cv2.boundingRect(np.uint8(patch>102))
        mask=face.getmask(ch,'L');glyph=np.array(mask,dtype=np.uint8).reshape(mask.size[::-1])
        gx,gy,gw,gh=cv2.boundingRect(np.uint8(glyph>102))
        if not min(bw,bh,gw,gh):return None
        ref=patch[yy:yy+bh,xx:xx+bw]/255.
        rendered=cv2.resize(glyph[gy:gy+gh,gx:gx+gw],(bw,bh),interpolation=cv2.INTER_AREA)/255.
        rings,_=cv2.findContours(np.pad(np.uint8(rendered>.5),1),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        perimeter=sum(cv2.arcLength(r,True) for r in rings)
        measures.append((bw,bh,gw,gh,(ref.sum()-rendered.sum())/max(1,perimeter),x.mean(),y.mean(),ch))
    a=np.array([m[:7] for m in measures]);size=float(np.median(a[:,1]/a[:,3])*128)
    scales=np.clip(100*a[:,0]/(a[:,2]*size/128),48,185)
    # A median suppresses an isolated misclassified glyph or thread glint.
    scale=float(np.median(scales));scales=np.clip(.75*scales+.25*scale,scale*.78,scale*1.24)
    off=float(np.clip(np.median(a[:,4]),-size*.025,size*.012))
    if abs(off)<.15:off=0.
    gaps=[]
    indices=[i for i,ch in enumerate(source) if not ch.isspace()]
    for k in range(len(measures)-1):
        m,n=measures[k:k+2]; segment=source[indices[k]:indices[k+1]]
        step=np.hypot(n[5]-m[5],n[6]-m[6])
        advance=face.getlength(segment)*size/128*scales[k]/100
        left=face.getbbox(m[7])[0]*size/128*scales[k]/100
        nextleft=face.getbbox(n[7])[0]*size/128*scales[k+1]/100
        predicted=advance+nextleft-left+(n[0]-m[0])/2
        gaps.append(float(np.clip((step-predicted)*1000/size/max(.48,scales[k]/100),-130,240)))
    return dict(size=size,scale=scale,scales=scales.tolist(),tracking=gaps,offset=off)
