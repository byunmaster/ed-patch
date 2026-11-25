"""글자색 제어 코드 대조 — 굽는 씬 스트림의 색 켜기·되돌리기가 원판과 같은 순서·같은 수인가, 켠 색이 스트림 안에서 닫히는가(마스터 11-11).

엔진(`$9FA0` 표): 0x18~0x1F = 색 쌍을 켠다(`$A4A2` — 이전 색을 `$FF201D/E` 에 접어 둠) · 0x04 = 접어 둔 색으로 되돌림 · `<ef nn>`·`<ee nn>` = 글자·바탕만 바꿈.
**쪽(0x05) 지움(`$A162`)과 메시지 끝(06·07)은 색을 되돌리지 않는다** — 되돌리기(04)가 빠지면 다음 창까지 색이 번진다(pce-ed1 결함 19개와 같은 부류).
이름 태그 `<1e>…<04>` 쌍은 화자 줄이라 따로 둔다(PS1 문안 이식으로 화자 줄이 늘고 주는 곳이 있다 — 쌍으로 닫히면 허용).

    python3 check_color_codes.py          # 0 이어야 통과
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import build
import common
import hangul
import scene

SET = {0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1F, 0xEE, 0xEF}  # 색 켜기(0x1E 는 화자 이름색)
NAME = 0x1E
RESTORE = 0x04


def color_seq(tokens) -> list[tuple[int, str]]:
    """스트림의 색 켜기·되돌리기 순서(이름 태그 쌍은 뺀다) — 켜기 직전의 열린 색 여부도 함께 본다."""
    out = []
    in_name = False
    for t in tokens:
        if t.kind != "ctl":
            continue
        if t.code == NAME:
            in_name = True
        elif t.code == RESTORE:
            if in_name:
                in_name = False
            else:
                out.append((RESTORE, ""))
        elif t.code in SET:
            out.append((t.code, t.raw[1:].hex()))
    return out


def open_at_end(seq) -> bool:
    """켠 색이 되돌려지지 않은 채 끝나는가."""
    opened = False
    for c, _ in seq:
        if c in SET:
            opened = True
        elif c == RESTORE:
            opened = False
    return opened


def compare(orig_tokens, new_tokens) -> list[str]:
    a, b = color_seq(orig_tokens), color_seq(new_tokens)
    errs = []
    if a != b:
        errs.append(
            f"색 코드 순서가 원판과 다르다 {[hex(c) for c, _ in a]} → {[hex(c) for c, _ in b]}"
        )
    if open_at_end(b) and not open_at_end(a):
        errs.append("켠 색이 되돌려지지 않고 끝난다(다음 창으로 번진다)")
    return errs


def main() -> int:
    orig = common.rom()
    tm = build.load_textmaps()
    cs = hangul.Charset(orig, build.collect_chars(tm))
    bl = archives.blocks(orig, archives.ARCHIVES["script"][0])
    n_streams = n_colored = 0
    errs = []
    for n, m in sorted(tm["maps"].items()):
        mod = scene.parse_module(bl[n][1])
        for k, ent in m["streams"].items():
            if not ent.get("ours") or ent.get("raw"):
                continue
            st = mod.streams.get(int(k, 16))
            if st is None:
                continue
            build.WHERE = f"{n:03d}:{k}"
            toks = build.build_stream(st, ent["ours"], cs)
            n_streams += 1
            if color_seq(st.tokens):
                n_colored += 1
            errs += [f"{n:03d}:{k} {e}" for e in compare(st.tokens, toks)]
    print(
        f"  글자색 코드 대조 — 씬 스트림 {n_streams}(색 든 것 {n_colored}) · 원판과 다름·번짐 {len(errs)}"
    )
    for e in errs[:40]:
        print("   ✗", e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
