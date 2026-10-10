"""전투 문구 복사의 **고정 길이**를 우리 문안 길이로 늘린다 — 직전 창 글자가 비치는 결함.

    python3 tools/patch_msgcopy.py --list     # 자리 목록(원본 N · 우리 길이)
    python3 tools/patch_msgcopy.py            # 조립·검산만
    python3 tools/patch_msgcopy.py --apply    # 빌드 이미지에 넣는다

## 무엇이 문제였나 (2026-10-09 마스터 QA 캡처 → 원본 JP 와 대조)

몬스터 등장 문구(「…가 나타났다.」·「…의 무리가 …」) 뒤에 **직전 창의 글자**가 비쳤다:

    슬라임버브의 무리가              캐리온크롤러가 나타났h요?
    나타났다. 습니다.

원인은 **메시지 적재 루틴이 길이를 상수로 박은 `memcpy`** 다. 문구마다 `mov #N,r6 · jsr memcpy`
(ED 0x0605BA00~0x0605C3B0 한 함수 · 75 갈래) 인데 **N = 원문 일본어 바이트 + NUL** 이다:

    원본  `キャリオンクローラーが現れた。`  (반각 가나 1B)  = 20B + NUL = 21
    우리  `캐리온크롤러가 나타났다.`                       = 24B + NUL = 25   → 21B 만 복사된다

잘린 뒤는 **목적지 버퍼(0x060BE310)에 이미 있던 이전 메시지**가 이어진다 — 종단이 안 들어가니
그 꼬리까지 화면에 나간다. 이전 메시지가 **우연히 같은 문구**였을 땐 안 보여서 QA 를 몇 바퀴 돌아도
간헐로만 나왔다(회심 복사 「7격」과 같은 계통 — `patch_crit_copy.py`).

## 고침

복사 상수 N 을 **우리 문안 길이+NUL** 로 늘린다(`mov #N,r6` 한 명령). 소스 리터럴이 우리가 옮긴 문안을 가리키는
자리만 고르므로(정본 표의 포인터) 데이터 복사는 안 건드린다. N 은 늘리기만 한다(원본이 더 길면 그대로).
⚠ **`strcpy` 로 바꾸지 않았다** — 같은 `memcpy` 를 쓰는 다른 자리와 **풀 리터럴을 공유**해 한꺼번에
바뀌고, 데이터 복사(0 을 품은 것)를 깰 수 있다. 상수 한 칸씩이 국소적이다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

LOAD_BASE = 0x06028000
# `memcpy(r4 dest, r5 src, r6 len)` — 첫 24B 시그니처(두 편 같다). 자리는 시그니처로 찾는다.
MEMCPY_SIG = bytes.fromhex("6343e00036008946e00c36078b3e605b7004c90320088907")
WINDOW = 8  # 길이 상수 앞 이 안(명령 수)에 소스·memcpy 적재가 모인다
FILES = ["/ED.BIN", "/ED2.BIN"] + [f"/BIN/ED2MON{i:02d}.BIN" for i in range(1, 11)]


def memcpy_addr(d):
    i = d.find(MEMCPY_SIG)
    assert i >= 0 and d.find(MEMCPY_SIG, i + 1) < 0, "memcpy 시그니처가 하나여야 한다"
    return LOAD_BASE + i


def _lit(d, base, pc, w):
    a = ((base + pc + 4) & ~3) + (w & 0xFF) * 4
    o = a - base
    return int.from_bytes(d[o : o + 4], "big") if 0 <= o <= len(d) - 4 else None


def sites(d, base, mc, strs):
    """`[(길이 상수 오프셋, N, 소스 주소, 우리 길이+NUL)]` — 소스가 우리 문안(`strs` 의 주소)인 자리만.

    한 갈래는 `[r4 목적지][r5 소스][r1 memcpy] bra/jsr · mov #N,r6` 꼴이다. 그래서 길이 상수
    `mov #N,r6`(0xE6NN) **앞** `WINDOW` 명령 안에서 ① r1 에 `memcpy` 를 적재하고 ② r5 에 `strs` 안의 리터럴을
    적재한 자리만 센다 — **앞쪽 가장 가까운** r5 가 이 갈래의 것이다(뒤쪽은 다음 갈래다).
    ⚠ N < 9 는 거른다(문구 복사의 최소는 9 — 작은 상수는 다른 자리의 데이터 복사와 우연히 겹친다).
    """
    out = []
    n = len(d)
    for pc in range(0, n - 2, 2):
        w = (d[pc] << 8) | d[pc + 1]
        if (w & 0xFF00) != 0xE600 or (w & 0xFF) < 9:  # mov #imm,r6
            continue
        has_mc, src = False, None
        for q in range(pc - 2, max(-2, pc - 2 * WINDOW), -2):
            x = (d[q] << 8) | d[q + 1]
            if (x & 0xF000) != 0xD000:
                continue
            v = _lit(d, base, q, x)
            if (x & 0x0F00) == 0x0100 and v == mc:
                has_mc = True
            if (x & 0x0F00) == 0x0500 and v in strs and src is None:
                src = v
        if not has_mc or src is None:
            continue
        o = src - base
        z = bytes(d[o : o + 200]).find(0)
        if z < 0:
            continue
        out.append((pc, w & 0xFF, src, z + 1))
    return out


def plan(fname, d, strs):
    """`(자리 목록, 고칠 것 [(오프셋, 새 N)])` — N 이 모자란 자리만."""
    import patch_ui as U

    base = U.ptr_base(fname)
    mc = memcpy_addr(common.extract("/ED2.BIN" if fname != "/ED.BIN" else "/ED.BIN"))
    rows = sites(d, base, mc, strs)
    fix = []
    for pc, n, src, need in rows:
        if need > n:
            assert need <= 127, f"{fname}: {need}B 는 `mov #imm` 범위(127)를 넘는다"
            fix.append((pc, need))
    return rows, fix


def text_starts(fname, d):
    """우리가 쓴 문안(시스템 정본)의 시작 주소 집합 — 빌드 이미지 기준."""
    import patch_ui as U

    base = U.ptr_base(fname)
    _f, mm = common.open_image()
    out = set()
    for p, _l, _s, _at, _sp, pre, _kr, ptrs, _jp in U.sys_rows(mm):
        if p != fname or not ptrs:
            continue
        for q in ptrs:
            v = int.from_bytes(d[q : q + 4], "big")
            out.add(v + len(pre) if False else v)  # 포인터는 앞 바이트 앞을 가리킨다 — 그대로 둔다
    mm.close()
    return out


def verify(dst, files):
    """되읽기 — 넣은 뒤 모자란 자리가 0 인가(게이트). 하나라도 남으면 실패한다."""
    _fd, mmd = common.open_image(dst)
    left = 0
    for fname in FILES:
        lba, fsize = files[fname]
        d = bytearray(common.read_extent(mmd, lba, fsize))
        rows, fix = plan(fname, d, text_starts(fname, d))
        left += len(fix)
        if rows:
            print(f"  ✅ 되읽기 {fname} — 복사 길이 {len(rows)}곳 · 모자란 {len(fix)}")
    mmd.close()
    assert left == 0, f"복사 길이가 모자란 자리가 {left}곳 남았다"


def main():
    apply = "--apply" in sys.argv
    check = "--check" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    files = common.dst_files(dst, mm)
    if (apply or check or "--list" in sys.argv) and not os.path.exists(dst):
        raise SystemExit(f"먼저 다른 패처를 돌린다 — {dst} 가 없다")
    if check:
        verify(dst, files)
        return
    _fd, mmd = common.open_image(dst)
    total = 0
    for fname in FILES:
        lba, fsize = files[fname]
        d = bytearray(common.read_extent(mmd, lba, fsize))
        rows, fix = plan(fname, d, text_starts(fname, d))
        total += len(fix)
        print(f"{fname}: 자리 {len(rows)} · 모자란 {len(fix)}")
        if "--list" in sys.argv:
            for pc, n, src, need in rows:
                mark = "  ← 늘림" if need > n else ""
                print(f"   0x{LOAD_BASE + pc:08X}  N={n:3d}  우리 {need:3d}B  src 0x{src:08X}{mark}")
        if apply and fix:
            with open(dst, "r+b") as f:
                for pc, need in fix:
                    cur = bytes(d[pc : pc + 2])
                    assert cur[0] == 0xE6, f"{fname} 0x{pc:X}: mov #imm,r6 가 아니다"
                    common.write_at(
                        f, lba, fsize, pc, bytes([0xE6, need]), label=f"{fname} 복사 길이", expect=cur
                    )
    mmd.close()
    if apply:
        print(f"  → 넣음 · {total}곳")
        verify(dst, files)
    else:
        print("  (검산만 — 실제로 넣으려면 `--apply`)")


if __name__ == "__main__":
    main()
