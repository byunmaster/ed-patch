"""인게임 음성 자막 — 스크립트에 **칸**을 끼우고, 그리기는 `subtitle_stub` 이 한다.

    python3 games/ss-ed3/tools/voice_sub.py --plan          # 무엇을 어디에 넣나 (안 굽는다)

빌드에 물려 있다 — `build.py` 가 맵마다 `patch()` 를 부르고, `/0.BIN` 에는
`subtitle_stub.patch()` 로 스텁·훅을 넣는다. 이 파일은 **맵 쪽**(칸 + 글자 표)만 안다.

🔴 **길이를 안 늘리고 포인터도 안 옮긴다.** 스크립트에 흐름 제어가 있어서 가능하다
   (`/0.BIN` 디스패치 표 `0x0600ce20`, 갈래 `0xFD`):

       FD 00 <BE32>   GOTO     32비트를 PC 에 그대로 넣는다      6바이트
       FD 01 <BE32>   CALL     복귀주소를 스택에 밀고 점프       6바이트
       FD 02          RETURN   스택에서 꺼내 PC 로               2바이트

   후킹 지점의 명령 하나(≥6바이트)를 `FD 00 <우리칸>` 으로 덮고, 우리 칸에서 **밀어낸
   명령을 그대로 실행한 뒤** 한 프레임 쉬고 `FD 00` 으로 돌아온다.
   ⇒ 원래 동작을 하나도 안 잃고, 스크립트 길이가 1바이트도 안 변한다.

🔴 **칸은 32B 정렬**이다 — 스텁이 스크립트 PC 전역(`0x0609408C`)을 읽어 `PC & ~31` 을
   칸으로 삼고, 칸+24 의 서명(`SUB!`)이 맞으면 칸+28 의 포인터가 가리키는 글자를 띄운다
   (`subtitle_stub.MAGIC_OFF`·`PTR_OFF`). ⚠ 트램펄린은 한 프레임에 지나가므로 `FF 35 0001`
   (한 프레임 대기)로 **PC 를 칸 안에 머물게** 한다. 열세 칸이면 13 프레임(0.2 초)이다.
   ⇒ 스텁은 맵을 모른다. 워크램에 값을 쓰는 옵코드를 찾을 필요도 없다.

       [밀어낸 옵코드 ≤14B][FF 35 00 01][FD 00 <복귀>][0…][SUB!][글자 포인터]   = 32B

🔴 **글자는 파일 끝 「섹터 여백」에 붙인다.** MAP076.BIN 은 119,008B 인데 디스크에서
   59섹터(120,832B)를 차지한다 — 그 1,824B 는 자기 익스텐트 안의 패딩이라 앞뒤 파일과
   안 겹친다(실측: MAP075.FON 이 LBA 22610 에서 끝나고 MAP076.ED3 가 22669 에서 시작).
   ⚠ 파일 **안**의 0런(12.5KB)은 쓰지 않는다 — 「0런 3중 검증을 통과해도 사운드 뱅크
     안이라 효과음이 조용히 깨진」 전례가 있다. 섹터 여백은 그 위험이 없다.
   ⇒ 대신 **ISO 디렉터리 레코드의 크기**를 같이 늘려야 엔진이 그만큼 읽어 온다
     (`dir_record()` — `build.py` 가 그 섹터를 같이 고친다).

   글자 한 벌 = `<표시 프레임 수 BE16> <얼굴 BE16> <표정 BE16>` + `이름\\0` + `줄\\0줄\\0…\\0`.
   **짝수 정렬**(스텁이 `mov.w` 로 읽는다). 첫 줄이 비어 있으면(`lines: []`) **닫는 칸**이다.
   얼굴은 `speaker` 에서 온다 — 0x14 미만(전역 인물)이면 그 번호, 아니면 없음(0xFFFF).
   이름은 `who` 다(엔진 대사창처럼 첫 줄에 색 14 로 — 그래서 본문은 두 줄까지).

🔴 **얼굴은 음성 전에 미리 싣는다** — `"preload": true` 후킹 하나가 장면의 얼굴 전부를
   `<0xFFFF> <얼굴 표정>… <0xFFFF 0>` 목록으로 스텁에 넘긴다(`by_map()` 이 장면에서 모은다).
   얼굴 그림은 CD 에서 오는데 음성(`FF 42`)이 흐르는 동안은 CD 가 음성 것이라 로드가 영영
   안 끝난다(2026-09-05 실측). 스텁은 목록을 한 장씩 켰다 캐시에 실리는 순간 꺼서 **그리지
   않고 캐시만** 채운다(`subtitle_stub`). 자리는 **음성 앞의 긴 대기**(V01: `0x1bc1a` 의
   `FF 35 003c`, 61 프레임)에 걸어 그 대기 동안 싣는다 — 얼굴 한 장에 ~12 프레임이다.

✅ **인게임에서 확인했다**(2026-09-04, MAP076 순례의 아침). 창은 컷신 위에 뜨고 입력으로
   안 닫힌다 — 표시 시간이 지나면 저절로 사라진다(아래 「표시 시간」).

🔴 **같은 화자가 이어지면 창을 새로 안 띄운다**(유저 요청 2026-09-06, 인게임 확인 뒤) —
   엔진 대사창처럼 줄을 밀어 올려 **이어 붙인다**(`link()`). 스텁은 안 고쳤다: 칸마다 앞
   칸의 줄을 함께 실어 보내고 앞 칸을 「다음 칸까지」(프레임 0)로 붙잡을 뿐이다.
   화제가 바뀌어 새로 띄우고 싶으면 그 칸에 `"new": true`. `--plan` 이 「↳ 이어 붙인다」·
   「⤒붙잡음」으로 보여 준다 — ⚠ **붙잡은 창은 다음 칸까지 안 닫히므로**, 사이가 길게
   비는 자리(몇 초 침묵)라면 `new` 를 준다.
"""

import argparse
import json
import os
import struct
import sys
from itertools import pairwise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import common as C
import hangul_map as H
import subtitle_stub as SS
import typeset as T

SCRIPT = os.path.join(C.GAME_DIR, "script", "voice.json")
BASE = 0x200000  # 스크립트 포인터 기준 (mapfile.BASE 와 같다)
SECTOR = 2048
GOTO = b"\xfd\x00"
WAIT1 = b"\xff\x35\x00\x01"  # 한 프레임 대기 — 스텁이 PC 를 볼 시간
SLOT = SS.SLOT
FPS = 60
#   ⚠ 글자 버퍼가 216px(`subtitle_stub.BUF_STRIDE`) 이라 한 줄 18 전각이 물리 한계다.
#     대사창(17)보다 한 칸 넓지만 여백이 없다 — 넘으면 조용히 잘린다.
MAX_COLS = SS.BUF_STRIDE * 2 // 12
MAX_LINES = SS.MAX_LINES  # 이름 줄까지 — 본문은 이름이 있으면 하나 적다
NO_FACE = 0xFFFF
#   엔진의 얼굴 캐시 = `(얼굴<<8)|표정` 열쇠 **8 칸 순환표**(조회 `0x060107E4`, 표 `0x002F8E24`, 커서 `0x002F8E34`).
#   없는 열쇠를 찾으면 그 자리에 새로 잡고(가장 오래된 칸을 밀어냄) CD 를 탄다 — 음성 중엔 CD 가 음성 몫이라
#   로드가 안 끝나고, 그 조회가 남의 칸을 밀어내 연쇄로 얼굴이 사라진다(09-30 V19 실측: 10 종 → 42초 뒤 전멸).
FACE_CACHE = 8
GLOBAL_CAST = 0x14  # 이 미만의 `speaker` 가 전역 인물(얼굴이 있다)
PRELOAD = 0xFFFF  # 프레임 자리에 이것이 오면 미리 싣기 목록


#   ── 표시 시간 ────────────────────────────────────────────────────────────
#   🔴 **`FF 35` 로 붙잡아 시간을 주면 안 된다** — 그만큼 장면이 늘어지는데 음성은 제
#     속도로 흐른다(2026-08-31). 창은 스텁이 **프레임 수를 세서** 스스로 닫는다 — 스크립트는
#     1 프레임만 머물고 지나가므로 장면에 더해지는 시간은 칸당 1 프레임뿐이다.
#   ⓘ 시간은 글자 수로 어림한다 — 음성 구간(VAD)을 직접 재는 것보다 거칠지만 **다음 칸이
#     오면 어차피 갈아 끼우므로** 길게 잡아도 겹치지 않는다. 짧은 침묵에는 창이 사라진다.
#     정본에 `dur`(초)를 적으면 그걸 쓴다. `dur: 0` 은 「다음 칸까지」다.
#   🔴 **장면의 마지막 칸은 0 이면 안 된다** — 뒤에 갈아 끼울 칸이 없어 창이 다음 맵까지
#     남는다(`plan()` 이 막는다).
DUR_BASE, DUR_PER_CHAR = 0.9, 0.22


def duration(h):
    """초 — 정본의 `dur` 가 우선, 없으면 글자 수 어림."""
    if "dur" in h:
        return float(h["dur"])
    return DUR_BASE + DUR_PER_CHAR * sum(len(t) for t in h["lines"])


def face(h):
    """`(얼굴, 표정)` — `face` 가 있으면 그것, 없으면 `speaker` 가 전역 인물일 때만."""
    if "face" in h:
        return (NO_FACE, 0) if h["face"] is None else (int(h["face"]), int(h.get("expr", 0)))
    sp = h.get("speaker")
    if sp is None or sp >= GLOBAL_CAST:
        return NO_FACE, 0
    return int(sp), int(h.get("expr", 0))


#   🔴 음성 자막의 `?`·`!` 는 **전각**으로 찍는다(마스터 10-01 「물음표 느낌표가 작다」) — 반각은 ASCII 글리프(6px)라 한글(12px)
#   옆에서 작아 보인다. 전각 칸은 엔진 일본어 글리프(`？！`)를 쓴다.
_FW = str.maketrans({"?": "？", "!": "！"})


def fw(t):
    return t.translate(_FW)


def entry(h, table=None):
    """글자 한 벌 — `<프레임> <얼굴> <표정>` + 이름 + 줄들(NUL 종결) + NUL. 짝수 길이.

    `preload` 후킹이면 `<0xFFFF>` + `_faces` 쌍들 + `<0xFFFF 0>` 목록이다.
    """
    if h.get("preload"):
        if h.get("lines") or h.get("delay"):
            raise SystemExit(f"{h['off']:#x}: 미리 싣기 칸엔 글자도 `delay` 도 못 둔다")
        out = struct.pack(">H", PRELOAD)
        out += b"".join(struct.pack(">HH", *p) for p in h.get("_faces", ()))
        return out + struct.pack(">HH", NO_FACE, 0)
    lines = h.get("_body", h["lines"])
    who = h.get("who", "") if lines else ""
    room = MAX_LINES - (1 if who else 0)
    if len(lines) > room:
        raise SystemExit(f"{h['off']:#x}: 줄이 {room} 을 넘는다({len(lines)}) — 이름 줄 몫을 뺀다")
    lines = [fw(t) for t in lines]
    for t in [who, *lines]:
        if "\n" in t:
            raise SystemExit(f"{h['off']:#x}: 줄 안에 개행 — `lines` 를 나눠 적는다: {t!r}")
        if T.cols(t) > MAX_COLS:
            raise SystemExit(f"{h['off']:#x}: 한 줄 {MAX_COLS} 칸까지다({T.cols(t)}): {t!r}")
    #   같은 화자가 이어지면 **창을 안 닫는다** — 다음 칸이 갈아 끼울 때까지 붙잡는다(0).
    frames = 0 if not lines or h.get("_hold") else round(duration(h) * FPS)
    if not 0 <= frames < PRELOAD:
        raise SystemExit(f"{h['off']:#x}: 표시 시간이 범위 밖이다 ({frames} 프레임)")
    fid, expr = face(h) if lines else (NO_FACE, 0)
    out = struct.pack(">HHH", frames, fid, expr)
    out += H.encode_kr(who, table) + b"\x00"
    out += b"".join(H.encode_kr(t, table) + b"\x00" for t in lines) + b"\x00"
    return out + b"\x00" * (len(out) % 2)


#   🔴 **후킹 지점의 길이는 「그 처리기가 PC 에 쓰는 자리를 전부」 보고 정한다.**
#     표를 믿지 말 것 — 자리마다 길이가 다른 옵코드가 실재한다(`FF 36`·`FF 0A`,
#     `script_ops.py` 참조). 예컨대 `FF 07` 은 처리기 `0x06011608` 안에서 PC 저장이
#     `0x0601170c` 한 곳뿐이고 거기서 항상 `+12` 라 분기와 무관하게 2+12=14 고정이다
#     (2026-08-30 확인). 자리를 새로 잡을 땐 같은 검산을 다시 한다(`script_ops.py --path`).
def slot(orig, ret_off, txt_off, frames=2):
    """칸 32B — 밀어낸 옵코드 · 대기(기본 2 프레임 = `FF 35 0001`) · 복귀 · 서명 · 글자 포인터.

    `frames` 는 `preload` 후킹의 `wait` 다 — 얼굴 한 장에 ~12 프레임이라 음성 앞에 긴 대기가
    없는 장면은 여기서 (얼굴 수 × 12 + 여유) 만큼 멈춰 CD 가 얼굴을 다 싣게 한다.
    """
    return _slot(orig + (WAIT + struct.pack(">H", frames - 1)), BASE + ret_off, txt_off)


def _slot(body, goto, txt_off=None):
    """칸 32B — `body` 뒤에 `FD 00 <goto>`, 글자가 있으면 끝에 서명 + 포인터."""
    blk = body + GOTO + struct.pack(">I", goto)
    if len(blk) > SS.MAGIC_OFF:
        raise SystemExit(f"칸에 안 든다({len(blk)}B) — 밀어낸 옵코드가 길다")
    blk = blk.ljust(SS.MAGIC_OFF, b"\x00")
    if txt_off is None:
        blk = blk.ljust(SLOT, b"\x00")
    else:
        assert txt_off % 2 == 0
        blk += struct.pack(">II", SS.MAGIC, BASE + txt_off)
    assert len(blk) == SLOT
    return blk


#   ── 대기 한복판에 넣기 ───────────────────────────────────────────────────
#   🔴 **음성은 옵코드 경계에 안 맞춰 온다.** V01 실측(2026-09-04): 대사 19 마디 중 옵코드
#     디스패치에 걸리는 건 넷뿐이고 나머지는 `FF 35 <n>`(n+1 프레임 대기) **한복판**에서
#     시작한다(7 초짜리 대기 안에 두 마디가 든다). 그래서 대기를 **쪼갠다** —
#     같은 `off` 의 후킹 여럿이 `delay`(디스패치로부터 프레임)로 갈려 **칸 사슬**이 된다:
#
#       자리: [앞 옵코드들][FF 35 n]…   →   칸0 [앞 옵코드들][FF 35 d1-1][FD 00 칸1]
#                                          칸1 [FF 35 d2-d1-1][FD 00 칸2] +서명+글자1
#                                          칸2 [FF 35 W-d2-1 ][FD 00 복귀] +서명+글자2
#
#     총 대기 W 는 그대로다(`FF 35 n` = n+1 프레임이라 조각마다 1 을 뺀다). 서명 칸은 최소
#     한 프레임 머문다(스텁이 PC 를 볼 시간). 뒤 옵코드 `FF 35` 만 쪼갠다 — `FF 37` 은
#     뜻이 아직 안 읽혀서 안 건드린다.
#   ⚠ 스텁은 **같은 포인터를 다시 안 켠다**(`subtitle_stub`) — 그래서 서명 칸에서 표시
#     시간이 다 돼 꺼져도 다음 프레임에 도로 켜지지 않는다.
WAIT = b"\xff\x35"


def split_waits(orig):
    """`(앞 옵코드들, 뒤 `FF 35` 대기들의 프레임 합)` — 뒤에서부터 `FF 35 nn nn` 을 벗긴다."""
    pre, total = orig, 0
    while len(pre) >= 4 and pre[-4:-2] == WAIT:
        total += struct.unpack(">H", pre[-2:])[0] + 1
        pre = pre[:-4]
    return pre, total


def wait(frames):
    assert frames >= 1
    return WAIT + struct.pack(">H", frames - 1)


def chain(orig, ret_off, subs, txt_offs):
    """같은 자리의 후킹 사슬 → 칸들(bytes 목록). `subs` 는 `delay` 오름차순, 첫 칸이 입구."""
    pre, total = split_waits(orig)
    ds = [int(h.get("delay", 0)) for h in subs]
    if len(subs) == 1 and ds[0] == 0:
        return [slot(orig, ret_off, txt_offs[0], int(subs[0].get("wait", 2)))]
    off = subs[0]["off"]
    if not total:
        raise SystemExit(f"{off:#x}: `delay` 를 쓰려면 자리 뒤가 `FF 35` 대기여야 한다")
    if any(b <= a for a, b in pairwise(ds)) or ds[0] < 0:
        raise SystemExit(f"{off:#x}: `delay` 는 오름차순이어야 한다: {ds}")
    if ds[-1] >= total:
        raise SystemExit(f"{off:#x}: `delay` {ds[-1]} 이 대기 {total} 프레임을 넘는다")
    #   칸 주소는 아직 모른다 — 자리표시자로 두고 `plan()` 이 채운다. 여기선 (본문, 글자) 만
    parts = []  # [(본문, 글자 오프셋 또는 None)]
    if pre or ds[0] > 0:
        parts.append((pre + (wait(ds[0]) if ds[0] > 0 else b""), None))
    for i, d in enumerate(ds):
        nxt = ds[i + 1] if i + 1 < len(ds) else total
        parts.append((wait(max(nxt - d, 1)), txt_offs[i]))
    return parts


#   ── 같은 화자는 창을 새로 안 띄운다 (유저 요청 2026-09-06) ───────────────
#   🔴 **창을 닫았다 여는 게 눈에 띈다** — 인게임 확인에서 「다음 대사가 이어지면 창이
#     닫히고 새로 뜬다」는 지적이 나왔다. 엔진 대사창처럼 **줄을 밀어 올려 이어 붙인다.**
#   방법은 자료 쪽뿐이다(스텁을 안 고친다) — 칸마다 **앞 칸의 줄을 함께** 실어 보내고,
#   앞 칸의 표시 프레임을 **0(다음 칸까지)** 으로 바꿔 그 사이에 창이 안 닫히게 한다.
#     ⇒ 스텁은 여전히 「칸 하나 = 창 한 벌」만 안다. 스크롤은 **우리가 미리 굴려 둔 그림**이다.
#   판정은 **화자(`who`) + 얼굴**이 같고 바로 다음 칸일 때. 화제가 바뀌어 새로 띄우고
#   싶으면 그 칸에 `"new": true` 를 적는다.
#   ⚠ 창은 이름 줄을 빼면 두 줄이라, 세 줄째가 오면 **맨 위가 밀려 나간다**(그게 스크롤이다).
#   🔴 **짧게 뜨고 사라지는 창은 앞뒤 대사와 한 창으로 묶는다**(마스터 10-01 — 「방금 알아챘어」「하지만 말이야」가 금방
#   사라져 못 읽는다). 스크롤은 안 쓴다(마스터가 뺐다) — **다음 창이 앞 창의 줄을 함께 싣는다**. 앞·뒤 칸 중 하나가
#   `MERGE_SHORT` 초보다 짧고 같은 화자·얼굴·자리이고 사이가 `MERGE_GAP` 초 안이면 `reflow` 로 두 줄 안에 다시 접는다
#   (안 들어가면 묶지 않는다). 접기는 문장·쉼표 뒤를 우선한다.
MERGE_SHORT = 2.0
MERGE_GAP = 1.5
HOLD_GAP = 1.5  # 같은 화자라도 말 사이가 이만큼 넘게 비면 창을 닫고 새로 띄운다
_ENDS = (".", "?", "!", "？", "！", ",", "…", "~")


def reflow(segments, room):
    """줄들을 이어 `room` 줄 이내·줄당 `MAX_COLS` 칸 이내로 다시 접는다 → 줄 목록 또는 `None`(안 들어감)."""
    words = [fw(w) for seg in segments for w in seg.split()]
    best = None
    for k in range(0 if room >= 1 else 1, len(words)):
        # k = 첫 줄 어절 수(0 이면 한 줄)
        rows = [" ".join(words)] if k == 0 else [" ".join(words[:k]), " ".join(words[k:])]
        if len(rows) > room or any(T.cols(r) > MAX_COLS for r in rows):
            continue
        score = -abs(T.cols(rows[0]) - T.cols(rows[-1])) if len(rows) > 1 else 0
        if len(rows) > 1 and words[k - 1].endswith(_ENDS):
            score += 100 + (50 if words[k - 1][-1] in ".?!？！…" else 0)
        if len(rows) == 1:
            score += 200  # 한 줄에 들어가면 그게 낫다
        if best is None or score > best[0]:
            best = (score, rows)
    return best[1] if best else None


def _close(a, b):
    """같은 화자·얼굴·자리이고 사이가 `MERGE_GAP` 초 안인 이웃인가."""
    return bool(
        a.get("who")
        and a.get("who") == b.get("who")
        and face(a) == face(b)
        and a["off"] == b["off"]
        and (int(b.get("delay", 0)) - int(a.get("delay", 0))) / FPS - a.get("_dur0", a.get("dur", 0)) < MERGE_GAP
    )


_TERMINAL = (".", "?", "!", "…", "~", "」", ")")


def _merge_short(hooks, order):
    """짧은 칸을 이웃과 한 창으로 — **글이 이어지면(쉼표·미완) 뒤 칸과, 문장이 끝났으면 앞 칸과** 묶는다.

    뒤 칸과 묶으면 **앞 칸 때부터** 합친 글을 띄우고(앞 칸 표시 시간을 뒤 칸 시작까지 늘린다) 뒤 칸도 같은 글이다 —
    같은 줄이 두 창에 겹쳐 나오지 않게(마스터 10-01 「하지만 말이야가 두 대사에 겹쳐서」). 한 칸은 한 번만 묶인다.
    """
    seq = [hooks[i] for i in order if hooks[i].get("lines") and not hooks[i].get("preload")]
    for h in seq:
        h.pop("_m", None)
        h["dur"] = h.setdefault("_dur0", h.get("dur", 9))  # 늘린 표시 시간을 되돌려 몇 번을 불러도 같다
    for i, h in enumerate(seq):
        if h.get("_m") or h["_dur0"] >= MERGE_SHORT:
            continue
        room = MAX_LINES - (1 if h.get("who") else 0)
        nxt = seq[i + 1] if i + 1 < len(seq) else None
        prev = seq[i - 1] if i > 0 else None
        cont = not h["lines"][-1].rstrip().endswith(_TERMINAL)
        if cont and nxt and not nxt.get("_m") and _close(h, nxt):
            m = reflow(h["lines"] + nxt["lines"], room)
            if m:
                span = (int(nxt.get("delay", 0)) - int(h.get("delay", 0))) / FPS
                h["_body"] = nxt["_body"] = m
                h["_m"] = nxt["_m"] = True
                h["dur"] = max(h["_dur0"], round(span, 2))
                continue
        if prev and not prev.get("_m") and _close(prev, h):
            m = reflow(prev["lines"] + h["lines"], room)
            if m:
                h["_body"] = m
                h["_m"] = True


def link(hooks, order):
    """`_body`(이어 붙인 본문) · `_hold`(앞 칸을 다음 칸까지 붙잡기) 를 매긴다."""
    prev = None
    _merge_short(hooks, order)
    for i in order:
        h = hooks[i]
        if h.get("preload") or not h.get("lines"):
            prev = None  # 닫는 칸·미리 싣기에서 사슬이 끊긴다
            continue
        #   🔴 같은 화자가 이어지면 **창·얼굴은 그대로 두고 글만 바꾼다**(마스터 10-01 — 스크롤은 안 한다). 앞 칸을 다음 칸까지
        #     붙잡고(`_hold`) 뒤 칸은 **자기 줄만** 띄운다. 창이 새로 뜨는 건 **화자가 바뀔 때, 또는 말 사이가 `HOLD_GAP` 초 넘게 비었을 때**다(마스터 10-01).
        same = (
            prev is not None
            and not h.get("new")
            and h.get("who", "")
            and h.get("who") == prev.get("who")
            and face(h) == face(prev)
            #   말 사이가 `HOLD_GAP` 초 넘게 비면(뜸을 들이면) 닫고 새로 띄운다 — 자리가 다르면 간격을 못 재니 이어진 것으로 본다
            and (
                h["off"] != prev["off"]
                or (int(h.get("delay", 0)) - int(prev.get("delay", 0))) / FPS - prev.get("_dur0", prev.get("dur", 0)) < HOLD_GAP
            )
        )
        room = MAX_LINES - (1 if h.get("who") else 0)
        if h.get("_m"):
            pass  # 짧은 칸 묶음(`_merge_short`)이 이미 몸통을 정했다
        elif same:
            h["_body"] = list(h["lines"])  # 앞 줄을 싣지 않는다 — 스크롤이 아니라 **교체**
            prev["_hold"] = True
        else:
            h["_body"] = list(h["lines"])
        prev = h


def plan(raw, hooks, table=None):
    """`(붙일 꼬리, [(오프셋, 덮을 6B)])` — 칸들 뒤에 글자 표.

    꼬리는 **옛 파일 끝을 32B 로 올린 자리**부터 시작한다(칸 정렬). 각 후킹은 자기 칸으로
    점프하고, 칸의 포인터는 그 뒤 글자 표의 제 벌을 가리킨다. 같은 `off` 의 후킹들은
    `delay` 순으로 **칸 사슬**이 된다(위 「대기 한복판에 넣기」).
    """
    if not hooks:
        return b"", []
    n = len(raw)
    start = -(-n // SLOT) * SLOT
    #   보이는 차례 = (자리, `delay`) — 칸 사슬 안 순서까지 맞춘다
    link(
        hooks,
        sorted(range(len(hooks)), key=lambda i: (hooks[i]["off"], int(hooks[i].get("delay", 0)))),
    )
    texts = [entry(h, table) for h in hooks]
    if hooks[-1].get("lines") and texts[-1][:2] == b"\x00\x00":
        raise SystemExit(
            f"{hooks[-1]['off']:#x}: 마지막 칸은 `dur` 가 0 이면 안 된다 — 창이 남는다"
        )
    #   자리별로 묶는다 — 같은 자리는 길이가 같아야 한다
    sites = []
    for i, h in enumerate(hooks):
        if h["len"] < len(GOTO) + 4:
            raise SystemExit(f"{h['off']:#x}: 후킹 지점이 짧다({h['len']}B) — GOTO 6B 가 안 든다")
        if sites and hooks[sites[-1][0]]["off"] == h["off"]:
            if hooks[sites[-1][0]]["len"] != h["len"]:
                raise SystemExit(f"{h['off']:#x}: 같은 자리의 후킹은 `len` 이 같아야 한다")
            sites[-1].append(i)
        else:
            sites.append([i])
    #   ⚠ 후킹끼리 겹치면 서로를 덮는다 — 6 바이트씩 잡아 두고 본다
    seen = sorted((hooks[s[0]]["off"], hooks[s[0]]["off"] + len(GOTO) + 4) for s in sites)
    for (a1, b1), (a2, _) in pairwise(seen):
        if a2 < b1:
            raise SystemExit(f"후킹 지점이 겹친다: {a1:#x} 와 {a2:#x}")
    #   글자 표는 칸들 뒤 — 칸 수를 먼저 센다
    chains = []
    nslots = 0
    for idxs in sites:
        idxs = sorted(idxs, key=lambda i: int(hooks[i].get("delay", 0)))
        chains.append(idxs)
        h0 = hooks[idxs[0]]
        if len(idxs) == 1 and not h0.get("delay"):
            nslots += 1
        else:
            pre, _ = split_waits(raw[h0["off"] : h0["off"] + h0["len"]])
            nslots += len(idxs) + (1 if pre or int(h0.get("delay", 0)) > 0 else 0)
    txt_at = {}
    at = start + SLOT * nslots
    for i, t in enumerate(texts):
        txt_at[i] = at
        at += len(t)
    tail = bytearray(b"\x00" * (start - n))
    patches = []
    here = start
    for idxs in chains:
        h0 = hooks[idxs[0]]
        orig = raw[h0["off"] : h0["off"] + h0["len"]]
        ret = h0["off"] + h0["len"]
        parts = chain(orig, ret, [hooks[i] for i in idxs], [txt_at[i] for i in idxs])
        patches.append((h0["off"], GOTO + struct.pack(">I", BASE + here)))
        if isinstance(parts[0], bytes):  # 홑칸
            tail += parts[0]
            here += SLOT
            continue
        for k, (body, txt) in enumerate(parts):
            nxt = here + SLOT if k + 1 < len(parts) else None
            tail += _slot(body, BASE + nxt if nxt else BASE + ret, txt)
            here += SLOT
    assert here == start + SLOT * nslots, (here, start, nslots)
    for t in texts:
        tail += t
    #   ⓘ 섹터 여백에 맞추지 않는다 — 꼬리가 붙은 맵은 `relocate.py` 가 트랙 1 끝의 새
    #     자리로 옮기므로 길이 제한이 없다(2026-09-05. 13/19 장면이 여백에 안 들었다).
    return bytes(tail), patches


def load_plan():
    if not os.path.exists(SCRIPT):
        return {}
    with open(SCRIPT, encoding="utf-8") as f:
        return json.load(f)


def by_map(doc=None):
    """`{맵 stem: [후킹…]}` — 한 맵에 장면이 여럿이면 오프셋 순으로 잇는다.

    장면마다 쓰는 얼굴을 모아 그 장면의 `preload` 후킹에 `_faces` 로 붙인다. 얼굴을 쓰는데
    미리 싣기 자리가 없으면 실패한다 — 음성 중엔 얼굴이 CD 를 못 타서 영영 안 뜬다.
    """
    doc = load_plan() if doc is None else doc
    out = {}
    for key, ent in sorted(doc.items()):
        if key.startswith("_"):
            continue
        hooks = [dict(h, _scene=key) for h in ent["hooks"]]
        faces = sorted({face(h) for h in hooks if h.get("lines")} - {(NO_FACE, 0)})
        pres = [h for h in hooks if h.get("preload")]
        if len(pres) > 1:
            raise SystemExit(f"{key}: 미리 싣기 후킹은 장면에 하나다")
        if faces and not pres:
            raise SystemExit(f"{key}: 얼굴 {faces} 을 쓰는데 `preload` 후킹이 없다")
        if len(faces) > FACE_CACHE:
            raise SystemExit(
                f"{key}: (얼굴, 표정) 조합이 {len(faces)} 종이라 엔진 캐시({FACE_CACHE} 칸)를 넘는다 — "
                f"넘친 조합은 밀려나고, 밀려난 것을 찾는 조회가 다른 칸까지 연쇄로 밀어 얼굴이 통째로 사라진다"
            )
        for h in pres:
            if any(o["off"] == h["off"] for o in hooks if o is not h):
                raise SystemExit(f"{key}: 미리 싣기 칸 {h['off']:#x} 은 혼자여야 한다")
            h["_faces"] = faces
        out.setdefault(ent["map"], []).extend(hooks)
    for hooks in out.values():
        hooks.sort(key=lambda h: h["off"])
    return out


def patch(data, stem, hooks, table=None):
    """맵 바이트 → `(후킹이 덮인 본문 + 꼬리, 칸 수)`. 꼬리만큼 **길어진다**."""
    tail, patches = plan(data, hooks, table)
    out = bytearray(data)
    for off, by in patches:
        out[off : off + len(by)] = by
    return bytes(out) + tail, len(hooks)


def dir_record(d, path_in_iso):
    """`(레코드가 든 섹터 LBA, 그 섹터 안 오프셋)` — 그 파일의 ISO 디렉터리 레코드 자리.

    ⚠ 디렉터리는 **여러 섹터**다(`/MAP` 은 352 항목). 익스텐트 첫 섹터만 읽고 오프셋을
      그대로 쓰면 엉뚱한 자리를 고친다 — 섹터 단위로 쪼개 돌려준다.
    """
    want = path_in_iso.rsplit("/", 1)[1].encode("ascii")
    root = d.pvd()[156 : 156 + 34]
    stack = [(int.from_bytes(root[2:6], "little"), int.from_bytes(root[10:14], "little"), "")]
    while stack:
        lba, size, path = stack.pop()
        data = d.read_extent(lba, size)
        pos = 0
        while pos < len(data):
            rl = data[pos]
            if rl == 0:
                pos = (pos // SECTOR + 1) * SECTOR
                continue
            rec = data[pos : pos + rl]
            name = rec[33 : 33 + rec[32]]
            full = f"{path}/{name.decode('ascii', 'replace').split(';')[0]}"
            if name not in (b"\x00", b"\x01"):
                if rec[25] & 0x02:
                    stack.append(
                        (
                            int.from_bytes(rec[2:6], "little"),
                            int.from_bytes(rec[10:14], "little"),
                            full,
                        )
                    )
                elif full == path_in_iso and name.split(b";")[0] == want:
                    return lba + pos // SECTOR, pos % SECTOR
            pos += rl
    raise KeyError(path_in_iso)


def resize_record(sector, off, old_size, new_size):
    """디렉터리 섹터 안 레코드의 크기(양끝 엔디언 8B)를 늘린 새 섹터."""
    rec = sector[off : off + 34]
    want = struct.pack("<I", old_size) + struct.pack(">I", old_size)
    assert rec[10:18] == want, rec[10:18].hex()
    out = bytearray(sector)
    out[off + 10 : off + 18] = struct.pack("<I", new_size) + struct.pack(">I", new_size)
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--disc", type=int, default=1)
    a = ap.parse_args()
    if not a.plan:
        ap.error("--plan")
    with C.open_disc(a.disc) as d:
        for stem, hooks in sorted(by_map().items()):
            iso = f"/MAP/{stem}.BIN"
            _, lba, size = d.find(iso)
            raw = d.read_extent(lba, size)
            tail, _patches = plan(raw, hooks)
            start = -(-size // SLOT) * SLOT
            print(f"── {iso}  {size:,}B → {size + len(tail):,}B  (여백 {(-size) % SECTOR}B)")
            at = start + SLOT * len(hooks)
            for i, h in enumerate(hooks):
                e = entry(h)
                fr, fid, _ = struct.unpack(">HHH", e[:6])
                tag = (
                    f"미리 싣기 {h.get('_faces')}"
                    if fr == PRELOAD
                    else f"{fr / FPS:4.1f}초"
                    + ("  ⤒붙잡음" if h.get("_hold") else "")
                    + (f"  얼굴 {fid}" if fid != NO_FACE else "")
                )
                print(
                    f"   {h['_scene']} 후킹 {h['off']:#07x} ({h['len']:2}B) → 칸 {start + SLOT * i:#07x}"
                    f"  글자 {at:#07x} {len(e):3}B  {tag}"
                )
                if h.get("who") and h.get("lines"):
                    carry = len(h.get("_body", ())) - len(h["lines"])
                    print(
                        f"        [{h['who']}]" + ("  ↳ 앞 창에 이어 붙인다" if carry > 0 else "")
                    )
                for t in h.get("_body", h.get("lines", ())):
                    print(f"        {t!r}")
                at += len(e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
