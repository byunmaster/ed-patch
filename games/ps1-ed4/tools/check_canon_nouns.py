"""고유명사 정본(`shared/canon/nouns/ed4.json`) ↔ 원본 대조 게이트.

① 🔴 정본에 있는데 원본(실행파일 문자열 + 씬 대본)에 안 나오는 항목 — 오타·밀린 자리. 지금 고칠 수 있으니 실패.
② 🔴 한 우리말 표기가 같은 갈래의 원문 둘에 붙었다 — 화면에서 같은 이름이 둘로 읽힌다(갈래가 다르면 정상: 소환수는 몬스터이자 마법).
③ ⚠ 실행파일 표에 있는데 정본에 안 옮긴 낱말 — 할 일이지 실패가 아니다.
원본 읽기가 없는 머신(originals 없음)에선 ②만 본다.
"""

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import textenc

CANON = os.path.join(common.ROOT, "..", "..", "shared", "canon", "nouns", "ed4.json")


def source_text():
    """(실행파일 문자열 집합, 대본 조각 문자열 목록) — 원본 이미지에서 그 자리에서 읽는다(파생 덤프에 기대지 않는다)."""
    import uitext
    from shared.ps1 import gmf_arc
    from shared.ps1 import gmf_script as scriptmap

    cm = textenc.charmap()
    exe = bytes(common.read_file(common.EXE_PATH))
    ui = {s["jp"] for s in uitext.sites(exe).values()}
    # 글자표에 없는 코드(痺·霧·鈴…)가 든 표 조각은 `sites` 가 못 읽는다 — 정본 참조(canon)로 번역한 조각은 그 원문을 이름으로 센다
    with open(os.path.join(common.ROOT, "ui_frag_ed4.json"), encoding="utf-8") as f:
        ui |= {r["canon"] for r in json.load(f).values() if isinstance(r, dict) and r.get("canon")}
    seg = []
    with common.open_disc(None) as d:
        for path, lba, size in d.files():
            if "/SC" not in path or not path.endswith(common.ARCHIVE_EXT) or size < 64:
                continue
            data = d.read_extent(lba, size)
            try:
                _, ents = gmf_arc.arc_parse(data)
            except gmf_arc.ArchiveError:
                continue
            for nm, off, sz in ents:
                if "\\BIN\\" not in nm or not nm.endswith(".BIN") or sz < 8:
                    continue
                for _, codes in scriptmap.parse(data[off : off + sz])["segments"]:
                    seg.append("".join(cm.get(c, "") for c in codes))
    return ui, seg


def main():
    with open(CANON, encoding="utf-8") as f:
        cats = json.load(f)["categories"]
    fail = []
    seen = collections.defaultdict(list)
    for kind, d in cats.items():
        for jp, kr in d.items():
            if kr:
                seen[(kind, kr)].append(jp)
    for (kind, kr), jps in sorted(seen.items()):
        if len(jps) > 1:
            fail.append(f"{kind}: 「{kr}」 가 원문 {len(jps)}개에 붙었다 — {' · '.join(jps)}")
    n = sum(len(v) for v in cats.values())
    if os.path.isdir(os.path.join(common.ROOT, "..", "..", "originals", "jp", "ps1-ed4")):
        ui, seg = source_text()
        with open(os.path.join(common.ROOT, "ui_frag_ed4.json"), encoding="utf-8") as f:
            frag_keys = {v["canon"] for v in json.load(f)["rows"].values() if "canon" in v}
        blob = "\n".join(seg) + "\n" + "\n".join(ui)
        for kind, d in sorted(cats.items()):
            # 실행파일 속 알 수 없는 한자 코드라 글로 못 읽는 이름은 ui_frag 가 원본 바이트 지문(stamp)으로 잇는다 — 그 canon 열쇠는 원본에 있는 것으로 친다
            ghost = [jp for jp in d if jp not in blob and jp not in frag_keys]
            if ghost:
                fail.append(f"{kind}: 원본(실행파일 표·씬 대본)에 안 나오는 항목 {len(ghost)} — {' · '.join(ghost)}")
        known = set().union(*[set(d) for d in cats.values()])
        miss = sorted(s for s in ui if s not in known and 0 < len(s) <= 8 and not s.isascii())
        print(f"  ⬜ 실행파일 표 낱말 중 정본에 없는 것(알림, 단어 아닌 줄 포함) {len(miss)}")
    else:
        print("  ⏭ 원본이 없다 — 원본 대조는 건너뛴다")
    for m in fail:
        print(f"  🔴 {m}")
    print(f"ed4 고유명사 정본 {n}항목 — {'🔴 어긋났다' if fail else '✅ 원본과 맞는다'}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
