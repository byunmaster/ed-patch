"""ED1 입장 배너 띄움 꼴 — **핫픽스 시험 경로(`ED_HOTFIX=1`) 전용**(마스터 11-09 「입장배너도 가능하다면 띄어쓰기를 넣는게 좋을 것 같고」).

배경: ED1 월드맵 입장 배너(마을·동굴에 다가갈 때 뜨는 팝업)는 **HUD·워프와 같은 표**(ED.EXE 0xBE690, 14B×48)의 항목을 다른 그리기 함수
`0x800A6D1C` 가 그린다(그래서 「ED1 은 배너 없음」으로 오판했다 — devlog 11-09). 표가 같아 항목을 띄우면 HUD 도 띄워진다 → 배너만 띄울 길이 필요하다.

길(데이터 672B 를 둘 빈 자리가 없다 — 원판 0 구간은 전부 변수 영역이다): 함수 머리를 **동굴(코드 동굴)** 로 돌려, 표 항목에서
  ① 후행 틈 공백(HUD 접미 앞 공백)을 떼고 ② 항목 슬롯 **마지막 바이트(14B 중 13번째)** 에 적어 둔 위치에 반각 공백 하나를 끼운 사본을
스택 버퍼에 만들어 그 사본을 그리게 한다. 표 항목 자체는 그대로(HUD·워프는 붙임 + 후행 공백) — 슬롯 꼬리 한 바이트만 위치로 쓴다
(널 뒤라 문자열로는 안 읽힌다. 가장 긴 항목도 널이 12번째 이내).
  위치 0xFF = 끼우지 않음. 표 밖 포인터(`0x800CDE90..+672` 아님)는 원래대로 그린다.

동굴 자리: ED.EXE 0xA8D0 바로 앞의 0 꼬리(몬스터 이름 구획 재packing 뒤 남는 곳, 약 160~170B — 코드는 160B). 원판에선 JP 이름 글자였던 곳이고 가리키는 참조가 없다
(정적 확인 — `verify()`), 실행은 PS1 데이터 구획에서도 된다.
"""

import struct

BANNER_FN = 0x800A6D1C  # 창 + 가운데 글자(x = 0x380 + ((0x30 − 3·strlen) >> 1))
CAVE_END = 0xA8D0  # 몬스터 이름 구획 뒤 「ニージャ」 칸 시작 — 그 앞의 0 꼬리가 동굴(이름이 바뀌면 시작이 밀린다 → `cave_span` 이 매번 잰다)
TABLE_RAM, TABLE_N, STRIDE = 0x800CDE90, 48, 14
NONE = 0xFF


def _r(rs=0, rt=0, rd=0, sh=0, fn=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | fn


def addiu(rt, rs, imm):
    return 0x24000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def lui(rt, imm):
    return 0x3C000000 | (rt << 16) | (imm & 0xFFFF)


def lbu(rt, off, rs):
    return 0x90000000 | (rs << 21) | (rt << 16) | (off & 0xFFFF)


def sb(rt, off, rs):
    return 0xA0000000 | (rs << 21) | (rt << 16) | (off & 0xFFFF)


def sw(rt, off, rs):
    return 0xAC000000 | (rs << 21) | (rt << 16) | (off & 0xFFFF)


def move(rd, rs):
    return _r(rs=rs, rt=0, rd=rd, fn=0x21)  # addu rd, rs, $zero


def subu(rd, rs, rt):
    return _r(rs=rs, rt=rt, rd=rd, fn=0x23)


def sltiu(rt, rs, imm):
    return 0x2C000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def beq(rs, rt, off):
    return 0x10000000 | (rs << 21) | (rt << 16) | (off & 0xFFFF)


def bne(rs, rt, off):
    return 0x14000000 | (rs << 21) | (rt << 16) | (off & 0xFFFF)


def j(addr):
    return 0x08000000 | ((addr >> 2) & 0x3FFFFFF)


NOP = 0
SP, A0, S0, T0, T1, T2, T3, T4, T5 = 29, 4, 16, 8, 9, 10, 11, 12, 13


def cave_code():
    """동굴 기계어 [(워드)]. 분기 오프셋은 라벨로 계산한다."""
    code, labels, fix = [], {}, []

    def L(name):
        labels[name] = len(code)

    def br(op, rs, rt, name):
        fix.append((len(code), name))
        code.append((op, rs, rt))

    emit = code.append
    # 표 안인가: (a0 − 표 시작) < 672 (부호 없는 비교)
    emit(lui(T5, 0x800D))
    emit(addiu(T5, T5, -0x2170))  # 0x800CDE90
    emit(subu(T5, A0, T5))
    emit(sltiu(T5, T5, STRIDE * TABLE_N))
    br(bne, T5, 0, "intable")
    emit(NOP)
    # 표 밖 — 원래 함수 머리 그대로(s0 = a0)
    emit(sw(S0, 0x18, SP))
    emit(move(S0, A0))
    emit(j(BANNER_FN + 0xC))
    emit(NOP)
    L("intable")
    emit(sw(S0, 0x18, SP))
    emit(lbu(T0, 13, A0))  # 끼울 위치(0xFF = 없음)
    emit(addiu(T1, SP, 0x20))  # 사본 버퍼
    emit(move(S0, T1))  # 로드 지연 칸
    emit(move(T2, 0))
    emit(move(T4, A0))
    L("loop")
    br(bne, T2, T0, "cp")
    emit(NOP)
    emit(addiu(T3, 0, 0x20))  # 반각 공백 하나 끼움
    emit(sb(T3, 0, T1))
    emit(addiu(T1, T1, 1))
    emit(addiu(T0, 0, 0xFF))
    L("cp")
    emit(lbu(T3, 0, T4))
    emit(NOP)
    br(beq, T3, 0, "done")
    emit(NOP)
    emit(sb(T3, 0, T1))
    emit(addiu(T1, T1, 1))
    emit(addiu(T4, T4, 1))
    emit(addiu(T2, T2, 1))
    br(beq, 0, 0, "loop")
    emit(NOP)
    L("done")
    emit(lbu(T3, -1, T1))  # 후행 틈 공백을 뗀다
    emit(addiu(T5, 0, 0x20))
    br(bne, T3, T5, "term")
    emit(NOP)
    emit(addiu(T1, T1, -1))
    L("term")
    emit(sb(0, 0, T1))
    emit(j(BANNER_FN + 0xC))
    emit(NOP)
    out = list(code)
    for at, name in fix:
        op, rs, rt = out[at]
        out[at] = op(rs, rt, labels[name] - (at + 1))
    return out


def cave_span(ed):
    """(파일 오프셋, 길이) — 코드(160B)를 둘 **안전한 0 런**. 몬스터 이름 구획 뒤 0 꼬리(0xA8D0 앞)는 더 이상 안 쓴다.

    🔴 옛 자리는 전투·시스템 문구가 길어지면(원문 ました → 존댓말, 마스터 11-15) 꼬리가 160B 아래로 줄어 빌드가 멈췄다
    (136B < 160B) — 문안을 줄이지 않고 **코드 자리를 옮겼다**(2-17·마스터 10-07 「칸 문제는 기술 먼저」). 자리는 `patch_hang_punct.free_run`
    (VAB 헤더 패딩에서 `vab.safe_len` 으로 검증된 0 런, 오름차순 첫 자리 — 결정적)이 고른다. 조사 훅·매달기 스텁이 이미 같은 방식이다.
    """
    from patch_hang_punct import free_run

    n = len(cave_code()) * 4
    off, _avail = free_run(ed, (0x0BF5DC, 0x0C105C, 0x09AF74, 0x09C9F4), n)  # 조사 훅 고정 자리를 피한다
    return off, n


def _ram(file_off):
    return 0x80010000 + file_off - 0x800


def _off(ram):
    return ram - 0x80010000 + 0x800


def apply(ed, spaces):
    """ed: ED.EXE 바이트(수정). spaces: 표 순서의 [끼울 바이트 위치 또는 None] 48개."""
    assert len(spaces) == TABLE_N
    code = cave_code()
    cf, cl = cave_span(ed)
    assert not any(ed[cf : cf + cl]), "동굴 자리가 0 이 아니다"
    sites = (  # (RAM, 원래 워드, 새 워드)
        (BANNER_FN, 0x27BDFFE0, j(_ram(cf))),  # addiu sp,sp,-0x20 → 동굴로
        (BANNER_FN + 4, 0xAFB00018, addiu(SP, SP, -0x40)),  # (지연 칸) 프레임을 0x40 으로
        (0x800A6E80, 0x27BD0020, addiu(SP, SP, 0x40)),  # 끝의 addiu sp,sp,0x20
    )
    for ram, old, new in sites:
        o = _off(ram)
        assert struct.unpack_from("<I", ed, o)[0] == old, f"함수 머리 원본 불일치 @0x{ram:X}"
        struct.pack_into("<I", ed, o, new)
    ed[cf : cf + len(code) * 4] = b"".join(struct.pack("<I", w) for w in code)
    base = 0xBE690
    for i, p in enumerate(spaces):
        o = base + i * STRIDE
        assert ed[o + 13] == 0 and 0 in ed[o : o + 13], f"슬롯 꼬리가 비지 않았다 @0x{o:X}"
        ed[o + 13] = NONE if p is None else p
    return cf


def verify(ed, cf=None):
    """동굴을 디스어셈블해 눈으로 볼 수 있게 + 동굴 자리를 가리키는 참조가 없는지(정적)."""
    from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    n = len(cave_code()) * 4
    cf = cave_span(ed)[0] if cf is None else cf
    lines = [f"{i.address:08X} {i.mnemonic} {i.op_str}" for i in md.disasm(bytes(ed[cf : cf + n]), _ram(cf))]
    return lines


def cave_referenced(ed, cf=None):
    """원판 코드·표에서 동굴 구간(RAM)을 가리키는 `lui`+`addiu/ori/적재·저장` 쌍(가장 가까운 앞 lui 로 풂)·포인터 워드 수 — 0 이어야 한다."""
    cf = cave_span(ed)[0] if cf is None else cf
    cl = len(cave_code()) * 4
    lo, hi = _ram(cf), _ram(cf) + cl
    n = len(ed) // 4
    w = struct.unpack("<%dI" % n, bytes(ed[: n * 4]))
    inside = range(cf // 4, (cf + cl) // 4)
    hits = 0
    for i, x in enumerate(w):
        if lo <= x < hi and i not in inside:
            hits += 1
        op = x >> 26
        if op in (9, 13, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x28, 0x29, 0x2A, 0x2B, 0x2E):
            r = (x >> 21) & 31
            for k in range(i - 1, max(i - 8, -1), -1):
                y = w[k]
                if y >> 26 == 0x0F and ((y >> 16) & 31) == r:
                    imm = x & 0xFFFF
                    a = ((y & 0xFFFF) << 16) + (imm if op == 13 else (imm - 0x10000 if imm >= 0x8000 else imm))
                    if lo <= a < hi:
                        hits += 1
                    break
    return hits
