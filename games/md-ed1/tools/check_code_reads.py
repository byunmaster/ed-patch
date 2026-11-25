"""코드가 **읽는** 원판 바이트 감사 — 문자열 칸을 비우거나 다시 쓰며 그 안쪽에 코드가 피연산자로 읽는 표 바이트(워드·바이트 상수)가
묻혀 있던 걸 지우는 사고를 잡는다(PCE II 에서 퀵메뉴 선택이 조용히 무시됐고, 우리도 연승 숫자 기준 워드 0x325BE 가
한글 코드로 덮여 「n연승」의 숫자가 엉뚱한 글자였다 — 11-07).

코드 영역(< 0x34500 · 0x1F6000~)의 **절대 주소 피연산자**(`op abs.l`, 주소 지정 모드 7/1)가 가리키는 자리 중, 명령이
주소를 **번지로 쓰는 것**(lea·pea·jsr·jmp — 문안 스트림·코드 진입 — 은 `sysmsg`/`build` 가 따로 본다)이 아니라
**값을 읽는 것**(move·add·cmp·tst …)인데 빌드에서 그 2B 가 원판과 다르면 실패한다. 의도한 변경은 ALLOW 에.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import scene

IMM_FIRST = {0x13FC, 0x33FC, 0x23FC}  # `move #imm,abs.l` — 주소가 즉치 뒤에 온다(앞 판독은 오탐)
ADDR_OPS = {0x41F9, 0x43F9, 0x45F9, 0x47F9, 0x49F9, 0x4BF9, 0x4DF9, 0x4879, 0x4EB9, 0x4EF9}
ALLOW: dict[int, str] = {}  # 주소 → 사유(의도한 변경)
CODE = [(0x200, 0x34500), (0x1F6000, 0x200000)]
# 씬 모듈의 「쓰기 lea ↔ 읽기 lea」 짝 — 같은 칸을 가리켜야 한다(원판 목표 차이가 새 모듈에서도 같아야 함). 씬 161: 0x384 `lea $C77(pc),a6; move.b d0,(a6)` 가 연승 수를
# 글자 칸에 쓰고 0x38C `lea $C76(pc),a1` 이 읽는다(+1 차). 읽기만 새 스트림으로 가고 쓰기가 옛 자리에 남던 결함(11-07, MD II 알림 꼴)을 막는다.
MODULE_PAIRS = {161: [(0x384, 0x38C)]}


def scan(orig: bytes, new: bytes) -> list[tuple[int, int, int]]:
    bad = []
    for lo, hi in CODE:
        for p in range(lo, hi - 5, 2):
            if orig[p : p + 6] != new[p : p + 6]:
                continue  # 우리가 고친 명령은 우리 몫
            w = struct.unpack(">H", new[p : p + 2])[0]
            v = struct.unpack(">I", new[p + 2 : p + 6])[0]
            ok = (w & 0x3F) == 0x39 or (
                (w >> 12) in (1, 2, 3) and (w & 0x1C0) == 0x1C0 and ((w >> 9) & 7) == 1
            )
            if not ok or w in ADDR_OPS or w in IMM_FIRST or (w >> 12) == 0 or not (0x200 <= v < 0x200000 - 4):
                continue
            if orig[v : v + 2] != new[v : v + 2] and v not in ALLOW:
                bad.append((p, w, v))
    return bad


def scan_modules(orig: bytes, new: bytes) -> list[tuple[int, int, int]]:
    """씬 모듈 코드의 `lea/pea d16(pc)` 가 **옛 스트림 안쪽**(시작이 아닌 자리)을 가리키면 그 바이트는 자료일 수 있다 — 씬 20 의 문 서술자는 첫 바이트가
    옛 스트림의 끝 코드(06)와 겹쳐 있어, 옛 스트림을 0 으로 지우자 서술자 [0] 이 06→00 으로 바뀌었다(11-07). 새 모듈의 같은 자리 1바이트가
    원판과 같아야 한다(코드 변위는 옮겨지지 않는 한 같다). 반환 (블록, 명령 자리, 목표)."""
    ob = archives.blocks(orig, archives.ARCHIVES["script"][0])
    nb = archives.blocks(new, archives.ARCHIVES["script"][0])
    bad = []
    for i in range(len(ob)):
        a, b = ob[i][1], nb[i][1]
        if a == b:
            continue
        mod = scene.parse_module(a)
        spans = [(tk.off, tk.off + len(tk.raw)) for st in mod.streams.values() for tk in st.tokens]
        for p in range(0, len(a) - 3, 2):
            w = (a[p] << 8) | a[p + 1]
            if (w & 0xF1FF) != 0x41FA and w != 0x487A:
                continue
            d = (a[p + 2] << 8) | a[p + 3]
            t = p + 2 + (d - 0x10000 if d & 0x8000 else d)
            if p in mod.roots or t in mod.streams or not 0 <= t < min(len(a), len(b)):  # 뿌리 lea 는 재조립이 새 자리로 옮긴다
                continue
            if any(lo <= t < hi for lo, hi in spans) and a[t] != b[t]:
                tn = p + 2 + (((b[p + 2] << 8) | b[p + 3]) ^ 0x8000) - 0x8000
                if tn == t:  # 목표가 안 옮겨졌는데 바이트가 달라졌다
                    bad.append((i, p, t))
        for w, r in MODULE_PAIRS.get(i, []):
            dw = lambda m, q: q + 2 + (((m[q + 2] << 8) | m[q + 3]) ^ 0x8000) - 0x8000
            if dw(b, w) - dw(b, r) != dw(a, w) - dw(a, r):
                bad.append((i, w, dw(b, w)))
    return bad


IMM_ALLOW = {0x7D04: "move.w #$9C40,d0 — 상수(SJIS 우연), 글자 아님"}


def scan_immediates(new: bytes) -> list[tuple[int, int]]:
    """코드의 `move.w #imm,(An)+ / Dn` 즉치 워드가 **SJIS 가나·한자**(우리 한글 코드 아님)면 화면 글자를 코드가 조립하는 것이다 — 주문서 「の書」 · 저장 확인
    「N番目の」(11-07 MD II 알림)는 연속 2자 텍스트 스캔·문안 참조 어디에도 안 걸렸다. 반환 (자리, 값)."""
    import json

    hang = set(
        json.loads((common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")).values()
    )
    bad = []
    for lo, hi in CODE:
        for p in range(lo, hi - 3, 2):
            w = (new[p] << 8) | new[p + 1]
            if (w & 0xF1FF) not in (0x30FC, 0x31FC, 0x303C) or p in IMM_ALLOW:
                continue
            v = (new[p + 2] << 8) | new[p + 3]
            b1, b2 = v >> 8, v & 0xFF
            if v in hang or not (0x81 <= b1 <= 0x9F or 0xE0 <= b1 <= 0xEF) or not (0x40 <= b2 <= 0xFC and b2 != 0x7F):
                continue
            try:
                ch = bytes([b1, b2]).decode("cp932")
            except UnicodeDecodeError:
                continue
            if "぀" <= ch <= "ヿ" or "一" <= ch <= "鿿":
                bad.append((p, v))
    return bad


def main() -> int:
    orig = common.rom()
    new = (common.BUILD_DIR / common.BUILD_TAG / "ed1-kr.bin").read_bytes()
    bad = scan(orig, new)
    for p, w, v in bad:
        print(f"  ❌ {p:#x} op {w:04x} 이 {v:#x} 를 읽는데 원판과 바이트가 다르다")
    mb = scan_modules(orig, new)
    for i, p, t in mb:
        print(f"  ❌ 씬 {i} 모듈 @{p:#x} lea 가 옛 스트림 안쪽 {t:#x} 를 가리키는데 새 모듈의 그 바이트가 원판과 다르다")
    ib = scan_immediates(new)
    for p, v in ib:
        print(f"  ❌ 코드 {p:#x} 즉치 워드 {v:#06x} 가 SJIS 가나·한자다 — 코드가 일본어 글자를 화면에 붙인다")
    if bad or mb or ib:
        return 1
    print("  코드가 읽는 절대 주소 피연산자 — 읽는 자리는 전부 원판과 같다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
