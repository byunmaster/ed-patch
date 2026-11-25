"""바뀐 대사 묶음의 **게임이 그린 화면** 전수 촬영 — `dialog_harness` 로 스트림을 주입해 쪽마다 찍는다.

    # 대상 목록(에뮬 없이): 전·후 조판 JSON 에서 바뀐 스트림
    python3 tools/dialog_sweep.py targets <전.json> <후.json> <목록.json>
    # 촬영(촬영 칸 안에서): sh scripts/capture.sh python3 tools/dialog_sweep.py shoot <cue> <카드> <목록.json> <조판.json> <출력 폴더>

`<조판.json>` = 그 롬의 `page_plan` 결과(`{멤버: {조각: 문안}}`) — 쪽 수 상한 추정에만 쓴다.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build
import script_kr
import typeset


def targets(before, after):
    members = build.identity_gate({})
    out = []
    for key in script_kr.load_all():
        m = key[1]
        mem = members[key]
        wins = typeset.windows(mem)
        streams = typeset.message_streams(mem)
        for si, (st, msg) in enumerate(zip(streams, wins, strict=True)):
            if any(before[m].get(str(i)) != after[m].get(str(i)) for pg in msg for i in pg):
                out.append({"archive": key[0], "member": key[1], "si": si})
    return out


def est_pages(mem, st, texts):
    """스트림의 쪽 수 추정 — 줄 흐름이 없는 끼움은 같은 줄, 쪽 넘김(`02`·`03`·`04`)에서 쪽을 닫는다."""
    pages, lines, prev = 0, 0, None
    for q, v in st["prints"]:
        t = texts.get(str(v)) or ""
        n = sum(1 for k in range(0, len(t), typeset.COLS) if t[k : k + typeset.COLS].strip())
        if prev is not None:
            ops = set(typeset._gap_ops(mem, prev, q))
            if ops & {2, 3, 4}:
                pages += -(-lines // typeset.PAGE_LINES) if lines else 0
                lines = 0
            elif not ops & {1}:
                n = max(0, n - 1) if lines else n  # 같은 줄에 이어 붙음
        lines += n
        prev = q
    pages += -(-lines // typeset.PAGE_LINES) if lines else 0
    return max(pages, 1)


def shoot(cue, card, tfile, jfile, out):
    import dialog_harness as D

    binp = cue.replace(".cue", ".bin")
    texts = json.load(open(jfile))
    tl = json.load(open(tfile))
    os.makedirs(out, exist_ok=True)
    state = "/tmp/claude-0/dhstate_" + os.path.basename(os.path.dirname(cue)) + ".st"
    e = D.make_state(cue, card, state)
    index = []
    for t in tl:
        mem = D.read_member(binp, t["archive"], t["member"])
        st = D.streams(mem)[t["si"]]
        cap = est_pages(mem, st, texts[t["member"]]) + 1
        name = t["member"].split("\\")[-1].replace(".BIN", "")
        shots = D.play_stream(e, state, mem, st, cap, os.path.join(out, f"{name}_s{t['si']:03d}"))
        index.append({**t, "shots": [os.path.basename(s) for s in shots], "est": cap - 1})
        json.dump(index, open(os.path.join(out, "index.json"), "w"), ensure_ascii=False)
    return index


if __name__ == "__main__":
    if sys.argv[1] == "targets":
        b, a = json.load(open(sys.argv[2])), json.load(open(sys.argv[3]))
        t = targets(b, a)
        json.dump(t, open(sys.argv[4], "w"), ensure_ascii=False)
        print(len(t), "스트림")
    else:
        shoot(*sys.argv[2:7])
