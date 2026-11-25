import sys,struct,glob,re
def parse(path):
    b=open(path,'rb').read()
    def sec(name,expect):
        pos=0
        while True:
            i=b.find(name+b'\x00',pos)
            if i<0: raise SystemExit('no '+str(name))
            j=i+len(name)
            n=struct.unpack('<I',b[j:j+4])[0]
            if n==expect: return b[j+4:j+4+n]
            pos=i+1
    return dict(cd=sec(b'SysCardRAM',196608)+sec(b'CDRAM',65536), vram=sec(b'VRAM',65536), ram=sec(b'RAM',8192))
files=sorted(glob.glob('/tmp/claude-0/ramsurvey/*.state'))
S=[(f.split('/')[-1][:-6],parse(f)) for f in files]
print(len(S),'snapshots', [ (n,len(d['cd']),len(d['vram']),len(d['ram'])) for n,d in S][:2])
def runs(mask,minlen):
    out=[];i=0;n=len(mask)
    while i<n:
        if mask[i]:
            j=i
            while j<n and mask[j]: j+=1
            if j-i>=minlen: out.append((i,j-i))
            i=j
        else: i+=1
    return out
for key,base,label in (('cd',0x68*0x2000,'CD-RAM(뱅크0x68~0x87)'),('vram',0,'VRAM(바이트)'),('ram',0,'기본RAM')):
    a=S[0][1][key]; n=len(a)
    same=bytearray(1 for _ in range(n))
    for _,d in S[1:]:
        x=d[key]
        for i in range(n):
            if x[i]!=a[i]: same[i]=0
    # also require value 00 or FF? report both: unchanged any value, and unchanged zero/FF
    z=[1 if (same[i] and a[i] in (0,0xFF)) else 0 for i in range(n)]
    tot=sum(z); print(label,'모든 스냅 동일+00/FF 바이트',tot,'/',n)
    for mn in (64,256,1024,4096):
        r=runs(z,mn); print('  연속 >=%d: %d 구간, 합 %d바이트'%(mn,len(r),sum(l for _,l in r)))
    big=sorted(runs(z,256),key=lambda t:-t[1])[:12]
    for off,l in big:
        adr = base+off if key=='cd' else off
        bank=(base+off)//0x2000 if key=='cd' else None
        print('   %s 오프 0x%X 크기 %d%s'%(label[:2],adr,l, (' 뱅크 0x%X+0x%X'%(bank,(base+off)%0x2000)) if bank is not None else ''))
