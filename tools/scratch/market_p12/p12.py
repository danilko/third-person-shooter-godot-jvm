"""P12 preview: python3 tools/scratch/market_p12/p12.py docs/previews/market_p12.svg  (run from the repo root;
then `magick -density 110 market_p12.svg market_p12.png`). Helpers come from market_plan.py, re-framed wider."""
import math, os, sys
src = open(os.path.join(os.path.dirname(__file__), 'market_plan.py')).read()
src = src[:src.index('H=PH+HEAD+26')].replace('BX=(150,760)', 'BX=(215,885)').replace('K=2.2', 'K=2.0')
exec(src)
oy = 96
W = PW + 2 * PAD
out.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" font-family="DejaVu Sans, sans-serif"><rect width="100%%" height="100%%" fill="#fff"/>' % (W, PH + oy + 150))
out.append('<text x="%d" y="26" font-size="18" font-weight="bold">PROPOSAL 12: the Japanese layout - one truck ramp from the existing signal, a public car park at dike height, the expressway moved south</text>' % PAD)
out.append('<text x="%d" y="46" font-size="12" fill="#444">North up, 50 m grid. Land, roads and today\'s viaduct are the built island\'s data; everything coloured is the proposal. Positions are from the round-6 measurements and are to be proven on a dry run before building.</text>' % PAD)
base(oy, '', '')
# new land: the west wedge and the quay pushed out
poly = [(270, 640), (303, 640), (303, 761), (720, 761), (720, 780), (270, 780)]
out.append('<polygon points="%s" fill="#f1d9a0" stroke="#b8860b" stroke-dasharray="5,3"/>' % ' '.join('%.1f,%.1f' % P(x, z, oy) for x, z in poly))
# the low yard
rect(oy, 303, 610, 712, 780, '#d5d5d5', None, stroke='#999')
line(oy, [(270, 780), (610, 780)], '#8a6508', 2.5)
line(oy, [(610, 780), (720, 780)], '#555', 2.5)
line(oy, [(610, 712), (610, 780)], '#555', 1.2, dash='3,3')
# upper terrace
rect(oy, 310, 385, 698, 738, '#c9bfa6', 'PUBLIC CAR PARK\nat dike height\n~40 cars', fs=10, stroke='#6b5d3a')
line(oy, [(372, 676), (372, 698)], '#e67e22', 9 * K)
text(oy, 384, 690, 'WEST: public gate, right turn in / out', 10, '#b35c00', bg=True)
line(oy, [(385, 724), (497, 724), (497, 747)], '#8e44ad', 3); text(oy, 392, 721, 'footbridge to the office and roof deck', 9, '#8e44ad')
# buildings
rect(oy, 395, 485, 741, 771, '#f7f7f7', 'HALL 90 x 30')
rect(oy, 497, 542, 747, 771, '#eef3f7', 'COLD STORE + ICE\noffice + roof deck', fs=9)
text(oy, 400, 736, 'truck berths 22 m', 10, '#333')
text(oy, 400, 778, 'quay apron 9 m', 9, '#555')
rect(oy, 550, 606, 720, 775, '#dfe7f2', 'BUYERS\'\nPARKING', fs=10, stroke='#888')
rect(oy, 306, 392, 742, 778, '#e2e2e2', 'small-boat quay', fs=9, stroke='#aaa')
rect(oy, 316, 382, 782, 786, '#c9a36b'); text(oy, 316, 796, 'pontoon, 3 boats', 9)
# the ramp from the existing signal
line(oy, [(567, 676), (567, 692.5)], '#e67e22', 9 * K)
arc = [(547 + 20 * math.cos(a), 692.5 + 20 * math.sin(a)) for a in [i * math.pi / 16 for i in range(0, 9)]]
line(oy, arc + [(440, 712.5)], '#c0392b', 10 * K * 0.9, op=0.9)
line(oy, [(440, 712.5), (415, 712.5)], '#e8a59c', 10 * K * 0.9)
text(oy, 452, 716, 'ONE ramp, 5 % over ~125 m, with footway', 10, '#fff')
text(oy, 592, 654, 'EAST: main gate at the existing signal', 10, '#b35c00', bg=True)
text(oy, 405, 706, 'level landing', 9, '#a33')
for sx in (400, 600):
    rect(oy, sx - 2, sx + 2, 698, 712, '#8e44ad', None, stroke='#8e44ad')
text(oy, 606, 706, 'stairs', 9, '#8e44ad')
# coast road corner: one arc R 60
c = [(325, 672), (299, 672)] + [(299 - 60 * math.sin(a), 732 - 60 * math.cos(a)) for a in [math.radians(d) for d in range(0, 89, 8)]] + [(239.1, 730.1), (235.7, 839.7), (234, 900)]
line(oy, c, '#111', 2.2, dash='7,5')
text(oy, 222, 652, 'coast road corner: one even curve (dashed)', 9, '#111', bg=True)
viaduct(oy)
# the mainline moved south (schematic) and the new on-ramp
PTS = [(380, 838), (400, 830), (415.5, 824.1), (540, 800.9), (640, 771.8), (705, 730)]
def mz0(x):
    for (a, b), (c_, d) in zip(PTS, PTS[1:]):
        if a <= x <= c_: return b + (d - b) * (x - a) / (c_ - a)
    return PTS[-1][1]
def mz(x): return sum(mz0(min(max(x + k, 381), 704)) for k in range(-40, 41, 5)) / 17.0
def bump(x):
    u = max(0.0, min(1.0, (x - 400) / 60.0, (670 - x) / 90.0))
    return u * u * (3 - 2 * u)
line(oy, [(x, mz(x) + 18 * bump(x)) for x in range(400, 675, 5)], '#3b1f7a', 2.5, dash='9,5')
text(oy, 400, 868, 'expressway main line 16-20 m further south here (dashed)', 10, '#3b1f7a', bg=True)
rect(oy, 760, 870, 798, 900, '#cfe8c9', 'FERRIS WHEEL PARK\ntoday; may move south\n(or the wheel onto a roof)', fs=10, stroke='#4c8a3f', op=0.7, dash='5,3')
gx, gz = 585, mz(585) + 18 + 12
t = math.radians(3.9)
sx_, sz_ = 775.6, gz - (775.6 - gx) * math.tan(t)
on = [(gx, gz), (sx_, sz_)]
piz = gz - (850 - gx) * math.tan(t)
cx_, cz_ = sx_ - 80 * math.sin(t), sz_ - 80 * math.cos(t)
on += [(cx_ + 80 * math.sin(t + a), cz_ + 80 * math.cos(t + a)) for a in [math.radians(d) for d in range(5, 87, 6)]]
on += [(850, piz - 74.6), (850, 690)]
line(oy, on, '#d6336c', 5, dash='12,5')
text(oy, 600, 836, 'NEW on-ramp: straight, one curve, straight', 10, '#d6336c', bg=True)
text(oy, 700, 768, "today's on-ramp (the S)", 9, '#5b3f8f', bg=True)
line(oy, [(545, 780), (545, 818)], '#000', 1); text(oy, 550, 800, '~30 m of water', 9, '#000', bg=True)
text(oy, 618, 792, 'plain sea wall, fenced strip under the viaduct', 9, '#333', bg=True)
out.append('</g>')
y0 = oy + PH + 26
notes = ['ONE vehicle way down (the ramp); people also leave by the stairs, the footbridge or a boat. A second truck ramp would take the car park\'s place.',
         'Tan = new land: the west gap filled and the quay pushed out about 19 m along the whole shore, one straight line from the west gap to the east bank (x 270 to 720).',
         'East of the yard (x 610 to 720, under the viaduct) it is a plain vertical sea wall with a railing, not a working quay: fenced maintenance yard, a few parking bays, piers standing on land.',
         'The public car park is level with the dike road, so visitors never drive across the truck floor. Military base and harbour are not touched.',
         'The expressway piers are not drawn: they move with the main line. The new on-ramp joins about 55 m further west than today.',
         'The new on-ramp\'s curve touches the north edge of the ferris wheel park: the park can shift south a little to clear it.']
for i, n in enumerate(notes):
    out.append('<text x="%d" y="%d" font-size="12" fill="#222">- %s</text>' % (PAD, y0 + i * 19, n))
out.append('</svg>')
open(sys.argv[1], 'w').write('\n'.join(out))
