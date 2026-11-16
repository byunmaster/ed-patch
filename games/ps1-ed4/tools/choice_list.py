"""선택지 창(`3B`) 전수 목록 — 멤버 · 지금(원판) 열 · 항목(우리 문안·반각 섞은 px) · 맞출 열. 읽기 전용.

    python3 tools/choice_list.py [--start]   # --start: 새 게임 시작 흐름(AT·AR 첫 장 멤버)만
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
import choice
import dump
import reinsert
import script_kr
import typeset


def rows():
    out = []
    kr = script_kr.load_all()
    for path, nm, data, off, sz in dump.script_members():
        key = (path, nm)
        if key not in kr:
            continue
        mem = data[off : off + sz]
        try:
            info = typeset.sm_text_base(mem), typeset.sm_table_len(mem)
        except Exception:
            continue
        segs = reinsert.member_segments(mem)
        for p, cols, nrow, idxs in choice.scan(mem, info[0], info[1]):
            items = [kr[key].get(i, {}).get("kr", "") for i in idxs]
            px = max(typeset.px_width(t) for t in items)
            need = min(choice.MAX_COLS, max(choice.MIN_COLS, -(-(px + choice.ENGINE_CLIP_PX) // 12)))
            out.append((path, nm.split("\\")[-1], p, cols, items, px, need, [len(segs[i]) for i in idxs]))
    return out


def main():
    start = "--start" in sys.argv
    for path, nm, p, cols, items, px, need, jlen in rows():
        if start and not nm.startswith(("AT0", "AR0")):
            continue
        print(f"{path}!{nm} @{p:#x}  열 {cols}→{need}  최대 {px}px  원문 글자수 {jlen}  " + " / ".join(items))


if __name__ == "__main__":
    main()
