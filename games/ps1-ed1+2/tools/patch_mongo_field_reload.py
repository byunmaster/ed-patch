#!/usr/bin/env python3
"""076 — 몽거 전투가 끝날 때의 딜레이(원판 동작): 필드 타일 재적재 플래그 1→0.

RE 확정(2026-09-24, 정적 전수 + emucap 실측 — 경위는 devlog 「076」):
- 전투가 끝나면 `0x80092130` 이 몬스터 기록(`0x800EE3F8 + i×14`)의 **+0xC 플래그**를
  보고, 1인 게 있으면 필드 그림(`ED2TIM.DAT` 조각 → VRAM (576,0))을 CD 에서 다시 읽는다
  (`0x80032E24`). 몽거만 이 재적재로 약 0.5초(29프레임) 늦다.
- 플래그는 몬스터 종류별 **하드코딩 상수**다(`0x800922A8` 의 122갈래 switch, 1인 건
  다섯뿐). 쓰는 곳도 저 한 곳뿐이다.
- 몬스터 그림은 늘 VRAM x=448(`0x1C0`)에 올라간다(슬롯 0 y=0 · 슬롯 1 y=128). 폭이
  128 을 넘어야 x=576 의 필드 타일을 덮는다. 플래그 1 인 다섯의 실제 TIM 폭:
  **몽거 120**(덮지 않음) · 69번 140 · 68번 240 · 94·117번 256(덮음). 즉 몽거만 원판이
  보수적으로 1을 박아 둔 것이다(프레임 폭 합 360 을 기준으로 잡은 흔적).

⇒ 몽거 갈래의 `addiu a0, zero, 1`(→ `sb a0, 0xC(v1)`) 즉값 한 바이트만 0 으로. 다른
   네 종은 그대로라 동작이 원판과 같다.

실측(패치 이미지): 몽거 전투 종료 키 → 필드 77 → 23프레임. 필드 타일·CLUT·청크0
VRAM 이 원경로와 바이트 동일(몽거가 슬롯 0 일 때·슬롯 1 일 때 둘 다). 연속 전투·패배
후 「전투 직전으로」 멈춤 없음.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import BUILD_DIR, extract, write_user_data

LBA = 1020  # ED2.EXE(LBA 756) 안, 0x80093E30 이 든 섹터
SIG_OFF = 1584  # 섹터 유저데이터 안 — 몽거 갈래(0x80093E30~0x80093E97) 시작
# 몽거 갈래 104B: +0=0x37 · +2=40 · +4=64 · +6=360 · +8=6 · +9=3 · +A/+B=0 · 끝이 flag 즉값 1
SIG = bytes.fromhex(
    "1400c38f37000424000064a01400c38f28000424020064a41400c38f40000424040064a4"
    "1400c38f68010424060064a41400c38f06000424080064a01400c38f03000424090064a0"
    "1400c38f000000000a0060a01400c38f000000000b0060a01400c38f01000424"
)
TARGET_OFF = SIG_OFF + 100  # `addiu a0, zero, 1` 즉값 하위 바이트
OLD, NEW = 0x01, 0x00
IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"


def _count_old_sig(path):
    with open(path, "rb") as f:
        return f.read().count(SIG)


def apply():
    n_old = _count_old_sig(IMG)
    if n_old == 0:
        buf = extract(LBA, 2048, path=IMG)
        assert buf[SIG_OFF:TARGET_OFF] == SIG[:100] and buf[TARGET_OFF] == NEW, (
            "076 서명 없음인데 대상 자리도 적용 상태가 아니다 — 확인 필요"
        )
        print("  076 몽거 필드 재적재 플래그 — 이미 적용됨")
        return 0
    assert n_old == 1, f"076 서명 개수 이상 — {n_old}곳(1곳이어야 함), 멈춘다"

    buf = bytearray(extract(LBA, 2048, path=IMG))
    assert buf[SIG_OFF : SIG_OFF + len(SIG)] == SIG, f"076 서명 불일치 @lba{LBA}+0x{SIG_OFF:X}"
    assert buf[TARGET_OFF] == OLD
    buf[TARGET_OFF] = NEW
    with open(IMG, "r+b") as f:
        write_user_data(f, LBA, bytes(buf), label="076 몽거 필드 재적재 플래그 1→0")

    buf2 = extract(LBA, 2048, path=IMG)
    assert buf2[TARGET_OFF] == NEW and buf2[SIG_OFF:TARGET_OFF] == SIG[:100], "076 되읽기 불일치"
    assert _count_old_sig(IMG) == 0, "076 적용 후에도 옛 서명이 남아 있다"
    print(f"  076 몽거 필드 재적재 플래그 1→0 @lba{LBA}+0x{TARGET_OFF:X} (되읽기 확인)")
    return 1


if __name__ == "__main__":
    sys.exit(0 if apply() >= 0 else 1)
