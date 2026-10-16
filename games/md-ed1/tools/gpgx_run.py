"""최소 libretro 프런트 — genesis_plus_gx 코어를 ctypes 로 돌려 MD 롬을 헤드리스로 굴린다.

emucap 호출 없이 롬을 몰아 돌리는 시험용 도구다(전투·대사 일괄 확인). 코어 바이너리는 커밋하지 않고
`.local/cache/gpgx/genesis_plus_gx_libretro.so` 에서 찾는다(환경변수 `GPGX_CORE` 로 덮는다).
화면은 320x224(전투 창 포함) RGB, 램은 68000 주소 `$FF0000` 부터 64KB 를 바이트 그대로 읽고 쓴다.
"""

import ctypes as C
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent


def main_tree() -> Path:
    """워크트리에는 `.local` 이 안 따라온다 — git 공통 디렉터리의 부모(메인 트리)를 거슬러 찾는다."""
    out = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=HERE,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return (Path(out) if os.path.isabs(out) else (HERE / out)).resolve().parent


CORE = Path(
    os.environ.get("GPGX_CORE")
    or main_tree() / ".local" / "cache" / "gpgx" / "genesis_plus_gx_libretro.so"
)

ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUD = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
AUS = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
POLL = C.CFUNCTYPE(None)
INP = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)

# libretro 조이패드 id (genesis_plus_gx 매핑: Y→A버튼 · B→B · A→C · X→X · L→Y · R→Z · select→Mode)
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
# MD 버튼 이름 → libretro id (MD A=Y, B=B, C=A)
MD = {
    "a": "y",
    "b": "b",
    "c": "a",
    "x": "x",
    "y": "l",
    "z": "r",
    "mode": "select",
    "start": "start",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
}


class Var(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class GameInfo(C.Structure):
    _fields_ = [
        ("path", C.c_char_p),
        ("data", C.c_void_p),
        ("size", C.c_size_t),
        ("meta", C.c_char_p),
    ]


class Genesis:
    """`g = Genesis(rom)` → `g.run(n)` · `g.press("c", 8)` · `g.ram(addr, n)` · `g.shot("a.png")`."""

    def __init__(
        self, rom: str | Path, srm: bytes | None = None, workdir: str | Path | None = None
    ):
        self.keep = []
        self.held: set[int] = set()
        self.frame = None
        self.fmt = 0
        wd = Path(workdir or HERE.parent / "work" / "gpgx")
        (wd / "system").mkdir(parents=True, exist_ok=True)
        (wd / "save").mkdir(parents=True, exist_ok=True)
        self.sysdir, self.savedir = str(wd / "system"), str(wd / "save")
        self.core = C.CDLL(str(CORE))
        c = self.core
        self.cbs = [
            ENV(self._env),
            VID(self._vid),
            AUD(lambda d, n: n),
            AUS(lambda a, b: None),
            POLL(lambda: None),
            INP(self._inp),
        ]
        c.retro_set_environment(self.cbs[0])
        c.retro_set_video_refresh(self.cbs[1])
        c.retro_set_audio_sample(self.cbs[3])
        c.retro_set_audio_sample_batch(self.cbs[2])
        c.retro_set_input_poll(self.cbs[4])
        c.retro_set_input_state(self.cbs[5])
        c.retro_init()
        c.retro_get_memory_data.restype = C.c_void_p
        c.retro_get_memory_size.restype = C.c_size_t
        c.retro_serialize_size.restype = C.c_size_t
        self.rom = Path(rom)
        data = self.rom.read_bytes()
        self.romdata = C.create_string_buffer(data, len(data))
        gi = GameInfo(str(self.rom).encode(), C.cast(self.romdata, C.c_void_p), len(data), None)
        if not c.retro_load_game(C.byref(gi)):
            raise SystemExit("롬을 못 읽었다")
        c.retro_run()
        if srm is not None:
            self.set_sram(srm)
        self.nframes = 1

    # ── 콜백 ──
    def _env(self, cmd, data):
        cmd &= 0xFFFF
        if cmd in (9, 31):
            p = C.c_char_p((self.sysdir if cmd == 9 else self.savedir).encode())
            self.keep.append(p)
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(p, C.c_void_p)
            return True
        if cmd == 10:
            self.fmt = C.cast(data, C.POINTER(C.c_uint))[0]
            return True
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

    # ── 실행 ──
    def run(self, n: int = 1):
        for _ in range(n):
            self.core.retro_run()
            self.nframes += 1

    def hold(self, *names: str):
        self.held = {BTN[MD.get(n, n)] for n in names}

    def release(self):
        self.held = set()

    def press(self, name: str | tuple, frames: int = 8, after: int = 6):
        names = (name,) if isinstance(name, str) else tuple(name)
        self.hold(*names)
        self.run(frames)
        self.release()
        self.run(after)

    # ── 메모리 ──
    def _mem(self, kind: int):
        p = self.core.retro_get_memory_data(kind)
        n = self.core.retro_get_memory_size(kind)
        return p, n

    def ram(self, addr: int, n: int = 1) -> bytes:
        """`$FFxxxx` 또는 하위 16비트 주소. ⚠ 코어는 램을 16비트 단위로 바이트 스왑해 두므로(리틀엔디언 호스트)
        바이트 주소는 `^1` 로 푼다 — 안 풀면 쓴 값이 이웃 바이트로 간다."""
        p, _ = self._mem(2)
        raw = C.string_at(p, 0x10000)
        return bytes(raw[(((addr & 0xFFFF) + i) ^ 1)] for i in range(n))

    def poke(self, addr: int, data: bytes):
        p, _ = self._mem(2)
        for i, b in enumerate(data):
            C.memset(p + (((addr & 0xFFFF) + i) ^ 1), b, 1)

    def sram(self) -> bytes:
        p, n = self._mem(0)
        return bytes(C.string_at(p, n)) if p else b""

    def set_sram(self, data: bytes):
        """⚠ 코어가 크기를 0 이나 1024 로 보고해도 포인터는 64KB 세이브 램이다 — 실제로 쓰면 이어하기 목록이 뜬다."""
        p, _ = self._mem(0)
        if not p:
            raise SystemExit("세이브 램 포인터가 없다")
        C.memmove(p, data[:0x10000], min(len(data), 0x10000))

    # ── 상태 ──
    def save_state(self) -> bytes:
        n = self.core.retro_serialize_size()
        buf = C.create_string_buffer(n)
        if not self.core.retro_serialize(buf, n):
            raise SystemExit("serialize 실패")
        return buf.raw

    def load_state(self, data: bytes):
        buf = C.create_string_buffer(data, len(data))
        if not self.core.retro_unserialize(buf, len(data)):
            raise SystemExit("unserialize 실패")

    # ── 화면 ──
    def image(self) -> Image.Image:
        return Image.fromarray(self.frame)

    def shot(self, path: str | Path):
        self.image().save(path)


if __name__ == "__main__":
    rom = sys.argv[1]
    g = Genesis(rom)
    g.run(120)
    g.shot(sys.argv[2] if len(sys.argv) > 2 else "/tmp/gpgx_test.png")
    print("frame", g.frame.shape, "ram[0..8]", g.ram(0, 8).hex())
