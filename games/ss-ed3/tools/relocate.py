"""음성 자막이 든 맵을 **트랙 1 끝**으로 옮긴다 — 꼬리 여백 대신 자리를 새로 판다.

    python3 games/ss-ed3/tools/relocate.py            # 두 디스크의 트랙 1 끝 지형(실측 대조)

🔴 **왜 옮기나** — 자막 칸·글자 표는 맵 파일 뒤에 붙는데(`voice_sub.py`) 맵 파일의 마지막
   섹터 여백은 맵마다 다르다. 실측(2026-09-05): 음성 장면 19 중 **13 이 안 든다**
   (MAP046 은 16B, MAP005 48B, MAP006 72B). 여백 안에서 짜내는 길은 없다.
   디스크는 빈 데가 없다(트랙 1 은 파일이 빈틈없이 붙어 있다) — 그래서 **트랙 1 자체를
   늘린다.** 원본 트랙 1 끝의 포스트갭(유저 데이터 0 인 MODE1 섹터 — 디스크 1 은 150,
   디스크 2 는 75)을 뒤로 밀고 그 앞에 옮긴 맵을 놓는다. 엔진은 디렉터리 레코드로 파일을
   찾으므로(크기를 늘렸을 때 그만큼 읽는 걸 V01 로 확인했다) 레코드의 LBA·크기만 옮긴다.
   옛 자리의 바이트는 그대로 둔다 — 아무도 안 읽는 죽은 데이터가 되고, 무변경 대조가 그
   구간을 원본과 같다고 본다.

⚠ **디스크 2 는 ISO 가 트랙 2 로 넘어간다**(`END00~16.GRP` · `V20.SAP`). 트랙 1 이
   N 섹터 늘면 트랙 2 의 모든 섹터가 N 만큼 뒤로 가므로 셋을 같이 고친다:
     · 그 파일들의 디렉터리 레코드 LBA  += N
     · PVD 볼륨 크기                      += N
     · 트랙 2 사본의 **섹터 헤더(MSF)**   += N — 실기 CD 컨트롤러는 헤더 주소를 대조한다.
       프리갭 앞머리는 MODE1 이라 ECC 가 헤더를 덮는다(`sector_fix`) · MODE2 는 헤더가
       ECC 밖이라 4 바이트만 갈면 된다.
   🔴 트랙 2 파일을 엔진이 **레코드가 아니라 박힌 LBA 로** 읽는다면 엔딩이 깨진다 — 아직
      엔딩까지 못 가 봐서 **미검증**이다(QA 회차의 몫, `docs/status.md`).

ⓘ 옮기는 건 **음성 자막이 든 맵 전부**다(여백에 드는 것도). 「드는 맵은 제자리, 안 드는
   맵은 이동」으로 가르면 문안이 한 줄 늘 때 기전이 바뀌어 검증이 새로 필요해진다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

import common as C

from shared.disc import mode1
from shared.disc.iso9660 import SECTOR, USER_SIZE

# 원본 트랙 1 지형 — 실측 2026-09-05 (`main()` 이 매번 다시 재서 대조한다)
DATA_END = {1: 141961, 2: 200730}  # 마지막 파일 끝 = 포스트갭 시작
TRACK1 = {1: 142111, 2: 200805}  # 트랙 1 섹터 수
PAD = {d: TRACK1[d] - DATA_END[d] for d in TRACK1}  # 포스트갭 (150 · 75)

SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def _bcd(v):
    return ((v // 10) << 4) | (v % 10)


def header(lba, mode=1):
    """섹터 헤더 4B — 절대 MSF(BCD) + 모드. LBA 0 = 00:02:00."""
    a = lba + 150
    return bytes([_bcd(a // 4500), _bcd(a // 75 % 60), _bcd(a % 75), mode])


def blank_sector(lba):
    """유저 데이터 0 인 MODE1 섹터 — 포스트갭·새 자리의 바탕."""
    sec = bytearray(SYNC + header(lba) + b"\x00" * (SECTOR - 16))
    mode1.sector_fix(sec)
    return bytes(sec)


class Layout:
    """옮길 파일에 차례로 새 LBA 를 준다 — 부르는 순서가 같으면 결과가 같다(결정성)."""

    def __init__(self, disc):
        self.disc = disc
        self.next = DATA_END[disc]
        self.moved = []  # (이름, 옛 lba, 새 lba, 섹터 수)

    def alloc(self, name, old_lba, size):
        n = -(-size // USER_SIZE)
        lba = self.next
        self.next += n
        self.moved.append((name, old_lba, lba, n))
        return lba

    @property
    def grown(self):
        """트랙 1 이 는 섹터 수 N."""
        return self.next - DATA_END[self.disc]

    def span_bytes(self):
        """새로 쓰이는 구간 `(lba, 바이트)` — 옮긴 파일 + 밀린 포스트갭. `touched` 규약."""
        return DATA_END[self.disc], (self.grown + PAD[self.disc]) * USER_SIZE


def grow(f, disc, n):
    """열린 `r+b` 트랙 1 이미지를 N 섹터 늘린다 — 옛 포스트갭 자리부터 빈 섹터 N + 포스트갭.

    ⚠ 원본 포스트갭이 정말 0 인지 먼저 본다 — 아니면 지우면 안 되는 것이다.
    """
    start = DATA_END[disc]
    f.seek(0, 2)
    assert f.tell() == TRACK1[disc] * SECTOR, (f.tell(), TRACK1[disc])
    for i in range(PAD[disc]):
        f.seek((start + i) * SECTOR)
        sec = f.read(SECTOR)
        assert sec == blank_sector(start + i), f"포스트갭 {start + i} 이 빈 섹터가 아니다"
    f.seek(start * SECTOR)
    f.truncate()
    for i in range(n + PAD[disc]):
        f.write(blank_sector(start + i))


def shift_track(src, dst, n):
    """트랙 2 이후의 사본 — 섹터 헤더의 MSF 를 N 만큼 뒤로 민다(N=0 이면 그대로 복사).

    ⚠ 원본 헤더가 자기 자리를 맞게 적고 있다는 걸 섹터마다 확인한다(첫 섹터 헤더 = 트랙 시작
      LBA). 어긋나 있으면 「덤프가 이상하다」이지 우리가 고칠 게 아니다.
    """
    size = os.path.getsize(src)
    assert size % SECTOR == 0, size
    with open(src, "rb") as a, open(dst, "wb") as b:
        first = None
        for i in range(size // SECTOR):
            sec = bytearray(a.read(SECTOR))
            if sec[:12] != SYNC:  # 오디오 트랙 — 헤더가 없다
                b.write(sec)
                continue
            mode = sec[15]
            if first is None:
                first = lba_of(sec[12:15])
            assert sec[12:15] == header(first + i, mode)[:3], (i, sec[12:16].hex())
            sec[12:15] = header(first + i + n, mode)[:3]
            if mode == 1:
                mode1.sector_fix(sec)
            b.write(sec)


def lba_of(h):
    m, s, fr = ((x >> 4) * 10 + (x & 15) for x in h[:3])
    return (m * 60 + s) * 75 + fr - 150


def move_record(sector, off, old_lba, old_size, new_lba, new_size):
    """디렉터리 섹터 안 레코드의 익스텐트 LBA·크기(양끝 엔디언 8B 씩)를 옮긴 새 섹터."""
    rec = sector[off : off + 34]
    want = struct.pack("<I", old_lba) + struct.pack(">I", old_lba)
    assert rec[2:10] == want, rec[2:10].hex()
    want = struct.pack("<I", old_size) + struct.pack(">I", old_size)
    assert rec[10:18] == want, rec[10:18].hex()
    out = bytearray(sector)
    out[off + 2 : off + 10] = struct.pack("<I", new_lba) + struct.pack(">I", new_lba)
    out[off + 10 : off + 18] = struct.pack("<I", new_size) + struct.pack(">I", new_size)
    return bytes(out)


def pvd_grow(sector, n):
    """PVD 의 볼륨 크기(섹터 수, 80~87 양끝 엔디언)를 N 늘린 새 섹터."""
    v = struct.unpack("<I", sector[80:84])[0]
    assert struct.unpack(">I", sector[84:88])[0] == v, sector[80:88].hex()
    out = bytearray(sector)
    out[80:88] = struct.pack("<I", v + n) + struct.pack(">I", v + n)
    return bytes(out)


def track2_files(d, disc):
    """트랙 1 밖에 있는 파일 — 디스크 2 의 엔딩 그림·음성."""
    return [(n, lba, size) for n, lba, size in d.files() if lba >= TRACK1[disc]]


def main():
    for disc in C.DISCS:
        with C.open_disc(disc) as d:
            fs = sorted(d.files(), key=lambda t: t[1])
            t1 = [f for f in fs if f[1] < TRACK1[disc]]
            end = t1[-1][1] + -(-t1[-1][2] // USER_SIZE)
            n = os.path.getsize(C.DISC_BIN[disc]) // SECTOR
            print(
                f"disc{disc}: 트랙1 {n} 섹터 · 마지막 파일 {t1[-1][0]} 끝 {end} · "
                f"포스트갭 {n - end} · 트랙 2 파일 {len(track2_files(d, disc))}"
            )
            assert (end, n) == (DATA_END[disc], TRACK1[disc]), "지형 상수가 원본과 다르다"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
