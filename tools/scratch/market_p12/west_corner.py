# single arc tangent to the z=672 leg and the N-S leg (arterials record), leg shifted 0/5/10 m west, R 40/45
from common import *
g=grid()
net=load(False); pts=gpts(net,"ring_kita__9")
ns=[p for p in pts if p[1]>720][:3]; print("N-S leg stations",[(round(p[0],1),round(p[1],1)) for p in ns])
(ax,az),(bx,bz)=ns[0][:2],ns[2][:2]
d=(bx-ax,bz-az); L=math.hypot(*d); d=(d[0]/L,d[1]/L)   # heading south
# measured land toe of the built N-S leg (first x going west where ground < 5.7) and crest edges
for z in (700,720,740,760,800):
    xr=ax+(z-az)*d[0]/d[1]; x=xr
    while H(g,x,z)>11.5: x-=0.5
    xc=x
    while H(g,x,z)>5.75: x-=0.5
    print("z %d road x %.1f land crest edge %.1f (%.1f m) land toe %.1f (%.1f m from road)"%(z,xr,xc,xr-xc,x,xr-x))
TOE=25.5  # measured road->land toe
BOX_E=205.0; RAIL=185.0+8.0
for sh in (0,5,10):
    for R in (40,45):
        # leg line shifted west by sh; intersect with z=672
        x0=ax-sh+(672-az)*d[0]/d[1]
        # travel west along z=672 (-1,0) then along d ; turn angle
        th=math.acos(-d[0]); T=R*math.tan(th/2)
        pe=(x0+T,672.0); ps=(x0+d[0]*T,672+d[1]*T)
        c=(pe[0],672+R)   # centre south of the E-W leg
        west=c[0]-R; toe=c[0]-R-TOE
        # nearest toe point to the station box (x<=205, z 634..726): toe circle radius R+TOE about c
        best=min(math.hypot(max(0,(c[0]+(R+TOE)*math.cos(a))-BOX_E), max(0,634-(c[1]+(R+TOE)*math.sin(a)), (c[1]+(R+TOE)*math.sin(a))-726)) for a in [math.radians(k/4) for k in range(180*4,270*4)])
        Tc=pe[0]+30+26
        print("shift %2d R %d: PI x %.1f turn %.1f deg, arc ends on z672 at x %.1f, on N-S leg at (%.1f,%.1f); toe westmost x %.1f -> %.1f m to station box (x 205), %.1f m to rail fence (x 193); min T centre for 30 m straight = %.1f"%(sh,R,x0,math.degrees(th),pe[0],ps[0],ps[1],toe,best,toe-RAIL,Tc))
# existing stations on the z672 leg
print("z672 stations x:",[round(p[0],1) for p in pts if abs(p[1]-672)<0.1])
