#!/usr/bin/env python3
"""**시스템·행동 로그의 문체**를 부류 단위로 지킨다 — **평어체**(마스터 확정 2026-10-03).

🔴 **09-03 의 「원문이 정중이니 정중」을 10-03 에 뒤집었다.** 종장 QA 에서 마스터가 「전투 로그는
반말(`기절해 버렸다`)인데 보물상자·승패·획득은 존댓말이라 한 화면에서 섞여 보인다」고 짚었고
「전부 평어」로 판정했다. 원문은 이 부류에서 정중(`〜ました`) 맞다 — 그래서 아래 수치는 그대로
「원문이 정중임」의 근거로 남기되, **우리 문체는 평어**다(원문 우선의 예외 — 일관성). 이 검사기의
방향이 반대로 뒤집혔다: 이제 **정중이 남으면 실패**다.

(이하 09-03 당시 서술 — 부류를 데이터로 가른다는 방법은 그대로 유효하다.)

**왜(2026-09-03).** 유저가 빛의 검 창 다섯을 인게임에서 보고 「끼워 넣었다는 정중이
아니네?」로 잡았다. 같은 순간에 뜨는 넷(`받았습니다`·`완성되었습니다`·`넣었습니다`)과
하나만 어긋나 있었다. 원인은 문안이 아니라 **판정을 블록 단위로 한 것**이다 —
원문을 한 블록씩 보면 흔들려 보이는데, **부류로 묶어 세면 규칙이 있다.**

    보물상자 부류   원문 정중 44 · 평서 0   (「평서 6」은 NPC 대사와 `ませんでした`
                                             오분류였다 — 08-31 의 97:11 은 오염된 값)
    획득·건넴 안내  원문 정중 117 · 평서 2  (둘 다 NPC 대사가 걸린 오탐)
    이름 색(참고)   대사 1,012 색 · 로그 117 무색 (무색 117 중 113이 이 부류)

⇒ **부류를 원문에서 읽으면 「원문 충실」과 「일관성」이 대립하지 않는다.** 이 검사기는
그 부류가 다시 흐르는 걸 막는다 — 이 축은 이미 08-29↔09-01 로 한 번 진동했다.

부류는 추측이 아니라 **데이터에 있는 것**으로 가른다 — 런타임 주입 표지(`\\x1a` 이름 ·
`\\x17` 아이템)를 쓰는 블록이 곧 시스템·행동 로그다(화자 이름표가 없다).

🔴 **ED2 도 실패로 친다**(2026-09-06). 예전엔 보고만 했는데 그 이유가 「정발 유래라 재작성
대기」였고 **그 전제가 이미 끝났다**(자체 번역 100%). ED2 로그 69블록을 ED1 과 같은 규칙으로
맞춰 **양쪽 다 0** 이 된 지금, 게이트로 거는 게 맞다 — 인게임 QA 로 문안이 움직여도 이 규칙은
안 움직인다.

⚠ 원문이 이 부류에서 평서인 예외 셋(`ED1SCN3:1120` · `ED1SCN4:741·749`)은 **부류 다수에
맞춰 정중으로 올렸다**(유저 확정 2026-09-03). 원문을 따르는 규칙에서 물러선 유일한 자리라
블록 주석에 근거를 남겼다.

  python3 tools/check_log_register.py          # ED1·ED2 실패
  python3 tools/check_log_register.py --ed2    # ED2 목록까지
"""

import json
import re
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "script"
INJECT = ("\x1a", "\x17")  # 런타임 주입 표지 = 시스템·행동 로그
POLITE = re.compile(r"(습니다|십시오|세요|십니다|습니까)[.!?…]?$")
# 평어로 올릴 대상은 평서(`〜습니다`)뿐이다 — `〜시겠습니까?` 같은 물음은 도구점 주인의 말이다
# (화자가 있으면 그 사람 말투 — policy 「창에 뜬다고 다 시스템 메시지가 아니다」).
STATEMENT = re.compile(r"습니다[.!?…]?$")
PLAIN = re.compile(r"(었다|았다|했다|였다|된다|한다|이다)[.!?…]?$")


# ── 표지 없는 해설·획득 안내 — 손으로 가린 **규칙**(마스터 10-03 「전부 평어」) ──────────────────
# 주입 표지(`\x1a`·`\x17`)가 없는 로그도 있다(`을(를) 받았습니다`·`건넸습니다`). 라벨이 빈 NPC 대사가
# 섞여 있어 정중 평서를 통째로 평어로 올릴 수는 없으므로 **한 문장짜리 파티 행동 서술**만 가린다:
# 동사가 아래 목록이고 · 쉼표·호칭·1~2인칭이 없고 · 문장 전부가 그 꼴이어야 한다.
LOG_VERB = (
    r"(받았|건넸|넣었|손에 넣었|장비했|동료가 되었|동료로 합류했|외웠|발견했|집었|돌려놓았|적었|"
    r"끼워 넣었|끼워 보았|사용했|열었|닫았|읽었|기도했|설치했|돌려받았)"
)
LOG_SENT = re.compile(r"^[^.!?,…{}]{0,44}" + LOG_VERB + r"습니다[.!]?(\{p\})?$")
LOG_PRON = re.compile(
    r"여러분|님[,.\s께]|당신|너희|저희|제가|저는|우리|그대|왕자님|오셨|주십시오|하겠습니다|드리|뵙|주셨|하셨|계십|십니다|시겠"
)
# 현재형 해설(`문에는 자물쇠가 걸려 있습니다`) — 정발이 해설 높임말을 쓰던 자리라 문두로 가린다.
LOG_NARR_HEAD = re.compile(r"^(문에는|석비에는|석비가) ")


def is_log_text(t):
    """주입 표지 없는 **시스템·행동 로그·해설** 문안인가 — 평어체로 올릴 대상."""
    tt = t.replace("\n", " ").replace("\x1a", "").replace("\x17", "")
    sents = [x.strip() for x in re.split(r"(?<=[.!])\s+|\{p\}", tt) if x.strip()]
    if not sents:
        return False
    if LOG_NARR_HEAD.match(sents[0]):
        return all(x.endswith(("있습니다.", "없습니다.")) for x in sents)
    return all(LOG_SENT.match(x) and not LOG_PRON.search(x) for x in sents)


def to_plain_text(t):
    """정중 평서 → 평어체. 과거(`ㅆ` 받침 + 습니다)와 현재 `있습니다·없습니다` 만 다룬다."""
    t = re.sub(
        r"([\uAC00-\uD7A3])습니다",
        lambda m: m.group(1) + "다" if (ord(m.group(1)) - 0xAC00) % 28 == 20 else m.group(0),
        t,
    )
    return re.sub(r"(있|없)습니다", r"\1다", t)


def scan(track):
    bad, total = [], 0
    for p in sorted(SCRIPT.glob(f"{track}SCN*.json")):
        for k, v in json.loads(p.read_text(encoding="utf-8")).items():
            if not isinstance(v, dict):
                continue
            t = v.get("t") or ""
            if not (any(m in t for m in INJECT) or is_log_text(t)):
                continue
            total += 1
            tail = t.rstrip().rstrip("}pn{").rstrip()
            if STATEMENT.search(tail):
                bad.append((p.stem, k, t[:60]))
    return total, bad


def main():
    t1, bad1 = scan("ED1")
    t2, bad2 = scan("ED2")
    bad = bad1 + bad2
    if bad:
        print(f"  ❌ 로그 부류 {len(bad)}곳이 정중체 — 이 부류는 평어체다(마스터 10-03)")
        for s, k, t in bad[:20]:
            print(f"       {s}:{k}  {t!r}")
    else:
        print(f"  ✅ 로그 부류 문체 고름 — ED1 {t1} · ED2 {t2}블록 전부 평어")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
