#!/usr/bin/env python3
"""**창 앞 개행**을 원본과 대조한다 — 2인 대사가 한 줄에 붙는 부류의 판정자.

**왜(2026-08-06).** `jp701`(세리오스/로우)이 `.....알았어. 로우` 로 붙어 나왔다. 다섯 번을
헛짚은 이유는 **어느 게이트도 개행을 안 보기 때문**이다 — `restore_tail_nl` 도크스트링이
이미 적어 뒀다: "구조 계약은 `%c`/`%s`/`%d` 개수만 보고 **0x0A는 안 본다**". 게다가 그
함수는 **블록 꼬리 하나만** 복원한다. jp701 이 잃은 건 중간 창의 꼬리였다.

판정은 간단하다 — 원본이 `\\x0a%c`(개행 뒤 창 시작)를 쓴 자리를 우리가 몇 개나 재현했는가.
원본보다 적으면 **그만큼 창이 앞 줄에 붙는다.** `check_text_health ③`(번역 쪽 휴리스틱)은
`jp245` 처럼 골격이 개행을 잃은 건 못 봤다 — 이쪽이 원인 표식이라 전수로 정확하다.

고치는 장치는 `nl_after`(→ `NL_WINS` → `build_from_template(nl=…)`). `--suggest` 는
템플릿 창을 훑어 **어느 창 뒤에 넣어야 하는지**를 찾아 준다(창 인덱스는 템플릿 토큰
기준이라 눈으로 세면 어긋난다).

  python3 tools/check_window_nl.py             # 결손 블록 목록
  python3 tools/check_window_nl.py --suggest   # nl_after 창 인덱스까지
  python3 tools/check_window_nl.py --apply     # align_overrides.json 에 nl_after 기록
"""

import json
import os
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from align_map import scene_map
from common import OUT_DIR, ROOT

NL_MC = b"\x0a" + R.MC  # 개행 뒤 창 시작


def _count_nl_mc(b):
    """`개행 → 창 시작` 자리 수 — **사이에 색 바이트가 끼어도 센다.**

    ⚠ `%c` 앞에 색 복귀 바이트를 박는 자리가 있다(`COLOR_ITEM`·`COLOR_LEAD` 등). 그러면
    `\x0a%c` 가 `\x0a\x01%c` 가 되어 **개행이 멀쩡한데 결손으로 오탐**한다(실측
    `ED1SCN2:235`, 2026-09-01 — 아이템 색을 넓히자 드러났다).
    """
    n = 0
    for i in range(len(b) - 1):
        if b[i] != 0x0A:
            continue
        j = i + 1
        while j < len(b) and b[j] in (1, 2, 3, 4, 5, 6, 7):  # 색 바이트는 건너뛴다
            j += 1
        if b[j : j + 2] == R.MC:
            n += 1
    return n


def raws_of(name):
    """{eid: 원본 바이트} — `load_jp_scene` 은 디코드 텍스트만 주므로 추출본에서 직접 읽는다."""
    p = os.path.join(OUT_DIR, "scn_jp", f"{name}.json")
    doc = json.load(open(p, encoding="utf-8"))
    return {e["entry_id"]: bytes.fromhex(e["raw_hex"]) for e in doc["entries"] if e.get("raw_hex")}


# 🔴 **편마다 씬 수가 다르다** — ED1 여섯 · ED2 열셋. 여기를 `range(1, 7)` 로 두면
#    **ED2 가 통째로 분모 밖**이 된다(2026-09-12 실측: 마스터가 화면에서 찾은 창 앞 개행
#    결손 넷이 전부 ED2 였고 이 검사기는 초록이었다). **배선은 돼 있는데 분모가 반쪽**인
#    꼴이라 게이트가 거짓 초록을 냈다.
SCN_COUNT = {"ED1": 6, "ED2": 13}


def scan(game="ED1", scenes=None):
    """[(씬, eid, 원본 `\\n%c` 수, 우리 수, 렌더 미리보기)] — 창 앞 개행이 모자란 블록."""
    out = []
    for scn in scenes or range(1, SCN_COUNT[game] + 1):
        name = f"{game}SCN{scn}"
        tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
        raws = raws_of(name)
        for eid, raw in raws.items():
            t = tr.get(eid)
            if not t:
                continue
            try:
                cand, reason = R.build_candidate(raw, t, eid)
            except Exception:
                continue
            if cand is None:
                continue  # 제외 블록은 JP 가 그대로 나가므로 결손이 아니다
            # ⚠ `drop_lead_nl` 은 **사람이 QA 로 확정한 편차**다 — 결손이 아니라 결정이다.
            # (jp912 게일 합류: 원판이 이 블록만 `\n` 으로 시작해 혼자 한 줄 내려 떠서,
            #  동료 합류 5블록 중 다수 4/5 에 맞췄다 — 유저 QA 2026-08-08.)
            # 빼지 않으면 라운드마다 같은 블록이 목록에 다시 뜬다(`--settled` 와 같은 교훈).
            if eid in R.LEAD_NL_DROP:
                continue
            # 🔴 **꽉 찬 줄(29열) 뒤의 개행은 우리가 일부러 뗀 것이다** — 결손이 아니다.
            #    그 자리는 엔진이 이미 자동 개행하므로 우리 개행을 더 얹으면 **빈 줄**이 된다
            #    (유저 QA 2026-08-31 아토스 국왕). `drop_frame_full_nl` 이 뗀다.
            #    ⚠ 이 예외가 없으면 **라운드마다 오간다** — 08-29 에 이 검사기를 보고 셋에
            #    개행을 넣었는데(`창 앞 개행 셋`), 09-01 에 빈 줄 때문에 도로 뺐다. 같은 셋이다.
            if R._tail_fills_frame(cand):
                continue
            want, got = _count_nl_mc(raw), _count_nl_mc(cand)
            if got < want:
                try:
                    prev = " / ".join(x[1] for x in t[1])[:56]
                except (TypeError, IndexError):
                    prev = ""
                out.append((name, eid, want, got, prev))
    return out


def suggest(name, eid):
    """`nl_after` 에 넣을 **템플릿 창 인덱스**들. 원본에서 `\\n%c` 로 시작하는 창의 앞 창.

    ⚠ 창 인덱스는 템플릿 토큰 기준이라 **눈으로 세면 어긋난다** — 원본 바이트를 `%c` 로
    갈라 세는 이 방식이 정본이다."""
    raw = raws_of(name).get(eid)
    if raw is None:
        return []
    # `%c` 로 자르면 조각 k 가 창 k 의 내용이다. 조각이 개행으로 끝나면
    # **다음 창이 새 줄에서 시작**한다는 뜻 → 그 창 인덱스를 nl_after 에 넣는다.
    segs = raw.rstrip(b"\x00").split(R.MC)
    return [k for k, s in enumerate(segs[:-1]) if s.endswith(b"\x0a")]


def verify(name, eid, wins):
    """제안을 인메모리로 적용해 본다 → (복원됐나, 본문이 그대로인가).

    ⚠ **적용 전에 반드시 통과시킨다.** `nl_after` 는 `build_from_template`(골격 채우기)
    에서만 먹으므로, 용량 초과로 `build_block` 폴백을 탄 블록에는 **아무 일도 안 일어난다**
    (jp533·jp407 실측). 검산 없이 적으면 정본에 무효 항목만 쌓인다."""
    raw = raws_of(name).get(eid)
    tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
    t = tr.get(eid)
    if raw is None or not t:
        return False, False
    before, _ = R.build_candidate(raw, t, eid)
    old = R.NL_WINS.get(eid)
    R.NL_WINS[eid] = set(wins)
    try:
        after, _ = R.build_candidate(raw, t, eid)
    finally:
        R.NL_WINS.pop(eid, None) if old is None else R.NL_WINS.__setitem__(eid, old)
    if before is None or after is None:
        return False, False

    # ⚠ 패딩까지 비교하면 안 된다 — 개행 1바이트가 늘면 4바이트 정렬이 달라진다.
    # ⚠ **창 앞 공백도 무시한다.** `%s` 주입 창 앞 공백(`제 이름은 류난`)은 개행이 들어가면
    #   빌더가 안 붙인다 — 이름이 새 줄에서 시작하니 띄어쓸 상대가 없다. 그 정당한 차이를
    #   "본문이 바뀌었다"로 읽어 jp496~499 를 계속 폴백으로 오판했다(2026-08-09).
    #   창 마커 **바로 앞** 공백만 지우므로 진짜 문안 변화는 그대로 걸린다.
    def norm(x):
        return x.rstrip(b"\x00").replace(b"\x0a", b"").replace(b"\x20" + R.MC, R.MC)

    return _count_nl_mc(after) == _count_nl_mc(raw), norm(after) == norm(before)


def main():
    # ⚠ **두 편을 다 돈다.** 한쪽만 돌면 그쪽만 초록이고 다른 편은 안 보인다.
    rows = scan("ED1") + scan("ED2")
    print(f"창 앞 개행 결손 {len(rows)}블록")
    deep = "--suggest" in sys.argv or "--apply" in sys.argv
    show = rows if deep else rows[:20]
    plans, dead = [], []
    for nm, e, want, got, prev in show:
        wins = suggest(nm, e) if deep else None
        mark = ""
        if wins:
            fixed, intact = verify(nm, e, wins)
            mark = f"  nl_after={wins} {'✅' if fixed and intact else '⛔폴백'}"
            (plans if fixed and intact else dead).append((nm, e, wins))
        print(f"  {nm} jp{e}  개행 {got}/{want}{mark}  {prev}")
    if len(rows) > len(show):
        print(f"  … 외 {len(rows) - len(show)}블록")
    if dead:
        print(
            f"⛔ `nl_after` 가 안 먹는 블록 {len(dead)}건 — build_block 폴백이라 조판을 봐야 한다:"
        )
        for nm, e, _ in dead:
            print(f"    {nm} jp{e}")

    if "--apply" in sys.argv and plans:
        path = os.path.join(ROOT, "align_overrides.json")
        ov = json.load(open(path, encoding="utf-8"))
        n = 0
        for nm, e, wins in plans:
            sc = ov.setdefault(nm, {})
            cur = dict(sc.get(str(e)) or scene_map(nm).get(e) or {})
            # 🔴 **`table` 을 요구하지 않는다**(2026-09-12). 예전엔 `not cur.get("table")` 로
            #    걸렀는데 그건 **배정 시대 가정**이다 — 자체 번역 블록(`script/`)은 좌표가
            #    없어서 전부 튕겼고, 실측으로 ED2 23건이 「제안은 ✅ 인데 반영 0건」이 됐다.
            #    런타임은 `table` 과 무관하게 `nl_after` 를 읽는다(`reinsert_kr_pilot:3428`).
            if cur.get("nl_after"):
                continue  # 이미 손으로 넣은 건 안 건드린다
            cur["nl_after"] = wins
            cur["note"] = (cur.get("note") or "") + (
                " · 창 앞 개행 복원(check_window_nl 2026-08-06)"
            ).strip()
            sc[str(e)] = cur
            n += 1
        json.dump(ov, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  → align_overrides.json 반영 {n}건")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
