#!/usr/bin/env python3
"""화면에 **나가면 안 되는 바이트열**을 센다 — 마크업 유출·조사 병기 노출.

**왜.** 다른 검출기들은 「있어야 할 것이 있는가」(창 수·인자·일본어 잔존)를 보는데, 이건
**「없어야 할 것이 없는가」**를 본다. mcpads 패처의 `validate_translations` 가 *"a small set of
forbidden Korean strings must never appear"* 로 같은 자리를 지킨다(2026-08-11 흡수).

⚠ **반드시 바이트 층에서 본다.** 페이지 문자열에는 센티널(`\\ue000` 개행 마커 · `\\x1b` 수치
주입 · `은(는)` 병기)이 **정상적으로** 들어 있다 — 거기서 세면 98건이 나오는데 전부 오탐이다
(실측 2026-08-11). 인코딩을 지나 실제로 블록에 실리는 바이트만이 화면이다.

검사 항목:

- **마크업 유출**(`{n}`·`{p}`·`{spk}`) — 정발 마크업이 안 걷힌 채 나갔다
- **이스케이프 리터럴**(`\\xNN`) — 제어코드가 글자로 나갔다
- **조사 병기**(`(는)`·`(가)`) — ⚠ 이건 **전부 오류가 아니다**. 런타임 조사 훅이 표시 직전에
  줄이므로 대사 렌더러 위에서는 정상이다. 문제는 **훅이 안 타는 자리**다 — 상점 프롬프트에서
  실제로 새어 나왔고(2026-07-27 유저 QA `해독초은 (는)`), 그래서 종류를 갈라 보고한다.

  python3 tools/check_forbidden.py         # 요약
  python3 tools/check_forbidden.py -v      # 자리마다
"""

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map
import reinsert_kr_pilot as R


def _josa_re():
    """`(는)`·`(가)` 를 게임 인코딩 바이트로 — 병기는 이 두 꼴만 쓴다."""
    alt = b"|".join(re.escape(hangul_map.syllable_sjis(c).to_bytes(2, "big")) for c in ("는", "가"))
    return re.compile(rb"\((?:" + alt + rb")\)")


BAN = {
    "마크업 유출": re.compile(rb"\{(n|p|/?spk)\}"),
    "이스케이프 리터럴": re.compile(rb"\\x[0-9A-Fa-f]{2}"),
}


# ── 리포에 남으면 안 되는 것: 정발 번역문 ────────────────────────────────────
# 화면 바이트가 아니라 **커밋되는 파일**을 본다. 축이 다르지만 묻는 것은 같다 —
# 「없어야 할 것이 없는가」.
#
# **왜.** `[kr] 문장급 문안은 코드에 임베드 금지`(CLAUDE.md)인데, 새는 자리가 문안 파일만이
# 아니었다(2026-08-13 전수). `align_overrides` 의 `subs` 는 **찾을 문자열이 곧 정발 원문**
# 이었고, `note` 는 판단 근거로 대사를 인용했고, **조판 테스트 픽스처**에도 실제 대사가
# 들어 있었다 — 마지막 것은 문안 파일만 훑어서는 영영 안 잡힌다.
#
# 기준은 **정발 코퍼스**다(초안이 아니라). 초안은 `work/` 라 머신에 없을 수 있는데 코퍼스는
# 빌드가 항상 만든다. 코퍼스가 없으면 검사를 건너뛴다(원본 없는 머신에서 게이트가 죽지 않게).
#
# ⚠ **검사 하나에 물음 둘을 섞지 않는다**(2026-08-18 정리). 섞어 뒀더니 문턱 하나로 둘을
# 같이 맞춰야 해서, 낮추면 오탐이 쏟아지고 높이면 유출이 샜다.
#
#   A. `scan_canon`  — **문안 정본(`script/*.json` 의 `t`)이 정발과 같은가.**
#                      전체 일치라 길이 문턱이 필요 없다. 같으면 **포인터로 바꾼다**
#                      (유저 확정 2026-08-18: "관용적인 표현이라도 일치하면 포인터로
#                      처리하자. 예외규칙이 많아질수록 더 쉽게 혼란에 빠지는것 같네").
#   B. `scan_repo`   — **코드·주석·픽스처에 정발 문장이 박혔나.** 부분 문자열 검색이라
#                      문턱이 없으면 흔한 낱말이 전부 걸린다(실측: 문턱을 떼자 3,189건이
#                      나왔고 `krwrap.py`·`duckstation.sh` 까지 걸렸다). 20자를 유지한다.
#
# ⚠ B 의 20자는 「창작성 판정」이 아니라 **부분 일치 검색의 잡음 하한**이다. 예전엔 이걸
# 창작성 기준으로 적어 뒀는데(「상투구는 안 센다」), 그 해석이 A 까지 오염시켜 상투구를
# 영영 안 고치게 만들었다.
MIN_LEN = 20
SCAN_EXT = (".json", ".py", ".md", ".sh", ".html")
# ⚠ **레포 상대경로로 비교한다.** 절대경로로 하면 레포가 `/root/work/...` 같은 자리에 있을 때
# `work` 가 **모든 디렉터리에 매칭돼** 검사가 통째로 건너뛰어진다 — 게이트가 조용히
# 초록불이 된다(2026-08-13 실측, 일부러 심은 문장을 못 잡아 발견했다).
SKIP_DIR = (".git", "work", ".local", "originals", "vendor", ".venv", "node_modules")
# ⚠ 예외 목록을 두지 않는다 — 같으면 포인터로 바꾸면 되니 통과시킬 이유가 없다.
ALLOW = set()


def _corpus_lines():
    """정발 코퍼스의 문장 집합 — 마크업·제어를 벗기고 길이로 거른다."""
    import glob
    import json

    from common import OUT_DIR

    out = set()
    for f in glob.glob(os.path.join(OUT_DIR, "dos_kr", "**", "*.json"), recursive=True):
        # 게임별 교정 규칙까지 태워야 검사 대상이 빌드 출력과 같아진다 — `dos_kr/ED2/…`.
        game = next((g for g in ("ED1", "ED2") if f"{os.sep}{g}{os.sep}" in f), None)
        try:
            doc = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        ents = doc.get("entries") if isinstance(doc, dict) else doc
        if not isinstance(ents, list):
            continue
        for e in ents:
            if not isinstance(e, dict):
                continue
            try:
                t = R.corpus_text(e.get("text", ""), game)
            except Exception:
                continue
            for seg in re.split(r"\{p\}", t):
                # ⚠ **페이지만 색인하면 문장 단위 복제를 통째로 놓친다.** 우리 정본의 `t` 는
                # **문장 단위**다(정발 한 페이지가 PS1 여러 블록으로 갈리므로 문장으로 잘라
                # 배정한다) — 페이지 집합에는 그 문장이 없어서, 한 글자도 다르지 않아도
                # 조용히 통과했다. 실측 2026-08-18: 게이트가 8건을 보는 동안 **35건**이
                # 새고 있었다. 쪼개는 규칙은 파이프라인 정본(`_sentences`)을 그대로 쓴다.
                for chunk in [seg, *R._sentences(seg)]:
                    # ⚠ **화자 마크업을 뗀 본문도 코퍼스로 친다.** 코퍼스는 `{spk}병사{/spk}
                    # 이봐…` 인데 우리 정본의 `t` 는 **본문만** 담는다 — 마크업만 지우면
                    # `병사` 가 본문 앞에 눌어붙어, 본문이 정발과 한 글자도 다르지 않아도
                    # 축자 일치가 안 나 조용히 통과한다. 실측 4건 보고 → 169건(2026-08-13).
                    for s in {chunk, re.sub(r"^\s*\{spk\}[^{}]*\{/spk\}", "", chunk)}:
                        s = re.sub(r"\{[^}]*\}", "", s)
                        s = re.sub(r"\\x[0-9A-Fa-f]{2}", "", s)
                        s = re.sub(r"\s+", " ", s).strip()
                        # ⚠ **한글이 없으면 문안이 아니다** — `..............` 같은 부호
                        # 덩어리가 길이만으로 걸려 오탐을 만든다(실측 12곳). 저작권 대상은
                        # 표현이지 부호가 아니다.
                        if len(s) >= MIN_LEN and s not in ALLOW and re.search(r"[가-힣]{3,}", s):
                            out.add(s)
    return out


# ED1 자체 번역 전환 중의 기준선 — **늘면 실패, 줄이면 내린다**.
# 32(08-18 실측) → **0**: 걸린 32건을 JP 원문에서 다시 썼다. 이제 하나만 늘어도 운다.
ED1_SIMILAR_BASELINE = 0


def scan_similar(threshold=0.90, report=0.80):
    """축자 일치를 피했어도 **정발 문장과 사실상 같은** 자리를 찾는다(ED1·ED2 정본).

    **왜.** 우리가 직접 쓴 문장은 `script/*.json` 에 그대로 남는다 — 그래서 「정발과 닮은」
    자리가 곧 **정발 문안이 리포에 박히는** 자리다. 짧은 대사는 직역이 최선이라 독립
    창작이어도 수렴한다(실측 2026-08-15: 축자 일치 0건인데 **50건이 90% 이상 일치**).

    ⚠ **2026-08-18 부터 ED1 도 본다.** 전엔 「ED1 은 정발을 포인터로 쓰니 리포에 안 남는다」로
    빼 뒀는데, **자체 번역으로 돌아서면서 ED1 정본이 우리 문장으로 채워진다.** 게다가 빼 둔
    동안 실제로 새 나갔다 — 오프닝 9줄이 **어절 하나를 지운 정발 문장**이라 축자 게이트를
    그냥 통과했다(`세계가 있어, [거기에] 자연의 혜택을 듬뿍`). 축자만 보는 게이트는
    「낱말 하나 지우기」 앞에서 무력하다.

    독립 창작임을 나중에 증명할 길이 없으므로 **닮은 자리는 우리 어투로 다시 쓴다.**

    20자 연속 겹침으로 후보를 좁힌 뒤(전수 비교는 O(n·m)이라 못 돈다) `SequenceMatcher`
    로 잰다. ⚠ 공백을 지우고 비교한다 — 띄어쓰기만 다른 건 같은 문장이다.
    """
    import collections
    import difflib
    import glob as _glob
    import json

    from common import ROOT

    lines = [re.sub(r"\s+", "", s) for s in _corpus_lines()]
    grams = collections.defaultdict(list)
    for s in lines:
        for i in range(len(s) - 19):
            grams[s[i : i + 20]].append(s)

    # ⚠ **낱말 나열은 예외다.** 지명·아이템 같은 **단어 수준 라벨은 저작권 대상이 아니고**
    # (루트 CLAUDE.md), 우리가 정한 표기를 게임이 정한 순서로 늘어놓으면 정발과 닮을 수밖에
    # 없다 — `ED2SCN2 jp300` 은 워프 목적지 34개를 나열한 표라 0.98 이 나온다.
    # 자리를 콕 집어 적는다(규칙으로 넓히면 진짜 문장이 빠져나간다).
    WORDLIST_OK = {("ED2SCN2", "300")}

    rows = []
    for path in sorted(_glob.glob(os.path.join(ROOT, "script", "ED*SCN*.json"))):
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        for eid, v in doc.items():
            t = re.sub(r"\s+", "", v.get("t", ""))
            best = 0.0
            for i in range(len(t) - 19):
                for cand in grams.get(t[i : i + 20], ()):
                    best = max(best, difflib.SequenceMatcher(None, t, cand).ratio())
            scn = os.path.basename(path)[:-5]
            if best >= report and (scn, eid) not in WORDLIST_OK:
                rows.append((best, scn, eid))
    rows.sort(reverse=True)
    over = [r for r in rows if r[0] >= threshold]
    for sim, scn, eid in rows[:10]:
        mark = "❌" if sim >= threshold else "·"
        print(f"      {mark} {sim:.2f} {scn} jp{eid}")
    ed1 = sum(1 for r in over if r[1].startswith("ED1"))
    # 🔴 **래칫** — ED1 은 아직 정발에서 문안이 오는 자리가 1,800 넘게 남아 있다(자체 번역
    #    전환 중). 지금 걸린 것들을 전부 실패로 치면 **늘 빨간불**이라 아무도 안 본다.
    #    그래서 기준선을 박고 **늘면 실패**한다 — 줄이면 이 숫자를 내린다(되돌릴 수 없다).
    #    ⚠ 이건 면죄부가 아니라 **작업 목록**이다: `--report` 로 뽑아 재작성한다.
    ed2 = len(over) - ed1
    print(
        f"  {'✅' if not over else '⚠'} 정발과 닮은 문안: "
        f"{threshold:.0%}+ {len(over)}건(ED1 {ed1}) · {report:.0%}+ {len(rows)}건"
    )
    if ed1 > ED1_SIMILAR_BASELINE:
        print(
            f"  ❌ ED1 닮은 문안이 기준선을 넘었다: {ed1} > {ED1_SIMILAR_BASELINE}"
            " — 새로 쓴 문안이 정발을 베꼈다는 뜻이다"
        )
    elif ed1 < ED1_SIMILAR_BASELINE:
        print(f"  ⬇ ED1 기준선을 내릴 수 있다: {ED1_SIMILAR_BASELINE} → {ed1}")
    return ed2 + max(0, ed1 - ED1_SIMILAR_BASELINE)


def scan_canon(verbose=False):
    """🔴 **문안 정본이 정발과 글자까지 같은 자리** — 포인터로 바꿔야 한다.

    `script/*.json` 의 `t` 는 **우리가 쓴 번역**이어야 한다. 정발과 같다면 둘 중 하나다 —
    ① 정발을 보고 옮겨 적었거나(리포에 정발 문안이 남는다) ② 우연히 같아졌거나. 어느 쪽이든
    **정발을 가리키면 된다**(방침이 정발 우선이고, 그러면 문안이 리포에서 사라진다).

    ⚠ **길이 예외를 두지 않는다**(유저 확정 2026-08-18). 예전엔 「상투구는 창작성이 낮으니
    통과」로 20자 문턱을 뒀는데, 그 예외가 판단을 흐렸다 — 자리마다 「이건 상투구인가」를
    다시 물어야 했고 문턱 언저리는 매번 결론이 갈렸다. 규칙은 하나다: **같으면 포인터로.**

    ⚠ **공백을 무시한다.** 정발은 `{n}` 자리에 공백이 없다(`부상자는대체 어디에 있는거야?`)
    — 띄어쓰기만 다듬어 옮겨 적은 자리가 통째로 빠져나가던 구멍이다(실측 2026-08-18).
    """
    import glob as _glob
    import json

    from common import ROOT

    lines = _corpus_lines()
    if not lines:
        print("  ⏭ 정발 코퍼스가 없어 건너뜀")
        return 0
    flat = {re.sub(r"\s+", "", s) for s in lines}
    # ⚠ **반대 방향도 본다.** 정발 엔트리는 문장 끝에 공백이 없는 자리가 많아(`일이야.자네가`)
    # `_sentences` 가 못 가르고 **한 줄로 뭉친다** — 그러면 우리 `t` 가 그 줄보다 **짧아서**
    # 전체 일치로는 영영 안 걸린다. 우리 문안이 정발 엔트리의 **일부**인 자리도 유출이다
    # (실측 2026-08-18: 그렇게 26건이 새고 있었다).
    joined = "".join(sorted(flat))
    hits = collections.Counter()
    rows = []
    # ⚠ **`textmap/` 도 본다.** `script/` 만 훑다가 전투 대사 하나가 `ours` 에 그대로 남아
    # 있었다(2026-08-18). 문안이 사는 자리는 둘이다 — 한쪽만 보면 반만 지키는 것이다.
    files = sorted(_glob.glob(os.path.join(ROOT, "script", "*SCN*.json")))
    files += sorted(_glob.glob(os.path.join(ROOT, "textmap", "*.json")))
    for path in files:
        scn = os.path.basename(path)[:-5]
        doc = json.load(open(path, encoding="utf-8"))
        items = doc.items() if "entries" not in doc else [
            (str(i), pp) for i, e in enumerate(doc["entries"])
            for pp in ([e] if "ours" in e else e.get("parts", []))
        ]
        for eid, v in items:
            if not isinstance(v, dict):
                continue
            t = ((v.get("t") or v.get("ours")) or "").strip()
            if not t or not re.search(r"[가-힣]{2,}", t):
                continue
            ft = re.sub(r"\s+", "", t)
            if ft in flat or (len(ft) >= 20 and ft in joined):
                hits[scn] += 1
                rows.append((scn, eid, t))
    # 🔴 **방향이 바뀌었다**(유저 확정 2026-08-18: 자체 번역). 예전 규칙은 「정발과 같으면
    #    포인터로」였는데, 이제 문안은 우리가 쓴다 — **우연히 같아지는 것은 침해가 아니다.**
    #    다만 자리를 가른다:
    #      · 대사(`script/*SCN*.json`) — 창작성이 있다. 긴 문장이 축자로 같으면 **베낀 것**이다.
    #      · EXE 시스템 문구(`textmap/*.json`) — 「〜が現れた。」는 누가 옮겨도 같다. **강제
    #        번역**이라 우연 일치가 정상이고, 다르게 쓰면 나빠진다(방침 08-04: 기능적 문구는
    #        `ours` 허용). 세되 **실패로 치지 않는다.**
    sys_hits = sum(v for k, v in hits.items() if not k.startswith("ED"))
    n = sum(hits.values()) - sys_hits
    print(
        f"  {'✅ 대사 정본에 정발 축자 없음' if not n else f'⚠ 대사 정본이 정발과 축자 동일 {n}건'}"
        + (f" · 시스템 문구 {sys_hits}건(강제 번역 — 실패 아님)" if sys_hits else "")
    )
    if n:
        print("      " + " · ".join(f"{k} {v}" for k, v in sorted(hits.items()) if k.startswith("ED")))
    if verbose:
        for scn, eid, t in rows[:40]:
            print(f"      {scn} jp{eid}: {t[:56]!r}")
    return n


def scan_repo(verbose=False):
    """커밋되는 파일에 정발 번역문이 있는가."""
    lines = _corpus_lines()
    if not lines:
        print("  ⏭ 정발 코퍼스가 없어 건너뜀(원본이 있는 머신에서 검사된다)")
        return 0
    # tools → 게임 → games → 레포 루트
    root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    bad = 0
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR]
        for f in files:
            if not f.endswith(SCAN_EXT):
                continue
            path = os.path.join(dirpath, f)
            try:
                data = open(path, encoding="utf-8").read()
            except Exception:
                continue
            # ⚠ **공백을 무시하고 찾는다.** 정발은 `{n}` 줄바꿈 자리에 공백이 없는데
            # (`부상자는대체 어디에 있는거야?`) 우리는 띄어 쓴다 — 띄어쓰기만 다듬어 옮겨
            # 적으면 **글자는 그대로인데 검사기가 통과시킨다**(실측 2026-08-18: 그 부류가
            # 대부분이었다). 저작권은 표현이 문제지 공백이 문제가 아니다.
            flat = re.sub(r"\s+", "", data)
            hit = [s for s in lines if re.sub(r"\s+", "", s) in flat]
            if hit:
                rel = os.path.relpath(path, root)
                # 🔴 EXE 시스템 문구(`textmap/`)는 **강제 번역**이라 우연 일치가 정상이다 —
                #    「〜が現れた。」는 누가 옮겨도 「〜이(가) 나타났다.」다(방침 08-18 · 08-04).
                #    세되 실패로 치지 않는다. 대사(`script/`)는 그대로 실패다.
                if os.sep + "textmap" + os.sep in path:
                    print(f"      ℹ {rel}: 시스템 문구 {len(hit)}건 (강제 번역 — 실패 아님)")
                    continue
                bad += len(hit)
                print(f"      ⚠ {rel}: 정발 번역문 {len(hit)}건")
                for h in hit[:3] if verbose else hit[:1]:
                    print(f"           {h[:56]!r}")
    print(
        f"  {'✅ 리포에 정발 번역문 없음' if not bad else f'⚠ 정발 번역문 {bad}건'}"
        + (
            ""
            if not bad
            else "\n      → 문안은 `align_map` 포인터로, 손댄 부분만 `subs_at` 오프셋으로 둔다"
        )
    )
    return bad


def scan(verbose=False):
    josa = _josa_re()
    bad = collections.defaultdict(list)
    kinds = collections.Counter()
    n = 0
    for name, eid, _jp, cand, t in R.iter_candidates():
        n += 1
        for k, rx in BAN.items():
            if m := rx.search(cand):
                bad[k].append((name, eid, m.group(0)))
        if josa.search(cand):
            stock = isinstance(t, tuple) and t and t[0] == "__stock__"
            kinds["정형 블록(훅 대상 — 정상)" if stock else "대사(훅 확인 필요)"] += 1
            if not stock:
                bad["조사 병기 — 대사"].append(
                    (name, eid, R.render_bytes(cand, ctrl=False)[:48].replace("\n", " "))
                )
    print(f"화면 바이트 검사 — 재삽입 블록 {n}개")
    for k in BAN:
        v = bad.get(k, [])
        print(f"  {'⚠' if v else '✅'} {k:<16} {len(v)}건")
        for nm, e, g in v[: (None if verbose else 3)]:
            print(f"        {nm} jp{e}: {g!r}")
    print(f"  · 조사 병기 방출 {sum(kinds.values())}건 — {dict(kinds)}")
    for nm, e, g in bad.get("조사 병기 — 대사", [])[: (None if verbose else 6)]:
        print(f"        {nm} jp{e}: {g!r}")
    print(
        "\n⚠ 조사 병기는 **훅이 타면 정상**이다 — 정형 블록은 1·2장 QA 로 확인됐다."
        "\n  대사 쪽은 인게임에서 병기가 그대로 보이는지 확인할 것(상점 프롬프트에서 실제로 샜다)."
    )
    return sum(len(v) for k, v in bad.items() if k in BAN)


if __name__ == "__main__":
    v = "-v" in sys.argv
    # 네 축을 한 진입점에서 본다 — 물음이 저마다 다르니 규칙도 저마다 하나씩이다.
    #   scan          화면에 나가는 바이트에 없어야 할 것이 있나
    #   scan_canon    **문안 정본이 정발과 글자까지 같나**(전체 일치 · 길이 문턱 없음)
    #   scan_repo     코드·주석·픽스처에 정발 문장이 박혔나(부분 일치 · 20자 하한)
    #   scan_similar  축자는 피했지만 사실상 같은 ED2 문안인가(없으면 「축자만 피하면
    #                 통과」가 되어 정발 문장이 리포에 남는다 — 실측 50건)
    sys.exit(1 if (scan(v) + scan_canon(v) + scan_repo(v) + scan_similar()) else 0)
