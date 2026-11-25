"""음악 이어 재생(마스터 11-20 「음악 겹침·중단」 — 관리자 승인 (b)·②) — 뱅크 0x73 꼬리.

🔴 왜: 컨테이너 짝 교체(`splitload` — 한 구역 컨테이너가 4뱅크를 넘어 쪼갠 씬)는 CD_READ 라 CD-DA 를 멈춘다. 종전엔 교체를 마친 뒤 엔진의 같은 곡 루틴(`$6856`)을
다시 불러 **곡을 처음부터** 다시 틀었고, 그것도 곡 명령(`$4B` < `$10`·`$4C` = 0)이 남아 있을 때만이었다.
실측 11-20: ① 씬 57 입장 — 스크립트 PLAY 직후 CD_READ ×2, 둘째 PLAY 호출 스택이 `splitload`. ② 루디아 마을 안 이동(곡이 16초 흐른 뒤) — 교체 READ 뒤 **PLAY 가 아예 없다**:
`$4B` 가 곡 번호가 아니라 엔진이 바꿔 둔 값(0x11 · `$4C` = 1)이라 다시 걸기 조건이 거짓 → 곡이 그냥 멎는다(마스터 「음악 중단」). 원판은 컨테이너가 하나라 교체가 없어 CD 호출 0.

동작(곡 명령 변수에 기대지 않고 **CD 위치로** 판단한다):
  · `savepos` — 교체(CD_READ) **직전**(첫 교체): BIOS `CD_SUBQ`(`$E01E`, 10B 를 `($FA)` 로 받는다)로 오디오 상태·절대 MSF 를 읽는다. 재생 중이면 위치가 든 곡 표 항목(엔진 `$691A~$697A`, 16곡)을
    찾아 끝 MSF·모드를 같이 저장한다. 방금 곡 명령을 건 직후(`$4B` < `$10`, `$4C` = 0)면 **그 곡의 범위 안일 때만** 믿는다(서브코드가 아직 옛 곡 위치일 수 있다) — 아니면 저장 안 함.
  · `replay` — 교체를 마친 뒤: 저장이 있으면 **그 위치부터** 곡 끝까지 `CD_PLAY`(`$E012`). 없으면 종전대로(곡 명령이 남아 있으면 엔진 `$6856` 으로 처음부터).
  🔴 `$76`(11-21 — 마스터 「루디아 겹침 여전 · 계단 오르내릴 때 처음부터」): 엔진은 컨테이너를 CD 로 읽을 때마다(뱅크 0x68 `$5716`) CD 곡 상태 `$76` 을 `FF`(안 흐름)로 지운다 —
  읽기가 CD-DA 를 죽이니 원판에선 맞는 말이다. 우리는 교체 뒤 CD 를 되살리는데 `$76` 은 `FF` 로 남았다. 그래서 ① 다음 씬 입장(`$6425`)의 「같은 곡이면 그대로」 판정
  (`($76 & $1F) == 곡`)이 늘 거짓 → SEARCH+PLAY 로 처음부터(계단마다), ② 성 → 마을(PSG) 입장(`$6466`)이 `$76` 비트7 을 보고 CD 페이드(명령 0x80)를 건너뜀 → 되살린 성 곡이
  마을 곡 위에 그대로(겹침). 실측: 마스터 상태 mc3.005539(마을 씬 12 · `$76` = FF · CD 재생 중 · 페이더 명령 0) · mc3/4/5.213701(씬 16 · `$76` = FF · 곡 머리 3~14초).
  고침: `savepos` 가 `$76` 을 떠 두고 `replay` 가 CD 를 되살린 뒤 되돌린다 — 교체가 엔진에 안 보인다.
  호출은 전부 먼 호출(`JSR $4FD8` + 뱅크 인자 + 주소) → 이 뱅크가 `$8000`(MPR4)에 걸리고 MPR3 은 0x72 라 엔진 표(뱅크 0x69)는 MPR3 을 잠깐 0x69 로 건다.
"""

import hook
import winmask

BANK = 0x73
WINDOW = 0x8000
ORG = winmask.TBL + winmask.TOTAL_LEN  # winmask 끝 바로 뒤
OFF = ORG - WINDOW
CODE_LEN = 321  # 코드 + 변수 길이 이상(꼬리 안: winmask 와 합쳐 1280B 이하)

CD_SUBQ = 0xE01E
CD_PLAY = 0xE012
CD_PAUSE = 0xE018
LOAD_TAIL_A = 0x7D55  # 원판 LOAD 성공 꼬리 첫 호출(뱅크 0x69)
LOAD_TAIL_B = 0x4240  # 둘째 호출(상주 구역)
LOAD_SITE = 0x1D3D  # 뱅크 0x69 +0x1D3D(논리 `$7D3D`) — `20 55 7D 20 40 42` 6B 를 먼 호출로 바꾼다
LOAD_SITE_ORIG = bytes.fromhex("2055 7d20 4042".replace(" ", ""))
ENG_BANK = 0x69
ENG_SAME_SONG = 0x6856  # 엔진 「같은 곡」 루틴(처음부터)
TBL_START = (0x691A, 0x692A, 0x693A)  # 곡별 시작 MSF(F8·F9·FA)
TBL_END = (0x694A, 0x695A, 0x696A, 0x697A)  # 곡별 끝 MSF 3B + 모드(FC·FD·FE·FF)
NSONG = 0x10
ENG_CD_STATE = 0x76  # 엔진 영 페이지 — CD 곡 상태(하위 5비트 곡 · 비트7 재생 예약 · 비트6 PSG 밑에서 페이드됨 · `FF` = 안 흐름)
STATUS_PLAYING = 0x00  # CD_SUBQ 버퍼 +0 = 오디오 상태(0 = 재생 중 · 2 = 일시정지 · 3 = 정지 — mednafen `DoNEC_PCE_READSUBQ`)


def _asm(buf_addr: int = 0) -> "hook.Asm":
    a = hook.Asm(ORG)
    # ── savepos ─────────────────────────────────────────────
    a.label("savepos")
    # 🔴 엔진 CD 곡 상태 — 컨테이너 로드(`$5716`)가 `FF` 로 지우기 전에 떠 둔다(아래 `rp_rest`)
    a.op("LDA", "zp", ENG_CD_STATE)
    a.op("STA", "abs", "s76")
    a.op("STZ", "abs", "valid")
    a.op("TMA", "tma", 3)
    a.op("PHA")
    a.op("LDA", "imm", ENG_BANK)
    a.op("TAM", "tam", 3)  # `$6000` 창 = 엔진 뱅크 0x69(곡 표)
    a.op("LDA", "imm", buf_addr & 0xFF)  # 버퍼 주소 = 이 뱅크의 변수(`$8000` 창)
    a.op(
        "STA", "zp", 0xFA
    )  # 🔴 BIOS `CD_SUBQ`(`$EFBF`)는 10B 를 `($FA)` 로 받는다(`$EA3B` 데이터 인 루프 — `$F8/$F9` 는 길이)
    a.op("LDA", "imm", buf_addr >> 8)
    a.op("STA", "zp", 0xFB)
    a.op("JSR", "abs", CD_SUBQ)
    a.op("LDA", "abs", "buf")
    a.op("CMP", "imm", STATUS_PLAYING)
    a.op("BNE", "rel", "sp_out")
    # 방금 곡 명령을 건 직후면 그 곡의 범위만 믿는다
    a.op("LDA", "zp", 0x4B)
    a.op("CMP", "imm", NSONG)
    a.op("BCS", "rel", "scan")
    a.op("LDA", "zp", 0x4C)
    a.op("BNE", "rel", "scan")
    a.op("LDX", "zp", 0x4B)
    a.op("JSR", "abs", "chk")
    a.op("BCC", "rel", "take")
    a.op("BRA", "rel", "sp_out")
    a.label("scan")
    a.op("CLX")  # LDX #0 보다 1B 짧다(11-22 — 뱅크 0x73 은 4B 가 모자라 `$76` 무효화를 넣느라 짠다)
    a.label("scan_lp")
    a.op("JSR", "abs", "chk")
    a.op("BCC", "rel", "take")
    a.op("INX")
    a.op("CPX", "imm", NSONG)
    a.op("BNE", "rel", "scan_lp")
    a.op("BRA", "rel", "sp_out")
    a.label("take")
    for src, dst in (("buf7", "msf0"), ("buf8", "msf1"), ("buf9", "msf2")):
        a.op("LDA", "abs", src)
        a.op("STA", "abs", dst)
    for i in range(4):
        a.op("LDA", "absx", TBL_END[i])
        a.op("STA", "abs", f"end{i}")
    a.op("INC", "abs", "valid")
    a.label("sp_out")
    a.op("PLA")
    a.op("TAM", "tam", 3)
    a.op("RTS")
    # chk — 곡 X 의 [시작, 끝) 안에 버퍼의 절대 MSF 가 드나. 안이면 C=0, 밖이면 C=1(BCD 분·초·프레임 사전식 비교)
    a.label("chk")
    a.op("LDA", "abs", "buf7")
    a.op("CMP", "absx", TBL_START[0])
    a.op("BCC", "rel", "chk_no")
    a.op("BNE", "rel", "chk_hi")
    a.op("LDA", "abs", "buf8")
    a.op("CMP", "absx", TBL_START[1])
    a.op("BCC", "rel", "chk_no")
    a.op("BNE", "rel", "chk_hi")
    a.op("LDA", "abs", "buf9")
    a.op("CMP", "absx", TBL_START[2])
    a.op("BCC", "rel", "chk_no")
    a.label("chk_hi")
    a.op("LDA", "abs", "buf7")
    a.op("CMP", "absx", TBL_END[0])
    a.op("BCC", "rel", "chk_yes")
    a.op("BNE", "rel", "chk_no")
    a.op("LDA", "abs", "buf8")
    a.op("CMP", "absx", TBL_END[1])
    a.op("BCC", "rel", "chk_yes")
    a.op("BNE", "rel", "chk_no")
    a.op("LDA", "abs", "buf9")
    a.op("CMP", "absx", TBL_END[2])
    a.op("BCS", "rel", "chk_no")
    a.label("chk_yes")
    a.op("CLC")
    a.op("RTS")
    a.label("chk_no")
    a.op("SEC")
    a.op("RTS")
    # ── replay ──────────────────────────────────────────────
    a.label("replay")
    a.op("PHX")
    a.op("PHY")
    a.op("LDA", "zp", 0x12)
    a.op("PHA")
    a.op("LDA", "zp", 0x13)
    a.op("PHA")
    a.op("LDA", "abs", "valid")
    a.op("BEQ", "rel", "rp_old")
    a.op("STZ", "abs", "valid")
    a.op("LDA", "abs", "msf0")
    a.op("STA", "zp", 0xF8)
    a.op("LDA", "abs", "msf1")
    a.op("STA", "zp", 0xF9)
    a.op("LDA", "abs", "msf2")
    a.op("STA", "zp", 0xFA)
    a.op("LDA", "imm", 0x40)  # 시작 모드 = MSF(엔진 `$68A4` 와 같다)
    a.op("STA", "zp", 0xFB)
    a.op("LDA", "abs", "end0")
    a.op("STA", "zp", 0xFC)
    a.op("LDA", "abs", "end1")
    a.op("STA", "zp", 0xFD)
    a.op("LDA", "abs", "end2")
    a.op("STA", "zp", 0xFE)
    a.op("LDA", "abs", "end3")
    a.op("STA", "zp", 0xFF)  # A = 끝 모드 그대로 부른다(엔진도 마지막 `LDA $FF` 직후)
    a.op("JSR", "abs", CD_PLAY)
    a.op("BRA", "rel", "rp_rest")
    # 저장이 없으면 종전대로 — 곡 명령이 남아 있을 때만 엔진 같은 곡 루틴(처음부터)
    a.label("rp_old")
    a.op("LDA", "zp", 0x4B)
    a.op("CMP", "imm", NSONG)
    a.op("BCS", "rel", "rp_pend")
    a.op("LDA", "zp", 0x4C)
    a.op("BNE", "rel", "rp_pend")
    a.op("TMA", "tma", 3)
    a.op("PHA")  # 원래 MPR3(0x72 — 먼 호출이 건 값)
    a.op("LDA", "imm", ENG_BANK)
    a.op("TAM", "tam", 3)
    a.op("JSR", "abs", ENG_SAME_SONG)
    a.op("PLA")
    a.op("TAM", "tam", 3)
    a.op("BRA", "rel", "rp_rest")
    # CD 를 못 되살렸다(교체 전에도 안 흐르고 있었다) — 엔진 상태는 로드가 둔 `FF`(안 흐름) 그대로가 맞다. 단 「재생 예약」(비트7)이 걸려 있었으면 되돌린다(엔진이 곧 PLAY 를 건다)
    a.label("rp_pend")
    a.op("LDA", "abs", "s76")
    a.op("BPL", "rel", "rp_out")
    # 🔴 11-21 엔진 CD 곡 상태(`$76`)를 교체 전 값으로 — CD 를 되살렸으니 엔진도 「그 곡이 흐르는 중」으로 알아야 한다(머리말 「`$76`」)
    a.label("rp_rest")
    a.op("LDA", "abs", "s76")
    a.op("STA", "zp", ENG_CD_STATE)
    a.label("rp_out")
    a.op("PLA")
    a.op("STA", "zp", 0x13)
    a.op("PLA")
    a.op("STA", "zp", 0x12)
    a.op("PLY")
    a.op("PLX")
    a.op("RTS")
    # ── loadhook — 원판 LOAD 함수(뱅크 0x69 `$7D2E`)의 성공 꼬리 `JSR $7D55 · JSR $4240` 자리 ──────────
    # 원판은 게임 안 LOAD 때 CD 를 멈추지 않는다(실측 11-20: 슬롯 2 동굴 → 슬롯 3 마을 LOAD 에서 CD 호출 0건, 동굴 CD 곡이 그대로 흐르는 채 마을 PSG 곡이 켜진다 — 원판도 겹침).
    # 새 장면이 CD 곡을 쓰면 스크립트가 LOAD 뒤에 다시 건다(슬롯 3→2 실측: LOAD 뒤 SEARCH+PLAY). 여기서 먼저 멈추면 PSG 장면에 옛 CD 곡이 안 남는다.
    a.label("loadhook")
    a.op("JSR", "abs", CD_PAUSE)
    # 🔴 CD 를 멈췄으니 엔진의 「곡 흐르는 중」 상태도 무효로 — 안 그러면 같은 슬롯·같은 곡을 다시 LOAD 했을 때 엔진이 「이미 흐름」으로 보고 다시 안 틀어 침묵한다(마스터 11-20 「2번세이브 로드 후 다시 2번세이브를 로드하면 음악이 끊긴다」, 실측: `$76` 이 07 인 채 CD_PAUSE 만 돎)
    a.op("LDA", "imm", 0xFF)
    a.op("STA", "zp", ENG_CD_STATE)
    a.op("TMA", "tma", 3)
    a.op("PHA")
    a.op("LDA", "imm", ENG_BANK)
    a.op("TAM", "tam", 3)  # 원래 호출은 뱅크 0x69 가 `$6000` 에 걸린 채 불렀다
    a.op("JSR", "abs", LOAD_TAIL_A)
    a.op("JSR", "abs", LOAD_TAIL_B)
    a.op("PLA")
    a.op("TAM", "tam", 3)
    a.op("RTS")
    # ── 변수 ───────────────────────────────────────────────
    for nm in ("valid", "msf0", "msf1", "msf2", "end0", "end1", "end2", "end3"):
        a.label(nm)
        a.data(b"\0")
    a.label("buf")
    a.data(b"\0")
    a.label("buf1")
    a.data(b"\0\0\0\0\0\0")
    a.label("buf7")
    a.data(b"\0")
    a.label("buf8")
    a.data(b"\0")
    a.label("buf9")
    a.data(b"\0")
    a.label("s76")
    a.data(b"\xff")
    return a


def _final() -> "hook.Asm":
    return _asm(_asm().labels["buf"])


def far_addr(name: str) -> int:
    return _final().labels[name]


def far_call(name: str) -> bytes:
    """먼 호출 6B(`JSR $4FD8` + 인자 뱅크 + 주소)."""
    return b"\x20\xd8\x4f" + bytes([BANK - 0x68 - 1]) + far_addr(name).to_bytes(2, "little")


def code() -> bytes:
    b = _final().bytes()
    assert len(b) <= CODE_LEN, (len(b), CODE_LEN)
    return b
