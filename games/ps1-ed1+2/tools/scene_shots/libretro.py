"""libretro 코어(pcsx_rearmed)를 ctypes 로 직접 돌리는 최소 머신 — 프레임·RAM·버튼·세이브스테이트.

코어 `.so` 와 BIOS 디렉터리는 이 머신의 것이라 레포에 없다 — 인자(또는 환경변수)로 받는다.
"""

import ctypes as C
import os

import numpy as np
from PIL import Image

BTN = {
    "b": 0, "y": 1, "select": 2, "start": 3, "up": 4, "down": 5, "left": 6, "right": 7,
    "a": 8, "x": 9, "l1": 10, "r1": 11, "l2": 12, "r2": 13,
}  # fmt: skip
ALIAS = {"cross": "b", "circle": "a", "square": "y", "triangle": "x"}


class _Var(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class _GameInfo(C.Structure):
    _fields_ = [
        ("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p),
    ]  # fmt: skip


_ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
_VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
_AUD = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
_AUS = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
_POLL = C.CFUNCTYPE(None)
_INP = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class Machine:
    """cue 하나를 부팅한 PS1. 메모리카드는 코어 안(libretro 가상 카드)에 둔다."""

    def __init__(self, core: str, system_dir: str, save_dir: str, cue: str, mcr: str | None = None):
        self.st = {"fmt": 0, "frame": None, "held": set()}
        self._keep = []
        st, keep = self.st, self._keep
        opts = {b"pcsx_rearmed_memcard1": b"libretro", b"pcsx_rearmed_memcard2": b"disabled"}

        def env(cmd, data):
            cmd &= 0xFFFF
            if cmd in (9, 31):  # SYSTEM_DIRECTORY · SAVE_DIRECTORY
                p = C.c_char_p((system_dir if cmd == 9 else save_dir).encode())
                keep.append(p)
                C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(p, C.c_void_p)
                return True
            if cmd == 10:  # PIXEL_FORMAT
                st["fmt"] = C.cast(data, C.POINTER(C.c_uint))[0]
                return True
            if cmd == 15:  # GET_VARIABLE
                v = C.cast(data, C.POINTER(_Var))[0]
                if v.key in opts:
                    p = C.c_char_p(opts[v.key])
                    keep.append(p)
                    C.cast(data, C.POINTER(_Var))[0].value = p
                    return True
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
            if st["fmt"] == 2:  # RGB565
                a = np.frombuffer(buf, dtype="<u2").reshape(h, pitch // 2)[:, :w].astype(np.uint32)
                r = ((a >> 11) & 31) * 255 // 31
                g = ((a >> 5) & 63) * 255 // 63
                b = (a & 31) * 255 // 31
                st["frame"] = np.dstack([r, g, b]).astype(np.uint8)
            else:  # XRGB8888
                a = (
                    np.frombuffer(buf, dtype=np.uint8)
                    .reshape(h, pitch)[:, : w * 4]
                    .reshape(h, w, 4)
                )
                st["frame"] = a[:, :, [2, 1, 0]].copy()

        def inp(port, dev, _idx, id_):
            return 1 if port == 0 and dev == 1 and id_ in st["held"] else 0

        self._cbs = [
            _ENV(env), _VID(vid), _AUD(lambda d, n: n), _AUS(lambda lft, rgt: None),
            _POLL(lambda: None), _INP(inp),
        ]  # fmt: skip
        cb = self._cbs
        c = self.core = C.CDLL(core)
        c.retro_set_environment(cb[0])
        c.retro_set_video_refresh(cb[1])
        c.retro_set_audio_sample(cb[3])
        c.retro_set_audio_sample_batch(cb[2])
        c.retro_set_input_poll(cb[4])
        c.retro_set_input_state(cb[5])
        c.retro_init()
        self._gi = _GameInfo(cue.encode(), None, 0, None)
        if not c.retro_load_game(C.byref(self._gi)):
            raise RuntimeError(f"코어가 이미지를 못 열었다: {cue}")
        c.retro_get_memory_data.restype = C.c_void_p
        c.retro_get_memory_size.restype = C.c_size_t
        c.retro_serialize_size.restype = C.c_size_t
        c.retro_run()
        mp, ms = c.retro_get_memory_data(0), c.retro_get_memory_size(0)
        if mcr and mp:
            with open(mcr, "rb") as f:
                d = f.read()
            C.memmove(mp, d, min(len(d), ms))
        self.ram = c.retro_get_memory_data(2)

    def run(self, n: int):
        for _ in range(n):
            self.core.retro_run()

    def press(self, buttons: str, hold: int = 4, after: int = 20):
        self.st["held"] = {BTN[ALIAS.get(x, x)] for x in buttons.split("+")}
        self.run(hold)
        self.st["held"] = set()
        self.run(after)

    def frame(self) -> np.ndarray:
        return self.st["frame"].copy()

    def shot(self, path: str):
        Image.fromarray(self.st["frame"]).save(path)

    def poke(self, addr: int, data):
        if isinstance(data, int):
            data = data.to_bytes(4, "little")
        C.memmove(self.ram + (addr & 0x1FFFFF), bytes(data), len(data))

    def peek(self, addr: int, n: int = 4) -> bytes:
        return C.string_at(self.ram + (addr & 0x1FFFFF), n)

    def w32(self, addr: int) -> int:
        return int.from_bytes(self.peek(addr, 4), "little")

    def dump(self) -> bytes:
        return C.string_at(self.ram, 0x200000)

    def save(self, path: str):
        n = self.core.retro_serialize_size()
        b = C.create_string_buffer(n)
        self.core.retro_serialize(b, n)
        with open(path, "wb") as f:
            f.write(b.raw)

    def load(self, path: str):
        with open(path, "rb") as f:
            d = f.read()
        self.core.retro_unserialize(d, len(d))


def default_core() -> str:
    return os.environ.get("PS1_LIBRETRO_CORE", "")
