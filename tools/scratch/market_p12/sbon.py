from common import *
import island_plan as PL, island_expressway as EX
from island_roadgen import rounded_polygon, arclen, at_s
net=load()
# 1. scan every ramp-class road: station turns, sign reversals > 1 deg
print("== S scan (final record): consecutive NONZERO station turns of opposite sign, both > 1 deg")
for n,r in sorted(net.roads.items()):
    if str(r.road_class)!="ramp": continue
    pts=[p[:2] for p in gpts(net,n)]; tr=turns(pts)
    big=[(i,t) for i,t in enumerate(tr) if abs(t)>1.0]
    rev=[(a,b) for a,b in zip(big,big[1:]) if a[1]*b[1]<0]
    tot=sum(abs(t) for t in tr)
    if rev:
        print("  %-16s %2d stations, %d reversal(s):"%(n,len(pts),len(rev))+"; ".join("%+.1f at (%.0f,%.0f) -> %+.1f at (%.0f,%.0f)"%(a[1],pts[a[0]+1][0],pts[a[0]+1][1],b[1],pts[b[0]+1][0],pts[b[0]+1][1]) for a,b in rev))
# 2. sb_on today
pts=gpts(net,"shuto_sb_on"); p2=[p[:2] for p in pts]; tr=turns(p2)
print("== shuto_sb_on stations (x,z,y) turn(deg, + = left in plan x/z-down frame) span")
for i,p in enumerate(pts):
    t=tr[i-1] if 0<i<len(pts)-1 else 0; sp=math.dist(p2[i],p2[i-1]) if i else 0
    print("  %7.1f %7.1f y%6.2f  %+6.1f  %5.1f"%(p[0],p[1],p[2],t,sp))
L=sum(math.dist(a,b) for a,b in zip(p2,p2[1:])); print("length %.0f m, climb %.2f"%(L,pts[0][2]-pts[-1][2]))
# 3. reproduce two_arc: m = mouth, t0 = chord of the mainline neighbours of the gore station, e,te = T arm
ml=[p[:2] for p in gpts(net,"shuto_wangan__3")]
print("mainline stations",[(round(a,1),round(b,1)) for a,b in ml])
m=(pts[0][0],-pts[0][1]); e=(850.0,-(672.0+26.0)); te=(0.0,1.0)
def run(m,t0,e,te,label):
    try: p,R=EX.two_arc(m,t0,e,te)
    except Exception as ex: print("  ",label,"-> two_arc:",ex); return
    tr=turns(p); pos=sum(t for t in tr if t>0); neg=sum(t for t in tr if t<0)
    Lp=sum(math.dist(a,b) for a,b in zip(p,p[1:]))
    print("  %s -> R %.0f, length %.0f, left turn %.1f deg, right turn %.1f deg  %s"%(label,R,Lp,pos,-neg,"S (REVERSE)" if min(pos,-neg)>1 else "one-way"))
t0c=(ml[4][0]-ml[2][0],-(ml[4][1]-ml[2][1])); l=math.hypot(*t0c); t0c=(t0c[0]/l,t0c[1]/l)
print("== two_arc reproduction; chord tangent heading E %.1f N; bearing mouth->T-mouth E %.1f N"%(math.degrees(math.atan2(t0c[1],t0c[0])),math.degrees(math.atan2(e[1]-m[1],e[0]-m[0]))))
run(m,t0c,e,te,"today (mouth %.1f,%.1f chord tangent, T 850)"%(m[0],-m[1]))
# design alignment
cl=rounded_polygon(PL.WG_MAIN[1:],[0.0]+PL.WG_MAIN_R[1:],closed=False,full_ends=True,arc_step=1.0); cum=arclen(cl,False)
def design(x):
    for i in range(len(cl)-1):
        if (cl[i][0]-x)*(cl[i+1][0]-x)<=0 and cl[i][0]>300:
            a,b=cl[i],cl[i+1]; f=(x-a[0])/(b[0]-a[0]); d=(b[0]-a[0],b[1]-a[1]); l=math.hypot(*d)
            return (x,a[1]+f*d[1]),(d[0]/l,d[1]/l)
q,t=design(640); print("design alignment at x 640: z %.1f heading E %.1f N ; record station z %.1f => %.1f m off the design arc"%(-q[1],math.degrees(math.atan2(t[1],t[0])),ml[3][1],-q[1]-ml[3][1]))
OFF=11.0   # mouth offset south of the centreline (measured below)
print("measured mouth offset from mainline station: %.1f m"%math.dist(pts[0][:2],ml[3]))
print("== (c) move SB_ON_X west, gore ON the design alignment, design tangent; T stays (850,672)")
for x in (640,620,610,600,592,585,575,560):
    q,t=design(x); mm=(q[0]+t[1]*OFF,q[1]-t[0]*OFF)
    run(mm,t,e,te,"SB_ON_X %d (z %.1f, heading E %.1f N)"%(x,-q[1],math.degrees(math.atan2(t[1],t[0]))))
    # analytic single arc: straight along t from mm, one arc, straight north into the T
    th=math.atan2(t[1],t[0]); zx=-(mm[1]+(850-mm[0])*math.tan(th)); room=zx-698.0
    k=math.tan((math.pi/2-th)/2)
    print("        single-arc: tangent line meets x 850 at z %.1f (%.1f m south of the T mouth) -> R max %.0f with a 15 m landing"%(zx,room,(room-15)/k if room>15 else 0))
print("== (a) move the T along ring_kita, gore as today (x 640 mouth, chord tangent / design tangent)")
q,t=design(640); mm=(q[0]+t[1]*OFF,q[1]-t[0]*OFF)
for xT in (800,820,850,863):
    ee=(float(xT),-698.0)
    run(m,t0c,ee,te,"T x %d, today's mouth"%xT); run(mm,t,ee,te,"T x %d, design mouth"%xT)
