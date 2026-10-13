# perpendicular distance of each mainline station to the design alignment (segment distance)
from common import *
import island_plan as PL
from island_roadgen import rounded_polygon
net=load()
J=PL.WG_LOOP_J; c1=PL.WG_MAIN[1]
cl=rounded_polygon([J]+PL.WG_MAIN[1:],[0.0]+PL.WG_MAIN_R[1:],closed=False,full_ends=True,arc_step=1.0)
def sd(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]; t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy or 1))); return math.hypot(p[0]-a[0]-dx*t,p[1]-a[1]-dy*t)
for n in ("shuto_wangan","shuto_wangan__1","shuto_wangan__2","shuto_wangan__2b","shuto_wangan__3","shuto_wangan__4"):
    for p in gpts(net,n):
        d=min(sd((p[0],-p[1]),a,b) for a,b in zip(cl,cl[1:]))
        if d>0.3: print("%s (%.1f,%.1f) %.1f m off; links %s"%(n,p[0],p[1],d,[str(l.type) for l in net.points[p[3]].links if l.type!=pm.LINK_SEGMENT]))
print("done")
