"""조판 전수(구운 바이트) — 대사·전투·시스템 문안 전량을 **이미지에 구운 한글 줄**로 훑어 줄·쪽 모양의 결함을 센다(마스터 10-31 「조판검사할 때 첫칸공백, 고아부호, 빈줄개행, 여러창일 때 균등한 문장 분배」).

`check_punct`·`check_linebreak` 는 **문안 → 조판기** 를 다시 태워 보므로 조판을 건너뛰는 잠금 줄·제어 틀·본 프로그램 문자열은 못 본다. 이 검사는 구운 바이트(`pairs.py` 디코드)를 직접 본다.
축(줄은 `↵`, 쪽은 `⏎`·`{12}` 로 가르고 화자 머리 `{16}…{14}`·`{name}` 줄은 뺀다):
  first_space  첫 칸 공백(2-5) — 줄이 공백으로 시작
  orphan_punct 고아 부호(2-3) — 줄이 `. , ! ? ～ ) 」 』` 로 시작
  blank_line   빈 줄 개행(2-4) — 글 없는 줄이 쪽 가운데·끝에 낌
  sp_after     부호 뒤 글자 붙임·부호 앞 공백·전각 부호(2-1·2-2, check_punct.RULES)
  last_page    마지막 쪽에 한 어절만 남음(여러 쪽일 때) — 2-16 ③
  page_orphan  쪽 끝 줄이 한 어절(쪽에 줄이 둘 이상일 때) — 2-16 ③
  skew         쪽 줄 수 치우침 — 인접 쪽 줄 수 차 ≥ 3. 조판기가 고를 수 있는 것은 이미 골랐다(check_linebreak h2) — 남는 것은 원판 쪽 가름(`\f`, 2-6)과 절 경계 제약(2-16 ②: 목적어·주어만 줄 끝에 남기지 않음) 때문이라 늘지만 않게 래칫
  color_*      색·연출 제어(4-6, 원판 그대로) — 원판 대비 색 시작(`16`·`15 nn`·`17`) 누락(missing)·추가(extra) · 닫는 코드(`14`) 누락으로 뒤로 번짐(unclosed: 한글이 원판보다 덜 닫힘) ·
               색 시작이 낱말 한가운데(midword: 한글 바로 뒤)
  overflow     줄 폭이 168px 를 넘김(변수 자리 `{…}` 가 든 줄은 못 잰다 — 건너뜀)
  center_skew  가운데 맞춤 줄(원판이 양쪽 공백을 둔 줄)의 좌우 여백 차가 4px 를 넘음(2-8) — 줄 끝 `.` `,` `…` 는 오른쪽 여백으로 친다
  center_grid  (알림) 차가 1~4px — 공백이 4px 단위라 글 폭이 4의 배수일 때 반 칸(2px) 어긋남이 피할 수 없다 → 기준선에 안 둔다
  one_line     한 줄에 들어가는 문장(엔진 꺾임 규칙: 마지막 글자 시작 x+12 ≤ 168)을 두 줄로 쪼갠 곳(2-10) — 문장은 줄 안의 끝 부호+공백에서도 끊는다. 가운데 맞춤 카드·인용 들여쓰기 쪽은 뺀다
  chapter_gap  장 번호–제목 사이가 12px 가 아닌 줄(2-8, 원판 전각 한 칸)
  banner_center 필드 지명 틀(우측 위 패널, 안쪽 x 227~315)의 지명 글자가 틀 한가운데에서 4px 넘게 쏠림(2-8, 마스터 11-04) — 글 시작 x = 234 + 머리 `{08}`(4px) + 앞 공백, 글 먹은 폭 = 폭-1. 쏠림 = 글 가운데 - 271
  name_gap    원문이 전각 공백으로 끝나(뒤에 이름 변수·표 글자가 이어 붙는 줄) 우리 줄이 공백 없이 끝난다(「여기는큐베라로」 — 마스터 11-05)
  head_rows   앞 줄이 화자 머리뿐인데 이 줄 첫 쪽 본문이 4줄 — 이름 줄이 밀려 올라간다(원판은 이 자리에 4줄이 없다, 11-06 642:22:6)
  ellipsis_sp `…` 뒤에 말이 바로 붙은 줄(2-11 — `에휴…정말이지`, 11-06 비주얼 씬·642:30:21)
  pause_sp    멈춤(`12`·`11`) 앞뒤가 둘 다 공백 — 이음 공백이 겹쳐 두 칸이 벌어진다(11-11)
  color_lead_sp 줄·쪽 첫머리가 색 켜기 + 공백 — `first_space` 가 `{` 로 시작하는 줄을 건너뛰는 구멍(11-11)
  banner_pad  월드맵 입장 배너 박스 줄 총 폭 > 84px — 글이 지워지고 흰 줄만 남는다(11-06)
  kana_slot   우리 출력에 반각 작은 가나(ｧ~ｭ) — 그 코드는 (다)안 반각 글꼴 표의 `! ? ' \" ( ) :` 슬롯이다(11-06)
  window_short 원문 창 수보다 우리 창이 적은 곳(원문 창을 합쳤다 — 2-17, 마스터 11-05)
  window_extra 원문 창 수보다 우리 창이 많은데, 글을 이어 다시 짜면 원문 창 수에 들어가는 곳(2-10 · 2-17, 마스터 11-05 「한 칸에 표시할 수 있음에도 문장 단위 개행으로 넘어가는 경우는 없어야」) — 길어서 부득이한 곳은 안 센다
  reward_nl    전투 보상 줄(「…를 해치웠다」·「ＥＰ n 포인트 획득」·「n GOLD를 얻었다」)의 앞뒤 개행이 원판과 다름 · 「ＥＰ」 와 수 사이 공백(2-9, pce-ed2 는 없음)
  comma_conn   짧은 연결 어미(고·며·으며·하며·면서) 뒤 쉼표(2-13 「뺀다」) — 앞 절 12자 이하 · 나열(다음 절도 같은 어미)·말머리 군말·「~자고,」는 남기는 부류라 뺀다
각 결함은 원판(일본어 줄)도 같은 꼴인지 갈라 센다 — 같은 꼴이면 `원판 동일`(결함이 아니라 원판 연출). 판정 열쇠는 `rel:메시지:줄`.

    python3 check_layout.py [--iso <이미지>] [--gate] [--freeze] [--list <축>]
`--gate` 는 기준선(`layout_baseline.json`)보다 늘면 실패(래칫). `--freeze` 로 내린다.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import chapter
import check_punct
import common
import pairs
import typeset
import narrow_font

BASE = Path(__file__).resolve().parents[1] / "layout_baseline.json"
HEAD = re.compile(r"\{16\}[^↵⏎]*(?:\{name\}|\{14\})?↵?")
CTRL = re.compile(r"\{[^}]*\}")
AXES = ("color_missing", "color_extra", "color_unclosed", "color_midword", "first_space", "orphan_punct", "blank_line", "sp_after", "last_page", "page_orphan", "skew", "overflow", "center_skew", "center_grid", "one_line", "reward_nl", "comma_conn", "chapter_gap", "banner_center", "window_extra", "window_short", "name_gap", "head_rows", "ellipsis_sp", "banner_pad", "kana_slot", "pause_sp", "color_lead_sp")
LEAD_PUNCT = ".,!?～)」』"
SEEN: list[str] = []  # 디버그 — one_line 이 센 문장
INFO = ("center_grid",)  # 알림만 두는 축


def pages_of(s: str) -> list[list[str]]:
    """구운 줄 → 쪽마다 글 줄 목록(화자 머리·제어 표지는 뺀다). 쪽 가름은 `⏎`·`{12}`."""
    out = []
    for p in re.split(r"⏎|\{12\}", HEAD.sub("", s, count=1) if s.startswith("{16}") else s):
        out.append(p.split("↵"))
    return out


def bare(line: str) -> str:
    return CTRL.sub("", line)


SPEAKER = re.compile(r"(?=\{16\})|\{1C [0-9A-F]{2}\}↵")
SENT_END = ".?!…」』~"
VAR = re.compile(r"\{(?:name|josa|1[CDE] [0-9A-F]{2}|13 [0-9A-F]{2})\}")


def seg_findings(s: str, c: dict[str, int], orig: bool = False) -> None:
    """화자 한 구간(머리 `{16}…{14}` 또는 `{1C nn}` 로 시작)의 쪽 모양."""
    pgs = [p for p in pages_of(s) if any(bare(x).strip() or "{" in x for x in p)]
    for pi, p in enumerate(pgs):
        texts = [bare(x) for x in p]
        for li, t in enumerate(texts):
            raw = p[li]
            if not t.strip():
                if not VAR.search(raw) and 0 < li < len(texts) - 1 and any(x.strip() or VAR.search(y) for x, y in zip(texts[li + 1 :], p[li + 1 :])):  # 변수 자리(이름·아이템)만 든 줄은 빈 줄이 아니다 — 시간 제어(`11 nn mm`)만 든 줄은 화면에서 빈 줄이다
                    c["blank_line"] += 1
                continue
            if t[0] in " \u3000" and not raw.startswith("{") and len(p) > 1:  # 한 줄짜리 띠(지명·장 제목)는 가운데 맞춤 공백이다
                c["first_space"] += 1
            if t.lstrip()[:1] and t.lstrip()[:1] in LEAD_PUNCT:
                c["orphan_punct"] += 1
            if "{" not in raw and len(p) > 1 and typeset.fit_px(t) > 14 * 12:  # 한 줄짜리 전투 알림은 창이 넓다(원판 같은 꼴) — 줄바꿈이 있는 대사만 잰다
                c["overflow"] += 1
        lines = [t for t in texts if t.strip()]
        if pi < len(pgs) - 1 and len(lines) >= 2 and len(lines[-1].split()) == 1 and lines[-1][-1] not in SENT_END:
            c["page_orphan"] += 1  # 문장 중간에서 한 어절로 끝나는 쪽
    if len(pgs) >= 2:
        last = [bare(x) for x in pgs[-1] if bare(x).strip()]
        if len(last) == 1 and (orig or len(last[0].split()) == 1):  # 원판은 어절 수를 못 센다(일본어 띄어쓰기) — 한 줄짜리 마지막 쪽이면 같은 꼴
            c["last_page"] += 1
        lens = [len([x for x in p if bare(x).strip()]) for p in pgs]
        if any(abs(a - b) >= 3 for a, b in zip(lens, lens[1:])):
            c["skew"] += 1


def findings(s: str, orig: bool = False) -> dict[str, int]:
    """한 줄(메시지)의 축별 결함 수."""
    c = dict.fromkeys(AXES, 0)
    for seg in SPEAKER.split(s):
        if seg.strip():
            seg_findings(seg, c, orig)
    plain = bare(s).replace("↵", "\n").replace("⏎", "\f")
    if re.search("[가-힣]", plain) and check_punct.violations(plain):
        c["sp_after"] += 1
    return c


PADRE = re.compile("^([ \u3000]*)(.*?)([ \u3000]*)$")
END = ".?!…」』"
SPLIT_SENT = re.compile(r"(?<=[.?!…])\s+(?=\S)")
CONN_END = re.compile(r"(?:하고|이고|으며|하며|받으며|면서|고|며)$")
COMMA_EXC = re.compile(r"(?:어때 지고|아니|어이|그런가|뭔가|어떤가|아이고|아,|어,|네,|예,|응,|글쎄|저기|자,|그래|음,|오오|어디 보자)")
MENU_CTRL = re.compile(r"\{(?:01|10 |11 |14)")  # 메뉴 항목·음성 시각 맞춤·변수 이어받기 쪽은 문장 모양이 아니다
REWARD = re.compile(r"해치웠다|포인트|GOLD")
REWARD_JP = re.compile(r"倒した|獲得|手に入れ")


def padpx(s: str) -> int:
    return sum(12 if c == "\u3000" else 4 for c in s)


def center_findings(o: str, k: str) -> dict[str, int]:
    """가운데 맞춤 줄의 좌우 여백 차(2-8) — 원판이 양쪽에 공백을 둔 줄만. 한쪽만 남은 줄(HUD 지명: 왼쪽 맞춤 설계)은 안 잰다."""
    c = {"center_skew": 0, "center_grid": 0}
    ol = bare(o).replace("⏎", "↵").split("↵")
    for i, line in enumerate(bare(k).replace("⏎", "↵").split("↵")):
        if i >= len(ol) or not line.strip():
            continue
        mo, m = PADRE.match(ol[i]), PADRE.match(line)
        if not (mo.group(1) and mo.group(3) and m.group(1) and m.group(3)):
            continue
        t = m.group(2)
        tail = len(t) - len(t.rstrip(".,…"))
        lp, rp = padpx(m.group(1)), padpx(m.group(3)) + (typeset.px(t[len(t) - tail :]) if tail else 0)
        tpx = typeset.px(t) + (4 * t.count(" ") if CHAPTER.match(t) else 0)  # 장 제목 띠의 낱말 사이는 ASCII 공백 `20`(8px 그려서 지움 — 모델의 공백은 4px 라 4px 씩 더한다, 11-10)
        if lp + tpx + rp == chapter.BAND_PX and True:  # 장 제목 띠(14칸=168px): 화면 띠 안쪽이 8px 더 넓다 — 그만큼을 뺀 값으로 잰다
            lp -= chapter.BAND_SLACK_PX
        d = abs(lp - rp)
        if d > 4:  # 가장 가까운 칸이라 4px 격자의 한계 안(마스터 11-09 「최대한 가운데」)
            c["center_skew"] += 1
        elif d > 1:
            c["center_grid"] += 1
    return c


def one_line_findings(k: str) -> int:
    """한 줄에 들어가는 문장이 두 줄로 쪼개진 수(2-10)."""
    n = 0
    k = HEAD.sub("", k)
    for pg in re.split(r"⏎|\{12\}", k):
        lines = [bare(x) for x in pg.split("↵")]
        if len(lines) < 2 or any(x[:1] == "\u3000" for x in lines) or MENU_CTRL.search(pg):
            continue
        cur, idx = "", set()
        sents = []
        for li, ln in enumerate(lines):
            t = ln.strip()
            if not t:
                continue
            for part in SPLIT_SENT.split(t):
                cur = f"{cur} {part}" if cur else part
                idx.add(li)
                if part[-1:] in END:
                    sents.append((cur, idx))
                    cur, idx = "", set()
        for t, idx in sents:
            if len(idx) >= 2 and not VAR.search(pg) and typeset.px(t[:-1]) + 12 <= 168:
                n += 1
                SEEN.append(t)
    return n


def reward_findings(o: str, k: str) -> int:
    """전투 보상 줄 — 앞뒤 개행이 원판과 같고 「ＥＰ」 뒤에 공백이 있는가(원판 꼴, 마스터 11-17)."""
    if not (REWARD.search(k) and "{name}" in k and REWARD_JP.search(o)):
        return 0
    lead = lambda s: bare(s)[:1] == "↵"  # noqa: E731
    trail = lambda s: bare(s)[-1:] == "↵"  # noqa: E731
    bad = lead(o) != lead(k) or trail(o) != trail(k)
    bad = bad or not re.search("ＥＰ[ \u3000]\\S", k)  # 마스터 11-17: ＥＰ 와 수 사이에 공백(원판 꼴)
    return int(bad)


CHAPTER = re.compile(r"(?:제[0-9０-９]+장|서장|종장)([ \u3000]+)(?=\S)")


def chapter_gap_findings(k: str) -> int:
    """장 번호–제목이 한 줄에 나오는 자리의 사이가 12px(반각 2칸 = 원판 전각 1칸)이 아닌 줄 수(2-8, 마스터 11-03)."""
    return sum(1 for ln in re.split("[↵⏎]", bare(k)) for m in CHAPTER.finditer(ln) if padpx(m.group(1)) != 12)


def _daegu(c: str, nxt_clause: str) -> bool:
    """앞 절 끝 3어절 안의 주어(도·은·는·이·가)와 다음 절 앞 3어절의 같은 조사 주어 — 대구."""
    pre = [t for t in c.split()[-4:-1] if len(t) >= 3]
    post = [t for t in nxt_clause.split()[:3] if len(t) >= 3]
    for a in pre:
        m = re.search(r"(도|은|는|이|가)$", a)
        if m and any(b.endswith(m.group(1)) for b in post):
            return True
    return False


def comma_findings(k: str) -> int:
    """짧은 연결 어미 뒤 쉼표(2-13 「뺀다」) 수."""
    flat = re.sub(r"[↵⏎]+", " ", bare(HEAD.sub("", k)))
    n = 0
    for sent in SPLIT_SENT.split(flat):
        cl = sent.split(", ")
        for i, c in enumerate(cl[:-1]):
            w = c.split()[-1] if c.split() else ""
            if not CONN_END.search(w) or len(re.sub(r"\s", "", c)) > 12 or COMMA_EXC.match(c.strip()):
                continue
            nxt = cl[i + 1].split()[-1].rstrip("….") if cl[i + 1].split() else ""
            prv = cl[i - 1].split()[-1].rstrip("….") if i and cl[i - 1].split() else ""
            if w.endswith(("말고", "자고")) or CONN_END.search(nxt) or CONN_END.search(prv):
                continue  # 관용·말머리·나열(앞뒤 절도 같은 어미)은 남긴다
            if _daegu(c, cl[i + 1]):
                continue  # 대구(같은 조사 주어 둘 — 「광산도 …고, 몬스터도 …」)는 쉼표를 넣는다(마스터 11-06 「대구는 쉼표넣자」)
            n += 1
    return n


COLOR_START = re.compile(r"\{(?:16|17|15(?: [0-9A-F]{2})+)\}")
COLOR_END = re.compile(r"\{14\}")


def color_findings(o: str, k: str) -> dict[str, int]:
    """원판(`o`)과 한글(`k`)의 색·연출 제어 대조 — 행 단위."""
    so, sk = len(COLOR_START.findall(o)), len(COLOR_START.findall(k))
    eo, ek = len(COLOR_END.findall(o)), len(COLOR_END.findall(k))
    c = dict.fromkeys(("color_missing", "color_extra", "color_unclosed", "color_midword"), 0)
    c["color_missing"] = int(sk < so)
    c["color_extra"] = int(sk > so)
    c["color_unclosed"] = int((sk - ek) > (so - eo))
    c["color_midword"] = int(bool(re.search(r"[가-힣]\{(?:16|17)\}", k)))
    return c


PANEL_ORIGIN, PANEL_CENTER, PANEL_MAX_W = 234, 271, 82  # labels.py 실측 상수(캡처 343×243 1:1)
PLACE = re.compile(r"(?:町|城|村|港|鉱山|洞窟|塔|王国)$")  # 지명 접미로 끝나는 원문(「毒鉱石」 같은 몬스터 이름은 안 걸린다)


def banner_skew(o: str, k: str) -> int | None:
    """지명 틀 줄이면 글 가운데의 쏠림(px), 아니면 None. 지명 틀 줄 = 한 줄짜리 원문이 지명 꼴이고 대사·목록 제어(`{10`·`{11`·`{16`)가 없는 것."""
    if re.search(r"[↵⏎]|\{1[016]", o) or re.search(r"[↵⏎]|\{1[016]", k) or not PLACE.search(bare(o).strip(" \u3000")):
        return None
    m = re.match(r"((?:\{0[89]\})*)((?:\{0[4-7]\})?)([ \u3000]*)(\S.*?)\s*(?:\{0[4-7]\})?$", k)
    if not m:
        return None
    name = m.group(4)
    if "{" in name:
        return None
    w = typeset.px(name)
    if w > PANEL_MAX_W:
        return None
    start = PANEL_ORIGIN + 4 * (m.group(1).count("{08}") - m.group(1).count("{09}")) + padpx(m.group(3))
    return round(start + w / 2 - 1 - PANEL_CENTER)


def window_extra(o: str, k: str, after_head: bool = False) -> int:
    """원문 창(`⏎` 쪽, 빈 쪽 제외)보다 우리 창이 많고, 우리 글을 이어 `typeset.pages` 로 다시 짜면 원문 창 수 이하인가."""
    def pages(t):
        return [p for p in t.split("⏎") if bare(p).replace("↵", "").strip()]

    po, pk = pages(o), pages(k)
    if len(pk) <= len(po) or VAR.search(k):  # 변수 자리는 폭을 못 잰다
        return 0
    head = "{16}" in k or after_head  # 앞 줄이 화자 머리뿐이면 첫 쪽은 본문 3줄
    flat = " ".join(bare(re.sub(r"\{16\}[^{]*\{14\}", "", p)).replace("↵", " ").strip() for p in pk)
    flat = re.sub(r" +", " ", flat).strip()
    try:
        n = len(typeset.pages(flat, headed=head))
    except AssertionError:
        return 0
    return int(n <= len(po))


def window_short(o: str, k: str) -> int:
    """원문 창(`⏎` 쪽, 빈 쪽 제외)보다 우리 창이 **적은** 곳 — 원문 창 둘을 한 창에 합쳤다(2-17: 원문 창은 늘리지도 줄이지도 않는다, 마스터 11-05)."""
    def pages(t):
        return [p for p in t.split("⏎") if bare(p).replace("↵", "").strip()]

    if VAR.search(k):
        return 0
    return int(len(pages(k)) < len(pages(o)))


HEAD_ONLY = re.compile(r"^(?:\{[0-9A-F ]+\})*\{16\}[^{]*(?:\{0[EF]\}[^{]*)*\{14\}\u21b5?$")


def head_rows(prev_o: str, o: str, k: str) -> int:
    """앞 줄이 화자 머리뿐이면 이 줄 첫 쪽에 이름 줄이 같이 뜬다 — 본문이 4줄이면 이름이 밀려 올라간다(원판은 이 자리에 4줄이 없다, 11-06 642:22:6)."""
    if not HEAD_ONLY.match(prev_o) or o.startswith("{16}"):
        return 0
    first = pages_of(k)[0]
    return int(len([x for x in first if bare(x).strip()]) >= 4)


def banner_pad(key: str, o: str, k: str) -> int:
    """월드맵 입장 배너 박스 줄(`{10 30} … {11 33 30}`)의 총 폭이 박스 안쪽(84px)을 넘나 — 넘으면 글이 지워지고 흰 줄만 남는다(11-06 낫슈마을 96px, 요르도항구·스엘마을 84px 은 정상)."""
    if not re.fullmatch(r"\{10 30\}[ \u3000]*[^{\u21b5\u23ce]*\{11 33 30\}", k):  # 박스 줄 = 속도 지시 + 여백·이름 + 꼬리 — 화자·줄바꿈·다른 제어가 낀 대사 줄은 아니다
        return 0
    body = bare(k)
    return int(typeset.px(body) > 84)


def ellipsis_findings(k: str) -> int:
    """`…` 뒤에 말이 바로 붙은 줄(규칙 2-11 — `에휴…정말이지` ✗ · `에휴… 정말이지` ✓). 예외(맨 앞 `…`·음절 끊기·되풀이)는 `typeset.spaced` 가 안다. 줄바꿈(`↵`)·쪽 가름(`⏎`)은 붙은 게 아니다."""
    t = bare(k).replace("↵", "\n").replace("⏎", "\n")
    return int(typeset.spaced(t) != t)


PAUSE_SP = re.compile(r"[ \u3000]\{1[12]\}[ \u3000]")
COLOR_LEAD_SP = re.compile(r"(?:^|↵|⏎|\{1[23]\})(?:\{(?:15 [0-9A-F]{2}|17)\})+[ \u3000]")


def pause_sp_findings(k: str) -> int:
    """멈춤(`12`·`11`) 앞뒤가 둘 다 공백 — 한 줄에서 멈춤을 지나 이어질 때 칸이 두 개 벌어진다(11-11 「없을… {12} 터이니」: `…` 이음 공백 + 조각 끝 공백이 겹쳤다)."""
    return len(PAUSE_SP.findall(k))


def color_lead_sp_findings(k: str) -> int:
    """줄·쪽 첫머리가 색 켜기(`15 nn`·`17`) + 공백 — 첫 칸 공백 판정(`first_space`)이 `{` 로 시작하는 줄을 건너뛰어 놓치는 자리(pce-ed1 11-10 사고)."""
    return len(COLOR_LEAD_SP.findall(k))


def analyze(iso: str):
    kg = pairs.KoGlyphs(iso)
    tot = {a: [0, 0] for a in AXES}  # [고칠 것, 원판 동일]
    hits: dict[str, list[str]] = {a: [] for a in AXES}
    same: dict[str, list[str]] = {a: [] for a in AXES}  # 원판 동일로 센 줄(목록 확인용 — `--list-same`)
    rows = 0
    _po = ""
    for fn in (pairs.package_rows, pairs.literal_rows, pairs.table_rows):
        for key, o, k, _sh in fn(iso, kg):
            if not k.strip() or not o.strip():
                continue
            rows += 1
            prev_o, _po = _po, o
            fk, fo = findings(k), findings(o, True)
            fk.update(color_findings(o, k))
            fk.update(center_findings(o, k))
            fk["one_line"] = one_line_findings(k)
            fk["reward_nl"] = reward_findings(o, k)
            fk["comma_conn"] = comma_findings(k)
            fk["chapter_gap"] = chapter_gap_findings(k)
            fk["window_extra"] = window_extra(o, k, bool(HEAD_ONLY.match(prev_o)) and not o.startswith("{16}"))
            fk["window_short"] = window_short(o, k)
            fk["name_gap"] = int(o.endswith("\u3000") and not k.endswith((" ", "\u3000")))
            fk["head_rows"] = head_rows(prev_o, o, k)
            fk["ellipsis_sp"] = ellipsis_findings(k)
            fk["pause_sp"] = pause_sp_findings(k)
            fk["color_lead_sp"] = color_lead_sp_findings(k)
            fk["banner_pad"] = banner_pad(key, o, k)
            fk["kana_slot"] = int(any(c in narrow_font.KANA_CHARS for c in k))  # 반각 글꼴 표에 새 코드를 얹은 작은 가나 슬롯 — 우리 출력에 그 가나가 0개여야 한다
            sk = banner_skew(o, k) if key[0].isdigit() and key.endswith(":0") else None  # 덩이 첫 줄만(S… 디버그 문자열 · T:… 지명 표는 지명 틀이 아니다)
            fk["banner_center"] = int(sk is not None and abs(sk) > 4)
            fo.update({a: 0 for a in AXES if a.startswith("color_") or a in ("center_skew", "center_grid", "one_line", "reward_nl", "comma_conn", "chapter_gap", "banner_center", "window_extra", "window_short", "name_gap", "head_rows", "ellipsis_sp", "banner_pad", "kana_slot", "pause_sp")})
            fo["color_lead_sp"] = color_lead_sp_findings(o)  # 원판에도 있는 꼴은 원판 동일로
            for a in AXES:
                if fk[a]:
                    if fo[a] >= fk[a]:
                        tot[a][1] += 1
                        same[a].append(f"{key}: 원문 {o[:60]!r} → {k[:60]!r}")
                    else:
                        tot[a][0] += 1
                        hits[a].append(f"{key}: {k[:70]}")
    analyze.same = same
    return rows, tot, hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", default=str(common.BUILD_DIR / "pce-ed2" / "ed2.iso"))
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--list")
    ap.add_argument("--list-same")
    a = ap.parse_args()
    rows, tot, hits = analyze(a.iso)
    print(f"  조판 전수(구운 바이트) [pce-ed2] — {rows}행 · " + " · ".join(f"{k} {v[0]}(+원판동일 {v[1]})" for k, v in tot.items()))
    if a.list:
        for h in hits[a.list]:
            print("   ", h)
    if a.list_same:
        for h in analyze.same[a.list_same]:
            print("   ", h)
    now = {k: v[0] for k, v in tot.items() if k not in INFO}
    if a.freeze:
        BASE.write_text(json.dumps(now, indent=1) + "\n")
        return 0
    if a.gate:
        base = json.loads(BASE.read_text()) if BASE.exists() else None
        if base is None:
            print("  ✗ 기준선이 없다 — --freeze")
            return 1
        worse = [k for k in now if now[k] > base.get(k, 10**9)]
        if worse:
            print(f"  ✗ 기준선 {base} 보다 늘었다: {worse}")
            return 1
        if any(now[k] < base.get(k, 0) for k in now):
            print(f"  ✗ 기준선 {base} 보다 줄었다 — --freeze 로 내린다(래칫)")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
