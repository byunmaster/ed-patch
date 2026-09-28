#!/usr/bin/env python3
"""ED2MON0~5.BIN 되읽기 게이트 — **우리가 쓴 자리가 쓰려던 것과 바이트로 같은가**.

🔴 **방향을 뒤집은 게이트다**(마스터 QA `047`, 2026-09-13). `check_scn_jp_left.scan_mon()`
류는 "이미지 어딘가에 일본어가 있나"를 본다 — 분모가 파일 전체라 스탯 이진 자료의 잡음이
압도적이다(그룹당 수천 건, 나이브 스캔으로는 못 가른다). 여기는 반대로 **우리 표(정본)가
분모**다 — 우리가 쓰려고 정한 것만 세니 잡음이 0이다.

⚠ **그래도 못 보는 자리가 있다** — "표에는 있는데 이미지에 안 쓴 것"(스캐너가 원리상 못
찾는 자리, 047 의 레밍플러스A 가 그 부류)은 여기 안 걸린다. 그건 `patch_ed2_monsters.plan()`
의 `none` 목록(정본에 없음)이 아니라 **`fit`/`over` 에도 아예 안 뜨는** 자리라 이 게이트의
분모 자체에 없다. 그건 "안 쓴 것" 집계(건너뜀 기준선)가 맡는다 — 둘이 짝이다.

  python3 tools/check_ed2mon_readback.py         # 이름 + 대사 둘 다
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import BUILD_DIR, ROOT, extract
from ed2_monster_review import MON as MON_ORIG
from patch_ed2_monster_lines import _enc as _enc_lines
from patch_ed2_monster_lines import _live_group_lba as _live_mon
from patch_ed2_monster_lines import overlay_refs
from patch_ed2_monsters import _enc as _enc_names
from patch_ed2_monsters import plan as names_plan

# ⚠ 접미 없는 바닥꼴은 안 본다 — `Xが現れた。`류 대사 템플릿(`patch_ed2_monster_lines
# .auto_lines`)에 그대로 박혀 있어 그쪽 담당이다. 여기서 같이 세면 이름 테이블과 무관한
# 자리가 죄다 "사각"으로 잡힌다(전수 확인: 105건 전부 이 부류였다). 이름 테이블 항목은
# 개체 접미가 반드시 붙는다.
SUFFIXES = ("Ａ", "Ｂ", "Ｃ", "Ｄ", "Ｅ", "Ｆ", "A", "B", "C", "D", "E", "F")

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"
LINES_TABLE = os.path.join(ROOT, "script", "ED2MON_LINES.json")
SKIP_BASELINE = os.path.join(ROOT, "script", "ed2mon_readback_skip_baseline.json")

# ⚠ `_live_mon` 은 `patch_ed2_monster_lines._live_group_lba` **그대로다** — 정본은
# 거기 하나다(DRY). 🔴 **정적 `MON` 을 그대로 읽으면 DUMMY 재배치를 놓친다**(2026-09-22
# 실측 — 경위는 `_live_group_lba` 독스트링). 이 되읽기 게이트가 옛 정적 `MON`(원본
# LBA)으로 읽던 시절엔 재배치된 그룹 전체가 "대사 못 찾음"으로 쏟아졌다(93건).


def check_names():
    """이름 테이블 — `plan()`(원본 기준 계획) vs **빌드 이미지**(제자리 치환이라 오프셋은 같다).

    ⚠ 슬롯을 넘어 보류된 것(`over`)은 애초에 안 썼으니 대상이 아니다.
    """
    fit, _over, _none = names_plan()
    bad = []
    # ⚠ `fit` 의 lba 는 `plan()` 이 **정적 원본 좌표**로 낸 것이다(그룹 안 상대 오프셋은
    # 재배치돼도 그대로다 — 옮기는 건 그룹 파일의 시작 LBA뿐). 그래서 **읽을 때만**
    # `_live_mon()` 의 현재 LBA로 바꿔 치환한다(`by_lba` 는 원본 좌표 판별용으로 남긴다).
    by_lba = {}
    for g, (lba, size) in MON_ORIG.items():
        by_lba[lba] = (g, size)
    live = _live_mon()
    for lba, off, jp, kr, slot in fit:
        g, _orig_size = by_lba[lba]
        cur_lba, size = live[g]
        buf = bytes(extract(cur_lba, size, path=IMG))
        want = _enc_names(kr) + b"\x00"
        got = buf[off : off + len(want)]
        if got != want:
            bad.append((g, off, jp, kr, "바이트 불일치"))
            continue
        if len(want) < slot and buf[off + len(want) - 1] != 0:
            bad.append((g, off, jp, kr, "종단 아님"))
    return bad


def check_name_coverage():
    """이름 정본 커버리지 — **스캐너가 아예 못 본 자리**를 잡는다(047 의 진짜 교훈).

    `plan()` 은 스캐너(`name_strings`)가 찾은 것만 안다 — 스캐너가 원리상 못 보는 자리는
    `fit`·`over`·`none` **어디에도 안 뜬다.** 그래서 "표에 있는데 안 씀"(건너뜀 기준선)도
    "쓴 게 틀림"(위 `check_names`)도 이걸 못 잡는다. 여기서는 **원본을 직접 훑어** 정본
    이름+접미 조합이 나오는 모든 자리를 세고, `plan()` 이 그 자리를 **알고나 있는지**
    (fit·over·none 중 하나에라도 올랐는지)만 본다 — 몰랐으면 스캐너 사각이다.
    """
    canon = json.load(open(os.path.join(ROOT, "textmap", "monsters_ed2.json"), encoding="utf-8"))
    fit, over, none = names_plan()
    known = {(g, off) for lba, off, *_ in fit + over for g, (l, _s) in MON_ORIG.items() if l == lba}
    known |= {(g, off) for g, off, _jp in none}

    # ⚠ **원본(originals/)을 훑는다** — `extract()` 기본 `path` 가 원본이다. 재배치는
    # 빌드 이미지에서만 일어나므로 여기는 정적 `MON_ORIG` 그대로가 맞다(수정 불필요).
    blind = []
    for g, (lba, size) in sorted(MON_ORIG.items()):
        buf = bytes(extract(lba, size))
        for jp_base in canon:
            for suf in SUFFIXES:
                target = (jp_base + suf).encode("shift_jis")
                idx = 0
                while True:
                    idx = buf.find(target, idx)
                    if idx < 0:
                        break
                    if (idx == 0 or buf[idx - 1] == 0) and (g, idx) not in known:
                        blind.append((g, idx, jp_base + suf))
                    idx += 1
    return blind


def check_lines():
    """대사 표 — 제자리 치환 + 꼬리 재배치 둘 다 있어 **정확한 오프셋을 다시 안 구한다.**

    ⚠ 재배치는 실행 시점에만 정해지는 값(꼬리의 빈자리)이라 `plan()` 격의 순수 함수가
    없다 — 대신 **기대 바이트(인코딩된 KR + 널)가 그룹 버퍼 어딘가에 널 경계로 실재하는가**
    를 본다. 「어디 있나」가 아니라 「있나」다 — 그래도 바이트 불일치·종단 누락·꼬리 잔존은
    전부 이 방식으로 걸린다(있어야 할 정확한 바이트열이 없으면 못 찾으니까).
    """
    with open(LINES_TABLE, encoding="utf-8") as f:
        table = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    live = _live_mon()
    missing = []
    for key, kr in table.items():
        want = _enc_lines(kr) + b"\x00"
        found = False
        for lba, size in live.values():
            cap = (size + 2047) // 2048 * 2048
            buf = bytes(extract(lba, cap, path=IMG))
            idx = buf.find(want)
            refs = None
            while idx >= 0:
                if idx == 0 or buf[idx - 1] == 0:
                    found = True
                    break
                # 포인터 표 바로 뒤에 붙은 대사는 앞이 널이 아니다 — 코드가 그 자리를
                # 직접 가리키면 문장 머리로 인정한다(적용기 `_apply_sha_table` 과 같은 규칙).
                if refs is None:
                    refs = overlay_refs(buf)[0]
                if idx in refs:
                    found = True
                    break
                idx = buf.find(want, idx + 1)
            if found:
                break
        if not found:
            missing.append(key)
    return missing


def check_baseline(bad_names, missing_lines, blind_names, *, strict=False):
    ids = (
        sorted(f"name:{g}:{off:#x}" for g, off, *_ in bad_names)
        + sorted(f"line:{k}" for k in missing_lines)
        + sorted(f"blind:{g}:{off:#x}" for g, off, _jp in blind_names)
    )
    print(
        f"  ED2MON 되읽기: 이름 불일치 {len(bad_names)}건 · 대사 못 찾음 {len(missing_lines)}건"
        f" · 스캐너 사각(표에 있는데 안 본 자리) {len(blind_names)}건"
    )
    for g, off, jp, kr, why in bad_names:
        print(f"    이름 {g}:{off:#x} {jp} -> {kr} ({why})")
    for g, off, jp in blind_names:
        print(f"    사각 {g}:{off:#x} {jp}")
    if not os.path.exists(SKIP_BASELINE):
        print(f"    (기준선 없음 — {os.path.relpath(SKIP_BASELINE, ROOT)} 를 만들면 회귀를 잡는다)")
        return
    with open(SKIP_BASELINE, encoding="utf-8") as f:
        base = json.load(f)
    base_ids = set(base["_ids"])
    new = sorted(set(ids) - base_ids)
    gone = sorted(base_ids - set(ids))
    print(f"    기준선 {len(base_ids)}건 대비 — 새로 어긋남 {len(new)} · 해소됨 {len(gone)}")
    if gone:
        print(f"    ℹ 해소된 자리(기준선을 손으로 갱신할 것): {', '.join(gone)}")
    if new and strict:
        raise SystemExit(
            "ED2MON 되읽기: 새로 어긋난 자리가 생겼다 — 화면이 우리 표와 다르다\n"
            + "\n".join(f"  {i}" for i in new)
            + f"\n기준선: {os.path.relpath(SKIP_BASELINE, ROOT)} (의도된 변화면 이 파일을 갱신한다)"
        )


def main():
    bad_names = check_names()
    missing_lines = check_lines()
    blind_names = check_name_coverage()
    check_baseline(bad_names, missing_lines, blind_names, strict="--strict" in sys.argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
