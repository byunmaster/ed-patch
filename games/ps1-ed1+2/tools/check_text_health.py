#!/usr/bin/env python3
"""정발 대조 없이 잡을 수 있는 결함을 전수로 훑는다 — 체크리스트가 못 보던 종류들.

**왜(유저 지적 2026-08-06).** "playthrough 가 못 잡는 게 많아서 의미가 없는 거 같네.
결국은 일일이 정발 대조 해야 되나." 그럴 필요 없다 — 그날 유저가 찾아낸 것들을 분류해 보니
**한 종류(시점 사본)만 체크리스트가 보고 있었고, 나머지는 전부 기계로 잡히는 것**이었다.

  ① **엔트리에 걸친 문장** — `T_042#10` 이 `사시는게 ` 로 끊기고 다음이 `입니다.` 로 시작한다.
     ⚠ 처음엔 "추출이 중간을 흘렸다"로 봤고 실제로 그랬다(`#11` `좋{n}을 것 ` 이 gap 으로
     떨어져 있었다 — `extract_dos_kr.gap_is_text` 로 회수, 2026-08-06). 회수 뒤에도 남는 건
     **정발이 한 문장을 엔트리 둘에 진짜로 나눠 둔** 자리다. 결함이 아니라 `chain` 의
     `+`(이어붙임) 문법을 써야 하는 자리라는 신호다.
  ② 인접 블록 중복 — `jp740`·`jp741` 이 같은 문장을 렌더(끝인사 블록이 본문을 통째로 뭄).
  ③ 화자 전환 마커(`\\x09\\x02`) 가 든 엔트리 — 2인 대사인데 한 창에 붙어 나오는 후보.
  ④ 창 꼬리 붙음 — 렌더 끝에 다른 대사의 인사가 이어 붙은 자리.

  python3 tools/check_text_health.py            # 요약
  python3 tools/check_text_health.py --report   # work/review/text_health.md
"""

import collections
import glob
import os
import re
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
import segment_copy as S
from align_jp_kr import load_jp_scene
from common import OUT_DIR, REVIEW_DIR

# 종결로 인정하는 꼬리 — 이걸로 안 끝나면 엔트리가 잘렸을 수 있다
_END = re.compile(r"(\{end\}|\{p\}|[.!?…」』]\s*$|\\x[0-9A-Fa-f]{2}\s*$)")
# 조사·어미로 시작 = 앞 엔트리의 이어짐(결손의 반대쪽 증거)
_CONT = re.compile(r"^(입니다|습니다|니다|을 것|것입니다|는데|지만|하고|라고|고요)")
# JP 본문 비교용 정규화 — 공백·구두점만 다른 건 같은 대사다
_JPN = re.compile(r"[\s、。，．・…！？!?,.\u3000]+")
# 선두 화자 플레이트 — **이것도 JP 차이가 아니다.** PS1 은 같은 대사를 「이어지는 말(플레이트
# 없음)」과 「말 걸었을 때(플레이트 있음)」 두 벌로 두는데, 플레이트를 안 걷으면 그 정상 쌍이
# 전부 중복으로 걸린다(SCN3 jp282·283 실측 2026-08-11).
_PLATE = re.compile(r"^\{c\}[^{]*\{c\}(\{n\})?")
# ⚠ **JP 가 갈리는데 정발이 안 갈라 둔 자리**는 영구 잔여다 — 고치려면 문안을 새로 써야 해서
# (정발 그대로 원칙에 어긋난다) 판정을 여기 못 박고 목록에서 뺀다. 안 그러면 라운드마다 같은
# 걸 다시 판단하게 된다(`lock_lines --settled` 와 같은 취지).
SETTLED_DUPS = {
    # `…はずですが · · ·`(말끝 흐림) / `…はずです。` — 정발 `T_125#27` 은 한 벌뿐이다
    ("ED1SCN2", 473, 475),
}


def entry_gaps(game="ED1"):
    """[(테이블, 앞 엔트리, 뒤 엔트리)] — 정발 추출이 중간을 흘린 자리."""
    out = []
    for f in sorted(glob.glob(os.path.join(OUT_DIR, "dos_kr", game, "*.json"))):
        t = os.path.basename(f)[:-5]
        if t.startswith("_"):
            continue
        E = S.entries(f"{game}/{t}")
        ks = sorted(E)
        for a, b in zip(ks, ks[1:], strict=False):
            ra, rb = E[a][2].rstrip(), E[b][2].lstrip()
            if not ra or not rb:
                continue
            if not _END.search(ra) and _CONT.match(rb):
                out.append((f"{game}/{t}", a, b, ra[-40:], rb[:40]))
    return out


def adjacent_dups(game="ED1"):
    """[(씬, 앞, 뒤, 문장)] — 이웃 블록이 같은 문장을 렌더(JP 는 다른데)."""
    out = []
    for scn in range(1, 7):
        name = f"{game}SCN{scn}"
        tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
        jp = {b["id"]: b for b in load_jp_scene(game, scn)}
        seen = collections.defaultdict(list)
        for e, t in tr.items():
            try:
                body = " ".join(x[1] for x in t[1])
            except (TypeError, IndexError):
                continue
            if len(body) >= 10:
                seen[body].append(e)
        for body, es in seen.items():
            if len(es) < 2:
                continue
            # ⚠ **본문만, 그것도 정규화해서 본다.** 화자까지 묶으면(`(speaker, body)`) 같은
            # 대사를 `男`·`女`·`老人` 이 돌아가며 하는 정상 블록이 전부 걸리고(48건 중 30건),
            # 공백·구두점을 안 걷으면 `あんな、親不孝者` vs `あんな 親不孝者` 처럼 **쉼표
            # 하나 다른 쌍둥이**가 걸린다(2026-08-06). 이름표도 쉼표도 **JP 가 다른 게 아니다.**
            if len({_JPN.sub("", _PLATE.sub("", jp.get(x, {}).get("body") or "")) for x in es}) < 2:
                continue  # JP 본문이 같으면 쌍둥이 — 정상
            es = sorted(es)
            for a, b in zip(es, es[1:], strict=False):
                if b - a <= 2 and (name, a, b) not in SETTLED_DUPS:
                    out.append((name, a, b, body[:60]))
    return out


def two_speaker(game="ED1"):
    """[(씬, eid, 정발좌표, 렌더)] — **정발이 화자를 바꾼 자리**(`\\x09\\x02`)를 한 창에 붙인 것.

    ⚠ 렌더 문장 모양으로 찾으려다 315건이 걸렸다(전부 오탐). 판정은 **정발 원문의 마커**로
    해야 정확하다 — `\\x09` 는 이름 주입, `\\x02` 는 화자 전환이다(T_041#38 실측).

    ⚠ **"붙어 나오는가"의 판정자는 이게 아니다**(2026-08-06). 이건 정발 쪽 마커 + 창 1개라는
    **번역 쪽 휴리스틱**이라 골격이 개행을 잃은 부류(`jp245`)를 못 보고, 반대로 정상 블록도
    센다. 원인 표식은 **원본 대비 `\\x0a%c` 결손**이고 그건 `tools/check_window_nl.py` 다
    (전수 13건, 그중 11건이 `nl_after` 로 기계 복원). 이 항목은 **2인 대사 자리 목록**으로만 쓴다.
    """
    import json

    from align_map import scene_map
    from common import ROOT

    out = []
    for scn in range(1, 7):
        name = f"{game}SCN{scn}"
        tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
        base = scene_map(name)
        ov = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8")).get(
            name, {}
        )
        for e, t in tr.items():
            o = ov.get(str(e)) or {}
            tbl = o.get("table") or (base.get(e) or {}).get("table")
            ent = o.get("entry_id")
            if ent is None:
                ent = (base.get(e) or {}).get("entry_id")
            if not tbl or ent is None:
                continue
            raw = S.entries(tbl).get(ent, ("", "", ""))[2]
            if "\\x09\\x02" not in raw:
                continue
            try:
                pages = [x[1] for x in t[1]]
            except (TypeError, IndexError):
                continue
            if len(pages) == 1 and len(pages[0]) > 12:  # 두 화자가 한 창에 붙었다
                out.append((name, e, f"{tbl.split('/')[-1]}#{ent}", pages[0][:60]))
    return out


def main():
    gaps, dups, two = entry_gaps(), adjacent_dups(), two_speaker()
    print(f"① 엔트리에 걸친 문장 {len(gaps)}건 (`+` 이어붙임 체인 대상)")
    print(f"② 인접 블록 중복        {len(dups)}건")
    print(f"③ 2인 대사 한 창 후보   {len(two)}건")
    if "--report" not in sys.argv:
        for t, a, b, ra, rb in gaps[:8]:
            print(f"  ① {t}#{a}→#{b}   …{ra}  ||  {rb}…")
        return 0
    os.makedirs(REVIEW_DIR, exist_ok=True)
    p = os.path.join(REVIEW_DIR, "text_health.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("# 정발 대조 없이 잡히는 결함\n")
        f.write(f"\n## ① 엔트리에 걸친 문장 {len(gaps)}건\n")
        f.write("\n앞 엔트리가 종결 없이 끊기고 뒤가 어미로 시작한다 — `chain` 에 `+` 로 잇는다.\n")
        for t, a, b, ra, rb in gaps:
            f.write(f"\n- `{t}#{a}` → `#{b}`\n  - …{ra}\n  - {rb}…\n")
        f.write(f"\n## ② 인접 블록 중복 {len(dups)}건\n")
        for nm, a, b, body in dups:
            f.write(f"\n- {nm} jp{a}·jp{b}: {body}\n")
        f.write(f"\n## ③ 2인 대사 한 창 후보 {len(two)}건\n")
        for nm, e, coord, pg in two:
            f.write(f"\n- {nm} jp{e} ({coord}): {pg}\n")
    print(f"  → {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
