"""디버그 맵 이동(RAM 만, 롬 무변경) — 문을 통과한 것처럼 엔진이 맵을 **새로** 푼다(객체 풀·맵 자료 포함).

    import gpgx_mapmove
    gpgx_mapmove.go(g, rom_bytes, scene, x=None, y=None)   # → 그 씬으로 들어갔나
    gpgx_mapmove.pool(g)                                    # 객체 (x, y, 레코드 hex)

원리: 문 이벤트가 부르는 서비스 `$036F`(`$2D50`)는 문 서술자 34바이트를 `$FF208C` 에 복사하고 `$FF1852` 의 비트 2 를 켠다 —
메인 루프가 그걸 보고 목적지 맵을 로드한다. 서술자는 `[+0]=? [+1]=도착 x [+2]=도착 y … [+0xC..D]=맵 id(워드)` 꼴이고, 맵 id → 씬은 표
`0x134DDC`(225칸, 중복 없음)다. 씬 156 의 문 서술자를 틀로 쓴다(`work/derived/text/script/156.bin` @0xEA).
🔴 `gpgx_battle.warp`(메뉴 LOAD)는 **모듈과 맵 id 만** 바꾸고 객체 풀은 저장본 그대로다 — NPC·객체 스크립트가 걸린 블록은 워프로는 못 닿는다.
순간이동(같은 맵 안): 플레이어 좌표의 원본은 `$FF34BA/BB`(타일×2 — `$FF1CBC` 레코드는 매 프레임 이 표에서 복사된다). 이벤트 플래그는 `$FF1B5C` 비트 배열.
"""

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE = None


def _template() -> bytes:
    global _TEMPLATE
    if _TEMPLATE is None:
        _TEMPLATE = (ROOT / "work/derived/text/script/156.bin").read_bytes()[0xEA : 0xEA + 34]
    return _TEMPLATE


def map_ids(rom: bytes) -> tuple[int, ...]:
    return struct.unpack(">225H", rom[0x134DDC : 0x134DDC + 450])


def go(
    g, rom: bytes, scene: int, x: int | None = None, y: int | None = None, frames: int = 240
) -> bool:
    d = bytearray(_template())
    d[0xC:0xE] = struct.pack(">H", map_ids(rom)[scene])
    if x is not None:
        d[1] = x
    if y is not None:
        d[2] = y
    g.poke(0x208C, bytes(d))
    w = g.ram(0x1852, 2)
    g.poke(0x1852, bytes([w[0], w[1] | 4]))
    g.run(frames)
    return int.from_bytes(g.ram(0x343C, 2), "big") == scene


def pool(g) -> list[tuple[int, int, str]]:
    n = g.ram(0x1ACD, 1)[0]
    return [
        (
            g.ram(0x1CBC + 8 * i + 2, 1)[0],
            g.ram(0x1CBC + 8 * i + 3, 1)[0],
            g.ram(0x1CBC + 8 * i, 8).hex(),
        )
        for i in range(1, max(1, n - 1))
    ]


def teleport(g, x: int, y: int) -> None:
    """같은 맵 안 순간이동 — 원본 `$FF34BA/BB`(타일×2, y 는 홀수)."""
    g.poke(0x34BA, bytes([2 * x, 2 * y + 1]))
    g.run(6)


def set_flags(g, fill: int = 0xFF, n: int = 0x100) -> None:
    g.poke(0x1B5C, bytes([fill]) * n)
