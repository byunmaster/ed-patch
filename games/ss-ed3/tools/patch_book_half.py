"""서책 반각 「」 · ' — 책 화면 문자열 그리기(`/BOOKPRG.BIN` `0x060E31BC`)의 **글자 전진을 4px 로** 줄이는 스텁.

    python3 games/ss-ed3/tools/patch_book_half.py --check    # 원본 바이트가 예상과 같은지 · 스텁 검산

🔴 **책 화면은 문자열을 2바이트씩 읽는다**(첫 바이트 0 이 끝) — 반각 1바이트를 넣으면 뒤가 뭉개진다. 그래서 반각 글자도 **2바이트 글자 그대로**(KANJI12 의 글리프 칸 셋 —
슬롯 6255·6256·6257 = `＇` `｢` `｣`, 글리프는 칸 왼쪽 6 열만 잉크) 두고, **그리는 호출을 스텁으로 감싸 전진만 8 → 4px** 로 줄인다. 책 화면의 12→8열 합산은 3 열씩 2 칸이라
6 열 글리프가 정확히 4 열이 된다. 줄 슬롯 바이트 수는 그대로라 홀수 바이트·종결자 문제가 생기지 않는다.

그리기 함수(`0x060E3178`, r4=x · r5=y · r6=코드)는 호출자의 풀 리터럴 `0x060E3220` 하나로만 불린다 → 그 값을 스텁 주소로 바꾼다. 스텁은 원 함수를 부른 뒤 코드가
셋 안이면 호출자의 x(`r8`)에서 4 를 빼 둔다(호출자가 이어서 8 을 더하므로 순전진 4).
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import codearea as CA
import font as F

PATH = "/BOOKPRG.BIN"
BASE = 0x060E0000  # 적재 주소(파일 맨 앞)
POOL = 0x060E3220  # 그리기 함수 주소 리터럴(`0x060E31DA mov.l 0x060E3220,r12` 하나만 읽는다)
DRAW = 0x060E3178
STUB = CA.BOOKH
SLOTS = (6255, 6256, 6257)  # `＇` `｢` `｣`
HALF_ADV = 4


def codes():
    """셋의 SJIS 코드(u16) — 연속이어야 스텁의 `code − 첫째 ≤ 2` 판정이 맞는다."""
    c = [int.from_bytes(F.sjis_of_index(i), "big") for i in SLOTS]
    assert c == list(range(c[0], c[0] + 3)), [hex(x) for x in c]
    return c


def stub():
    """`(스텁 바이트, 자리)` — 코드 + 풀(DRAW · 첫째 코드)."""
    import subtitle_stub as SS

    a = SS.Asm(STUB)
    a.sts_pr()  # sts.l pr,@-r15
    a.push(6)  # 코드(r6)를 지킨다 — 호출이 r6 를 망친다
    a.movl_pc(1, "DRAW")
    a.jsr(1)
    a.nop()
    a.pop(2)  # r2 = 코드
    a.movl_pc(1, "BASE")
    a.sub(2, 1)  # r2 = 코드 − 첫째
    a.movi(1, 2)
    a._e(0x3216)  # cmp/hi r1,r2 — T = (r2 > 2) 부호없음
    a.bt("done")  # 셋 밖이면 그대로
    a.add(8, -HALF_ADV)  # 호출자가 +8 하므로 순 4
    a.label("done")
    a.lds_pr()
    a.rts()
    a.nop()
    blob, addr = a.resolve({"DRAW": DRAW, "BASE": codes()[0]})
    assert len(blob) <= CA.BOOKH_ROOM, len(blob)
    return blob, addr


def patch(out):
    """`/BOOKPRG.BIN` 바이트(`bytes`) → 새 바이트. 스텁은 폰트 RAM 코드 예약 칸(`CA.SIDE`)에 쌓인다."""
    off = POOL - BASE
    assert out[off : off + 4] == struct.pack(">I", DRAW), "BOOKPRG 풀 리터럴이 예상과 다르다"
    # 0x060E31DA `mov.l 0x060E3220,r12` — 풀을 가리키는 그 명령이 맞는지(d = (0x3220 − ((0x31DA&~3)+4))/4 = 0x11)
    ins = out[0x31DA:0x31DC]
    assert ins == bytes([0xDC, 0x11]), ins.hex()
    blob, _ = stub()
    b = bytearray(out)
    b[off : off + 4] = struct.pack(">I", STUB)
    CA.put(b, BASE, STUB, blob)
    return bytes(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.parse_args()
    blob, addr = stub()
    print(
        f"스텁 {len(blob)}B @ {STUB:#x} (방 {CA.BOOKH_ROOM}B) 풀 { ({k: hex(v) for k, v in addr.items()}) }"
    )
    print("코드", [hex(c) for c in codes()])
    print(blob.hex())


if __name__ == "__main__":
    main()
