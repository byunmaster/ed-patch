"""본 프로그램(rel 130, 뱅크 0x68~0x71)의 **바이트 장부** — 쓰기 · 자유 공간 · 겹침 검사를 한 곳에서.

모든 프로그램 패치(후킹 루틴 · 글리프 풀 · 시스템 문구 · 참조 고치기)가 여기 한 번씩 적고, 마지막에 `spans()` 로 디스크에 쓸
(선형 바이트, 새 바이트, 기대 원본, 라벨) 목록을 낸다. 겹치는 쓰기는 **그 자리에서 죽는다**(뒤 단계가 앞 단계를 덮는 사고).
자유 공간 = 원본의 0xFF 패딩(`PADDING` — 디스크 · 런타임 모두 불변) + 문구를 옮기며 비운 칸(마지막에 0xFF 로 채운다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

PROG_REL = 130
BANK0 = 0x68
BANK = 8192
OVERLAY_BANK0 = 0x72  # 이 뱅크부터는 씬 패키지가 런타임에 덮어쓴다 — 빈 칸은 문자열 전용(글리프 풀 · 코드 금지)
NBANKS = 12  # 뱅크 0x68~0x73 (0x72·0x73 = 세이브 선택 화면 등 — 글 문자열만 훑는다)

# 원본의 0xFF 패딩(뱅크, 오프셋, 길이) — `tools/freespace` 스캔(2026-10-12)과 런타임(첫 마을) 대조로 확인했다.
PADDING = [
    (0x6B, 0x10C4, 3900),
    (0x71, 0x13FB, 3077),
    (0x6A, 0x15B0, 2640),
    (0x6C, 0x1966, 1690),
    (0x69, 0x1DB4, 588),
    (0x6D, 0x1DC5, 571),
    (0x70, 0x1E1A, 486),
    (0x6F, 0x1F3A, 198),
    (0x6E, 0x1F3C, 196),
    (0x73, 0x0A75, 5515),  # 데이터 선택 화면 오버레이(뱅크 0x73)의 꼬리 — 화면 문자열이 한국어로 길어질 때 같은 뱅크 안으로 옮긴다. 첫 마을에서는 씬 패키지가 이 뱅크를 덮어쓰므로 런타임 불변 대조는 못 한다(화면이 지난 뒤)
]


# 원본의 0x00 칸(뱅크 0x68 은 `$4000` 에 늘 걸려 있어 어디서나 부를 수 있다) — 런타임 첫 마을에서도 0 으로 불변(257/257)이지만 **전투에서는 앞 16B(`+0x1463`~`+0x1472`)를 게임이 쓴다**
# (10-20 실측 — 풀 글리프 첫 자 「흔」이 전투 로그에서만 깨졌다. 전투 1500프레임 뒤 풀 전 구간 대조: 이 16B 만 바뀜). 그래서 앞 16B 는 풀에서 뺀다.
ZERO_PADDING = [(0x68, 0x1473, 241)]


def linear(bank: int, off: int) -> int:
    return PROG_REL * 2048 + (bank - BANK0) * BANK + off


class Prog:
    def __init__(self, orig: bytes | None = None):
        """`orig` = 본 프로그램 원본 80KB(테스트가 가짜를 넣는다). 없으면 원본 디스크에서 읽는다."""
        self.orig = (
            bytes(orig)
            if orig is not None
            else bytes(common.track_data(PROG_REL, NBANKS * BANK // 2048))
        )
        self.writes: dict[tuple[int, int], tuple[bytes, str]] = {}
        self.free_runs: dict[int, list[list[int]]] = {}  # 뱅크 → [[시작, 끝)]
        self.zero_runs: list[tuple[int, int, int]] = []  # 0x00 칸 — 쓰기 기대 바이트가 0
        self.vacated: list[tuple[int, int, int]] = []  # 비운 칸 — 마지막에 0xFF 로 채운다
        for bank, off, ln in PADDING:
            assert set(self.o(bank, off, ln)) == {0xFF}, (
                f"패딩이 0xFF 가 아니다 {bank:02X}+{off:04X}"
            )
            self.free_runs.setdefault(bank, []).append([off, off + ln])
        for bank, off, ln in ZERO_PADDING:
            assert set(self.o(bank, off, ln)) == {0}, f"0 칸이 0 이 아니다 {bank:02X}+{off:04X}"
            self.free_runs.setdefault(bank, []).append([off, off + ln])
            self.zero_runs.append((bank, off, ln))

    def o(self, bank: int, off: int, n: int) -> bytes:
        s = (bank - BANK0) * BANK + off
        return self.orig[s : s + n]

    def cur(self, bank: int, off: int, n: int) -> bytes:
        """지금까지의 쓰기를 반영한 바이트."""
        out = bytearray(self.o(bank, off, n))
        for (b, o), (data, _l) in self.writes.items():
            if b != bank:
                continue
            lo, hi = max(o, off), min(o + len(data), off + n)
            if lo < hi:
                out[lo - off : hi - off] = data[lo - o : hi - o]
        return bytes(out)

    def put(self, bank: int, off: int, data: bytes, label: str) -> None:
        for (b, o), (d, lab) in self.writes.items():
            if b == bank and o < off + len(data) and off < o + len(d):
                raise ValueError(
                    f"프로그램 쓰기 겹침: 「{label}」 {bank:02X}+{off:04X} ↔ 「{lab}」 {b:02X}+{o:04X}"
                )
        self.writes[(bank, off)] = (bytes(data), label)

    def vacate(self, bank: int, off: int, n: int) -> None:
        """원래 있던 바이트를 비운다 — 자유 공간으로 돌려주고 마지막에 0xFF 로 채운다."""
        self.vacated.append((bank, off, n))
        self.free(bank, off, n)

    def free(self, bank: int, off: int, n: int) -> None:
        runs = self.free_runs.setdefault(bank, [])
        runs.append([off, off + n])
        runs.sort()
        merged = []
        for r in runs:
            if merged and merged[-1][1] >= r[0]:
                merged[-1][1] = max(merged[-1][1], r[1])
            else:
                merged.append(list(r))
        self.free_runs[bank] = merged

    def alloc(self, bank: int, n: int) -> int:
        """같은 뱅크 안에서 `n` 바이트를 가장 작은 맞는 빈 곳(같으면 앞쪽)에서 떼 온다."""
        cands = sorted(
            (r[1] - r[0], r[0], r) for r in self.free_runs.get(bank, []) if r[1] - r[0] >= n
        )
        if not cands:
            raise ValueError(f"뱅크 {bank:02X} 에 {n}B 자유 공간이 없다")
        _w, off, r = cands[0]
        r[0] += n
        if r[0] >= r[1]:
            self.free_runs[bank].remove(r)
        return off

    def fits(self, bank: int, n: int, plus: tuple[int, int] | None = None) -> bool:
        """`n` 바이트가 들어갈 빈 곳이 있나 — `plus`(옮기며 비울 칸)를 더한 뒤의 사정으로 본다. 장부는 안 바꾼다."""
        runs = [list(r) for r in self.free_runs.get(bank, [])]
        if plus:
            runs.append([plus[0], plus[0] + plus[1]])
        runs.sort()
        merged = []
        for a, b in runs:
            if merged and merged[-1][1] >= a:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        return any(b - a >= n for a, b in merged)

    def pack_failures(self, bank: int, sizes: list[int], plus: list[tuple[int, int]]) -> list[int]:
        """`sizes`(큰 것부터 가장 작은 맞는 빈 곳에) 를 한꺼번에 앉혀 보고 **못 앉는 항목의 번호**를 낸다. `plus` = 옮기며 비울 칸들. 장부는 안 바꾼다."""
        runs = [list(r) for r in self.free_runs.get(bank, [])] + [[o, o + n] for o, n in plus]
        runs.sort()
        merged: list[list[int]] = []
        for a, b in runs:
            if merged and merged[-1][1] >= a:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        free = merged
        fails = []
        for i in sorted(range(len(sizes)), key=lambda i: -sizes[i]):
            cands = sorted(
                (r[1] - r[0], r[0], k) for k, r in enumerate(free) if r[1] - r[0] >= sizes[i]
            )
            if not cands:
                fails.append(i)
                continue
            _w, _o, k = cands[0]
            free[k][0] += sizes[i]
        return fails

    def reserve(self, bank: int, off: int, n: int) -> None:
        """자유 공간에서 [off, off+n) 을 뺀다(후킹 루틴처럼 자리를 정해 쓰는 쪽)."""
        out = []
        for a, b in self.free_runs.get(bank, []):
            if b <= off or a >= off + n:
                out.append([a, b])
                continue
            if a < off:
                out.append([a, off])
            if b > off + n:
                out.append([off + n, b])
        self.free_runs[bank] = out

    def runs_left(self) -> list[tuple[int, int, int]]:
        """글리프 풀이 앉을 수 있는 빈 칸 — 뱅크 0x72~ 는 뺀다(런타임에 씬 패키지가 덮어쓰는 뱅크라 글리프 표를 두면 깨진다. 문자열 전용 칸이다)."""
        return [(b, r[0], r[1] - r[0]) for b, rs in sorted(self.free_runs.items()) if b < OVERLAY_BANK0 for r in rs]

    def spans(self) -> list[tuple[int, bytes, bytes, str]]:
        """디스크에 쓸 (선형 바이트, 새 바이트, 기대 원본, 라벨). 비운 칸 중 다른 쓰기가 안 덮은 곳은 0xFF 로 채운다."""
        w = dict(self.writes)
        for bank, off, n in self.vacated:
            cover = sorted(
                (o, o + len(d))
                for (b, o), (d, _l) in self.writes.items()
                if b == bank and o < off + n and off < o + len(d)
            )
            pos = off
            for lo, hi in cover + [(off + n, off + n)]:
                if lo > pos:
                    w[(bank, pos)] = (b"\xff" * (min(lo, off + n) - pos), "vacated")
                pos = max(pos, hi)
        out = []
        for (bank, off), (data, label) in sorted(w.items()):
            out.append((linear(bank, off), data, self.o(bank, off, len(data)), label))
        return out
