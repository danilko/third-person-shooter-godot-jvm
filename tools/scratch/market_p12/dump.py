from common import *
for final in (True,False):
    net=load(final); print("=== final" if final else "=== arterials", len(net.roads))
    for n,r in sorted(net.roads.items()):
        pts=gpts(net,n)
        if any(200<=p[0]<=900 and 620<=p[1]<=900 for p in pts):
            print(n, getattr(r,"road_class",None), len(pts))
            if not final and not n.startswith("ring_kita"): continue
            for p in pts:
                if 150<=p[0]<=950 and 560<=p[1]<=950:
                    P_=net.points[p[3]]
                    print("   %8.1f %8.1f y%6.2f %s %s"%(p[0],p[1],p[2],p[3][:10],[str(l.type) for l in P_.links if l.type!=pm.LINK_SEGMENT][:2]))
