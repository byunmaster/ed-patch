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
import re
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


def scan_inline(scenes=None, verbose=False):
    """**창 한복판에서 바뀌는 화자** — 원문 둘째 이름창과 우리 것을 대조한다.

    위 `scan` 은 **첫 헤더만** 본다(`jp[2:jp.find(MC, 2)]`). 그런데 원문은 한 블록 안에서
    화자를 바꾸기도 한다 — `%cアトラス%c\n…\n%cフローラ%c\n…` 처럼 이름창이 둘이다(실측 16블록).

    🔴 **여기서 하나가 새고 있었다**(2026-09-06). `ED2SCN8:242` 는 우리 문안이 창을 둘로만
    적어(`란도!!{p}란도 씨, 그만하세요.`) 둘째 이름창이 채울 자리로 잡혔고, **본문 첫 어절
    `란도` 가 그 칸에 밀려 들어갔다** — 화면에 「란도 / 씨, 그만하세요.」로 나가 플로라의 말이
    란도 것이 됐다. 창을 하나 더 열어(`{p}플로라{p}`) 고쳤다.
    ⚠ **본문이 인물 이름으로 시작할 때만 난다** — 그래서 나머지 15블록은 멀쩡했다.

    ⚠ **`%c…%c` 를 다 이름창으로 세지 않는다** — 아이템·강조 색 구간이 같은 꼴이다. 원문이
    **`\n%c…%c\n`**(제 줄을 통째로 차지)인 자리만 센다. 이 구조 조건 하나로 실측 16건이
    전부 진짜 이름창이었다(오탐 0).
    ⚠ **화자맵(`_speaker_map`)으로 거르지 않는다** — 그건 정발 유래라 ED2 이름이 없다.
    실제로 그걸로 걸렀더니 `アトラス`·`フローラ` 가 빠져 **문제의 셋이 통째로 안 보였다**
    (2026-09-06, 검출기가 먼저 틀린 네 번째다). 정본(`shared/glossary`)을 쓰고, 표에 없는
    이름은 **버리지 말고 따로 센다.**
    """
    canon = _canon_persons()
    bad, nonl, unknown = [], [], []
    for scn in R.scene_list(scenes):
        for _s, eid, jp, cand, _t in R.iter_candidates((scn,)):
            jt = R.render_bytes(jp.rstrip(b"\x00"), ctrl=True)
            m = re.search(r"\n%c([^%\n]{1,14})%c\n", jt)
            if not m:
                continue
            ot = R.render_bytes(cand.rstrip(b"\x00"), ctrl=True)
            head = ot.find("\n")
            m2 = re.search(r"%c([^%\n]{1,14})%c(\n?)", ot[head + 1 :]) if head >= 0 else None
            if not m2:
                continue
            want = canon.get(m.group(1))
            if want is None:
                unknown.append((scn, eid, m.group(1)))
            elif not _same_person(m2.group(1), want):
                bad.append((scn, eid, m2.group(1), want))
            if not m2.group(2):
                # 이름창 뒤 개행 결손 — 원문엔 있다. 화면에서 본문이 이름줄에 붙는지는
                # **인게임 확인**이 필요해 보고만 한다(2026-09-06 현재 셋).
                nonl.append((scn, eid, m2.group(1)))
    print(f"  {'✅' if not bad else '❌'} 창 중간 화자 전환 이름창 (어긋남 {len(bad)})")
    for scn, eid, ours, want in bad[:20]:
        print(f"      {scn}:{eid}  {ours} → {want}")
    if nonl:
        print(f"      ℹ 이름창 뒤 개행 없음 {len(nonl)}곳 — 원문엔 있다. 인게임 확인 대기")
        if verbose:
            for scn, eid, nm in nonl:
                print(f"         {scn}:{eid} [{nm}]")
    if unknown and verbose:
        print(f"      ℹ 정본에 없는 원문 이름 {len(unknown)} — 대조를 못 했다")
        for scn, eid, nm in unknown:
            print(f"         {scn}:{eid} {nm}")
    return len(bad)


def scan_nl_after_gaps(scenes=None, verbose=False):
    """**본문 창 뒤에 이어지는 창이 붙어 보일 자리** — 키입력개행(qa2-002, 마스터 09-20).

    원본 JP 본문 창의 raw 토큰이 `%c` 경계 직전 `nl` 로 끝나는데, 우리 재조판은 그
    창을 통째로 우리 번역으로 갈아 끼우며 그 nl 을 버린다(`build_from_template` 는
    `chunks[k]` 를 그대로 내보낼 뿐 원문 토큰을 안 본다). **다음 창에 실제 내용
    (`body`/`name`)이 있을 때만** 화면에서 붙어 보인다 — 다음이 `empty`(블록 종단
    `%c%c`)면 뒤에 아무 것도 없어 무해하다.

    ⚠ **"발견되면 무조건 자동 삽입"은 아니다**(2026-09-20 조사) — 전 정본(본문 창
    12,865개)에서 이 조건에 맞는 자리는 43개뿐이고, 나머지 raw-nl 종료 창 1,224개는
    다음이 `empty`/종단이라 안전하다. 그래서 이 함수는 **자동으로 안 고친다** — 43개
    후보 중 `align_overrides.json` 의 `nl_after` 로 이미 덮인 것과 대조해 **빠진
    자리만** 보고한다. 인덱스는 `kind=="body"` 인 창(이름창 인덱스를 주면 조용히
    무동작이다 — 000-a/b 가 그렇게 한 번 틀렸다)."""
    ov = R._load_overrides()
    have = {}
    for scn, entries in ov.items():
        if not isinstance(entries, dict):
            continue
        for eid, e in entries.items():
            if isinstance(e, dict) and "nl_after" in e:
                have.setdefault(scn, set()).update(e["nl_after"])

    missing = []
    for scn in R.scene_list(scenes):
        for _s, eid, jp, _cand, _t in R.iter_candidates((scn,)):
            wins = R.template_windows(R.parse_template(jp))
            for k, (kind, seg) in enumerate(wins):
                if kind != "body":
                    continue
                if not (seg and seg[-1][0] == "nl"):
                    continue
                nxt = wins[k + 1][0] if k + 1 < len(wins) else "END"
                if nxt not in ("body", "name"):
                    continue
                if k in have.get(scn, set()):
                    continue
                missing.append((scn, eid, k, nxt))
    print(f"  {'✅' if not missing else 'ℹ'} 키입력개행 후보(raw nl+다음 창 있음) 미반영 {len(missing)}건")
    if missing and verbose:
        for scn, eid, k, nxt in missing:
            print(f"      {scn}:{eid}  창{k}(body, raw nl 종료) → 다음 창 {nxt}")
    return 0  # 게이트 실패시키지 않는다 — 화면 확인 전 후보 보고일 뿐(위 이름창 개행 축과 같은 성격)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = scan(set(args) if args else None, "--all" in sys.argv)
    n += scan_canon(verbose=True)
    n += scan_runtime_labels(set(args) if args else None, verbose=True)
    n += scan_inline(set(args) if args else None, verbose="-v" in sys.argv)
    n += scan_nl_after_gaps(set(args) if args else None, verbose="-v" in sys.argv)
    sys.exit(1 if n else 0)
