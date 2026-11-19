"""Flat red/navy embroidered badge reconstruction from reference pixels."""
import cv2
import numpy as np
from geometry_redraw import outlines

def badge(raw,plan):
    lines={t['value'].strip().upper():t for t in plan['texts']}
    required=['WORKERS OVERALL','DENIM SUPPLY','999','DENIM FACTORY','SINCE 1985','QUALITY DENIM']
    if not all(k in lines for k in required):return None
    im=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR);h,w=im.shape[:2]
    hsv=cv2.cvtColor(cv2.medianBlur(im,9),cv2.COLOR_BGR2HSV)
    H,S,V=cv2.split(hsv)
    red=((H<12)|(H>168))&(S>110)
    navy=(H>90)&(H<155)&(V<164)
    if red.mean()<.12 or navy.mean()<.025:return None
    cream='#f5ead2';ruby='#bf1024';blue='#092b49';tan='#b69665'
    # Each band is a search window; the ink itself determines the baseline and span.
    zones=[(.32,.68,.195,.267,'sans',cream,ruby),(.19,.81,.262,.45,'slab',cream,ruby),
           (.405,.595,.49,.64,'serif',ruby,blue),(.225,.775,.64,.823,'slab',cream,ruby),
           (.42,.585,.811,.863,'sans',cream,ruby),(.375,.625,.858,.925,'sans',cream,blue)]
    texts=[]
    for phrase,(l,r,top,bottom,font,fill,back) in zip(required,zones):
        x0,x1=int(l*w),int(r*w);y0,y1=int(top*h),int(bottom*h)
        mask=red if phrase=='999' else (S<106)&(V>155)
        crop=np.uint8(mask[y0:y1,x0:x1])
        n,_,stats,_=cv2.connectedComponentsWithStats(crop)
        boxes=sorted([(x+x0,y+y0,b,a) for x,y,b,a,area in stats[1:] if a>.22*(y1-y0) and .003*w<b<.078*w and area>.000055*w*h],key=lambda v:v[0])
        chars=phrase.replace(' ','')
        if len(boxes)!=len(chars):
            # Fit type as one phrase when individual source letters touch.
            centers=[(x+b/2,y+a/2) for x,y,b,a in boxes]
        else:centers=[(x+b/2,y+a/2) for x,y,b,a in boxes]
        W=(x1-x0);cx=(x0+x1)/2
        if len(centers)>=3:
            xx,yy=np.array(centers).T
            fit=np.polyfit((xx-cx)/(W/2),yy,2)
            mid=float(np.polyval(fit,0));bend=float(np.clip(fit[0],-.65*(y1-y0),.65*(y1-y0)))
            height=float(np.median([v[3] for v in boxes]))
        else:mid=(y0+y1)/2;bend=0;height=(y1-y0)*.8
        # Stroke widths and tracking for this vintage badge layout.
        metrics=[(.346,.231,.019,.049),(.582,.315,.081,.109),(.173,.568,0,.140),(.514,.769,-.088,.090),(.155,.836,-.006,.037),(.241,.898,-.022,.035)]
        span,base_y,end_drop,em=metrics[len(texts)]
        # Remove connected components belonging to the source line rather than painting a strip.
        roi=((H<12)|(H>168))&(S>105) if phrase=="999" else S<115
        full=np.uint8(roi & (V>85))
        n,ids,boxes,_=cv2.connectedComponentsWithStats(full)
        for idx,(x,y,b,a,area) in enumerate(boxes[1:],1):
            xx=x+b/2;yy=y+a/2
            if not (x0-8<xx<x1+8 and y0-10<yy<y1+10 and b<.087*w and a<.15*h):continue
            baseline=base_y*h+end_drop*h*((xx-w/2)/(span*w/2))**2
            if abs(yy-baseline)>max(em*h*.77,12):continue
            rr=5 if phrase=="999" else 3
            xa=max(0,x-rr);ya=max(0,y-rr);xb=min(w,x+b+rr);yb=min(h,y+a+rr)
            local=cv2.dilate(np.uint8(ids[ya:yb,xa:xb]==idx),np.ones((2*rr+1,2*rr+1),'uint8'))>0
            red[ya:yb,xa:xb][local]=(back==ruby);navy[ya:yb,xa:xb][local]=(back==blue)
        texts.append(dict(value=phrase,x=w*.5,y=base_y*h,width=span*w,size=em*h,curve=end_drop*h,font=font,fill=fill,stroke=cream if phrase=='999' else 'none',arc=True))
    support=((S>43)|(V<211)).astype(np.uint8)
    outer=max(cv2.findContours(support,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0],key=cv2.contourArea)
    base=np.zeros_like(support);cv2.drawContours(base,[outer],-1,1,-1)
    def smooth(mask,k):
        return cv2.GaussianBlur(np.uint8(mask)*255,(0,0),k)>127
    base=smooth(base,5)
    inside=cv2.erode(np.uint8(base),cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(27,27)))>0
    paths=[dict(d=f'M0 0H{w}V{h}H0Z',fill='#ffffff')]
    for mask,col in [(base,tan),(inside,cream),(smooth(red,2),ruby),(smooth(navy,1.8),blue)]:
        paths.append(dict(d=''.join(outlines(mask)),fill=col))
    for fx in (.354,.649):
        cx,cy=fx*w,.861*h
        paths.append(dict(d=f'M{cx-19} {cy-17}h38v34h-38Z',fill=blue))
        pts=[(cx+np.sin(k*np.pi/5)*(16 if k%2==0 else 6)*w/1536,cy-np.cos(k*np.pi/5)*(16 if k%2==0 else 6)*h/1024) for k in range(10)]
        paths.append(dict(d='M'+'L'.join('%.2f %.2f'%pt for pt in pts)+'Z',fill=cream))
    return dict(width=w,height=h,paths=paths,texts=texts)
