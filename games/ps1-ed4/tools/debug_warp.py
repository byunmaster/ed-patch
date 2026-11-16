"""디버그 이동 — 시험용(헤드리스 하네스 전용, 제품 롬엔 아무것도 넣지 않는다).

게임 자신의 맵 이동 연산(`14 <방향> 07 <맵이름 7자> <인자 3바이트>`)을 이벤트 VM 에 주입한다 — 맵 이름 리터럴을 덮는 옛 워프와 달리
**게임의 맵 전환 경로를 그대로 타므로** 플레이어·카메라·파티가 이동 연산의 입구 규칙대로 놓인다.
방법: 새 게임 첫 대사가 ○ 를 기다리는 순간의 상태에서 빈 RAM(`BUF`)에 이동 연산 스트림을 올리고, ○ 를 누르며 VM 의 PC 를 그 스트림으로 계속 꽂는다.
   python3 tools/debug_warp.py census            # 원판 이벤트의 이동 연산 목록(맵 이름 → 흔한 방향·인자) — 에뮬 없이
   sh scripts/capture.sh python3 tools/debug_warp.py shoot <cue> <card.mcr> <맵이름[:방향[:인자3 hex]]>… --out <폴더>
캡처에는 「디버그 이동」을 표기한다(출력 폴더 이름·`INDEX.txt`).
"""

import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OP14 = re.compile(rb"\x14([\x00\x01\x02\x03\x08\x88])\x07([A-Z]{2}\d{5})(...)", re.DOTALL)


def census():
    import build

    members = build.identity_gate({})
    cnt = collections.defaultdict(collections.Counter)
    for m in members.values():
        for mt in OP14.finditer(m):
            cnt[mt.group(2).decode()][(mt.group(1)[0], mt.group(3))] += 1
    return {n: c.most_common(1)[0][0] for n, c in sorted(cnt.items())}, cnt


def stream(name, d=0, args=b"\0\0\0"):
    return bytes([0x14, d, 0x07]) + name.encode() + args + b"\0" * 16


def warp(e, name, d=0, args=b"\0\0\0", tries=6, settle=240):
    """첫 대사 대기 상태에서 호출한다. 이동 연산을 먹이고 맵이 서 때까지 돌린다."""
    import dialog_harness as D

    e.poke(D.BUF, stream(name, d, args))
    for _ in range(tries):
        e.poke(D.PC, D.BUF.to_bytes(4, "little"))
        e.press("circle", 6, 30)
        e.run(60)
    e.run(settle)


def main():
    cmd = sys.argv[1]
    if cmd == "census":
        best, cnt = census()
        for n, (d, a) in best.items():
            print(n, d, a.hex(), sum(cnt[n].values()))
        print(len(best), "맵")
    elif cmd == "shoot":
        import dialog_harness as D

        cue, card = sys.argv[2], sys.argv[3]
        out = sys.argv[sys.argv.index("--out") + 1]
        targets = [a for a in sys.argv[4 : sys.argv.index("--out")]]
        if targets == ["all"]:
            targets = list(census()[0])
        os.makedirs(out, exist_ok=True)
        best, _ = census()
        base = os.path.join(out, "base.state")
        D.make_state(cue, card, base)
        e = None
        for t in targets:
            p = t.split(":")
            name = p[0]
            d, a = best.get(name, (0, b"\0\0\0"))
            if len(p) > 1 and p[1]:
                d = int(p[1])
            if len(p) > 2:
                a = bytes.fromhex(p[2])
            if e is None:
                import headless_ps1 as H  # noqa: F401

                e = D.make_state(cue, card, base)
            else:
                e.load(base)
                e.run(1)
            warp(e, name, d, a)
            e.shot(f"{out}/{name}.png")
            print(name, d, a.hex(), flush=True)
        with open(f"{out}/INDEX.txt", "w") as f:
            f.write(
                "디버그 이동 캡처 — 새 게임 첫 대사 상태에서 게임의 맵 이동 연산을 주입해 이동했다(제품 롬 아님).\n"
            )
            f.write("\n".join(targets) + "\n")


if __name__ == "__main__":
    main()
