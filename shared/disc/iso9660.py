"""ISO9660 읽기 — raw 2352 이미지에서 파일 목록·내용을 꺼낸다.

**둘째 소비자가 실재해서 올렸다**(새턴 ED1+2 · 새턴 ED3 — 둘 다 MODE1/2352).
PS1 쪽은 MODE2 Form1 이라 `user_off` 만 다르고 나머지는 같다.

⚠ **읽기 전용이다.** 원본을 여는 자리라 쓰기 경로를 같이 두지 않는다
(`docs/patcher-checklist.md` 2 — 사전조건 없는 쓰기 경로를 미리 만들지 않는다).
"""

import hashlib
import mmap
import os

SECTOR = 2352  # raw 섹터(sync 12 + header 4 + …)
USER_SIZE = 2048

MODE1_USER_OFF = 16  # sync(12) + header(4)                — 새턴
MODE2_FORM1_USER_OFF = 24  # sync(12) + header(4) + subheader(8) — PS1

_MAX_DEPTH = 8


def digests(path):
    """{size, sha1} — 원본 지문 표기·확인에 같이 쓴다."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return {"size": os.path.getsize(path), "sha1": h.hexdigest()}


class Disc:
    """raw 2352 이미지 하나. `with Disc(path, user_off=...) as d:` 로 쓴다.

    ⚠ `user_off` 는 **기본값을 두지 않는다** — 틀리면 PVD 가 안 잡히는 게 아니라
    **엉뚱한 바이트를 조용히 읽는다**(MODE1 이미지를 MODE2 로 읽으면 8바이트씩 밀린다).
    부르는 쪽이 자기 플랫폼을 명시하게 한다.
    """

    def __init__(self, path, *, user_off):
        self.path = path
        self.user_off = user_off
        # SIM115 예외 — 이 객체가 곧 컨텍스트 매니저다(`close`/`__exit__` 가 닫는다)
        self._f = open(path, "rb")  # noqa: SIM115
        self._mm = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
        self._files = None

    # ── 수명 ────────────────────────────────────────────────────────────────
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        if self._mm is not None:
            self._mm.close()
            self._f.close()
            self._mm = self._f = None

    # ── 섹터 ────────────────────────────────────────────────────────────────
    def sector_user(self, lba):
        off = lba * SECTOR + self.user_off
        return self._mm[off : off + USER_SIZE]

    def read_extent(self, lba, size):
        out = bytearray()
        for i in range((size + USER_SIZE - 1) // USER_SIZE):
            out += self.sector_user(lba + i)
        return bytes(out[:size])

    # ── ISO9660 ─────────────────────────────────────────────────────────────
    def pvd(self):
        p = self.sector_user(16)
        if not (p[0] == 1 and p[1:6] == b"CD001"):
            raise ValueError(
                f"PVD 시그니처 불일치 — user_off={self.user_off} 가 이 이미지에 안 맞는다: {self.path}"
            )
        return p

    def files(self):
        """전체 파일 목록 `[(경로, LBA, 크기)]` — LBA 순. 결과는 한 번만 훑는다."""
        if self._files is None:
            root = self.pvd()[156 : 156 + 34]
            out = []
            self._walk(
                int.from_bytes(root[2:6], "little"),
                int.from_bytes(root[10:14], "little"),
                "",
                out,
                0,
            )
            out.sort(key=lambda x: x[1])
            self._files = out
        return self._files

    def _walk(self, lba, size, path, out, depth):
        if depth > _MAX_DEPTH:
            return
        data = self.read_extent(lba, size)
        pos = 0
        while pos < len(data):
            rec_len = data[pos]
            if rec_len == 0:  # 레코드는 섹터 경계를 안 넘는다 → 다음 섹터로
                pos = (pos // USER_SIZE + 1) * USER_SIZE
                continue
            rec = data[pos : pos + rec_len]
            ext_lba = int.from_bytes(rec[2:6], "little")
            ext_size = int.from_bytes(rec[10:14], "little")
            flags = rec[25]
            name = rec[33 : 33 + rec[32]]
            pos += rec_len
            if name in (b"\x00", b"\x01"):  # `.` / `..`
                continue
            full = f"{path}/{name.decode('ascii', 'replace').split(';')[0]}"
            if flags & 0x02:
                self._walk(ext_lba, ext_size, full, out, depth + 1)
            else:
                out.append((full, ext_lba, ext_size))

    def find(self, path_in_iso):
        """`(경로, LBA, 크기)` — 없으면 KeyError."""
        for ent in self.files():
            if ent[0] == path_in_iso:
                return ent
        raise KeyError(path_in_iso)

    def read(self, path_in_iso):
        """ISO 안 경로 하나를 bytes 로. 대량이면 `files()` 로 직접 돈다."""
        _, lba, size = self.find(path_in_iso)
        return self.read_extent(lba, size)
