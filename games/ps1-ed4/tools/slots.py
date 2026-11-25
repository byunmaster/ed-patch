"""한글 글리프 자리 배정 — 번역 문안에 쓰인 글자 중 **자리 정본(`hangul_map.json`)에 없는 것**을 새 자리에 붙인다.

    python3 tools/slots.py status           # 필요한 글자 · 이미 배정 · 새로 필요한 수 · 후보 자리
    python3 tools/slots.py assign           # 부족한 글자를 후보 자리에 이어 붙여 정본을 갱신한다(⚠ 커밋 전 diff 를 본다)

🔴 정본(`hangul_map.json`)은 **추가만** 한다 — 한 번 배정한 글자·자리는 안 옮긴다(배포 뒤엔 못 옮긴다). 그래서 **지금 배정은 임시일 수 있다**(마스터 확정 전 단계).
후보 자리 = 코드표에서 **가나·한자인 코드**(기호·숫자·부호는 한국어 문안도 원본 코드를 쓰므로 건드리지 않는다) 중 아직 배정 안 된 것을
**원본 전체(대본 + 실행파일 문자열)에서 덜 쓰이는 순**(같으면 코드 순)으로 쓴다 — 번역이 끝나면 일본어 글자는 안 남으므로 모든 가나·한자가 결국 후보지만,
**번역 도중 빌드에서 아직 일본어로 남은 글에 한글이 덮어 쓰는 피해가 가장 적은 곳부터** 채운다(덜 쓰이는 글자부터).
⚠ 아직 번역 안 된 일본어 글이 그 자리를 쓰고 있으면 화면에서 그 글자가 한글로 **오독**된다 — 번역 중 시험 빌드에서만 보이는 일시적 현상이다(`status` 가 몇 곳인지 센다).
"""

import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dump
import font
import hangul
import textenc
import uitext

# 🔴 글리프 빈 슬롯 구간(arena) — **한글 후보에서 뺀다.** 실행파일 표 풀이 모자랄 때 표를 이 자리로 옮긴다(`exetab.relocate_units`, 관리자 10-24).
#    최종 빌드에선 일본어가 다 번역돼 이 가나·한자 글리프를 아무도 안 읽는다(번역 도중 시험 빌드에선 그 자리 일본어가 오독된다).
#    표 기준 상수(`lui` 불변)의 16비트 범위 때문에 주소 0x80078000 이상만 쓴다(표 대부분이 `lui 0x8008`): 슬롯 1653~1935 = 283개 = 5,094B.
ARENA = (1653, 1936)  # [처음, 끝) 슬롯 번호 — 한글 후보에서 뺀다
ARENA_SAFE_END = 1873  # 🔴 1873~1879 는 **검 아이콘 그림 조각**이다(로드 창·상태 창 — 코드가 즉시값이 아니라 계산으로 읽어 정적 전수가 놓쳤다, 10-25 마스터 「검 아이콘이 깨짐」). 원본 문안이 쓰는 마지막 코드 1872 까지만 UI 표 옮기기에 쓴다 · 모자라는 만큼은 먼저 옮긴 표의 죽은 u16 배열이 받는다(`uitext.apply`)
ARENA2 = (72, 101)  # [처음, 끝) — 후보 자리 중 연속 29칸을 UI 표 옮기기 둘째 자리로(arena 1653~1872 만으론 모자라 — 10-25)
BT_SLOTS = (101, 113)  # [처음, 끝) — 조사 훅 받침 비트표 자리(후보 자리 중 연속 12칸을 한글에서 뺀다, 12×18=216B ≥ 208B)
#  # 🔴 실제로 **써도 되는** 끝 — 그 뒤(1922~1935, 14슬롯)는 한자가 아니라 엔진이 그리는 그림 조각(능력치 비교 화살표 등)이라 쓰면 장비 화면에 잡음이 뜬다(10-25)


# 원본 코드표에 없는데 한국어가 쓰는 부호 — 한글처럼 갈무리로 그려 자리를 준다(규칙 1-3: 말줄임표는 전각 한 글자·점은 바닥)
EXTRA_GLYPHS = "…"


def arena_range():
    """(파일 오프셋 시작, 끝) — 글리프 배열 안 arena."""
    off = font.font_off()
    return off + font.GLYPH_BYTES * ARENA[0], off + font.GLYPH_BYTES * ARENA[1]


def in_arena(code):
    return ARENA[0] <= code < ARENA[1]


def is_cjk_or_kana(ch):
    o = ord(ch)
    return 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or ch == "々"


def usage():
    """{코드: 출현 수} — 대본 조각 + 실행파일 문자열 전체(번역 여부와 무관, 원본 기준)."""
    cnt = Counter()
    for p in glob.glob(os.path.join(common.OUT_DIR, "script", "*.json")):
        with open(p, encoding="utf-8") as f:
            for seg in json.load(f)["segments"]:
                cnt.update(seg["codes"])
    exe = bytes(common.read_file(common.EXE_PATH))
    cm = textenc.charmap()
    import struct

    n = len(exe) // 2
    w = struct.unpack(f"<{n}H", exe[: n * 2])
    cur = []
    for x in w:
        if dump.is_term(x):
            if cur:
                # 🔴 「전부 디코드되는 문자열」만 세면 수치 제어코드(5·0·0)가 낀 조각(마법 설명 머리 「レンジ」「効果」)의 글자를 못 센다 —
                #    그 글자 칸이 후보로 풀려 한글이 앉으면 「効果」가 「돌뱃」으로 깨진다(10-25). 디코드되는 코드는 모두 센다.
                cnt.update(c for c in cur if c in cm)
            cur = []
        else:
            cur.append(x)
    return cnt


def candidates(table):
    """후보 자리 — 가나·한자 코드 **와 코드표가 못 읽는 코드**(미해독 한자 — 번역이 끝나면 아무도 안 읽는다). 기호·숫자·부호(코드표가 읽는 비한자)·arena·이미 배정은 뺀다.

    ⚠ 미해독 코드는 기호일 수도 있으나 **우리 문안은 코드표가 읽는 기호만 쓴다**(원본 코드로) — 못 읽는 코드를 우리가 쓸 일이 없다.
    """
    cm = textenc.charmap()
    taken = set(table.values())
    cnt = usage()
    cand = [
        c
        for c in range(font.font_slots())
        if c not in taken
        and not in_arena(c)
        and not (BT_SLOTS[0] <= c < BT_SLOTS[1])
        and not (ARENA2[0] <= c < ARENA2[1])
        and (c not in cm or is_cjk_or_kana(cm[c]))
        and c
        >= textenc.KANA_BASE  # 앞쪽(0~62)은 제어·기호·부호 블록 — 못 읽는 코드라도 엔진이 직접 쓰는 글리프(▼ 등)일 수 있어 안 건드린다
    ]
    cand.sort(key=lambda c: (cnt[c], c))
    return cand, cnt


def needed_chars():
    """번역 정본들이 쓰는 글자 — UI 문안 + 대본 정본."""
    import script_kr

    chars = set(uitext.used_chars()) | set(script_kr.used_chars())
    return {c for c in chars if c.strip()}


def missing(table):
    rev = hangul.reverse_charmap()
    out = []
    for ch in sorted(needed_chars()):
        if ch in table or ch in rev:
            continue
        if not (0xAC00 <= ord(ch) <= 0xD7A3 or 0x3131 <= ord(ch) <= 0x3163 or ch in EXTRA_GLYPHS or 0xE000 <= ord(ch) < 0xF900):
            raise SystemExit(
                f"🔴 한글 음절이 아닌데 코드표에도 없는 글자 {ch!r} — 기호면 원본 코드를 찾아야 한다(자리를 새로 주지 않는다)"
            )
        out.append(ch)
    return out


def status():
    table = hangul.load()
    miss = missing(table)
    cand, cnt = candidates(table)
    print(
        f"필요 글자 {len(needed_chars())} · 이미 배정 {len(table)} · 새로 필요 {len(miss)} · 후보 자리 {len(cand)}"
    )
    if miss:
        pick = cand[: len(miss)]
        cm = textenc.charmap()
        print("  새 글자 → 자리(원래 글자 · 원본 출현 수):")
        for ch, c in list(zip(miss, pick, strict=True))[:8]:
            print(f"   {ch} → {c}  ({cm.get(c, '미해독')} · {cnt[c]}곳)")
        print(f"  ⚠ 아직 일본어로 남은 글에서 오독될 곳 합계 {sum(cnt[c] for c in pick)}")
    return miss


def repack():
    """배정 중 arena 안(또는 기호 블록 0~62)에 있는 글자를 후보 자리로 옮긴다(자리 정본·반각 정본 둘 다). 개발 단계 정본이라 허용한다(배포 뒤엔 못 한다)."""
    table = hangul.load()
    cand, _cnt = candidates(table)
    moved = 0
    for path in (hangul.MAP_PATH, hangul.HALF_PATH):
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        for i, c in enumerate(doc["codes"]):
            if in_arena(c) or c < textenc.KANA_BASE:
                doc["codes"][i] = cand.pop(0)
                moved += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write("\n")
    print(f"arena 안 배정 {moved}자를 옮겼다")
    return 0


def assert_arena_free(table=None):
    """🔴 빌드 단언 — arena 슬롯에 한글·반각 글리프가 배정돼 있으면 실패한다(표 풀이 그 자리를 쓴다)."""
    table = table or hangul.load()
    bad = sorted(ch for ch, c in table.items() if in_arena(c) or c < textenc.KANA_BASE)
    if bad:
        raise SystemExit(
            f"🔴 글리프 arena 슬롯 {ARENA} 에 글자가 배정돼 있다: {''.join(bad)} — `slots.py repack`"
        )
    bad = sorted(ch for ch, c in table.items() if BT_SLOTS[0] <= c < BT_SLOTS[1] or ARENA2[0] <= c < ARENA2[1])
    if bad:
        raise SystemExit(f"🔴 조사 훅 받침표 자리 {BT_SLOTS} 에 글자가 배정돼 있다: {''.join(bad)}")


def assign():
    table = hangul.load()
    miss = missing(table)
    if not miss:
        print("새로 필요한 글자 없음")
        return 0
    cand, _cnt = candidates(table)
    if len(cand) < len(miss):
        raise SystemExit(f"🔴 후보 자리가 모자란다 {len(cand)} < {len(miss)}")
    with open(hangul.MAP_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    for ch, c in zip(miss, cand[: len(miss)], strict=True):
        doc["chars"].append(ch)
        doc["codes"].append(c)
    with open(hangul.MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{len(miss)}자 배정: " + "".join(miss))
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "status":
        status()
        return 0
    if cmd == "assign":
        return assign()
    if cmd == "repack":
        return repack()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
