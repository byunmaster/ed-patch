#!/usr/bin/env python3
"""**화면에 나갈 문안**을 맞춤법 검사기에 돌린다 — 정발 코퍼스가 아니라 재조립 결과를 본다.

`spellcheck_corpus.py` 와 짝이지만 보는 곳이 다르다. 저쪽은 **정발 원문 전량**을 보고
(쓰지 않는 엔트리까지), 이쪽은 **실제로 블록에 실리는 문안**만 본다. 셋이 갈린다:

- **`ours`(우리가 쓴 문안)가 들어온다** — A급 치환은 정발 코퍼스에만 걸려 이 문안은
  파이프라인 어디에서도 검사받은 적이 없다(`ours_to_pointer.py` 주석 ②).
- **슬라이스·이음(`chain`/`subs`)의 결과를 본다** — 정발 원문엔 없던 이음매가 생긴다.
- **안 쓰는 엔트리를 안 본다** — 검토량이 줄고 보고서가 실제 화면과 1:1 이 된다.

⚠ 창 조판(줄바꿈) 전 문안이다. 검사기에 개행을 넣으면 청크 줄 대응이 깨지고, 어차피
줄바꿈은 `krwrap` 관할이라 맞춤법 판정에 넣을 이유가 없다.

⚠ 산출물엔 정발 문안이 실린다 — REVIEW_DIR(gitignore) 로만 나간다.
⚠ 외부 서비스에 문안을 보낸다 — 유저 승인 하에만 실행할 것.

  python3 tools/spellcheck_render.py               # 전 씬 검사 → 보고서
  python3 tools/spellcheck_render.py --report      # 캐시만으로 보고서 재생성
  python3 tools/spellcheck_render.py --apply       # A급을 dos_spelling_fixes 에 반영
"""

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_REPO, "shared"))

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import REVIEW_DIR, ROOT
from patch_sys_ui import _scn_layout
from text import spellcheck as sc

OUT = os.path.join(REVIEW_DIR, "corpus")
SPELL_JSON = os.path.join(ROOT, "dos_spelling_fixes.json")
CACHE = os.path.join(OUT, "render_spell_cache.json")

# 센티널·제어 잔재는 검사기에 보내면 낱말로 오해받는다(`%s를` → 조사를 지어낸다).
# 자리만 비워 두고 그 문장은 `inject` 로 표시해 A급에서 뺀다.
SENT = re.compile(f"[{R.NAME_SENT}{R.NUM_SENT}{R.ITEM_SENT}{R.HARD_NL}]|%[csd]|`[0-9{{]")

# ── 문체만 건드리는 제안 걷어내기 ────────────────────────────────────────────
# ⚠ **B급 1,078건 중 절대다수가 「정발 어투를 표준 현대문으로 바꾸라」였다**(2026-08-11 전수).
# `기쁘옵니다.`→`기쁩니다.` · `왔노라.`→`왔다.` · `모르것지만유`→`모르겠지만,` · 호격 뒤 쉼표.
# 번역 정책은 **정발 표기 그대로**라 이건 전부 물리칠 것이고, 개별 `reject` 로 쌓으면 회차마다
# 새 표면형이 다시 올라온다(`-는걸` 가드를 넷이나 따로 물리치고서야 규칙으로 바꿨다).
# 그래서 **부류로 거른다** — 사람이 볼 목록이 1,078 → 90 안쪽이 되고, 새 표면형도 같이 걸린다.
_PUNCT = ".,!?…·~\"'’”)》」"
_TERM = ".!?…"
# 정발이 쓰는 문체 표지. **왼쪽에만 있고 오른쪽에서 사라지면** 어투를 바꾸려는 것이다.
_STYLE = re.compile(
    r"(옵니다|옵나이다|사옵|시옵|나이다|노라|구려|하오|이오|시오|다오"  # 사극·경어체
    r"|[가-힣]소[.!?]*$|[가-힣]네[.!?,]*$|[가-힣]오[.!?]*$|[가-힣]지요[.!?]*$"  # 하게·하오체 종결
    r"|유[.!?]*$|구먼|것지|것소|그려|잖유|여유)"  # 사투리(오누·가울 노인 등)
)
# 존대 등급을 **올리는** 제안(평어 → 합쇼체). 화자 신분이 정하는 것이지 맞춤법이 아니다.
_HONOR = re.compile(r"(습니다|세요|십시오|해요|이에요|예요|입니다)")
# 고유명사 — 사전에 없으니 검사기가 **아는 낱말로 끌어당긴다**(`쟈그리`→`자그니`·`자극`·`저기로`,
# `파렌`→`파리`, `프람`→`불`). 개별 `reject` 로는 못 막는다: 조사가 붙을 때마다 새 표면형이
# 되기 때문이다(`쟈그리는`·`쟈그리에`·`쟈그리로`·`쟈그리의`를 따로 물리쳐야 한다).
# 표기 정본은 `docs/jeongbal-deviations.md` 이고, 여기엔 **검사기가 실제로 건드린 것만** 둔다.
_PROPER = ("쟈그리", "파렌", "라누라", "온리크", "솔디스", "프람", "Gold")
# 정발의 **옛 표기** — 틀린 게 아니라 낡게 읽힐 뿐이다. 유저 확정 2026-08-11: **정발 유지**
# ("오타까지는 아니니까"). 어미가 붙어 표면형이 늘어나므로(`오래간만이군`·`오래간만이로군`·
# `오래간만에`) 낱말로 판정한다.
_OLD_ORTHO = (
    "요즈음",
    "오래간만",
    "이제까지",
    "이제껏",
    "둥그런",
    "부인이",
    "잘되었",
    "주시었",
    "주시어",
    "멈추어",
    "세어서",
    "바래요",
    "시일",
)


def _strip(s, chars):
    for ch in chars:
        s = s.replace(ch, "")
    return re.sub(r"\s+", " ", s).strip()


def style_only(x, y):
    """문체만 건드리는 제안이면 사유, 아니면 None.

    ⚠ **종결부호를 새로 다는 제안은 남긴다** — 정발에 온점이 빠진 자리는 실제로 채워 왔다
    (`docs/status.md` 온점 누락 방침). 부호를 **바꾸는** 것만 문체로 본다.
    """
    if any(p in x and p not in y for p in _PROPER):
        return "고유명사를 사전 낱말로 바꿈"
    if any(p in x and p not in y for p in _OLD_ORTHO):
        return "정발 옛 표기(유지 확정)"
    if _strip(x, _PUNCT) == _strip(y, _PUNCT):
        if not x.rstrip().endswith(tuple(_TERM)) and y.rstrip().endswith(tuple(_TERM)):
            return None  # 종결부호 보완 — 사람이 본다
        return "부호만 바꿈"
    a, b = _strip(x, _PUNCT), _strip(y, _PUNCT)
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    if i >= 2 and i >= max(len(a) - i, len(b) - i) and max(len(a) - i, len(b) - i) <= 4:
        return "어간이 같고 어미만 다름"
    if _STYLE.search(x) and not _STYLE.search(y):
        return "정발 문체 표지를 지움"
    if _HONOR.search(y) and not _HONOR.search(x):
        return "존대 등급을 올림"
    if i >= 2 and len(a) - i <= 5 and len(b) - i <= 5:
        return "어간이 같고 꼬리만 다름"
    return None


def collect():
    """{문장: {"n": 횟수, "inject": bool, "at": [씬:eid …], "ours": bool}}"""
    ov = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8"))
    uniq = {}
    for name, _lba, _size in _scn_layout():
        tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
        ours = {int(k) for k, v in ov.get(name, {}).items() if "ours" in v}
        for eid, v in sorted(tr.items()):
            if not isinstance(v, tuple) or len(v) < 2 or not isinstance(v[1], list):
                continue
            for _, page in v[1]:
                if not isinstance(page, str):
                    continue
                inject = bool(SENT.search(page))
                s = SENT.sub(" ", page)
                s = re.sub(r"\s+", " ", s).strip()
                if len(s) < 2 or not re.search(r"[가-힣]", s):
                    continue
                d = uniq.setdefault(s, {"n": 0, "inject": False, "at": [], "ours": False})
                d["n"] += 1
                d["inject"] |= inject
                d["ours"] |= eid in ours
                if len(d["at"]) < 6:
                    d["at"].append(f"{name}:{eid}")
    return uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=900)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    uniq = collect()
    keys = sorted(uniq)
    meta = {s: {"n": v["n"], "inject": v["inject"]} for s, v in uniq.items()}
    n_ours = sum(1 for v in uniq.values() if v["ours"])
    print(
        f"화면 문안 {len(keys)}종 (우리 문안 {n_ours} · 주입 자리 {sum(v['inject'] for v in uniq.values())})"
    )

    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    save = lambda c: json.dump(c, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    parts = sc.chunks(keys, a.chunk)
    n_new = len([p for p in parts if "\n".join(p) not in cache])
    print(f"  청크 {len(parts)}개 · 캐시 {len(parts) - n_new} · 요청 {0 if a.report else n_new}")
    if not a.report:
        sc.fetch(parts[: a.limit] if a.limit else parts, cache, jobs=a.jobs, on_save=save)

    # ⚠ 검사기가 문장을 합치거나 쪼개면 그 **청크 전체가 통째로 버려진다**(`collate` 의
    # `skewed`). 136청크 중 22가 그렇게 날아갔다 — 코퍼스의 16%가 검사 없이 통과하는데
    # 로그 한 줄 말고는 티가 안 난다. 깨진 청크만 **잘게 다시** 물어본다(줄이 적을수록
    # 대응이 덜 깨지고, 깨져도 잃는 문장이 적다).
    def broken(ps):
        return [p for p in ps if "\n".join(p) in cache and sc.collate([p], cache, meta)[2]]

    for size in (max(120, a.chunk // 6), 0):
        if a.report:
            break
        bad = broken(parts)
        if not bad:
            break
        flat = [s for p in bad for s in p]
        # 마지막 라운드는 **한 문장씩** 묻는다 — 그러면 검사기가 줄을 쪼개도 통째로
        # 이어 붙여 되살릴 수 있다(아래 `_solo`). 청크로는 그게 불가능하다.
        fine = sc.chunks(flat, size) if size else [[s] for s in flat]
        print(f"  ⚠ 줄 대응이 깨진 청크 {len(bad)} → {len(fine)}개로 다시 검사")
        sc.fetch(fine, cache, jobs=a.jobs, on_save=save)
        parts = [p for p in parts if p not in bad] + fine

    # 한 문장 청크의 응답이 여러 줄로 쪼개졌으면 이어 붙여 되살린다(문장 경계가 하나뿐이라
    # 대응이 유일하다). 이걸 안 하면 그 문장은 영영 검사에서 빠진다.
    for p in parts:
        src = "\n".join(p)
        if len(p) == 1 and src in cache and "\n" in cache[src]:
            cache[src] = " ".join(x.strip() for x in cache[src].split("\n") if x.strip())

    changed, pairs, skewed = sc.collate(parts, cache, meta)
    # ⚠ **물리친 제안도 기억해야 한다.** 검사기는 매번 같은 오판을 다시 낸다(`네놈`→`네 놈`,
    # `알현장`→`알 현장`). 채택분만 `known` 으로 넘기면 물리친 것들이 회차마다 A급에 다시
    # 올라와, 사람이 같은 판단을 반복하다 결국 섞여 들어간다. `reject` 는 그 판단의 정본이다.
    doc = json.load(open(SPELL_JSON, encoding="utf-8"))
    known = list(doc.get("replace", [])) + [r[:2] for r in doc.get("reject", [])]
    auto, manual, dropped = sc.classify(pairs, known)
    # ⚠ 감탄 종결어미 `-는걸/-은걸`을 의존명사 `것을`로 오인해 띄우는 제안이 회차마다 새 표면형으로
    # 올라온다(`드는걸`·`맞는걸`·`가벼워진걸`·`오는걸` — 넷을 따로 물리쳤다). 어미는 앞말에 붙는다.
    # `먹을 걸까`(=것일까)와는 **앞 음절의 어미**로 갈린다 — `-는/-은/-ㄴ` 뒤의 `걸`만 어미다.
    _EOMI_GEOL = re.compile(r"(?:는|은|[가-힣])걸[.!?]*$")
    auto = [(x, y, v) for x, y, v in auto if not (_EOMI_GEOL.search(x) and " 걸" in y)]
    # 문체만 건드리는 제안은 부류로 걷어낸다(위 `style_only` 주석 참조).
    n_style = sum(1 for x, y, _v in manual if style_only(x, y))
    manual = [(x, y, v) for x, y, v in manual if not style_only(x, y)]

    p = os.path.join(OUT, "render_spell_report.md")
    open(p, "w", encoding="utf-8").write(
        sc.report("화면 문안 맞춤법 검토", len(keys), changed, auto, manual, dropped, skewed)
    )
    print(f"  → {p}")
    print(
        f"  A급 {len(auto)} · B급 {len(manual)} · 문체만 걷어냄 {n_style} · 부호공백 버림 {dropped}"
    )

    # 검토용 기계 판독본 — 사람이 훑는 건 위 마크다운이고, 이건 골라내는 도구용이다.
    pj = os.path.join(OUT, "render_spell_pairs.json")
    json.dump(
        {
            k: [[x, y, v["n"], v["ex"]] for x, y, v in rows]
            for k, rows in (("A", auto), ("B", manual))
        },
        open(pj, "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=0,
    )

    if a.apply:
        add = sc.merge_replace(SPELL_JSON, auto)
        print(f"  dos_spelling_fixes.json: replace +{len(add)}")
        print("  ⚠ `ours` 문안은 이 표를 안 지나간다 — 보고서에서 직접 고칠 것")


if __name__ == "__main__":
    main()
