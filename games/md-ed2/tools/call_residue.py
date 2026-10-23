"""번역된 스트림이 부르는(call)·잇는(goto) 조각 중 **원문 바이트 그대로 남은 일본어**를 찾는다.

짝 표(`pair_texts.py`)가 번역 대상 행의 한글 칸에 가나·한자를 보이는 두 부류를 가른다 — (1) 스트림 머리의 데이터 바이트를 글자로 잘못 읽은 디코더 경계 (2) **call/goto 로 끌어 쓰는 짧은 조각**(화자 이름 등)이
번역 표에 없어 원문 그대로 남은 것(한글 슬롯 코드로 읽혀 엉뚱한 글자 + 한자가 화면에 뜬다).

    python3 tools/call_residue.py [한글롬]      # 행 = 번호 · 출발 스트림 · 조각 자리 · 원문 · 한글
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle
import common
import pairdump
import scene

JA = re.compile(r"[぀-ヿ一-鿿]")


def _reach(b: bytes, start: int, depth: int = 0, seen: set[int] | None = None):
    """start 스트림이 부르거나 이어 가는 (조각 자리) 들 — call/goto 를 따라 모은다."""
    seen = seen if seen is not None else set()
    try:
        st = scene.parse_stream(b, start)
    except (ValueError, IndexError):
        return
    for t in st.tokens:
        if t.ref in (scene.CALL, scene.GOTO) and t.target is not None and t.target not in seen:
            seen.add(t.target)
            yield t.target
            if depth < 4:
                yield from _reach(b, t.target, depth + 1, seen)


def _frag(ob: bytes, kb: bytes, tgt: int) -> tuple[str, str] | None:
    """조각 tgt 의 원판·한글 글자 — 한글 쪽 바이트가 원판과 같고 원문이 일본어면 (원판, 한글)."""
    try:
        so, sk = scene.parse_stream(ob, tgt), scene.parse_stream(kb, tgt)
    except (ValueError, IndexError):
        return None
    if so.end != sk.end or ob[tgt : so.end] != kb[tgt : sk.end]:
        return None
    txt = "".join(pairdump.decode_text(t.raw, False) for t in so.tokens if t.kind == "text")
    if not JA.search(txt) or not all(0x20 <= ord(c) or c == "　" for c in txt):
        return None
    k = "".join(pairdump.decode_text(t.raw, True) for t in sk.tokens if t.kind == "text")
    return txt, k


def main() -> None:
    import scene_sweep

    kr = Path(sys.argv[1] if len(sys.argv) > 1 else common.BUILD_DIR / "ed2-kr.bin").read_bytes()
    orig = common.rom()
    rows = []
    for n, ((_s, jb, _e), (_s2, bb, _e2)) in enumerate(
        zip(battle.blocks(orig), battle.blocks(kr), strict=True)
    ):
        for tgt in battle.refs(jb):
            for f in _reach(jb, tgt):
                r = _frag(jb, bb, f)
                if r:
                    rows.append((f"전투{n:03d}", f"{tgt:04x}", f"{f:04x}", *r))
    km = {(b, k): m for b, k, m in scene_sweep.built_modules(kr)}
    for blk, k, om in archives.modules(orig):
        nm = km[(blk, k)]
        for x, st in scene.parse_module(om).streams.items():
            if om[x : st.end] == nm[x : st.end]:
                continue  # 안 바뀐 스트림은 번역 대상이 아니다
            for f in _reach(om, x):
                r = _frag(om, nm, f)
                if r:
                    rows.append((f"씬{blk:03d}-{k}", f"{x:04x}", f"{f:04x}", *r))
    seen = set()
    for r in rows:
        if (r[0], r[2]) in seen:
            continue
        seen.add((r[0], r[2]))
        print("\t".join(r))
    print(f"조각 {len(seen)}곳", file=sys.stderr)


if __name__ == "__main__":
    main()
