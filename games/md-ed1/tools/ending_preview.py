"""엔딩을 **오프닝 자리에서** 틀어 보는 시험용 롬 — 인게임 확인 전용(배포 빌드 아님).

    python3 tools/ending_preview.py            # work/emu/ed1_endnarr.bin · ed1_enddlg.bin
    python3 tools/ending_preview.py --check    # 후킹 자리의 원본 바이트만 확인

왜 필요한가 — 엔딩 루틴(`$2C29A`·`$2C350`·`$2DE80`)은 **롬 어디서도 호출되지 않는다**(앞 루틴에서
흘러들어온다). 그래서 최종 전투까지 가지 않으면 엔딩 문안을 화면으로 못 본다. 오프닝은 타이틀에서
「처음부터」만 고르면 바로 도는 자리라, 그 호출을 엔딩으로 바꿔치기하면 **문안·조판·글꼴을 그대로**
볼 수 있다.

후킹 자리(원본 실측):

    013780  lea.l  $16224.l, a3     ← 오프닝 자막 표
    013786  bsr.w  $14e44           ← 워드 스크립트 드라이버(자막 공용)
    02de90  lea.l  $2de9e.l, a3     ← 엔딩 나레이션 표 (같은 드라이버)
    02c34a  lea.l  $2ed38.l, a3     ← 엔딩 대사 표 (드라이버가 다르다: $2eb4c, a2 = 그림 $2fa10)

- **나레이션**: 표 주소 4바이트만 갈아 끼운다(드라이버가 같다).
- **대사**: 드라이버가 달라 호출 세 줄을 통째로 덮어쓴다(오프닝 뒤 코드까지 18B) — 시험용이라
  엔딩이 끝난 뒤 흐름은 보장하지 않는다.

🔴 **체크섬을 반드시 다시 맞춘다** — 이 게임은 부팅 때 헤더 체크섬(0x18E)을 스스로 검사하고,
틀리면 `$11330` 에서 **붉은 화면**을 칠하며 멈춘다(2026-09-06 실측: 안 맞춰 굽고 한 번 물렸다).
에뮬레이터가 아니라 **게임**이 본다.

⚠ 산출물은 `work/emu/` 에만 둔다(배포 빌드 아님).
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

HOOK = 0x13780  # lea.l $16224.l, a3
HOOK_OPERAND = HOOK + 2
ORIG_LEA = bytes.fromhex("47f900016224")
# 엔딩은 **장면 준비까지 하는 루틴**을 부른다(표만 갈아 끼우면 팔레트·그림이 없어 빨간 화면이 된다).
#   02c2c6  그림 적재(gfx_d $1d3dba → VRAM $e000) · 팔레트 · `bsr $2de86`(나레이션)
#   02c33a  `bsr $2c92c` · `lea $2f1fe,a1` · `lea $2fa10,a2` · `lea $2ed38,a3` · `bsr $2eb4c`(대사 8화면)
#   02c1a2  엔딩 **전체** — 화면·음악 준비 뒤 아래를 차례로 부른다(직선 시퀀스, 표가 아니다)
#             jsr $2c2c6(나레이션) · jsr $2c33a(대사 8화면) · jsr $2c366 · $2c4d6 · $2c502 …
FULL_ENTRY = 0x2C1A2
NARR_ENTRY = 0x2C2C6
DLG_ENTRY = 0x2C33A


def _src() -> bytes:
    p = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_") / "ed1-kr.bin"
    if not p.exists():
        raise SystemExit(f"빌드가 없다: {p} — python3 tools/build.py 부터")
    return p.read_bytes()


def main() -> None:
    d = _src()
    if d[HOOK : HOOK + 6] != ORIG_LEA:
        raise SystemExit(f"후킹 자리가 다르다 @{HOOK:#x}: {d[HOOK : HOOK + 6].hex()}")
    if "--check" in sys.argv:
        print(f"  후킹 자리 OK @{HOOK:#x} — {ORIG_LEA.hex()}")
        return

    def hook(entry: int, name: str) -> Path:
        b = bytearray(d)
        # `lea $16224,a3`(6) + `bsr $14e44`(4) = 10B 자리에 `jsr entry`(6) + `nop`×2(4)
        b[HOOK : HOOK + 10] = b"\x4e\xb9" + struct.pack(">I", entry) + b"\x4e\x71\x4e\x71"
        b[0x18E:0x190] = struct.pack(">H", common.header_checksum(bytes(b)))  # 게임이 본다
        out = common.EMU_DIR / name
        out.write_bytes(bytes(b))
        return out

    # 오프닝을 **먼저 돌리고** 엔딩을 부르는 판 — 오프닝이 화면·팔레트를 정리해 두므로 배경 쓰레기가
    # 줄어든다(엔딩은 최종 전투 뒤 화면 상태를 물려받는 구조라 타이틀에서 바로 뛰면 타일이 남는다).
    after = bytearray(d)
    after[HOOK + 10 : HOOK + 20] = b"\x4e\xb9" + struct.pack(">I", FULL_ENTRY) + b"\x4e\x71\x4e\x71"
    after[0x18E:0x190] = struct.pack(">H", common.header_checksum(bytes(after)))
    out3 = common.EMU_DIR / "ed1_ending_after_op.bin"
    out3.write_bytes(bytes(after))

    out0 = hook(FULL_ENTRY, "ed1_ending.bin")
    out1 = hook(NARR_ENTRY, "ed1_endnarr.bin")
    out2 = hook(DLG_ENTRY, "ed1_enddlg.bin")
    print(f"  {out0} — 오프닝 자리에서 엔딩 **전체**(진입 {FULL_ENTRY:#x}) ⭐ 이걸 쓴다")
    print(f"  {out1} — 나레이션만(진입 {NARR_ENTRY:#x}) · 화면 준비가 빠져 배경이 깨진다")
    print(f"  {out2} — 대사만(진입 {DLG_ENTRY:#x}) · 위와 같음")
    print(f"  {out3} — 오프닝을 튼 **뒤** 엔딩(배경이 덜 깨진다)")
    print("  타이틀에서 「처음부터」를 고르면 바로 돈다.")


if __name__ == "__main__":
    main()
