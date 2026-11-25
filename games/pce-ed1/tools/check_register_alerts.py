"""말투·분량 경보 래칫 — 마스터 11-13 밤샘 정적 일 3.

    python3 games/pce-ed1/tools/check_register_alerts.py          # 검사
    python3 games/pce-ed1/tools/check_register_alerts.py --freeze # 기준선을 지금 상태로(검토한 뒤에만)

경보 둘(그대 금지는 `master_rulings.json` 의 「2인칭-그대-금지」 가 건다):
  ① 반말 줄 듣는 이 「-시-」 섞임 — 문장의 끝 어절이 반말 꼴(시는군·시는데·시네·시지·시겠어 …)에
     높임 「-시-」 가 낀 줄. 듣는 이를 높이면서 말끝은 낮춘 꼴이다(원문 등급과 어긋날 수 있다).
     하게체(시게)·합쇼는 대상이 아니다. 제3자 높임이면 정상이라 기준선에 올린다.
  ② 원문 대비 길이 급감 — 원문(가나·한자, 부호·공백 뺀 8자↑) 대비 한글 글자 수가 0.38 미만.
     번역이 문장을 빠뜨렸을 때 걸린다. 쪽 분할로 짧은 메시지는 기준선에 올린다.
기준선(`register_alert_baseline.json`)에 없던 열쇠가 새로 걸리면 실패 — 검토해 고치거나 기준선에 올린다.
양성 대조: 검출기가 죽어 0 이 나오는 걸 막으려고 합성 문장으로 먼저 자가 시험한다.
"""

import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

GAME = Path(common.GAME_DIR)
SCRIPT = GAME / "script"
MSGS = GAME / "work" / "derived" / "messages"
BASE = GAME / "register_alert_baseline.json"

SENT = re.compile(r"[^.?!…]+[.?!…]*")
# 끝 어절이 반말 꼴이면서 높임 시 가 든 것
HON_BAN = re.compile(r"(주시|보시|하시|가시|오시|드시|계시|으시|물러나시|되시|이시|시)(는군|는데|네|지|겠어|려나|나|어|ㄴ가|는가)[?!.…]*$")
HON_BAN2 = re.compile(r"시(지\s?않겠어|지\s?않을래|지\s?않아)[?!.…]*$")
JP_STRIP = re.compile(r"[\s　\x0c\n・、。！？…]")
KR_STRIP = re.compile(r"[\s\x0c\n.,!?…~「」『』]")


def hon_ban_hits(text: str) -> bool:
    for page in text.split("\f"):
        for s in SENT.findall(page.replace("\n", "")):
            s = s.strip()
            last = s.split(" ")[-1] if s else ""
            if HON_BAN.search(last) or HON_BAN2.search(s):
                return True
    return False


def selftest() -> None:
    assert hon_ban_hits("이봐, 오늘은 웬일로 순순히 물러나시는군."), "① 양성 대조 실패"
    assert hon_ban_hits("그 선장의 어머님에 대해 좀 더 알려 주시지 않겠어?"), "① 양성 대조 실패(2)"
    assert not hon_ban_hits("우리 집에서 쉬었다 가시게."), "① 하게체는 대상이 아니다"
    assert not hon_ban_hits("왕자님께서는 안녕하십니까."), "① 합쇼는 대상이 아니다"


def scan() -> tuple[set[str], set[str]]:
    a, b = set(), set()
    for f in sorted(glob.glob(str(SCRIPT / "scn*.json"))):
        sid = Path(f).stem[3:]
        kr = json.load(open(f, encoding="utf-8")).get("messages", {})
        for k, v in kr.items():
            t = v.get("t") if isinstance(v, dict) else None
            if t and hon_ban_hits(t):
                a.add(f"{sid}#{k}")
        jf = MSGS / f"scn{sid}.json"
        if not jf.exists():
            continue
        for m in json.load(open(jf, encoding="utf-8")):
            v = kr.get(m["key"])
            t = v.get("t") if isinstance(v, dict) else None
            if not t:
                continue
            j, kk = JP_STRIP.sub("", m["jp"]), KR_STRIP.sub("", t)
            if len(j) >= 8 and len(kk) / len(j) < 0.38:
                b.add(f"{sid}#{m['key']}")
    return a, b


def main() -> int:
    selftest()
    a, b = scan()
    if "--freeze" in sys.argv:
        BASE.write_text(
            json.dumps({"hon_ban": sorted(a), "short": sorted(b)}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"기준선 갱신 — ① {len(a)} · ② {len(b)}")
        return 0
    base = json.load(open(BASE, encoding="utf-8")) if BASE.exists() else {"hon_ban": [], "short": []}
    na, nb = sorted(a - set(base["hon_ban"])), sorted(b - set(base["short"]))
    print(f"말투·분량 경보 [pce-ed1] — ① 반말 줄 -시- 섞임 {len(a)}(기준선 {len(base['hon_ban'])}) · ② 길이 급감 {len(b)}(기준선 {len(base['short'])})")
    for x in na:
        print("  ① 새 경보", x)
    for x in nb:
        print("  ② 새 경보", x)
    return 1 if (na or nb) else 0


if __name__ == "__main__":
    sys.exit(main())
