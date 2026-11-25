"""좁은 글꼴(`06` 모드, 한 칸 8px) 한글 — 디버그 마을(패키지 258) 목록용(마스터 11-09 「3번으로 갈무리 콘덴스드 같은 폰트」).

원판 `06` 모드는 한 바이트 가나·ASCII 를 8×12 도안(12바이트)으로 그리고(`$6450 JSR $6513` → 뱅크 0x6C `$652C` 표 조회), 두 바이트 코드(리드 `$E0`↑)는 BIOS 글꼴로 가서 한글이 깨진다.
우리 후킹의 ASCII 이음매(`hook.py` `ascii`)에 **리드 `FA`** 를 얹는다 — 둘째 바이트 = `TRAIL0 + 번호` → 패키지 안 도안 표(`TABLE_OFF`, 16B 간격·앞 12B = 8×12 행 비트, 왼쪽이 MSB)에서 읽어 `$309B` 에 채운다.
전진 8px 은 원판 처리기가 그대로 한다(두 바이트도 `06` 모드면 `$67E6` → `$6432`). 도안 = `shared/fonts` 의 Galmuri11-Condensed(7×11, 전진 8).
쓰는 줄 = `data/ctrl_lines.tsv` 에서 틀이 `⟦` 로 시작하는 것(그 틀의 글자는 전부 이 부호로 낸다).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common

LEAD = 0xFA  # 글리프 리드 F0~F8 · 조사 F9 다음 — 비어 있다
TRAIL0 = 0x24
REL = 258  # 디버그 마을 패키지
TABLE_OFF = 0x2000  # 패키지 안(앞 덩이 · 지역 글리프 표 사이의 0xFF 채움) — 뱅크 경계라 창 `$8000` + 번호×16
STRIDE = 16
# 배틀 테스트 마을(패키지 2050·2178·2306·2434 = 장면 16~19)도 같은 좁은 목록을 쓴다(마스터 11-22 「전투시험에서 깨짐」) — 도안 표 사본을 각 패키지의
# 0xFF 꼬리에 둔다. 그 마을의 글자(`BT_MEMO`)를 **앞 번호**로 매겨 사본은 앞 `bt_count()` 개만 담는다. 장면 번호(`$26F3`)로 표 위치를 고른다.
BT_MEMO = "배틀 테스트"
BT_LOC = {16: 0x6900, 17: 0x6800, 18: 0x5100, 19: 0x5400}  # 장면 → 패키지 안 표 위치(`뱅크 경계 안`, 256B 정렬)
SCENE_MAIN = 2  # 디버그 마을
MARK = "⟦"
_TSV = common.GAME_DIR / "data" / "ctrl_lines.tsv"
_chars: list[str] | None = None
_bt_n = 0


def chars() -> list[str]:
    """좁은 글꼴로 내는 한글(코드포인트순) — 번호가 이 순서다."""
    global _chars
    if _chars is None:
        s, bt = set(), set()
        for ln in _TSV.read_text(encoding="utf-8").splitlines():
            f = ln.split("\t")
            if len(f) >= 2 and f[1].startswith(MARK):
                cs = set(re.findall(r"[가-힣]", f[1]))
                s |= cs
                if len(f) >= 3 and BT_MEMO in f[2]:
                    bt |= cs
        _chars = sorted(bt) + sorted(s - bt)
        global _bt_n
        _bt_n = len(bt)
        assert len(_chars) < 200, "좁은 한글 번호가 한 리드(200)를 넘는다"
    return _chars


def enc(text: str) -> bytes:
    cs = {c: i for i, c in enumerate(chars())}
    out = bytearray()
    for ch in text:
        if ch == "\n":
            out.append(0x0D)  # 줄바꿈(원판 제어)
        elif ch == " ":
            out.append(0x60)  # 공백 4px
        elif ch.isascii() and (ch.isdigit() or ch.isupper()):  # ASCII 대문자·숫자 한 바이트(8px). 소문자(0x60~)는 `06` 모드에서 가나 도안으로 읽혀 깨진다(「Uty」 → 「Iボボ」, 11-23 실측) — 소문자는 아래 전각 통과  # ASCII 숫자 한 바이트 — 배틀 테스트 마을 격자 줄은 메시지 길이가 255B 를 넘으면 엔진이 깨진 글을 읽는다(「長い!」, 마스터 11-22). 원판도 ASCII 숫자
            out.append(ord(ch))
        elif ch == "　":
            out += b"\x60\x60\x60"
        elif ch in cs:
            out += bytes([LEAD, TRAIL0 + cs[ch]])
        elif ch in "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ":  # 원판 전각 숫자·라틴 — `06` 모드에서 원판이 그리던 두 바이트 그대로(「ＥＦ０１」 목록과 같다)
            out += ch.encode("cp932")
        else:
            raise KeyError(f"좁은 글꼴에 없는 글자 {ch!r}")
    return bytes(out)


def rows(ch: str) -> bytes:
    import fonts

    f = fonts.galmuri("Galmuri11-Condensed")
    b = f.bits(ch, dx=0, dy=-3, rows=12, width=8)
    return bytes(int("".join(str(int(x)) for x in r), 2) for r in b)


def bt_count() -> int:
    chars()
    return _bt_n


def bt_table() -> bytes:
    """배틀 테스트 마을용 도안 표 — 앞 `bt_count()` 글자(번호 0부터)만."""
    return table()[: bt_count() * STRIDE]


def table() -> bytes:
    out = bytearray()
    for ch in chars():
        g = rows(ch)
        assert len(g) == 12
        out += g + bytes(STRIDE - 12)
    return bytes(out)
