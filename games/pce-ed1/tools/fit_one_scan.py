#!/usr/bin/env python3
"""원문 한 창 → 우리 두 창 이상으로 갈린 메시지 전수(마스터 11-05 「자막은 OFF문안을 최대한 따르기」) — 2-10(문장마다 새 줄)을 이 메시지에 한해 풀어 한 창에 채울 수 있는지 본다.

  python3 tools/fit_one_scan.py [--write]    # 목록을 찍고, --write 면 `script/typeset_fit_one.json` 을 쓴다(typeset.pages 가 읽는다)
원문 창 수 = 메시지 토큰의 쪽 넘김(`05`·`03`) 수 + 1(끝 쪽 넘김은 안 센다). 우리 창 수 = 이음·이름 변수 문안을 `typeset.pages(…, four=True)` 로 짠 쪽 수.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import messages as M
import typeset

OUT = common.GAME_DIR / "script" / "typeset_fit_one.json"
PAGE_OPS = (0x05, 0x03)


def orig_windows(m) -> int:
    toks = list(m.tokens)
    if m.terminated and len(toks) >= 2 and toks[-2] in (("op", 0x05), ("op", 0x03)):
        toks.pop(-2)  # 종료(`06`·`07`) 바로 앞 쪽 넘김(`05 06`)도 끝의 쪽 넘김이다 — 11-07: 이걸 창으로 세어 원문 한 창을 둘로 잘못 셌다
    while toks and isinstance(toks[-1], tuple) and toks[-1][0] == "op" and toks[-1][1] in PAGE_OPS:
        toks.pop()  # 끝의 쪽 넘김은 다음 메시지로 가는 것 — 이 메시지의 창이 아니다
    return 1 + sum(1 for t in toks if isinstance(t, tuple) and t[0] == "op" and t[1] in PAGE_OPS)


def gate_timed() -> set[tuple[int, str]]:
    """나레이션 게이트 음성 타이머(`_g` 토막)가 쪽마다 시각을 쥔 메시지 — 쪽 수가 바뀌면 싱크가 어긋나는 구조 계약이라 풀지 않는다(보고 목록에 사유)."""
    import voice_editor_data as VED

    typeset.FIT_ONE = set()  # 풀기 전 기준(편집기 자료가 풀기 파일에 기대지 않게)
    try:
        return {(r["scene"], r["key"]) for r in VED.build()[0] if "_g" in r["clip"]}
    finally:
        typeset.FIT_ONE = None


def scan() -> tuple[list[dict], list[dict]]:
    fit, nofit = [], []
    locked = gate_timed()
    seen: set[tuple[str, str]] = set()
    for p in sorted(common.OUT_DIR.glob("text/*.bin")):
        tail = p.stem.split("_")[-1]
        if not tail.isdigit():
            continue
        sid = int(tail)
        try:
            trs = M.load_translations(sid)
        except Exception:
            continue
        blk = p.read_bytes()
        for m in M.parse(blk):
            tr = trs.get(m.key)
            if not tr or tr.get("raw") or not tr.get("t"):
                continue
            t = tr["t"]
            if (m.key, t) in seen:
                continue
            sp = M.speaker_kind(m, sid)
            ow = orig_windows(m)
            src = font.expand_packed(t.lstrip(" ")).rstrip("\f")  # 끝 `\f`(쪽 넘김 옵코드로 끝나는 메시지)는 빈 쪽이 아니다
            typeset.FIT_ONE = set()  # 지금 규칙(풀기 없음)으로 짠 창 수
            ours = typeset.pages(src, speaker=sp, four=True)
            if len(ours) <= ow:
                continue
            seen.add((m.key, t))
            typeset.FIT_ONE = None
            row = {"scene": sid, "key": m.key, "orig": ow, "ours": len(ours), "speaker": sp, "t": t, "src": src}
            if (sid, m.key) in locked:
                nofit.append({**row, "lines": None, "why": "게이트 음성 타이머(쪽 수가 싱크 계약)"})
                continue
            chunks = src.split("\f")
            if ow == 1 and len(chunks) > 1:  # 원문은 한 창인데 번역이 `\f` 로 갈랐다 — 이어서 한 창에 들면 이어 붙인다
                one = typeset.fit_one_pages(" ".join(chunks), speaker=sp)
                (fit if one is not None else nofit).append({**row, "lines": one, "src": src, "why": "" if one else "번역이 쪽을 갈랐고 이어도 한 창에 안 든다"})
                continue
            if ow == 1 and len(chunks) == 1:
                one = typeset.fit_one_pages(src, speaker=sp)
                (fit if one is not None else nofit).append({**row, "lines": one, "why": "" if one else "한 창(3·4줄)에 안 들어간다"})
                continue
            if len(chunks) == ow:  # 쪽 조각이 원문 쪽과 1:1 — 갈린 조각만 풀어 본다
                typeset.FIT_ONE = set()
                bad = [c for c in chunks if len(typeset.pages(c, speaker=sp, four=True)) > 1]
                ok = [c for c in bad if typeset.fit_one_pages(c, speaker=sp) is not None]
                typeset.FIT_ONE = None
                if bad and len(ok) == len(bad):
                    fit.append({**row, "lines": [" | ".join(typeset.fit_one_pages(c, speaker=sp)) for c in ok], "src": src, "chunks": ok, "why": ""})
                    continue
                nofit.append({**row, "lines": None, "why": f"쪽 조각 {len(bad) - len(ok)}개가 한 창에 안 들어간다" if bad else "조각은 1창씩인데 합친 조판이 갈랐다"})
                continue
            nofit.append({**row, "lines": None, "why": f"번역이 쪽을 다시 나눴다(조각 {len(chunks)} ≠ 원문 창 {ow})"})
    # 이름 변수 이어쓰기(INLINE_LEAD)는 편집기·ON 자막이 「앞 꼬리 + 이름 + 문안」 이은 글을 짠다 — 그 글도 한 창으로(ROM 창은 `translate` 의 lead 경로)
    import translate as T
    import voice_editor_data as VED

    for p in sorted(common.OUT_DIR.glob("text/*.bin")):
        tail = p.stem.split("_")[-1]
        if not tail.isdigit():
            continue
        sid = int(tail)
        blk = p.read_bytes()
        ms = M.parse(blk)
        trs = M.load_translations(sid)
        for m in ms:
            if m.key in T.INLINE_LEAD:
                joined = VED.joined_kr(blk, m.key, trs, {x.key for x in ms})
                src = font.expand_packed(joined)
                one = typeset.fit_one_pages(src, speaker=False)
                if one is not None:
                    fit.append({"scene": sid, "key": m.key, "orig": 1, "ours": 0, "speaker": False, "t": joined, "src": src, "lines": one})
    typeset.FIT_ONE = None
    fit, nofit = metric_gate(fit, nofit)
    return effective_gate(fit, nofit)


def effective_gate(fit: list[dict], nofit: list[dict]) -> tuple[list[dict], list[dict]]:
    """풀기 목록에 올린 문안이 **실제 조판(`typeset.pages` — 화자 `nl=` 쪽 수 계약 분기 포함)에서도** 원문 창 수 안에 드는가.
    🔴 11-07: `fit_one_pages` 만 보고 ✔ 로 올렸다가 쪽 수가 계약인 씬(`speaker == "nl="` — 13칸 첫 줄 조판과 10칸 조판의 창 수가 다르면 종전으로 되돌린다)에서
    롬은 그대로 2창으로 나가던 것(씬 2 도구점 NPC 「왕자님, 이런 데서 놀고…」)을 잡는다 — 못 이룬 것은 사유와 함께 nofit 으로 내린다."""
    keep: list[dict] = []
    for r in fit:
        if r["key"] in __import__("translate").INLINE_LEAD or not r.get("ours"):
            keep.append(r)  # 이름 변수 이어쓰기는 다른 경로(lead 조판)
            continue
        typeset.set_scene(r["scene"])
        typeset.FIT_ONE = set(r.get("chunks") or [r["src"]])
        got = typeset.pages(r["src"], speaker=r["speaker"], four=True, keep_windows=typeset.keep_windows(r["scene"]))
        typeset.FIT_ONE = None
        keep.append(r)  # 풀기 파일에는 그대로 둔다 — 같은 문안이 계약 씬 밖(다른 메시지·편집기)에서 효과가 있고, 지문이 그걸 잡는다
        if len(got) > r["orig"]:
            nofit.append({**r, "lines": None, "why": "쪽 수가 계약인 씬(`nl=`) — 창 수를 못 바꾼다(풀어 짠 줄은 있으나 롬 조판이 종전으로 되돌린다)"})
    return keep, nofit


def metric_gate(fit: list[dict], nofit: list[dict]) -> tuple[list[dict], list[dict]]:
    """풀어 짠 안이 줄·쪽 나눔 지표(2-16: a b d e f g h h2 i)를 **늘리면** 풀지 않는다 — 한 창으로 합쳐도 이음 갈림이 새로 생기면 안 된다."""
    import linebreak_metrics as LM

    keep: list[dict] = []
    import translate as T

    for r in fit:
        if r["key"] in T.INLINE_LEAD:  # 이름 변수 이어쓰기 — 편집기·ON 글(앞 꼬리+이름+문안)이라 단위 지표로 못 잰다
            keep.append(r)
            continue
        t = r["t"]
        srcs = set(r.get("chunks") or [r["src"]])
        typeset.FIT_ONE = set()
        before = LM.measure_unit(t, r["scene"])
        typeset.FIT_ONE = srcs
        after = LM.measure_unit(t, r["scene"])
        typeset.FIT_ONE = None
        worse = {k: (before[k], after[k]) for k in ("a", "b", "d", "e", "f", "g", "h", "h2", "i") if after[k] > before[k]}
        # 🔴 마스터 11-05 「원문칸은 최대한 유지」(번역 규칙 2-17 맨 앞·2-10 「가능하면」) — 풀어 한 창이 되면 이음 갈림 지표가 한둘 느는 건 감수한다(원문 창 수가 먼저).
        #   늘어난 만큼은 기준선(`linebreak_baseline.json`)에 올려 적고, 왜 올렸는지 devlog 에 둔다.
        keep.append({**r, "worse": worse})
    return keep, nofit


def main() -> int:
    fit, nofit = scan()
    print(f"원문 1창 → 우리 2창+: 한 창에 채워짐 {len(fit)} · 안 채워짐/원문 여러 창 {len(nofit)}")
    for r in fit:
        print(f"  ✔ scn{r['scene']:03d} {r['key'][:8]} 원문 {r['orig']}→우리 {r['ours']} {' / '.join(r['lines'])}" + (f"  [지표 +{r['worse']}]" if r.get("worse") else ""))
    for r in nofit:
        print(f"  ✗ scn{r['scene']:03d} {r['key'][:8]} 원문 {r['orig']}→우리 {r['ours']} [{r.get('why','')}] {r['t'][:40]!r}")
    if "--write" in sys.argv:
        texts = sorted({c for r in fit for c in (r.get("chunks") or [r["src"]])})
        OUT.write_text(json.dumps({"_doc": "원문이 한 창인데 우리 조판이 둘 이상으로 가른 문안 — 2-10(문장마다 새 줄)을 풀어 한 창에 채운다(마스터 11-05). tools/fit_one_scan.py --write 가 만든다", "texts": texts}, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"→ {OUT} ({len(texts)}문안)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
