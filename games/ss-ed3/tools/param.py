"""`/SYSTEM/PARAM.BIN` — 표 넷이 한 파일에 이어 붙어 있다.

🔴 **경계를 못 보면 표끼리 서로를 밀고 들어간다.** 실측으로 데인 자리다 — 적 stride 를
파일 끝까지 밀었더니 아이템 설명과 쓰레기가 섞여 **이름 아닌 144 건**이 나왔고, 그 탓에
`ネクロマンサー` 가 표에 없다고 오판해 다른 이름의 번역 근거로 삼았다(2026-08-24).

경계는 추측이 아니라 **데이터가 스스로 말한다** — 표마다 `reserve`(빈 슬롯) 와
`Sentinel`(끝) 이 박혀 있다. 그걸 찾은 뒤로 세 표가 정본과 정확히 맞았다(2026-08-25).
⚠ 칸 수는 **표 끝이 다음 구간의 시작과 맞는지**로 검산한다 — `names()` 는 표식을 거르므로
칸 수를 조금 적게 잡아도 **결과가 같아 보인다**(실측: 149 로 적었는데도 147 이 나왔다).
`tests/test_param.py` 가 이 등식을 지킨다.

    0x009C  적          stride 0x4C × 95   → 고유 48 (0x50 「零號機」는 시험 레코드 — 표 밖. 0x9C 「うりぼう」는 실제로 나온다)
    0x1CD0  아이템      stride 0x44 × 151  → 실제 147 (+reserve 3, 끝 Sentinel)
    0x44EC  ── 빈 영역 7,140B (전부 0) ⚠ 안 쓴다, 아래 주석
    0x60D0  아이템 설명 NUL 구분           → 132 (+ASCII 더미 4)
    0x6F8C  마법·기술   stride 0x50 × 48   → 주문 16 · 기술 19 · 내부 라벨
    0x838C  마법 설명   NUL 구분           → 21
    0x85F1  ── 이후 끝까지 수치 데이터 (텍스트 없음)

⚠ **텍스트는 이 다섯이 전부다**(2026-08-25 전수 확인). `0x85F1` 뒤 15,835B 를 훑으면
일본어 조각이 8 건 잡히는데 **전부 `勝` 한 글자짜리 오탐**이다 — 수치가 우연히 SJIS 로
디코드된 것. 이 게임 전반의 함정이라 `docs/status.md` 「함정」 절에도 적혀 있다.

⚠ **빈 영역 7,140B 에 손대지 않는다.** 여유 공간처럼 보이지만 이 레포엔 「0런 3중 검증을
통과하고도 사운드 뱅크 안이라 효과음이 조용히 깨진」 전례가 있다(`docs/reference`).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import common as C

PATH = "/SYSTEM/PARAM.BIN"

ENEMY = (0x009C, 0x4C, 95)  # 🔴 0x9C 의 「うりぼう」도 적이다 — 종전 0xE8 시작이라 번역에서 빠졌다(마스터 10-09 화면 확인)
ITEM = (0x1CD0, 0x44, 151)
SPELL = (0x6F8C, 0x50, 48)
DESC_ITEM = (0x60D0, 0x6F8C)  # 아이템 설명 — NUL 구분 (start, end)
DESC_SPELL = (0x838C, 0x85F1)  # 마법·적기술 설명 — 같은 규약
GAP = (0x44EC, 0x60D0)  # ⚠ 전부 0 — 쓰지 않는다

# 표의 끝·빈 칸을 나타내는 표식. 이름이 아니므로 목록에서 뺀다.
MARKS = ("reserve", "Sentinel", "Sentinel.")
# 설명문 끝에 붙은 디버그 더미 — ASCII 라 한눈에 갈린다.
DESC_NL = "＄"  # 화면 개행 (제어코드가 아니라 전각 문자다)


def load(disc=1):
    with C.open_disc(disc) as d:
        return d.read(PATH)


def _at(b, off, limit):
    """`off` 에서 NUL 까지. 못 읽으면 `None` (그래픽·쓰레기 구간)."""
    e = b.find(b"\x00", off, off + limit)
    if e < 0 or e == off:
        return None
    try:
        return b[off:e].decode("shift_jis")
    except UnicodeDecodeError:
        return None


def records(b, table):
    """`(base, stride, count)` 표 → 칸마다 이름(빈 칸은 `None`). **표식도 그대로 준다.**"""
    base, stride, count = table
    return [_at(b, base + k * stride, stride) for k in range(count)]


def names(b, table):
    """표 → 실제 이름만. `reserve`·`Sentinel`·빈 칸을 뺀다 — 경계 표식이 곧 필터다."""
    return [n for n in records(b, table) if n and n not in MARKS]


def descs(b, area=DESC_ITEM, keep_dummy=False):
    """설명문. `＄` 가 개행이고, 아이템 쪽은 끝에 ASCII 더미(`quux`…`Sentinel`) 넷이 붙는다."""
    out = []
    for p in b[area[0] : area[1]].split(b"\x00"):
        if not p:
            continue
        try:
            t = p.decode("shift_jis")
        except UnicodeDecodeError:
            continue
        if not keep_dummy and t.isascii():
            continue
        out.append(t)
    return out


def main():
    b = load()
    for label, tbl in (("적", ENEMY), ("아이템", ITEM), ("마법·기술", SPELL)):
        rec, nm = records(b, tbl), names(b, tbl)
        print(f"{label:<10}칸 {len(rec):>3} · 이름 {len(nm):>3} · 고유 {len(set(nm)):>3}")
    for label, area in (("아이템 설명", DESC_ITEM), ("마법 설명", DESC_SPELL)):
        ds = descs(b, area)
        rows = [l for t in ds for l in t.split(DESC_NL)]
        w, r = max(len(l) for l in rows), max(len(t.split(DESC_NL)) for t in ds)
        print(f"{label:<8}{len(ds):>4} 조각 · {len(rows):>3} 행 · 최장 {w} 전각 · 최다 {r} 행")
    gap = b[GAP[0] : GAP[1]]
    print(f"{'빈 영역':<9}{len(gap):,}B · 0 아닌 바이트 {sum(1 for x in gap if x)}")


if __name__ == "__main__":
    main()
