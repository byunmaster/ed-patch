"""번역 정본 → 씬 블록 바이트 합성.

정본(커밋):
    script/speakers.json      {"侍女": "시녀", …}   화자 이름(JP 는 단어 수준이라 커밋 OK)
    script/scnNNN.json        {"messages": {열쇠: {"t": "우리 문안"}}}   열쇠 = messages.Message.key
        `t` 는 산문. `\\n` 하드 개행 · `\\f` 강제 페이지. 조판은 typeset.pages 가 한다.
JP 원문은 정본에 없다 — `work/derived/messages/scnNNN.json` 이 열쇠↔원문 대조표다(커밋 안 함).

합성: [1F 화자 04 | 09 nn] + (원문이 화자 뒤 01 로 시작했으면 01) + 줄들(01) · 창(05) + 종료(원문 것).
종료가 없는 조각(화자 전환·옵코드 앞에서 끊긴 메시지)은 splice 가 `0F` 로 다음 자리에 잇는다.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import messages as M
import typeset

PAGE = 0x05
NL = 0x01


class TranslateError(Exception):
    pass


def body_chars(scene_id: int) -> set[str]:
    """씬 하나의 대사 본문이 쓰는 우리 글리프 글자(화자 이름은 `name_chars`)."""
    out: set[str] = set()
    for e in M.load_translations(scene_id).values():
        out |= {ch for ch in font.expand_packed(e["t"]) if font.needs_glyph(ch)}
    return out


def _jp_corpus() -> str:
    """이 게임 원문 전체(씬 대사·시스템 표·전투 표의 JP 문자열)를 한 덩이로 — 정본 이름이 이 게임에 나오나 가르는 데 쓴다.
    ⚠ 부분 문자열 일치라 넉넉하게 잡힌다(과포함은 안전, 누락은 없다). 파생물이 없으면 죽는다 — 조용히 전체로 돌아가지 않는다."""
    import glob
    import json

    out: list[str] = []

    def walk(o) -> None:
        if isinstance(o, str):
            out.append(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                out.append(str(k))
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    import common

    root = common.OUT_DIR
    files = [f for d in ("messages", "sys", "battle") for f in sorted(glob.glob(str(root / d / "*.json")))]
    if not files:
        raise FileNotFoundError(f"원문 파생물이 없다: {root}/(messages|sys|battle)")
    for f in files:
        walk(json.loads(Path(f).read_text("utf-8")))
    return "\n".join(out)


def name_chars() -> set[str]:
    """씬 대사 밖에서 오는 우리 글리프 글자 — 공용 정본(고유명사·UI·화자)의 화면 표기. 🔴 늘 상주한다."""
    # 🔑 **화면에 나가는 표기만** 공용에서 받는다(`kr_texts`) — 열쇠도 `_aliases` 도 안 온다.
    #    ⚠ `load_speakers()` 는 **맵**이라 조판이 쓰고, 글리프 커버리지는 이쪽이다.
    import canon  # shared/ — 공통 문안 정본(ED1 = PS1 씨앗)

    # 정본은 화면에 나가는 범주만(ui·speaker) — system·battle 문구 조각은 이 게임이 안 쓰는 것이 많아 글리프를 낭비한다
    chars: set[str] = set()
    canon_vals = [v for c in ("ui", "speaker") for v in canon.table(c, "ed1").values()]
    # 🔴 고유명사는 **이 게임 원문에 실제로 나오는 이름만** — 정본은 ED1·ED2 공통이라 전체를 잡으면 다른 게임이 이름을
    #    더할 때마다 이 게임의 상주 칸이 깎인다(10-18 「흰슬러그」·「넬」). 안 나오는 이름의 글자는 상주 대상이 아니고,
    #    대사 본문에만 쓰이면 `body_chars` → 블록 동적 칸으로 간다. 상주 순서(`glyph_order.json`)는 안 건드린다.
    corpus = _jp_corpus()
    names = [kr for _c, jp, kr in canon.all_names("ed1") if jp in corpus]
    for v in names + canon_vals + list(M.load_speaker_overrides().values()):
        chars |= {ch for ch in v if font.needs_glyph(ch)}
    return chars


def all_glyph_chars() -> set[str]:
    """정본 전체가 쓰는 우리 글리프 글자(한글·부호·숫자) — 대사 본문 + 이름. 상주/동적 가름은 `glyphdyn`."""
    chars = set(name_chars())
    for p in sorted(M.SCRIPT_DIR.glob("scn*.json")):
        chars |= body_chars(int(p.stem[3:]))
    return chars


STYLE_OPS = frozenset(range(0x19, 0x21)) - {0x1F}  # 글자색·강조 옵코드(1D = 해설·품목 이름 뒤 색 바꿈 …) — 1바이트, 폭 없음
PAGE_OPS = (0x05, 0x03)
TAIL_OK = frozenset({0x04, 0x05, 0x03, 0x00, 0x06, 0x07}) | STYLE_OPS  # 끝 옵코드 줄에 이것만 있으면 통째로 낸다


def _page_style_ops(m: M.Message) -> list[tuple[int, int]]:
    """[(원문 쪽 번호, 옵코드)] — 메시지 첫머리나 쪽 옵코드(`05`·`03`) 바로 뒤에 오는 글자색 옵코드만.
    🔴 컴포즈가 이걸 안 내서 해설(초록)이 흰색으로, 품목 이름 뒤 문구가 노란색으로 나갔다(마스터 10-29 — 첫 번역 도구 때부터 빠져 있었다).
    쪽 한가운데의 색 옵코드는 번역 문안에 자리를 못 대므로 내지 않는다."""
    out = []
    pg = 0
    for i, t in enumerate(m.tokens):
        if not isinstance(t, tuple):
            continue
        if t[1] in PAGE_OPS:
            pg += 1
        elif t[1] in STYLE_OPS and (i == 0 or m.tokens[i - 1] in (("op", 0x05), ("op", 0x03))):
            out.append((pg, t[1]))
    return out


def _page_end_resets(m: M.Message) -> set[int]:
    """색 되돌림(`04`)이 쪽 옵코드 바로 앞에 오는 원문 조각 번호들 — 마지막 조각의 끝은 `compose` 의 끝 옵코드 줄이 낸다."""
    out = set()
    pg = 0
    for i, t in enumerate(m.tokens):
        if not isinstance(t, tuple):
            continue
        if t[1] in PAGE_OPS:
            pg += 1
        elif t[1] == 0x04 and i + 1 < len(m.tokens) and m.tokens[i + 1] in (("op", 0x05), ("op", 0x03)):
            out.add(pg)
    return out


# 원판이 엉뚱한 이름을 글자로 박은 화자 머리를 정본 인물로 바로잡는다(마스터 11-05 「입구의 병사로 되어있다면 그건 버그같아」) — 열쇠 → 원문 화자 이름.
SPEAKER_FIX: dict[str, str] = {}  # 🔴 비어 있다(11-06 마스터 「여긴 입구의 병사가 맞아」) — 씬 41 「뭐, 뭐라고!?」(4bc93adb…)의 원판 머리 「入口の兵士」는 맞는 화자라 로우로 바꾸지 않는다. 11-05 에 로우로 둔 것은 되돌렸다. 로우로 고칠 줄은 #6 「뭐야 너, 이분을…」 하나(머리 `09 02` = 파티 둘째 칸 — 정상 진행에서 로우)이고 그건 문안·머리 바이트로 이미 맞다
# 앞 메시지 끝 글(「…나는 」)에 **이름 변수**가 이어 찍히는 메시지(`voice_sched.inline_name`) — 화자 창이 아니라 앞 줄 끝에서 이어 쓰는 줄이다(씬 41 「나는 〈게일〉이라고 하는데…」, 마스터 11-05).
# 일반화하면 다른 씬 지문이 움직여 열쇠로 명시한다.
INLINE_LEAD = {"9223868c8171327f"}
_JOSA_LEAD = re.compile(r"(은/는|을/를|이/가|와/과|으로/로)")
_JOSA_MARK = "\uE0F0"  # 조사 토큰을 한 글자로 재기 위한 자리표시(12px)
# 아이템 이름 변수(`0E`) 뒤에 이어지는 조사 조각 중, 가장 긴 아이템 이름(88px — 「오비스3 지팡이」 등)에서 마침표가 칸 13 에 매달리는 것(11-05 상점·획득 문구 정적 전수 9메시지) — 이름 폭을 앞 줄로 보고 짠다.
ITEM_LEAD_PX = 88
ITEM_LEAD_KEYS = {"13b66243f5a5d657", "18707d602e09b9d0", "307c3a628f63c549", "3d9064889e3b1a10", "4052436f1fba7dd6", "426a922f914976f9", "5a4fe8f6a8ad3e2e", "a15fb5a15ffe078e", "c52d3234408ec07f"}
# 🔴 「{이름}이 동료가 되었습니다」(원판 「{이름}が仲間になりました。」 — 이름 뒤 개행 없음): 합류하는 동료(씬 18 류난 · 32 로우 · 41 게일 · 69 게일)의 이름은 두 글자(24px)라 한 줄로 낸다(11-06 마스터 「한줄에 나올 것 같은데 두줄로 나오네」). 세리오스가 이어질 일은 없다.
# 🔴 장 끝 카드 앞 문장(씬 19 「…해방되었습니다.」, 종료 `06 08` 뒤에 제목 메시지가 같은 창에 이어진다) — 줄이 덜 찬 채 끝나면 제목이 문장 줄 뒤에 붙는다(11-15 재촬영).
#    원문은 줄이 꽉 차서 제목이 다음 줄로 갔을 뿐이라 우연이다. 끝에 개행(`01`)을 내 제목이 늘 제 줄에서 시작하게 한다. 꽉 찬 줄 뒤엔 인터프리터가 스스로 넘기므로 안 낸다.
CARD_LEAD_KEYS = {"c535c4fa26f502cf"}
# 보물상자 「(품목)이/가 들어 있었습니다.」 — 긴 품목 이름 뒤에서 「이」가 줄 끝에 못 들어가 다음 줄로 가면, 우리가 낸 개행이 「이」와 「들어」를 또 갈랐다(마스터 11-17 「들어 있었습니다. 는 윗줄에 이어져야」).
# 개행 없이 한 줄로 두면 엔진이 이름 폭대로 접는다 — 「…깃털 / 이 들어 있었습니다.」
# 🔴 「{품목}을/를 받았습니다·건넸습니다·말씀이시죠」 조각 전부(마스터 11-18 「점토를 받았습니다. 가 한줄에 나와야하는데 개행되었어」): 앞 폭을 최장 품목(88px)으로 잡아 「품목+조사」 뒤에서 **늘** 줄을 갈랐다 — 짧은 이름도.
#    앞 폭을 안 주고 한 줄로 짠다(줄넘김은 엔진 `wordck` 가 실제 이름 폭대로 어절에서 한다).
FREE_FLOW_KEYS = {"307c3a628f63c549", "13b66243f5a5d657", "18707d602e09b9d0", "3d9064889e3b1a10", "4052436f1fba7dd6", "426a922f914976f9", "5a4fe8f6a8ad3e2e", "a15fb5a15ffe078e", "c52d3234408ec07f"}
JOIN_KEYS = {"9ccdf127e26e6daf", "b27d8c0c4008c32f"}  # 씬 63 의 「소니아가」(82841ed9…)는 156px 꽉 찬 줄이라 따로 둔다(종전 두 줄)
# 한 창(OFF) 안에서 쪽마다 화자가 갈리는 메시지 — {(씬, 열쇠): {쪽 번호(0부터): 화자}}. 음성 자막(ON)의 `voice_sched` `page_speakers` 와 같은 사실(씬 34 끝 쪽 「오오오오!!」 = 레지스탕스들, 마스터 11-17)
PAGE_SPEAKER = {(34, "71be6cb377aba2e5"): {3: "레지스탕스들"}}
JOIN_NAME = "류난"
NAME_LONGEST = "세리오스"  # 파티 다섯 중 최장(`typeset_check.ACTOR` 와 같은 값 — 정본 사전 person 「セリオス」)


def compose(m: M.Message, tr: dict, table: dict[str, bytes], speakers: dict[str, str], lead_px: int = 0) -> bytes:
    out = bytearray()
    if m.speaker is not None:
        name = SPEAKER_FIX[m.key] if m.key in SPEAKER_FIX else speakers.get(m.speaker, m.speaker)
        out += b"\x1f" + font.encode(name, table, msg=True) + b"\x04"  # 화자명도 대사창 — 공백 반각
    elif m.common is not None:
        out += bytes([0x09, m.common])
    lead_nl = (bool(m.tokens) and m.tokens[0] == ("op", NL)) or bool(m.key_fixed and m.speaker is not None)  # 나중에 단 화자 머리(밀매상)도 이름 줄 끝에 개행(마스터 11-18)
    # 🔴 **첫 줄을 비우는 머리 개행은 안 낸다**(마스터 10-31 「첫줄을 굳이 비워놔야할 이유도 없는것 같아서 우리는 첫줄부터」 — 원문 2줄 서술이 가운데 느낌을 내던 꼴이
    #    우리 3줄에선 빈 줄만 남았다, gon 009). 앞 메시지가 찍던 줄 끝에 **이어 붙는** 메시지(`lead_px`)의 머리 개행은 줄바꿈이라 그대로 낸다.
    if lead_nl and (lead_px or m.speaker is not None or m.common is not None):  # 화자 머리 뒤 개행은 「이름 줄 끝」이라 그대로(007 기준 화면: 이름 밑에 바로 글)
        out.append(NL)
    style = _page_style_ops(m)
    resets = _page_end_resets(m) if style else set()
    pgs: list = []
    out += bytes(op for k, op in style if k == 0)
    if tr.get("raw"):
        # 🔴 **조판기(`typeset.pages`→공용 `krwrap`)를 아예 안 거친다** — 원판이 가운데맞춤을 앞뒤
        #    전각 공백으로 **미리 구워** 낸 고정폭 표(필드 입장 배너 지명 46개, `scn000.json`)라 어절
        #    경계 공백을 지우는 일반 대사 조판기를 태우면 공백이 사라져 왼쪽 정렬이 된다(devlog 09-27).
        #    `krwrap` 은 공용(`shared/`)이라 이 게임에서 못 고친다 — 문안 쪽에서 통째로 비켜 간다.
        import center_plan

        for i, seg in enumerate(tr["t"].split(center_plan.HALF_MARK)):  # 배너 가운데용 반 칸 공백(4px)
            if i:
                out += font.HALF_SPACE
            for j, part in enumerate(seg.split(center_plan.JOIN_MARK)):  # 글자 바로 뒤 반 칸 = 앞 글자 변형 코드(코드 한 개 절약)
                if j:
                    out[-2:] = font.variant(bytes(out[-2:]))
                out += font.encode(part, table)
    else:
        # 🔴 **줄머리 공백은 조판기가 지우므로 여기서 따로 낸다** — 앞 메시지가 찍은 품목 이름 바로 뒤에 이어지는 문안
        #    (「약초 말이군. 정말 고마워.」)은 이름과 띄어야 하는데, `krwrap` 이 줄머리 공백을 먹어 「약초말이군」으로 붙었다.
        lead_sp = len(tr["t"]) - len(tr["t"].lstrip(" "))
        if lead_sp:
            out += font.encode(" " * lead_sp, table, msg=True)
        bounds: list[int] = []
        src = tr["t"].lstrip(" ")
        # 🔴 **이름 변수 뒤에 이어지는 조사 조각**(「 은/는 보물상자를 열었다.」 — 앞 이름은 인터프리터가 찍는다)은 이름 폭을 모르면 줄이 13칸을 넘는다
        #    (11-04 마스터 「세리오스는 보물상자를 열었다.」 마침표가 틀 칸에 걸림). 파티 최장 이름 폭을 앞 줄 폭(`lead_px`)으로 주고, 조사 토큰은 한 글자(12px)로 잰다.
        jm = _JOSA_LEAD.match(src) if not lead_px else None
        if jm:
            lead_px = ITEM_LEAD_PX if m.key in ITEM_LEAD_KEYS else typeset.px(JOIN_NAME if m.key in JOIN_KEYS else NAME_LONGEST)
            if m.key in FREE_FLOW_KEYS:
                lead_px = 0  # 앞 폭을 안 주고 한 줄로 짠다 — 줄넘김은 엔진(`wordck`)이 이름 폭대로 한다
            src = _JOSA_MARK + src[jm.end() :]
        pgs = typeset.pages(
            font.expand_packed(src),
            speaker=False if (m.key in INLINE_LEAD and lead_px) else M.speaker_kind(m, typeset._SCENE),
            lead_px=lead_px,
            four=True,
            keep_windows=typeset.keep_windows(typeset._SCENE),
            _bounds=bounds,
        )
        if jm:
            pgs = [pg if isinstance(pg, typeset.Card) else [ln.replace(_JOSA_MARK, jm.group(0)) for ln in pg] for pg in pgs]
            if len(pgs[0]) > 1 and not isinstance(pgs[0], typeset.Card) and m.key not in JOIN_KEYS and m.key not in FREE_FLOW_KEYS:
                # 한 줄에 안 들어가면 **이름+조사 뒤에서** 끊고 나머지를 새 줄부터 짠다(「세리오스는 / 보물상자를 열었다.」 — 끝 낱말 하나만 외톨이로 내려가는 것보다 낫다, 마스터 11-04 요청 예시)
                alt = typeset.pages(font.expand_packed(src[1:].lstrip(" ")), speaker=False, four=True)
                if len(alt[0]) + 1 <= 4:
                    pgs = [[jm.group(0), *alt[0]], *alt[1:]]
        # 하드 개행이 든 화자 없는 창(장 끝 카드)은 줄을 그대로 둔 것이라 **개행도 그대로** 넣는다 —
        # 꽉 찬 제목 줄 뒤의 빈 줄이 먹혔다(종장 카드 화면 2026-09-25: 13칸 제목 바로 밑에 「끝」).
        for i, pg in enumerate(pgs):
            if i:
                # 색 되돌림(`04`)은 원문에서 쪽 옵코드 바로 앞에 온다 — 조각(`\f`)이 끝나는 쪽 앞에 낸다
                if style and any(bounds[min(kk, len(bounds) - 1)] == i for kk in range(1, len(bounds))):
                    pc = max(j for j, b0 in enumerate(bounds) if b0 <= i) - 1
                    if pc in resets:
                        out.append(0x04)
                out.append(PAGE)
                spk_pg = PAGE_SPEAKER.get((typeset._SCENE, m.key), {}).get(i)
                if spk_pg:  # 한 창 안에서 쪽마다 화자가 갈리는 메시지 — 그 쪽 머리에 인라인 이름 색 런(`1F 이름 04`, sysmsg 「{1F}자그리스{04}」 와 같은 꼴)+줄바꿈. 쪽·창 수는 그대로
                    out += b"\x1f" + font.encode(spk_pg, table, msg=True) + b"\x04" + bytes([NL])
                # 🔴 글자색 옵코드(`1D` 등)는 쪽 첫머리에 온다 — 원문 쪽 번호 k 의 옵코드는 번역의 k 번째 `\f` 조각이 시작하는 쪽에 낸다
                out += bytes(op for k, op in style if k and bounds[min(k, len(bounds) - 1)] == i)
            verbatim = isinstance(pg, typeset.Card)  # 쪽마다 — 한 문안 안에 카드 쪽과 줄 계획 쪽이 섞일 수 있다
            for j, line in enumerate(pg):
                # 🔴 **틀을 꽉 채운 줄 뒤에는 개행을 안 넣는다** — 인터프리터가 열 ≥ $99(13)에서 스스로
                #    넘기므로 우리 `01` 이 얹히면 **빈 줄**이 된다(our-findings 2026-08-30, PS1 이 122곳).
                if j and (verbatim or typeset.FULL_LINE_NL or typeset.cols(pg[j - 1]) < typeset.FULL):
                    out.append(NL)
                # 장 끝 카드(verbatim)는 줄을 그대로 둔다 — 앞 공백은 전각(U+3000, 12px)+ASCII 반각(4px)으로 가운데에 맞춘 값
                out += font.encode(line, table, msg=True)  # 🔴 11-06: 카드 안 ASCII 공백도 반각(4px) — 전각 공백(U+3000)만 12px. 제목 앞 공백은 폭에 맞춰 가운데로 계산해 둔다(마스터 「장 끝 제목이 가운데 정렬이 안됨」)
        # 🔴 **끝 공백은 조판기가 지우므로 여기서 따로 낸다**(10-28 검수 — 「그리고 각각의␣」{촛대}「에,␣」{길모아의 별}「과␣」{길모아의 눈물} 이 「각각의촛대에,길모아의 별과길모아의 눈물」로 붙어 나갔다).
        #    이름·품목 변수 바로 앞에서 끝나는 조각의 끝 공백 — 줄머리 공백(`lead_sp`)과 같은 갈래. 쪽 끝(`\f`)이면 안 낸다.
        core = tr["t"].rstrip("\f")
        if core == tr["t"] and core.endswith(" ") and core.strip(" "):
            out += font.encode(" " * (len(core) - len(core.rstrip(" "))), table, msg=True)
    # 🔴 색을 켠 메시지(`1D`)는 끝 옵코드 줄(`04` 색 되돌림 · `05`/`03` 쪽 · 종료)을 원문 순서 그대로 낸다 — 안 내면 해설의 초록이 뒤 대사까지 번진다(마스터 10-30
    #    「이후까지 대사가 초록」)·끝의 `05 1D`(다음 메시지가 쓸 색)도 사라진다. 색을 안 켠 메시지는 종전 그대로(아래).
    tail = []
    for t in reversed(m.tokens):
        if not isinstance(t, tuple):
            break
        tail.append(t[1])
    tail.reverse()
    if style and tail and all(op in TAIL_OK for op in tail):
        out += bytes(tail)
        return bytes(out)
    if m.terminated:
        if m.key in CARD_LEAD_KEYS and pgs and pgs[-1] and not isinstance(pgs[-1], typeset.Card) and typeset.cols(pgs[-1][-1]) < typeset.FULL:
            out.append(NL)
        # 🔴 종료(`06`·`07`) 바로 앞의 쪽 대기(`05`·`03`)도 원문 그대로 낸다(11-07 기능 투어 — 「…だね。どうもありがとう。05 06」 상점 구매 확인이 키 대기 없이 지나갔다.
        #    번역문 끝에는 `\f` 가 없어 쪽 옵코드가 안 나왔고, 호출한 코드가 종료 뒤에 따로 기다리지 않는 흐름(상점·여관)에서 문구가 번쩍 사라진다).
        if len(m.tokens) >= 2 and m.tokens[-2] in (("op", PAGE), ("op", 0x03)):
            out.append(m.tokens[-2][1])
        out.append(m.tokens[-1][1])
    elif m.tokens and m.tokens[-1] == ("op", NL) and not tr.get("raw") and pgs and pgs[-1] and not isinstance(pgs[-1], typeset.Card):
        # 🔴 11-11 꽉 찬(13칸) 마지막 줄 뒤에도 낸다 — 안 내면 다음 메시지가 같은 줄에 붙어 런타임 어절 검사(`wordck`)가 「…요.」+「또」를 한 어절로 보고
        #    줄째 아랫줄로 내린다(씬 45·46·47 밀매상 「오늘은 아무것도 / 없습니다요.또 들러 주십쇼.」 — 마스터 11-11). `01` 은 「다음 글자 전 줄바꿈」 표시일 뿐이라 꽉 찬 줄 뒤에서도
        #    빈 줄이 안 생긴다(devlog 「꽉 찬 줄 뒤 `01` = 빈 줄은 틀린 모델」 — 정확히 13칸 「류난은 횃불을 사용했다.」 뒤 `01` 실화면).
        # 🔴 끝 개행(`01`)은 원문의 일부다 — 다음 메시지가 새 줄에서 이어진다(씬 15 「왕자!?」+「자, 잠시…」가 한 줄로 붙었다, 마스터 10-30). 꽉 찬 줄 뒤엔 인터프리터가 스스로 넘기므로 안 낸다
        out.append(NL)
    elif m.tokens and m.tokens[-1] in (("op", PAGE), ("op", 0x03)):
        # 화자 전환 앞의 페이지 옵코드는 원문 흐름의 일부다 — 빼먹으면 다음 화자가 같은 창에 이어 붙는다(실측)
        out.append(m.tokens[-1][1])
    elif (
        m.speaker is not None
        and not tr.get("raw")
        and not any(t == ("op", NL) for t in m.tokens)
        and len(m.speaker) + len(m.jp) >= typeset.FULL
        and pgs
        and pgs[-1]
        and not isinstance(pgs[-1], typeset.Card)
        and _line_px(speakers.get(m.speaker, m.speaker)) + _line_px(pgs[-1][-1]) <= typeset.FULL * 12 - 12
    ):  # 다음 글자(12px)가 아직 들어가는 줄 — 156px 꽉 찬 줄은 다음 글자에서 인터프리터가 스스로 넘긴다(gon 004 실측: 「…습니다.왕」 156px 까지 붙었다)
        # 🔴 **원문은 이름+글이 틀을 꽉 채운 한 줄이라 인터프리터가 스스로 넘겼는데 우리 줄은 짧다** — 종료 없이 이어지는 메시지(씬 6 장비 셋 「王家のつるぎを装備しました。」 14칸)는
        #    다음 메시지의 이름이 우리 줄 끝에 붙어 「…습니다.왕 / 가의 갑옷을…」로 접혔다(마스터 10-31 gon 004, 규칙 2-1·2-6). 원문이 암묵으로 넘긴 자리를 `01` 로 낸다(하드 개행은 문안에 못 둔다 — 게이트).
        out.append(NL)
    return _restore_reset(bytes(out), tail)


def _restore_reset(out: bytes, tail: list[int]) -> bytes:
    """🔴 원판 끝 옵코드의 색 되돌림(`04`)을 되살린다 — 색 켜기(`1D`)가 **메시지 앞 틈**(이름 변수 `09 nn` 뒤)에 있는 메시지는 안에 켜기가 없어
    위 「색을 켠 메시지」 갈래를 못 타고 끝 `04` 가 빠졌다. 그러면 켜진 색(노랑·초록)이 다음 창 본문까지 번진다(마스터 11-11: 씬 31·32·33 「레지스탕스의 남자」
    이름 줄이 본문까지 노랑 · 씬 36 「리더가 되었습니다」 뒤 류난 대사가 초록). 원문 끝 옵코드에 `04` 가 있고 우리 끝에 없으면, 원문에서 `04` 뒤에 오던
    옵코드가 우리 끝에 남아 있는 자리 앞에(없으면 맨 끝에) 낸다."""
    if 0x04 not in tail:
        return out
    k = len(out)
    while k > 0 and out[k - 1] < 0x24:
        k -= 1
    if 0x04 in out[k:]:
        return out
    after = tail[tail.index(0x04) + 1 :]
    for j in range(k, len(out)):
        if out[j] in after:
            return out[:j] + b"\x04" + out[j:]
    return out + b"\x04"


def _line_px(line: str) -> int:
    """줄의 엔진 전진 px(`gwin.adv` — 공백·반각 부호 4 · 「」·합자 8 · 나머지 12). 조사 토큰(`을/를`)은 한 글자. `typeset.cols` 는 반 칸을 올림해 인터프리터의 자동 넘김과 어긋난다(12.5칸을 13으로)."""
    import gwin

    for pair in font.JOSA_PAIRS:
        line = line.replace(pair, pair.split("/")[0][:1])
    return sum(gwin.adv(c) for c in font.ligate(line))


def continuation_leads(block: bytes, msgs: list, trs: dict, speakers: dict) -> dict[str, int]:
    """앞 메시지가 찍던 줄 끝에 **이어 붙는** 메시지의 {열쇠: 이미 쓴 폭(px)}.

    앞 메시지는 종료 없이 옵코드(`10`·`0F`·`0D` …)로 끝나고, 그 옵코드 바로 뒤에서 이 메시지가 시작한다 — 같은 창이 이어져 줄 끝에서 이어 쓴다. `10` 호출(공유 하위 문구,
    예: 「아니, 세리오스 왕자님!!」)이면 그 문구의 폭도 얹는다. 런타임 어절 검사는 앞 메시지가 쓴 폭을 몰라 낱말 가운데서 끊는다(씬 64, 10-22) — 조판기가 이 폭을 알고 짠다.
    """
    by_start = {m.start: m for m in msgs}

    def last_line(m) -> str:
        tr = trs.get(m.key)
        if not tr or not tr.get("t"):
            return ""
        pg = typeset.pages(font.expand_packed(tr["t"].lstrip(" ")), speaker=M.speaker_kind(m, typeset._SCENE), four=True, keep_windows=typeset.keep_windows(typeset._SCENE))
        return pg[-1][-1] if pg and pg[-1] else ""

    leads: dict[str, int] = {}
    # 메시지 **앞**에서 수치를 찍는 `1D 22`(씬 192 「(금액) Gold를 …」 — 11-07 캡처로 「?」 잘림 확인) — 값 자리는 4자리(마스터 09-27) × 8px 가 이미 줄에 찍혀 있다.
    # 메시지 안의 수치 op 는 검사기가 자리표시로 세지만, 앞에 떨어진 이것은 못 세서 줄이 156px 를 넘었다.
    for m in msgs:
        if m.start >= 2 and block[m.start - 2] == 0x1D and block[m.start - 1] == 0x22:
            leads[m.key] = typeset.px(typeset.NUMCH * 4)
    for ia, a in enumerate(msgs):
        n_in = msgs[ia + 1] if ia + 1 < len(msgs) else None
        if n_in is not None and n_in.key in INLINE_LEAD and n_in.start == a.end and not a.terminated:
            import voice_sched as VS

            nm, _hd = VS.inline_name(block, msgs, ia + 1)
            if nm is not None:
                import gwin_rt

                la = last_line(a)
                lead = typeset.px(la) + (typeset.SPACE_PX if trs.get(a.key, {}).get("t", "").endswith(" ") else 0) + typeset.px(gwin_rt.common_speaker(nm))
                if 0 < lead < typeset.FULL * 12:
                    leads[n_in.key] = lead
            continue
        if a.terminated or a.end + 3 > len(block):
            continue
        op = block[a.end]
        ln = M.OTHER_OPS.get(op)
        n = by_start.get(a.end + ln) if ln else None
        # 🔴 「주문 현자」 꼬리(「 어느 주문을 …?」 — 씬 16·23·45~49·89·92·102·115~117·130·132·147·152·155·159~161)는 앞 메시지와 `0D 08` 두 옵코드 뒤에서 이어진다.
        #    옵코드가 둘이라 아래 한 옵코드 규칙에 안 걸려 앞 줄이 쓴 폭을 모른 채 짰고, 같은 줄에 이어 찍히며 「주문을」이 칸 13 에 닿아
        #    ▼ 와 겹치고 다음 줄이 공백으로 시작했다(마스터 11-14, 744.png). 두 옵코드를 건너뛴 자리를 이음 자리로 본다(11-14).
        double_op = False
        if n is None and op == 0x0D and block[a.end + 1] == 0x08:
            n = by_start.get(a.end + 2)
            double_op = n is not None
        if n is None or n.speaker is not None or n.common is not None:
            continue
        if n.tokens and n.tokens[0] == ("op", NL):
            continue
        if a.tokens and a.tokens[-1] in (("op", NL), ("op", PAGE), ("op", 0x03)):
            la = ""
        else:
            la = last_line(a)
        lp = ""
        if op == 0x10:  # 공유 하위 문구 호출
            tgt = by_start.get((block[a.end + 1] | block[a.end + 2] << 8) - M.BASE)
            if tgt is not None:
                lp = last_line(tgt)
        lead = typeset.px(la) + (typeset.SPACE_PX if la and lp else 0) + typeset.px(lp)
        if double_op:  # 꼬리 머리 공백(compose 가 따로 낸다)도 앞 줄 폭에 얹는다
            lead += typeset.SPACE_PX * (len(trs.get(n.key, {}).get("t", "")) - len(trs.get(n.key, {}).get("t", "").lstrip(" ")))
        if 0 < lead < typeset.FULL * 12:  # 줄이 꽉 찼으면 인터프리터가 이미 넘겼다 — 새 줄에서 시작
            leads[n.key] = lead
    return leads


def with_added_speakers(scene_id: int, msgs: list) -> list:
    """원판에 화자 머리가 없는 밀매상 메시지에 머리를 붙인 목록(`ADD_SMUGGLER_SPEAKER`)."""
    keys = ADD_SMUGGLER_SPEAKER.get(scene_id)
    if not keys:
        return msgs
    import dataclasses

    return [dataclasses.replace(m, key_fixed=m.key, speaker=SMUGGLER_JP) if m.key in keys and m.speaker is None and m.common is None else m for m in msgs]


SHARED_FLOW_KEYS = {"cd3848e2f5850f53"}  # 밀매상 「뭘 원하십니까요?」 — 앞 폭 없이 한 줄(아래 translate_block 주석)


def translate_block(scene_id: int, block: bytes, table: dict[str, bytes]) -> tuple[bytes, int]:
    """번역이 있는 메시지를 합성해 splice. (새 블록, 넣은 메시지 수)."""
    trs = M.load_translations(scene_id)
    if not trs:
        return block, 0
    typeset.set_scene(scene_id)  # 쪽을 늘려도 되는 씬인가(2-16) — 조판 지표·지문도 같은 씬 번호로 짠다
    speakers = M.load_speakers()
    msgs = M.parse(block)
    msgs = with_added_speakers(scene_id, msgs)
    edits = []
    seen = set()
    leads = continuation_leads(block, msgs, trs, speakers)
    for m in msgs:
        tr = trs.get(m.key)
        if tr is None and m.speaker in speakers and not m.jp.strip():
            tr = {
                "t": ""
            }  # 이름만 있는 메시지(이벤트 코드가 화자 표시용으로 부른다) — speakers.json 으로 자동
        if tr is None:
            continue
        if m.pinned:
            raise TranslateError(
                f"scn {scene_id} 열쇠 {m.key}: pinned(안쪽 참조) — 자리 규칙으로 못 넣는다"
            )
        # 🔴 두 흐름이 공유하는 질문(마스터 11-18 「밀매상 뭘 원하십니까요? 한 줄로」): 「뭘 원하십니까요?」는 「더는 못 가지시는 모양입죠.」 뒤에 이어 붙는 길(앞 줄 폭
        #    120px)과 인사 쪽 지움 뒤 새 창으로 오는 길이 같은 메시지를 쓴다. 앞 폭을 주고 짜면 머리 개행이 박혀 새 창에서 「뭘 / 원하십니까요?」 두 줄이 된다.
        #    앞 폭 없이 한 줄로 짜 두고 이어 붙는 길의 줄넘김은 엔진 어절 검사(`wordck`)에 맡긴다.
        lp = 0 if m.key in SHARED_FLOW_KEYS else leads.get(m.key, 0)
        edits.append((m, compose(m, tr, table, speakers, lead_px=lp)))
        seen.add(m.key)
    missing = set(trs) - seen
    if missing:
        raise TranslateError(
            f"scn {scene_id}: 정본 열쇠 {sorted(missing)} 가 블록에 없다(원문이 바뀌었나)"
        )
    edits = merge_sell_thanks(scene_id, block, edits)
    new_block = remap_page_jumps(scene_id, block, M.splice(block, edits), msgs, trs)
    return apply_orphans(scene_id, block, new_block, table, speakers), len(edits)


_SELL_STRUCT = re.compile(rb"\xa9(.)\x85\xfa\xa9(.)\x85\xfb\x20\xd8\x4f\x06\x27\x9e", re.S)


def sell_structs(block: bytes) -> list[tuple[int, int]]:
    """판매 목록 호출(far `$9E27`)의 구조체가 든 (질문 포인터, 감사 포인터) 블록 오프셋 목록.

    구조체 8B = 질문·확인·거절·감사 메시지 포인터 넷(논리 `$A000`+오프셋)."""
    out = []
    for m in _SELL_STRUCT.finditer(block):
        off = (m.group(2)[0] << 8 | m.group(1)[0]) - 0xA000
        if 0 <= off <= len(block) - 8:
            out.append((block[off] | block[off + 1] << 8, block[off + 6] | block[off + 7] << 8))
    return [(q - 0xA000, t - 0xA000) for q, t in out]


def merge_sell_thanks(scene_id: int, block: bytes, edits: list) -> list:
    """🔴 판매 감사(「정말 감사합니다.」) 메시지 끝에 질문(「어느 것을 판매하시겠습니까?」)을 줄 바꿔 이어 쓴다 (마스터 11-18 「판매 뒤 감사가 바로 지워지고 질문이 나온다 — 감사를 유지한 채
    아래줄에 질문」, 원판도 같은 동작).

    원인(devlog 11-19 후속2): 감사 뒤 엔진(뱅크 0x6F `$9F31 JMP $9E4B`)이 목록 위젯을 다시 열어 질문 메시지를 보이고, 메시지 첫 바이트 `08`(창 다시 그리기)이 감사를 지운다.
    엔진 쪽은 `$9F31` 을 헤더 표시 뒤(`$9E58`)로 돌려 질문을 건너뛰고(`build.code_patches` 「sell thanks keep」), 여기서 감사 메시지 끝에 질문 본문을 이어 쓴다.
    감사 메시지가 `01 07` 로 끝나는 꼴(원판 공통)만 다룬다 — 컴포즈가 끝 `01` 을 떨구므로 직접 낸다. 못 맞추면 죽는다(질문이 사라지는 씬을 만들지 않는다)."""
    pairs = sell_structs(block)
    if not pairs:
        return edits
    by_start = {m.start: i for i, (m, _) in enumerate(edits)}

    def idx(ptr: int, what: str) -> int:
        st = ptr + 1 if block[ptr] == 0x08 else ptr  # `08` 로 시작하는 메시지는 본문이 한 바이트 뒤(parse 가 `08` 을 앞 옵코드로 뗀다)
        if st not in by_start:
            raise TranslateError(f"scn {scene_id}: 판매 {what} 메시지(@{ptr:#x})가 번역 목록에 없다")
        return by_start[st]

    out = list(edits)
    for qptr, tptr in pairs:
        qi, ti = idx(qptr, "질문"), idx(tptr, "감사")
        qm, qb = out[qi]
        tm, tb = out[ti]
        if qm.speaker is not None or qm.common is not None or qb[:1] in (b"\x1f", b"\x09"):
            raise TranslateError(f"scn {scene_id}: 판매 질문에 화자·공통 머리가 있다 — 감사에 이을 수 없다")
        if tb[-1:] != b"\x07" or tb[-2:-1] in (bytes([PAGE]), b"\x03") or not tm.terminated:
            raise TranslateError(f"scn {scene_id}: 판매 감사 끝이 `07` 단독이 아니다 — {tb[-4:].hex()}")
        if tm.key == qm.key:
            continue
        out[ti] = (tm, tb[:-1] + bytes([NL]) + qb)
    return out



def _walk_pages(buf: bytes, start: int, k: int, follow_jump: bool) -> int | None:
    """`start` 에서 토큰을 따라 걸어 k 번째 쪽 옵코드(`03`·`05`) 바로 뒤 오프셋을 낸다. `follow_jump` 면 `0F` 로 따라간다(우리가 splice 로 놓은 꼬리 점프). 못 찾으면 None."""
    i, pages, hops = start, 0, 0
    while 0 <= i < len(buf):
        v = buf[i]
        if M.is_lead(v):
            i += 2
            continue
        if v == M.JUMP and follow_jump and hops < 4:
            i = (buf[i + 1] | buf[i + 2] << 8) - M.BASE
            hops += 1
            continue
        if v in M.TERM:
            return None
        i += M.TEXT_OPS.get(v, M.OTHER_OPS.get(v, 1))
        if v in PAGE_OPS:
            pages += 1
            if pages == k:
                return i
    return None


def remap_page_jumps(scene_id: int, orig: bytes, new: bytes, msgs: list, trs: dict) -> bytes:
    """🔴 **쪽 머리로 들어가는 스크립트 점프를 새 쪽 머리로 옮긴다**(마스터 11-18 씬 50 「남자」 첫 대사가 「라고요,」부터 — 다치지 않은 갈래의 `0F` 가 원판 메시지 둘째 쪽(`05` 바로 뒤)으로 들어오는데
    한국어 메시지는 쪽 길이가 달라 그 오프셋이 글자 한가운데로 떨어졌다). 메시지 **밖**(코드 자리)의 `0F lo hi` 가 번역된 메시지의 k 번째 쪽 머리(앞 바이트 `05`·`03`)를 가리키면, 새 바이트에서 k 번째 쪽 머리를 걸어 찾아
    피연산자를 고친다. 쪽 수가 모자라면 빌드를 죽인다(창 수 계약). 쪽 머리가 아닌 중간 진입(문장 꼬리 공유 등)은 여기서 안 다룬다 — `check_script_jumps` 기준선."""
    inmsg = bytearray(len(orig))
    for m in msgs:
        inmsg[m.start : m.end] = b"\x01" * (m.end - m.start)
    out = bytearray(new)
    for j in range(len(orig) - 2):
        if orig[j] != M.JUMP or inmsg[j] or inmsg[j + 1]:
            continue
        w = (orig[j + 1] | orig[j + 2] << 8) - M.BASE
        host = next((t for t in msgs if t.start < w < t.end), None)
        if host is None or orig[w - 1] not in PAGE_OPS or host.key not in trs or M._parse_from(orig, w) is None:
            continue
        # 원판에서 host.start → w 사이 쪽 옵코드 수 k(w 직전의 것까지)
        i, k = host.start, 0
        while i < w:
            v = orig[i]
            if M.is_lead(v):
                i += 2
                continue
            i += M.TEXT_OPS.get(v, M.OTHER_OPS.get(v, 1))
            if v in PAGE_OPS:
                k += 1
        if i != w:
            continue  # 토큰 경계가 아니다 — 우연 일치
        t = _walk_pages(new, host.start, k, True)
        if t is None:
            raise TranslateError(f"scn {scene_id}: 점프 +{j:#06x} 가 메시지 {host.key} 의 {k}번째 쪽 머리로 들어가는데 번역에 그 쪽이 없다(쪽 수 계약)")
        addr = M.BASE + t
        out[j + 1], out[j + 2] = addr & 0xFF, addr >> 8
    return bytes(out)


# 🔴 **메시지 밖에 서 있는 조각** — `messages.parse` 는 두 글자 미만의 가나·한 글자 화자 머리를 메시지로 안 잡아 번역이 닿지 않고 일본어가 그대로 남았다
#    (10-20 짝 표·화면 확인 — 마스터 「A」):
#    ① 슬롯 옵코드(`0B`·`0E`) 곁의 한 글자 조사 「は」「を」 → 같은 2바이트 동적 조사 토큰(`F9 24` 은/는 · `F9 26` 을/를). 슬롯 이름 바로 뒤에 붙으면
#       「류난은약초를」처럼 붙어서 반 칸 공백(`F8 24`)을 더 넣는 자리는 공간이 모자라 **블록 끝으로 잇는다**(`0F` 점프 · 같은 방식 splice).
#    ② 한 글자 화자 머리 「男」「女」「娘」(`1F 이름 04`) → 정본 화자 표기(남자·여자·소녀). 이름칸이 더 길어 역시 블록 끝으로 잇는다.
#    바이트가 기대와 다르면 빌드가 죽는다 — 원문과 다른 글자는 건드리지 않는다.
def _orphan_patches() -> dict[int, list[tuple[int, bytes, bytes]]]:
    j = font.josa_code
    sp = font.HALF_SPACE
    return {
        # (씬 50 갈래 이음은 11-06 부터 `messages._merge_jump_tails` 가 한다 — 「盗ま」+`0F` 조각을 꼬리까지 이은 한 메시지로 읽어 이 자리 패치가 필요 없다)
        56: [(0x879, b"\x82\xcd", j("은/는")), (0x87D, b"\x82\xf0", j("을/를"))],
        133: [(0x2C6, b"\x0b\x82\xcd\x0e", b"\x0b" + j("은/는") + sp + b"\x0e")],
        195: [(0xADC, b"\x0b\x82\xcd", b"\x0b" + j("은/는") + sp)],
        197: [
            (0x923, b"\x0b\x82\xcd\x0e", b"\x0b" + j("은/는") + sp + b"\x0e"),
            (0x927, b"\x82\xf0", j("을/를")),
        ],
        220: [(0x4C2, b"\x82\xcd", j("은/는"))],
    }


ORPHAN_SPEAKERS = ("男", "女", "娘")
# 씬 20 「男」/「兵士」 — 조건 갈래(`0F d4 af` 가 男 쪽을 건너뛴다). 男 은 한글이 4B 라 꼬리로 빼고 끝 점프(`0F d8 af` = 04 자리)를 같이 옮긴다, 兵士 는 같은 길이
BRANCH_SPEAKER_SITES = {20: [(0xFCF, "男", b"\x0f\xd8\xaf"), (0xFD4, "兵士", b"")]}
# 🔴 밀매상(「やみの商人」) 머리 없는 메시지에 화자 머리를 단다(마스터 11-11 「첫대사는 화자명이 나와야할것 같네」) — 씬 45·46·47 의 같은 밀매상 메시지 중
#    원판에 머리가 없고 **자기 창을 여는** 것(더는 못 가짐 · 없음)에 `1F 이름 04`. 🔴 못 찾음(4쪽 설명 — 엔진이 찍은 아이템 이름에 이어지는 조각)·작별(「없음」 창에 이어 붙는 조각)은 창 한가운데라 머리를 달면 이름이 중간에 박힌다(마스터 캡처 11-11: 「없습니다요.또 들러 주십쇼.」가 한 창). 이름은 speakers.json(정본 「밀매상」)에서 읽는다.
ADD_SMUGGLER_SPEAKER = {
    45: {"bc91ddb1af196ba3", "367c60f03acf472e"},
    46: {"bc91ddb1af196ba3", "367c60f03acf472e"},
    47: {"bc91ddb1af196ba3", "367c60f03acf472e"},
}
SMUGGLER_JP = "やみの商人"

# 🔴 **메시지 밖 일본식 부호**(마스터 10-30 「류난。 — 마침표가 일본식」): 슬롯 이름 토큰(`09 xx`·`10 xx xx`) 바로 뒤의 「。」「、」(`81 42`·`81 41`)는 메시지 조각이 아니라
#    번역이 안 닿고 원문 그대로 화면에 나왔다(씬 18 「제 이름은 류난。」). 같은 2바이트라 반각 부호 코드(`F0 27` . · `F0 25` ,)로 **제자리**에서 바꾼다 —
#    자리는 전수 스캔(메시지 칸 밖의 `81 41`·`81 42` 중 이름 토큰 뒤)으로 찾았고, 바이트가 기대와 다르면 빌드가 죽는다. 새 자리가 생기면 `check_jp_punct.py` 가 알린다.
PUNCT_SITES = {18: [0x524], 64: [0x2DC, 0x36E], 77: [0x85F], 115: [0xFCF], 131: [0xB97, 0xD06]}
PUNCT_MAP = {b"\x81\x42": ".", b"\x81\x41": ","}

# 🔴 **창의 첫 행을 비우는 머리 개행**(마스터 10-31 gon 009 「첫줄을 굳이 비워놔야할 이유도 없는것 같아서 우리는 첫줄부터」): 화자 없는 **새 창**(바로 앞이 문장 끝 00/06/07
#    또는 페이지 03/05) 앞에 `01` 이 메시지 **밖**에 서 있는 자리가 넷(씬 0 필드 서술 「세리오스는 라이아스 일행을…」 · 32 · 95 · 106). `messages.parse` 가 머리 개행을 메시지에 넣는 건
#    화자 머리 뒤뿐이라 compose 의 머리 개행 규칙이 못 봤다(「원문엔 머리 개행이 없다」는 파서 착시). 인터프리터 점프표(`$67A4`)의 옵코드 `18` 은 `$6808 RTS` — 아무 일도 안 하는 한
#    바이트라 그 `01` 을 제자리에서 `18` 로 바꾼다(블록 배치 불변 → 쪽 수 불변). 화자 머리 뒤 `04 01`(167곳)은 이름 줄 끝이라 그대로.
NOP_OP = 0x18
BLANK_ROW_BEFORE = M.TERM | set(PAGE_OPS)
BLANK_ROW_FIX = True


def blank_row_patches(orig: bytes) -> list[tuple[int, bytes, bytes]]:
    out = []
    for m in M.parse(orig):
        if (
            m.speaker is None
            and m.common is None
            and m.start >= 2
            and orig[m.start - 1] == NL
            and orig[m.start - 2] in BLANK_ROW_BEFORE
        ):
            out.append((m.start - 1, bytes([NL]), bytes([NOP_OP])))
        # 동료 합류 「{이름}이 동료가 되었습니다」(씬 41 게일, 마스터 11-08 「게일 동료 빈 줄은 원본도 마찬가지인데 의미 없는 빈 줄은 제거」):
        #   `05 01 09 xx 1D <메시지>` — 새 창 맨 앞 개행 `01` 이 이름 토큰(`09 xx`) 앞에 서 있어 첫 줄이 빈다. 같은 방식으로 제자리 NOP.
        elif (
            m.speaker is None
            and m.common is None
            and m.start >= 5
            and orig[m.start - 4] == NL
            and orig[m.start - 3] == 0x09
            and orig[m.start - 1] == 0x1D
            and orig[m.start - 5] in BLANK_ROW_BEFORE
        ):
            out.append((m.start - 4, bytes([NL]), bytes([NOP_OP])))
    return out


# 🔴 동료 합류 효과음(마스터 11-19 「게일 재합류 효과음 넣자. 모든 파티합류 메세지에 효과음 누락된 부분 더 있으면 추가」): 원판은 합류 메시지(「…が仲間になりました。」) 바로 뒤에
#    `0C 26`(효과음 옵코드) 을 두는데 씬 69 게일 재합류(「…が仲間に加わりました。」)만 없다. 원판과 달라지는 개선 — 그 메시지 뒤 3B 옵코드(`14 9C 00` 플래그 세트) 앞에 `0C 26` 을 낀다.
JOIN_SFX_KEYS = {"b27d8c0c4008c32f"}  # 씬 69 게일 재합류. 나머지 합류(씬 18·32·41·63)는 원판에 이미 있다(11-19 전 씬 표)
JOIN_SFX = b"\x0c\x26"


def join_sfx_patches(orig: bytes) -> list[tuple[int, bytes, bytes]]:
    out = []
    for m in M.parse(orig):
        if m.key in JOIN_SFX_KEYS and orig[m.end] != 0x0C:
            if orig[m.end] != 0x14:
                raise TranslateError(f"합류 메시지 {m.key} 뒤가 `14`(플래그 세트)가 아니다({orig[m.end]:#04x}) — 원문이 바뀌었나")
            old = bytes(orig[m.end : m.end + 3])
            out.append((m.end, old, JOIN_SFX + old))
    return out


def apply_orphans(
    scene_id: int, orig: bytes, block: bytes, table: dict[str, bytes], speakers: dict[str, str]
) -> bytes:
    """`orig` = 번역 전 블록(주소 기준 · 메시지 칸 판별), `block` = splice 결과(제자리 + 끝에 이은 꼬리)."""
    patches = list(_orphan_patches().get(scene_id, []))
    own_exit: set[int] = set()  # 새 바이트가 이미 제 출구 점프로 끝나는 꼬리(복귀 점프를 또 붙이지 않는다)
    spans = [(m.start, m.end) for m in M.parse(orig)]
    for i in range(len(orig) - 3):
        if orig[i] == 0x1F and orig[i + 3] == 0x04 and not any(a <= i < b for a, b in spans):
            try:
                nm = orig[i + 1 : i + 3].decode("cp932")
            except UnicodeDecodeError:
                continue
            if nm in ORPHAN_SPEAKERS and nm in speakers:
                patches.append((i, orig[i : i + 4], b"\x1f" + font.encode(speakers[nm], table) + b"\x04"))
    for off, jp, tail in BRANCH_SPEAKER_SITES.get(scene_id, []):  # 갈래로 갈린 화자 머리(`1F 12 xx 00 0F .. 男 0F .. 兵士 04`) — 갈래마다 이름을 한글로(마스터 11-17 「여긴 아예 화자명이 한자네」)
        if tail:  # 꼬리로 빼는 쪽 — 점프 3B 만 덮을 수 있게 앞 3B 를 옛 자리로 두고 나머지(옛 점프 인자, 이제 죽은 바이트)는 0 으로 채운다. 바뀐 구간이 兵士 자리까지 이어져 구조 대조가 꼬리 복귀 점프를 「원래 조각 바로 뒤」로 본다
            old = jp.encode("cp932") + tail
            patches.append((off, old[:3], font.encode(speakers[jp], table) + tail))
            own_exit.add(off)
            patches.append((off + 3, old[3:], b"\x00" * len(old[3:])))
        else:
            patches.append((off, jp.encode("cp932"), font.encode(speakers[jp], table)))
    for off in PUNCT_SITES.get(scene_id, []):
        old = bytes(orig[off : off + 2])
        if old not in PUNCT_MAP:
            raise TranslateError(f"scn {scene_id} +{off:#06x}: 일본식 부호 자리가 아니다({old.hex()}) — 원문이 바뀌었나")
        new = font.encode(PUNCT_MAP[old], table, msg=True)
        assert len(new) == 2, new
        patches.append((off, old, new))
    if BLANK_ROW_FIX:
        patches += blank_row_patches(orig)
    patches += join_sfx_patches(orig)
    if not patches:
        return block
    out = bytearray(block)
    for off, old, new in patches:
        if bytes(orig[off : off + len(old)]) != old:
            raise TranslateError(
                f"scn {scene_id} +{off:#06x}: 조각 자리가 {old.hex()} 가 아니다({bytes(orig[off:off+len(old)]).hex()}) — 원문이 바뀌었나"
            )
        if len(new) <= len(old):
            out[off : off + len(new)] = new
            continue
        if len(old) < 3:
            raise TranslateError(f"scn {scene_id} +{off:#06x}: 자리 {len(old)}B 라 점프(3B)를 못 둔다")
        at = M.BASE + len(out)  # 끝에 이은 꼬리: 새 바이트 + 원래 자리 뒤로 되돌아가는 점프
        back = M.BASE + off + len(old)
        out += new + (b"" if off in own_exit else bytes([0x0F, back & 0xFF, back >> 8]))
        out[off : off + 3] = bytes([0x0F, at & 0xFF, at >> 8])
    return bytes(out)
