#!/usr/bin/env python3
"""새턴 헤드리스 하네스 — beetle-saturn libretro 코어를 ctypes 로 돌린다(emucap 호출 0번).

    python3 tools/ss_headless.py <이미지.cue> <스크립트.json> <출력폴더> [--core <so>] [--bkr <백업RAM.bkr>]

스크립트: [["wait",프레임],["press","c",프레임,후프레임],["shot","이름"],
          ["save","경로"],["load","경로"],["poke","0x06037F56","e915"],["peek","0x06037F56",길이],
          ["find","hex"]]
🔴 **코어·BIOS·세이브는 git 밖이다** — 코어는 `.local/cache/beetle-saturn/src/mednafen_saturn_libretro.so`
   (`git clone libretro/beetle-saturn-libretro && make -j8`), BIOS 는 emucap firmware 에서 시스템 폴더로 심볼릭 링크한다.
   스테이트는 **내비게이션 전용**이다 — 문안 확인에 쓰지 않는다(CLAUDE.md).
⚠ 주소는 SH-2 주소다. WorkRAM-L(0x00200000~)·H(0x06000000~) 를 한 버퍼의 앞·뒤 1MB 로 매핑한다.
"""

import ctypes as C
import json
import os
import sys

import numpy as np
from PIL import Image

def _cache_dir():
    """메인 트리의 `.local/cache` — 워크트리 안에는 `.local` 을 만들지 않는다(CLAUDE.md)."""
    here = os.path.dirname(os.path.abspath(__file__))
    common = os.popen(f"git -C '{here}' rev-parse --path-format=absolute --git-common-dir").read().strip()
    return os.path.join(os.path.dirname(common), ".local", "cache")


CACHE = _cache_dir()

ENV_SYSTEM_DIR, ENV_SAVE_DIR, ENV_PIXFMT, ENV_GETVAR, ENV_VARUPD = 9, 31, 10, 15, 17


class Var(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]


# 새턴 버튼 → libretro 조이패드 id (beetle-saturn `input.c` 표: Saturn A=libretro B · B=A · C=R · X=Y · Y=X · Z=L · L=L2 · R=R2)
BTN = {
    "a": 0, "x": 1, "start": 3, "up": 4, "down": 5, "left": 6, "right": 7,
    "b": 8, "y": 9, "z": 10, "c": 11, "l": 12, "r": 13,
}  # fmt: skip


class Harness:
    def __init__(self, core_so, cue, outdir, bios_dir=None, bkr=None):
        self.out = outdir
        os.makedirs(outdir, exist_ok=True)
        here = os.path.join(CACHE, "beetle-saturn")
        self.sys = os.path.join(here, "system")
        self.sav = os.path.join(here, "save")
        os.makedirs(self.sys, exist_ok=True)
        os.makedirs(self.sav, exist_ok=True)
        fw = bios_dir or "/root/.local/share/emucap/firmware"
        for b in ("sega_101.bin", "mpr-17933.bin"):
            s, d = os.path.join(fw, b), os.path.join(self.sys, b)
            if os.path.exists(s) and not os.path.exists(d):
                os.symlink(s, d)
        self.core = C.CDLL(core_so)
        self.frame, self.fmt, self.held = None, 0, set()
        self._keep = []
        ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
        VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
        AUD = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
        AUS = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
        POLL = C.CFUNCTYPE(None)
        INP = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
        self._cbs = [
            ENV(self._env), VID(self._vid), AUD(lambda d, n: n), AUS(lambda a, b: None),
            POLL(lambda: None), INP(self._inp),
        ]  # fmt: skip
        c = self.core
        c.retro_set_environment(self._cbs[0])
        c.retro_set_video_refresh(self._cbs[1])
        c.retro_set_audio_sample(self._cbs[3])
        c.retro_set_audio_sample_batch(self._cbs[2])
        c.retro_set_input_poll(self._cbs[4])
        c.retro_set_input_state(self._cbs[5])
        c.retro_init()
        gi = GameInfo(cue.encode(), None, 0, None)
        assert c.retro_load_game(C.byref(gi)), "load fail"
        c.retro_get_memory_data.restype = C.c_void_p
        c.retro_get_memory_size.restype = C.c_size_t
        c.retro_serialize_size.restype = C.c_size_t
        if bkr:  # 내부 백업 RAM(32KB) — emucap `.bkr` 과 같은 바이트
            bp, bs = c.retro_get_memory_data(0), c.retro_get_memory_size(0)
            d = open(bkr, "rb").read()
            assert bp and bs >= len(d), f"백업 RAM 을 못 연다 ({bp}, {bs})"
            C.memmove(bp, d, len(d))
        self.ram = c.retro_get_memory_data(2)
        self.ram_size = c.retro_get_memory_size(2)
        self.run(1)

    # ── libretro 콜백
    def _env(self, cmd, data):
        cmd &= 0xFFFF
        if cmd in (ENV_SYSTEM_DIR, ENV_SAVE_DIR):
            p = C.c_char_p((self.sys if cmd == ENV_SYSTEM_DIR else self.sav).encode())
            self._keep.append(p)
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(p, C.c_void_p)
            return True
        if cmd == ENV_PIXFMT:
            self.fmt = C.cast(data, C.POINTER(C.c_uint))[0]
            return True
        if cmd == ENV_GETVAR:
            v = C.cast(data, C.POINTER(Var))[0]
            val = {b"beetle_saturn_region": b"Japan", b"beetle_saturn_autortc": b"enabled"}.get(v.key)
            if val:
                p = C.c_char_p(val)
                self._keep.append(p)
                C.cast(data, C.POINTER(Var))[0].value = p
                return True
            return False
        if cmd == ENV_VARUPD:
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

    def _inp(self, port, dev, idx, id_):
        return 1 if (port == 0 and dev == 1 and id_ in self.held) else 0

    # ── 조작
    def run(self, n):
        for _ in range(n):
            self.core.retro_run()

    def press(self, names, hold, after=20):
        self.held = {BTN[b] for b in names.split("+")}
        self.run(hold)
        self.held = set()
        self.run(after)

    def shot(self, name):
        Image.fromarray(self.frame).save(os.path.join(self.out, name + ".png"))

    def save(self, path):
        n = self.core.retro_serialize_size()
        b = C.create_string_buffer(n)
        self.core.retro_serialize(b, n)
        open(path, "wb").write(b.raw)

    def load(self, path):
        d = open(path, "rb").read()
        self.core.retro_unserialize(d, len(d))

    def _off(self, addr):
        # WorkRAM-H 0x06000000~ = 버퍼 뒤 1MB, WorkRAM-L 0x00200000~ = 앞 1MB (실측으로 확인할 것)
        a = addr & 0x1FFFFFFF
        return (a - 0x06000000 + 0x100000) if a >= 0x06000000 else (a - 0x00200000)

    # 🔴 코어의 WorkRAM 은 **16비트 단위로 바이트가 뒤집힌 채**(호스트 LE) 들어 있다 — 실측: `0602F14E` 의
    #    `64 90` 이 `90 64` 로 보였다. 바이트 주소 a 는 버퍼의 a^1 이다.
    def peek(self, addr, n):
        o = self._off(addr)
        lo, hi = o & ~1, (o + n + 1) & ~1
        raw = bytearray(C.string_at(self.ram + lo, hi - lo))
        for i in range(0, len(raw), 2):
            raw[i], raw[i + 1] = raw[i + 1], raw[i]
        return bytes(raw[o - lo : o - lo + n])

    def poke(self, addr, data):
        for i, b in enumerate(data):
            C.memmove(self.ram + ((self._off(addr) + i) ^ 1), bytes([b]), 1)

    def find(self, pat):
        buf = bytearray(C.string_at(self.ram, self.ram_size))
        for i in range(0, len(buf), 2):
            buf[i], buf[i + 1] = buf[i + 1], buf[i]
        out, i = [], 0
        while (j := bytes(buf).find(pat, i)) >= 0:
            out.append(j)
            i = j + 1
        return out


def main():
    cue, script, out = sys.argv[1:4]
    core = os.path.join(CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    if "--core" in sys.argv:
        core = sys.argv[sys.argv.index("--core") + 1]
    bkr = sys.argv[sys.argv.index("--bkr") + 1] if "--bkr" in sys.argv else None
    h = Harness(core, cue, out, bkr=bkr)
    print("ram", hex(h.ram or 0), h.ram_size, "fmt", h.fmt, flush=True)
    for step in json.load(open(script)):
        op = step[0]
        if op == "wait":
            h.run(step[1])
        elif op == "press":
            h.press(step[1], step[2], step[3] if len(step) > 3 else 20)
        elif op == "shot":
            h.shot(step[1])
            print("shot", step[1], h.frame.shape, flush=True)
        elif op == "save":
            h.save(step[1])
        elif op == "load":
            h.load(step[1])
        elif op == "poke":
            h.poke(int(step[1], 16), bytes.fromhex(step[2]))
        elif op == "peek":
            print("peek", step[1], h.peek(int(step[1], 16), step[2]).hex(), flush=True)
        elif op == "find":
            print("find", step[1], [hex(x) for x in h.find(bytes.fromhex(step[1]))[:8]], flush=True)
    print("done")


if __name__ == "__main__":
    main()
