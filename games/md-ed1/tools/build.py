"""md-ed1 빌드 — 정본(script/*.json)만 읽어 work/build/<꼬리표>/ed1-kr.bin 을 만든다. 결정적이다.

    python3 tools/build.py            # 빌드 + 게이트
    python3 tools/build.py --check    # 빌드 없이 게이트만(정본 검증)

안전장치(docs/patcher-checklist.md):
- 입력 지문(common.rom) · 쓰기는 `_write(label, lo, hi)` 한 통로 — **허용 구간 밖은 즉시 거부**
  (대본 아카이브 자리 · 꼬리 빈 공간 · 글꼴 리소스 0 · 헤더 체크섬).
- 끝에 원본과 byte 대조: 허용 구간 밖은 한 바이트도 안 바뀌어야 한다.
- 화면에 나가는 바이트 게이트: 미수록 글자(인코딩 불가) · 대사창 210px(17.5칸) 초과 줄 · 3줄 초과 페이지 ·
  참조 제어코드 불일치 → **빌드 실패**. 실패하면 산출물을 `.failed` 로 이름 바꾼다.
"""

import json
import os
import re
import struct
import sys
from pathlib import Path
from typing import ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(common_root := Path(__file__).resolve().parents[3] / "shared"))
import actor_names
import archives
import battle
import captions
import common
import dict_names
import field_hud
import field_names
import gfxtext
import halfspace
import hangul
import hud_status
import josa
import linebreak
import lz
import party_template
import punctwrap
import scene
import spell_digit
import sysmsg
import tables
import textmap
import wordwrap
from text import krwrap

# 대사창 한 줄 = 210px(전각 17.5칸) — 원판이 **저절로 넘긴다**: 전각 17자(204px) 뒤 18째 글자를 다음 줄로
# 보냈다(화자 없는 꼴·이름창 꼴 둘 다, 09-27 `r5-typeset-dialog-wrap-jp*.png`). 옛 값 18칸(216px)은 안쪽 폭으로 잰 추정이었다
WIDTH = 17.5
LINES = 3

SCRIPT_LO, SCRIPT_HI = 0x135324, 0x1918D2  # 대본 블록 자리(색인 0x134FA0 은 항목만 고친다)
TAIL_LO, TAIL_HI = common.FREE_TAIL
CAPTION_RESERVE = (
    0x1000  # 자막(오프닝·엔딩 나레이션·엔딩 대사)을 꼬리로 옮길 자리 — 제자리 칸이 만원이라서
)
# 꼬리 **끝**에 조사 훅(기계어+표)을 예약한다 — 아카이브는 그 앞까지만 쓴다.
# ⚠ 표는 **한글 코드 수를 따라 자란다**(종성 비트표 = 코드 하나에 1비트). 0x180 으로 재 두었더니
# 글자 33 자를 새로 굳히자마자 2바이트가 넘쳤다(2026-09-07). 그래서 **글리프 상한**(1,370자)까지
# 재 둔다 — 172B(한글 비트표) + 16B(반각) + 252B(기계어) + 쌍 표 ≈ 460B.
JOSA_RESERVE = 0x3E0  # 0x340→0x3E0(씬 라운드 2026-10-11): 한글 1,025자에서 기계어 424 + 표 384 = 808B — 쌍 표가 크다. (0x280→0x340: 으로/로·과/와 를 넣으며 표가 2비트로 커졌다)
# 조사 훅 앞에 어절 줄넘김 본체(tools/wordwrap.py, 326B)를 둔다 — 넘칠 때 글자가 아니라 어절을
# 다음 줄로 보낸다(마스터 2026-09-30 번복, 전 기종 — 09-27 밤의 글자 단위 "최종 판정"을 다시 뒤집었다)
WRAP_RESERVE = 0x180
# 어절 줄넘김 앞에 필드 HUD 뒷말·방위 앞 공백 트램펄린(tools/field_hud.py, 18B)을 둔다(2026-09-27 밤)
FIELD_HUD_RESERVE = 0x20
# 자막 자리 **앞**에 시스템 메시지 중 꼬리로 옮기는 스트림(도망 둘, sysmsg.RELOCATE)의 칸을 둔다 — 아카이브는 그 앞까지만
SYSMSG_TAIL = sysmsg.TAIL_SIZE
SYSMSG_TAIL_AT = (
    TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE - CAPTION_RESERVE - SYSMSG_TAIL
)
# 글꼴 리소스 1(반각)·5(자막)의 표·글리프 칸 — 표 0 의 빈 자리에 두면 한글이 ~1,100자를 넘을 때 안 들어간다
# (씬 라운드 2026-10-11). 리소스 1 = 표 268B + 글리프 3.8KB, 리소스 5 = 글자당 표 2B + 글리프 64B(Neo 16×16).
FONT_RESERVE = 0x5000
ARCHIVE_TOP = SYSMSG_TAIL_AT - FONT_RESERVE
FONT_AT = ARCHIVE_TOP


BATTLE_LO, BATTLE_HI = 0x0CAB04, 0x0D85B4  # 전투 아카이브 LZ 구간(첫 블록 시작 ~ 끝 블록 끝)


# 시험 빌드 전용 디버그 플래그(`$FF01B2`=0x62) — 부팅 `0x1085C` 의 지워진 A+B+C 검사 자리(14B:
# move.w d0,d1 · andi.w #$70 · cmpi.w #$70 · bne.w +2)를 `move.b #$62,$FF01B2` + nop 둘로 바꾼다.
# 앞 두 줄(패드 읽기 `jsr $A64`)은 그대로 둔다. 분석은 docs/status.md 「디버그 모드 분석」.
DEBUG_BUILD = os.environ.get("ED_DEBUG") == "1"
DEBUG_TAGS_OK = ("test-", "debug")  # 꼬리표 `debug` = 마스터용(인게임 QA), `test-*` = 시험
DEBUG_OUT_NAME = "ed1-kr-DEBUG.bin"  # 🔴 제품 파일명(ed1-kr.bin)과 달라야 emucap SRAM 이름도 갈린다
DEBUG_HDR_AT = 0x150  # 헤더 「해외판 이름」 칸(원판은 공백) — 에뮬 창·목록에 (DEBUG) 가 보이게
DEBUG_HDR = b"DRAGON SLAYER (DEBUG)".ljust(32)
DEBUG_SITE = 0x1085C
DEBUG_PATCH = bytes.fromhex("13fc006200ff01b2") + bytes.fromhex("4e71") * 3  # 8B + nop×3 = 14B
# 필드 전투 스킵 — 조우 판정 `$22FAC` 의 걸음 카운터 검사(`0x22FD8`: cmpi.b #0,$FF3609 + beq.w 12B)를 꼬리 스텁으로 돌린다.
# 디버그 플래그($FF01B2 = 0x62)가 서 있고 **A 버튼을 누른 채** 걸으면 카운터만 줄이고 조우를 건너뛴다(A 를 떼면 평소 그대로).
DEBUG_SKIP_SITE = 0x22FD8
DEBUG_SKIP_STUB_AT = (
    ARCHIVE_TOP - 0x60
)  # 꼬리 아카이브 구간 끝 쪽의 빈 자리(ARCHIVE_TOP = 글꼴 꼬리 시작)
DEBUG_SKIP_STUB = bytes.fromhex(
    "0c390062 00ff01b2 6610"  # cmpi.b #$62,$FF01B2 / bne.s 평소
    "08390006 00ff1855 6706"  # btst #6,$FF1855(A 버튼) / beq.s 평소
    "4ef900022fe4"  # jmp $22FE4 — 조우 없이 카운터 감소로
    "0c390000 00ff3609 6606"  # 평소: cmpi.b #0,$FF3609 / bne.s 계속
    "4ef900022ff2"  # jmp $22FF2 — 조우
    "4ef900022fe4"  # 계속: jmp $22FE4
)
# 대사 보기(디버그 롬만) — 램 우편함 `$FFE800`(스트림 램 주소 .l)·`$FFE804`(창 종류 a5 .w)에 값을 쓰면, 필드 메인 루프의 입력 읽기
# (`$16B0: jsr $A64` — 4프레임마다 불린다)에서 엔진 메시지 함수(`movea.l $200.w,a6 / jsr (a6)` — 씬 모듈이 NPC 대사를 부르는
# 그 꼴)를 불러 대사를 창에 띄운다. 끝나면 `$FFE806` 에 1 을 쓴다(하네스가 읽는다). 걸어가 말 걸기 없이 씬 모듈 안 모든 스트림을
# 실제 창에 띄우려는 것(헤드리스 `gpgx_msgview.py`). 걸음 판정(`$22FD8`)·플레이어 갱신(`$226D4`)에 먼저 걸었으나 실내·정지 중엔 안 불려 옮겼다(카운터 스텁으로 열 자리를 재서 골랐다).
DEBUG_VIEW_SITE = 0x16B0
DEBUG_VIEW_AT = ARCHIVE_TOP - 0xC0
DEBUG_VIEW_BOX = 0xFFE800
_BOX = DEBUG_VIEW_BOX.to_bytes(4, "big")
_BOX5 = (DEBUG_VIEW_BOX + 4).to_bytes(4, "big")
_VIEW_BODY = (
    bytes.fromhex("48e7fffe")  # movem.l d0-d7/a0-a6,-(a7)
    + bytes.fromhex("2279")
    + _BOX  # movea.l $FFE800,a1
    + bytes.fromhex("3a79")
    + _BOX5  # movea.w $FFE804,a5
    + bytes.fromhex("42b9")
    + _BOX  # clr.l $FFE800
    + bytes.fromhex("2c780200")  # movea.l $200.w,a6
    + bytes.fromhex("4e96")  # jsr (a6)
    + bytes.fromhex("13fc000100ffe806")  # move.b #1,$FFE806 — 「끝났다」 표식
    + bytes.fromhex("4cdf7fff")  # movem.l (a7)+,d0-d7/a0-a6
)
DEBUG_VIEW_STUB = (
    bytes.fromhex("4eb900000a64")  # jsr $A64.l — 덮어쓴 원래 명령(d0 = 패드)
    + bytes.fromhex("0c390062")
    + bytes.fromhex("00ff01b2")  # cmpi.b #$62,$FF01B2
    + bytes.fromhex("66")
    + bytes([6 + 2 + len(_VIEW_BODY)])  # bne.s 끝
    + bytes.fromhex("4ab9")
    + _BOX  # tst.l $FFE800
    + bytes.fromhex("67")
    + bytes([len(_VIEW_BODY)])  # beq.s 끝
    + _VIEW_BODY
    + bytes.fromhex("4e75")  # rts
)
DEBUG_VIEW_PATCH = bytes.fromhex("4eb9") + DEBUG_VIEW_AT.to_bytes(
    4, "big"
)  # jsr 스텁 (6B, 원래와 같은 길이)
DEBUG_SKIP_PATCH = (
    bytes.fromhex("4ef9") + DEBUG_SKIP_STUB_AT.to_bytes(4, "big") + bytes.fromhex("4e71") * 3
)  # 6B + nop×3 = 12B


# 🔴 디버그 진입키(제품 롬 — 마스터 11-07 「스타트 a b 원판대로 하자. md 1 도 이렇게 맞추자」, md-ed2 와 같은 키): **Start+A+B 를 약 1초(VBlank 60회) 함께**
# 쥐면 `$FF01B2` 가 0↔0x62 로 토글된다(켜짐 = 원판에 죽어 있던 C+방향 고속 이동·C 벽 통과). 같은 키로 다시 1초 = 끄기. (옛 키: A→A+C 1초.)
# 훅은 패드 갱신 호출 `jsr $9042`(`0xB772` VBlank · `0xBA56` 일시정지 루프, 각 6B)를 스텁 호출로 — 스텁이 그 호출을 먼저 하고 raw 패드 바이트 `$FF0058`
# (Start 0x80·A 0x40·C 0x20·B 0x10·방향 0x0F; 필드 입력 `$FF1854` 는 Start 가 빠져 있다)가 **정확히 0xD0**(Start+A+B 만)인 VBlank 를 센다.
# ⚠ 일시정지 루프는 한 프레임에 수십 번 이 호출을 돈다 — 그래서 **VBlank 진입(`0xB614`)에 틱 바이트(`$FFB302`)를 올리는 훅**을 따로 두고, 스텁은 틱이 바뀐 호출만 센다.
# 셋 중 하나라도 떼거나 C·방향이 섞이면 0 으로. 60 에 이르면 한 번 토글(소리 `$FF2024=0x1B`)하고 뗄 때까지 안 센다(`$FFB301` 은 원판이 안 쓰는 0 구간).
# ⚠ Start 를 먼저 쥐면 일시정지(필드에서 2프레임 만에 열림)가 열린다 — VBlank 는 일시정지 중에도 돌아 세기는 계속된다(켜진 뒤 Start 로 풀면 된다).
KEY_SITE = 0xB772
KEY_SITE2 = 0xBA56  # 같은 패드 갱신 호출의 둘째 자리(다른 루프) — 둘 다 스텁으로
KEY_SITE_OLD = bytes.fromhex("4eb900009042")
KEY_POLLS = 60
KEY_AT = ARCHIVE_TOP - 0x240  # 앞쪽 0xFF 빈 자리(스텁 둘이 0x100 안에 든다)


def _key_stub() -> bytes:
    """Start+A+B 유지 검사 스텁. 항목은 바이트열 또는 ("b", 코드, 라벨)·("L", 라벨) — 짧은 분기(.s)만 쓴다."""
    prog: list = [
        bytes.fromhex("4eb900009042"),  # jsr $9042.l — 덮어쓴 원래 호출(패드 갱신)
        bytes.fromhex("48e7c000"),  # movem.l d0-d1,-(a7)
        bytes.fromhex("103900ffb302"),  # move.b tick,d0 — VBlank 훅이 올리는 틱
        bytes.fromhex("b03900ffb303"),  # cmp.b last,d0
        ("b", 0x67, "chkv"),  # beq.s chkv
        bytes.fromhex("13c000ffb303"),  # move.b d0,last
        ("b", 0x60, "newf"),  # bra.s newf — 새 프레임
        ("L", "chkv"),
        # 일시정지 루프는 VBlank 훅이 안 돈다(실측) — V 카운터가 줄어드는(감기는) 호출을 새 프레임으로 센다
        bytes.fromhex("303900c00008"),  # move.w $C00008.l,d0 (HV 카운터)
        bytes.fromhex("e048"),  # lsr.w #8,d0
        bytes.fromhex("123900ffb304"),  # move.b $FFB304.l,d1
        bytes.fromhex("13c000ffb304"),  # move.b d0,$FFB304.l
        bytes.fromhex("b001"),  # cmp.b d1,d0
        ("b", 0x64, "done"),  # bcc.s done — 줄지 않았다
        ("L", "newf"),
        bytes.fromhex("103900ff0058"),  # move.b $FF0058.l,d0 — raw 패드(held)
        bytes.fromhex("0c0000d0"),  # cmpi.b #$D0,d0 — Start+A+B 만
        ("b", 0x66, "reset"),  # bne.s reset
        bytes.fromhex("0c39") + bytes([0, KEY_POLLS]) + bytes.fromhex("00ffb301"),  # cmpi.b #N,count
        ("b", 0x67, "done"),  # beq.s done — 이미 토글했다
        bytes.fromhex("523900ffb301"),  # addq.b #1,count
        bytes.fromhex("0c39") + bytes([0, KEY_POLLS]) + bytes.fromhex("00ffb301"),  # cmpi.b #N,count
        ("b", 0x66, "done"),  # bne.s done
        bytes.fromhex("0a39006200ff01b2"),  # eori.b #$62,$FF01B2 — 토글
        bytes.fromhex("13fc001b00ff2024"),  # move.b #$1b,$FF2024 — 소리
        ("b", 0x60, "done"),  # bra.s done
        ("L", "reset"),
        bytes.fromhex("423900ffb301"),  # clr.b count
        ("L", "done"),
        bytes.fromhex("4cdf0003"),  # movem.l (a7)+,d0-d1
        bytes.fromhex("4e75"),  # rts
    ]
    pos, labels = 0, {}
    for it in prog:
        if isinstance(it, bytes):
            pos += len(it)
        elif it[0] == "L":
            labels[it[1]] = pos
        else:
            pos += 2
    out, pos = b"", 0
    for it in prog:
        if isinstance(it, bytes):
            out += it
            pos += len(it)
        elif it[0] == "b":
            d = labels[it[2]] - (pos + 2)
            assert 0 < d < 128
            out += bytes([it[1], d])
            pos += 2
    return out


KEY_STUB = _key_stub()
VBL_SITE = 0xB614  # VBlank 핸들러 머리 12B(`movem.l d0-d7/a0-a6,-(a7)` + `ori.b #1,$FF00E7`) — 틱을 올리고 같은 둘을 하고 0xB620 으로
VBL_OLD = bytes.fromhex("48e7fffe00390001 00ff00e7".replace(" ", ""))
VBL_AT = KEY_AT + len(KEY_STUB)
VBL_STUB = (
    bytes.fromhex("523900ffb302")  # addq.b #1,tick
    + bytes.fromhex("48e7fffe")  # movem.l d0-d7/a0-a6,-(a7)
    + bytes.fromhex("00390001 00ff00e7".replace(" ", ""))  # ori.b #1,$FF00E7.l
    + bytes.fromhex("4ef9")
    + (0xB620).to_bytes(4, "big")  # jmp $B620
)
VBL_PATCH = bytes.fromhex("4ef9") + VBL_AT.to_bytes(4, "big") + bytes.fromhex("4e71") * 3  # 6B + nop×3 = 12B
assert len(KEY_STUB) + len(VBL_STUB) <= 0x100, len(KEY_STUB) + len(VBL_STUB)
KEY_PATCH = bytes.fromhex("4eb9") + KEY_AT.to_bytes(4, "big")  # jsr 스텁 (6B)
# 필드 메뉴 주문 목록 줄(`$27640` 줄 만들기) — 주문 이름 버퍼(`$FF3450`)에서 **앞 공백을 건너뛰고 (10 − 공백 수)바이트를 그대로 복사**한다.
# 원판은 「이름 + 전각 레벨 2B」 길이가 늘 이 수와 같아 06 이 안 걸렸다. 우리 레벨 숫자(`spell_digit`)는 반각 1B + 06 이라 복사가 **06 까지 삼켜**
# 줄이 거기서 끝나 오른쪽 「10MP」 소모량이 통째로 사라졌다(10-24 짝 캡처 `burn-1024/menu-qa3/`에서 발견). ⇒ 복사 루프(`$276E0`, 6B)를
# 06 에서 멈추는 스텁 호출로 바꾼다(줄은 미리 공백으로 채워져 있어 나머지는 공백 그대로).
SPELL_LIST_SITE = 0x276E0
SPELL_LIST_OLD = bytes.fromhex("16dd538466fa")  # move.b (a5)+,(a3)+ / subq.l #1,d4 / bne.b
SPELL_LIST_AT = ARCHIVE_TOP - 0x180
SPELL_LIST_STUB = bytes.fromhex(
    "2f00"  # move.l d0,-(a7)
    "101d"  # 루프: move.b (a5)+,d0
    "0c000006"  # cmpi.b #6,d0
    "6706"  # beq.b 끝
    "16c0"  # move.b d0,(a3)+
    "5384"  # subq.l #1,d4
    "66f2"  # bne.b 루프
    "201f"  # 끝: move.l (a7)+,d0
    "4e75"  # rts
)
SPELL_LIST_PATCH = bytes.fromhex("4eb9") + SPELL_LIST_AT.to_bytes(4, "big")  # jsr 스텁 (6B)
# 시스템 메뉴 여섯째 행 「경험치UP」 숨기기 — `0x26CDA` 의 `cmpi.b #$62,$FF01B2 / bne.w` 를 무조건 건너뛰기로(원판에서도 확인 키가 무한 루프로 굳는다)
# 🔴 코드가 **즉치 워드**로 화면 글자를 붙이는 곳(11-07 MD II 알림 — 연속 2자 텍스트 스캔·문안 참조 어디에도 안 걸린다):
#  (1) 0x32BE 주문서 이름 「<주문 이름 8B>の書<06>」 — `34FC 82CC · 34FC 8F91 · 14BC 0006`(12B) → 「의 책<06>」(정본 「~의 책」, 공백 한 칸이 필요해 `24FC`(long 즉치)
#      + `34FC`(06 까지 한 워드) + NOP 로 같은 12B 에 넣는다. a2 는 짝수 자리에서 시작해 쓰기 폭이 모두 짝수 자리다)
#  (2) 0x262B8 저장 확인문 「N番目の」 — 번호 뒤 `番 目 の` 즉치 셋 → 「번째」+반각 공백(`14FC 0020` = move.b — 워드 0020 은 00 이 문자열 끝이라 못 쓴다)
SPELLBOOK_SITE = 0x32BE
SPELLBOOK_OLD = bytes.fromhex("34fc82cc34fc8f9114fc0006")
SPELLBOOK_PATCH = bytes.fromhex("24fc8c5d208c" + "34fc9d06" + "4e71")
SLOTNO_SITE = 0x262B8
SLOTNO_OLD = bytes.fromhex("34fc94d434fc96da34fc82cc")
SLOTNO_PATCH = bytes.fromhex("34fc8b8434fc8f8114fc0020")
MENU_ROW_SITE = 0x26CDA
EXPUP_SITE = 0x27258  # 경험치 목록 창을 그리는 `jsr $2A4C6.l` (6B)
EXPUP_OLD = bytes.fromhex("4eb90002a4c6")
EXPUP_AT = ARCHIVE_TOP - 0x280
EXPUP_STUB = bytes.fromhex("423900ff1af3") + bytes.fromhex("4ef90002a4c6")  # clr.b $FF1AF3.l · jmp $2A4C6.l(꼬리 호출 — 원래 jsr 의 복귀를 그대로 쓴다)
EXPUP_PATCH = bytes.fromhex("4eb9") + EXPUP_AT.to_bytes(4, "big")
MENU_ROW_PATCH = bytes.fromhex("60000022")  # bra.w $26CFE

# 🔴 HUD 장 제목 가운데(마스터 11-08 「장 제목 전 기종 가운데」 — 원판도 틀보다 약 18px 왼쪽이었다): 제목 문자열(`$FF1B3C`, 30B 칸 — 세이브·카드 줄과 같은 바이트라 데이터로는 못 옮긴다)을
# **그리기 직전에** 가운데로 다시 놓는다. 그리기 호출(`0x2550E: bsr.w $2A654` + `rts`, 6B)을 스텁으로 — 스텁은 앞뒤 공백을 떼고(공백=0x20 1B=6px, 한글·전각 2B=12px)
# 글 폭(len B)의 가운데가 글 영역 가운데(틀 224px − 좌우 8px = 208px → 칸 안 104px = 17.33B)에 오도록 앞 공백 s' = (35−len)/2 B 로 스택 버퍼 30B 에 다시 쓴 뒤 같은 그리기를 부른다.
# 칸(30B)을 넘지 않게 s'+len ≤ 30 으로 자른다. 세이브에 든 옛 문자열도 같은 길이라 그대로 가운데로 온다.
# HUD 지명 칸(72px)의 글 가운데는 박스 안(227~316px) 가운데보다 5.5px 왼쪽이다 — 칸 원점이 박스 왼쪽 + 4px(실화면 엘아스타 글리프 150/150 일치로 x=231 확정, 11-08).
# 앞 공백을 한 바이트(6px) 늘려 오른쪽으로 민다(칸 안 여백은 모든 항목이 좌우 ≥1B 라 들어간다) → 쏠림 +0.5px.
PLACE_SHIFT_B = 1
TITLE_SITE = 0x2550E
TITLE_OLD = bytes.fromhex("61005144" "4e75")
TITLE_AT = ARCHIVE_TOP - 0x168  # 스텁이 띠 한글 내림 루프로 164B 가 돼 8B 앞당겼다(뒤는 DEBUG_VIEW_AT = -0xC0)


def _title_stub() -> bytes:
    prog: list = [
        bytes.fromhex("48e7f0b0"),  # movem.l d0-d3/a0/a2/a3,-(a7)
        bytes.fromhex("204b"),  # movea.l a3,a0 (원본 문자열)
        bytes.fromhex("4fefffdc"),  # lea -36(a7),a7 (버퍼)
        bytes.fromhex("244f"),  # movea.l a7,a2
        bytes.fromhex("701d"),  # moveq #29,d0
        ("L", "fill"),
        bytes.fromhex("14fc0020"),  # move.b #$20,(a2)+
        ("d", 0x51C8, "fill"),  # dbra d0,fill
        bytes.fromhex("421a421a"),  # clr.b (a2)+ x2 (끝 표식)
        bytes.fromhex("7200"),  # moveq #0,d1 (첫 비공백)
        ("L", "ls"),
        bytes.fromhex("0c3000201000"),  # cmpi.b #$20,(a0,d1.w)
        ("b", 0x66, "lf"),  # bne.s lf
        bytes.fromhex("5241"),  # addq.w #1,d1
        bytes.fromhex("0c41001e"),  # cmpi.w #30,d1
        ("b", 0x66, "ls"),  # bne.s ls
        ("L", "lf"),
        bytes.fromhex("741e"),  # moveq #30,d2 (끝 다음)
        ("L", "le"),
        bytes.fromhex("b441"),  # cmp.w d1,d2
        ("b", 0x67, "ef"),  # beq.s ef
        bytes.fromhex("0c30002020ff"),  # cmpi.b #$20,-1(a0,d2.w)
        ("b", 0x66, "ef"),  # bne.s ef
        bytes.fromhex("5342"),  # subq.w #1,d2
        ("b", 0x60, "le"),  # bra.s le
        ("L", "ef"),
        bytes.fromhex("3602"),  # move.w d2,d3
        bytes.fromhex("9641"),  # sub.w d1,d3 (len)
        ("b", 0x67, "go"),  # beq.s go — 빈 제목
        bytes.fromhex("7023"),  # moveq #35,d0 — (35−길이)>>1: 실화면 잉크 최근접(11-10: 34 는 홀수 길이 제목이 −4.5px 왼쪽으로 쏠렸다 — 1~4장 띠 반각 2칸 복원 뒤 재측정)
        bytes.fromhex("9043"),  # sub.w d3,d0
        bytes.fromhex("e240"),  # asr.w #1,d0
        ("b", 0x6C, "pos"),  # bge.s pos
        bytes.fromhex("7000"),  # moveq #0,d0
        ("L", "pos"),
        bytes.fromhex("3400"),  # move.w d0,d2
        bytes.fromhex("d443"),  # add.w d3,d2
        bytes.fromhex("0c42001e"),  # cmpi.w #30,d2
        ("b", 0x6F, "fit"),  # ble.s fit
        bytes.fromhex("701e"),  # moveq #30,d0
        bytes.fromhex("9043"),  # sub.w d3,d0
        ("L", "fit"),
        bytes.fromhex("45f70000"),  # lea 0(a7,d0.w),a2
        bytes.fromhex("d0c1"),  # adda.w d1,a0
        bytes.fromhex("5343"),  # subq.w #1,d3
        ("L", "cp"),
        bytes.fromhex("14d8"),  # move.b (a0)+,(a2)+
        ("d", 0x51CB, "cp"),  # dbra d3,cp
        ("L", "go"),
        # 🔴 띠 전용 한글 — 한글(코드 0x8A~0x9F 리드)만 코드 +0x5800 로 바꿔 **한 행 내린 띠 글리프**를 그린다(숫자는 그대로, 마스터 11-09 「숫자는 그대로 두고
        # 한글만 한 칸 내리면」). 버퍼(30B)를 훑으며 리드가 0x81 이상이면 뒤 바이트를 건너뛴다.
        bytes.fromhex("244f"),  # movea.l a7,a2
        bytes.fromhex("41ea001e"),  # lea 30(a2),a0 (끝)
        ("L", "lp"),
        bytes.fromhex("b5c8"),  # cmpa.l a0,a2
        ("b", 0x64, "lx"),  # bcc.s lx
        bytes.fromhex("121a"),  # move.b (a2)+,d1
        bytes.fromhex("0c010081"),  # cmpi.b #$81,d1
        ("b", 0x65, "lp"),  # bcs.s lp (반각)
        bytes.fromhex("524a"),  # addq.l #1,a2 (뒤 바이트 건너뜀)
        bytes.fromhex("0c01008a"),  # cmpi.b #$8A,d1
        ("b", 0x65, "lp"),  # bcs.s lp
        bytes.fromhex("0c01009f"),  # cmpi.b #$9F,d1
        ("b", 0x62, "lp"),  # bhi.s lp
        bytes.fromhex("062a0058fffe"),  # addi.b #$58,-2(a2)
        ("b", 0x60, "lp"),  # bra.s lp
        ("L", "lx"),
        bytes.fromhex("264f"),  # movea.l a7,a3
        bytes.fromhex("4eb90002a654"),  # jsr $2A654.l
        bytes.fromhex("4fef0024"),  # lea 36(a7),a7
        bytes.fromhex("4cdf0d0f"),  # movem.l (a7)+,d0-d3/a0/a2/a3
        bytes.fromhex("4e75"),  # rts
    ]
    pos, labels = 0, {}
    for it in prog:
        if isinstance(it, bytes):
            pos += len(it)
        elif it[0] == "L":
            labels[it[1]] = pos
        elif it[0] == "b":
            pos += 2
        else:
            pos += 4
    out, pos = b"", 0
    for it in prog:
        if isinstance(it, bytes):
            out += it
            pos += len(it)
        elif it[0] == "b":
            d = labels[it[2]] - (pos + 2)
            assert -128 <= d < 128 and d != 0, (it, d)
            out += bytes([it[1], d & 0xFF])
            pos += 2
        elif it[0] == "d":
            d = labels[it[2]] - (pos + 2)
            assert -32768 <= d < 0
            out += it[1].to_bytes(2, "big") + (d & 0xFFFF).to_bytes(2, "big")
            pos += 4
    return out


TITLE_STUB = _title_stub()
assert len(TITLE_STUB) <= 0xA8, len(TITLE_STUB)
TITLE_PATCH = bytes.fromhex("4ef9") + TITLE_AT.to_bytes(4, "big")  # jmp 스텁 (6B — bsr.w + rts 자리)


class Rom:
    """쓰기 통로 하나 — 허용 구간(라벨) 밖은 거부."""

    ALLOWED: ClassVar[dict[str, tuple[int, int]]] = {
        "script-table": (0x134FA0, 0x134FA0 + 225 * 4),
        "battle-table": (battle.ARCHIVE, battle.ARCHIVE + battle.COUNT * 4),
        "battle": (BATTLE_LO, BATTLE_HI),
        "script": (SCRIPT_LO, SCRIPT_HI),
        "tail": (TAIL_LO, ARCHIVE_TOP),
        "font-tail": (ARCHIVE_TOP, ARCHIVE_TOP + FONT_RESERVE),
        "josa-code": (TAIL_HI - JOSA_RESERVE, TAIL_HI),
        "josa-tramp": (josa.DEAD_HANDLER, josa.DEAD_HANDLER + 12),
        "josa-name-hook": (josa.NAME_FN_PATCH, josa.NAME_FN_PATCH + 6),
        "josa-mon-hook": (josa.NAME_MON_PATCH, josa.NAME_MON_PATCH + 6),
        "josa-act-hook": (josa.NAME_ACT_PATCH, josa.NAME_ACT_PATCH + 6),
        "wrap-code": (TAIL_HI - JOSA_RESERVE - WRAP_RESERVE, TAIL_HI - JOSA_RESERVE),
        "wrap-tramp": (wordwrap.TRAMP, wordwrap.TRAMP + 6),
        "half-code": (
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE + halfspace.CODE_OFF,
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE + halfspace.CODE_OFF + halfspace.CODE_LEN,
        ),
        "half-tramp": (halfspace.TRAMP, halfspace.TRAMP + 6),
        "half-site": (halfspace.SITE, halfspace.SITE + 4),
        "punct-code": (TAIL_HI - punctwrap.CODE_LEN, TAIL_HI),
        "punct-site": (punctwrap.SITE, punctwrap.SITE + 6),
        **{f"wrap-site:{s:x}": (s, s + 4) for s in wordwrap.SITES},
        "field-hud-space-tramp": (
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE,
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE,
        ),
        "field-hud-space-site": (field_hud.SPACE_SITE, field_hud.SPACE_SITE + 6),
        "field-hud-align": (field_hud.ALIGN_SITE, field_hud.ALIGN_SITE + 4),
        **{f"field-hud-dir:{i}": (a, a + 2) for i, (a, _c, _w) in enumerate(field_hud.DIRECTIONS)},
        **{f"field-hud-suffix:{i}": (a, a + 4) for i, (a, _c, _w) in enumerate(field_hud.SUFFIX)},
        **{
            f"josa-tbl:{i:02x}": (josa.HANDLER_TBL + i * 2, josa.HANDLER_TBL + i * 2 + 2)
            for i in (josa.IDX_ACTOR, josa.IDX_ITEM)
        },
        **{
            f"josa-arg:{i:02x}": (josa.ARGLEN_TBL + i, josa.ARGLEN_TBL + i + 1)
            for i in (josa.IDX_ACTOR, josa.IDX_ITEM)
        },
        "spell-digit": (spell_digit.AT, spell_digit.AT + len(spell_digit.NEW)),
        "hud-status": (hud_status.BASE, hud_status.BASE + hud_status.N * hud_status.STRIDE),
        "font0-header": (0x1A54D2, 0x1A54DE),
        "font0-table": (0x1A551A, 0x1A6080),
        "font0-glyphs": (0x1A62CE, 0x1BA1FA),
        "font1-header": hangul.FONT1_HDR,
        "font5-header": hangul.FONT5_HDR,
        "checksum": (0x18E, 0x190),
        **{f"table:{t[0]}": (t[1], t[1] + (t[2] + 1) * t[4]) for t in tables.TABLES},
        **{f"table:{g[0]}": (g[1], g[1] + 0x200) for g in tables.ZGROUPS},
        **{f"table:{t[0]}": (t[1], t[1] + t[2] * t[3]) for t in tables.SLOTS},
        "font2-glyphs": hangul.FONT2_GLYPHS,
        "font4-header": hangul.FONT4_HDR,
        "font4-table": hangul.FONT4_TABLE,
        "font4-glyphs": hangul.FONT4_GLYPHS,
    }

    def __init__(self, data: bytes):
        self.orig = data
        self.buf = bytearray(data)
        self.log: list[tuple[str, int, bytes]] = []
        self.allowed = captions.widen_for_tail(
            dict(
                self.ALLOWED,
                **sysmsg.allowed(data),
                **sysmsg.allowed_tail(SYSMSG_TAIL_AT),
                **gfxtext.allowed(),
                **captions.allowed(data),
                **captions.allowed_tail(
                    TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE - CAPTION_RESERVE,
                    CAPTION_RESERVE,
                ),
            ),
            TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE - CAPTION_RESERVE,
            CAPTION_RESERVE,
        )

    def write(self, label: str, at: int, data: bytes) -> None:
        lo, hi = self.allowed[label]
        if not (lo <= at and at + len(data) <= hi):
            raise SystemExit(
                f"[{label}] 허용 구간 밖 쓰기 {at:#x}+{len(data)} (구간 {lo:#x}~{hi:#x})"
            )
        self.buf[at : at + len(data)] = data
        self.log.append((label, at, bytes(data)))

    def verify_no_overlap(self) -> None:
        """🔴 **앞 단계가 쓴 바이트가 최종 이미지에 살아남았나.**

        ⚠ 묻는 말이 「겹치나」가 아니라 **「살아남았나」**다(pce-ed1 이 다듬어 준 축, 2026-09-07) —
        겹침만 보면 **내 겹침 판정에 구멍이 있으면 같이 샌다.** 최종 버퍼와 대조하면 어떤 경로로
        덮였든 잡힌다. 덮인 것을 찾으면 **누가 덮었는지**까지 기록에서 되짚어 말해 준다.

        ss-ed1+2 가 2026-09-07 에 물린 자리다: 뒤 단계가 이주 자리를 **원본 덤프의 칸 경계**로
        골랐는데 앞 단계가 그 표를 통째로 다시 깔아 놓아, **살아 있는 한글 이름 위에 대사를 얹었다.**
        게이트 셋이 다 초록이었다 — 되읽기는 *자기가 쓴 직후*를, 라운드트립은 *덤프↔원본*을,
        무변경 구간은 *안 여는 자리*를 본다. **아무도 「두 단계가 같은 바이트를 썼나」를 안 본다.**

        주인 목록을 손으로 들지 않는다 — `write()` 가 남긴 기록만 보면 구조로 잡힌다.
        """
        for i, (label, at, data) in enumerate(self.log):
            if self.buf[at : at + len(data)] == data:
                continue
            culprit = next(
                (
                    f"[{lb}] {a:#x}+{len(dd)}"
                    for lb, a, dd in self.log[i + 1 :]
                    if a < at + len(data) and at < a + len(dd)
                ),
                "(뒤에 겹쳐 쓴 기록이 없다 — write() 를 안 거친 쓰기다)",
            )
            raise SystemExit(
                f"[{label}] {at:#x}+{len(data)} 가 최종 이미지에 안 남았다 — {culprit} 이 덮었다"
            )

    def verify_immutable(self) -> None:
        marks = bytearray(len(self.buf))
        for lo, hi in self.allowed.values():
            marks[lo:hi] = b"\x01" * (hi - lo)
        for i, (a, b) in enumerate(zip(self.orig, self.buf, strict=True)):
            if a != b and not marks[i]:
                raise SystemExit(f"무변경 구간이 바뀌었다 @{i:#x}")


def normalize(text: str) -> str:
    """부호 규칙(유저 확정 2026-09-05): 온점·쉼표·공백은 반각, 「…」 뒤에 온점 없음.

    ⚠ 「…」 **연속을 하나로 합치지 않는다**(10-18 — 옛 `re.sub(r"…+", "…")` 가 규칙 1-3 「원문 점 n 개 → …×round(n/3)」의 침묵 대사
    「……………」를 화면에서 「…」 하나로 줄이고 있었다. 문안·검사는 다 통과하고 **화면에서만 틀린** 부류).
    """
    text = text.replace("...", "…").replace("‥", "…").replace("。", ".").replace("、", ",")
    text = re.sub(r"…\s*[.。]", "…", text)
    return text


# 띄어 쓰되 줄에서 갈리면 안 되는 정본 이름(마스터 10-21 「노예 상인」 — 줄이 「노예」/「상인」으로 갈리면 읽기 나쁘다).
# 조판 동안만 붙임 공백(PUA, ps1 `NOBREAK_SP` 와 같은 값)으로 두고 끝나면 보통 공백으로 되돌린다.
# ⚠ 조판 중 폭은 1.0(공백 0.5 보다 넓다)이라 줄이 반 칸 일찍 끊길 수 있다 — 넘치는 쪽이 아니라 안전하다.
NOBREAK_SP = "\ue003"
# ⚠ 임시 — 이름을 여기 박아 둔 것은 임시다(관리자 10-21). 정본이 띄운 이름 전반을 공용 krwrap 의 비끊김 공백으로 받는 일은 라운드 뒤 main 과제.
NOBREAK_NAMES = ("노예 상인",)


LB_RULES = os.environ.get("ED_LB", "1") != "0"  # 규칙 2-16 후처리 — 지표 「전」 값을 재려고 끌 수 있다


def typeset(text: str, lead: str = "") -> list[list[str]]:
    """자유 문안 → 페이지(줄 목록). `\\f` 는 강제 페이지.

    `lead` 는 **첫 줄 앞에 그대로 붙는** 글자다(조판기가 지우면 안 되는 자리). 조사 훅 뒤의
    공백이 그것이다 — `<0e><ec01> 들어 있었습니다.` 에서 앞 공백이 없으면 화면이
    「눈물이들어 있었습니다」가 된다. krwrap 도 typeset 도 앞 공백을 지우므로 따로 받는다
    (2026-09-07 초벌 시험에서 잡았다). ⚠ 폭 검사는 **붙인 뒤**에 한다.
    """
    text = normalize(text)
    if LB_RULES and not text.lstrip().startswith("「"):  # 2-16 ① 문장 중간 손 개행은 공백으로 읽는다(문장 끝 개행은 아래 문장 단위 조판이 지킨다). 「…」로 연 표지판·비문 꼴은 손 개행을 둔다
        text = re.sub(r"(?<![.?!…」)])\n+(?=\S)", " ", text)
    for nm in NOBREAK_NAMES:
        text = text.replace(nm, nm.replace(" ", NOBREAK_SP))
    pages = []
    for chunk in text.split("\f"):
        chunk = chunk.strip()
        if not chunk:
            continue
        part = krwrap.wrap_pages(chunk, width=WIDTH, lines_per_page=LINES, strip_after="", cell_width=linebreak.cell_width)
        part = [[ln.replace(NOBREAK_SP, " ") for ln in pg] for pg in part]
        if LB_RULES:  # 2-16 절째 내림 · 쪽 끝 고아 · 창 고르기(tools/linebreak.py) — 덩이(`\f` 사이) 단위
            part = linebreak.improve_pages(part, WIDTH)
        pages += part
    if lead and pages and pages[0]:
        pages[0][0] = lead + pages[0][0]
    for pg in pages:
        if len(pg) > LINES:
            raise SystemExit(f"페이지가 {LINES}줄을 넘는다: {pg}")
        for ln in pg:
            if krwrap.text_width(ln, linebreak.cell_width) > WIDTH:
                raise SystemExit(f"줄이 {WIDTH}칸을 넘는다: {ln!r}")
    return pages


JOIN_PAGED: list[str] = []  # 이음 글이 쪽에 안 들어가 `<03>` → `<05>` 로 바꾼 자리(블록:키) — 빌드 끝에 알린다
WHERE = ""  # 지금 짜는 스트림(블록:키)


def typeset_after(body: str, lead: str, cur: float, lines: int) -> tuple[list[list[str]], bool | str]:
    """앞 조각이 이미 `cur` 칸을 쓴 줄에 이어 찍히는 글의 조판 → (쪽 목록, 첫 줄을 새 줄로 시작하나).

    조판기는 첫 줄 폭을 못 바꾸므로 `cur` 칸을 채우는 앞붙이 낱말을 달아 짠 뒤 떼어 낸다(어림은 반 칸 넉넉한 쪽).
    첫 낱말조차 안 들어가면 앞붙이 줄만 남는다 — 그 줄을 지우고 `True`(새 줄로 시작)를 낸다.
    ⚠ 쪽 줄 수(`LINES`)를 넘으면 `"page"` — 부른 쪽이 앞의 `<03>` 을 `<05>` 로 바꾼다."""
    k = int(cur + 0.5) if cur % 1 == 0 else int(cur)  # 앞붙이 + 공백 한 칸(0.5)이 cur 이상이 되게
    fill = "가" * k
    pages = typeset(fill + " " + body.strip())
    first = pages[0][0]
    if first == fill:
        pages[0] = pages[0][1:]
        if not pages[0]:
            pages = pages[1:]
        used = lines + len(pages[0]) if pages else lines
        brk = True
    else:
        pages[0][0] = lead + first[k + 1 :] if lead else first[k + 1 :]
        used = lines - 1 + len(pages[0])
        brk = False
    if used > LINES:
        # 쪽에 안 들어간다 — 키 대기(`<03>`)를 쪽 넘김(`<05>`)으로 바꿔 새 쪽 머리에서 시작한다(키 입력은 그대로 한 번)
        return typeset(body, lead), "page"
    return pages, brk


def build_stream(
    st: scene.Stream, ours: str, cs: hangul.Charset, *, raw_text: bool = False
) -> list[scene.Token]:
    """정본 한 항목 → 새 토큰 목록. 참조 토큰은 원본 토큰을 그대로(오프셋은 재조립이 다시 잰다).

    `raw_text` 면 조판기를 안 태운다 — 여백까지 우리가 정한 자리(장 카드·HUD 제목)를 위해서다.
    조판기는 줄을 strip 하고 다시 감기 때문에 「30바이트 고정」 같은 계약을 조용히 깬다.
    """
    refs = [t for t in st.tokens if t.ref]
    end = next((t for t in st.tokens if t.kind == "end"), None)
    out: list[scene.Token] = []
    pending_text: list[str] = []
    # `<03>`(키 대기) 뒤 글은 **앞 글과 같은 줄에 이어 찍힌다**(원판도 그렇다). 조판기는 조각마다 줄 머리부터 짜므로
    # 앞 조각이 쓴 폭 `cur` 을 첫 줄 폭에서 빼 줘야 한다(10-23 밤샘 — 「30 Gold면 충분하다.」 뒤 「가자!!」가 18칸을 넘었다).
    # None = 모른다(이름·수치 삽입 뒤 등 — 그땐 지금까지처럼 줄 머리로 짠다). `lines` = 이 쪽에서 쓴 줄 수.
    st_join = {"cur": 0.0, "lines": 1}

    def trim_seam_space():
        # 이음새 공백(위 `want`)은 뒤 글이 같은 줄에 이어질 때만 쓴다 — 뒤 글이 넘쳐 줄·쪽이 바뀌면 앞 줄 끝에 남아
        # 폭만 먹는다(「디나 공주라고? ⏎ 그 여자라면」, 10-28 검수 줄 끝 공백 38행). 줄을 가르는 자리에서 되돌려 지운다.
        for i in range(len(out) - 1, -1, -1):
            t = out[i]
            if t.kind == "ctl" and t.code == 0x03:
                continue
            if t.kind == "text" and t.raw.endswith(b" "):
                if len(t.raw) > 1:
                    out[i] = scene.Token(t.off, t.raw[:-1], "text")
                else:
                    del out[i]
            return

    def flush_text(at_end: bool = False, join: bool = False, brk: bool = False):
        if not pending_text:
            return
        if raw_text:
            body = "".join(pending_text)
            pending_text.clear()
            for pi, pg in enumerate(body.split("\f")):
                if pi:
                    out.append(scene.Token(0, b"\x05", "ctl", 0x05))
                for li, ln in enumerate(pg.split("\n")):
                    if li:
                        out.append(scene.Token(0, b"\x01", "ctl", 0x01))
                    if ln:
                        out.append(scene.Token(0, cs.encode(ln), "text"))
            return
        body = "".join(pending_text)
        lead = " " if body[:1] == " " else ""
        pages = typeset(body, lead)
        cur = st_join["cur"]
        lead_break = False
        if cur and pages and cur + krwrap.text_width(pages[0][0], linebreak.cell_width) > WIDTH:
            pages, lead_break = typeset_after(body, lead, cur, st_join["lines"])
        if lead and not pages and not at_end:
            # 조각이 공백 하나뿐이면(`<ebf0> <0e>…` — 「일행은 」과 품목 이름 사이) 조판기가 빈 쪽으로 보고 버려
            # 「일행은약초를」로 붙는다(sfc-ed2 가 같은 결함을 찾았다 10-19). 끝 코드 앞 공백만 버린다.
            pages = [[lead]]
        # 조각 **끝** 공백도 조판기가 지운다(`제 이름은 <0901>입니다` 가 「이름은류난」으로 붙는다 — 10-19
        # 전수 검수). 뒤에 이름·품목 코드가 이어지는 자리라 되살린다. 줄이 가득 차 못 붙이면 줄바꿈이 대신한다.
        # `join` = 뒤에 같은 쪽의 글이 이어 찍히는 자리(참조 · 줄·쪽 넘김 아닌 모든 제어코드(`<03>`·`<11..>`·`<12..>`·`<14..>`…) · 되돌림 끝 `<06>`) —
        # 문장 끝 부호로 끝났으면 이음새에 공백 하나를 낸다(「찾아왔다.안으로」 — 원문엔 없던 이음새 공백).
        want = body.endswith(" ") or (join and body[-1:] in ".?!…")
        if (
            not at_end
            and not brk
            and want
            and body.strip()
            and pages
            and pages[-1]
            and not pages[-1][-1].endswith(" ")
            and krwrap.text_width(pages[-1][-1] + " ", linebreak.cell_width) <= WIDTH
        ):
            pages[-1][-1] += " "
        pending_text.clear()
        if lead_break == "page" and out and out[-1].kind == "ctl" and out[-1].code == 0x03:
            trim_seam_space()
            out[-1] = scene.Token(0, b"\x05", "ctl", 0x05)
            JOIN_PAGED.append(WHERE)
            st_join.update(cur=0.0, lines=1)
        elif lead_break:
            trim_seam_space()
            out.append(scene.Token(0, b"\x01", "ctl", 0x01))
            st_join["lines"] += 1
            st_join["cur"] = 0.0
        for pi, pg in enumerate(pages):
            if pi:
                out.append(scene.Token(0, b"\x05", "ctl", 0x05))
                st_join["lines"] = 1
                st_join["cur"] = 0.0
            for li, ln in enumerate(pg):
                if li:
                    out.append(scene.Token(0, b"\x01", "ctl", 0x01))
                    st_join["lines"] += 1
                    st_join["cur"] = 0.0
                out.append(scene.Token(0, cs.encode(ln), "text"))
                if st_join["cur"] is not None:
                    st_join["cur"] += krwrap.text_width(ln, linebreak.cell_width)

    parts = textmap.parse_ours(ours)
    for pi_, (kind, val) in enumerate(parts):
        if kind == "text":
            pending_text.append(val)
        elif (
            LB_RULES
            and kind == "ctl"
            and val[0] == 0x01
            and val[1] is None
            and pending_text
            and pi_ + 1 < len(parts)
            and parts[pi_ + 1][0] == "text"
            and not st_join.get("prev") in (0x04, 0x09)
            and not linebreak.sentence_end(("".join(pending_text).split(" ") or [""])[-1])
            and "".join(pending_text).strip()
        ):
            pending_text.append(" ")  # 규칙 2-16 ① 문장 중간 손 개행은 공백으로 읽는다
        elif kind == "page":
            # 🔴 예전엔 `\f` 를 본문에 이어 붙여 조판기에 맡겼는데, **뒤에 제어코드가 오면**
            # 조판기가 빈 쪽으로 보고 버려 `<05>` 가 통째로 사라졌다(2026-09-07 실측: 퍼거슨 대화에서
            # 왕자의 말과 퍼거슨의 대답이 한 창에 붙었다). 쪽 넘김은 **여기서** 토큰으로 낸다.
            flush_text(brk=True)
            out.append(scene.Token(0, b"\x05", "ctl", 0x05))
            st_join.update(cur=0.0, lines=1)
        else:
            code, tgt, raw = val
            if tgt is not None:
                m = next((t for t in refs if t.code == code and t.target == tgt), None)
                if m is None:
                    raise SystemExit(
                        f"정본의 참조 <{code:02x}:{tgt:04x}> 가 원본 스트림에 없다 @{st.start:#x}"
                    )
                refs.remove(m)
                flush_text(join=True)
                out.append(m)
                st_join["cur"] = None  # 호출·분기가 채우는 폭은 모른다
            elif code in scene.END:
                flush_text(at_end=code != 0x06, join=code == 0x06)
                out.append(scene.Token(0, bytes([code]), "end", code))
            else:
                flush_text(join=code not in (0x01, 0x05), brk=code in (0x01, 0x05))
                out.append(scene.Token(0, raw, "ctl", code))
                if code == 0x01:
                    if st_join.get("prev") not in (0x04, 0x09):  # 이름표(`<1e>…<04>`·`<09nn>`) 뒤 `<01>` 은 머리줄 — 글 줄이 아니다
                        st_join["lines"] += 1
                    st_join["cur"] = 0.0
                elif code == 0x05:
                    st_join.update(cur=0.0, lines=1)
                elif code != 0x03:
                    st_join["cur"] = None  # 이름·수치 삽입 등 — 폭을 모른다
                st_join["prev"] = code
    flush_text(at_end=True)
    if refs:
        raise SystemExit(
            f"원본의 참조 {[hex(t.target) for t in refs]} 가 정본에 없다 @{st.start:#x}"
        )
    if end is not None and not (out and out[-1].kind == "end"):
        out.append(scene.Token(0, end.raw, "end", end.code))
    if not raw_text:
        strip_dead_seam_space(out)
    return out


def strip_dead_seam_space(out: list[scene.Token]) -> None:
    """뒤에 같은 줄로 이어질 글이 없는 이음새 공백을 지운다 — 글 조각 끝 공백 뒤에 효과음(`0C`)·참조만 있고 그 다음이
    줄·쪽 넘김·이름표(`09nn`)·끝(되돌림 끝 `06` 은 호출한 쪽 글과 이어지므로 제외)이면 그 공백은 쓸 데가 없다(10-30 전수 촬영: 「혹시 아십니까? 」 줄 끝 공백 —
    화면엔 안 보이나 폭만 먹는다). 참조 뒤가 글이면 호출 대상이 이어 찍을 수 있어 그대로 둔다."""
    for i in range(len(out) - 1, -1, -1):
        t = out[i]
        if t.kind != "text" or not t.raw.endswith(b" "):
            continue
        j = i + 1
        while j < len(out) and (out[j].ref or (out[j].kind == "ctl" and out[j].code == 0x0C)):
            j += 1
        nxt = out[j] if j < len(out) else None
        # `09nn` 은 이름표(바로 뒤 `<01>`)일 수도, 문장 속 파티 이름(뒤에 글이 이어진다 — 「나는 <0903>이라고」)일 수도 있다.
        # 뒤에 글이 이어지면 그 공백은 이름 앞 띄어쓰기다 — 지우면 「나는게일이라고」로 붙는다(변수 줄 조판 검사로 잡음).
        after = out[j + 1] if j + 1 < len(out) else None
        inline_name = (
            nxt is not None
            and nxt.kind == "ctl"
            and nxt.code == 0x09
            and not (after is not None and after.kind == "ctl" and after.code in (0x01, 0x05))
        )
        if not inline_name and (
            (nxt is not None and nxt.kind == "end" and nxt.code != 0x06)
            or (nxt is not None and nxt.kind == "ctl" and nxt.code in (0x01, 0x05, 0x04, 0x09))
        ):
            if len(t.raw) > 1:
                out[i] = scene.Token(t.off, t.raw[:-1], "text")
            else:
                del out[i]


def encode_tagged(s: str, cs: hangul.Charset) -> bytes:
    """`<fe0c>` 같은 raw 태그를 섞은 표 문안 → 바이트."""
    out = b""
    pos = 0
    for m in re.finditer(r"<([0-9a-fA-F]+)>", s):
        out += cs.encode(s[pos : m.start()]) + bytes.fromhex(m.group(1))
        pos = m.end()
    return out + cs.encode(s[pos:])


def build_tables(orig: bytes, names: dict, cs: hangul.Charset) -> list[tuple[str, int, bytes]]:
    """표 → (라벨, 자리, 본문). 폭 = 원본 본문 길이. 넘치는 항목은 **전부 모아** 실패로 알린다."""
    out = []
    over = []
    for name, recs in tables.records(orig).items():
        tbl = names.get(name, {})
        align = tables.align_of(name)
        for i, (pos, raw) in enumerate(recs):
            ours = normalize(tbl.get(str(i), {}).get("ours", ""))
            if not ours:
                continue
            enc = encode_tagged(ours, cs)
            if name in tables.SLOT_CAP:  # 06 종결 칸 — 이름+06 만, 나머지는 원본
                if len(enc) > tables.SLOT_CAP[name]:
                    over.append(f"{name}[{i}] {ours!r} {len(enc)}B > {tables.SLOT_CAP[name]}B")
                    continue
                out.append((f"table:{name}", pos, enc + b"\x06"))
                continue
            w = len(raw)
            if len(enc) > w:
                over.append(f"{name}[{i}] {ours!r} {len(enc)}B > {w}B")
                continue
            n = w - len(enc)
            if align == "right":
                body = b" " * n + enc
            elif align == "center":
                # 🔴 `center` 를 안 다뤄 장 제목·지명이 **왼쪽에 붙어** 있었다(2026-09-06).
                # 원본이 앞뒤로 공백을 나눠 넣은 자리다 — 남는 칸은 뒤에 준다(반각 6px 단위).
                lead = n // 2 + (PLACE_SHIFT_B if name in ("place_a", "place_b") else 0)
                body = b" " * lead + enc + b" " * (n - lead)
            else:
                body = enc + b" " * n
            out.append((f"table:{name}", pos, body))
    if over:
        raise SystemExit(
            "표 항목이 폭을 넘는다 — 칸 배치(textmap/ui_layout.json)나 정본 값을 줄인다:\n    "
            + "\n    ".join(over)
        )
    return out


def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_textmaps() -> dict:
    """정본 전부 — 대본(script/*.json) · 표(사전·정본 + ui_layout.json) · 시스템 메시지 · 자막 · 전투(메시지·몬스터)."""
    return {
        "maps": textmap.load_all(),
        "names": dict_names.names(),
        "smap": _load(sysmsg.MAP_JSON),
        "cmap": _load(captions.MAP_JSON),
        "bmap": _load(battle.MAP_JSON),
        "monsters": battle.monsters(common.rom()),
    }


def collect_chars(tm: dict) -> set[str]:
    """정본 전체가 쓰는 글자 집합(태그 제거 · 부호 정규화 뒤) — 글꼴 표 0 과 코드 배정의 분모."""
    chars: set[str] = set()
    strip = lambda t: normalize(re.sub(r"<[^>]*>", "", t))
    for m in tm["maps"].values():
        for e in m["streams"].values():
            chars.update(strip(e.get("ours", "")))
    for t in tm["names"].values():
        for e in t.values():
            chars.update(normalize(e.get("ours", "")))
    for e in tm["smap"].values():
        chars.update(strip(e.get("ours", "")))
    for e in tm["cmap"].values():
        chars.update(strip(e.get("ours", "")))
    for e in tm["bmap"].values():
        chars.update(strip(battle.expand_names(e.get("ours", ""), tm["monsters"])))
    for e in tm["monsters"].values():
        chars.update(e.get("ours", ""))
    chars.update(field_hud.chars())  # 필드 HUD 뒷말·방위(문안을 안 거친다) — 늘 굽는다
    chars.update(josa.chars())  # 조사 훅이 그리는 글자(는은가이를을와과으로) — 늘 굽는다
    chars.update(halfspace.chars())  # 「의␣」 — 아이템 칸 14B 에 반각 공백을 녹인 합성 글자
    chars.update(field_names.chars())  # 대본 블록 91 지명 표(문안 스트림 밖) — 늘 굽는다
    chars.update(party_template.chars())  # 블록 141 파티 합류 레코드(소니아) — 늘 굽는다
    chars.update(actor_names.chars())  # 블록 161 배우 이름 레코드(문안 스트림 밖) — 늘 굽는다
    return chars


def main(check_only: bool = False) -> None:
    global WHERE
    orig = common.rom()
    tm = load_textmaps()
    maps, names, smap, cmap, bmap, monsters = (
        tm["maps"],
        tm["names"],
        tm["smap"],
        tm["cmap"],
        tm["bmap"],
        tm["monsters"],
    )
    chars = collect_chars(tm)
    cs = hangul.Charset(orig, chars)
    table_writes = build_tables(orig, names, cs)
    sys_writes = sysmsg.plan(
        orig,
        {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in smap.items()},
        cs.encode,
        tail_at=SYSMSG_TAIL_AT,
    )
    cap_writes = captions.plan(
        orig,
        {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in cmap.items()},
        cs.encode,
        tail_at=TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE - CAPTION_RESERVE,
    )
    print(
        f"  정본 블록 {len(maps)} · 한글 {len(cs.hangul)}자 · 표 0 {len(cs.entries)}/{cs.r0['entries']}"
    )

    base = archives.ARCHIVES["script"][0]
    bl = archives.blocks(orig, base)
    new_blocks: dict[int, bytes] = {}
    posdump: dict[int, dict[int, int]] = {}
    for n, m in sorted(maps.items()):
        s, b, e = bl[n]
        mod = scene.parse_module(b)
        replace = {}
        for k, ent in m["streams"].items():
            if not ent.get("ours"):
                continue
            off = int(k, 16)
            st = mod.streams.get(off)
            if st is None:
                raise SystemExit(f"블록 {n}: 스트림 {k} 가 없다")
            if textmap.jp_key(st) != ent["jp"]:
                raise SystemExit(f"블록 {n} 스트림 {k}: 원문 해시가 갈렸다")
            WHERE = f"{n:03d}:{k}"
            replace[off] = build_stream(st, ent["ours"], cs, raw_text=bool(ent.get("raw")))
        if not replace:
            continue
        new = scene.reassemble(mod, replace)
        if os.environ.get("ED_DUMP_POS"):
            posdump[n] = dict(scene.LAST_POS)
        scene.verify_reassembly(mod, new, replace)
        new_blocks[n] = new
    if JOIN_PAGED:
        print(f"  이음 글 {len(JOIN_PAGED)}곳은 쪽에 안 들어가 `<03>` → `<05>` : {' '.join(JOIN_PAGED)}")
    if posdump:  # 검수용(ED_DUMP_POS=1): 씬별 「원본 스트림 시작 → 새 자리」 — 롬 바이트에는 영향이 없다
        (common.BUILD_DIR / "pos.json").write_text(
            json.dumps({str(k): {hex(a): hex(b) for a, b in v.items()} for k, v in posdump.items()})
        )
    # 대본 블록 91 — 문안 스트림 밖의 지명 표(입장 배너). scene.py 로는 안 보여 별도 경로로 얹는다.
    fn_base = new_blocks.get(field_names.BLOCK, bl[field_names.BLOCK][1])
    new_blocks[field_names.BLOCK] = field_names.new_block(fn_base, cs)
    for dn in field_names.DEST_JP:  # 블록 92·93 목적지 표(같은 14B 칸 꼴)
        new_blocks[dn] = field_names.new_dest_block(dn, new_blocks.get(dn, bl[dn][1]), cs)
    # 블록 141 파티 합류 레코드(소니아) — 같은 길이로 덮는다
    new_blocks[party_template.BLOCK] = party_template.new_block(
        new_blocks.get(party_template.BLOCK, bl[party_template.BLOCK][1]), cs
    )
    # 블록 161 배우 이름 레코드 둘 — 같은 길이로 덮는다
    new_blocks[actor_names.BLOCK] = actor_names.new_block(
        new_blocks.get(actor_names.BLOCK, bl[actor_names.BLOCK][1]), cs
    )
    battle_blocks: dict[int, bytes] = {}
    for n, (_s, bb, _e) in enumerate(battle.blocks(orig)):
        nb = battle.plan_block(
            bb,
            n,
            {k: dict(v, ours=normalize(v.get("ours", ""))) for k, v in bmap.items()},
            monsters,
            cs.encode,
        )
        if nb is not None:
            battle_blocks[n] = nb
    if check_only:
        print(
            f"  게이트 OK — 바뀌는 블록 {len(new_blocks)} · 표 항목 {len(table_writes)} · 시스템 메시지 쓰기 {len(sys_writes)} · 자막 쓰기 {len(cap_writes)} · 전투 블록 {len(battle_blocks)}"
        )
        return

    rom = Rom(orig)
    # 1. 대본 아카이브 — 블록을 원 자리부터 차례로, 넘치면 꼬리로
    cur, region = SCRIPT_LO, "script"
    script_end = None
    table = bytearray(orig[base : base + 225 * 4])
    for n, (s, _b, e) in enumerate(bl):
        packed = lz.encode(new_blocks[n]) if n in new_blocks else orig[s:e]
        packed = packed + (b"\x00" if len(packed) & 1 else b"")
        if region == "script" and cur + len(packed) > SCRIPT_HI:
            script_end, cur, region = cur, TAIL_LO, "tail"
        if region == "tail" and cur + len(packed) > ARCHIVE_TOP:
            raise SystemExit("대본 아카이브가 꼬리 빈 공간도 넘는다")
        rom.write(region, cur, packed)
        table[n * 4 : n * 4 + 4] = struct.pack(">I", cur - base)
        cur += len(packed)
    rom.write("script-table", base, bytes(table))
    # 새 블록이 앞에서부터 채우고 남은 뒤쪽은 원판 압축 바이트가 죽은 채 남는다 — 통째 블록 하나가 남아 일본어 사본이 된다
    # (check_orphan_copies.py, 마스터 11-17 전 게임 점검). 참조가 없는 줄 알지만 「읽히는 길이 없다」는 증명이 아니라 지워 둔다.
    s_end = cur if script_end is None else script_end
    if s_end < SCRIPT_HI:
        rom.write("script", s_end, b"\xff" * (SCRIPT_HI - s_end))
    # 1b. 전투 아카이브 — 같은 규칙, 꼬리는 대본과 이어 쓴다
    bbase = battle.ARCHIVE
    bbl = battle.blocks(orig)
    btable = bytearray(orig[bbase : bbase + battle.COUNT * 4])
    bcur, bregion = BATTLE_LO, "battle"
    for n, (s, _b, e) in enumerate(bbl):
        packed = lz.encode(battle_blocks[n]) if n in battle_blocks else orig[s:e]
        packed = packed + (b"\x00" if len(packed) & 1 else b"")
        if bregion == "battle" and bcur + len(packed) > BATTLE_HI:
            bcur, bregion = (cur if region == "tail" else TAIL_LO), "tail"
        if bregion == "tail" and bcur + len(packed) > ARCHIVE_TOP:
            raise SystemExit("전투 아카이브가 꼬리 빈 공간도 넘는다")
        rom.write(bregion, bcur, packed)
        btable[n * 4 : n * 4 + 4] = struct.pack(">I", bcur - bbase)
        bcur += len(packed)
    if bregion == "battle" and bcur < BATTLE_HI:  # 전투 아카이브도 같다 — 남는 뒤쪽 원판 블록을 지운다
        rom.write("battle", bcur, b"\xff" * (BATTLE_HI - bcur))
    if bregion == "tail":
        cur, region = bcur, "tail"
    rom.write("battle-table", bbase, bytes(btable))
    # 2. 글꼴 리소스 0
    hdr, tbl, gl = cs.resource0()
    rom.write("font0-header", cs.r0["hdr"], hdr)
    rom.write("font0-table", cs.r0["table"], tbl)
    rom.write("font0-glyphs", cs.r0["desc"], orig[cs.r0["desc"] : cs.r0["desc"] + 4] + gl)
    for label, pos, body in hangul.resource1(cs, FONT_AT):  # 반각 쉼표 — 표 0 이 비운 자리에
        rom.write(label, pos, body)
    # 네오둥근모는 반각도 리소스 5 로 그리니 공백(0x20)도 표에 든다 — 빠지면 조회가 첫 항목(「!」)으로 떨어진다
    cap5 = {
        c
        for c in captions.font5_chars(cmap)
        if c.strip()
        or (c == " " and captions.FONT_SRC in ("neodgm", "galmuri14", "galmuri11bold", "galmuri11"))
    }
    if captions.FONT_ID and cap5:  # <fd85> 를 단 자막 전용 글꼴(리소스 5, Galmuri14 14×14)
        for label, pos, body in hangul.resource5(
            cs,
            cap5,
            hangul.layout_after_r1(cs, FONT_AT),
            cell=captions.FONT_CELL,
            source=captions.FONT_SRC,
            tail_end=FONT_AT + FONT_RESERVE,
        ):
            rom.write(label, pos, body)
    for label, pos, body in hangul.resource2_labels():  # HUD 「ｱﾄ」 → 「남다」 (8×8, 마스터 도안)
        rom.write(label, pos, body)
    hud_chars = set()
    for grp in ("party_rec", "party_name"):
        for e in names.get(grp, {}).values():
            hud_chars.update(re.sub(r"<[^>]*>", "", e.get("ours", "")))
    hud_chars.update(party_template.chars())  # 소니아(블록 141 레코드)도 HUD 이름칸에 그려진다
    for label, pos, body in hangul.resource4(cs, hud_chars):  # HUD 이름 12×12
        rom.write(label, pos, body)
    # 2b-3. 주문 레벨 숫자를 반각으로(「레지나1을」) — 이름 버퍼 빌더의 14B
    spell_digit.check(orig)
    for label, pos, body in spell_digit.plan():
        rom.write(label, pos, body)
    # 2b-2. HUD 상태이상 8칸(守跳毒眠黙乱気絶 → 수·반·독·잠·묵·혼·기·절) — 무압축 타일 교체(마스터 10-10)
    for label, pos, body in hud_status.plan():
        rom.write(label, pos, body)
    # 2c. 조사 훅 — 이름 뒤 조사를 런타임에 고른다(제어코드 EB·EC)
    for label, pos, body in josa.plan(orig, cs, TAIL_HI - JOSA_RESERVE):
        rom.write(label, pos, body)
    # 2d. 어절 줄넘김 — 렌더러($978C)가 넘칠 때 글자가 아니라 어절을 다음 줄로 보낸다(마스터 2026-09-30)
    for label, pos, body in wordwrap.plan(orig, TAIL_HI - JOSA_RESERVE - WRAP_RESERVE):
        rom.write(label, pos, body)
    for label, pos, body in halfspace.plan(cs, TAIL_HI - JOSA_RESERVE - WRAP_RESERVE):
        rom.write(label, pos, body)
    # 2d-2. 반각 부호(. , ! ?)는 줄 끝에서 4px 더 허용 — 엔진 자동 줄바꿈이 1px 로 꺾는 것을 없앤다(마스터 10-08)
    #       꼬리는 조사 훅 예약 **맨 끝**(훅 최대치 771B 뒤)에 둔다 — 겹치면 빌드가 막는다
    if josa.size(cs) > JOSA_RESERVE - punctwrap.CODE_LEN:
        raise SystemExit("조사 훅이 부호 줄바꿈 꼬리 자리를 침범한다 — JOSA_RESERVE 를 늘린다")
    for label, pos, body in punctwrap.plan(TAIL_HI - punctwrap.CODE_LEN):
        rom.write(label, pos, body)
    # ⚠ 합성 글리프(field_hud·field_names 의 PUA 콘덴스드 슬라이스)는 뺀다 — 일부러 큰 왼쪽
    # 여백을 구워 둔 자리라(공백을 그림 안에 녹였다) 정상 글자처럼 재면 문턱이 깨진다. 이
    # 글리프들은 로그 렌더러($978C)를 안 타는 고정폭 HUD 전용이라 애초에 안 재도 된다.
    normal_wide = {v for k, v in cs.hangul.items() if k not in hangul.CUSTOM_GLYPHS}
    gap, sp = wordwrap.gap_gate(bytes(rom.buf), normal_wide)
    print(
        f"  어절 줄넘김 — 글자 틈 최대 {gap}px < 문턱 {wordwrap.SPACE_PX}px ≤ 공백 틈 최소 {sp}px"
    )
    # 2e. 필드 HUD 뒷말(부근·입구)·방위(동서남북) — 문안을 안 거치고 코드가 SJIS 를 직접 찍는 여덟 자리
    field_hud_tramp_at = TAIL_HI - JOSA_RESERVE - WRAP_RESERVE - FIELD_HUD_RESERVE
    for label, pos, body in field_hud.plan(cs, field_hud_tramp_at):
        rom.write(label, pos, body)
    # 3. 고정 폭 표(아이템·주문·지명·메뉴 라벨) — 제자리
    for label, pos, body in table_writes:
        rom.write(label, pos, body)
    # 3a. 그래픽 문자(타이틀 메뉴 셀)
    for label, pos, body in gfxtext.plan(orig, names):
        rom.write(label, pos, body)
    # 3b. 시스템 메시지 묶음 + 참조 명령
    for label, pos, body in sys_writes:
        rom.write(label, pos, body)
    # 3c. 오프닝 자막 · 엔딩 문안 영역 + 표
    for label, pos, body in cap_writes:
        rom.write(label, pos, body)
    # 3c2. 디버그 진입키(A→A+C 1초) + 「경험치UP」 행 숨김 — 제품 롬에 들어간다(마스터 10-24)
    rom.allowed["debug-key-stub"] = (KEY_AT, KEY_AT + len(KEY_STUB))
    rom.write("debug-key-stub", KEY_AT, KEY_STUB)
    if bytes(rom.buf[VBL_SITE : VBL_SITE + 12]) != VBL_OLD:
        raise SystemExit("디버그 진입키 VBlank 자리(0xB614)의 원본 명령이 다르다")
    rom.allowed["debug-key-vbl-stub"] = (VBL_AT, VBL_AT + len(VBL_STUB))
    rom.write("debug-key-vbl-stub", VBL_AT, VBL_STUB)
    rom.allowed["debug-key-vbl-site"] = (VBL_SITE, VBL_SITE + len(VBL_PATCH))
    rom.write("debug-key-vbl-site", VBL_SITE, VBL_PATCH)
    if bytes(rom.buf[KEY_SITE : KEY_SITE + 6]) != KEY_SITE_OLD:
        raise SystemExit("디버그 진입키 자리(0xB772, VBlank 패드 갱신 호출)의 원본 명령이 다르다")
    rom.allowed["debug-key-site"] = (KEY_SITE, KEY_SITE + len(KEY_PATCH))
    rom.write("debug-key-site", KEY_SITE, KEY_PATCH)
    if bytes(rom.buf[KEY_SITE2 : KEY_SITE2 + 6]) != KEY_SITE_OLD:
        raise SystemExit("디버그 진입키 둘째 자리(0xBA56)의 원본 명령이 다르다")
    rom.allowed["debug-key-site2"] = (KEY_SITE2, KEY_SITE2 + len(KEY_PATCH))
    rom.write("debug-key-site2", KEY_SITE2, KEY_PATCH)
    if bytes(rom.buf[SPELL_LIST_SITE : SPELL_LIST_SITE + 6]) != SPELL_LIST_OLD:
        raise SystemExit("주문 목록 줄 복사 루프(0x276E0)의 원본 명령이 다르다")
    rom.allowed["spell-list-stub"] = (SPELL_LIST_AT, SPELL_LIST_AT + len(SPELL_LIST_STUB))
    rom.write("spell-list-stub", SPELL_LIST_AT, SPELL_LIST_STUB)
    rom.allowed["spell-list-site"] = (SPELL_LIST_SITE, SPELL_LIST_SITE + len(SPELL_LIST_PATCH))
    rom.write("spell-list-site", SPELL_LIST_SITE, SPELL_LIST_PATCH)
    # 「경험치UP」 여섯째 줄은 원판 코드(0x26CDA)가 `$FF01B2`==0x62(디버그 켬)일 때만 더한다 — 숨기던 건너뛰기를 걷었다(마스터 11-07 「다 살려두자」).
    # 원판 고장 원인: 경험치 목록 창이 열릴 때 커서 줄 변수 `$FF1AF3`(앞 메뉴에서 쓰던 5)가 안 지워져 인물 번호 5 = 빈 슬롯을 읽고 무한 루프 → 창을 그리기 전에 0 으로.
    if bytes(rom.buf[EXPUP_SITE : EXPUP_SITE + 6]) != EXPUP_OLD:
        raise SystemExit("경험치UP 목록 창 호출(0x27258)의 원본 명령이 다르다")
    rom.allowed["expup-stub"] = (EXPUP_AT, EXPUP_AT + len(EXPUP_STUB))
    rom.write("expup-stub", EXPUP_AT, EXPUP_STUB)
    rom.allowed["expup-site"] = (EXPUP_SITE, EXPUP_SITE + len(EXPUP_PATCH))
    rom.write("expup-site", EXPUP_SITE, EXPUP_PATCH)
    if bytes(rom.buf[TITLE_SITE : TITLE_SITE + 6]) != TITLE_OLD:
        raise SystemExit("HUD 장 제목 그리기 호출(0x2550E)의 원본 명령이 다르다")
    rom.allowed["title-center-stub"] = (TITLE_AT, TITLE_AT + len(TITLE_STUB))
    rom.write("title-center-stub", TITLE_AT, TITLE_STUB)
    rom.allowed["title-center-site"] = (TITLE_SITE, TITLE_SITE + len(TITLE_PATCH))
    rom.write("title-center-site", TITLE_SITE, TITLE_PATCH)
    for lbl, site, old, new in (
        ("spellbook-suffix", SPELLBOOK_SITE, SPELLBOOK_OLD, SPELLBOOK_PATCH),
        ("slot-number-suffix", SLOTNO_SITE, SLOTNO_OLD, SLOTNO_PATCH),
    ):
        if bytes(rom.buf[site : site + len(old)]) != old:
            raise SystemExit(f"{lbl}: {site:#x} 의 원본 명령이 다르다")
        rom.allowed[lbl] = (site, site + len(new))
        rom.write(lbl, site, new)
    # 3d. 🔴 시험 빌드 전용 디버그 스위치(ED_DEBUG=1, 꼬리표 test-*) — 제품 롬에는 한 바이트도 안 닿는다
    if DEBUG_BUILD:
        if not common.BUILD_TAG.startswith(DEBUG_TAGS_OK):
            raise SystemExit(
                "ED_DEBUG=1 은 디버그 전용 꼬리표(debug · test-*)에서만 된다 — 예: ED_BUILD_TAG=debug"
            )
        rom.allowed["debug-flag"] = (DEBUG_SITE, DEBUG_SITE + len(DEBUG_PATCH))
        rom.write("debug-flag", DEBUG_SITE, DEBUG_PATCH)
        rom.allowed["debug-skip-site"] = (DEBUG_SKIP_SITE, DEBUG_SKIP_SITE + len(DEBUG_SKIP_PATCH))
        rom.write("debug-skip-site", DEBUG_SKIP_SITE, DEBUG_SKIP_PATCH)
        rom.allowed["debug-skip-stub"] = (
            DEBUG_SKIP_STUB_AT,
            DEBUG_SKIP_STUB_AT + len(DEBUG_SKIP_STUB),
        )
        rom.write("debug-skip-stub", DEBUG_SKIP_STUB_AT, DEBUG_SKIP_STUB)
        rom.allowed["debug-view-stub"] = (DEBUG_VIEW_AT, DEBUG_VIEW_AT + len(DEBUG_VIEW_STUB))
        rom.write("debug-view-stub", DEBUG_VIEW_AT, DEBUG_VIEW_STUB)
        rom.allowed["debug-view-site"] = (DEBUG_VIEW_SITE, DEBUG_VIEW_SITE + len(DEBUG_VIEW_PATCH))
        rom.write("debug-view-site", DEBUG_VIEW_SITE, DEBUG_VIEW_PATCH)
        rom.allowed["debug-header"] = (DEBUG_HDR_AT, DEBUG_HDR_AT + len(DEBUG_HDR))
        rom.write("debug-header", DEBUG_HDR_AT, DEBUG_HDR)
        print(
            "  ⚠ 디버그 빌드 — $FF01B2=0x62 (C+방향=고속 이동·벽 통과, 시스템 메뉴 「경험치UP」은 누르면 굳는다)"
        )
    # 4. 체크섬 · 대조 · 출력
    rom.write("checksum", 0x18E, struct.pack(">H", common.header_checksum(rom.buf)))
    rom.verify_no_overlap()
    nsame = hangul.verify_glyph_distinct(
        bytes(rom.buf), tuple((cs.hangul[p], cs.hangul[b]) for p, b in halfspace.COMPOSITES)
    )
    print(f"  구운 글리프 중복 — 허용된 같은 묶음 {nsame}(합성 글자·원판 줄표), 그 밖 0")
    _sc = archives.ARCHIVES["script"][0]
    nev = scene.verify_event_tables(
        [b for _s, b, _e in archives.blocks(orig, _sc)],
        [b for _s, b, _e in archives.blocks(bytes(rom.buf), _sc)],
    )
    print(f"  씬 이벤트 표 {nev}개 — 전부 원판과 바이트까지 같다")
    nwr = battle.verify_mid_writes(orig, bytes(rom.buf))
    print(f"  전투 블록 코드의 문안 한복판 쓰기 {nwr}곳 — 전부 우리 롬에서도 같은 제어 바이트를 가리킨다")
    ncall = battle.verify_calls(orig, bytes(rom.buf))
    print(f"  전투 스트림 call·goto {ncall}개 — 전부 원판과 같은 골격의 스트림을 가리킨다")
    nslot = battle.verify_slot_plus3(orig, bytes(rom.buf))
    print(f"  전투 블록 {nslot}개 — 진짜 슬롯의 +3 정규화 값(−최솟값)이 전부 원판과 같다(그림 타일 계산)")
    nsum = battle.verify_summon_letters(orig, bytes(rom.buf))
    print(f"  전투 소환 알파벳 쓰기 {nsum}곳 — 전부 우리 빈 슬롯 이름의 ASCII 알파벳 자리를 가리킨다")
    rom.verify_immutable()
    out_dir = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    # 🔴 지난 실패 표식을 지운다 — `pull-build.sh` 는 `.failed` 가 하나라도 있으면 **그 칸을 통째로**
    # 거부한다(유저 맥에서 실측 2026-09-06: 성공 이미지 옆에 아침의 .failed 가 남아 못 받았다).
    for stale in out_dir.glob("*.failed"):
        stale.unlink()
    out = out_dir / (DEBUG_OUT_NAME if DEBUG_BUILD else "ed1-kr.bin")
    out.write_bytes(bytes(rom.buf))
    # 쓰기 기록 — `check_diff_audit` 가 「원판과 다른 바이트 ⊆ 실제로 쓴 구간」을 본다(11-07). 빌드 칸이 아니라 derived 에 둔다(파일서버 목록에 안 나오게)
    common.OUT_DIR.mkdir(parents=True, exist_ok=True)
    (common.OUT_DIR / ("write_log_debug.json" if DEBUG_BUILD else "write_log.json")).write_text(
        json.dumps([[lb, at, len(d)] for lb, at, d in rom.log]), encoding="utf-8"
    )
    used = cur - SCRIPT_LO if region == "script" else (SCRIPT_HI - SCRIPT_LO) + (cur - TAIL_LO)
    print(
        f"  {out} — 바뀐 블록 {len(new_blocks)} · 아카이브 {used:,}B ({region}) · 쓰기 {len(rom.log)}건"
    )


if __name__ == "__main__":
    try:
        main("--check" in sys.argv)
    except SystemExit as e:
        out_dir = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_")
        p = out_dir / (DEBUG_OUT_NAME if DEBUG_BUILD else "ed1-kr.bin")
        if p.exists():
            p.rename(p.with_suffix(".bin.failed"))
        raise SystemExit(f"❌ 빌드 실패: {e}") from e
