#!/usr/bin/env python3
"""이미지 전체 잔존 게이트 — 최종 이미지의 대본 멤버에 **원문 그대로인 긴 텍스트 런**이 알려진 자리 밖에 남았나(sfc-ed2 와 같은 꼴).

    python3 tools/check_image_residue.py --built <빌드 이미지.bin> [--freeze]

⚠ 정본(`script/`)에서 출발하는 검사(`check_jp_left`·`check_no_text_loss`)는 **정본에 없는 조각**을 못 본다 — 분모 밖 누락(파서가 놓친 조각·
   건너뛰어 원문이 남은 조각)이 조용히 남는다. 그래서 반대로 **이미지에서 출발**한다: 빌드 이미지와 원본의 같은 멤버를 0xFFFF 로 갈라
   (`dump_script.runs_of`) 텍스트 런(`is_text`)을 비교해, 바이트가 원본과 같고 `MIN_LEN` 코드 이상인 런을 센다.
   한글 글리프도 같은 16비트 코드 대역이라 「한자로 보이나」는 못 가르므로 **원본과 같은가**로 가른다.
기준선 `image_residue_baseline.json`(멤버 → 개수)보다 **늘면 실패**, 줄면 `--freeze` 로 내린다(래칫). 기준선 값은 「아직 안 옮긴 알려진 자리」다.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import dump_script

MIN_LEN = 5  # 코드 수 — 원문 5코드 연속(창)이 빌드 런에 그대로 있으면 센다. 10-18: 12 였을 때 짧은 문장이 샜고, 5 에서 잡음은 이벤트 VM 데이터 몇 개뿐이었다(실측)
BASELINE = os.path.join(common.ROOT, "image_residue_baseline.json")
TEXT_MEMBER = dump_script.TEXT_MEMBER["ed3"]


def _window_ok(w):
    """창이 글자 대역에 있나 — 0 채움·제어 코드·같은 코드 반복(데이터)은 글이 아니다."""
    return all(dump_script.KANA_LO <= x < 0x8000 for x in w) and len(set(w)) > 1


def residue(orig_mem, built_mem, n=None):
    """원문 그대로 남은 텍스트 런의 수 — 빌드 런이 원본 텍스트 런의 `n` 코드 창을 하나라도 그대로 품으면 센다.

    🔴 런 전체가 같은지가 아니라 **창**을 본다: 일부만 번역돼 런이 원본과 달라진 문장(이름만 박힌 문장 등)과 짧은 문장이 둘 다 샌다
    (sfc-ed2 가 24곳을 놓친 꼴). 알려진 자리를 뺀 나머지에 원문이 있는지를 본다."""
    n = n or MIN_LEN
    grams = set()
    for _, c in dump_script.runs_of(orig_mem):
        if dump_script.is_text(c):
            grams.update(w for i in range(len(c) - n + 1) if _window_ok(w := tuple(c[i : i + n])))
    return sum(
        1 for _, c in dump_script.runs_of(built_mem) if any(tuple(c[i : i + n]) in grams for i in range(len(c) - n + 1))
    )


def members(bin_path, tree=None):
    """{(아카이브, 멤버): 바이트} — `SCE*/SC*.DAT` 안의 `..\\DATA\\*.BIN`."""
    files = tree or common.iso_tree(bin_path)[0]
    out = {}
    for path, (lba, size) in sorted(files.items()):
        if not (path.startswith("/SCE") and path.endswith(".DAT")):
            continue
        data = common.read_lba("ed3", lba, size, path=bin_path)
        try:
            ents = common.arc_members(data)
        except common.ArchiveError:
            continue
        for nm, (off, sz) in ents.items():
            if nm.startswith("..") and TEXT_MEMBER in nm:
                out[(os.path.basename(path), nm)] = data[off : off + sz]
    return out


def scan(built, orig=None):
    om = members(orig or common.orig_bin("ed3"))
    bm = members(built)
    return {f"{a}:{m}": n for (a, m), blob in bm.items() if (n := residue(om.get((a, m), b""), blob))}


def load_baseline():
    if not os.path.exists(BASELINE):
        return {}
    with open(BASELINE, encoding="utf-8") as f:
        return json.load(f)


def judge(found, base):
    """(늘어난 항목 목록, 줄어든 항목 목록)."""
    up = [f"{k}: {v} > 기준선 {base.get(k, 0)}" for k, v in sorted(found.items()) if v > base.get(k, 0)]
    down = [k for k, v in sorted(base.items()) if found.get(k, 0) < v]
    return up, down


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--built", required=True)
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    found = scan(a.built)
    base = load_baseline()
    up, down = judge(found, base)
    print(f"  이미지 잔존 런(원문 {MIN_LEN}코드 창이 그대로): {sum(found.values()):,}개 · 멤버 {len(found):,} · 기준선 {sum(base.values()):,}개")
    if a.freeze:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(found.items())), f, ensure_ascii=False, indent=1)
        print(f"  기준선 갱신 — {len(found):,}멤버")
        return 0
    if up:
        print("🔴 알려진 자리 밖에 원문이 남았다:\n  " + "\n  ".join(up[:20]))
        return 1
    if down:
        print(f"  ⚠ 줄었다 — 기준선을 내리자: --freeze ({len(down)}멤버)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
