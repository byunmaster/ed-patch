#!/usr/bin/env python3
"""새턴 헤드리스 **대화형 서버** — 한 번 부팅해 두고 명령 파일로 조작한다(`heavy.sh` 잠금 한 번에 여러 실험).

    sh scripts/heavy.sh python3 games/ss-ed3/tools/ss_server.py <이미지.cue> <작업폴더> [--bkr 백업RAM.bkr] [--state 시작상태] [--idle 1100]

작업폴더/cmd/NNNN.json 에 명령 하나(`{"op": …}`)를 놓으면 번호 순으로 실행하고 작업폴더/out/NNNN.json 에 결과를 쓴다.
`--idle` 초 동안 명령이 없으면 상태를 `작업폴더/last.state` 에 저장하고 끝난다(잠금 20분 규칙 — 다음 차례에 `--state` 로 이어 간다).

명령: run{n} · press{btns,hold,after} · shot{name,crop?[x0,y0,x1,y1]} · peek{addr,n} · poke{addr,hex} · find{hex} ·
      save{path} · load{path} · script{ops:[…위 명령 목록…]} · quit
🔴 스테이트·RAM 쓰기는 **내비게이션 전용**이다 — 문안은 화면(shot)으로만 판정한다(CLAUDE.md).
"""

import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ss_headless as H


def do(h, c):
    op = c["op"]
    if op == "run":
        h.run(int(c["n"]))
    elif op == "press":
        h.press(c["btns"], int(c.get("hold", 6)), int(c.get("after", 20)))
    elif op == "shot":
        if c.get("crop"):
            from PIL import Image

            x0, y0, x1, y1 = c["crop"]
            Image.fromarray(h.frame[y0:y1, x0:x1]).save(os.path.join(h.out, c["name"] + ".png"))
        else:
            h.shot(c["name"])
        return {"shape": list(h.frame.shape)}
    elif op == "peek":
        return {"hex": h.peek(int(str(c["addr"]), 16), int(c["n"])).hex()}
    elif op == "poke":
        h.poke(int(str(c["addr"]), 16), bytes.fromhex(c["hex"]))
    elif op == "find":
        return {"at": [hex(x) for x in h.find(bytes.fromhex(c["hex"]))[:16]]}
    elif op == "save":
        h.save(c["path"])
    elif op == "load":
        h.load(c["path"])
    elif op == "script":
        return {"results": [do(h, s) for s in c["ops"]]}
    else:
        raise ValueError(op)
    return {}


def main():
    a = sys.argv[1:]
    cue, work = a[0], a[1]
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
    idle = float(opt("--idle", 1100))
    core = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    os.makedirs(os.path.join(work, "cmd"), exist_ok=True)
    os.makedirs(os.path.join(work, "out"), exist_ok=True)
    h = H.Harness(core, cue, os.path.join(work, "shots"), bkr=opt("--bkr"))
    if opt("--state"):
        h.load(opt("--state"))
        h.run(2)
    print("ready", flush=True)
    last = time.time()
    done = set()
    while True:
        cmds = sorted(f for f in glob.glob(os.path.join(work, "cmd", "*.json")) if f not in done)
        if not cmds:
            if time.time() - last > idle:
                break
            time.sleep(0.2)
            continue
        for f in cmds:
            done.add(f)
            last = time.time()
            n = os.path.basename(f)[:-5]
            try:
                with open(f, encoding="utf-8") as fp:
                    c = json.load(fp)
                if c["op"] == "quit":
                    last = 0
                    idle = 0
                    res = {"ok": True}
                else:
                    res = {"ok": True, **do(h, c)}
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "err": repr(e)}
            with open(os.path.join(work, "out", n + ".json"), "w", encoding="utf-8") as fp:
                json.dump(res, fp)
            if idle == 0:
                break
    h.save(os.path.join(work, "last.state"))
    print("bye", flush=True)


if __name__ == "__main__":
    main()
