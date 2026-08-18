#!/usr/bin/env python3
"""**QA 대본** — 진행 순서로 JP 원문과 우리 문안을 나란히 뜬다(정발을 켜지 않고 확인).

**왜.** 오배정은 **화면만 봐선 못 잡는다**(유저 지적 2026-08-11) — 그 자체로 자연스럽기
때문이다. 그래서 지금까지는 PS1 과 DOS 정발을 나란히 켜고 일일이 대조해야 했는데, 그건
**두 게임을 같은 지점까지 진행시켜 모든 NPC 에게 말을 거는** 일이라 감당이 안 된다.

우리는 화면에 나갈 바이트를 이미 갖고 있다. **JP 블록 순서 = PS1 대화 순서**이므로, 둘을
나란히 늘어놓으면 정발을 켜지 않고도 「이 자리에 이 말이 맞는가」를 읽어서 판정할 수 있다.
어제 오배정 열넷을 인게임 없이 그렇게 가려냈다.

⚠ **산출물은 `work/review/`(gitignore)로만 나간다** — 정발에서 파생한 문안이 들어가므로
리포에 남으면 저작권 규율에 어긋난다(루트 `CLAUDE.md`).

  python3 tools/script_dump.py ED1SCN3              # 씬 대본
  python3 tools/script_dump.py ED1SCN3 --from 600 --to 700
  python3 tools/script_dump.py --requa              # 재검수 대기분만(전/후 대조)

⚠ **`--jeongbal`(정발 대조표)은 걷어냈다**(2026-08-12). 「모든 정발 대사가 제자리를
찾았는가」를 보던 축인데, 배정을 그만두고 **번역 정본**(`script/`)으로 옮기면서 물음 자체가
없어졌다 — 정발에 대응이 없으면 이제 우리가 쓴다. 마지막까지 그 축으로 7건을 회수했고
경위는 [devlog](../docs/devlog.md) 2026-08-12.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import OUT_DIR, REVIEW_DIR, ROOT
from patch_sys_ui import _scn_layout


def jp_text(b):
    """JP raw → 사람이 읽는 문자열(`%c` 는 창 경계로 `|`)."""
    out, i = [], 0
    while i < len(b):
        c = b[i]
        if c == 0x25 and i + 1 < len(b) and b[i + 1] in b"csd":
            out.append("|" if b[i + 1] == 0x63 else f"%{chr(b[i + 1])}")
            i += 2
        elif c < 0x20:
            out.append(" ")
            i += 1
        elif c >= 0x81:
            out.append(b[i : i + 2].decode("cp932", "replace"))
            i += 2
        else:
            out.append(chr(c))
            i += 1
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _src(scn, eid, _cache={}):  # noqa: B006
    """그 블록이 무는 정발 좌표(사람이 확인할 수 있게)."""
    if scn not in _cache:
        with open(os.path.join(ROOT, "align_map.json"), encoding="utf-8") as f:
            am = json.load(f).get(scn, {})
        with open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8") as f:
            ov = json.load(f).get(scn, {})
        _cache[scn] = (am, ov)
    am, ov = _cache[scn]
    o, a = ov.get(str(eid)) or {}, am.get(str(eid)) or {}
    if "ours" in o:
        return "ours(자체 번역)"
    t = o.get("table") or a.get("table")
    if not t:
        return "—"
    return f"{t} {o.get('chain') or o.get('entry_id') or a.get('entry_id')}"


def dump(scn, lo=None, hi=None):
    with open(os.path.join(OUT_DIR, "scn_jp", f"{scn}.json"), encoding="utf-8") as f:
        raw = {
            e["entry_id"]: bytes.fromhex(e["raw_hex"])
            for e in json.load(f)["entries"]
            if e.get("raw_hex")
        }
    out = [
        f"# {scn} 대본 — JP 원문 ↔ 우리 문안",
        "",
        "⚠ 정발에서 파생한 문안 포함 — **커밋 금지**(work/review).",
        "",
        "`JP` 가 그 자리에서 실제로 나오는 일본어다. **뜻이 맞는지**를 읽어서 본다 —",
        "어색함이 아니라 **다른 대사를 물었는가**가 이 대본으로 잡는 것이다.",
        "",
    ]
    n = 0
    for _s, eid, _jp, cand, _t in R.iter_candidates((scn,)):
        if (lo and eid < lo) or (hi and eid > hi):
            continue
        n += 1
        kr = re.sub(r"\s+", " ", R.render_bytes(cand, ctrl=False)).strip()
        out += [
            f"### jp{eid}  `{_src(scn, eid)}`",
            f"- JP  {jp_text(raw[eid])}",
            f"- KR  {kr}",
            "",
        ]
    path = os.path.join(REVIEW_DIR, f"script_{scn}.md")
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"  {scn}: {n}블록 → {path}")
    return n


def requa_table():
    """재검수 대기분의 **전/후 문안**을 나란히 — 게임을 켜지 않고 판정한다.

    「전」은 락이 걸린 시점의 문안이라 지금 코드로는 못 만든다(그때의 배정이 필요하다).
    그래서 **지금 문안 + JP 원문 + 사유**만 낸다 — 뜻이 맞는지는 JP 로 판정되고,
    사유(`--why` 로 적은 것)가 무엇을 왜 바꿨는지 알려 준다.
    """
    with open(os.path.join(ROOT, "locked_lines.json"), encoding="utf-8") as f:
        q = json.load(f).get("_requa", {})
    out = [
        "# 재검수 대기 — 인게임 확인 뒤 문안이 바뀐 자리",
        "",
        "⚠ 정발 파생 문안 포함 — **커밋 금지**.",
        "",
        "`JP` 와 대조해 뜻이 맞으면 `lock_lines.py --requa-clear <씬> <eid>` 로 뺀다.",
        "",
    ]
    n = 0
    for scn in sorted(q):
        want = {int(k) for k in q[scn]}
        if not want:
            continue
        out += [f"## {scn} — {len(want)}건", ""]
        with open(os.path.join(OUT_DIR, "scn_jp", f"{scn}.json"), encoding="utf-8") as f:
            raw = {
                e["entry_id"]: bytes.fromhex(e["raw_hex"])
                for e in json.load(f)["entries"]
                if e.get("raw_hex")
            }
        for _s, eid, _jp, cand, _t in R.iter_candidates((scn,)):
            if eid not in want:
                continue
            n += 1
            why = q[scn].get(str(eid)) or ""
            kr = re.sub(r"\s+", " ", R.render_bytes(cand, ctrl=False)).strip()
            out += [
                f"### jp{eid}  `{_src(scn, eid)}`",
                f"- 사유  {why}",
                f"- JP  {jp_text(raw[eid]) if eid in raw else '—'}",
                f"- KR  {kr}",
                "",
            ]
    path = os.path.join(REVIEW_DIR, "requa.md")
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"  재검수 대기 {n}건 → {path}")


_CARD_WORDS = None


def _norm(t):
    """시점 사본 대조용 정규화 — 표기·제어·공백 차이를 지운다."""
    t = re.sub(r"\{/?spk\}|\{n\}|\{p\}|\{end\}|\\x[0-9A-Fa-f]{2}|`[0-9]", " ", t)
    return re.sub(r"[^가-힣0-9]", "", t)


def _chapter_card(body):
    """챕터 카드 계열인가 — **`patch_gfx_cards` 가 TIM 그래픽으로 처리**하는 자리다.

    장 제목(`여행의 시작`)·장 끝 표시(`… 끝`)는 텍스트 배정 대상이 아니라 그림이다.
    제목 목록은 그 도구가 정본으로 갖고 있으니 재사용한다(두 벌이면 어긋난다).
    ⚠ **장 끝 해설**(`파렌 왕국은 괴물들에게서 해방되었다`)도 여기 걸린다. 그건 SCN 이 아니라
    **`ED.EXE` 안에** 있고(0xB9E0~) `patch_sys_ui` 가 이미 한글로 바꿔 놨다 — 화면에는 정상
    출력된다. ⚠ 처음엔 SCN 파일만 뒤지고 「PS1 에 없는 연출」이라 단정했다가 유저가 바로잡았다.
    **「찾아봤는데 없다」는 매처의 한계일 뿐**이라는 그 부류를 또 밟은 것이다(2026-08-12).
    """
    global _CARD_WORDS
    if _CARD_WORDS is None:
        from patch_gfx_cards import CARDS

        _CARD_WORDS = {t for _a, _c, t in CARDS} | {c for _a, c, _t in CARDS}
    b = re.sub(r"[^가-힣0-9]", "", body)
    return any(re.sub(r"[^가-힣0-9]", "", w) in b for w in _CARD_WORDS if len(w) > 3)


def _item_name(body):
    """아이템·몬스터 이름인가 — **`patch_items` 관할**이라 대사 배정 대상이 아니다.

    `천둥말뚝B` · `갑옷거미A` 처럼 개체 접미가 붙어 목록에 쏟아진다(2026-08-12).
    """
    global _ITEM_WORDS
    if _ITEM_WORDS is None:
        from patch_items import MONSTERS, NAMES

        _ITEM_WORDS = {re.sub(r"\s", "", v) for v in list(NAMES.values()) + list(MONSTERS.values())}
    b = re.sub(r"[\sA-Za-z0-9]", "", body)
    return bool(b) and b in _ITEM_WORDS



def main():
    if "--requa" in sys.argv:
        return requa_table()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lo = hi = None
    for k, v in (("--from", "lo"), ("--to", "hi")):
        if k in sys.argv:
            val = int(sys.argv[sys.argv.index(k) + 1])
            lo, hi = (val, hi) if v == "lo" else (lo, val)
    scenes = args or [s for s, _l, _z in _scn_layout()]
    for scn in scenes:
        dump(scn, lo, hi)


if __name__ == "__main__":
    main()
