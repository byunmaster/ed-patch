#!/usr/bin/env python3
"""빌드 코드에 **굳어 있는 한글 문안**이 정본(script·textmap)을 덮지 않는지 본다(10-20, style 전수 검수).

**왜.** `shop_price_build` 가 가격 확인 마지막 줄을 `encode_ext("괜찮으시겠습니까?")` 로 코드에 박아, 정본 script 의 가게별 말투
(해요·하게·하우·반말·사투리)가 화면에서 전부 합쇼체로 바뀌고 「그래도」가 빠졌다(ED1·ED2 21곳). 정본(script)과 빌드 코드가 **같은 문안을
두 곳에** 두면, 코드 쪽이 이겨서 정본 수정이 화면에 안 닿는다 — 검출기들은 정본만 읽으므로 못 본다.

두 가지를 본다.
  ① **정적(AST)** — 화면 문안을 만드는 `encode_ext(…)`·`enc(…)` 호출의 첫 인자에 **한글 리터럴**이 있으면 허용 목록(`ALLOWED`)에 있어야 한다.
     허용은 조사 병기 조각(`은(는)`·`이(가)`)·이름 한 낱말(`에게`·`류난`)·셀프테스트 문자열뿐이다. 새 문장이 박히면 실패 — 정본(script·textmap)에서
     읽게 고친다. (`check_`·`test_`·`past_` 같은 도구·테스트 파일은 제외.)
  ② **배선** — 상점 가격 프롬프트(`SHOP_PRICE`)가 전부 **정본 문안을 갖고** 있고(없어 폴백이 나가면 실패), 방출 바이트가 그 정본의 줄을 그대로 낸다.

  python3 tools/check_hardcoded_ko.py [-v]
"""

import ast
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("LOCK_BYPASS", "1")

HANGUL = re.compile(r"[가-힣]")
SKIP = re.compile(r"^(check_|test_|past_|make_|audit_)")
CALLS = {"encode_ext", "enc", "_enc"}

# (파일, 리터럴) — 허용 사유: 조사 병기 조각(훅이 푼다) · 이름 한 낱말 · 셀프테스트.
ALLOWED = {
    ("reinsert_kr_pilot.py", "은(는)"),  # 조사 병기 — 런타임 훅이 받침 보고 푼다
    ("reinsert_kr_pilot.py", "이(가)"),
    ("reinsert_kr_pilot.py", "이슈타"),  # 라운드트립 셀프테스트
    ("reinsert_kr_pilot.py", "야, 안녕하세요."),  # 〃
    ("patch_items.py", "에게"),  # 데미지 조사 조각 — 가게별 변형 없음
    ("patch_items.py", "류난"),  # 이름 한 낱말(정본 표기)
}


def hardcoded_literals(path):
    """[(줄, 호출, 리터럴)] — 화면 인코더 호출의 첫 인자 속 한글 문자열 상수."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = getattr(f, "id", None) or getattr(f, "attr", None)
        if name not in CALLS or not n.args:
            continue
        for c in ast.walk(n.args[0]):
            if isinstance(c, ast.Constant) and isinstance(c.value, str) and HANGUL.search(c.value):
                out.append((n.lineno, name, c.value))
    return out


def scan_static():
    bad = []
    for p in sorted(glob.glob(os.path.join(HERE, "*.py"))):
        b = os.path.basename(p)
        if SKIP.match(b):
            continue
        for ln, name, lit in hardcoded_literals(p):
            if (b, lit) not in ALLOWED:
                bad.append((b, ln, name, lit))
    return bad


def scan_shop_wiring(verbose=False):
    """상점 가격 블록이 정본 문안을 갖고, 방출 바이트가 그 줄을 그대로 내는지."""
    import reinsert_kr_pilot as R

    bad, n = [], 0
    for scn in sorted(set(R.scene_list(None))):
        cands = {eid: cand for _s, eid, _jp, cand, _t in R.iter_candidates([scn])}
        for eid, ours in sorted(R.SHOP_PRICE_OURS.items()):
            n += 1
            if not ours:
                bad.append((scn, eid, "정본 문안 없음 — 폴백이 나간다"))
                continue
            cand = cands.get(eid)
            if cand is None:
                bad.append((scn, eid, "후보 바이트를 못 만들었다"))
                continue
            text = R.render_bytes(cand)
            for ln in R.shop_price_lines(ours):
                if ln.replace("\x1b", "%d") not in text:
                    bad.append((scn, eid, f"방출에 정본 줄이 없다: {ln!r}"))
    return n, bad


def main(argv):
    verbose = "-v" in argv
    rc = 0
    bad = scan_static()
    for b, ln, name, lit in bad:
        print(f"  ❌ {b}:{ln} {name}({lit!r}) — 빌드 코드에 굳은 한글 문안 — 정본(script·textmap)에서 읽게 고치거나 사유와 함께 ALLOWED 에 올린다")
        rc = 1
    n, wb = scan_shop_wiring(verbose)
    for scn, eid, why in wb:
        print(f"  ❌ {scn} jp{eid}: 상점 가격 프롬프트 {why}")
        rc = 1
    if rc == 0:
        print(f"  ✅ 코드에 굳은 한글 문안 0 · 상점 가격 프롬프트 {n}건이 전부 정본 문안으로 나간다")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
