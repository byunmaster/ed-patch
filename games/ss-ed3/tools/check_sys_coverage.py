"""시스템 문자열에 **우리 표가 아예 없는** 일본어가 남았나 — 커버리지 검사.

    python3 games/ss-ed3/tools/check_sys_coverage.py          # 목록
    python3 games/ss-ed3/tools/check_sys_coverage.py --check  # 남으면 1 로 죽는다 (게이트)

🔴 **왜 필요한가 — `reinsert_sys.py` 는 이걸 구조적으로 못 본다.** 그 도구는 「우리 표에
   있는 것이 다 들어갔나」를 센다. 표에 **아예 없는** 원문은 실패도 종결 불일치도 아니고
   **그냥 안 옮겨진 채 화면에 나간다.** 빌드도 게이트도 초록이다.

   실측(유저 인게임 QA 2026-09-07) — 전투 승리 화면에 **「쥬리오は、전투에 이겼다!」**.
   승리 문구는 조각 셋을 이어 붙이는데(`이름` + `たち` + `<09>は、` + `戦闘に勝った！`)
   **마지막만 표에 있었다.** 앞 둘은 표에 없으니 아무 검사에도 안 걸렸다.
   ⇒ 「넣은 것을 세는 검사」와 「안 넣은 것을 세는 검사」는 **다른 축**이다.

🔑 **바이트로 댄다.** `strtab.text_of` 는 제어를 `<0F>` 로 그리는데 표의 키는 실제 `\\x0f`
   라, 글자로 대면 같은 문자열이 다르게 보인다(처음에 그렇게 재서 오탐이 44 → 실제 29).

⚠ **일본어 문자(가나 **또는** 한자)가 있는 것만 센다.** `/0.BIN` 을 NUL 로 끊으면 코드·표가
   문자열처럼 잡힌다(`'bビja!瑞'` 꼴). 이 한 겹으로 대부분이 걸러진다.
   🔴 **처음엔 가나만 봤다가 순한자를 통째로 놓쳤다**(pc98 발 지적, 09-07) — 29 → 93 으로
   넓히니 그 차이에서 **블랙잭 `５０枚`** 가 나왔다. 40·30·20·10·0 은 옮겼는데 50 만 빠져
   있었다. **같은 창 안에서 다섯은 한글, 하나만 일본어**라 눈으로도 잘 안 걸리는 부류다.

⚠ 남는 것은 **사유를 적어 받아들인다**(`script/sys_coverage_accept.json`). 두 부류다 —
   **개발자 메뉴**(입구를 죽여서 화면에 안 나온다. 그 구역은 자막 스텁이 쓴다) ·
   **파서 쓰레기**(두 글자짜리 조각). 늘 빨간불이면 아무도 안 본다.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import reinsert_sys as RS
import strtab as S

ACCEPT = os.path.join(C.GAME_DIR, "script", "sys_coverage_accept.json")

#   SJIS 히라가나(0x829F~0x82F1) · 가타카나(0x8340~0x8396)
KANA = re.compile(rb"(?:\x82[\x9f-\xf1]|\x83[\x40-\x96])")
#   SJIS 2 바이트 한자 영역 — 🔴 **가나만 보면 순한자 문자열을 통째로 놓친다**(pc98 발, 09-07).
#   실측: 가나 기준 29 → 일본어 문자 기준 93. 그 차이 64 중 하나가 **진짜 결함**이었다
#   (블랙잭 `５０枚` — 40·30·20·10·0 은 옮겼는데 50 만 빠져 화면에 `枚` 가 그대로 났다).
#   ⚠ 「한 창 안에서 넷은 한글, 둘은 깨짐」이 이 부류의 전형이다 — 눈으로도 잘 안 걸린다.
KANJI = re.compile(rb"(?:[\x88-\x9f\xe0-\xea][\x40-\xfc])")


def japanese(raw):
    """화면 문안의 표지 — 가나 **또는** 한자."""
    return bool(KANA.search(raw) or KANJI.search(raw))
#   종결 바이트는 표기가 갈리므로 양쪽에서 떼고 댄다
_TERM = b"\x00\x0f\x10"


def covered(raw, keys):
    """그 원문이 우리 표에 있나 — 종결 바이트 표기 차이를 흡수한다."""
    body = raw.rstrip(_TERM)
    return raw in keys or body in {k.rstrip(_TERM) for k in keys}


def scan():
    """`[(파일, off, 보기용 글자)]` — 가나가 있는데 표에 없는 것."""
    tbl = RS.table()
    keys = set()
    for k in tbl:
        try:
            keys.add(k.encode("shift_jis"))
        except UnicodeEncodeError:
            pass  # 우리말 키는 원문이 아니다
    out = []
    for f in RS.FILES:
        with C.open_disc(1) as d:
            data = d.read(f)
        for s in S.strings(data, S.load_base(f)):
            raw = s["raw"].lstrip(bytes(range(0x20)))  # 선행 제어를 뗀다
            if not japanese(raw) or covered(raw, keys):
                continue
            out.append((f, s["off"], S.text_of(s["raw"])))
    return out


def accepted():
    if not os.path.exists(ACCEPT):
        return {}
    with open(ACCEPT, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="남으면 1 로 죽는다 (게이트)")
    a = ap.parse_args()

    ok = accepted()
    rows = scan()
    left = [(f, o, t) for f, o, t in rows if f"{f}:{o}" not in ok]
    print(
        f"표에 없는 일본어 {len(rows)} · 사유 적힌 것 {len(rows) - len(left)} · 남은 것 {len(left)}"
    )
    for f, o, t in left[:20]:
        print(f"  🔴 {f} {o}  {t!r}")
    if a.check and left:
        print(
            "  🔴 화면에 일본어로 나갈 수 있다 — 옮기거나 사유를 적는다(sys_coverage_accept.json)"
        )
        return 1
    if a.check:
        print("  ✅ 표에 없는 일본어 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
