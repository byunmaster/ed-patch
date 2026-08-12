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
  python3 tools/script_dump.py --jeongbal ED1SCN3   # **정발 쪽에서** 본다(누락 찾기)

⚠ **두 방향이 잡는 것이 다르다.** 위(PS1 대본)는 「모든 PS1 블록이 맞는 문안을 갖는가」를
보고, `--jeongbal` 은 「**모든 정발 대사가 제자리를 찾았는가**」를 본다 — 후자가 **누락**을
잡는다. 여관 주인 `jp687`·`jp688` 은 정발에 대응이 있는데 `ours`(자체 번역)를 쓰고 있었다.
"""

import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402
from common import OUT_DIR, REVIEW_DIR, ROOT  # noqa: E402
from patch_sys_ui import _scn_layout  # noqa: E402


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
    out = ["# 재검수 대기 — 인게임 확인 뒤 문안이 바뀐 자리", "",
           "⚠ 정발 파생 문안 포함 — **커밋 금지**.", "",
           "`JP` 와 대조해 뜻이 맞으면 `lock_lines.py --requa-clear <씬> <eid>` 로 뺀다.", ""]
    n = 0
    for scn in sorted(q):
        want = {int(k) for k in q[scn]}
        if not want:
            continue
        out += [f"## {scn} — {len(want)}건", ""]
        with open(os.path.join(OUT_DIR, "scn_jp", f"{scn}.json"), encoding="utf-8") as f:
            raw = {e["entry_id"]: bytes.fromhex(e["raw_hex"])
                   for e in json.load(f)["entries"] if e.get("raw_hex")}
        for _s, eid, _jp, cand, _t in R.iter_candidates((scn,)):
            if eid not in want:
                continue
            n += 1
            why = q[scn].get(str(eid)) or ""
            kr = re.sub(r"\s+", " ", R.render_bytes(cand, ctrl=False)).strip()
            out += [f"### jp{eid}  `{_src(scn, eid)}`",
                    f"- 사유  {why}",
                    f"- JP  {jp_text(raw[eid]) if eid in raw else '—'}",
                    f"- KR  {kr}", ""]
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


def _textmap_used():
    """`textmap/*.json` 이 쓰는 정발 좌표 — **SCN 밖 문안**(EXE·MONDLL)의 사용 표시.

    ⚠ **대조표는 SCN 배정만 봐선 안 된다.** 이 게임의 문안은 최소 넷에 흩어져 있다 —
    `ED1SCN*.BIN`(대사) · `ED.EXE`(시스템·장 끝 해설) · `ED1MAIN.EXE`(UI) · `MONDLL`(전투).
    장 끝 해설(`파렌 왕국은 괴물들에게서 해방되었다`)이 「임자 없음」으로 떴는데 실제로는
    `ED.EXE` 에서 **이미 한글로 나가고 있었다**(2026-08-12, 유저 지적).

    textmap 은 표·엔트리가 아니라 **파일·오프셋**(`SINDLL/C_004.DLL` +0x29E5)으로 참조하므로
    덤프의 `file_offset` 으로 되짚는다.
    """
    import glob

    want = collections.defaultdict(set)  # {표: {오프셋}}
    for path in glob.glob(os.path.join(ROOT, "textmap", "*.json")):
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        for ent in doc.get("entries", []):
            for part in ent.get("parts", []) + ([ent["src"]] if "src" in ent else []):
                f_ = part.get("f") or ""
                if "/" not in f_ or not f_.upper().endswith(".DLL"):
                    continue
                table = "ED1/" + f_.split("/")[-1].removesuffix(".DLL").removesuffix(".dll")
                want[table].add(int(part["o"]))
    out = set()
    for table, offs in want.items():
        path = os.path.join(OUT_DIR, "dos_kr", f"{table}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            ents = json.load(f)["entries"]
        # 엔트리는 오프셋 순 — 각 참조가 어느 엔트리 안에 드는지 찾는다
        marks = sorted((int(e["file_offset"], 16), e["entry_id"]) for e in ents)
        for o in offs:
            prev = None
            for start, eid in marks:
                if start > o:
                    break
                prev = eid
            if prev is not None:
                out.add((table, prev))
    return out


_ITEM_WORDS = None


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


def jeongbal_dump(scn=None):
    """정발 표·엔트리 순서로 뜬다 — 각 엔트리를 **무는 블록**을 표시해 누락을 드러낸다.

    ⚠ **사용 여부는 전 씬을 합쳐 센다.** 정발 표는 씬을 넘나들어서(루디아 성 `C_000` 은
    SCN1 이 주로 쓰는데 SCN3 에서도 한 엔트리를 쓴다) 한 씬만 보면 남의 씬이 쓰는 엔트리가
    전부 「임자 없음」으로 뜬다(첫 실행에서 243건 중 대부분이 그랬다, 2026-08-12).
    """
    import check_page_holes as H

    by_table = {}
    exe_used = _textmap_used()
    for s2, _l, _z in _scn_layout():
        used, _loose = H._used(s2)
        for (table, eid), pages in used.items():
            by_table.setdefault(table, {}).setdefault(eid, []).extend(
                f"{s2[-1]}:{e}" for v in pages.values() for e in v
            )
    out = ["# 정발 쪽에서 본 대조표 — 임자 없는 대사 찾기", "",
           "⚠ 정발 문안 포함 — **커밋 금지**(work/review).", "",
           "`←` 가 그 엔트리를 무는 PS1 블록이다. **`⚠ 임자 없음`** 은 정발에 있는데 화면에",
           "안 나가는 대사다 — 배정이 빠졌거나, PS1 에 그 장면이 없거나 둘 중 하나다.", ""]
    # ⚠ **EXE 사용은 「누락 아님」 표시로만 쓴다.** EXE 전용 표(SCN 이 전혀 안 쓰는 표)까지
    # 목록에 넣으면 대사 배정 대상이 아닌 자리가 쏟아진다 — 넣었더니 192 → 310 이 됐다.
    # 넣는 목적은 **거짓 누락을 지우는 것**이지 범위를 넓히는 게 아니다(2026-08-12 유저 지적).
    for table, eid in exe_used:
        if table in by_table:
            by_table[table].setdefault(eid, []).append("EXE")
    # 쓰이는 엔트리의 본문 — **시점 사본 판정용**. 같은 말이 다른 표에서 이미 나가고 있으면
    # 그 엔트리는 「누락」이 아니라 안 쓰는 사본이다(유저 지적 2026-08-12).
    spoken = set()
    for table, seen in by_table.items():
        for eid in seen:
            pg = H._pages(table, eid)
            if pg:
                spoken.add(_norm(" ".join(pg)))
    miss = 0
    for table in sorted(by_table):
        rows, seen = [], by_table[table]
        n_ent = max(seen) + 6
        for eid in range(n_ent):
            pg = H._pages(table, eid)
            if not pg:
                continue
            body = re.sub(r"\s+", " ", " / ".join(pg).replace("{n}", " ")).strip()
            if not re.search(r"[가-힣]", body):
                continue
            # ⚠ 노이즈를 걷는다 — 첫 실행 773건 중 대부분이 아래였다(2026-08-12):
            # 화자 이름뿐 · 본문 3자 미만 조각 · 상점 공통 · 챕터 카드(`제 5 장`).
            if eid not in seen:
                if H._silent(table, eid, 0) or H._shop(table, eid):
                    continue
                if _chapter_card(body) or _item_name(body):
                    continue
                if _norm(body) in spoken:  # 같은 말이 다른 표에서 나간다 = 시점 사본
                    continue
            if eid in seen:
                who = " ".join(sorted(set(seen[eid]))[:4])
                rows.append(f"- `#{eid}` ← {who}  {body[:70]}")
            else:
                miss += 1
                rows.append(f"- `#{eid}` **⚠ 임자 없음**  {body[:76]}")
        if rows:
            out += [f"## {table}", "", *rows, ""]
    path = os.path.join(REVIEW_DIR, "jeongbal_unused.md")
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"  임자 없는 정발 엔트리 {miss}건 → {path}")
    return miss


def main():
    if "--requa" in sys.argv:
        return requa_table()
    if "--jeongbal" in sys.argv:
        return jeongbal_dump()
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
