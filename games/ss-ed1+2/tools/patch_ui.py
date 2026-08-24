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
import dump_ui
import font
from fonts import convert_chars
from glossary import lookup, table

CANON = os.path.join(common.GAME_DIR, "script", "ui.json")
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
                kr = lookup(jp, cat)
                # 🔴 조용히 건너뛰지 않는다 — 한 칸만 일본어로 남으면 화면에서 바로 튄다.
                assert kr, f"{key}/{name}[{i}] 0x{at:06x}: 정본에 없는 {cat} {jp!r}"
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
    for path in dump_ui.FILES.values():
        lba, size = next((l, s) for p, l, s in common.iso_files(mm) if p == path)
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
    for path in dump_ui.FILES.values():
        lba, size = next((l, s) for p, l, s in common.iso_files(mm) if p == path)
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


def _nname(s):
    """이름 대조용 정규화 — 반각 가나·중점·공백을 지운다.

    ⚠ 표엔 같은 이름이 **반각 가나**(`ｷｬﾘｵﾝ ｸﾛｰﾗｰ`)나 **중점 표기**(`ﾃﾞｽ･ｶﾞｰﾃﾞｨｱﾝ`)로도
      들어 있다. 정본은 한 꼴만 들고 있으므로 맞출 때만 눕힌다(쓸 때는 원문 그대로 안 쓴다).
    """
    t = unicodedata.normalize("NFKC", s)
    for ch in ("･", "・", " ", "\u3000"):
        t = t.replace(ch, "")
    return t


def name_kr(jp, canon):
    """JP 이름 → KR. 못 찾으면 None(부르는 쪽이 실패로 친다)."""
    if jp in canon:
        return canon[jp]
    n = _nname(jp)
    if n in canon:
        return canon[n]
    # 🔴 **변종 접미**(Ａ~Ｅ)는 정본에 안 넣는다 — 같은 몸이 넷씩 늘어 표가 네 배가 된다.
    #   `スライムＢ` = `スライム` + `B`. 붙일 때는 반각으로 붙인다(1바이트라 칸이 산다).
    if n[-1:] in "ABCDE" and n[:-1] in canon:
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
    canon = {}
    for cat in ("item", "monster", "person", "place"):
        for k, v in table(cat).items():
            canon.setdefault(k, v)
            canon.setdefault(_nname(k), v)
    out, miss = [], []
    for key, off, n, anchor, what in NAME_TABLES:
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


def _ptrs_to(d, at):
    """파일 안에서 `at` 을 가리키는 BE32 포인터들의 오프셋."""
    pat = (NAME_PTR_BASE + at).to_bytes(4, "big")
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
    return bytes(buf) + b"\x00" * (t["room"] - len(buf)), moves


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
        taken = set(keep.values())
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
    """
    orig = common.extract(path)
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
    mm0.close()
    _f0.close()
    n_kr = sum(1 for r in rs if r[6])
    print(f"표 {len({(r[0], r[1]) for r in rs})} · 레코드 {len(rs)} · 한글 {n_kr}")
    print(
        f"씬 지명 헤더 {len(scn)}곳 · {len({r[0] for r in scn})}파일 · {len({r[5] for r in scn})}종"
    )
    print(f"챕터 카드 {len(cards)}장 · SAVE/LOAD 문구 {len(msgs)}자리")
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
        [r[6] for r in rs] + [r[6] for r in scn] + [r[6] for r in cards + msgs] + names,
        refresh="--refresh" in sys.argv,
    )
    print(f"  한글 슬롯 {len(plan)}자")

    _f, mm = common.open_image(dst)
    files = {p: (lba, size) for p, lba, size in common.iso_files(mm)}
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

        # ── 반각 폰트 — 원본에 없는 글리프만 채운다(온점 등)
        gaps = ascii_gaps(
            [r[6] for r in rs] + [r[6] for r in scn] + [r[6] for r in cards + msgs] + names,
            common.extract(FON_ASCII),
        )
        if gaps:
            alba, asize = files[FON_ASCII]
            for ch, g in bake_ascii(gaps).items():
                common.write_at(
                    f, alba, asize, ord(ch) * ASCII_STRIDE, g, label=f"{FON_ASCII} {ch!r}"
                )
            print(f"  반각 폰트 {FON_ASCII}: 원본에 없던 {''.join(gaps)!r} 구움")

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
