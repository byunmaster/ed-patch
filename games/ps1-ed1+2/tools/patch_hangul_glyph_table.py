#!/usr/bin/env python3
"""058ⓑ/062 반각 글리프 굽기 — HUD 지명·경로 라벨을 "조각낸 전각" 그림으로 굽는다.

경위(2026-09-14): 개별 음절을 반각 코드 하나씩(0xC1~0xCA)에 렌더했더니 마스터
화면에서 "늑대의입"이 "늑다으입"으로 깨졌다 — 반각 **전진폭 6px** 인데 우리 글리프는
7px(Galmuri11-Condensed 의 BBX 폭)라, 각 글자의 7번째 열이 **다음 글자의 첫 열에
덮였다**(RE 실측: 화면 x=260·266·272·278 — 정확히 6px 간격). 062 로 번호가 붙었다.

**"슬롯을 늘리면 되지 않나"부터 확인했다** — 안 된다. 슬롯(8B) 바로 뒤는 널 패딩이
아니라 **살아있는 이벤트 핸들러 포인터 표**다(RE 디스어셈블: 그 포인터가 가리키는
코드가 카메라 좌표 `0x800E43FC`에 값을 쓴다 — 진짜 코드다). 1바이트만 밀려도 포인터가
`0x8017A4DC`→`0x8017A400`처럼 **코드 한가운데를 가리키게 돼 소프트락**이 난다.
원본이 이 자리에 3음절(6B)+NUL 만 넣어 뒀던 것도 이 8B 벽 때문이었다.

**그래서 마스터 조건문대로 간다** — 슬롯을 못 늘리는 자리는 **전각 문자열을 그림으로
그리고 6px씩 잘라 여러 코드에 나눠 굽는다.** 반각 전진폭이 정확히 6px로 빈틈없이
이어지므로(RE 실측), 화면에서 그 코드들이 순서대로 나오면 원본 그림이 그대로
복원된다.

🔴 **후속(같은 날) — 7조각(42px)은 슬롯 자체가 아니라 복사 루틴에 걸렸다.** RE 가
실측: 이 HUD 자리의 이름 복사는 **최대 7바이트**이고 그 **안에서** 널을 만나야만
복사된다 — 내용 6B(널이 인덱스6)는 종단 OK, 내용 7B(널이 인덱스7)는 **복사 창
밖이라 종단이 안 온다.** 그 결과 ED2 는 재진입 시 버퍼에 남은 옛 이름 꼬리가
그대로 그려졌고, ED1 은 접미 조립 루틴(RAM 0x800856BC)이 이름 끝을 못 찾아 잔재
글자 뒤에 접미(" 입구")를 붙였다 — **내용은 6바이트(6조각)가 상한**이다.

⇒ **41px(자간 0, 4글자 압축)이 아니라 마스터가 직접 도트로 찍은 36px(6조각) 도안을
그대로 쓴다** — 자간이 도안 안에 이미 들어 있어 압축보다 읽기 좋다. `HUD_GRID`
(아래)가 그 정본이고, **우리가 다듬거나 재압축하지 않는다.**
큐베라프로스(경로 라벨, 66px/11조각)도 같은 방식으로 확정됐다 — ED1 에서 6조각이
군더더기 없이 그려짐을 확인해 ED1·ED2 가 같은 복사 상한(7B, 내용 6B)을 쓴다는 게
섰고, 마스터가 이 자리도 도안을 찍어 `ROUTE_GRID` 로 정본이 됐다(구분자는 물결표가
아니라 줄표 — 아래 참조).

⚠ **이 코드들은 이제 "이 문자열 전용"이다** — 조각은 음절이 아니라 그림 일부라
다른 글자로 재활용 불가(RE 지적). 기존 0xC1~0xCA(10칸, 음절 하나씩 굽던 시절 것)도
같은 이유로 **새 그림으로 다시 굽는다** — 조사 훅의 `HALFWIDTH_KR_ALLOC`(음절 배정)은
그대로 두되(코드값 자체는 안 바뀐다), 화면에 나가는 내용만 바꾼다.

⚠ **주소가 단조가 아니다**(RE 실측·확정). 표 색인은 손계산 금지 — RE 가 시뮬레이터로
가지를 밟아 낸 값을 그대로 쓴다. 식(`주소 = 0x80104778 + 색인 × 11`)은 검산용이다.

형식: 8×11 비트맵, 행당 1바이트(MSB=왼쪽 픽셀), 글리프당 11바이트. **잉크는 열
0~5(6px)에만** — 열 6·7 은 항상 비운다(안 그러면 다음 조각을 먹는다, 062 의 원인
그대로).

표는 ED.EXE·ED2.EXE 두 벌이다(034·051·058ⓑ 와 같은 "사본이 둘" 부류) — `EXES` 아래
둘 다 굽는다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import BUILD_DIR, extract, write_user_data

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"

# {코드: (표 색인, 원본 글리프 11B)} — RE 확정. 색인이 연속이 아니다 — 손대지 말고
# 이 표 그대로 쓴다. 원본 바이트는 반각 가타카나(빈 칸으로 골라 겹칠 소비자가 없음,
# RE 3층 스캔 확정) — 쓰기 전 사전조건으로 대조해 이중 적용·주소 어긋남을 막는다.
GLYPH_ROWS = {
    # 0xC1~0xCA — 058ⓑ 최초 배정(2026-09-14). 062 이전엔 음절 하나씩 담았다.
    0xC1: (223, bytes.fromhex("0c701010fc101010102040")),  # ﾁ
    0xC2: (226, bytes.fromhex("0020a4a484040808102040")),  # ﾂ
    0xC3: (228, bytes.fromhex("00780000fc101010102040")),  # ﾃ
    0xC4: (230, bytes.fromhex("4040404060504840404040")),  # ﾄ
    0xC5: (232, bytes.fromhex("101010fc10101010102040")),  # ﾅ
    0xC6: (233, bytes.fromhex("000078000000000000fc00")),  # ﾆ
    0xC7: (234, bytes.fromhex("007c040448281018244080")),  # ﾇ
    0xC8: (235, bytes.fromhex("3000f808102068a4202020")),  # ﾈ
    0xC9: (236, bytes.fromhex("0008080810101020204080")),  # ﾉ
    0xCA: (237, bytes.fromhex("0000484848444444848400")),  # ﾊ
    # 0xCB·0xCE~0xD4 — 062 추가 배정(2026-09-14, RE). 색인이 세 가지(0x800AE5A0·
    # 0x800AE5E4·0x800AE5F4)로 갈리는 비단조 표라 손계산 금지 — 값 그대로.
    0xCB: (240, bytes.fromhex("80808098e0808080808078")),  # ﾋ
    0xCE: (249, bytes.fromhex("2020fc20a8a8a4a4a42060")),  # ﾎ
    # 0xCF(252, ﾏ) — 062 가 7조각→6조각으로 줄면서 안 쓰게 됐다. 굽지 않고 되돌려
    # 둔다(원래 가타카나 그대로) — 다음에 반각 칸이 하나 더 필요하면 여기서 고른다.
    0xD0: (253, bytes.fromhex("0060100060100000c03008")),  # ﾐ
    0xD1: (254, bytes.fromhex("0020202020404848849ce4")),  # ﾑ
    0xD2: (255, bytes.fromhex("0008080848301018244080")),  # ﾒ
    0xD3: (256, bytes.fromhex("00f8202020fc202020201c")),  # ﾓ
    0xD4: (258, bytes.fromhex("40407cc444482020202020")),  # ﾔ
}
# {실행파일: (LBA, 크기, 표 base file오프셋)} — base = RAM 0x80104778 등가, 실행파일마다
# 로드 위치가 달라 file오프셋만 다르다. 주소 = base + 색인×11(검산용 식).
EXES = {
    "ED.EXE": (257, 1021952, 0xF4F78),
    "ED2.EXE": (756, 872448, 0xD0910),
}

# 조각 배정 — 어느 코드가 캔버스의 몇 번째 6px 조각을 담는지. 순서가 곧 화면 좌→우.
# 둘 다 복사 상한(7B, 내용 6B)이 확정돼 **마스터 도트 도안**(HUD_GRID·ROUTE_GRID)이
# 정본이다 — 폰트에서 다시 계산하지 않고 그 비트맵을 그대로 6px씩 잘라 쓴다.
HUD_CODES = (0xC1, 0xC2, 0xC3, 0xC4, 0xCB, 0xCE)  # 36px → 6조각
ROUTE_CODES = (0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4)  # 66px → 11조각

# 🔴 **마스터가 직접 도트로 찍은 정본**(2026-09-14, 도트판) — 36×11, 6px 6조각.
# **다듬거나 재압축하지 않는다.**
HUD_GRID = (
    ".#.......####.#.#...##....#...##...#",
    ".#.......#....#.#..#..#...#..#..#..#",
    ".#.......#....#.#.#....#..#.#....#.#",
    ".######..#....#.#.#....#..#.#....#.#",
    ".........#....#.#..#..#...#..#..#..#",
    "########.#....###...##....#...##...#",
    ".........#....#.#.........#.........",
    ".######..#....#.#.........#..#.....#",
    "......#..#....#.#.#######.#..#######",
    "......#..####.#.#.........#..#.....#",
    "......#.......#.#.........#..#######",
)

# 🔴 **마스터가 직접 도트로 찍은 정본**(2026-09-15, 도트판) — 66×11, 6px 11조각.
# **다듬거나 재압축하지 않는다.** 원본 물결표(SJIS 0x8160, 전각)와 대조해 모양을
# 확인받았으나, 최종 부호는 마스터 판정으로 **줄표(하이픈)**로 바뀌었다 — 물결표가
# 11칸 안에서 좌우로 빡빡했던 것과 달리 줄표는 4칸이라 훨씬 선명하다("큐베라-프로스").
ROUTE_GRID = (
    ".#######..#..#..#.#.#####..#.........########...#######......#....",
    ".......#..#..#..#.#.....#..#...........#..#...........#......#....",
    ".......#..#..#..#.#.....#..#...........#..#...........#......#....",
    ".#######..#..#..#.#.....#..#...........#..#.....#######.....#.#...",
    ".......#..#######.#.#####..#...........#..#.....#..........#...#..",
    "......#...#..#..#.#.#......##..####....#..#.....#.........#.....#.",
    "#########.#..#..#.#.#......#.........########...#######...........",
    "..#...#...#..#..#.#.#......#.......................#..............",
    "..#...#...#..#..#.#.#......#.......................#..............",
    "..#...#...####..#.#.#####..#........##########.#########.#########",
    "..#...#.........#.#........#......................................",
)


def _pack_glyph(bits6):
    """(11,6) 0/1 배열 → 11바이트, 행당 1B, MSB=왼쪽 픽셀. 열 6·7 은 항상 0(062 핵심)."""
    out = bytearray(11)
    for r in range(11):
        b = 0
        for c in range(6):
            if bits6[r][c]:
                b |= 1 << (7 - c)
        out[r] = b
    return bytes(out)


def slice_grid(grid, codes):
    """고정 비트맵(문자열 행 목록) → {코드: 11B 글리프} — `HUD_GRID` 처럼 손으로 확정된
    도안 전용. `slice_word()` 와 달리 폰트를 다시 그리지 않는다 — **입력 자체가 이미
    정본**이라 재계산할 대상이 없다(마스터 도트 원안, 손으로 다듬지 않는다)."""
    assert len(grid) == 11, f"행 수 {len(grid)} != 11"
    width = len(codes) * 6
    for r, row in enumerate(grid):
        assert len(row) == width, f"{r}행 길이 {len(row)} != {width}"
    out = {}
    for i, code in enumerate(codes):
        chunk = [[1 if ch == "#" else 0 for ch in row[i * 6 : i * 6 + 6]] for row in grid]
        out[code] = _pack_glyph(chunk)
    return out


def bake_glyphs():
    """{코드: 11B 글리프} — HUD·ROUTE 둘 다 마스터 도안(`HUD_GRID`·`ROUTE_GRID`)을 쓴다."""
    out = {}
    out.update(slice_grid(HUD_GRID, HUD_CODES))
    out.update(slice_grid(ROUTE_GRID, ROUTE_CODES))
    assert set(out) == set(GLYPH_ROWS), (
        f"조각 배정과 GLYPH_ROWS 코드 집합이 다르다: {set(out) ^ set(GLYPH_ROWS)}"
    )
    return out


def render_ascii(glyphs):
    """검산용 — 코드마다 8×11 을 텍스트로 그린다. 테두리 없음(오독 방지, 관리자 지적)."""
    lines = []
    for code in sorted(glyphs):
        lines.append(f"0x{code:02X}")
        for byte in glyphs[code]:
            lines.append("".join("#" if byte & (1 << (7 - c)) else "." for c in range(8)))
        lines.append("")
    return "\n".join(lines)


def render_strip_ascii(glyphs, codes):
    """검산용 — codes 순서대로 6px 간격 이어붙인 실제 화면 재현(테두리 없음)."""
    lines = [""] * 11
    for code in codes:
        rows = glyphs[code]
        for r in range(11):
            lines[r] += "".join("#" if rows[r] & (1 << (7 - c)) else "." for c in range(6))
    return "\n".join(lines)


def count_unbaked():
    """빌드 전체에서 **원본 그대로 남은** 글리프 칸이 몇 개인지 — 사본 개수 게이트용."""
    n = 0
    for lba, size, base in EXES.values():
        buf = extract(lba, size, path=IMG)
        for idx, orig in GLYPH_ROWS.values():
            off = base + idx * 11
            if bytes(buf[off : off + 11]) == orig:
                n += 1
    return n


def apply():
    glyphs = bake_glyphs()
    total = 0
    for exe, (lba, size, base) in EXES.items():
        buf = bytearray(extract(lba, size, path=IMG))
        n = 0
        for code, (idx, orig) in GLYPH_ROWS.items():
            off = base + idx * 11
            cur = bytes(buf[off : off + 11])
            if cur == glyphs[code]:  # 재빌드 — 이미 우리 값
                continue
            assert cur == orig, (
                f"{exe} 반각 글리프 표 @0x{off:X}(색인 {idx}, 코드 0x{code:02X}) 원본 불일치: "
                f"{cur.hex()} != {orig.hex()} — 다른 패치가 먼저 이 표를 건드렸을 수 있다"
            )
            buf[off : off + 11] = glyphs[code]
            n += 1
        if n:
            with open(IMG, "r+b") as f:
                write_user_data(f, lba, bytes(buf), label=f"반각 한글 글리프 표({exe})")
        print(
            f"  {exe}: 반각 한글 글리프 {n}개 구움 (0xC1~0xCA·0xCB·0xCE·0xD0~0xD4, 총 {len(GLYPH_ROWS)}칸)"
        )
        total += n
    remaining = count_unbaked()
    assert remaining == 0, (
        f"반각 글리프 표 — 아직 원본인 칸이 {remaining}개 남았다(사본을 하나 빠뜨렸을 수 있다)"
    )
    return total


if __name__ == "__main__":
    if "--preview" in sys.argv:
        g = bake_glyphs()
        print(render_ascii(g))
        print("--- 늑대의입 (이어붙임) ---")
        print(render_strip_ascii(g, HUD_CODES))
        print("--- 큐베라프로스 (이어붙임) ---")
        print(render_strip_ascii(g, ROUTE_CODES))
        sys.exit(0)
    sys.exit(0 if apply() else 1)
