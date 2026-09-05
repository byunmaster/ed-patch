"""고유명사 정본이 **자기 안에서 갈리지 않았나** — 사전 없이 기계로 잡히는 것만 본다.

    python3 tools/check_glossary.py       # 갈린 자리가 있으면 종료코드 1

## 🔴 왜 「음차 유도」가 아니라 이건가

「가타카나를 한글로 유도해 현재 표기와 대조」를 만들어 봤는데 **안 통했다**(2026-08-28 실측).
이 이름들은 가타카나로 적힌 **영어**라 모라 단위로 옮기면 `ブラックナイト → 부락쿠나이토` 가
나오고, `ハサミムシ → 집게벌레` 처럼 **뜻으로 옮긴 것**도 섞여 있다. 역방향(한글→로마자)으로
점수를 매겨 봐도 **그날 실제로 고친 셋이 167 중 30·40·62위**로 한복판에 묻혔다 — 신호가 없다.
⇒ 사전 없이 「맞는 표기」를 유도할 길은 없다. **대신 「우리끼리 어긋난 자리」는 정확히 잡힌다.**

## 축 둘

① **같은 원문이 다른 표기로** — 반각 가나·중점·등호를 눕혀 맞춰 본다. 오탐이 없다.
   실측: `バトルスーツ → 배틀 슈트` vs `バトル・スーツ → 배틀 슈츠`.
② **같은 조각이 다른 표기로** — 공통 접두·접미를 모아 한글이 갈리는지 본다.
   실측으로 셋을 잡았다: `인크랍/데스크랩`(クラブ) · `워무드/웜마스터`(ワーム) ·
   `팡크스/팬텀`(ファン) — **셋 다 정발 쪽이 틀린 쪽**이었다.
   ⚠ **한 글자도 안 겹칠 때만** 센다 — 「두 글자 이상」으로 두면 맞는 짝이 줄줄이 걸린다
     (실측 5건 중 4건이 오탐). 그래도 오탐이 남으므로(`ファン` 은 funk/phantom 으로 원래
     갈린다) ②는 **보고만** 한다.

🔴 **①만 실패로 친다.** ②는 사람이 판정할 후보다 — 늘 빨간불인 게이트는 아무도 안 본다.
"""

import collections
import os
import re
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "shared",
    ),
)

import glossary

KATA = re.compile(r"^[\u30a0-\u30ff\u31f0-\u31ff\uff66-\uff9f\u3000 =\uff1d\u30fb\uff65]+$")


def fold(s):
    """같은 이름을 같게 보는 꼴 — 🔴 규칙은 `names.bare` 가 정본이다."""
    from names import bare

    return bare(s)


def same_source_split(t):
    """① 같은 원문인데 표기가 갈린 것."""
    g = collections.defaultdict(list)
    for jp, kr in t.items():
        if kr:
            g[fold(jp)].append((jp, kr))
    return [(k, v) for k, v in sorted(g.items()) if len({kr for _j, kr in v}) > 1]


def _common(ss, tail):
    if not ss:
        return ""
    n = min(len(s) for s in ss)
    out = ""
    for i in range(1, n + 1):
        part = {(s[-i:] if tail else s[:i]) for s in ss}
        if len(part) != 1:
            break
        out = next(iter(part))
    return out


def same_fragment_split(t, minlen=3):
    """② 같은 가타카나 조각인데 한글이 갈린 것 — **후보만** 낸다."""
    mon = {j: k for j, k in t.items() if k and KATA.match(j)}
    out, seen = [], set()
    for tail in (True, False):
        cnt = collections.Counter()
        for j in mon:
            for L in range(minlen, min(len(j), 8) + 1):
                cnt[j[-L:] if tail else j[:L]] += 1
        for frag, n in cnt.items():
            if n < 2:
                continue
            grp = [(j, mon[j]) for j in mon if (j.endswith(frag) if tail else j.startswith(frag))]
            # 🔴 **한 글자도 안 겹칠 때만** 센다. 「두 글자 이상 겹쳐야 한다」로 두면
            #    `웜드/웜마스터`(웜) · `자데인/자바`(자) · `레드랫/워랫`(랫) 처럼 **맞는 짝**이
            #    줄줄이 걸린다(실측 5건 중 4건이 오탐이었다). 실제로 틀린 셋은 전부 겹치는
            #    글자가 **하나도 없었다**(인크랍/데스크랩 · 워무드/웜마스터 · 팡크스/팬텀).
            if len(grp) < 2 or _common([k for _j, k in grp], tail):
                continue
            key = tuple(sorted(j for j, _k in grp))
            if key in seen:
                continue
            seen.add(key)
            out.append(("\uc811\ubbf8" if tail else "\uc811\ub450", frag, grp))
    return sorted(out, key=lambda r: (-len(r[1]), r[1]))


def cross_category_split():
    """③ **범주를 가로질러 갈린 자리** → `[(원문, [(범주, 표기)], 화면에 나가는 표기)]`.

    🔴 ① 은 **범주 안**만 본다(`for cat in categories()`), 그래서 같은 원문이 범주마다 다른
       자리는 **구조적으로 안 보인다.** 그런데 대사의 이름 자리는 범주를 모른 채
       `typeset_scn._names()` 로 **뭉쳐서** 찾으므로 **뒤 범주가 이긴다** — 화면엔 한쪽만 나온다.

    ⚠ **실패로 안 친다** — 갈림이 **의도된 것도 있다.** 정본 `_doc` 이 못 박아 뒀다:
      「같은 JP 가 범주에 따라 다른 것을 가리킨다(`カース` = 아이템 커스 / 몬스터 카스)」.
      유저 확정 2026-09-05: `カース` 는 구분하려고 다르게 쓴 것이고, `ブラムナ`(주문 프람나 /
      몬스터 브람나퀸·브람나독)도 같은 꼴이다.
    ⇒ 그러니 여기서 물을 것은 「갈렸나」가 아니라 **「화면에 나가는 쪽이 맞나」**다.
    """
    from typeset_scn import _names

    per = collections.defaultdict(dict)
    for cat in glossary.categories():
        for jp, kr in glossary.table(cat).items():
            per[jp][cat] = kr
    merged = _names()
    out = []
    for jp, d in per.items():
        if len(set(d.values())) > 1:
            out.append((jp, sorted(d.items()), merged.get(jp)))
    return sorted(out)


def main():
    bad = 0
    for cat in glossary.categories():
        t = glossary.table(cat)
        split = same_source_split(t)
        if split:
            bad += len(split)
            print(
                f"  \u274c [{cat}] \uac19\uc740 \uc6d0\ubb38\uc778\ub370 \ud45c\uae30\uac00 \uac08\ub838\ub2e4 {len(split)}"
            )
            for _k, v in split:
                print("     " + " \u00b7 ".join(f"{j}\u2192{kr}" for j, kr in v))
    if not bad:
        print(
            "  \u2705 \uac19\uc740 \uc6d0\ubb38\uc774 \ub450 \ud45c\uae30\ub85c \uac08\ub9b0 \uc790\ub9ac\ub294 \uc5c6\ub2e4"
        )
    cross = cross_category_split()
    print(f"  ℹ 범주를 가로질러 갈린 자리 {len(cross)} (판정은 사람)")
    for jp, per, win in cross:
        print(f"     {jp} → " + " · ".join(f"{c}:{k}" for c, k in per) + f"   ⇒ 화면 {win!r}")

    frag = same_fragment_split(glossary.table("monster"))
    print(
        f"  \u2139 \uac19\uc740 \uc870\uac01\uc778\ub370 \ud45c\uae30\uac00 \uac08\ub9b0 \ud6c4\ubcf4 {len(frag)} (\ud310\uc815\uc740 \uc0ac\ub78c)"
    )
    for kind, f, grp in frag[:12]:
        print(f"     [{kind} {f}] " + " \u00b7 ".join(f"{j}\u2192{k}" for j, k in grp))
    if bad:
        raise SystemExit(
            f"\uc815\ubcf8\uc774 \uc790\uae30 \uc548\uc5d0\uc11c \uac08\ub838\ub2e4 ({bad}\uac74)"
        )


if __name__ == "__main__":
    main()
