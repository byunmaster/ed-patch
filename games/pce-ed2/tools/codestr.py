"""장면 패키지 코드 영역에 박힌 일본어 문장 — 메시지 표 밖이라 번역 단위 목록도 잔존 게이트도 못 봤던 자리(10-18 재검수에서 발견).

모양: `JSR $403C` + `BIT $6xxx`(인라인 포인터 — 오퍼랜드 = 문자열 주소, 베이스 `$6000` = 패키지 파일 오프셋) 가 가리키는 SJIS 문자열(`00` 끝).
원문 자리에는 한국어가 안 들어가는 것이 있어(글자당 2바이트로 같지만 조사·공백이 는다) **0xFF 패딩으로 옮기고 포인터만 바꾼다**(줄이지 않는다 — 마스터 「칸 문제는 기술 먼저」).
원문 바이트는 데이터에 두지 않는다 — 문자열 바이트의 sha1(12자)로 대조한다(저작권 규칙).
제어: `13 89` = 이름 토큰(대상) · `1B` = 수 · `06 81 40 04` = 원문 그대로(숫자 자리 스타일).
"""

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon
import font


@dataclass(frozen=True)
class Spec:
    rel: int
    ptr: int  # `BIT` 오퍼랜드(2바이트)의 패키지 파일 오프셋
    old: int  # 원문 문자열 시작 오프셋 (= 포인터가 가리키던 곳)
    n: int  # 원문 문자열 길이(끝 `00` 포함)
    sha: str  # 원문 문자열 바이트 sha1 앞 12자
    free: int  # 옮겨 쓸 0xFF 패딩의 시작 오프셋
    parts: tuple  # str(한국어 글) 또는 bytes(제어 원문)


@dataclass(frozen=True)
class C:
    """정본 조각 — `canon.lookup(key, "battle", "ed2")` 에서 읽고 `{name}`(대상 이름 토큰은 따로 붙인다)·`{n}`(수 토큰)을 자리표로 푼다. `cut` = 끝에서 뗄 글(원문이 부호가 없을 때)."""

    key: str
    cut: str = ""

    def resolve(self) -> list:
        kr = canon.lookup(self.key, "battle", "ed2")
        if kr is None:
            raise ValueError(f"정본에 없다: {self.key!r}")
        if self.cut and kr.endswith(self.cut):
            kr = kr[: -len(self.cut)]
        out: list = []
        for i, piece in enumerate(kr.replace("{name}", "\x00").split("{n}")):
            if i:
                out.append(NUM)
            if piece:
                out.append(piece.replace("\x00", ""))
        return out


NAME = b"\x13\x89"
NUM = b"\x1b"
STYLE = b"\x06\x81\x40\x04"
END = b"\x0d\x00"
SPECS = (
    # 「防御力が▢ ▢さがった」 — 장면 코드의 능력치 감소 문구(386·514·1026 에 같은 코드)
    Spec(386, 0x8D, 0x90, 23, "b9a5afb4d8a1", 0xBF, ("방어력이", STYLE, NUM, " 내려갔다.", END)),
    Spec(514, 0x20C, 0x20F, 23, "b9a5afb4d8a1", 0x23E, ("방어력이", STYLE, NUM, " 내려갔다.", END)),
    Spec(1026, 0xFC, 0xFF, 23, "b9a5afb4d8a1", 0x12E, ("방어력이", STYLE, NUM, " 내려갔다.", END)),
    # 「{이름}が共鳴している」 — 정본에 없는 문장(후보)
    Spec(514, 0xCC, 0x135, 18, "4ecdd74481b6", 0x262, (NAME, "이(가) 공명하고 있다.", END)),
    # 최종 보스: 연속 공격 뒤 합계 피해 — 「{이름}に合計{n}のダメージ」 · 「{이름}に{n}のダメージ｜」(정본 「에게 {n}의 피해!!」)
    # 정본 조각 조합: 「{name}에게 합계」 + 「{n}의 피해」(끝 부호는 원문대로 — 첫 문장은 없고 둘째는 !!)
    Spec(2690, 0xD9, 0xDC, 21, "6a9872a10a4f", 0x1D0, (NAME, C("{name}に合計"), " ", C("{n}のダメージ!!", "!!"), END)),
    Spec(2690, 0x155, 0x158, 19, "fc1904e82227", 0x1E6, (NAME, C("に{n}のダメージ。"), END)),
)
BASE = 0x6000


def chars_by_pkg() -> dict[int, set[str]]:
    """패키지별로 이 문장들이 쓰는 한글 — 글리프 풀 선택이 미리 알아야 한다."""
    out: dict[int, set[str]] = {}
    for sp in SPECS:
        for p in _flat(sp):
            if isinstance(p, str):
                out.setdefault(sp.rel, set()).update(c for c in font.mark_josa(p) if "가" <= c <= "힣")
    return out


def _flat(sp: Spec) -> list:
    out: list = []
    for p in sp.parts:
        out.extend(p.resolve() if isinstance(p, C) else [p])
    return out


def _bytes(sp: Spec, tab) -> bytes:
    return b"".join(tab.enc(p) if isinstance(p, str) else p for p in _flat(sp))


def apply(rel: int, pkg: bytes, new: bytearray, tab) -> None:
    """`new`(재배치한 패키지 바이트)의 코드 영역에 한국어 문자열을 쓰고 포인터를 돌린다. 원문 바이트가 다르거나 자리가 모자라면 오류."""
    used: dict[int, int] = {}
    for sp in SPECS:
        if sp.rel != rel:
            continue
        old = pkg[sp.old : sp.old + sp.n]
        if hashlib.sha1(old).hexdigest()[:12] != sp.sha or old[-1] != 0:
            raise ValueError(f"패키지 {rel}: 코드 문자열 {sp.old:#x} 가 기대한 원문이 아니다")
        if pkg[sp.ptr - 4 : sp.ptr] != b"\x20\x3c\x40\x2c" or (pkg[sp.ptr] | pkg[sp.ptr + 1] << 8) != BASE + sp.old:
            raise ValueError(f"패키지 {rel}: {sp.ptr:#x} 가 JSR $403C · BIT 포인터 꼴이 아니다")
        kr = _bytes(sp, tab)
        at = sp.free
        if any(b != 0xFF for b in pkg[at : at + len(kr)]) or at + len(kr) > sp.free + 0x100:
            raise ValueError(f"패키지 {rel}: 0xFF 패딩 {at:#x}+{len(kr)} 가 비어 있지 않다")
        if used.get(at):
            raise ValueError("자리 겹침")
        used[at] = len(kr)
        new[at : at + len(kr)] = kr
        ptr = BASE + at
        new[sp.ptr], new[sp.ptr + 1] = ptr & 0xFF, ptr >> 8
        new[sp.old : sp.old + sp.n] = b"\xff" * sp.n  # 옛 문자열은 `RTS` 뒤 자료라 실행되지 않는다 — 지워 둔다(잔존 게이트가 일본어 바이트로 본다)
