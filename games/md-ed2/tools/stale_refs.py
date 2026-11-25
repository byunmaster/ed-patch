"""옮긴 문안의 옛 칸을 아직 겨냥하는 `lea d(pc)` 검사 — 쓰기·읽기 짝이 한쪽만 옮겨진 결함(PCE II 퀵메뉴와 같은 부류, 11-07).

    python3 tools/stale_refs.py [롬.bin]     # 빌드 게이트(check.sh 5e5) — 있으면 실패

번역이 문안을 옮기면(`relocations.tsv` 「옮김」) 옛 칸은 0 으로 지워진다. 그 옛 칸을 PC 상대 `lea` 가 아직 가리키면 코드는 지운 자리를 읽고 쓴다.
실측: 049-2(맵 7030) 도구점 「팔기 분기」 구매 경로가 `lea $b20(pc),a3`(상점 표 O)·`lea $b26(pc),a6`(머리 워드 I)를 그대로 두어, 「삽니다」 뒤 목록 창이 비고
머리 워드는 쓰레기통에 써졌다(같은 모양 15모듈 30곳). 파서가 그 코드 구간을 글 스트림으로 덮어 뿌리 `lea` 로 안 잡혔기 때문이다(`build._repoint_code_leas` 가 고친다).
"""

import csv
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import scene
import scene_sweep


def stale_in(new: bytes, spans: list[tuple[int, int]]) -> list[tuple[int, int, int]]:
    """새 모듈 `new` 의 `lea d(pc),aN` 중 목표가 지워진 옛 칸(`spans` = [(시작, 끝)], 앞 4B 가 0)에 드는 것 → [(명령 자리, 목표, 칸 시작)]."""
    out = []
    for p in range(0, len(new) - 3, 2):
        w = (new[p] << 8) | new[p + 1]
        if (w & 0xF1FF) != 0x41FA:
            continue
        t = p + 2 + struct.unpack(">h", new[p + 2 : p + 4])[0]
        for a, e in spans:
            if a <= t < e and new[a : a + 4] == b"\0\0\0\0":
                out.append((p, t, a))
    return out


def selftest() -> bool:
    mod = bytearray(0x40)
    mod[0:2] = bytes.fromhex("41fa")  # lea $20(pc),a0 → 0x22
    mod[2:4] = struct.pack(">h", 0x22 - 2)
    mod[0x20:0x28] = b"\0" * 8
    ok1 = [x[1] for x in stale_in(bytes(mod), [(0x20, 0x28)])] == [0x22]
    mod[0x20:0x24] = b"\x4e\x71\x82\xa8"  # 옛 칸이 안 지워졌으면(제자리 번역) 잡지 않는다
    ok2 = stale_in(bytes(mod), [(0x20, 0x28)]) == []
    return ok1 and ok2


def run(kr: bytes) -> list[tuple[str, int, int, int]]:
    orig = common.rom()
    km = {(b, k): m for b, k, m in scene_sweep.built_modules(kr)}
    moved: dict[str, list[int]] = {}
    for r in csv.reader(
        (common.GAME_DIR / "relocations.tsv").read_text(encoding="utf-8").splitlines(),
        delimiter="\t",
    ):
        if len(r) > 3 and r[1] == "옮김" and r[3]:
            moved.setdefault(r[0], []).append(int(r[2], 16))
    bad = []
    for b, k, om in archives.modules(orig):
        key = f"{b:03d}-{k}"
        if key not in moved:
            continue
        po = scene.parse_module(om)
        spans = [(o, po.streams[o].end) for o in moved[key] if o in po.streams]
        for p, t, a in stale_in(km[(b, k)], spans):
            bad.append((key, p, t, a))
    return bad


def main() -> int:
    if not selftest():
        print("❌ 옛 칸 참조 검사 자체 시험 실패")
        return 1
    path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin"
    )
    bad = run(path.read_bytes())
    print(f"옛 칸 참조 검사 [md-ed2] — 지운 옛 칸을 겨냥하는 lea {len(bad)} · 자체 시험 통과")
    for key, p, t, a in bad[:20]:
        print(f"  ✗ {key} lea@{p:#x} → {t:#x} (옛 칸 {a:#x})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
