"""md-ed1 아카이브 — 색인(BE32 오프셋 × n, 첫 값 = 4n) + LZ 블록들. 정본 좌표는 여기.

    python3 tools/archives.py --check   # 아카이브 전부 스캔 · 대본/전투 아카이브의 분모 확인
    python3 tools/archives.py --dump    # work/derived/text/ 에 블록(.bin)과 대본 덤프(.txt)

블록은 `lz.block_span` 으로 이어지므로 색인 없이도 체인을 찾을 수 있다 — `scan_chains` 가
롬 전체를 훑어 **색인이 있는 것과 없는 것**을 다 보여 준다(그래픽·맵도 같은 코덱이다).

⚠ 대본 블록은 **씬 모듈**이다 — 헤더 + 68000 코드(pc 상대 참조) + 이벤트 자료 + SJIS 문안.
문안을 늘리면 코드가 문안을 가리키는 pc 상대 변위가 어긋난다(`docs/status.md` 3절).
"""

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import lz

# 이름 → (색인 주소, 기대 블록 수, 기대 총 출력 바이트). 실측 2026-09-05.
ARCHIVES = {
    "script": (0x134FA0, 225, 663_896),  # 씬 모듈 — 대본 본진 (0x135324~0x1918D2)
    "battle": (0x0CA94C, 110, 103_680),  # 전투 모듈 — 몬스터 이름·「～が現れた」
    "gfx_a": (0x085E16, 15, 307_200),
    "gfx_b": (0x0D8690, 97, 535_040),
    "sys": (0x196EAE, 6, 18_048),  # 게임 시작 로드 목록(0x11C7C)이 쓰는 스테이징 블록
    "gfx_c": (0x1BED0E, 23, 218_304),
    "gfx_d": (0x1D3DBA, 13, 206_336),
}

SJIS_RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){4,}")
SPEAKER = re.compile(rb"\x1e((?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){1,8})\x04")


def table(d: bytes, base: int) -> list[int]:
    """색인 → 블록 시작 주소 목록. 첫 값이 4n 이 아니면 색인이 아니다."""
    first = struct.unpack(">I", d[base : base + 4])[0]
    if first < 4 or first % 4 or first > 4 * 4096:
        raise ValueError(f"{base:#x}: 색인이 아니다 (첫 값 {first:#x})")
    n = first // 4
    offs = struct.unpack(f">{n}I", d[base : base + 4 * n])
    return [base + o for o in offs]


def blocks(d: bytes, base: int) -> list[tuple[int, bytes, int]]:
    """(시작, 출력, 끝) — 끝은 헤더 길이로 잰 다음 블록 자리. 디코더가 헤더와 어긋나면 죽는다."""
    out = []
    for s in table(d, base):
        data, end = lz.decode(d, s)
        span = lz.block_span(d, s)
        if end not in (s + span, s + span - 1):
            raise SystemExit(f"{s:#x}: 디코더 끝({end:#x}) ≠ 헤더 길이({s + span:#x})")
        out.append((s, data, s + span))
    return out


def scan_chains(d: bytes, lo: int, hi: int) -> list[list[tuple[int, int, int]]]:
    """색인 없이 블록 체인을 찾는다 — (시작, 끝, 출력길이) 의 연속 묶음."""
    found = []
    x = lo
    while x < hi:
        hdr = struct.unpack("<H", d[x : x + 2])[0]
        span = hdr + 1 + ((hdr + 1) & 1)
        if 8 <= hdr <= 0x8000 and x + span <= hi:
            try:
                data, end = lz.decode(d, x)
            except (ValueError, IndexError):
                end = -1
            if end in (x + span, x + span - 1):
                found.append((x, x + span, len(data)))
                x += span
                continue
        x += 1
    chains: list[list[tuple[int, int, int]]] = []
    for b in found:
        if chains and chains[-1][-1][1] == b[0]:
            chains[-1].append(b)
        else:
            chains.append([b])
    return chains


def render(b: bytes) -> str:
    """SJIS + 제어코드를 사람이 읽게 편다(코드 영역도 그대로 찍힌다 — 문안 경계는 아직 안 갈랐다)."""
    out = []
    i = 0
    while i < len(b):
        c = b[i]
        if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEA) and i + 1 < len(b):
            out.append(b[i : i + 2].decode("cp932", "replace"))
            i += 2
        elif 0x20 <= c < 0x7F:
            out.append(chr(c))
            i += 1
        else:
            out.append(
                {0x00: "<00>\n", 0x01: "<01>\n", 0x05: "<05>\n", 0x1E: "\n<1E>"}.get(
                    c, f"<{c:02x}>"
                )
            )
            i += 1
    return "".join(out)


def check(d: bytes) -> None:
    for name, (base, n_exp, tot_exp) in ARCHIVES.items():
        bl = blocks(d, base)
        tot = sum(len(b) for _, b, _ in bl)
        chars = sum(len(m.group()) // 2 for _, b, _ in bl for m in SJIS_RUN.finditer(b))
        spk = sum(len(SPEAKER.findall(b)) for _, b, _ in bl)
        print(
            f"  {name:7s} {base:#08x}: 블록 {len(bl):3d} · {bl[0][0]:#x}~{bl[-1][2]:#x} · "
            f"출력 {tot:,}B · SJIS 런 {chars:,}자 · 화자 {spk}"
        )
        if len(bl) != n_exp or (tot_exp is not None and tot != tot_exp):
            raise SystemExit(f"{name}: 분모가 갈렸다 (기대 {n_exp}블록 {tot_exp}B)")
    # 인코더 회귀 — 실물 블록을 다시 눌러 풀면 같아야 한다(합성 테스트만으론 실물 분포를 못 본다)
    s0, b0, _ = blocks(d, ARCHIVES["script"][0])[35]
    packed = lz.encode(b0)
    if lz.decode(packed, 0)[0] != b0:
        raise SystemExit("인코더 왕복 실패 (script 35)")
    print(f"  인코더 왕복 OK — script 35: 원본 {lz.block_span(d, s0):,}B ↔ 재압축 {len(packed):,}B")


def dump(d: bytes) -> None:
    """script 는 스트림 단위(scene.py — 번역 정본의 단위), battle 은 아직 통째 렌더."""
    import scene

    root = common.OUT_DIR / "text"
    for name in ("script", "battle"):
        base = ARCHIVES[name][0]
        dst = root / name
        dst.mkdir(parents=True, exist_ok=True)
        for i, (s, b, _) in enumerate(blocks(d, base)):
            (dst / f"{i:03d}.bin").write_bytes(b)
            if name == "script":
                mod = scene.parse_module(b)
                lines = [f"# {name} {i} @{s:#x} {len(b)}B · 스트림 {len(mod.streams)}"]
                for off in sorted(mod.streams):
                    lines.append(f"\n## {i:03d}:{off:04x}\n{mod.streams[off].text()}")
                (dst / f"{i:03d}.txt").write_text("\n".join(lines), encoding="utf-8")
            else:
                (dst / f"{i:03d}.txt").write_text(
                    f"# {name} {i} @{s:#x} {len(b)}B\n" + render(b), encoding="utf-8"
                )
        print(f"  {name}: {dst}")


if __name__ == "__main__":
    d = common.rom()
    if "--dump" in sys.argv:
        dump(d)
    elif "--scan" in sys.argv:
        for c in scan_chains(d, 0x080000, common.FREE_TAIL[0]):
            if len(c) >= 2:
                print(
                    f"  chain {c[0][0]:06x}-{c[-1][1]:06x} n={len(c)} out={sum(b[2] for b in c):,}"
                )
    else:
        check(d)
