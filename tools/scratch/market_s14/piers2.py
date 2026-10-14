import json,struct,sys,math,glob
import numpy as np
BOX=(240,720,700,960)
def load(f):
    g=json.load(open(f)); b=open(f[:-5]+'.bin','rb').read()
    def acc(i):
        a=g['accessors'][i]; bv=g['bufferViews'][a['bufferView']]
        off=bv.get('byteOffset',0)+a.get('byteOffset',0)
        n=a['count']; comp={5126:('f',4),5125:('I',4),5123:('H',2)}[a['componentType']]
        k={'VEC3':3,'SCALAR':1,'VEC2':2,'VEC4':4}[a['type']]
        stride=bv.get('byteStride',0)
        assert not stride or stride==comp[1]*k
        return np.frombuffer(b,dtype=comp[0],count=n*k,offset=off).reshape(n,k) if k>1 else np.frombuffer(b,dtype=comp[0],count=n,offset=off)
    return g,acc
out=[]
for f in sys.argv[1:]:
    g,acc=load(f)
    mats=[m['name'] for m in g['materials']]
    for n in g['nodes']:
        nm=n.get('name','')
        if 'mesh' not in n or 'colonly' in nm or nm.startswith('mmesh'): continue
        if not nm.endswith('__surface'): continue
        t=np.array(n.get('translation',[0,0,0]))
        for p in g['meshes'][n['mesh']]['primitives']:
            if mats[p['material']]!='M_Concrete': continue
            P=acc(p['attributes']['POSITION'])+t
            I=acc(p['indices']).reshape(-1,3).astype(int)
            A,B,C=P[I[:,0]],P[I[:,1]],P[I[:,2]]
            cen=(A+B+C)/3
            m=(cen[:,0]>BOX[0])&(cen[:,0]<BOX[1])&(cen[:,2]>BOX[2])&(cen[:,2]<BOX[3])
            A,B,C,cen=A[m],B[m],C[m],cen[m]
            nrm=np.cross(B-A,C-A); L=np.linalg.norm(nrm,axis=1)+1e-12
            ext=np.maximum.reduce([A[:,1],B[:,1],C[:,1]])-np.minimum.reduce([A[:,1],B[:,1],C[:,1]])
            ok=(np.abs(nrm[:,1])/L<0.2)&(ext>2.5)
            for a_,b_,c_ in zip(A[ok],B[ok],C[ok]):
                out.append((nm,a_,b_,c_))
print(len(out),'tall vertical concrete tris')
# cluster
pts=np.array([ (np.vstack([a,b,c])[:,0].mean(), np.vstack([a,b,c])[:,2].mean(), min(a[1],b[1],c[1]), max(a[1],b[1],c[1])) for _,a,b,c in out])
used=np.zeros(len(pts),bool); cl=[]
for i in range(len(pts)):
    if used[i]: continue
    grp=[i]; used[i]=True; q=[i]
    while q:
        j=q.pop()
        d=np.hypot(pts[:,0]-pts[j,0],pts[:,1]-pts[j,1])
        for k in np.where((d<2.5)&~used)[0]:
            used[k]=True; grp.append(k); q.append(k)
    G=pts[grp]
    cl.append((G[:,0].mean(),G[:,1].mean(),G[:,2].min(),G[:,3].max(),len(grp),np.ptp(G[:,0]),np.ptp(G[:,1])))
for c in sorted(cl): print('x %7.1f z %7.1f  y %5.1f..%5.1f  n=%d  span %.1f x %.1f'%c)
