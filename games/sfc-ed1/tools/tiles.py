"""sfc-ed1 타일·코드 예산 — 「어느 글자 코드의 타일을 덮어써도 되나」의 정본.

글꼴은 부팅 때 시트($18:E02C, 1bpp 8B/타일)의 타일 $000~$17F 384장이 VRAM 워드 $1000 에
올라간다($00:9177~$00:9198 이 $200B 씩 여섯 번 — 평면1 은 $FF 로 미리 채워 2bpp 로 편다).
글자 한 자 = 타일 **t(위) + t+$10(아래)** 이고 코드→t 는 표 `$03:F3EC`(2B×$D0)가 정한다.

⇒ 자리는 셋으로 갈린다. **셋이 같은 웅덩이를 나눠 쓰므로 한 곳에서 정한다**:
  · **지키는 코드** — 우리가 렌더에 쓰는 반각(숫자·부호·영문, `encode.KR_TABLE`)
  · **상주 글리프** — 메뉴 라벨처럼 **정적 타일맵**이 타일 번호로 직접 가리키는 자리(창이 열려 있는 내내 VRAM 에 있어야 한다)
  · **동적 슬롯** — 대사 렌더러 훅이 글자마다 빌려 쓰는 자리(글리프를 VRAM 에 갈아 끼운다)

🔴 슬롯·상주는 **원본 가나의 타일을 빼앗는다** — 안 옮긴 일본어는 그 자리에서 깨진 한글로 보인다
(status 13.7). 그래서 「배치 표가 아직 쓰는 타일」은 빼고 고른다. 라벨을 한글로 다시 구우면
그 타일이 풀리므로, **슬롯은 반드시 「구운 뒤의 롬」으로 다시 재야 한다**(`layout_tiles(out)`).
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001
import common
import menus

UPLOADED = 0x180  # VRAM 에 올라가는 시트 타일 수(6청크 × 64)
CHAR_CODES = 0xCF  # $CF = 개행 — 글자 코드는 그 아래


def code_tile(buf: bytes) -> dict[int, int]:
    """글자 코드 → 위 타일 번호(아래는 +$10)."""
    t = common.snes2off(text.TILE_TABLE)
    return {c: buf[t + 2 * c] | ((buf[t + 2 * c + 1] & 3) << 8) for c in range(0xD0)}


def layout_tiles(buf: bytes) -> set[int]:
    """창 배치 표 셋이 **지금** 쓰는 타일 번호 전부(정적 타일맵이라 상주해야 한다)."""
    out: set[int] = set()
    for addr in menus.LAYOUT_TABLES.values():
        base = common.snes2off(addr)
        for wid in range(menus.LAYOUT_COUNT):
            p = (
                buf[base + 3 * wid]
                | (buf[base + 3 * wid + 1] << 8)
                | (buf[base + 3 * wid + 2] << 16)
            )
            try:
                o = common.snes2off(p)
            except ValueError:
                continue
            w, h = buf[o + 2], buf[o + 3]
            if w * h > 4000:  # 표 자신을 가리키는 더미 항목
                continue
            for i in range(w * h):
                out.add((buf[o + 4 + 2 * i] | (buf[o + 5 + 2 * i] << 8)) & 0x3FF)
    return out


def overwritable(rom: bytes, lay: set[int], keep_codes: set[int]) -> list[int]:
    """타일을 덮어써도 되는 글자 코드(오름차순 — 배정은 결정적이어야 한다).

    조건 넷: ① 우리가 쓰는 코드가 아니다 ② 위·아래 타일이 둘 다 업로드 범위 안이다
    ③ 그 타일을 **다른 코드가 같이 쓰지 않는다**(하나만 깨진다) ④ 배치 표가 안 쓴다."""
    tile = code_tile(rom)
    dup = Counter(tile.values())
    out = []
    for c in range(CHAR_CODES):
        if c in keep_codes:
            continue
        t = tile[c]
        if t + 0x10 >= UPLOADED:
            continue
        if dup[t] != 1:
            continue
        if t in lay or t + 0x10 in lay:
            continue
        out.append(c)
    return out


def vram_word(tile_no: int) -> int:
    """타일 번호 → VRAM 워드 주소($00:91F5 실측: 워드 $1000 + 8×타일)."""
    return 0x1000 + 8 * tile_no


def report(rom: bytes) -> dict:
    import encode

    keep = set(encode.KR_TABLE.values()) | set(encode.LEADS)
    lay = layout_tiles(rom)
    pool = overwritable(rom, lay, keep)
    return {"layout_tiles": len(lay), "pool": len(pool), "pool_codes": pool}


if __name__ == "__main__":
    r = report(common.rom_bytes())
    print(f"배치 표가 쓰는 타일 {r['layout_tiles']} · 덮어써도 되는 코드 {r['pool']}")
    print(" ".join(f"{c:02X}" for c in r["pool_codes"]))
