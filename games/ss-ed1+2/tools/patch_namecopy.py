"""몬스터 이름(`…A`·`…B` 접미 포함) 고정 폭 복사를 **NUL 종단 복사**로 바꾼다 — ED2 몬스터 오버레이.

    python3 tools/patch_namecopy.py            # 조립·검산만
    python3 tools/patch_namecopy.py --apply    # 빌드 이미지에 넣는다

## 무엇이 문제였나 (2026-10-09, `check_fixed_copy` 를 오버레이로 넓히다 드러났다)

`/BIN/ED2MON02·03·06·08` 에는 이름을 **원문 길이만큼만** 언롤로 퍼 나르는 자리가 있다
(`mov.b @r1+,r3 · add #1,r2 · mov.b r3,@r2` × N). 목적지는 이름 버퍼 `0x0609F561` 이다.

    炎の騎士Ａ    10B (NUL 없음 — 고정 폭)   → 우리 `불꽃의 기사A` 12B  (뒤 2B 가 잘린다)
    砂もぐらＣ    10B + NUL = 11B            → 우리 `모래두더지C` 11B + NUL  (종단이 잘린다)
    木人Ａ        6B                         → 우리 `나무인간A` 9B

잘리면 이름 뒤에 **버퍼에 있던 이전 내용**이 이어져 로그에 깨진 이름(「나무인…」 + 꼬리)이 뜬다 — 등장 문구
(`patch_msgcopy.py`)와 같은 계통이다. 상수를 늘리려 해도 언롤이라 바이트로 박혀 있어 못 늘린다 →
`patch_crit_copy.py` 와 같이 **NUL 까지 도는 루프**로 바꾼다.

목적지 버퍼 폭: `0x0609F561` 주변 리터럴 전수 — 다음 필드가 `0x0609F578`(+0x17)에 한 번, 나머지는 `0x0609F5A8`(+0x47)
이다. 우리 이름은 최대 14B 라 넉넉하되 `LIMIT` 로 폭주는 막는다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_fixed_copy as C
import common
import patch_ui as U
import sh2

LIMIT = 24  # 복사 상한(바이트) — 우리 이름 최대 14B, 버퍼는 0x17 이상
FILES = [f"/BIN/ED2MON{i:02d}.BIN" for i in range(1, 11)]
UNIT = bytes.fromhex("631472012230")  # mov.b @r1+,r3 · add #1,r2 · mov.b r3,@r2
HEAD = bytes.fromhex("27206273")  # mov.b r2,@r7 · mov r7,r2   (첫 글자는 앞에서 r2 에 읽어 뒀다)
TAIL = bytes.fromhex("7201611063732210")  # add #1,r2 · mov.b @r1,r1 · mov r7,r3 · mov.b r1,@r2
# 변형 B — 목적지가 r2 에 이미 있고(앞에서 적재), 첫 UNIT 의 `add #1,r2` 자리에 **다른 명령(채움)** 이 끼어 있다:
#   mov.b @r1+,r3 · <채움> · mov.b r3,@r2 · (UNIT × n) · mov.b @r1,r1 · add #1,r2 · mov.b r1,@r2
FIRST_B = ("6314", None, "2230")
TAIL_B = bytes.fromhex("611072012210")


def _asm_fill(word):
    """첫 UNIT 에 끼어 있던 채움 명령 하나를 그대로 다시 낸다 — `mov #imm,rN` 과 `add #imm,rN` 만 안다."""
    op, n, imm = word >> 12, (word >> 8) & 15, word & 0xFF
    if op == 0xE:
        return f"mov   #{imm - 256 if imm > 127 else imm},r{n}"
    if op == 0x7:
        return f"add   #{imm - 256 if imm > 127 else imm},r{n}"
    return None


def routine_b(base, fill):
    """변형 B 대체 코드. 들어올 때 r1 = 소스 시작 · r2 = 목적지 시작."""
    if isinstance(fill, int):
        # 🔴 채움이 `mov.l @(d,pc),rN` 같은 **자리 의존 명령**이면 옮기면 리터럴 주소가 어긋난다 —
        #   원본 순서(`mov.b @r1+,r3 · 채움 · mov.b r3,@r2`)와 주소를 그대로 두고 그 뒤만 새로 쓴다.
        head = b"\x63\x14" + fill.to_bytes(2, "big")
        rest, body = routine_b(base + 4, None)
        return head + rest, body
    pre = f"{fill}\n        mov.b @r1+,r3" if fill else ""
    src = f"""
        {pre}
        mov.b r3,@r2                ; 첫 글자
        tst   r3,r3
        bt    done
        mov   #{LIMIT},r0
    copy:
        add   #1,r2
        mov.b @r1+,r3
        mov.b r3,@r2
        tst   r3,r3
        bt    done                  ; 🔴 NUL 까지 옮긴다
        add   #-1,r0
        tst   r0,r0
        bf    copy
    done:
        nop
    """
    return sh2.assemble(src.splitlines(), base)


def routine(base):
    """제자리 대체 코드. 들어올 때 r1 = 소스 둘째 바이트 · r2 = 첫 바이트 · r7 = 목적지 시작."""
    src = f"""
        mov.b r2,@r7                ; 첫 글자(앞에서 이미 읽어 r2 에 있다)
        tst   r2,r2
        bt    done
        mov   r7,r2
        mov   #{LIMIT},r0           ; 남은 칸 — 소스가 깨져도 이름 버퍼를 안 넘는다
    copy:
        add   #1,r2
        mov.b @r1,r3
        add   #1,r1
        mov.b r3,@r2
        tst   r3,r3
        bt    done                  ; 🔴 NUL 까지 옮긴다 — 고침의 전부
        add   #-1,r0
        tst   r0,r0
        bf    copy
    done:
        mov   r7,r3                 ; 원 코드가 끝에 하던 일(`mov r7,r3`)
    """
    return sh2.assemble(src.splitlines(), base)


def failing(fname, orig, built):
    """고쳐야 할 언롤 자리 `[(런 오프셋, 복사 길이)]` — 우리 이름이 칸에 안 맞는 곳."""
    bad = {lit for lit, *_ in C.check(fname, orig, built, set())[0]}
    out = []
    for at, cap, srcs in C.sites(orig):
        if any(s[0] in bad for s in srcs):
            out.append((at, cap))
    return out


def build(fname, orig, at):
    """`(넣을 바이트, 오프셋, 복사 길이)` 또는 None — 머리(`mov.b r2,@r7 · mov r7,r2`)부터 꼬리까지를 루프로.

    언롤 개수 `n` 은 연속한 UNIT 을 **직접 센다**(`check_fixed_copy` 의 `cap` 은 꼬리 변형을 못 알아봐 하나 모자랄 수
    있다). 복사 길이 = 첫 글자 1 + n + 꼬리 1.
    """
    n = 0
    while bytes(orig[at + 6 * n : at + 6 * n + 6]) == UNIT:
        n += 1
    start = at - len(HEAD)
    end = at + 6 * n + len(TAIL)
    if bytes(orig[start:at]) != HEAD or bytes(orig[at + 6 * n : end]) != TAIL:
        return _build_b(fname, orig, at)
    size = end - start
    code, _body = routine(C.LOAD_BASE + start)
    assert len(code) <= size, f"{fname}: 새 코드 {len(code)}B > 자리 {size}B"
    return code + b"\x00\x09" * ((size - len(code)) // 2), start, n + 2


def _build_b(fname, orig, at):
    """변형 B — 첫 UNIT(`6314 <채움> 2230`, `check_fixed_copy` 의 런 **앞**에 붙어 있다) + 런 + 꼬리 B."""
    st = at - 6
    first = bytes(orig[st : st + 6])
    if first[0:2] != bytes.fromhex(FIRST_B[0]) or first[4:6] != bytes.fromhex(FIRST_B[2]):
        return None
    word = (first[2] << 8) | first[3]
    fill = word if word >> 12 == 0xD else _asm_fill(word)  # 0xD = mov.l @(d,pc),rN (목적지 주소 적재)
    if fill is None:
        return None
    n = 0
    while bytes(orig[at + 6 * n : at + 6 * n + 6]) == UNIT:
        n += 1
    end = at + 6 * n + len(TAIL_B)
    if bytes(orig[at + 6 * n : end]) != TAIL_B:
        return None
    code, _body = routine_b(C.LOAD_BASE + st, fill)
    size = end - st
    assert len(code) <= size, f"{fname}: 새 코드 {len(code)}B > 자리 {size}B"
    return code + b"\x00\x09" * ((size - len(code)) // 2), st, n + 2


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    files = common.dst_files(dst, mm)
    if not os.path.exists(dst):
        raise SystemExit(f"먼저 다른 패처를 돌린다 — {dst} 가 없다")
    _fd, mmd = common.open_image(dst)
    total = 0
    for fname in FILES:
        C.LOAD_BASE = U.ptr_base(fname)
        orig = common.extract(fname)
        lba, fsize = files[fname]
        built = bytes(common.read_extent(mmd, lba, fsize))
        todo = failing(fname, orig, built)
        total += len(todo)
        for at, cap in todo:
            got = build(fname, orig, at)
            if got is None:
                print(f"  ⚠ {fname}: 0x{C.LOAD_BASE + at:08X} — 머리·꼬리가 다른 변형이라 못 바꿨다 (칸 {cap}B)")
                continue
            blob, start, cap = got
            was = bytes(orig[start : start + len(blob)])
            cur = bytes(built[start : start + len(blob)])
            print(f"{fname}: 0x{C.LOAD_BASE + start:08X} 언롤 {cap}B → 루프 ({len(blob)}B)")
            if apply:
                assert cur in (was, blob), f"{fname} 0x{start:X}: 원본도 우리 것도 아니다"
                with open(dst, "r+b") as f:
                    common.write_at(f, lba, fsize, start, blob, label=f"{fname} 이름 복사", expect=cur)
    mmd.close()
    if apply:
        print(f"  → 넣음 · {total}곳 (이미 넣었으면 0)")
        # 🔴 되읽기 — 넣은 뒤엔 어긋나는 언롤이 **0** 이어야 한다(`check_fixed_copy` 와 같은 눈금)
        _fd2, mm2 = common.open_image(dst)
        left = 0
        for fname in FILES:
            C.LOAD_BASE = U.ptr_base(fname)
            lba, fsize = files[fname]
            rest = failing(fname, common.extract(fname), bytes(common.read_extent(mm2, lba, fsize)))
            left += len(rest)
            for at, cap in rest:
                print(f"  ⚠ 남음 {fname}: 0x{C.LOAD_BASE + at:08X} 칸 {cap}B")
        mm2.close()
        assert left == 0, f"이름 복사가 어긋나는 언롤이 {left}곳 남았다"
        print("  ✅ 되읽기 — 어긋나는 이름 복사 0")
    else:
        print(f"  (검산만 — {total}곳 · 실제로 넣으려면 `--apply`)")


if __name__ == "__main__":
    main()
