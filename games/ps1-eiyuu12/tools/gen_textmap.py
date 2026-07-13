"""임베드형 번역 테이블 → textmap 분류기 (임베드 테이블을 파생 체계로 옮길 때 — 차기 게임 부트스트랩).

도구 파일의 리터럴 테이블(ast 파싱 — import 부작용 없음)을 읽어 각 KR 문장을
정발 DOS 코퍼스에서 역검색한다:
  · 원문 그대로 발견 → (파일, 오프셋, 길이) 포인터 (리포에 문안 미수록)
  · 조판 변환(온점·쉼표 공백 제거)의 역변형으로 발견 → 포인터 + x 플래그
  · 미발견 → 우리 번역("ours")으로 textmap에 직접 수록
출력: textmap/<class>.json + 분류 통계. 검증: derive() 결과 == 원 테이블 전수 비교.

사용: .venv/bin/python tools/gen_textmap.py
"""

import ast
import itertools
import json
import os

from common import ROOT
from derive_text import DOS_ED1, TEXTMAP_DIR, _guard, derive, jkey, transform

TOOLS = os.path.join(ROOT, "tools")

# (클래스, 도구 파일, 변수명, 키 방식)
SOURCES = [
    ("battle", "battle_text.py", "B", "jp"),
    ("items_battle", "patch_items.py", "BATTLE", "jp"),
    ("opening", "patch_opening_font.py", "LINES", "off"),
]

# 역검색 대상 코퍼스 (텍스트 밀도 높은 것 우선 — 첫 발견을 채택)
CORPUS_FILES = ["ED1MAIN.EXE", "OPENING.EXE", "ENDING.EXE", "OPEN.EXE"]
PUNCT = ",.，．。、"


def load_table(fname, var):
    tree = ast.parse(open(os.path.join(TOOLS, fname), encoding="utf-8").read())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == var
        ):
            return ast.literal_eval(node.value)
    raise SystemExit(f"{fname}에 {var} 리터럴 없음")


def corpus():
    files = list(CORPUS_FILES)
    for sub in ("MONDLL", "SINDLL"):
        d = os.path.join(DOS_ED1, sub)
        files += [os.path.join(sub, n) for n in sorted(os.listdir(d)) if n.upper().endswith(".DLL")]
    out = []
    for rel in files:
        p = os.path.join(DOS_ED1, rel)
        if os.path.exists(p):
            out.append((rel, open(p, "rb").read()))
    return out


def space_variants(kr, cap=6):
    """조판 변환의 역후보: 부호 뒤 공백이 제거된 자리에 공백을 되살린 조합."""
    spots = [i for i, ch in enumerate(kr) if ch in PUNCT and i + 1 < len(kr) and kr[i + 1] != " "]
    spots = spots[:cap]
    for mask in itertools.product((0, 1), repeat=len(spots)):
        if not any(mask):
            continue
        s, shift = kr, 0
        for on, i in zip(mask, spots):
            if on:
                s = s[: i + 1 + shift] + " " + s[i + 1 + shift :]
                shift += 1
        yield s


def classify(kr, corp):
    """KR 문장 → src 포인터 또는 None(ours)."""
    cands = [(kr, False)] + [(v, True) for v in space_variants(kr)]
    for cand, x in cands:
        try:
            b = cand.encode("euc-kr")
        except UnicodeEncodeError:
            continue
        if len(b) < 6:  # 너무 짧으면 오검색 — ours로
            continue
        for rel, data in corp:
            o = data.find(b)
            if o >= 0:
                return {"f": rel, "o": o, "l": len(b), **({"x": True} if x else {})}
    return None


def main():
    corp = corpus()
    os.makedirs(TEXTMAP_DIR, exist_ok=True)
    for cls, fname, var, kind in SOURCES:
        table = load_table(fname, var)
        items = list(table.items()) if kind == "jp" else [(f"0x{o:04X}", s) for o, s in table]
        entries, n_src = [], 0
        for key, kr in items:
            k = jkey(key) if kind == "jp" else key
            src = classify(kr, corp)
            e = {"k": k}
            if src:
                got = corp_slice(corp, src)
                assert (transform(got) if src.get("x") else got) == kr
                e["src"] = src
                n_src += 1
            else:
                e["ours"] = kr
            e["sha"] = _guard(kr)
            entries.append(e)
        with open(os.path.join(TEXTMAP_DIR, f"{cls}.json"), "w", encoding="utf-8") as f:
            json.dump({"class": cls, "entries": entries}, f, ensure_ascii=False, indent=1)
        print(f"{cls}: {len(entries)}개 = 정발 포인터 {n_src} + 우리 번역 {len(entries) - n_src}")
        # 라운드트립 검증: 파생 결과 == 원 테이블
        d = derive(cls)
        want = {(jkey(k) if kind == "jp" else k): v for k, v in items}
        assert d == want, f"{cls}: 파생 불일치 {sum(1 for k in want if d.get(k) != want[k])}건"
        print("  ↳ 라운드트립 일치 ✓")


def corp_slice(corp, src):
    data = dict(corp)[src["f"]]
    return data[src["o"] : src["o"] + src["l"]].decode("euc-kr")


if __name__ == "__main__":
    main()
