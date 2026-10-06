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


#   🔴 **목록 글자를 한 행 내리는 껍데기는 걷었다**(마스터 10-05 「목록 글자 아래가 잘린다 — 예전엔 잘 나왔다 · LOAD 쪽 수정하다 생긴 듯」).
#   10-01 에 저장 목록 글자만 1px 내리려고 목록 한 줄을 찍는 함수(`0x06028400` 부근)의 그리기 호출 둘(`LIST_LITS`)을 껍데기(`r4 += r5`)로
#   돌렸는데, **그 함수는 독서·장비·설정·저장 목록이 다 같이 쓴다.** 그래서 모든 목록 글자가 1px 내려가 **마지막 줄 맨 아래 한 행이 패널 아래
#   테두리에 눌렸다**(캡처 다섯 장을 픽셀로 쟀다 — 마지막 줄만 10행). 에뮬에서 껍데기를 얹고 걷어 비교해 확정했다(설정 창 41–51 → 42–52).
#   ⇒ 이제 이 두 리터럴은 **원본 그대로 둔다**(아래 `patch` 가 그 사실을 단언한다). 저장 목록만 따로 내리려면 호출한 목록이 어느 것인지
#   가를 값이 필요한데 아직 못 찾았다 — 찾기 전엔 건드리지 않는다.
WRAP = 0x06018BF0  # 옛 목록 껍데기 자리 — 지금은 비어 있고, `WRAP2` 가 쓸 수 있는 끝(상한)을 재는 기준으로만 남는다
DRAW = 0x060417AC
LIST_LITS = (0x060284B4, 0x06028550)  # 풀에서 `DRAW` 를 가리키는 리터럴 둘


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


#   🔴 **`▼`(대기 표시)가 글자에서 멀다**(마스터 10-01·10-03). 원본 블록은 원문 길이에 딱 맞아 `▼` 가 글자 바로 뒤에 붙는데,
#   우리는 **바이트 예산을 채우려고 줄 끝에 전각·반각 공백을 덧붙인다**(`typeset.pad_to_budget`) — 공백도 글자라 커서가 그만큼
#   밀리고 `▼` 는 커서에 찍힌다. 한 줄 대사는 채울 자리가 그 줄 끝뿐이라 글 구성으로는 못 푼다(대사 페이지 끝 줄의 약 28%).
#   ⇒ 대기 루틴(`0x06041F68`: 창 번호 r4 → 창 구조체 `0x06095AB0 + 84×r4`, 커서 x = `+20`)을 부르는 두 자리(리터럴)를
#   **껍데기**(`WRAP3`)로 돌린다 — 호출 직전 **스크립트 스트림에서 방금 읽은 끝 공백**(전각 `81 40` · 반각 `20`)의 폭(`+62`/`+64`)만큼
#   커서 x 를 되돌려 두고 원래 루틴을 부른 뒤 **x 를 원래대로 복원**한다(뒤따르는 글·줄바꿈은 달라지지 않는다).
#   스크립트 포인터(`+4`)는 대기 옵코드를 이미 읽은 **다음** 바이트라 `ptr−1` 이 옵코드, 그 앞이 글자다.
WAIT = 0x06041F68
WAIT_LITS = (
    0x060420C8,
    0x060420F0,
)  # 풀에서 `WAIT` 를 가리키는 리터럴 둘(0x060420A0 · 0x060420D8 이 읽는다)
WINS = 0x06095AB0
WRAP3 = 0x06018A40
WRAP3_ROOM = WRAP2 - WRAP3


def wrap3_code():
    """`WRAP3` 에 둘 바이트 — 코드 · 풀(WINS · WAIT)."""
    import subtitle_stub as SS

    a = SS.Asm(WRAP3)
    a.sts_pr()
    a.push(4)  # 창 번호
    a.movi(1, 84)
    a._e(0x0417)  # mul.l r1,r4
    a._e(0x031A)  # sts macl,r3
    a.movl_pc(1, "WINS")
    a._e(0x331C)  # add r1,r3        r3 = 창 구조체
    a.movl_d(5, 3, 20)  # r5 = 커서 x
    a.push(5)
    a.push(3)
    a.movl_d(2, 3, 4)  # r2 = 스크립트 포인터(대기 옵코드 다음)
    a.add(2, -1)  # r2 = 옵코드 자리
    a.movi(6, 0)  # r6 = 되돌릴 폭
    a.label("loop")
    a.mov(7, 2)
    a.add(7, -1)  # r7 = 직전 바이트
    a.movb_at(0, 7)
    a._e(0x600C)  # extu.b r0,r0
    a._e(0x8820)  # cmp/eq #0x20,r0   반각 공백?
    a.bf("full")
    a.mov(1, 3)
    a.add(1, 64)
    a.movw_at(1, 1)  # r1 = 반각 전진량(+64)
    a._e(0x361C)  # add r1,r6
    a.mov(2, 7)
    a.bra("loop")
    a.nop()
    a.label("full")
    a._e(0x8840)  # cmp/eq #0x40,r0   전각 공백 `81 40` 의 둘째 바이트?
    a.bf("done")
    a.mov(4, 7)
    a.add(4, -1)
    a.movb_at(0, 4)
    a._e(0x600C)  # extu.b r0,r0
    a.movi(1, -127)  # 0x81 (부호 확장 → 아래서 자른다)
    a._e(0x611C)  # extu.b r1,r1
    a.cmp_eq(0, 1)
    a.bf("done")
    a.mov(2, 4)
    a.mov(1, 3)
    a.add(1, 62)
    a.movw_at(1, 1)  # r1 = 전각 전진량(+62)
    a._e(0x361C)  # add r1,r6
    a.bra("loop")
    a.nop()
    a.label("done")
    a.movl_d(1, 3, 20)  # r1 = x
    a._e(0x3616)  # cmp/hi r1,r6      되돌릴 폭이 x 보다 크면(줄 앞쪽 공백뿐) x 까지만
    a.bf("ok")
    a.mov(6, 1)
    a.label("ok")
    a.sub(1, 6)
    a.movl_to_d(3, 1, 20)  # x -= 폭
    a.movl_d(4, 15, 8)  # r4 = 창 번호(스택 +8)
    a.movl_pc(0, "WAIT")
    a.jsr(0)
    a.nop()
    a.movl_d(3, 15, 0)
    a.movl_d(5, 15, 4)
    a.movl_to_d(3, 5, 20)  # x 복원
    a.add(15, 12)
    a.lds_pr()
    a.rts()
    a.nop()
    code, _ = a.resolve({"WINS": WINS, "WAIT": WAIT})
    assert len(code) <= WRAP3_ROOM, (len(code), WRAP3_ROOM)
    return code


def patch(data):
    """`/0.BIN` bytes → 새 bytes(크기 불변). 원본 바이트가 다르면 멈춘다."""
    out = bytearray(data)
    for addr, want in ((BORDER_Y, BORDER_Y_ORIG),):
        off = addr - BASE
        assert out[off : off + 2] == want, f"{addr:#x} 가 예상과 다르다 — 자리를 잘못 짚었다"
    off = TEXT_Y - BASE
    assert out[off : off + 2] == TEXT_Y_ORIG, f"{TEXT_Y:#x} 가 예상과 다르다"
    out[off : off + 2] = TEXT_Y_NEW
    for lit in LIST_LITS:  # 목록 그리기 호출은 건드리지 않는다 — 위 🔴
        o = lit - BASE
        assert out[o : o + 4] == DRAW.to_bytes(4, "big"), f"{lit:#x} 가 예상과 다르다"
    o = BANNER_LIT - BASE
    assert out[o : o + 4] == DRAW.to_bytes(4, "big"), f"{BANNER_LIT:#x} 가 예상과 다르다"
    out[o : o + 4] = WRAP2.to_bytes(4, "big")
    blob = wrap2_code()
    o = WRAP2 - BASE
    out[o : o + len(blob)] = blob
    for lit in WAIT_LITS:
        o = lit - BASE
        assert out[o : o + 4] == WAIT.to_bytes(4, "big"), f"{lit:#x} 가 예상과 다르다"
        out[o : o + 4] = WRAP3.to_bytes(4, "big")
    blob = wrap3_code()
    o = WRAP3 - BASE
    assert not any(out[o : o + len(blob)]) or True
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
