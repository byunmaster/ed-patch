"""글자색 옵코드 대조 — 원문 메시지의 색 켜기(`1D` 등 STYLE_OPS)·되돌림(`04`)·화자 머리(`1F`)가 우리 조립(`translate.compose`)에 **같은 순서로** 있나.

🔴 10-29 마스터 QA: 컴포즈가 색 옵코드를 처음부터 안 내서 해설이 흰색·장비 문구가 노랑이었고(1차 고침), 켜기만 내고 **끄기(`04`)를 안 내서** 초록이 뒤 대사까지
번졌다(10-30). 켜기만 세지 않고 끄기까지 원문과 같은 순서로 대조한다. 어긋나면 실패.

    python3 games/pce-ed1/tools/check_style_ops.py        # 원본 필요(씬 블록) — check.sh 가 부른다
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import containers
import font
import glyphdyn
import messages as M
import translate as T
import typeset

WATCH = T.STYLE_OPS | {0x04, 0x1F}


def ctrl_seq(b: bytes) -> list[int]:
    """메시지 바이트 → 관찰 대상 제어 바이트 순서. 두 바이트 글자(리드 ≥ 0x24)는 건너뛴다."""
    out, i = [], 0
    while i < len(b):
        c = b[i]
        if c >= 0x24:
            i += 2
            continue
        if c in WATCH:
            out.append(c)
        i += 2 if c == 0x09 else 1
    return out


def orig_seq(m: M.Message) -> list[int]:
    seq = []
    if m.speaker is not None:
        seq += [0x1F, 0x04]
    seq += [t[1] for t in m.tokens if isinstance(t, tuple) and t[1] in WATCH]
    return seq


def check() -> list[str]:
    chars = glyphdyn.forced_chars() | (T.all_glyph_chars() & set(font._order_canon()))
    table, _ = font.build_table(chars)
    errs: list[str] = []
    seen: set[tuple[int, str]] = set()
    n = 0
    for c in containers.scan():
        for b in c["blocks"]:
            sid = b["id"]
            trs = M.load_translations(sid)
            if not trs:
                continue
            btab, _ = glyphdyn.block_table(table, sid)
            typeset.set_scene(sid)
            speakers = M.load_speakers()
            for m in M.parse(b["data"]):
                tr = trs.get(m.key)
                if tr is None or (sid, m.key) in seen or tr.get("raw"):
                    continue
                seen.add((sid, m.key))
                want = orig_seq(m)
                if not (set(want) & T.STYLE_OPS):
                    # 🔴 11-11 「틈 켜기」 — 색 켜기(`1D`)가 메시지 **앞 틈**(이름 변수 뒤)에 있는 메시지는 안에 켜기가 없어 위 대조 밖이었고, 끝 `04`(색 되돌림)가 빠져
                    #    켜진 색이 다음 창 본문까지 번졌다(씬 31·32·33 노랑 · 씬 36 초록). 원문 끝 옵코드에 `04` 가 있으면 우리 끝에도 있어야 한다
                    tail = []
                    for t in reversed(m.tokens):
                        if not isinstance(t, tuple):
                            break
                        tail.append(t[1])
                    if 0x04 in tail:
                        n += 1
                        out = T.compose(m, tr, btab, speakers)
                        k = len(out)
                        while k > 0 and out[k - 1] < 0x24:
                            k -= 1
                        if 0x04 not in out[k:]:
                            errs.append(f"scn{sid:03d} 메시지 {m.key}(블록 {m.start}): 틈에서 색을 켠 메시지 — 원문 끝 옵코드 {[hex(x) for x in reversed(tail)]} 에 `04` 가 있는데 조립 끝 {[hex(x) for x in out[k:]]} 에 없다")
                    continue  # 색을 안 켜는 메시지는 종전 조립 그대로 — 대상 밖
                n += 1
                got = ctrl_seq(T.compose(m, tr, btab, speakers))
                # 쪽 한가운데 색 옵코드는 번역에 자리가 없어 안 낸다(`_page_style_ops` 주석) — 그 밖은 같아야 한다
                anchored = [op for _, op in T._page_style_ops(m)]
                exp = [x for x in want if x not in T.STYLE_OPS or x in anchored]
                if got != exp:
                    errs.append(f"scn{sid:03d} 메시지 {m.key}(블록 {m.start}): 원문 제어 {[hex(x) for x in want]} → 기대 {[hex(x) for x in exp]} · 조립 {[hex(x) for x in got]}")
    print(f"색 옵코드 든 메시지 {n}개 대조")
    return errs


if __name__ == "__main__":
    e = check()
    for x in e:
        print("✗", x)
    print("색 옵코드 대조 위반", len(e))
    sys.exit(1 if e else 0)
