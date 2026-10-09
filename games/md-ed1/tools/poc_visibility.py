"""가시성·재압축·재배치 PoC — **work/emu 에만 쓴다**(제품 빌드가 아니다, 쓰기 사전조건 없음).

한 롬으로 세 주장을 잰다(2026-09-05, `docs/status.md` 7절):
  1. 글꼴 교체가 화면에 닿는가 — 리소스 0 의 「お」 글리프(두 면)를 Galmuri14 「한」으로 바꾼다.
     첫 대사 인사말의 첫 글자(お) 자리에 한 이 뜨면 통과.
  2. 우리 인코더 출력을 게임이 푸는가 — 블록 104(첫 대사 씬 = 침실. ⚠ 35 가 아니다 — 侍女 는
     여러 블록에 있고, RAM 0xFF6650 을 블록과 맞대 104 로 확정했다)를 재압축한다.
  3. 색인이 임의 오프셋을 받는가 — 재압축 블록을 꼬리 빈 공간(0x1EC35C)에 두고 색인만 돌린다.
  + 헤더 체크섬을 다시 맞춘다(부팅 체크섬 루틴 `$1131E` 가 롬 전체를 읽는다).

    python3 tools/poc_visibility.py   → work/emu/poc1.bin
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import font
import lz
import scene

BDF = common.ROOT / "shared" / "fonts" / "Galmuri14.bdf"
SCENES = (104,)  # 첫 대사(침실) 씬 모듈 — RAM 0xFF6650 실측
LENGTHEN = True  # False 면 1~3 만(재압축·재배치), True 면 4(길이 변경 재조립 + 원본 자리 소거)까지


def bdf_glyph(path: Path, ch: str) -> list[list[int]]:
    """BDF 에서 글자 하나를 14×14 비트 행렬로(폭 14 초과분은 자른다, 세로는 BBX 로 맞춘다)."""
    want = f"ENCODING {ord(ch)}"
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    i = next(i for i, l in enumerate(lines) if l.strip() == want)
    j = i
    while not lines[j].startswith("BBX"):
        j += 1
    bw, bh, _bx, by = map(int, lines[j].split()[1:5])
    k = j
    while lines[k].strip() != "BITMAP":
        k += 1
    rows = []
    for r in lines[k + 1 : k + 1 + bh]:
        v = int(r.strip(), 16)
        nbytes = (len(r.strip()) + 1) // 2
        rows.append([(v >> (nbytes * 8 - 1 - x)) & 1 for x in range(bw)])
    # 14×14 캔버스에 놓는다 — 아래 정렬(베이스라인 아래 by 만큼 내려간 글자는 위로 붙인다)
    grid = [[0] * 14 for _ in range(14)]
    top = max(0, 14 - bh - max(0, 0 - by)) if bh <= 14 else 0
    for y in range(min(bh, 14)):
        for x in range(min(bw, 14)):
            grid[top + y][x] = rows[y][x]
    return grid


def ring(fill: list[list[int]]) -> list[list[int]]:
    """테두리 면 = 8방향 팽창 − 채움 (원본 두 번째 면의 형상과 같은 규칙, PoC 라 근사)."""
    h, w = len(fill), len(fill[0])
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if fill[y][x]:
                continue
            if any(
                0 <= y + dy < h and 0 <= x + dx < w and fill[y + dy][x + dx]
                for dy in (-1, 0, 1)
                for dx in (-1, 0, 1)
            ):
                out[y][x] = 1
    return out


def pack(rows: list[list[int]]) -> bytes:
    return b"".join(struct.pack(">H", sum(v << (15 - x) for x, v in enumerate(r))) for r in rows)


def main() -> None:
    rom = bytearray(common.rom())
    r0 = font.resources(rom)[0]
    codes = font.codes(rom, r0)
    idx = codes.index(int.from_bytes("お".encode("cp932"), "big"))
    fill = bdf_glyph(BDF, "한")
    g = r0["glyphs"] + idx * r0["stride"]
    rom[g : g + 28] = pack(fill)
    rom[g + 28 : g + 56] = pack(ring(fill))
    print(f"글리프 お(#{idx}) @{g:#x} ← 한")
    for row, rr in zip(fill, ring(fill), strict=True):
        print(
            "   "
            + "".join("#" if v else "." if not w else "+" for v, w in zip(row, rr, strict=True))
        )

    base = archives.ARCHIVES["script"][0]
    dst = common.FREE_TAIL[0]
    for n in SCENES:
        s_n, b_n, e_n = archives.blocks(rom, base)[n]
        if LENGTHEN:
            # 4. 길이 변경 — 첫 대사의 호칭 「王子さま」 → 이름을 붙인 꼴(+8B).
            #    스트림을 끝에 다시 쓰고 lea·오프셋을 돌린다(scene.reassemble). 원본 블록 자리는 FF 로
            #    지워 게임이 옛 자리를 읽으면 즉시 드러나게 한다.
            mod = scene.parse_module(b_n)
            st = mod.streams[0x818]
            toks = [scene.Token(t.off, t.raw, t.kind, t.code, t.ref, t.target) for t in st.tokens]
            k = next(i for i, t in enumerate(toks) if t.kind == "text")
            toks[k].raw = toks[k].raw.replace(
                "王子さま".encode("cp932"), "セリオス王子さま".encode("cp932"), 1
            )
            new = scene.reassemble(mod, {0x818: toks})
            scene.verify_reassembly(mod, new, {0x818: toks})
            print(f"블록 {n} 재조립 {len(b_n)} → {len(new)}B (스트림 0x818 +8B)")
            rom[s_n:e_n] = b"\xff" * (e_n - s_n)
            b_n = new
        packed = lz.encode(b_n)
        assert dst + len(packed) < common.FREE_TAIL[1]
        rom[dst : dst + len(packed)] = packed
        rom[base + n * 4 : base + n * 4 + 4] = struct.pack(">I", dst - base)
        out, _ = lz.decode(rom, dst)
        assert out == b_n, "재압축 블록이 넣은 것과 다르다"
        print(
            f"블록 {n} {s_n:#x}({lz.block_span(rom, s_n)}B) → {dst:#x}({len(packed)}B), "
            f"색인[{n}] = {dst - base:#x}"
        )
        dst += len(packed) + (len(packed) & 1)

    cs = common.header_checksum(rom)
    rom[0x18E:0x190] = struct.pack(">H", cs)
    print(f"체크섬 {common.HDR_CHECKSUM:04x} → {cs:04x}")
    common.EMU_DIR.mkdir(parents=True, exist_ok=True)
    p = common.EMU_DIR / ("poc2.bin" if LENGTHEN else "poc1.bin")
    p.write_bytes(rom)
    print(p)


if __name__ == "__main__":
    main()
