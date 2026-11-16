"""이벤트 VM 연산 시험 주입(시험 전용, 제품 롬 불변 — 캡처 「디버그 이동」): 첫 대사 대기 상태에서 연산 하나(+인자)를 먹여 화면을 찍는다.

   sh scripts/capture.sh python3 tools/op_probe.py <cue> <card.mcr> <맵|-> <출력폴더> <연산hex,..> [인자hex]

맵 이동 뒤에는 VM 이 놀아 연산이 안 먹으므로 맵은 보통 「-」(첫 대사 대기 상태 그대로).
환경 변수(전부 시험용):
  POKE_ADDR + POKE_VALUES   주소(hex)에 값(hex 바이트) 하나씩 쓰며 값마다 한 번씩 돈다(예: 의뢰 번호)
  POKE_RAW                  `주소=hex바이트;…` 연산 전에 RAM 쓰기(코드 즉치 시험 포함)
  POKE_STR                  `색인=hex글리프코드열;…` 의뢰 문자열 표(굽힌 코드의 표 주소를 RAM 에서 읽는다)의 색인 번째 문자열을 바꾼다
  EXTRA                     마지막에 이만큼 프레임을 더 돌려 한 장(`…_final.png`)
  WINTRACE=<경로접두>   창 열기·글 그리기 덫(`wintrace.py`) — 연산 뒤 로그를 `<접두>.<연산>.json` 으로 · KEYS=콤마 목록 연산 뒤 추가 입력
  TRACE_FN / SCAN_RAM       함수 진입 인자 기록 덫 · RAM 문자열 검색(점검용)
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import debug_warp as W
import dialog_harness as D


def poke_strings(e, spec):
    """`색인=hex;…` — 의뢰 문자열 표 기준(굽힌 `0x8003FA1C` 의 `lui`/`addiu` 에서 표 주소를 읽는다)."""
    lui = struct.unpack("<I", e.peek(0x8003FABC, 4))[0] & 0xFFFF
    add = struct.unpack("<h", e.peek(0x8003FAC0, 4)[:2])[0]
    base = (lui << 16) + add
    for item in [x for x in spec.split(";") if x]:
        idx, hx = item.split("=")
        ptr = struct.unpack("<H", e.peek(base + 2 * int(idx), 2))[0]
        e.poke(base + ptr, bytes.fromhex(hx))
        print("POKE_STR", idx, hex(base), hex(ptr), e.peek(base + ptr, 8).hex(), flush=True)


def trace_install(e):
    sys.path.insert(0, "/tmp/claude-0")
    import trace_put as TP

    fn = int(os.environ["TRACE_FN"], 16)
    o1, o2 = struct.unpack("<2I", e.peek(fn, 8))
    stub, entry = TP.build(fn, o1, o2)
    e.poke(TP.LOG, bytes(0x2000))
    e.poke(TP.STUB, stub)
    e.poke(fn, entry)


def trace_report(e):
    import trace_put as TP

    n = struct.unpack("<I", e.peek(TP.LOG, 4))[0]
    print("TRACE 호출", n, flush=True)
    for k in range(1, min(n, 40) + 1):
        r = struct.unpack("<6I", e.peek(TP.LOG + 32 * k, 24))
        print("TRACE", k, " ".join(f"{x:08x}" for x in r), flush=True)


def scan_ram(e):
    ram = e.peek(0x80000000, 0x200000)
    for pat in (b"Rose", b"R\0o\0s\0e\0"):
        p = -1
        while True:
            p = ram.find(pat, p + 1)
            if p < 0:
                break
            print("SCAN", pat, hex(0x80000000 + p), ram[p - 8 : p + 24].hex(), flush=True)


def main():
    cue, card, name, out, ops = sys.argv[1:6]
    args = bytes.fromhex(sys.argv[6]) if len(sys.argv) > 6 else b""
    os.makedirs(out, exist_ok=True)
    e = D.make_state(cue, card, out + "/base.state")
    if name != "-":
        W.warp(e, name, 0, b"\0\0\0", settle=200)
    here = out + "/warped.state"
    e.save(here)
    pokes = [p for p in os.environ.get("POKE_VALUES", "").split(",") if p]
    for op in ops.split(","):
        for pv in pokes or [""]:
            tag = f"{op}_v{pv}" if pv else op
            e.load(here)
            e.run(1)
            if pv:
                e.poke(int(os.environ["POKE_ADDR"], 16), bytes([int(pv, 16)]))
            for item in [x for x in os.environ.get("POKE_RAW", "").split(";") if x]:
                a_, h_ = item.split("=")
                e.poke(int(a_, 16), bytes.fromhex(h_))
            if os.environ.get("POKE_STR"):
                poke_strings(e, os.environ["POKE_STR"])
            if os.environ.get("TRACE_FN"):
                trace_install(e)
            if os.environ.get("WINTRACE"):
                import wintrace

                wintrace.install(e)
            e.poke(D.BUF, bytes([int(op, 16)]) + args + b"\0" * 32)
            for k in range(4):
                e.poke(D.PC, D.BUF.to_bytes(4, "little"))
                e.press("circle", 6, 30)
                e.run(60)
                e.shot(f"{out}/op{tag}_{k}.png")
            for k in range(3):
                e.press("circle", 6, 40)
                e.shot(f"{out}/op{tag}_c{k}.png")
            for kname in [k for k in os.environ.get("KEYS", "").split(",") if k]:  # 연산 뒤 추가 입력(시험용)
                e.press(kname, 6, 30)
                e.run(40)
                e.shot(f"{out}/op{tag}_k{kname}.png")
            if os.environ.get("WINTRACE"):
                import json

                import wintrace

                evs = wintrace.drain(e)
                json.dump(evs, open(os.environ["WINTRACE"] + f".{tag}.json", "w"))
                print("WINTRACE", tag, len(evs), flush=True)
            if os.environ.get("EXTRA"):
                e.run(int(os.environ["EXTRA"]))
                e.shot(f"{out}/op{tag}_final.png")
            if os.environ.get("TRACE_FN"):
                trace_report(e)
            if os.environ.get("SCAN_RAM"):
                scan_ram(e)
            import ui_tour

            print(tag, ui_tour.wins(e), flush=True)


if __name__ == "__main__":
    main()
