import sys, math, os
import numpy as np
ROOT="/data/danilko/git/third-person-shooter"
sys.path.insert(0, ROOT+"/blender/addons/road_kit_authoring"); sys.path.insert(0, ROOT+"/tools")
sys.dont_write_bytecode=True
import point_model as pm
P=ROOT+"/assets/world_source/pieces/"
def load(final=True): return pm.load_network(P+("IslandRoads.roads.json" if final else "IslandRoads.arterials.roads.json"))
def gpts(net,name):  # godot (x,z,y)
    return [(net.points[u].pos[0], -net.points[u].pos[1], net.points[u].pos[2]+5.6, u) for u in net.roads[name].points]
def grid(name="island_natural.f32"):
    g=np.fromfile(ROOT+"/assets/world_source/terrain/"+name,dtype="<f4").reshape(2305,2305); return g
def H(g,x,z):
    fx=(x+2304)/2.0; fz=(z+2304)/2.0; i=int(fx); j=int(fz); tx=fx-i; tz=fz-j
    return float(g[j,i]*(1-tx)*(1-tz)+g[j,i+1]*tx*(1-tz)+g[j+1,i]*(1-tx)*tz+g[j+1,i+1]*tx*tz)
def turns(pts):
    out=[]
    for a,b,c in zip(pts,pts[1:],pts[2:]):
        h1=math.atan2(b[1]-a[1],b[0]-a[0]); h2=math.atan2(c[1]-b[1],c[0]-b[0])
        d=math.degrees((h2-h1+math.pi)%(2*math.pi)-math.pi); out.append(d)
    return out
