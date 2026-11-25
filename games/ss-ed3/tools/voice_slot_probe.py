"""음성 자막 스텁이 **지금 롬에서 글자를 그리나** — 합성 자막 칸 하나를 맵 바깥 빈자리에 심고 스크립트 PC 를 거기 둔다(롬·세이브 불변).

    sh scripts/capture.sh python3 games/ss-ed3/tools/voice_slot_probe.py <디스크1.cue> <Disc1 백업RAM.bkr> <출력폴더>

스텁은 창 갱신 훅에서 매 프레임 스크립트 PC 를 보고, PC 가 서명(`SUB!`)이 붙은 32B 칸 안이면 그 칸의 글자 포인터로 창·글자를 그린다. 그래서 장면을 실제로
틀지 않아도 칸 하나(`FF 35 0001` + `FD 00 <자기 자신>` — 제자리 대기)와 글자 하나만 있으면 스텁·훅·글자 그리기가 도는지 화면으로 볼 수 있다.
스텁 위치가 바뀌는 변경(코드 예약 칸 이전 등)의 회귀다 — 옛 롬과 새 롬의 화면이 **화소까지 같아야** 한다. 얼굴은 안 쓴다(`0xFFFF`).
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dialog_sweep as DS
import hangul_map as H
import ss_headless as H0
import subtitle_stub as SS

LWRAM = 0x00200000
PC = 0x0609408C
LINES = ("이건 음성 자막 시험이다.", "두 번째 줄도 나온다.")


def find_zero_run(h, n):
    """현재 LWRAM 의 32B 정렬 0 런(길이 n 이상) 하나 — 맵 파일 끝 쪽에서 찾는다."""
    buf = h.peek(LWRAM + 0x1000, 0xA0000)
    z = b"\x00" * (n + 32)
    i = buf.rfind(z)
    if i < 0:
        raise SystemExit("0 런을 못 찾았다")
    a = LWRAM + 0x1000 + i
    return a + (-a % 32)


def main():
    cue, bkr, out = sys.argv[1:4]
    core = os.path.join(H0.CACHE, "beetle-saturn", "src", "mednafen_saturn_libretro.so")
    h = H0.Harness(core, cue, out, bkr=bkr)
    DS.boot(h)
    h.shot("00_boot")
    table = H.load()
    rec = struct.pack(">HHH", 0, 0xFFFF, 0) + H.encode_kr("시험", table) + b"\x00"
    rec += b"".join(H.encode_kr(t, table) + b"\x00" for t in LINES) + b"\x00"
    rec += b"\x00" * (len(rec) % 2)
    slot_at = find_zero_run(h, 32 + len(rec) + 64)
    txt_at = slot_at + 32
    body = b"\xff\x35\x00\x01" + b"\xfd\x00" + struct.pack(">I", slot_at)
    slot = body.ljust(SS.MAGIC_OFF, b"\x00") + struct.pack(">II", SS.MAGIC, txt_at)
    assert len(slot) == 32 and txt_at % 2 == 0
    h.poke(slot_at, slot)
    h.poke(txt_at, rec)
    h.poke(PC, struct.pack(">I", slot_at))
    print(f"칸 {slot_at:#x} 글자 {txt_at:#x}", flush=True)
    for k in range(6):
        h.run(30)
        h.shot(f"01_after_{(k + 1) * 30:03d}")
    pcv = struct.unpack(">I", h.peek(PC, 4))[0]
    print(f"PC {pcv:#x} (칸 {slot_at:#x})")


if __name__ == "__main__":
    main()
