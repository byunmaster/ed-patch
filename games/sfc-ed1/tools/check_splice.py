#!/usr/bin/env python3
"""공유 꼬리 이음 검사 — 분기($FA)·호출($FC) 목표가 **문장 한가운데**(직전 항목이 개행 아닌 글자·사전·치환)로 들어가는 진입점을 전수로 세고,
번역문이 그 자리에 `<@>` 라벨을 두었는지 본다(PCE I 에서 라벨 없는 진입이 이음 어미가 깨지는 부류로 나왔다, 관리자 11-06).

  python3 tools/check_splice.py                # 개수·라벨 누락만(게이트)
  python3 tools/check_splice.py --table X.tsv  # 진입점마다 「원판 이어 읽기 | 우리 이어 읽기」 표(사람이 읽는다)

개행 바로 뒤로 들어가는 진입(화자 머리 뒤 본문 등)은 문장 한가운데가 아니라서 세지 않는다. 라벨이 없으면 실패한다. 읽기 자체는 표를 사람이 읽는다.
"""
import sys,re,json,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import common,script,units
import importlib.util as iu
sp=iu.spec_from_file_location('sfctext',Path(__file__).with_name('text.py'));t=iu.module_from_spec(sp);sp.loader.exec_module(t)
rom=common.rom_bytes()
items,_u=units.extract(rom)
res=t.resolver(rom)
targets={tg for it in items for tg in it.targets}
BRK={0xE0,0xE4,0xFF,0xFE,0xEF,0xFA,0xF9,0xFC,0xFD,0xE3}
# 조각 범위
rng=[];st=0
for k,it in enumerate(items):
    if k and common.off2snes(it.off)>>16!=common.off2snes(items[k-1].off)>>16:
        rng.append((st,k));st=k
    if it.kind=='ctrl' and it.code in (0xE0,0xE4):
        rng.append((st,k+1));st=k+1
if st<len(items): rng.append((st,len(items)))
import hashlib
seg_of={}
for a,b in rng:
    raw=b''.join(bytes([x.code])+x.args for x in items[a:b])
    for i in range(a,b): seg_of[i]=(a,b,hashlib.sha1(raw).hexdigest()[:12])
idx={it.off:i for i,it in enumerate(items)}
KR=json.load(open(common.GAME_DIR/'textmap'/'segments.json',encoding='utf-8'))
TOK=re.compile(r"<[0-9A-F]{2}(?::[0-9A-F]+)?>|<@>")
def dec(a,b):
    r=''
    for it in items[a:b]:
        if it.kind=='char': r+=('⏎' if it.code==0xCF else t.TABLE.get(it.code,'?'))
        elif it.kind=='ctrl':
            r+= '⏎' if it.code==0xCF else ''
        elif it.kind=='dict': r+='{D%X:%02X}'%(it.code,it.args[0])
        else: r+='{S%X}'%it.code
    return r
# 진입점: 목표 항목 i, 직전 항목이 글자/사전/치환
entries=collections.defaultdict(list)  # tg -> [(src_idx, code)]
for si,it in enumerate(items):
    if it.kind!='ctrl' or it.code not in (0xFA,0xFC): continue
    for k,tg in enumerate(it.targets):
        if k in it.dead or tg not in idx: continue
        ti=idx[tg]
        if ti and items[ti].kind=='char' and (items[ti-1].kind in('dict','subst') or (items[ti-1].kind=='char' and items[ti-1].code!=0xCF)):
            entries[tg].append((si,it.code))
def kr_pieces(seg_id):
    return KR.get(seg_id,{}).get('kr')
def toks_pos(kr):
    return [(m.start(),m.end(),m.group(0)) for m in TOK.finditer(kr)]
rows=[]
for tg,srcs in sorted(entries.items()):
    ti=idx[tg]; a,b,sid=seg_of[ti]
    kind=items[ti-1].kind
    # 같은 조각의 진입 라벨 순서(글자 뒤 글자 목표)
    labs=[j for j in range(a+1,b) if items[j].off in targets and items[j].kind=='char' and items[j-1].kind=='char']
    li=labs.index(ti) if ti in labs else -1
    # 꼬리 원판
    e=ti
    while e<b and not(items[e].kind=='ctrl' and items[e].code in BRK): e+=1
    jp_tail=dec(ti,e)
    krt=kr_pieces(sid)
    if krt is None: kr_tail='(번역 없음)'
    elif li<0: kr_tail='(라벨 대상 아님: 앞이 사전/치환)'
    else:
        tp=toks_pos(krt); lab=[x for x in tp if x[2]=='<@>']
        if li>=len(lab): kr_tail='(<@> 없음)'
        else:
            pos=lab[li][1]; m=re.compile(r"<(?:E0|E4|FF|FE|EF|FA|F9|FC|FD|E3)(?::[0-9A-F]+)?>").search(krt,pos)
            kr_tail=krt[pos:m.start() if m else len(krt)].replace('\n','⏎')
    for si,code in srcs:
        sa,sb,ssid=seg_of[si]
        s0=si
        while s0>sa and not(items[s0-1].kind=='ctrl' and items[s0-1].code in BRK): s0-=1
        jp_pre=dec(s0,si)
        skr=kr_pieces(ssid)
        if skr is None: kr_pre='(번역 없음)'
        else:
            # 이 점프가 조각 안에서 몇 번째 토큰인가
            n=0
            for j in range(sa,si):
                if items[j].kind=='ctrl': n+=1
                if items[j].off in targets and items[j].kind=='char' and j>sa and items[j-1].kind=='char': n+=1
            tp=toks_pos(skr)
            if n<len(tp):
                st_,en_,tk=tp[n]
                # 직전 끊김 토큰
                pb=0
                for q in range(n-1,-1,-1):
                    if re.match(r"<(?:E0|E4|FF|FE|EF|FA|F9|FC|FD|E3)(?::[0-9A-F]+)?>",tp[q][2]): pb=tp[q][1];break
                kr_pre=skr[pb:st_].replace('\n','⏎')
                if not tk.startswith('<F'): kr_pre+=f' (토큰 어긋남:{tk})'
            else: kr_pre='(토큰 수 어긋남)'
    # 마지막 행
        rows.append(dict(entry=f"{common.off2snes(tg):06X}",src=f"{common.off2snes(items[si].off):06X}",code=f"{code:02X}",prev=kind,
              label=('있음' if li>=0 and not kr_tail.startswith('(') else ('없음' if li>=0 else '해당없음')),
              jp=f"{jp_pre} | {jp_tail}",kr=f"{kr_pre} | {kr_tail}"))
import argparse
ap=argparse.ArgumentParser();ap.add_argument("--table");a=ap.parse_args()
if a.table:
    with open(a.table,'w',encoding='utf-8') as f:
        f.write("진입\t점프원\t코드\t직전\t라벨\t원판 이어 읽기\t우리 이어 읽기\n")
        for r in rows: f.write("\t".join([r['entry'],r['src'],r['code'],r['prev'],r['label'],r['jp'],r['kr']])+"\n")
bad=[r for r in rows if r['label']!='있음' or '<@> 없음' in r['kr']]
nt=sum(1 for r in rows if r['kr'].startswith('(번역 없음)') or ' | (번역 없음)' in r['kr'])
print(f"공유 꼬리 이음: 문장 한가운데 진입 {len(set(r['entry'] for r in rows))}곳({len(rows)}사이트) · 번역문 `<@>` 라벨 누락 {len(bad)}")
for r in bad[:10]: print("   ",r['entry'],r['src'],r['label'])
sys.exit(1 if bad else 0)
