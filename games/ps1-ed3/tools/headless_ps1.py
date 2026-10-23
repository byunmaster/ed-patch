"""libretro 코어(pcsx_rearmed)를 emucap 없이 스크립트로 돌리는 최소 프런트 — 호출 없이 RAM 쓰기·입력·캡처를 루프로 한다.

코어 `.so` 는 레포에 없다 — `.local/cache/rearmed/pcsx_rearmed_libretro.so`(ps1-ed1+2 하네스와 같은 것)를 두고 `CORE` 환경변수로 덮을 수 있다.
BIOS 는 emucap 펌웨어 폴더를 링크한다. 무거운 일이니 `sh scripts/heavy.sh …` 로 돌린다. 원본·세이브는 읽기만 한다(카드는 메모리에 올려 쓴다 — 파일은 안 바뀐다).
"""

import ctypes as C
import os
import subprocess

import numpy as np
from PIL import Image


BTN = {"b": 0, "y": 1, "select": 2, "start": 3, "up": 4, "down": 5, "left": 6, "right": 7, "a": 8, "x": 9, "l1": 10, "r1": 11, "l2": 12, "r2": 13}
ALIAS = {"cross": "b", "circle": "a", "square": "y", "triangle": "x"}  # PS1 → libretro 이름


def _cache():
    top = os.path.dirname(subprocess.check_output(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], text=True).strip())
    return os.path.join(top, ".local", "cache", "rearmed")


class Var(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]


class Emu:
    def __init__(self, cue, card=None):
        here = _cache()
        self.sysdir, self.savedir = os.path.join(here, "system"), os.path.join(here, "save")
        os.makedirs(self.sysdir, exist_ok=True)
        os.makedirs(self.savedir, exist_ok=True)
        for b in ("scph5500.bin", "scph5501.bin", "scph5502.bin"):
            s, d = "/root/.local/share/emucap/firmware/" + b, os.path.join(self.sysdir, b)
            if os.path.exists(s) and not os.path.exists(d):
                os.symlink(s, d)
        self.core = C.CDLL(os.environ.get("CORE", os.path.join(here, "pcsx_rearmed_libretro.so")))
        self.fmt, self.frame, self.held, self._keep = 0, None, set(), []
        env_t = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
        vid_t = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
        aud_t = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
        aus_t = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
        poll_t = C.CFUNCTYPE(None)
        inp_t = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
        self._cbs = [
            env_t(self._env), vid_t(self._vid), aud_t(lambda d, n: n), aus_t(lambda left, right: None),
            poll_t(lambda: None), inp_t(lambda p, dev, i, id_: 1 if (p == 0 and dev == 1 and id_ in self.held) else 0),
        ]
        c = self.core
        c.retro_set_environment(self._cbs[0])
        c.retro_set_video_refresh(self._cbs[1])
        c.retro_set_audio_sample(self._cbs[3])
        c.retro_set_audio_sample_batch(self._cbs[2])
        c.retro_set_input_poll(self._cbs[4])
        c.retro_set_input_state(self._cbs[5])
        c.retro_init()
        gi = GameInfo(cue.encode(), None, 0, None)
        assert c.retro_load_game(C.byref(gi)), "retro_load_game 실패"
        c.retro_get_memory_data.restype = C.c_void_p
        c.retro_get_memory_size.restype = C.c_size_t
        c.retro_serialize_size.restype = C.c_size_t
        c.retro_run()
        if card:
            mp, ms = c.retro_get_memory_data(0), c.retro_get_memory_size(0)
            data = open(card, "rb").read()
            C.memmove(mp, data, min(len(data), ms))
        self.ram = c.retro_get_memory_data(2)

    def _env(self, cmd, data):
        cmd &= 0xFFFF
        if cmd in (9, 31):
            p = C.c_char_p((self.sysdir if cmd == 9 else self.savedir).encode())
            self._keep.append(p)
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(p, C.c_void_p)
            return True
        if cmd == 10:
            self.fmt = C.cast(data, C.POINTER(C.c_uint))[0]
            return True
        if cmd == 15:
            v = C.cast(data, C.POINTER(Var))[0]
            vals = {b"pcsx_rearmed_memcard1": b"libretro", b"pcsx_rearmed_memcard2": b"disabled"}
            if v.key in vals:
                p = C.c_char_p(vals[v.key])
                self._keep.append(p)
                C.cast(data, C.POINTER(Var))[0].value = p
                return True
            return False
        if cmd == 17:
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if cmd == 3:
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        return False

    def _vid(self, data, w, h, pitch):
        if not data:
            return
        buf = C.string_at(data, pitch * h)
        if self.fmt == 2:
            a = np.frombuffer(buf, dtype="<u2").reshape(h, pitch // 2)[:, :w].astype(np.uint32)
            r, g, b = ((a >> 11) & 31) * 255 // 31, ((a >> 5) & 63) * 255 // 63, (a & 31) * 255 // 31
            self.frame = np.dstack([r, g, b]).astype(np.uint8)
        else:
            a = np.frombuffer(buf, dtype=np.uint8).reshape(h, pitch)[:, : w * 4].reshape(h, w, 4)
            self.frame = a[:, :, [2, 1, 0]].copy()

    def run(self, n=1):
        for _ in range(n):
            self.core.retro_run()

    def press(self, buttons, frames=10, after=20):
        self.held = {BTN[ALIAS.get(b, b)] for b in buttons.split("+")}
        self.run(frames)
        self.held = set()
        self.run(after)

    def shot(self, path):
        Image.fromarray(self.frame).save(path)

    def peek(self, addr, n):
        return C.string_at(self.ram + (addr & 0x1FFFFF), n)

    def poke(self, addr, data):
        C.memmove(self.ram + (addr & 0x1FFFFF), bytes(data), len(data))

    def u32(self, addr):
        return int.from_bytes(self.peek(addr, 4), "little")

    def save(self, path):
        n = self.core.retro_serialize_size()
        b = C.create_string_buffer(n)
        self.core.retro_serialize(b, n)
        with open(path, "wb") as f:
            f.write(b.raw)

    def load(self, path):
        with open(path, "rb") as f:
            d = f.read()
        self.core.retro_unserialize(d, len(d))
