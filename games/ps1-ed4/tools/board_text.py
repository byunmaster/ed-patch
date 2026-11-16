"""알선소 의뢰 게시판 상세 창 문안 — 의뢰 표 읽기 · 어절 단위 재조판 · 행 수 검사.

구조(11-06 실측, 원판 대조): 의뢰 하나 = 요약 1줄(주황) + 빈 줄 + 본문 `a2`줄(2~3) + 보상 줄. 16열 창은 폭 192px(16자)·6행이라 줄마다 한 행이어야 한다.
엔진은 줄이 폭을 넘으면 **글자 단위로** 접고(어절 인식 없음) 행이 늘면 보상 줄을 덮거나 다음 쪽으로 밀린다 — 그래서 문안을 줄 폭 안으로 미리 끊는다.
의뢰 표(`0x80085FD8` = EXE 0x767D8, 8B 항목): u16 (본문 시작 색인 −1 | 줄 수+2 << 12) · s16 보상 …, 문자열 표 `0x80082388`(u16 오프셋) — 슬롯 = 요약 + 본문 `a2`줄.
"""

import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
import common
import typeset

UI_PATH = os.path.join(common.ROOT, "ui_ed4.json")
FRAG_PATH = os.path.join(common.ROOT, "ui_frag_ed4.json")
TABLE = 0x72B88  # 문자열 포인터 표(u16 오프셋) — EXE 파일 오프셋
QUESTS = 0x767D8  # 의뢰 표 8B 항목
LIMIT = 192  # 16열 창 줄 폭(px) — 일본어 16자가 한 줄에 들어간다
TERM = (0x0000, 0x8000, 0x8002, 0xFFFF)


def px(text):
    """이 창의 줄 폭 — 🔴 **공백·부호도 한 칸(12px)씩**이다(11-06 실측: 반각 훅이 이 창엔 안 먹어 「…가도에 출몰」 12자+공백 4 = 16칸에서 접힘). 곧 한 줄 16글자(공백 포함)."""
    return 12 * len(text)


class Board:
    """원본 EXE 의 의뢰 구조 + 우리 문안(ui·frag 표)."""

    def __init__(self):
        self.exe = bytes(common.read_file(common.EXE_PATH))
        with open(UI_PATH, encoding="utf-8") as f:
            self.ui = {int(k, 16): v for k, v in json.load(f)["strings"].items()}
        with open(FRAG_PATH, encoding="utf-8") as f:
            self.fr = {int(k, 16): v for k, v in json.load(f)["rows"].items() if "kr" in v}
        self.ptr = struct.unpack_from(f"<{0x300}H", self.exe, TABLE)

    def _w(self, a):
        return struct.unpack_from("<H", self.exe, a)[0]

    def slot(self, i):
        """색인 i 의 문자열 → (시작 오프셋, 종류 'ui'|'fr', kr). 앞의 0 종결 워드는 건너뛴다."""
        a = TABLE + self.ptr[i]
        while self._w(a) == 0:
            a += 2
        if a in self.ui:
            return a, "ui", self.ui[a]["kr"]
        if a in self.fr:
            return a, "fr", self.fr[a]["kr"]
        raise KeyError(f"의뢰 문자열 {i} @ {a:#x} 에 번역이 없다")

    def quests(self):
        """[(의뢰 번호, 시작 색인 a1, 본문 줄 수 a2, 보상액)] — 표 항목이 유효한 것."""
        out = []
        for q in range(1, 125):
            v, b, _c, _d = struct.unpack_from("<HhHH", self.exe, QUESTS + 8 * q)
            a1, a2 = (v & 0xFFF) + 1, (v >> 12) - 2
            if 1 <= a2 <= 8 and a1 <= 560:
                out.append((q, a1, a2, b))
        return out

    def texts(self, a1, a2):
        return [self.slot(a1 + k)[2] for k in range(a2 + 1)]  # [요약, 본문…]


SENT_END = (".", "?", "!", "…")


def reflow(summary, body, limit=LIMIT):
    """(새 본문 목록 | None, 사유) — 요약은 그대로(≤ limit), 본문 낱말을 어절 단위로 `len(body)` 줄 안에 다시 끊는다.

    낱말 순서·문안은 그대로이고 줄 구분만 바꾼다. 비용이 가장 낮은 끊기를 DP 로 고른다:
    원래 줄 경계를 지키는 것이 가장 싸고, 새 경계는 문장 끝 뒤가 싸며 문장 한가운데는 비싸고, 낱말 하나·두 글자짜리 고아 줄은 벌점이다.
    """
    if px(summary) > limit:
        return None, f"요약 {px(summary)}px > {limit}px"
    n = len(body)
    words, orig = [], set()  # orig = 원래 줄 경계가 있던 낱말 색인(그 낱말 앞에서 끊었다)
    for line in body:
        if not line:
            continue
        if words:
            orig.add(len(words))
        words += line.split(" ")
    for w in words:
        if px(w) > limit:
            return None, f"낱말 「{w}」 {px(w)}px > {limit}px"
    m = len(words)
    INF = 10**9

    def width(a, b):
        return px(" ".join(words[a:b]))

    def edge(b):  # 낱말 b 앞에서 끊는 값
        if b in orig:
            return 0
        return 1 if words[b - 1].endswith(SENT_END) else 8

    def orphan(a, b):  # 원래 줄 그대로인 짧은 줄은 고아가 아니다 — 새로 끊어 생긴 한 낱말 줄만 벌점
        kept = (a == 0 or a in orig) and (b == m or b in orig)
        return 5 if b - a == 1 and len(words[a]) <= 3 and not kept else 0

    # best[k][b] = 낱말 b 개를 k 줄에 담는 최소 비용(마지막 줄이 b 에서 끝남)
    best = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0
    for k in range(1, n + 1):
        for b in range(1, m + 1):
            for a in range(b):
                if best[k - 1][a] >= INF or width(a, b) > limit:
                    continue
                c = best[k - 1][a] + (edge(a) if a else 0) + orphan(a, b)
                if c < best[k][b]:
                    best[k][b], back[k][b] = c, a
    # 쓴 줄 수가 적으면 합쳐진 원래 경계마다 벌점 2
    pick, cost = None, INF
    for k in range(1, n + 1):
        if best[k][m] >= INF:
            continue
        a, b, used = m, k, set()
        while b:
            a = back[b][a]
            if a:
                used.add(a)
            b -= 1
        c = best[k][m] + 2 * len(orig - used)
        if c < cost:
            pick, cost = k, c
    if pick is None:
        # 가장 적은 줄로 담았을 때 몇 줄이 필요한지 알린다
        out, cur = [], []
        for w in words:
            if px(" ".join(cur + [w])) <= limit:
                cur.append(w)
            else:
                out.append(" ".join(cur))
                cur = [w]
        out.append(" ".join(cur))
        return None, f"본문 {len(out)}줄 필요(슬롯 {n}줄) — 남는 말 「{out[n]}」"
    cuts, a, b = [], m, pick
    while b:
        a = back[b][a]
        cuts.append(a)
        b -= 1
    cuts = sorted(c for c in cuts if c) + [m]
    out, prev = [], 0
    for c in cuts:
        out.append(" ".join(words[prev:c]))
        prev = c
    return out + [""] * (n - len(out)), ""


def violations(board, limit=LIMIT):
    """[(의뢰 번호, 사유)] — 줄이 폭을 넘어 접히는 의뢰(요약·본문 어느 줄이든)."""
    bad = []
    for q, a1, a2, _b in board.quests():
        for k, t in enumerate(board.texts(a1, a2)):
            if px(t) > limit:
                bad.append(
                    (q, f"{'요약' if k == 0 else f'본문 {k}'} {px(t)}px > {limit}px 「{t}」")
                )
    return bad
