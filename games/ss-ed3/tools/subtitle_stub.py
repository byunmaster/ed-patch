"""컷신 자막 **자체 렌더러 스텁** — SH-2 를 손으로 짠다.

    python3 games/ss-ed3/tools/subtitle_stub.py            # 어셈블 + 자기검사
    python3 games/ss-ed3/tools/subtitle_stub.py --bin OUT  # 바이트로 뽑는다

왜 필요한가 — 엔진의 글자 창(대사창 `FF 02` · 띠 `FF 87`)은 **컷신 중에 못 쓴다**
(2026-09-04 실측: 배우 배치가 어긋나거나 게임이 뻗는다). 그래서 **명령 표에 우리 명령을
직접 얹는다.** 창 테두리 패턴은 원판 것(`0x12000`)을 그대로 가리키므로 픽셀이 원판과 같다.

스크립트가 어떻게 알리는가 — **자기 PC 로**(2026-09-04). 엔진은 스크립트 PC 를 전역
(`0x0609408C`)에 두므로, 스텁이 그걸 읽어 **우리 칸 안이면 켠다.** 칸은 32B 정렬이라
`PC & ~31` 이 곧 칸이고, 칸 끝의 **서명 + 글자 포인터**가 「우리 칸」임과 무엇을 띄울지를
말한다(`voice_sub.slot()`). ⇒ 스텁은 맵을 모른다 — **어느 맵이든 같은 스텁**이다.
🔴 트램펄린은 **한 프레임 안에 지나가서** 그냥 두면 못 본다 — 블록마다 `FF 35 0001`
(한 프레임 대기)을 넣어 **PC 가 머물게** 한다. 열세 블록이면 다 합쳐 13 프레임(0.2 초)이라
장면이 늘어지지 않는다. ⇒ **워크램에 값을 쓰는 스크립트 옵코드를 찾을 필요가 없다.**
글자 앞 워드가 **표시 프레임 수**다(0 = 다음 칸까지) — 침묵 구간에 창이 남지 않는다.

어디에 무는가 — **창 갱신 함수의 에필로그**(`0x060101BA`). 그 함수는 컷신에도 매 프레임
불리고(180 프레임에 184 회), **명령 표에 마지막으로 얹는 쪽**이라 우리 명령이 안 덮인다.
⚠ 훅은 `r8` 을 거쳐 뛴다 — 에필로그가 곧 `r8` 을 스택에서 되살리므로 안전하다.
   (`r0` 은 반환값일 수 있어 안 건드린다.)

🔴 **손인코딩 기계어는 디스어셈블로 검산한다**(루트 CLAUDE.md 「빌드 규율」). 이 파일의
`--bin` 산출물을 에뮬 RAM 에 얹고 `disassemble` 로 한 줄씩 맞춰 본 뒤에만 빌드에 넣는다.
"""

import argparse
import struct

#   🔴 자리는 **디버그 메뉴 코드**(`0x0601641C~0x0601A20C`, 15,856B)다 — 2026-09-05.
#     문자열 구역(332B)이 꽉 차서 옮겼다. 이 구역은 **입구가 하나**다: `0x06008B26` 이
#     `0x0601641C`(디버그 메뉴 본체)를 부르는데, 그 앞 `0x06008B1C` 가 **디버그 플래그
#     `0x060793a8`**(타이틀에서 패드 `0x0888` 조합으로만 1 이 된다 — `0x0603CDD4`)을 보고
#     0 이면 건너뛴다. 리터럴·bsr 전수 스캔으로 다른 입구가 없음을 확인했고(부품 표
#     `0x06079634`·`0x06079764`·`0x060797e0` 은 전부 이 구역 안에서만 읽는다), 컷신·대화
#     6,000 프레임에 exec BP 를 걸어 한 번도 안 걸렸다.
#     ⇒ `patch()` 가 **그 분기를 무조건 건너뛰게**(bt→bra) 바꿔 구역을 완전히 죽인 뒤 쓴다.
#     🔴 `0x0601A20C` 부터는 산 데이터(각도 표, `0x06005870` 등이 읽는다) — 넘지 않는다.
#   ⚠ `0x06076110` 은 **빈칸이 아니다** — 엔진 BSS 다(`gbr+0x1c` 가 그 주소를 들고 있고
#   세이브스테이트엔 0x20 간격 항목이 들어 있었다). 2026-09-04 실측.
STUB = 0x06018C00  # 디버그 메뉴 처리기 표(`0x06079764`)의 첫 항목 — 여기부터 처리기 코드
STUB_END = 0x0601A20C  # 산 데이터 시작
DEBUG_GATE = 0x06008B1C  # `bt 0x6008bc4`(8952) → `bra`(A052): 디버그 메뉴 입구를 막는다
HOOK = 0x060101BA  # 창 갱신 함수(0x06010070)의 공통 에필로그
TAB = 0x25C00000  # VDP1 명령 표 (CMDSRCA 계산에만 쓴다 — 표엔 직접 안 쓴다)
EMIT = 0x0606B838  # 엔진 스프라이트 등록: emit(r4=명령 30B, r5=Z). 아래 `skip_draw` 주석
Z_NEAR = 0x500000  # = gbr+104(0xa00000) >> gbr+172(1) — 맵 화면 실측. Z 는 이보다 커야 받는다
PCVAR = 0x0609408C  # 스크립트 PC 전역 (실측: 맵 주소 `0x0021bf30` 이 들어 있었다)
#   🔴 블록은 **32B 정렬 칸**에 하나씩이다 — 칸 = PC & ~31. 옮겨 온 옵코드(≤14B) +
#   `FF 35 0001` + `FD 00 <복귀>` = 24B 뒤에 **서명(4B) + 글자 포인터(4B)** 가 온다.
#   서명이 안 맞으면 남의 코드다(맵 안 아무 데나 PC 가 있을 때 우연히 맞을 확률 2^-32).
SLOT = 32
MAGIC = 0x53554221  # 'SUB!'
MAGIC_OFF = 24
PTR_OFF = 28
#   글자 = `<표시 프레임 수 BE16> <얼굴 BE16> <표정 BE16>` + `이름\0` + `줄1\0줄2\0…\0`.
#   프레임 수 0 = 다음 칸까지 둔다. 얼굴 0xFFFF = 없음. 이름이 비면 이름 줄을 안 그린다.
#   첫 줄이 비어 있으면 **닫는 칸**이다(창을 닫고 얼굴을 치운다).
#   🔴 프레임 수 0xFFFF 는 **미리 싣기 목록**이다 — 뒤에 `<얼굴 표정>` 쌍이 0xFFFF 로 끝난다.
#     얼굴은 CD 에서 오는데 음성(`FF 42`)이 흐르는 동안은 **CD 가 음성 것**이라 로드가 영영
#     안 끝난다(2026-09-05 실측, 상태 6 에 멈춘다). 그래서 음성 전에 스텁이 엔진 얼굴 작업을
#     한 장씩 켜서(상태 1) 캐시에 실리자마자(상태 2) 꺼 버린다(상태 0) — 그려지지 않고 캐시만
#     남는다(실측: 키 표 `0x002F8E24` 에 들어오고 화면엔 안 뜬다). 음성 중엔 캐시 적중이라
#     CD 를 안 탄다.
#   ⚠ 포인터는 짝수여야 한다 — 프레임 수를 `mov.w` 로 읽는다(홀수면 어드레스 에러).
LINE_PITCH = 16  # 줄 간격(px) — 12px 글자 + 4

#   ── 글자 ─────────────────────────────────────────────────────────────────
#   🔴 엔진의 글자 함수를 그대로 부른다 — 우리가 폰트를 다시 그리지 않는다.
#     규약은 띠 그리기(`0x0600FFDA~`)에서 읽었다:
#       clear(r4=버퍼, r5=길이)                              `0x0601a838`
#       draw (r4=대상, r5=행 스트라이드(B), r6=문자열, r7=글자높이, 스택 색·0·1)  `0x060417ac`
#     실측 뒷받침: 띠 버퍼가 `0x980`(2,432B) = 152B × 16행 = **304px 4bpp** 이고
#     그때 r5 가 `0x98`(152)였다 — 즉 r5 는 **행 바이트 수**다.
CLEARFN = 0x0601A838
DRAWFN = 0x060417AC
BUF = 0x25C79000  # 우리 글자 버퍼 (빈 VRAM)
CRED_PITCH = 12  # 크레딧 자막 줄 간격(px) — Galmuri9 9 행 + 3
CRED_CELL = 10  # 크레딧 자막 글자 폭(px) — Galmuri9 9 + 간격 1. 반각은 그 절반 − 1 이 아니라 CELL//2//2·2 = 4
BUF_STRIDE = 108  # 216px 4bpp = 108B — 원판 대사창 글자 스프라이트와 같은 폭
BUF_LEN = 108 * 48  # 216x48
MAX_LINES = 3  # 48px ÷ 16 — 이름 줄이 있으면 본문은 둘

#   ── 얼굴 — 엔진의 얼굴 작업(`0x0601086C`, 매 프레임 우리 훅 **뒤에** 돈다)을 값으로 몬다.
#     상태 `0x06093EF4`: 0 없음 · 1 시작(조회→캐시면 곧 2, 아니면 CD 로드 뒤 6→2) · 2 밀려
#     들어옴 · 3 떠 있음 · 4 = 「밀어내고 새 얼굴」(5 를 거쳐 id≥0 이면 1, 아니면 0).
#     인게임 실측 2026-09-05: 보이기 = winx·winy·id·표정 쓰고 상태 1, 갈기 = 새 id + 상태 4,
#     치우기 = id 0xFFFF + 상태 4. 창 좌표(엔진 대사창 값 0x40·0xC4)에서 얼굴은 우리 테두리
#     왼쪽(화면 17,172)에 놓인다 — 엔진 대사창과 같은 그림이 된다.
F_STATE = 0x06093EF4
F_ID = 0x06094056
F_EXPR = 0x06093FF0
F_WINX = 0x0609402C
F_WINY = 0x06093EF0
WIN_X, WIN_Y = 0x40, 0xC4
NAME_COLOR, BODY_COLOR = 14, 15  # 엔진 대사창과 같다 — 이름은 14(연청), 본문은 15(흰)

#   ── 스텁 변수 표(코드 바로 뒤, 4 정렬) — 오프셋
V_FLAG, V_TIMER = 0, 2  # 창 켜짐(u16) · 남은 프레임(u16)
V_TXTP, V_DRAWN, V_PRE = 4, 8, 12  # 래치한 글자 · 그린 글자 · 미리 싣기 목록 커서(0 = 없음)
V_FACE_ID, V_FACE_EXPR = 16, 18  # 지금 얼굴 (0xFFFF = 없음)
V_NOFACE = 20  # 상수 쌍 `FFFF 0000` — 치울 때 face_apply 에 준다
VAR_LEN = 24


class Asm:
    """필요한 만큼만 있는 SH-2 어셈블러. **인코딩은 주석에 비트로 적는다.**"""

    def __init__(self, org):
        self.org, self.w, self.lbl, self.fix = org, [], {}, []

    def _e(self, word):
        self.w.append(word)

    def at(self):
        return self.org + len(self.w) * 2

    def label(self, n):
        self.lbl[n] = self.at()

    # ── 자료 이동 ────────────────────────────────────────────────
    def push(self, m):  # mov.l Rm,@-r15   0010 1111 mmmm 0110
        self._e(0x2F06 | (m << 4))

    def pop(self, n):  # mov.l @r15+,Rn   0110 nnnn 1111 0110
        self._e(0x60F6 | (n << 8))

    def movl_pc(self, n, name):  # mov.l @(d,PC),Rn   1101 nnnn dddddddd
        self.fix.append((len(self.w), name, "pcl"))
        self._e(0xD000 | (n << 8))

    def movw_at(self, n, m):  # mov.w @Rm,Rn     0110 nnnn mmmm 0001
        self._e(0x6001 | (n << 8) | (m << 4))

    def movw_d_r0(self, m, d):  # mov.w @(disp,Rm),R0   1000 0101 mmmm dddd  (disp×2)
        assert d % 2 == 0 and 0 <= d <= 30
        self._e(0x8500 | (m << 4) | (d >> 1))

    def movw_r0_d(self, n, d):  # mov.w R0,@(disp,Rn)   1000 0001 nnnn dddd  (disp×2)
        assert d % 2 == 0 and 0 <= d <= 30
        self._e(0x8100 | (n << 4) | (d >> 1))

    def movb_at(self, n, m):  # mov.b @Rm,Rn     0110 nnnn mmmm 0000
        self._e(0x6000 | (n << 8) | (m << 4))

    def movl_inc(self, n, m):  # mov.l @Rm+,Rn   0110 nnnn mmmm 0110
        self._e(0x6006 | (n << 8) | (m << 4))

    def movl_to(self, n, m):  # mov.l Rm,@Rn    0010 nnnn mmmm 0010
        self._e(0x2002 | (n << 8) | (m << 4))

    def movl_d(self, n, m, d):  # mov.l @(disp,Rm),Rn   0101 nnnn mmmm dddd  (disp×4)
        assert d % 4 == 0 and 0 <= d <= 60
        self._e(0x5000 | (n << 8) | (m << 4) | (d >> 2))

    def movl_to_d(self, n, m, d):  # mov.l Rm,@(disp,Rn)   0001 nnnn mmmm dddd  (disp×4)
        assert d % 4 == 0 and 0 <= d <= 60
        self._e(0x1000 | (n << 8) | (m << 4) | (d >> 2))

    def movw_inc(self, n, m):  # mov.w @Rm+,Rn   0110 nnnn mmmm 0101
        self._e(0x6005 | (n << 8) | (m << 4))

    def and_(self, n, m):  # and Rm,Rn         0010 nnnn mmmm 1001
        self._e(0x2009 | (n << 8) | (m << 4))

    def mov(self, n, m):  # mov Rm,Rn        0110 nnnn mmmm 0011
        self._e(0x6003 | (n << 8) | (m << 4))

    def movi(self, n, i):  # mov #imm,Rn     1110 nnnn iiiiiiii
        self._e(0xE000 | (n << 8) | (i & 0xFF))

    def add(self, n, i):  # add #imm,Rn      0111 nnnn iiiiiiii
        self._e(0x7000 | (n << 8) | (i & 0xFF))

    # ── 판단·흐름 ────────────────────────────────────────────────
    def tst(self, n, m):  # tst Rm,Rn        0010 nnnn mmmm 1000
        self._e(0x2008 | (n << 8) | (m << 4))

    def movl_at(self, n, m):  # mov.l @Rm,Rn  0110 nnnn mmmm 0010
        self._e(0x6002 | (n << 8) | (m << 4))

    def movw_to(self, n, m):  # mov.w Rm,@Rn  0010 nnnn mmmm 0001
        self._e(0x2001 | (n << 8) | (m << 4))

    def sub(self, n, m):  # sub Rm,Rn         0011 nnnn mmmm 1000
        self._e(0x3008 | (n << 8) | (m << 4))

    def cmp_hs(self, n, m):  # cmp/hs Rm,Rn   0011 nnnn mmmm 0010  (T = Rn >= Rm, 부호없음)
        self._e(0x3002 | (n << 8) | (m << 4))

    def cmp_eq(self, n, m):  # cmp/eq Rm,Rn   0011 nnnn mmmm 0000
        self._e(0x3000 | (n << 8) | (m << 4))

    def shlr(self, n):  # shlr Rn             0100 nnnn 00000001
        self._e(0x4001 | (n << 8))

    def shlr2(self, n):  # shlr2 Rn           0100 nnnn 00001001
        self._e(0x4009 | (n << 8))

    def shll2(self, n):  # shll2 Rn           0100 nnnn 00001000
        self._e(0x4008 | (n << 8))

    def addr(self, n, m):  # add Rm,Rn        0011 nnnn mmmm 1100
        self._e(0x300C | (n << 8) | (m << 4))

    def jsr(self, n):  # jsr @Rn              0100 nnnn 00001011
        self._e(0x400B | (n << 8))

    def jmp(self, n):  # jmp @Rn              0100 nnnn 00101011  (지연 슬롯 하나)
        self._e(0x402B | (n << 8))

    def sts_pr(self):  # sts.l PR,@-r15       0100 1111 00100010
        self._e(0x4F22)

    def cmp_pz(self, n):  # cmp/pz Rn        0100 nnnn 00010001
        self._e(0x4011 | (n << 8))

    def dt(self, n):  # dt Rn                0100 nnnn 00010000
        self._e(0x4010 | (n << 8))

    def bt(self, name):  # bt disp           10001001 dddddddd
        self.fix.append((len(self.w), name, "b8"))
        self._e(0x8900)

    def bf(self, name):  # bf disp           10001011 dddddddd
        self.fix.append((len(self.w), name, "b8"))
        self._e(0x8B00)

    def bra(self, name):  # bra disp         1010 dddddddddddd
        self.fix.append((len(self.w), name, "b12"))
        self._e(0xA000)

    def bsr(self, name):  # bsr disp         1011 dddddddddddd  (지연 슬롯 하나)
        self.fix.append((len(self.w), name, "b12"))
        self._e(0xB000)

    def shll(self, n):  # shll Rn             0100 nnnn 00000000
        self._e(0x4000 | (n << 8))

    #   bt/bf 는 ±128 명령까지다 — 스텁이 길어져 못 닿는 자리는 반대 조건으로 건너뛰고 bra 한다
    def bt_far(self, name):
        self._far(name, self.bf)

    def bf_far(self, name):
        self._far(name, self.bt)

    def _far(self, name, skip):
        lbl = f"_far{len(self.w)}"
        skip(lbl)
        self.bra(name)
        self.nop()
        self.label(lbl)

    def lds_pr(self):  # lds.l @r15+,PR      0100 1111 00100110
        self._e(0x4F26)

    def rts(self):  # rts                    0000 0000 00001011
        self._e(0x000B)

    def nop(self):
        self._e(0x0009)

    # ── 마무리 ───────────────────────────────────────────────────
    def resolve(self, pool):
        """`pool` = {이름: 4바이트 값}. 리터럴을 코드 뒤 4정렬 자리에 놓는다."""
        base = self.org + len(self.w) * 2
        base += base % 4
        addr = {}
        for i, name in enumerate(pool):
            addr[name] = base + i * 4
        for idx, name, kind in self.fix:
            at = self.org + idx * 2
            if kind == "pcl":
                d = (addr[name] - ((at & ~3) + 4)) // 4
                assert 0 <= d <= 255 and ((at & ~3) + 4 + d * 4) == addr[name], (name, d)
                self.w[idx] |= d
            else:
                d = (self.lbl[name] - (at + 4)) // 2
                lim = 0x7F if kind == "b8" else 0x7FF
                assert -lim - 1 <= d <= lim, (name, d)
                self.w[idx] |= d & (0xFF if kind == "b8" else 0xFFF)
        out = b"".join(struct.pack(">H", x) for x in self.w)
        out += b"\x00" * ((self.org + len(out)) % 4)
        for name in pool:
            out += struct.pack(">I", pool[name])
        return out, addr


def build():
    """`(스텁 바이트, 훅 바이트, 자리표)` — 글자는 스텁에 없다. 맵의 칸이 가리킨다."""
    a = Asm(STUB)
    #   ⚠ 지키는 건 r0(반환값일 수 있다)과 PR 뿐이다 — r1~r7 은 호출 규약상 스크래치이고
    #     r8~r13 은 밀어낸 에필로그가 스택에서 되살린다. r14 는 에필로그가 SP 로 쓴다 — 안 건드린다.
    #   레지스터 배정: r11 = 변수 표 · r8 = 글자 걷는 포인터 · r9 = 얼굴 쌍/버퍼 · r10 = 이름
    #     r12 = F_STATE · r13 = 남은 줄 수. 하위 루틴은 r0~r4 를 쓴다.
    a.push(0)
    a.sts_pr()
    a.movl_pc(11, "VAR")
    #   ── 스크립트가 우리 칸에 들어왔나 → 칸 = PC & ~31, 칸+24 가 서명이면 켜고 포인터를 든다
    #     ⚠ 트램펄린은 한 프레임에 지나가므로 블록마다 `FF 35 0001` 로 PC 를 머물게 한다.
    a.movl_pc(0, "PCVAR")
    a.movl_at(0, 0)
    a.movi(2, -SLOT)
    a.and_(0, 2)
    a.movl_d(3, 0, MAGIC_OFF)
    a.movl_pc(2, "MAGIC")
    a.cmp_eq(3, 2)
    a.bf("no_latch")
    a.movl_d(3, 0, PTR_OFF)
    #   🔴 **같은 포인터는 다시 안 켠다** — 칸 안에서 오래 기다리는 사이(대기 옵코드를 칸에
    #     옮겨 왔을 때) 표시 시간이 다 돼 껐는데 다음 프레임에 또 켜지면 시간이 무의미해진다.
    #     한 장면의 마지막은 **닫는 칸**(빈 글자)이라 다음에 같은 장면을 다시 봐도 첫 칸이 켜진다.
    a.movl_d(1, 11, V_TXTP)
    a.cmp_eq(3, 1)
    a.bt("no_latch")
    a.movl_to_d(11, 3, V_TXTP)
    a.movi(0, 1)
    a.movw_r0_d(11, V_FLAG)
    a.label("no_latch")
    #   ── 미리 싣기 — 목록(PRE)이 있으면 얼굴 작업이 놀 때(상태 0) 한 장 켜고, 캐시에 실려
    #     들어오려는 순간(상태 2) 꺼서 다음 장으로 간다. 0xFFFF 가 끝.
    a.movl_d(8, 11, V_PRE)
    a.tst(8, 8)
    a.bt("no_pre")
    a.movl_pc(12, "F_STATE")
    a.movw_at(0, 12)
    a.tst(0, 0)
    a.bf("pre_busy")
    a.movw_at(2, 8)  # r2 = 얼굴 (부호 확장 — 0xFFFF 는 -1)
    a.movi(1, -1)
    a.cmp_eq(2, 1)
    a.bf("pre_next")
    a.movi(1, 0)
    a.movl_to_d(11, 1, V_PRE)
    a.bra("no_pre")
    a.nop()
    a.label("pre_next")
    a.movw_d_r0(8, 2)
    a.mov(3, 0)  # r3 = 표정
    a.bsr("face_write")
    a.nop()
    a.movi(0, 1)
    a.movw_to(12, 0)
    a.bra("no_pre")
    a.nop()
    a.label("pre_busy")
    a.movi(1, 2)
    a.cmp_eq(0, 1)
    a.bf("no_pre")
    a.movi(0, 0)
    a.movw_to(12, 0)
    a.add(8, 4)
    a.movl_to_d(11, 8, V_PRE)
    a.label("no_pre")
    #   ── 꺼져 있으면 아무것도 안 한다
    a.movw_d_r0(11, V_FLAG)
    a.tst(0, 0)
    a.bt_far("done")
    #   ── 포인터가 바뀌었을 때만 다시 그린다 (매 프레임 그리면 비싸다) — 같으면 시간만 센다
    a.movl_d(1, 11, V_TXTP)
    a.movl_d(0, 11, V_DRAWN)
    a.cmp_eq(0, 1)
    a.bt_far("tick")
    a.movl_to_d(11, 1, V_DRAWN)
    #   r8 = 글자. 앞 워드가 표시 프레임 수 → TIMER. 0xFFFF 면 미리 싣기 목록이다
    a.mov(8, 1)
    a.movw_inc(0, 8)
    a.movi(1, -1)
    a.cmp_eq(0, 1)
    a.bf("not_pre")
    a.movl_to_d(11, 8, V_PRE)
    #   🔴 엔진 얼굴 캐시(8 칸 FIFO)를 **비운다** — 씬 앞에 남은 남의 얼굴이 적중으로 잡혀 우리
    #     조합이 안 실리고, 이어 싣는 사이 그 적중분이 밀려나 음성 중 미스가 된다(V19 실측
    #     2026-09-30: 앞 대사의 (0,10)·(1,10) 이 적중 → 나머지 다섯을 싣다 밀려남 → 표정 7 이 안 뜸).
    #     키 8 워드를 0xFFFF(없는 키)로, 커서를 0 으로 — 전부 미스라 목록 순서대로 0~7 칸에 실린다.
    a.movl_pc(1, "RING")
    a.movi(0, -1)
    a.movi(3, 8)
    a.label("ring_clr")
    a.movw_to(1, 0)
    a.add(1, 2)
    a.dt(3)
    a.bf("ring_clr")
    a.movi(0, 0)
    a.movw_to(1, 0)
    a.movi(0, 0)
    a.movw_r0_d(11, V_FLAG)
    a.bra("done")
    a.nop()
    a.label("not_pre")
    a.movw_r0_d(11, V_TIMER)
    a.mov(9, 8)  # r9 = 얼굴·표정 쌍
    a.add(8, 4)
    a.mov(10, 8)  # r10 = 이름
    a.label("skip_name")
    a.movb_at(0, 8)
    a.add(8, 1)
    a.tst(0, 0)
    a.bf("skip_name")  # r8 = 본문 첫 줄
    a.movb_at(0, 8)
    a.tst(0, 0)
    a.bf("draw")
    #   닫는 칸 — 창을 끄고 얼굴을 치운다
    a.movi(0, 0)
    a.movw_r0_d(11, V_FLAG)
    a.mov(9, 11)
    a.add(9, V_NOFACE)
    a.bsr("face_apply")
    a.nop()
    a.bra("done")
    a.nop()
    a.label("draw")
    a.bsr("face_apply")
    a.nop()
    #   버퍼를 지운다 — clear(버퍼, 길이)
    a.movl_pc(4, "BUF")
    a.movl_pc(5, "BUFLEN")
    a.movl_pc(0, "CLEARFN")
    a.jsr(0)
    a.nop()
    #   이름 줄(있으면, 색 14) → 본문 줄들(색 15). r9 = 대상 행, r13 = 남은 줄
    a.movl_pc(9, "BUF")
    a.movi(13, MAX_LINES)
    a.movb_at(0, 10)
    a.tst(0, 0)
    a.bt("line")
    a.mov(4, 9)
    a.movi(5, NAME_COLOR)
    a.mov(6, 10)
    a.bsr("draw_line")
    a.nop()
    a.movl_pc(2, "PITCH")
    a.addr(9, 2)
    a.dt(13)
    a.label("line")
    a.mov(4, 9)
    a.movi(5, BODY_COLOR)
    a.mov(6, 8)
    a.bsr("draw_line")
    a.nop()
    #   NUL 을 지나 다음 줄로 — 비어 있으면 끝
    a.label("nul")
    a.movb_at(0, 8)
    a.add(8, 1)
    a.tst(0, 0)
    a.bf("nul")
    a.movb_at(0, 8)
    a.tst(0, 0)
    a.bt("skip_draw")
    a.dt(13)
    a.bt("skip_draw")
    a.movl_pc(2, "PITCH")
    a.addr(9, 2)
    a.bra("line")
    a.nop()
    #   ── 표시 시간 — 0 이면 다음 칸까지 둔다. 다 되면 창을 끄고 얼굴도 치운다
    a.label("tick")
    a.movw_d_r0(11, V_TIMER)
    a.tst(0, 0)
    a.bt("skip_draw")
    a.add(0, -1)
    a.movw_r0_d(11, V_TIMER)
    a.tst(0, 0)
    a.bf("skip_draw")
    a.movw_r0_d(11, V_FLAG)
    a.mov(9, 11)
    a.add(9, V_NOFACE)
    a.bsr("face_apply")
    a.nop()
    a.bra("done")
    a.nop()
    a.label("skip_draw")
    #   ── 창 + 글자를 **엔진의 스프라이트 등록 함수**로 올린다 — 표에 직접 쓰지 않는다.
    #     🔴 표를 직접 쓰면 안 보인다(2026-09-04 실측): 엔진은 명령을 워크램 객체로 만들어
    #     **슬레이브 SH-2** 가 정렬하고 VBLANK-OUT 에 SCU DMA 로 표를 **통째로 다시 쓴다.**
    #     우리가 END 뒤에 얹은 명령은 그 DMA 가 END 를 다시 놓는 순간 표 밖이 된다.
    #     emit(r4=명령 30B, r5=Z) `0x0606b838` — 객체 풀에서 칸을 받아 DMAC 로 복사하고
    #     큐에 `[0x28, obj, 1, 0]` 을 넣은 뒤 슬레이브를 깨운다. 정렬키 = (Z-near)>>16 이고
    #     **작을수록 위에** 그린다(버킷을 높은 쪽부터 걷는다). near = gbr+104 >> gbr+172.
    a.movl_pc(4, "TPL")
    a.movl_pc(5, "Z_BORDER")
    a.movl_pc(0, "EMIT")
    a.jsr(0)
    a.nop()
    a.movl_pc(4, "TPL")
    a.add(4, 32)
    a.movl_pc(5, "Z_TEXT")
    a.movl_pc(0, "EMIT")
    a.jsr(0)
    a.nop()
    a.label("done")
    a.lds_pr()
    a.pop(0)
    #   ── 밀어낸 에필로그를 그대로
    a.mov(15, 14)
    a.lds_pr()
    for r in (14, 13, 12, 11, 10, 9):
        a.pop(r)
    a.rts()
    a.pop(8)
    #   ── 하위 루틴 셋 (bsr 로 온다 — PR 은 위에서 이미 스택에 있다)
    #   face_write(r2=얼굴, r3=표정): 창 좌표 + 얼굴 + 표정을 엔진 변수에 쓴다. r0·r1 을 쓴다
    a.label("face_write")
    a.movl_pc(1, "F_WINX")
    a.movi(0, WIN_X)
    a.movw_to(1, 0)
    a.movl_pc(1, "F_WINY")
    a.movi(0, WIN_Y >> 1)  # 0xC4 는 imm8 로 부호가 붙는다 — 반을 넣고 왼쪽 시프트
    a.shll(0)
    a.movw_to(1, 0)
    a.movl_pc(1, "F_ID")
    a.movw_to(1, 2)
    a.movl_pc(1, "F_EXPR")
    a.movw_to(1, 3)
    a.rts()
    a.nop()
    #   face_apply(r9 = <얼굴 표정> 쌍): 지금 얼굴과 같으면 그대로. 다르면 보이기/갈기/치우기.
    #     r0~r4 · r12 를 쓴다
    a.label("face_apply")
    a.sts_pr()
    a.movw_at(2, 9)
    a.movw_d_r0(9, 2)
    a.mov(3, 0)
    a.movw_d_r0(11, V_FACE_ID)
    a.cmp_eq(0, 2)
    a.bf("fa_change")
    a.movw_d_r0(11, V_FACE_EXPR)
    a.cmp_eq(0, 3)
    a.bt("fa_ret")
    a.label("fa_change")
    a.mov(0, 2)
    a.movw_r0_d(11, V_FACE_ID)
    a.mov(0, 3)
    a.movw_r0_d(11, V_FACE_EXPR)
    a.movl_pc(12, "F_STATE")
    a.movw_at(4, 12)  # r4 = 지금 상태
    a.movi(1, -1)
    a.cmp_eq(2, 1)
    a.bt("fa_hide")
    a.bsr("face_write")
    a.nop()
    a.movi(0, 1)  # 놀고 있으면 시작(1), 떠 있으면 갈기(4)
    a.tst(4, 4)
    a.bt("fa_set")
    a.movi(0, 4)
    a.bra("fa_set")
    a.nop()
    a.label("fa_hide")
    a.tst(4, 4)
    a.bt("fa_ret")  # 이미 없다
    a.movl_pc(1, "F_ID")
    a.movw_to(1, 2)
    a.movi(0, 4)
    a.label("fa_set")
    a.movw_to(12, 0)
    a.label("fa_ret")
    a.lds_pr()
    a.rts()
    a.nop()
    #   draw_line(r4=대상, r5=색, r6=문자열): 엔진 draw(대상, 행바이트, 문자열, 높이, 스택 색·0·1)
    for name, width in (("draw_line", 12), ("draw_line9", CRED_CELL)):
        a.label(name)
        a.sts_pr()
        a.movi(1, 1)
        a.push(1)
        a.movi(1, 0)
        a.push(1)
        a.push(5)
        a.movi(5, BUF_STRIDE)
        a.movi(7, width)  # 글자 폭 — 엔진 draw 가 이 값으로 **전진량**(전각 폭, 반각 폭/2)을 잡는다
        a.movl_pc(0, "DRAWFN")
        a.jsr(0)
        a.nop()
        a.add(15, 12)  # 밀어 넣은 인자 셋을 걷는다
        a.lds_pr()
        a.rts()
        a.nop()
    stub, addr = a.resolve(
        {
            "VAR": 0,
            "TPL": 0,
            "EMIT": EMIT,
            "Z_BORDER": Z_NEAR + 0x10001,
            "Z_TEXT": Z_NEAR + 1,
            "PCVAR": PCVAR,
            "MAGIC": MAGIC,
            "BUF": BUF,
            "BUFLEN": BUF_LEN,
            "PITCH": BUF_STRIDE * LINE_PITCH,
            "CLEARFN": CLEARFN,
            "DRAWFN": DRAWFN,
            "RING": 0x002F8E24,
            "F_STATE": F_STATE,
            "F_ID": F_ID,
            "F_EXPR": F_EXPR,
            "F_WINX": F_WINX,
            "F_WINY": F_WINY,
        }
    )
    stub = bytearray(stub)
    tail = len(stub)
    var = STUB + tail  # 변수 표 (아래 V_*), 4 정렬
    tpl = var + VAR_LEN
    for name, val in (("VAR", var), ("TPL", tpl)):
        o = addr[name] - STUB
        stub[o : o + 4] = struct.pack(">I", val)
    #   변수 표 — DRAWN 0 은 어떤 포인터와도 다르다. FACE_ID 는 「없음」(0xFFFF)으로 시작해야
    #   첫 얼굴이 뜬다. NOFACE 는 치울 때 face_apply 에 주는 상수 쌍이다.
    stub += struct.pack(">HHIIIHHHH", 0, 0, 0, 0, 0, 0xFFFF, 0, 0xFFFF, 0)
    assert len(stub) == tail + VAR_LEN
    #   창 테두리 · 글자 — **살아 있는 표에서 뜬 값 그대로** 쓴다(글자 쪽은 src 만 우리 버퍼로).
    #     테두리 [20] 264x64 src 0x12000 colr 0x4f60 · 글자 [21] 216x48 src 0x78000 colr 0x4740
    stub += bytes.fromhex("0000000008804f6024002140ffa400300000000000a5006e0000000000000000")
    stub += struct.pack(
        ">8H16x",
        #   ⚠ CMDSRCA 는 **VRAM 안 오프셋 ÷ 8** 이지 절대주소가 아니다
        0x0000,
        0x0000,
        0x0880,
        0x4740,
        (BUF - TAB) // 8,
        (216 // 8) << 8 | 48,
        0xFFB4,
        0x003A,
    )
    assert STUB + len(stub) <= STUB_END, (len(stub), STUB_END - STUB)
    hook = struct.pack(">HHH I", 0xD801, 0x482B, 0x0009, STUB)
    return (
        bytes(stub),
        hook,
        {
            "flag": var + V_FLAG,
            "timer": var + V_TIMER,
            "txtp": var + V_TXTP,
            "drawn": var + V_DRAWN,
            "pre": var + V_PRE,
            "face": var + V_FACE_ID,
            "tpl": tpl,
            "draw_line": a.lbl["draw_line"],
            "draw_line9": a.lbl["draw_line9"],
        },
    )


#   ══ 크레딧 자막 (V20) ═══════════════════════════════════════════════════════
#   🔴 크레딧엔 맵 스크립트도, 대사창 갱신 함수(`HOOK`)도 없다 — 프레임마다 도는 자리가 필요하다.
#     엔진에는 **프레임 태스크 표**(`0x06095E60`, 16 칸)가 있고 VBlank 콜백(`0x060469E4`)이 매 프레임 칸을 차례로
#     `jsr` 한다. 필드·크레딧 **공통** 태스크 `0x06047908` 은 `0x0604BD10` 을 부르는 얇은 래퍼라, 그 호출의
#     **주소 리터럴**(`TASK_LIT`)만 우리 루틴으로 바꾸면 매 프레임 불린다(2026-09-30: 10 스텝에 11 회).
#     우리 루틴은 할 일을 하고 **원래 함수로 꼬리 점프**한다(PR 그대로 — 원래 함수가 래퍼로 돌아간다).
#   ⓘ 크레딧은 **고해상도**(TVMD 하위 3 비트 == 2)이고 필드는 아니다 — 그걸로 크레딧인지 안다.
#     크레딧에 들어오면(처음 본 프레임) 시계를 0 으로 놓고 세며, 나가면 꺼서 다음에 다시 센다.
#   자료: 항목 12B `<시작 u32> <끝 u32> <글자 포인터 u32>`(프레임 = 시계) 앞에 `<개수 u16> <0 u16>`.
#     글자 = `<프레임 0> <x s16> <y s16>` + 이름 `\0`(비움) + 줄들 — **대사창 글자와 같은 꼴**이라
#     `voice_sub.entry` 의 줄 인코딩을 그대로 쓴다. x·y 는 VDP1 로컬 좌표(원점 = 화면 가운데).
#   ⚠ 글자는 **테두리 없이** 글자 스프라이트 하나만 등록한다(대사창이 아니다 — 마스터 09-30).
CRED = 0x06016420  # 죽은 디버그 메뉴 구역 안(`0x0601641C` 부터) — 스텁(`STUB`) 앞
TASK_LIT = 0x06047924  # 태스크 `0x06047908` 이 부르는 함수 주소 리터럴
TASK_ORIG = 0x0604BD10
TVMD = 0x25F80000  # VDP2 화면 모드 — 하위 3 비트 2 = 640 폭(고해상도)
CV_ARM, CV_IDX, CV_X, CV_Y, CV_CLK, CV_TXTP = 0, 2, 4, 6, 8, 12  # 크레딧 변수(작은 것 먼저 — mov.w 변위가 30 까지)
CV_XC, CV_YC = 16, 18  # 글자 스프라이트 오른쪽 아래 — **확대·축소 스프라이트**라 두 점을 준다
CV_HK = 20  # 메인 스레드 등록 루틴이 불린 횟수(계측 — 프레임마다 도는지 본다)
CV_XR, CV_XCR = 24, 26  # 그림이 **오른쪽**일 때(자막은 왼쪽) 쓰는 x — 기본 x·xc 는 그림이 왼쪽일 때(자막은 오른쪽)
CV_MINX, CV_SIDE = 28, 30  # 이번 프레임에 등록된 크레딧 글자들의 XA 최솟값(0x7FFF = 없음) · 래치한 그림 쪽(0 왼쪽 · 1 오른쪽)
CV_LEN = 32
EMIT_LIT = 0x0603EE30  # 크레딧 글자 함수의 `jsr emit` 이 읽는 풀 리터럴(값 = EMIT)
XABUF = 0x0607D1C8  # 크레딧 글자 함수가 방금 등록한 글자 명령의 XA(로컬 x) — 이름 글자가 검은 칸 쪽에 놓이므로 그림 좌우를 가른다
HOOK2 = 0x0603EDE8  # 크레딧 글자 함수 에필로그 — 메인 스레드에서 프레임마다 `emit` 을 ~26 회 부르는 함수의 끝
HOOK2_ORIG = bytes.fromhex("6fe34f266ef66df66cf66bf6")
CRED_ROWS = MAX_LINES  # 이름 줄이 없으니 버퍼(216x48)에 세 줄까지 든다


def _credits_code(a):
    for r in (9, 10, 11, 12, 13):
        a.push(r)
    a.sts_pr()
    a.movl_pc(11, "VARC")
    #   ── 크레딧인가(고해상도) — 아니면 꺼 두고 나간다
    a.movl_pc(1, "TVMD")
    a.movw_at(0, 1)
    a.movi(2, 7)
    a.and_(0, 2)
    a.movi(1, 2)
    a.cmp_eq(0, 1)
    a.bt("c_hi")
    a.movi(0, 0)
    a.movw_r0_d(11, CV_ARM)
    a.movi(1, 0)
    a.movl_to_d(11, 1, CV_TXTP)
    a.bra("c_out")
    a.nop()
    a.label("c_hi")
    a.movw_d_r0(11, CV_ARM)
    a.tst(0, 0)
    a.bf("c_run")
    #   처음 본 프레임 — 시계 0, 항목 0, 글자 없음
    a.movi(0, 1)
    a.movw_r0_d(11, CV_ARM)
    a.movi(0, 0)
    a.movw_r0_d(11, CV_IDX)
    a.movi(1, 0)
    a.movl_to_d(11, 1, CV_CLK)
    a.movl_to_d(11, 1, CV_TXTP)
    a.label("c_run")
    #   ── 시계 +1 → r1, 항목 번호 → r2, 개수 → r4, 표 시작 → r3
    a.movl_d(1, 11, CV_CLK)
    a.add(1, 1)
    a.movl_to_d(11, 1, CV_CLK)
    a.movw_d_r0(11, CV_IDX)
    a.mov(2, 0)
    a.movl_pc(3, "CTAB")
    a.movw_at(4, 3)
    a.add(3, 4)
    a.label("c_scan")
    a.cmp_hs(2, 4)  # 번호 >= 개수 → 없다
    a.bt("c_none")
    a.mov(5, 2)
    a.shll2(5)  # 4i
    a.mov(6, 5)
    a.addr(5, 5)  # 8i
    a.addr(5, 6)  # 12i
    a.addr(5, 3)  # 항목 주소
    a.movl_d(6, 5, 4)  # 끝
    a.cmp_hs(1, 6)  # 시계 >= 끝 → 지나갔다, 다음 항목
    a.bf("c_have")
    a.add(2, 1)
    a.bra("c_scan")
    a.nop()
    a.label("c_have")
    a.movl_at(6, 5)  # 시작
    a.cmp_hs(1, 6)
    a.bf("c_none")  # 아직 안 왔다
    a.movl_d(7, 5, 8)  # 글자 포인터
    a.bra("c_set")
    a.nop()
    a.label("c_none")
    a.movi(7, 0)
    a.label("c_set")
    a.mov(0, 2)
    a.movw_r0_d(11, CV_IDX)
    #   ── 바뀌었나
    a.movl_d(1, 11, CV_TXTP)
    a.cmp_eq(1, 7)
    a.bt("c_same")
    a.movl_to_d(11, 7, CV_TXTP)
    a.tst(7, 7)
    a.bt("c_out")  # 글자가 없어졌다 — 그릴 것 없다
    #   ── 새 글자 — 좌표를 뜨고 버퍼에 굽는다
    a.mov(8, 7)
    a.movw_inc(0, 8)  # 프레임(안 쓴다)
    a.movw_inc(0, 8)
    a.movw_r0_d(11, CV_X)
    a.movw_inc(0, 8)
    a.movw_r0_d(11, CV_Y)
    a.movw_inc(0, 8)
    a.movw_r0_d(11, CV_XC)
    a.movw_inc(0, 8)
    a.movw_r0_d(11, CV_YC)
    a.movw_inc(0, 8)
    a.movw_r0_d(11, CV_XR)
    a.movw_inc(0, 8)
    a.movw_r0_d(11, CV_XCR)
    a.label("c_skipname")
    a.movb_at(0, 8)
    a.add(8, 1)
    a.tst(0, 0)
    a.bf("c_skipname")
    a.movl_pc(4, "BUF")
    a.movl_pc(5, "BUFLEN")
    a.movl_pc(0, "CLEARFN")
    a.jsr(0)
    a.nop()
    a.movl_pc(9, "BUF")
    a.movi(13, CRED_ROWS)
    a.label("c_line")
    a.mov(4, 9)
    a.movi(5, BODY_COLOR)
    a.mov(6, 8)
    a.movl_pc(0, "DRAWLINE")
    a.jsr(0)
    a.nop()
    a.label("c_nul")
    a.movb_at(0, 8)
    a.add(8, 1)
    a.tst(0, 0)
    a.bf("c_nul")
    a.movb_at(0, 8)
    a.tst(0, 0)
    a.bt("c_emit")
    a.dt(13)
    a.bt("c_emit")
    a.movl_pc(2, "PITCH")
    a.addr(9, 2)
    a.bra("c_line")
    a.nop()
    a.label("c_same")
    a.label("c_emit")
    #   🔴 여기서 스프라이트를 **등록하지 않는다** — 이 코드는 VBlank 콜백(인터럽트)에서 돈다. 인터럽트 안에서
    #     `emit` 을 부르면 메인 스레드의 등록(크레딧 글자 프레임당 ~26 회)과 부딪혀 크레딧이 **페이지를 못 넘긴다**
    #     (2026-10-01 실측: 등록만 빼면 진행이 정상). 등록은 아래 `cemit`(메인 스레드)에서 한다.
    a.label("c_out")
    a.lds_pr()
    for r in (13, 12, 11, 10, 9):
        a.pop(r)
    a.movl_pc(1, "ORIG")
    a.jmp(1)
    a.nop()


def _credits_emit_code(a):
    """`cemit` — 크레딧 글자 함수(`HOOK2`) 에필로그 자리에 걸린다(메인 스레드, 프레임마다).

    ISR 쪽 루틴이 정해 둔 글자(`CV_TXTP`)가 있으면 글자 스프라이트 하나를 엔진에 등록한다. 끝은 밀어낸
    에필로그를 그대로(`HOOK` 과 같은 꼴 — r14~r9 를 되살리고 복귀)."""
    a.label("cemit")
    a.push(0)
    a.sts_pr()
    a.movl_pc(11, "VARC")
    a.movl_d(1, 11, CV_HK)
    a.add(1, 1)
    a.movl_to_d(11, 1, CV_HK)
    #   🔴 그림이 어느 쪽인가는 **게임이 알려 준다** — 크레딧 이름 글자는 검은 칸(그림 반대쪽)에 놓인다. 글자 하나하나가 등록될 때
    #     `cwrap` 이 그 XA(로컬 x)의 **최솟값**을 모은다. 이번 프레임에 글자가 있었고 최솟값이 −40 보다 작으면 이름이 왼쪽 =
    #     그림이 오른쪽이다. **글자가 없던 프레임은 쪽을 그대로 둔다**(옛 값으로 튀지 않게 — 마스터 10-01).
    a.movw_d_r0(11, CV_MINX)
    a.movl_pc(1, "SENT")
    a.cmp_eq(0, 1)
    a.bt("ce_keep")
    a.add(0, 40)
    a.cmp_pz(0)
    a.bt("ce_art_l")
    a.movi(0, 1)
    a.bra("ce_store")
    a.nop()
    a.label("ce_art_l")
    a.movi(0, 0)
    a.label("ce_store")
    a.movw_r0_d(11, CV_SIDE)
    a.movl_pc(0, "SENT")
    a.movw_r0_d(11, CV_MINX)
    a.label("ce_keep")
    a.movl_d(1, 11, CV_TXTP)
    a.tst(1, 1)
    a.bt("ce_out")
    a.movl_pc(4, "TPLC")
    a.movw_d_r0(11, CV_SIDE)
    a.tst(0, 0)
    a.bt("ce_left_art")
    a.movw_d_r0(11, CV_XR)
    a.movw_r0_d(4, 12)
    a.movw_d_r0(11, CV_XCR)
    a.movw_r0_d(4, 20)
    a.bra("ce_y")
    a.nop()
    a.label("ce_left_art")
    a.movw_d_r0(11, CV_X)
    a.movw_r0_d(4, 12)
    a.movw_d_r0(11, CV_XC)
    a.movw_r0_d(4, 20)
    a.label("ce_y")
    a.movw_d_r0(11, CV_Y)
    a.movw_r0_d(4, 14)
    a.movw_d_r0(11, CV_YC)
    a.movw_r0_d(4, 22)
    a.movl_pc(5, "Z_TEXT")
    a.movl_pc(0, "EMIT")
    a.jsr(0)
    a.nop()
    a.label("ce_out")
    a.lds_pr()
    a.pop(0)
    a.mov(15, 14)
    a.lds_pr()
    for r in (14, 13, 12, 11, 10, 9):
        a.pop(r)
    a.rts()
    a.pop(8)


def _credits_wrap_code(a):
    """`cwrap` — 크레딧 글자 함수가 글자 하나를 등록할 때(`emit` 호출 리터럴) 거쳐 가는 껍데기.

    방금 채운 글자 명령의 XA 를 읽어 이번 프레임의 **최솟값**(`CV_MINX`)에 모으고 원래 `emit` 으로 점프한다
    (인자·PR·스택은 그대로). r0~r2 만 쓴다 — 이 호출 뒤 호출자는 r0~r3 를 다시 채운다."""
    a.label("cwrap")
    a.movl_pc(1, "XABUF")
    a.movw_at(1, 1)
    a.movl_pc(2, "VARC")
    a.movw_d_r0(2, CV_MINX)
    a._e(0x3017)  # cmp/gt r1,r0   T = r0 > r1  (부호 있음) — 지금 최솟값이 이번 값보다 크면
    a.bf("cw_skip")
    a.mov(0, 1)
    a.label("cw_skip")
    a.movw_r0_d(2, CV_MINX)
    a.movl_pc(0, "EMIT")
    a.jmp(0)
    a.nop()


def build_credits(draw_line, table=b""):
    """`(자리 CRED 에 쓸 바이트, {이름: 주소})` — 코드 · 풀 · 변수 · 글자 명령 · 표.

    `table` 은 `<개수> <0>` + 항목 12B 들 + 글자들(포인터는 아래 `ctab` 기준으로 채워 넘긴다 —
    `voice_credits.blob(ctab)`). 코드 길이가 값에 안 걸려서 두 번 조립한다(첫 번엔 자리만 잰다).
    """

    def asm(pool):
        a = Asm(CRED)
        _credits_code(a)
        _credits_emit_code(a)
        _credits_wrap_code(a)
        code, addr = a.resolve(pool)
        return code, addr, a.lbl

    base_pool = {
        "VARC": 0,
        "TVMD": TVMD,
        "CTAB": 0,
        "BUF": BUF,
        "BUFLEN": BUF_LEN,
        "CLEARFN": CLEARFN,
        "PITCH": BUF_STRIDE * CRED_PITCH,
        "DRAWLINE": draw_line,
        "EMIT": EMIT,
        "Z_TEXT": Z_NEAR + 1,
        "ORIG": TASK_ORIG,
        "TPLC": 0,
        "XABUF": XABUF,
        "SENT": 0x7FFF,
    }
    code, _, _ = asm(base_pool)
    var = CRED + len(code)
    var += -var % 4
    tplc = var + CV_LEN
    ctab = tplc + 32
    pool = dict(base_pool, VARC=var, CTAB=ctab, TPLC=tplc)
    code, addr, lbl = asm(pool)
    out = bytearray(code)
    out += b"\x00" * (var - CRED - len(out))
    out += b"\x00" * CV_LEN
    #   글자 명령 하나(32B) — 대사창 글자와 같되 **확대·축소 스프라이트**(`0x0001`, 두 점 지정)다. 좌표는 매 프레임 덮어쓴다
    out += struct.pack(
        ">8H16x", 0x0001, 0x0000, 0x0880, 0x4740, (BUF - TAB) // 8, (216 // 8) << 8 | 48, 0, 0
    )
    assert len(out) == ctab - CRED
    out += table
    assert CRED + len(out) <= STUB - 0x140, (len(out), STUB - 0x140 - CRED)  # 끝 0x140B 는 `patch_ui_center.WRAP`·`WRAP2` 자리
    return bytes(out), {"ctab": ctab, "var": var, "tplc": tplc, "cred": CRED, "cemit": lbl["cemit"], "cwrap": lbl["cwrap"]}


BASE = 0x06004000  # `/0.BIN` 적재 주소
#   ⚠ 원본이 이래야 쓴다 — 스텁 자리는 디버그 메뉴 처리기 머리(`mov.l r8,@-r15 …`), 훅 자리는
#     에필로그 `mov r14,r15 · lds.l @r15+,pr · mov.l @r15+,r14 …`, 디버그 입구는
#     `mov.b @r1,r1 · extu.b · tst · bt`. 다르면 자리를 잘못 짚은 것이다.
STUB_ORIG = bytes.fromhex("2f862f962fa62fb6")
HOOK_ORIG = bytes.fromhex("6fe34f266ef66df66cf6")
GATE_ORIG = bytes.fromhex("8952")
GATE_NEW = bytes.fromhex("a052")  # 같은 변위, 무조건 분기


def patch(data, table_fn=None):
    """`/0.BIN` 에 스텁 + 훅을 넣는다 → 새 bytes. 크기 불변.

    스텁은 디버그 메뉴 코드 자리에 들어가므로 **그 메뉴의 입구(`DEBUG_GATE`)를 먼저 막는다** —
    타이틀 조합키로 켜지는 개발용 메뉴라 게임엔 없어도 된다.
    `table_fn(ctab)` 이 있으면 **크레딧 자막**(V20)도 넣는다 — 표를 `ctab` 자리 기준으로 만들어 돌려준다.
    """
    out = bytearray(data)
    stub, hook, where = build()

    def put(addr, blob, expect):
        off = addr - BASE
        assert 0 <= off and off + len(blob) <= len(out), hex(addr)
        assert out[off : off + len(expect)] == expect, f"{addr:#x} 가 예상과 다르다"
        out[off : off + len(blob)] = blob

    put(DEBUG_GATE, GATE_NEW, GATE_ORIG)
    put(STUB, stub, STUB_ORIG)
    put(HOOK, hook, HOOK_ORIG)
    if table_fn is not None:
        _, ca = build_credits(where["draw_line9"])
        blob, ca = build_credits(where["draw_line9"], table_fn(ca["ctab"]))
        put(CRED, blob, b"")
        put(TASK_LIT, struct.pack(">I", CRED), struct.pack(">I", TASK_ORIG))
        #   등록은 메인 스레드에서 — 크레딧 글자 함수 에필로그 12B 를 `mov.l @(1,pc),r8 · jmp @r8 · nop · nop · 주소` 로
        put(HOOK2, struct.pack(">HHHHI", 0xD801, 0x482B, 0x0009, 0x0009, ca["cemit"]), HOOK2_ORIG)
        #   글자 하나를 등록하는 `emit` 호출의 풀 리터럴 → `cwrap`(XA 최솟값을 모은다)
        put(EMIT_LIT, struct.pack(">I", ca["cwrap"]), struct.pack(">I", EMIT))
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", help="스텁을 이 파일로 쓴다")
    ap.add_argument("--hook", help="훅 10바이트를 이 파일로 쓴다")
    a = ap.parse_args()
    stub, hook, where = build()
    print(f"스텁 {len(stub)}B @ {STUB:#x}   훅 {len(hook)}B @ {HOOK:#x}")
    print(
        f"  플래그 {where['flag']:#x}   미리싣기 {where['pre']:#x}   명령 템플릿 {where['tpl']:#x}"
    )
    print("  스텁:", stub.hex())
    print("  훅  :", hook.hex())
    if a.bin:
        with open(a.bin, "wb") as f:
            f.write(stub)
    if a.hook:
        with open(a.hook, "wb") as f:
            f.write(hook)


if __name__ == "__main__":
    main()
