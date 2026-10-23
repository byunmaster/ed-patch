"""긴 대사 줄 이어 풀기 — 한 줄(`00` 까지)을 풀어 담는 작업 버퍼(`$30E5`~`$31E5`, 256B)가 넘치면 엔진은 원판이 박아 둔 「長い！」 문구를 대신 찍는다
(`$7F20` → `$5036`, 실측 10-19 전수 촬영: 화면에 일본어 「長い！」 + 깨진 글). 원문 일본어는 반각 가나라 한 줄이 253B 안이었지만 한글은 2바이트라 번역 45줄이 255B 를 넘었다.

해법(마스터 방침 「칸 문제는 기술 먼저」): **쪽 끝에서 풀기를 끊고, 그리기를 마친 뒤 이어 푼다.**
 ① 쪽 끝 제어(`13` — 버퍼엔 `12` 로 들어간다) 처리 `$7E72` 를 우리 루틴으로 — 쪽을 하나 넣은 뒤 버퍼가 `$3178` 이상 찼으면(한 쪽은 최대 102B 라 다음 쪽이 안 넘친다)
    풀기를 `00` 으로 닫고 곧바로 돌아간다(`$AF` 복원 · 원본 `00` 처리와 같은 모양). 이어 풀 자리(MPR4 뱅크)를 기억한다.
 ② 메시지 보여 주기 핸들러(`$454C`)의 꼬리 `JMP $4F0F`(그리기) 를 우리 루틴으로 — 그리고 나서 「이어 풀기」 표시가 있으면 버퍼를 비우고 MPR4/5 를 되돌려 `$7DD4`(초기화 없이 풀기 루프 재진입)로 이어 푼 뒤 다시 그린다.
    (그리기 루틴 `$4F0F` 는 기다리는 동안 다른 슬롯을 돌려 MPR4/5 를 바꾸므로 되돌린다.)
 ③ 한도 검사 모드(`$7F1D`=FF — `$7DCA` 입구, 호출부는 `$654C`(`A3`)·`$6587`(`A1`) 둘뿐이고 둘 다 꼬리를 이어 풀기로 바꿨다)에서만 끊는다 — 한도 없는 입구(`$7DCD`)의 호출부는 그대로.
⚠ 쪽을 끊어도 같은 창에 이어 그려진다(쪽 끝 `12` 는 키 대기 뒤 쪽을 지우고 새 쪽을 시작하므로 이음매가 안 보인다 — 실화면 확인).
자리: 뱅크 0x6E(마운트 `$6000`)의 0xFF 패딩 머리 `+0x1F3C`(196B 중 약 127B).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout

BANK = 0x6E
CODE_OFF = 0x1F3C
ORG = 0x6000 + CODE_OFF
SEAM_13 = 0x1E72  # `$7E72: INC $7E4F` (3B) → `JMP 우리 13 처리`
SEAM_13_OLD = bytes.fromhex("ee4f7e")
SEAM_TAIL = 0x0563  # 핸들러 `$654C`(`A3`)의 꼬리 `$6563: JMP $4F0F` (3B) → `JMP 우리 꼬리`
SEAM_TAIL_OLD = bytes.fromhex("4c0f4f")
SEAM_TAIL2 = 0x05B1  # 루틴 `$6587`(`A1`)의 `$65B1: JSR $4F18`(그리기, 3B) → `JSR 우리 꼬리2`
SEAM_TAIL2_OLD = bytes.fromhex("20184f")
FLUSH_HI, FLUSH_LO = 0x31, 0x78  # 버퍼 포인터가 이 값(`$3178`) 이상이면 쪽 끝에서 끊는다 — 한 쪽 최대 102B + 여유


class _A:
    """미니 어셈블러(라벨 · 상대 분기)."""

    def __init__(self, org: int):
        self.org = org
        self.out = bytearray()
        self.labels: dict[str, int] = {}
        self.fix: list[tuple[int, str, str]] = []

    def pc(self) -> int:
        return self.org + len(self.out)

    def label(self, n: str) -> None:
        self.labels[n] = self.pc()

    def b(self, *xs: int) -> None:
        self.out += bytes(xs)

    def abs_(self, op: int, tgt) -> None:
        self.out.append(op)
        self.fix.append((len(self.out), "abs", tgt))
        self.out += b"\0\0"

    def rel(self, op: int, tgt: str) -> None:
        self.out.append(op)
        self.fix.append((len(self.out), "rel", tgt))
        self.out.append(0)

    def done(self) -> bytes:
        for at, kind, tgt in self.fix:
            t = self.labels[tgt] if isinstance(tgt, str) else tgt
            if kind == "abs":
                self.out[at : at + 2] = t.to_bytes(2, "little")
            else:
                d = t - (self.org + at + 1)
                assert -128 <= d <= 127, (tgt, d)
                self.out[at] = d & 0xFF
        return bytes(self.out)


def _routine() -> _A:
    a = _A(ORG)
    # ① 쪽 끝 제어 `13` — 원본(`INC $7E4F; LDA #$12; JMP $7DE4`)과 같이 `12` 를 넣고, 가득 찼으면 풀기를 닫고 돌아간다.
    #    끊는 조건: 한도 검사 모드(`$7F1D`=FF — `$7DCA` 입구, 호출부는 `$654C`(`A3`)·`$6587`(`A1`) 둘뿐이고 둘 다 꼬리를 이어 풀기로 바꿨다 —
    #    한도 없는 입구 `$7DCD` 의 호출부는 그대로) · 포인터가 `$3178` 이상 · 끼워 넣은 문자열(`1F`) 안이 아닐 때.
    #    (쪽 끝만 보면 된다 — 전수 모의: 번역 2,945줄 어느 것도 이 규칙으로 풀면 버퍼가 251B 를 안 넘는다)
    a.label("h13")
    a.b(0xEE, 0x4F, 0x7E)  # INC $7E4F
    a.b(0xA9, 0x12)  # LDA #$12
    a.abs_(0x20, 0x7F13)  # JSR $7F13 (버퍼에 쓰기)
    a.abs_(0xAD, 0x7F1D)  # LDA $7F1D
    a.rel(0xF0, "cont")  # BEQ cont
    a.b(0xA5, 0x7E, 0xC9, FLUSH_LO, 0xA5, 0x7F, 0xE9, FLUSH_HI)  # 포인터 >= $3178 ?
    a.rel(0x90, "cont")  # BCC cont
    a.abs_(0xAD, 0x7EFA)  # LDA $7EFA
    a.rel(0xD0, "cont")  # BNE cont
    a.b(0x43, 0x10)  # TMA #$10 — 이어 풀 자리(MPR4 뱅크)를 기억
    a.abs_(0x8D, "SAVE")
    a.b(0xA9, 0x01)
    a.abs_(0x8D, "CONT")  # 「이어 풀기」 표시
    a.b(0x68, 0x85, 0xAF)  # PLA; STA $AF  (원본 `00` 처리 `$7E3A` 와 같은 모양)
    a.b(0x62, 0x92, 0x7E)  # CLA; STA ($7E)
    a.b(0x60)  # RTS
    a.label("cont")
    a.abs_(0x4C, 0x7DDA)  # JMP $7DDA
    # 이어 풀기 — 버퍼·그리기 포인터를 비우고 MPR4/5 를 되돌려, 원본 `$7DD4`(`$AF` 를 쌓고 `$7EFA` 를 0 으로)와 같은 머리로 루프(`$7DDA`)에 재진입
    a.label("resume")
    a.abs_(0x9C, "CONT")
    a.b(0xA9, 0xE5, 0x85, 0x7E, 0x85, 0x7C, 0xA9, 0x30, 0x85, 0x7F, 0x85, 0x7D)
    a.abs_(0xAD, "SAVE")
    a.b(0x53, 0x10, 0x1A, 0x53, 0x20)  # TAM #$10; INC; TAM #$20 (그리기가 기다리는 동안 다른 슬롯이 MPR4/5 를 바꾼다)
    a.b(0xA5, 0xAF, 0x48)  # LDA $AF; PHA
    a.abs_(0x9C, 0x7EFA)  # STZ $7EFA
    a.abs_(0x4C, 0x7DDA)  # JMP $7DDA
    # ② 꼬리 — 핸들러 `A3`(`$654C`): 그리고, 이어 풀 게 남았으면 풀고 다시 그린다
    a.label("tail")
    a.b(0xA0, 0x01)  # LDY #1
    a.abs_(0x20, 0x4F0F)  # JSR $4F0F
    a.abs_(0xAD, "CONT")
    a.rel(0xF0, "end")
    a.b(0xB7, 0x84)  # SMB3 $84
    a.abs_(0x20, "resume")
    a.rel(0x80, "tail")
    a.label("end")
    a.b(0x60)
    # ②' 꼬리2 — 루틴 `A1`(`$6587`): `JSR $4F18` 자리. 그리기 입구의 A·Y 를 기억해 두었다 같은 값으로 다시 부른다
    a.label("tail2")
    a.abs_(0x8D, "TA")
    a.abs_(0x8C, "TY")
    a.label("t2")
    a.abs_(0xAD, "TA")
    a.abs_(0xAC, "TY")
    a.abs_(0x20, 0x4F18)  # JSR $4F18
    a.abs_(0xAD, "CONT")
    a.rel(0xF0, "end")
    a.abs_(0x20, "resume")
    a.rel(0x80, "t2")
    for n in ("CONT", "SAVE", "TA", "TY"):
        a.label(n)
        a.b(0)
    return a


def code() -> bytes:
    return _routine().done()


def labels() -> dict[str, int]:
    return _routine().labels


def reserve(prog: layout.Prog) -> int:
    n = len(code())
    prog.reserve(BANK, CODE_OFF, n)
    return n


def install(prog: layout.Prog) -> None:
    a = _routine()
    b = a.done()
    assert prog.o(BANK, SEAM_13, 3) == SEAM_13_OLD, "긴 줄 이음매(쪽 끝 제어) 원본 바이트가 다르다"
    assert prog.o(BANK, SEAM_TAIL, 3) == SEAM_TAIL_OLD, "긴 줄 이음매(그리기 꼬리) 원본 바이트가 다르다"
    assert prog.o(BANK, SEAM_TAIL2, 3) == SEAM_TAIL2_OLD, "긴 줄 이음매(그리기 꼬리2) 원본 바이트가 다르다"
    prog.put(BANK, CODE_OFF, b, "longline routine")
    L = a.labels
    prog.put(BANK, SEAM_13, bytes([0x4C]) + L["h13"].to_bytes(2, "little"), "longline seam 13 $7E72")
    prog.put(BANK, SEAM_TAIL, bytes([0x4C]) + L["tail"].to_bytes(2, "little"), "longline seam tail $6563")
    prog.put(BANK, SEAM_TAIL2, bytes([0x20]) + L["tail2"].to_bytes(2, "little"), "longline seam tail2 $65B1")
