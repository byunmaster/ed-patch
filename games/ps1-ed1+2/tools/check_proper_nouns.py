#!/usr/bin/env python3
"""**고유명사가 정본 표기대로 들어갔는가** — 원문에 있는 이름을 우리 문안에서 찾는다.

⚠ **정본의 출처가 2026-08-18 에 바뀌었다.** 그전엔 「고유명사는 **정발 표기**를 따른다」가
방침이었고(유저 확정 2026-08-12) 이 도구의 이름표도 그랬다. 자체 번역으로 전환한 뒤
정본은 **우리가 정한 표기**다(`shared/glossary/eiyuu.json` + 아래 네 곳). **검사 내용은
그대로다** — 「정본과 우리 문안이 맞나」를 보는 것이고, 바뀐 건 정본이 누구 것이냐뿐이다.

**왜.** 정본이 **네 군데로 흩어져 있다** —
아이템·마법은 `patch_items.NAMES`, 몬스터는 `patch_items.MONSTERS`, 인물은
`align_jp_kr.SPEAKER_DICT`, 지명은 `patch_sys_ui.PLACES`. 대사 문안은 그 어느 것도
안 지나므로 **손으로 쓰다 얼마든지 어긋난다**(`은의 피리` 를 `은피리` 로 붙여 쓴 자리가
여섯 곳 있었다, 실측 2026-08-12).

`check_spellings` 는 **우리가 이미 아는 갈림**을 쌍으로 세는 도구다. 이건 반대로
**원문을 축으로 전수**한다 — 원문에 이름이 있는데 문안에 대응 표기가 없으면 보고한다.

⚠ **전부 오류는 아니다.** 세 부류가 섞여 나온다:

- **진짜 누락** — 이름이 통째로 빠졌거나 다른 표기로 나갔다. 고친다.
- **대명사 치환** — 저본이 `ジェルマン` 을 `그분` 으로 뭉갠 자리. 방침상 이름을 되살리는
  게 맞지만, 문맥이 이미 그 사람을 가리키면 그대로 두는 게 자연스럽다. **사람이 판정한다.**
- **부분 인용** — 원문이 `クルスの村` 인데 문안이 `크루즈` 로만 받는 자리. 정상이다.
  그래서 지명은 **접미(마을·항구·성…)를 떼고** 핵심어로만 본다.

⚠ **게이트가 아니다.** 판정이 필요한 후보를 보여 줄 뿐이다.

  python3 tools/check_proper_nouns.py            # 전 씬 요약
  python3 tools/check_proper_nouns.py ED1SCN3    # 한 씬, 자리마다
  python3 tools/check_proper_nouns.py --all      # 자리마다(전 씬)
"""

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import align_jp_kr
import patch_items
import patch_sys_ui
import reinsert_kr_pilot as R
from check_align_fit import jp_text

# 지명 접미 — 원문/문안 양쪽에서 떼고 핵심어만 본다(`クルスの村` ↔ `크루즈`).
#
# ⚠ **`PLACES` 는 플레이트 표기라 대사와 다르다.** 화면 폭이 좁아 붙여 쓰고(`크루즈마을`),
# 보통명사 합성 지명은 아예 다르게 옮겼다 — `風よけの穴` 이 플레이트로는 `방풍의동굴` 인데
# 정발 **대사**(`F_000` 지명 목록)에서는 `바람막이 구멍` 이다. `狼の口`(플레이트 `늑대입`,
# 대사 `늑대의 입`)도 같다. 그래서 지명은 **가타카나 고유명 부분만** 본다 — 접미와
# 보통명사 합성은 대사 쪽 관용을 따르는 게 맞고, 이 도구가 판정할 일이 아니다.
JP_SUFFIX = re.compile(r"(の(村|町|港|城|国|里|塔|山|洞窟|鉱山|王国|公国|共和国))$")
KR_SUFFIX = re.compile(r"\s*(마을|거리|항구|항|성|나라|왕국|공국|공화국|탑|산|동굴|광산)$")
KATAKANA = re.compile(r"[ァ-ヴー]{2,}")

# ⚠ 이 이름들은 **짧아서 딴 낱말에 먹힌다** — 원문에 이 낱말이 함께 있으면 건너뛴다.
# 실측(2026-08-12): 마법 `ホー`(호) 가 인물 `ホール`(홀) 에, `ルクス`(룩스) 가 지명
# `コルクス`(콜크스) 에 먹혀 스물다섯 곳이 오탐으로 떴다.
SKIP_IF = {
    "ロー": ("ローブ", "ローズ"),
    "ホー": ("ホール", "オークホーン"),
    "ルクス": ("コルクス",),
}

# 화자 사전에는 이름이 아닌 역할어가 섞여 있다(`兵士`·`侍女`). 그건 이 검사 대상이 아니다.
NOT_A_NAME = re.compile(r"^[一-鿿]+$")


def _canon_pairs():
    """(일문, 정발 한글, 갈래) — 네 정본을 한 표로 모은다."""
    out = []
    for jp, kr in patch_items.NAMES.items():
        out.append((jp, kr, "아이템·마법"))
    for jp, kr in patch_items.MONSTERS.items():
        out.append((jp, kr, "몬스터"))
    # 인물·지명은 **가타카나 고유명이 든 것만** — `兵士`·`おじいさん`·`王家の墓` 같은
    # 역할어·보통명사 합성은 이름이 아니라 대사 관용을 따르는 층이다.
    for jp, kr in align_jp_kr.SPEAKER_DICT.items():
        if KATAKANA.search(jp):
            out.append((jp, kr, "인물"))
    for jp, kr in patch_sys_ui.PLACES:
        stem_jp, stem_kr = JP_SUFFIX.sub("", jp), KR_SUFFIX.sub("", kr)
        if KATAKANA.fullmatch(stem_jp):
            out.append((stem_jp, stem_kr, "지명"))
    # 긴 이름부터 봐야 `鉄のつるぎ` 가 `つるぎ` 에 먹히지 않는다.
    seen = set()
    rows = []
    for jp, kr, kind in sorted(out, key=lambda r: -len(r[0])):
        if not jp or not kr or (jp, kr) in seen:
            continue
        seen.add((jp, kr))
        rows.append((jp, kr, kind))
    return rows


_KATA = re.compile(r"[ァ-ヶーヽヾ]")


def _name_in(hay, needle):
    """원문에 이름이 **낱말로** 있는가 — 앞뒤가 가타카나면 다른 낱말의 일부다.

    ⚠ 실측: `バザール`(바자르, 시장) 안의 `ザール` 이 몬스터 「잘」로 잡혔다(SCN5 jp339·340,
    2026-08-13). 같은 부류를 `check_terms` 에서도 물었다(아이템 `배틀 슈츠` 가 금지어 「틀」
    에 걸린 것) — **한 자리를 `SKIP_IF` 로 막지 않고 경계를 규칙으로 둔다.**
    """
    i = hay.find(needle)
    while i >= 0:
        before = hay[i - 1] if i else ""
        after = hay[i + len(needle)] if i + len(needle) < len(hay) else ""
        if not (_KATA.match(before) or _KATA.match(after)):
            return True
        i = hay.find(needle, i + 1)
    return False


def scan(scenes=None, verbose=False):
    pairs = _canon_pairs()
    tot = 0
    kinds = collections.Counter()
    for scn in R.scene_list(scenes):
        if scenes and scn not in scenes:
            continue
        # ⚠ **블록 경계가 원문과 우리가 다르게 갈린다.** 원문 `…アクダムの手から` / `解放…`
        # 을 우리는 `…생각이옵니다.` / `이제는 루디아를 아크담의…` 로 나눴다 — 앞 블록만
        # 보면 이름이 없다(SCN1 `jp333` 실측). 그래서 **다음 블록 문안까지 합쳐** 찾는다.
        # ⚠ **화자 이름은 본문에 없는 게 정상이다** — 이름창으로 따로 나간다. 본문만 보면
        # `{c}情報屋 トミー{c}` 블록이 전부 「이름이 없다」로 뜬다(ED1+ED2 14곳 실측
        # 2026-08-17). 화자 문자열을 같이 본다.
        blocks = []
        for spk, eid, jp, cand, _t in R.iter_candidates((scn,)):
            kr = R.render_bytes(cand, ctrl=False)
            body = kr.replace("\n", " ") if kr else ""
            blocks.append((eid, jp, jp_text(jp), body, str(spk or "")))

        hits = []
        for i, (eid, jp, j, flat, spk) in enumerate(blocks):
            # ⚠ **인자 블록은 보지 않는다.** 이름이 `%s` 로 주입되는 자리라
            # (`ワプの翼 を渡しました`) 문안에 이름이 없는 게 정상이다.
            if b"%s" in jp or b"%d" in jp or not flat:
                continue
            kr = flat
            flat = " ".join([flat, spk] + [b[3] for b in blocks[i + 1 : i + 3]])
            for name, ours, kind in pairs:
                if not _name_in(j, name) or ours in flat:
                    continue
                if any(x in j for x in SKIP_IF.get(name, ())):
                    continue
                hits.append((eid, name, ours, kind, kr))
                kinds[kind] += 1
                break  # 한 블록에 여러 개면 첫 하나만 — 고치면 다시 뜬다
        tot += len(hits)
        print(f"  {'✅' if not hits else '⚠'} {scn}: 정발 표기가 안 보이는 곳 {len(hits)}")
        if verbose:
            for eid, name, ours, kind, kr in hits:
                print(f"      jp{eid} [{kind}] 원문 [{name}] → 문안에 [{ours}] 없음")
                print(f"           {kr.replace(chr(10), ' ')[:64]}")
    per = " · ".join(f"{k} {n}" for k, n in kinds.most_common())
    print(
        f"\n{'✅ 전부 정발 표기대로다' if not tot else f'⚠ 후보 {tot}곳 ({per})'}"
        "\n  ⚠ 게이트가 아니다 — 대명사 치환·부분 인용이 섞여 나오니 사람이 판정한다."
    )
    return tot


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    scan(set(args) if args else None, verbose=bool(args) or "--all" in sys.argv)
