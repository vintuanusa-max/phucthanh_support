import numpy as np,cv2,re
def source_palette(rgb):
    small=cv2.resize(rgb,(192,128),interpolation=cv2.INTER_AREA)
    lab=cv2.cvtColor(small,cv2.COLOR_RGB2LAB)
    cv2.setRNGSeed(12)
    _,ids,centers=cv2.kmeans(lab.reshape(-1,3).astype('float32'),12,None,(3,40,.2),3,cv2.KMEANS_PP_CENTERS)
    groups=[]
    for idx in np.argsort(-np.bincount(ids.ravel(),minlength=12)):
        c=centers[idx]
        if not any(np.linalg.norm((c-p)*[.68,1,1])<29 for p in groups):groups.append(c)
    cols=cv2.cvtColor(np.uint8([groups]),cv2.COLOR_LAB2RGB)[0]
    return ['#%02x%02x%02x'%tuple(c) for c in cols]
def locate(labels,texts,rgb):
    h,w=labels.shape
    rows=[]
    # Combine shades of embroidered light lettering before finding connected glyphs.
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    masks=[((hsv[:,:,2]>150)&(hsv[:,:,1]<105)).astype('uint8')]
    masks.extend((labels==color).astype('uint8') for color in np.unique(labels) if np.median(hsv[:,:,2][labels==color])<200)
    for color,mask in enumerate(masks):
        n,ids,stats,xy=cv2.connectedComponentsWithStats(mask)
        nodes=[(i,*stats[i,:4]) for i in range(1,n) if .006*w<stats[i,2]<.13*w and .014*h<stats[i,3]<.2*h and stats[i,4]>.00005*w*h and .07<stats[i,4]/(stats[i,2]*stats[i,3])<.98]
        rows.append((color,ids,sorted(nodes,key=lambda a:a[1]+a[3]/2)))
    used=set()
    results=[]
    for t in texts:
        chars=t['value'].replace(' ','');n=len(chars)
        x0,y0,x1,y1=t['box'];tx=(x0+x1)*w/2000;ty=(y0+y1)*h/2000;tw=(x1-x0)*w/1000
        best=None
        for col,ids,nodes in rows:
            for start,node in enumerate(nodes):
                chain=[node];pen=0
                for pos in range(start+1,len(nodes)):
                    if len(chain)==n:break
                    _,x,y,bw,bh=chain[-1];v=nodes[pos];i,X,Y,B,H=v
                    dx=X-x-bw;dy=(Y+H/2)-(y+bh/2)
                    if dx>max(bh*1.8,tw/max(n,1)*2.2):break
                    if dx<-.45*min(bw,B) or abs(dy)>max(bh,H)*.78 or not .52<H/bh<1.9:continue
                    if (col,i) in used:continue
                    chain.append(v);pen+=abs(np.log(H/bh))
                if len(chain)!=n or any((col,v[0]) in used for v in chain):continue
                xs=np.array([v[1]+v[3]/2 for v in chain]);ys=np.array([v[2]+v[4]/2 for v in chain])
                width=chain[-1][1]+chain[-1][3]-chain[0][1]
                if width<=0:continue
                score=(.7 if t["value"].isdigit() and col==0 else 0)+abs(xs.mean()-tx)/w*3+abs(ys.mean()-ty)/h*3+abs(np.log(width/max(tw,1)))*.4+pen/n*.3
                if n>3:score+=np.std(ys-np.polyval(np.polyfit(xs-xs.mean(),ys,2),xs-xs.mean()))/h*5
                if best is None or score<best[0]:best=(score,col,ids,chain)
        if best is None or best[0]>.68:continue
        _,col,ids,chain=best
        used.update((col,v[0]) for v in chain)
        mask=np.isin(ids,[v[0] for v in chain]).astype('uint8')
        xs=np.array([v[1]+v[3]/2 for v in chain]);ys=np.array([v[2]+v[4]/2 for v in chain])
        coef=np.polyfit(xs-xs.mean(),ys,2) if n>2 else [0,0,0]
        heights=[v[4] for v in chain];r=max(2,int(np.median(heights)*.09))
        inner=cv2.dilate(mask,np.ones((2*r+1,2*r+1),'uint8'));outer=cv2.dilate(inner,np.ones((7,7),'uint8'))
        bg=np.bincount(labels[(outer>0)&(inner==0)]).argmax()
        ink=np.bincount(labels[mask>0]).argmax()
        results.append((t,ink,bg,chain,coef,inner))
    return results
