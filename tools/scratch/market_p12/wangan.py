from common import *
import island_plan as PL, island_expressway as EX
from island_roadgen import rounded_polygon, arclen, at_s
g=grid(); net=load()
def build(main,rad): 
    cl=rounded_polygon(main,rad,closed=False,full_ends=True,arc_step=1.0); return cl
def zat(cl,x):
    for i in range(len(cl)-1):
        if (cl[i][0]-x)*(cl[i+1][0]-x)<=0 and cl[i][0]>250 and cl[i+1][0]!=cl[i][0]:
            a,b=cl[i],cl[i+1]; f=(x-a[0])/(b[0]-a[0]); return -(a[1]+f*(b[1]-a[1])), math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))
def dist_to(cl,p):
    return min(math.hypot(p[0]-q[0],-p[1]-q[1]) for q in cl)
M0=PL.WG_MAIN[1:]; R0=[0.0]+PL.WG_MAIN_R[1:]
cl0=build(M0,R0)
print("== every wangan station vs the DESIGN alignment (distance > 0.5 m listed)")
for n in sorted(net.roads):
    if n.startswith("shuto_wangan"):
        for p in gpts(net,n):
            d=dist_to(cl0,p)
            if d>0.5: print("   %s (%.1f,%.1f) is %.1f m off the design line"%(n,p[0],p[1],d))
def arcs(cl):
    out=[];cur=None
    for i in range(1,len(cl)-1):
        t=turns([(cl[i-1][0],-cl[i-1][1]),(cl[i][0],-cl[i][1]),(cl[i+1][0],-cl[i+1][1])])[0]
        if abs(t)>0.05 and 250<cl[i][0]<760:
            if cur is None: cur=[cl[i],cl[i],t]
            cur[1]=cl[i]
        elif cur: out.append(cur); cur=None
    return [("%s arc x %.0f..%.0f (z %.0f..%.0f)"%("L" if c[2]<0 else "R",c[0][0],c[1][0],-c[0][1],-c[1][1])) for c in out]
HALF=11.5
def show(label,main,rad):
    cl=build(main,rad); print("==",label); print("   ",arcs(cl))
    row=[]
    for x in (400,450,500,540,580,620,640,680,705):
        z,h=zat(cl,x); z0,h0=zat(cl0,x)
        row.append("x%d z%.0f(%+.0f) h%.0f"%(x,z,z-z0,h))
    print("    "+"  ".join(row))
    # quay possible keeping 12 m of water north of the deck edge between x 392 and 545 (hall + cold store frontage)
    q=min(zat(cl,x)[0]-HALF-12.0 for x in range(392,546,2))
    q2=min(zat(cl,x)[0]-HALF-12.0 for x in range(392,611,2))
    sb=max(H(g,x,zat(cl,x)[0]) for x in range(420,700,10)); sbm=min(H(g,x,zat(cl,x)[0]) for x in range(420,700,10))
    print("    quay line limit (deck edge - 12 m): x 392..545 -> z %.0f (yard depth from toe 712: %.0f m); x 392..610 -> z %.0f (%.0f m); seabed under the line %.0f..%.0f"%(q,q-712,q2,q2-712,sbm,sb))
    for x in (540,560,580,600,640):
        z,h=zat(cl,x); th=math.radians(h); zx=(z+11)-(850-x)*math.tan(th); room=zx-698
        print("      sb_on gore at x %d: heading E %.1f N, single arc into T(850): room %.0f m -> Rmax %.0f"%(x,h,room,max(0,(room-15)/math.tan((math.pi/2-th)/2))))
show("TODAY (design)",M0,R0)
A=(370.0,-840.0)
for k in (20,40,60):
    B=(640.0-k,-795.0-k)
    main=[m for m in M0 if m not in ((470.0,-805.0),(640.0,-795.0))]
    i=main.index(A); main=main[:i+1]+[B]+main[i+1:]
    rad=[R0[M0.index(m)] if m in M0 else 150.0 for m in main]
    show("drop corner (470,805); slide corner (640,795) %d m down the diagonal to (%.0f,%.0f)"%(k,B[0],-B[1]),main,rad)
# keep both corners but slide both
for D in (20,40):
    main=list(M0); main[main.index((470.0,-805.0))]=(470.0,-805.0-D); main[main.index((640.0,-795.0))]=(640.0-D,-795.0-D)
    show("keep 3 corners: (470,%d) and (%d,%d)"%(805+D,640-D,795+D),main,R0)
