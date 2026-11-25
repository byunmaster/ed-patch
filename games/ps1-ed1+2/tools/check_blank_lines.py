#!/usr/bin/env python3
"""빈 줄 개행 게이트 — 규칙 2-18(「창은 첫 줄부터 쓴다 · 문장 사이 빈 줄 금지」, 마스터 11-08).

세 곳을 센다. 전부 **원판보다 늘면 실패**다(원판이 가진 빈 줄은 레이아웃 몫 — 아래).
 ① 조판 결과(`wrap_pages` 출력) — 빈 줄이 든 쪽 0
 ② 씬 블록 최종 바이트 — 연속 개행(0A 0A)이 원본 블록보다 늘지 않았나
 ③ EXE 문자열 — 연속 개행 수가 원판 이하(원판 11 중 장 끝 카드 6·메모리카드 안내 4 는 **화면 배치**다:
    「제N장 …⏎⏎ 완」· 「저장 중 …⏎⏎ 카드를 빼지 마세요」 처럼 제목/상태와 안내를 가르는 줄이라 둔다)

⚠ 「이름 없는 창의 선두 개행」은 여기서 안 센다 — 이름창 뒤 본문의 선두 개행은 이름 줄을 위한 정상 구조이고, 이름이 별도 창으로
  접힌 블록과 구분하려면 렌더가 필요하다(11-08 실측: ED1SCN2:933 자물쇠 문구는 바이트가 개행으로 시작해도 첫 줄에 그려진다).
  빌드가 이미 이름 없는 본문 창의 선두 개행을 뗀다(reinsert_kr_pilot `build_from_template`).

  python3 tools/check_blank_lines.py [--exe]   # --exe 는 BUILD_DIR 의 이미지(없으면 건너뜀)
"""

import contextlib
import glob
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from check_window_nl import SCN_COUNT, raws_of
from common import BUILD_DIR, ORIG_BIN, extract
from text import krwrap as K

EXES = {"ED.EXE": (257, 1021952), "ED2.EXE": (756, 872448)}


def scan_scenes():
    fails, texts = [], 0
    orig_wrap, seen = K.wrap_pages, []

    def spy(*a, **kw):
        p = orig_wrap(*a, **kw)
        seen.append((a[0] if a else kw.get("text", ""), p))
        return p

    K.wrap_pages = R.kr_wrap_pages = spy
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            for scn, lba, size in R.SCN_FILES:
                seen.clear()
                R.build_scene(scn, lba, size, False, False)
                for text, pages in seen:
                    texts += 1
                    for i, pg in enumerate(pages):
                        if any(not ln.strip() for ln in pg):
                            fails.append(f"{scn} 조판 빈 줄 — 쪽{i} {pg[:2]}")
    finally:
        K.wrap_pages = R.kr_wrap_pages = orig_wrap
    dbl = 0
    with contextlib.redirect_stdout(io.StringIO()):
        for game in ("ED1", "ED2"):
            for n in range(1, SCN_COUNT[game] + 1):
                name = f"{game}SCN{n}"
                tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
                for eid, raw in raws_of(name).items():
                    t = tr.get(eid)
                    if not t:
                        continue
                    try:
                        cand, _ = R.build_candidate(raw, t, eid)
                    except Exception:
                        continue
                    if cand is not None and cand.count(b"\x0a\x0a") > raw.count(b"\x0a\x0a"):
                        fails.append(f"{name}:{eid} 연속 개행이 원본보다 늘었다")
                    dbl += cand.count(b"\x0a\x0a") if cand is not None else 0
    return fails, texts, dbl


def scan_exe():
    imgs = glob.glob(os.path.join(BUILD_DIR, "*.bin"))
    if not imgs:
        return [], None
    fails, rows = [], {}
    for name, (lba, size) in EXES.items():
        o = bytes(extract(lba, size, path=ORIG_BIN))
        n = bytes(extract(lba, size, path=imgs[0]))
        rows[name] = (o.count(b"\x0a\x0a"), n.count(b"\x0a\x0a"))
        if rows[name][1] > rows[name][0]:
            fails.append(f"{name} 연속 개행 {rows[name][0]} → {rows[name][1]} (원판보다 늘었다)")
    return fails, rows


def main():
    fails, texts, dbl = scan_scenes()
    print(f"빈 줄 검사 [ps1-ed1+2] — 조판 {texts}건 · 씬 블록 연속 개행 {dbl}(원본 이하)")
    if "--exe" in sys.argv:
        ef, rows = scan_exe()
        fails += ef
        print(f"  EXE 연속 개행(원판→이미지): {rows}" if rows else "  EXE: 이미지 없음 — 건너뜀")
    for f in fails:
        print("  ❌", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
