"""헤드리스 PC엔진 CD 실행기(libretro beetle-pce) — emucap 호출 없이 프레임 단위로 돌려 RAM 을 읽고 쓰고 화면을 찍는다 (마스터 10-18 「전 씬·전 몬스터 일괄 검수」 준비).

`games/pce-ed1/tools/headless_pce.py`(pce-ed1 이 먼저 세움)와 같은 코어·같은 입력 규약을 **라이브러리 꼴**로 다시 썼다 — 스크립트 파일이 아니라 파이썬에서 부른다.
  코어 = `.local/cache/libretro/mednafen_pce_libretro.so`(메인 트리 — 바이너리 커밋 금지, `CORE` 환경변수로 덮음) · 시스템 디렉터리 = 같은 곳 `system/`(syscard3.pce)
  ⚠ 공용 firmware 를 건드리지 않는다. 구형 카드 시험은 `PCEHL_SYSTEM` 으로 따로 만든 디렉터리를 준다.
  ⚠ 코어에 BP 가 없다 — 「언제 바뀌나」는 프레임마다 RAM 을 떠서 비교한다(`Emu.diff_run`).
  ⚠ 부팅 타이밍이 emucap(mednafen)과 다르다 — 입력은 화면 확인으로 맞춘다.
사용 예:
    emu = Emu("games/pce-ed2/work/build/pce-ed2/ed2.cue", bram="/root/save/pce-ed2/ed2.sav")
    emu.run(3000); emu.press("run", 10, 60); emu.press("i", 1200, 200)   # 서장 필드까지(I 를 누른 채 시작)
    emu.shot("/tmp/x.png")
"""

import ctypes as C
import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

# beetle-pce 패드: PCE I = RetroPad B(0)? — 아래 값은 pce-ed1 하네스에서 검증된 것(I=8, II=0)
BTN = {"i": 8, "ii": 0, "select": 2, "run": 3, "up": 4, "down": 5, "left": 6, "right": 7}

ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUD = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
AUS = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
POLL = C.CFUNCTYPE(None)
INP = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
LOG = C.CFUNCTYPE(None, C.c_int, C.c_char_p)


class _Var(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class _GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]


class _LogCB(C.Structure):
    _fields_ = [("log", LOG)]


def _cache_dir() -> Path:
    common = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], text=True, cwd=Path(__file__).parent).strip()
    return Path(os.path.abspath(common)).parent / ".local" / "cache" / "libretro"


class Emu:
    """한 번에 하나만 만든다(코어가 프로세스 전역 상태를 쥔다)."""

    def __init__(self, cue: str, bram: str | None = None):
        here = _cache_dir()
        self.sys_dir = os.environ.get("PCEHL_SYSTEM", str(here / "system"))
        self.save_dir = str(here / "save")
        self.core = C.CDLL(os.environ.get("CORE", str(here / "mednafen_pce_libretro.so")))
        self.fmt = 0
        self.frame_img = None
        self.held: set[int] = set()
        self.frames = 0
        self._keep = []
        self._logs = _LogCB(LOG(lambda lv, m: None))
        c = self.core
        self._cbs = [ENV(self._env), VID(self._vid), AUD(lambda d, n: n), AUS(lambda a, b: None), POLL(lambda: None), INP(self._inp)]
        c.retro_set_environment(self._cbs[0])
        c.retro_set_video_refresh(self._cbs[1])
        c.retro_set_audio_sample(self._cbs[3])
        c.retro_set_audio_sample_batch(self._cbs[2])
        c.retro_set_input_poll(self._cbs[4])
        c.retro_set_input_state(self._cbs[5])
        c.retro_init()
        assert c.retro_load_game(C.byref(_GameInfo(os.fspath(cue).encode(), None, 0, None))), "retro_load_game 실패"
        c.retro_get_memory_data.restype = C.c_void_p
        c.retro_get_memory_size.restype = C.c_size_t
        c.retro_serialize_size.restype = C.c_size_t
        c.retro_set_controller_port_device(0, 1)
        c.retro_run()
        if bram:
            d = Path(bram).read_bytes()
            C.memmove(c.retro_get_memory_data(0), d, min(len(d), c.retro_get_memory_size(0)))

    # ── 코어 콜백
    def _env(self, cmd, data):
        cmd &= 0xFFFF
        if cmd == 27:
            C.cast(data, C.POINTER(_LogCB))[0] = self._logs
            return True
        if cmd in (9, 31):
            p = C.c_char_p((self.sys_dir if cmd == 9 else self.save_dir).encode())
            self._keep.append(p)
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(p, C.c_void_p)
            return True
        if cmd == 10:
            self.fmt = C.cast(data, C.POINTER(C.c_uint))[0]
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

    def _vid(self, data, w, h, pitch):
        if not data:
            return
        buf = C.string_at(data, pitch * h)
        if self.fmt == 2:
            a = np.frombuffer(buf, dtype="<u2").reshape(h, pitch // 2)[:, :w].astype(np.uint32)
            self.frame_img = np.dstack([((a >> 11) & 31) * 255 // 31, ((a >> 5) & 63) * 255 // 63, (a & 31) * 255 // 31]).astype(np.uint8)
        else:
            a = np.frombuffer(buf, dtype=np.uint8).reshape(h, pitch)[:, : w * 4].reshape(h, w, 4)
            self.frame_img = a[:, :, [2, 1, 0]].copy()

    def _inp(self, port, dev, idx, id_):
        return 1 if (port == 0 and dev == 1 and id_ in self.held) else 0

    # ── 조작
    def run(self, n: int = 1) -> None:
        for _ in range(n):
            self.core.retro_run()
            self.frames += 1

    def press(self, buttons: str, frames: int, after: int = 20) -> None:
        self.held = {BTN[b] for b in buttons.split("+")}
        self.run(frames)
        self.held = set()
        self.run(after)

    def hold(self, buttons: str | None) -> None:
        """누른 채로 둔다(`run` 이 따로 부를 때까지) — None 이면 뗀다."""
        self.held = {BTN[b] for b in buttons.split("+")} if buttons else set()

    def _ram_ptr(self) -> int:
        return self.core.retro_get_memory_data(2)

    def peek(self, addr: int, n: int = 1) -> bytes:
        """CPU 주소 `$2000~$3FFF`(작업 RAM) 읽기."""
        return C.string_at(self._ram_ptr() + ((addr - 0x2000) & 0x1FFF), n)

    def poke(self, addr: int, data: bytes) -> None:
        C.memmove(self._ram_ptr() + ((addr - 0x2000) & 0x1FFF), data, len(data))

    def ram(self) -> bytes:
        return C.string_at(self._ram_ptr(), 0x2000)

    def shot(self, path: str) -> None:
        Image.fromarray(self.frame_img).save(path)

    def save(self, path: str) -> None:
        n = self.core.retro_serialize_size()
        b = C.create_string_buffer(n)
        self.core.retro_serialize(b, n)
        Path(path).write_bytes(b.raw)

    def load(self, path: str) -> None:
        d = Path(path).read_bytes()
        self.core.retro_unserialize(d, len(d))

    def diff_run(self, n: int, lo: int = 0x2000, hi: int = 0x4000) -> list[bytes]:
        """프레임마다 RAM `[lo, hi)` 를 떠서 목록으로 돌려준다 — BP 가 없는 코어에서 「언제 어느 바이트가 바뀌나」를 보는 방법."""
        out = []
        for _ in range(n):
            self.run(1)
            out.append(C.string_at(self._ram_ptr() + (lo - 0x2000), hi - lo))
        return out

    def frame_hash(self) -> str:
        import hashlib

        return hashlib.sha1(self.frame_img.tobytes()).hexdigest()[:12]
