#!/usr/bin/env python3
"""**이름창에 남의 이름이 뜨는가** — 원문 화자 헤더와 우리 화자를 대조한다.

**왜.** 번역 정본(`script/`)의 화자(`s`)는 배정 시대 초안에서 물려받았는데, 그건 **정발
엔트리의 화자**라서 PS1 원문과 어긋난 자리가 있다. 바즈눈 성 알현이 전형이다 — 세리오스·
류난·게일의 대사가 전부 `크레아 왕비` 이름표를 달고 나간다(2026-08-12 전수에서 발견).

⚠ **화자맵이 정답은 아니다.** `_speaker_map` 은 JP 이름 → 정발 이름 대응표라 **우리가 정한
표기**와 어긋난다 — `ジェルマン` 을 `젤만` 으로 주지만 우리 정본은 `제르만` 이고(유저 확정
2026-08-11), `大盗賊 ゲイル` 을 `게일` 로 뭉개면 손자 게일과 구분이 사라진다. 그래서 두
층을 가른다:

- **인물이 다르다** — 이름이 서로 겹치지 않는다. **진짜 오류**다.
- **표기가 다르다** — 한쪽이 다른 쪽을 품거나 글자가 겹친다(`제르만`/`젤만` ·
  `대도 게일`/`게일` · `한스 대통령`/`한스`). 우리 표기를 따른다.

⚠ 원문에 **헤더가 없는 블록**(앞 블록에서 이어지는 말)은 보지 않는다 — 파이프라인이
원문 헤더 유무로 이름창 방출을 정하므로, 우리 `s` 가 남아 있어도 화면에 안 나간다.

  python3 tools/check_speakers.py            # 전 씬
  python3 tools/check_speakers.py ED1SCN4    # 한 씬
  python3 tools/check_speakers.py --all      # 표기 차이까지(판정 참고용)

정본에 `"sx": true` 를 달면 그 블록은 검사에서 빠진다(정체를 숨긴 인물 등 의도적 불일치).
"""

import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R


def _canon_persons():
    """고유명사 정본의 인물 표 — `shared/glossary` 하나가 정본이다."""
    sys.path.insert(0, os.path.join(R.ROOT, "..", "..", "shared"))
    import glossary as G

    return dict(G.table("person"))


SCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "script")


def _same_person(ours, canon):
    """표기 차이인가(같은 인물인가). 품음 관계이거나 글자가 많이 겹치면 같은 사람으로 본다."""
    a, b = ours.replace(" ", ""), canon.replace(" ", "")
    if a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.5


def _script(scn):
    p = os.path.join(SCRIPT_DIR, f"{scn}.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    p = os.path.join(R.ROOT, "work", "review", f"draft_{scn}.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def candidates(scn):
    """[(블록, 우리 화자, JP 이름, 정발 대응, 다른 인물인가)]"""
    d = _script(scn)
    out = []
    for _s, eid, jp, _c, _t in R.iter_candidates((scn,)):
        k = str(eid)
        if k not in d or not R.jp_has_header(jp) or R.jp_header_is_fmt(jp):
            continue
        try:
            name = jp[2 : jp.find(R.MC, 2)].decode("cp932")
        except (UnicodeDecodeError, ValueError):
            continue
        canon = R._speaker_map().get(name)
        ent = d[k] or {}
        ours = ent.get("s")
        # ⚠ **일부러 다른 이름을 쓰는 자리가 있다** — 정체를 숨긴 인물이 이름을 밝히기 전까지
        # `갇힌 사람` 처럼 나오다가 소개 뒤에 실명으로 바뀌는 연출이다(게일 `jp560`, 유저 확인
        # 2026-08-12). 정본에 `"sx": true` 를 달면 여기서 뺀다.
        if not canon or not ours or ours == canon or ent.get("sx"):
            continue
        out.append((eid, ours, name, canon, not _same_person(ours, canon)))
    return out


def scan_runtime_labels(scenes=None, verbose=False):
    """**런타임 이름창(`%s`)인데 라벨이 박혀 있는가** — 화면이 아니라 **도구**가 오염된다.

    이름창이 `{c}%s{c}` 인 블록은 **엔진이 런타임에 리더 이름을 꽂는다.** 우리 `s` 는 화면에
    안 나가므로 위 `scan` 이 `jp_header_is_fmt` 로 건너뛴다 — 화면 검사로는 그게 옳다.

    🔴 **그런데 라벨이 남아 있으면 화자 기준으로 도는 것들이 전부 틀린 답을 본다.**
    실측(2026-08-25): 86블록에 라벨이 박혀 있었고 **대개 듣는 쪽 이름**이었다(앞 창에서
    상속된 것이다) — 일행이 문지기에게 하는 말 셋이 `입구의 병사` 로, 세리오스가 게일을
    꾸짖는 말이 `게일` 로 달려 있었다. 그 상태로 인물별 대사를 뽑아 검수를 돌렸더니
    **소니아 표에 세리오스 대사 셋이 섞여** 「합류 장면에서 소니아가 반말을 쓴다」는 가짜
    신호가 났다. `check_speech_level` 도 같은 것을 본다.

    ⚠ 고치는 방법은 **라벨을 지우는 것**이다(맞는 이름으로 바꾸는 게 아니다) — 화자가
    런타임 리더라 **고정 이름은 무엇을 넣어도 거짓**이다. 지워도 화면은 안 바뀐다
    (2026-08-25 실증: 86건을 지우고 재빌드해 **이미지 sha1 동일**).
    """
    bad = []
    for scn in R.scene_list(scenes):
        if scenes and scn not in scenes:
            continue
        d = _script(scn)
        for _s, eid, jp, _c, _t in R.iter_candidates((scn,)):
            k = str(eid)
            if not R.jp_has_header(jp) or not R.jp_header_is_fmt(jp):
                continue
            ent = d.get(k) or {}
            if ent.get("s"):
                bad.append((scn, eid, ent["s"]))
    print(f"  {'✅' if not bad else '⚠'} 런타임 이름창(`%s`)에 박힌 라벨 {len(bad)}곳")
    if bad and verbose:
        for scn, eid, s in bad[:20]:
            print(f"      {scn} jp{eid}: [{s}] ← 화자는 런타임 리더다")
    if bad:
        print("      ⚠ 라벨을 **지운다**(바꾸는 게 아니다) — 화면은 안 바뀌고 도구만 바로잡힌다.")
    return len(bad)


def scan(scenes=None, show_all=False):
    tot = 0
    for scn in R.scene_list(scenes):
        if scenes and scn not in scenes:
            continue
        rows = candidates(scn)
        wrong = [r for r in rows if r[4]]
        tot += len(wrong)
        print(
            f"  {'✅' if not wrong else '⚠'} {scn}: 남의 이름 {len(wrong)}곳"
            f" (표기 차이 {len(rows) - len(wrong)})"
        )
        for eid, ours, name, canon, bad in rows:
            if bad or show_all:
                mark = "⚠" if bad else "  "
                print(f"      {mark} jp{eid}: 우리 [{ours}] ← 원문 [{name} = {canon}]")
    print(
        f"\n{'✅ 남의 이름 없음' if not tot else f'⚠ 남의 이름 {tot}곳'}"
        "\n  ⚠ 표기 차이는 **우리 표기가 맞다** — 편차 대장"
        "(docs/jeongbal-deviations.md)이 정본이고, `_speakers` 에 등록하면 여기서 사라진다."
    )
    return tot


def scan_canon(verbose=False):
    """🔴 **이름창에 나가는 이름이 정본과 같은가** — 화자맵과 `s` 를 정본에 대조한다.

    **왜 이게 따로 필요한가.** 위 `scan` 은 「원문 화자와 우리 화자가 같은 사람인가」를 본다.
    같은 사람이면 **표기가 갈려도 통과**한다 — 그 시절엔 표기 정본이 없었기 때문이다.
    2026-08-19 에 `shared/glossary` 가 인물 220 · 지명 97 로 채워지면서 기준이 생겼다.

    ⚠ **정본이 없던 동안 실제로 갈렸다**(2026-08-19 실측, 131블록 13종) — `盗賊` 이
    도둑/도적, `ピート` 가 피토/피트, `フォルス` 가 폴스/훨스, `町長` 이 촌장/시장.
    ED2 주인공 `アトラス` 조차 정본에 없었으니 **아무도 지켜 주지 않았다.**

    🔴 **화면을 그리는 것은 `s` 가 아니라 화자맵이다**(`reinsert_kr_pilot._tpl_name` —
    맵을 먼저 보고 없을 때만 `s` 로 떨어진다). 그래서 두 층을 다 본다:

    - **화자맵** — 화면에 나가는 값. 정본과 다르면 **실패**.
    - **`s`** — 폴백이자 사람이 읽는 자리. 어긋나면 **실패**(맵이 비면 이게 화면이 된다).

    ⚠ 정본에 **없는** 이름은 실패로 치지 않는다 — 정본은 상위집합이지만 맵에는 `%s` 템플릿
    화자처럼 이름이 아닌 것도 섞인다. 「할 일」로 보여만 준다.
    """
    canon = _canon_persons()
    bad, unknown = [], set()
    for jp, kr in sorted(R._speaker_map().items()):
        if jp not in canon:
            unknown.add(jp)
        elif canon[jp] != kr:
            bad.append(("화자맵", jp, kr, canon[jp]))
    for scn in R.scene_list(None):
        d = _script(scn)
        for _s, eid, jp, _c, _t in R.iter_candidates((scn,)):
            k = str(eid)
            ent = d.get(k) or {}
            ours = (ent.get("s") or "").strip()
            if not ours or ent.get("sx") or not R.jp_has_header(jp) or R.jp_header_is_fmt(jp):
                continue
            try:
                name = jp[2 : jp.find(R.MC, 2)].decode("cp932")
            except (UnicodeDecodeError, ValueError):
                continue
            if name in canon and canon[name] != ours:
                bad.append((scn, name, ours, canon[name]))
    print(f"  {'✅' if not bad else '❌'} 이름창 표기가 정본과 같다 (어긋남 {len(bad)})")
    if bad and verbose:
        for where, jp, ours, want in bad[:40]:
            print(f"      {where:<9} {jp} — {ours} → {want}")
    if unknown:
        print(f"      ℹ 정본에 없는 화자 {len(unknown)} — 이름이 아닌 것(`%s` 템플릿)이 섞인다")
    return len(bad)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = scan(set(args) if args else None, "--all" in sys.argv)
    n += scan_canon(verbose=True)
    n += scan_runtime_labels(set(args) if args else None, verbose=True)
    sys.exit(1 if n else 0)
