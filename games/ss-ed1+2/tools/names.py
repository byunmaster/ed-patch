"""**개체 접미와 이름 대조** — 이름 규칙의 정본. 세 곳이 따로 들다 갈렸다.

## 왜 한 곳인가

같은 물음(「이 원문이 어느 이름인가」)을 세 도구가 각자 답하고 있었고, **답이 달랐다**
(실측 2026-08-29):

    derive_encounters.MARKS  ＡＢＣＤＥＦABCDEF        ← Ｇ~Ｊ 를 모른다
    patch_mon_names.MARKS    ＡＢＣＤＥＦＧＨＩＪ…      ← 프라임(`'`)까지 안다
    patch_scn._MARK          ＡＢＣＤＥＦＧＨＩＪ + ♀♂  ← 반각·공백까지 편다

    `くぐつ戦士Ｇ` → derive (없다) · mon_names (꼭두각시전사G) · patch_scn (꼭두각시전사G)

한 화면에서 이름이 붙고 다른 화면에서 원문이 남는다. 🔴 **표를 두 곳에 두면 갈린다** —
이 레포가 오늘만 세 번 물린 실패다(열쇠 중립화표 · 창 총량 전제 · 이것).

## 무엇을 아나

- **개체 접미** `Ａ`~`Ｊ`(전각·반각) · **성별** `♀♂` · **프라임** `'`(분열체 표시, 개수를 지킨다)
- **표기 흔들림** — 반각 가나 · 폭 맞춤 공백 · 중점(`ﾃﾞｽ･ｶﾞｰﾃﾞｨｱﾝ` vs 정본 `デスガーディアン`)
⚠ 접미는 **반각**으로 되돌린다 — 전각으로 붙이면 전투 화면(반각)과 갈린다.
⚠ **통짜부터 본다** — `ゴドウィン２世` 처럼 끝 글자가 접미처럼 생긴 이름이 있다.
"""

import re
import unicodedata

MARKS = "ＡＢＣＤＥＦＧＨＩＪABCDEFGHIJ♀♂"
PRIME = "'’"
HALF = {c: (chr(ord(c) - 0xFEE0) if "Ａ" <= c <= "Ｚ" else c) for c in MARKS}
HALF.update({"’": "'", "'": "'"})

# ⚠ `＝` 도 뗀다 — 일본어 이름의 구분자다(`バトル＝スーツ`). `check_glossary` 만 떼고
#   있었고 나머지 둘은 안 떼서 **셋이 갈려 있었다**(2026-08-29).
_TRIM = re.compile(r"[\s　・･=＝]")


def bare(s):
    """이름 대조용 꼴 — **반각 가나를 펴고 공백·중점을 뗀다**.

    ⚠ **표를 손으로 들지 않는다** — NFKC 가 반각 가나(탁점 포함)를 편다. 표로 접다가
      작은 모음(`ｧｨｩｪｫ`)을 빠뜨려 절반이 안 붙었다(2026-08-29).
    """
    return _TRIM.sub("", unicodedata.normalize("NFKC", s))


def split_mark(jp, table):
    """`(우리 표기, 반각 접미)` — 정본에 없으면 `(None, "")`.

    프라임은 개체 번호가 아니라 **분열체 표시**라 개수까지 지킨다(`A''` 는 둘째 분열).
    """
    if jp in table:
        return table[jp], ""
    body, prime = jp, ""
    while len(body) > 1 and body[-1] in PRIME:
        body, prime = body[:-1], HALF[body[-1]] + prime
    if body in table:  # 접미 없이 프라임만 붙는 꼴
        return table[body], prime
    if len(body) > 1 and body[-1] in MARKS and body[:-1] in table:
        return table[body[:-1]], HALF[body[-1]] + prime
    return None, ""


def lookup(jp, table, *, fold=True):
    """원문 한 덩어리 → 우리 표기. 없으면 `None`.

    `fold` 면 **표기 흔들림까지 흡수한다**(반각 가나 · 폭 맞춤 공백 · 중점) — 같은 이름이
    자리마다 다르게 적힌 칸을 잇는다. 정확한 대조만 원하면 끄고 쓴다.
    """
    kr, sfx = split_mark(jp, table)
    if kr is not None:
        return kr + sfx
    if not fold:
        return None
    folded = {bare(k): v for k, v in table.items()}
    kr, sfx = split_mark(bare(jp), folded)
    return None if kr is None else kr + sfx


def internal_key(jp):
    """**게임 내부 키**인가 — 반각 가나가 섞였으면 그렇다.

    🔴 건드리면 자료를 부순다. 지명·이름 표에 `ｴﾙｱｽﾀ`·`ﾙﾃﾞｨｱT`·`ｲｼｭ/ｲｽ` 처럼 섞여 있는데,
       글자가 이름처럼 보인다고 번역하면 **그 키로 찾는 코드가 못 찾는다.**
    ⚠ 두 번 헛짚었다(2026-08-27) — 「반각 가나·ASCII 만」으로 재면 `ｲｼｭﾀ～ｲｽﾞｰ` 의 전각
      물결에 걸리고, 「전각 가나·한자가 있나」로 재면 `ｳｲﾙ～城` 의 한자에 걸린다.
      화면에 나가는 이름은 **원본이 전부 전각**이므로, 반각 가나가 하나라도 섞였으면 키다.
    🔴 실측 2026-08-29: 이 규칙이 `patch_ui` 에만 있어서, 이름 유도를 붙인 `patch_scn` 이
       **내부 키 19곳을 번역했다.** 그래서 여기로 모았다.
    """
    return any("\uff66" <= c <= "\uff9f" for c in jp)


# ── 지명의 종류 말 띄우기 (마스터 확정 2026-09-27) ────────────────────────────────
# 「크루즈마을」→「크루즈　마을」 — sfc 「엘아스타 마을」과 같은 규칙이다. 지명 **자체에**
# 붙은 종류 말(마을·성·동굴·탑…)만 띄운다 — 접미(`근처`·`입구`)는 `patch_ui` 몫이다.
# ⚠ **전각 공백**이다 — HUD 가 두 바이트를 한 글자로 읽어 반각 1B 는 짝을 깬다
#   (「곶의동굴 근틀」, `patch_ui` 접미 주석). 공유 정본(`shared/glossary`)은 안 고친다 —
#   전각 공백은 이 기종의 인코딩 선택이라 다른 게임에 흘리면 안 된다.
# ⚠ 목록에 없는 끝말(`입`·`변토`·`해운`·`알`·통짜 낱말)은 **일부러 뺐다** — 이름의 일부이지
#   시설 종류가 아니다(`나락의입`·`용의알`). 긴 것부터 본다(`초가집` 이 `집` 보다 먼저).
KIND_WORDS = (
    "초가집",
    "마을",
    "항구",
    "요새",
    "광산",
    "동굴",
    "호수",
    "섬",
    "성",
    "탑",
    "묘",
    "집",
    "길",
    "방",
)


def space_kind(kr, sp="　"):
    """지명 끝의 종류 말 앞에 공백 하나 — 이미 띄웠거나 종류 말뿐이면 그대로."""
    if not kr or sp in kr or " " in kr:
        return kr
    for w in KIND_WORDS:
        if kr.endswith(w) and len(kr) > len(w):
            return kr[: -len(w)] + sp + w
    return kr


# ── 대사 속 지명 띄어쓰기 (마스터 판정 2026-09-27 — 두 기종 공통, 대사에만) ────────────────
# HUD·표·세이브 슬롯은 붙인다(판정 (나), `patch_ui._fit_place`). **대사만** 아래 셋으로 띄운다:
#   ① 「성」·「섬」은 붙인다 — `루디아성`·`그로스토스성`·`해적섬`
#   ② 「~의」 뒤는 띄운다 — `국경의 동굴`·`바람의 탑`·`로엘의 집`
#   ③ 나머지 종류 말은 띄운다 — `크루즈 마을`·`베르가 광산`·`네리아 항구`(`KIND_WORDS`)
# ⚠ 공백은 **반각**이다 — 대사는 반각 공백이 보통 띄어쓰기다(전각은 HUD 짝수 약속 몫).
# ⚠ 「섬」도 붙이는 끝말이다(마스터 판정 2026-09-27 — `해적섬`·`론윌섬`). 「변토」·「입」·「알」처럼
#   목록 밖 끝말도 「~의」 뒤면 ② 로 띄운다(`네사의 변토`·`나락의 입`·`용의 알`).
#   「의」 없이 목록 밖 끝말이면 그대로다(가짜 예: `바람굴`).
ATTACHED_KINDS = ("성", "섬")


def space_place_dialog(kr):
    """대사에 쓸 지명 꼴 — 위 규칙 셋. 안 바뀌면 그대로."""
    if not kr or " " in kr or "　" in kr:
        return kr
    if kr.endswith(ATTACHED_KINDS):
        return kr
    i = kr.rfind("의", 1, len(kr) - 1)
    if i > 0:
        return kr[: i + 1] + " " + kr[i + 1 :]
    return space_kind(kr, " ")
