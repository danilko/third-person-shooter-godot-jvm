import sys,math,pickle
R="/data/danilko/git/third-person-shooter"
sys.path.insert(0,R+"/blender/addons/road_kit_authoring"); sys.path.insert(0,R+"/blender/lib"); sys.path.insert(0,R+"/tools")
sys.dont_write_bytecode=True
import point_model as pm, point_edges as pe
net=pm.load_network(R+"/assets/world_source/pieces/IslandRoads.roads.json")
b=pe.band_corridors(pe.solve_all(net,None)[3],owners=True)
out=[]
for line,half,own in b:
    pts=[(p[0],-p[1],p[2],(p[3] if len(p)>3 else half)) for p in line]
    if any(150<x<800 and 620<z<1000 for x,z,*_ in pts):
        out.append((str(own),half,pts))
pickle.dump(out,open(sys.argv[1],"wb"))
for o,h,p in out: print(o, "half" ,h if isinstance(h,(int,float)) else "?", len(p), "x %.0f..%.0f z %.0f..%.0f y %.1f..%.1f"%(min(q[0] for q in p),max(q[0] for q in p),min(q[1] for q in p),max(q[1] for q in p),min(q[2] for q in p),max(q[2] for q in p)))
