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
- **ED2 정발**(참고) — 같은 물건을 ED2 가 뭐라 부르는지 센다. **한 디스크에 두 편이 담기고
  플레이어는 이어서 한다** — 편마다 이름이 달라지면 그게 결함이다([policy.md] 표기 방침).
  ⚠ 코퍼스는 `work/` 라 없을 수 있다. 없으면 이 축만 건너뛴다.

⚠ **게이트다** — 표에 든 것은 전부 **유저가 확정한 결정**이라 어긋나면 고칠 자리다.
새 용어를 넣을 때는 근거(원문 낱말 · 결정 날짜)를 함께 적는다.

  python3 tools/check_terms.py          # 전 축
  python3 tools/check_terms.py -v       # 어긋난 자리마다
"""

import collections
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
from common import OUT_DIR
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
    # `X의책` 이다. 원문 `呪文の書` 는 셋 다 되므로 원음으로 판정이 안 서고, **우리 안의
    # 일관성**이 기준이 됐다 — ED2 아이템을 `프람의 책` 으로 넣었으니 대사도 「책」이다
    # (유저 확정 2026-08-14).
    "呪文の書": ("주문책", ("마법책", "주문서"), "우리 ED2 아이템 표기(`X의 책`)와 한 말"),
    "旅": ("여행", ("모험",), "SCN2 에서 한 대사 안에 둘이 섞여 있었다(2026-08-13)"),
    "型": ("본", ("틀",), "「본을 뜨다」가 바른 표현(유저 2026-08-13)"),
    "勇者": ("용사", ("용자",), "전 씬 용사 9 · 용자 2 로 갈려 있었다(2026-08-13)"),
    # 영어는 원본 그대로가 방침이다(표기 방침) — UI 는 `HP` 인데 대사만 「체력」으로 갈렸다
    "ＨＰ": (
        "HP",
        ("체력",),
        "영어(EP·HP·BGM)는 원본 유지 · UI 라벨도 HP. ⚠ ED2 정발은 「체력」이라 참고축이 ⚠ 를 띄우는데, 우리 UI 가 HP 라 대사만 「체력」이면 한 화면에서 어긋난다 — HP 가 맞다",
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


def scan_ed2():
    """ED2 정발이 같은 것을 뭐라 부르는지 — 참고축(게이트 아님)."""
    root = os.path.join(OUT_DIR, "dos_kr", "ED2")
    files = sorted(glob.glob(os.path.join(root, "*.json")))
    if not files:
        print("  – ED2 정발 코퍼스가 없다(work/ 라 머신마다 다르다) — 이 축은 건너뛴다")
        return
    # ⚠ **한 글자 낱말은 세지 않는다.** 부분일치라 `본` 이 `본다`·`본인` 에 죄다 걸린다
    #   (실측: `型` 을 세니 ED2 에서 본 30 · 틀 58 이 나왔는데 **둘 다 이 뜻으로는 0회**였다).
    #   두 글자 이상만 봐도 갈림은 대부분 잡힌다.
    words = {w for canon, bad, _ in TERMS.values() for w in (canon, *bad) if len(w) > 1}
    cnt = collections.Counter()
    for p in files:
        doc = json.load(open(p, encoding="utf-8"))
        rows = doc.get("entries", doc) if isinstance(doc, dict) else doc
        for e in rows:
            t = e.get("text", "") if isinstance(e, dict) else str(e)
            for w in words:
                cnt[w] += len(re.findall(re.escape(w), t))
    print(f"  ℹ ED2 정발({len(files)}파일)에서 세어 본 낱말 — 참고축(게이트 아님):")
    for term, (canon, bad, _why) in TERMS.items():
        cand = [w for w in (canon, *bad) if len(w) > 1]
        if not cand:
            print(f"      – [{term}] 한 글자라 부분일치 잡음이 커서 안 센다")
            continue
        row = " · ".join(f"{w} {cnt[w]}" for w in cand)
        others = [cnt[b] for b in bad if len(b) > 1] or [0]
        mark = "✅" if len(canon) > 1 and cnt[canon] >= max(others) else "⚠"
        print(f"      {mark} [{term}] {row}")


if __name__ == "__main__":
    v = "-v" in sys.argv
    bad = scan_dialog(v) + scan_ui(v)
    scan_ed2()
    print(f"\n{'✅ 용어가 한 표기다' if not bad else f'⚠ 용어가 갈린 곳 {bad}'}")
    sys.exit(1 if bad else 0)
