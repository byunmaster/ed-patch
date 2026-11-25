"""조판 결과 전수 검사 — 실제로 굽는 롬 바이트의 모든 대사·전투 문안을 쪽·줄로 풀어 규칙 2-1·2-3·2-4·2-5·2-6·2-16 ③ 위반을 센다(마스터 10-31).

    python3 tools/typeset_audit.py [롬.bin] [--list]      # 빌드 게이트(check.sh 5e4) — 기준선(typeset_audit_baseline.json)보다 늘면 실패, 줄면 --freeze

단위는 spacing_check 와 같다(씬 모듈 짝지은 스트림 + 전투 블록 — 표 머리 제외). 화자 머리(1E 이름 04)는 줄에서 뺀다. 변수(09·0E·02·15·10)는 `§`(폭 4)로 두고
변수가 낀 줄은 폭 검사(넘침)에서 뺀다. 쪽 = 05·03 사이, 단위 = 화자(1E) 바뀜 사이.
 첫칸공백  줄이 공백으로 시작(2-5)            고아부호  줄 머리가 닫는 부호·마침표 따위(2-3)      빈줄   빈 줄 · 꽉 찬 줄 뒤 개행(2-4)
 부호뒤    `, . ! ?` 바로 뒤 한글(2-1)         접힘     줄 머리가 조사 조각(낱말 속 접힘, 2-6)         넘침   줄 폭 > 17.5 슬롯
 꼬리한어절 단위의 마지막 쪽이 한 어절(2-16 ③)  쪽끝고아  쪽 끝 줄이 한 어절(2-16 ③)                    줄수치우침 쪽 줄 수 차 ≥ 2(2-16 ③)
 가운데어긋남 가운데 맞춤 자리의 좌우 여백 차 > 6px(2-8)  가운데반칸  차가 정확히 6px = 반각 한 칸(바이트 단위 한계, 2-8)  가운데최근접 앞 공백을 한 칸 옮기면 가운데에 더 가까워지는 줄(배너·장 제목·장 카드·서장 — 개정 2-8 마스터 11-09 「최대한 가운데, 같을 때만 왼쪽」, HUD 지명은 칸 단위로 못 재서 실측 시트로 본다)
 창적음   한글 창(쪽) 수가 원문보다 적다 — 원문 두 창을 한 창으로 합친 곳(2-17, pce-ed2·ps1-ed4 에서 발견)
 창많음   한글 창(쪽) 수가 원문보다 많다 — 원문 창 구분을 못 지킨 곳(2-17, 마스터 11-06 게이트 승격·래칫; 3줄 창에 안 들어가 쪽이 넘치는 곳은 기준선에 사유와 함께 남는다)
 한줄문장  한 줄에 통째로 드는 문장이 두 줄에 걸침(2-10)   쉼표뺄것  접속부사 뒤 · 줄 끝 짧은 연결어미 뒤 쉼표(2-13)  쉼표애매  앞 절이 짧은(≤8음절) 줄 안 연결어미 뒤 쉼표(2-13 — 판정 대기)
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import banners
import chapters
import layout
import places
import scene_sweep
import spacing_check as SP

BASE = Path(__file__).resolve().parents[1] / "typeset_audit_baseline.json"
VARS = {0x09, 0x0E, 0x02, 0x15, 0x10}
PAGE = {0x05}
VAR_W = 4.0
KEYS = (
    "첫칸공백", "고아부호", "빈줄", "부호뒤", "접힘", "넘침", "색낱말속", "꼬리한어절", "쪽끝고아", "쪽끝한어절", "줄수치우침",
    "가운데어긋남", "가운데반칸", "가운데최근접", "한줄문장", "쉼표뺄것", "쉼표애매", "전투넘침", "창적음", "창많음",
)
ORPHAN_HEAD = re.compile(r"^[.,!?~)」』]")
BOUND = re.compile(r"^(?:[은는을를에의도만과와로께]|에서|에게|까지|부터|처럼|보다|한테|으로)(?=[ ]|$|[.,!?…」])")
AFTER_PUNCT = re.compile(r"[,.!?][가-힣]")
BATTLE_W = 23.0  # 전투 창 한 줄 — 실측(sweep-1031 b02/07: 23.0슬롯 줄이 x 8~290 에 앉는다, 창은 x 8~312)
# 2-13 쉼표 — 「뺀다」 부류만 센다(부르는 말·감탄·응답·나열·군말은 남긴다)
CONJ_HEAD = layout._CONJ | {"또한"}
CONN_RE = re.compile(r"(?:하고|하며|으며|면서|이며|아서|어서|해서|으니|으나|려고|도록|다가|되고|있고|없고|하니|오니|[가-힣]니까|[가-힣]서|[가-힣]고|[가-힣]며)$")
NOT_CONN = re.compile(r"(?:습니까|십니까|입니까|아이고|어이고|말고|그러고)$")
COMMA_RE = re.compile(r"(\S+?),(?=\s|$)")
CLAUSE_MAX = 11  # 줄 끝 연결어미 쉼표는 앞 절이 이 음절 이하일 때만 뺀다 — 2-13 ⑨ 와 같은 잣대(읽는 소리대로)
DAEGU_RE = re.compile(r"\S+도 ")  # 대구 절 — 「~도 …」
DAEGU_NEXT = re.compile(r"\s*\S+도 ")
CLAUSE_SHORT = 8  # 줄 안 연결어미 쉼표는 이 이하일 때만 센다(애매 — 목록)


def units(tokens, decode):
    """토큰 → [단위] , 단위 = [쪽] , 쪽 = [줄 문자열]. 화자 머리는 뺀다."""
    out, pages, lines, cur, skip, eat = [], [], [], "", False, False

    def end_line():
        nonlocal cur, eat
        lines.append(cur)
        cur = ""

    def end_page():
        nonlocal lines
        end_line()
        while lines and lines[-1] == "":
            lines.pop()  # 쪽 맨 끝 빈 줄(끝 개행)은 줄이 아니다
        if lines:
            pages.append(lines)
        lines = []

    def end_unit():
        nonlocal pages
        end_page()
        if pages:
            out.append([[ln for ln in pg[1:]] if len(pg) > 1 and pg[0] == "§" else pg for pg in pages])
        pages = []

    for t in tokens:
        if t.kind == "text":
            s = decode(bytes(t.raw))
            if skip:
                skip, eat = False, True
                continue
            eat = False
            cur += s
        elif t.kind == "ctl":
            if t.code == 0x1E:
                end_unit()
                skip = True
            elif t.code in (0x01, 0x03):
                if eat:
                    eat = False  # 화자 머리 뒤 줄 바꿈
                else:
                    end_line()
            elif t.code in PAGE:
                end_page()
            elif t.code in VARS or t.code in (0x0B, 0xEB, 0xEC):
                cur += "§"
        elif t.kind == "end":
            break
    end_unit()
    return out


def _syllables(seg: str) -> int:
    """읽는 소리 음절 수(숫자는 한 자 = 한 음절로 센다 — 2-13 ⑨ 근사)."""
    return len(re.findall("[가-힣]", seg)) + len(re.findall(r"\d", seg))


def comma_hits(pg, hit):
    """한 쪽의 쉼표 → 쉼표뺄것(접속부사 뒤 · 줄 끝 짧은 연결어미 뒤) · 쉼표애매(줄 안 짧은 연결어미 뒤)."""
    text, ends, n = "", set(), 0
    for li, ln in enumerate(pg):
        text += ln
        n += len(ln)
        if li < len(pg) - 1:
            ends.add(n - 1)
            text += " "
            n += 1
    for m in COMMA_RE.finditer(text):
        w = m.group(1)
        pre = text[: m.start()]
        seg = re.split(r"[.!?…~,]", pre)[-1].strip() + w
        if "§" in seg or not re.search("[가-힣]", w):
            continue
        if w in CONJ_HEAD and seg == w:
            hit("쉼표뺄것", "접속부사 " + text[max(0, m.start() - 6) : m.end() + 8])
        elif CONN_RE.search(w) and not NOT_CONN.search(w) and "기도" not in seg:
            prev = re.split(r"[.!?…~]", pre)[-1].split(",")
            if DAEGU_RE.search(re.split(r"[.!?…~,]", pre)[-1] + w) and (
                DAEGU_NEXT.match(text[m.end() :])
                or (len(prev) >= 2 and DAEGU_RE.search(prev[-2]))
            ):
                continue  # 같은 조사 두 절이 맞서는 대구 — 쉼표를 넣는다(2-13 ⑪, 마스터 11-06)
            syl, lineend = _syllables(seg), m.end() - 1 in ends
            ctx = text[max(0, m.start() - 14) : m.end() + 8]
            if lineend and syl <= CLAUSE_MAX:
                hit("쉼표뺄것", f"줄끝 {syl}음절 {ctx}")
            elif not lineend and syl <= CLAUSE_SHORT:
                hit("쉼표애매", f"줄안 {syl}음절 {ctx}")


def short_sentence_hits(pg, hit, tag):
    """한 줄에 통째로 들어가는데 두 줄 이상에 걸친 문장(2-10). 변수가 낀 문장은 실폭을 몰라 `layout.short_sentences` 가 이미 뺀다."""
    lim = BATTLE_W if tag.startswith("전투") else layout.WIDTH
    clean = [ln.replace("{", "「").replace("}", "」").rstrip(" ·") for ln in pg]
    for i0, j0, i1, j1 in layout.short_sentences(clean, lim):
        txt = " ".join(clean[i0 : i1 + 1])
        if len(re.findall("[가-힣]", txt)) >= 3:
            hit("한줄문장", " ⏎ ".join(clean[i0 : i1 + 1])[:40])


def audit_unit(pages, hit, tag=""):
    """한 단위의 쪽들 → hit(축, 내용) 호출."""
    for pg in pages:
        comma_hits(pg, hit)
        short_sentence_hits(pg, hit, tag)
    for pi, pg in enumerate(pages):
        for li, ln in enumerate(pg):
            plain = ln.replace("§", "")
            # 스트림 첫 줄은 변수·호출 뒤에 이어 붙는 조각일 수 있어(`<0e> 말이군요`) 공백이 어절 사이다 — 줄·쪽 머리만 본다
            if (li or pi) and ln.startswith(" ") and ln.strip() and not ln.endswith(" "):  # 양쪽에 공백이 있으면 칸 가운데 맞춤 라벨
                hit("첫칸공백", ln[:14])
            # 줄 머리로 넘어온 부호(`. , ! ? ) 」`) — 말줄임만 있는 줄·문장 머리 …는 대사 자체다
            if li and ORPHAN_HEAD.match(ln) and not re.fullmatch(r"[.,!?…~]{3,}", ln.rstrip()):
                hit("고아부호", pg[li - 1][-6:] + "⏎" + ln[:8])
            # 빈줄은 원판 짝과 개수를 맞대어 센다(blank_count) — 꽉 찬 줄(17.5) 뒤 개행은 화면에 빈 줄을 안 만든다(실측 000-1:0995)
            # 롬의 「」 글리프 코드는 decoder 가 `{ }` 로 읽는다(반각 0.5) · 끝의 `·` 는 코드 바이트 오독 — 폭에서 뺀다
            w = layout.tw(ln.rstrip(" ·").replace("{", "「").replace("}", "」").replace("§", "가" * int(VAR_W)))
            if "§" not in ln and w > layout.WIDTH and not tag.startswith("전투"):  # 전투 창은 폭이 달라 촬영으로 본다
                hit("넘침", f"{w:g} {ln[:16]}")
            if tag.startswith("전투") and "§" not in ln and w > BATTLE_W:  # 전투 창 한 줄(실측 23.0슬롯) — 이름 뒤에 이어 붙는 조각은 앞 이름 폭이 더해지니 촬영(battle_ctx --edges)으로 본다
                hit("전투넘침", f"{w:g} {ln[:16]}")
            if AFTER_PUNCT.search(ln):
                hit("부호뒤", AFTER_PUNCT.search(ln).group() + " " + plain[:12])
            if li and BOUND.match(ln) and not re.search(r"[.!?…」~]$", pg[li - 1].rstrip()):
                hit("접힘", pg[li - 1][-6:] + "⏎" + ln[:8])
    if len(pages) >= 2:
        prev = pages[-2][-1].rstrip() if pages[-2] else ""
        last = "".join(pages[-1])
        # 마지막 창이 한 어절 — 앞 창이 문장 끝으로 닫히면 그 어절이 한마디(「어이!!」)일 수 있어 문장이 이어질 때만 센다
        if layout._nwords(pages[-1]) == 1 and re.search("[가-힣]", last) and not layout._END_RE.search(prev):
            hit("꼬리한어절", f"{prev[-8:]}⏎{last[:10]}")
        # 줄 수 치우침 — 쪽이 문장 중간에서 갈렸는데 이웃 두 쪽의 줄 수 차가 2 이상(문장 끝에서 갈린 쪽은 글쓴이의 문장 나눔이라 센 대로 둔다)
        for i in range(len(pages) - 1):
            p, q = pages[i], pages[i + 1]
            if abs(len(p) - len(q)) >= 2 and not layout._END_RE.search(p[-1].rstrip()):
                hit("줄수치우침", f"{len(p)}/{len(q)} {p[-1][-8:]}⏎{q[0][:8]}")
    a, b = layout.orphan_pages(pages)
    for _ in range(b):
        hit("쪽끝고아", " ".join(p[-1] for p in pages)[:20])
    for _ in range(a - b):
        hit("쪽끝한어절", " ".join(p[-1] for p in pages)[:20])  # 문장이 거기서 끝나는 한 어절 — 낮음(정보)


COLOR_OPEN = {0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1F, 0xEE, 0xEF}


def color_mid(tokens, decode) -> int:
    """색 시작·복귀(04) 코드가 낱말 한가운데(앞 글 끝과 뒤 글 머리가 공백 없이 붙은 자리)에 놓인 수 — 원판과 개수를 맞대어 본다(번역이 색 범위를 낱말과 어긋나게 놓았나)."""
    n = 0
    toks = [t for t in tokens if t.kind != "eof"]
    for i, t in enumerate(toks):
        if t.kind == "ctl" and (t.code in COLOR_OPEN or t.code == 0x04) and 0 < i < len(toks) - 1:
            a, b = toks[i - 1], toks[i + 1]
            if a.kind == "text" and b.kind == "text":
                sa, sb = decode(bytes(a.raw)), decode(bytes(b.raw))
                if sa and sb and sa[-1] != " " and sb[0] != " ":
                    n += 1
    return n


def margin_diff(s: str, box_px: int, signed: bool = False) -> int | None:
    """가운데 맞춤 줄의 좌우 여백 차(px) — 글자 폭은 전각 12 · 반각(공백·ASCII) 6, 줄 끝 부호(. , …)는 폭에서 뺀다(2-8). 글이 없으면 None."""
    core = s.strip(" ")
    if not core:
        return None
    core = core.rstrip(".,…")
    lead = (len(s) - len(s.lstrip(" "))) * 6
    px = sum(6 if ord(c) < 0x80 else 12 for c in core)
    d = lead - (box_px - lead - px)
    return d if signed else abs(d)


def center_rows(rom: bytes, dec):
    """→ [(자리, 여백 차 px)] — 가운데 맞춤 자리 전부: 입장 배너 표(14B 칸) · HUD 지명 표(12B 칸) · 장 HUD 제목(30B) · 장 카드 첫 줄 · 서장 HUD 제목.
    (타이틀 그림 낱말은 잉크 여백으로 따로 쟀다 — 9px/10px, 1px.)"""
    rows = []
    mods = {(b, k): m for b, k, m in scene_sweep.built_modules(rom)}
    for (b, k), spots in banners.BY_MODULE.items():
        for off, n in spots:
            for i in range(n):
                at = off + banners.STRIDE * i
                t = dec(mods[(b, k)][at : at + banners.ENTRY])
                if t.strip():
                    # 배너 글꼴은 반각 한 칸 ≈ 8px · 글자 바탕 여백으로 대칭 칸이 평균 −3px(실측 11-09) — 칸 수로 실제 좌−우를 잰다
                    pl, pr = len(t) - len(t.lstrip(" ")), len(t) - len(t.rstrip(" "))
                    right_heavy = t.strip() in {banners.pua_text(n) for n in banners.RIGHT_HEAVY}
                    sg = BANNER_UNIT * (pl - pr) + (BANNER_BIAS_RIGHT if right_heavy else BANNER_BIAS)
                    rows.append((f"배너 {b}-{k}@{off:#x}[{i}]", abs(sg), sg, BANNER_UNIT, True))
    for i, (_p, raw) in enumerate(places.records(rom)):
        s = dec(raw)
        if s.strip() and sum(1 if ord(c) < 0x80 else 2 for c in s.strip()) <= places.CENTER:
            rows.append((f"지명 {i}", margin_diff(s + " " * (places.CENTER - sum(1 if ord(c) < 0x80 else 2 for c in s)), places.CENTER * 6), None, 6, False))
    for key, (_hud, card) in chapters.STREAMS.items():  # 장 제목은 빌더가 만드는 문안 그대로 잰다(스트림은 재배치돼 원래 자리에 없다)
        h = chapters.hud(key)
        rows.append((f"장HUD {key}", margin_diff(h, chapters.HUD_CENTER * 2), margin_diff(h, chapters.HUD_CENTER * 2, True), 6, False))
        if card is not None:
            c = chapters.card_first_line(key)
            rows.append((f"장카드 {key}", margin_diff(c, chapters.CARD_CENTER * 2), margin_diff(c, chapters.CARD_CENTER * 2, True), 6, False))
    t0 = dec(rom[0x3A194 : 0x3A194 + 30])
    rows.append(("서장 HUD", margin_diff(t0, chapters.HUD_CENTER * 2), margin_diff(t0, chapters.HUD_CENTER * 2, True), 6, False))
    return [r for r in rows if r[1] is not None]


# 갈무리14 배너 재측정(11-09): 대칭 칸 −2~−4(평균 −3)·왼쪽 올림 홀수 칸 +7·오른쪽 올림 둘(`banners.RIGHT_HEAVY`) −5 — 홀수 칸은 +7 쪽을 맞추려 편향 −1(대칭 칸은 −3 이라 판정이 같다)
BANNER_UNIT, BANNER_BIAS, BANNER_BIAS_RIGHT = 8, -1, 3


def not_nearest(sg: int, unit: int) -> bool:
    """「최대한 가운데」(규칙 2-8, 마스터 11-09) — 앞 공백을 한 칸 줄이거나 늘렸을 때(좌−우가 `2*unit` 움직인다) 더 가까운 자리가 있나. 같은 거리면 왼쪽(좌−우가 작은 쪽)이 맞다."""
    return any(abs(c) < abs(sg) or (abs(c) == abs(sg) and c < sg) for c in (sg - 2 * unit, sg + 2 * unit))


def window_count(pages) -> int:
    """글자가 든 창(쪽) 수 — 빈 쪽(화자 머리만 든 쪽 따위)은 세지 않는다."""
    return sum(1 for pg in pages if any(ln.strip() for ln in pg))


def blank_count(pages) -> int:
    """화면에 빈 줄을 만드는 줄 수(규칙 2-18, 마스터 11-08 — 화면 기준). **쪽 머리의 `<01>` 하나는 엔진이 빈 줄로 안 낸다**(석비 옛·새 롬 같은 화면, 실측)
    — 그 하나는 세지 않는다. 쪽 머리에 둘 이상 · 쪽 가운데의 빈 줄은 센다(쪽 끝 빈 줄은 units 가 이미 뗐다)."""
    n = 0
    for pg in pages:
        for li, ln in enumerate(pg):
            if ln.strip() != "" or (li == 0 and len(pg) == 1):
                continue
            if li == 0 and len(pg) > 1 and pg[1].strip() != "":
                continue  # 쪽 머리 빈 줄 하나(바로 뒤에 글줄)
            n += 1
    return n


# 원판 구조라 남기는 곳 — 전투 등장 문구는 `02`(몬스터 이름 줄) 아홉 개가 줄을 이루고, 몬스터가 적으면 빈 줄로 보인다(변수 자리, 글이 아니다)
STRUCT_BLANK = {"전투095:03ba": 2}


def selftest() -> bool:
    ok = True

    def got(pages):
        c = Counter()
        audit_unit(pages, lambda k, w: c.update([k]))
        return c

    cases = {
        "첫칸공백": [["가나다", " 라마바"]],
        "고아부호": [["가나다", "!?"]],
        "부호뒤": [["가나,다라"]],
        "접힘": [["그것을 이야기할 사람이", "를 만났다"]],
        "넘침": [["가" * 18]],
        "꼬리한어절": [["가나다 라마바 사아자", "차카타 파하"], ["그렇다."]],
        "쪽끝고아": [["가나다 라마바", "사아자"], ["차카타 파하 가나다 라마바."]],
        "줄수치우침": [["가", "나", "다"], ["라"]],
    }
    for k, pages in cases.items():
        if got(pages)[k] == 0:
            print(f"  ✗ 자체 시험: {k} 를 못 잡았다")
            ok = False
    if got([["안녕하세요 이 몸은 장군이다.", "잘 부탁한다."]])["한줄문장"] != 0:
        print("  ✗ 자체 시험: 한줄문장이 문장 끝 줄을 잘못 셌다")
        ok = False
    if got([["네, 여기", "있습니다. 감사합니다."]])["한줄문장"] != 1:
        print("  ✗ 자체 시험: 한줄문장을 못 잡았다")
        ok = False
    for pg, key in (([["그리고, 우리는 갔다."]], "쉼표뺄것"), ([["우리는 이 일을 맡고,", "가겠다."]], "쉼표뺄것"), ([["내가 봤다니까, 제스톤은 갔다."]], "쉼표애매")):
        if got(pg)[key] != 1:
            print(f"  ✗ 자체 시험: {key} 를 못 잡았다 {pg}")
            ok = False
    if sum(got([["아트라스, 그래, 가자.", "란도, 플로라, 신디."]]).values()):
        print("  ✗ 자체 시험: 부르는 말·나열 쉼표를 잡았다")
        ok = False
    for n, want in ((24, 1), (23, 0)):  # 전투 창 한 줄 23.0슬롯 — 24 는 넘침, 23 은 꽉 참(안 센다)
        c = Counter()
        audit_unit([["가" * n]], lambda k, w, c=c: c.update([k]), "전투001")
        if c["전투넘침"] != want:
            print(f"  ✗ 자체 시험: 전투넘침이 {n}슬롯 줄을 잘못 셌다")
            ok = False
    if margin_diff("   가나   ", 60) != 0 or margin_diff("  가나다   ", 66) != 6 or margin_diff(" 가나다. ", 48) != 0:
        print("  ✗ 자체 시험: 가운데 여백 차 계산이 틀렸다")
        ok = False
    if window_count([["가나", "다"], ["라"]]) != 2 or window_count([["가"], [" "], []]) != 1:
        print("  ✗ 자체 시험: 창 수(창적음)를 잘못 셌다")
        ok = False
    if (
        blank_count([["가나다", "", "라마바"]]) != 1
        or blank_count([["", "가나다"]]) != 0  # 쪽 머리 빈 줄 하나는 화면에 안 난다
        or blank_count([["", "", "가나다"]]) != 2
    ):
        print("  ✗ 자체 시험: 빈줄을 못 셌다")
        ok = False
    if sum(got([["안녕하세요, 왕자님.", "오늘은 날씨가 좋군요."]]).values()):
        print("  ✗ 자체 시험: 멀쩡한 쪽을 잡았다")
        ok = False
    if not (not_nearest(-11, 8) and not not_nearest(5, 8) and not_nearest(6, 6) and not not_nearest(-6, 6) and not not_nearest(-3, 8)):
        print("  ✗ 자체 시험: 가운데최근접 판정이 틀렸다")
        ok = False
    return ok


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin"
    if not selftest():
        print("❌ 검사기 자체 시험 실패 — 가짜 꼴을 못 잡았다")
        return 1
    dec = SP.decoder()
    cnt, rows, nunit = Counter(), [], 0
    rom_bytes = path.read_bytes()
    for tag, atoks, toks in SP.iter_pairs(common.rom(), rom_bytes):
        if not any("가" <= ch <= "힣" for t in toks if t.kind == "text" for ch in dec(bytes(t.raw))):
            continue
        nb_old = sum(blank_count(p) for p in units(atoks, lambda r: "가" * len(r)))  # 원판은 한글이 아니라 글자 수만 본다
        nb_new = sum(blank_count(p) for p in units(toks, dec)) - STRUCT_BLANK.get(tag, 0)
        if nb_new > 0:  # 절대 기준(규칙 2-18): 원문이 비워도 우리 문안은 빈 줄이 없다 — 원판과 견주지 않는다
            cnt["빈줄"] += nb_new
            rows.append(("빈줄", tag, f"화면 빈 줄 {nb_new} (원판 {nb_old})"))
        pg_old = sum(window_count(pages) for pages in units(atoks, lambda r: "가" * len(r)))
        pg_new = sum(window_count(pages) for pages in units(toks, dec))
        if pg_new < pg_old:
            cnt["창적음"] += pg_old - pg_new
            rows.append(("창적음", tag, f"원문 창 {pg_old} → 한글 {pg_new}"))
        if pg_new > pg_old:
            cnt["창많음"] += pg_new - pg_old
            rows.append(("창많음", tag, f"원문 창 {pg_old} → 한글 {pg_new}"))
        cm_old = color_mid(atoks, lambda r: "가" * len(r) if r.strip() else " ")
        cm_new = color_mid(toks, dec)
        if cm_new > cm_old:
            cnt["색낱말속"] += cm_new - cm_old
            rows.append(("색낱말속", tag, f"원판 {cm_old} → 롬 {cm_new}"))
        for pages in units(toks, dec):
            nunit += 1
            audit_unit(pages, lambda k, w, tag=tag: (cnt.update([k]), rows.append((k, tag, w))), tag)
    for site, d, sg, unit, banner in center_rows(rom_bytes, dec):
        if sg is not None and not_nearest(sg, unit):
            cnt["가운데최근접"] += 1
            rows.append(("가운데최근접", site, f"좌−우 {sg}px — 한 칸 옮기면 더 가깝다"))  # 지명 HUD 는 sg=None(박스 안 잉크 여백이 칸 수로 안 나온다 — 실측 시트로 본다)
        if banner:
            continue
        if d > 6:
            cnt["가운데어긋남"] += 1
            rows.append(("가운데어긋남", site, f"{d}px"))
        elif d > 1:
            cnt["가운데반칸"] += 1
            rows.append(("가운데반칸", site, f"{d}px"))
    line = " · ".join(f"{k} {cnt[k]}" for k in KEYS)
    print(f"  조판 전수 검사 — 단위 {nunit:,} · {line}")
    if "--list" in sys.argv:
        for k, tag, w in rows:
            print(f"  {k}\t{tag}\t{w}")
    if "--freeze" in sys.argv:
        BASE.write_text(json.dumps({k: cnt[k] for k in KEYS}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("  기준선을 썼다")
        return 0
    if not BASE.exists():
        print("❌ 기준선(typeset_audit_baseline.json)이 없다 — --freeze")
        return 1
    base = json.loads(BASE.read_text(encoding="utf-8"))
    bad = [k for k in KEYS if cnt[k] > base.get(k, 0)]
    if bad:
        print("❌ 기준선보다 늘었다: " + " · ".join(f"{k} {base.get(k, 0)}→{cnt[k]}" for k in bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
