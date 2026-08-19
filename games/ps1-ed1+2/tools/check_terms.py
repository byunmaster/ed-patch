#!/usr/bin/env python3
"""**같은 것을 같은 말로 부르는가** — 일반명사 용어가 UI·대사·ED2 사이에서 갈리는지 본다.

**왜.** 고유명사는 `check_proper_nouns` 가 네 정본과 대조한다. 그런데 **일반명사**는 정본이
없다 — `呪文`·`旅`·`型` 같은 말은 아이템표에도 화자 사전에도 없어서 **아무도 대조하지
않는다.** 그래서 이런 일이 벌어졌다(실측 2026-08-13):

> 시스템 UI 는 `전투의 주문`·`회복의 주문` 인데, 대사에서는 현자가 **`마법`을 전수**하고
> 있었다. 한 이미지 안에서 메뉴와 대사가 다른 말을 쓰는데도 **모든 게이트가 초록**이었다 —
> UI 는 `patch_sys_ui`, 대사는 재삽입 파이프라인 관할이라 층이 아예 달랐다.

세 축으로 본다:

- **대사** — 원문에 감시 낱말이 있는데 우리 문안이 **정본이 아닌 표기**를 쓰면 보고.
- **UI** — 시스템 라벨에 **정본이 아닌 표기**가 있으면 보고(위 사고의 반대 방향).
- **편 간 일관성**(참고) — **우리** ED1 문안과 **우리** ED2 문안이 같은 말을 쓰는지 센다.
  **한 디스크에 두 편이 담기고 플레이어는 이어서 한다** — 편마다 이름이 달라지면 그게
  결함이다([policy.md] 표기 방침).
  ⚠ **2026-08-19 에 대상을 갈아탔다.** 그전엔 **ED2 정발 코퍼스**를 셌다 — 「정발이 뭐라
  부르나」를 참고축으로 둔 것인데, 자체 번역으로 바뀐 뒤엔 **답이 필요한 질문이 아니다**
  (우리 표기를 정발 빈도에 맞출 이유가 없다). 지금은 우리 두 편을 서로 대조한다 — 같은 노력으로
  실제로 고칠 수 있는 것을 보여 준다.

⚠ **게이트다** — 표에 든 것은 전부 **유저가 확정한 결정**이라 어긋나면 고칠 자리다.
새 용어를 넣을 때는 근거(원문 낱말 · 결정 날짜)를 함께 적는다.

  python3 tools/check_terms.py          # 전 축
  python3 tools/check_terms.py -v       # 어긋난 자리마다
"""

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import common
import reinsert_kr_pilot as R
from check_align_fit import jp_text
from common import ROOT
from patch_sys_ui import SCN_FILES

# 원문 낱말 → (정본 표기, 갈리면 안 되는 다른 표기들, 근거)
#
# ⚠ **정본이 아닌 표기를 「금지어」로 적는다.** 「정본이 없으면 실패」로 짜면 부분 인용·
#   대명사 치환에 전부 걸려 늘 빨간불이 된다(`check_proper_nouns` 가 게이트가 아닌 이유다).
TERMS = {
    "呪文": (
        "주문",
        ("마법",),
        "마법=초자연 에너지 · 주문=발동 명령어(유저 정정 2026-08-13). ED2 정발도 주문 126 · 마법 0",
    ),
    # ⚠ **정발이 안에서 갈린다** — ED2 대사는 `주문서` 9회인데 아이템 표(`ED2MAIN.EXE`)는
    # `X의책` 이다. 원문 `呪文の書` 는 「책」·「서」 둘 다 되므로 원음으로 판정이 안 서고,
    # **우리 안의 일관성**이 기준이 됐다 — ED2 아이템이 `프람의 책` 이고 ED1 도
    # `고대의 검의 책` 이라 대사도 「책」이다(유저 확정 2026-08-14).
    # ⚠ 두 브랜치가 한때 서로 반대 정본을 들고 있었다 — 여기가 정본이다.
    "呪文の書": ("주문책", ("마법책", "주문서"), "우리 아이템 표기(`X의 책`)와 한 말"),
    # ⚠ **고유명사가 화면에서 갈리고 있었다**(2026-08-18 실측: 사이레스 36 · 사일레스 5).
    # 편차 대장은 `사이레스` 로 확정했는데(ED2 16곳 · 원음) ED1 정발은 `사일레스` 를 쓰고,
    # 교정 규칙도 게이트도 없어 **같은 석비 문안이 마을마다 갈려 나갔다**.
    "サイレス": ("사이레스", ("사일레스",), "편차 대장 확정 — ED2 16곳·원음(2026-08-12)"),
    "旅": ("여행", ("모험",), "SCN2 에서 한 대사 안에 둘이 섞여 있었다(2026-08-13)"),
    "型": ("본", ("틀",), "「본을 뜨다」가 바른 표현(유저 2026-08-13)"),
    "勇者": ("용사", ("용자",), "전 씬 용사 9 · 용자 2 로 갈려 있었다(2026-08-13)"),
    # 영어는 원본 그대로가 방침이다(표기 방침) — UI 는 `HP` 인데 대사만 「체력」으로 갈렸다
    "ＨＰ": (
        "HP",
        ("체력",),
        "영어(EP·HP·BGM)는 원본 유지 · UI 라벨도 HP. ⚠ ED2 정발은 「체력」이라 참고축이 ⚠ 를 띄우는데, 우리 UI 가 HP 라 대사만 「체력」이면 한 화면에서 어긋난다 — HP 가 맞다. ⚠ 참고축의 ⚠ 는 **정발이 「체력」을 쓴다는 사실**을 보여 줄 뿐이라 닫히지 않는다 — 쫓지 말 것. 우리 쪽은 대사·UI 둘 다 0이고, 우리 문안에 있는 「체력」 다섯 곳은 전부 원문이 `体力作り`(몸 만들기)라 스탯과 무관하다(2026-08-17 전수 확인)",
    ),
}

# ⚠ **금지어가 다른 뜻으로 정당하게 쓰이는 자리** — 원문이 달라서 그렇다.
ALLOW = {
    "마법의 물건",  # 원문 `魔法の品`(용의 알) — 이건 진짜 마법이다
}


def _has(word, text):
    """낱말이 **낱말로서** 있는가.

    ⚠ 한 글자 낱말은 부분일치로 오탐이 쏟아진다 — 아이템 `배틀 슈츠` 가 `型`의 금지어
    `틀` 에 걸렸다(실측 2026-08-13). 앞이 한글이면 딴 낱말 속이라 뺀다(`배틀`·`일본`).
    두 글자 이상은 그대로 본다(`마법책` 처럼 접미가 붙어 나오기 때문).
    """
    if len(word) == 1:
        return re.search(rf"(?<![가-힣]){re.escape(word)}", text) is not None
    return word in text


def _ed_exe():
    """원본 ED.EXE 바이트 — UI 라벨의 JP 원문을 읽으려고 쓴다(LBA 257, 실측)."""
    out = bytearray()
    with open(common.ORIG_BIN, "rb") as f:
        for i in range((1021952 + 2047) // 2048):
            f.seek((257 + i) * 2352 + 24)
            out += f.read(2048)
    return bytes(out)


def _mask(kr):
    """정당한 예외를 지운 사본 — 금지어 탐지는 이 위에서 한다."""
    for a in ALLOW:
        kr = kr.replace(a, "")
    return kr


def scan_dialog(verbose=False):
    hits = []
    for scn, _l, _z in SCN_FILES:
        for _s, eid, jp, cand, _t in R.iter_candidates((scn,)):
            kr = R.render_bytes(cand, ctrl=False)
            if not kr:
                continue
            j, k = jp_text(jp), _mask(kr.replace("\n", " "))
            for term, (canon, bad, _why) in TERMS.items():
                if term not in j:
                    continue
                for b in bad:
                    if _has(b, k):
                        hits.append((scn, eid, term, canon, b, k[:56]))
    print(f"  {'✅' if not hits else '⚠'} 대사: 용어가 갈린 곳 {len(hits)}")
    if verbose:
        for scn, eid, term, canon, b, k in hits:
            print(f"      {scn} jp{eid} [{term}] {b} → {canon}\n           {k}")
    return len(hits)


def scan_ui(verbose=False):
    """시스템 라벨 — 대사와 반대 방향으로 어긋날 수 있다.

    ⚠ **여기서도 원문을 본다.** 금지어만 보고 잡았더니 `모험을 계속한다`(원문 `冒険の続きを
    する`)가 `旅`=여행 규칙에 걸렸다 — 원문이 `冒険` 인 자리라 「모험」이 맞다(실측
    2026-08-13). UI 라벨은 오프셋으로 키가 잡혀 있으니 **원본 EXE 에서 JP 를 읽어** 댄다.
    """
    import patch_items as I
    import patch_sys_ui as U

    # ⚠ **표 이름을 `getattr` 로 무르게 잡지 말 것.** 처음에 `LABELS` 라 넣었는데 실제 이름은
    #   `UI` 라 기본값 `{}` 이 돌아왔고 — **아무것도 안 보면서 초록불**이 떴다. 심어 보고서야
    #   잡았다(2026-08-13). 표가 사라지면 여기서 죽는 게 맞다.
    ed = _ed_exe()
    pairs = []  # (KR 라벨, JP 원문 | None)
    for off, kr in U.UI.items():
        if not isinstance(kr, str):
            continue
        try:
            jp = ed[off : off + 24].split(b"\x00")[0].decode("cp932")
        except Exception:  # noqa: BLE001
            jp = None
        pairs.append((kr, jp))
    # 아이템·몬스터명은 표 자체가 JP → KR 이라 원문이 딸려 온다.
    pairs += [(kr, jp) for jp, kr in I.NAMES.items() if isinstance(kr, str)]

    hits = []
    for v, jp in pairs:
        for term, (canon, bad, _why) in TERMS.items():
            # 원문을 못 읽은 자리만 금지어 단독으로 본다(보수적으로 계속 감시).
            if jp is not None and term not in jp:
                continue
            for b in bad:
                if _has(b, v) and canon not in v:
                    hits.append((v, term, canon, b))
    print(f"  {'✅' if not hits else '⚠'} 시스템 UI: 용어가 갈린 라벨 {len(hits)}")
    if verbose:
        for v, term, canon, b in hits:
            print(f"      {v!r} [{term}] {b} → {canon}")
    return len(hits)


def _ours_by_game():
    """{게임: [문안]} — 우리 정본 전량. 원천이 둘이다(대사 + textmap)."""
    out = {"ED1": [], "ED2": []}
    for p in sorted(glob.glob(os.path.join(ROOT, "script", "ED*SCN*.json"))):
        game = os.path.basename(p)[:3]
        with open(p, encoding="utf-8") as f:
            for v in json.load(f).values():
                t = (v or {}).get("t")
                if isinstance(t, str) and t:
                    out[game].append(t)
    for p in sorted(glob.glob(os.path.join(ROOT, "textmap", "*.json"))):
        game = "ED2" if os.path.basename(p)[:-5].endswith("_ed2") else "ED1"
        with open(p, encoding="utf-8") as f:
            stack = [json.load(f)]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                t = o.get("ours")
                if isinstance(t, str) and t:
                    out[game].append(t)
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return out


def scan_item_tables():
    """**ED1·ED2 이름표가 같은 물건을 같은 말로 부르는가** — 게이트다.

    🔴 아무도 안 보던 자리다(2026-08-19 실측). 이 파일의 다른 축은 **대사**만 보는데 아이템
    이름은 `patch_items.NAMES`(ED1)·`patch_ed2_sys.NAMES_ED2`(ED2) 라는 **별개 표**에 있어서,
    겹치는 셋이 **셋 다 다른 표기**였다(`幅広のつるぎ` 대형검/날 넓은 칼 · `くさりかたびら`
    미늘 갑옷/쇠사슬옷 · `布の服` 헝겊 옷/천 옷).

    ⚠ **대사에 한 번도 안 나와서 다른 게이트가 못 봤다** — 장비·상점 화면에는 나간다.
    한 디스크에서 이어 하는 플레이어에겐 같은 장비가 편마다 다른 이름으로 보인다
    (「고유명사는 ED1·ED2 가 한 표기」 — policy 2026-08-12).
    """
    from patch_ed2_sys import NAMES_ED2
    from patch_items import MONSTERS, NAMES

    bad = []
    for tbl, what in ((NAMES, "아이템"), (MONSTERS, "몬스터")):
        for k in sorted(set(tbl) & set(NAMES_ED2)):
            if tbl[k] != NAMES_ED2[k]:
                bad.append((what, k, tbl[k], NAMES_ED2[k]))
    print(f"  {'✅' if not bad else '❌'} ED1·ED2 이름표가 한 표기다 (갈린 것 {len(bad)})")
    for what, k, a, b in bad:
        print(f"      {what} {k}  ED1={a!r}  ED2={b!r}")
    return len(bad)


def scan_between_games():
    """**우리 ED1 과 우리 ED2 가 같은 말을 쓰는가** — 참고축(게이트 아님).

    ⚠ 게이트가 아닌 이유: 한쪽 편에만 나오는 낱말이 많아(`竜の祭` 는 ED1 전용) 0 을 「갈림」
    으로 읽으면 오탐이 쏟아진다. **양쪽에 다 나오면서 갈린 자리**만 사람이 본다.
    """
    # ⚠ **한 글자 낱말은 세지 않는다.** 부분일치라 `본` 이 `본다`·`본인` 에 죄다 걸린다
    #   (실측: `型` 을 세니 본 30 · 틀 58 이 나왔는데 **둘 다 이 뜻으로는 0회**였다).
    per = _ours_by_game()
    print(f"  ℹ 편 간 표기 대조 (우리 문안 ED1 {len(per['ED1'])}줄 · ED2 {len(per['ED2'])}줄):")
    split = 0
    for term, (canon, bad, _why) in TERMS.items():
        cand = [w for w in (canon, *bad) if len(w) > 1]
        if not cand:
            print(f"      – [{term}] 한 글자라 부분일치 잡음이 커서 안 센다")
            continue
        row = []
        forms = {}
        for g in ("ED1", "ED2"):
            blob = "\n".join(per[g])
            forms[g] = {w: blob.count(w) for w in cand}
            row.append(f"{g} " + "/".join(f"{w} {forms[g][w]}" for w in cand))
        # 양쪽에 다 나오는데 **우세한 표기가 다르면** 갈린 것이다
        top = {g: max(forms[g], key=lambda w, g=g: forms[g][w]) for g in ("ED1", "ED2")}
        both = all(sum(forms[g].values()) for g in ("ED1", "ED2"))
        mark = "⚠" if both and top["ED1"] != top["ED2"] else "✅"
        if mark == "⚠":
            split += 1
        print(f"      {mark} [{term}] " + " · ".join(row))
    if split:
        print(f"      ⚠ 편마다 우세 표기가 다른 낱말 {split} — 정본을 정해 양쪽을 맞춘다")


if __name__ == "__main__":
    v = "-v" in sys.argv
    bad = scan_dialog(v) + scan_ui(v) + scan_item_tables()
    scan_between_games()
    print(f"\n{'✅ 용어가 한 표기다' if not bad else f'⚠ 용어가 갈린 곳 {bad}'}")
    sys.exit(1 if bad else 0)
