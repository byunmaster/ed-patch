#!/usr/bin/env python3
"""조사 훅이 붙을 자리를 **추정하지 않고 도출**해 정본 표와 대조한다.

동적 조사 훅은 세 지점에 붙는다(`patch_josa_hook`). ED1 은 인게임으로 확정한 주소를
상수로 박아 뒀는데, **ED2 도 같은 엔진이라 같은 코드가 다른 자리에 옮겨져 있다.** 옮겨진
자리를 손으로 찾아 박으면 다음 사람이 그 값을 검증할 길이 없다 — 여기서 매번 다시 찾는다.

**도출 방법.** ED1 훅 지점의 명령어 열을 **주소를 마스크해** 시그니처로 삼고 ED2.EXE 를
훑는다. `j`/`jal` 의 타깃과 `lui`/`addiu` 의 즉시값은 재배치로 달라지므로 지우고, opcode
와 레지스터만 본다. 실측(2026-08-15): 세 지점 모두 **후보가 정확히 하나**다.

| 지점      | ED1          | ED2          | 뜻                          |
| --------- | ------------ | ------------ | --------------------------- |
| `HOOK`    | `0x800B2054` | `0x80089A8C` | 워크슬롯 조립 직후          |
| `PREWRAP` | `0x800B1D60` | `0x80089798` | 자동 개행 삽입 전 평문      |
| `DRAWSTR` | `0x800A9A60` | `0x800805BC` | 단문 직접 그리기 진입       |
| 워크버퍼  | `0x801190B0` | `0x800F1718` | 줄 stride 66 — **양쪽 같다** |

워크버퍼는 훅 근처에서 `lui+addiu` 가 만드는 상수의 **최빈값**으로 잡는다. stride 는
`base+0x42`(=66) 가 같이 나오는 것으로 확인한다 — 두 게임 다 그렇다.

⚠ **이 값이 맞아도 인게임 확인은 따로다.** 여기서 보는 건 「같은 함수인가」까지고,
「그 자리에서 훅이 안전한가」는 실행해 봐야 안다(ED1 은 구판 훅이 크래시한 이력이 있다).

  python3 tools/check_josa_sites.py        # 도출 → 정본 대조
"""

import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import extract

EXE = {"ED1": (257, 1021952), "ED2": (756, 872448)}
T_ADDR = 0x80010000  # 두 EXE 다 같다(헤더 실측) — 파일 오프셋 = RAM − T_ADDR + 0x800

# ED1 정본(인게임 확정) — `patch_josa_hook` 의 상수와 같아야 한다.
ED1_SITES = {"HOOK": 0x800B2054, "PREWRAP": 0x800B1D60, "DRAWSTR": 0x800A9A60}
ED1_WORK = 0x801190B0
# ED2 도출 결과(이 도구가 매번 재확인한다).
ED2_SITES = {"HOOK": 0x80089A8C, "PREWRAP": 0x80089798, "DRAWSTR": 0x800805BC}
ED2_WORK = 0x800F1718
LINE_STRIDE = 66

# 즉시값·분기 타깃을 지울 opcode — 재배치로 달라지는 자리다.
_IMM_OPS = {15, 9, 13, 8, 35, 43, 4, 5, 1}  # lui addiu ori lw sw beq bne regimm
_JUMP_OPS = {2, 3}  # j jal


def _fo(ram):
    return ram - T_ADDR + 0x800


def _mask(w):
    op = w >> 26
    if op in _JUMP_OPS:
        return op << 26
    if op in _IMM_OPS:
        return (w >> 16) << 16
    return w


def _words(buf, off, n):
    return [struct.unpack_from("<I", buf, off + 4 * i)[0] for i in range(n)]


def find_site(src, dst, ram, window=(8, 10, 12, 14, 18, 24)):
    """`src` 의 `ram` 시그니처를 `dst` 에서 찾는다 → (후보 목록, 쓴 창 크기).

    ⚠ **창 크기를 고정하면 안 된다.** 짧으면 후보가 여럿이고, 길면 재배치로 달라진 명령이
    끼어 0이 된다(실측: `HOOK` 은 8워드에서 유일한데 12워드에선 0, `DRAWSTR` 은 12에서 셋,
    14에서 유일). **후보가 하나가 될 때까지 넓히고, 0이 되면 직전 결과를 쓴다.**
    """
    best = ([], window[0])
    for n in window:
        sig = [_mask(w) for w in _words(src, _fo(ram), n)]
        hits = []
        for i in range(0, len(dst) - 4 * n, 4):
            if all(_mask(struct.unpack_from("<I", dst, i + 4 * k)[0]) == sig[k] for k in range(n)):
                hits.append(T_ADDR + i - 0x800)
                if len(hits) > 8:
                    break
        if not hits:
            break  # 더 넓히면 계속 0이다 — 직전 결과가 최선
        best = (hits, n)
        if len(hits) == 1:
            break
    return best


def find_work(buf, ram, span=0x400):
    """훅 근처 `lui+addiu` 가 만드는 상수의 최빈값 = 워크버퍼 베이스.

    반환 `(base, 최빈 횟수, stride 확인)`. stride 는 `base + 66` 이 같은 근처에서 따로
    만들어지는지로 본다 — 줄 슬롯을 가리키는 코드가 그 상수를 쓴다(두 게임 다 나온다).
    """
    c = collections.Counter()
    lo = max(0, _fo(ram) - span)
    for i in range(lo, min(len(buf) - 40, _fo(ram) + span), 4):
        w = struct.unpack_from("<I", buf, i)[0]
        if (w >> 26) != 0x0F:  # lui
            continue
        rt = (w >> 16) & 0x1F
        for j in range(i + 4, i + 40, 4):
            v = struct.unpack_from("<I", buf, j)[0]
            if (v >> 26) == 9 and ((v >> 21) & 0x1F) == rt:  # addiu, 같은 레지스터
                c[((w & 0xFFFF) << 16) + struct.unpack_from("<h", buf, j)[0]] += 1
                break
    if not c:
        return None, 0, False
    base, hits = c.most_common(1)[0]
    return base, hits, (base + LINE_STRIDE) in c


def main():
    src = bytes(extract(*EXE["ED1"]))
    dst = bytes(extract(*EXE["ED2"]))
    bad = 0

    for name, ed1 in ED1_SITES.items():
        hits, n = find_site(src, dst, ed1)
        want = ED2_SITES[name]
        ok = hits == [want]
        bad += not ok
        got = ", ".join(f"{h:#x}" for h in hits) or "없음"
        print(
            f"  {name:<8} ED1 {ed1:#x} → ED2 후보 [{got}] (창 {n}워드)  "
            f"정본 {want:#x} {'✅' if ok else '❌'}"
        )

    for game, buf, site, want in (
        ("ED1", src, ED1_SITES["HOOK"], ED1_WORK),
        ("ED2", dst, ED2_SITES["HOOK"], ED2_WORK),
    ):
        base, hits, stride_ok = find_work(buf, site)
        ok = base == want and stride_ok
        bad += not ok
        print(
            f"  워크버퍼 {game} → {base:#x} (참조 {hits}회 · stride {LINE_STRIDE} "
            f"{'확인' if stride_ok else '못 봄'}) 정본 {want:#x} {'✅' if ok else '❌'}"
        )

    print(
        "\n  ✅ 조사 훅 자리 도출 = 정본"
        if not bad
        else f"\n  ❌ {bad}건 어긋남 — 원본이 다르거나 표를 고쳐야 한다"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
