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

⚠ **자리는 「그림이 있는」 것만 쓴다.** 폰트 배열의 끝은 `font.glyph_count` 가 빈 칸 연속으로
   **추정**한 값이라, 그 근처는 폰트가 아닐 수 있다. 그림이 있으면 그 자리가 폰트 안이라는
   증거다(빈 칸을 덮으면 뭘 덮는지 모른다).

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


def used_codes(disc):
    """원본이 실제로 화면에 내보내는 코드 전부.

    ⚠ **멤버의 u16 을 통째로 세면 안 된다** — 스크립트는 바이트 스트림이라 opcode 가 코드처럼
      보인다(그렇게 셌더니 5,413 중 5,077 이 「쓰인다」로 나와 빈 자리가 336 뿐이었다).
      **파서가 문자열로 인정한 조각**만 센다.
    """
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
            for _, codes in info["segments"]:
                used.update(codes)

    cm = textenc.charmap(disc)
    lba, size = common.iso_files(disc)[dump_names.EXE[disc]]
    exe = common.read_lba(disc, lba, size)
    for t in exetext.scan_tables(exe, cm):
        for x in struct.unpack_from(f"<{t['n']}H", exe, t["table"]):
            codes, _ = exetext.raw_string(exe, t["base"] + x)
            used.update(codes or [])
    # 표를 못 찾은 구역도 화면에 나간다 — 라벨 붙인 낱말 구역 전량을 더한다.
    labels = dump_names.REGIONS[disc]
    rev = {v: k for k, v in cm.items()}
    for r in dump_names.split(dump_names.regions(dump_names.strings(exe, cm)), labels):
        for text in r["items"]:
            used.update(rev[ch] for ch in text if ch in rev)
    return used


def free_slots(disc, used=None):
    """[코드] — 안 쓰는데 **그림이 있는** 자리. 카나 끝 다음부터."""
    used = used_codes(disc) if used is None else used
    exe, _, _ = font.exe_bytes(disc)
    first = max(textenc.kana_map(disc)) + 1
    n = font.glyph_count(exe, disc)
    return [c for c in range(first, n) if c not in used and font.read_glyph(exe, c, disc).any()]


def assign(disc, free=None):
    """{글자: 코드} — 빈 자리 앞에서부터, **공백 먼저 그다음 가나다순**."""
    chars = list(EXTRA) + ksc_syllables()
    free = sorted(free if free is not None else free_slots(disc))
    if len(free) < len(chars):
        raise SystemExit(f"{disc}: 빈 자리가 모자라다 {len(free)} < {len(chars)}")
    return dict(zip(chars, free[: len(chars)], strict=True))


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
    table = assign(a.disc, free)
    chars = list(table)
    print(f"{a.disc}: 글자 {len(chars):,} · 원본이 쓰는 코드 {len(used):,} · 빈 자리 {len(free):,}")
    print(
        f"  배정 0x{table[chars[0]]:03X} ~ 0x{table[chars[-1]]:03X} · 남는 자리 {len(free) - len(chars):,}"
    )
    for ch in (" ", "가", "한", "글", "힣"):
        if ch in table:
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
