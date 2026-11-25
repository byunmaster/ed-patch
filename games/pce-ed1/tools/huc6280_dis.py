"""HuC6280(6502+65C02+PCE 전용 일부) 디스어셈블러 — 손인코딩 기계어·원판 할당기(`$5501`, rel 36 +0x4D0 = 논리 `$5501`) 읽기·검산용(빌드 규율: 손인코딩 기계어는 디스어셈블로 검산).

  python3 tools/huc6280_dis.py <rel> <논리 시작 주소> <시작 오프셋> <끝 오프셋>   # 데이터 트랙의 섹터 rel 부터 읽는다
모르는 옵코드는 `.db` 로 낸다(전수 표가 아니다 — 쓰는 것만).
"""

import sys

M={'imp':0,'imm':1,'zp':1,'zpx':1,'zpy':1,'abs':2,'abx':2,'aby':2,'ind':2,'inx':1,'iny':1,'rel':1,'zpi':1,'ain':2,'tst_z':2,'tst_a':3,'bbr':2,'ims':2}
ops={}
def add(b,m,mode): ops[b]=(m,mode)
for base,m in ((0x00,'ORA'),(0x20,'AND'),(0x40,'EOR'),(0x60,'ADC'),(0x80,'STA'),(0xA0,'LDA'),(0xC0,'CMP'),(0xE0,'SBC')):
    for off,mode in ((0x09,'imm'),(0x05,'zp'),(0x15,'zpx'),(0x0D,'abs'),(0x1D,'abx'),(0x19,'aby'),(0x01,'inx'),(0x11,'iny'),(0x12,'zpi')):
        if m=='STA' and off==0x09: continue
        add(base+off,m,mode)
for b,m in ((0x0A,'ASL'),(0x4A,'LSR'),(0x2A,'ROL'),(0x6A,'ROR')): add(b,m,'imp')
for base,m in ((0x00,'ASL'),(0x20,'ROL'),(0x40,'LSR'),(0x60,'ROR'),(0xC0,'DEC'),(0xE0,'INC')):
    for off,mode in ((0x06,'zp'),(0x16,'zpx'),(0x0E,'abs'),(0x1E,'abx')): add(base+off+0,m,mode)
for b,m,mode in ((0xA2,'LDX','imm'),(0xA6,'LDX','zp'),(0xB6,'LDX','zpy'),(0xAE,'LDX','abs'),(0xBE,'LDX','aby'),(0xA0,'LDY','imm'),(0xA4,'LDY','zp'),(0xB4,'LDY','zpx'),(0xAC,'LDY','abs'),(0xBC,'LDY','abx'),(0x86,'STX','zp'),(0x96,'STX','zpy'),(0x8E,'STX','abs'),(0x84,'STY','zp'),(0x94,'STY','zpx'),(0x8C,'STY','abs'),(0xE0,'CPX','imm'),(0xE4,'CPX','zp'),(0xEC,'CPX','abs'),(0xC0,'CPY','imm'),(0xC4,'CPY','zp'),(0xCC,'CPY','abs'),(0x24,'BIT','zp'),(0x2C,'BIT','abs'),(0x89,'BIT','imm'),(0x34,'BIT','zpx'),(0x3C,'BIT','abx'),
 (0x4C,'JMP','abs'),(0x6C,'JMP','ind'),(0x7C,'JMP','ain'),(0x20,'JSR','abs'),(0x60,'RTS','imp'),(0x40,'RTI','imp'),(0x44,'BSR','rel'),(0x80,'BRA','rel'),(0x90,'BCC','rel'),(0xB0,'BCS','rel'),(0xF0,'BEQ','rel'),(0xD0,'BNE','rel'),(0x30,'BMI','rel'),(0x10,'BPL','rel'),(0x50,'BVC','rel'),(0x70,'BVS','rel'),
 (0x18,'CLC','imp'),(0x38,'SEC','imp'),(0x58,'CLI','imp'),(0x78,'SEI','imp'),(0xD8,'CLD','imp'),(0xF8,'SED','imp'),(0xB8,'CLV','imp'),(0x48,'PHA','imp'),(0x68,'PLA','imp'),(0x08,'PHP','imp'),(0x28,'PLP','imp'),(0xDA,'PHX','imp'),(0xFA,'PLX','imp'),(0x5A,'PHY','imp'),(0x7A,'PLY','imp'),(0xAA,'TAX','imp'),(0xA8,'TAY','imp'),(0x8A,'TXA','imp'),(0x98,'TYA','imp'),(0xBA,'TSX','imp'),(0x9A,'TXS','imp'),(0xE8,'INX','imp'),(0xC8,'INY','imp'),(0xCA,'DEX','imp'),(0x88,'DEY','imp'),(0xEA,'NOP','imp'),(0x1A,'INC','imp'),(0x3A,'DEC','imp'),(0x62,'CLA','imp'),(0x82,'CLX','imp'),(0xC2,'CLY','imp'),(0x64,'STZ','zp'),(0x74,'STZ','zpx'),(0x9C,'STZ','abs'),(0x9E,'STZ','abx'),(0x53,'TAM','imm'),(0x43,'TMA','imm'),(0x03,'ST0','imm'),(0x13,'ST1','imm'),(0x23,'ST2','imm'),(0xD4,'CSH','imp'),(0x54,'CSL','imp'),(0xF4,'SET','imp'),(0x0F,'BBR0','bbr'),(0x4F,'BBR4','bbr'),(0x8F,'BBS0','bbr'),(0x83,'TST','tst_z'),(0x93,'TST','tst_a'),(0xA3,'TST','tst_zx'),(0xB3,'TST','tst_ax'),(0x73,'TII','ims'),(0xE3,'TIA','ims'),(0xF3,'TAI','ims'),(0xC3,'TDD','ims'),(0xD3,'TIN','ims'),(0x04,'TSB','zp'),(0x0C,'TSB','abs'),(0x14,'TRB','zp'),(0x1C,'TRB','abs')):
    ops[b]=(m,mode)
def dis(buf,base,start,end):
    i=start
    while i<end:
        b=buf[i]; a=base+i
        if b not in ops: print(f'{a:04X}: {b:02X}         .db'); i+=1; continue
        m,mode=ops[b]; n={'imp':0,'imm':1,'zp':1,'zpx':1,'zpy':1,'abs':2,'abx':2,'aby':2,'ind':2,'ain':2,'inx':1,'iny':1,'rel':1,'zpi':1,'bbr':2,'tst_z':2,'tst_a':3,'tst_zx':2,'tst_ax':3,'ims':6}[mode]
        raw=buf[i:i+1+n]; v=raw[1:]
        if mode=='imp': op=''
        elif mode=='imm': op=f'#${v[0]:02X}'
        elif mode=='zp': op=f'${v[0]:02X}'
        elif mode=='zpx': op=f'${v[0]:02X},X'
        elif mode=='zpy': op=f'${v[0]:02X},Y'
        elif mode=='abs': op=f'${v[1]<<8|v[0]:04X}'
        elif mode=='abx': op=f'${v[1]<<8|v[0]:04X},X'
        elif mode=='aby': op=f'${v[1]<<8|v[0]:04X},Y'
        elif mode=='ind': op=f'(${v[1]<<8|v[0]:04X})'
        elif mode=='ain': op=f'(${v[1]<<8|v[0]:04X},X)'
        elif mode=='inx': op=f'(${v[0]:02X},X)'
        elif mode=='iny': op=f'(${v[0]:02X}),Y'
        elif mode=='zpi': op=f'(${v[0]:02X})'
        elif mode=='rel': t=a+2+(v[0]-256 if v[0]>127 else v[0]); op=f'${t:04X}'
        elif mode=='bbr': t=a+3+(v[1]-256 if v[1]>127 else v[1]); op=f'${v[0]:02X},${t:04X}'
        elif mode=='tst_z': op=f'#${v[0]:02X},${v[1]:02X}'
        elif mode=='tst_a': op=f'#${v[0]:02X},${v[2]<<8|v[1]:04X}'
        elif mode=='tst_zx': op=f'#${v[0]:02X},${v[1]:02X},X'
        elif mode=='tst_ax': op=f'#${v[0]:02X},${v[2]<<8|v[1]:04X},X'
        elif mode=='ims': op=f'${v[1]<<8|v[0]:04X},${v[3]<<8|v[2]:04X},${v[5]<<8|v[4]:04X}'
        print(f'{a:04X}: {" ".join(f"{x:02X}" for x in raw):<18} {m} {op}')
        i+=1+n


if __name__ == "__main__":
    import common

    rel, base, a, b = int(sys.argv[1]), int(sys.argv[2], 16), int(sys.argv[3], 16), int(sys.argv[4], 16)
    dis(common.track_data(rel, 8), base, a, b)
