#!/usr/bin/env python3
"""**원판 대조 조판 누락 게이트 — 변수 앞 공백 · 쪽 구간 수 · 끝 개행.**

왜(10-30). pce-ed1 에서 보물상자 문구가 변수 칸 앞 공백 없이 붙고, 원판의 쪽·줄 나눔과 메시지 끝 개행이 우리 문안에 없어
다음 문장·선택지가 같은 줄에 붙었다(마스터 「띄어쓰기 개행 제대로 안 된 게 꽤 있을 것 같은데」). 같은 부류가 이 게임에 있나 원판과
짝지어 센다 — 전부 0 이고, 다시 생기면 실패한다. 분모(블록·구간 수)와 양성 대조(일부러 망가뜨린 후보를 잡나)를 같이 찍는다.

  ① 변수 앞 공백 — 씬 후보·실행파일 문자열에서 한글 바로 뒤에 `%s`/`%d`(색 코드 `%c` 사이 포함)가 오면 어절 경계가 없다.
  ② 쪽 구간 수 — 원판 블록의 `%c` 구간 수와 우리 후보가 같아야 한다(쪽 나눔이 줄면 두 문장이 한 쪽에 붙는다).
  ③ 끝 개행 — 원판 구간이 `\\n` 으로 끝나는데 우리 구간이 아니면, 그 구간 마지막 줄이 칸을 꽉 채워 엔진이 자동으로 넘기는
     경우(`drop_frame_full_nl` 의도)만 허용한다.

  python3 tools/check_orig_breaks.py
"""

import io
import json
import os
import re
import sys
import contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

# 핫픽스 덮개를 얹은 값(v1.2.1 준비분)을 잰다 — 공용 판정기 말뭉치(`rulings_corpus.py`)와 같은 잣대. 제품 롬은 그 값에 못 미쳐도 이 게이트가 막지 않는다.
os.environ["ED_HOTFIX"] = "1"
with contextlib.redirect_stdout(io.StringIO()):
    import reinsert_kr_pilot as R

HG_VAR = re.compile(r"[가-힣](?:%c)*%[sd]")


def seg_full(seg):
    """구간 마지막 줄이 칸을 꽉 채우나 — 변수가 든 줄은 폭을 못 재므로 판정 불가(허용 안 함)."""
    last = seg.rstrip("\n").split("\n")[-1]
    if not last or "%s" in last or "%d" in last:
        return False
    return abs(sum(R.cell_w(c) for c in last) - R.FRAME_SLOTS) < 1e-9


def judge(jp_raw, cand):
    """(변수앞공백, 구간수어긋남, 끝개행누락, 구간수) — 블록 하나."""
    k = R.render_bytes(cand.rstrip(b"\x00"), ctrl=True)
    j = jp_raw.rstrip(b"\x00").decode("cp932", "replace")
    var = len(HG_VAR.findall(k))
    js, ks = j.split("%c"), k.split("%c")
    if len(js) != len(ks):
        return var, 1, 0, len(js)
    tail = sum(1 for a, b in zip(js, ks) if a.endswith("\n") and b.strip() and not b.endswith("\n") and not seg_full(b))
    return var, 0, tail, len(js)


def main():
    nblk = nseg = 0
    bad = {"변수앞공백": [], "구간수": [], "끝개행": []}
    for scn in sorted(os.listdir(os.path.join(C.OUT_DIR, "scn_jp"))):
        name = scn[:-5]
        if not name.startswith(("ED1SCN", "ED2SCN")):
            continue
        with contextlib.redirect_stdout(io.StringIO()):
            cands = list(R.iter_candidates([name]))
        for _n, eid, raw, cand, _t in cands:
            v, s, t, n = judge(raw, cand)
            nblk += 1
            nseg += n
            if v:
                bad["변수앞공백"].append(f"{name}:{eid}")
            if s:
                bad["구간수"].append(f"{name}:{eid}")
            if t:
                bad["끝개행"].append(f"{name}:{eid}")
    # 양성 대조 — 일부러 망가뜨린 후보를 잡아야 한다(못 잡으면 검사기가 죽은 것)
    import hangul_map

    def enc(s):
        return b"".join(
            ch.encode() if ch in "\n%cs " else hangul_map.syllable_sjis(ch).to_bytes(2, "big") for ch in s
        )

    raw = b"%c\x8e\x98\x8f\x97%c\n\x82\xb1\x82\xf1\x82\xc9\x82\xbf\x82\xcd\x81B\n%c\x00\x00"
    good = enc("%c여자%c\n안녕\n%c") + b"\x00\x00"
    assert judge(raw, good) == (0, 0, 0, 4), "양성 대조 — 정상 후보가 걸렸다"
    assert judge(raw, enc("%c여자%c\n안녕%c") + b"\x00\x00")[2] == 1, "양성 대조 — 끝 개행 누락을 못 잡았다"
    assert judge(raw, enc("%c여자%c\n안녕\n"))[1] == 1, "양성 대조 — 구간 수 부족을 못 잡았다"
    assert judge(raw, enc("%c여자%c\n안녕%s\n%c"))[0] == 1, "양성 대조 — 변수 앞 공백 없음을 못 잡았다"
    assert judge(raw, enc("%c여자%c\n안녕 %s\n%c"))[0] == 0, "양성 대조 — 공백 있는 변수를 걸었다"
    # 실행파일 문자열(원판과 짝지은 한글 열)
    nexe = 0
    exe_bad = []
    kr_bin = os.path.join(C.BUILD_DIR, "Eiyuu Densetsu (KR).bin")
    if os.path.exists(kr_bin):
        import tempfile

        import pair_table_sys as PS

        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "pairs.tsv")
            with contextlib.redirect_stdout(io.StringIO()):
                PS.battle_system(kr_bin, out)
            with open(out, encoding="utf-8") as fh:
                rows = [ln.split("\t") for ln in fh.read().split("\n")[1:] if ln.strip()]
        for r in rows:
            if len(r) >= 3:
                nexe += 1
                if HG_VAR.search(r[2]):
                    exe_bad.append(r[0])
        bad["변수앞공백"] += exe_bad
    else:
        print("  ❌ 안 쟀다 — 최종 이미지 없음(실행파일 문자열)")
        return 1
    tot = sum(len(v) for v in bad.values())
    print(
        f"  원판 대조 조판 누락 [ps1-ed1+2] — 씬 {nblk}블록 · 쪽 구간 {nseg} · 실행파일 {nexe}문자열 · "
        f"변수앞공백 {len(bad['변수앞공백'])} · 구간수 {len(bad['구간수'])} · 끝개행 {len(bad['끝개행'])} (양성 대조 통과)"
    )
    for k, v in bad.items():
        for x in v[:10]:
            print(f"    ❌ {k} {x}")
    return 1 if tot else 0


if __name__ == "__main__":
    sys.exit(main())
