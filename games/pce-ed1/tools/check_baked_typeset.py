"""조판 전수 게이트 — 공통 번역 규칙 2-1~2-17 + 4-6 을 **굽는 바이트**(`translate.compose` 출력)를 디코드한 쪽·줄에서 센다.

    python3 tools/check_baked_typeset.py            # 기준선(`typeset_baked_baseline.json`)보다 늘면 실패 · 줄면 알린다(래칫) — check.sh 가 부른다
    python3 tools/check_baked_typeset.py --list     # 위반 열쇠·미리보기를 축별로 찍는다
    python3 tools/check_baked_typeset.py --freeze   # 기준선을 지금 값으로(줄었을 때만)

왜 따로 두나: 번역 정본 문자열만 보는 기존 검사(`scene_check`·`linebreak_metrics`·`typeset_check --punct`)는 **조판기 입력**을 본다. 이 검사는 빌드가 실제로 쓰는
`compose` 바이트를 되읽어(글리프 코드 → 글자, 제어 옵코드 → 줄·쪽) 런타임 줄넘김 모델(`typeset_check.wrap`)에 태운 **결과**를 센다 — 화면에 나가는 것과 같은 단위다.

축(단위 = 쪽(창) 하나 · 문안 하나; 한 쪽에 같은 축이 여러 번이어도 1):
  2-1  부호(, . ! ?) 뒤에 공백 없이 글자가 붙음(소수점·`!?`·닫는 부호 앞·줄 끝 제외)
  2-2  부호(, . ! ?) 앞 공백
  2-3  고아 부호(줄 첫머리에 부호만) · 2-4 빈 줄 · 2-5 줄 첫 칸 공백 · 2-6 낱말 가운데서 넘어감 — `typeset_check.problems` ①②③④
  2-7  넘침 — 한 쪽의 런타임 줄 수가 창 한도(화자 첫 쪽 3 · 그 밖 4)보다 많다
  2-11 `…` 뒤 공백 · 2-12 `?!…` 순서 — 글자 단위(`typeset_check.punct_rows` 와 같은 정규식·예외)
  2-17 마지막 창 한 어절 고아 — 둘 이상의 쪽으로 나뉜 문안의 마지막 쪽이 한 줄·한 어절이고 앞 쪽이 문장 끝이 아니다(쪽 끝 온전한 한 문장은 괜찮다)
  4-6  색 제어 — 원판 대비 누락·안 닫힘(`check_style_ops` 가 순서 대조) + 이 검사가 **조립 바이트에서** 켜기 수 > 끄기 수(안 닫힘)를 센다

범위: 씬 대사(조립 바이트 전량) · 전투 문구(`script/sys/battle.json`, 가장 긴 이름·수치로 조립해 줄넘김) · 시스템 조립 문장(`typeset_check.cases`). 못 닿는 것은 「정적만」 —
전투·시스템은 런타임에 조각이 이어 붙으므로 조립 순서가 추정인 문장(`guess`)은 센다만 하고 실패 기준에서 같은 기준선으로 묶는다.
양성 대조: 같은 검출기에 일부러 틀린 쪽을 먹여 축마다 걸리는지 확인한다(안 걸리면 검사기가 죽은 것 — 실패).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import containers
import font
import glyphdyn
import messages as M
import translate as T
import typeset
import typeset_check as TC

BASELINE = common.GAME_DIR / "typeset_baked_baseline.json"
# 이음이 아닌 메시지 — 저장 순서로 앞 메시지(`…있었습니다.` + `0D`) 바로 뒤지만 **별개 갈래의 새 창**이다: 빈 보물상자 「(이름)은 보물상자를 다시 한번…」(씬 21·25·29 — 상자 열기 메시지 뒤 `0D` 다음에 이어 저장된 빈 상자 분기).
#   첫 칸 공백을 두면 「세리오스들 은」으로 이름과 조사가 떨어진다(마스터 11-17) — 이음 검사의 오탐이라 이 셋만 뺀다.
FRESH_AFTER_0D = {(21, "9fadde3af66697df"), (25, "9fadde3af66697df"), (29, "9fadde3af66697df")}
AXES = ("2-1", "2-2", "2-3", "2-4", "2-5", "2-6", "2-7", "2-11", "2-12", "2-17", "4-6", "H13", "2-NL")
SENT_END = set(".!?…~」』")
OPLEN = {**M.TEXT_OPS, **M.OTHER_OPS}
STYLE = T.STYLE_OPS
PUN = ",.!?"
RX_21 = re.compile(r"(?<![0-9])[,.!?](?=[가-힣A-Za-z0-9])")  # 부호 바로 뒤 글자(소수점 3.5 는 앞이 숫자라 제외)
RX_21B = re.compile(r"(?<=[0-9])[,.!?](?=[가-힣A-Za-z])")  # 숫자 뒤 부호 + 글자(「3.」 다음 글자) — 소수점이 아닌 꼴
JOSA_LEAD = re.compile(r"^ ?(은/는|을/를|이/가|와/과|으로/로)")  # 이름 변수 뒤에 이어지는 조사 조각
RX_22 = re.compile(r"[ 　][,.!?]")
RX_ELL = re.compile(r"…(?=[가-힣A-Za-z0-9])(?![가-힣A-Za-z0-9]…)")
RX_QE = re.compile(r"[?!？！]…")


# ── 디코드 ─────────────────────────────────────────────────────────────────


def inverse(btab: dict[str, bytes]) -> dict[bytes, str]:
    return {v: k for k, v in btab.items()}


def glyph_other(pair: bytes) -> str:
    """상주 글리프 표에 없는 두 바이트 — 반각 공백(F8 24) · 동적 조사 자리(F9 xx — 글자 한 칸) · SJIS 전각(`81 40` 공백 · `82 xx` 전각 영숫자 …)."""
    if pair == font.HALF_SPACE:
        return " "
    if pair[0] == 0xF9:
        return "이"
    try:
        return pair.decode("cp932")
    except UnicodeDecodeError:
        return "\ufffd"


def decode(by: bytes, inv: dict[bytes, str]):
    """조립 바이트 → (화자 머리 글자, 쪽 목록[쪽 = 줄 목록 문자열 + 색 켜기/끄기 수]). 쪽 경계 = 05/03, 끝 = 00/06/07, 줄 경계 = 01(문자열의 `\\n`)."""
    head, pages, cur = "", [], []
    on = off = 0
    pon = poff = 0
    i, in_head = 0, False
    n = len(by)
    while i < n:
        c = by[i]
        if c >= 0x24:  # 두 바이트 글리프
            ch = inv.get(by[i : i + 2])
            if ch is None:
                ch = glyph_other(by[i : i + 2])
            if in_head:
                head += ch
            else:
                cur.append(ch)
            i += 2
            continue
        if c == 0x1F:
            if cur or pages:  # 본문 중간의 이름 색 런(`1F 이름 04`, 씬 34 OFF 끝 쪽 화자) — 머리가 아니라 그 쪽의 글자다(줄 수에 든다), 색 켜기·끄기 짝도 맞춘다
                pon += 1
            else:
                in_head = True
            i += 1
            continue
        if c == 0x04:
            if in_head:
                in_head = False
                if i + 1 < n and by[i + 1] == 0x01:  # 이름 줄 끝 개행 — 본문 줄이 아니다
                    i += 1
            else:
                poff += 1
            i += 1
            continue
        if c == 0x01:
            cur.append("\n")
            i += 1
            continue
        if c in (0x05, 0x03):
            pages.append(("".join(cur), pon, poff))
            cur, pon, poff = [], 0, 0
            i += 1
            continue
        if c in (0x00, 0x06, 0x07):
            break
        if c in STYLE:
            pon += 1
        i += OPLEN.get(c, 1)
    if cur or not pages:
        pages.append(("".join(cur), pon, poff))
    return head, pages


# ── 축 검출(쪽 하나) ───────────────────────────────────────────────────────


def hangs(lines: list[str]) -> bool:
    """줄에서 매다는 부호(`! , . ?`)가 13칸 밖(칸 ≥ 13 — 창 오른쪽 틀 칸)에 찍히나. 런타임은 칸 13 의 부호를 넘기지 않고 **매단다**(`typeset_check.wrap`)
    — 틀 칸은 줄이 위로 밀려도 안 지워져 「. .」 잔상이 남는다(11-04 마스터 레벨업·상자 캡처). 수치 자리(`typeset.NUMCH`)는 8px."""
    for ln in lines:
        px = 0
        for ch in ln:
            if ch in TC.HANG and px // 12 >= TC.WIDTH:
                return True
            px += typeset.adv(ch)
    return False


def page_axes(text: str, *, cap: int, on: int = 0, off: int = 0, joined: bool = False, lead: str = "") -> set[str]:
    """한 쪽의 조립 글 → 걸린 축 집합. 런타임 줄넘김은 `typeset_check.wrap`(줄넘김 모델)."""
    hit: set[str] = set()
    if joined and text.startswith(" "):  # 앞 메시지(이름 변수 등)에 이어 쓰는 조각 — 첫 공백은 이음이다
        text = text[1:]
    lines, cuts = TC.wrap(text)
    if lead and hangs([(lead + text.lstrip(" ")).split("\n")[0][: len(lead) + 40]]):  # `lead` = 앞에서 인터프리터가 찍는 이름(파티 최장) — 조사 조각의 **첫 줄**만 이름까지 잰다(굽힌 줄 경계 기준 — 꽉 찬 줄 뒤엔 개행이 없어 재조판하면 거짓 양성)
        hit.add("H13")
    nonblank = [x for x in lines if x]
    silence = len(nonblank) == 1 and all(c in TC.PUNCT for c in nonblank[0])
    for p in TC.problems(lines, cuts):
        hit.add({"①": "2-3", "②": "2-4", "③": "2-5", "④": "2-6"}[p[0]])
    if silence:
        hit.discard("2-3")
        hit.discard("2-4")
    if len(lines) > cap:
        hit.add("2-7")
    for ln in text.split("\n"):  # 손 개행 줄 단위 — 줄 끝 부호는 뒤가 없어 안 걸린다
        if RX_21.search(ln) or RX_21B.search(ln):
            hit.add("2-1")
        if RX_22.search(ln):
            hit.add("2-2")
    flat = text.replace("\n", " ")
    for m in RX_ELL.finditer(flat):
        if re.search(r"(^|[\n\f「『(]|[.!?。] )$", flat[: m.start()]) or flat[: m.start()].strip() == "":  # 문장 끝 부호 + 공백 뒤 `…` 도 문장 맨 앞(11-06)
            continue
        pre = re.search(r"([가-힣]+)$", flat[: m.start()])
        if pre and flat.startswith(pre.group(1), m.end()):
            continue
        hit.add("2-11")
    if RX_QE.search(flat):
        hit.add("2-12")
    return hit


def unclosed(m: M.Message, pages: list[tuple[str, int, int]]) -> bool:
    """4-6 — 원문은 색을 켜고 껐는데(켜기 ≤ 끄기) 조립은 켜기만 많다(안 닫힘). 원문이 끝까지 안 껐으면(메시지 끝 초기화에 맡김) 같다."""
    o_on = sum(1 for t in m.tokens if isinstance(t, tuple) and t[1] in STYLE)
    o_off = sum(1 for t in m.tokens if isinstance(t, tuple) and t[1] == 0x04)
    g_on = sum(p[1] for p in pages)
    g_off = sum(p[2] for p in pages)
    return o_on <= o_off and g_on > g_off


def orphan_last(pages: list[tuple[str, int, int]], jp: str = "") -> bool:
    """2-17 — 둘 이상의 쪽, 마지막 쪽이 한 줄·한 어절이고 앞 쪽이 문장 끝이 아니다. 원문 마지막 창도 짧은 외침(6자 이하)이면 원문 그대로라 뺀다."""
    if len(pages) < 2:
        return False
    jl = [x for x in jp.split("\f") if x.strip()]
    if jl and len(re.sub(r"[\s\u3000]", "", jl[-1])) <= 6:
        return False
    last = pages[-1][0].strip()
    prev = pages[-2][0].strip()
    if not last or "\n" in last or " " in last or not prev:
        return False
    return prev[-1] not in SENT_END


# ── 양성 대조 ─────────────────────────────────────────────────────────────


def encode(text: str, btab: dict[str, bytes]) -> bytes:
    out = bytearray()
    for ch in text:
        if ch == "\n":
            out.append(0x01)
        elif ch == " ":
            out += font.HALF_SPACE
        else:
            out += btab[ch]
    return bytes(out) + b"\x00"


def end_to_end_control(btab: dict[str, bytes]) -> list[str]:
    """실제 글리프 표 → 바이트 → `decode` → 검출. 디코더가 코드·공백·개행을 잘못 읽으면(검출기가 조용히 0 을 내는 부류) 여기서 걸린다."""
    inv = inverse(btab)
    miss = []
    for ax, t in {"2-1": "왕자님,안녕하세요", "2-2": "왕자님 , 안녕", "2-12": "정말이냐?…", "2-11": "그래…그랬구나", "2-5": "왕자님\n 안녕"}.items():
        _, pages = decode(encode(t, btab), inv)
        if ax not in page_axes(pages[0][0], cap=4):
            miss.append(f"종단 {ax}")
    _, pages = decode(encode("왕자님, 안녕하세요.\n정말 반갑습니다.", btab), inv)
    if page_axes(pages[0][0], cap=4):
        miss.append("종단 오탐")
    return miss


def positive_control() -> list[str]:
    """일부러 틀린 쪽 — 축마다 걸려야 한다. 안 걸린 축 목록을 돌려준다."""
    cases = {
        "2-1": ("안녕하세요.반갑습니다", 4),
        "2-2": ("안녕하세요 . 반갑습니다", 4),
        "2-3": ("가나다라마바사아자차카타\n.", 4),
        "2-5": ("가나다\n 라마바", 4),
        "2-6": ("가나다라마바사아자차카타파하", 4),  # 낱말 가운데 넘김(공백 없는 14자)
        "2-7": ("가\n나\n다\n라\n마", 4),
        "2-11": ("그래…그랬구나", 4),
        "2-12": ("뭐라고?…", 4),
    }
    miss = []
    for ax, (t, cap) in cases.items():
        if ax not in page_axes(t, cap=cap):
            miss.append(ax)
    if "2-11" in page_axes("훔쳐 갔습니다. …어찌하면 좋겠습니까.", cap=4):  # 문장 끝 부호 뒤에서 시작하는 `…` 는 문장 맨 앞 — 붙여 쓴다(씬 110)
        miss.append("2-11 문장 가운데 시작 오탐")
    if "H13" not in page_axes("은 보물상자를 열었다.", cap=4, lead="세리오스") or not hangs(["최대 ＨＰ가 2000이 됐다!"]) or hangs(["최대 ＨＰ가", "2000이 됐다!"]):
        miss.append("H13")
    fake = M.Message(0, 0, None, None, [("op", 0x1D), "가나다", ("op", 0x04)])
    if not unclosed(fake, [("가나다", 1, 0)]) or unclosed(fake, [("가나다", 1, 1)]):
        miss.append("4-6")
    if orphan_last([("가나다 라마 바사아자차\n카타파하 거머", 0, 0), ("고", 0, 0)], jp="가나다라 마바사아자차카타파하 거머버서어저처커터퍼허 ㄱㄴㄷㄹㅁ") is False:
        miss.append("2-17b")
    if not orphan_last([("가나다라 마바사아자차\n카타파하 거머", 0, 0), ("고", 0, 0)]):
        miss.append("2-17")
    # 음성 대조 — 정상 쪽은 안 걸려야 한다
    ok = page_axes("안녕하세요. 반갑습니다.\n3.5 배 늘었다.", cap=4)
    if ok:
        miss.append(f"오탐 {sorted(ok)}")
    return miss


# ── 수집 ───────────────────────────────────────────────────────────────────


def scene_rows() -> dict[str, list[tuple[str, str]]]:
    hits: dict[str, list[tuple[str, str]]] = {a: [] for a in AXES}
    chars = glyphdyn.forced_chars() | (T.all_glyph_chars() & set(font._order_canon()))
    table, _ = font.build_table(chars)
    speakers = M.load_speakers()
    seen: set[tuple[int, str]] = set()
    nmsg = npg = 0
    for c in containers.scan():
        for b in c["blocks"]:
            sid = b["id"]
            trs = M.load_translations(sid)
            if not trs:
                continue
            btab, _ = glyphdyn.block_table(table, sid)
            inv = inverse(btab)
            typeset.set_scene(sid)
            prev = None  # (앞 메시지 열기 여부, 앞 메시지 마지막 쪽 끝 글자)
            for m in M.parse(b["data"]):
                prev_open, prev_tail = prev[:2] if prev else (False, "")
                # 앞 메시지 끝과 이 메시지 시작 **사이 바이트**(옵코드)에 쪽 넘김·줄바꿈이 있으면 새 창·새 줄이다 — 첫 공백은 이음이 아니라 첫 칸 공백이다
                gap = b["data"][prev[2] : m.start] if prev else b""
                # 🔴 00 = 문장 끝(키 대기 후 창 닫기) — 다음 메시지는 새 창이라 이음이 아니다(11-06 씬 76 「 침대를…」 첫 칸 공백)
                gap = gap.rstrip(bytes(T.STYLE_OPS))  # 🔴 11-11 틈 끝의 글자색 켜기(`1D` 등)는 흐름이 아니다 — 떼고 본다(씬 18 「 병사는…」: 틈 `0C 26 04 00 1D` = 창 닫기 뒤 색 켜기라 새 창 첫 칸인데 마지막 바이트만 봐 놓쳤다)
                gap_break = bool(gap) and ((len(gap) <= 8 and (gap[-1] in (0x05, 0x03, 0x01, 0x00) or (gap[-1] in (0x04, 0x06, 0x07) and 0x05 in gap)))  # `0C nn 05 04 06` = 쪽 넘김 뒤 표시 모드 복원·끝 — 새 쪽(씬 69 「…완성되었습니다.」 뒤 「석비에는」, 11-18)
                                                   or (b"\x0f" in gap and not re.match(r"^ (은/는|을/를|이/가|와/과|으로/로)", (trs.get(m.key) or {}).get("t", ""))))  # 점프(0F)가 낀 틈은 흐름이 끊긴다 — 이름 변수 뒤 조사 조각(「 은/는 …」)은 예외(변수가 앞에서 찍힌다)  # 메시지 바로 앞의 마지막 옵코드가 쪽 넘김·줄바꿈 — 글이 새 쪽·새 줄에서 시작한다
                tr = trs.get(m.key)
                if tr is None or tr.get("raw"):
                    prev = None
                    continue
                if (sid, m.key) in seen:
                    prev = None
                    continue
                seen.add((sid, m.key))
                if "\n" in tr.get("t", "") and m.speaker is None and m.common is None:
                    prev = None  # 🔴 11-20: 건너뛴 메시지가 사이에 끼면 그 앞 메시지는 이음 후보가 아니다(씬 54 오델로 「자네 차례일세」: 사이의 할머니 메시지(`00` 종료)를 건너뛰고 한참 앞 메시지를 「앞」으로 봐 첫 공백을 이음으로 오인)
                    continue  # 장 끝 카드 — 손으로 맞춘 줄
                by = T.compose(m, tr, btab, speakers)
                head, pages = decode(by, inv)
                nmsg += 1
                # 2-1(이음) — 앞 메시지가 종료 없이 이어지는데 부호로 끝났고 이 메시지가 공백·개행 없이 글자로 시작 — 같은 줄에 「다.뭘」 로 붙는다(화면 전수 표본, 11-02)
                first = pages[0][0]
                if prev_open and (sid, m.key) not in FRESH_AFTER_0D and not gap_break and prev_tail and prev_tail in PUN and not head and first and first[0] not in " \n" and (first[0].isalnum() or "가" <= first[0] <= "힣"):
                    hits["2-1"].append((f"scn{sid:03d}:{m.key[:8]}", f"이음 ⟨…{prev_tail}|{first[:8]}⟩"))
                tail_txt = pages[-1][0].rstrip(" ")
                end_op = by.rstrip(b"\x00\x06\x07")[-1:]  # 쪽 넘김(05·03)·줄바꿈(01)으로 끝나면 다음 메시지는 새 쪽·새 줄 — 이음이 아니다
                prev = (not m.terminated and m.cont is None and end_op not in (b"\x05", b"\x03", b"\x01"), "" if pages[-1][0].endswith(" ") else tail_txt[-1:], m.end)  # 끝에 공백이 있으면 이음 경계가 이미 떨어져 있다(이름 변수가 끼는 곳 — 씬 41 「이셨나. 〔게일〕이라고」)
                npg += len(pages)
                tag = f"scn{sid:03d}:{m.key[:8]}"
                for pi, (text, pon, poff) in enumerate(pages):
                    cap = 3 if (head and pi == 0) else 4
                    frag = pi == 0 and not head and bool(m.tokens) and isinstance(m.tokens[0], str) and not gap_break  # 원문이 글로 시작(이름 변수 뒤 이음 조각 「…말씀이군요」) **이고 바로 앞 메시지와의 사이 옵코드에 쪽 넘김·줄바꿈이 없을 때만** 첫 공백이 이음이다(코드가 변수를 찍고 이어 가는 흐름은 정적으로 못 보니 그 밖은 이음으로 본다)(11-04: 앞 쪽이 끝나 새 창이 열리는데도 면제해 씬 18 「 그리고 제가」 의 첫 칸 공백을 놓쳤다)
                    for ax in page_axes(text, cap=cap, on=pon, off=poff, joined=frag, lead=(T.JOIN_NAME if m.key in T.JOIN_KEYS else TC.ACTOR) if (pi == 0 and JOSA_LEAD.match(tr.get("t", ""))) else ""):
                        hits[ax].append((tag, f"쪽{pi + 1} ⟨{text.replace(chr(10), '|')[:40]}⟩"))
                # 2-NL(11-11) — 원문이 끝 개행(`01`)으로 끝나는 열린 메시지는 우리 조립도 `01` 로 끝나야 한다: 꽉 찬 13칸 줄 뒤에서 `01` 을 빼면 다음 메시지가 같은 줄에 붙어
                #   `wordck` 가 「…요.」+「또」를 한 어절로 아랫줄에 내린다(씬 45·46·47 밀매상 「없습니다요.또 들러 주십쇼.」)
                if not m.terminated and m.tokens and m.tokens[-1] == ("op", 0x01) and not tr.get("raw") and by[-1:] not in (b"\x01", b"\x05") and pages[-1][0].strip():  # 쪽 넘김(05)으로 끝나도 다음 메시지는 새 쪽 — 줄이 안 붙는다(11-18 씬 69 게일 합류)
                    hits["2-NL"].append((tag, f"끝 개행 없음 ⟨…{pages[-1][0][-14:]!r}⟩".replace("\n", "|")))
                if unclosed(m, pages):
                    hits["4-6"].append((tag, f"켜기 {sum(p[1] for p in pages)} 끄기 {sum(p[2] for p in pages)} ⟨{pages[-1][0][:30]!r}⟩".replace("\n", "|")))
                if orphan_last(pages, m.jp):
                    hits["2-17"].append((tag, f"⟨{pages[-2][0][-14:]!r} / {pages[-1][0]!r}⟩".replace("\n", "|")))
    hits["_n_scene"] = nmsg  # type: ignore[assignment]
    hits["_n_pages"] = npg  # type: ignore[assignment]
    return hits


def battle_system_rows(hits: dict) -> None:
    """전투 문구 · 시스템 조립 문장 — 이미 조립·줄넘김을 흉내 내는 `typeset_check` 의 결과(줄)에 부호 축을 더한다."""
    bt, nbt, _mon = TC.battle_rows()
    for k, lines, probs in bt:
        for p in probs:
            if p.startswith("③") and lines and lines[0].startswith(" ") and p.endswith("1줄"):
                continue  # 이름 변수 뒤에 이어 붙는 조각(` 내려갔다!`) — 첫 공백은 이음이다
            hits[{"①": "2-3", "②": "2-4", "③": "2-5", "④": "2-6"}[p[0]]].append((f"전투:{k[:8]}", "|".join(lines)))
    sy = TC.run() or []
    # 변수 폭 훑기 — 수치 1~4자리(자리마다 8px) × 파티 이름 전부. 가장 긴 값만 재면 짧은 값에서 부호가 틀 칸에 걸리는 걸 놓친다(11-04 「최대 ＨＰ가 16포인트 올랐다.」)
    glos = TC.sysbuild.glossary()
    party = sorted({glos[k] for k in ("セリオス", "ロウ", "ゲイル", "ソニア", "リゼル", "ルディア") if k in glos} | {TC.ACTOR})
    keep = (TC.ACTOR, TC.VALUE)
    swept = set()
    for actor in party:
        for nd in (1, 2, 3, 4):
            TC.ACTOR, TC.VALUE = actor, typeset.NUMCH * nd
            for c, lines, _p in TC.run() or []:
                if hangs(lines) and (c.name, nd) not in swept:
                    swept.add((c.name, nd))
                    hits["H13"].append((f"시스템:{c.name}", f"{actor}·{nd}자리 " + "|".join(lines).replace(typeset.NUMCH, "#")))
            for k, lines, _p in TC.battle_rows()[0]:
                if hangs(lines) and (k, nd) not in swept:
                    swept.add((k, nd))
                    hits["H13"].append((f"전투:{k[:8]}", f"{nd}자리 " + "|".join(lines).replace(typeset.NUMCH, "#")))
    # 11-08 마스터 「전투중 창 초과하면 초과된 부분이 남아」 — 위는 문제 있는 줄·가장 긴 이름만 훑었다. 몬스터 이름 전부 × 자릿수 × 문제 없는 줄까지(이름 앞붙임 문구만 이름에 따라 달라진다)
    import battle as _battle

    _names = sorted(set(_battle.kr_names()[0].values()))
    for nm in _names:
        for nd in (1, 2, 3, 4):
            TC.VALUE = typeset.NUMCH * nd
            for k, lines, _p in TC.battle_rows(mon=nm, include_ok=True)[0]:
                if hangs(lines) and (k, "mon") not in swept:
                    swept.add((k, "mon"))
                    hits["H13"].append((f"전투:{k[:8]}", f"{nm}·{nd}자리 " + "|".join(lines).replace(typeset.NUMCH, "#")))
    TC.ACTOR, TC.VALUE = keep
    for c, lines, probs in sy:
        for p in probs:
            hits[{"①": "2-3", "②": "2-4", "③": "2-5", "④": "2-6"}[p[0]]].append((f"시스템:{c.name}", "|".join(lines)))
    # 부호 축(문자열 단위) — 전투·시스템·씬 정본 밖 모든 script/sys 문자열
    n = 0
    for f in sorted((common.GAME_DIR / "script" / "sys").glob("*.json")):
        if f.name in ("labels.json", "names.json"):
            continue

        def walk(o, key=""):
            nonlocal n
            if isinstance(o, dict):
                for k, v in o.items():
                    if k.startswith("_"):
                        continue
                    walk(v, k)
            elif isinstance(o, list):
                for v in o:
                    walk(v, key)
            elif isinstance(o, str):
                n += 1
                t = re.sub(r"\{(01|00|06|07|0A)\}", "\n", o)  # 줄바꿈·메시지 끝·분기(0A — 다음 조각은 따로 읽힌다)
                t = re.sub(r"\{[0-9A-Fa-f]+\}", "", t)  # 제어 토큰은 폭이 없다(공백이 아니다)
                for ln in t.split("\n"):
                    if RX_21.search(ln) or RX_21B.search(ln):
                        hits["2-1"].append((f"sys:{f.stem}:{str(key)[:8]}", ln[:40]))
                    if RX_22.search(ln):
                        hits["2-2"].append((f"sys:{f.stem}:{str(key)[:8]}", ln[:40]))

        walk(json.loads(f.read_text("utf-8")))
    hits["_n_battle"] = nbt
    hits["_n_sys"] = len(sy)


def counts(hits: dict) -> dict[str, int]:
    return {a: len(hits[a]) for a in AXES}


def main() -> int:
    miss = positive_control()
    chars_ = glyphdyn.forced_chars() | (T.all_glyph_chars() & set(font._order_canon()))
    table_, _ = font.build_table(chars_)
    miss += end_to_end_control(table_)
    if miss:
        print("✗ 양성 대조 실패 — 검출기가 못 거른 축:", miss)
        return 1
    hits = scene_rows()
    battle_system_rows(hits)
    cnt = counts(hits)
    base = json.loads(BASELINE.read_text("utf-8")) if BASELINE.exists() else {}
    print(
        f"조판 전수(굽는 바이트): 씬 문안 {hits['_n_scene']}({hits['_n_pages']}쪽) · 전투 문구 {hits['_n_battle']} · 시스템 조립 {hits['_n_sys']} — "
        + " ".join(f"{a}={cnt[a]}" for a in AXES)
    )
    if "--list" in sys.argv:
        for a in AXES:
            print(f"== {a} ({cnt[a]})")
            for tag, pv in hits[a][:60]:
                print(f"  {tag}  {pv}")
    if "--freeze" in sys.argv:
        BASELINE.write_text(json.dumps(cnt, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print("기준선을 지금 값으로 내렸다")
        return 0
    bad = [a for a in AXES if cnt[a] > base.get(a, 0)]
    for a in bad:
        print(f"✗ {a}: {cnt[a]} > 기준선 {base.get(a, 0)}")
    down = [a for a in AXES if cnt[a] < base.get(a, 0)]
    if down:
        print("줄었다 — `--freeze` 로 기준선을 내린다:", {a: (base[a], cnt[a]) for a in down})
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
