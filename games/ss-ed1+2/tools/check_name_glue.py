"""**띄어 쓴 이름은 줄 끝에서 갈리지 않는다** — 번역 규칙 2-6(마스터 10-31, ED1 전투 「레스의 / 잎을 사용했다」).

    python3 tools/check_name_glue.py

전투 줄은 엔진이 이름을 끼운 뒤 기계어(`patch_msgwrap`)가 `0x20` 에서만 끊는다. 그래서 이름 표(아이템 · 주문 · 몬스터)와
ED2 몬스터 이름의 안쪽 공백은 **줄바꿈 금지 반각 코드**(`font.NB_CODE`)로 적는다(`font.glue_name`).

본 것 (최종 이미지에서)
  ① 이름 표 칸을 포인터로 따라가 읽는다 — 정본에 공백이 든 이름은 **안쪽 공백이 전부 `NB_CODE`** 이고 `0x20` 이 없다.
  ② 본체 둘 + ED2 몬스터 파일 — 띄어 쓴 이름이 `0x20` 꼴로 남은 곳이 0(문장 안에 품은 이름 포함).
  ③ 모집단 — 공백 든 이름 수를 표별로 센다(0 이면 실패 — 검사기가 헛돈다).
"""

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import font
import patch_mon_names as M
import patch_ui


def plain_vs_glued(kr, plan):
    return font.to_bytes(kr, plan), font.to_bytes(font.glue_name(kr), plan)


def split_plain(d, kr, plan):
    """이름 가운데 색 표지(`%c`)가 낀 조각에 `0x20` 꼴로 남은 이름의 자리(없으면 -1) — 원판이 이름을 색 구간으로 쪼갠 문장 조각."""
    pat = b"(?:%c)*".join(re.escape(font.to_bytes(c, plan)) for c in kr)
    m = re.search(pat, d)
    while m and b"%c" not in m.group(0):  # 붙은 꼴은 위의 `find` 가 본다
        m = re.compile(pat).search(d, m.start() + 1)
    return m.start() if m else -1


def scan(d, ptr_rows, plan):
    """이름 표 한 파일 → (센 이름 수, [실패])."""
    bad, n = [], 0
    for kr, ptrs in ptr_rows:
        if " " not in kr:
            continue
        _plain, glued = plain_vs_glued(kr, plan)
        for p in ptrs:
            n += 1
            at = int.from_bytes(d[p : p + 4], "big") - patch_ui.NAME_PTR_BASE
            z = d.find(b"\x00", at, at + 64)
            got = bytes(d[at:z])
            if got != glued or b" " in got:
                bad.append((kr, got.hex()))
    return n, bad


def _scene_spans():
    """쓰기 장부에서 **씬 문안 패처**(`patch_scn`)가 쓴 구간 — 씬 창은 엔진이 글자 단위로 접고 이름 붙임은 조판기(`typeset_scn._NB`)가
    한다. 여기 든 이름은 `0x20` 이어도 된다(메시지 창 `msgwrap` 몫이 아니다)."""
    import json as _json

    led = os.path.join(common.BUILD_DIR, "write_ledger.jsonl")
    if not os.path.exists(led):
        return []
    out = []
    with open(led, encoding="utf-8") as f:
        for ln in f:
            e = _json.loads(ln)
            if e.get("t") == "patch_scn.py":
                out.append((e["a"], e["a"] + e["n"]))
    return out


def _in_scene(spans, abs_off):
    return any(a <= abs_off < b for a, b in spans)


def reserved_code_unused():
    """줄바꿈 금지 코드(`font.NB_CODE`)로 쓰는 글자가 문안에 따로 쓰이면 읽어 되돌릴 때 공백과 섞인다 — 쓰인 곳 수."""
    import patch_scn

    ch = chr(font.NB_CODE)
    sysj = common.sys_lines()
    return sum(t.count(ch) for t in [*patch_scn.all_texts(), *sysj.values()] if t)


def main():
    img = glob.glob(os.path.join(common.BUILD_DIR, "*.bin"))
    if not img:
        print("     ⏭ 빌드 이미지가 없다 — 건너뜀")
        return 0
    with open(patch_ui.HMAP, encoding="utf-8") as f_:
        syl = json.load(f_)["syllables"]
    plan = {c: (font.sjis_of_index(i), i) for c, i in syl.items()}
    f0, mm0 = common.open_image()
    try:
        rows = patch_ui.name_rows(mm0)
    finally:
        mm0.close()
        f0.close()
    f1, mm1 = common.open_image(img[0])
    total = 0
    bad = []
    try:
        files = {p: (l, s) for p, l, s in common.iso_files(mm1)}
        for t in rows:
            d = common.read_extent(mm1, *files[t["path"]])
            n, b = scan(d, [(kr, ptrs) for _a, _jp, kr, ptrs in t["recs"] if kr], plan)
            total += n
            bad += [(t["path"], t["what"], *x) for x in b]
        # ② 띄어 쓴 이름이 `0x20` 꼴로 남은 곳 — 본체 둘과 ED2 몬스터 파일 전체(이름 표 밖의 메시지 속 이름까지)
        names = patch_ui.spaced_names()
        scene = _scene_spans()
        for path in ("/ED.BIN", "/ED2.BIN", *M.FILES):
            d = bytes(common.read_extent(mm1, *files[path]))
            for kr in names:
                plain = plain_vs_glued(kr, plan)[0]
                total += 1
                at = d.find(plain)
                while at >= 0 and _in_scene(scene, files[path][0] * 2048 + at):
                    at = d.find(plain, at + 1)
                if at >= 0:
                    bad.append((path, "메시지", kr, f"0x20 꼴이 남았다(0x{at:X})"))
                sp = split_plain(d, kr, plan) if " " in kr else -1
                if sp >= 0 and not _in_scene(scene, files[path][0] * 2048 + sp):
                    bad.append((path, "메시지", kr, f"색 표지로 쪼갠 조각에 0x20 꼴이 남았다(0x{sp:X})"))
        mon = M.table("monster", "eiyuu")
        for path in M.FILES:
            d = bytes(common.read_extent(mm1, *files[path]))
            for _t, _jp, kr in M.slots(path, mon):
                if " " in kr and plain_vs_glued(kr, plan)[1] not in d:
                    bad.append((path, "몬스터", kr, "글루 꼴이 없다"))
    finally:
        mm1.close()
        f1.close()
    used = reserved_code_unused()
    if used:
        print(
            f"  ❌ 이름 안 줄바꿈 금지 — 예약 글자 {font.NB_CODE:#x} 가 문안에 {used}번 쓰였다(공백과 섞인다)"
        )
        return 1
    if total == 0:
        print("  ❌ 이름 안 줄바꿈 금지 — 센 이름이 0 (검사기가 헛돈다)")
        return 1
    mark = "✅" if not bad else "❌"
    print(
        f"  {mark} 이름 안 줄바꿈 금지 — 띄어 쓴 이름 {total - len(bad)}/{total}칸이 줄바꿈 금지 코드로 묶였다"
    )
    for x in bad[:10]:
        print(f"      🔴 {x}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
