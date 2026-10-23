"""헤드리스 에뮬 하네스 — genesis_plus_gx libretro 코어를 ctypes 로 돌린다(emucap 호출 0번으로 일괄 시험).

    코어: `.local/cache/gpgx/genesis_plus_gx_libretro.so` (libretro 빌드봇 nightly — 바이너리는 커밋하지 않는다)
    from headless import Core
    c = Core(rom_path, sram_path)      # sram 은 16KB `.sav|.srm`(웹 세이브와 같은 바이트)
    c.run(120); c.press("c", 8); png = c.shot("x.png"); c.ram(addr, n)  # addr 은 68000 주소(0xFF0000~) 또는 RAM 오프셋

입력: libretro 패드 → 메가드라이브(코어 규약): B=0 Y=1 SELECT=2 START=3 UP=4 DOWN=5 LEFT=6 RIGHT=7 A=8 X=9 L=10 R=11 (실측으로 맞춘다 — `BTN`).
"""

import ctypes as C
import os
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
CORE = Path(os.environ.get("GPGX_CORE", "")) if os.environ.get("GPGX_CORE") else None


def _common_dir() -> Path:
    # 워크트리에는 .local 이 안 따라온다 — 메인 트리 것을 거슬러 찾는다(git common dir)
    import subprocess

    out = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return (Path(out) if os.path.isabs(out) else ROOT / out).resolve().parent


def core_path() -> Path:
    if CORE:
        return CORE
    p = _common_dir() / ".local" / "cache" / "gpgx" / "genesis_plus_gx_libretro.so"
    if not p.exists():
        raise SystemExit(
            f"코어 없음: {p} — libretro 빌드봇 genesis_plus_gx_libretro.so.zip 을 받아 푼다"
        )
    return p


ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUD = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
AUS = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
POLL = C.CFUNCTYPE(None)
INP = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)

BTN = {
    "b": 0,
    "y": 1,
    "select": 2,
    "start": 3,
    "up": 4,
    "down": 5,
    "left": 6,
    "right": 7,
    "a": 8,
    "x": 9,
    "l": 10,
    "r": 11,
}
# 메가드라이브 A/B/C ↔ libretro: GPGX 는 B→MD A · A→MD B · R(또는 X?)→MD C 로 매핑한다 — `MD` 로 이름을 맞춘다(실측 필요)
MD = {"a": "y", "b": "b", "c": "a"}


class Var(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class GameInfo(C.Structure):
    _fields_ = [
        ("path", C.c_char_p),
        ("data", C.c_void_p),
        ("size", C.c_size_t),
        ("meta", C.c_char_p),
    ]


class Core:
    def __init__(self, rom: str, sram: str | None = None, workdir: str | None = None):
        here = Path(workdir) if workdir else _common_dir() / ".local" / "cache" / "gpgx"
        self.sysdir = here / "system"
        self.savedir = here / "save"
        self.sysdir.mkdir(parents=True, exist_ok=True)
        self.savedir.mkdir(parents=True, exist_ok=True)
        self.lib = C.CDLL(str(core_path()))
        self.fmt = 0
        self.frame = None
        self.held: set[int] = set()
        self._keep: list = []
        self.cbs = [
            ENV(self._env),
            VID(self._vid),
            AUD(lambda d, n: n),
            AUS(lambda lft, rgt: None),
            POLL(lambda: None),
            INP(self._inp),
        ]
        L = self.lib
        L.retro_set_environment(self.cbs[0])
        L.retro_set_video_refresh(self.cbs[1])
        L.retro_set_audio_sample(self.cbs[3])
        L.retro_set_audio_sample_batch(self.cbs[2])
        L.retro_set_input_poll(self.cbs[4])
        L.retro_set_input_state(self.cbs[5])
        L.retro_init()
        data = Path(rom).read_bytes()
        self._rom = C.create_string_buffer(data, len(data))
        gi = GameInfo(str(rom).encode(), C.cast(self._rom, C.c_void_p), len(data), None)
        if not L.retro_load_game(C.byref(gi)):
            raise SystemExit("롬을 못 올렸다")
        L.retro_get_memory_data.restype = C.c_void_p
        L.retro_get_memory_size.restype = C.c_size_t
        L.retro_serialize_size.restype = C.c_size_t
        self.run(1)
        self.sram_ptr = L.retro_get_memory_data(0)
        self.sram_size = L.retro_get_memory_size(0)
        self.ram_ptr = L.retro_get_memory_data(2)
        self.ram_size = L.retro_get_memory_size(2)
        if sram:
            d = Path(sram).read_bytes()
            C.memmove(self.sram_ptr, d, min(len(d), self.sram_size))

    # ── libretro 콜백
    def _env(self, cmd, data):
        cmd &= 0xFFFF
        if cmd in (9, 31):  # system / save dir
            p = C.c_char_p(str(self.sysdir if cmd == 9 else self.savedir).encode())
            self._keep.append(p)
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(p, C.c_void_p)
            return True
        if cmd == 10:  # pixel format
            self.fmt = C.cast(data, C.POINTER(C.c_uint))[0]
            return True
        if cmd == 17:  # variable update
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if cmd == 3:  # can dupe — 아니라고 답한다(코어가 늘 새 프레임을 준다)
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        return False

    def _vid(self, data, w, h, pitch):
        if not data:
            return
        buf = C.string_at(data, pitch * h)
        if self.fmt == 2:  # RGB565
            a = np.frombuffer(buf, dtype="<u2").reshape(h, pitch // 2)[:, :w].astype(np.uint32)
            r = ((a >> 11) & 31) * 255 // 31
            g = ((a >> 5) & 63) * 255 // 63
            b = (a & 31) * 255 // 31
            self.frame = np.dstack([r, g, b]).astype(np.uint8)
        else:  # XRGB8888
            a = np.frombuffer(buf, dtype=np.uint8).reshape(h, pitch)[:, : w * 4].reshape(h, w, 4)
            self.frame = a[:, :, [2, 1, 0]].copy()

    def _inp(self, port, dev, idx, id_):
        if port != 0 or dev != 1:
            return 0
        return 1 if id_ in self.held else 0

    # ── 조작
    def run(self, n: int = 1):
        for _ in range(n):
            self.lib.retro_run()

    def hold(self, names: str):
        """`a+b+c` 처럼 MD 버튼 이름(a·b·c·start·up·…)으로 누른 채로 둔다(빈 문자열 = 뗀다)."""
        self.held = {BTN[MD.get(x, x)] for x in names.split("+") if x}

    def press(self, names: str, frames: int = 8, after: int = 20):
        self.hold(names)
        self.run(frames)
        self.hold("")
        self.run(after)

    # ── 메모리·상태
    def _off(self, addr: int) -> int:
        return addr & 0xFFFF if addr >= 0xFF0000 else addr

    swap = True  # GPGX(LSB_FIRST) 는 work_ram 이 16비트 단위로 바이트가 뒤집혀 있다 — 바이트 주소는 `^1`(실측)

    def ram(self, addr: int, n: int) -> bytes:
        """RAM 읽기 — 68000 주소(0xFFxxxx)든 오프셋이든 된다."""
        o = self._off(addr)
        raw = C.string_at(self.ram_ptr, 0x10000)
        if not self.swap:
            return raw[o : o + n]
        return bytes(raw[(o + i) ^ 1] for i in range(n))

    def poke(self, addr: int, data: bytes):
        o = self._off(addr)
        for i, b in enumerate(data):
            oo = (o + i) ^ 1 if self.swap else o + i
            C.memmove(self.ram_ptr + oo, bytes([b]), 1)

    def save_state(self) -> bytes:
        n = self.lib.retro_serialize_size()
        b = C.create_string_buffer(n)
        self.lib.retro_serialize(b, n)
        return b.raw

    def load_state(self, d: bytes):
        self.lib.retro_unserialize(d, len(d))

    def shot(self, path: str | None = None):
        im = Image.fromarray(self.frame)
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            im.save(path)
        return im
