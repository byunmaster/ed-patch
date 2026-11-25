"""안 B 의 asm 훅(S3) — **반각을 스프라이트가 아니라 타일 비트맵 합성으로 한다.** 모델·근거는 `tilecomp.py`·`root-cause.md`.

글자 그리기 루프(`0x80018ACC` 에서 `jal`)가 글리프마다 이 훅을 부른다. 훅은
1. (조사 표지면) 직전 글자의 받침으로 실제 조사 글리프로 바꾼다(`josa_rt`),
2. 대사창(열 24)이면 **줄 안의 픽셀 위치**(`POS`)에 글리프를 합성한다 — 엔진이 쓸 타일(왼쪽)은 합성 18B(`OUTA`)로 소스를 돌려주고
   `fp+0x40/0x42`(rect x·y)를 그 타일 칸으로 고쳐 주며, 글자가 칸 경계를 걸치면 **오른쪽 타일**(`SPB`)은 훅이 직접
   전개표(`0x800A620C`)로 4bpp 로 펼쳐 `LoadImage(0x8008A8DC)` 한다(엔진 링 `fp+0x58+idx×84` 의 한 칸을 쓰고 `idx` 를 올린다),
3. 대사창이 아니면 원판 그대로(폰트 베이스).

🔴 스프라이트 x·w·h 는 **한 번도 안 건드린다** — 배경이 타일에 구워져 있어 칸을 움직이면 구멍·겹침·줄 끝 조각이 생기던 것(10-08)이
   구조적으로 사라진다. 상태는 전역 소량(POS 2B · 현재 타일 포인터 · 합성 버퍼 18B 둘)이고 `PATCH["data"]`(SDK 오류 함수 자리)에 둔다.

저장 규약: 글리프는 12행×12비트 **밀착 18B**(MSB 우선, 이웃 열 쌍이 뒤바뀐 채). 6px(=3쌍)씩 옮기는 것은 짝을 안 깨므로 저장 순서 그대로
비트를 밀면 화면에서 같은 만큼 옆으로 간다 — 3바이트(두 행)를 24비트 정수로 보고 **6비트 단위**(행 하나 = 두 단위)로 만진다.
"""

import engine_patch as E

# 상태 배치(S = PATCH["data"] 기준 오프셋)
OFF_POS, OFF_ZADV, OFF_CURP, OFF_IDX, OFF_LAST = 0, 2, 4, 10, 8  # CURP 는 4B(4~7)라 IDX 는 그 뒤
OFF_RA, OFF_V0, OFF_V1, OFF_A0, OFF_A2 = 12, 16, 20, 24, 28
OFF_OUTA, OFF_SPB = 32, 52  # 합성 버퍼 18B(+2)
OFF_HALF = 72  # 반 칸(6px) 글자 코드 u16 목록, 0 종결(최대 44칸 = 88B — 공백·괄호·부호 + 반각 ASCII(숫자·영문·&%'-) 마스터 10-12)
OFF_MK = 160  # 조사 표지 6 × 8B
OFF_LC, OFF_LIM = 208, 210  # 직전에 그린 글자의 열(메시지 창의 커서 점프를 알아챈다) · 줄 끝 판정 한계 px((열−1)×12)
OFF_BL = 212  # 받침표 u16 목록, 0 종결
HALF_SLOTS = 44
MSG_WINDOWS = ((10, 3, 0), (17, 1, 0), (6, 4, 0), (14, 4, 0), (20, 4, 0))  # 개별 목록 (열, 행, 줄 앞 밀기 px) — 10×3 퇴각 확인 · 17×1 「대열…」 메시지(`engine_patch.LINEUP_COLS`) · 6×4 전투 square **+ 시스템 설정 창**(둘 다 창 열 6 으로 줄인 뒤 — 커서 줄 반각 `cursor_hook` 과 같은 목록) · 14×4 세이브/로드 데이터 창(제목 가운데 정렬, 마스터 10-11) · 20×4 「…괜찮습니까?」 확인 창(물음표 반각). 🔴 시스템 설정 창이 7×4 일 땐 넣지 않았다(필드 메뉴 `0x80033CDC` 계열). 열·행이 유일한 창만 센다(14×4·20×4 는 창 생성 호출이 하나씩, 실측 10-11).
MSG_GENERIC = ((1, 3), (5, 18))  # 일반 규칙: 행 1~3 · 열 5~18 인 작은 창 + **전투 화면 영역(창 y)** — 전투 메시지 창(출현은 열이 이름 길이+4·행이 몬스터 종류 수로 **가변**이라 목록으로 못 센다: 승리·패배 10×1 · 레벨업 18×2 · 경험치·전리품 13×2 …). 열 3·4 팝업·행 4 이상(square 6×4·필드 메뉴 7×4)은 제외.
MSG_Y = (-48, -12)  # 창 표의 y 는 화면 가운데(120) 기준 상대값(= y−120): 전투 메시지 창(y 72~108)만. 전투 밖 1·2행 창(`0x80024040` y150 · `0x80028C20` y12)은 원판 그대로 — 용도를 모르는 창을 안 바꾼다(관리자 10-10)
MSG_OFF = 0x1C8  # 메시지 창 갈래 코드를 두는 자료 자리 안 위치(패널 스텁 `PANEL_CODE_OFF`+192B 바로 뒤) — 죽은 함수 자리가 모자라 밖으로 뺐다(11-11 패널 스텁이 12B 늘어 0x1BC→0x1C8)
N_MARK = 6
DJUMP_ADDR = 0x8008A428 + 368 - 60  # R2 맨 끝 60B(`cursor_hook.R2`+`R2_LEN`−60) — 대사창 칸 연속성 서브루틴(`djump_words`)
DJUMP_LEN = 60


def djump_words():
    """대사창 글자의 칸 연속성 — 입력 t5 = 열, t9 = 자료 기준. 출력 t6 = 1 이면 위치·타일 초기화 필요.

    열 0 이거나 직전 글자(이 훅이 부른 마지막 글자) 바로 다음 칸이 아니면 초기화한다 — 숫자 명령처럼 훅 밖에서 그려지는 칸이 줄 첫머리·중간에 끼면
    다음 글자가 직전 글자 뒤(= 윗줄 끝)에서 이어 그려지던 문제(마스터 10-13 「5 ……?Pia」). 건너뛴 칸은 위치를 열 × 12px 로 맞춘다."""
    src = f"""
    djump:
      lhu   t3, {OFF_LC}(t9)                # 직전 글자의 열 + 1
      addiu t7, t5, 1
      sh    t7, {OFF_LC}(t9)
      beq   t5, zero, dz
      li    t6, 1                           # (지연 슬롯)
      beq   t3, t5, dno                     # 연속
      sll   t4, t5, 3                       # (지연 슬롯)
      sll   t7, t5, 2
      addu  t4, t4, t7                      # 열 × 12
      jr    ra
      sh    t4, {OFF_POS}(t9)               # (지연 슬롯)
    dz:
      jr    ra
      sh    zero, {OFF_POS}(t9)             # (지연 슬롯) 줄 첫 칸 — 위치 0
    dno:
      jr    ra
      move  t6, zero                        # (지연 슬롯)
"""
    words, _ = E.asm(src, DJUMP_ADDR)
    E.verify(words, DJUMP_ADDR)
    assert 4 * len(words) <= DJUMP_LEN, f"djump 서브루틴이 자리를 넘는다 ({4 * len(words)}B)"
    return list(words)


def data_size(n_blist):
    return (OFF_BL + 2 * (n_blist + 1) + 3) & ~3


def data_base(p, n_blist=0):
    """자료 자리 — SDK 오류 출력 함수 자리(`PATCH["data"]`)의 앞에서부터."""
    return p["data"]


def data_blob(p, half_codes, markers, blist):
    """자료 바이트 — 상태 0, 반 칸 목록, 표지 표, 받침표."""
    import struct

    assert len(half_codes) < HALF_SLOTS and len(markers) == N_MARK
    blob = bytearray(data_size(len(blist)))
    struct.pack_into("<I", blob, OFF_CURP, data_base(p) + OFF_OUTA)  # 현재 타일 포인터 초기값(줄 첫 칸 전에 안 깨지게)
    for i, c in enumerate(half_codes):
        struct.pack_into("<H", blob, OFF_HALF + 2 * i, c)
    for i, (mk, w, wo, fl) in enumerate(markers):
        struct.pack_into("<4H", blob, OFF_MK + 8 * i, mk, w, wo, fl)
    for i, c in enumerate(blist):
        struct.pack_into("<H", blob, OFF_BL + 2 * i, c)
    return bytes(blob)


def hooks_b(disc, n_blist, with_josa=True):
    """([워드], 라벨) — 타일 합성 훅. `with_josa=False` 면 조사 표지 코드를 안 본다(작게)."""
    import font

    p = E.PATCH[disc]
    S = data_base(p, n_blist)
    sh, sl = S >> 16, S & 0xFFFF
    fb = font.FONTS[disc]["ram"]
    fbh, fbl = fb >> 16, fb & 0xFFFF
    fbl = fbl - 0x10000 if fbl >= 0x8000 else fbl
    fbh += 1 if fbl < 0 else 0
    hd = p["handles"]
    josa = f"""
      lhu   t0, {OFF_LAST}(t9)              # 직전에 그려진 글자(변수의 끝 글자)
      addiu t1, t9, {OFF_MK}
      li    t2, {N_MARK}
    jm_loop:
      lhu   t3, 0(t1)
      nop
      beq   t3, a2, jm_hit
      nop
      addiu t2, t2, -1
      bne   t2, zero, jm_loop
      addiu t1, t1, 8                       # (지연 슬롯)
      j     jm_done
      nop
    jm_hit:
      addiu t4, t9, {OFF_BL}                # 받침표
      move  t3, zero                        # 부류 0 = 받침 없음
    jb_loop:
      lhu   t5, 0(t4)
      nop
      beq   t5, zero, jb_end
      andi  t6, t5, 0x7fff                  # (지연 슬롯)
      bne   t6, t0, jb_loop
      addiu t4, t4, 2                       # (지연 슬롯)
      srl   t3, t5, 15
      addiu t3, t3, 1                       # 1 받침 · 2 ㄹ 받침
    jb_end:
      lhu   t5, 6(t1)                       # 플래그 bit0 없으면 전진 0 · bit1 ㄹ 을 없음으로
      nop
      andi  t6, t5, 2
      beq   t6, zero, jd_go
      li    t7, 2                           # (지연 슬롯)
      bne   t3, t7, jd_go
      nop
      move  t3, zero
    jd_go:
      beq   t3, zero, jd_none
      nop
      lhu   t8, 2(t1)                       # 받침 있음 꼴
      j     jm_done
      nop
    jd_none:
      lhu   t8, 4(t1)                       # 받침 없음 꼴
      andi  t6, t5, 1
      beq   t6, zero, jm_done
      li    t6, 1                           # (지연 슬롯)
      sh    t6, {OFF_ZADV}(t9)              # 안 그리고 전진 0(공백 글리프 + 폭 0)
    jm_done:
      lhu   t6, {OFF_ZADV}(t9)
      nop
      bne   t6, zero, jm_end                # 안 그렸으면 「직전 글자」는 그대로
      nop
      sh    t8, {OFF_LAST}(t9)
    jm_end:
""" if with_josa else ""
    src = f"""
    hook_b:
      lui   t9, {sh:#x}
      ori   t9, t9, {sl:#x}
      sw    ra, {OFF_RA}(t9)
      sw    v0, {OFF_V0}(t9)
      sw    v1, {OFF_V1}(t9)
      sw    a0, {OFF_A0}(t9)
      sw    a2, {OFF_A2}(t9)
      move  t8, a2                          # 최종 글자 = 이 글자
      sh    zero, {OFF_ZADV}(t9){josa}
      li    t1, 12                          # 전진폭 — 반 칸 글자 목록에 있으면 6
      addiu t2, t9, {OFF_HALF}
    hl_loop:
      lhu   t3, 0(t2)
      nop
      beq   t3, zero, hl_done
      nop
      bne   t3, t8, hl_loop
      addiu t2, t2, 2                       # (지연 슬롯)
      li    t1, 6
    hl_done:
      lhu   t3, {OFF_ZADV}(t9)              # 「(으)」 가 안 그려지면 전진 0
      nop
      beq   t3, zero, hz
      nop
      move  t1, zero
    hz:
      lh    t0, 0x10(fp)                    # ── 이 글자가 놓일 창 칸을 찾는다
      nop
      addiu t0, t0, -1
      andi  t0, t0, 0x1ff                   # s = 슬롯 번호
      lui   t4, {hd >> 16:#x}
      ori   t4, t4, {hd & 0xFFFF:#x}
      li    t5, 12
    scan:
      lhu   t6, 0(t4)
      lhu   t7, 0xe(t4)
      beq   t6, zero, next
      lhu   t3, 6(t4)                       # (지연 슬롯) 열
      lhu   t2, 8(t4)                       # 행
      subu  t6, t0, t7                      # k = s - slotbase
      bltz  t6, next
      nop
      mult  t3, t2
      mflo  t2
      nop
      slt   t2, t6, t2                      # k < 열×행 ?
      bne   t2, zero, found
      nop
    next:
      addiu t5, t5, -1
      bne   t5, zero, scan
      addiu t4, t4, 22
      j     out_plain
      nop
    found:
      li    t2, {E.COLS}
      beq   t3, t2, dlg                     # 대사창(열 24) · 그 밖은 전투 메시지 창만(`msg_stub`) — 목록·패널·팝업은 원판 그대로
      div   zero, t6, t3                    # (지연 슬롯)
      j     {S + MSG_OFF:#x}
      nop
    dlg:
      mfhi  t5                              # col
      addiu t2, t9, {OFF_OUTA}              # (mfhi 결과를 바로 읽지 않게 끼운 명령)
      or    t3, t8, t5                      # 코드 0 이고 열 0 = 줄 머리 내어쓰기 빈 칸(수첩 「」 항목 둘째 줄 등, 원판 자료)
      bne   t3, zero, dsk
      subu  t0, t0, t5                      # (지연 슬롯) t0 = 이 줄 첫 칸의 슬롯 번호
      li    t1, 6                           # 반 칸 — 뒤 글자가 윗줄 「 다음 글자와 맞는다(마스터 11-09 「반각공백으로 윗줄과 라인」). 줄 안의 코드 0 은 원판대로 한 칸
    dsk:
      li    t6, 276                         # 줄 끝 한계 (열 − 1) × 12
      sh    t6, {OFF_LIM}(t9)
      jal   {DJUMP_ADDR:#x}                 # 칸 연속성 판정(R2 꼬리 서브루틴) — t6 = 1 이면 위치·타일 초기화(줄 첫 칸 · 칸이 건너뛰었다)
      nop
      beq   t6, zero, nreset                # 직전 글자 바로 다음 칸 — 위치를 이어 간다
      nop
    rst:
      sw    t2, {OFF_CURP}(t9)
      sw    zero, 0(t2)
      sw    zero, 4(t2)
      sw    zero, 8(t2)
      sw    zero, 12(t2)
      sw    zero, 16(t2)
    nreset:
      lhu   t2, {OFF_POS}(t9)
      li    t3, 12
      div   zero, t2, t3
      mflo  t4                              # t = 타일 번호
      mfhi  t7                              # o = 타일 안 위치(0 · 6)
      addu  t0, t0, t4                      # 엔진이 쓸 타일 칸의 슬롯
      sll   v0, t8, 4                       # ── 글리프 소스 = 폰트 + 코드×18
      sll   v1, t8, 1
      addu  v0, v0, v1
      lui   v1, {fbh:#x}
      addiu v1, v1, {fbl}
      addu  v0, v0, v1
      lw    v1, {OFF_CURP}(t9)              # 현재 타일 포인터
      addiu a0, t9, {OFF_OUTA}
      addiu a2, t9, {OFF_SPB}
      li    t2, 6                           # ── 3바이트(두 행) 6번
    loop:
      lbu   t3, 0(v0)
      lbu   t4, 1(v0)
      lbu   t5, 2(v0)
      sll   t3, t3, 16
      sll   t4, t4, 8
      or    t3, t3, t4
      or    t3, t3, t5                      # G = 글리프 24비트
      lbu   t4, 0(v1)
      lbu   t5, 1(v1)
      lbu   t6, 2(v1)
      sll   t4, t4, 16
      sll   t5, t5, 8
      or    t4, t4, t5
      or    t4, t4, t6                      # C = 현재 타일 24비트
      beq   t7, zero, o0
      move  a1, zero                        # (지연 슬롯) 넘침 = 0
      srl   t5, t3, 6                       # o = 6: 행마다 오른쪽 6비트 이동 — 왼쪽 절반만 타일에 남고
      lui   t6, 0x3
      ori   t6, t6, 0xf03f
      and   t5, t5, t6
      or    t4, t4, t5
      sll   a1, t3, 6                       # 오른쪽 절반은 다음 타일의 왼쪽으로 넘친다
      lui   t6, 0xfc
      ori   t6, t6, 0xfc0
      and   a1, a1, t6
      j     stz
      nop
    o0:
      or    t4, t4, t3                      # o = 0: 그대로 겹친다
    stz:
      srl   t5, t4, 16
      sb    t5, 0(a0)
      srl   t5, t4, 8
      sb    t5, 1(a0)
      sb    t4, 2(a0)
      srl   t5, a1, 16
      sb    t5, 0(a2)
      srl   t5, a1, 8
      sb    t5, 1(a2)
      sb    a1, 2(a2)
      addiu v0, v0, 3
      addiu v1, v1, 3
      addiu a0, a0, 3
      addiu a2, a2, 3
      addiu t2, t2, -1
      bne   t2, zero, loop
      nop
      lhu   t2, {OFF_POS}(t9)               # ── 위치 전진 · 현재 타일 고르기
      lhu   t3, {OFF_LIM}(t9)
      nop
      sltu  a1, t2, t3                      # 옛 위치 < 한계((열 − 1) × 12 · 대사창 276) → 다음 타일이 줄 안(≤ 23번) — 넘친 조각을 써도 된다
      addu  t2, t2, t1
      sh    t2, {OFF_POS}(t9)
      addu  t3, t7, t1
      slti  t3, t3, 12                      # o + 전진 < 12 → 같은 타일에 머문다
      addiu t4, t9, {OFF_OUTA}
      bne   t3, zero, keepc
      addiu t5, t9, {OFF_SPB}               # (지연 슬롯)
      move  t4, t5
    keepc:
      sw    t4, {OFF_CURP}(t9)
      sh    t0, {OFF_IDX}(t9)
      move  t6, t0                          # ── rect 를 칸으로 — 먼저 오른쪽(넘친) 타일, 그다음 엔진이 쓸 왼쪽
      move  t5, zero
      beq   t7, zero, setr
      nop
      lhu   t2, {OFF_ZADV}(t9)
      nop
      bne   t2, zero, setr
      addiu t3, t0, 1                       # (지연 슬롯)
      beq   a1, zero, setr                  # 줄 끝을 넘는 다음 타일은 안 쓴다(칸 번호가 다음 줄로 넘어가지 않게)
      nop
      move  t6, t3
      li    t5, 1
    setr:
      sll   t3, t6, 1
      lui   t4, 0x800e
      addiu t4, t4, -0x1b48                 # 칸 → VRAM 위치 표 `0x800DE4B8`
      addu  t3, t3, t4
      lhu   t3, 0(t3)
      nop
      andi  t4, t3, 0xff
      srl   t4, t4, 2
      addiu t4, t4, 0x140
      sh    t4, 0x40(fp)
      srl   t3, t3, 8
      andi  t3, t3, 0xff
      sh    t3, 0x42(fp)
      beq   t5, zero, out
      nop
      lhu   t3, 0x14(fp)                    # 엔진 링 한 칸 — 이 칸에 넘친 타일을 펼친다
      nop
      sll   t4, t3, 6
      sll   t5, t3, 4
      sll   t6, t3, 2
      addu  t4, t4, t5
      addu  t4, t4, t6                      # idx × 84
      addiu t4, t4, 0x58
      addu  t4, t4, fp                      # 목적지
      addiu t3, t3, 1
      andi  t3, t3, 7
      sh    t3, 0x14(fp)                    # 엔진은 다음 칸을 쓴다
      addiu t5, t9, {OFF_SPB}
      move  t6, t4
      li    t2, 18
      lui   t7, 0x800a
      addiu t7, t7, 0x620c                  # 바이트 → 4바이트(8픽셀 4bpp) 전개표
    exl:
      lbu   t3, 0(t5)
      nop
      sll   t3, t3, 2
      addu  t3, t3, t7
      lw    t3, 0(t3)
      nop
      sw    t3, 0(t6)
      addiu t5, t5, 1
      addiu t2, t2, -1
      bne   t2, zero, exl
      addiu t6, t6, 4                       # (지연 슬롯)
      sw    zero, 0(t6)                     # 13번째 행(0) — 엔진도 0 6B 를 채운다
      sh    zero, 4(t6)
      addiu a0, fp, 0x40
      move  a1, t4
      jal   0x8008a8dc                      # LoadImage(rect, 데이터)
      nop
      lui   t9, {sh:#x}
      ori   t9, t9, {sl:#x}
      lhu   t6, {OFF_IDX}(t9)
      li    t5, 0
      j     setr
      nop
    out_plain:
      lui   a1, {fbh:#x}
      j     rest
      addiu a1, a1, {fbl}                   # (지연 슬롯)
    out:
      lw    a0, {OFF_A0}(t9)
      addiu a1, t9, {OFF_OUTA}              # 소스 = 합성 버퍼 (엔진이 a1 + a0 를 읽는다)
      subu  a1, a1, a0
    rest:                                   # 두 갈래가 같이 쓰는 복구(a1 은 건드리지 않는다) — 11-09 내어쓰기 반 칸 3워드를 이 중복에서 벌었다
      lw    ra, {OFF_RA}(t9)
      lw    v0, {OFF_V0}(t9)
      lw    v1, {OFF_V1}(t9)
      lw    a0, {OFF_A0}(t9)
      lw    a2, {OFF_A2}(t9)
      jr    ra
      nop
"""
    words, labels = E.asm(src, p["dead"])
    E.verify(words, p["dead"])
    return words, labels


LIST_COLS = (8, 11)  # 목록·이름 창 열 8~11 — 상점 구매(0x35)·판매(0x36) · 도구(11)·장비(10) · 소지품 고르기(11) · 전투 마법(8×8)·전투 도구(8×3) (`cursor_hook.LIST_COLS` 와 같다. 마스터 11-09 「띄어쓰기는 반각」은 창 종류와 무관)


def msg_len(disc):
    """메시지 갈래 스텁의 워드 수(표 포함) — 라벨 주소는 길이에 안 든다. 공백 코드 값은 길이에 안 든다(`li` 한 워드)."""
    _, labels = hooks_b(disc, 0)
    return len(msg_stub(disc, labels, 1)[0])


def msg_stub(disc, labels, space=None):
    """([워드], 시작 주소) — 전투 메시지 창(`MSG_WINDOWS`: 레벨업·경험치·전리품·승리·패배)의 갈래. 훅 `found:` 에서 `j` 로 들어온다.

    그 창이 아니면 `out_plain`(원판 그대로). 맞으면 열 `col` 을 구하고, **엔진이 커서를 옮겼으면**(열이 직전 글자 + 1 이 아니면 — 이름 뒤 폭 표 · 숫자 자리)
    위치를 `열 × 12` 로 다시 잡아 줄 처음처럼 시작한다. 레벨업 줄 「쥬리오의 레벨이 올랐습니다.」 의 어절 사이 공백이 반 칸이도록 한다(규칙 1-1, 관리자 10-09).
    들어올 때 레지스터: t3 = 열 수 · t4 = 창 표 항목 · t6 = 칸 번호 k · t0 = 슬롯 번호 · t9 = 자료 · `div t6, t3` 은 이미 했다(지연 슬롯).
    """
    p = E.PATCH[disc]
    base = p["data"] + MSG_OFF
    op = labels["out_plain"]
    chk = ["      lhu   t5, 8(t4)                       # 행", "      nop"]
    assert all(bias == 0 for _c, _r, bias in MSG_WINDOWS), "줄 앞 밀기(bias)는 모든 창이 0 — 표·코드에서 걷어 자리를 아꼈다"
    chk += [  # 개별 목록(열|행<<8 u16 · 0 종결)을 코드 뒤 표에서 훑는다 — 코드 자리를 아끼려 풀어 쓰지 않는다
        "      sll   t7, t5, 8",
        "      or    t7, t7, t3                      # 열쇠 = 열 | 행 << 8",
        "      lui   t2, @TH@",
        "      ori   t2, t2, @TL@",
        "    msg_l:",
        "      lhu   t6, 0(t2)",
        "      addiu t2, t2, 2                       # (로드 지연 자리)",
        "      beq   t6, zero, msg_ld",
        "      nop",
        "      bne   t6, t7, msg_l",
        "      nop",
        "      j     msg_ok",
        "      nop",
        "    msg_ld:",
    ]
    (r0, r1), (c0, c1) = MSG_GENERIC
    chk += [
        f"      addiu t2, t5, -{r0}",
        f"      sltiu t2, t2, {r1 - r0 + 1}",
        "      beq   t2, zero, msg_lst               # 행이 1~3 이 아니면 목록 창 판정으로",
        "      nop",
        f"      addiu t2, t3, -{c0}",
        f"      sltiu t2, t2, {c1 - c0 + 1}",
        "      beq   t2, zero, msg_lst               # 열이 5~18 이 아니면 목록 창 판정으로",
        "      lh    t2, 4(t4)                       # (지연 슬롯) 창 y(화면 가운데 기준)",
        "      nop",
        f"      addiu t2, t2, {-MSG_Y[0]}",
        f"      sltiu t2, t2, {MSG_Y[1] - MSG_Y[0] + 1}",
        "      bne   t2, zero, msg_ok                # 전투 화면 영역이면 메시지 창",
        "      nop",
        "    msg_lst:                                # 목록 창(열 8~11) — 공백만 반 칸(마스터 11-09 「띄어쓰기는 반각」)",
    ]
    if space is not None:
        lo, hi = LIST_COLS
        chk += [
            f"      addiu t2, t3, -{lo}",
            f"      sltiu t2, t2, {hi - lo + 1}",
            f"      beq   t2, zero, {op:#x}                  # 목록 창이 아니면 원판 그대로",
            f"      li    t2, {space}                     # (지연 슬롯)",
            "      bne   t8, t2, msg_ok",
            "      li    t1, 12                          # (지연 슬롯) 공백이 아니면 전각 폭",
            "      li    t1, 6                           # 공백 — 반 칸",
        ]
    else:
        chk += [f"      j     {op:#x}", "      nop"]
    chk += ["    msg_ok:"]
    msg_checks = "\n".join(chk) + "\n"
    src = f"""
{msg_checks}      mfhi  t5                              # col
      addiu t2, t9, {OFF_OUTA}
      subu  t0, t0, t5
      addiu t6, t3, -1
      sll   t7, t6, 3
      sll   t6, t6, 2
      addu  t6, t6, t7                      # (열 − 1) × 12
      sh    t6, {OFF_LIM}(t9)
      lhu   t6, {OFF_LC}(t9)
      sh    t5, {OFF_LC}(t9)
      addiu t6, t6, 1
      beq   t6, t5, {labels['nreset']:#x}    # 직전 글자 바로 다음 칸 — 이어 쓴다
      nop
      sll   t6, t5, 3
      sll   t7, t5, 2
      addu  t6, t6, t7                      # 열 × 12
      sh    t6, {OFF_POS}(t9)
      j     {labels['rst']:#x}
      nop
"""
    def fill(tab):
        return src.replace("@TH@", f"{tab >> 16:#x}").replace("@TL@", f"{tab & 0xFFFF:#x}")

    n_code = len(E.asm(fill(0x80000000), base)[0])
    tab = base + 4 * n_code
    words, _ = E.asm(fill(tab), base)
    assert len(words) == n_code
    E.verify(words, base)
    import struct

    raw = b"".join(struct.pack("<H", c | (r << 8)) for c, r, _bias in MSG_WINDOWS) + b"\0\0"
    raw += b"\0" * (-len(raw) % 4)
    return list(words) + list(struct.unpack(f"<{len(raw) // 4}I", raw)), base


# ── 월드맵 장소 패널 가운데 정렬(마스터 10-09 「반각 가능하면 해 봐」) ───────────────────────────────
# 패널 문자열은 대사창 훅(`0x80018ACC`)을 안 탄다 — `0x8001BEB4`(문자열 하나를 칸 스프라이트로 늘어놓는 함수, 호출처 11곳이 전부 장소 표 `0x800AAEFC` 기준 = 패널 전용)가
# 글자마다 x 를 12px 씩 늘리고, **제어 코드(최상위 비트)** 를 만나면 줄을 바꾼다. 원판은 들여쓰기를 0 코드(12px 빈 글자)로 해 가운데를 흉내 냈는데, 줄의 칸 수(바이트)가 고정이라
# 한글 글자 수가 갈리면 반 칸(6px)을 못 맞춘다. 그래서 **엔진이 줄마다 가운데를 계산**하게 한다: 줄 시작 x = 칸 왼쪽 + 36 − 6×(그 줄의 글자 수) (칸 폭 72px, 0 코드는 글자로 안 센다).
# 0 코드는 이제 폭 0 이다(원판 일본어 줄도 같은 규칙으로 가운데). 세 군데를 바꾼다(PANEL_SITES) — 줄 시작(첫 줄 · 줄바꿈 뒤)과 글자 후 x 전진.
PANEL_CODE_OFF = 0x108  # 자료 자리 안, 상태·표(OFF_BL…) 뒤


PANEL_INIT_ADDR = 0x8008A2A4  # 첫 줄 진입 스텁 둘(8B)을 둘 자리 — 커서 줄 훅 R1(`cursor_hook.R1`, 428B 검증 구간) 꼬리의 안 쓰는 16B 첫머리(= R1 + 412). `engine_patch.apply_panel` 이 겹침을 검산한다
PANEL_ROW_PX = (
    72  # 패널 칸 폭 — 줄 폭이 이를 넘으면 글자 간격 11px(마스터 11-11 「6글자 초과에 대해서만」)
)


def panel_stubs(disc, space):
    """([워드], 시작 주소, {라벨: 주소}, [첫 줄 진입 워드]) — 패널 정렬 스텁(줄 시작 · 줄바꿈 뒤 줄 시작 · x 전진).

    줄의 **실제 폭**을 재서 가운데 맞춘다: 공백(`space` 코드)은 6px · 나머지 글자는 12px · 0 코드(들여쓰기)는 폭 0.
    폭이 칸(72px)을 넘으면 그 줄만 글자 **간격을 11px** 로 줄여(글자 수만큼 1px 씩 — 공백은 6px 그대로) 칸 안에 넣고, 그 간격을
    `fp+0x24`(원판이 줄바꿈 때 줄 시작 x 를 읽던 자리 — 우리 스텁은 안 쓴다)에 줄마다 둔다. 글자 후 전진(`stub_adv`)이 그 값을 읽는다.
    첫 줄 진입 스텁 `stub_init`(2워드)은 자리가 모자라 R1 꼬리(`PANEL_INIT_ADDR`)에 따로 둔다.
    함수 안에 t 레지스터 사용이 없어(전수 확인) t0~t9 를 자유롭게 쓴다."""
    assert 0 < space < 0x7FFF, space
    p = E.PATCH[disc]
    base = p["data"] + PANEL_CODE_OFF
    src = f"""
    stub_line:                              # 줄바꿈 뒤 — idx = fp+0x22 + 1
      lh    t0, 0x22(fp)
      nop
      addiu t0, t0, 1
    stub_calc:
      lw    t1, 0x60(fp)                    # 문자열
      addiu t6, zero, {space}               # 공백 코드
      addiu t2, zero, -{PANEL_ROW_PX}       # 줄 폭 − 칸 폭
      move  t7, zero                        # 공백 아닌 글자 수
    sc_loop:
      sll   t3, t0, 1
      addu  t3, t3, t1
      lhu   t4, 0(t3)
      addiu t0, t0, 1                       # (지연 슬롯) 다음 칸
      andi  t5, t4, 0x8000
      bne   t5, zero, sc_done               # 제어 코드 = 줄 끝
      addiu t3, zero, 12                    # (지연 슬롯)
      beq   t4, zero, sc_loop               # 0 = 들여쓰기 빈 글자 — 안 센다
      nop
      bne   t4, t6, sc_add
      addiu t7, t7, 1                       # (지연 슬롯) 글자 수 + 1
      addiu t3, zero, 6                     # 공백 = 반 칸 폭
      addiu t7, t7, -1                      # 공백은 글자 수에서 뺀다
    sc_add:
      j     sc_loop
      addu  t2, t2, t3                      # (지연 슬롯)
    sc_done:
      addiu t8, zero, 12
      blez  t2, sc_ok                       # 폭 ≤ 칸 — 12px 그대로
      lw    t6, 0x34(fp)                    # (지연 슬롯) 창 핸들
      addiu t8, zero, 11                    # 넘으면 이 줄만 11px
      subu  t2, t2, t7                      # 폭에서 글자 수만큼
    sc_ok:
      sra   t3, t2, 1                       # (폭 − 72) / 2
      lhu   t6, 2(t6)                       # 칸 왼쪽 x
      sh    t8, 0x24(fp)                    # 이 줄의 글자 간격
      subu  t6, t6, t3                      # 왼쪽 + 36 − 폭/2
      jr    ra
      sh    t6, 0x10(fp)                    # (지연 슬롯) 이 줄의 x
    stub_adv:                               # 글자 하나 뒤 x 전진 — 0 코드는 폭 0, 공백은 6, 나머지는 줄 간격
      lw    t0, 0x60(fp)
      lh    t1, 0x22(fp)
      addiu t3, zero, {space}
      sll   t1, t1, 1
      addu  t0, t0, t1
      lhu   t2, 0(t0)
      lhu   t1, 0x24(fp)
      beq   t2, zero, sa_store              # 0 코드 — v0(= 옛 x) 그대로
      nop
      bne   t2, t3, sa_add
      nop
      addiu t1, zero, 6
    sa_add:
      addu  v0, v0, t1
    sa_store:
      jr    ra
      sh    v0, 0x10(fp)                    # (지연 슬롯)
"""
    words, labels = E.asm(src, base)
    E.verify(words, base)
    assert 4 * len(words) <= MSG_OFF - PANEL_CODE_OFF, (
        f"패널 스텁 {4 * len(words)}B 가 자리({MSG_OFF - PANEL_CODE_OFF}B)를 넘는다"
    )
    init, _ = E.asm(f"stub_init:\n  j {labels['stub_calc']:#x}\n  move t0, zero", PANEL_INIT_ADDR)
    E.verify(init, PANEL_INIT_ADDR)
    labels = dict(labels, stub_init=PANEL_INIT_ADDR)
    return words, base, labels, init


# 고칠 자리(원본 워드 대조) — 줄 시작(첫 줄) · 줄바꿈 뒤 · x 전진. (자리, 원본 워드들, 스텁 라벨)
PANEL_SITES = {
    "ed3": [
        (0x8001C138, (0x97C20010, 0x00000000, 0xA7C20024), "stub_init"),  # lhu v0,0x10(fp) · nop · sh v0,0x24(fp)
        (0x8001C310, (0x97C20024, 0x00000000, 0xA7C20010), "stub_line"),  # lhu v0,0x24(fp) · nop · sh v0,0x10(fp)
        (0x8001C2F0, (0x2443000C, 0xA7C30010), "stub_adv"),  # addiu v1,v0,12 · sh v1,0x10(fp)
    ]
}
