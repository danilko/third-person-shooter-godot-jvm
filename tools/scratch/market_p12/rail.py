from common import *
net=pm.load_network(P+"IslandRail.roads.json")
for n,r in sorted(net.roads.items()):
    pts=gpts(net,n)
    sel=[p for p in pts if 100<=p[0]<=330 and 600<=p[1]<=900]
    if sel:
        print(n, getattr(r.base,"lane_width",None))
        for p in sel: print("   %.1f %.1f y%.2f"%p[:3])
