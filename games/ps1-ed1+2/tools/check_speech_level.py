#!/usr/bin/env python3
"""**한 사람이 한 호흡에 존대와 반말을 섞는가** — 어투 혼용을 두 축으로 잰다.

**왜.** 정발 저본에서 옮겨 오는 문장과 우리가 새로 쓴 문장이 한 블록에 섞이면 어투가
갈린다. 화면에서는 같은 인물이 한 창 안에서 말을 높였다 낮췄다 하는 꼴이 된다.

**⚠ 「반말처럼 보이는 것」의 태반은 반말이 아니다**(2026-08-16 실측). 한국어의 손윗사람
말투 — **하소체·하게체**(`~구나`·`~란다`·`~느냐`·`~게다`·`~일세`) — 는 어머니·황태후·
노인이 아랫사람에게 쓰는 **정중한** 어투다. 이걸 반말로 세면 27건이 오탐으로 뜬다
(디나 왕비·페리시아 황태후·라이아스가 통째로 걸렸다). 그래서 **해라체 평서형만** 센다.

**축 둘.**

- `mixed_in_block()` — 한 창(`{p}` 사이) 안에서 존대 종결과 해라체 종결이 함께 나오는가.
  ⚠ `{p}` 를 문장 경계로 치면 안 된다 — 창이 갈리면 **화자도 갈린다**(한 블록에 병사의
  말과 왕자의 대꾸가 같이 든다). 창 단위로 끊어야 오탐이 사라진다.
- `vs_original()` — **원문이 경어체인데 우리가 해라체인가**(`です`·`ます`·`ください` ↔
  `~는다`·`~거야`). 사람이 「누구에게 하는 말인가」를 몰라도 판정이 서는 **객관 축**이다.

⚠ **화자별 통계는 축으로 안 쓴다.** 한 인물이 윗사람에겐 존대, 적에겐 반말을 쓰는 건
정상이라 「갈린다」가 곧 오류가 아니다 — 실측에서 상위 후보가 전부 정당했다(세리오스가
왕에겐 존대, 적에겐 반말). 사람이 볼 목록이 아니라 노이즈가 된다.

  python3 tools/check_speech_level.py        # 두 축 요약
  python3 tools/check_speech_level.py -v     # 자리마다
"""

import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import OUT_DIR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(ROOT, "script")

# 존대 — 합쇼체·해요체. ⚠ **하옵체까지 넣어야 한다**(`~사옵나이다`·`~주시옵소서`).
# 라이아스·시녀처럼 궁중 말투를 쓰는 인물이 통째로 「반말」로 잡혔다(jp15 실측).
HON = re.compile(
    r"(습니다|습니까|십니다|십니까|입니다|합니다|됩니다|옵니다|사옵|드립니다|십시오"
    r"|나이다|옵나이다|옵소서|시옵소서|사이다"
    r"|세요|셔요|예요|이에요|어요|아요|여요|지요|나요|까요|군요|네요|는데요)$"
)
# 해라체 평서·의문 — ⚠ 하소체(`~구나`·`~란다`·`~느냐`)와 하게체(`~네`·`~게`·`~일세`)는
#    **뺀다.** 손윗사람이 아랫사람에게 쓰는 정중한 어투라 존대와 섞여도 오류가 아니다.
PLAIN = re.compile(
    r"(는다|았다|었다|였다|한다|이다|있다|없다|같다|거야|잖아|는군|로군|겠다|더군)$"
)
# 원문 경어 표지 / 거친 표지.
JP_HON = re.compile(r"(です|ます|ました|ません|ましょ|でしょ|ください|ござい|いたし|おります)")
JP_PLAIN = re.compile(r"(だぞ|だな|だよ|だぜ|だろ|かい|やがる|きさま|おまえ)")
# 조판·제어 부스러기를 지운다(어미 판정은 **글자 끝**을 봐야 한다).
CLEAN = re.compile(r"[\x00-\x1f%a-zA-Z0-9\"'~()\[\]\s]+")


def registers(text):
    """(존대 문장 수, 해라체 문장 수)."""
    h = p = 0
    for s in re.split(r"[.!?…]+|\n", text):
        s = CLEAN.sub("", s).strip()
        if len(s) < 3:
            continue
        if HON.search(s):
            h += 1
        elif PLAIN.search(s):
            p += 1
    return h, p


def _scripts():
    for path in sorted(glob.glob(os.path.join(SCRIPT_DIR, "ED*SCN*.json"))):
        scn = os.path.basename(path)[:-5]
        with open(path, encoding="utf-8") as f:
            yield scn, json.load(f)


def mixed_in_block():
    """한 창 안에서 존대와 해라체가 같이 나오는 자리."""
    out = []
    for scn, d in _scripts():
        for eid, v in d.items():
            for page in (v.get("t") or "").split("{p}"):
                h, p = registers(page)
                if h and p:
                    out.append((scn, eid, v.get("s") or "", page.replace("\n", " ")[:70]))
    return out


def _by_jp(hon_side):
    """원문 어투와 우리 어투가 **반대**인 자리.

    `hon_side=True`  — 원문 경어체인데 우리는 해라체뿐(높여야 할 자리를 낮췄다).
    `hon_side=False` — 원문 반말·거친 말투인데 우리는 존대뿐(**낮춰야 할 자리를 높였다**).

    ⚠ 뒤쪽 축은 2026-08-19 에 붙였다. 자체 번역을 대량으로 쓰면 **모르는 자리를 일단
    높여 쓰는 쪽으로 쏠린다** — NPC 의 거친 말투(`だぜ`·`やがる`·`きさま`)가 통째로
    공손해지면 캐릭터가 뭉개진다. 앞쪽 축만으로는 그 방향이 안 보였다.

    ⚠ **해요체와 합쇼체를 못 가른다** — `HON` 이 둘을 한 묶음으로 본다. 마을 사람이
    `~가세요`(친근한 존대)로 말해도 원문이 `だい` 면 여기 뜬다. 그래서 이 축은 목록이지
    게이트가 아니다 — 뜬 자리에서 볼 것은 「존대냐」가 아니라 **「격식이 원문보다
    높은가」**다.
    """
    out = []
    for scn, d in _scripts():
        jp_path = os.path.join(OUT_DIR, "scn_jp", f"{scn}.json")
        if not os.path.exists(jp_path):
            continue
        with open(jp_path, encoding="utf-8") as f:
            raw = {
                e["entry_id"]: bytes.fromhex(e["raw_hex"])
                for e in json.load(f)["entries"]
                if e.get("raw_hex")
            }
        for eid, v in d.items():
            r = raw.get(int(eid))
            if not r:
                continue
            jp = r.decode("cp932", "ignore")
            if hon_side:
                if not JP_HON.search(jp) or JP_PLAIN.search(jp):
                    continue
            elif not JP_PLAIN.search(jp) or JP_HON.search(jp):
                continue
            h, p = registers(v.get("t") or "")
            hit = (p >= 2 and h == 0) if hon_side else (h >= 2 and p == 0)
            if hit:
                out.append((scn, eid, v.get("s") or "", (v.get("t") or "").replace("\n", " ")[:70]))
    return out


def vs_original():
    return _by_jp(True)


def vs_original_plain():
    return _by_jp(False)


def main():
    verbose = "-v" in sys.argv
    a, b, c2 = mixed_in_block(), vs_original(), vs_original_plain()
    for label, rows in (
        ("한 창 안에서 존대↔해라체 혼용", a),
        ("원문 경어 → 우리 해라체", b),
        ("원문 반말 → 우리 존대", c2),
    ):
        print(f"  {'✅' if not rows else '⚠'} {label}: {len(rows)}곳")
        if rows and verbose:
            for scn, eid, spk, t in rows:
                print(f"      {scn} jp{eid} [{spk}] {t!r}")
    if a or b or c2:
        c = collections.Counter(r[0] for r in a + b + c2)
        print("      씬별:", dict(sorted(c.items())))
    print(
        "  ⚠ 게이트가 아니다 — 적에겐 반말·왕에겐 존대처럼 **한 창에 두 상대**가 섞이는"
        "\n    정당한 자리가 있다(`비겁한 것은 네 쪽이다!! 왕이여, 도망치십시오!!`). 사람이 본다."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
