#!/usr/bin/env python3
"""최소 libretro 프런트(PC엔진 CD) — beetle-pce(mednafen_pce_libretro.so)를 ctypes 로 돌려 스크립트를 재생한다(emucap 호출 0번, 부팅~침실 약 17초).
코어: `git clone https://github.com/libretro/beetle-pce-libretro && make` → `.local/cache/libretro/mednafen_pce_libretro.so`(바이너리 커밋 금지, `CORE` 환경변수로 덮음). 시스템 디렉터리 = 같은 폴더 `system/`(syscard3.pce 를 둔다).
사용: headless_pce.py <cue> <스크립트.json> <출력폴더> [BRAM.sav]
⚠ 부팅 타이밍이 emucap 과 다르다(타이틀이 더 늦게 온다) — 입력은 화면 확인으로 맞춘다. 패드는 코어 포트 장치를 JOYPAD 로 지정해야 먹는다.
스크립트 연산: wait N · press "i+run" 프레임 [뒤프레임] · shot 이름 · peek 주소(CPU $2000~$3FFF) 길이 · poke 주소 hex ·
              until 주소 hex 최대프레임 (워크 RAM 바이트 열이 나올 때까지) · save 파일 · load 파일
"""

import ctypes as C
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

CUE, SCRIPT, OUT = sys.argv[1:4]
BRAM = sys.argv[4] if len(sys.argv) > 4 else None
# 메인 트리 `.local/cache/libretro/`(워크트리엔 .local 이 없다 — git 공용 디렉터리를 거슬러 찾는다): 코어 .so · system/(syscard3.pce) · save/
_COMMON = subprocess.check_output(
    ["git", "rev-parse", "--git-common-dir"],
    text=True,
    cwd=os.path.dirname(os.path.abspath(__file__)),
).strip()
HERE = os.path.join(os.path.dirname(os.path.abspath(_COMMON)), ".local", "cache", "libretro")
SYS = os.path.join(HERE, "system")
SAVE = os.path.join(HERE, "save")
os.makedirs(OUT, exist_ok=True)
core = C.CDLL(os.environ.get("CORE", os.path.join(HERE, "mednafen_pce_libretro.so")))
ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUD = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
AUS = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
POLL = C.CFUNCTYPE(None)
INP = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class Var(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class GameInfo(C.Structure):
    _fields_ = [
        ("path", C.c_char_p),
        ("data", C.c_void_p),
        ("size", C.c_size_t),
        ("meta", C.c_char_p),
    ]


state = {"fmt": 0, "frame": None, "held": set()}
keep = []
LOG = C.CFUNCTYPE(None, C.c_int, C.c_char_p)
logcb = LOG(
    lambda lv, fmt: print(
        "LOG", lv, fmt.decode(errors="replace").strip(), file=sys.stderr, flush=True
    )
)


class LogCB(C.Structure):
    _fields_ = [("log", LOG)]


logs = LogCB(logcb)


def env(cmd, data):
    cmd &= 0xFFFF
    if os.environ.get("ENVDBG"):
        print("ENV", cmd, file=sys.stderr, flush=True)
    if cmd == 27:
        C.cast(data, C.POINTER(LogCB))[0] = logs
        return True
    if cmd in (9, 31):
        p = C.c_char_p((SYS if cmd == 9 else SAVE).encode())
        keep.append(p)
        C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(p, C.c_void_p)
        return True
    if cmd == 10:
        state["fmt"] = C.cast(data, C.POINTER(C.c_uint))[0]
        return True
    if cmd == 15:
        return False
    if cmd == 17:
        C.cast(data, C.POINTER(C.c_bool))[0] = False
        return True
    if cmd == 3:
        C.cast(data, C.POINTER(C.c_bool))[0] = True
        return True
    return False


def vid(data, w, h, pitch):
    if not data:
        return
    buf = C.string_at(data, pitch * h)
    if state["fmt"] == 2:
        a = np.frombuffer(buf, dtype="<u2").reshape(h, pitch // 2)[:, :w].astype(np.uint32)
        r = ((a >> 11) & 31) * 255 // 31
        g = ((a >> 5) & 63) * 255 // 63
        b = (a & 31) * 255 // 31
        state["frame"] = np.dstack([r, g, b]).astype(np.uint8)
    else:
        a = np.frombuffer(buf, dtype=np.uint8).reshape(h, pitch)[:, : w * 4].reshape(h, w, 4)
        state["frame"] = a[:, :, [2, 1, 0]].copy()


# beetle-pce 패드: PCE I = RetroPad B(0), II = RetroPad A(8), SELECT=2, RUN=START(3)
BTN = {"i": 8, "ii": 0, "select": 2, "run": 3, "up": 4, "down": 5, "left": 6, "right": 7}


def inp(port, dev, idx, id_):
    return 1 if (port == 0 and dev == 1 and id_ in state["held"]) else 0


cbs = [
    ENV(env),
    VID(vid),
    AUD(lambda d, n: n),
    AUS(lambda l, r: None),
    POLL(lambda: None),
    INP(inp),
]
core.retro_set_environment(cbs[0])
core.retro_set_video_refresh(cbs[1])
core.retro_set_audio_sample(cbs[3])
core.retro_set_audio_sample_batch(cbs[2])
core.retro_set_input_poll(cbs[4])
core.retro_set_input_state(cbs[5])
core.retro_init()
assert core.retro_load_game(C.byref(GameInfo(CUE.encode(), None, 0, None))), "load fail"
core.retro_get_memory_data.restype = C.c_void_p
core.retro_get_memory_size.restype = C.c_size_t
core.retro_serialize_size.restype = C.c_size_t
core.retro_set_controller_port_device(0, 1)
core.retro_run()
if BRAM:
    mp = core.retro_get_memory_data(0)
    d = open(BRAM, "rb").read()
    C.memmove(mp, d, min(d.__len__(), core.retro_get_memory_size(0)))
frames = 0


def run(n):
    global frames
    for _ in range(n):
        core.retro_run()
        frames += 1


def ram(a):
    return core.retro_get_memory_data(2) + ((int(a.lstrip("$"), 16) - 0x2000) & 0x1FFF)


def shot(name):
    Image.fromarray(state["frame"]).save(os.path.join(OUT, name + ".png"))


for step in json.load(open(SCRIPT)):
    op = step[0]
    if op == "wait":
        run(step[1])
    elif op == "press":
        state["held"] = {BTN[b] for b in step[1].split("+")}
        run(step[2])
        state["held"] = set()
        run(step[3] if len(step) > 3 else 20)
    elif op == "shot":
        shot(step[1])
        print("shot", step[1], "frame", frames, flush=True)
    elif op == "peek":
        print(
            "peek", step[1], C.string_at(ram(step[1]), step[2]).hex(), "frame", frames, flush=True
        )
    elif op == "poke":
        C.memmove(ram(step[1]), bytes.fromhex(step[2]), len(step[2]) // 2)
    elif op == "until":
        want = bytes.fromhex(step[2])
        n = 0
        while C.string_at(ram(step[1]), len(want)) != want and n < step[3]:
            run(1)
            n += 1
        print("until", step[1], "hit" if n < step[3] else "timeout", "frame", frames, flush=True)
    elif op == "save":
        n = core.retro_serialize_size()
        b = C.create_string_buffer(n)
        core.retro_serialize(b, n)
        open(step[1], "wb").write(b.raw)
    elif op == "load":
        d = open(step[1], "rb").read()
        core.retro_unserialize(d, len(d))
print("done", frames)
