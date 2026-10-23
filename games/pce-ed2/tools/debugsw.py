"""디버그 메뉴 살리기(마스터 10-21 판정 19 A, 「디버그모드는 일단 살려보고 싶긴해」) — 원판에 숨어 있는 개발자 메뉴(WARP·LVL·GOLD·ITEM·MAGIC·PATH·ENTRY·MASK·ENCNT·SPOT·ABC·VISUAL)를
제품 롬에서 **숨김 제스처**로만 연다. 평소 플레이에는 영향이 없다(RUN 만 누르면 원판과 같다 — 원판에서 필드의 RUN 은 뗄 때까지 기다리는 개발자 키였다).

열기: 필드에서 **RUN 을 누른 채 I 와 II 를 같이 누른다**(세 버튼 동시). 닫기는 메뉴의 방식(II).

설계가 마스터 제안(「부팅 때 I+II 로 `$86` bit7 을 세우고 필드에서 RUN+II」)과 다른 까닭(10-22 실측): `$86` bit7 은 **이어하기 때 세이브에서 복원되는 RAM 블록 안에 있어** 부팅 스위치로 세워도 이어하기 직후 3B 로 덮인다
(새 게임에서만 0xBB 가 유지됐다). 그래서 지속하는 플래그에 기대지 않고 **열 때의 패드로 직접 판정**한다 — 한 번의 제스처로 열리고, 세이브·이어하기·전투 복귀와 무관하게 늘 같다.
① 뱅크 0x6A `$609E` `TST #$04,$26E5`(SELECT 새로 눌림 — RUN+SELECT 30프레임 소프트 리셋 함정 `$4159` 때문에 못 쓴다) → `JMP $5FEE; NOP`.
   본체(뱅크 0x68 `+0x1FEE` 의 18B 빈 칸, 고정 뱅크) = `$2228` 의 I(bit0)·II(bit1)가 **둘 다** 눌려 있으면 `JMP $60AD`(메뉴 입구), 아니면 `JMP $60A4`(원래 다음 줄 — RUN 을 쥐고 있는 동안 기다림).
② 뱅크 0x6A `$60AD` `BBR7 $86,$609B`(개발기 게이트 검사) → NOP×3 — 게이트 없이 메뉴로 들어간다.
③ 뱅크 0x6F `$6902` `BBS7 $86,$690D`(전투 중 II 를 눌렀을 때 디버그 「전투 설정」 창(승리·패배·도망 강제)으로 가는 분기) → `JMP $7F3A`. 본체(뱅크 0x6F `+0x1F3A` 빈 칸 13B) =
   `$2228` 의 RUN(bit3)이 눌려 있으면 `JMP $690D`(디버그 창), 아니면 `JMP $6905`(원래 일반 전투 설정 창). 즉 전투 중 **RUN 을 쥔 채 II** 가 디버그 전투 설정 창이다.
   마스터 10-22 판정 Q5 「2」: 한때 이 창 코드(`$690D`~`$6969` 93B)와 문자열 36B 를 글리프 풀로 돌려줬던 것을 **원래대로 되돌렸다**(1282 멈춤 75/102 · 1538 글리프 자리 빠듯함을 감수).
   게이트(`$86` bit7)는 안 서지만(필드 고속 이동 등 다른 게이트도 안 선다) 메뉴의 토글은 `$86` 의 다른 비트를 쓰므로 그대로 된다.
시험 빌드(`ED_DEBUG=1`)도 같은 제스처다(하네스는 `hold('run+i+ii')`).
④ 메뉴 문자열(뱅크 0x69 `$7549`~, 영어 라벨 그대로)에서 **저장 데이터를 바꾸는 다섯 항목**(WARP·LVL·GOLD·ITEM·MAGIC) 뒤에 `!`(마스터 판정 19 A). 글자 수를 안 바꾸고 맞췄다 — 줄 끝 여백(LVL ·
   PATH · MASK · SPOT)과 「C ATRB」 사이 공백이 4바이트라 `!` 네 개(WARP · GOLD · ITEM · MAGIC)와 맞바꾼다(LVL 은 자기 여백 자리에 `!`). 창 설명 `18 82 86 8c 8d` 의 셋째 인자가 너비(칸 수 = 인자 − 0x81, 실측: 0x8c → 11칸 · 0x8d → 12칸에서 줄이 꺾였다)라
   「 ITEM! MAGIC!」(13칸)을 담으려 `8c` → `8e`(13칸)로 넓힌다 — 인자를 안 고치면 「MAGIC!」 의 `C!` 가 다음 줄로 꺾여 메뉴가 밀린다(10-22 실화면 두 번).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout

STUB_BANK, STUB_OFF, STUB_LEN = 0x68, 0x1FEE, 18  # 뱅크 0x68 고정 뱅크의 0xFF 18B(원본부터)
STUB_ADDR = 0x4000 + STUB_OFF
KEY = (0x6A, 0x09E)  # `$609E` TST #$04,$26E5
KEY_ORIG = bytes.fromhex("9304e526")
MENU_GATE = (0x6A, 0x0AD)  # `$60AD` BBR7 $86,$609B
MENU_GATE_ORIG = bytes.fromhex("7f86eb")
BATTLE_GATE = (0x6F, 0x902)  # `$6902` BBS7 $86,$690D
BATTLE_GATE_ORIG = bytes.fromhex("ff8608")
BATTLE_STUB = (0x6F, 0x1F3A, 13)  # 뱅크 0x6F 끝 0xFF 패딩 198B 의 앞쪽(layout.PADDING)
BATTLE_STUB_ADDR = 0x6000 + BATTLE_STUB[1]
BATTLE_WINDOW, BATTLE_NORMAL = 0x690D, 0x6905  # 디버그 전투 설정 창 · 원래 일반 창
OPEN, KEEP_WAIT = 0x60AD, 0x60A4  # 메뉴 입구 · 원래 다음 줄(RUN 을 쥐는 동안 기다림)


def stub() -> bytes:
    """`TST #$01,$2228; BEQ no; TST #$02,$2228; BEQ no; JMP $60AD; no: JMP $60A4` — 18B."""
    code = bytes.fromhex("93012822" "f009" "93022822" "f003") + bytes([0x4C, OPEN & 0xFF, OPEN >> 8]) + bytes([0x4C, KEEP_WAIT & 0xFF, KEEP_WAIT >> 8])
    assert len(code) == STUB_LEN, len(code)
    return code


def battle_stub() -> bytes:
    """`LDA $2228; AND #$08; BEQ no; JMP $690D; no: JMP $6905` — 13B(RUN 을 쥐면 디버그 창)."""
    code = bytes.fromhex("ad282229" "08f003") + bytes([0x4C, BATTLE_WINDOW & 0xFF, BATTLE_WINDOW >> 8, 0x4C, BATTLE_NORMAL & 0xFF, BATTLE_NORMAL >> 8])
    assert len(code) == BATTLE_STUB[2], len(code)
    return code


MENU_WIDTH = (0x69, 0x1546)  # 창 설명 `18 82 86 8c 8d` 의 셋째 인자(너비) — 0x8c(11칸) → 0x8e(13칸)
MENU_TEXT = (0x69, 0x1549)  # `05` 바로 뒤 — 항목 줄들
ROWS_OLD = [b"WARP", b"LVL \x01 GOLD", b"ITEM\x01 MAGIC", b"PATH ", b"ENTRY", b"MASK ", b"ENCNT", b"SPOT ", b"A\x01 B\x01 C ATRB", b"VISUAL"]
ROWS_NEW = [b"WARP!", b"LVL!\x01 GOLD!", b"ITEM!\x01 MAGIC!", b"PATH", b"ENTRY", b"MASK", b"ENCNT", b"SPOT", b"A\x01 B\x01 CATRB", b"VISUAL"]


def menu_text(rows: list[bytes]) -> bytes:
    return b"".join(b"\x01 " + r + b"\x0d" for r in rows)


def reserve(prog: layout.Prog) -> None:
    prog.reserve(STUB_BANK, STUB_OFF, STUB_LEN)
    prog.reserve(*BATTLE_STUB)


def install(prog: layout.Prog) -> None:
    assert set(prog.o(STUB_BANK, STUB_OFF, STUB_LEN)) == {0xFF}, "새 본체 자리가 비어 있지 않다"
    for (b, o), orig in ((KEY, KEY_ORIG), (MENU_GATE, MENU_GATE_ORIG), (BATTLE_GATE, BATTLE_GATE_ORIG)):
        assert prog.o(b, o, len(orig)) == orig, f"디버그 자리 원본 바이트가 기대와 다르다 {b:02X}+{o:04X}"
    prog.put(STUB_BANK, STUB_OFF, stub(), "디버그 제스처 본체(RUN+I+II)")
    prog.put(KEY[0], KEY[1], bytes([0x4C, STUB_ADDR & 0xFF, STUB_ADDR >> 8, 0xEA]), "디버그 열기 — SELECT 검사를 제스처 본체로(JMP $5FEE)")
    prog.put(MENU_GATE[0], MENU_GATE[1], bytes([0xEA, 0xEA, 0xEA]), "디버그 메뉴 입구의 개발기 게이트 검사 해제")
    assert set(prog.o(*BATTLE_STUB)) == {0xFF}, "전투 설정 본체 자리가 비어 있지 않다"
    prog.put(BATTLE_STUB[0], BATTLE_STUB[1], battle_stub(), "디버그 전투 설정 창 본체(RUN+II)")
    prog.put(BATTLE_GATE[0], BATTLE_GATE[1], bytes([0x4C, BATTLE_STUB_ADDR & 0xFF, BATTLE_STUB_ADDR >> 8]), "디버그 전투 설정 창 분기 — 개발기 게이트 대신 RUN 쥠으로(JMP $7F3A)")
    old, new = menu_text(ROWS_OLD), menu_text(ROWS_NEW)
    assert len(old) == len(new), (len(old), len(new))
    assert prog.o(MENU_TEXT[0], MENU_TEXT[1], len(old)) == old, "디버그 메뉴 문자열이 기대와 다르다"
    assert prog.o(MENU_WIDTH[0], MENU_WIDTH[1], 1) == b"\x8c"
    prog.put(MENU_TEXT[0], MENU_TEXT[1], new, "디버그 메뉴 — 저장을 바꾸는 다섯 항목 뒤 `!`")
    prog.put(MENU_WIDTH[0], MENU_WIDTH[1], b"\x8e", "디버그 메뉴 창 너비 11→13칸")

