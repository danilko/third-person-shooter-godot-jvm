import pickle,math,sys
sys.path.insert(0,"/data/danilko/git/third-person-shooter/tools/scratch/market_p12")
from common import *
B=pickle.load(open('bands.pkl','rb'))
for o,_,p in B:
    if o in('ichiba_michi','ichiba_michi_loop'):
        print('==',o)
        for q in p[::3]: print('  x %.1f z %.1f y %.2f half %.1f  -> edges z %.1f..%.1f'%(q[0],q[1],q[2]+5.6,q[3],q[1]-q[3],q[1]+q[3]))
g=grid("island_natural.f32")
print("ground y along columns (natural grid):")
for x in (270,300,330,360,400,450,500,540,580,600,620):
    print(' x',x,' '.join('%d:%.1f'%(z,H(g,x,z)) for z in range(690,900,10)))
