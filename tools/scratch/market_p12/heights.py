from common import *
for nm in ("island_natural.f32","island_land.f32"):
    g=grid(nm); print("==",nm)
    zs=list(range(660,800,6))
    print("x\\z  "+" ".join("%5d"%z for z in zs))
    for x in (240,270,300,320,330,340,350,380,420,455,500,532,567,600,620,637,650,660,680,700,720):
        print("%4d  "%x+" ".join("%5.1f"%H(g,x,z) for z in zs))
