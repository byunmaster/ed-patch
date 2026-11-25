"""패턴 검색→치환 자리 전수 감사(11-07 관리자 공지 — SFC II 프리징: 이미지 전체 패턴 치환이 우연히 같은 바이트의 음악·팔레트·데이터까지 고침).

이 빌드에서 **바이트 패턴을 찾아 피연산자를 고치는** 곳은 둘이다:
  ① `systext.scan_literals` — 뱅크 0x69~0x73 에서 `JSR $503E/$4ED5/$4ED1 · BIT $addr`(`20 xx xx 2C lo hi`)
  ② `kanma.py` 장면 코드 — 패키지 창에서 `JSR $56F5 · BIT $addr`(`20 F5 56 2C lo hi`)
둘 다 **그 자리가 진짜 명령어일 때만** 옳다. 자료(표·음악·팔레트) 안에서 우연히 같은 6바이트가 나오면 거기를 고쳐 버린다.
여기서는 ① 의 매치마다 「바로 앞 명령들이 불법 없이 이어져 그 JSR 에 정확히 닿는가」를 디코드로 보고, 안 닿는 자리를 센다.
기준선(`data/pattern_sites_baseline.json`)보다 늘면 실패 — 새 매치는 사람이 보고 사유를 적어야 한다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import dis6280
import layout
import systext

BASE = Path(__file__).resolve().parents[1] / "data" / "pattern_sites_baseline.json"
LEAD = 40  # 앞쪽 몇 바이트에서 동기를 찾나


def reaches(code: bytes, target: int) -> bool:
    """`target` 앞 LEAD 바이트 안의 어느 시작점에서 불법(.db) 없이 읽어 가면 정확히 target 에 닿나(앞 명령 둘 이상을 거쳐야 한다)."""
    for s in range(max(0, target - LEAD), target - 1):
        i, n, good = s, 0, True
        while i < target:
            t, ln = dis6280.decode(code[i : i + 7], 0x6000 + i)
            if t.startswith(".db"):
                good = False
                break
            i += ln
            n += 1
        if good and i == target and n >= 2:
            return True
    return False


def literal_rows(prog: layout.Prog) -> list[tuple[int, int, bool]]:
    rows = []
    for (b, _off), ps in sorted(systext.scan_literals(prog).items()):
        code = prog.o(b, 0, layout.BANK)
        for pos in ps:
            rows.append((b, pos - 4, reaches(code, pos - 4)))  # pos-4 = JSR 시작
    return sorted(rows)


def table_rows(prog: layout.Prog) -> list[tuple[str, int, int, bool]]:
    """표 시작 즉치(`LDY #hi / LDX #lo`, 두 순서) — 옮긴 표는 **뱅크 안 모든 매치**의 hi·lo 를 고친다. 매치마다 명령 경계인지 본다."""
    rows = []
    for name, bank, a, _b in systext.TABLES:
        code = prog.o(bank, 0, layout.BANK)
        for _hi, _lo, start in systext.table_sites(prog, bank, a):
            rows.append((name, bank, start, reaches(code, start)))
    return rows


def package_rows() -> list[tuple[int, int, bool]]:
    """장면 코드 패키지의 `JSR $56F5 · BIT <포인터>` — 번역한 메시지를 가리키는 호출만 고친다(포인터가 실제 메시지 시작과 같아야 한다). 그 호출이 명령 경계인지 본다."""
    import common
    import kanma

    rows = []
    for n in kanma.PKGS:
        if not any(k.startswith(f"{n}:") for k in kanma.load_ko()):
            continue
        pkg = common.track_data(kanma.pkg_rel(n), 128)
        refs = kanma.msg_refs(pkg)
        for off, _m in kanma.messages(pkg, n):
            for pos in refs.get(off, []):
                rows.append((n, pos - 4, reaches(pkg, pos - 4)))
    return rows


def unreached(prog: layout.Prog) -> list[str]:
    return [f"{b:02X}+{o:04X}" for b, o, ok in literal_rows(prog) if not ok]


def main() -> int:
    prog = layout.Prog()
    rows = literal_rows(prog)
    trows = table_rows(prog)
    bad = [f"{b:02X}+{o:04X}" for b, o, ok in rows if not ok]
    bad += [f"표 {n} {b:02X}+{o:04X}" for n, b, o, ok in trows if not ok]
    prows = package_rows()
    bad += [f"패키지 {n} +{o:04X}" for n, o, ok in prows if not ok]
    print(f"표 시작 즉치 {len(trows)}곳 · 장면 패키지 호출 {len(prows)}곳")
    base = json.loads(BASE.read_text()) if BASE.exists() else {"unreached": []}
    new = sorted(set(bad) - set(base["unreached"]))
    print(f"패턴 치환 자리(리터럴 피연산자) {len(rows)}곳 — 명령 경계 미확인 {len(bad)}곳, 기준선 밖 {len(new)}곳")
    for x in bad:
        print("  미확인", x, "(기준선)" if x in base["unreached"] else "← 새 것")
    if "--freeze" in sys.argv:
        BASE.write_text(json.dumps({"unreached": bad}, indent=1) + "\n")
        print("기준선 갱신")
        return 0
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
