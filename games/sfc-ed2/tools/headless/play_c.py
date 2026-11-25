#!/usr/bin/env python3
# c.py "spec" "shots" REL [extra]  -> 명령 보내고 끝날 때까지 기다린 뒤 샷을 한 장(sheet)으로
import sys,os,subprocess,time,glob
from PIL import Image

spec,shots,rel=sys.argv[1:4]; extra=sys.argv[4] if len(sys.argv)>4 else ""
script=subprocess.run([sys.executable,SC+'/play_mk.py',spec,'4'],capture_output=True,text=True).stdout.strip()
end=subprocess.run([sys.executable,SC+'/play_mk.py',spec,'4'],capture_output=True,text=True).stderr.split()
if rel=='auto': rel=str(int(end[-1])+30 if end else 60)
shots=shots.replace('end',str(int(rel)-1))
if os.path.exists(O+'/done.txt'): os.remove(O+'/done.txt')
n0=len(glob.glob(O+'/c*_*.png'))
open(O+'/cmd.tmp','w').write(f"{script}\n{shots}\n{rel}\n{extra}\n"); os.rename(O+'/cmd.tmp',O+'/cmd.txt')
t=time.time()
while True:
    time.sleep(0.3)
    if os.path.exists(O+'/done.txt'): break
    if time.time()-t>500: print("timeout"); sys.exit(1)
time.sleep(0.2)
fs=sorted(glob.glob(O+'/c*_*.png'),key=os.path.getmtime)[-len([x for x in shots.split(',') if x]):] if shots else []
if fs:
    ims=[Image.open(f) for f in fs]; w,h=ims[0].size; c=min(3,len(ims)); r=(len(ims)+c-1)//c
    S=Image.new('RGB',(w*c,h*r))
    for i,im in enumerate(ims): S.paste(im,((i%c)*w,(i//c)*h))
    if len(ims)<=2: S=S.resize((S.width*2,S.height*2))
    S.save(O+'/sheet.png')
print(open(O+'/done.txt').read(), [os.path.basename(f) for f in fs])
