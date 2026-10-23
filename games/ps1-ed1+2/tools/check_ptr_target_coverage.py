#!/usr/bin/env python3
"""**메시지 포인터 표의 모든 목표가 번역 단위 목록 안에 있는가** — 목록 밖을 가리키면 거기는 일본어로 남아도 안 보인다.

sfc-ed1 이 찾았다(10-18): 번역 단위 목록이 훑는 구간 밖을 포인터 표가 가리켜 장면 대사 101개가 일본어 그대로였다.
단위 목록도 잔존 게이트도 **목록을 기준으로** 돌아서 원리상 못 본 자리다.

- 씬(ED1SCN1~6 · ED2SCN1~13): 빌드 이미지에서 코드의 문자열 참조(`find_refs`)를 모아, **번역 단위 구간**
  (`work/derived/scn_jp/<씬>.json` 의 엔트리 `[file_offset, +raw 길이)`) 안에 드는지 센다. 밖이면 실패.
- ED2MON(전투 대사 오버레이): 참조 목표가 가리키는 자리부터 널까지에 **가나가 있으면** 실패 —
  `check_scn_jp_left.scan_mon` 은 문자열 단위로만 보는데, 참조가 문자열 한복판을 가리키면(이름 접두를
  건너뛰는 꼴) 그 꼬리를 따로 읽는다.

판정 함수(`outside_spans`)는 순수 함수라 합성 데이터로 테스트한다(`tests/test_jp_gates.py`).

  python3 tools/check_ptr_target_coverage.py
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

KANA = re.compile(r"[ぁ-んァ-ヶ]")


def outside_spans(targets, spans):
    """[목표] 중 어느 `[시작, 끝)` 구간에도 안 드는 것."""
    return [t for t in targets if not any(a <= t < b for a, b in spans)]


def main():
    import reinsert_kr_pilot as R
    from check_scn_jp_left import IMG
    from common import OUT_DIR, extract
    from ed2_monster_review import MON
    from patch_ed2_monster_lines import _live_group_lba, overlay_refs
    from patch_sys_ui import _scn_layout

    total = out = 0
    bad = []
    for name, lba, size in _scn_layout():
        if not name.startswith(("ED1SCN", "ED2SCN")):
            continue
        doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{name}.json"), encoding="utf-8"))
        te = int(doc["source"]["text_end"], 16)
        data = bytes(extract(lba, size, path=IMG))
        spans = []
        for e in doc["entries"]:
            a = int(e["file_offset"], 16)
            spans.append((a, a + (len(bytes.fromhex(e["raw_hex"])) if e.get("raw_hex") else 1)))
        with R.overlay_for(name):
            base = R.ov_base()
            refs = sorted({a - base for _, _, _, a in R.find_refs(data, te)})
        o = outside_spans(refs, spans)
        total += len(refs)
        out += len(o)
        bad += [f"{name}@{x:#x}" for x in o]
    print(f"  씬 포인터 목표 {total} · 번역 단위 구간 밖 {out}")

    mon_total = mon_kana = 0
    live = _live_group_lba()
    for g, (lba, size) in sorted(MON.items()):
        refs, _ = overlay_refs(bytes(extract(lba, size)))
        data = bytes(extract(live[g][0], live[g][1], path=IMG))
        for off in sorted(refs):
            if off >= len(data):
                continue
            mon_total += 1
            end = data.find(b"\x00", off)
            tail = data[off : end if end > 0 else off + 200].decode("cp932", "ignore")
            if KANA.search(tail):
                mon_kana += 1
                bad.append(f"ED2MON{g}@{off:#x} {tail[:20]!r}")
    print(f"  ED2MON 참조 목표 {mon_total} · 목표 꼬리에 가나 {mon_kana}")
    for b in bad[:30]:
        print(f"    ❌ {b}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
