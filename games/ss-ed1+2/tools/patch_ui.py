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
import unicodedata

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

import common
import dump_scn
import dump_ui
import font
from fonts import convert_chars
from glossary import lookup, table

CANON = os.path.join(common.GAME_DIR, "script", "ui.json")
SYS_CANON = os.path.join(common.GAME_DIR, "script", "system.json")
HMAP = os.path.join(common.GAME_DIR, "hangul_map_11kanji.json")
FON = "/11KANJI.FON"
FON_ASCII = "/11ASCII.FON"
ASCII_STRIDE = 11  # 11행 × 1바이트 (8×11)
PAD = "　"  # 전각 공백 — 원본 폰트에 이미 있어 슬롯을 안 먹는다


def load_canon():
    with open(CANON, encoding="utf-8") as f:
        d = json.load(f)
    return (
        d["tables"],
        d.get("pad", {}),
        d.get("cards", []),
        d.get("pad_to_jp", []),
        d.get("msgs", []),
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
SUFFIXED_TABLE = "지명"
WIDE_SP = "\u3000"


def _internal_key(jp):
    """**반각 가나가 섞인** 항목 — 게임 내부 키다(화면에 안 나온다).

    🔴 건드리면 자료를 부순다. 지명 표에 `ｴﾙｱｽﾀ`·`ﾙﾃﾞｨｱT`·`ｲｼｭ/ｲｽ`·`ﾘｭｳE` 처럼 섞여
       있는데, 글자가 지명처럼 보인다고 번역하면 그 키로 찾는 코드가 못 찾는다.
    ⚠ 정본에 없으니 `assert kr` 로도 걸리지만, 그러면 **표를 통째로 못 등록한다** —
      ED2 셋째 묶음(103칸)은 화면 지명과 내부 키가 한 표에 섞여 있다(2026-08-27).
    ⚠ 두 번 헛짚었다(2026-08-27). 「반각 가나·ASCII 만」으로 재면 `ｲｼｭﾀ～ｲｽﾞｰ` 의 **전각
      물결**(U+FF5E)에 걸리고, 「전각 가나·한자가 있나」로 재면 `ｳｲﾙ～城` 의 **한자**에 걸린다.
      화면에 나가는 지명은 **원본이 전부 전각**이므로, 반각 가나가 하나라도 섞였으면 키다.
    """
    return any("\uff66" <= c <= "\uff9f" for c in jp)


def rows():
    """`(파일키, 표이름, 색인, 오프셋, stride, JP, KR|None)` — 원본에서 읽어 정본과 짝짓는다."""
    tables, pad, _cards, pad_to_jp, _msgs = load_canon()
    out = []
    for key, path in dump_ui.FILES.items():
        buf = common.extract(path)
        col = 0 if key == "ED" else 1
        for name, ed, ed2, stride, n, n2 in dump_ui.TABLES:
            off = (ed, ed2)[col]
            if off is None:
                continue
            cnt = n2 if (col == 1 and n2) else n
            canon = tables[name]
            assert len(canon) >= cnt, f"{name}: 정본 {len(canon)}줄 < 원본 {cnt}줄"
            # 🔴 값이 붙는 표는 **JP 라벨 폭에 맞춰 채운다**(정본 `pad_to_jp` 주석).
            #   한글이 더 넓은 행이 있으면 표 전체를 그만큼 함께 민다.
            shift = 0
            if name in pad_to_jp:
                shift = max((_half(k) - _half(j) for j, k in canon[:cnt] if k), default=0)
                shift = max(shift, 0)
            for i, (jp_raw, at, _slack) in enumerate(dump_ui.read_table(buf, off, stride, cnt)):
                jp, kr = canon[i]
                # 🔴 **사전조건** — 원문이 우리 생각과 다르면 그 자리에서 실패한다.
                #   오프셋을 손으로 적었으니 배치가 어긋나면 엉뚱한 자리를 덮는다.
                assert jp_raw == jp, (
                    f"{key}/{name}[{i}] 0x{at:06x}: 원문이 다르다 {jp_raw!r}≠{jp!r}"
                )
                if kr and (w := pad.get(name)):
                    kr = kr + PAD * (w - len(kr))
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
                kr = lookup(jp, cat)
                # 🔴 조용히 건너뛰지 않는다 — 한 칸만 일본어로 남으면 화면에서 바로 튄다.
                assert kr, f"{key}/{name}[{i}] 0x{at:06x}: 정본에 없는 {cat} {jp!r}"
                if name == SUFFIXED_TABLE and rec_len(kr + WIDE_SP) <= stride:
                    kr += WIDE_SP  # 접미와 띄운다 — 아래 주석
                out.append((key, name, i, at, stride, jp, kr))
        # ── 파티 기본 이름 — 지명과 같은 수법(정본은 glossary), 자리만 손으로 적었다
        for k, at, fl in dump_ui.PERSON_SLOTS:
            if k != key:
                continue
            rec = buf[at : at + fl]
            z = rec.find(b"\x00")
            assert z > 0, f"{key} 0x{at:06x}: 인명 자리에 널이 없다"
            jp = rec[:z].decode("cp932")
            kr = lookup(jp, "person")
            assert kr, f"{key} 0x{at:06x}: 정본에 없는 인명 {jp!r}"
            # ⚠ 필드 **마지막 바이트가 `09`** 인 꼴이 있다(뜻은 모른다 — 씬 헤더도 같다).
            #   그 자리는 남겨야 하므로 쓰는 폭을 한 칸 줄인다. 널 패딩으로 덮으면
            #   원본이 무엇을 하려던 건지 모른 채 없애는 셈이다.
            w = fl - 1 if rec[fl - 1] == 9 else fl
            out.append((key, "파티 이름", at, at, w, jp, kr))
    return out


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
            return s, fl, jp, kr
    return None


def scn_rows(mm):
    """`[(파일, lba, size, 시작, 필드길이, JP, KR, 꼬리바이트)]`."""
    places = table("place")
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


def _card_text(jp, ch, title):
    """원본 꼴을 따라 우리 카드 문자열을 짓는다 — 여백만 다시 잰다."""
    head, _, rest = jp.partition("\n")
    lead = len(head) - len(head.lstrip("\t "))
    pre = head[:lead]  # `\t` 와 앞 여백
    tab = "\t" if pre.startswith("\t") else ""
    jp_body = head[lead:]
    kr_body = f"{ch}　{title}"
    pad1 = max(0, (lead - len(tab)) + (_half(jp_body) - _half(kr_body)) // 2)
    line2 = rest.split("\n")[-1]  # `      完%c`
    n2 = len(line2) - len(line2.lstrip(" "))
    return f"{tab}{' ' * pad1}{kr_body}\n\n{' ' * n2}끝%c"


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
                out.append((path, lba, size, i, nxt - i, t, _card_text(t, *want[hit])))
            i = j
    # ⚠ 정본 열둘은 **장 목록**이다 — 문자열 카드는 열뿐이고 ED2 의 序章·終章 은 그림 판으로만
    #   있다(`patch_gfx_cards.py`). 그래서 「정본에 있는데 디스크에 없다」는 실패가 아니다.
    #   반대 방향(디스크에 있는데 정본에 없다)은 위에서 여전히 막는다 — 그쪽이 사고다.
    only_gfx = [jp for jp in want if jp not in seen]
    assert len(only_gfx) <= 2, f"문자열 카드가 너무 많이 빈다: {only_gfx}"
    return out


def msg_rows(mm, msgs):
    """SAVE/LOAD·본체 RAM 문구 — `[(파일, lba, size, 오프셋, 여유, JP, KR)]`.

    🔴 **자리를 손으로 안 적는다.** 같은 JP 가 한 파일 안에 여러 번, 편마다 또 한 벌씩 있다
      (실측 61 자리 / 고유 30 종). 하나만 고치면 어떤 화면에서만 일본어가 남는다.
    ⚠ **긴 것부터 맞춘다** — 짧은 문구가 긴 문구의 부분 문자열인 자리가 있다
      (`ロードに失敗しました` ⊂ `ロードに失敗しました。`). 짧은 쪽을 먼저 물리면 긴 문장을
      잘라 먹는다(PS1 이 같은 자리에서 물렸다 — `patch_sys_ui.MSGS` 주석).
    """
    want = sorted(((jp, kr) for jp, kr in msgs), key=lambda x: -len(x[0]))
    enc = [(jp, kr, jp.encode("cp932")) for jp, kr in want]
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
            run = d[i:j]
            hit = next(((jp, kr, b) for jp, kr, b in enc if run.endswith(b)), None)
            if hit:
                nxt = j
                while nxt < len(d) and d[nxt] == 0:
                    nxt += 1
                seen.add(hit[0])
                out.append((path, lba, size, i, nxt - i, run[: len(run) - len(hit[2])], hit[1]))
            i = j
    missing = [jp for jp, _k in want if jp not in seen]
    assert not missing, f"디스크에서 못 찾은 문구 {len(missing)}: {missing[:3]}"
    return out


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
    """이름 대조용 정규화 — 반각 가나·중점·공백을 지운다.

    ⚠ 표엔 같은 이름이 **반각 가나**(`ｷｬﾘｵﾝ ｸﾛｰﾗｰ`)나 **중점 표기**(`ﾃﾞｽ･ｶﾞｰﾃﾞｨｱﾝ`)로도
      들어 있다. 정본은 한 꼴만 들고 있으므로 맞출 때만 눕힌다(쓸 때는 원문 그대로 안 쓴다).
    """
    t = unicodedata.normalize("NFKC", s)
    for ch in ("･", "・", " ", "\u3000"):
        t = t.replace(ch, "")
    return t


def name_canon(what):
    """`{JP: KR}` — **그 표의 범주를 먼저 본다**.

    🔴 범주를 무시하고 합쳐 읽으면 **같은 원문이 범주에 따라 다른 것을 가리키는** 자리가
       조용히 틀린다 — `カース` 는 아이템이 「커스」, 몬스터가 「카스」다(정본 머리말).
       합쳐 읽던 동안 몬스터 표에 아이템 이름이 들어가 있었다(2026-08-24).
    """
    first = {"몬스터": "monster", "아이템": "item", "주문": "item"}[what]
    canon = {}
    for cat in (first, "item", "monster", "person", "place"):
        for k, v in table(cat).items():
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
    #   `スライムＢ` = `スライム` + `B`. 붙일 때는 반각으로 붙인다(1바이트라 칸이 산다).
    #   ⚠ **Ｅ 에서 끊지 않는다** — 소환 목록은 `毒大ガエルＨ` 까지 간다(2026-08-24).
    if len(n) > 1 and "A" <= n[-1:] <= "Z" and n[:-1] in canon:
        return canon[n[:-1]] + n[-1]
    # `〜の書`(주문서)도 파생이다 — 밑말이 주문 이름이라 정본에 따로 안 둔다.
    if n.endswith("の書") and n[:-2] in canon:
        return canon[n[:-2]] + "의 서"
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


def name_pack(t, plan):
    """표 하나 → `(새 바이트, {포인터 오프셋: 새 값})`. 안 넣는 칸은 원문을 그대로 옮긴다."""
    buf, moves = bytearray(), {}
    for _at, jp, kr, ptrs in t["recs"]:
        new_at = t["off"] + len(buf)
        body = (
            b"".join(plan[c][0] if c in plan else c.encode("cp932") for c in kr)
            if kr
            else jp.encode("cp932")
        )
        buf += body + b"\x00"
        if len(buf) & 1:  # 2바이트 정렬 — 원본도 짝수 자리에 깐다
            buf += b"\x00"
        for p in ptrs:
            moves[p] = NAME_PTR_BASE + new_at
    assert len(buf) <= t["room"], f"{t['path']} {t['what']}: {len(buf)}B > 자리 {t['room']}B"
    t["used"] = len(buf)  # 뒤 여유는 시스템 메시지의 도너로 쓴다(`sys_pack`)
    return bytes(buf) + b"\x00" * (t["room"] - len(buf)), moves


# ── 시스템 메시지 — 전투·보상·상태 (2026-08-24) ──────────────────────────────
# 🔴 **정본은 sha1 키다**(`script/system.json`) — 원문 평문을 커밋에 안 남긴다
#    (루트 CLAUDE.md 「저작권」). 그래서 **자리도 손으로 안 적는다** — 파일의 문자열을
#    훑어 해시로 붙인다. 배치가 바뀌어도 따라온다.
# ⚠ 이름 표(`NAME_TABLES`) 범위는 건너뛴다 — 거기는 `name_rows` 몫이다.


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
    """시스템 메시지 — `[(파일, lba, size, 오프셋, 여유, 앞바이트, KR)]` (문구 표와 같은 꼴).

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
    canon, exact = doc["lines"], set(doc.get("exact", []))
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
                    and not hit[1].endswith(SYS_EXTRA_SUFFIX)
                ):
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
                            canon[sys_key(jp)],
                            ptrs,
                        )
                    )
            i = j
    missing = [k for k in canon if k not in seen]
    assert not missing, f"디스크에서 못 찾은 시스템 메시지 {len(missing)}: {missing[:4]}"
    return out


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
    for path, _l, _s, at, span, _pre, kr, _p in sysm:
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


def sys_pack(sysm, ntabs, plan):
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
        moves = {}
        # 🔴 **포인터가 없는 자리는 못 옮긴다** — 코드가 절대주소로 집는다. 제자리에 박고
        #   자리에서 뺀다. 넘치면 문안을 줄이는 수밖에 없다(2026-08-24, ED.BIN 0x26CF8).
        for _p, _l, _s, at, span, pre, kr, ptrs in recs:
            if ptrs:
                continue
            blob = pre + b"".join(plan[c][0] if c in plan else c.encode("cp932") for c in kr)
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
        want = sorted((r for r in recs if r[7]), key=lambda r: -(len(r[5]) + rec_len(r[6]) + 1))
        # ⚠ **몬스터 파일은 자리가 빠듯하다.** 그 파일들은 꽉 차 있어 기존 0런이 사실상
        #   없고(ED2MON01·02 는 **0바이트**), 풀은 「우리 레코드 자리」가 전부다. 우리 문안은
        #   원문보다 줄마다 2바이트쯤 길어서(원문 `が現れた。` 10B vs `이(가) 나타났다.` 12B —
        #   한국어는 띄어쓰기가 있다) **총량이 원본보다 커진다.**
        #   → 들어가는 줄만 정본에 넣는다. 거르는 건 `derive_encounters.py` 몫이고, 여기서는
        #     넘치면 예전대로 죽는다(조용히 넘기지 않는다).
        #   ⚠ 문안을 줄여 맞추지 않는다 — PS1 도 `이(가) 나타났다.` 라, 여기서만 줄이면
        #     **두 이식판의 표기가 갈린다**(2026-08-27 확인).
        for _p, _l, _s, _at, _span, pre, kr, ptrs in want:
            blob = pre + b"".join(plan[c][0] if c in plan else c.encode("cp932") for c in kr)
            blob += b"\x00"
            i = next((k for k, (_o, n) in enumerate(free) if n >= len(blob)), None)
            assert i is not None, f"{path}: 자리가 모자란다 — {kr!r} {len(blob)}B"
            o, n = free.pop(i)
            blk = max(a for a, _n in pool if a <= o)
            body[blk][o - blk : o - blk + len(blob)] = blob
            new_at = o + len(pre)  # 포인터는 **앞 바이트 다음**을 가리킨다(원본과 같게)
            for q in ptrs:
                moves[q] = ptr_base(path) + (o if len(pre) == 0 else new_at - len(pre))
            if n - len(blob) >= 2:
                free.append((o + len(blob), n - len(blob)))
                free.sort(key=lambda b: -b[1])
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
        # 이미 배정된 글자는 **자리를 지킨다** — 재배정하면 낡은 이미지의 폰트와 어긋난다.
        keep = {c: i for c, i in old.items() if c in need}
        taken = set(keep.values()) | reserved_slots(krs)
        pool = [i for i in free if i not in taken]
        old = dict(keep)
        for c in need:
            if c not in old:
                old[c] = pool.pop(0)
        old = {c: old[c] for c in need}
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
        ours, orig = rec_len(kr) - 1, len(jp.encode("cp932"))
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
            if "가" <= ch <= "힣" or ch.isascii() or ch.isspace():
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
        out[ch] = np.packbits(bits, axis=1).tobytes()
        assert len(out[ch]) == ASCII_STRIDE
    return out


def rec_len(kr):
    """레코드 바이트 수 — 한글은 슬롯 SJIS 2B, **반각은 1B**, 끝에 널 1B.

    🔴 낱말 사이는 **반각 공백**이다. 전각으로 두면 `마지막 들른 마을로` 가 21B 로 한 칸을
      넘긴다(PS1 도 같은 자리에서 물려 `에` 를 뺐다 — 유저 확정 2026-08-01). 이 렌더러엔
      반각짝 `/11ASCII.FON` 이 있고 **원본 레코드도 이미 반각을 쓴다**(`ＨＰ    ` ·
      `残り    ` · `ﾏﾆｭｱﾙ `) — 16px 타이틀(`patch_title.py`)과 갈리는 지점이다.
    """
    n = 0
    for ch in kr:
        try:
            n += len(ch.encode("cp932"))
        except UnicodeEncodeError:
            n += 2  # 슬롯 배정 = 전각 2B
    return n + 1


def encode(kr, stride, plan):
    """레코드 바이트 — 본문 + 널 + 0 채움. 넘치면 실패한다."""
    body = b"".join(plan[c][0] if c in plan else c.encode("cp932") for c in kr)
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
    """헤더 필드 — 우리 이름 + 널 채움 + **원본 꼬리 바이트 그대로**."""
    body = b"".join(plan[c][0] if c in plan else c.encode("cp932") for c in kr)
    assert len(body) < fl, f"{kr!r} 이 {len(body)}B 로 헤더 {fl}B 에 안 든다"
    return body + b"\x00" * (fl - 1 - len(body)) + bytes([tail])


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
    cards = card_rows(mm0, load_canon()[2])
    msgs = msg_rows(mm0, load_canon()[4])
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
    for path, _l, _s, at, fl, jp, kr, _t in scn:
        if rec_len(kr) > fl:
            print(f"  ❌ {path} 0x{at:05x} {jp}→{kr} {rec_len(kr)}B > 헤더 {fl}B")
            bad += 1
    for path, _l, _s, at, span, pre, kr in cards + msgs:
        if rec_len(kr) + (len(pre) if isinstance(pre, bytes) else 0) > span:
            head = len(pre) if isinstance(pre, bytes) else 0
            print(f"  ❌ {path} 0x{at:06x} {rec_len(kr) + head}B > {span}B: {kr!r}")
            bad += 1
    if bad:
        raise SystemExit(f"❌ 폭을 넘는 레코드 {bad}건 — 넣기 전에 문안을 줄인다")
    print("  ✅ 원문 대조 · 폭 검사 통과")
    if "--apply" not in sys.argv:
        return

    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not os.path.exists(dst):
        raise SystemExit(f"먼저 자막을 넣는다(patch_title.py --apply) — {dst} 가 없다")

    plan = slot_plan(
        [r[6] for r in rs] + [r[6] for r in scn] + [r[6] for r in cards + msgs + sysm] + names,
        refresh="--refresh" in sys.argv,
    )
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
            body = head + b"".join(plan[c][0] if c in plan else c.encode("cp932") for c in kr)
            bycard.setdefault((path, lba, size), {})[at] = body + b"\x00" * (span - len(body))
        csec = 0
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
        for path, (body, moves) in sys_pack(sysm, ntabs, plan).items():
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
        if gaps:
            alba, asize = files[FON_ASCII]
            for ch, g in bake_ascii(gaps).items():
                common.write_at(
                    f, alba, asize, ord(ch) * ASCII_STRIDE, g, label=f"{FON_ASCII} {ch!r}"
                )
            print(f"  반각 폰트 {FON_ASCII}: 원본에 없던 {''.join(gaps)!r} 구움")

        # ── 전각 폰트의 구멍 — 원본에 글리프가 없는 전각 글자(말줄임표 등)
        kgaps = kanji_gaps(
            [r[6] for r in rs] + [r[6] for r in scn] + [r[6] for r in cards + msgs + sysm] + names,
            common.extract(FON),
        )
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
        out.append(inv.get(w) or w.decode("cp932", "replace"))
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
        got = decode(rec[: rec.find(b"\x00")], inv)
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
    for ch, (_s, idx) in plan.items():
        o = idx * font.GLYPH_STRIDE
        if fon[o : o + font.GLYPH_STRIDE] != glyphs[ch]:
            bad.append(f"글리프 {ch!r} 슬롯 {idx} 가 안 들어갔다")
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
    for path, lba, size, at, _span, pre, kr, ptrs in sysm:
        if path not in cache:
            cache[path] = common.read_extent(mm2, lba, size)
        d = cache[path]
        # 포인터가 없는 자리는 제자리에 박았다 — 그 자리를 그대로 읽는다.
        a = int.from_bytes(d[ptrs[0] : ptrs[0] + 4], "big") - ptr_base(path) if ptrs else at
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
