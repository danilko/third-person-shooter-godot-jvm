# lay out arm + level bend + straight ramp as a polyline with heights; measure pier distances, deck clearances, apron take
from common import *
g=grid(); net=load()
PIERS={"sb_off":[(539.2,786.9),(569.8,780.7),(600.1,772.8),(628.9,760.5),(654.5,742.7),(675.9,719.8),(692.0,693.0),(706.2,632.5)],
"sb_on":[(646.6,784.2),(676.7,780.1),(707.5,780.5),(738.0,785.8)],
"main":[(527.5,801.8),(560.2,799.6),(592.4,793.8),(623.6,783.8),(652.9,769.3),(680.4,751.6),(705.0,730.0),(728.5,706.5)]}
DECK={n:[(p[0],p[1],p[2]) for p in gpts(net,n)] for n in ("shuto_sb_off","shuto_sb_on","shuto_wangan__3","shuto_wangan__4")}
HALF={"shuto_sb_off":4.5+1,"shuto_sb_on":4.5+1,"shuto_wangan__3":11.5,"shuto_wangan__4":11.5}
def segd(p,a,b):
    dx,dz=b[0]-a[0],b[1]-a[1]; t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dz)/(dx*dx+dz*dz))); q=(a[0]+dx*t,a[1]+dz*t)
    return math.hypot(p[0]-q[0],p[1]-q[1]),t
def layout(xc,mouth,R,dirx,grade,vc=10.0,drop=6.4,ytop=12.0):
    pts=[]  # (x,z,y,tag)
    z0=672+mouth
    for s in range(0,int(mouth)+1,2): pts.append((xc,672+s,ytop,"arm"))
    cx=xc+dirx*R
    for k in range(1,19):
        a=math.radians(k*5); pts.append((cx-dirx*R*math.cos(a), z0+R*math.sin(a), ytop,"bend"))
    xb=cx; zr=z0+R; L=drop/grade+vc
    n=int(L//2)
    for i in range(1,n+1):
        s=i*L/n
        # parabolic VCs of length vc at both ends
        if s<vc: y=ytop-grade*s*s/(2*vc)
        elif s>L-vc: y=ytop-drop+grade*(L-s)**2/(2*vc)
        else: y=ytop-grade*(s-vc/2)
        pts.append((xb+dirx*s,zr,y,"ramp"))
    return pts,zr,xb,xb+dirx*L
def report(name,pts,zr,x0,x1,half=3.75):
    print("--",name,": ramp centreline z %.1f, x %.1f -> %.1f (%.1f m), band z %.2f..%.2f, apron taken (toe z 712) %.1f m of 49"%(zr,x0,x1,abs(x1-x0),zr-half,zr+half,max(0,zr+half-712)))
    for grp,pl in PIERS.items():
        for p in pl:
            d=min(math.hypot(p[0]-q[0],p[1]-q[1]) for q in pts)
            if d<25: print("     pier %s %s: %.1f m %s"%(grp,p,d,"OK" if d>=7.65 else "FAIL <7.65"))
    for dn,dl in DECK.items():
        worst=None
        for q in pts:
            for a,b in zip(dl,dl[1:]):
                d,t=segd(q,a,b)
                if d<=HALF[dn]+half:
                    yd=a[2]+(b[2]-a[2])*t
                    if worst is None or yd-q[2]<worst[0]: worst=(yd-q[2],q,yd)
        if worst: print("     under %s: least surface-over-surface %.2f m at (%.1f,%.1f) road y %.2f deck y %.2f [%s]"%(dn,worst[0],worst[1][0],worst[1][1],worst[1][2],worst[2],worst[1][3]))
    # fill height under the ramp vs natural ground
    fills=[q[2]-H(g,q[0],q[1]) for q in pts if q[3]!="arm"]
    print("     fill over present ground: max %.1f m; ground under bend end %.1f"%(max(fills),H(g,pts[[q[3] for q in pts].index("ramp")][0],zr)))
for g_ in (0.07,0.08):
    print("==== grade %.0f %%  (length = 6.4/g + 10 m of vertical curve)"%(g_*100))
    for xc in (336,341):
        for m,R in ((26,20),(20.5,20),(20.5,15)):
            report("WEST T x %d mouth %.1f R %d east"%(xc,m,R),*layout(xc,m,R,+1,g_))
    for xc in (643,655,660,665):
        report("EAST new T x %d mouth 20.5 R20 west"%xc,*layout(xc,20.5,20,-1,g_))
    report("EAST reuse 567 (x 566) R20 WEST",*layout(566,20.4,20,-1,g_))
    report("EAST reuse 567 (x 566) R15 WEST",*layout(566,20.4,15,-1,g_))
    report("EAST reuse 567 (x 566) R20 EAST",*layout(566,20.4,20,+1,g_))
    report("EAST reuse 567 (x 566) R15 EAST",*layout(566,20.4,15,+1,g_))
# today's ichiba_michi
pts=gpts(net,"ichiba_michi"); print("ichiba_michi today:")
for a,b in zip(pts,pts[1:]): print("   (%.0f,%.0f)->(%.0f,%.0f) %.1f m grade %.1f %%"%(a[0],a[1],b[0],b[1],math.dist(a[:2],b[:2]),100*(a[2]-b[2])/math.dist(a[:2],b[:2])))
print("  corner turns",[round(t,1) for t in turns([p[:2] for p in pts])])
# dike road vs decks today
for dn,dl in DECK.items():
    for a,b in zip(dl,dl[1:]):
        if (a[1]-672)*(b[1]-672)<0:
            t=(672-a[1])/(b[1]-a[1]); print(dn,"crosses z672 at x %.1f deck y %.2f -> %.2f over the dike road (12.0)"%(a[0]+(b[0]-a[0])*t,a[2]+(b[2]-a[2])*t,a[2]+(b[2]-a[2])*t-12.0))
# east land: extent of 5.6 land at z 730 and piers standing on it
x=600
while H(g,x,730)>5: x+=1
print("land at z 730 runs east to x",x)
