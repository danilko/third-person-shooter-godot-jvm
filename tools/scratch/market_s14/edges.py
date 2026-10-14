import pickle,math,numpy as np
B=pickle.load(open('bands.pkl','rb'))
X=np.arange(200,800,1.0); Z=np.arange(640,1000,1.0)
XX,ZZ=np.meshgrid(X,Z)
masks={}
for o,_,p in B:
    if o.startswith('JCT'): continue
    m=masks.setdefault(o,np.zeros(XX.shape,bool)); yv=masks.setdefault(o+'#y',np.full(XX.shape,np.nan))
    for a,b in zip(p,p[1:]):
        ax,az,ay,ah=a; bx,bz,by,bh=b
        dx,dz=bx-ax,bz-az; L2=dx*dx+dz*dz+1e-9
        x0,x1=min(ax,bx)-12,max(ax,bx)+12; z0,z1=min(az,bz)-12,max(az,bz)+12
        sel=(XX>=x0)&(XX<=x1)&(ZZ>=z0)&(ZZ<=z1)
        t=np.clip(((XX[sel]-ax)*dx+(ZZ[sel]-az)*dz)/L2,0,1)
        d=np.hypot(XX[sel]-(ax+t*dx),ZZ[sel]-(az+t*dz))
        h=ah+t*(bh-ah); inside=d<=h
        idx=np.where(sel)
        m[idx[0][inside],idx[1][inside]]=True
        yv[idx[0][inside],idx[1][inside]]=(ay+t*(by-ay))[inside]+5.6
pickle.dump((X,Z,masks),open('masks.pkl','wb'))
for o in sorted(k for k in masks if not k.endswith('#y')):
    m=masks[o]; yv=masks[o+'#y']
    print('==',o)
    row=[]
    for x in range(250,781,10):
        i=int(x-200); col=np.where(m[:,i])[0]
        if len(col)==0: continue
        row.append('x%d z%.0f..%.0f y%.1f'%(x,Z[col.min()],Z[col.max()],np.nanmean(yv[col,i])))
    for k in range(0,len(row),5): print('   '+' | '.join(row[k:k+5]))
