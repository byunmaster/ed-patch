"""회심/통한 메시지 복사를 **NUL 종단 복사**로 바꾼다 — 14바이트 고정 제약을 없앤다.

    python3 tools/patch_crit_copy.py            # 조립·검산만
    python3 tools/patch_crit_copy.py --apply    # 빌드 이미지에 넣는다

## 무엇이 문제였나 (2026-08-27 실측)

전투에서 회심의 일격이 나면 화면이 이랬다:

    세리오스의 공격
    회심의 일격!!
    7격              ← ???
    슬라임에게 42의 피해!!

원인은 **고정 길이 복사**다. 이 자리는 문자열을 `mov.b @r1+,r3 · add #1,r2 · mov.b r3,@r2`
로 **정확히 14바이트** 퍼 나른다(언롤 12회 + 앞뒤 하나씩).

    원본  `会心の一撃!!\\n`  13B + NUL = **14B**  → 종단까지 딱 들어간다
    우리  `회심의 일격!!\\n`  **14B 가 전부 내용** → NUL 이 안 들어간다

종단이 없으니 그 버퍼에 **직전에 있던 메시지의 꼬리**가 그대로 이어진다. 실측:

    `%c세리오스%c의 공격\\n` = 19B → 14B 를 덮고 남는 꼬리 `a7 88a5 0a 00` = 「<반쪽>격」

⚠ 그래서 `~의 공격` 의 반각 공백은 **죄가 없다.** 그 문안이 19B 가 되면서 꼬리가 드러났을
  뿐이고, 짧을 때(`공격` 16B)는 꼬리가 `0a 00` 이라 우연히 안 보였다. 「+4 지점을 셋째 줄로
  그린다」는 옛 진단(devlog 2026-08-26 (2))도 이 우연을 잘못 읽은 것이다.

## 그래서 코드를 고친다 — 데이터로는 못 푼다

문안을 13B 이하로 깎으면 되지만(`회심의 일격!`), 그건 **한 문안을 위해 표현을 깎는 것**이고
같은 함정이 다른 자리에도 남는다. 언롤 88B 자리에 **NUL 까지 도는 루프 26B** 를 넣으면
제약 자체가 없어진다(유저 확정 2026-08-27).

    copy:  add #1,r2 · mov.b @r1,r3 · add #1,r1 · mov.b r3,@r2 · tst r3,r3 · bt done
           add #-1,r0 · tst r0,r0 · bf copy          ← r0 = 남은 칸(상한)

⚠ **상한을 둔다**(`LIMIT`). 목적지 버퍼 크기를 모르는 채 NUL 만 믿고 돌면, 소스가 깨졌을 때
  워크램을 밀어 버린다. 소스는 우리 정본이라 NUL 이 확실하지만 가드는 값이 싸다.
⚠ 진입 시 **첫 바이트는 이미 읽혀 r3 에 있다**(원 코드의 지연 슬롯 `mov.b @r1+,r3`).
  그래서 루프는 둘째 바이트부터 돈다 — 이 순서를 바꾸면 첫 글자가 사라진다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import sh2

LOAD_BASE = 0x06028000
LIMIT = 40  # 복사 상한(바이트). 원본 13B · 우리 문안 14B — 넉넉하되 폭주는 막는다

# 🔴 **자리를 손으로 안 적는다** — 편마다 다르다(ED 0x0604DF18 · ED2 0x060369AE).
#    이 꼴은 컴파일러 언롤이라 파일 안에 **여러 곳**이 있다(ED 7 · ED2 10). 그래서
#    「12회 연속」만으로는 못 고르고, **앞의 두 갈래 적재**까지 함께 본다:
#      mov.l @(a,pc),r1 · bra +2 · mov.b @r1+,r3   ← 회심 쪽
#      mov.l @(b,pc),r1 · mov.b @r1+,r3            ← 통한 쪽
#      mov.l @(c,pc),r2 · mov.b r3,@r2             ← 목적지 · 첫 바이트
#    이 머리는 두 편 다 **한 곳**뿐이다(실측).
HEAD = ("a002", "6314", "d1??", "6314", "d2??", "2230")
UNIT = "631472012230"  # mov.b @r1+,r3 · add #1,r2 · mov.b r3,@r2
UNROLL = 12  # 가운데 반복 횟수(실측, 두 편 같다)
TAIL = "611072012210"  # mov.b @r1,r1 · add #1,r2 · mov.b r1,@r2


def _match(d, at, hexpat):
    """`??` 를 와일드카드로 보는 바이트 대조."""
    for i, ch in enumerate(hexpat):
        if ch == "?":
            continue
        b = d[at + i // 2]
        nib = (b >> 4) if i % 2 == 0 else (b & 0xF)
        if nib != int(ch, 16):
            return False
    return True


def find_copy(d):
    """`(패치 시작 파일오프셋, 패치 길이)` — 언롤 복사 몸통을 시그니처로 찾는다."""
    head = "".join(HEAD)
    hits = []
    for at in range(0, len(d) - len(head) // 2, 2):
        if not _match(d, at, head):
            continue
        body = at + len(head) // 2  # 첫 `mov.b r3,@r2` 뒤
        if not _match(d, body, UNIT * UNROLL + TAIL):
            continue
        hits.append(at)
    assert len(hits) == 1, f"머리가 {len(hits)}곳이다 (기대 1) — 시그니처를 더 좁혀야 한다"
    at = hits[0]
    start = at + len(head) // 2 - 2  # `mov.b r3,@r2`(첫 바이트 저장)부터 우리 것으로 바꾼다
    end = at + len(head) // 2 + (len(UNIT * UNROLL) + len(TAIL)) // 2
    return start, end - start


def routine(base):
    """제자리 대체 코드. 들어올 때 r1 = 소스 둘째 바이트 · r2 = 목적지 · r3 = 첫 바이트."""
    src = f"""
        mov   #{LIMIT},r0           ; 남은 칸 — 소스가 깨져도 워크램을 안 민다
        mov.b r3,@r2                ; 첫 바이트(원 코드가 이미 읽어 뒀다)
        tst   r3,r3
        bt    done                  ; 빈 문자열
    copy:
        add   #1,r2
        mov.b @r1,r3
        add   #1,r1
        mov.b r3,@r2
        tst   r3,r3
        bt    done                  ; 🔴 **NUL 까지 옮긴다** — 여기가 고침의 전부다
        add   #-1,r0
        tst   r0,r0
        bf    copy
    done:
        nop
    """
    return sh2.assemble(src.splitlines(), base)


def build(fname, d):
    """`(넣을 바이트, 파일 오프셋, 디스어셈블)`."""
    at, size = find_copy(d)
    code, body = routine(LOAD_BASE + at)
    assert len(code) <= size, f"{fname}: 새 코드 {len(code)}B > 자리 {size}B"
    blob = code + b"\x00\x09" * ((size - len(code)) // 2)  # 남는 자리는 nop
    assert len(blob) == size
    return blob, at, sh2.verify(code, LOAD_BASE + at, body)


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    # 🔴 **쓰기 자리는 빌드 이미지가 정한다** — 규칙은 `common.dst_files` 가 정본이다.
    files = common.dst_files(dst, mm)
    if apply and not os.path.exists(dst):
        raise SystemExit(f"먼저 다른 패처를 돌린다 — {dst} 가 없다")

    for fname in ("/ED.BIN", "/ED2.BIN"):
        d = common.extract(fname)
        blob, at, dis = build(fname, d)
        print(f"{fname}: 복사 몸통 0x{LOAD_BASE + at:08X} {len(blob)}B → 루프 (명령 {len(dis)})")
        if "--dis" in sys.argv:
            for ln in dis:
                print("   ", ln)
        if not apply:
            continue
        lba, fsize = files[fname]
        # ⚠ 다시 돌려도 돌아야 한다 — 게이트가 체인을 통째로 돌리므로 이미 넣은 위에서 또
        #   실행된다. 사전조건은 「원본 언롤이거나 이미 우리 루프」다.
        _fd, mmd = common.open_image(dst)
        cur = bytes(common.read_extent(mmd, lba, fsize)[at : at + len(blob)])
        mmd.close()
        _fd.close()
        was = bytes(d[at : at + len(blob)])
        assert cur in (was, blob), f"{fname} 0x{LOAD_BASE + at:X}: 원본도 우리 것도 아니다"
        with open(dst, "r+b") as f:
            common.write_at(f, lba, fsize, at, blob, label=f"{fname} 회심 복사 루프", expect=cur)
        print(f"   → 넣음 · {len(blob)}B")
    if apply:
        verify(dst, files)
    else:
        print("  (검산만 — 실제로 넣으려면 `--apply`)")


def verify(dst, files):
    """되읽기 — 루프가 그대로 들어갔나."""
    _f2, mm2 = common.open_image(dst)
    for fname in ("/ED.BIN", "/ED2.BIN"):
        blob, at, _dis = build(fname, common.extract(fname))
        d = common.read_extent(mm2, *files[fname])
        assert bytes(d[at : at + len(blob)]) == blob, f"{fname}: 되읽기 불일치"
        print(f"  ✅ 되읽기 {fname} — 복사 루프 {len(blob)}B")
    mm2.close()
    _f2.close()


if __name__ == "__main__":
    main()
