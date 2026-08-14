#!/usr/bin/env python3
"""ED2 시스템 텍스트(ED2.EXE) 한글화 — 파티 이름 · 메뉴 · 전투 커맨드 · 지명 두 표.

**왜 따로인가.** 디스크에 실행파일이 둘이고(`ED.EXE` LBA 257 · `ED2.EXE` LBA 756)
**같은 UI 문자열을 각자 한 벌씩** 들고 있다. 공유가 아니라 **사본**이라 ED1 쪽만 고치면
ED2 화면은 일본어로 남고, 따로 번역하면 **한 디스크가 두 말을 한다.**

그래서 새로 번역하지 않는다 — **ED1 정본(`patch_sys_ui.UI`·`PLACES`)을 원문으로 대조해
옮긴다.** 오프셋이 아니라 **원본 SJIS 문자열**로 짝을 짓기 때문에 두 EXE 의 배치가 달라도
어긋나지 않고, 한쪽을 고치면 다른 쪽이 따라온다(실측: 메뉴 52건 중 51건이 ED1 정본으로
덮인다 — `呪文能力` 하나만 ED2 에 새로 있다).

지명은 표가 둘이다. **HUD 판(14B)** 은 화면 우하단에 뜨는 것이고, **워프 메뉴(16B)** 는
목적지 목록이라 접미(`の町`·`の港`)가 붙는다. 정발 ED2 의 워프 목적지 표
(`dos_kr/ED2/F_000` 30곳)가 후자의 정본이다.

⚠ **둘 다 붙여 쓴다** — 슬롯이 좁은 층이라 그렇다(`늑대입`). 대사에서는 띄운다
(`늑대의 입`) — [policy.md](../docs/policy.md) 「표기 방침」.

⚠ **폰트가 먼저다.** ED2.EXE 에 한글 글리프를 굽는 건 `reinsert_kr_pilot` 이 한다
(`font_map.FONT_BASE`). 이 스크립트만 돌리면 글자가 안 나온다.

전제: `build.py` 체인 안에서 재삽입 뒤에 돈다 — 이미지 제자리 갱신.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hangul_map as H  # noqa: E402
import patch_sys_ui as P  # noqa: E402
from common import BUILD_DIR, extract, write_user_data  # noqa: E402

ED2_LBA, ED2_SIZE = 756, 872448
IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"

# 파티 이름 (0x800, 12B 슬롯) — 정발 ED2 코퍼스 실측(아트라스 188회 · 플로라 101 ·
# 신디 66 · 란도 56). ED1 party 가 ED.EXE 0x800 에 있는 것과 같은 자리다.
PARTY = {
    "アトラス": "아트라스",
    "ランドー": "란도",
    "フローラ": "플로라",
    "シンディ": "신디",
}

# ED1 에 없는 메뉴 라벨 — 나머지는 `patch_sys_ui.UI` 에서 원문으로 끌어온다.
# ⚠ `呪文` 은 「주문」이다(유저 개념 정정 2026-08-13, policy). 마법이 아니다.
MENU_EXTRA = {"呪文能力": "주문능력"}

# 지명 — **고유명은 ED1 과 한 표기**여야 한다(policy 「표기 방침」). ED1 에 있는 것은
# `patch_sys_ui.PLACES` 에서 원문으로 끌어오고, ED2 에만 나오는 것만 여기 적는다.
# 근거는 정발 ED2 코퍼스 실측 — 이슈타(29회) · 이즈(28) · 프로스(25) · 큐베라(15) ·
# 아훌(9) · 유이시스(8) · 베른(5) · 네사(4) · 사피아(3) · 그로스토스(3) · 테크니카(13) ·
# 모건(17) · 보아드(55) · 아네스(2). `ウイル` 은 대사에 「윌」로 나온다.
PLACES_ED2 = {
    "クルス": "크루즈",
    "ベルガ": "베르가",
    "ネリア": "네리아",
    "ロンド": "론도",
    "ラルファ": "랄파",
    "シリカ": "시리카",
    "ヨルド": "요르도",
    "ナッシュ": "낫슈",
    "セレ": "세레",
    "スエル": "스엘",
    "アムダ": "암다",
    "セダル": "세달",
    "ルドラ": "루드라",
    "カウル": "카울",
    "ナスール": "나슬",
    "ファエト": "파에토",
    "コルクス": "콜크스",
    "ボアード海運": "보아드해운",
    "イシュタ": "이슈타",
    "アフル": "아훌",
    "イズー": "이즈",
    "キュベラ": "큐베라",
    "プロス": "프로스",
    "ウイル": "윌",
    "ベルン": "베른",
    "ユイシス": "유이시스",
    "奈落の口": "나락의입",
    "アネスの塔": "아네스의탑",
    "サピアの湖": "사피아호수",
    "モーガンの家": "모건의집",
    "ネサの辺土": "네사의변토",
    "グロストス城": "그로스토스성",
    "テクニカ": "테크니카",
    "溶岩炉": "용암로",
    "玉座の間": "옥좌의방",
    "中庭": "안뜰",
    "スロット１": "슬롯1",
    "スロット２": "슬롯2",
}

# ── ED2 아이템·주문 이름 ────────────────────────────────────────────────────
# ED1 정본(`patch_items.NAMES`·`MONSTERS`)이 153건 중 55건을 덮는다 — 두 편이 무기·방어구·
# 도구를 공유해서다. 여기엔 **ED2 에만 있는 것**만 적는다.
#
# 정발 소재: `originals/kr/dos-ed2/ED2MAIN.EXE 0x14A775` 에 27개짜리 14B stride 표가 있다
# (은의 플레이트 · 지팡이의 파편 · 투시 안경 · 철 아령 · 변환로의 열쇠 …).
#
# ⚠ **보통명사 아이템 둘은 ED2 정발을 따른다**(유저 확정 2026-08-14) — `幅広のつるぎ` 와
# `くさりかたびら` 는 고유명사가 아니라 원음 판정이 안 서는 자리다. ED1 은 `대형검`·
# `미늘 갑옷` 을 유지하므로 **두 편이 갈린다** — 의도한 결정이다.
NAMES_ED2 = {
    # 주문 (ED1 에 없는 것만)
    "ストール": "스톨",
    "ブラムナ": "브람나",
    "ヒュドナ": "휴도나",
    "エント": "엔트",
    "ビス": "비스",
    "ビスナ": "비스나",
    "レストナ": "레스토나",
    # 도구·시나리오 아이템
    "大笑い袋": "웃음보따리",
    "透視メガネ": "투시 안경",
    "鉄アレイ": "철 아령",
    "フレイアの微笑": "프레이아의 미소",
    "変換炉のカギ": "변환로의 열쇠",
    "光の杖": "빛의 지팡이",
    "切符": "표",
    "密造酒": "밀조주",
    "ランプ": "램프",
    "竜の涙": "용의 눈물",
    "ビキニ": "비키니",
    "布の服": "천 옷",
    # ⚠ ED1 과 갈리는 둘 (위 주석)
    "幅広のつるぎ": "날 넓은 칼",
    "くさりかたびら": "쇠사슬옷",
}

# 이름 구획은 **통째로 다시 채운다**(`repack_names`) — 칸 하나하나에 맞추지 않는다.
# ⚠ 처음엔 제자리 치환만 해서 칸이 좁은 다섯을 줄여 썼는데(`성지팡이`·`빛의 봉` …),
# ED2 정발은 `성스러운 지팡이`·`빛의 지팡이`·`얼음의 지팡이`·`용의 눈물` 이다(유저 지적
# 2026-08-14). 이름을 줄일 게 아니라 **자리를 옮기는 게 맞다** — ED1 도 그렇게 한다.
# 안전 근거: 이 구획의 이름 **153건이 전부 `lui`/`addiu` 로 참조된다**(참조 0건 0, 실측).
# 그래서 옮긴 뒤 `patch_items.redirect` 가 참조를 전부 갱신할 수 있다.
# ⚠ 시나리오 칸은 `0xD4930` 까지면 **16B 모자란다**(필요 208 / 칸 192). 바로 뒤
# `0xD4934~0xD494F` 가 28B 0런이라 거기까지 넓혔다 — 다음 문자열(`たち` 0xD4950) 전까지다.
REPACK = ((0x800, 0xF44, "ED2 이름"), (0xD4870, 0xD4950, "ED2 시나리오 아이템"))

# 주문책 — `Xの書` 는 **주문 이름 + 「의 책」**이다(`呪文` 은 「주문」, policy 「표기 방침」).
# 이름은 ED1 정본에서 끌어오므로 여기 다시 적지 않는다 — 주문 표기를 고치면 책도 따라온다.
BOOK_SUFFIX = "의 책"

# 워프 메뉴(16B) 접미 — 정발 `F_000` 30곳의 표기를 따른다. 핵심어는 위 표를 쓰고
# 접미만 여기서 붙인다(같은 지명이 두 표에서 다른 말을 하지 않게).
SUFFIX = {"の町": "", "の村": "마을", "の港": "항", "の鉱山": "광산", "の城": "성"}


def _enc(kr):
    """한글은 슬롯 SJIS 로, 나머지(숫자·부호)는 원래 SJIS 로 — `patch_sys_ui.enc_msg` 관용.

    ⚠ `H.encode_kr` 은 완성형 밖 글자에 죽는다. `슬롯1` 의 `1` 이 그 자리였다.
    """
    out = bytearray()
    for ch in kr:
        out += H.encode_kr(ch) if "가" <= ch <= "힣" else ch.encode("shift_jis")
    return bytes(out)


def _jp_at(buf, off):
    end = buf.find(b"\x00", off)
    try:
        return buf[off:end].decode("cp932")
    except Exception:  # noqa: BLE001 — 바이너리 구간
        return None


def positional():
    """{ED2 오프셋: ED1 우리표기} — 두 UI 블록을 **자리로** 짝짓는다.

    ⚠ **문자열로 짝지으면 안 된다.** ED1 은 같은 원문을 문맥마다 다르게 옮겼다 —
    `強さ` 가 셋(파티 메뉴 `상태` · 전투 커맨드 `능력치` · 능력치 창 `힘`)이고
    `逃げる` 가 둘(`도망감`/`도망간다`)이다. 첫 값이 전부에 붙어 **능력치 창에
    「상태 6」이 떴다**(유저 QA 2026-08-14).

    ED2 블록은 ED1 과 같은 순서인데 `ＳＡＶＥ`·`ＬＯＡＤ` 처럼 **더 있는 항목**이 있어
    단순 zip 이 뒤부터 통째로 밀린다. 그래서 삽입을 견디는 시퀀스 정렬로 맞춘다.
    """
    from difflib import SequenceMatcher

    ed = extract(P.ED_LBA, P.ED_SIZE)
    a = [(o, _jp_at(ed, o), P.UI[o]) for o in sorted(P.UI) if 0xBE290 <= o <= 0xBE5C6]
    b = _walk(extract(ED2_LBA, ED2_SIZE), 0x99C84, 0x9A030)
    out, pad = {}, {}
    sm = SequenceMatcher(None, [x[1] for x in a], [x[1] for x in b], autojunk=False)
    for i, j, n in sm.get_matching_blocks():
        for d in range(n):
            o1, _jp, kr = a[i + d]
            o2 = b[j + d][0]
            out[o2] = kr
            if o1 in P.VALUE_PAD:  # 값 메뉴 — JP 렌더폭에 맞춰야 값 컬럼이 선다
                pad[o2] = P.VALUE_PAD[o1]
            if o1 in P.FIELD_MENU:  # SAVE/LOAD 칸에 맞춰 벌려 쓴다
                pad[o2] = -P.FIELD_WIDTH
    return out, pad


def _walk(buf, lo, hi):
    out, i = [], lo
    while i < hi:
        if buf[i] == 0:
            i += 1
            continue
        e = buf.find(b"\x00", i)
        s = _jp_at(buf, i)
        if s:
            out.append((i, s))
        i = e + 1
    return out


def ed1_canon():
    """{원본 JP: 우리 표기} — ED1 정본을 **원문으로** 뒤집어 만든다.

    ⚠ 오프셋으로 옮기면 안 된다. 두 EXE 는 배치가 다르고, ED1 표를 고쳤을 때 ED2 가
    안 따라오면 그때부터 한 디스크가 두 말을 한다.
    """
    ed = extract(P.ED_LBA, P.ED_SIZE)
    out = {}
    for off, kr in P.UI.items():
        jp = _jp_at(ed, off)
        if jp:
            out.setdefault(jp, kr)
    for jp, kr in list(P.PLACES) + list(P.SCN_PLACES):
        out.setdefault(jp, kr)
    return out


def plan():
    """[(오프셋, JP, KR, 슬롯B)] — 쓸 것 전부. 슬롯 초과는 여기서 걸러 보고한다."""
    import re

    buf = extract(ED2_LBA, ED2_SIZE)
    canon = ed1_canon()
    canon.update(PARTY)
    canon.update(MENU_EXTRA)
    canon.update(PLACES_ED2)
    canon.update(NAMES_ED2)
    import patch_items as PI

    canon.update({k: v for k, v in PI.NAMES.items() if k not in canon})
    canon.update({k: v for k, v in PI.MONSTERS.items() if k not in canon})
    # `Xの書` 는 주문 이름에서 파생한다 — 한 번 적으면 이름 표기를 고칠 때 같이 움직인다.
    for jp, kr in list(canon.items()):
        canon.setdefault(jp + "の書", kr + BOOK_SUFFIX)

    by_off, pad = positional()
    rows, over = [], []
    for lo, hi in ((0x99C84, 0x9A030), (0x9A030, 0x9A280), (0x9A280, 0x9A550)):
        i = lo
        while i < hi:
            if buf[i] == 0:
                i += 1
                continue
            end = buf.find(b"\x00", i)
            jp = _jp_at(buf, i)
            if not jp:
                i = end + 1
                continue
            kr = by_off.get(i) or canon.get(jp)
            if kr is None and lo == 0x9A030:  # 워프 메뉴 — 접미를 떼고 다시 본다
                m = re.match(r"(.+?)(の町|の村|の港|の鉱山|の城)$", jp)
                if m and m.group(1) in canon:
                    kr = canon[m.group(1)] + SUFFIX[m.group(2)]
            if kr:
                # 쓸 수 있는 공간 = **다음 문자열 시작까지**(널 패딩 포함).
                # ⚠ 널 종단 다음부터 세야 한다. 처음에 `i + 1` 에서 시작했더니 문자열
                # 한복판이라 while 이 한 발도 안 나가고 **슬롯 = 문자열 길이**가 됐다 —
                # 16B 칸에 든 `竜の卵`(7B)이 「8B 라 안 들어간다」로 잘못 걸렸다.
                nxt = end
                while nxt < hi and buf[nxt] == 0:
                    nxt += 1
                slot = nxt - i
                enc = _enc(kr)
                t = pad.get(i)
                if t is not None and t < 0:  # 칸 채움(벌려 쓰기)
                    enc = P.justify(kr, -t, slot)
                elif t is not None:  # 값 메뉴 — JP 렌더폭까지 패딩
                    h = t - P.render_width(kr)
                    if h > 0:
                        enc += b"\x81\x40" * (h // 2) + b" " * (h % 2)
                (rows if len(enc) + 1 <= slot else over).append((i, jp, kr, slot, enc))
            i = end + 1
    return rows, over


def repack_names(buf, canon):
    """이름 구획을 KR 로 다시 채우고 참조를 갱신한다. 반환: 옮긴 이름 수."""
    import patch_items as PI

    n = 0
    for lo, hi, label in REPACK:
        names = _walk(buf, lo, hi)
        moved, cur, packed = {}, lo, bytearray()
        for off, jp in names:
            kr = canon.get(jp)
            kb = (_enc(kr) if kr else jp.encode("shift_jis")) + b"\x00"
            kb += b"\x00" * (-len(kb) % 4)  # 정렬은 관례(코드는 바이트 접근)
            assert cur + len(kb) <= hi, f"{label}: 예산 초과 @{jp} ({cur - lo}/{hi - lo}B)"
            moved[PI.ram_of(off)] = PI.ram_of(cur)
            packed += kb
            cur += len(kb)
        buf[lo:hi] = packed.ljust(hi - lo, b"\x00")
        PI.redirect(buf, moved)
        print(f"  {label}: {len(names)}개 재packing ({len(packed)}/{hi - lo}B)")
        n += len(names)
    return n


def apply():
    rows, over = plan()
    for off, jp, kr, slot, enc in over:
        print(f"  ⚠ 슬롯 초과 — {off:#07x} {jp!r} → {kr!r} ({len(enc) + 1}B > {slot}B)")
    buf = bytearray(extract(ED2_LBA, ED2_SIZE, path=IMG))
    canon = ed1_canon()
    canon.update(PARTY)
    canon.update(MENU_EXTRA)
    canon.update(PLACES_ED2)
    canon.update(NAMES_ED2)
    import patch_items as PI

    canon.update({k: v for k, v in PI.NAMES.items() if k not in canon})
    canon.update({k: v for k, v in PI.MONSTERS.items() if k not in canon})
    for jp, kr in list(canon.items()):
        canon.setdefault(jp + "の書", kr + BOOK_SUFFIX)
    n_names = repack_names(buf, canon)
    for off, _jp, _kr, slot, enc in rows:
        b = enc + b"\x00"
        buf[off : off + slot] = b + b"\x00" * (slot - len(b))
    with open(IMG, "r+b") as f:
        n = write_user_data(f, ED2_LBA, bytes(buf), label="ED2 시스템 UI (ED2.EXE)")
    print(
        f"ED2.EXE: 섹터 {n}개 수정 — 시스템 문자열 {len(rows)}건"
        + (f" (초과 {len(over)})" if over else "")
    )
    return len(over)


if __name__ == "__main__":
    if "--plan" in sys.argv:
        rows, over = plan()
        for off, jp, kr, slot, _e in rows:
            print(f"  {off:#07x} [{slot:>3}B] {jp:<12} → {kr}")
        print(f"\n쓸 것 {len(rows)}건 · 슬롯 초과 {len(over)}건")
        sys.exit(0)
    sys.exit(1 if apply() else 0)
