import json, glob, numpy as np, sys
N=2305; X0=-2304.0; STEP=2.0
g=np.fromfile('assets/world_source/terrain/island_land.f32',dtype=np.float32).reshape(N,N)
BX=(150,760); BZ=(630,900); K=2.2; PW=int((BX[1]-BX[0])*K); PH=int((BZ[1]-BZ[0])*K); HEAD=58; PAD=20
ix=lambda v:int((v-X0)/STEP)
roads={}
for f in glob.glob('assets/world_source/pieces/Roads_IslandRoads_island_*.lanekit.json'):
    for l in json.load(open(f))['lanes']:
        if l['kind']!='through': continue
        pts=[(p[0],p[2]) for p in l['points']]
        if any(BX[0]-60<=x<=BX[1]+60 and BZ[0]-60<=z<=BZ[1]+60 for x,z in pts):
            roads.setdefault((l['road_name'],l['road_class']),[]).append(pts)
out=[]
def P(x,z,oy): return ((x-BX[0])*K+PAD, (z-BZ[0])*K+oy)
def rect(oy,x0,x1,z0,z1,fill,label=None,stroke='#333',fs=11,op=1,dash=None):
    a=P(x0,z0,oy); w=(x1-x0)*K; h=(z1-z0)*K
    out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" stroke="%s" stroke-width="1" fill-opacity="%s"%s/>'%(a[0],a[1],w,h,fill,stroke,op,' stroke-dasharray="%s"'%dash if dash else ''))
    if label:
        lines=label.split('\n'); cy=a[1]+h/2-(len(lines)-1)*fs*0.6
        for i,t in enumerate(lines): out.append('<text x="%.1f" y="%.1f" font-size="%d" text-anchor="middle" dominant-baseline="middle">%s</text>'%(a[0]+w/2,cy+i*fs*1.2,fs,t))
def text(oy,x,z,t,fs=11,fill='#333',anchor='start',bg=False):
    a=P(x,z,oy)
    if bg: out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%d" fill="#fff" fill-opacity="0.85" stroke="#999" stroke-width="0.5"/>'%(a[0]-4,a[1]-fs,len(t)*fs*0.53+8,fs+8))
    out.append('<text x="%.1f" y="%.1f" font-size="%d" fill="%s" text-anchor="%s">%s</text>'%(a[0],a[1],fs,fill,anchor,t))
def line(oy,pts,stroke,w,dash=None,op=1):
    out.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%s" stroke-opacity="%s" stroke-linejoin="round"%s/>'%(' '.join('%.1f,%.1f'%P(x,z,oy) for x,z in pts),stroke,w,op,' stroke-dasharray="%s"'%dash if dash else ''))
def circle(oy,x,z,r,label):
    a=P(x,z,oy); out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#fff" stroke="#c0392b" stroke-width="2"/>'%(a[0],a[1],r*K))
    for i,t in enumerate(label.split('\n')): out.append('<text x="%.1f" y="%.1f" font-size="9" text-anchor="middle">%s</text>'%(a[0],a[1]-8+i*11,t))
def base(oy,title,note):
    out.append('<text x="%d" y="%d" font-size="15" font-weight="bold">%s</text>'%(PAD,oy-34,title))
    out.append('<text x="%d" y="%d" font-size="12" fill="#444">%s</text>'%(PAD,oy-14,note))
    out.append('<clipPath id="c%d"><rect x="%d" y="%d" width="%d" height="%d"/></clipPath><g clip-path="url(#c%d)">'%(oy,PAD,oy,PW,PH,oy))
    out.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#a9d3ea"/>'%(PAD,oy,PW,PH))
    for z in range(BZ[0],BZ[1],2):          # land, as runs of 2 m cells
        row=g[ix(z), ix(BX[0]):ix(BX[1])]>0.35
        x=0
        while x<len(row):
            if row[x]:
                e=x
                while e<len(row) and row[e]: e+=1
                a=P(BX[0]+2*x,z,oy); out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#e9e4d6"/>'%(a[0],a[1],(e-x)*2*K+0.5,2*K+0.5)); x=e
            else: x+=1
    for gx in range(300,760,50): line(oy,[(gx,BZ[0]),(gx,BZ[1])],'#000',0.3,op=0.15); text(oy,gx+2,896,'x %d'%gx,8,'#666')
    for gz in range(650,900,50): line(oy,[(BX[0],gz),(BX[1],gz)],'#000',0.3,op=0.15); text(oy,252,gz-2,'z %d'%gz,8,'#666')
    for (name,cls),ls in roads.items():
        if cls in('expressway','ramp') or name=='ichiba_michi': continue
        for pts in ls: line(oy,pts,'#666',3.2*K*0.9)
    text(oy,330,668,'dike road on the crest (2+2)',10,'#fff')
    text(oy,262,885,'sea',14,'#2a6f97')
def viaduct(oy):
    for (name,cls),ls in roads.items():
        if cls in('expressway','ramp'):
            for pts in ls: line(oy,pts,'#7a5ea8',3.3*K,op=0.75)
    text(oy,600,830,'expressway viaduct, deck 12 m over the water',11,'#5b3f8f')
def lane_today(oy):
    for (name,cls),ls in roads.items():
        if name=='ichiba_michi':
            for pts in ls: line(oy,pts,'#c0392b',3.0*K)
def ramp(oy,foot,label='two-way ramp, ~100 m at 6 %',lx=452):
    line(oy,[(567,676),(567,698)],'#e67e22',9*K); text(oy,575,690,'level landing 20 m',10,'#b35c00')
    line(oy,[(567,698),(562,706),(550,711)]+foot,'#c0392b',8*K*0.9,op=0.85)
    text(oy,lx,708,label,10,'#fff')
H=PH+HEAD+26
out.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" font-family="DejaVu Sans, sans-serif"><rect width="100%%" height="100%%" fill="#fff"/>'%(PW+2*PAD, 10*H+50))
out.append('<text x="%d" y="24" font-size="17" font-weight="bold">Fish market outside the dike: plan preview (north up, 50 m grid; coast, roads and viaduct are the built island\'s own data)</text>'%PAD)
# ---------------- today
oy=40+HEAD
base(oy,'TODAY','The red lane kinks straight off the crest junction, runs down the sea face and dead-ends behind the hall. No car park, no forecourt.')
rect(oy,405,570,705,775,'#bdbdbd',op=0.55)
lane_today(oy)
rect(oy,442.5,532.5,732,768,'#f7f7f7','HALL 90 x 36'); rect(oy,542.5,565.5,732,755,'#f7f7f7','ice'); rect(oy,409.5,432.5,732,748,'#f7f7f7','office',fs=9)
rect(oy,412.5,502.5,781,785,'#c9a36b'); text(oy,415,794,'pontoon',9)
text(oy,300,738,'empty plot',10,'#555'); text(oy,588,748,'empty plot',10,'#555'); viaduct(oy); out.append('</g>')
# ---------------- proposal 1
oy+=H
base(oy,'PROPOSAL 1: the reviews\' layout, drawn to fit','The viaduct is only 10-25 m off this quay, so the hall cannot move south at all: it slides 37 m west, and the truck yard stays 15 m deep (the planner asked for 30-35 m).')
out.append('<polygon points="%s" fill="#f1d9a0" stroke="#b8860b" stroke-dasharray="5,3"/>'%' '.join('%.1f,%.1f'%P(x,z,oy) for x,z in [(285,762),(500,762),(500,778),(285,778)]))
text(oy,290,790,'reclaimed: quay 16 m out',10,'#8a6508')
ramp(oy,[(445,711),(405,720)])
rect(oy,405,540,717,732,'#d5d5d5','truck yard, 15 m deep',fs=10)
rect(oy,405,495,732,768,'#f7f7f7','HALL (37 m west)'); rect(oy,502,525,732,755,'#f7f7f7','ice',fs=9); rect(oy,532,566,734,760,'#e3e9d2','trade\nparking',fs=9)
rect(oy,300,372,712,772,'#dfe7f2','PUBLIC CAR PARK\n72 x 60 m\n~120 cars'); circle(oy,388,729,15,'turning\nsquare\n30 m')
viaduct(oy); line(oy,[(545,845),(493,781)],'#000',1); text(oy,470,858,'10 m of water left to the deck at this corner',10,'#000',bg=True); out.append('</g>')
# ---------------- proposal 2
oy+=H
base(oy,'PROPOSAL 2: my own variant, NOT reviewed','The hall moves to the WEST plot, where the viaduct is furthest off, and 26 m south; today\'s site becomes the forecourt and car park at the foot of the ramp.')
rect(oy,300,402,762,804,'#f1d9a0',stroke='#b8860b',dash='5,3'); text(oy,404,800,'reclaimed: quay 42 m out',10,'#8a6508')
ramp(oy,[(455,711),(440,718)])
rect(oy,300,398,718,758,'#d5d5d5','truck yard, 40 m deep',fs=10)
rect(oy,300,390,758,794,'#f7f7f7','HALL 90 x 36\n(142 m west, 26 m south)'); rect(oy,300,370,808,812,'#c9a36b'); text(oy,305,824,'pontoon',9)
rect(oy,455,566,722,760,'#dfe7f2','PUBLIC CAR PARK\n110 x 38 m, ~150 cars'); rect(oy,405,452,746,762,'#ececec','market square',fs=9)
circle(oy,428,729,15,'turning\nsquare\n30 m'); line(oy,[(413,729),(398,736)],'#c0392b',6)
viaduct(oy); line(oy,[(440,868),(391,806)],'#000',1); text(oy,405,880,'12 m of water to the deck at this corner, 20 m and more further west',10,'#000',bg=True); out.append('</g>')
# ---------------- proposal 3
oy+=H
base(oy,'PROPOSAL 3: your sketch - one shared yard, hall at the west end, no public car park, the west gap closed','Hall on the west plot, then truck yard, parking and trade parking in one paved strip. Vehicles turn in the yard. The 14-24 m water slot west of the plot is filled; 12 m of new quay in front of the hall.')
out.append('<polygon points="%s" fill="#f1d9a0" stroke="#b8860b" stroke-dasharray="5,3"/>'%' '.join('%.1f,%.1f'%P(x,z,oy) for x,z in [(296,630),(302,630),(302,762),(384,762),(384,774),(272,774),(276,760),(286,700)]))
text(oy,255,790,'gap closed + quay 12 m out',9,'#8a6508')
rect(oy,374,570,717,762,'#d5d5d5',None)
ramp(oy,[(455,711),(442,719)])
text(oy,430,731,'entrance',10,'#c0392b')
rect(oy,282,372,724,760,'#f7f7f7','HALL 90 x 36\n(160 m west)'); rect(oy,290,335,707,721,'#f7f7f7','office + ice',fs=9)
rect(oy,376,452,736,760,'#c8c8c8','TRUCK YARD\nberths on the hall\'s east side',fs=9,stroke='#888')
rect(oy,462,532,738,760,'#dfe7f2','PARKING ~45 cars',fs=10,stroke='#888'); rect(oy,536,568,738,760,'#e3e9d2','trade',fs=9,stroke='#888')
text(oy,470,729,'shared yard 196 x 45 m: trucks and cars turn here',10,'#333')
rect(oy,290,352,778,782,'#c9a36b'); text(oy,356,784,'pontoon',9)
viaduct(oy); line(oy,[(420,850),(370,776)],'#000',1); text(oy,330,862,'45 m of open water to the deck in front of the hall',10,'#000',bg=True); out.append('</g>')
# ---------------- proposal 4
oy+=H
base(oy,'PROPOSAL 4: proposal 3 pushed east, a large office + cold store, the yard round the whole hall','Hall 20 m further east and 12 m south; office + cold store attached on its east side; one yard along the hall\'s whole land side and on east to the trade bays. West gap filled, quay 22 m out.')
out.append('<polygon points="%s" fill="#f1d9a0" stroke="#b8860b" stroke-dasharray="5,3"/>'%' '.join('%.1f,%.1f'%P(x,z,oy) for x,z in [(296,630),(302,630),(302,762),(447,762),(447,784),(270,784),(276,760),(286,700)]))
text(oy,255,800,'gap closed + quay 22 m out',9,'#8a6508')
out.append('<polygon points="%s" fill="#d5d5d5" stroke="#333"/>'%' '.join('%.1f,%.1f'%P(x,z,oy) for x,z in [(296,705),(440,705),(440,717),(570,717),(570,762),(447,762),(447,736),(296,736)]))
ramp(oy,[(455,711),(447,719)])
text(oy,452,731,'entrance',10,'#c0392b')
rect(oy,302,392,736,772,'#f7f7f7','HALL 90 x 36'); rect(oy,397,442,736,772,'#eef3f7','OFFICE +\nCOLD STORE\n45 x 36, 3 floors',fs=9)
text(oy,306,722,'truck apron along the hall, 31 m deep: berths on the land side',10,'#333')
rect(oy,452,500,740,760,'#c8c8c8','truck bays',fs=9,stroke='#888'); rect(oy,504,540,740,760,'#dfe7f2','parking ~25',fs=9,stroke='#888'); rect(oy,543,568,740,760,'#e3e9d2','trade',fs=9,stroke='#888')
text(oy,470,729,'shared yard: turn here',10,'#333')
rect(oy,306,376,788,792,'#c9a36b'); text(oy,380,794,'pontoon',9)
viaduct(oy); line(oy,[(470,850),(446,786)],'#000',1); text(oy,380,862,'15 m of water to the deck at this corner, 30 m in front of the hall',10,'#000',bg=True); out.append('</g>')
# ---------------- proposal 5
oy+=H
base(oy,'PROPOSAL 5: one rectangular yard, with the two reviews\' changes','A single paved rectangle 274 x 57 m from the dike toe to the old quay line. Buildings stand in its south-west corner, the ramp comes down inside its north-east edge. "Trade" bays merged into the parking.')
out.append('<polygon points="%s" fill="#f1d9a0" stroke="#b8860b" stroke-dasharray="5,3"/>'%' '.join('%.1f,%.1f'%P(x,z,oy) for x,z in [(296,630),(302,630),(302,762),(455,762),(455,776),(270,776),(276,760),(286,700)]))
text(oy,255,792,'gap closed + quay 14 m out',9,'#8a6508')
rect(oy,296,570,705,762,'#d5d5d5',None)
ramp(oy,[(490,711),(480,718)],'two-way ramp, ~75 m at 8 %',492)
rect(oy,455,480,722,740,'none','gate +\nscale',fs=8,stroke='#c0392b',dash='3,2')
rect(oy,302,392,736,766,'#f7f7f7','HALL 90 x 30'); rect(oy,404,449,736,766,'#eef3f7','COLD STORE + ICE\noffice on top',fs=9)
text(oy,393,754,'12 m',8,'#666')
text(oy,306,722,'truck apron 31 m deep: berths along the buildings',10,'#333')
rect(oy,270,296,705,736,'#c8c8c8','turn',fs=9,stroke='#888')
rect(oy,484,566,742,760,'#dfe7f2','PARKING ~40 (traders + visitors)',fs=10,stroke='#888')
text(oy,486,733,'waiting bays for trucks',9,'#333')
rect(oy,306,376,780,784,'#c9a36b'); text(oy,380,786,'pontoon',9)
for sx in (330,410): rect(oy,sx-2,sx+2,696,706,'#8e44ad',None,stroke='#8e44ad')
text(oy,336,701,'stairs up the dike (evacuation)',8,'#8e44ad')
viaduct(oy); line(oy,[(480,850),(452,778)],'#000',1); text(oy,380,862,'22 m of water to the deck at this corner, 40 m in front of the hall',10,'#000',bg=True); out.append('</g>')
# ---------------- proposal 6
oy+=H
base(oy,'PROPOSAL 6: the yard reaches the junction - an upper terrace at the dike\'s height, the quay level below','The east part of the yard is filled up to the crest (+6 m), so the junction opens straight onto it: parking up there, no landing piece. One ramp inside the yard takes trucks down to the hall.')
out.append('<polygon points="%s" fill="#f1d9a0" stroke="#b8860b" stroke-dasharray="5,3"/>'%' '.join('%.1f,%.1f'%P(x,z,oy) for x,z in [(296,630),(302,630),(302,762),(455,762),(455,776),(270,776),(276,760),(286,700)]))
text(oy,255,792,'gap closed + quay 14 m out',9,'#8a6508')
rect(oy,296,486,705,762,'#d5d5d5',None)
rect(oy,486,572,676,762,'#c9bfa6','',stroke='#6b5d3a'); text(oy,492,690,'UPPER TERRACE, level with the dike road (+6 m)',10,'#4a3f22')
rect(oy,494,566,722,758,'#dfe7f2','PARKING ~45\n(traders + visitors)',fs=10,stroke='#888')
line(oy,[(486,705),(486,762)],'#6b5d3a',4); line(oy,[(486,762),(572,762)],'#6b5d3a',4); text(oy,500,773,'retaining wall, 6 m',9,'#6b5d3a')
line(oy,[(486,711),(411,711)],'#c0392b',8*K*0.9,op=0.85); text(oy,418,708,'ramp down, 75 m at 8 %',10,'#fff')
line(oy,[(567,678),(567,700),(540,711),(486,711)],'#c0392b',2,dash='6,4')
rect(oy,302,392,736,766,'#f7f7f7','HALL 90 x 30'); rect(oy,404,449,736,766,'#eef3f7','COLD STORE + ICE\noffice on top',fs=9)
text(oy,306,728,'truck apron (quay level): berths along the buildings',10,'#333')
rect(oy,270,296,705,736,'#c8c8c8','turn',fs=9,stroke='#888')
rect(oy,455,484,740,760,'#c8c8c8','trucks\nwait',fs=8,stroke='#888')
rect(oy,306,376,780,784,'#c9a36b'); text(oy,380,786,'pontoon',9)
for sx in (330,):rect(oy,sx-2,sx+2,696,706,'#8e44ad',None,stroke='#8e44ad')
rect(oy,474,486,745,749,'#8e44ad',None,stroke='#8e44ad'); text(oy,336,701,'stairs',8,'#8e44ad')
viaduct(oy); line(oy,[(600,850),(560,766)],'#000',1); text(oy,470,862,'the terrace top is about level with the viaduct deck, 10-25 m away',10,'#000',bg=True); out.append('</g>')
# ---------------- proposal 7
oy+=H
base(oy,'PROPOSAL 7: your marked-up plan as I read it - a full rectangle, no ramp from the T, a new junction at each end','Yard 300 x 57 m with the turning end taken down to the quay line. The existing T keeps three arms. East: a new junction at x 650 and an L-shaped ramp into the yard\'s east end. West: a ramp up the dike face to a new T.')
out.append('<polygon points="%s" fill="#f1d9a0" stroke="#b8860b" stroke-dasharray="5,3"/>'%' '.join('%.1f,%.1f'%P(x,z,oy) for x,z in [(296,630),(302,630),(302,762),(455,762),(455,776),(262,776),(262,740),(286,700)]))
text(oy,300,792,'gap closed + quay 14 m out',9,'#8a6508')
rect(oy,270,570,705,762,'#d5d5d5',None)
line(oy,[(650,676),(650,698)],'#e67e22',9*K); text(oy,658,690,'new junction + level landing',10,'#b35c00')
line(oy,[(650,698),(650,738),(643,745),(570,745)],'#c0392b',8*K*0.9,op=0.85); text(oy,578,741,'EAST RAMP 127 m at 5 %',10,'#fff')
line(oy,[(270,750),(258,752),(252,762),(249,838)],'#c0392b',8*K*0.9,op=0.85); line(oy,[(249,838),(241,838)],'#e67e22',7*K)
text(oy,160,800,'WEST RAMP',10,'#c0392b'); text(oy,150,812,'~95 m at 6.5 %',10,'#c0392b'); text(oy,166,852,'new T',10,'#b35c00')
rect(oy,302,392,736,766,'#f7f7f7','HALL 90 x 30'); rect(oy,404,449,736,766,'#eef3f7','COLD STORE + ICE\noffice on top',fs=9)
text(oy,306,722,'truck apron 31 m deep: berths along the buildings',10,'#333')
rect(oy,272,296,707,760,'#c8c8c8','turn /\nwest\ngate',fs=9,stroke='#888')
rect(oy,470,560,712,732,'#dfe7f2','PARKING ~40 (traders + visitors)',fs=10,stroke='#888')
rect(oy,455,480,748,760,'none','scale',fs=8,stroke='#c0392b',dash='3,2')
rect(oy,306,376,780,784,'#c9a36b'); text(oy,380,786,'pontoon',9)
for sx in (330,410): rect(oy,sx-2,sx+2,696,706,'#8e44ad',None,stroke='#8e44ad')
text(oy,336,701,'stairs up the dike',8,'#8e44ad')
viaduct(oy); line(oy,[(690,700),(652,712)],'#000',1); text(oy,694,703,'passes under the expressway ramp decks',10,'#000',bg=True); out.append('</g>')
# ---------------- proposal 8
oy+=H
base(oy,'PROPOSAL 8: mirrored west and east entrances, yard further right','Yard 260 x 57 m at x 350..610. A new junction at each end (x 305 and x 655), each with a level landing and an L-shaped ramp of ~92 m at 6.8 %. The dike road\'s bend moves about 20 m west so the west junction sits on straight road.')
out.append('<polygon points="%s" fill="#f1d9a0" stroke="#b8860b" stroke-dasharray="5,3"/>'%' '.join('%.1f,%.1f'%P(x,z,oy) for x,z in [(296,630),(302,630),(302,700),(350,700),(350,762),(458,762),(458,776),(345,776),(345,764),(262,764),(262,740),(286,700)]))
text(oy,262,790,'gap closed, quay 14 m out in front of the hall',9,'#8a6508')
rect(oy,350,610,705,762,'#d5d5d5',None)
line(oy,[(185,600),(185,900)],'#222',3,dash='10,5'); text(oy,150,880,'railway',10,'#222')
line(oy,[(318,676),(300,677),(270,680),(246,690),(230,706),(221,728),(220,760),(220,900)],'#111',2,dash='7,5'); text(oy,196,742,'dike road',9,'#111'); text(oy,196,753,'moved 20 m',9,'#111')
for jx,dirn,lab in ((655,-1,'EAST'),(305,1,'WEST')):
    line(oy,[(jx,676),(jx,698)],'#e67e22',9*K)
    edge=610 if dirn<0 else 350
    line(oy,[(jx,698),(jx,738),(jx+7*dirn,745),(edge,745)],'#c0392b',8*K*0.9,op=0.85)
text(oy,662,690,'new junction + landing',10,'#b35c00'); text(oy,236,668,'new junction + landing',10,'#b35c00')
text(oy,614,757,'EAST ramp',9,'#c0392b'); text(oy,300,757,'WEST ramp',9,'#c0392b')
rect(oy,350,362,707,760,'#c8c8c8','',stroke='#888'); rect(oy,598,610,707,760,'#c8c8c8','',stroke='#888'); text(oy,352,716,'gate',8,'#333'); text(oy,588,716,'gate',8,'#333')
rect(oy,366,456,736,766,'#f7f7f7','HALL 90 x 30'); rect(oy,468,513,736,760,'#eef3f7','COLD STORE + ICE\noffice on top',fs=9)
text(oy,368,722,'truck apron 31 m deep: berths along the buildings',10,'#333')
rect(oy,520,594,712,732,'#dfe7f2','PARKING ~35',fs=10,stroke='#888')
rect(oy,370,440,780,784,'#c9a36b'); text(oy,444,786,'pontoon',9)
for sx in (400,480): rect(oy,sx-2,sx+2,696,706,'#8e44ad',None,stroke='#8e44ad')
viaduct(oy)
line(oy,[(560,850),(514,764)],'#000',1); text(oy,440,862,'25 m of water to the deck at the cold store, 30 m at the hall',10,'#000',bg=True)
line(oy,[(700,712),(640,722)],'#000',1); text(oy,640,706,'east end lies under the expressway ramp decks (piers)',10,'#000',bg=True); out.append('</g>')
# ---------------- proposal 9
oy+=H
base(oy,'PROPOSAL 9: proposal 8 with the three reviews\' changes - the east ramp clears every pier','East junction moved 12 m west (x 643): the ramp passes north-west of the pier line, no pier moves. Buildings 26 m east for a forecourt at the west gate. Rounded, widened bends. Dike road bend moved 10 m, not 20.')
out.append('<polygon points="%s" fill="#f1d9a0" stroke="#b8860b" stroke-dasharray="5,3"/>'%' '.join('%.1f,%.1f'%P(x,z,oy) for x,z in [(296,630),(302,630),(302,700),(350,700),(350,762),(484,762),(484,776),(386,776),(386,764),(262,764),(262,740),(286,700)]))
text(oy,262,790,'gap closed; quay 14 m out in front of the hall',9,'#8a6508')
rect(oy,350,610,705,762,'#d5d5d5',None)
line(oy,[(185,600),(185,900)],'#222',3,dash='10,5'); text(oy,150,880,'railway',10,'#222')
line(oy,[(318,674),(300,674),(280,676),(258,686),(240,702),(231,724),(230,760),(230,900)],'#111',2,dash='7,5'); text(oy,196,742,'dike road',9,'#111'); text(oy,190,753,'moved 10 m',9,'#111')
import math
def lramp(jx,edge,dirn):
    line(oy,[(jx,676),(jx,698)],'#e67e22',9*K)
    pts=[(jx,698),(jx,732)]+[(jx+dirn*18*(1-math.cos(a)), 732+18*math.sin(a)) for a in [i*math.pi/16 for i in range(1,9)]]+[(edge,750)]
    line(oy,pts,'#c0392b',8*K*0.9,op=0.85)
lramp(643,610,-1); lramp(305,350,1)
text(oy,650,690,'EAST: right-in / right-out, no signal',10,'#b35c00'); text(oy,196,664,'WEST: main gate, signal',10,'#b35c00')
for px,pz in [(539.2,786.9),(569.8,780.7),(600.1,772.8),(628.9,760.5),(654.5,742.7),(675.9,719.8),(692.0,693.0),(706.2,632.5),(646.6,784.2),(676.7,780.1),(707.5,780.5),(527.5,801.8),(560.2,799.6),(592.4,793.8),(623.6,783.8),(652.9,769.3),(680.4,751.6),(705.0,730.0),(728.5,706.5)]:
    a=P(px,pz,oy); out.append('<circle cx="%.1f" cy="%.1f" r="4" fill="#222" stroke="#fff" stroke-width="1"/>'%a)
rect(oy,392,482,736,766,'#f7f7f7','HALL 90 x 30'); rect(oy,494,539,736,760,'#eef3f7','COLD STORE + ICE\noffice on top',fs=9)
rect(oy,352,390,707,760,'#e2e2e2','FORECOURT\n40 m:\nsee the\nquay',fs=9,stroke='#aaa')
text(oy,396,722,'truck apron 31 m: berths along the buildings',10,'#333')
rect(oy,548,604,712,756,'#dfe7f2','PARKING\n~35',fs=10,stroke='#888')
rect(oy,396,466,780,784,'#c9a36b'); text(oy,470,786,'pontoon',9)
for sx in (430,515): rect(oy,sx-2,sx+2,696,706,'#8e44ad',None,stroke='#8e44ad')
viaduct(oy)
line(oy,[(700,760),(658,744)],'#000',1); text(oy,640,772,'black dots: piers as built. Nearest to the ramp 15 m',10,'#000',bg=True); out.append('</g>')
out.append('</svg>')
open(sys.argv[1],'w').write('\n'.join(out))
