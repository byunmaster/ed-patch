"""패배 귀환 확인창 「(지명)의 입구로 돌아갑니다」 앞 전각 공백 걷기(마스터 11-18 「엘아스타 앞에 첫칸 전각으로 비어있는데 … 번역판은 빈칸 없게」).

문구는 `10 7D C0`(지명 버퍼 `$C07D` 를 이벤트 서브루틴으로 찍는다) + 인라인 글(뱅크 0x74 `$DE76`~)이다. 버퍼에는 HUD 가운데 맞춤용 **앞 반 칸 표시(`F8 24`) + 전각 공백(`81 40`) 몇 쌍**이
구워져 있어(11-05~11-08) 이 창에서 첫 칸이 비어 보였다. 공용 복사 루틴(`$9505`)·HUD 호출은 고치면 HUD 가 쏠리므로(list_strip 주석) **이 메시지 머리에서만**
버퍼를 제자리에서 걷는다 — `10 7D C0` 앞에 기계어 호출(`15 lo hi`)을 끼운다: 앞 `F8 24` · `81 40` 쌍을 건너뛰고 뒤 내용을 버퍼 맨 앞으로 당긴다(`06` 까지).
HUD 는 그릴 때마다 지명 표를 다시 복사하므로(`$6D+0x1294`) 걷어 둔 버퍼가 HUD 에 남지 않는다. 멱등(앞 공백이 없으면 제자리 복사).

루틴 자리: 뱅크 0x74 끝 FF(`freespace.BANK74_TAIL` 앞쪽 `CODE_LEN`B) — 이 뱅크는 늘 `$C000` 창에 걸려 있다(게임 변수·메시지가 거기 산다).
"""

import hook

BANK = 0x74
OFF = 0x1EA6
WINDOW = 0xC000
ADDR = WINDOW + OFF
CODE_LEN = 56  # code() 길이 이상(53B)
MSG_OFF = 0x1E76  # 메시지 머리(`10 7D C0` + 글) — 세 코드 자리가 이 주소를 가리킨다(옮기지 않는다)
HEAD_OLD = bytes.fromhex("107dc0" "82cc93")  # 머리 3B + 원문 「の入」 앞 3B (이 6B 를 아래로 바꾼다)
HEAD_NEW = bytes([0x15, ADDR & 0xFF, ADDR >> 8]) + bytes.fromhex("107dc0")  # `15 루틴` + 원래 `10 7D C0`
TEXT_SHIFT = 3  # 인라인 글 시작이 이만큼 뒤로(0x1E79 → 0x1E7C), 방 37B → 34B
BUF = 0xC07D


def code() -> bytes:
    a = hook.Asm(ADDR)
    a.op("PHA")
    a.op("PHX")
    a.op("PHY")
    a.op("LDY", "imm", 0)
    a.op("LDA", "absy", BUF)
    a.op("CMP", "imm", 0xF8)
    a.op("BNE", "rel", "s1")
    a.op("INY")
    a.op("INY")
    a.label("s1")
    a.op("LDA", "absy", BUF)
    a.op("CMP", "imm", 0x81)
    a.op("BNE", "rel", "s2")
    a.op("INY")
    a.op("LDA", "absy", BUF)
    a.op("CMP", "imm", 0x40)
    a.op("BEQ", "rel", "s3")
    a.op("DEY")
    a.op("BRA", "rel", "s2")
    a.label("s3")
    a.op("INY")
    a.op("BRA", "rel", "s1")
    a.label("s2")
    a.op("LDX", "imm", 0)
    a.label("c")
    a.op("LDA", "absy", BUF)
    a.op("STA", "absx", BUF)
    a.op("INX")
    a.op("INY")
    a.op("CMP", "imm", 0x06)
    a.op("BNE", "rel", "c")
    a.op("PLY")
    a.op("PLX")
    a.op("PLA")
    a.op("RTS")
    return a.bytes()


if __name__ == "__main__":
    c = code()
    print(len(c), c.hex(" "))
    assert len(c) <= CODE_LEN
