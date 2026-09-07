"""폰트 소재 판정 — 「한글을 어디에 얹나」의 정본 측정.

레트로 PC 는 한자를 **본체 CGROM** 으로 그리는 게 보통이라, 새턴·PS1 처럼 「폰트 파일에
한글을 부어 넣기」가 성립하지 않는다. 이 게임은 다행히 **CGROM 도트를 직접 읽어 RAM 에
찍는 소프트웨어 렌더링**이라 그 루틴 하나가 후킹 지점이 된다.

이 스크립트는 그 판정을 **재현 가능하게** 다시 낸다(원본만 있으면 어디서나 같은 답).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# CG 윈도우 규약 (PC-9801)
#   out 0xA1 = 문자 코드 하위(ten) · out 0xA3 = 상위(ku)
#   out 0xA5 = 행 번호      · in  0xA9 = 그 행의 도트 8비트
#   out 0x68, 0x0B = CG 도트 접근 모드
CG_SEQ = bytes.fromhex("e6a186e0e6a3")  # out A1 / xchg al,ah / out A3
CG_ROW = bytes.fromhex("e6a5e4a9")  # out A5 / in A9
CG_MODE = bytes.fromhex("b00be668")  # mov al,0Bh / out 68h


def find_all(data: bytes, pat: bytes) -> list[int]:
    out, i = [], data.find(pat)
    while i >= 0:
        out.append(i)
        i = data.find(pat, i + 1)
    return out


def main() -> int:
    flats = common.check_originals()
    total = 0
    for key, flat in flats.items():
        seq = find_all(flat, CG_SEQ)
        row = find_all(flat, CG_ROW)
        mode = find_all(flat, CG_MODE)
        total += len(seq)
        print(
            f"{key:9s} CG코드지정 {len(seq):2d}곳  행읽기 {len(row):3d}곳  CG모드 {len(mode):2d}곳"
        )
        for off in seq:
            print(f"            {off:#08x}")
    if total == 0:
        raise SystemExit("🔴 CG 루틴이 하나도 안 잡혔다 — 판정이 뒤집혔다. 문서를 고쳐라.")
    print()
    print(f"판정: 게임이 CGROM 글리프를 **직접 읽어 그린다**(총 {total}곳).")
    print("      ⇒ 한글은 폰트 파일 교체가 아니라 **이 루틴의 후킹**으로 넣는다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
