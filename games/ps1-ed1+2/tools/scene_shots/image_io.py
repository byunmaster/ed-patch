"""MODE2/2352 BIN 에서 논리 섹터를 읽는 최소 리더(빌드 이미지 안 씬 오버레이를 읽는 데만 쓴다)."""

SECTOR = 2352
HEAD = 24  # 동기 12 + 헤더 4 + 서브헤더 8


class Image:
    def __init__(self, bin_path: str):
        self._f = open(bin_path, "rb")  # noqa: SIM115 — 프로세스 수명 동안 연다

    def read(self, lba: int, size: int) -> bytes:
        out = bytearray()
        for i in range((size + 2047) // 2048):
            self._f.seek((lba + i) * SECTOR + HEAD)
            out += self._f.read(2048)
        return bytes(out[:size])
