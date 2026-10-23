"""이어 붙는 조각의 줄 폭 게이트(10-23) — 구운 롬을 흐름대로(call 은 끼우고 goto 는 따라가며) 걸어 **한 줄에 이어 쓰이는 조각**의 글자 폭이
17.5칸(`build.WIDTH`)을 넘는 줄을 센다. 조판기가 앞 조각이 쓴 폭을 모르던 결함(호출 조각·`<03>`·goto 꼬리)의 재발을 막는다.

    python3 tools/check_join_width.py <롬.bin>             # 기준선보다 늘면 실패 · 분모 0 이면 실패
    python3 tools/check_join_width.py <롬.bin> --freeze    # 줄었을 때 기준선을 내린다(래칫)

세는 것 — 한글이 6할 이상이고 raw 태그가 없는 줄(코드 바이트가 글로 읽힌 가짜를 뺀다), 글 기준 **유일한 줄**. 화자 이름 칸(`1E…04`)과
`07` 로 끝나는 이름 호출은 줄이 아니다. 변수(`02·09·0B·0E·15·EB·EC`)는 폭 0.
기준선 = 끊을 자리 없이 앞 글과 붙은 어절(`프래드`+`였지.`) 등 정적으로 못 가르는 것들 — 어절 줄넘김 훅이 런타임에 받는다(devlog 10-23).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import pairdump
import scene
import scene_sweep
from text import krwrap

WIDTH = 17.5
BASELINE = Path(__file__).resolve().parents[1] / "textmap" / "join_width_baseline.json"
VARS = (0x02, 0x09, 0x0B, 0x0E, 0x15, 0xEB, 0xEC)


def walk(b: bytes, start: int, cur: list, depth: int = 0) -> list[tuple[float, str]]:
    """cur = [폭, 글, 이름칸 여부]. 끝난 줄 (폭, 글) 목록."""
    lines: list[tuple[float, str]] = []
    pos, seen, hops = start, set(), 0
    while hops < 60 and pos not in seen and 0 <= pos < len(b):
        hops += 1
        seen.add(pos)
        try:
            st = scene.parse_stream(b, pos)
        except Exception:
            break
        jump, ended, pc = None, False, False
        for t in st.tokens:
            if t.kind == "text":
                if not cur[2]:
                    s = pairdump.decode_text(t.raw, True)
                    cur[0] += krwrap.text_width(s)
                    cur[1] += s
            elif t.kind == "end":
                ended = True
                if t.code == 7:
                    lines.append((cur[0], cur[1]))
                    cur[:] = [0.0, "", False]
            elif t.kind == "ctl":
                c = t.code
                if c == 0x1E:
                    cur[2] = True
                elif c == 0x04:
                    cur[2] = False
                elif c in (1, 5):
                    lines.append((cur[0], cur[1]))
                    cur[:] = [0.0, "", False]
                elif c in VARS:
                    pass
                elif c in pairdump.COND:
                    pc = True
                    continue
                elif t.ref == scene.GOTO and t.target is not None:
                    if not pc:
                        jump = t.target
                elif t.ref == scene.CALL and t.target is not None and depth < 3:
                    lines += walk(b, t.target, cur, depth + 1)
            pc = pc and t.kind == "ctl" and t.code in pairdump.COND
        if ended or jump is None:
            break
        pos = jump
    if depth == 0:
        lines.append((cur[0], cur[1]))
    return lines


def scan(rom: bytes) -> tuple[int, int, dict[str, float]]:
    """(스트림 수, 잰 줄 수, {넘친 줄 글: 폭})"""
    n_streams = n_lines = 0
    over: dict[str, float] = {}
    for _blk, _k, b in scene_sweep.built_modules(rom):
        mod = scene.parse_module(b)
        for off in sorted(mod.streams):
            n_streams += 1
            for w, tx in walk(b, off, [0.0, "", False]):
                if not tx.strip():
                    continue
                n_lines += 1
                if w > WIDTH and "<" not in tx and sum("가" <= c <= "힣" for c in tx) >= len(tx) * 0.6:
                    over[tx] = w
    return n_streams, n_lines, over


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("사용: check_join_width.py <롬.bin> [--freeze]")
        return 2
    n_streams, n_lines, over = scan(Path(args[0]).read_bytes())
    if n_lines == 0:
        print("❌ 이어 붙는 조각 폭 검사 — 잰 줄이 0(분모 0 — 걷기가 아무것도 못 읽었다)")
        return 1
    base = json.loads(BASELINE.read_text(encoding="utf-8"))["over"] if BASELINE.exists() else None
    print(
        f"  이어 붙는 조각 폭 검사 — 스트림 {n_streams} · 잰 줄 {n_lines} · {WIDTH}칸 넘는 한글 줄 {len(over)} (기준선 {base})"
    )
    if "--freeze" in sys.argv:
        if base is not None and len(over) > base:
            print(f"❌ 기준선보다 늘었다({len(over)} > {base}) — 올려 얼리지 않는다")
            return 1
        BASELINE.write_text(json.dumps({"over": len(over)}, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  기준선 {len(over)} 로 얼렸다")
        return 0
    if base is None:
        print("❌ 기준선이 없다 — --freeze 로 만든다")
        return 1
    if len(over) > base:
        print(f"❌ 넘치는 줄이 기준선보다 늘었다({len(over)} > {base}):")
        for tx, w in sorted(over.items()):
            print(f"    {w:5.1f}칸  {tx}")
        return 1
    if len(over) < base:
        print(f"  ✂ 기준선보다 줄었다({len(over)} < {base}) — `--freeze` 로 내린다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
