"""디스크 쓰기 가드 — 무변경 구간과 쓰기 사전조건. **기종 무관**(바이트 영역만 안다).

`docs/patcher-checklist.md` 2 — 사전조건 없는 쓰기 경로를 두지 않는다. 섹터 규격(MODE1/MODE2)은
이 모듈이 모른다: 쓰는 쪽(`mode2.write_user_data` 등)이 **유저 데이터 절대 오프셋**으로 바꿔 부른다.

    guard = Guard()
    guard.add(lba=1000, size=2048 * 4, regions=[("TOC", 0, 64, "same")])   # 파일 안 상대 구간
    guard.check(lo=abs_offset, old=old_bytes, new=new_bytes, label="대본 재삽입")
"""


class WriteGuard(Exception):
    """무변경 구간을 바꾸려 했거나 쓰기 사전조건이 어긋났다 — 쓰기를 취소하고 그 자리에서 실패."""


class Guard:
    USER_SIZE = 2048

    def __init__(self):
        # {(lba, size): [(이름, 시작, 끝, mode)]} — 시작·끝은 그 파일 안 상대 바이트
        self.regions = {}

    def add(self, lba, size, regions):
        self.regions[(lba, size)] = list(regions)

    def _abs(self):
        out = []
        for (lba, _size), regs in self.regions.items():
            base = lba * self.USER_SIZE
            out += [(base + a, base + b, name, mode) for name, a, b, mode in regs]
        return out

    def check(self, lo, old, new, label):
        """`lo`(유저 데이터 절대 오프셋)부터의 `old`→`new` 가 무변경 구간을 건드리면 `WriteGuard`."""
        assert len(old) == len(new), (len(old), len(new))
        for g_lo, g_hi, name, _mode in self._abs():
            a, b = max(lo, g_lo), min(lo + len(old), g_hi)
            if a >= b:
                continue
            for o in range(a - lo, b - lo):
                if old[o] != new[o]:
                    raise WriteGuard(
                        f"무변경 구간 침범 — `{label}` 이 「{name}」 @0x{lo + o:X}"
                        f"(유저데이터 절대) 를 {old[o]:02X}→{new[o]:02X} 로 바꾸려 했다"
                    )


def check_expect(cur, expect, label, where):
    """쓰기 **사전조건** — `expect` 가 bytes 면 `cur` 의 앞부분이 정확히 그것, int 면 `cur` 전체가 그 값.

    어긋나면 `WriteGuard`. `where` 는 사고 때 위치를 알리는 문자열(예 `lba 100`).
    """
    if isinstance(expect, bytes):
        n = len(expect)
        want = expect
    else:
        n = len(cur)
        want = bytes([expect]) * n
    got = bytes(cur[:n])
    if got != want:
        o = next(i for i, (x, y) in enumerate(zip(got, want, strict=False)) if x != y)
        raise WriteGuard(
            f"쓰기 사전조건 불일치 — `{label}` @{where}+0x{o:X}: {got[o]:02X} (기대 {want[o]:02X})"
        )
