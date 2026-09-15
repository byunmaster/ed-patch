#!/usr/bin/env python3
"""038 — 세레 저택 NPC 슬롯 설치 인자 한 바이트(원판 결함, 우리가 만든 게 아니다).

RE 확정(2026-09-15): `jal 0x8002E610`(NPC 슬롯 설치) 호출을 ED2SCN4 안에서 전수로
뜨니 **같은 명단이 다섯 벌**(lba 1958·1959·1961·1964·1965) 있었다. 슬롯 9(다섯 벌
공통 `a3=0x0e`)만 `a2`(조형 id) 값이 갈린다 — lba1958 하나만 `4`, 나머지 넷은 `6`.
같은 자리·같은 다른 인자인데 조형 id 하나만 다른 건 **설계가 아니라 오타의 모양**
이다. 원본 디스크도 `0x04`라 우리 파이프라인이 만든 결함이 아니다.

⚠ **"id 6 이 제니다"는 아직 확정이 아니다** — 잰 것은 "같은 자리의 다른 네 벌이
6이다"까지. 화면 확인(RE → 마스터)이 남아 있다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import BUILD_DIR, extract, write_user_data

LBA = 1958  # ED2SCN4 안, 서명이 유일하게 걸리는 섹터
SIG_OFF = 120  # 섹터 유저데이터 안 오프셋(inner) — 서명 시작
SIG = bytes.fromhex("0900042480000524040006240e000724")  # addiu a0,9 / a1,128 / a2,4 / a3,14
TARGET_OFF = SIG_OFF + 8  # a2 즉값의 하위 바이트(리틀엔디안 워드의 첫 바이트)
OLD, NEW = 0x04, 0x06
IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"


def _count_old_sig(path):
    """빌드 전체에서 **결함 있는(a2=4)** 서명이 몇 번 나오는지 — raw 파일 스캔.

    ⚠ **새 서명(a2=6)은 세지 않는다** — 다섯 벌 중 넷은 원래부터 6이라 항상
    여러 곳에서 걸린다. 모호함을 없애야 하는 건 "고쳐야 할 그 한 자리"뿐이다.
    """
    with open(path, "rb") as f:
        data = f.read()
    return data.count(SIG)


def apply():
    n_old = _count_old_sig(IMG)
    if n_old == 0:
        buf = extract(LBA, 2048, path=IMG)
        assert buf[TARGET_OFF] == NEW, "038 서명 없음인데 대상 자리도 6이 아니다 — 확인 필요"
        print("  038 제니 슬롯 — 이미 적용됨")
        return 0
    assert n_old == 1, f"038 서명 개수 이상 — {n_old}곳(1곳이어야 함), 멈춘다"

    buf = bytearray(extract(LBA, 2048, path=IMG))
    assert buf[SIG_OFF : SIG_OFF + len(SIG)] == SIG, (
        f"038 서명 불일치 @lba{LBA}+0x{SIG_OFF:X}: {bytes(buf[SIG_OFF : SIG_OFF + len(SIG)]).hex()}"
    )
    assert buf[TARGET_OFF] == OLD, f"038 대상 바이트 불일치: {buf[TARGET_OFF]:#x} != {OLD:#x}"
    before = bytes(buf[SIG_OFF : SIG_OFF + len(SIG)])
    buf[TARGET_OFF] = NEW
    after = bytes(buf[SIG_OFF : SIG_OFF + len(SIG)])
    # 나머지 15바이트(서명 16B 중 대상 1B 제외)는 그대로여야 한다.
    assert before[:8] == after[:8] and before[9:] == after[9:], "038 서명 주변 바이트가 흔들렸다"

    with open(IMG, "r+b") as f:
        write_user_data(f, LBA, bytes(buf), label="038 NPC 슬롯 조형 id 4→6")

    buf2 = extract(LBA, 2048, path=IMG)
    assert buf2[TARGET_OFF] == NEW, "038 되읽기 불일치"
    n_old2 = _count_old_sig(IMG)
    assert n_old2 == 0, f"038 적용 후에도 결함 서명이 남아 있다 — {n_old2}곳"
    print(f"  038 NPC 슬롯 조형 id 4→6 @lba{LBA}+0x{TARGET_OFF:X} (결함 서명 0곳, 되읽기 확인)")
    return 1


if __name__ == "__main__":
    sys.exit(0 if apply() >= 0 else 1)
