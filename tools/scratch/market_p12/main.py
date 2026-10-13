from common import *
import island_plan as PL, island_expressway as EX
from island_roadgen import rounded_polygon, arclen, at_s
cl=rounded_polygon(PL.WG_MAIN[1:],[0.0]+PL.WG_MAIN_R[1:],closed=False,full_ends=True,arc_step=4.0)
sel=[(x,-y) for x,y in cl if 330<=x<=800]
import math
prev=None
for i in range(1,len(sel)-1):
    a,b,c=sel[i-1],sel[i],sel[i+1]
    t=turns([a,b,c])[0]; d=math.dist(a,b)
    tag="arc" if abs(t)>0.3 else "str"
    if tag!=prev or i%6==0: print("%7.1f %7.1f turn %+5.2f seg %.1f %s"%(b[0],b[1],t,d,tag))
    prev=tag
net=load()
for n in ("shuto_wangan__3","shuto_sb_on","shuto_sb_off"):
    r=net.roads[n]; print(n,"lanes fwd/bwd",r.base.lanes_fwd if hasattr(r.base,'lanes_fwd') else None, "lw",r.base.lane_width, [k for k in vars(r.base).keys()][:40])
    break
