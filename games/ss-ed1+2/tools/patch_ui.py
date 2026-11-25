"""HUD·시스템 메뉴 한글화 — `ED.BIN`·`ED2.BIN` 제자리 재삽입 + `11KANJI.FON` 굽기.

    python3 tools/patch_ui.py            # 항등 검증만 (넣기 전 안전판)
    python3 tools/patch_ui.py --apply    # 빌드 이미지에 넣는다
    python3 tools/patch_ui.py --apply --refresh   # 슬롯 정본 갱신 (새 글자가 생겼을 때만)

⚠ **자막(`patch_title.py --apply`)을 먼저** 넣는다 — 빌드 사본을 그쪽이 만든다.

🔴 **레코드는 고정폭이다.** 포인터는 표의 첫 항목만 가리키고 나머지는 코드가 색인으로
   집는다(`dump_ui.py`). 한 칸을 넘기면 다음 항목을 먹어 메뉴가 통째로 밀리는데
   **빌드도 단위 테스트도 통과하고 화면만 깨진다** — 그래서 stride 를 매번 대조한다.

🔴 **원본을 originals 에서 읽는다.** 제자리 갱신 이미지를 되읽으면 두 번째 회차부터
   「원문이 우리 한글」이 되어 사전조건이 저절로 통과한다(레포 빌드 규율).

문안 정본은 `script/ui.json`, 저본은 PS1(`ps1-ed1+2/tools/patch_sys_ui.py:UI` — 정발 대조 +
인게임 QA 완료). 슬롯 정본은 `hangul_map_11kanji.json` 이고 **커밋한다**(빌드는 결정적).
⚠ 16px 쪽 정본은 `hangul_map.json` 이다 — 폰트가 다르니 슬롯 공간도 따로다.
"""

import hashlib
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "shared",
    ),
)

import canon as shared_canon
import common
import dump_scn
import dump_ui
import font
from font import byte_len, to_bytes
from fonts import convert_chars
from canon import lookup, table

CANON = os.path.join(common.GAME_DIR, "script", "ui.json")
SYS_CANON = os.path.join(common.GAME_DIR, "script", "system.json")
HMAP = os.path.join(common.GAME_DIR, "hangul_map_11kanji.json")
FON = "/11KANJI.FON"
FON_ASCII = "/11ASCII.FON"
ASCII_STRIDE = 11  # 11행 × 1바이트 (8×11)
PAD = "　"  # 전각 공백 — 원본 폰트에 이미 있어 슬롯을 안 먹는다


# 🔴 **메뉴 라벨(JP→KR)은 정본에서 읽는다**(마스터 2026-10-08 — 사전은 고유명사만, 라벨은 `shared/canon`).
#    `script/ui.json` 의 `tables` 는 **표 구조(어느 표에 어느 JP 가 몇 번째로 오나)** 만 든다 — 값은 정본이
#    갖는다. 정본에 없는 JP(`ＯＮ`·`ＳＡＶＥ` 처럼 원문 그대로 두는 칸)만 이 파일의 KR(None)을 따른다.
#    같은 JP 가 자리마다 다른 말이면(強さ=상태·강함·힘, 逃げる=도망·도망간다) 정본 열쇠가 `원문@자리` 다.
_UI_POS = {
    "필드 메뉴": "파티메뉴",
    "전투 명령": "전투커맨드",
    "능력치": "능력치",
    "EP 표시": "경험치표시",
    "전투설정/도망": "전투설정",
}


def _ui_label(jp, table_name):
    """표 칸 JP → 정본 KR. 없으면 None. ED1 정본을 먼저, 없으면 ED2(겹치는 열쇠는 값이 같다)."""
    k = re.sub(r"[\s\u3000]", "", jp)
    keys = ([f"{k}@{_UI_POS[table_name]}"] if table_name in _UI_POS else []) + [k]
    for title in ("ed1", "ed2"):
        for key in keys:
            v = shared_canon.lookup(key, "ui", title)
            if v is not None:
                return v
    return None


def _chapter_title(jp):
    for title in ("ed1", "ed2"):
        v = shared_canon.lookup(jp, "chapter", title)
        if v is not None:
            return v
    return None


def _cards():
    """챕터 카드 `[JP 제목, 번호 라벨, KR 제목]` — 🔴 전부 정본(`shared/canon` chapter)에서 읽는다.

    제목은 `JP제목` 열쇠, 번호 라벨(`제１장`·`종장`·`서장`)은 `JP제목@번호` 열쇠다. ED1 정본 먼저, ED2 다음 —
    예전엔 `ui.json` 이 12장 목록을 JP 열쇠로 들고 있었다(마스터 2026-10-08 — 자기 표 금지).
    """
    out = []
    for title in ("ed1", "ed2"):
        for jp, ti in shared_canon.table("chapter", title).items():
            if "@" in jp:
                continue
            # 번호 라벨(`제목@번호`)이 있는 장 제목만 — 정본엔 다른 기종의 장 표기(`第１章` 등)도 들어 있다
            no = shared_canon.lookup(f"{jp}@번호", "chapter", title)
            if no:
                out.append([jp, no, ti])
    assert len(out) == 12, f"정본 chapter 의 번호 붙은 장 제목이 12 가 아니다: {len(out)}"
    return out


def _canon_at(category, place):
    """정본 `category` 의 `원문@자리` 열쇠 중 그 자리 것 → `{원문: KR}` (ED1 먼저, ED2 다음).

    `@시스템` = 시스템 문자열 스캔이 통째로 집는 라벨(지명 접미 6칸·`メニュートップ`). 예전엔 `system.json` 이
    이 JP→KR 을 해시 열쇠로 들고 있었다. (새턴 본체 RAM·세이브 안내문 `msgs` 는 새턴 고유 문안이라 정본이 아니다 —
    `ui.json` 의 해시 열쇠 script.)
    """
    out = {}
    for title in ("ed1", "ed2"):
        for k, v in shared_canon.table(category, title).items():
            if k.endswith("@" + place):
                out.setdefault(k[: -len(place) - 1], v)
    return out


def _canon_sys_lines():
    """`{sys_key(JP): KR}` — 시스템 문자열 스캔에 정본 라벨을 보탠다(`_canon_at("ui", "시스템")`)."""
    return {sys_key(jp): kr for jp, kr in _canon_at("ui", "시스템").items()}


def load_canon():
    """`(cards, pad_to_jp, msgs{sha1: KR})` — 🔴 표 칸·카드 목록을 이 폴더에 두지 않는다. JP 는 원본에서 읽고 KR 은 정본이 갖는다
    (`_ui_label` · `_cards`; 마스터 2026-10-08 — 워커는 JP→KR 표를 자기 폴더에 두지 않는다)."""
    with open(CANON, encoding="utf-8") as f:
        d = json.load(f)
    return (
        _cards(),
        d.get("pad_to_jp", []),
        d.get("msgs", {}),
    )


def _pad_to(kr, target):
    """반각 단위 `target` 폭이 되도록 뒤에 공백을 붙인다 — 전각 우선, 홀수 하나는 반각."""
    need = target - _half(kr)
    if need <= 0:
        return kr
    return kr + PAD * (need // 2) + " " * (need % 2)


# ── 「…근처」 접미와 띄우기 ──────────────────────────────────────────────────
# 화면의 「곶의동굴 근처」는 **여기서 조립된다** — `ED.BIN` 0x44BE8 루틴이 이 표(14B 스트라이드)
# 에서 지명을 **NUL 까지 상한 없이** 복사하고, 뒤에 접미를 **정확히 4B** 붙인다
# (스택에 `入口`[0]·`付近`[4]·`北`[8]·`南`[12]·`東`[16]·`西`[20] 를 4B 간격으로 깔아 둔다).
#
# 🔴 그래서 **접미 쪽엔 공백을 못 넣는다** — 4B 는 전각 두 자로 이미 꽉 찼다.
#    넣는 자리는 **지명 끝**뿐이고, 레코드가 14B 라 우리 이름이 짧은 만큼 여유가 있다.
#
# ⚠ **반각 공백(1B)은 쓰지 말 것.** 「곶의동굴 근처」가 「곶의동굴 근틀」로 나왔다(유저 QA
#   2026-08-25). 길이 문제가 아니라 **바이트 짝이 깨진 것**이다 — 이 화면은 두 바이트를
#   한 글자로 읽으므로 1B 를 끼우면 뒤가 전부 반 칸씩 밀려 엉뚱한 글자가 된다.
#   전각 공백(`\u3000`, JIS 0)은 2B 라 짝이 유지되고, 원본 폰트가 이미 쓰던 슬롯이라
#   빈칸으로 그대로 그려진다.
# 💡 길이 상한은 **원문 자신이 알려 준다** — 원문 최장이 `ベルガの鉱山`(12B)+`付近`(4B)=16B 다.
#    12B 에서 잘린다고 봤던 앞선 진단은 틀렸다(반각 공백이 만든 착시였다).
# ⚠ 안 들어가는 칸은 **그냥 붙여 쓴다**(실측: ED2 `그로스토스성` 12B+2B+NUL=15B > 14B).
#    성·탑처럼 긴 지명은 원래 접미가 안 붙는 자리다.
# 🔴 **포인터가 있어도 못 옮기는 자리**(2026-08-28 실기). 위 주석의 접미 표가 그것이다 —
#    조립 루틴(`ED.BIN` 0x44BE8)이 **4B 간격의 표로** 집으므로, 참조를 갱신해도 표가 흩어지면
#    깨진다. 실제로 시스템 메시지가 늘자 배치기가 여섯을 옮겼고 화면에 `メ§電 リ…처` 가 떴다.
#    ⚠ 「포인터가 없으면 못 옮긴다」만으로는 부족하다 — **포인터가 있는데도 못 옮기는 자리**가
#      있다. 코드가 그 주소를 쓰는지 여부는 포인터 유무로 안 갈린다.
#    ⚠ `ED2.BIN` 에는 이 표가 없다(원문 `入口`·`付近`·`南` 이 아예 없다).
# 🔴 **`ED2.BIN` 0x69CE2 — ED2 「긴꼴」 지명 표의 맨 앞 칸**(`エルアスタ`, 입장 배너 표). 표 등록(`dump_ui`)은 0x69CF2 부터라
#    이 칸만 **시스템 문자열**로 잡히는데, **그 포인터가 표 전체의 기준 포인터**다(코드가 `기준 + 색인×16` 으로 집는다).
#    이주(sys_pack)가 이 문자열을 옮기면 기준 포인터가 새 자리로 따라가 **표 36칸을 통째로 엉뚱한 곳에서 읽는다** —
#    실화면: 월드맵 마을 팝업이 「엘아스타」 대신 「%c%s%c에게」 템플릿을 그렸다(2026-10-08, JP 원본 같은 지점은 「エルアスタ」).
#    ⇒ **제자리에만 쓴다**(핀). 칸 16B 에 「엘아스타마을」 12B+널이 든다.
# 🔴 **「(별도 1글자 문자열) 4곳 — 「…」의 주문은 봉인되어 있다 앞의 낫표**(마스터 10-27 「」 반각). 1B+널 이라 제자리에 들어가고, 풀에 맡기면 가장 작은
#    조각(이름 표 꼬리의 2B)에 앉아 표 패딩 검사(`check_table_padding` C)가 운다.
PINNED_INPLACE = {
    "/ED.BIN": (0x44BC8, 0x44BD0, 0x44BD8, 0x44BDC, 0x44BE0, 0x44BE4, 0x2BFE8, 0x36E84),
    "/ED2.BIN": (0x69CE2, 0x12680, 0x14718),
}

SUFFIXED_TABLE = "지명"
WIDE_SP = "\u3000"


def _internal_key(jp):
    """**게임 내부 키**인가 — 🔴 규칙은 `names.internal_key` 가 정본이다.

    여기에만 있던 탓에 `patch_scn` 이 모르고 내부 키 19곳을 번역했다(2026-08-29).
    """
    from names import internal_key

    return internal_key(jp)


# 🔴 **칸이 원문에 접미를 구운 지명**(ED2 「지명 긴꼴」 표의 `マスクーンの町` 등)은 사전(고유명사)에 열쇠가 없다 —
#    그 칸 꼴은 **정본**(`shared/canon` ed2 `ui`)이 든다(마스터 2026-10-08·10-07 「지명 칸은 원문 꼴 그대로」).
#    예전엔 여기 JP 다섯(`_NO_SUFFIX_PLACES`)을 코드에 들고 접미를 벗겨 재조회했다 — 같은 지식을 코드에 둔 것이었다.
def _route_name(jp):
    """길 이름 `ｲｼｭﾀ～ｲｽﾞｰ`(반각 가나 + 전각 물결) → 한국어. 씬 정본(`script/scn.json`)이 같은 문자열을 번역해 둔다(ED2SCN46·47 헤더) — 같은 말을 한 곳에서 읽는다."""
    import patch_scn

    return patch_scn.load_canon(quiet=True).get(patch_scn.line_key(jp))


def _place_lookup(jp, cat):
    """사전(`place`)을 먼저, 없으면 정본 `ui` 의 칸 꼴(`~の町` 구운 꼴)."""
    kr = lookup(jp, cat, "eiyuu")
    if kr is not None or cat != "place":
        return kr
    return shared_canon.lookup(jp, "ui", "ed2") or shared_canon.lookup(jp, "ui", "ed1")


# 🔴 **종류 말은 붙여 쓴다**(마스터 판정 (나) 2026-09-27 — PS1 과 같은 꼴). HUD·표·헤더의
#    지명은 「크루즈마을」이고, 공백은 **뒷말(입구·부근·방위) 앞에만** 전각으로 둔다.
#    ⚠ 한때 종류 말을 전각으로 띄웠다(24종) — 칸이 안 드는 이름이 섞여 이름마다 판정하는
#      장치까지 붙었는데, 판정 (나)로 통째로 걷었다. 경위는 devlog 09-27.
#    ⚠ 공백은 **전각**이다 — 지명 칸 바이트 길이가 늘 짝수여야 한다(`check_place_fields`).


# 🔴 **입장 배너 필드 폭 상수**(`0x0607AD60`, 라이브 확정 — devlog 09-27 「드디어 잡았다」).
#   배너 박스는 타일 단위(10타일×9px=90px)인데 이 함수는 **왼쪽 패딩만** 계산한다(오른쪽
#   패딩이 없다 — `strcat` 로 이름을 그대로 붙이고 끝). 그런데 우리 지명 표(`ED.BIN`
#   `0x060AC754`+색인×14)는 전 칸(48/48)에 **HUD 접미("…부근/…입구") 구분용 트레일링
#   전각공백**이 박혀 있다(`patch_ui.py` `_fit_place`, `SUFFIXED_TABLE="지명"`). 그 공백이
#   `strlen()` 에 잡혀 실제로 그려지므로 **오른쪽에 항상 12px 이 고정으로 남는다** — 이
#   12px 은 전 칸에 똑같이 붙으므로(전각이라 바이트 길이가 늘 짝수) 왼쪽 시작점만 그만큼
#   옮기면 보이는 이름이 도로 가운데로 온다.
#   실측: 상수 15(왼쪽 13·오른쪽 23, 차 10px) → **17**(왼쪽 19·오른쪽 17, 차 2px —
#   6px 단위라 이보다 더 가깝게는 못 맞춘다). 완전히 0 으로 닫으려면 이름 복사 자리
#   (`jsr 0x06095d5c`)를 코드 훅으로 바꿔 트레일링 공백 자체를 안 그려야 하는데, 이 함수는
#   마을 진입마다 도는 자리라 관리자 판단으로 **상수 하나로 닫는 쪽**을 택했다(devlog 09-27).
#   ⚠ `ED2.BIN` 은 이미 다른 값(14)을 쓴다 — 박스 크기를 확인 안 했으니 이번엔 건드리지
#   않는다(`ED.BIN`=ED1 만).
# 🔴 **가운데 = 가능한 위치 중 가장 가까운 것, 같을 때만 왼쪽**(번역 규칙 2-8, 마스터 11-09). 배너 전용 표(꼬리 전각공백 없음)로 바뀌며 필드폭 17→15(꼬리 공백 2B 몫 환원), 시작 x 는 실렌더로 최근접을 골랐다.
BANNER_FIELD_NEW = 15
BANNER_X_NEW = 62
HUD_FIELD_OFF = 0x516A1  # `/ED.BIN` 파일 오프셋 — `add #16,r1`(RAM 0x060796A0)의 즉치 바이트
HUD_FIELD_NEW = 17
ED2_BANNER_X_NEW = 62
BANNER_FIELD_OFF = 0x52D85  # `/ED.BIN` 파일 오프셋 — `add #12,r1`(RAM 0x0607AD84)의 즉치 바이트

# 🔴 **마스터 미세조정**(2026-09-27 「약간 왼쪽으로 치우치게」) — 위 필드폭은 6px 단위라
#   왼쪽 19/오른쪽 17 까지만 좁힌다. 마스터는 반대(왼쪽이 더 좁고 오른쪽이 더 넓은 쪽)를
#   원해 **픽셀 단위로 시작 x 를 정하는 자리**(`0x0607ADCA`, `jsr 0x0607D160` 지연 슬롯의
#   `mov #63,r4`)를 직접 건드린다 — 필드폭(바이트 단위, 6px 배수)과 달리 이 자리는 1px
#   단위로 왼쪽·오른쪽을 함께 옮긴다. `63→61`(-2px)로 왼쪽17·오른쪽19 예상.
BANNER_XBASE_OFF = 0x52DCB  # `/ED.BIN` 파일 오프셋 — `mov #63,r4`(RAM 0x0607ADCA)의 즉치 바이트

# 🔴 **마스터 미세조정 2**(2026-09-27 「위쪽에 쏠려 있다」) — 배너가 상하로도 위로 쏠려
#   있었다(실측 위2px·아래5px). x 와 같은 자리 바로 옆에 **y 를 1px 단위로 정하는 자리**가
#   있다(`0x0607ADC6`, `mov #61,r5` — x_base 를 넣는 지연 슬롯 바로 앞 명령). `62`(+1px)로
#   위3·아래4 후보와 `63`(+2px)로 위4·아래3 후보를 라이브로 만들어 마스터가 `62`를 골랐다.
BANNER_YBASE_OFF = 0x52DC7  # `/ED.BIN` 파일 오프셋 — `mov #61,r5`(RAM 0x0607ADC6)의 즉치 바이트


# 🔴 **입장 배너 전용 이름 표**(마스터 11-09 「입장배너도 가능하다면 띄어쓰기」· 정본 일반 꼴 `canon.place_general` — 성·섬은 붙임). 배너 호출부는 HUD·워프와
#   **리터럴이 따로**다 — ED1 `ED.BIN` 0x5B7E8(= 지명 표 − 14B, 한 군데) · ED2 `ED2.BIN` 의 긴꼴 표 리터럴 0x06091CD2(= 표 − 32B) 여덟 군데(그림 함수 `0x06058D78` 호출부).
#   → 전용 표를 시스템 메시지 자리 풀에 깔고(`sys_pack(extra=…)` — 구조가 우리 것인 풀) **그 리터럴만** 새 표로 돌린다. HUD·워프는 옛 표(붙임) 그대로.
#   표 앞 `lead` 바이트는 원 호출부가 기준 포인터를 「한 칸 앞」으로 두는 규약이라 맞춘 더미다(`check_place_fields.table_base_refs` 의 같은 주의).
BANNER_TABLES = {
    "/ED.BIN": dict(key="ED", tab="지명", stride=14, lead=14, title="ed1", ptrs=(0x5B7E8,)),
}
# 🔴 **ED2 입장 배너 띄어쓰기는 런타임 끼움**(11-09) — 긴꼴 표(36칸×16B)는 워프 목록과 같이 쓰고 워프는 붙여 써야 해서(마스터), 표를 복제하지 않는다
#   (연속 576B 자리도 없다 — 풀 최대 조각 344B). 대신 **배너 그리기 함수(`ED2.BIN` 0x06058D78)가 부르는 strlen 리터럴(0x30DFC)을 작은 루틴으로 돌린다**:
#   이름 포인터가 긴꼴 표 칸이면 **칸의 마지막 바이트(15번 — 이름 널 뒤라 워프·검사기가 안 본다)** 에 적힌 위치에 전각 공백을 끼운 사본을
#   함수 프레임 앞 32B(쓰이지 않는다)에 만들고, 이름 포인터(r9)·r4 를 그 사본으로 돌려 원래 strlen 으로 넘어간다. 아니면(헤더 이름 등) 그대로 넘긴다.
BANNER_HOOKS = {  # 파일 → 종류 → (풀 리터럴 파일 오프셋, 원래 가리키던 주소)
    "/ED.BIN": dict(strlen=(0x52DE4, 0x06095DB8), draw=(0x52DEC, 0x0607D160)),
    "/ED2.BIN": dict(strlen=(0x30DFC, 0x0607B340), draw=(0x30E04, 0x06064554)),
}
BANNER_HOOK_ROWS = {  # 호출부 표 — ED1 은 호출부 리터럴(전용 표 포인터)을 따라 읽고, ED2 는 긴꼴 표 자리(제자리)
    "/ED.BIN": dict(deref=0x060837E8, plus=14, stride=14, n=48),
    "/ED2.BIN": dict(abs=0x06091CF2, stride=16, n=36),
}
ED2_LONG_TBL = 0x06091CF2  # 긴꼴 표 시작(= 호출부 리터럴 0x06091CD2 + 0x20)
ED2_LONG_N = 36


def _asm(ops, lits):
    """아주 작은 SH-2 어셈블러 — ops: ("w",값) · ("label",이름) · ("br",옵코드,라벨) · ("lit",이름,레지스터) · ("bsr",) · ("data",이름) ; lits: {이름: 16비트}.
    ⚠ 위치 독립이어야 한다(놓일 주소는 풀이 정한다, 짝수만 보장) — 분기는 상대, 상수는 mov.w 즉치. → (바이트, {라벨: 오프셋})"""
    L, pos = {}, 0
    for o in ops:
        if o[0] == "label":
            L[o[1]] = pos
        else:
            pos += 2
    body = pos
    litat = {k: body + 2 * i for i, k in enumerate(lits)}
    out, pos = bytearray(), 0
    for o in ops:
        if o[0] == "label":
            continue
        if o[0] == "w":
            out += o[1].to_bytes(2, "big")
        elif o[0] == "br":
            d = (L[o[2]] - (pos + 4)) // 2
            assert -128 <= d < 128 if o[1] != 0xA0 else -2048 <= d < 2048
            out += (((o[1] << 8) | (d & 0xFF)) if o[1] != 0xA0 else (0xA000 | (d & 0xFFF))).to_bytes(2, "big")
        elif o[0] == "lit":
            d = (litat[o[1]] - (pos + 4)) // 2
            assert 0 <= d < 256
            out += ((0x9000 | (o[2] << 8)) | d).to_bytes(2, "big")
        else:
            raise AssertionError(o)
        pos += 2
    for v in lits.values():
        out += (v & 0xFFFF).to_bytes(2, "big")
    return bytes(out), L


def _hi_lo(v):
    """mov.w 부호 확장 → (상위 16, 하위 16) — 하위가 음수가 되면 상위를 1 올린다."""
    hi = (v + 0x8000) >> 16
    return hi, v - (hi << 16)


def banner_hook_codes(path, data):
    """배너 이름 끼움·가운데 보정 루틴 둘 → (`strlen` 자리 루틴 + 칸별 [끼울 위치, x 보정] 표, `draw` 자리 루틴).

    그리기 함수(ED1 0x0607AD60 · ED2 0x06058D78)의 프레임(r14, 앞 32B 는 안 쓰인다)을 쓴다 — r14+31 = x 보정 바이트, r14+0.. = 끼운 이름 사본.
    ① strlen 루틴: 이름 포인터(r4)가 호출부 표 칸이면 그 칸의 [위치, 보정]을 읽어 보정을 r14+31 에 두고, 위치가 있으면 반각 공백(1B)을 끼운 사본으로 r9·r4 를 돌린 뒤 원래 strlen 으로.
    ② draw 루틴: x(r4) 에 r14+31 을 더해 원래 그리기로. 표 밖 이름(씬 헤더 등)은 보정 0 · 사본 없음."""
    cfg = BANNER_HOOK_ROWS[path]
    s_lit, s_orig = BANNER_HOOKS[path]["strlen"]
    _d_lit, d_orig = BANNER_HOOKS[path]["draw"]
    ops, lits = [], {}

    def w(x):
        ops.append(("w", x))

    def label(n):
        ops.append(("label", n))

    def br(op, n):
        ops.append(("br", op, n))

    def litw(r, n, v):
        ops.append(("lit", n, r))
        lits[n] = v & 0xFFFF

    w(0x61E3)  # mov r14,r1
    w(0x711F)  # add #31,r1
    w(0xE000)  # mov #0,r0
    w(0x2100)  # mov.b r0,@r1      보정 0 으로 시작
    w(0x072A)  # sts pr,r7
    w(0xB000)  # bsr L0 (바로 다음 — pr = L0)
    w(0x0009)  # nop
    label("L0")
    w(0x032A)  # sts pr,r3         r3 = L0 (위치 독립 기준)
    w(0x472A)  # lds r7,pr
    base = cfg.get("abs") or cfg["deref"]
    hi, lo = _hi_lo(base)
    litw(1, "TH", hi)
    w(0x4128)  # shll16 r1
    litw(2, "TL", lo)
    w(0x312C)  # add r2,r1
    if "deref" in cfg:
        w(0x6112)  # mov.l @r1,r1     호출부 리터럴(전용 표 포인터)
        w(0x7100 | cfg["plus"])  # add #plus,r1   칸 앞 더미를 건너 표 시작
    w(0x6243)  # mov r4,r2
    w(0x3218)  # sub r1,r2         r2 = r4 − 표
    litw(5, "LIM", cfg["n"] * cfg["stride"])
    w(0x3252)  # cmp/hs r5,r2
    br(0x89, "PASS")  # bt (표 밖)
    w(0xE600)  # mov #0,r6
    w(0xE500 | cfg["stride"])  # mov #stride,r5
    label("LP")
    w(0x3252)  # cmp/hs r5,r2
    br(0x8B, "DONE")  # bf
    w(0x3258)  # sub r5,r2
    w(0x7601)  # add #1,r6
    br(0xA0, "LP")  # bra LP
    w(0x0009)  # nop
    label("DONE")
    w(0x2228)  # tst r2,r2
    br(0x8B, "PASS")  # bf (칸 시작이 아니면 그대로)
    litw(1, "DOFF", 0)  # 자리표 — 아래서 채운다(데이터 오프셋 − L0)
    w(0x313C)  # add r3,r1         r1 = 데이터 표
    w(0x6063)  # mov r6,r0
    w(0x4000)  # shll r0           2·색인
    w(0x021C)  # mov.b @(r0,r1),r2 끼울 위치
    w(0x7001)  # add #1,r0
    w(0x001C)  # mov.b @(r0,r1),r0 x 보정
    w(0x61E3)  # mov r14,r1
    w(0x711F)  # add #31,r1
    w(0x2100)  # mov.b r0,@r1
    w(0x2228)  # tst r2,r2
    br(0x89, "PASS")  # bt (끼움 없음)
    w(0x6323)  # mov r2,r3
    w(0x65E3)  # mov r14,r5
    label("L1")
    w(0x6244)  # mov.b @r4+,r2
    w(0x2520)  # mov.b r2,@r5
    w(0x7501)  # add #1,r5
    w(0x4310)  # dt r3
    br(0x8B, "L1")  # bf
    w(0xE220)  # mov #0x20,r2      반각 공백 1B
    w(0x2520)
    w(0x7501)
    label("L2")
    w(0x6244)
    w(0x2520)
    w(0x7501)
    w(0x2228)  # tst r2,r2
    br(0x8B, "L2")  # bf
    w(0x69E3)  # mov r14,r9
    w(0x64E3)  # mov r14,r4
    label("PASS")
    hi, lo = _hi_lo(s_orig)
    litw(1, "SH", hi)
    w(0x4128)
    litw(2, "SL", lo)
    w(0x312C)
    w(0x412B)  # jmp @r1
    w(0x0009)  # nop
    # DOFF 확정: 데이터 = 코드·상수 바로 뒤. L0 오프셋은 11번째 슬롯 직후(첫 일곱 + 라벨).
    code, L = _asm(ops, lits)
    dat_off = len(code)
    doff = dat_off - L["L0"]
    lits["DOFF"] = doff
    code, L = _asm(ops, lits)
    assert len(code) == dat_off and len(data) == 2 * cfg["n"]
    a = code + bytes(data)
    # ② draw
    ops2, lits2 = [], {}
    for x in (0x61E3, 0x711F, 0x6010, 0x340C):  # mov r14,r1 · add #31,r1 · mov.b @r1,r0 · add r0,r4
        ops2.append(("w", x))
    hi, lo = _hi_lo(d_orig)
    ops2 += [("lit", "H", 1), ("w", 0x4128), ("lit", "L", 2), ("w", 0x312C), ("w", 0x412B), ("w", 0x0009)]
    lits2 = {"H": hi, "L": lo}
    b, _ = _asm(ops2, lits2)
    return a, b


def ed2_banner_space_pos(rs):
    """긴꼴 표 칸마다 끼울 바이트 위치(0 = 없음) — 정본 일반 꼴(띄움)에서 반각 공백의 자리. → {색인: 위치}"""
    out = {}
    for k, n, i, _at, _st, jp, kr in rs:
        if k != "ED2" or n != "지명 긴꼴" or not kr:
            continue
        nm = banner_name(jp.strip(WIDE_SP + " "), kr.strip(WIDE_SP + " "), "ed2")
        cs = [c for c, ch in enumerate(nm) if ch == " "]
        assert len(cs) <= 1, (i, nm)
        out[i] = 2 * cs[0] if cs else 0  # 공백 앞은 전부 전각(2B)
    return out


def banner_dx():
    """배너 x 보정(칸별 −1/0/+1px) — 실화면 측정(`ss_banner_call.py --write-dx`)으로 만든 정본 `script/banner_dx.json`. 없으면 0."""
    p = os.path.join(common.GAME_DIR, "script", "banner_dx.json")
    if not os.path.exists(p):
        return {"ED1": [0] * 48, "ED2": [0] * 36}
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    assert len(d["ED1"]) == 48 and len(d["ED2"]) == 36 and all(-6 <= x <= 6 for x in d["ED1"] + d["ED2"])
    return d


def banner_hook_blobs(rs):
    """`[(경로, 바이트, [리터럴 파일 오프셋], 0)]` — 경로마다 strlen 루틴(+칸별 표)·draw 루틴."""
    dx = banner_dx()
    pos = ed2_banner_space_pos(rs)
    out = []
    for path, key, n in (("/ED.BIN", "ED1", 48), ("/ED2.BIN", "ED2", 36)):
        assert common.extract(path)[BANNER_HOOKS[path]["strlen"][0] :][:4] == BANNER_HOOKS[path]["strlen"][1].to_bytes(4, "big")
        assert common.extract(path)[BANNER_HOOKS[path]["draw"][0] :][:4] == BANNER_HOOKS[path]["draw"][1].to_bytes(4, "big")
        data = bytearray()
        for i in range(n):
            data += bytes([(pos.get(i, 0) if key == "ED2" else 0) & 0xFF, dx[key][i] & 0xFF])
        a, b = banner_hook_codes(path, bytes(data))
        out.append((path, a, [BANNER_HOOKS[path]["strlen"][0]], 0))
        out.append((path, b, [BANNER_HOOKS[path]["draw"][0]], 0))
    return out


def banner_name(jp, kr, title):
    """배너 이름 — 정본 일반 꼴(띄움, `canon.place_general`) → 반각 공백. 칸 폭이 모자라면 호출부가 붙인 꼴로 물러선다."""
    g = shared_canon.place_general(jp, title)
    assert g, f"정본 place_general 에 없는 지명: {jp!r}"
    return g  # 띄움은 반각 공백(마스터 11-09 「입장배너도 반각공백」) — 배너 전용 표·끼움 루틴만 쓴다(HUD·워프 꼴과 무관)


def banner_extra(rs, plan):
    """`sys_pack` 에 얹을 배너 표 → `[(경로, 표 바이트, [리터럴 파일 오프셋], 앞 더미 바이트)]` — 포인터 값 = 표 시작 − 더미(그 앞 칸은 읽히지 않는다)."""
    out = []
    for path, c in BANNER_TABLES.items():
        rows_ = sorted((i, jp, kr) for k, n, i, _at, _st, jp, kr in rs if k == c["key"] and n == c["tab"])
        blob = bytearray()
        for i, jp, kr in rows_:
            assert i * c["stride"] == len(blob), f"{path} 배너 표 {i}번 칸이 건너뛰었다"
            if not kr:
                blob += b"\x00" * c["stride"]
                continue
            nm = banner_name(jp.strip(WIDE_SP + " "), kr.strip(WIDE_SP + " "), c["title"])
            try:
                blob += encode(nm, c["stride"], plan)
            except AssertionError:
                nm = kr.strip(WIDE_SP + " ")  # 칸에 안 들면 붙인 꼴
                blob += encode(nm, c["stride"], plan)
        out.append((path, bytes(blob), list(c["ptrs"]), c["lead"]))
    return out + banner_hook_blobs(rs)


# 🔴 **ED2 배너 시작 x**(마스터 11-08 「딱 가운데가 아니면 왼쪽 여백을 더 짧게」, 번역 규칙 2-8) — ED2 도 같은 그리기 함수(`ED2.BIN` 0x06058D78, ED1 의 0x0607AD60 과
#   같은 꼴)이고 이름이 길이로 가운데 놓이지만 글자 잉크가 오른쪽으로 1px 치우쳐(실화면 호출 측정 — 긴꼴 30곳 좌 = 우+1·3곳 좌 = 우) **왼쪽이 오른쪽보다 1px 크다**.
#   시작 x 를 ED1 과 같게 2px 앞당긴다(63→61): 좌 14·우 17 꼴, 왼 ≤ 오 · 차 3px(`tools/ss_banner_call.py` 로 재 본다).
ED2_BANNER_XBASE_OFF = 0x30DE3  # `/ED2.BIN` 파일 오프셋 — `mov #63,r4`(RAM 0x06058DE2)의 즉치 바이트


def patch_banner_field(f, files):
    lba2, size2 = files["/ED2.BIN"]
    common.write_at(
        f,
        lba2,
        size2,
        ED2_BANNER_XBASE_OFF,
        bytes([ED2_BANNER_X_NEW]),
        expect=bytes([63]),
        label=f"ED2.BIN 입장배너 시작x(63→{ED2_BANNER_X_NEW}px)",
    )
    lba, size = files["/ED.BIN"]
    # 🔴 HUD 지명 상자(`0x0607968C`)의 왼쪽 패딩 `add #16,r1`(RAM 0x060796A0) → 17. 왼쪽 반각 칸 수 = (폭 − 길이)/2 를 0 쪽으로 버리는데, 접미 앞 반각 공백(마스터 11-09)으로
    #   길이가 홀수가 되면 한 칸(6px) 모자라게 놓여 좌−우 −9px 였다. 폭 17 은 **홀수 길이만** 바꾼다(짝수 길이는 (17−2k)/2 = (16−2k)/2 — 지명 칸은 전각 짝수라 안 변한다).
    #   오른쪽 패딩(`add #16,r2`)은 그대로라 합은 16 칸으로 같다. 좌−우 −9 → +3(한 칸 = 12px 이동, 최근접).
    common.write_at(
        f,
        lba,
        size,
        HUD_FIELD_OFF,
        bytes([HUD_FIELD_NEW]),
        expect=bytes([16]),
        label=f"ED.BIN HUD 지명 왼쪽 패딩 폭(16→{HUD_FIELD_NEW}, 홀수 길이용)",
    )
    common.write_at(
        f,
        lba,
        size,
        BANNER_FIELD_OFF,
        bytes([BANNER_FIELD_NEW]),
        expect=bytes([12]),
        label=f"ED.BIN 입장배너 필드폭(12→{BANNER_FIELD_NEW})",
    )
    common.write_at(
        f,
        lba,
        size,
        BANNER_XBASE_OFF,
        bytes([BANNER_X_NEW]),
        expect=bytes([63]),
        label=f"ED.BIN 입장배너 시작x(63→{BANNER_X_NEW}px)",
    )
    common.write_at(
        f,
        lba,
        size,
        BANNER_YBASE_OFF,
        bytes([62]),
        expect=bytes([61]),
        label="ED.BIN 입장배너 시작y(61→62px)",
    )


def _fit_place(kr, room, suffixed, where):
    """지명 한 칸 → 칸(`room` = 널 포함 바이트)에 드는 꼴.

    `suffixed`(「…부근」 표)면 뒤에 접미가 붙으므로 끝에 **반각 공백**을 하나 붙인다(마스터 11-09 「방향접미 앞 공백 반각」 —
    종전 전각). 안 들면 붙여 쓴다. 홀수 길이가 되는 칸은 이 접미 표뿐이다(`check_place_fields` 가 이 한 칸만 허용한다).
    """
    if suffixed and rec_len(kr + " ") <= room:
        return kr + " "
    return kr


def rows():
    """`(파일키, 표이름, 색인, 오프셋, stride, JP, KR|None)` — 원본에서 읽어 정본과 짝짓는다."""
    _cards, pad_to_jp, _msgs = load_canon()
    out = []
    for key, path in dump_ui.FILES.items():
        buf = common.extract(path)
        col = 0 if key == "ED" else 1
        for name, ed, ed2, stride, n, n2 in dump_ui.TABLES:
            off = (ed, ed2)[col]
            if off is None:
                continue
            cnt = n2 if (col == 1 and n2) else n
            table_rows = list(dump_ui.read_table(buf, off, stride, cnt))
            canon = [(jp_raw, _ui_label(jp_raw, name)) for jp_raw, _at, _sl in table_rows]
            # 🔴 값이 붙는 표는 **JP 라벨 폭에 맞춰 채운다**(정본 `pad_to_jp` 주석).
            #   한글이 더 넓은 행이 있으면 표 전체를 그만큼 함께 민다.
            shift = 0
            if name in pad_to_jp:
                shift = max((_half(k) - _half(j) for j, k in canon[:cnt] if k), default=0)
                shift = max(shift, 0)
            for i, (jp, at, _slack) in enumerate(table_rows):
                kr = canon[i][1]
                if kr and name in pad_to_jp:
                    kr = _pad_to(kr, _half(jp) + shift)
                out.append((key, name, i, at, stride, jp, kr))
        # ── 지명 — 정본이 `shared/glossary` 다(위 GLOSSARY_TABLES 주석)
        for name, ed, ed2, stride, n, n2, cat in dump_ui.GLOSSARY_TABLES:
            off = (ed, ed2)[col]
            if off is None:
                continue
            cnt = n2 if (col == 1 and n2) else n
            for i, (jp, at, _slack) in enumerate(dump_ui.read_table(buf, off, stride, cnt)):
                if not jp:  # 빈 칸 — 원본이 안 쓰는 자리다
                    continue
                if _internal_key(jp):
                    continue  # 반각 내부 키 — 화면에 안 나온다(아래 헬퍼 주석)
                kr = _route_name(jp) if "\uff5e" in jp else None  # 길 이름 「A～B」 — HUD 표시명(씬 정본이 이미 번역한 같은 문자열)
                kr = kr or _place_lookup(jp, cat)
                # 🔴 조용히 건너뛰지 않는다 — 한 칸만 일본어로 남으면 화면에서 바로 튄다.
                assert kr, f"{key}/{name}[{i}] 0x{at:06x}: 정본에 없는 {cat} {jp!r}"
                kr = _fit_place(kr, stride, name == SUFFIXED_TABLE, f"{key}/{name}")
                out.append((key, name, i, at, stride, jp, kr))
        # ── 파티 기본 이름 — 지명과 같은 수법(정본은 glossary), 자리만 손으로 적었다
        for k, at, fl in dump_ui.PERSON_SLOTS:
            if k != key:
                continue
            rec = buf[at : at + fl]
            z = rec.find(b"\x00")
            assert z > 0, f"{key} 0x{at:06x}: 인명 자리에 널이 없다"
            jp = rec[:z].decode("cp932")
            from names import person_table

            kr = person_table().get(jp)
            assert kr, f"{key} 0x{at:06x}: 정본에 없는 인명 {jp!r}"
            # ⚠ 필드 **마지막 바이트가 `09`** 인 꼴이 있다(뜻은 모른다 — 씬 헤더도 같다).
            #   그 자리는 남겨야 하므로 쓰는 폭을 한 칸 줄인다. 널 패딩으로 덮으면
            #   원본이 무엇을 하려던 건지 모른 채 없애는 셈이다.
            w = fl - 1 if rec[fl - 1] == 9 else fl
            out.append((key, "파티 이름", at, at, w, jp, kr))
    return out


# ── 반각 도트 글리프 — 저장 바이트가 막히는 지명 전용(PS1 수법 이식) ──────────────────
# 🔴 **마스터 지시(2026-10-05)**: 「새턴도 ps1과 똑같이 도트로 처리하면 돼. ps1에서
#   도트작업했던 모든것들은 새턴에도 동일 적용이야」. 狼の口 정본이 「늑대입」→「늑대의입」
#   (4글자·8B)으로 바뀌면서 씬 지명 헤더(아래 `scn_header`) 11곳이 막혔다(ED1SCN27 2 ·
#   ED2SCN33 9) — 자리가 8B(널 포함 본문 7B)뿐인데 헤더는 4바이트 정렬이라 칸을 못 늘린다
#   (헤더 바로 뒤가 SH-2 코드, 위 주석). HUD·배너·워프 표는 `glossary.lookup` 이 채우는
#   별도 자리라 넉넉해서 안 막힌다 — **씬 헤더만** 막힌다.
#
# PS1 은 `ps1-ed1+2/tools/patch_hangul_glyph_table.py` 에서 같은 류의 문제(8B 벽)를
# **저장 바이트를 2B/글자 → 1B/글자로 줄여서** 풀었다 — 전각 한글 대신 **반각 코드 하나하나에
# 그림 조각(6px)을 구워** 6글자를 6B 로 담는다(`HUD_GRID`, 마스터가 직접 찍은 36×11 도안).
# **그 도안은 정본이라 다시 그리거나 손보지 않고 그대로 가져온다** — 아래 `HUD_GRID` 는
# PS1 원본과 바이트까지 같다.
#
# 새턴도 **같은 지오메트리다**(2026-09-27 이번 세션이 라이브 RE 로 이미 확정해 둔 값,
# 「HUD 좁은 글꼴 조사」·「배너 정렬」 두 회차에 걸친 디스어셈블):
#   `0x0607D5D4`(반각/전각 판정, 표 없이 순수 산수) — `(c-32)∈[0,94)` 또는
#   `(c+95)&0xFF∈[0,62)`(=0xA1~0xDF) 면 반각. `0x0607D768`(반각 블리터)은 **표 참조 없이
#   `/11ASCII.FON` 을 코드값×11 로 직접 색인하는 고정 스트라이드 비트 블리터**다 — PS1 처럼
#   "주소가 단조가 아니다" 같은 복잡함이 없다. 커서 전진은 **반각이면 무조건 6px**(여러
#   문맥에서 라이브로 반복 실측, 예외 없음). ⇒ PS1 의 8×11 비트맵(열 6·7 은 항상 0)·6px
#   전진 규약과 **구조가 완전히 같아서, 그 비트맵을 그대로 6px씩 잘라 쓸 수 있다.**
#
# PS1 이 쓴 정확한 코드(0xC1·0xC2·0xC3·0xC4·0xCB·0xCE)는 새턴에서 전부 **이미 쓰는 중**이다
# (반각 가타카나 ﾁﾂﾃﾄﾋﾎ — 원본 UI·대사에 남아 있다). 그래서 새턴 전용으로 빈 칸을 새로
# 골랐다 — JP 원문 전량(`work/derived/scn_jp/*.json`·`ui_jp.json`·`title_jp.json`) + 우리
# KR 출력(`script/*.json`) 을 전수 스캔해 0xA1~0xDF 63칸 중 **7칸이 완전히 비어 있음**을
# 확인했다(0xA1·0xA3·0xA4·0xA6·0xA9·0xD2·0xD4). 그중 0xA1·0xA3·0xA4 는 **원본 글리프조차
# 빈 칸**(00×11)이라 가장 안전하다. 6개만 쓰고 0xD4 는 다음에 반각 칸이 더 필요할 때 쓰도록
# 비워 둔다(PS1 의 0xCF 와 같은 관례).
SS_HUD_CODES = (0xA1, 0xA3, 0xA4, 0xA6, 0xA9, 0xD2)  # 왼→오, PS1 HUD_CODES 와 같은 순서

# PS1 `patch_hangul_glyph_table.HUD_GRID` 그대로(36×11, 6px 6조각) — **다듬지 않는다.**
HUD_GRID = (
    ".#.......####.#.#...##....#...##...#",
    ".#.......#....#.#..#..#...#..#..#..#",
    ".#.......#....#.#.#....#..#.#....#.#",
    ".######..#....#.#.#....#..#.#....#.#",
    ".........#....#.#..#..#...#..#..#..#",
    "########.#....###...##....#...##...#",
    ".........#....#.#.........#.........",
    ".######..#....#.#.........#..#.....#",
    "......#..#....#.#.#######.#..#######",
    "......#..####.#.#.........#..#.....#",
    "......#.......#.#.........#..#######",
)

# 🔴 **「사피아의호수」추가(마스터 지시 2026-10-05) — 첫 조사는 틀렸다.** 처음엔 「새턴에
#   빈 반각 코드가 9개뿐이라 11개가 필요한 SAPIA_GRID 는 못 넣는다」고 보고했는데, 관리자가
#   짚었다 — 그 조사가 **JP 원문 전체**를 "쓰는 중"으로 셌다. JP 원문은 거의 다 우리 KR
#   문안으로 **덮인다**(번역이 곧 그 자리를 비운다) — 화면에 실제로 남는 반각 사용은 최종
#   KR 출력(+남은 일본어 2종, 전부 도달 불가한 개발자 화면 한자라 반각과 무관)뿐이다.
#   **그 기준으로 다시 세니 0xA1~0xDF 63칸 중 실사용은 `･`(0xA5) 하나뿐**이었다 — 56칸이
#   비어 있다(HUD 의 6칸을 빼도 50칸). 11개는 충분하다.
SS_SAPIA_CODES = (0xA2, 0xA7, 0xA8, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1)

# PS1 `patch_hangul_glyph_table.SAPIA_GRID` 그대로(66×11, 6px 11조각) — **다듬지 않는다.**
# PS1 자리(ED2SCN10 필드 HUD)와 같은 류: `サピアの湖`("사피아호수", 5음절) 의 씬 헤더가
# 12B(본문 11B)인데, PS1 과 자모를 맞춘 「사피아의호수」(6음절·12B)는 전각으로 못 들어간다
# (12B+NUL=13B > 12B) — HUD_GRID 와 같은 이유로 도트가 **필수**다(관리자 확인: SAPIA 11조각은
# HUD 조각과도, 자기들끼리도 겹치는 픽셀이 없다).
SAPIA_GRID = (
    "...#....#..#######.#...###...#....###....#....#####.........#.....",
    "...#....#...#...#..#..#...#..#...#...#...#..................#.....",
    "...#....#...#...#..#.#.....#.#..#.....#..#.###########....##.##...",
    "...#....#...#...#..#.#.....#.#..#.....#..#..............##.....##.",
    "...#....#...#...#..#.#.....#.#...#...#...#...#######..............",
    "..#.#...##..#...#..#.#.....#.##...###....#..#.......#..###########",
    "..#.#...#...#...#..#.#.....#.#...........#..#.......#.......#.....",
    ".#...#..#...#...#..#.#.....#.#...........#...#######........#.....",
    ".#...#..#...#...#..#..#...#..#..########.#......#...........#.....",
    "#.....#.#..#######.#...###...#...........#.###########......#.....",
    "........#..........#.........#...........#..................#.....",
)

# {이름: (그리드, 코드순서)} — 둘 다 6px 조각 그리드다. 추가할 땐 여기 한 줄.
DOTART_GRIDS = {
    "hud": (HUD_GRID, SS_HUD_CODES),
    "sapia": (SAPIA_GRID, SS_SAPIA_CODES),
}


def _pack_dotart_glyph(row_bits):
    """11행 × 6px(`#`/`.`) 문자열 → 11B(행당 1B, MSB=왼쪽, 열 6·7은 항상 0)."""
    out = bytearray(11)
    for r, row in enumerate(row_bits):
        b = 0
        for c, ch in enumerate(row):
            if ch == "#":
                b |= 1 << (7 - c)
        out[r] = b
    return bytes(out)


def ellipsis_glyph():
    """`…` 11KANJI 글리프 — 점 셋을 **한국식 바닥**(글자 아랫줄, 온점과 같은 행)에 둔다.

    🔴 마스터 2026-10-08: 「…」는 전각 한 글자, 점 셋은 한국식 바닥 — 일본식 가운데 점은 안 된다(전 기종·전 게임).
       원본·Galmuri11 의 `…` 는 가운데 줄(5행)에 있다 → 같은 점 모양을 온점의 행(10행)으로 내린다.
    """
    g, miss = convert_chars("…")
    assert not miss, "Galmuri11 에 …가 없다"
    rows = [g["…"][r * 2 : r * 2 + 2] for r in range(11)]
    assert sum(1 for r in rows if any(r)) == 1, "…의 점이 한 행이 아니다 — 모양이 바뀌었다"
    src = next(i for i, r in enumerate(rows) if any(r))
    # 🔴 마스터 11-15 「…의 점을 그 기종 마침표와 같은 모양·크기로」(규칙 1-3) — 반각 `.`(bake_ascii)은 1×2px 점이 8·9행(원판 ！ 점과 같다).
    #    옛 꼴(점 1px · 10행)은 마침표보다 작고 한 줄 낮았다 → 같은 점 열마다 8·9행에 세로 2px 로 놓는다(위치는 열 그대로).
    # 🔴 마스터 11-16 「원판 ?! 점에 맞춰 마침표를」 — 점 하나는 마침표와 같은 1×2px(원판 ！ 점), 열은 원래 「…」 그대로.
    dots = rows[src]
    rows = [b"\x00\x00"] * 11
    rows[8] = rows[9] = dots
    return b"".join(rows)


def bake_dotart_glyphs():
    """{코드: 11B 글리프} — `DOTART_GRIDS` 의 각 그리드를 6px씩 잘라 해당 코드에 붙인다."""
    out = {}
    for name, (grid, codes) in DOTART_GRIDS.items():
        assert len(grid) == 11, f"{name} 행 수 {len(grid)} != 11"
        width = len(codes) * 6
        for r, row in enumerate(grid):
            assert len(row) == width, f"{name} {r}행 길이 {len(row)} != {width}"
        for i, code in enumerate(codes):
            chunk = [row[i * 6 : i * 6 + 6] for row in grid]
            out[code] = _pack_dotart_glyph(chunk)
    return out


# {우리 KR 지명: 도트 바이트열} — **씬 헤더 전용** 오버라이드(`scn_encode`). HUD·배너·워프
# 표는 자리가 넉넉해 평범한 전각 인코딩 그대로 간다(`glossary.lookup`). 짧은 꼴(「늑대입」)로
# 되돌리는 예외는 두지 않는다(마스터 지시 2026-10-05).
DOTART_PLACES = {
    "늑대의입": bytes(SS_HUD_CODES),
    "사피아의호수": bytes(SS_SAPIA_CODES),
}



def dotart_claimed_codes():
    """`DOTART_PLACES`/`DOTART_GRIDS` 가 실제로 점유하는 반각 코드 전부."""
    return {c for _g, codes in DOTART_GRIDS.values() for c in codes}


def dotart_text_codes(rs, scn, ntabs, sysm, cards_msgs_kr):
    """**최종 화면에 실제로 나가는 글** 이 쓰는 반각 코드 — 도트가 훔칠 수 없는 칸.

    🔴 JP 원문 전체를 센 첫 조사는 틀렸다(관리자 지적 2026-10-05) — 원문은 거의 다 KR 로
      덮이므로 "원문이 쓴다"가 "화면에 남는다"가 아니다. 여기는 **KR 출력 쪽만** 센다
      (한글 슬롯은 늘 전각 2B 라 반각 코드를 쓰지 않으므로 애초에 안 걸린다 — 그 밖의
      글자만 `cp932` 로 재 1B 면 반각).
    """
    used = set()

    def mark(kr):
        if not kr:
            return
        for ch in kr:
            if "가" <= ch <= "힣":
                continue
            try:
                b = ch.encode("cp932")
            except UnicodeEncodeError:
                continue
            if len(b) == 1 and (0x21 <= b[0] <= 0x7E or 0xA1 <= b[0] <= 0xDF):
                used.add(b[0])

    for _k, _n, _i, _at, _s, _jp, kr in rs:
        mark(kr)
    for _p, _l, _s, _at, _fl, jp, kr, _t in scn:
        mark(kr)
    for t in ntabs:
        for _at, _jp, kr, _ptrs in t["recs"]:
            mark(kr)
    for _p, _l, _s, _at, _sp, _pre, kr, _ptrs, _jp in sysm:
        mark(kr)
    for kr in cards_msgs_kr:
        mark(kr)
    return used


def check_dotart_codes(rs, scn, ntabs, sysm):
    """🔴 **게이트** — 도트가 점유한 코드가 실제 화면 글과 겹치면 그 글이 깨진다(관리자
    요청 2026-10-05, 「이식할 때 누출 검사를 같이 건다」). `DOTART_PLACES` 를 늘릴 때마다
    돈다."""
    cards, _pj, msgs = load_canon()
    cards_msgs_kr = [e[-1] for e in cards] + list(msgs.values())
    text_codes = dotart_text_codes(rs, scn, ntabs, sysm, cards_msgs_kr)
    clash = dotart_claimed_codes() & text_codes
    assert not clash, f"도트 코드가 실제 화면 글과 겹친다: {sorted(hex(c) for c in clash)}"


# ── 씬 파일 지명 헤더 ────────────────────────────────────────────────────────
# 🔴 **HUD 우하단 지명은 `ED.BIN` 의 표가 아니라 여기서 온다**(2026-08-24 실측 — 표를
#   넣었는데 화면은 그대로 일본어였다). 씬 파일은 `[지명 헤더][SH-2 코드][텍스트]` 가
#   지역마다 반복되고, 그 헤더가 화면에 뜬다.
#
# 헤더 자리는 **SH-2 프롤로그**로 잡는다 — 헤더 바로 뒤가 늘 `2F 86 2F 96 2F A6`
# (`MOV.L R8/R9/R10,@-R15`)이다. 다만 그 프롤로그는 **평범한 함수에도 있으므로**
# 앞 12~16B 가 지명 정본에 있을 때만 헤더로 친다. 실측: 프롤로그 1,473곳 중 499곳.
# ⚠ 그 조건을 빼면 대사 꼬리(`なさい。%c`)와 포인터 표가 줄줄이 걸린다.
# ⚠ 인명(`ロー`·`ゲイル`)도 프롤로그 앞에 온다 — **place 범주로만** 찾아 갈라낸다.
#
# 필드는 **4바이트 정렬**이다(이름 + 널 하나 이상 + 패딩). 마지막 바이트가 `09` 인 꼴이
# 있는데 뜻은 모른다 — **원본 값을 그대로 남긴다.**
# ⚠ **`patch_scn.SCN_RE` 와 이름은 같고 뜻이 다르다** — 저쪽은 본체 둘과 `ED2MON*` 까지
#   품는다(「씬 문안이 있는 파일 전부」). 여기는 **씬 파일만** 이다. 4-D 가 말하는 「같은
#   지식이 두 곳」의 반대 꼴 — **다른 지식이 같은 이름**이라 그대로 갖다 쓰면 조용히 틀린다.
SCN_RE = re.compile(r"^/BIN/(ED1SCN|ED2SCN)\d+\.BIN$")
PROLOGUE = bytes.fromhex("2f862f962fa6")


def scn_header(d, i, places):
    """프롤로그 i 앞의 지명 헤더 → `(시작, 필드길이, JP, KR)`. 아니면 None."""
    for fl in (4, 8, 12, 16, 20, 24):
        s = i - fl
        if s < 0:
            return None
        h = d[s:i]
        z = h.find(b"\x00")
        if z <= 0:
            continue
        if any(x != 0 for x in h[z : fl - 1]) or h[fl - 1] not in (0, 9):
            continue
        try:
            jp = h[:z].decode("cp932")
        except UnicodeDecodeError:
            continue
        kr = places.get(jp)
        if kr:
            # 🔴 널이 반드시 남아야 한다 — 꼬리 바이트(`09`)가 끝을 차지하므로 본문은 fl-2 까지.
            return s, fl, jp, _fit_place(kr, fl - 1, False, "씬 지명 헤더")
    return None


def scn_rows(mm):
    """`[(파일, lba, size, 시작, 필드길이, JP, KR, 꼬리바이트)]`."""
    places = table("place", "eiyuu")
    out = []
    for path, lba, size in common.iso_files(mm):
        if not SCN_RE.match(path):
            continue
        d = common.read_extent(mm, lba, size)
        st = 0
        while (i := d.find(PROLOGUE, st)) >= 0:
            st = i + 2
            r = scn_header(d, i, places)
            if r:
                s, fl, jp, kr = r
                out.append((path, lba, size, s, fl, jp, kr, d[s + fl - 1]))
    return out


# ── 챕터 카드 ────────────────────────────────────────────────────────────────
# 화면 아래 상시 표시되는 장 이름이자 장을 끝낼 때 뜨는 카드다 — **같은 문자열 하나**다
# (디스크 전량에 사본이 없다). 꼴은 `\t + 여백 + 第N章　제목 + \n\n + 여백 + 完 + %c`.
# 🔴 자리를 손으로 안 적는다 — `章`·`完` 을 가진 문자열을 훑어 **JP 제목으로** 짝짓는다.
# ⚠ 가운데맞춤은 원본이 **여백을 손으로 넣어** 한다. 우리 문안은 폭이 달라지므로 그만큼
#   여백을 다시 잰다(반각 단위: 전각 1자 = 2). 안 하면 카드가 한쪽으로 쏠린다.
CARD_RE = ("章", "完")


def _half(t):
    """반각 단위 폭 — 전각 2, 반각 1. ⚠ 한글은 cp932 로 인코딩이 안 되니 전각으로 센다."""
    n = 0
    for c in t:
        try:
            n += len(c.encode("cp932"))
        except UnicodeEncodeError:
            n += 2
    return n


CARD_END_SPACES = 14  # 「끝」 앞 반각 공백 수 — 커서(▽) 가운데에 가장 가까운 자리(`_card_text` 주석)


def _card_text(jp, ch, title):
    """원본 꼴을 따라 우리 카드 문자열을 짓는다 — 여백만 다시 잰다."""
    head, _, rest = jp.partition("\n")
    lead = len(head) - len(head.lstrip("\t "))
    pre = head[:lead]  # `\t` 와 앞 여백
    tab = ""  # 🔴 선두 `\t` 는 안 쓴다 — 탭 카드는 코드가 시작+1 을 가리켜 탭이 죽은 1B 였는데, 그 리터럴을 시작으로 돌려(`card_ptr_fixes`) 그 자리를 카드 글 첫 바이트로 쓴다
    jp_body = head[lead:]
    kr_body = f"{ch}　{title}"
    pad1 = max(0, lead + (_half(jp_body) - _half(kr_body)) // 2 - (1 if pre.startswith(chr(9)) else 0))  # 원문 앞 여백 = 탭 1B + 반각 공백들 — 탭 자리까지 공백으로 센다 ⇒ 같은 위치
    # 🔴 「끝」은 아래 커서(▽)에 맞춘다(마스터 11-09 「장끝카드는 끝을 커서에 맞추면 될거같네」) — 원문 완(完) 줄의 공백 수(13·14 로 갈렸다)가 아니라 **커서 기준 고정 수**다.
    #   실화면(대화창 경로로 카드 번호를 띄워 잼): 커서 잉크 중심 x=108(ED1·ED2 같다), 반각 공백 6px 이라 14칸이면 끝 중심 110(+2px) · 13칸이면 104(−4px) — 최근접 14.
    return f"{tab}{' ' * pad1}{kr_body}\n\n{' ' * CARD_END_SPACES}끝%c"


def fit_card(card, limit):
    """카드 문자열이 **원문 칸(JP 바이트)** 을 넘으면 덜어 낸다 — 메뉴 경로(`card_rows`)와 씬 경로(`typeset_scn._chapter_card`)가 **같은 결과**를 내야 한다(둘이 갈리면
    같은 칸에 두 글이 겹쳐 구조 대조가 「칸 뒤 채움에 설명 안 되는 바이트」로 운다, 11-09).

    🔴 「끝」 줄을 커서 기준 14칸으로 고정하면(`CARD_END_SPACES`) 원문 칸을 1B 넘는 카드(종장)가 있다 — 첫 줄 가운데맞춤 여백에서 반각 한 칸씩 덜어 칸 안에 넣는다(제목이 반 칸
    왼쪽으로 갈 뿐이다). ⚠ 선두 `\t` 는 못 덜어 낸다: 탭 있는 카드는 코드가 **탭 다음 바이트**를 가리키고(포인터 풀에 카드 시작 주소가 없다 — 제４·５장만 시작을 가리킨다) 탭 자리는 죽은 1B 다.
    그걸 지웠더니 포인터가 한 칸 밀려 구조 대조(`check_structure` 「칸 뒤 채움에 설명 안 되는 바이트」)가 울었다(11-09)."""

    def nbytes(t):
        return sum(2 if "\x80" <= c else 1 for c in t.replace("%c", "XX"))

    while nbytes(card) > limit:
        head = card.split("\n")[0]
        lead = len(head) - len(head.lstrip("\t"))  # 선두 탭은 건드리지 않는다
        k = head.find(" ", lead)
        if k < 0 or head[lead:].lstrip(" ") == head[lead:]:
            break  # 덜어 낼 첫 줄 여백이 없다
        card = card[:k] + card[k + 1 :]
    return card


def card_ptr_fixes(cards):
    """탭으로 시작하는 카드의 **포인터 리터럴을 시작(+0)으로 돌린다** → `[(경로, 리터럴 파일 오프셋, 옛 4B, 새 4B)]`.

    원판은 탭 카드(`\\t` 로 시작)를 시작+1(탭 다음)로 가리킨다 — 탭은 화면에 안 그려지는 죽은 1B 다(제４·５장만 시작을 가리킨다). 그 리터럴을 시작으로 옮기면 탭 자리를 카드 글
    첫 바이트(반각 공백)로 쓸 수 있다(`_card_text`) — 「끝」 줄을 커서 기준 14칸으로 맞추고도 원문 칸을 안 넘는다(종장). 리터럴은 카드마다 **정확히 하나**여야 한다(아니면 멈춘다)."""
    out = []
    for path, _lba, _size, at, _span, jp, _kr in cards:
        if not isinstance(jp, str) or not jp.startswith("\t"):  # 문구 행(`msgs`)은 앞 바이트열이라 거른다
            continue
        if path != "/ED.BIN":
            continue  # ED2 카드는 씬 경로(`patch_scn`)가 이주시켜 포인터를 새 사본으로 돌린다(최종 이미지 실측) — 여기서 안 건드린다
        base = ptr_base(path)
        orig = common.extract(path)
        old = (base + at + 1).to_bytes(4, "big")
        hits = [q for q in range(0, len(orig) - 3, 4) if orig[q : q + 4] == old]
        assert len(hits) == 1, f"{path} 0x{at:06x}: 탭 카드 포인터 리터럴이 하나가 아니다 {[hex(h) for h in hits]}"
        out.append((path, hits[0], old, (base + at).to_bytes(4, "big")))
    return out


def card_ptr_fix_offsets():
    """`{(경로, 리터럴 파일 오프셋)}` — 선언한 탭 카드 포인터 리터럴(`card_ptr_fixes`). 게이트(`check_ptr_align` · `check_stale_refs`)가 「일부러 돌린 곳」으로 안다."""
    f, mm = common.open_image()
    try:
        return {(path, q) for path, q, _o, _n in card_ptr_fixes(card_rows(mm, load_canon()[0]))}
    finally:
        mm.close()
        f.close()


def card_rows(mm, cards):
    """`[(파일, lba, size, 오프셋, 여유, JP, KR)]`."""
    want = {jp: (ch, ti) for jp, ch, ti in cards}
    out, seen = [], set()
    have = {p for p, _l, _s in common.iso_files(mm)}
    for path in list(dump_ui.FILES.values()) + [p for p in SYS_EXTRA_FILES if p in have]:
        lba, size = next((l, s) for p, l, s in common.iso_files(mm) if p == path)
        # ⚠ 파일을 늘렸으면 **늘어난 크기**를 들고 다닌다 — 뒤의 배치·되읽기가 이 값을 쓴다
        size = _tails().get(path, (0, size))[1] or size
        d = common.read_extent(mm, lba, size)
        i = 0
        while i < len(d):
            if d[i] == 0:
                i += 1
                continue
            j = i
            while j < len(d) and d[j] != 0:
                j += 1
            try:
                t = d[i:j].decode("cp932")
            except UnicodeDecodeError:
                i = j
                continue
            if all(k in t for k in CARD_RE):
                hit = next((jp for jp in want if jp in t), None)
                assert hit, f"{path} 0x{i:06x}: 정본에 없는 챕터 카드 {t!r}"
                nxt = j
                while nxt < len(d) and d[nxt] == 0:
                    nxt += 1
                seen.add(hit)
                kr_card = fit_card(_card_text(t, *want[hit]), nxt - i - 1)  # 칸 = 본문 + NUL + 뒤 0 패딩(`nxt - i`) — NUL 몫 1B 를 뺀다
                out.append((path, lba, size, i, nxt - i, t, kr_card))
            i = j
    # ⚠ 정본 열둘은 **장 목록**이다 — 문자열 카드는 열뿐이고 ED2 의 序章·終章 은 그림 판으로만
    #   있다(`patch_gfx_cards.py`). 그래서 「정본에 있는데 디스크에 없다」는 실패가 아니다.
    #   반대 방향(디스크에 있는데 정본에 없다)은 위에서 여전히 막는다 — 그쪽이 사고다.
    only_gfx = [jp for jp in want if jp not in seen]
    assert len(only_gfx) <= 2, f"문자열 카드가 너무 많이 빈다: {only_gfx}"
    return out


def msg_scan(mm, msgs):
    """SAVE/LOAD·본체 RAM 문구 — `[(파일, lba, size, 오프셋, 여유, 앞바이트, KR, JP)]`. `msgs` = `{JP sha1: KR}`.

    🔴 **자리를 손으로 안 적는다.** 같은 JP 가 한 파일 안에 여러 번, 편마다 또 한 벌씩 있다
      (실측 61 자리 / 고유 30 종). 하나만 고치면 어떤 화면에서만 일본어가 남는다.
    ⚠ **긴 것부터 맞춘다** — 짧은 문구가 긴 문구의 부분 문자열인 자리가 있다
      (`ロードに失敗しました` ⊂ `ロードに失敗しました。`). 짧은 쪽을 먼저 물리면 긴 문장을
      잘라 먹는다(PS1 이 같은 자리에서 물렸다 — `patch_sys_ui.MSGS` 주석). `_sys_match` 가 가장 앞선(=가장 긴) 접미를 고른다.
    🔴 JP 원문 평문을 정본에 안 둔다 — 열쇠는 sha1 이고 원문은 디스크에서 읽는다(`system.json` 과 같은 꼴).
    """
    out, seen = [], set()
    have = {p for p, _l, _s in common.iso_files(mm)}
    for path in list(dump_ui.FILES.values()) + [p for p in SYS_EXTRA_FILES if p in have]:
        lba, size = next((l, s) for p, l, s in common.iso_files(mm) if p == path)
        # ⚠ 파일을 늘렸으면 **늘어난 크기**를 들고 다닌다 — 뒤의 배치·되읽기가 이 값을 쓴다
        size = _tails().get(path, (0, size))[1] or size
        d = common.read_extent(mm, lba, size)
        i = 0
        while i < len(d):
            if d[i] == 0:
                i += 1
                continue
            j = i
            while j < len(d) and d[j] != 0:
                j += 1
            # 🔴 **접미로 맞춘다.** 문구 앞에 BE32 포인터가 붙어 한 런을 이루는 자리가 많다
            #   (실측: `\x06\x0b華\x06\x07zﾘゲームの記録が ありません。`). 통째 비교로는
            #   그런 자리를 통째로 놓치고, 앞 바이트를 다시 인코딩하면 포인터가 깨진다.
            #   그래서 **뒤에서 맞추고 앞은 원본 바이트 그대로** 이어 붙인다.
            run = bytes(d[i:j])
            hit = _sys_match(run, msgs)
            if hit:
                k, jp = hit
                nxt = j
                while nxt < len(d) and d[nxt] == 0:
                    nxt += 1
                seen.add(sys_key(jp))
                out.append((path, lba, size, i, nxt - i, run[:k], msgs[sys_key(jp)], jp))
            i = j
    missing = [h for h in msgs if h not in seen]
    assert not missing, f"디스크에서 못 찾은 문구 {len(missing)}: {missing[:3]}"
    return out


def msg_rows(mm, msgs):
    """`msg_scan` 에서 JP 를 뗀 7값 — `[(파일, lba, size, 오프셋, 여유, 앞바이트, KR)]`."""
    return [r[:7] for r in msg_scan(mm, msgs)]


# ── 고유명사 표 — 아이템 · 주문 · 몬스터 (2026-08-24) ─────────────────────────
# 🔴 **문안은 공용 고유명사 정본이 낸다**(`shared/glossary`). 여기엔 **자리만** 적는다 —
#    두 이식판이 같은 이름을 쓰게 하는 유일한 길이다.
# 자리는 `(파일키, 시작 오프셋, 개수, 첫 문자열, 무엇)` — 앵커와 개수가 어긋나면 실패한다.
NAME_TABLES = [
    ("ED", 0x000CD4, 114, "ナイフ", "아이템"),
    ("ED", 0x002494, 30, "フラム", "주문"),
    ("ED", 0x01B734, 223, "スライムＢ", "몬스터"),
    ("ED2", 0x000B3C, 119, "ナイフ", "아이템"),
    ("ED2", 0x002324, 33, "フラム", "주문"),
]
# ⚠ **손대지 않는 것** — 내부 자리표시자다. 번역하면 오히려 틀린다.
NAME_SKIP = {"ＭＧ１４", "ＭＧ１５", "ＭＧ２２"}
NAME_PTR_BASE = 0x06028000  # `ED.BIN`·`ED2.BIN` 의 적재 주소 (`dump_scn.BASES`)

# 🔴 **ED2 의 전투 문안은 본체가 아니라 몬스터 파일에 있다**(2026-08-27 — 유저 캡처에서
#    「スライムが現れた。」가 일본어로 남았다). ED1 은 같은 문안이 `ED.BIN` 안이라 진작
#    들어갔는데, ED2 는 `/BIN/ED2MON*.BIN` 이라 **파일 목록에서 통째로 빠져 있었다.**
#    ⚠ `dump_ui.FILES` 를 늘리지 않는다 — 그건 표 색인(`col = 0 if key == "ED" else 1`)에
#      쓰여서 편이 셋이 되면 깨진다. 시스템 메시지 순회만 넓힌다.
#    ⚠ **포인터 베이스가 다르다** — `ED2MON*` 은 0x060E0000 이다(`ptr_base()`).
#      상수를 쓰던 동안 포인터가 0곳으로 잡혀 앞말을 통째로 끌고 가려다 막혔다.
SYS_EXTRA_FILES = [f"/BIN/ED2MON{i:02d}.BIN" for i in range(1, 11)]

# 🔴 **그 파일에서는 출현 문구만 건드린다.** 몬스터 파일에는 이름 자체(`スライムＡ`)도 있는데
#    그건 **고정 폭 표**라 재배치하면 코드가 색인으로 집는 자리가 밀린다. 열어 두면 시스템
#    메시지 경로가 이름까지 옮기려 든다(실측 2026-08-27: `/BIN/ED2MON01.BIN` 0x974).
#    이름은 별도 축이다 — `NAME_TABLES` 로 다뤄야 한다.
SYS_EXTRA_SUFFIX = "が現れた。"


def ptr_base(path):
    """그 파일의 **적재 주소**. 🔴 파일군마다 다르다 — 상수로 쓰면 포인터를 못 찾는다.

    `ED.BIN`·`ED2.BIN` 0x06028000 vs **`ED2MON*.BIN` 0x060E0000**. 상수를 쓰던 동안
    ED2MON 은 포인터가 **0곳**으로 잡혀, 코드와 NUL 없이 붙은 런의 앞말을 통째로
    끌고 가려다 「앞말이 일본어」로 막혔다(2026-08-27).
    """
    b = dump_scn.base_for(os.path.basename(path))
    assert b, f"적재 주소를 모르는 파일: {path}"
    return b


def _nname(s):
    """이름 대조용 정규화 — 🔴 규칙은 `names.bare` 가 정본이다(셋이 갈려 있었다)."""
    from names import bare

    return bare(s)


def name_canon(what):
    """`{JP: KR}` — **그 표의 범주를 먼저 본다**.

    🔴 범주를 무시하고 합쳐 읽으면 **같은 원문이 범주에 따라 다른 것을 가리키는** 자리가
       조용히 틀린다 — `カース` 는 아이템이 「커스」, 몬스터가 「카스」다(정본 머리말).
       합쳐 읽던 동안 몬스터 표에 아이템 이름이 들어가 있었다(2026-08-24).
    """
    first = {"몬스터": "monster", "아이템": "item", "주문": "item"}[what]
    canon = {}
    for cat in (first, "item", "monster", "person", "place"):
        from names import person_table

        for k, v in (person_table() if cat == "person" else table(cat, "eiyuu")).items():
            canon.setdefault(k, v)
            canon.setdefault(_nname(k), v)
    return canon


def name_kr(jp, canon):
    """JP 이름 → KR. 못 찾으면 None(부르는 쪽이 실패로 친다)."""
    if jp in canon:
        return canon[jp]
    n = _nname(jp)
    if n in canon:
        return canon[n]
    # 🔴 **변종 접미**(Ａ~）는 정본에 안 넣는다 — 같은 몸이 넷씩 늘어 표가 네 배가 된다.
    #   `スライムＢ` = `スライム` + `B`. 붙일 때는 반각으로 붙인다(마스터 10-10 — `names.HALF` 가 정본).
    #   ⚠ **Ｅ 에서 끊지 않는다** — 소환 목록은 `毒大ガエルＨ` 까지 간다(2026-08-24).
    if len(n) > 1 and "A" <= n[-1:] <= "Z" and n[:-1] in canon:
        from names import HALF

        return canon[n[:-1]] + HALF[n[-1]]
    # `〜の書`(주문책)도 파생이다 — 밑말이 주문 이름이라 정본에 따로 안 둔다.
    #   「~의 책」이다(마스터 10-06 「모든 주문은 ~의 책」 — PS1 BOOK_SUFFIX 와 같게).
    if n.endswith("の書") and n[:-2] in canon:
        return canon[n[:-2]] + "의 책"
    return None


def name_rows(mm):
    """고유명사 표 다섯 — `[{key,path,lba,size,off,what,recs,room}]`.

    🔴 **칸을 늘려 쓴다(재배치).** 한 칸씩 제자리에 맞추면 34칸이 넘친다(`궁극의 지팡이`
       15B > 12B 등). 그런데 표는 **포인터 참조**라(칸마다 BE32 하나) 표 전체를 다시 깔고
       포인터를 고치면 된다 — 총량은 표마다 57~658B 남는다(실측).
    ⚠ 포인터 값 = `0x06028000 + 파일 오프셋`(BE32). 파일 전체를 훑어 그 값을 쓰는 자리를
      모은다 — 한 칸을 두 곳에서 가리키는 경우가 있어 **전부** 고친다.
    ⚠ 칸 사이 채움에 `\t`(0x09)가 섞여 있다. **포인터는 그 뒤를 가리키므로** 이름의 일부가
      아니다(실측: `0xCEB`(\t)를 가리키는 포인터는 없고 `0xCEC` 를 가리킨다). 다시 깔 때는
      0 으로 채운다.
    """
    out, miss = [], []
    for key, off, n, anchor, what in NAME_TABLES:
        canon = name_canon(what)
        path = dump_ui.FILES[key]
        lba, size = next((l, s) for p, l, s in common.iso_files(mm) if p == path)
        d = common.read_extent(mm, lba, size)
        recs, i, got, end = [], off, 0, off
        while got < n:
            while i < len(d) and d[i] < 0x20:  # 칸 사이 채움(0x00·0x09)
                i += 1
            j = i
            while j < len(d) and d[j] != 0:
                j += 1
            jp = d[i:j].decode("cp932")
            if got == 0:
                assert jp == anchor, f"{path} 0x{off:06X} {what}: 첫 칸이 {jp!r} (기대 {anchor!r})"
            kr = None if jp in NAME_SKIP else name_kr(jp, canon)
            if kr is None and jp not in NAME_SKIP:
                miss.append(jp)
            recs.append((i, jp, kr, _ptrs_to(d, i)))
            i, end, got = j, j + 1, got + 1
        while end < len(d) and d[end] < 0x20:  # 마지막 칸 뒤 채움까지가 우리 자리
            end += 1
        out.append(
            {
                "key": key,
                "path": path,
                "lba": lba,
                "size": size,
                "off": off,
                "what": what,
                "recs": recs,
                "room": end - off,
            }
        )
    assert not miss, f"정본에 없는 고유명사 {len(miss)}: {miss[:8]}"
    return out


def _ptrs_to(d, at, base=NAME_PTR_BASE):
    """파일 안에서 `at` 을 가리키는 BE32 포인터들의 오프셋."""
    pat = (base + at).to_bytes(4, "big")
    out, i = [], 0
    while True:
        j = d.find(pat, i)
        if j < 0:
            return out
        out.append(j)
        i = j + 1


_SPACED = None


def spaced_names():
    """이름 표 정본(아이템·주문·몬스터)에서 띄어 쓴 이름 — 긴 것부터. 시스템 메시지가 이름을 문장 안에 품은 자리를 묶는 데 쓴다."""
    global _SPACED
    if _SPACED is None:
        names = {v for cat in ("item", "monster") for v in table(cat, "eiyuu").values() if " " in v}
        _SPACED = sorted(names, key=lambda n: (-len(n), n))
    return _SPACED


def sys_bytes(kr, plan):
    """시스템 메시지 바이트 — 🔴 문장 안 띄어 쓴 이름은 줄바꿈 금지 코드로(번역 규칙 2-6, `font.glue_in_text`)."""
    return to_bytes(font.glue_in_text(kr, spaced_names()), plan)


def name_pack(t, plan):
    """표 하나 → `(새 바이트, {포인터 오프셋: 새 값})`. 안 넣는 칸은 원문을 그대로 옮긴다."""
    import patch_scn

    prot, od = patch_scn.protected_tails_of(t["path"])
    prot = [(a, b) for a, b in prot if t["off"] <= a < t["off"] + t["room"]]
    buf, moves = bytearray(), {}
    for _at, jp, kr, ptrs in t["recs"]:
        new_at = t["off"] + len(buf)
        body = to_bytes(font.glue_name(kr), plan) if kr else jp.encode("cp932")
        # 🔴 남이 포인터로 들어오는 꼬리(빈 문자열 자리, 마스터 10-22)는 **원판 그대로** 둔다 — 겹치면 그 뒤로 건너뛴다
        for a_, b_ in prot:
            if new_at < b_ and new_at + len(body) + 2 > a_:
                buf += b"\x00" * max(0, a_ - t["off"] - len(buf)) if a_ > new_at else b""
                new_at = t["off"] + len(buf)
                if new_at < b_:
                    buf += od[new_at:b_]
                    if len(buf) & 1:
                        buf += b"\x00"
                    new_at = t["off"] + len(buf)
        buf += body + b"\x00"
        if len(buf) & 1:  # 2바이트 정렬 — 원본도 짝수 자리에 깐다
            buf += b"\x00"
        for p in ptrs:
            moves[p] = NAME_PTR_BASE + new_at
    assert len(buf) <= t["room"], f"{t['path']} {t['what']}: {len(buf)}B > 자리 {t['room']}B"
    t["used"] = len(buf)  # 뒤 여유는 시스템 메시지의 도너로 쓴다(`sys_pack`)
    out = bytearray(bytes(buf) + b"\x00" * (t["room"] - len(buf)))
    for a_, b_ in prot:  # 칸 뒤 여유 안의 보호 구간도 원판 바이트로
        lo, hi = a_ - t["off"], min(b_ - t["off"], t["room"])
        out[lo:hi] = od[a_ : a_ + (hi - lo)]
    return bytes(out), moves


# ── 시스템 메시지 — 전투·보상·상태 (2026-08-24) ──────────────────────────────
# 🔴 **정본은 sha1 키다**(`script/system.json`) — 원문 평문을 커밋에 안 남긴다
#    (루트 CLAUDE.md 「저작권」). 그래서 **자리도 손으로 안 적는다** — 파일의 문자열을
#    훑어 해시로 붙인다. 배치가 바뀌어도 따라온다.
# ⚠ 이름 표(`NAME_TABLES`) 범위는 건너뛴다 — 거기는 `name_rows` 몫이다.


def _is_ed1_file(path):
    """ED1 쪽 파일 — `ED.BIN` · `ED1SCN*` · `ED1INIT` (ED2 는 `ED2.BIN` · `ED2SCN*` · `ED2MON*`)."""
    return path == "/ED.BIN" or path.startswith("/BIN/ED1")


def sys_key(jp):
    return hashlib.sha1(jp.encode("utf-8")).hexdigest()[:16]


def _sys_match(run, canon):
    """런 안에서 정본과 맞는 **접미**를 찾는다 → `(앞 바이트 수, JP)`.

    🔴 **접미로 맞춘다.** 문구 앞에 포인터·다른 문자열이 0 없이 붙어 한 런을 이루는 자리가
       있다(문구 표가 같은 이유로 그렇게 한다). 통째 비교로는 조용히 놓친다 — 실측 4건.
    🔴 **두 번 훑는다 — 문자 폭으로, 그 다음 바이트 단위로.** 앞이 포인터 바이트면 그 안에
       SJIS 선두 바이트처럼 생긴 값이 섞여 있어서, 문자 폭으로 걸으면 **이름 시작을 건너뛴다.**
       실측(2026-08-25): 전투 메시지의 `ｻﾝﾀﾞｰﾊｳﾝﾄﾞ`·`ヘルニルド`·`アクダム` 가 그렇게 빠져
       화면에 일본어로 남아 있었다.
    🔴 **둘 다 보고 「더 앞선」 것을 고른다 — 먼저 찾은 것을 쓰지 않는다.** 문자 폭 걷기가
       어긋나면 이름 시작을 지나쳐 **더 뒤의 짧은 정본**(`が現れた。`)을 먼저 잡고, 그러면
       이름이 앞말로 남아 일본어가 된다(실측 2026-08-27: `チャンタラーが現れた。` 가
       k=31 에 있는데 문자 폭 패스가 31 을 건너뛰고 k=43 을 물었다).
       앞선 매칭 = 앞말이 가장 적게 남는 매칭이다.
    ⚠ 바이트 단위라도 **디코드가 되고 해시가 맞아야** 한다 — 우연히 맞을 확률은 없다시피 하고,
      보존되는 앞말은 `_no_jp_prefix()` 가 따로 본다.
    """
    best = None
    for step_by_char in (True, False):
        k = 0
        while k < len(run):
            if run[k] < 0x20:
                k += 1
                continue
            try:
                jp = run[k:].decode("cp932")
            except UnicodeDecodeError:
                k += 1
                continue
            if sys_key(jp) in canon:
                if best is None or k < best[0]:
                    best = (k, jp)
                break
            b = run[k]
            k += (2 if (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF) else 1) if step_by_char else 1
    return best


def sys_rows(mm):
    """시스템 메시지 — `[(파일, lba, size, 오프셋, 여유, 앞바이트, KR, 포인터, JP)]`.

    🔴 **`앞바이트`(6번째)는 JP 원문이 아니다 — 거의 늘 비어 있다.** 매칭된 JP 접미 앞에
       0 없이 붙은 **이름 등 처리 안 된 바이트**만 담는다(`_no_jp_prefix` 용). 대부분의
       줄은 런 맨 앞에서 바로 매칭돼 이 필드가 빈 바이트열이다(실측 2026-10-07:
       1,143자리 중 1,135자리가 공백 — `check_prose_glossary.py` 가 이걸 JP 로 착각해
       대조 커버리지가 8/1,143 뿐이었다, 다루디아 옛 표기 잔존 사고). **JP 원문은 9번째
       `jp`를 쓴다**(`_sys_match()` 가 찾은 그 값 그대로).

    🔴 **`exact` 는 「통짜일 때만 맞는」 표시다.** 홑조사(`に`·`は`)처럼 짧은 정본은 접미
       매칭 탓에 **아직 일본어인 문장의 끝**과도 맞는다(실측: `に` 가 `/ED2.BIN` 0x18006 의
       미번역 대사 끝에 걸렸다). 그렇다고 못 넣으면 조사만 든 자리가 영영 일본어로 남는다.
       그래서 이 표시가 붙은 정본은 **앞말이 일본어인 자리를 실패가 아니라 건너뛴다** —
       통짜인 자리에서만 쓰인다.
    ⚠ 표시가 없는 정본은 예전대로 **앞말이 일본어면 실패**다(`_no_jp_prefix`). 조각을
      함부로 넣는 사고를 막는 장치라 기본값을 바꾸지 않는다.
    """
    with open(SYS_CANON, encoding="utf-8") as f:
        doc = json.load(f)
    canon, exact = {**_canon_sys_lines(), **doc["lines"]}, set(doc.get("exact", []))
    # 🔴 **작품별 값** — ED1·ED2 가 같은 원문(같은 열쇠)을 공유해도 정본이 작품마다 따로 정한 문구(`system.json` `by_game.ED1`)는 ED1 쪽 파일에서만 그 값을 쓴다
    #    (11-08: 「は目が覚めた。」 정본 ed1 「잠에서 깨어났다」 · ed2 「깨어났다」 — 한 열쇠라 ED1 전투 2곳이 ed2 값이었다).
    by_game = doc.get("by_game", {}).get("ED1", {})
    skip = {}
    for key, off, n, _a, _w in NAME_TABLES:
        skip.setdefault(dump_ui.FILES[key], []).append((off, n))
    # 🔴 **고정폭 표가 가진 자리는 손대지 않는다.** 그 표는 포인터가 첫 칸만 가리키고 나머지는
    #   코드가 색인으로 집는다 — 재배치하면 메뉴가 통째로 밀린다. 상태 약어를 정본에 넣었다가
    #   `verify` 가 잡았다(2026-08-24). 여기서 아예 못 잡히게 막는다.
    fixed = {}
    for key, path in dump_ui.FILES.items():
        col = 0 if key == "ED" else 1
        # ⚠ **지명 표도 넣는다**(`GLOSSARY_TABLES`). 빠뜨렸더니 같은 지명을 정본에 넣었을 때
        #   표와 **두 주인**이 되어 되읽기가 18건 울었다(2026-08-27:
        #   `'보아드해운' ≠ '보아드해운　'` — 표는 접미 공백까지 붙인다).
        #   그 표들은 정본이 `shared/glossary` 라 시스템 메시지가 건드릴 자리가 아니다.
        for _name, ed, ed2, stride, n, n2 in dump_ui.TABLES:
            off, cnt = (ed, ed2)[col], (n, n2)[col]
            if off and cnt:
                fixed.setdefault(path, []).append((off, off + stride * cnt))
        for _name, ed, ed2, stride, n, n2, _cat in dump_ui.GLOSSARY_TABLES:
            off = (ed, ed2)[col]
            cnt = (n2 if (col == 1 and n2) else n) or 0
            if off and cnt:
                fixed.setdefault(path, []).append((off, off + stride * cnt))
    # 🔴 **우리가 쓰는 표는 전부 막는다 — 목록을 손으로 안 든다**(2026-08-28).
    #    위 둘(`TABLES`·`GLOSSARY_TABLES`)엔 **지명 표가 없었다.** 그래서 시스템 메시지가
    #    그 표의 첫 칸(`エルアスタ`)을 「옮길 수 있는 문자열」로 보고 옮겼고, 그 자리를
    #    가리키던 **표 베이스 포인터(0x44E6C)** 까지 새 주소로 바꿨다. 루틴은 그 포인터에
    #    `색인×14` 를 더해 집으므로, 첫 칸만 맞고 나머지는 **코드 바이트를 이름으로 읽는다**
    #    (화면에 `A!A!A!B근처`). ⇒ `rows()` 가 아는 표 구간을 **그대로** 보호 범위로 쓴다.
    #    ⚠ 「어느 표가 위험한가」를 사람이 고르지 않는다 — 표는 다 색인으로 집힌다.
    for r in rows():
        rpath = dump_ui.FILES[r[0]]
        off, stride = int(r[3]), int(r[4])
        fixed.setdefault(rpath, []).append((off, off + stride))
    out, seen = [], set()
    have = {p for p, _l, _s in common.iso_files(mm)}
    for path in list(dump_ui.FILES.values()) + [p for p in SYS_EXTRA_FILES if p in have]:
        lba, size = next((l, s) for p, l, s in common.iso_files(mm) if p == path)
        # ⚠ 파일을 늘렸으면 **늘어난 크기**를 들고 다닌다 — 뒤의 배치·되읽기가 이 값을 쓴다
        size = _tails().get(path, (0, size))[1] or size
        d = common.read_extent(mm, lba, size)
        # 이름 표가 차지한 구간 — 여기 문자열은 건너뛴다
        holes = []
        for off, n in skip.get(path, []):
            i, got = off, 0
            while got < n:
                while i < len(d) and d[i] < 0x20:
                    i += 1
                j = i
                while j < len(d) and d[j] != 0:
                    j += 1
                i, got = j, got + 1
            holes.append((off, i))
        i = 0
        while i < len(d):
            if d[i] == 0:
                i += 1
                continue
            j = i
            while j < len(d) and d[j] != 0:
                j += 1
            if not any(a <= i < b for a, b in holes + fixed.get(path, [])):
                hit = _sys_match(d[i:j], canon)
                # 위 SYS_EXTRA_SUFFIX 주석 — 못 늘린 파일은 자리가 0 이라 출현 문구만
                if (
                    hit
                    and path in SYS_EXTRA_FILES
                    and path not in _tails()
                    # ⚠ 꼬리 개행까지 받는다 — 실제 문자열은 `…が現れた。\n` 인 것이 있다
                    and not hit[1].rstrip("\n").endswith(SYS_EXTRA_SUFFIX)
                ):
                    hit = None
                if hit and any(a <= i + hit[0] < b for a, b in fixed.get(path, [])):
                    # 🔴 **맞은 자리도 본다** — 런 시작만 보면 표 앞에서 시작한 런이 표
                    #    안까지 삼킨다. 실측 2026-08-28: `エルアスタ`(지명 표 첫 칸)가 이렇게
                    #    잡혀 옮겨졌고, 그 자리를 가리키던 **표 베이스 포인터**까지 바뀌어
                    #    HUD 가 `색인×14` 로 코드 바이트를 읽었다(`A!A!A!B근처`).
                    hit = None
                if hit:
                    k, jp = hit
                    nxt = j
                    while nxt < len(d) and d[nxt] == 0:
                        nxt += 1
                    # 🔴 **자리는 고정 폭 표 앞에서 멈춘다.** 자리(span)는 「다음 자료가
                    #    시작하는 데」까지인데, 표를 스캔에서만 빼고 여기서 안 막으면 그 앞
                    #    레코드의 자리가 **표를 삼킨다** — 그리고 풀에 들어가 덮인다
                    #    (실측 2026-08-27: `ED/지명[0] '큰독개구리C' ≠ '엘아스타　'`).
                    for a, _b in fixed.get(path, []):
                        if i < a < nxt:
                            nxt = a
                    # 🔴 **재배치 단위는 「포인터가 가리키는 자리」다.** 한 런에 문자열이 둘
                    #   이상 붙어 있고(0 없이) 포인터가 그 중간을 가리키는 자리가 있다.
                    #   우리 글 앞에서 **가장 가까운 포인터 대상**을 잡아야 앞말을 안 끌고 간다.
                    pb = ptr_base(path)
                    base = i
                    for o in range(i + k, i - 1, -1):
                        if _ptrs_to(d, o, pb):
                            base = o
                            break
                    ptrs = _ptrs_to(d, base, pb)
                    pre = d[base : i + k]
                    # 🔴 **몬스터 파일은 통짜만 건드린다.** 자리가 빠듯해 못 넣은 줄이 있고
                    #    (`derive_encounters.py` 가 목록으로 보고한다), 그 자리에 짧은 정본
                    #    (`が現れた。` = `이(가) 나타났다.`)이 **접미로 걸린다.** 그러면 이름이
                    #    앞말로 남아 일본어가 된다 — 실패가 아니라 **손대지 않는 게 맞다**.
                    if path in SYS_EXTRA_FILES and _jp_bytes(pre):
                        # ⚠ 앞말이 **일본어면** 손대지 않는다 — 못 넣은 줄에 짧은 정본이
                        #   접미로 걸린 것이다. `%c%s%c` 같은 제어·인자는 통과시킨다
                        #   (런타임 이름 + `が現れた。` 꼴 — 조사는 훅이 접는다).
                        i = j
                        continue
                    if sys_key(jp) in exact and _jp_bytes(pre):
                        i = j  # 통짜인 자리에서만 쓴다 — 위 독스트링
                        continue
                    # 🔴 **한 글자 접미 조각(`Ｂ`~`Ｈ` → 반각, 마스터 10-24 J3=B)은 「포인터가 가리키는 칸」에서만 바꾼다.** 포인터 없는 `Ｂ` 가
                    #    이웃 바이트 끝(데이터)에 접미로 걸린 자리가 둘 있었다(ED.BIN 0x7FD63 · ED2.BIN 0x65323) — 문자열이 아니라 자료라 건드리면 깨진다.
                    if len(jp) == 1 and "Ａ" <= jp <= "Ｚ" and not ptrs:
                        seen.add(sys_key(jp))
                        i = j
                        continue
                    _no_jp_prefix(path, base, pre, jp)
                    seen.add(sys_key(jp))
                    out.append(
                        (
                            path,
                            lba,
                            size,
                            base,
                            nxt - base,
                            d[base : i + k],
                            by_game.get(sys_key(jp), canon[sys_key(jp)]) if _is_ed1_file(path) else canon[sys_key(jp)],
                            ptrs,
                            jp,
                        )
                    )
            i = j
    missing = [k for k in canon if k not in seen]
    assert not missing, f"디스크에서 못 찾은 시스템 메시지 {len(missing)}: {missing[:4]}"
    return _drop_mon_name_rows(out)


def _drop_mon_name_rows(rows):
    """🔴 **몬스터 이름 칸은 `patch_mon_names` 것이다 — 시스템 행에서 뺀다**(2026-10-19 qa r4, ED2MON07 0xA10).
    정본 몬스터 이름(`ウィーバー` → 와이바)이 시스템 정본(`_canon_sys_lines`)에도 들어 있어 같은 칸이 시스템 행으로도 잡혔다. 그러면 `sys_pack` 이 그 칸을
    풀로 보고 다른 문구(`%c%s%cに` → 「에게 」)를 거기 깔고, 뒤 단계 `patch_mon_names` 가 이름을 **제자리**에 다시 써서 덮는다 — 문구 포인터가 이름을 가리켰다
    (「…에게 」 자리에 「콘B」). 한 칸에 주인 둘(`_no_double_owner` 와 같은 부류)."""
    import patch_mon_names as M
    from canon import table

    mon = table("monster", "eiyuu")
    owned = {p: {t for t, _jp, _kr in M.slots(p, mon)} for p in {r[0] for r in rows if r[0] in SYS_EXTRA_FILES}}
    return [r for r in rows if r[3] not in owned.get(r[0], ())]


def _no_double_owner(inplace, sysm):
    """🔴 **한 자리에 주인이 둘이면 안 된다.**

    카드·문구는 **제자리**에 쓰고 시스템 메시지는 **풀에 다시 깐다**. 같은 문자열을 양쪽
    정본에 적으면 두 번 쓰이고, 나중 쪽이 앞엣것을 덮는다 — 24자리가 그렇게 깨졌다
    (2026-08-24, 되읽기가 잡았다). 겹치면 **시스템 정본에서 빼는 게 맞다**(카드·문구가
    자리를 안다).
    """
    spans = {}
    for path, _l, _s, at, span, _pre, _kr in inplace:
        spans.setdefault(path, []).append((at, at + span))
    bad = []
    for path, _l, _s, at, span, _pre, kr, _p, _jp in sysm:
        if any(at < b and a < at + span for a, b in spans.get(path, [])):
            bad.append(f"{path} 0x{at:06X} {kr!r}")
    if bad:
        for b in bad[:6]:
            print(f"  ❌ {b}")
        raise SystemExit(
            f"카드·문구가 이미 가진 자리를 시스템 정본이 또 가졌다 ({len(bad)}자리) "
            f"— system.json 에서 뺀다"
        )


def _jp_bytes(pre):
    """보존되는 앞말에 일본어 바이트가 있나(SJIS 선두·반각 가나)."""
    return any(0x81 <= b <= 0x9F or 0xA1 <= b <= 0xDF or 0xE0 <= b <= 0xEF for b in pre)


def _no_jp_prefix(path, base, pre, jp):
    """🔴 **접미만 맞으면 앞말이 일본어로 남는다.**

    정본에 짧은 조각(`が現れた。`)을 넣으면 이름이 구워진 자리(`スライムが現れた。`)도
    같이 걸린다 — 앞말은 보존되므로 화면에 **「スライム이(가) 나타났다.」** 가 뜬다.
    빌드는 성공하고 되읽기도 통과한다(자리마다 따로 보니까). 그래서 여기서 막는다:
    **보존되는 앞말에 일본어가 있으면 실패**. 그런 자리는 조각이 아니라 **통짜로** 적는다.
    ⚠ 앞말이 「같은 런에 붙은 남의 문자열」이면 `base` 가 그 뒤를 가리키므로 여기 안 온다.
    """
    if _jp_bytes(pre):
        raise SystemExit(
            f"시스템 정본 {jp!r} 이 {path} 0x{base:X} 의 앞말을 일본어로 남긴다 "
            f"— 조각 말고 통짜로 적는다"
        )


_TAILS = None


def _tails():
    """`{경로: (원 크기, 새 크기)}` — 파일 확장으로 생긴 꼬리. 한 번만 잰다."""
    global _TAILS
    if _TAILS is None:
        import expand_files

        _f, mm = common.open_image()
        _TAILS = expand_files.tails(mm)
        mm.close()
        _f.close()
    return _TAILS


def sys_pack(sysm, ntabs, plan, extra=()):
    """시스템 메시지를 **자리 풀에 다시 깐다** → `{파일: ({오프셋: 바이트}, {포인터: 값})}`.

    🔴 **제자리로는 안 들어간다.** 조사를 병기하면(`은(는)`) 일본어 두 글자가 여덟 바이트가
       되어 29자리가 넘친다. 전부 포인터 참조라(런 안 포인터까지 훑어 확정) 자리를 옮길 수
       있고, **자기 칸 전부 + 이름 표를 다시 깔고 남은 꼬리**를 한 풀로 묶으면 들어간다
       (실측 ED 773/1,548 · ED2 666/837).
    ⚠ **먼저 풀 전체를 0 으로 덮는다** — 옮긴 자리에 옛 일본어가 남으면 다른 포인터가
      그걸 가리키고 있을 때 조용히 살아난다.
    ⚠ 큰 것부터 넣는다(first-fit decreasing). 작은 것부터면 큰 게 갈 데가 없어진다.
    """
    out = {}
    _tails()
    for path in {r[0] for r in sysm}:
        recs = [r for r in sysm if r[0] == path]
        pool = [(r[3], r[4]) for r in recs]
        # 🔴 **파일을 늘려 만든 꼬리도 풀이다**(`tools/expand_files.py`, 2026-08-27).
        #    ED2MON 은 꽉 차 있어 우리 레코드 자리만으로는 모자랐다 — 꼬리 섹터를 크기
        #    필드로 열어 ~10KB 를 얻었다. ⚠ `patch_mon_names` 는 이름 칸 안에서만 노므로
        #    이 꼬리는 여기 전용이다(둘이 안 겹친다).
        if path in _TAILS:
            old, new = _TAILS[path]
            pool.append((old, new - old))
        for t in ntabs:
            if t["path"] == path and t["room"] > t["used"]:
                pool.append((t["off"] + t["used"], t["room"] - t["used"]))
        pool.sort()
        # 🔴 **남이 포인터로 들어오는 꼬리는 풀이 아니다**(마스터 10-22) — 풀 조각에서 도려낸다(원판 바이트 그대로 남는다)
        import patch_scn

        _prot = patch_scn.protected_tails_of(path)[0]
        _cut = []
        for at, n in pool:
            cur = at
            for a_, b_ in _prot:
                if b_ <= cur or a_ >= at + n:
                    continue
                if a_ > cur:
                    _cut.append((cur, a_ - cur))
                cur = max(cur, b_)
            if cur < at + n:
                _cut.append((cur, at + n - cur))
        pool = _cut
        # 🔴 **붙어 있는 칸은 하나로 합친다**(2026-08-24). 배정은 칸을 넘지 못하므로,
        #   합치지 않으면 총량이 남는데도 조각이 다 작아 큰 문안이 갈 데가 없어진다 —
        #   실측 ED2 는 256B 가 남은 채 25B 하나를 못 넣고 죽었다. 레코드의 span 은
        #   「다음 자료가 시작하는 자리」까지라 **연속 레코드는 원래 맞닿아 있다.**
        merged = []
        for at, n in pool:
            if merged and merged[-1][0] + merged[-1][1] == at:
                merged[-1][1] += n
            else:
                merged.append([at, n])
        pool = [(a, n) for a, n in merged]
        body = {}
        for at, n in pool:
            body[at] = bytearray(n)
        free = sorted(pool, key=lambda b: -b[1])
        # 🔴 **못 박은 자리는 풀에서 뺀다.** 제자리에 쓰는 것만으로는 부족하다 — 그 자리가
        #   풀에 남아 있으면 배치기가 **다른 문안을 거기 얹는다**(실측: 접미 표 위에
        #   `%c%s%c은(는) ` 이 깔렸다). 앞뒤 조각은 다시 풀로 돌린다.
        for pa in PINNED_INPLACE.get(path, ()):
            pn = next((sp for _p2, _l2, _s2, a2, sp, *_r in recs if a2 == pa), 4)
            free = [(o, n) for o, n in free if not (o <= pa < o + n)] + [
                x
                for o, n in free
                if o <= pa < o + n
                for x in ((o, pa - o), (pa + pn, o + n - pa - pn))
                if x[1] >= 2
            ]
        free.sort(key=lambda b: -b[1])
        moves = {}
        # 🔴 **못 옮기는 자리는 제자리에 박는다** — 코드가 절대주소로 집는다. 자리에서 빼고,
        #   넘치면 문안을 줄이는 수밖에 없다(2026-08-24, ED.BIN 0x26CF8).
        #   ⚠ 못 옮기는 조건은 **둘**이다 — 포인터가 없거나, `PINNED_INPLACE` 이거나
        #     (포인터가 있어도 표로 집히는 자리, 위 주석).
        pin = PINNED_INPLACE.get(path, ())
        for _p, _l, _s, at, span, pre, kr, ptrs, _jp in recs:
            if ptrs and at not in pin:
                continue
            blob = pre + sys_bytes(kr, plan)
            blob += b"\x00"
            assert len(blob) <= span, (
                f"{path} 0x{at:X}: 포인터가 없어 못 옮기는데 {len(blob)}B > {span}B — "
                f"문안을 줄인다: {kr!r}"
            )
            blk = max(a for a, _n in pool if a <= at)
            body[blk][at - blk : at - blk + len(blob)] = blob
            free = [(o, n) for o, n in free if not (o <= at < o + n)] + [
                x
                for o, n in free
                if o <= at < o + n
                for x in ((o, at - o), (at + len(blob), o + n - at - len(blob)))
                if x[1] >= 2
            ]
            free.sort(key=lambda b: -b[1])
        want = sorted(
            [r for r in recs if r[7] and r[3] not in pin]
            + [(path, 0, 0, 0, 0, blob_, "", ptrs_, lead_) for p_, blob_, ptrs_, lead_ in extra if p_ == path],
            key=lambda r: -(len(r[5]) + rec_len(r[6]) + 1),
        )
        # ⚠ **몬스터 파일은 자리가 빠듯하다.** 그 파일들은 꽉 차 있어 기존 0런이 사실상
        #   없고(ED2MON01·02 는 **0바이트**), 풀은 「우리 레코드 자리」가 전부다. 우리 문안은
        #   원문보다 줄마다 2바이트쯤 길어서(원문 `が現れた。` 10B vs `이(가) 나타났다.` 12B —
        #   한국어는 띄어쓰기가 있다) **총량이 원본보다 커진다.**
        #   → 들어가는 줄만 정본에 넣는다. 거르는 건 `derive_encounters.py` 몫이고, 여기서는
        #     넘치면 예전대로 죽는다(조용히 넘기지 않는다).
        #   ⚠ 문안을 줄여 맞추지 않는다 — PS1 도 `이(가) 나타났다.` 라, 여기서만 줄이면
        #     **두 이식판의 표기가 갈린다**(2026-08-27 확인).
        for _p, _l, _s, _at, _span, pre, kr, ptrs, _jp in want:
            blob = pre + sys_bytes(kr, plan)
            blob += b"\x00"
            # 🔴 **짝수 주소에만 놓는다**(2026-08-28). 이 게임의 어떤 화면은 두 바이트를
            #    한 글자로 **고정**해 읽는다(HUD 지명). 홀수 자리에 놓으면 그 화면에서만
            #    통째로 밀려 깨진다 — SJIS 선행 바이트를 보는 렌더러는 멀쩡해서 **메뉴는
            #    정상인데 HUD 만 깨진다.** 실측: `엘아스타` 가 0x2C6A1 로 가 있었고, 그
            #    포인터 하나가 HUD 조립 루틴의 리터럴 풀(0x44E6C)에 있었다.
            #    ⚠ 홀수는 문안에 **반각이 섞이면** 자연히 생긴다(`전투 직전으로` 13B).
            # 🔴 **가장 꼭 맞는 조각**을 고른다(best-fit, 10-10). 가장 큰 조각부터 쓰면(first-fit) 큰 조각이 먼저 쪼개져
            #    총량이 995B 남고도 11B 하나가 못 들어갔다 — 전각 접미로 이름 표가 1B 씩 불며 드러났다.
            fits = [k for k, (o_, n_) in enumerate(free) if n_ - (o_ & 1) >= len(blob)]
            i = min(fits, key=lambda k: (free[k][1], free[k][0]), default=None)
            assert i is not None, f"{path}: 자리가 모자란다 — {kr!r} {len(blob)}B"
            o, n = free.pop(i)
            if o & 1:  # 앞의 한 바이트는 버린다 — 짝수로 맞춘다
                o, n = o + 1, n - 1
            blk = max(a for a, _n in pool if a <= o)
            body[blk][o - blk : o - blk + len(blob)] = blob
            new_at = o + len(pre)  # 포인터는 **앞 바이트 다음**을 가리킨다(원본과 같게)
            for q in ptrs:
                moves[q] = ptr_base(path) + (o if len(pre) == 0 else new_at - len(pre)) - (_jp if isinstance(_jp, int) else 0)
            rest_o, rest_n = o + len(blob), n - len(blob)
            if rest_o & 1:  # 남는 조각도 짝수에서 시작하게
                rest_o, rest_n = rest_o + 1, rest_n - 1
            if rest_n >= 2:
                free.append((rest_o, rest_n))
                free.sort(key=lambda b: -b[1])
        # 독약 빌드(시험용, `ED_POOL_POISON=<바이트>`) — 문안을 다 깔고 **남은 풀 조각**을 눈에 띄는 값으로 채운다. 입장 배너 전용 표·끼움 루틴처럼
        #   비운 자리에 새로 놓는 것이 「그 자리를 아무도 안 읽는다」는 전제에 서므로, 그 전제를 하네스 대조(독약 빌드 ≡ 정상 빌드 화면)로 확인한다.
        if os.environ.get("ED_POOL_POISON"):
            pz = int(os.environ["ED_POOL_POISON"], 0)
            for o, n in free:
                blk = max(a for a, _n in pool if a <= o)
                body[blk][o - blk : o - blk + n] = bytes([pz]) * n
        out[path] = ({a: bytes(b) for a, b in body.items()}, moves)
    return out


def needed(krs):
    """슬롯을 먹어야 하는 글자 — cp932 로 안 되는 것(=한글)만."""
    need = set()
    for kr in krs:
        for ch in kr or "":
            try:
                ch.encode("cp932")
            except UnicodeEncodeError:
                need.add(ch)
    return sorted(need)


def slot_plan(krs, refresh=False):
    """`{글자: (SJIS 2B, 슬롯 인덱스)}`. ⚠ 자동 갱신하지 않는다 — 낡은 폰트와 어긋난다.

    ⚠ 슬롯 계획은 **표 라벨과 씬 헤더를 한꺼번에** 받아야 한다. 따로 세우면 나중에 부른
      쪽이 앞의 배정을 모른 채 같은 슬롯을 다시 쓴다.
    """
    need = needed(krs)
    old = {}
    if os.path.exists(HMAP):
        with open(HMAP, encoding="utf-8") as f:
            old = json.load(f)["syllables"]
    if refresh or not old:
        free = font.free_slots("11kanji")
        assert len(need) <= len(free), f"슬롯 부족 {len(need)}>{len(free)}"
        # 🔴 **덧붙이기만 한다**(2026-09-06). 이미 배정된 글자는 자리를 지키고, **안 쓰이게
        #    된 글자도 안 뺀다.**
        #    까닭: **세이브가 이 코드를 그대로 담는다** — 파티원 이름이 백업 RAM 에 우리
        #    글리프 코드로 적힌다(실측: 유저 세이브 32KB 안에 16곳 — 세리오스·류난·로우·
        #    게일·아트라스·란도·플로라·신디). 슬롯을 회수해 다른 글자에 주면 **옛 세이브의
        #    이름이 엉뚱한 글자로 뜬다.** pce-ed1 이 실제로 물린 사고다(2026-09-06 중계).
        #    ⚠ 자리는 넉넉하다 — 쓰는 글자 1,120 · 여유 2,959.
        keep = dict(old)
        taken = set(keep.values()) | reserved_slots(krs)
        pool = [i for i in free if i not in taken]
        old = dict(keep)
        for c in need:
            if c not in old:
                old[c] = pool.pop(0)
        with open(HMAP, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "_doc": "한글 → 11KANJI.FON 슬롯 인덱스 (커밋 정본). 16px 쪽은 hangul_map.json",
                    "syllables": old,
                },
                f,
                ensure_ascii=False,
                indent=1,
            )
        print(f"  슬롯 정본 갱신: {len(old)}자 → {os.path.basename(HMAP)}")
    missing = [c for c in need if c not in old]
    assert not missing, f"정본에 없는 글자 {len(missing)}자 — `--refresh`: {''.join(missing[:12])}"
    return {c: (font.sjis_of_index(i), i) for c, i in old.items()}


def scn_suffix_fit(scn, canon=None):
    """지명이 **원문보다 길어지지 않았나** → 넘치는 `[(지명, 우리B, 원문, 원문B)]`.

    이 필드(`fl`)는 **뒤가 곧바로 SH-2 코드**라 늘리면 코드를 덮는다. 원문 안에서만 논다.
    ⚠ 여기는 **마을 안 HUD** 다 — 바깥의 「곶의동굴 근처」는 `ED.BIN` 의 지명 표에서
      조립된다(위 `SUFFIXED_TABLE` 주석). 접미와 띄우는 것도 그쪽 일이다.
    """
    seen, bad = {}, []
    for _p, _l, _s, _at, _fl, jp, kr, _t in scn:
        seen.setdefault(kr, jp)
    for kr, jp in seen.items():
        ours, orig = scn_rec_len(kr) - 1, len(jp.encode("cp932"))
        if ours > orig:
            bad.append((kr, ours, jp, orig))
    return bad


def kanji_gaps(krs, orig_kanji):
    """우리가 쓰는 **전각 글자 중 원본 폰트에 글리프가 없는 것** — `ascii_gaps` 의 전각판.

    🔴 없으면 **조용히 빈칸으로 나간다**(반각 온점과 같은 부류). 실측 2026-08-24:
      말줄임표 `…`(SJIS 0x8163 · 슬롯 35) 가 통째로 비어 있다 — PS1 문안을 맞추며 들어왔다.
    ⚠ 자리는 **게임 자신의 계산**으로 잡는다(`font.game_index`) — 우리 식이 어긋나면
      엉뚱한 글자가 나오는데 빌드도 되읽기도 통과한다.
    """
    need = set()
    for kr in krs:
        for ch in kr or "":
            if "가" <= ch <= "힣" or ch.isascii() or ch.isspace() or ch in font.HALF_QUOTES:
                continue  # ⚠ 전각 공백(`\u3000`)은 빈 글리프가 정답이다 — 반각 0x20 과 같다
            try:
                b = ch.encode("cp932")
            except UnicodeEncodeError:
                continue  # 한글은 위에서 걸렀다 — 여기 오는 건 슬롯을 받은 글자다
            if len(b) == 2:
                need.add(ch)
    out = []
    for ch in sorted(need):
        i = font.game_index(ch.encode("cp932"))
        if not any(orig_kanji[i * font.GLYPH_STRIDE :][: font.GLYPH_STRIDE]):
            out.append(ch)
    return out


def reserved_slots(krs):
    """전각 구멍을 메울 슬롯 — 한글 배정에서 **빼야 한다**.

    `font.free_slots()` 는 **원본** 기준으로 「빈 글리프」를 세므로, 우리가 구우려는 자리도
    비어 있다고 본다. 안 빼면 한글이 늘었을 때 말줄임표 위에 음절이 얹힌다.
    """
    return {font.game_index(c.encode("cp932")) for c in kanji_gaps(krs, common.extract(FON))}


def ascii_gaps(krs, orig_ascii):
    """우리가 쓰는 **반각 글자 중 원본 폰트에 글리프가 없는 것**.

    🔴 없으면 **조용히 빈칸으로 나간다.** 실측 2026-08-24: 온점 `.`(0x2E) 슬롯이 통째로
      비어 있어 시스템 메시지의 온점이 전부 사라졌다 — 바이트는 멀쩡히 들어가 있었고
      되읽기도 통과했다. 화면만 틀리는 부류라 검사기가 없으면 못 잡는다.
    ⚠ 공백(0x20)은 빈 글리프가 정답이라 뺀다. `%` 는 서식 지시자라 그려지지 않는다.
    """
    need = {c for kr in krs for c in (kr or "") if 0x21 <= ord(c) < 0x7F and c != "%"}
    return sorted(c for c in need if not any(orig_ascii[ord(c) * ASCII_STRIDE :][:ASCII_STRIDE]))


def bake_ascii(chars):
    """반각 글리프를 Galmuri11 로 굽는다 — 8×11, 행당 1바이트."""
    import numpy as np
    from fonts import galmuri

    bdf = galmuri()
    out = {}
    for ch in chars:
        bits = bdf.bits(ch, dy=-3, rows=11, width=8)
        assert bits.any(), f"Galmuri11 에 없는 반각 글자 {ch!r}"
        if ch in ".,":
            # 마스터 11-13 「마침표·쉼표 한국식」 — 원판 ！ 아래 점(1×2)과 같은 점, 쉼표는 왼쪽 아래 꼬리.
            #   (옛 쉼표가 마침표와 같아진 사고 10-20 qa r5 — 꼬리를 11행 안(10행)에 직접 둔다.)
            bits[:] = 0
            # 🔴 마스터 11-16 「원판의 ? ! 에 맞춰서 마침표를」(규칙 1-3, 2×2 안을 대체) — 원판 ！ 아래 점은 1×2px(8·9행, 원판 ？ 점은 9행 1px).
            #    마침표는 그 점(1×2·8·9행) 그대로, 쉼표는 같은 점을 머리로 두고 왼쪽 아래 꼬리 한 점.
            if ch == ".":
                bits[8, 1] = bits[9, 1] = 1
            else:
                bits[8, 2] = bits[9, 2] = 1
                bits[10, 1] = 1
        out[ch] = np.packbits(bits, axis=1).tobytes()
        assert len(out[ch]) == ASCII_STRIDE
    return out


# ── 반각 영문·숫자 — 번역 글꼴(GalmuriMono11) 마스터 10-27 (규칙 1-8 「원판 글꼴과 번역 글꼴을 화면으로 비교」 → 번역 글꼴)
# PS1 I·II 와 같은 글꼴이다(`ps1-ed1+2/tools/patch_ascii_galmuri.py` — 이름이 `common` 으로 부딪혀 임포트할 수 없어 굽는 규칙만 옮겼다).
# 반각 진행 6px 칸에 들어가는 GalmuriMono11(전진 6 · 잉크 5 · 높이 10). 소문자 내림(g j p q y)은 2행이라 11행 칸을 넘어 줄기 한 행을 덜어 낸다.
# 🔴 **0 은 빗금 없이, 폭도 줄이지 않는다**(규칙 1-8, 마스터 10-26) — Mono11 의 빗금 0 대신 대문자 O 꼴을 쓴다(PS1 다음 판과 같은 꼴).
LATIN_CODES = (*range(0x30, 0x3A), *range(0x41, 0x5B), *range(0x61, 0x7B))
LATIN_ORIG_SHA1 = "9fb763ffc94daf95e70016e350481b83c87b32c7"  # 원판 11ASCII 62자 연결 지문 — 이중 적용·주소 어긋남을 막는다


def bake_latin():
    """`{코드: 11B}` — A–Z a–z 0–9 를 GalmuriMono11 로 (8×11 · 행당 1B · MSB=왼쪽, 잉크는 열 0~4)."""
    from fonts import load_bdf

    font_, asc = load_bdf(os.path.join(common.ROOT, "shared", "fonts", "GalmuriMono11.bdf"))
    out = {}
    for code in LATIN_CODES:
        w, h, xo, yo, rows = font_[code]
        nbits = ((w + 7) // 8) * 8
        top = asc - (yo + h) - 3
        grid = [0] * 15
        for r, v in enumerate(rows):
            if 0 <= top + r < len(grid):
                grid[top + r] = ((v >> (nbits - 8)) if nbits >= 8 else (v << (8 - nbits))) >> xo & 0xFF
        used = [r for r in range(len(grid)) if grid[r]]
        if used and used[-1] >= ASCII_STRIDE:
            cand = [r for r in (8, 9, 10) if grid[r] == grid[r + 1] or grid[r] == grid[r - 1]]
            del grid[cand[0] if cand else 9]
            grid.append(0)
        assert not any(grid[ASCII_STRIDE:]), f"0x{code:02X} 11행 초과"
        assert all(b & 0x07 == 0 for b in grid[:ASCII_STRIDE]), f"0x{code:02X} 열 5~7 잉크"
        out[code] = bytes(grid[:ASCII_STRIDE])
    out[0x30] = out[0x4F]  # 0 = 빗금 없는 꼴
    return out


# ── 방향 없는 따옴표 `"` `'` — 마스터 도안 시안 A(10-28, 규칙 1-2 「방향 없는 반각 " ' 한 글자로 열고 닫는다」, 분열 몬스터 A' A" 도 같은 글자).
# 8×11 칸에 열 0~5 만 쓰고(진행 6px) 위 3행만 잉크 — 한글 꼭대기(0행)에 맞춘다. 원판은 `"` 칸이 비어 있었고 `'` 는 왼쪽으로 기운 작은 점이었다.
QUOTE_GRID = {
    '"': (".#.#....", ".#.#....", ".#.#...."),
    "'": ("..#.....", "..#.....", "..#....."),
}


def quote_glyph(ch):
    rows = list(QUOTE_GRID[ch]) + ["........"] * (ASCII_STRIDE - len(QUOTE_GRID[ch]))
    return bytes(int(r.replace(".", "0").replace("#", "1"), 2) for r in rows)


# 「」 반각 마스터 도안 A판(10-26, 정본 — 다시 그리지 않는다). 12×11: 「 = 0~5열 · 」 = 6~11열, 진행 6px.
KAGI_GRID = (
    "####........",
    "#...........",
    "#...........",
    "#...........",
    "#........#..",
    "#........#..",
    "#........#..",
    ".........#..",
    ".........#..",
    ".........#..",
    "......####..",
)


# 『』 A2판 v2(10-27, 마스터 「가로 1칸 길게」 — 같은 규격)
KAGI2_GRID = (
    "#####.......",
    "#...#.......",
    "#.###.......",
    "#.#.........",
    "#.#.....###.",
    "#.#.....#.#.",
    "###.....#.#.",
    "........#.#.",
    "......###.#.",
    "......#...#.",
    "......#####.",
)
KAGI_CHARS = "「」『』"


def kagi_glyph(ch):
    """「 『 → 도안 0~5열, 」 』 → 6~11열을 8×11 칸 왼쪽(0~5열)에 놓은 11B."""
    grid = KAGI_GRID if ch in "「」" else KAGI2_GRID
    c0 = 0 if ch in "「『" else 6
    return bytes(int(row[c0 : c0 + 6].replace(".", "0").replace("#", "1").ljust(8, "0"), 2) for row in grid)


def bake_half_quotes(chars):
    """반각 곡선 따옴표 글리프 — Galmuri11 의 좁은 따옴표를 8×11 칸에 놓되, **여는 쪽은 칸 오른쪽 끝·닫는 쪽은 왼쪽 끝**에 잉크를 붙인다
    (옆 글자에 붙어 읽힌다, 마스터 10-19). 위치는 `font.HALF_QUOTES` 코드(원판 반각 폰트에서 비어 있고 안 쓰이는 칸)."""
    import numpy as np
    from fonts import galmuri

    bdf = galmuri()
    out = {}
    for ch in chars:
        if ch in KAGI_CHARS:
            out[ch] = kagi_glyph(ch)
            continue
        bits = bdf.bits(ch, dy=-3, rows=11, width=8)
        assert bits.any(), f"Galmuri11 에 없는 따옴표 {ch!r}"
        cols = np.where(bits.any(axis=0))[0]
        shift = (7 - cols.max()) if ch in font.HALF_QUOTE_OPENING else -cols.min()
        bits = np.roll(bits, shift, axis=1)
        out[ch] = np.packbits(bits, axis=1).tobytes()
        assert len(out[ch]) == ASCII_STRIDE
    return out


def rec_len(kr):
    """레코드 바이트 수 — 본문 + 널 1B. 🔴 세는 규칙은 `font.byte_len` 이 정본이다.

    🔴 낱말 사이는 **반각 공백**이다. 전각으로 두면 `마지막 들른 마을로` 가 21B 로 한 칸을
      넘긴다(PS1 도 같은 자리에서 물려 `에` 를 뺐다 — 유저 확정 2026-08-01). 이 렌더러엔
      반각짝 `/11ASCII.FON` 이 있고 **원본 레코드도 이미 반각을 쓴다**(`ＨＰ    ` ·
      `残り    ` · `ﾏﾆｭｱﾙ `) — 16px 타이틀(`patch_title.py`)과 갈리는 지점이다.
    """

    return byte_len(kr) + 1


def encode(kr, stride, plan):
    """레코드 바이트 — 본문 + 널 + 0 채움. 넘치면 실패한다."""
    body = to_bytes(kr, plan)
    assert len(body) + 1 <= stride, f"{kr!r} 이 {len(body) + 1}B 로 stride {stride} 를 넘는다"
    return body + b"\x00" * (stride - len(body))


def check(rs):
    """넣기 전 안전판 — 정본이 자리에 들어가나. 폭 넘침·글리프 없음을 미리 잡는다."""
    bad = 0
    for key, name, i, at, stride, _jp, kr in rs:
        if kr is None:
            continue
        nb = rec_len(kr)
        if nb > stride:
            print(f"  ❌ {key}/{name}[{i}] 0x{at:06x} {kr!r} {nb}B > stride {stride}")
            bad += 1
    return bad


def scn_encode(kr, fl, tail, plan):
    """헤더 필드 — 우리 이름 + 널 채움 + **원본 꼬리 바이트 그대로**.

    🔴 저장 바이트가 막히는 지명(`DOTART_PLACES`)은 전각 한글이 아니라 반각 도트 글리프
      6B 로 적는다(위 섹션, PS1 수법 이식·마스터 지시 2026-10-05).
    """
    body = DOTART_PLACES.get(kr) or to_bytes(kr, plan)
    assert len(body) < fl, f"{kr!r} 이 {len(body)}B 로 헤더 {fl}B 에 안 든다"
    return body + b"\x00" * (fl - 1 - len(body)) + bytes([tail])


def scn_rec_len(kr):
    """씬 헤더용 레코드 길이 — `DOTART_PLACES` 오버라이드가 있으면 그 길이, 없으면 `rec_len`."""
    if kr in DOTART_PLACES:
        return len(DOTART_PLACES[kr]) + 1
    return rec_len(kr)


def write_file(f, path, lba, size, patch, label):
    """`{오프셋: 바이트}` 를 제자리에 쓴다 — **이어진 덩어리로 끊어서.**

    ⚠ `min~max` 를 한 덩어리로 쓰지 않는다. `ED2.BIN` 은 HUD 표와 메뉴 풀이 190KB 넘게
      떨어져 있어 그 사이 원본 바이트를 통째로 다시 깔게 되고, 그러면 **다른 패처가 같은
      파일에 넣은 것을 조용히 되돌린다**(실측: 199,580B/98섹터 → 848B/2섹터).
    🔴 **틈을 메우는 바이트는 원본이 아니라 「지금 이미지」에서 읽는다**(2026-08-24).
      64B 문턱은 되돌림을 **줄일** 뿐 못 막는다 — 시스템 메시지 풀 두 덩이(0x26C64·0x26CA4)가
      25B 떨어져 한 런이 되면서, 그 사이에 있던 `없음`(0x26C8B, 앞 단계가 쓴 것)이
      **원본 일본어로 되돌아갔다.** 빌드는 성공했고 되읽기가 잡았다.
      ⚠ 이건 「원본이 어땠나」를 묻는 읽기가 아니라 「지금 무엇이 있나」를 묻는 읽기다 —
        레포 규율(제자리 갱신 이미지를 되읽지 말 것)이 말하는 비멱등과 반대 방향이다.
        값은 전부 원본에서 유도했고, 여기서 읽는 건 **안 건드릴 틈**뿐이라 멱등이다.
    """
    f.flush()
    _fd, mmd = common.open_image(f.name)
    try:
        orig = common.extract(path, mmd)
    finally:
        mmd.close()
        _fd.close()
    runs, cur = [], []
    for at in sorted(patch):
        if cur and at - (cur[-1] + len(patch[cur[-1]])) > 64:
            runs.append(cur)
            cur = []
        cur.append(at)
    runs.append(cur)
    nsec = nb = 0
    for run in runs:
        lo, hi = run[0], run[-1] + len(patch[run[-1]])
        buf = bytearray(orig[lo:hi])
        for at in run:
            buf[at - lo : at - lo + len(patch[at])] = patch[at]
        nsec += common.write_at(f, lba, size, lo, bytes(buf), label=label)
        nb += hi - lo
    return len(runs), nb, nsec


def main():
    common.verify_source()
    rs = rows()
    _f0, mm0 = common.open_image()
    scn = scn_rows(mm0)
    cards = card_rows(mm0, load_canon()[0])
    msgs = msg_rows(mm0, load_canon()[2])
    ntabs = name_rows(mm0)
    names = [r[2] for t in ntabs for r in t["recs"] if r[2]]
    sysm = sys_rows(mm0)
    mm0.close()
    _f0.close()
    n_kr = sum(1 for r in rs if r[6])
    print(f"표 {len({(r[0], r[1]) for r in rs})} · 레코드 {len(rs)} · 한글 {n_kr}")
    print(
        f"씬 지명 헤더 {len(scn)}곳 · {len({r[0] for r in scn})}파일 · {len({r[5] for r in scn})}종"
    )
    _over = scn_suffix_fit(scn)
    if _over:
        print(f"  ⚠ 원문보다 길어진 지명 {len(_over)}종 — 접미를 붙이면 잘릴 수 있다")
        for kr, ours, jp, orig in _over[:5]:
            print(f"      {kr!r} {ours}B > {jp!r} {orig}B")
    print(f"챕터 카드 {len(cards)}장 · SAVE/LOAD 문구 {len(msgs)}자리")
    _no_double_owner(cards + msgs, sysm)
    print(f"시스템 메시지 {len(sysm)}자리 · 고유 {len({r[6] for r in sysm})}종")
    print(
        f"고유명사 {len(names)}칸 — "
        + " · ".join(f"{t['key']} {t['what']} {len(t['recs'])}" for t in ntabs)
    )
    bad = check(rs)
    check_dotart_codes(rs, scn, ntabs, sysm)
    for path, _l, _s, at, fl, jp, kr, _t in scn:
        if scn_rec_len(kr) > fl:
            print(f"  ❌ {path} 0x{at:05x} {jp}→{kr} {scn_rec_len(kr)}B > 헤더 {fl}B")
            bad += 1
    for path, _l, _s, at, span, pre, kr in cards + msgs:
        if rec_len(kr) + (len(pre) if isinstance(pre, bytes) else 0) > span:
            head = len(pre) if isinstance(pre, bytes) else 0
            print(f"  ❌ {path} 0x{at:06x} {rec_len(kr) + head}B > {span}B: {kr!r}")
            bad += 1
    if bad:
        raise SystemExit(f"❌ 폭을 넘는 레코드 {bad}건 — 넣기 전에 문안을 줄인다")
    print("  ✅ 원문 대조 · 폭 검사 통과")
    if "--verify-final" in sys.argv:
        # 🔴 체인이 **끝난** 최종 이미지에서 이 패처의 되읽기를 다시 한다 — 단계 직후에만 돌면 뒤 단계가 덮어쓴 것을 아무도 못 본다(2026-10-19 ED2MON 꼬리).
        dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
        if not os.path.exists(dst):
            raise SystemExit("되읽기(최종): 빌드 이미지가 없다 — 먼저 빌드한다")
        with open(HMAP, encoding="utf-8") as f_:
            syl = json.load(f_)["syllables"]
        plan = {c: (font.sjis_of_index(i), i) for c, i in syl.items()}
        _fo, mmo = common.open_image()
        files = common.dst_files(dst, mmo)
        # ⚠ 재배치로 LBA·크기가 바뀐 파일이 있다 — 행의 (lba, size) 를 **최종 이미지의 것**으로 바꿔 넘긴다
        sysm_f = [(r[0], *files[r[0]], *r[3:]) if r[0] in files else r for r in sysm]
        verify(dst, rs, scn, cards + msgs, plan, files)
        verify_names(dst, ntabs, plan, files)
        verify_sys(dst, sysm_f, plan, files)
        return
    if "--apply" not in sys.argv:
        return

    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not os.path.exists(dst):
        raise SystemExit(f"먼저 자막을 넣는다(patch_title.py --apply) — {dst} 가 없다")

    # 🔴 **씬 문안까지 한 번에 받는다.** `slot_plan` 은 `need` 에 없는 글자를 버리므로
    #    소비자를 하나라도 빠뜨리면 그 글자가 정본에서 밀려난다(2026-08-27 실측: 씬 문안만
    #    주고 `--refresh` 를 돌렸더니 UI 글자 10자가 날아갔다).
    import patch_scn

    all_krs = (
        [r[6] for r in rs]
        + [r[6] for r in scn]
        + [r[6] for r in cards + msgs + sysm]
        + names
        + patch_scn.all_texts()  # ⚠ 인자 없이 — 이 시점엔 `mm0` 이 이미 닫혀 있다
    )  # 🔴 글자 슬롯 계획과 폰트 구멍 검사(`kanji_gaps`)가 **같은 목록**을 본다 — 따로 두니 한쪽만 빠져 ‘ ’ 가 빈 칸으로 나왔다
    plan = slot_plan(all_krs, refresh="--refresh" in sys.argv)
    print(f"  한글 슬롯 {len(plan)}자")

    _f, mm = common.open_image(dst)
    # ⚠ **크기는 늘어난 쪽을 쓴다** — `expand_files` 가 꼬리 섹터를 열었으므로 원본 크기로
    #   보면 그 꼬리에 못 쓰고 되읽기도 짧게 읽는다(실측 2026-08-27: `되읽기 ''`).
    files = {
        p: (lba, _tails().get(p, (0, size))[1] or size) for p, lba, size in common.iso_files(mm)
    }
    mm.close()
    _f.close()

    with open(dst, "r+b") as f:
        patch_banner_field(f, files)
        for key, path in dump_ui.FILES.items():
            patch = {
                at: encode(kr, stride, plan)
                for k, _n, _i, at, stride, _jp, kr in rs
                if k == key and kr
            }
            lba, size = files[path]
            nrun, nb, nsec = write_file(f, path, lba, size, patch, f"{path} UI 라벨")
            print(f"  {path}: {len(patch)}칸 · 덩어리 {nrun} ({nb:,}B, 섹터 {nsec})")

        # ── 씬 지명 헤더 — 화면에 뜨는 건 여기다
        byfile = {}
        for path, lba, size, at, fl, _jp, kr, tail in scn:
            byfile.setdefault((path, lba, size), {})[at] = scn_encode(kr, fl, tail, plan)
        tsec = 0
        for (path, lba, size), patch in byfile.items():
            _r, _b, nsec = write_file(f, path, lba, size, patch, f"{path} 지명 헤더")
            tsec += nsec
        print(f"  씬 지명 헤더: {len(scn)}곳 · {len(byfile)}파일 · 섹터 {tsec}")

        # ── 챕터 카드 — 화면 아래 장 이름이자 장 끝 카드다(같은 문자열)
        bycard = {}
        for path, lba, size, at, span, pre, kr in cards + msgs:
            head = pre if isinstance(pre, bytes) else b""
            body = head + to_bytes(kr, plan)
            bycard.setdefault((path, lba, size), {})[at] = body + b"\x00" * (span - len(body))
        csec = 0
        for path, q, _old, new in card_ptr_fixes(cards):  # 탭 카드 포인터 리터럴 +1 → +0
            key_ = next((k for k in bycard if k[0] == path), None)
            assert key_, f"{path}: 카드 쓰기 칸이 없다"
            bycard[key_][q] = new
        for (path, lba, size), patch in bycard.items():
            _r, _b, nsec = write_file(f, path, lba, size, patch, f"{path} 챕터 카드")
            csec += nsec
        print(f"  챕터 카드 {len(cards)}장 + 문구 {len(msgs)}자리 · 섹터 {csec}")

        # ── 고유명사 표 — **다시 깔고 포인터를 고친다**(칸 하나씩으로는 34칸이 넘친다)
        nsec = 0
        for t in ntabs:
            blob, moves = name_pack(t, plan)
            nsec += common.write_at(
                f, t["lba"], t["size"], t["off"], blob, label=f"{t['path']} {t['what']} 표"
            )
            pt = {at: v.to_bytes(4, "big") for at, v in moves.items()}
            _r, _b, ps = write_file(
                f, t["path"], t["lba"], t["size"], pt, f"{t['path']} {t['what']} 포인터"
            )
            nsec += ps
            print(
                f"  {t['path']} {t['what']}: {len(t['recs'])}칸 · {len(blob)}B/{t['room']}B"
                f" · 포인터 {len(moves)}"
            )
        print(f"  고유명사 표 {len(ntabs)}개 · 섹터 {nsec}")

        # ── 시스템 메시지 — 자리 풀에 다시 깐다(제자리로는 29자리가 넘친다)
        ssec = 0
        for path, (body, moves) in sys_pack(sysm, ntabs, plan, extra=banner_extra(rs, plan)).items():
            lba, size = files[path]
            _r, _b, a = write_file(f, path, lba, size, body, f"{path} 시스템 메시지")
            pt = {at: v.to_bytes(4, "big") for at, v in moves.items()}
            _r, _b, b2 = write_file(f, path, lba, size, pt, f"{path} 시스템 포인터")
            ssec += a + b2
            print(
                f"  {path} 시스템: {sum(1 for r in sysm if r[0] == path)}자리 · 포인터 {len(moves)}"
            )
        print(f"  시스템 메시지 · 섹터 {ssec}")

        # ── 반각 폰트 — 원본에 없는 글리프만 채운다(온점 등)
        gaps = ascii_gaps(
            [r[6] for r in rs] + [r[6] for r in scn] + [r[6] for r in cards + msgs + sysm] + names,
            common.extract(FON_ASCII),
        )
        gaps = [c for c in gaps if c not in QUOTE_GRID]  # `"` 는 아래 도안 A 로 굽는다 — Galmuri 로 먼저 굽지 않는다
        assert not {ord(c) for c in gaps} & set(font.HALF_QUOTES.values()), f"반각 구멍 {gaps!r} 이 반각 따옴표·「」 코드와 겹친다"
        if gaps:
            alba, asize = files[FON_ASCII]
            for ch, g in bake_ascii(gaps).items():
                common.write_at(
                    f, alba, asize, ord(ch) * ASCII_STRIDE, g, label=f"{FON_ASCII} {ch!r}"
                )
            print(f"  반각 폰트 {FON_ASCII}: 원본에 없던 {''.join(gaps)!r} 구움")

        # ── 반각 영문·숫자 — 번역 글꼴(GalmuriMono11, 0 은 빗금 없이). 62자 전부 굽는다(어느 글자가 어디 쓰일지 가리지 않는다)
        alba, asize = files[FON_ASCII]
        cur = b"".join(bytes(common.extract(FON_ASCII)[c * ASCII_STRIDE :][:ASCII_STRIDE]) for c in LATIN_CODES)
        assert hashlib.sha1(cur).hexdigest() == LATIN_ORIG_SHA1, "11ASCII 영문·숫자가 원판과 다르다 — 다른 패치가 먼저 건드렸다"
        for code, g in bake_latin().items():
            common.write_at(f, alba, asize, code * ASCII_STRIDE, g, label=f"{FON_ASCII} 영문·숫자 {chr(code)!r}", expect=bytes(cur[LATIN_CODES.index(code) * ASCII_STRIDE :][:ASCII_STRIDE]))
        print(f"  반각 폰트 {FON_ASCII}: 영문·숫자 {len(LATIN_CODES)}자 번역 글꼴(Mono11·0 빗금 없음)")

        # ── 물음표 `?` — 마스터 11-13 A안: 원판 전각 ？ 의 잉크(열 3~7, 5폭)를 왼쪽에 붙이고 오른쪽 1px 비움(반각 진행 6px)
        alba, asize = files[FON_ASCII]
        orig_ascii = common.extract(FON_ASCII)
        okj = common.extract(FON)
        gi = font.jis_index("？") if hasattr(font, "jis_index") else None
        qg = bytes(
            ((int.from_bytes(okj[gi * font.GLYPH_STRIDE + r * 2 :][:2], "big") >> 7) & 0x3F) << 2 & 0xFF
            for r in range(ASCII_STRIDE)
        )
        off = ord("?") * ASCII_STRIDE
        common.write_at(f, alba, asize, off, qg, label=f"{FON_ASCII} 물음표 '?'", expect=bytes(orig_ascii[off : off + ASCII_STRIDE]))
        print(f"  반각 폰트 {FON_ASCII}: 물음표 A안(전각 ？ 잉크)")

        # ── 방향 없는 따옴표 `"` `'` — 도안 A(코드 0x22·0x27). `'` 는 원판 칸을 덮는다(원판이 그대로인지 확인하고)
        alba, asize = files[FON_ASCII]
        orig_ascii = common.extract(FON_ASCII)
        for ch in QUOTE_GRID:
            off = ord(ch) * ASCII_STRIDE
            common.write_at(f, alba, asize, off, quote_glyph(ch), label=f"{FON_ASCII} 따옴표 {ch!r}", expect=bytes(orig_ascii[off : off + ASCII_STRIDE]))
        print(f"  반각 폰트 {FON_ASCII}: 방향 없는 따옴표 \" ' 도안 A")

        # ── 반각 곡선 따옴표 — 쓰이는 것만 굽는다(코드는 `font.HALF_QUOTES`, 원판에서 비어 있고 안 쓰이는 칸이어야 한다)
        used_q = sorted({c for kr in all_krs for c in (kr or "") if c in font.HALF_QUOTES})
        if used_q:
            alba, asize = files[FON_ASCII]
            orig_ascii = common.extract(FON_ASCII)
            for ch, g in bake_half_quotes(used_q).items():
                off = font.HALF_QUOTES[ch] * ASCII_STRIDE
                assert not any(orig_ascii[off : off + ASCII_STRIDE]), f"{ch!r} 코드 {font.HALF_QUOTES[ch]:#x} 칸이 원판에서 안 비었다"
                common.write_at(f, alba, asize, off, g, label=f"{FON_ASCII} 반각 따옴표 {ch!r}")
            print(f"  반각 폰트 {FON_ASCII}: 곡선 따옴표 {''.join(used_q)!r} 구움")

        # ── 반각 도트 글리프 — DOTART_PLACES 가 실제로 scn 헤더에 쓰인 지명만 굽는다
        used_dotart = sorted(
            {kr for _p, _l, _s, _at, _fl, _jp, kr, _t in scn if kr in DOTART_PLACES}
        )
        if used_dotart:
            alba, asize = files[FON_ASCII]
            orig_ascii = common.extract(FON_ASCII)
            for code, g in bake_dotart_glyphs().items():
                off = code * ASCII_STRIDE
                common.write_at(
                    f,
                    alba,
                    asize,
                    off,
                    g,
                    label=f"{FON_ASCII} 도트 0x{code:02X}",
                    expect=bytes(orig_ascii[off : off + ASCII_STRIDE]),
                )
            n_codes = sum(len(DOTART_PLACES[kr]) for kr in used_dotart)
            print(f"  반각 도트 {FON_ASCII}: {n_codes}칸 구움 ({'·'.join(used_dotart)})")

        # ── 전각 폰트의 구멍 — 원본에 글리프가 없는 전각 글자(말줄임표 등)
        kgaps = kanji_gaps(all_krs, common.extract(FON))
        if kgaps:
            kg, kmiss = convert_chars("".join(kgaps))
            assert not kmiss, f"Galmuri11 에 없는 전각 글자: {''.join(kmiss)}"
            kflba, kfsize = files[FON]
            for ch in kgaps:
                common.write_at(
                    f,
                    kflba,
                    kfsize,
                    font.game_index(ch.encode("cp932")) * font.GLYPH_STRIDE,
                    kg[ch],
                    label=f"{FON} 전각 {ch!r}",
                )
            print(f"  전각 폰트 {FON}: 원본에 없던 {''.join(kgaps)!r} 구움")

        # ── 폰트 — 계획대로 글리프를 굽는다
        glyphs, missing = convert_chars("".join(plan))
        assert not missing, f"Galmuri11 에 없는 글자: {''.join(missing)}"
        flba, fsize = files[FON]
        for ch, (_sjis, idx) in plan.items():
            common.write_at(
                f, flba, fsize, idx * font.GLYPH_STRIDE, glyphs[ch], label=f"{FON} 글리프 {idx}"
            )
        print(f"  폰트 {FON}: 글리프 {len(glyphs)}자 구움")
        common.write_at(
            f, flba, fsize, font.game_index("…".encode("cp932")) * font.GLYPH_STRIDE, ellipsis_glyph(),
            label=f"{FON} … 한국식 바닥",
        )
        print("  전각 폰트 …: 점 셋을 글자 아랫줄로 내렸다")

    verify(dst, rs, scn, cards + msgs, plan, files)
    verify_names(dst, ntabs, plan, files)
    verify_sys(dst, sysm, plan, files)
    print(f"  → {dst}")


def decode(b, inv):
    """레코드 바이트 → 글자. 🔴 **2바이트씩 끊어 읽으면 안 된다** — 반각 공백(1B)이 끼면
    그 뒤가 통째로 어긋난다(2026-08-24 실측: 공백이 든 레코드 20건이 전부 깨져 보였는데
    쓰기는 멀쩡했다). SJIS 선행 바이트를 보고 1B/2B 를 가른다."""
    out, j = [], 0
    while j < len(b):
        n = 2 if (0x81 <= b[j] <= 0x9F or 0xE0 <= b[j] <= 0xFC) else 1
        w = b[j : j + n]
        q = {v: k for k, v in font.HALF_QUOTES.items()}.get(w[0]) if len(w) == 1 else None  # 반각 곡선 따옴표 코드
        out.append(" " if w == bytes([font.NB_CODE]) else inv.get(w) or q or w.decode("cp932", "replace"))
        j += n
    return "".join(out)


def verify(dst, rs, scn, cards, plan, files):
    """되읽기 — 쓴 것을 다시 읽어 정본과 대조한다. 폰트 글리프까지 본다."""
    inv = {sjis: ch for ch, (sjis, _i) in plan.items()}
    _f, mm2 = common.open_image(dst)
    mm = mm2
    bufs = {k: common.read_extent(mm, *files[p]) for k, p in dump_ui.FILES.items()}
    fon = common.read_extent(mm, *files[FON])
    glyphs, _ = convert_chars("".join(plan))
    bad = []
    for key, name, i, at, stride, _jp, kr in rs:
        if kr is None:
            continue
        rec = bufs[key][at : at + stride]
        got = decode(rec[: rec.find(b"\x00")], inv)
        if got != kr:
            bad.append(f"{key}/{name}[{i}] 0x{at:06x} {got!r} ≠ {kr!r}")
    cache = {}  # 씬 파일은 헤더가 여럿이다 — 파일마다 한 번만 읽는다
    for path, _lba, _size, at, fl, _jp, kr, _tail in scn:
        if path not in cache:
            cache[path] = common.read_extent(mm2, *files[path])
        rec = cache[path][at : at + fl]
        raw = rec[: rec.find(b"\x00")]
        # 🔴 도트 글리프는 일반 디코더로 읽으면 바이트 그대로의 반각(｡｣､ｦｩﾒ)으로 나온다 —
        #   그게 맞다(`scn_encode` 가 실제로 그 바이트를 쓴다). 쓴 바이트가 정확히 그
        #   조합일 때만 지명으로 되돌려 대조한다.
        got = kr if kr in DOTART_PLACES and raw == DOTART_PLACES[kr] else decode(raw, inv)
        if got != kr:
            bad.append(f"{path} 0x{at:05x} {got!r} ≠ {kr!r}")
    for path, _lba, _size, at, span, pre, kr in cards:
        if path not in cache:
            cache[path] = common.read_extent(mm2, *files[path])
        head = len(pre) if isinstance(pre, bytes) else 0
        rec = cache[path][at + head : at + span]
        got = decode(rec[: rec.find(b"\x00")], inv)
        if got != kr:
            bad.append(f"{path} 0x{at:06x} {got!r} ≠ {kr!r}")
    for path, q, _old, new in card_ptr_fixes(cards):
        if path not in cache:
            cache[path] = common.read_extent(mm2, *files[path])
        if cache[path][q : q + 4] != new:
            bad.append(f"{path} 탭 카드 포인터 리터럴 0x{q:X} 가 시작을 안 가리킨다")
    for ch, (_s, idx) in plan.items():
        o = idx * font.GLYPH_STRIDE
        if fon[o : o + font.GLYPH_STRIDE] != glyphs[ch]:
            bad.append(f"글리프 {ch!r} 슬롯 {idx} 가 안 들어갔다")
    o = font.game_index("…".encode("cp932")) * font.GLYPH_STRIDE
    if fon[o : o + font.GLYPH_STRIDE] != ellipsis_glyph():
        bad.append("글리프 … 가 한국식 바닥으로 안 들어갔다")
    mm2.close()
    _f.close()
    if bad:
        for b in bad[:8]:
            print(f"  ❌ {b}")
        raise SystemExit(f"되읽기가 정본과 다르다 ({len(bad)}건) — 이 이미지를 쓰지 않는다")
    print(
        f"  ✅ 되읽기 {sum(1 for r in rs if r[6])}칸 + 씬 헤더 {len(scn)}곳 + "
        f"카드 {len(cards)}장 + 글리프 {len(plan)}자"
    )


def verify_names(dst, ntabs, plan, files):
    """되읽기 — 고유명사 표는 **포인터를 따라가** 읽는다(자리가 움직였으니 그게 정본이다)."""
    inv = {sjis: ch for ch, (sjis, _i) in plan.items()}
    _f2, mm2 = common.open_image(dst)
    n = 0
    for t in ntabs:
        d = common.read_extent(mm2, t["lba"], t["size"])
        for _at, jp, kr, ptrs in t["recs"]:
            assert ptrs, f"{t['path']} {jp}: 포인터가 없다"
            at = int.from_bytes(d[ptrs[0] : ptrs[0] + 4], "big") - NAME_PTR_BASE
            j = at
            while j < len(d) and d[j] != 0:
                j += 1
            got = decode(d[at:j], inv)
            want = kr or jp
            assert got == want, f"{t['path']} {jp}: 되읽기 {got!r} ≠ {want!r}"
            n += 1
    mm2.close()
    _f2.close()
    print(f"  ✅ 되읽기 고유명사 {n}칸 (포인터 추적)")


def verify_sys(dst, sysm, plan, files):
    """되읽기 — 시스템 메시지도 **포인터를 따라가** 읽는다(자리를 옮겼으니 그게 정본이다)."""
    inv = {sjis: ch for ch, (sjis, _i) in plan.items()}
    _f2, mm2 = common.open_image(dst)
    cache, n = {}, 0
    for path, lba, size, at, _span, pre, kr, ptrs, _jp in sysm:
        if path not in cache:
            cache[path] = common.read_extent(mm2, lba, size)
        d = cache[path]
        # 제자리에 박은 자리(포인터가 없거나 `PINNED_INPLACE`)는 그 자리를 그대로 읽는다.
        movable = ptrs and at not in PINNED_INPLACE.get(path, ())
        # 🔴 **모든 포인터**를 따라간다(첫 포인터만 보던 때 두 번째 포인터가 엉뚱한 문구를 가리켜도 통과했다, 2026-10-19 ED2MON04)
        for q in ptrs if movable else [None]:
            a = int.from_bytes(d[q : q + 4], "big") - ptr_base(path) if movable else at
            j = a + len(pre)
            while j < len(d) and d[j] != 0:
                j += 1
            got = decode(d[a + len(pre) : j], inv)
            assert got == kr, f"{path} 0x{a:06X}: 되읽기 {got!r} ≠ {kr!r}"
            n += 1
    mm2.close()
    _f2.close()
    print(f"  ✅ 되읽기 시스템 메시지 {n}자리 (포인터 추적)")


if __name__ == "__main__":
    # ⚠ **실패하면 산출물을 무효화한다**(레포 빌드 규율) — 낡은 이미지를 정상으로 오해하는
    #   사고를 막는다. `patch_title.py` 와 같은 장치.
    try:
        main()
    except BaseException:
        d = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
        if "--apply" in sys.argv and os.path.exists(d):
            shutil.move(d, d + ".failed")
            print(f"  ⚠ 실패 — 산출물을 무효화했다: {os.path.basename(d)}.failed")
        raise
