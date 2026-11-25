"""마스터 mednafen 상태 → 새 롬에서 읽는 BRAM 세이브 — 「그 자리」를 새 빌드로 다시 여는 길(11-18).

상태(`mcN`)는 옛 빌드의 코드·데이터가 RAM 에 든 채 복원돼 새 코드를 시험할 수 없다. 대신 게임 상태 변수(`$C000~$C3FF`, 뱅크 0x74 머리)만 꺼내
세이브(601B 비트 직렬화)로 구우면, 새 롬을 **콜드부트 → 이어하기**로 그 씬·좌표·깃발·파티·소지품에 선다(맵 로드가 새 롬 코드·씬 블록으로 돈다).

    # 1) 마스터 상태를 gunzip 한 `.mc`(playbook) — 상태 파일의 `SysCardRAM` 구역(뱅크 0x68~, 192KB)에서 뱅크 0x74 머리 1024B 를 직접 읽는다
    # 2) python3 games/pce-ed1/tools/state2save.py <mcN.mc> --sav /root/save/pce-ed1/ed1.sav --out <새.sav> [--slot 3]
    # 3) emucap: 새 롬 launch → reset → write_memory(bram, input_file={path,length:2048}) → 부팅 입력 → 이어하기(슬롯 번호만큼 down)

⚠ 이어하기 직후라 이벤트 진행 중이던 것(음성·창)은 그 자리의 입장 스크립트부터 다시 돈다. 걷지 않고 화면 번호·방향만 바꿔야 하면 `--set ADDR=VAL`.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import savefile as S


def game_vars(state: bytes) -> bytes:
    """상태 파일의 `SysCardRAM`(이름 뒤 크기 4B + 자료, 뱅크 0x68 부터) 안 뱅크 0x74 머리 — 게임 변수 `$C000~$C3FF`."""
    i = state.find(b"SysCardRAM")
    if i < 0:
        raise SystemExit("상태에 SysCardRAM 구역이 없다(gunzip 한 파일인가)")
    i += 10
    size = int.from_bytes(state[i : i + 4], "little")
    d = i + 4
    if size < 0x18400:
        raise SystemExit(f"SysCardRAM 크기 {size}")
    return state[d + 0x18000 : d + 0x18400]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("state", help="gunzip 한 mednafen 상태(`.mc`)")
    ap.add_argument("--sav", required=True, help="틀로 쓸 BRAM(마스터 세이브)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--slot", type=int, default=3)
    ap.add_argument("--src", type=int, default=1, help="틀 슬롯(항목 모양만 베낀다)")
    ap.add_argument("--set", action="append", default=[], metavar="ADDR=VAL")
    a = ap.parse_args()
    ram = game_vars(Path(a.state).read_bytes())
    bram = Path(a.sav).read_bytes()
    ents = S.entries(bram)
    off, sz = ents[a.src - 1]
    tmpl = bram[off : off + sz]
    vals = S.decode(tmpl[S.ENTRY_HDR : S.ENTRY_HDR + S.SAVE_LEN])
    skipped = []
    for addr, bits, kind in S.layout():
        if kind == "z" or not 0xC000 <= addr < 0xC400:
            continue
        v = ram[addr - 0xC000]
        if (v - 1 if kind == "m1" else v) >= 1 << bits or (kind == "m1" and v == 0):
            skipped.append(
                addr
            )  # 실행 중에만 쓰는 값(예: $C013=FF) — 세이브 폭에 안 들어간다. 틀 값을 둔다
            continue
        vals[addr] = v
    if skipped:
        print("틀 값 유지(폭 초과):", " ".join(f"${x:04X}" for x in skipped))
    S.set_values(vals, a.set)
    out = S.set_entry(bram, a.slot, vals, tmpl)
    Path(a.out).write_bytes(out)
    v = (
        S.decode(out[ents[0][0] + S.ENTRY_HDR : ents[0][0] + S.ENTRY_HDR + S.SAVE_LEN])
        if False
        else vals
    )
    print(
        f"슬롯 {a.slot} ← 장{v[S.CHAPTER] + 1} 지역{v[S.REGION]} 씬{v[S.SCENE]} xy=({v[0xC000]},{v[0xC001]}) → {a.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
