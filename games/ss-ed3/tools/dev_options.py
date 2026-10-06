"""개발용 빌드 옵션 — **환경변수로 켤 때만** 동작한다(기본 꺼짐, 배포·게이트 빌드엔 영향 없음).

    ED_DEV_ISABEL_HP=1 ED_BUILD_TAG=ss-ed3-dev python3 games/ss-ed3/tools/build.py

엔딩·크레딧 확인을 하려면 `before_isabel` 세이브에서 최종전을 거쳐야 하는데 전투가 길다(마스터 10-02). 이 옵션은 이자벨의
HP 를 낮춰 **한 대에 끝나게** 한다. ⚠ **꼭 `ED_BUILD_TAG` 를 따로 준다** — 안 주면 정상 이미지 칸을 덮어쓴다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import param as P

ENV_ISABEL_HP = "ED_DEV_ISABEL_HP"
ENEMY_NAME = "イザベル"
HP_OFF = 22 + 12  # 적 레코드 안 HP(u16 big-endian) — 이름 22B 뒤 12B


def isabel_hp():
    """켜져 있으면 정수, 아니면 `None`."""
    v = os.environ.get(ENV_ISABEL_HP)
    if not v:
        return None
    n = int(v)
    if not 1 <= n <= 0xFFFF:
        raise SystemExit(f"{ENV_ISABEL_HP}: 1~65535 (받은 값 {v})")
    return n


def patch_param(b):
    """`PARAM.BIN` bytes → 이자벨 HP 를 바꾼 bytes(옵션이 꺼져 있으면 그대로). 같은 길이."""
    hp = isabel_hp()
    if hp is None:
        return b
    base, st, n = P.ENEMY
    out = bytearray(b)
    hit = 0
    for k in range(n):
        rec = base + k * st
        z = b.find(b"\x00", rec, rec + st)
        if z <= rec:
            continue
        try:
            nm = b[rec:z].decode("shift_jis")
        except UnicodeDecodeError:
            continue
        if nm == ENEMY_NAME:
            out[rec + HP_OFF : rec + HP_OFF + 2] = struct.pack(">H", hp)
            hit += 1
    assert hit == 1, f"{ENEMY_NAME} 레코드가 하나여야 한다({hit})"
    return bytes(out)
