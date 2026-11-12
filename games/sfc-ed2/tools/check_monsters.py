"""몬스터 이름 군 구조 검사 — 빌드 롬의 군 99개를 엔진(`$C1:6570`)처럼 걷는다: 슬롯 k(0~3)의 이름 = 앞 k 개 문자열을 `len+1` 씩 건너뛴 자리의 길이 접두 문자열.
원판은 4마리 미만 군에 길이 0 칸을 채워 두어 빈 슬롯이 빈 이름으로 끝난다. 이 칸이 없으면 빈 슬롯에 **다음 군의 이름**이 복사돼
이벤트 전투(군82, 신디 단독)가 멈췄다(10-24 — 달라 보이는 증상은 빌드가 「번역 문자열만」 다시 쓰고 뒤 패딩을 빠뜨린 것).

    python3 games/sfc-ed2/tools/check_monsters.py [--rom 빌드롬]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import monsters
import script


def slot_lens(d: bytes, w: int) -> list[int]:
    """엔진 걷기 — 슬롯 0~3 의 이름 길이(0 = 빈 이름)."""
    base = common.snes2off(0xCB0000 | w)
    out = []
    for k in range(4):
        y = 0
        for _ in range(k):
            y += d[base + y] + 1
        out.append(d[base + y])
    return out


def main() -> int:
    common.verify_originals()
    args = sys.argv[1:]
    rom = Path(args[args.index("--rom") + 1]).read_bytes() if "--rom" in args else None
    if rom is None:
        import glob

        rom = Path(glob.glob(str(common.BUILD_DIR / "sfc-ed2" / "*.sfc"))[0]).read_bytes()
    src = common.rom_bytes()
    t = common.snes2off(monsters.TABLE)
    bad = []
    for gi, (_w, ss) in enumerate(monsters.groups(src)):
        w = rom[t + 2 * gi] | rom[t + 2 * gi + 1] << 8
        ls = slot_lens(rom, w)
        want = [len(ss) > k for k in range(4)]
        got = [x > 0 for x in ls]
        if want != got:
            bad.append((gi, len(ss), ls))
    print(f"몬스터 이름 군 구조: 군 {len(monsters.groups(src))}개 · 어긋남 {len(bad)}")
    for gi, n, ls in bad[:10]:
        print(f"    ✗ 군{gi}: 원판 이름 {n}개인데 빌드 슬롯 길이 {ls}")
    # 이름 번역 — 원판 바이트 그대로 남은 이름은 화면 일본어다. 이름 뒤에 제어 토큰 꼬리(`0C 80 …`)가 붙은 원문은 일본어 런 검사(가나 12자)·이름 검사가 못 봤다
    # (10-24: 군33 넷째 「ガードD」 + `0C 80 7E 80` 이 번역 없이 남았다) — 그래서 롬의 이름 바이트를 원판과 직접 맞대고, 꼬리는 그대로 보존됐는지 본다.
    kr_groups = monsters.groups(rom)
    n_names = n_tail = 0
    untr, lost = [], []
    for gi, ((_w, ss), (_w2, ks)) in enumerate(zip(monsters.groups(src), kr_groups)):
        for si, sb in enumerate(ss):
            n_names += 1
            cut = next((o for o, _ln in script.tokens(sb, 0, len(sb)) if sb[o] == 0x0C), None)
            tail = bytes(sb[cut:]) if cut is not None else b""
            n_tail += bool(tail)
            kb = ks[si] if si < len(ks) else b""
            if kb == sb:
                untr.append((gi, si))
            elif tail and not kb.endswith(tail):
                lost.append((gi, si))
    print(f"몬스터 이름 번역: 이름 {n_names}개 · 제어 토큰 꼬리 붙은 원문 {n_tail}개 · 원판 그대로 남은 이름 {len(untr)} · 꼬리 잃은 이름 {len(lost)}")
    for gi, si in untr[:10]:
        print(f"    ✗ 군{gi} 슬롯{si}: 이름이 원판 바이트 그대로(번역 안 됨)")
    for gi, si in lost[:10]:
        print(f"    ✗ 군{gi} 슬롯{si}: 제어 토큰 꼬리가 사라졌다")
    return 1 if bad or untr or lost else 0


if __name__ == "__main__":
    sys.exit(main())
