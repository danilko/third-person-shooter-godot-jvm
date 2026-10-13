from common import *
import json,glob
g=grid()
print("height map (rows z, cols x), natural grid")
xs=list(range(170,350,8)); print("z\\x "+" ".join("%4d"%x for x in xs))
for z in range(640,770,8): print("%4d "%z+" ".join("%4.0f"%H(g,x,z) for x in xs))
# crest north toe along x (first z going north from 672 where h<11.5 and <6)
for x in (300,320,340,360,400,450,500,540,600,640,660,700):
    zn=672
    while H(g,x,zn)>11.5: zn-=1
    zt=zn
    while H(g,x,zt)>5.7: zt-=1
    zs=672
    while H(g,x,zs)>11.5: zs+=1
    ze=zs
    while H(g,x,ze)>5.7: ze+=1
    zq=ze
    while H(g,x,zq)>0: zq+=1
    print("x %d crest z %d..%d land toe z %d sea toe z %d yard south edge z %d seabed %.1f"%(x,zn+1,zs-1,zt,ze,zq,H(g,x,zq+10)))
# rails
for f in glob.glob(P+"*.json"):
    if "ail" in os.path.basename(f): print(os.path.basename(f))
