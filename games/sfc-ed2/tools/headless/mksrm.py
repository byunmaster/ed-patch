"""mksrm.py 입력.srm 출력.srm WRAMaddr=val[,..]  — 슬롯0 의 WRAM($0100~)를 고치고 체크섬(마지막 바이트: 슬롯 0x50C 바이트 합 ≡ 0)을 맞춘다. 시험 전용."""
import sys
b=bytearray(open(sys.argv[1],'rb').read())
for kv in sys.argv[3].split(','):
    a,v=kv.split('='); b[0x15+int(a,16)-0x100]=int(v,16)
s=sum(b[0x15:0x15+0x50B])&255
b[0x15+0x50B]=(-s)&255
open(sys.argv[2],'wb').write(b)
