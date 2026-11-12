"""원판 EXE 에서 우리가 코드·자료 자리로 돌린 구간을 **바깥에서 읽는 코드가 없는가** — 정적 게이트.

구간(ED3.EXE RAM): 커서 훅 R1·R2, 죽은 함수, SDK 오류 출력 함수 자리. 원판 ED3.EXE 코드·SLPS·PSX2·오버레이 `MD*.BIN` 에서
`j/jal` 표적 · `lui+addiu/ori/ld/st` 상수 · 분기 유입 · 절대 포인터 워드가 구간 안을 가리키면 실패한다(구간 자신 안의 참조는 제외).
🔴 양성 대조: 일부러 `jal` 하나를 구간 안으로 심은 버퍼를 같은 검사기에 먹여 **잡히는지** 먼저 본다 — 못 잡으면 빈 검사라 실패.
동적(실행 BP)은 별개다(devlog 11-07) — 이건 정적 절반이다.
"""

import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

REGIONS = {
    "R1 커서 훅": (0x8008A108, 0x8008A108 + 428),
    "R2 서브루틴": (0x8008A428, 0x8008A428 + 368),
    "SDK 오류 출력 자료": (0x8008CD94, 0x8008CD94 + 0x418),
    "죽은 함수": (0x8008DAD4, 0x8008DAD4 + 1092),
}
CODE_END = 0x84000  # ED3.EXE 코드 범위(이 뒤는 자료)


def _sx(v):
    return v - 0x10000 if v & 0x8000 else v


def _which(a):
    for k, (s, e) in REGIONS.items():
        if s <= a < e:
            return k
    return None


def scan(data, pcbase):
    """{구간: [(바이트 위치, 종류, 표적)]} — 구간 안에서 나온 참조는 뺀다."""
    hits = collections.defaultdict(list)
    lui = {}
    for i in range(len(data) // 4):
        w = struct.unpack_from("<I", data, i * 4)[0]
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        src = pcbase + i * 4
        if op in (2, 3):
            a = ((w & 0x3FFFFFF) << 2) | 0x80000000
            k = _which(a)
            if k and _which(src) != k:
                hits[k].append((src, "jal" if op == 3 else "j", a))
        if op == 0x0F:
            lui[rt] = (imm << 16, i)
            continue
        if (
            op in (9, 0x0D, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x28, 0x29, 0x2B)
            and rs in lui
            and i - lui[rs][1] <= 64
        ):
            a = (lui[rs][0] + (imm if op == 0x0D else _sx(imm))) & 0xFFFFFFFF
            k = _which(a)
            if k and _which(src) != k:
                hits[k].append((src, f"lui+{op:02x}", a))
            if op in (9, 0x0D):
                lui[rt] = (a, i)
            else:
                lui.pop(rt, None)
        elif op == 0:
            lui.pop((w >> 11) & 31, None)
        if op in (1, 4, 5, 6, 7):
            t = src + 4 + (_sx(imm) << 2)
            k = _which(t)
            if k and _which(src) != k:
                hits[k].append((src, "branch", t))
        k = _which(w)
        if k and op not in (2, 3) and _which(src) != k:
            hits[k].append((src, "word", w))
    return hits


# ── 옛 기준 상수 잔존 — 우리가 읽는 곳을 절대 주소로 바꾼 표 항목(데이터 창 제목 포인터 배열 10·11·13 · 경험치 제목 표 항목)
OLD_CONSTS = {0x801E4B90 + 4 * k: f"포인터 배열[{k}]" for k in (10, 11, 13)}
OLD_CONSTS[0x800B0A60] = "경험치 제목 표 항목"
EXPECT_ORIG = len(
    OLD_CONSTS
)  # 원판에서 읽는 곳이 정확히 이만큼(항목마다 하나) — 다르면 가정이 깨진 것이다


def old_const_uses(data, pcbase):
    """`lui` 뒤 모든 사용(분기·지연 슬롯을 넘어서 — 같은 `lui` 를 두 갈래가 나눠 써도) 중 옛 기준 상수로 풀리는 곳."""
    out, lui = [], {}
    for i in range(len(data) // 4):
        w = struct.unpack_from("<I", data, i * 4)[0]
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op == 0x0F:
            lui[rt] = (imm << 16, i)
            continue
        if (
            op in (9, 0x0D, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x28, 0x29, 0x2B)
            and rs in lui
            and i - lui[rs][1] <= 200
        ):
            a = (lui[rs][0] + (imm if op == 0x0D else _sx(imm))) & 0xFFFFFFFF
            if a in OLD_CONSTS:
                out.append((pcbase + i * 4, OLD_CONSTS[a]))
            if op in (9, 0x0D):
                lui[rt] = (a, i)
            elif op != 0x2B and op < 0x28:
                lui.pop(rt, None)
        elif op == 0:
            lui.pop((w >> 11) & 31, None)
    return out


def check_old_consts(built):
    lba, sz = common.iso_files("ed3")["/ED3.EXE"]
    o = old_const_uses(common.read_lba("ed3", lba, sz)[0x800 : 0x800 + CODE_END], 0x80010000)
    tree, _ = common.iso_tree(built)
    lba, sz = tree["/ED3.EXE"]
    b = old_const_uses(
        common.read_lba("ed3", lba, sz, path=built)[0x800 : 0x800 + CODE_END], 0x80010000
    )
    ok = len(o) == EXPECT_ORIG and not b
    print(
        f"옛 기준 상수 잔존 [ed3] — 원판 읽는 곳 {len(o)}(기대 {EXPECT_ORIG}) · 제품 잔존 {len(b)}"
    )
    for pc, nm in b:
        print(f"  🔴 {pc:#x} 가 아직 {nm} 를 읽는다")
    return 0 if ok else 1


def selftest():
    """양성 대조 — 구간 밖에서 구간 안으로 `jal` · `lui+ori` 를 심으면 둘 다 잡혀야 한다."""
    s = REGIONS["죽은 함수"][0] + 8
    buf = struct.pack("<I", (3 << 26) | ((s & 0x0FFFFFFF) >> 2))
    buf += struct.pack("<I", (0x0F << 26) | (4 << 16) | (s >> 16))
    buf += struct.pack("<I", (0x0D << 26) | (4 << 21) | (4 << 16) | (s & 0xFFFF))
    h = scan(buf, 0x80020000)
    return len(h.get("죽은 함수", [])) == 2


def main():
    rc = 0
    if "--built" in sys.argv:
        rc = check_old_consts(sys.argv[sys.argv.index("--built") + 1])
    if not selftest():
        print("🔴 check_free_refs: 양성 대조 실패 — 심은 참조를 못 잡는다(빈 검사)")
        return 1
    iso = common.iso_files("ed3")
    found = collections.defaultdict(list)
    n_scanned = 0

    def run(label, data, pcbase):
        nonlocal n_scanned
        n_scanned += 1
        for k, v in scan(data, pcbase).items():
            for x in v:
                found[k].append((label,) + x)

    lba, sz = iso["/ED3.EXE"]
    d = common.read_lba("ed3", lba, sz)
    run("/ED3.EXE", d[0x800 : 0x800 + CODE_END], 0x80010000)
    for p in ("/SLPS_012.01", "/PSX2.EXE"):
        lba, sz = iso[p]
        run(p, common.read_lba("ed3", lba, sz)[0x800:], 0x80010000)
    for p, (lba, sz) in sorted(iso.items()):
        if not p.endswith(".DAT"):
            continue
        d = common.read_lba("ed3", lba, sz)
        try:
            ents = common.arc_parse(d)[1]
        except common.ArchiveError:
            continue
        for nm, off, s in ents:
            if nm.replace("\\", "/").split("/")[-1].startswith("MD"):
                run(p + "!" + nm, d[off : off + s], 0)
    bad = {k: v for k, v in found.items() if v}
    # 오버레이는 올라오는 자리를 몰라 분기 유입을 뺀 나머지(j/jal·상수·포인터)만 믿는다 — pcbase=0 이라 branch 는 구간 밖 표적
    bad = {
        k: [x for x in v if x[2] != "branch" or x[0] in ("/ED3.EXE", "/SLPS_012.01", "/PSX2.EXE")]
        for k, v in bad.items()
    }
    bad = {k: v for k, v in bad.items() if v}
    tot = sum(len(v) for v in bad.values())
    print(
        f"원판 EXE 재사용 구간 바깥 참조 [ed3] — 구간 {len(REGIONS)} · 훑은 파일 {n_scanned} · 바깥 참조 {tot}"
    )
    for k, v in bad.items():
        for x in v[:5]:
            print(f"  🔴 {k}: {x[0]} @{x[1]:#x} {x[2]} → {x[3]:#x}")
    return 1 if (tot or rc) else 0


if __name__ == "__main__":
    sys.exit(main())
