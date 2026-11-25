"""옮기거나 비운 원판 문자열 칸을 **읽는 코드**가 있나 — 정적 후보 검색(11-07, 퀵메뉴 표 사건 뒤).

원판 코드(뱅크 0x68~0x71) 안에서 같은 뱅크의 읽기 계열 명령(LDA·LDX·LDY·CMP·ORA·AND·EOR·ADC·SBC abs, abs,X/Y)의 피연산자가 `prog_writes.tsv` 의
「prog vacated」·제자리 고친 literal 칸을 가리키면 후보로 낸다. 후보는 **데이터 속 우연한 바이트 열**도 섞여(디스어셈 대조 필요) 게이트가 아니라 조사 도구다.
11-07 결과: 후보 중 진짜는 `6A+00F2 LDX $6282,Y`(퀵메뉴 위치→항목 표) 하나였고 `layout.PINNED_DATA` 로 막았다. 나머지 셋(70+0609 · 70+178A · 70+1CB4)은 명령 경계가 아닌 우연 일치.
실행: `python3 games/pce-ed2/tools/audit_string_readers.py` (제품 롬 `work/build/pce-ed2/ed2.iso` 와 `work/review/prog_writes.tsv` 필요)."""

import sys, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common, layout

O = bytes(common.track_data(130, 12 * 8192 // 2048))
spans = [
    l.rstrip("\n").split("\t")
    for l in open(str(common.GAME_DIR / "work" / "review" / "prog_writes.tsv"))
    if not l.startswith("#")
]
base = 130 * 2048


def bank_off(lin):
    r = lin - base
    return 0x68 + r // 8192, r % 8192


rng = []
for s in spans:
    if (
        s[0] == "prog vacated"
        or s[0].startswith("prog literal")
        and "(moved)" not in s[0]
        and "ref" not in s[0]
        and "tail" not in s[0]
        and "far" not in s[0]
    ):
        lin, ln = int(s[1]), int(s[2])
        b, o = bank_off(lin)
        if b < 0x72 and lin < base + 12 * 8192:
            rng.append((b, o, ln, s[0]))
rng = sorted(set(rng))
IDX = {
    0xBD,
    0xB9,
    0xBE,
    0xBC,
    0xDD,
    0xD9,
    0x7D,
    0x79,
    0x3D,
    0x39,
    0x1D,
    0x19,
    0x5D,
    0x59,
    0xFD,
    0xF9,
}  # 읽기 계열 인덱스
DIR = {
    0xAD,
    0xAE,
    0xAC,
    0xCD,
    0xEC,
    0xCC,
    0x2D,
    0x0D,
    0x4D,
    0x6D,
    0xED,
}  # 읽기 계열만(STA/STX/STY·BIT 제외)
JMP = {0x20, 0x4C}
res = {}
for b, o, ln, lab in rng:
    lo = 0x6000 + o
    hi = lo + ln
    hits = []
    for bb in (
        b,
    ):  # 같은 뱅크 코드만(MPR3 에 그 뱅크가 올라온 상태) — 다른 뱅크에서의 접근은 따로 본다
        d = O[(bb - 0x68) * 8192 : (bb - 0x67) * 8192]
        for i in range(len(d) - 2):
            op = d[i]
            a = d[i + 1] | d[i + 2] << 8
            if op in IDX and lo <= a < hi:
                hits.append((bb, i, hex(op), hex(a), "idx"))
            elif op in DIR and op != 0x2C and lo <= a < hi:
                hits.append((bb, i, hex(op), hex(a), "dir"))
    res[(b, o, ln, lab)] = hits
tot = 0
for k, v in res.items():
    if v:
        tot += 1
        print(
            f"{k[0]:02X}+{k[1]:04X} len{k[2]} [{k[3][:28]}]",
            [(f"{x[0]:02X}+{x[1]:04X}", x[2], x[3], x[4]) for x in v][:5],
        )
print("ranges", len(res), "with candidate operand", tot)


def ud(path, lin, n):
    f = open(path, "rb")
    out = b""
    pos = lin
    while pos < lin + n:
        sec = pos // 2048
        off = pos % 2048
        take = min(lin + n - pos, 2048 - off)
        f.seek((common.T2_SECTOR + sec) * common.RAW + common.USER_OFF + off)
        out += f.read(take)
        pos += take
    return out


P = ud(str(common.GAME_DIR / "work" / "build" / "pce-ed2" / "ed2.iso"), base, 12 * 8192)
print("--- 읽기 대상 바이트가 롬에서 바뀌었나(원판 대 제품)")
seen = set()
for k, v in res.items():
    b0, o0 = k[0], k[1]
    for bb, i, op, a, kind in v:
        a = int(a, 16) - 0x6000
        # 대상 뱅크는 k[0] (문자열이 사는 뱅크) — 읽는 쪽은 그 뱅크가 MPR3 에 올라온 상태로 본다
        ob = O[(k[0] - 0x68) * 8192 + a : (k[0] - 0x68) * 8192 + a + (1 if kind == "dir" else 24)]
        pb = P[(k[0] - 0x68) * 8192 + a : (k[0] - 0x68) * 8192 + a + (1 if kind == "dir" else 24)]
        if ob != pb and (k[0], a, kind, bb, i) not in seen:
            seen.add((k[0], a, kind, bb, i))
            print(
                f"읽는 코드 {bb:02X}+{i:04X} {op} → 대상 {k[0]:02X}+{a:04X}({kind}) 원판 {ob.hex()} / 제품 {pb.hex()}"
            )
