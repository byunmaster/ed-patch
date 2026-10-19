#!/usr/bin/env python3
"""쓰기 겹침 감사 — **서로 다른 도구가 같은 파일의 같은 바이트를 쓴 자리**를 가른다(쓰기 장부 `common._ledger`).

    python3 tools/check_write_overlap.py            # 보고
    python3 tools/check_write_overlap.py --strict   # 결함(`over`)이 있으면 실패 — check.sh 가 이쪽으로 부른다

🔴 왜(2026-10-19 qa r4): `patch_ui` 가 ED2MON 꼬리에 시스템 문안을 깔고 **뒤 단계** `patch_scn` 이 같은 꼬리 맨 앞부터 대사를 다시 깔아 앞 문구를 덮었다. 챕터 끝 카드
   꼬리 위에도 대사가 얹혔다. 각 단계의 되읽기는 자기가 쓴 것만, 자기 단계 직후만 본다 — 뒤 단계가 앞 단계를 덮는 것은 구조상 아무도 안 본다. 이쪽은 **모든 패처의 모든 쓰기**를 본다.

분류(파일 내 오프셋 기준 — 절대 위치는 단계 중간의 재배치로 달라져 거짓 겹침을 낸다):
  same / pad  같은 값 · 여백(앞 쓰기의 겹친 구간이 전부 0) — 무해.
  ptr         앞뒤 둘 다 **포인터** 쓰기 — 뒤 단계가 같은 문자열의 이주 사본으로 포인터를 돌림. 결과는 최종 이미지 되읽기(`patch_ui --verify-final` ·
              `check_sys_final`)가 포인터를 따라가 보증한다.
  jp          앞 쓰기의 겹친 구간이 **원문 일본어 잔재**(가나) — 뒤 단계(`patch_mon_names`·`patch_namecopy`·`patch_scn`)가 번역으로 교체. 「남은 일본어」 게이트가 보증.
  over        **앞 쓰기의 번역·데이터를 다른 값으로 덮음 = 결함**(챕터 카드 꼬리·ED2MON 꼬리가 이 부류였다). `--strict` 는 0 이어야 한다.
디렉터리 레코드(`크기`·`LBA`) 갱신은 파일이 아니라 디렉터리 안의 위치라 뺀다(단계가 순서대로 다시 쓰는 것이 정상).
"""

import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))

_SLOTS = None


def _slot_codes():
    """우리 한글 슬롯의 SJIS 2B 코드 집합 — 원문이 안 쓰는 칸이라 이 코드를 담은 쓰기는 **번역**이다."""
    global _SLOTS
    if _SLOTS is None:
        import common
        import font

        with open(os.path.join(common.GAME_DIR, "hangul_map_11kanji.json"), encoding="utf-8") as f:
            _SLOTS = {font.sjis_of_index(i) for i in json.load(f)["syllables"].values()}
    return _SLOTS


def load():
    import common

    if not os.path.exists(common.LEDGER):
        raise SystemExit("쓰기 겹침: 장부가 없다 — 먼저 빌드한다(`common._ledger`)")
    with open(common.LEDGER, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f]


def _path(r):
    m = re.match(r"(/\S+)", r["l"])
    return m.group(1) if m else None


def _is_jp(b):
    """앞 쓰기의 겹친 구간이 **번역이 아니다**(우리 한글 슬롯 코드를 하나도 안 담았다) — 원문 일본어 잔재다."""
    slots, i = _slot_codes(), 0
    while i < len(b):
        if 0x81 <= b[i] <= 0x9F or 0xE0 <= b[i] <= 0xFC:
            if b[i : i + 2] in slots:
                return False
            i += 2
        else:
            i += 1
    return any(b)


def overlaps(rows):
    """`[(앞 쓰기, 뒤 쓰기, 겹친 바이트 수, 분류)]` — 같은 파일의 서로 다른 도구, 파일 내 오프셋 기준."""
    rows = [r for r in rows if r.get("o") is not None and _path(r) and not re.search(r"크기|LBA", r["l"])]
    idx = sorted(range(len(rows)), key=lambda i: (_path(rows[i]), rows[i]["o"]))
    out, active, cur = [], [], None
    for i in idx:
        r = rows[i]
        if _path(r) != cur:
            active, cur = [], _path(r)
        start = r["o"]
        active = [j for j in active if rows[j]["o"] + rows[j]["n"] > start]
        for j in active:
            q = rows[j]
            if q["t"] == r["t"]:
                continue
            lo, hi = start, min(q["o"] + q["n"], r["o"] + r["n"])
            if hi <= lo:
                continue
            first, second = (q, r) if j < i else (r, q)
            fb = bytes.fromhex(first["d"])[lo - first["o"] : hi - first["o"]]
            sb = bytes.fromhex(second["d"])[lo - second["o"] : hi - second["o"]]
            if fb == sb:
                kind = "same"
            elif not any(fb):
                kind = "pad"
            elif "포인터" in first["l"] and "포인터" in second["l"]:
                kind = "ptr"
            elif _is_jp(fb):
                kind = "jp"
            else:
                kind = "over"
            out.append((first, second, hi - lo, kind))
        active.append(i)
    return out


def main():
    ov = overlaps(load())
    kinds = collections.Counter(k for *_x, k in ov)
    over = [(a, b, n) for a, b, n, k in ov if k == "over"]
    print(
        f"  쓰기 겹침 [같은 파일·다른 도구 {len(ov)}] — 같은 값 {kinds['same']} · 여백 {kinds['pad']} · 포인터 재지정 {kinds['ptr']} · 일본어 잔재 교체 {kinds['jp']} · "
        f"**앞 번역을 덮음(결함) {len(over)}**"
    )
    for a, b, n in over[:12]:
        print(f"     ❌ {a['t']} {a['l'][:56]} ← {b['t']} {b['l'][:56]}  ({n}B @0x{max(a['o'], b['o']):X})")
    if "--strict" in sys.argv and over:
        raise SystemExit(f"쓰기 겹침 {len(over)}건 — 앞 단계가 쓴 번역·데이터를 뒤 단계가 덮었다")


if __name__ == "__main__":
    main()
