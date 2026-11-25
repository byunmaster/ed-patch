"""디버그 진입키(A → A+C 1초) 실측 하네스 — 필드에서 키 순서·유지 길이별로 `$FF01B2` 가 토글되는지 본다.

    python3 gpgx_debugkey.py --rom <롬> [--slot 0] [--state <상태파일>]

각 시험은 필드 상태를 새로 불러 시작한다. 출력: 시험 이름 · 결과(`$FF01B2` 값) · 기대.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gpgx_battle import boot_to_field
from gpgx_run import Genesis

FLAG = 0x01B2


def flag(g) -> int:
    return g.ram(FLAG, 1)[0]


def seq(g, steps):
    """steps = [(버튼 튜플, 프레임)…] — 버튼은 MD 이름(a b c up…)."""
    for names, n in steps:
        g.hold(*names)
        g.run(n)
    g.release()
    g.run(20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True)
    ap.add_argument("--slot", type=int, default=0)
    ap.add_argument("--save", default="/root/save/md-ed1/md-ed1-slots.sav")
    a = ap.parse_args()
    g = Genesis(a.rom, srm=Path(a.save).read_bytes())
    boot_to_field(g, a.slot)
    state = g.save_state()
    ok = True

    def case(name, steps, want, pre=None):
        nonlocal ok
        g.load_state(state)
        g.run(2)
        if pre is not None:
            g.poke(FLAG, bytes([pre]))
        seq(g, steps)
        got = flag(g)
        good = got == want
        ok &= good
        print(f"{'OK ' if good else 'NG '} {name}: $FF01B2={got:#04x} (기대 {want:#04x})", flush=True)

    A, C, B = ("a",), ("c",), ("b",)
    AC = ("a", "c")
    for k in (30, 44, 52):
        case(f"A 먼저 → C 더해 {k}f", [(A, 10), (AC, k)], 0)
    for k in (64, 70, 90):
        case(f"A 먼저 → C 더해 {k}f", [(A, 10), (AC, k)], 0x62)
    case("한 번 더(끄기) 70f", [(A, 10), (AC, 70)], 0, pre=0x62)
    case("C 먼저 → A 더해 90f", [(C, 10), (AC, 90)], 0)
    case("A·C 같은 프레임 90f", [(AC, 90)], 0)
    case("A+C 40f → B 섞임 → A+C 40f", [(A, 5), (AC, 40), (("a", "b", "c"), 3), (AC, 40)], 0)
    case("A+C 40f → 놓았다 → A+C 40f", [(A, 5), (AC, 40), ((), 3), (A, 5), (AC, 40)], 0)
    case("A+C+위 90f(걸으며 — 세지 않음)", [(A, 5), (("a", "c", "up"), 90)], 0)
    case("A 만 길게 200f", [(A, 200)], 0)
    case("C 만 길게 200f", [(C, 200)], 0)
    print("전부 OK" if ok else "⚠ 어긋남 있음")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
