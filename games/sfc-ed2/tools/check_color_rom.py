"""구운 롬 색 제어 코드 전수 대조 — 원판·한글 롬을 같은 걷기(`romdump.Dec`)로 읽어 메시지마다 `$04`·`$18~$1F` 열(종류·개수·순서)이 같은지 본다.
`check_color.py`(문안 지도·구간 안)가 못 보는 구멍을 메운다: 색 열기 없이 닫기만 든 구간 · 구간 밖(머리 틈·이름 변수 뒤)의 코드 · 트램펄린 뒤 실제 바이트.
앞 메시지의 색이 다음 대사까지 번지는 결함(pce-ed1 19건)은 코드가 빠지거나 더해질 때만 생기므로, 열이 원판과 같으면 번질 일도 같다.
번역이 의도로 붙인 화자 머리(`$C5521A`)만 예외다.

    python3 games/sfc-ed2/tools/check_color_rom.py [롬]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import romdump
import script
import segs



def seq(t: str) -> list[str]:
    return [t[i + 1 : i + 3] for i, c in enumerate(t) if c == "\x01"]


def collect(jp: bytes, kb: bytes) -> tuple[int, list[str]]:
    dj, dk = romdump.Dec(jp, False), romdump.Dec(kb, True, romdump.kr_glyph_map(kb))
    dj.colors = dk.colors = True
    starts = set()
    for s, _e in script.all_units(jp):
        starts.add(s + 4 if jp[s : s + 4] == b"\x5c\x0b\x8f\xc1" else s)
    starts |= {s for s, _e in segs.segments(jp)}
    n, bad = 0, []
    for o in sorted(starts):
        if segs.excluded(o):  # 몬스터 이름 풀·저장 안내 등 — 다른 종류(spans·records)가 번역하고 옮긴 자리라 제자리 읽기가 안 맞는다
            continue
        a = common.off2snes(o)
        try:
            tj, tk = dj.walk(o), dk.walk(romdump.kr_start(jp, kb, o))
        except Exception:
            continue
        sj, sk = seq(tj), seq(tk)
        if not sj and not sk:
            continue
        n += 1
        if sj != sk and (a & 0xFFFFFF) not in {0xC5521A}:
            bad.append(f"${a:06X} 원판 {' '.join(sj)} ≠ 한글 {' '.join(sk)}")
    return n, bad


def main() -> None:
    kp = Path(sys.argv[1]) if len(sys.argv) > 1 else common.BUILD_DIR / "sfc-ed2" / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
    n, bad = collect(common.rom_bytes(), kp.read_bytes())
    for b in bad[:30]:
        print("  " + b)
    print(f"롬 색 코드 대조 — 색이 든 메시지 {n} · 위반 {len(bad)}")
    if bad or n < 1000:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
