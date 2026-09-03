"""한글 ↔ 글리프 자리 배정 — **커밋되는 정본**.

한글은 「원본이 안 쓰는 한자 자리를 덮어쓰고, 문안은 그 자리의 코드로 인코딩」해서 넣는다.
색인이 곧 문자 코드라(`font.py`) 자리를 정하면 그게 그대로 인코딩이 된다.

🔴 **배정은 파생물이 아니라 정본이다.** 「안 쓰는 자리」는 덤프에서 나오는데, 소재를 하나 더
   열면(새 대사 구역·새 낱말 표) 쓰는 코드가 늘어 **빈 자리 목록이 통째로 밀린다.**
   그러면 이미 넣은 문안이 **전부 다른 글자로 읽힌다.** 그래서 한 번 정하면
   `hangul_map_<disc>.json` 에 박아 두고 빌드는 그 파일만 읽는다
   (루트 `CLAUDE.md` 「제1 원칙 — 빌드는 결정적이어야 한다」).
   갱신은 `--freeze` 로 **명시적으로만**. 그때 이미 넣은 문안은 다시 구워야 한다.

🔴 **디스크마다 따로 든다.** ED3·ED4 는 코드표가 다르고(카나 탈락이 다르다) 쓰는 한자도
   달라서, 한 벌로 묶으면 한쪽이 남의 글자를 덮는다.

🔴 **자리는 「번역이 물러나게 한 한자」에서 나온다.**

폰트는 ED3 1,900 · ED4 1,990 글리프에서 끝나고, **원본이 그 중 대부분을 쓴다.** 그래서
지금 이 순간 비어 있는 자리는 **ED3 125 · ED4 119** 뿐이다. 그런데 우리가 문안을 한글로
바꾸면 그 자리에 있던 한자는 **더 이상 아무도 안 쓴다** — 자리가 그만큼 비어난다.

    지금            빈 자리 125 / 119
    대사를 다 옮기면 빈 자리 **1,219 / 1,139**   (대사 전용 한자 1,094 / 1,020)
    실행파일 낱말까지 옮기면 사실상 폰트 전체

⇒ **폰트 배열을 넓힐 필요가 없다.** `used_codes` 는 「원본이 쓰는 코드」가 아니라
   **「우리 패치 뒤에도 일본어로 남는 코드」**를 센다. 번역이 늘면 자리가 는다.

⚠ 그래서 **배정은 번역이 늘 때마다 바뀔 수 있다.** 그게 되는 이유는 `build.py` 가 매번
   **정본에서 이미지를 통째로 다시 굽기** 때문이다 — 이미 넣은 문안이 옛 배정으로 남아
   있는 일이 없다. 🔴 **배포한 뒤에는 다르다** — 한 번 내보내면 그 배정은 못 옮긴다
   (옛 패치를 깐 사람의 세이브·차분이 어긋난다). 배포 시점에 얼려 못 박는다.

⚠ **폰트 끝은 `font.font_end` 로 잰다.** 옛 `glyph_count`(빈 칸 연속 추정)는 ED3 를 5,413 로
   봤는데 **진짜는 1,900** 이다 — 그 뒤는 낱말 표와 문자열 풀이라, 거기 구우면 이름·아이템
   표를 통째로 덮어쓴다. 하마터면 그렇게 구울 뻔했다(2026-09-03).

⚠ **실행파일 꼬리의 0런은 빈 공간이 아니다**(ED3 32KB · ED4 32KB). 인게임에서 읽어 보니
   포인터가 들어 있었다 — 런타임 버퍼다(「빈 공간의 VAB 함정」과 같은 자리).

⚠ **카나·기호 대역(0x00~카나 끝)은 안 건드린다** — 시스템이 우리 덤프 밖에서 쓸 수 있다.
"""

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dump_names
import exetext
import font
import scriptmap
import textenc

# 한글 말고 자리를 따로 받아야 하는 글자 — **코드표에 없어서** 그렇다.
# 🔴 공백: 원본 일본어엔 띄어쓰기가 없어 표에 아예 없다(2026-09-03 ED4 PoC 에서 드러났다).
#    빈 글리프를 구우면 화면에서 12px 공백이 된다.
EXTRA = " "


def map_path(disc):
    return os.path.join(common.ROOT, f"hangul_map_{disc}.json")


def ksc_syllables():
    """완성형(KS X 1001) 한글 음절 2,350자 — **가나다순**(코드 순서가 곧 가나다순)."""
    out = []
    for hi in range(0xB0, 0xC9):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes((hi, lo)).decode("euc_kr")
            except UnicodeDecodeError:
                continue
            if "가" <= ch <= "힣":
                out.append(ch)
    return out


def used_codes(disc, after_patch=True):
    """**우리 패치 뒤에도 일본어로 남는** 코드. 그게 곧 「못 쓰는 자리」다.

    `after_patch=False` 면 원본이 쓰는 코드 전부(참고용).

    ⚠ **멤버의 u16 을 통째로 세면 안 된다** — 스크립트는 바이트 스트림이라 opcode 가 코드처럼
      보인다(그렇게 셌더니 5,413 중 5,077 이 「쓰인다」로 나와 빈 자리가 336 뿐이었다).
      **파서가 문자열로 인정한 조각**만 센다.
    """
    import glossary
    import script as script_canon

    canon = script_canon.load(disc) if after_patch else {}
    words = set(glossary.flat(disc)) if after_patch else set()
    used = set(textenc.CONTROL)
    for path, (lba, size) in sorted(common.iso_files(disc).items()):
        if "/SC" not in path or not path.endswith(".DAT"):
            continue
        data = common.read_lba(disc, lba, size)
        try:
            _, ents = common.arc_parse(data)
        except common.ArchiveError:
            continue
        for nm, off, sz in ents:
            if not nm.endswith(".BIN") or sz < 8:
                continue
            # ⚠ 규격 밖 멤버(`*B.BIN` 등)는 건너뛴다 — 가려내는 건 `check_script.py` 몫이다.
            #   여기서 조용히 넘기는 게 걱정되면 그쪽 수치를 본다(ED3 452/595 · ED4 356/481).
            try:
                info = scriptmap.parse(data[off : off + sz])
            except (struct.error, scriptmap.ScriptError, IndexError, ValueError):
                continue
            done = canon.get((path, nm), {})
            for i, (_, codes) in enumerate(info["segments"]):
                if i in done:
                    continue  # 이 조각은 한글로 바뀐다 — 여기 쓰인 한자는 물러난다
                used.update(codes)

    cm = textenc.charmap(disc)
    lba, size = common.iso_files(disc)[dump_names.EXE[disc]]
    exe = common.read_lba(disc, lba, size)
    for t in exetext.scan_tables(exe, cm):
        for x in struct.unpack_from(f"<{t['n']}H", exe, t["table"]):
            codes, _ = exetext.raw_string(exe, t["base"] + x)
            if textenc.decode(codes or [], disc) in words:
                continue  # 이 낱말은 정본이 옮긴다
            used.update(codes or [])
    # 표를 못 찾은 구역도 화면에 나간다 — 라벨 붙인 낱말 구역 전량을 더한다.
    labels = dump_names.REGIONS[disc]
    rev = {v: k for k, v in cm.items()}
    for r in dump_names.split(dump_names.regions(dump_names.strings(exe, cm)), labels):
        for text in r["items"]:
            if text in words:
                continue
            used.update(rev[ch] for ch in text if ch in rev)
    return used


def test_slots(disc):
    """[코드] — **시험 빌드용**. 원본이 쓰든 말든 폰트 자리를 전부 빌린다.

    🔴 이 자리로 구운 이미지는 **배포물이 아니다.** 안 옮긴 문안이 엉뚱한 글자로 나온다.
       쓰는 이유는 하나 — 지금 보려는 것(메뉴·HUD·타이틀)을 **오늘 화면에서 확인**하려고.
       본 빌드는 `free_slots` 를 쓴다(원본과 안 부딪히는 자리만).
    """
    exe, _, _ = font.exe_bytes(disc)
    first = max(textenc.kana_map(disc)) + 1
    n = font.font_end(exe, disc)
    return [c for c in range(first, n) if font.read_glyph(exe, c, disc).any()]


def free_slots(disc, used=None):
    """[코드] — 안 쓰는데 **그림이 있는** 자리. 카나 끝 다음부터."""
    used = used_codes(disc) if used is None else used
    exe, _, _ = font.exe_bytes(disc)
    first = max(textenc.kana_map(disc)) + 1
    n = font.font_end(exe, disc)
    return [c for c in range(first, n) if c not in used and font.read_glyph(exe, c, disc).any()]


def needed_chars(disc):
    """[글자] — 자리를 받아야 하는 것, **급한 순서대로**.

    🔴 순서가 곧 우선순위다. 자리가 모자랄 때 **뒤가 잘리기 때문**이다:
      ① 공백 ② 대사 정본(많이 쓰는 것부터) ③ UI 문안 ④ 고유명사 정본.
      대사가 먼저인 이유는 **자리를 비워 주는 쪽이 대사**이기 때문이다 — 대사를 옮겨야
      한자가 물러나고, 그래야 나머지가 들어갈 자리가 생긴다.

    ⚠ 코드표에 이미 있는 글자(숫자·부호)는 뺀다.
    """
    import collections

    import glossary
    import script as script_canon
    import uitext

    have = set(textenc.charmap(disc).values()) | set(textenc.CONTROL.values())
    freq = collections.Counter()
    for lines in script_canon.load(disc).values():
        for row in lines.values():
            freq.update(row["kr"])
    ui = collections.Counter()
    for row in uitext.load(disc).values():
        ui.update(row["kr"])
    names = set()
    for kr in glossary.flat(disc).values():
        names.update(kr)

    out = list(EXTRA)
    for src in (freq, ui):
        out += [ch for ch, _ in src.most_common() if ch not in have and ch not in out]
    out += sorted(ch for ch in names if ch not in have and ch not in out)
    return out


def assign(disc, free=None, chars=None, keep=None):
    """{글자: 코드} — **이미 배정된 것은 안 옮기고** 새 글자만 빈 자리에 덧붙인다.

    🔴 이미 배정된 글자는 안 옮긴다 — 옮기면 이미 구운 이미지의 문안이 통째로 다른 글자로
       읽힌다. 그래서 `keep`(정본)이 먼저고, 새 글자는 남은 자리를 **급한 순서대로** 가져간다.
    반환: (배정, 자리가 모자라 못 넣은 글자 목록)
    """
    chars = needed_chars(disc) if chars is None else list(chars)
    keep = keep or {}
    free = sorted(free if free is not None else free_slots(disc))
    taken = set(keep.values())
    pool = [c for c in free if c not in taken]
    out = dict(keep)
    short = []
    for ch in chars:
        if ch in out:
            continue
        if not pool:
            short.append(ch)
            continue
        out[ch] = pool.pop(0)
    return out, short


def load(disc):
    p = map_path(disc)
    if not os.path.exists(p):
        raise SystemExit(f"배정 정본이 없다: {p}\n  먼저: hangul_map.py --disc {disc} --freeze")
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    return {ch: c for ch, c in zip(doc["chars"], doc["codes"], strict=True)}


def encode(text, disc, table=None):
    """문안 → 코드열. 한글·공백은 배정 자리로, 나머지는 코드표로.

    ⚠ 표에 없는 글자면 **곧바로 운다** — 조용히 빠지면 화면에서만 사라진다
      (`・`(U+30FB) vs `·`(U+00B7), `〜` vs `~` 같은 자리에서 잘 걸린다).
    """
    table = load(disc) if table is None else table
    rev = {v: k for k, v in textenc.charmap(disc).items()}
    for code, ch in textenc.CONTROL.items():
        rev.setdefault(ch, code)
    out = []
    for ch in text:
        if ch in table:
            out.append(table[ch])
        elif ch in rev:
            out.append(rev[ch])
        else:
            raise KeyError(f"{disc}: 넣을 수 없는 글자 {ch!r} (U+{ord(ch):04X})")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--freeze", action="store_true", help="배정을 정본으로 박는다")
    ap.add_argument("--check", action="store_true", help="정본이 원본과 부딪히지 않나 (게이트)")
    a = ap.parse_args()
    common.verify_source(a.disc)
    used = used_codes(a.disc)
    free = free_slots(a.disc, used)
    keep = load(a.disc) if os.path.exists(map_path(a.disc)) else {}
    if a.check and not os.path.exists(map_path(a.disc)):
        print(f"⏭ {a.disc}: 글리프 자리 정본이 아직 없다 (쓸 수 있는 자리 {len(free)})")
        return 0
    table, short = assign(a.disc, free, keep=keep)
    chars = sorted(table, key=lambda c: table[c])
    print(
        f"{a.disc}: 배정 {len(chars):,}자 · 패치 뒤에도 일본어로 남는 코드 {len(used):,} · "
        f"쓸 수 있는 자리 {len(free):,} (남는 {max(0, len(free) - len(chars)):,})"
    )
    # 🔴 **끝까지 옮기면 자리가 되나** — 이게 「폰트를 넓혀야 하나」의 답이다.
    exe, _, _ = font.exe_bytes(a.disc)
    end = font.font_end(exe, a.disc)
    first = max(textenc.kana_map(a.disc)) + 1
    print(f"  전망: 폰트 자리 {end - first} 중, 대사·낱말을 다 옮기면 대부분이 빈다")
    print("        (같은 작품 전량 한국어의 고유 음절은 1,227자 — 새턴 ED3 실측)")
    if short:
        print(
            f"  ⬜ 자리가 모자라 못 넣은 글자 {len(short)} — {''.join(short[:20])}\n"
            "     ⚠ 대사를 더 옮기면 한자가 물러나 자리가 는다(그게 이 표가 크는 방식이다).\n"
            "     ⚠ 그때까지 그 글자가 든 문안은 빌드가 **건너뛰고 알린다**(조용히 안 넣는다)."
        )
    for ch in list(table)[:6]:
        print(f"    {ch!r} → 0x{table[ch]:03X}")
    if a.check:
        # 🔴 **부딪힘이 1급이다** — 배정한 자리를 원본도 쓰면 그 글자가 화면에서 바뀐다.
        #    반대로 「지금 계산한 배정과 정본이 다르다」는 경고다: 새 소재를 찾았다는 뜻이고,
        #    다시 박으려면 **이미 넣은 문안을 다시 구워야** 하므로 사람이 판단한다.
        canon = load(a.disc)
        exe, _, _ = font.exe_bytes(a.disc)
        n = font.glyph_count(exe, a.disc)
        bad = sorted(set(canon.values()) & used)
        outside = sorted(c for c in canon.values() if not (0 <= c < n))
        blankg = sorted(c for c in canon.values() if not font.read_glyph(exe, c, a.disc).any())
        for label, xs in (
            ("원본이 쓰는 자리", bad),
            ("폰트 밖", outside),
            ("그림 없는 자리", blankg),
        ):
            if xs:
                print(f"  🔴 {label} {len(xs)} — {' '.join(f'0x{c:03X}' for c in xs[:8])}")
        if canon != table:
            print("  ⚠ 지금 계산한 배정이 정본과 다르다 — 새 소재를 찾은 것이다.")
            print("     다시 박으려면 `--freeze`, ⚠ 그때 **이미 넣은 문안을 다시 구워야 한다.**")
        ok = not (bad or outside or blankg)
        print(f"{a.disc}: 글리프 자리 정본 — {'✅ 원본과 안 부딪힌다' if ok else '🔴 부딪힌다'}")
        return 0 if ok else 1
    if not a.freeze:
        if os.path.exists(map_path(a.disc)):
            same = load(a.disc) == table
            print(f"\n정본과 {'같다' if same else '🔴 다르다 — 소재가 바뀌었다'}")
            return 0 if same else 1
        print(f"\n정본이 없다 — `--freeze` 로 박는다 ({map_path(a.disc)})")
        return 0
    with open(map_path(a.disc), "w", encoding="utf-8") as f:
        json.dump(
            {
                "_doc": "글자 → 글리프 코드. 🔴 파생물이 아니라 정본이다 — tools/hangul_map.py",
                "disc": a.disc,
                "chars": chars,
                "codes": [table[c] for c in chars],
            },
            f,
            ensure_ascii=False,
            indent=1,
        )
    print(f"\n✅ 정본으로 박았다 → {map_path(a.disc)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
