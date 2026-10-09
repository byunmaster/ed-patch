#!/usr/bin/env python3
"""런타임 조립 템플릿(`%c%s%c...`) 이 **가장 긴 이름을 꽂아도** 창 폭을 안 넘나
(2026-09-14, 마스터 QA 056).

**왜 필요한가**: `%s` 자리(이름)는 **런타임에** 채워지므로 빌드 시점 조판(`krwrap`/
`wrap_page`)을 거치지 못한다(전투 로그는 엔진 자체 prewrap 이 줄바꿈을 한다 — RE 실기
추적, 2026-09-14). 우리 조판기는 안 보는 줄이니 **넘치면 낱말 한가운데서 잘린다**
(RE 실기: "아시카사고A는 사이레스를 외쳤 / 다." — 어절 한복판에서 잘림).

**KISS**: 엔진의 prewrap 을 한국어용으로 다시 만들지 않는다. 대신 **모든 런타임 템플릿이
가장 긴 이름을 꽂아도 29 반각(=14.5슬롯, 창 틀)을 안 넘게** 만든다 — 이 게이트가 그걸 잰다.

⑴ `%s`를 가진 런타임 템플릿을 전부 모은다(battle.json · battle_ed2.json ·
   monster_lines_ed2.json · items_battle.json · script/ED2MON_LINES.json).
⑵ `%s`자리에 **가장 긴 이름**을 꽂는다(파티 최장 · 몬스터 최장(접미 포함) 둘 다, ED1·ED2
   모두 — 042 가 "ED1 만 보고 고쳐 ED2 가 틀어진" 전례가 있다).
⑶ 조사 병기(`은(는)` 류)는 **훅이 접은 뒤 길이**로 센다(RE 확인: 훅이 prewrap 보다 먼저
   돈다) — 이름의 마지막 글자 받침으로 어느 쪽으로 접힐지 정해 그 한 글자만 센다.
⑷ 29 반각(14.5슬롯)을 넘으면 실패.

  python3 tools/check_runtime_template_width.py         # 게이트
  python3 tools/check_runtime_template_width.py -v       # 넘치는 것 상세
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(__file__).rsplit("/games/", 1)[0] + "/shared")
os.environ.setdefault("LOCK_BYPASS", "1")

import patch_ed2_sys as PS
import patch_items as PI
import patch_sys_ui as PU
from text.josa import batchim

TOOLS = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(TOOLS)

FRAME_HALFWIDTH = 29  # 창 틀 — 14.5슬롯(WRAP=14.0 + HANG_SLOTS=0.5) * 2
JOSA_PAIR = re.compile(r"(은|이|을)\((는|가|를)\)")

# 🔴 **진짜 한계는 줄 수가 아니라 바이트다**(RE 실기, 2026-09-15). 메시지박스 진입부
# (`0x800B1D24`)의 `strcpy(fp+0x18, msg)` 에 길이 검사가 없다 — 버퍼 여유는
# `fp+0xA0(s0 저장) − fp+0x18 = 0x88(136)`, 그 뒤 `fp+0xA8` 이 **복귀주소(ra)** 다.
# 136B 를 넘기면 s0→fp→ra 를 차례로 덮는다 — **ra 가 깨지면 소프트락 부류**다.
# `prewrap`(`0x800ACE18`)이 같은 버퍼에 개행을 최대 8개까지 끼워 넣고 되쓰므로
# **자동 개행분(+8)까지 여유를 두고 128B 를 넘지 않게** 한다(하드 한계 136, 권장 128).
# 줄 수(6줄, 넘치면 스크롤— 배열 밖으로 안 나가 안전)와는 **완전히 다른 축**이다.
BYTE_LIMIT = 128
AUTO_NEWLINE_RESERVE = 8  # prewrap 이 추가로 끼워 넣을 수 있는 개행 수의 상한

# 폭 초과를 **실패가 아니라 보고로** 내리는 이름 — 마스터 판정(2026-09-25, qa2 089):
# 「몬스터명은 전투에서만 쓰이고 전투 문구는 로그성이라 개행돼도 상관없다」.
# 드러스트고스트(7음절, 공용 용어집 표기)는 6음절+접미에 맞춰 다듬은 틀 74조합에서 +2반각
# 넘친다 — 이름을 줄이는 대신 엔진 prewrap 에 맡긴다. ⚠ **바이트 예산(`check_byte_budget`)은
# 그대로 본다** — 그쪽은 보기가 아니라 소프트락(구조)이라 예외가 없다.
# 🔴 09-27 비움 — 7음절 이름은 폭이 아니라 **엔진 이름 칸(13B = 6음절+접미)**을 넘어 끝 글자가 깨졌다(마스터 QA 109,
#   「드러스트고스+」). 마스터 판정으로 「드러스트유령」(6음절)으로 줄였다. 7음절 이름은 다시 만들지 않는다.
WIDTH_EXEMPT_NAMES: set[str] = set()

# 폭 초과를 **실패가 아니라 보고로** 내리는 **템플릿** — QA 110(마스터 09-27 신규 규칙):
# 「로그성 메시지(도구·주문 사용 등)는 강제 개행을 없애고, 넘칠 때만 어절 단위로 개행합니다」.
# 이 표는 문장 자체가 `%s`(이름) 뒤에서 넘칠 수 있는데, 위 WIDTH_EXEMPT_NAMES 와 같은 근거
# (2026-09-25, qa2 089 — 로그성 문구는 개행돼도 되고 엔진 prewrap 이 맡는다)를 **템플릿**
# 단위로 적용한다. ⚠ 이건 추정이 아니라 **실측**이다 —
# `check_prewrap_rules.prewrap()` 으로 원판·빌드 두 EXE 에 이 템플릿 + 최장 이름 조합을
# 실제로 태워 본 결과: 원판은 ④(낱말 중간 절단)를 냈고, 09-27 어절 백오프 스텁(`patch_hang_punct
# .stub_backoff`)을 적용한 빌드는 **0건**(마지막 공백에서 정확히 물러나 개행)이었다.
# ⇒ 이 축(견본 32건)은 `CRTW.check()`(이론상 최악, 여기)가 아니라 `check_prewrap_rules
# ._battle_table` 류의 실행 검증이 정본이고, 여기서는 실패로 안 센다.
# 폭 초과를 보고로 내리는 **표 전체** — 몬스터 전투 대사(ED2MON)는 전부 로그성이다(09-27 규칙).
# 09-28 마스터 지시로 우리가 넣었던 문장 중간 개행 140줄을 걷었다(원문에 있던 5줄만 남김 —
# 그 개행은 09-15 엔진이 낱말 한가운데서 끊던 시절 056 대응으로 손으로 박은 것). 실측:
# 걷어 낸 140줄 × 최장 이름 12개 = 1,680조합을 빌드 prewrap 에 태워 ④(낱말 중간 절단) 0건.
WIDTH_EXEMPT_SOURCES: set[str] = {"script/ED2MON_LINES.json"}

WIDTH_EXEMPT_TEMPLATES: set[str] = {
    "%c%s%c은(는) 꼬리로 공격했다.\n",
    "%c%s%c의 목을 물어뜯었다.\n",
    # 🔴 10-10 마스터 2-10 「한 줄에 나올 수 있는 문장은 한 줄로」 — 문장 안 강제 개행을 걷은 로그 문구 열넷. 최장 이름 조합에서
    # 29반각을 넘어도 엔진 prewrap 의 어절 백오프가 마지막 공백에서 물러나 개행한다(위 09-27 근거와 같다). 실측: 이 템플릿 ×
    # 파티·몬스터 이름 전부(+접미 A~D) 17,370조합을 **빌드 prewrap 에 태워** 낱말 중간 절단 0건. 이름·문장을 줄이지 않는다.
    # 🔴 10-10 마스터 「노려 / 그라디우스를…」 — 이름이 들어가는 로그 문장의 **문장 중간 강제 개행**을 걷은 열세 템플릿(2-10). 빌드 prewrap 에
    # 이 템플릿 × 파티·몬스터 이름 전부(+접미 A~D, 앞 조각이 이름 없는 꼴은 이름을 앞에 붙임) 22,030조합을 태워 낱말 중간 절단 0건(실측).
    # 같은 방식으로 재면 「심심해서 잠이 오기 시작했다」만 5음절 이름(바이오레드)에서 ④ 가 나 그 한 줄은 원래 개행을 되돌렸다.
    "%c%s%c은(는) 소름 끼치는 괴성을 질렀다!!\n",
    "그 소리를 들은 %c%s%c은(는) 공포로 ",
    "%c%s%c의 시체에 붉은 약을 뿌렸다.\n",
    "%c%s%c은(는) 좀비가 되어 되살아났다.",
    "%c%s%c의 눈에 들어가고 말았다!!\n",
    "은(는) %c%s%c을(를) 노려 그라디우스를 내리쳤다!!\n",
    "은(는) ＨＰ가 가장 낮은 %c%s%c에게 덤벼들었다!!",
    "은(는) ＨＰ가 가장 낮은 %c%s%c에게 덤벼들었다!!\n",
    "%c헤르닐드%c는 불의 지팡이를 %c%s%c에게 쳐들었다.\n",
    "%c%s%c의 눈앞에 불기둥이 나타났다!!\n",
    "%c%s%c은(는) 저주의 말을 남겼다.",
    "%c%s%c이(가) 죽을힘을 다해 부딪쳤다!!",
    "%c%s%c은(는) 몸이 마비되었다.\n",
    "%c%s%c은(는) 실을 토했다.\n",
    "%c%s%c은(는) 잠들어 버렸다.",
    "%c%s%c은(는) 포자를 퍼뜨렸다.\n",
    "%c%s%c을(를) 물어뜯었다!!",
    "%c%s%c은(는) 모래를 토했다!!\n",
    "은(는) %c%s%c을(를) 물어뜯었다!!\n",
    "%c%s%c은(는) 날카로운 주둥이로 ",
    "%c%s%c에게 숨어 있는 곳을 ",
    "은(는) %c%s%c을(를) 노려봤다!!\n",
    "%c%s'%c라고 부르기로 했다.",
    "%c%s%c이(가) 모습을 나타냈다.\n",
    "%c%s%c에게 레스를 외웠다.",
    "%c%s%c을(를) 포기했다.",
}


def _enc_len(s):
    """실제 인코딩 바이트 수 — 한글은 hangul_map(2B), 나머지(%c·부호 포함)는 1B."""
    return sum(2 if "가" <= ch <= "힣" else 1 for ch in s)


def _hw(ch):
    """반각 열 수 — 한글 1글자=2, ascii 반각=1, 그 외(전각 부호 등)=2."""
    if "가" <= ch <= "힣":
        return 2
    if ch.isascii():
        return 1
    return 2


def _width(s):
    return sum(_hw(c) for c in s)


def _fold(text, name):
    """`은(는)` 류를 name 의 마지막 글자 받침에 맞춰 실제 한 글자로 접는다."""
    last = name[-1] if name else ""
    has_batchim = bool(batchim(last)) if "가" <= last <= "힣" else False

    def rep(m):
        return m.group(1) if has_batchim else m.group(2)

    return JOSA_PAIR.sub(rep, text)


def longest_names():
    """(이름, 출처) — ED1·ED2 파티/주인공 + 몬스터(접미 포함) 최장 후보들."""
    names = []
    names.append((PU.HERO[0x800], "ED1 주인공"))
    for kr in PS.PARTY.values():
        names.append((kr, "ED2 파티"))
    from dict_tables import monsters_ed2

    mon_ed2 = monsters_ed2()
    for kr in mon_ed2.values():
        names.append((kr, "ED2 몬스터"))
    for kr in PI.MONSTERS.values():
        names.append((kr, "ED1 몬스터"))
    # 접미(A~F, 최대 2자 — `′`·`”` 분열체 포함)까지 더한 최악값도 후보에 넣는다.
    worst = max(names, key=lambda t: len(t[0]))
    names.append((worst[0] + "A′", f"{worst[1]}(접미 최악)"))
    return names


def templates():
    """[(출처, 원문 템플릿)] — `%s`를 가진 런타임 조립 문자열 전부."""
    out = []
    for rel in ("textmap/battle.json", "textmap/battle_ed2.json", "textmap/items_battle.json"):
        path = os.path.join(GAME, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        for e in d.get("entries", []):
            t = e.get("ours", "")
            if "%s" in t:
                out.append((rel, t))
    from dict_tables import monster_lines_ed2

    for v in monster_lines_ed2().values():
        if "%s" in v:
            out.append(("textmap/monster_lines_ed2.json", v))
    path = os.path.join(GAME, "script", "ED2MON_LINES.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        for k, v in d.items():
            if not k.startswith("_") and "%s" in v:
                out.append(("script/ED2MON_LINES.json", v))
    return out


ED1_SRC = ("textmap/battle.json",)
ED2_SRC = ("textmap/battle_ed2.json", "textmap/monster_lines_ed2.json", "script/ED2MON_LINES.json")
# items_battle.json 은 두 편이 공유(아이템 사용은 ED1·ED2 둘 다에서 일어난다) — 명시하지 않고
# 기본값(둘 다)으로 둔다.

# 실제 다개체 접미 — `′`/`″` 분열체는 뺀다(붉은슬라임류 2~4종에만 실존, SPLIT_SLIME_MSGS
# 가 따로 지킨다). ⚠ **A~F 는 전부 반각 알파벳 1바이트라 폭에 미치는 영향이 동일**하다 —
# 여섯 글자를 다 넣으면 같은 문제를 여섯 번 세는 것과 같다. 대표로 "A" 하나만 쓴다.
_SUFFIXES_REAL = ("", "A")

# 🔴 **`%s` 가 이름이 아닌 템플릿** — `.replace("%s", name)` 은 모든 `%s` 를 **같은
# 이름**으로 채우는데, 아래는 (마지막) `%s` 가 이름이 아니다(056 재측정 2026-09-15):
#   - "주문을 익혔습니다" — 둘째는 **마법 이름**(최장 4음절, 몬스터 이름보다 훨씬 짧다).
#     실측: 진짜 마법 풀로 재면 27반각(<=29, 안전). 몬스터 이름을 넣으면 32반각으로
#     **거짓 초과**가 뜬다.
#   - "%s의 피해" — 둘째는 **숫자**(피해량). 몬스터 이름을 넣으면 35반각으로 거짓 초과.
#   - "%c해적%c에 %s의 피해!!\n" — 위와 **같은 문형**("...%s의 피해!!\n")인데 대상이
#     "해적"(ED1 라누라 해적단 전용 고정 상대, `%c%s%c의 공격\n`↔`%c해적%c의 공격\n`
#     쌍처럼 이 단체만 이름이 고정된 자리)으로 박혀 있다 — 이 `%s`도 **숫자**(피해량)다.
#     이름 후보를 넣으면 자이언트에이프A 등 3건이 29반각을 1~2 넘겨 거짓 초과가 뜬다
#     (2026-09-15 재조사 — 056 재측정에서 셋째로 찾은 같은 부류).
# 이 셋은 손으로 올바른 풀(마법 이름·짧은 숫자)로 검산해 안전을 확인했고 줄바꿈도 이미
# 반영돼 있다 — 여기서 빼지 않으면 이 도구 자신이 매번 거짓 양성을 낸다.
NUMERIC_S_TEMPLATES = frozenset(
    {
        "%c%s%c은(는)\n%s 주문을 익혔습니다.",
        "%c%s%c에 %s의\n피해!!\n",
        "%c해적%c에 %s의 피해!!\n",
        # qa2-026(마스터 QA 2026-09-22) — 대상이 유정물(사람)인데 "에"를 써 "에게"로
        # 교정. 조사만 바뀌었을 뿐 **문형은 그대로**(둘째 %s 는 여전히 피해량 숫자다) —
        # 문자열 리터럴로 등록하는 방식이라 텍스트가 바뀌면 새로 등록해야 한다.
        "%c%s%c에게 %s의 피해!!\n",  # 10-10 2-10: 문장 안 강제 개행 걷음
        "%c해적%c에게 %s의 피해!!\n",
    }
)


def realistic_names(src):
    """(이름, 출처) — **src 템플릿이 실제로 받을 수 있는** 이름만(2026-09-14, 마스터 QA
    056 — "16,475건은 우리가 셀 수 있는 것이지 일어나는 것이 아니다").

    ⚠ **분모를 세 축으로 좁힌다** — ⑴ **편(ED1/ED2) 분리**: `textmap/battle.json` 은
    ED1 코퍼스라 ED1 몬스터·주인공만, ED2 전용 파일 셋은 ED2 파티·몬스터만 받는다
    (ED1 몬스터가 ED2 전용 대사를 말할 일이 없다 — 파일이 이미 갈려 있다는 사실
    자체가 근거다, 새 RE 불필요). ⑵ **파티는 실제 인원만**(ED2 는 4명 고정, "최악
    이름" 이론치를 안 쓴다). ⑶ **접미는 무접미+A 두 경우만**(A~F 는 전부 반각 1B 라
    폭엔 동일하다 — `′`/`″` 분열체는 붉은슬라임류
    2~4종에만 실존해 일반화하면 과대추정이다 — `patch_ed2_monsters.SPLIT_SLIME_MSGS`
    가 그 자리를 별도로 지킨다).

    🔴 **"어느 템플릿을 어느 몬스터가 실제로 쓰는가"(AI/기술표 매핑)는 아직 없다** —
    그건 새 RE 가 필요해 이번 축소엔 안 넣었다. 그래서 이 함수도 여전히 **위쪽
    추정**이다(그 종이 그 템플릿을 아예 안 쓸 수도 있는데 후보에는 남는다) — 다만
    이전 216 후보(ED1 몬스터 92종 + 이론상 최악 접미)보다는 분모가 훨씬 좁혀졌다.
    """
    names = []
    if src in ED1_SRC:
        names.append((PU.HERO[0x800], "ED1 주인공"))
        for kr in PI.MONSTERS.values():
            for suf in _SUFFIXES_REAL:
                names.append((kr + suf, "ED1 몬스터"))
    elif src in ED2_SRC:
        for kr in PS.PARTY.values():
            names.append((kr, "ED2 파티"))
        from dict_tables import monsters_ed2

        mon_ed2 = monsters_ed2()
        for kr in mon_ed2.values():
            for suf in _SUFFIXES_REAL:
                names.append((kr + suf, "ED2 몬스터"))
    else:  # items_battle.json 등 — 편이 안 갈리는 자리는 두 편 다 받는다
        names.append((PU.HERO[0x800], "ED1 주인공"))
        for kr in PS.PARTY.values():
            names.append((kr, "ED2 파티"))
        from dict_tables import monsters_ed2

        mon_ed2 = monsters_ed2()
        for kr in mon_ed2.values():
            for suf in _SUFFIXES_REAL:
                names.append((kr + suf, "ED2 몬스터"))
        for kr in PI.MONSTERS.values():
            for suf in _SUFFIXES_REAL:
                names.append((kr + suf, "ED1 몬스터"))
    return names


def check_byte_budget(*, strict=True, verbose=False):
    """**진짜 게이트** — 메시지박스 버퍼(fp+0x18~0xA0, 136B) 오버플로를 막는다.

    `check()`/`check_realistic()`(반각 폭)는 **보기**(어절 중간 절단)를 본다 — 이건
    **구조**(`ra` 를 덮으면 소프트락)를 본다. 성격이 달라 **strict=True 가 기본**이다.
    """
    tmpls = templates()
    over = []
    for src, t in tmpls:
        if t in NUMERIC_S_TEMPLATES:
            continue
        names = realistic_names(src)
        manual_nl = t.count("\n")
        for name, name_src in names:
            filled = t.replace("%s", name)  # %c 는 유지 — 실제 버퍼에 그대로 나간다
            blen = _enc_len(filled) + AUTO_NEWLINE_RESERVE + 1  # +1 널 종단
            if blen > BYTE_LIMIT:
                over.append((src, t, name, name_src, blen))
    print(
        f"  런타임 템플릿 {len(tmpls)}개 — 메시지박스 버퍼({BYTE_LIMIT}B 권장) 초과 {len(over)}건"
    )
    if verbose:
        for src, t, name, name_src, blen in over:
            print(f"    [{src}] {t!r} + {name!r}({name_src}) = {blen}B")
    if over and strict:
        lines = [
            f"    [{src}] {t!r} + {name!r}({name_src}) = {blen}B"
            for src, t, name, name_src, blen in over
        ]
        raise SystemExit(
            f"런타임 템플릿이 메시지박스 버퍼({BYTE_LIMIT}B)를 넘는다 — "
            f"strcpy 에 길이검사가 없어 ra 를 덮을 수 있다(소프트락)\n" + "\n".join(lines[:20])
        )
    return len(over)


def check_realistic(*, top_n=20, verbose=False, strict=False):
    """`check()`(이론상 최악)와 짝 — **실제로 날 수 있는 조합**만으로 다시 센다.

    🔴 **2026-09-15 게이트로 승격** — 056 재측정에서 세 번째 거짓 초과 템플릿
    (`%c해적%c에 %s의 피해!!\n`, `%s`가 이름이 아니라 숫자)을 `NUMERIC_S_TEMPLATES`
    로 걸러내자 실제 초과가 **0건**이 됐다. "0이 된 축을 보고로만 두면 다시 늘어도
    아무도 안 본다"(루트 CLAUDE.md) — 그래서 `strict=True`로 `build.py` 에 물렸다.
    ⚠ 분모가 여전히 위쪽 추정이긴 하다(`realistic_names()` 참조 — "어느 템플릿을
    어느 몬스터가 실제로 쓰는가" 매핑은 없다) — 하지만 그건 **과대추정 방향**이라
    실제로 날 수 있는 조합을 놓치지 않는다(가짜 초과는 낼 수 있어도 가짜 통과는 안 낸다).
    가장 많이 넘친 상위 `top_n` 을 같이 낸다: 마스터가 "어디부터 고칠지" 정할 때
    체감이 가장 큰 자리다(긴 이름 × 긴 문장).
    """
    tmpls = templates()
    over, exempt = [], []
    for src, t in tmpls:
        if t in NUMERIC_S_TEMPLATES:
            continue
        names = realistic_names(src)
        t_novis = t.replace("%c", "")
        for name, name_src in names:
            filled = t_novis.replace("%s", name)
            folded = _fold(filled, name)
            # 🔴 **모든 줄을 잰다** — 첫 줄만 재면 "넘치는 자리에 \n 을 넣는다"는 고침
            # 자체가 게이트를 무력화한다(둘째 줄이 아무리 넘쳐도 통과). 2026-09-15,
            # 관리자 지적 — 고치는 법과 재는 법이 정면으로 부딪히는 자리였다.
            w = max(_width(line) for line in folded.split("\n"))
            if w > FRAME_HALFWIDTH:
                row = (src, t, name, name_src, w, w - FRAME_HALFWIDTH)
                exempt_rows = t in WIDTH_EXEMPT_TEMPLATES or src in WIDTH_EXEMPT_SOURCES or (
                    name.rstrip("ABCDEFGHIJ′”") in WIDTH_EXEMPT_NAMES
                )
                (exempt if exempt_rows else over).append(row)
    over.sort(key=lambda r: -r[5])
    if exempt:
        print(
            f"  ℹ 폭 초과 허용(이름 {', '.join(sorted(WIDTH_EXEMPT_NAMES)) or '없음'} · "
            f"템플릿 {len(WIDTH_EXEMPT_TEMPLATES)}개) {len(exempt)}조합 — 실패로 안 센다"
        )
    print(
        f"  실제 분모(편 분리·파티 4인 고정·무접미+A 두 경우): 템플릿 {len(tmpls)}개, "
        f"초과 조합 {len(over)}건 (이전 이론치는 check() 참조)"
    )
    print(f"  초과폭 상위 {min(top_n, len(over))}건(개별 조합):")
    for src, t, name, name_src, w, excess in over[:top_n]:
        print(f"    +{excess}반각(총 {w}) [{src}] {t!r} + {name!r}({name_src})")
    # 🔴 위 목록은 **같은 템플릿이 이름만 바뀌어 반복**되는 경우가 대부분이다 — 진짜
    # 손볼 자리는 "이름"이 아니라 "그 템플릿 문장 자체"다. 템플릿별로 묶어서
    # 몇 개 이름에서 넘치는지 보여주면 "무엇부터 줄일지"가 바로 보인다.
    by_template = {}
    for src, t, _name, _name_src, _w, excess in over:
        key = (src, t)
        cur = by_template.setdefault(key, [0, 0])
        cur[0] += 1
        cur[1] = max(cur[1], excess)
    ranked = sorted(by_template.items(), key=lambda kv: (-kv[1][1], -kv[1][0]))
    print(f"\n  템플릿별 집계 — 문장 자체를 줄이면 가장 큰 상위 {min(10, len(ranked))}개:")
    for (src, t), (n_over, max_excess) in ranked[:10]:
        print(f"    [{src}] 최대 +{max_excess}반각, {n_over}개 이름에서 초과: {t!r}")
    if over and strict:
        raise SystemExit(
            "런타임 템플릿이 실제로 날 수 있는 이름 조합에서 창 틀(29반각)을 넘는다 — "
            "낱말 한가운데서 잘릴 위험(056)"
        )
    return over


def check(*, strict=True, verbose=False):
    names = longest_names()
    over = []
    tmpls = templates()
    for src, t in tmpls:
        if t in NUMERIC_S_TEMPLATES:
            continue
        # `%c...%c`(제어 색코드)는 화면에 안 나가는 1바이트 런타임 코드다 — 폭에서 뺀다.
        t_novis = t.replace("%c", "")
        for name, name_src in names:
            filled = t_novis.replace("%s", name)
            folded = _fold(filled, name)
            # 🔴 **모든 줄을 잰다**(2026-09-15 정정) — 예전엔 "여러 줄로 자연히 나뉘면
            # 이 게이트 대상이 아니다"로 첫 줄만 쟀는데, 그러면 "넘치는 자리에 \n 을
            # 넣는다"는 **고치는 법 자체가 게이트를 무력화한다**(둘째 줄이 얼마나
            # 넘치든 통과). 검사기 커버리지 결함(4-B) — 관리자 지적.
            w = max(_width(line) for line in folded.split("\n"))
            if w > FRAME_HALFWIDTH:
                over.append((src, t, name, name_src, w))
    print(
        f"  런타임 템플릿 {len(tmpls)}개 × 후보 이름 {len(names)}개 — 창 틀(29반각) 초과 {len(over)}건"
    )
    if verbose:
        for src, t, name, name_src, w in over:
            print(f"    [{src}] {t!r} + {name!r}({name_src}) = {w}반각")
    if over and strict:
        lines = [
            f"    [{src}] {t!r} + {name!r}({name_src}) = {w}반각"
            for src, t, name, name_src, w in over
        ]
        raise SystemExit(
            "런타임 템플릿이 가장 긴 이름을 꽂으면 창 틀(29반각)을 넘는다 — "
            "낱말 한가운데서 잘릴 위험\n" + "\n".join(lines[:20])
        )
    return len(over)


if __name__ == "__main__":
    if "--realistic" in sys.argv:
        check_realistic(verbose="-v" in sys.argv)
        sys.exit(0)
    if "--bytes" in sys.argv:
        sys.exit(1 if check_byte_budget(strict=False, verbose="-v" in sys.argv) else 0)
    sys.exit(1 if check(strict=False, verbose="-v" in sys.argv) else 0)
