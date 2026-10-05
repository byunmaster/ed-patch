"""전투 위쪽 배너(기술명 · 승리 문구) 글자를 **세로 가운데**로 — `/0.BIN` 상수 하나.

    python3 games/ss-ed3/tools/patch_ui_center.py --check    # 원본 바이트가 예상과 같은지

배너는 창 갱신 함수(`0x0601005C~0x060101BA`)가 그린다. 테두리 조각 셋은 기준 y 에서 **−119**, 글자
스프라이트는 **−116** 이라 글자가 테두리 위끝에서 3px 아래에 놓인다. 원본은 글자 높이가 낮은 일본어
(위 여유 2·아래 여유 1)라 멀쩡했는데, **한글은 획이 한 줄 더 내려와** 안쪽 14 행(16~29)에서 위 3 · 아래 0 으로
바닥에 붙었다(2026-09-30 마스터 스크린샷, 픽셀로 잰 값).
⇒ 글자 y 를 **−117** 로 한 줄 올린다 — 위 2 · 아래 1(마스터 지정). 인게임에서 `진공 베기` 로 위 2 · 아래 1 을 확인했다.

⚠ 이 상수는 **글자 스프라이트 하나**(`0x06079568` 명령의 YA)를 정한다 — 테두리·대사창·이름 배너
(다른 코드)는 그대로다. 대상이 이름 배너(`이자벨`)는 위치가 괜찮다는 마스터 확인(09-30).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

BASE = 0x06004000  # `/0.BIN` 적재 주소
#   `add #-116,r1` (0x71 0x8C) — 글자 명령의 YA = 기준 y − 116. 다음 명령이 `mov.w r1,@r2`.
TEXT_Y = 0x0601016E
TEXT_Y_ORIG = bytes.fromhex("718c")
TEXT_Y_NEW = bytes.fromhex("718b")  # −117
#   테두리 쪽은 그대로 — 안 건드린다는 걸 검산으로 못박는다.
BORDER_Y = 0x060101A4
BORDER_Y_ORIG = bytes.fromhex("7189")  # −119


#   🔴 **LOAD FILE 목록 글자를 한 행 내린다**(마스터 10-01 「텍스트가 1px 내려가면 일관성」). 목록 한 줄을 버퍼에 찍는
#   함수(`0x06028400` 부근)가 엔진 글자 그리기(`0x060417ac`)를 **둘** 부른다(이름·LV). 호출 대상은 각각 풀의 리터럴이라
#   그 둘을 **우리 껍데기**로 돌린다 — 껍데기는 `r4 += r5`(행 바이트 = 한 행)만 하고 원래 그리기로 점프한다.
#   스택 인자·PR 이 그대로라 호출 규약이 안 깨진다. 껍데기 12B 는 디버그 메뉴 죽은 영역 끝(`STUB − 16`)에 둔다.
DRAW = 0x060417AC
LIST_LITS = (0x060284B4, 0x06028550)  # 풀에서 `DRAW` 를 가리키는 리터럴 둘
WRAP = 0x06018BF0
WRAP_CODE = bytes.fromhex("345cd001402b0009") + DRAW.to_bytes(4, "big")  # add r5,r4 · mov.l @(1,pc),r0 · jmp @r0 · nop · 리터럴


#   🔴 **배너 안의 파티 이름만 1px 높게 나왔다**(마스터 10-01 「쥬리오 만 1px 더」). 배너 글자는 시스템 문자열이라 **내려앉은
#   글리프**(`lowered_map`)로 나가는데 이름(쥬리오)은 **세이브·RAM 에서 오는 값**이라 옛 세이브엔 **본 글리프 코드**가
#   적혀 있다(세이브에 코드가 그대로 적힌다 — 본 배정은 못 바꾼다). ⇒ 배너가 글자를 그리기 직전에 문자열 안의
#   파티 이름 글자만 **본 → 내려앉은 코드**로 바꿔 주는 껍데기(`WRAP2`)를 건다(제자리 변환이라 여러 번 불려도 같다).
BANNER_LIT = 0x06010044  # 배너 글자 그리기 호출의 풀 리터럴(`DRAW`)
WRAP2 = 0x06018AC0
WRAP2_ROOM = WRAP - WRAP2  # 코드 + 풀 + 표가 들어갈 자리


def _person_pairs():
    """파티·인물 이름 글자의 `(본 코드 2B + 내려앉은 코드 2B)` 쌍 — 내려앉은 판이 따로 있는 글자만."""
    import json

    import hangul_map as H

    with open(os.path.join(C.GAME_DIR, "script", "system.json"), encoding="utf-8") as f:
        names = json.load(f)["person"].values()
    base, low = H.load(), H.load_low()
    chars = sorted({c for n in names for c in n if c in low and c in base})
    return b"".join(
        H.sjis.sjis_of_index(base[c]) + H.sjis.sjis_of_index(low[c]) for c in chars
    ), chars


def wrap2_code():
    """`WRAP2` 에 둘 바이트 — 코드 · 풀(DRAW · 표 시작 · 표 끝) · 표."""
    import subtitle_stub as SS

    table, _ = _person_pairs()

    def asm(tab, tend):
        a = SS.Asm(WRAP2)
        a.push(8)
        a.push(9)
        a.mov(1, 6)
        a.label("next")
        a.movb_at(2, 1)
        a.tst(2, 2)
        a.bt("done")
        a.cmp_pz(2)
        a.bt("one")
        a.mov(3, 1)
        a.add(3, 1)
        a.movb_at(3, 3)
        a.movl_pc(0, "TAB")
        a.movl_pc(9, "TEND")
        a.label("scan")
        a.cmp_hs(0, 9)
        a.bt("nomatch")
        a.movb_at(8, 0)
        a.cmp_eq(8, 2)
        a.bf("nxt")
        a.mov(8, 0)
        a.add(8, 1)
        a.movb_at(8, 8)
        a.cmp_eq(8, 3)
        a.bf("nxt")
        a.mov(8, 0)
        a.add(8, 2)
        a.movb_at(2, 8)
        a._e(0x2120)  # mov.b r2,@r1
        a.add(8, 1)
        a.movb_at(2, 8)
        a.mov(3, 1)
        a.add(3, 1)
        a._e(0x2320)  # mov.b r2,@r3
        a.bra("nomatch")
        a.nop()
        a.label("nxt")
        a.add(0, 4)
        a.bra("scan")
        a.nop()
        a.label("nomatch")
        a.add(1, 2)
        a.bra("next")
        a.nop()
        a.label("one")
        a.add(1, 1)
        a.bra("next")
        a.nop()
        a.label("done")
        a.pop(9)
        a.pop(8)
        a.movl_pc(0, "DRAW")
        a.jmp(0)
        a.nop()
        return a.resolve({"DRAW": DRAW, "TAB": tab, "TEND": tend})[0]

    n = len(asm(0, 0))
    tab = WRAP2 + n
    code = asm(tab, tab + len(table))
    assert len(code) == n
    blob = code + table
    assert len(blob) <= WRAP2_ROOM, (len(blob), WRAP2_ROOM)
    return blob


def patch(data):
    """`/0.BIN` bytes → 새 bytes(크기 불변). 원본 바이트가 다르면 멈춘다."""
    out = bytearray(data)
    for addr, want in ((BORDER_Y, BORDER_Y_ORIG),):
        off = addr - BASE
        assert out[off : off + 2] == want, f"{addr:#x} 가 예상과 다르다 — 자리를 잘못 짚었다"
    off = TEXT_Y - BASE
    assert out[off : off + 2] == TEXT_Y_ORIG, f"{TEXT_Y:#x} 가 예상과 다르다"
    out[off : off + 2] = TEXT_Y_NEW
    for lit in LIST_LITS:
        o = lit - BASE
        assert out[o : o + 4] == DRAW.to_bytes(4, "big"), f"{lit:#x} 가 예상과 다르다"
        out[o : o + 4] = WRAP.to_bytes(4, "big")
    o = WRAP - BASE
    out[o : o + len(WRAP_CODE)] = WRAP_CODE
    o = BANNER_LIT - BASE
    assert out[o : o + 4] == DRAW.to_bytes(4, "big"), f"{BANNER_LIT:#x} 가 예상과 다르다"
    out[o : o + 4] = WRAP2.to_bytes(4, "big")
    blob = wrap2_code()
    o = WRAP2 - BASE
    out[o : o + len(blob)] = blob
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.parse_args()
    d = C.open_disc(1)
    for name, lba, size in d.files():
        if name == "/0.BIN":
            b = d.read_extent(lba, size)
    new = patch(b)
    diff = [i for i in range(len(b)) if b[i] != new[i]]
    print(f"바뀐 바이트 {len(diff)} — {TEXT_Y:#x}: {TEXT_Y_ORIG.hex()} → {TEXT_Y_NEW.hex()}")


if __name__ == "__main__":
    main()
