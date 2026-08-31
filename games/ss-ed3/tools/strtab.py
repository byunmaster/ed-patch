"""NUL 로 끊기는 문자열 표 — 본체 `/0.BIN` · `/SYSTEM/*` · `/EVT` · `/BTL` 의 정본.

`MAP*.BIN` 은 스크립트라 문법이 다르다(`mapfile.py`). 여기는 **표**다 — 인명 · 챕터 제목 ·
몬스터명 · 스탯 이름 · 메뉴 · 세가새턴 저장 안내 같은 것들이 NUL 로 끊겨 늘어서 있다.

## 자리를 어떻게 정하나

🔴 **NUL 로 가른다 — SJIS 런을 앞에서부터 훑지 않는다.** 런 스캔은 **정렬이 밀린다**:
   앞 바이트가 우연히 SJIS 첫 바이트로 읽히면 한 글자를 먹어 `天球儀２−２` 가
   `球儀２−２` 로 잘린다(실측). 잘린 문자열을 되끼우면 옆 바이트를 먹는다.

## 무엇을 문자열로 치나 — 채널 둘

  (a) **포인터가 그 자리를 가리킨다** — 파일 안 BE32 가 `로드베이스 + 오프셋` 과 같다.
      SH-2 리터럴 풀의 절대주소다. **이게 1급 근거**이고, 재삽입에서 고쳐야 할 자리이기도 하다.
  (b) 포인터가 안 잡히면(표 하나에 포인터가 base 한 개뿐인 경우가 흔하다)
      **2글자 이상 + JIS 제1수준(구 ≤47)** 만 받는다.

⚠ **앞에 붙은 이진 바이트를 건너뛰지 않는다.** 「몇 바이트 넘기고 다시 본다」를 재 봤더니
   마커는 0.6% 늘고 **쓰레기가 2,633 개** 늘었다(`弄AP%03d.ED3` · `d泥` · `3d∝` 꼴).
   그래서 조각 **맨 앞부터** 읽히는 것만 받는다 — 스탯 이름처럼 길이 바이트가 앞에 붙은
   표 몇 개를 놓치지만(실측 마커 8건), 그건 재삽입 설계 때 그 표만 따로 연다.

⚠ (b) 의 구 제한이 하는 일: 코드·데이터 바이트가 SJIS 로 디코드되면 **제2수준 희귀 한자**
   (聶·稘·琢·廁·楝·緲·磊·碾…)로 나온다. 게임 UI 는 그런 글자를 안 쓴다. 실측 `/0.BIN` —
   런 911 개 중 **224 개만** 남고(포인터 확인 168 · 휴리스틱 56) 버린 687 개는 전부 쓰레기였다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import font as F
import mapfile as M

# 로드 주소 — `/0.BIN` 은 **IP.BIN 0xF0 실측**(`06 00 40 00`). 나머지는 미확인이라 두지 않는다
# (틀린 베이스를 주면 포인터가 안 잡히는 게 아니라 **엉뚱한 자리를 확인해 준다**).
LOAD_BASE = {"/0.BIN": 0x06004000}

# 🔴 **읽을거리(`BOOK*.BIN`)는 포인터가 파일 상대다** — 베이스가 0 이다(실측 2026-08-31:
#    BOOK06 의 줄 오프셋 31 개가 **전부** 파일 안 BE32 로 가리켜진다).
#    이걸 안 주면 구 제한(`MAX_KU`, JIS 1수준)에 걸려 **2수준 한자가 든 줄이 통째로 빠진다** —
#    책 산문엔 逞·踵·悸·拗·囁·惧 같은 글자가 실제로 나온다. 실측으로 9 권 10 줄이 빠졌고,
#    그 줄만 일본어로 남아 **본문이 깨져 보였다**(유저 보고 2026-08-30).
#    ⚠ 구 제한은 `/0.BIN` 같은 **코드 파일**에는 여전히 필요하다 — 거기선 코드 바이트가
#      희귀 한자로 디코드되는 게 쓰레기의 주범이다. 그래서 **파일 갈래로** 가른다.


def load_base(name):
    """그 파일의 포인터 베이스 — 모르면 `None`(휴리스틱만 쓴다)."""
    if name and name.startswith("/SYSTEM/BOOK") and name.endswith(".BIN"):
        return 0
    return LOAD_BASE.get(name)

MAX_KU = 47  # JIS 제1수준까지
MIN_CHARS = 2

# 문자열 **안에** 들어오는 서식 제어 — 실측: 안내문이 `00 00 09 20 20 20 …` 꼴로 늘어선다
# (NUL 종료 + 패딩 + TAB + 공백 들여쓰기). 이걸 거부하면 세가새턴 저장 안내가 통째로 빠진다.
#   🔴 `0x10` = **메시지 끝 표식**이다(창을 닫고 다음을 기다린다). 이걸 안 받으면
#     그 표식이 붙은 문자열이 통째로 「글이 아니다」로 떨어진다 — 실측 2026-08-31:
#     **전투 보상 `経験値%dと…` · 레벨업 `%sのレベルが%dになった。` · 빈 보물상자** 등
#     아홉이 덤프에서 빠져 있었고, 정본에 없으니 화면에 일본어로 나왔다(유저 인게임 확인).
#     `0x0F` 은 **페이지 넘김**이다(`typeset.PAGE`) — 이걸 막으면 `%sを<0F>売りました。`
#     같이 **앞뒤가 갈린 문안**이 안 잡혀, 뒤만 번역되고 앞은 일본어로 남는다.
ALLOWED_CTRL = (0x09, 0x0A, 0x0D, 0x0F, 0x10)


def ptr_targets(b, base):
    """파일 안 BE32 중 **이 파일 안**을 가리키는 것 → `{오프셋: 그 주소를 쓴 자리들}`.

    ⚠ 2바이트 단위로 훑는다 — SH-2 리터럴 풀은 4B 정렬이지만, 4B 로만 보면 짝수 정렬만
    맞는 자리를 놓친다. 값 범위가 좁아(파일 크기) 오탐은 적다.
    """
    n = len(b)
    out = {}
    for i in range(0, n - 3, 2):
        v = int.from_bytes(b[i : i + 4], "big")
        if base <= v < base + n:
            out.setdefault(v - base, []).append(i)
    return out


def _max_ku(s):
    """이 문자열이 쓰는 가장 높은 JIS 구. 디코드 실패·EUC 밖이면 999(= 탈락).

    ⚠ **2바이트씩 건너뛰며 읽지 않는다.** 문자열 앞에 서식 제어(`09`)나 반각 공백이
    붙으면 정렬이 한 칸 밀려 멀쩡한 문안이 통째로 쓰레기로 읽힌다 — 실측으로 물렸다
    (`\t売る`·`\t買う` 같은 메뉴가 전부 탈락했다). `_shape` 와 같은 걸음으로 걷는다.
    """
    m = 0
    i = 0
    while i < len(s):
        if M.is_sjis_pair(s, i):
            try:
                ch = s[i : i + 2].decode("shift_jis")
            except UnicodeDecodeError:
                return 999
            idx = F.jis_index(ch)
            if idx is None:
                return 999
            m = max(m, idx // 94 + 1)
            i += 2
        else:
            i += 1
    return m


def _shape(seg):
    """조각이 SJIS(+반각 ASCII)로만 돼 있나 → `(문자수, 일본어 있나)` · 아니면 None."""
    i = 0
    nch = 0
    jp = False
    while i < len(seg):
        if M.is_sjis_pair(seg, i):
            i += 2
            nch += 1
            jp = True
        elif 0x20 <= seg[i] < 0x7F:
            i += 1
            nch += 1
        elif seg[i] in ALLOWED_CTRL:
            i += 1
        else:
            return None
    return (nch, jp) if nch else None


def _blank(seg):
    """보이는 글자가 공백뿐인가 — 전각 공백(`81 40`)·반각 공백·서식 제어만."""
    t = text_of(seg)
    return not t.strip().strip("　")


def strings(b, base=None):
    """`[{off, raw, by}]` — `by` 는 `ptr`(포인터 확인) 또는 `heur`(구 제한 휴리스틱).

    ⚠ **NUL 로 가른 조각의 시작 오프셋**이라 정렬이 안 밀린다.
    """
    targets = ptr_targets(b, base) if base is not None else {}
    out = []
    off = 0
    for seg in b.split(b"\x00"):
        if seg:
            sh = _shape(seg)
            if sh and sh[1]:
                nch, _ = sh
                heur = nch >= MIN_CHARS and _max_ku(seg) <= MAX_KU
                #   🔴 **포인터는 「더하기」로만 쓴다** — 휴리스틱이 잡던 줄을 빼면
                #     `book.paragraphs()` 의 문단 색인이 밀려 **기존 번역이 엉뚱한 문단에
                #     붙는다**(실측 2026-08-31: 빈 줄 셋을 빼자 BOOK11·13 이 통째로 −1 밀렸다).
                #     그래서 포인터로만 잡히는 것 중 **공백뿐이 아닌 줄**만 더한다.
                if off in targets and (heur or not _blank(seg)):
                    out.append({"off": off, "raw": seg, "by": "ptr"})
                elif heur:
                    out.append({"off": off, "raw": seg, "by": "heur"})
        off += len(seg) + 1

    #   🔴 **포인터가 조각 한복판을 가리키는 자리도 담는다**(2026-08-31).
    #     `/0.BIN` 은 포인터 표 바로 뒤에 문자열을 붙여 놓은 자리가 있어, NUL 로만 가르면
    #     앞의 포인터 바이트가 섞여 조각 전체가 「글이 아니다」로 탈락한다. 그 바람에
    #     **상점 금액 `%dピア` 와 전투 보상 `経験値%dと…` 이 통째로 안 잡혔다**
    #     (유저 인게임 실측 2026-08-31 — 화면에 일본어로 떴다).
    #   ⚠ 이미 담은 문자열 **안쪽**을 가리키는 포인터는 버린다 — 겹쳐 쓰면 서로 먹는다.
    spans = [(s["off"], s["off"] + len(s["raw"])) for s in out]
    for t in sorted(targets):
        if t >= len(b) or any(a <= t < z for a, z in spans):
            continue
        e = b.find(b"\x00", t)
        seg = b[t : e if e >= 0 else len(b)]
        sh = _shape(seg)
        if seg and sh and sh[1] and not _blank(seg):
            out.append({"off": t, "raw": seg, "by": "ptr"})
            spans.append((t, t + len(seg)))
    out.sort(key=lambda s: s["off"])
    return out


def text_of(raw):
    """`raw` → 사람이 읽는 꼴. 디코드 안 되는 짝은 바이트로 남긴다(왕복 보존)."""
    out = []
    i = 0
    while i < len(raw):
        if M.is_sjis_pair(raw, i):
            try:
                out.append(raw[i : i + 2].decode("shift_jis"))
            except UnicodeDecodeError:
                out.append(f"<{raw[i]:02X}><{raw[i + 1]:02X}>")
            i += 2
        elif 0x20 <= raw[i] < 0x7F:
            out.append(chr(raw[i]))
            i += 1
        else:
            out.append(f"<{raw[i]:02X}>")
            i += 1
    return "".join(out)


def encode_text(s):
    """`text_of` 의 역 — 되끼울 때 쓴다(라운드트립이 이 짝을 본다)."""
    out = bytearray()
    i = 0
    while i < len(s):
        if s[i] == "<" and i + 3 < len(s) and s[i + 3] == ">":
            out.append(int(s[i + 1 : i + 3], 16))
            i += 4
            continue
        out += s[i].encode("shift_jis")
        i += 1
    return bytes(out)
