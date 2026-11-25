"""음성 자막 V02~V16 **실제 장면**을 헤드리스에서 재생해 자막 창을 찍는다(롬·세이브 불변, 상태·RAM 쓰기는 진입용).

    sh scripts/capture.sh python3 games/ss-ed3/tools/voice_scene.py <디스크.cue> <백업RAM.bkr> <출력폴더> \\
        --disc 1 --scenes V02,V03 [--slot 0] [--maxf 9000] [--entry preload|arm]

방법(10-24): 필드가 한가할 때(스크립트 PC 전역 `0x0609408C` = 0) PC 에 스크립트 주소를 쓰면 엔진이 그 스크립트를 돈다(`dialog_sweep.py` 와 같은 길).
  ① 구운 이미지의 `MAPnnn.BIN`(음성 칸이 붙은 **우리 맵**) 바이트를 `0x00200000` 에 통째로 쓴다 — 시계 장면 표(`voice.json` `clock`)가 맵 꼬리에 있다.
  ② PC 를 그 장면의 **미리 싣기 자리**(`clock.preload.off`, 없으면 `clock.off`)에 둔다 — 여기서 FF 42(음성) 로 이어진다.
  ③ 자막 창 깃발(`subtitle_stub` 변수 표 `flag`)이 올라가는 순간마다 화면을 남기고, 깃발 오름 수를 `items` 수와 견준다.
⚠ 배경·배우는 옛 맵 그대로다 — **자막 창·얼굴·시각**만 판정한다. 장면 밖 연출(배우 이동)은 이 길로 못 본다.
산출: <출력폴더>/<장면>/ 캡처 + result.jsonl(깃발 오름 수 · items 수 · 마지막 깃발 프레임).
"""

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import ss_headless as H
import subtitle_stub as SS

PC = 0x0609408C
LWRAM = 0x00200000
NOSHOT = False
ORIG_DISC = 0


def scenes_table():
    with open(os.path.join(C.GAME_DIR, "script", "voice.json"), encoding="utf-8") as f:
        d = json.load(f)
    return {
        k: v for k, v in d.items() if k.startswith("V") and isinstance(v, dict) and "clock" in v
    }


def map_bytes(cue, stem, orig_disc=0):
    """구운 이미지(`cue` 의 `.bin`)에서 그 맵 파일 바이트 — 옮겨진 맵도 디렉터리 레코드가 새 자리를 가리킨다.
    `orig_disc` 가 있으면 **원판**(그 번호 디스크)에서 읽는다(원판 대조용)."""
    from shared.disc import Disc

    if orig_disc:
        with C.open_disc(orig_disc) as d:
            fs = {n: (lba, size) for n, lba, size in d.files()}
            return d.read_extent(*fs[f"/MAP/{stem}.BIN"])
    binp = cue[:-4] + ".bin"
    d = Disc(binp, user_off=C.USER_OFF)
    fs = {n: (lba, size) for n, lba, size in d.files()}
    return d.read_extent(*fs[f"/MAP/{stem}.BIN"])


class Run:
    def __init__(self, cue, bkr, out):
        core = os.path.join(H.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
        self.h = H.Harness(core, cue, out, bkr=bkr)
        self.cue = cue
        self.out = out

    def u32(self, a):
        return struct.unpack(">I", self.h.peek(a, 4))[0]

    def to_field(self, slot):
        """부팅 → 불러오기 `slot`(0 부터) → 필드가 한가해질 때까지."""
        h = self.h
        h.press("start", 10, 300)
        h.press("start", 10, 300)
        h.run(2205)
        h.press("start", 10, 120)
        h.press("c", 10, 120)
        h.press("c", 10, 120)
        for _ in range(slot):
            h.press("down", 6, 10)
        h.press("c", 10, 300)
        h.press("c", 10, 300)
        h.run(900)
        return self.u32(PC)

    def play(self, vid, spec, maxf, entry, shot_gap=90):
        h = self.h
        stem = f"MAP{spec['map']:03d}" if isinstance(spec["map"], int) else spec["map"]
        data = map_bytes(self.cue, stem, ORIG_DISC)
        clk = spec["clock"]
        off = clk["preload"]["off"] if entry == "preload" and clk.get("preload") else clk["off"]
        flag = SS.build()[2]["flag"]
        h.poke(LWRAM, data)
        h.run(2)
        h.poke(PC, struct.pack(">I", LWRAM + off))
        os.makedirs(os.path.join(self.out, vid), exist_ok=True)
        rises, last_on, last_shot, shots = 0, False, -9999, 0
        pcs = []
        last_rise = None
        for fr in range(maxf):
            h.run(1)
            on = bool(struct.unpack(">H", h.peek(flag, 2))[0]) if fr % 2 == 0 else last_on
            if on and not last_on:
                rises += 1
                last_rise = fr
            last_on = on
            if fr % 300 == 0:
                pcs.append(self.u32(PC) - LWRAM)
            if on and fr - last_shot >= shot_gap and not NOSHOT:
                h.shot(f"{vid}/{vid}_{fr:06d}")
                last_shot = fr
                shots += 1
        return {"scene": vid, "map": stem, "entry": entry, "pc": hex(LWRAM + off), "rises": rises,
                "items": len(spec["items"]), "last_rise": last_rise, "shots": shots, "frames": maxf, "pcs": pcs}  # fmt: skip


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cue")
    ap.add_argument("bkr")
    ap.add_argument("out")
    ap.add_argument("--scenes", required=True)
    ap.add_argument("--slot", type=int, default=0)
    ap.add_argument("--maxf", type=int, default=9000)
    ap.add_argument("--entry", default="preload")
    ap.add_argument(
        "--orig-disc",
        type=int,
        default=0,
        help="원판 대조 — 이 번호 디스크의 원판 맵 바이트를 쓴다(이미지는 원판 cue 를 준다)",
    )
    ap.add_argument(
        "--noshot", action="store_true", help="화면을 안 찍고 PC 궤적만 본다(원판 대조용)"
    )
    a = ap.parse_args()
    global NOSHOT, ORIG_DISC
    NOSHOT = a.noshot
    ORIG_DISC = a.orig_disc
    os.makedirs(a.out, exist_ok=True)
    tbl = scenes_table()
    r = Run(a.cue, a.bkr, a.out)
    pc = r.to_field(a.slot)
    print(f"필드 PC={pc:#x}", flush=True)
    base = r.h.snap()
    log = open(os.path.join(a.out, "result.jsonl"), "a")  # noqa: SIM115
    for vid in a.scenes.split(","):
        r.h.restore(base)
        r.h.run(1)
        rec = r.play(vid, tbl[vid], a.maxf, a.entry)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.flush()


if __name__ == "__main__":
    main()
