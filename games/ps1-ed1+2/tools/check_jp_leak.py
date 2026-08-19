#!/usr/bin/env python3
"""재조립 **결과 바이트**에 원문이 남았는가 — 화면에 깨진 글자로 나가는 자리를 잡는다.

**왜.** 블록이 게이트에 걸려 통째로 탈락하면 화면에 일본어가 뜬다 — 그건
`check_ed2_reinsert`·`build.py` 가 본다. 그런데 **탈락하지 않고도** 원문이 남는 길이 따로
있다: 원문이 `%c아이템명%c나머지` 처럼 색 구간을 쓰는데 우리 문안이 그 경계에 안 맞으면,
조립기가 **못 채운 구간의 원문을 그대로 둔다.** 구조 계약(`%c`·`%s` 개수)은 지켜지니
게이트가 다 초록이고, 화면에만 깨진 글자가 나간다:

    %c切符%cを 渡しました。%c   +  "표를 건넸습니다."
    →  %c자符%c표를 건넸습니다.%c        ← 符 가 살아서 나간다

⚠ **한글 슬롯을 쓰므로 깨진 일본어는 「엉뚱한 한글」로 보인다**(`密造酒` → `密짚숌`).
그래서 화면을 봐도 오타처럼 읽히지 실수를 못 알아챈다 — 바이트로 봐야 잡힌다.

**판정은 축이 둘이다** — 하나로는 절반만 잡힌다.

- `leaked()` — 후보 바이트 중 **우리 한글 슬롯 밖**이면서 가나·한자인 코드.
  부호(`～`·`『』`·전각 영숫자)는 게임 폰트의 정상 글리프라 뺀다(안 빼면 79건 오탐, 실측).
- `shared_runs()` — **원문 raw 와 2글자 이상 연속 일치.** 위 축은 슬롯 **안**의 한자를
  못 본다(`密造酒` 에서 `密` 만 잡고 `造酒` 는 놓친다) — 그 구멍을 이쪽이 메운다.

실측(2026-08-15): ED1 체인 등록분 **0건**, ED2 **49건**. ED2 만 걸린 건 우연이 아니라
**ED2 가 재삽입 피드백 루프 밖에 있었기** 때문이다(체인 미등록 → 빌드가 문안을 안 본다).

🔴 **축이 하나 더 있다 — 「정본에 항목조차 없는 블록」**(2026-08-19, ED2 검수가 찾았다).
위 둘은 **재조립 후보를 만들 수 있는 블록**만 본다(`iter_candidates` 는 번역표를 돈다).
번역표에 아예 없는 블록은 순회 자체에 안 들어와 **원문이 그대로 화면에 나가는데도 초록**이다.
실제로 여덟 블록이 그렇게 새고 있었다(`ED2SCN10:67` · `ED2SCN11:222·225` · `ED2SCN12:123·158` …).
전부 **포인터 표 접두**(anchor_tail)라 눈으로도 안 띄었다 — `untranslated()` 가 이 구멍을 메운다.

  python3 tools/check_jp_leak.py            # 체인 등록분(ED1)
  python3 tools/check_jp_leak.py --ed2      # ED2 씬까지
"""

import json
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import os

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from font_map import JIS_KANJI1_INDEX
from hangul_map import jis_index_to_sjis

# 우리가 한글로 덮어쓴 슬롯 — 여기 있는 코드는 화면에 한글로 나간다.
OUR_SLOTS = {jis_index_to_sjis(JIS_KANJI1_INDEX + i) for i in range(2350)}
JP_CHAR = re.compile(r"[ぁ-ゟァ-ヺ一-鿋]")  # 가나·한자만 — 부호·전각 영숫자는 정상 글리프


def leaked(buf):
    """후보 바이트에 남은 원문 글자들."""
    out, i = [], 0
    while i < len(buf):
        c = buf[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:  # SJIS 2바이트 선행
            if i + 1 < len(buf):
                s = (c << 8) | buf[i + 1]
                if s not in OUR_SLOTS:
                    ch = s.to_bytes(2, "big").decode("cp932", "replace")
                    if JP_CHAR.match(ch):
                        out.append(ch)
            i += 2
        else:
            i += 1
    return out


def shared_runs(jp, cand, chars=2):
    """원본과 후보에 **똑같이 들어 있는 2바이트 글자 연속열**(기본 2자 이상).

    ⚠ `leaked()` 만으로는 절반밖에 못 본다. 우리가 한자 슬롯을 한글로 덮어썼으므로
    **원문 한자의 코드가 우리 슬롯 안에 있으면 「엉뚱한 한글」로 렌더돼 코드로는 구분이
    안 된다** — `密造酒` 가 `密짚숌` 으로 보이는 이유이고, `密` 만 잡히고 `造酒` 는
    안 잡힌다. 그래서 **원문 raw 와 대조**하는 축을 함께 둔다: 우리 문안이 원문의 2바이트
    글자 두 개 이상을 그대로 재현할 일은 없다.
    """
    out, i = [], 0
    body = jp.rstrip(b"\x00")
    while i + 2 * chars <= len(cand):
        c = cand[i]
        if not (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC):
            i += 1
            continue
        n = 0
        while i + 2 * (n + 1) <= len(cand):
            d = cand[i + 2 * n]
            if not (0x81 <= d <= 0x9F or 0xE0 <= d <= 0xFC):
                break
            n += 1
        for ln in range(n, chars - 1, -1):
            seq = cand[i : i + 2 * ln]
            if seq in body:
                out.append(seq.decode("cp932", "replace"))
                break
        i += 2 * max(n, 1)
    return out


# 「문장인가」를 가르는 두 표 — 지명 헤더·값 표를 걸러 낸다(안 걸러 내면 560건 오탐, 실측).
_KANA = re.compile(r"[ぁ-ゟァ-ヺ]")
_PLATE = re.compile(r"\{c\}[^{}]+\{c\}\{n\}")  # 이름창 + 개행 = 대사다
_TERM = re.compile(r"[。？！]")


def _tail(s):
    """포인터 표 접두를 지난 **실제 텍스트**만. 추출기가 비텍스트를 이스케이프로 흘려 둔다."""
    i = s.rfind("\\x80")
    return s[i + 4 :] if i >= 0 else s


def is_dialogue(t):
    """이 꼬리 텍스트가 **화면에 나가는 대사**인가 — 지명 헤더·값 표와 가른다.

    좁게 잡는다(넓히면 560건이 쏟아진다, 실측):

    - **이름창 + 개행**이 있으면 대사다 → 무조건 참
    - 아니면 **가나 6자 이상 + 종결 부호**를 요구한다 (`グロストス城` 은 5자라 빠진다)
    """
    return bool(_PLATE.search(t) or (len(_KANA.findall(t)) >= 6 and _TERM.search(t)))


def untranslated(scenes=None, verbose=False):
    """번역표에 **항목조차 없는데** 화면에는 대사가 나가는 블록.

    ⚠ 「재조립 결과에 남은 원문 0」은 「번역이 다 됐다」가 아니다 — `iter_candidates` 는
    번역표를 돌기 때문에 **항목이 없으면 순회에 안 들어온다.** 그 사각을 여기서 본다.

    판정은 `is_dialogue` 가 하고, 여기서 하나를 더 뺀다 —
    **꼬리가 같은 번역된 블록이 있으면 제외한다.** 재삽입기가 대표 사본으로 참조를 돌리므로
    (`_register_mid_alias`) 그 사본은 원문이 안 나간다. 정형문 사본이 여기 걸린다.
    """
    rows = []
    for name in dict.fromkeys(R.scene_list(scenes) if scenes is None else scenes):
        with open(os.path.join(R.OUT_DIR, "scn_jp", f"{name}.json"), encoding="utf-8") as f:
            txt = {e["entry_id"]: (e.get("text") or "") for e in json.load(f)["entries"]}
        with R.overlay_for(name):
            try:
                tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
            except Exception:  # noqa: BLE001,S112 — 체인 밖 씬은 셀 수 없다
                continue
        done = {_tail(txt[e]) for e in txt if e in tr}
        for eid, s in sorted(txt.items()):
            if eid in tr or not s:
                continue
            t = _tail(s)
            if t in done:
                continue
            if is_dialogue(t):
                rows.append((name, eid, t[:46]))
    for name, eid, t in rows if verbose or rows else []:
        print(f"    ⚠ {name} jp{eid}  정본에 항목이 없다  {t!r}")
    print(
        f"  {'✅' if not rows else '❌'} 정본에 항목이 없는 대사 블록: {len(rows)}"
        + ("" if not rows else "  ← 화면에 원문이 그대로 나간다")
    )
    return len(rows)


def scan(scenes=None, verbose=False):
    rows = []
    for scn, eid, jp, cand, _t in R.iter_candidates(scenes):
        hit = leaked(cand) or shared_runs(jp, cand)
        if hit:
            rows.append((scn, eid, "".join(hit), R.render_bytes(cand)[:56]))
    for scn, eid, chars, shown in rows if verbose or rows else []:
        print(f"    ⚠ {scn} jp{eid} [{chars}]  {shown!r}")
    print(
        f"  {'✅' if not rows else '⚠'} 재조립 결과에 남은 원문: {len(rows)}블록"
        + ("" if not rows else "  ← 화면에 깨진 글자로 나간다")
    )
    return len(rows)


if __name__ == "__main__":
    sc = R.ED2_SCENES if "--ed2" in sys.argv else None
    v = "-v" in sys.argv
    a, b = scan(sc, v), untranslated(sc, v)
    # ⚠ 두 축의 요약을 **맨 끝 한 줄**로 다시 낸다 — 사이에 `load_translations` 의 진행
    #   출력이 끼어 `check.sh` 의 `tail -1` 이 요약을 놓친다(실측 2026-08-19).
    print(f"  {'✅' if not (a + b) else '❌'} 화면에 나가는 원문: 재조립 잔존 {a} · 정본 밖 {b}")
    sys.exit(1 if a + b else 0)
