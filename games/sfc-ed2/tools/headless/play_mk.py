# mk.py "spec" [T0]  tokens: u/d/l/r N (N tiles=12f) or N f (frames, e.g. d200f); A B X Y L R S(start) E(select) [xN repeat]; wN wait frames
import sys
K={'u':'up','d':'down','l':'left','r':'right'}
B={'A':'a','B':'b','X':'x','Y':'y','L':'l','R':'r','S':'start','E':'select'}
TILE=8
t=int(sys.argv[2]) if len(sys.argv)>2 else 10
out=[]
for tok in sys.argv[1].split():
    if tok[0] in K:
        s=tok[1:]
        n=int(s[:-1]) if s.endswith('f') else int(s)*TILE
        out.append(f"{t}:{n}:{K[tok[0]]}"); t+=n+2
    elif tok[0]=='w': t+=int(tok[1:])
    elif tok[0] in B:
        n=int(tok[1:]) if tok[1:] else 1
        for _ in range(n): out.append(f"{t}:6:{B[tok[0]]}"); t+=22
    else: raise SystemExit("bad "+tok)
print(",".join(out)); print("END",t,file=sys.stderr)
