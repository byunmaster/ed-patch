#!/usr/bin/env python3
"""**이어 그려지는 블록 경계가 성한가** — 앞 블록 꼬리에 뒷 블록 머리가 붙는 자리를 본다.

**왜.** 원작은 한 문장을 **블록 둘로 갈라** 두고, 앞 블록이 개행도 창 종료도 없이 끝나면
엔진이 뒷 블록을 **같은 줄에 이어 그린다**. 그런데 조판은 블록마다 따로 돈다 — 경계 너머를
모른다. 그래서 두 가지가 조용히 샌다(둘 다 유저 QA 로 잡혔다, 2026-08-12):

- **붙음** — `말일세,` + `현자답지` 가 `말일세,현자답지` 로 나온다. 정본에는 공백이 멀쩡히
  있는데도 그렇다. 경계는 문안이 아니라 **블록 사이**라 어느 쪽 문안에도 안 보인다.
  전수 **71곳**이었다.
- **넘침** — 붙여 놓고 보니 그 줄이 창 폭을 넘는다(`이 100점을` + `체력, 공격력, 방어력,`
  = 19슬롯). 엔진이 제 맘대로 꺾어 `이 100체력` 같은 꼴이 되고, 꺾인 자리의 공백이 다음 줄
  **선두에 남아 들여쓰기처럼 보인다**.
- **선두 공백** — 앞 블록이 개행으로 끝나는데 뒷 블록이 공백으로 시작한다. 붙음을 막으려고
  넣은 공백이, 나중에 그 경계에 꼬리 개행이 붙으면서 갈 곳을 잃은 것이다.
- **들여쓰기** — 블록 **안**에서 개행 뒤 줄이 공백으로 시작한다. 이름창(`%c이름%c`) 뒤가
  대부분이다 — 원문이 이름과 본문을 공백으로 갈라 둔 흔적이고, 시점 사본 중 **일부에만**
  남아 같은 대사가 캐릭터에 따라 들여쓰였다 갔다 한다(유저 QA 2026-08-13, 8곳).

**고치는 법.** 붙음은 뒷 블록 **선두에 붙임 공백**(`\\ue003`)을 넣는다 — 보통 공백은
`.strip()` 에 지워지고 선두 개행은 빈 줄이 되어 조판이 버린다(둘 다 실측).
넘침은 앞 블록에 **꼬리 개행**(오버라이드 `trail_nl`)을 붙여 우리가 먼저 끊는다 — 엔진이
꺾게 두지 않는다. ⚠ 개행은 줄을 하나 더 쓰므로 **창을 넘길 수 있다**(`ED1SCN4 jp640` 은
넣으면 이어 7줄이 된다) — 넣은 뒤 `check_tail_cut` 을 반드시 본다. 그 자리는 대신 양쪽
문안을 `{n}` 으로 끊어 경계 폭을 맞춘다. 선두 공백은 그냥 지운다.

⚠ **게이트다.** 둘 다 화면에 바로 보이고, 고치는 법이 정해져 있다.

  python3 tools/check_block_join.py            # 전 씬
  python3 tools/check_block_join.py ED1SCN3    # 한 씬
"""

import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from patch_sys_ui import SCN_FILES

NOBREAK_SP = R.NOBREAK_SP
WRAP = R.WRAP


def _w(s):
    """화면 폭(슬롯). ⚠ `%c` 는 **화면에 안 그려지는 제어**라 빼고 센다 — 넣으면 창 종단이
    붙은 블록마다 2슬롯씩 부풀어 멀쩡한 줄이 넘침으로 뜬다(실측 2026-08-12).
    `%s`·`%d` 는 런타임에 이름·수치가 들어오므로 자리값으로 그대로 센다."""
    return sum(R.cell_w(c) for c in s.replace("%c", ""))


def _is_plate(raw):
    """앞 블록이 **지명·이름 플레이트**인가 — 뒤 대사에 이어 그려지지 않는다.

    씬 파일에는 대사만 있는 게 아니라 워프 목록·맵 이름 같은 **낱말 블록**이 섞여 있다
    (`리젤`+`스엘`+`콜크스`, `그로스토스성`+`그로스토스성`). 이어 그려지는 자리가 아닌데
    경계 규칙에는 걸려서 붙음으로 뜬다 — ED2 전수에서 32곳이 이 부류였다(2026-08-17).

    ⚠ **양쪽을 다 본다**(2026-08-20). 처음엔 앞 블록만 봤는데, **뒤 블록이 맵 헤더**인
    자리를 놓쳤다 — 보물상자 문구(`…들어 있었다.`) 다음에 지명(`그로스토스성`)이 오는
    꼴로 ED2 에서 다섯이 그랬다. 헤더는 앞 대사에 이어 그려지지 않으므로 경계가 아니다.

    ⚠ **조용히 빼지 않는다.** 아래에서 따로 세어 보고한다 — 규칙이 진짜 대사를 삼키기
    시작하면 그 수가 늘어나므로 눈에 띄어야 한다.
    """
    s = (raw or "").strip()
    return bool(s) and len(s) <= 8 and "\n" not in s and "%c" not in s and s[-1] not in ".!?…"


def scan(scenes=None):
    join = []  # 공백 없이 붙는 경계
    plate = []  # 낱말 플레이트라 이어 그려지지 않는 경계
    over = []  # 붙고 나서 폭을 넘는 줄
    lead = []  # 개행 뒤인데 선두 공백이 남은 블록
    indent = []  # 블록 **안**에서 개행 뒤 줄이 공백으로 시작
    for scn, _l, _z in SCN_FILES:
        if scenes and scn not in scenes:
            continue
        with redirect_stdout(io.StringIO()):
            pairs = [
                (eid, R.render_bytes(c, ctrl=True), R.render_bytes(jp.rstrip(b"\x00"), ctrl=True))
                for _s, eid, jp, c, _t in R.iter_candidates((scn,))
            ]
        rows = {eid: k for eid, k, _j in pairs}
        jps = {eid: j for eid, _k, j in pairs}
        for eid, raw in rows.items():
            # ⚠ **블록 안**의 선두 공백은 경계와 별개다. 이름창(`%c이름%c`) 뒤 개행에
            # 붙임 공백이 남으면 본문 첫 줄만 한 칸 들여쓰기돼 보인다 — 원문이 이름과
            # 본문을 공백으로 갈라 둔 흔적이라 시점 사본 중 일부에만 남는다
            # (`%c세리오스%c\n아직이다` 는 멀쩡한데 `%c류난%c\n 아직이다` 만 들여쓰였다,
            # 유저 QA 2026-08-13). 뒤에 이어 붙는 줄이 아니므로 그냥 지운다.
            for i, ln in enumerate((raw or "").split("\n")):
                if i and ln.startswith((" ", NOBREAK_SP)):
                    indent.append((scn, eid, i, ln[:16]))
            nxt = rows.get(eid + 1)
            if not raw or not nxt:
                continue
            # 앞 블록이 **개행으로** 끝나면 뒷 블록은 새 줄에서 시작한다 — 그 자리의 선두
            # 공백은 줄이 들여쓰기돼 보인다(` 현자답지 못한 짓이라고`, 유저 QA 2026-08-12).
            # 경계에 공백을 넣어 뒀다가 나중에 꼬리 개행(`trail_nl`)이 붙으면 이렇게 남는다.
            if raw.endswith("\n"):
                if nxt[:1] in (" ", NOBREAK_SP):
                    lead.append((scn, eid + 1, nxt.split("\n")[0][:16]))
                continue
            if raw.endswith("%c"):  # 창을 닫았다 — 경계가 아니다
                continue
            # 🔴 **원본도 종단 `%c` 없이 끝나면 우리 결함이 아니다.** 원본과 같은 구조를
            #    낸 것이고, 엔진이 거기서 무엇을 하든 원본에서도 똑같이 한다.
            #    ⚠ 이 축이 없으면 `drop_extra_tail_mc`(원본에 없는 종단을 떼는 장치)가
            #      고친 자리를 검출기가 「붙음」으로 오탐한다(실측 5곳, 2026-09-06).
            #      예전엔 우리가 종단을 **더 내고 있어서** 이 자리가 안 보였다.
            if not (jps.get(eid) or "").endswith("%c"):
                continue
            tail = raw.split("\n")[-1]
            head = nxt.split("\n")[0]
            # 🔴 **꽉 찬 줄(29열) 뒤는 경계가 아니다** — 엔진이 거기서 스스로 줄을 넘긴다.
            #    그래서 뒷 블록은 다음 행에서 시작하고, 붙지도 넘치지도 않는다. 이 규칙은
            #    `join_lines`/`_fills_frame` 가 이미 쓰던 것이고 **인게임으로 확인됐다**
            #    (2026-08-30 유저 QA: 꽉 찬 줄 뒤에 커서가 2행에 있어 빈 줄이 났다).
            #    ⚠ 이 줄이 없으면 `drop_frame_full_nl` 이 지운 군더더기 개행을 검출기가
            #    「붙음」으로 오탐한다(실측 10곳).
            if abs(_w(tail) - R.FRAME_SLOTS) < 1e-9:
                continue
            # ⚠ 뒷 블록이 `%c` 로 시작하면 **이름창·색 전환이 새로 열린다** — 앞 줄에 안 붙는다.
            # (`…무사하겠지!!` + `%c류난%c` 는 화자가 바뀌는 자리지 문장이 이어지는 자리가 아니다.)
            if not head or head.startswith("%c"):
                continue
            if head[0] not in (" ", NOBREAK_SP):
                bucket = plate if (_is_plate(raw) or _is_plate(nxt)) else join
                bucket.append((scn, eid, tail[-12:], head[:12]))
                continue
            if _w(tail + head) > WRAP:
                over.append((scn, eid, _w(tail + head), tail[-12:], head[:14]))
    for scn, eid, t, h in join:
        print(f"  ⚠ {scn} jp{eid}→{eid + 1} 공백 없이 붙는다: …{t!r} + {h!r}")
    for scn, eid, w, t, h in over:
        print(f"  ⚠ {scn} jp{eid}→{eid + 1} 이은 줄이 {w}슬롯(>{WRAP}): …{t!r} + {h!r}")
    for scn, eid, h in lead:
        print(f"  ⚠ {scn} jp{eid} 개행 뒤인데 선두 공백이 남았다: {h!r}")
    for scn, eid, i, h in indent:
        print(f"  ⚠ {scn} jp{eid} {i}번째 줄이 공백으로 시작한다(들여쓰기로 보인다): {h!r}")
    if plate:
        print(f"  ℹ 낱말 플레이트라 이어 그려지지 않는 경계 {len(plate)}곳 — 제외했다")
    bad = len(join) + len(over) + len(lead) + len(indent)
    print(
        f"\n{'✅ 블록 경계 이상 없음' if not bad else f'⚠ 붙음 {len(join)} · 넘침 {len(over)} · 선두 공백 {len(lead)} · 들여쓰기 {len(indent)}'}"
    )
    return bad


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(1 if scan(set(args) if args else None) else 0)
