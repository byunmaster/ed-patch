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

MAX_KU = 47  # JIS 제1수준까지
MIN_CHARS = 2

# 문자열 **안에** 들어오는 서식 제어 — 실측: 안내문이 `00 00 09 20 20 20 …` 꼴로 늘어선다
# (NUL 종료 + 패딩 + TAB + 공백 들여쓰기). 이걸 거부하면 세가새턴 저장 안내가 통째로 빠진다.
ALLOWED_CTRL = (0x09, 0x0A, 0x0D)


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
                if off in targets:
                    out.append({"off": off, "raw": seg, "by": "ptr"})
                elif nch >= MIN_CHARS and _max_ku(seg) <= MAX_KU:
                    out.append({"off": off, "raw": seg, "by": "heur"})
        off += len(seg) + 1
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
