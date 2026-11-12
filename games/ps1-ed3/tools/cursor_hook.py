"""커서 줄(글자 명령 종류 4)에 **반각 합성**을 거는 훅 — `docs/cursor-line-halfwidth.md` §3·§6. 기본 빌드에 들어간다(마스터 10-10 「당연히 빌드에도 포함」, 종전 `ED_CURSOR_HW=1` 시험 손잡이는 걷었다).

`0x8001A7E8`(커서가 놓인 줄을 타일로 만든다)이 글자 코드 배열(`fp+0x28`, 열 수만큼)을 채운 직후(`0x8001A9C8`)에 이 훅을 부른다. 훅은 그 줄의 **합성 타일**
(반 칸 글자는 6px, 나머지 12px — `tile_hook` 의 24비트 시프트와 같은 계산)을 임시 버퍼에 만들고, 코드 배열을 **음수 가상 코드**로 덮는다.
`0x80018574` 의 글리프 주소 계산(`FONT + 코드×18`)이 **부호 있는 16비트**라 가상 코드가 임시 버퍼를 가리키고, 그 뒤 4bpp 확장·커서 테두리 입히기는 원판 그대로다.

🔴 **목록 창 반각 공백(마스터 11-09 「띄어쓰기는 반각이어야해」)** — 상점·도구·장비 목록(열 8~11)은 줄을 이 훅의 두 자리(`0x8001A9C8` 커서 줄 · `0x8001B214` 글자+숫자 줄)로 그려서
이름 속 공백(12px 칸)만 반 칸으로 합성한다(다른 반 칸 글자는 전각 그대로). 같은 창의 빨간 줄(살 수 없는 항목)은 일반 글자 줄이라 `tile_hook.msg_stub` 의 목록 갈래가 맡는다.
자리는 R1(`hookc`·`hookl`·`lst`/`deny`)·자료 꼬리(`allow` 앞 판정)로 나눠 넣었다 — `allow_words`.

코드는 정적(참조 0)·동적(범위 BP 0회)으로 죽었다고 검증한 `0x8008A108~0x8008A2B3`(428B)에 두고, 공용 서브루틴 `or24` 는 `0x8008A428~`(368B)에 둔다.
임시 버퍼는 자료 자리 안(`PATCH["data"]` + `BUF_OFF`) — `FONT − 18·m` 이 되도록 오프셋을 맞춘다(그래야 가상 코드가 정수).
"""

import engine_patch as E
import tile_hook as H

R1 = 0x8008A108  # 훅 본체(428B)
R1_LEN = 428
R2 = 0x8008A428  # 서브루틴(368B)
R2_LEN = 368
STR_TAIL = R2 + 216  # R2 본체(212B) 뒤 빈 꼬리 — 세이브/로드 데이터 창 제목 문자열을 둔다(`engine_patch.apply_detail_titles`). 152B(76워드)
R2ROW = R2 + 60  # 서브루틴 row6 시작(or24 는 R2 맨 앞 15워드)
SITE = 0x8001A9C8  # 훅 자리: `lui v0,0x801f` · `lhu v0,0x76b8(v0)` 두 워드를 `jal 훅 · nop` 로
SITE_ORIG = (0x3C02801F, 0x944276B8)  # lui v0,0x801f · lhu v0,0x76b8(v0)
R1_SHA1 = "d591f9c731a2e08e2d60836628d44ae3c107b522"  # 원본 두 구간(참조 0·범위 BP 0회로 검증한 죽은 코드)
R2_SHA1 = "61c4151d7a3735245a7f571b2f4d1710cbece9db"
COLS_MAX = 14  # 임시 버퍼 한계(열 + 1 타일) — 14열 데이터 창(세이브/로드)까지(10-25)
FONT = 0x8009E170
PROTO_WINDOWS = ((6, 4), (14, 4))  # 시험 빌드에서 커서 반각을 켜는 목록 창(전투 square 6×4)


def buf_layout(disc):
    """(버퍼 주소, 가상 코드 시작) — 주소는 자료 자리 안, FONT − 18·m. 메시지 갈래(`tile_hook.msg_stub`) 바로 뒤에서 시작한다."""
    p = E.PATCH[disc]
    base = p["data"] + H.MSG_OFF + 4 * H.msg_len(disc)
    while (FONT - base) % 18:
        base += 1
    v0 = (base - FONT) // 18
    assert -0x8000 <= v0 < 0, v0
    return base, v0


def p_end(disc):
    p = E.PATCH[disc]
    return p["data"] + p["data_len"]


def allow_addr(disc):
    """허용 판정 서브루틴 `allow` 자리 — 임시 버퍼(열 14 + 1 타일) 바로 뒤, 자료 자리 꼬리."""
    base, _ = buf_layout(disc)
    return (base + (COLS_MAX + 1) * 18 + 3) & ~3


LIST_COLS = (8, 11)  # 목록·이름 창 열 8~11(상점 구매·판매 · 도구 · 장비 · 소지품 고르기 · 전투 마법·도구) — 이 창은 공백만 반 칸(마스터 11-09 「띄어쓰기는 반각」)


def allow_words(disc, b_addr):
    """([A 워드], A 주소, [B 워드]) — 허용 판정 서브루틴 `allow`: 입력 t0 = 창 · 출력 v0 = 1 허용/0 아님 · t1 = 열 · s0 = 1 이면 **목록 창**(공백만 반 칸).
    허용 규칙은 종전 인라인 판정(`PROTO_WINDOWS` · `tile_hook.MSG_GENERIC` · `MSG_Y`)과 같고(열은 버퍼 한계 `COLS_MAX` 로 자른다), 마지막에 목록 창(열 8~11)을 더한다 —
    앞 규칙이 이긴다(전투 안 10×3 등은 종전 그대로). 자리가 모자라 둘로 나눈다: A(앞 판정 22워드)는 자료 자리 꼬리, B(목록·거부 8워드)는 R1 뒤 빈 곳 `b_addr`."""
    (r0, r1), (c0, c1) = H.MSG_GENERIC
    c1 = min(c1, COLS_MAX)
    prows = {r for _c, r in PROTO_WINDOWS}
    assert len(prows) == 1 and len(PROTO_WINDOWS) == 2, "허용 창 목록이 한 행 수 · 둘로 묶여야 압축 판정이 맞다"
    pr = prows.pop()
    (pc0, _), (pc1, _) = PROTO_WINDOWS
    tail = allow_addr(disc)
    lst = b_addr
    deny = b_addr + 4 * 6
    a_src = f"""
    allow:
      lhu   t1, 6(t0)
      lhu   t2, 8(t0)
      lh    t4, 4(t0)                       # 창 y(화면 가운데 기준)
      li    t3, {pr}
      bne   t2, t3, gen
      li    t3, {pc0}                       # (지연 슬롯)
      beq   t1, t3, yes
      li    t3, {pc1}                       # (지연 슬롯)
      beq   t1, t3, yes
      nop
    gen:
      addiu t3, t2, -{r0}
      sltiu t3, t3, {r1 - r0 + 1}
      beq   t3, zero, {lst:#x}
      addiu t3, t1, -{c0}                   # (지연 슬롯)
      sltiu t3, t3, {c1 - c0 + 1}
      beq   t3, zero, {lst:#x}
      addiu t3, t4, {-H.MSG_Y[0]}           # (지연 슬롯)
      sltiu t3, t3, {H.MSG_Y[1] - H.MSG_Y[0] + 1}
      beq   t3, zero, {lst:#x}
      nop
    yes:
      jr    ra
      li    v0, 1                           # (지연 슬롯)
"""
    b_src = f"""
    lst:
      addiu t3, t1, -{LIST_COLS[0]}
      sltiu t3, t3, {LIST_COLS[1] - LIST_COLS[0] + 1}
      beq   t3, zero, deny
      li    s0, 1                           # (지연 슬롯) 목록 창 — 공백만 반 칸
      jr    ra
      li    v0, 1                           # (지연 슬롯)
    deny:
      jr    ra
      move  v0, zero                        # (지연 슬롯)
"""
    aw, _ = E.asm(a_src, tail)
    bw, bl = E.asm(b_src, b_addr)
    assert bl["lst"] == lst and bl["deny"] == deny
    E.verify(aw, tail)
    E.verify(bw, b_addr)
    return list(aw), tail, list(bw)


def hook_words(disc, space):
    """([워드], 라벨) — 훅 본체 + (서브루틴 주소는 `R2`)."""
    p = E.PATCH[disc]
    S = H.data_base(p)
    atb, v0 = buf_layout(disc)
    font_hi, font_lo = FONT >> 16, FONT & 0xFFFF
    if font_lo >= 0x8000:
        font_hi += 1
        font_lo -= 0x10000
    src = f"""
    hookl:                                  # 목록 줄 훅 자리(`0x8001AF98` — 글자 줄 + 숫자 칸): 배열 fp+0x30 · 칸 수 fp+0x26 · 창 전부 허용(공백만 반 칸)
      addiu sp, sp, -16
      sw    ra, 0(sp)
      sw    s0, 4(sp)
      li    gp, 0x30                        # 코드 배열 위치(fp+gp)
      lh    t1, 0x26(fp)
      li    s0, 1                           # 목록 모드 — 공백만 반 칸
      sltiu t3, t1, {COLS_MAX + 1}
      beq   t3, zero, done                  # 칸 수가 버퍼 한계를 넘으면 원판 그대로
      nop
      beq   t1, zero, done
      nop
    hbody:
      lui   t9, {S >> 16:#x}
      ori   t9, t9, {S & 0xFFFF:#x}
      sll   t3, t1, 4                       # 버퍼 0 으로 — (열+1)×18 바이트
      sll   t4, t1, 1
      addu  t3, t3, t4
      addiu t3, t3, 21
      srl   t3, t3, 2
      lui   t4, {atb >> 16:#x}
      ori   t4, t4, {atb & 0xFFFF:#x}
    zl:
      sw    zero, 0(t4)
      addiu t3, t3, -1
      bne   t3, zero, zl
      addiu t4, t4, 4
      move  t5, zero                        # 위치(px)
      move  t6, zero                        # 칸
    cl:
      sll   t7, t6, 1
      addu  t7, t7, fp
      addu  t7, t7, gp
      lhu   t0, 0(t7)                       # 글자 코드(커서 줄 배열은 fp+0x28: 원본이 fp+0x10 에 0x18 을 더해 읽는다 · 목록 줄은 fp+0x30)
      li    t2, 12
      bne   s0, zero, hs
      addiu t3, t9, {H.OFF_HALF}            # (지연 슬롯)
    hl:
      lhu   t4, 0(t3)
      nop
      beq   t4, zero, hd
      nop
      bne   t4, t0, hl
      addiu t3, t3, 2
      j     hd
      li    t2, 6                           # (지연 슬롯) 반 칸 글자
    hs:
      li    t3, {space}                     # 목록 창 — 공백만
      bne   t0, t3, hd
      nop
      li    t2, 6
    hd:
      sll   t3, t0, 4
      sll   t4, t0, 1
      addu  t3, t3, t4
      lui   t4, {font_hi:#x}
      addiu t4, t4, {font_lo}
      addu  t3, t3, t4                      # 글리프 18B
      li    t4, 12
      div   zero, t5, t4
      mflo  a0                              # 타일 번호
      mfhi  a1                              # 타일 안 위치(0·6)
      sll   a2, a0, 4
      sll   v0, a0, 1
      addu  a2, a2, v0
      lui   v0, {atb >> 16:#x}
      ori   v0, v0, {atb & 0xFFFF:#x}
      addu  a2, a2, v0                      # 이 타일
      addiu a3, a2, 18                      # 다음 타일(스필)
      jal   {R2ROW:#x}                      # 두 행 묶음 6번 — 서브루틴(R2)
      nop
      addu  t5, t5, t2
      addiu t6, t6, 1
      bne   t6, t1, cl
      nop
      addiu t3, zero, {v0}                  # 코드 배열 → 가상 코드(음수)
      addu  t4, fp, gp
      move  t5, t1
    rw:
      sh    t3, 0(t4)
      addiu t3, t3, 1
      addiu t5, t5, -1
      bne   t5, zero, rw
      addiu t4, t4, 2                       # (지연 슬롯)
    done:
      lw    ra, 0(sp)
      lw    s0, 4(sp)
      move  gp, zero
      addiu sp, sp, 16
      lui   v0, 0x801f
      lhu   v0, 0x76b8(v0)
      jr    ra
      nop
    hookc:                                  # 커서 줄 훅 자리(`0x8001A9C8`): 배열 fp+0x28 · 칸 수 = 창 열 · 허용 창만
      addiu sp, sp, -16
      sw    ra, 0(sp)
      sw    s0, 4(sp)
      li    gp, 0x28
      lw    t0, 0x78(fp)
      jal   {allow_addr(disc):#x}
      move  s0, zero                        # (지연 슬롯)
      beq   v0, zero, done
      nop
      j     hbody
      nop
"""
    return src


SITE_L = 0x8001B214  # 목록 줄(`0x8001AF98`) 훅 자리: 같은 두 워드 `lui v0,0x801f` · `lhu v0,0x76b8(v0)`


def build(disc, space=0xE5):
    """([R1 워드], [R2 워드], [사이트 워드 둘], 라벨, [allow 워드], allow 주소, [목록 사이트 워드 둘])"""
    src = hook_words(disc, space)
    w1, lab1 = E.asm(src, R1)
    E.verify(w1, R1)
    # 서브루틴 or24: dst=t7, val=t4 — 3바이트를 24비트로 읽어 OR 해 되쓴다. 쓰는 레지스터 v0·v1 만.
    sub = """
    or24:
      lbu   v0, 0(t7)
      lbu   v1, 1(t7)
      sll   v0, v0, 16
      sll   v1, v1, 8
      or    v0, v0, v1
      lbu   v1, 2(t7)
      nop
      or    v0, v0, v1
      or    v0, v0, t4
      srl   v1, v0, 16
      sb    v1, 0(t7)
      srl   v1, v0, 8
      sb    v1, 1(t7)
      jr    ra
      sb    v0, 2(t7)
"""
    row6 = f"""
    row6:
      addiu sp, sp, -8
      sw    ra, 0(sp)
      li    t8, 6
    rl:
      lbu   t0, 0(t3)
      lbu   t4, 1(t3)
      lbu   v0, 2(t3)
      sll   t0, t0, 16
      sll   t4, t4, 8
      or    t0, t0, t4
      or    t0, t0, v0                      # 두 행 = 24비트
      beq   a1, zero, o0
      move  t4, t0                          # (지연 슬롯)
      srl   t4, t0, 6
      lui   v0, 0x3
      ori   v0, v0, 0xf03f
      and   t4, t4, v0                      # 왼쪽 타일 몫
    o0:
      move  t7, a2
      jal   {R2:#x}
      nop
      beq   a1, zero, nosp
      nop
      sll   t4, t0, 6
      lui   v0, 0xfc
      ori   v0, v0, 0xfc0
      and   t4, t4, v0                      # 넘친 조각
      move  t7, a3
      jal   {R2:#x}
      nop
    nosp:
      addiu a2, a2, 3
      addiu a3, a3, 3
      addiu t3, t3, 3
      addiu t8, t8, -1
      bne   t8, zero, rl
      nop
      lw    ra, 0(sp)
      addiu sp, sp, 8
      jr    ra
      nop
"""
    w2, lab2 = E.asm(sub, R2)
    w3, lab3 = E.asm(row6, R2 + 4 * len(w2))
    assert R2 + 4 * len(w2) == R2ROW, (hex(R2 + 4 * len(w2)), hex(R2ROW))
    w2 = w2 + w3
    E.verify(w2, R2)
    assert 4 * len(w2) <= R2_LEN
    assert 4 * len(w2) <= STR_TAIL - R2, f"R2 본체가 문자열 꼬리를 침범한다 ({4 * len(w2)}B)"
    site = [(3 << 26) | ((lab1["hookc"] >> 2) & 0x3FFFFFF), 0]
    site_l = [(3 << 26) | ((lab1["hookl"] >> 2) & 0x3FFFFFF), 0]
    b_addr = R1 + 4 * len(w1)
    aw, ab, bw = allow_words(disc, b_addr)
    assert ab + 4 * len(aw) <= p_end(disc), f"allow 가 자료 자리 끝을 넘는다 ({ab + 4 * len(aw):#x} > {p_end(disc):#x})"
    assert 4 * (len(w1) + len(bw)) <= R1_LEN, f"R1 이 구간을 넘는다 ({4 * (len(w1) + len(bw))}B > {R1_LEN}B)"
    return w1 + bw, w2, site, lab1, aw, ab, site_l


def apply(exe, disc, space=0xE5):
    """실행파일 bytearray 에 커서 줄 반각 훅을 넣는다(시험 빌드 전용). 사전조건(두 구간 sha1 · 훅 자리 원본 워드)이 안 맞으면 **쓰기 전에** 선다."""
    import hashlib
    import struct

    if disc != "ed3":
        return ""
    for what, a, n, sha in (("죽은 코드 1", R1, R1_LEN, R1_SHA1), ("죽은 코드 2", R2, R2_LEN, R2_SHA1)):
        o = E._off(a)
        got = hashlib.sha1(bytes(exe[o : o + n])).hexdigest()
        if got != sha:
            raise SystemExit(f"🔴 커서 훅 사전조건 — {what} {a:#x} sha1 이 다르다 ({got[:12]})")
    E._expect(exe, SITE, SITE_ORIG, "커서 줄 훅 자리")
    E._expect(exe, SITE_L, SITE_ORIG, "목록 줄 훅 자리")
    w1, w2, site, _lab, aw, ab, site_l = build(disc, space)
    struct.pack_into(f"<{len(w1)}I", exe, E._off(R1), *w1)
    struct.pack_into(f"<{len(w2)}I", exe, E._off(R2), *w2)
    struct.pack_into(f"<{len(aw)}I", exe, E._off(ab), *aw)
    struct.pack_into("<II", exe, E._off(SITE), *site)
    struct.pack_into("<II", exe, E._off(SITE_L), *site_l)
    return f" · 커서 줄 반각 훅({4 * len(w1)}B+{4 * len(w2)}B)"

