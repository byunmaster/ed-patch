"""battle_ctx — 행동 루틴 흐름 추적과 길 위 분기 고정."""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import battle_ctx as X

# 0: move.b 0(a2),d7 · 4: cmpi.b #6,d7 · 8: bne.w $12 · c: lea x(pc),a1 · 10: rts · 12: rts
CODE = bytes.fromhex("1e2a00000c0700066600000843fa00104e754e75")


def _have_capstone() -> bool:
    try:
        import capstone  # noqa: F401
    except ImportError:
        return False
    return True


def test_path_and_guard_patches():
    if not _have_capstone():
        return
    g = X.graph(CODE, [0])
    fall = X.path(g, 0, 0x0C)  # lea 로 가는 길 = bne 를 안 타는 쪽
    assert fall is not None and (8, "fall") in fall
    assert X.guard_patches(CODE, g, fall) == [(8, b"\x4e\x71\x4e\x71")]  # 4바이트 bne → nop 둘
    taken = X.path(g, 0, 0x12)
    assert X.guard_patches(CODE, g, taken) == [
        (8, b"\x60\x00")
    ]  # 워드 꼴 bne → bra(변위 워드는 그대로)


def test_service_branch_left_alone():
    if not _have_capstone():
        return
    # 상태 전략: jsr 뒤의 분기는 서비스 결과를 보므로 고정하지 않는다: 0: move.b 0(a2),d7 · 4: jsr (a6) · 6: bne.w $e · a: rts · c: nop · e: rts
    code = bytes.fromhex("1e2a00004e96660000064e754e714e75")
    g = X.graph(code, [0])
    st = X.path(g, 0, 0x0A)
    assert st is not None
    assert (
        X.guard_patches(code, g, st, state_only=True) == []
    )  # 「상태」 전략은 서비스 뒤 분기를 건드리지 않는다
    assert X.guard_patches(code, g, st) != []  # 「전부」 전략은 고정한다


def test_table_start_uses_original_header():
    # 한글 블록의 다섯째 워드는 새 길이로 덮여 있다 — 원판 t[4] + 레코드 구역이 자란 만큼
    orig = struct.pack(">6H", 12, 266, 296, 328, 368, 1248) + bytes(1248 - 12)
    built = struct.pack(">6H", 12, 320, 350, 382, 1302, 1248) + bytes(1302 - 12)
    assert X.table_start(built, orig) == 368 + 54
