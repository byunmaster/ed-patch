"""나레이션 게이트($C04C) 전수 — 씬 블록 이벤트 코드에서 ON/OFF 경로의 메시지 표시를 가른다.

나레이션 값은 본 프로그램이 아니라 **씬 블록 안**(`$A000` 적재)에서 읽힌다(policy.md
「분기를 찾았다(10-05 넷째)」). 흔한 꼴:

    LDA $C04C · BEQ off · [JSR $5815 +4B 음성] · LDX lo · LDY hi · JSR $5BD7(타이머) · BRA 끝
    off: LDA #lo · STA $10 · LDA #hi · STA $11 · JSR $5B76/$5B5B (메시지)

⇒ ON 이면 음성만 내고 창을 건너뛰고, OFF 면 창만 띄운다. 마스터 판정(10-05): **나레이션과 무관하게
자막**. `patch_block` 은 ON 경로 타이머 호출(`LDX #lo · LDY #hi · JSR $5BD7`)의 **JSR 목적지 2B 만**
상주부(`resident`, 본 프로그램 뱅크 0x6B 꼬리 `$9E60~`) 입구로 바꾼다. 상주부는
  ① X·Y(원래 타이머)와 시각을 적고 ② 반환 주소부터 훑어 **OFF 경로의 메시지 적재**
     (`A9 lo 85 10 A9 hi 85 11` + `JSR/JMP $5B76·$5B5B·$5B06·$5B0B`)를 찾아 그 메시지를 띄우고
  ③ **원래 타이머 − 읽은 시간**만큼 `$5BD7` 로 기다린다(0 이하면 안 기다린다).
읽은 시간은 플레이 시간 시계(`$C1B3` 초 · `$C1B2` 초 안 프레임, 뱅크 0x74 — 장면 코드가 돌 때 MPR6).
낭독 한 줄기에 줄이 여럿인 장면(017: 12.5초 + 84.5초 ≈ 음성 102초)에서 줄 박자가 원판 ON 과 같게 간다.
⚠ 옛 판(10-05 다섯째)은 메시지 뒤 「AD_STAT 로 음성 끝까지」 기다렸다 — 낭독 장면에선 첫 줄에서 낭독
전체가 끝날 때까지 서 버려 다음 줄이 음성 뒤에 떴다(싱크 결함). 블록 꼬리에 스텁을 붙이는 안은
컨테이너 슬롯이 빠듯해 접었다(006 은 6B, 034 는 38B 넘쳤다 — 실측).
입구는 셋: 훑어 처음 만난 메시지 · 하나 건너뛰기(063 — ON 메시지가 먼저 걸린다) · 2쪽부터(198).
**어느 입구를 쓸지는 빌드가 같은 훑기를 파이썬으로 돌려 정하고**, 기대한 메시지와 안 맞으면 빌드가 죽는다.

스캔(`main`)의 입력은 `containers.py --dump`·`messages.py` 의 파생물이다. 출력에 원문 머리가
들어가므로 `work/review/` 로만 쓴다(커밋 금지).

    python3 games/pce-ed1/tools/narration_gates.py      # → work/review/narration_gates.jsonl + 요약
"""

import glob
import json
import re
from pathlib import Path

import common
import hook
from hook import Asm

BASE = 0xA000  # 씬 블록 적재 주소(블록 오프셋 = 주소 - BASE)
GATE = b"\xad\x4c\xc0"  # LDA $C04C
VOICE = b"\x20\x15\x58"  # JSR $5815 — AD_CPLAY 스트리밍 시작(인라인 4B)
TIMER = b"\x20\xd7\x5b"  # JSR $5BD7 — X+Y*256 프레임 대기
# 메시지 표시: LDA #lo · STA $10 · LDA #hi · STA $11 · (JSR $5B76 | JSR $5B5B | JMP $5B06 | JMP $5B0B)
MSG = re.compile(
    rb"\xa9(.)\x85\x10\xa9(.)\x85\x11(?:\x20\x76\x5b|\x20\x5b\x5b|\x4c\x06\x5b|\x4c\x0b\x5b)",
    re.DOTALL,
)

TERM_BYTES = (0, 6, 7)  # 메시지 종료 바이트(messages.TERM)
TIMER_AT = re.compile(rb"\xa2(.)\xa0(.)\x20\xd7\x5b", re.DOTALL)  # LDX #lo · LDY #hi · JSR $5BD7
SHOW_5B_TAILS = (b"\x20\x5b\x5b", b"\x4c\x06\x5b")  # 나머지(JSR $5B76 · JMP $5B0B)는 $5B76 꼴
SHOW_76, SHOW_5B = 0x5B76, 0x5B5B  # 메시지 표시 — `$10/$11` = 메시지 주소
WAIT_FRAMES = 0x5BD7  # 게임의 코루틴 대기(X+Y×256 프레임, 0 이면 65536)
CLOCK_F, CLOCK_S = 0xC1B2, 0xC1B3  # 플레이 시간: 초 안 프레임(0~59) · 초(하위 바이트) — ⚠ 장면 연출 중엔 멈춘다(10-12 실측). 시간은 프레임 카운터(`FRAMECNT`)로 잰다
FRAMECNT = hook.FRAMECNT  # IRQ1 트램펄린이 매 VBlank 에 올리는 16비트 카운터(하위·상위) — `inst` 가 처음 쓸 때 RAM 에서 꽂는다
TICK_ADDR, IRQ_SITE = hook.TICK_ADDR, hook.IRQ_SITE
RES_ORG = 0x9E56  # 상주부 — 뱅크 0x6B 꼬리 FF 패딩 `$9E56~$9FFF`(426B)
RES_END = 0xA000
# 🔴 뱅크 0x6A 꼬리 FF 24B(`$6B5C`)는 쓰지 않는다 — 게임이 실행 중에 쓰는 버퍼였다(10-06 실측: 부팅 뒤 RAM 에
#    00~0D 목록이 들어 있었다). 그래서 런타임 훑기(표가 필요했다)를 버리고 호출 자리에 인라인으로 싣는다.
PAT = (
    (0, 0xA9),
    (2, 0x85),
    (3, 0x10),
    (4, 0xA9),
    (6, 0x85),
    (7, 0x11),
)  # 메시지 적재 꼴(빌드가 찾는다)
FLAG_PAGE2 = 0x01  # 인라인 플래그 — OFF 메시지의 첫 쪽 넘김(05) 다음부터 띄운다
FLAG_VOICE0 = 0x02  # 인라인 플래그 — 쪽 마감 표의 0 을 **음성 재생이 실제로 시작된 때**(`PLAYSTART`)에 묶는다. 아직 안 시작했으면 시작을 기다린 뒤 창을 연다
# ── ON 자동 넘김(마스터 10-06 「on 일 때는 음성에 맞춰 자동으로 넘어가고」) ──────────────────────
# 대사 엔진(뱅크 0x6C)의 쪽 대기 루프는 매 프레임 `LDA $CF1A`(버튼) · `AND #$60` 으로 넘길지 정한다.
# 그 `LDA $CF1A` 넷을 같은 길이의 `JSR AUTO_ORG` 로 바꾸고, 자막 모드(`AUTO_FLAG`)일 때 플레이 시계가
# **지금 쪽의 마감**(`AUTO_TL`·`AUTO_TH`)을 넘으면 버튼 값(`$20`)을 돌려준다 — 그 밖의 메시지는 원래 그대로.
# 마감은 쪽마다 **메시지 바이트 수**(글자 2B · 줄바꿈 등 제어 1B — 사실상 글자 수)에 비례해 원래 타이머를
# 나눈다(마지막 쪽 = 타이머 끝). 쪽이 넘어갈 때마다(자동이든 손이든) 훅이 MPR4 에 뱅크 0x6B 를 잠깐 걸어 상주부 `npage` 로
# 다음 쪽 마감을 구한다 — 진행 상태는 상주부 자기 뱅크에 두고, 훅 쪽엔 표시·마감 3B 만 둔다.
# 🔴 처음엔 표를 워크 RAM `$22BC~` 에 뒀다 — 09-07 에 「쓰기 0회」로 잰 구간인데, **BIOS(`$F2DD`·`$F2E3`)가
#    `$22BD` 를 음성 재생 중에 수백 번 쓴다**(10-06 실측, 쪽 번호가 0 으로 되돌아가 잡혔다). 그 구간은 BIOS
#    작업 영역과 겹친다 — 워크 RAM 은 쓰지 않는다.
AUTO_ORG = (
    0x5FBC  # 뱅크 0x68 꼬리 FF 패딩 `$5FBC~$5FFF`(68B) — 대사 엔진이 돌 때도 `$4000` 창에 있다
)
AUTO_END = 0x6000
AUTO_SITES = (0x6BB3, 0x6BE6, 0x6C35, 0x6D38)  # 뱅크 0x6C — 쪽 대기 · 끝 대기의 `LDA $CF1A`
AUTO_FLAG, AUTO_TL, AUTO_TH = (
    0x5FFD,
    0x5FFE,
    0x5FFF,
)  # 훅 뒤 3B — 자막 모드 · 지금 쪽 마감(프레임 카운터 값, 하위·상위)
PAD = 0xCF1A  # 버튼 트리거
SPEED = 0xC051  # 글자 찍는 속도(0~3 → 글자당 1·3·5·0 프레임, 표 `$5B8A`) — 3 = 즉시


# 씬 → {게이트 순번(블록 안 `LDA $C04C` 의 몇 번째인가): 규칙}. 순번은 번역해도 안 바뀐다(코드는
# 블록 앞쪽이고 대본 길이가 코드 바이트를 안 바꾼다) — 그래도 `patch_block` 이 꼴을 다시 확인한다.
#   single     ON 경로에 타이머가 꼭 하나 → 그 자리에 자막
#   all        ON 경로가 플래그로 두 음성 중 하나를 고른다(갈래마다 타이머 하나) → 둘 다
#   last       타이머가 이어서 둘 — 앞 것은 연출(BSR) 박자라 그대로, 마지막 자리에 자막
#   last_page2 ON 이 메시지 1쪽(기도문)을 이미 띄운다 → 마지막 타이머 자리에 OFF 메시지의 **2쪽부터**
#   raias      원판 실수: BEQ +0x14 가 OFF 에서도 설교를 건너뛴다. 이 장면은 음성이 설정과 무관하게
#              나가므로 OFF 도 **ON 경로로** 흘린다(BEQ +0x00) — 메시지만 띄우고 음성을 안 기다리면
#              빨리 넘길 때 다음 이벤트가 음성을 끊는다(실측, 같은 충돌로 굳은 적도 있다)
#   single_pre single 인데 OFF 경로가 메시지 앞에 연출 호출(≤10B — `JSR $5BCD`·`JSR $645E` 류)을 먼저 한다.
#              ON 경로는 그 연출을 원래도 안 거치므로 메시지만 자막으로 띄운다(006 · 057 · 168, 10-05)
#   skip       자동으로 못 거는 자리(status.md 「나레이션 자막 — 남은 자리」) — 손대지 않는다
# 메시지가 OFF 경로에 없는 게이트(효과음·BGM 분기 등)는 표에 없다 = 안 건드린다.
SITES: dict[int, dict[int, str]] = {
    2: {0: "raias"},
    6: {0: "single_pre", 1: "single", 3: "single", 4: "skip"},
    17: {0: "single", 1: "single"},
    18: {0: "skip", 1: "single"},
    20: {0: "single", 1: "single"},
    32: {0: "skip"},
    34: {0: "single", 1: "single"},
    40: {0: "single"},
    41: {0: "skip"},
    46: {0: "all"},
    50: {0: "all"},
    57: {0: "single_pre"},
    62: {0: "single"},
    63: {0: "all"},
    73: {0: "single"},
    74: {0: "all"},
    88: {0: "single", 1: "single"},
    98: {0: "skip", 1: "skip"},
    100: {0: "single"},
    151: {0: "skip", 1: "skip"},
    155: {0: "single"},
    168: {1: "single_pre", 2: "single", 3: "single", 4: "single"},
    177: {0: "single", 1: "single", 2: "single", 3: "single"},
    196: {0: "single", 1: "last"},
    198: {0: "last_page2"},
    201: {0: "all"},
    203: {0: "single", 1: "single", 2: "single", 3: "single", 4: "single"},
    204: {0: "single", 1: "single"},
}


# 장면 2: 음성 호출은 원판 그대로 두되, 호출 자리에서 **재생 시작을 기다리는 틱을 건다**(`VOICE_ARM`·`PLAYSTART`). 소리가 실제로 나기 시작하는 시각은 환경마다 다르다
# (이 에뮬은 호출 뒤 0.65초, 마스터 환경은 의자에 앉은 뒤 — 10-13). 설교 창은 `FLAG_VOICE0` 로 표의 0 을 그 시작에 묶는다(없으면 늦게 뜬다).
VOICE0 = {2}
GREET_VOICE = re.compile(rb"\x20\x15\x58....", re.DOTALL)  # 음성 호출(JSR $5815 + 인라인 4B) — 이 장면엔 하나


GREET_END = {2: 9.35}  # 인사 창이 닫히는 때(음성 시작 기준 초) = 설교 창이 열리는 때(실측: 음성 9초부터 설교 문안, 에뮬 10-13)


def _voice0_stub(sid: int, out: bytearray, sermon_load: bytes, sermon_tab: int) -> bytes:
    """장면 2 게이트 자리 스텁 — 인사 창(음성 호출 바로 앞의 메시지 적재)을 음성 시작~`GREET_END` 초 동안, 이어 설교 창을 띄운다. 반환: `JSR` 피연산자 2B.
    상주부 호출은 인라인 4B 뒤에 `BRA +11`(건너뜀) · 메시지 적재 11B 를 두는 원래 꼴 그대로(거리 7)."""
    call = GREET_VOICE.search(bytes(out))
    if not call:
        raise GateError(f"scn{sid:03d}: 음성 호출이 없다")
    ms = [m for m in MSG.finditer(bytes(out), 0, call.start()) if m.end() == call.start()]
    if not ms:
        raise GateError(f"scn{sid:03d}: 음성 호출 바로 앞에 인사 메시지가 없다")
    gload = ms[0].group(0)
    addr = (gload[1] | gload[5] << 8) - BASE
    gtab = page_table(bytes(out[addr : addr + 0x400]), 0, False, [GREET_END[sid]])
    gtab_at = BASE + len(out)
    out += gtab
    stub_at = BASE + len(out)

    def call_entry(tab_at: int, load: bytes) -> bytes:
        return bytes([0x20, ENTRY & 0xFF, ENTRY >> 8, 7, tab_at & 0xFF, tab_at >> 8, FLAG_VOICE0, 0x80, 11]) + load

    out += call_entry(gtab_at, gload) + call_entry(sermon_tab, sermon_load) + b"\x60"
    if len(out) > 0x2000:
        raise GateError(f"scn{sid:03d}: 인사 스텁을 붙이면 블록이 뱅크(8KB)를 넘는다")
    return stub_at.to_bytes(2, "little")


def _patch_greet(sid: int, out: bytearray) -> None:
    ms = list(GREET_VOICE.finditer(bytes(out)))
    if len(ms) != 1:
        raise GateError(f"scn{sid:03d}: 음성 호출이 {len(ms)}곳(하나여야)")
    m = ms[0]
    c, ps, arm = FRAMECNT, hook.PLAYSTART, hook.VOICE_ARM
    stub_at = BASE + len(out)
    inst = _resident_asm().labels["inst"]
    out += bytes(
        [0x20, inst & 0xFF, inst >> 8]  # JSR inst — 틱 트램펄린이 아직 없으면 건다
        + [0xA9, 1, 0x8D, arm & 0xFF, arm >> 8]  # LDA #1 · STA arm
        + [0xAD, c & 0xFF, c >> 8, 0x8D, ps & 0xFF, ps >> 8]  # PLAYSTART = 호출 때 카운터(재생 시작이 안 보일 때 값)
        + [0xAD, (c + 1) & 0xFF, (c + 1) >> 8, 0x8D, (ps + 1) & 0xFF, (ps + 1) >> 8]
    ) + bytes(out[m.start() : m.start() + 7]) + b"\x60"  # 음성 호출 · RTS
    if len(out) > 0x2000:
        raise GateError(f"scn{sid:03d}: 음성 스텁을 붙이면 블록이 뱅크(8KB)를 넘는다")
    out[m.start() : m.start() + 7] = b"\x20" + stub_at.to_bytes(2, "little") + b"\xea" * 4


FPS = 59.826  # PCE 프레임/초
SEC_PER_SECTOR = 2048 * 2 / 16000  # 음성 1섹터 = 2048B × 2니블 ÷ 16000Hz
SYNC_TOL = 1.5  # 초 — 음성 길이와 자막 시간이 이 안이면 맞는 것(마스터 10-08)
VOICE_AT = re.compile(
    rb"\x20\x15\x58.{2}(.)(.)", re.DOTALL
)  # JSR $5815 + 인라인 4B(오프셋 2B · 섹터 수 2B)
# 음성이 다음 게이트로 이어진다고 볼 수 없는 자리 — 하위 스크립트가 쥐는 구간이라 늘려도 안 맞는다(미해결, 표에 열려 있다고 찍는다)
OPEN_RUNS: dict[int, str] = {
    6: "마지막 게이트(+0x29f)가 skip — ON 경로가 `$5EC9`(객체 생성 연산)만 하고 메시지를 건너뛴다. 남은 50초 낭독 자막이 없다",
}

# 설정과 무관하게 음성이 나가는 장면(게이트 없음) — 첫 음성 호출 바로 뒤 타이머에 자막을 건다. 장면 224 = 종장 최종보스 아그니쟈의 독백(첫 방문은
# 음성만, 다시 오면 같은 문안을 창으로 띄운다). 장면 2 라이아스는 SITES 의 raias 규칙이 맡는다.
ALWAYS: dict[int, str] = {224: "voice_then_msg"}
ALWAYS_REACH = 0x40
PRE_MAX = 10  # single_pre: OFF 경로 메시지 앞 연출 호출의 최대 길이


class GateError(Exception):
    pass


def gate_events(b: bytes, sid: int) -> list[tuple]:
    """씬 `sid` 의 SITES 게이트마다 (순번, 규칙, 게이트, ON 경로 끝, 음성[(자리, 프레임)], 타이머[(자리, 프레임)])."""
    idx = [m.start() for m in re.finditer(re.escape(GATE), b)]
    out = []
    for gi, rule in sorted(SITES.get(sid, {}).items()):
        if gi >= len(idx):
            raise GateError(f"scn{sid:03d}: 게이트 {gi} 가 없다(블록에 {len(idx)}개)")
        o = idx[gi]
        tgt = o + 5 + (9 if rule == "raias" else b[o + 4])
        voices = [
            (v.start(), ((v.group(1)[0] | v.group(2)[0] << 8) * SEC_PER_SECTOR * FPS))
            for v in VOICE_AT.finditer(b, o + 5, tgt)
        ]
        timers = [
            (t.start(), t.group(1)[0] | t.group(2)[0] << 8)
            for t in TIMER_AT.finditer(b, o + 5, tgt)
        ]
        out.append((gi, rule, o, tgt, voices, timers))
    return out


def voice_runs(b: bytes, sid: int) -> list[dict]:
    """음성 토막마다 「그 음성이 도는 동안 이어진 타이머들」. 다음 음성이 시작되면 끊긴다.
    `all`(갈래)은 음성마다 자기 뒤 첫 타이머와 짝이고 음성 없는 타이머는 토막에 안 든다.
    skip 게이트를 만나면 그 토막은 `open` — 뒤가 어디서 이어지는지 모르니 늘리지 않는다.
    타이머 항목 = (자리, 프레임, 자막이 걸리는 타이머인가)."""
    runs: list[dict] = []
    cur = None
    for gi, rule, _o, tgt, voices, timers in gate_events(b, sid):
        if rule == "skip":
            if cur:
                cur["open"] = True
            cur = None
            continue
        if rule == "all":
            for k, (vp, vf) in enumerate(voices):
                nxt = voices[k + 1][0] if k + 1 < len(voices) else tgt
                tm = [(p, v, True) for p, v in timers if vp < p < nxt][:1]
                runs.append({"gate": gi, "voice": vf, "timers": tm, "open": False})
            cur = None
            continue
        picked = (
            {timers[-1][0]} if rule in ("last", "last_page2") and timers else {p for p, _ in timers}
        )
        for p, kind, val in sorted(
            [(p, "V", f) for p, f in voices] + [(p, "T", v) for p, v in timers]
        ):
            if kind == "V":
                cur = {"gate": gi, "voice": val, "timers": [], "open": False}
                runs.append(cur)
            elif cur is not None:
                cur["timers"].append((p, val, p in picked))
    return runs


def retime(b: bytes, sid: int) -> dict[int, int]:
    """음성이 자막보다 `SYNC_TOL` 넘게 길면 그 토막 마지막 자막 타이머를 늘려 음성 끝에 맞춘다 — {타이머 자리: 더할 프레임}.
    ON 경로 타이머만 바꾸므로 OFF(키 입력)는 바이트도 흐름도 그대로다. 마스터 10-08 (가)."""
    add: dict[int, int] = {}
    for r in voice_runs(b, sid):
        if r["open"]:
            continue
        gap = r["voice"] - sum(v for _, v, _ in r["timers"])
        patched = [p for p, _, ok in r["timers"] if ok]
        if gap > SYNC_TOL * FPS and patched:
            add[patched[-1]] = add.get(patched[-1], 0) + round(gap)
    return add


def _resident_asm() -> Asm:
    """호출 자리: `JSR RES_ORG · .db 거리, 타이머lo, 타이머hi, 플래그`(원래 `LDX · LDY · JSR $5BD7` 7B 자리).
    거리 = 반환 주소(JSR 마지막 바이트)에서 OFF 경로 메시지 적재(`A9 lo 85 10 A9 hi 85 11 …`)까지."""
    a = Asm(RES_ORG)
    a.label("entry")
    a.op("TSX")  # 반환 주소 → $10/$11, 스택의 반환 주소는 +4(인라인을 건너뛴다)
    a.op("LDA", "absx", 0x2101)
    a.op("STA", "zp", 0x10)
    a.op("CLC")
    a.op("ADC", "imm", 4)
    a.op("STA", "absx", 0x2101)
    a.op("LDA", "absx", 0x2102)
    a.op("STA", "zp", 0x11)
    a.op("ADC", "imm", 0)
    a.op("STA", "absx", 0x2102)
    a.op("LDY", "imm", 1)
    a.op("LDA", "izpy", 0x10)
    a.op("STA", "abs", "cand")
    a.op("INY")
    a.op("LDA", "izpy", 0x10)
    a.op("STA", "abs", "tl")
    a.op("INY")
    a.op("LDA", "izpy", 0x10)
    a.op("STA", "abs", "th")
    a.op("INY")
    a.op("LDA", "izpy", 0x10)
    a.op("STA", "abs", "mode")
    a.op("JSR", "abs", "inst")
    a.op("LDA", "abs", FRAMECNT)
    a.op("STA", "abs", "b0")
    a.op("LDA", "abs", FRAMECNT + 1)
    a.op("STA", "abs", "b1")
    a.op("LDA", "abs", "mode")
    a.op("AND", "imm", FLAG_VOICE0)
    a.op("BEQ", "rel", "b0ok")
    a.label("vw")  # 음성 재생 시작 대기 — 틱이 `VOICE_ARM` 을 내리면 시작한 것. 8.5초(상위 바이트 차 2)를 넘기면 호출 때 값으로 간다
    a.op("LDA", "abs", hook.VOICE_ARM)
    a.op("BEQ", "rel", "have")
    a.op("LDA", "abs", FRAMECNT + 1)
    a.op("SEC")
    a.op("SBC", "abs", hook.PLAYSTART + 1)
    a.op("CMP", "imm", 2)
    a.op("BCS", "rel", "have")
    a.op("LDX", "imm", 1)
    a.op("LDY", "imm", 0)
    a.op("JSR", "abs", WAIT_FRAMES)
    a.op("BRA", "rel", "vw")
    a.label("have")
    a.op("LDA", "abs", hook.PLAYSTART)
    a.op("STA", "abs", "b0")
    a.op("LDA", "abs", hook.PLAYSTART + 1)
    a.op("STA", "abs", "b1")
    a.label("b0ok")
    # 메시지 적재: lo = [거리+1] · hi = [거리+5] · 표시 루틴 = [거리+9](76/0B → $5B76 · 5B/06 → $5B5B)
    a.op("LDA", "abs", "cand")
    a.op("CLC")
    a.op("ADC", "imm", 9)
    a.op("TAY")
    a.op("LDA", "izpy", 0x10)
    a.op("STA", "abs", "kind")
    a.op("LDY", "abs", "cand")
    a.op("INY")
    a.op("LDA", "izpy", 0x10)
    a.op("TAX")
    a.op("INY")
    a.op("INY")
    a.op("INY")
    a.op("INY")
    a.op("LDA", "izpy", 0x10)
    a.op("STX", "zp", 0x10)
    a.op("STA", "zp", 0x11)
    a.op("LDA", "abs", "mode")
    a.op("AND", "imm", FLAG_PAGE2)
    a.op("BEQ", "rel", "show")
    # 2쪽부터 — 첫 쪽 넘김(05) 다음 글자로 포인터를 옮긴다
    a.op("LDY", "imm", 0)
    a.label("pg")
    a.op("LDA", "izpy", 0x10)
    a.op("INY")
    a.op("CMP", "imm", 5)
    a.op("BNE", "rel", "pg")
    a.op("TYA")
    a.op("CLC")
    a.op("ADC", "zp", 0x10)
    a.op("STA", "zp", 0x10)
    a.op("BCC", "rel", "show")
    a.op("INC", "zp", 0x11)
    a.label("show")
    a.op("JSR", "abs", "prep")
    a.op("LDA", "abs", "kind")
    a.op("CMP", "imm", 0x76)
    a.op("BEQ", "rel", "s76")
    a.op("CMP", "imm", 0x0B)
    a.op("BEQ", "rel", "s76")
    a.op("JSR", "abs", SHOW_5B)
    a.op("BRA", "rel", "wait")
    a.label("s76")
    a.op("JSR", "abs", SHOW_76)
    # wait: 마지막 쪽 마감(= 시작 + 원래 타이머, prep 이 cs·cf 에 남겼다)까지 1프레임씩 양보한다.
    #   손으로 일찍 넘겼으면 남은 만큼 기다리고, 마감을 넘겼으면 바로 돌아간다(원래 타이머 − 읽은 시간).
    a.label("wait")
    a.op("STZ", "abs", AUTO_FLAG)  # 자막 모드 끝
    a.label("rest")  # 남은 쪽 무게까지 마저 걸어 cs·cf = 시작 + T 로(손으로 일찍 닫았어도)
    a.op("LDA", "abs", "fin")
    a.op("BNE", "rel", "wl")
    a.op("JSR", "abs", "npage")
    a.op("BRA", "rel", "rest")
    a.label("wl")
    a.op("LDA", "abs", FRAMECNT)  # 카운터 ≥ 마감(cl·ch) 이면 끝
    a.op("SEC")
    a.op("SBC", "abs", "cl")
    a.op("LDA", "abs", FRAMECNT + 1)
    a.op("SBC", "abs", "ch")
    a.op("BCS", "rel", "done")
    a.label("more")
    a.op("LDX", "imm", 1)
    a.op("LDY", "imm", 0)
    a.op("JSR", "abs", WAIT_FRAMES)
    a.op("BRA", "rel", "wl")
    a.label("done")
    a.op("STZ", "abs", hook.VOICE_ARM)  # 재생 시작 대기 끝(못 봤어도)
    a.op("LDA", "abs", "old51")  # 글자 찍는 속도를 설정대로
    a.op("STA", "abs", SPEED)
    a.op("RTS")
    _prep(a)
    a.label("glob")  # 전역 시각표가 켜졌나 — 0 으로 두고 굽는다(패딩 FF 면 부팅하자마자 켜진 걸로 읽힌다)
    a.data(b"\x00")
    for v in ("tl", "th", "n", "cl", "ch", "fin", "b0", "b1", "mode", "cand", "kind", "old51"):  # fmt: skip
        a.label(v)
        a.data(b"\xff")  # 패딩 값 그대로 — 쓰기 전에 늘 채운다
    return a


def _prep(a: Asm) -> None:
    """자막 모드 준비. 들어올 때: b0·b1 = 시작 프레임 카운터, tl·th = 쪽 마감 표(블록 꼬리), $10/$11 = 메시지.
    표 = `n` 쪽 수 + 쪽마다 프레임 거리(16비트) — **창이 열린 시각에서 그 쪽이 끝나는 때까지**의 거리. 마지막 쪽 = 원래 타이머(음성 끝).
    표는 빌드가 만든다(`page_table`) — 쪽 나눔은 나레이션 OFF 때 대사창 그대로, 시각은 음성 박자(마스터 10-12).
    `npage` 는 표에서 다음 쪽 마감을 꺼내 AUTO_TL·AUTO_TH 와 cl·ch 에 쓴다 — 훅이 쪽이 넘어갈 때마다 부른다.
    쪽 글자는 설정과 무관하게 **즉시** 찍는다(`$C051` = 3 — 글자 찍는 속도 표 `$5B8A` 의 0프레임 칸, 끝나면 되돌린다)."""
    # sched: 전역 시각표(장면 한 토막 전체 — 여러 메시지의 모든 쪽) 시작. A=표 주소 하위 · X=상위. 지금부터 쪽마다 표의 시각(음성 시작에서 잰다)에
    # 자동으로 넘긴다 — 메시지 사이의 월드 시간(연출)은 그대로 흐르고, 늦으면 밀린 만큼 빨리 넘어간다. 표를 다 쓴 뒤 마지막 쪽이 넘어가면 스스로 끈다
    a.label("sched")  # = prep 앞에 기준 시각·전역 표시를 더한 것(코드가 같아 prep 으로 흘려 보낸다 — 상주부 자리가 빠듯하다)
    a.op("STA", "abs", "tl")
    a.op("STX", "abs", "th")
    a.op("JSR", "abs", "inst")
    a.op("LDA", "abs", FRAMECNT)
    a.op("STA", "abs", "b0")
    a.op("LDA", "abs", FRAMECNT + 1)
    a.op("STA", "abs", "b1")
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", "glob")
    a.label("prep")
    a.op("LDA", "abs", SPEED)
    a.op("STA", "abs", "old51")
    a.op("LDA", "imm", 3)
    a.op("STA", "abs", SPEED)
    a.op("LDA", "abs", "tl")
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "abs", "th")
    a.op("STA", "zp", 0xED)
    a.op("LDA", "izp", 0xEC)  # 표 머리 = 쪽 수
    a.op("STA", "abs", "n")
    a.op("INC", "abs", "tl")
    a.op("BNE", "rel", "p1")
    a.op("INC", "abs", "th")
    a.label("p1")
    a.op("STZ", "abs", "fin")
    a.op("JSR", "abs", "npage")
    a.op("LDA", "imm", 1)
    a.op("STA", "abs", AUTO_FLAG)
    a.op("RTS")
    # next: 표에서 한 쪽 마감을 꺼내 AUTO_TS·AUTO_TF 에. 마지막 쪽까지 꺼내면 fin
    a.label("npage")
    a.op("LDA", "abs", "fin")
    a.op("BEQ", "rel", "ngo")
    a.op("LDA", "abs", "glob")  # 끝까지 꺼냈다 — 전역 시각표면 마지막 쪽이 넘어간 지금 자막 모드를 끝낸다
    a.op("BEQ", "rel", "nret")
    a.op("STZ", "abs", "glob")
    a.op("STZ", "abs", AUTO_FLAG)
    a.op("LDA", "abs", "old51")
    a.op("STA", "abs", SPEED)
    a.label("nret")
    a.op("RTS")
    a.label("ngo")
    a.op("LDA", "abs", "tl")
    a.op("STA", "zp", 0xEC)
    a.op("LDA", "abs", "th")
    a.op("STA", "zp", 0xED)
    a.op("LDY", "imm", 0)
    a.op("LDA", "izpy", 0xEC)  # 마감 = 기준 + 표의 프레임 거리(16비트)
    a.op("CLC")
    a.op("ADC", "abs", "b0")
    a.op("STA", "abs", "cl")
    a.op("INY")
    a.op("LDA", "izpy", 0xEC)
    a.op("ADC", "abs", "b1")
    a.op("STA", "abs", "ch")
    a.op("LDA", "abs", "tl")
    a.op("CLC")
    a.op("ADC", "imm", 2)
    a.op("STA", "abs", "tl")
    a.op("BCC", "rel", "nt")
    a.op("INC", "abs", "th")
    a.label("nt")
    a.op("DEC", "abs", "n")
    a.op("BNE", "rel", "no")
    a.op("INC", "abs", "fin")
    a.label("no")
    a.op("LDA", "abs", "cl")
    a.op("STA", "abs", AUTO_TL)
    a.op("LDA", "abs", "ch")
    a.op("STA", "abs", AUTO_TH)
    a.op("RTS")
    # inst: IRQ1 핸들러의 `JSR $57A5`(`IRQ_SITE`)을 프레임 카운터 트램펄린으로 바꿔 끼운다 — 이미 바꿨으면 그대로. 읽기·쓰기 사이 IRQ 가 못 끼게 SEI.
    a.label("inst")
    a.op("LDA", "abs", IRQ_SITE + 1)
    a.op("CMP", "imm", hook.IRQ_ORIG & 0xFF)  # 원래 `20 A5 57` — 하위가 다르면 이미 바꿨다
    a.op("BNE", "rel", "inst1")
    a.op("PHP")
    a.op("SEI")
    a.op("LDA", "imm", TICK_ADDR & 0xFF)
    a.op("STA", "abs", IRQ_SITE + 1)
    a.op("LDA", "imm", TICK_ADDR >> 8)
    a.op("STA", "abs", IRQ_SITE + 2)
    a.op("PLP")
    a.label("inst1")
    a.op("RTS")


def auto_hook() -> bytes:
    """대사 엔진 쪽 대기의 `LDA $CF1A` 대신. 자막 모드이고 시계가 지금 쪽 마감을 넘었으면 A=$20(버튼).
    쪽이 넘어가면(자동이든 손이든) 뱅크 0x6B 를 MPR4 에 잠깐 걸고 상주부 `npage` 로 다음 마감을 구한다."""
    a = Asm(AUTO_ORG)
    a.op("PHX")
    a.op("PHY")
    a.op("LDA", "abs", AUTO_FLAG)
    a.op("BEQ", "rel", "plain")
    a.op("LDA", "abs", FRAMECNT)  # 카운터 ≥ 마감 이면 누른다
    a.op("SEC")
    a.op("SBC", "abs", AUTO_TL)
    a.op("LDA", "abs", FRAMECNT + 1)
    a.op("SBC", "abs", AUTO_TH)
    a.op("BCC", "rel", "plain")
    a.label("press")
    a.op("LDA", "imm", 0x20)
    a.op("BRA", "rel", "hit")
    a.label("plain")
    a.op("LDA", "abs", PAD)
    a.op("AND", "imm", 0x60)
    a.op("BEQ", "rel", "out")
    a.label("hit")
    a.op("PHA")
    a.op("LDA", "abs", AUTO_FLAG)
    a.op("BEQ", "rel", "hit2")
    a.op("PHP")
    a.op("SEI")
    a.op("TMA", "tma", 4)
    a.op("PHA")
    a.op("LDA", "imm", 0x6B)
    a.op("TAM", "tam", 4)
    a.op("JSR", "abs", _resident_asm().labels["npage"])
    a.op("PLA")
    a.op("TAM", "tam", 4)
    a.op("PLP")
    a.label("hit2")
    a.op("PLA")
    a.label("out")
    a.op("PLY")
    a.op("PLX")  # 호출부는 X(작업 번호)를 곧 쓴다. A 는 곧바로 `AND #$60` 하니 플래그는 상관없다
    a.op("RTS")
    b = a.bytes()
    assert AUTO_ORG + len(b) <= AUTO_FLAG, len(b)
    # 🔴 표시·마감 3B 까지 굽는다 — 패딩 FF 그대로 두면 부팅하자마자 「자막 모드 켜짐」으로 읽힌다
    return b + b"\xff" * (AUTO_FLAG - AUTO_ORG - len(b)) + b"\x00\xff\xff"


def resident() -> bytes:
    b = _resident_asm().bytes()
    assert RES_ORG + len(b) <= RES_END, len(b)
    return b


ENTRY = RES_ORG
SCHED = _resident_asm().labels["sched"]  # 전역 시각표 시작(`LDA #하위 · LDX #상위 · JSR SCHED`)


def find_load(b: bytes, start: int, end: int, skip: int = 0) -> int | None:
    """[start, end) 에서 메시지 적재 꼴의 자리(블록 오프셋)."""
    for c in range(start, end):
        if all(c + o < len(b) and b[c + o] == v for o, v in PAT):
            if skip:
                skip -= 1
                continue
            return c
    return None


TIMING_FILE = common.GAME_DIR / "script" / "voice_timing.json"  # 마스터가 편집기에서 고친 쪽 끝 시각 — {"scn002@0x37": [초, …]}


def timing_overrides() -> dict[str, list[float]]:
    return json.loads(TIMING_FILE.read_text("utf-8")) if TIMING_FILE.exists() else {}


def page_table(msg: bytes, timer: int, page2: bool = False, ends: list[float] | None = None) -> bytes:
    """쪽 마감 표 — `[쪽 수] + 쪽마다 (초, 프레임)`, 창이 열린 시각에서 그 쪽이 끝날 때까지의 거리.
    기본 = 메시지 바이트 수 비례(글자 2B · 제어 1B, 종료 바이트 포함): 쪽 끝 = floor(T × 누적/전체). 마지막 쪽 = T 그대로.
    `ends`(초)가 있으면 그 값(마지막 쪽 포함 — 그 값이 곧 창이 닫히는 때). 쪽은 `05`(쪽 넘김)로 나뉜다."""
    i = 0
    if page2:  # 상주부가 첫 쪽 넘김(05) 다음부터 띄운다
        i = msg.index(b"\x05") + 1
    body = msg[i:]
    end = next(k for k, c in enumerate(body) if c in TERM_BYTES)
    w = end + 1
    cuts = [k + 1 for k, c in enumerate(body[:end]) if c == 5]
    frames = [timer * c // w for c in cuts] + [timer]
    if ends is not None:
        if len(ends) != len(frames):
            raise GateError(f"voice_timing: 쪽 {len(frames)}개인데 시각 {len(ends)}개")
        frames = [round(e * FPS) for e in ends]
    out = bytearray([len(frames)])
    for f in frames:
        if not 0 <= f <= 0xFFFF:
            raise GateError(f"쪽 마감 {f} 프레임이 16비트를 넘는다")
        out += f.to_bytes(2, "little")
    return bytes(out)


def patch_block(sid: int, blk: bytes) -> tuple[bytes, int]:
    """씬 `sid` 블록의 나레이션 게이트에 자막 스텁을 건다. (새 블록, 바꾼 타이머 수)."""
    b = bytearray(blk)
    gates = [m.start() for m in re.finditer(re.escape(GATE), b)]
    picks: list[tuple[int, int, bool, int]] = []  # (타이머 자리, OFF 메시지 주소, 2쪽부터?, 타이머)
    extra = retime(bytes(blk), sid)  # 음성이 자막보다 길면 늘린다(ON 만)
    for gi, rule in SITES.get(sid, {}).items():
        if rule == "skip":
            continue
        if gi >= len(gates):
            raise GateError(f"scn{sid:03d}: 게이트 {gi} 가 없다(블록에 {len(gates)}개)")
        o = gates[gi]
        if rule == "raias":
            if b[o + 3 : o + 5] != b"\xf0\x14":
                raise GateError(
                    f"scn{sid:03d} 게이트 {gi}: BEQ +0x14 가 아니다 — {b[o + 3 : o + 5].hex()}"
                )
            tgt = o + 5 + 9  # ON 경로(타이머 7B + BRA 2B) 바로 뒤의 메시지
            b[o + 4] = 0x00  # OFF 도 ON 경로로
            rule = "single"
        else:
            if b[o + 3] != 0xF0:
                raise GateError(f"scn{sid:03d} 게이트 {gi}: BEQ 가 아니다")
            tgt = o + 5 + b[o + 4]
        if rule == "single_pre":
            m = MSG.search(bytes(b), tgt, tgt + PRE_MAX + 11)
            rule = "single"
        else:
            m = MSG.match(bytes(b), tgt)
        if not m:
            raise GateError(f"scn{sid:03d} 게이트 {gi}: OFF 경로에 메시지가 없다")
        page2 = rule == "last_page2"  # 상주부가 OFF 메시지의 첫 쪽 넘김(05) 다음부터 띄운다
        timers = list(TIMER_AT.finditer(bytes(b), o + 5, tgt))
        if rule == "single" and len(timers) != 1:
            raise GateError(f"scn{sid:03d} 게이트 {gi}: 타이머가 {len(timers)}개(하나여야)")
        if rule == "all" and len(timers) < 2:
            raise GateError(f"scn{sid:03d} 게이트 {gi}: 갈래 타이머가 {len(timers)}개")
        pick = timers[-1:] if rule in ("last", "last_page2") else timers
        for t in pick:
            timer = t.group(1)[0] | (t.group(2)[0] << 8)
            timer += extra.get(t.start(), 0)
            if timer > 0xFFFF:
                raise GateError(
                    f"scn{sid:03d} +{t.start():#x}: 늘린 타이머 {timer} 가 16비트를 넘는다"
                )
            picks.append((t.start(), m.start(), page2, timer))
    if sid in ALWAYS:  # 게이트가 없는 장면 — 첫 `JSR $5815` 바로 뒤 타이머, 그 뒤 첫 메시지 적재(음성 재생 뒤 이미 들은 쪽 분기가 띄우는 창)
        v = VOICE_AT.search(bytes(b))
        t = TIMER_AT.match(bytes(b), v.end()) if v else None
        if not v or not t:
            raise GateError(f"scn{sid:03d}: 음성 바로 뒤에 타이머가 없다")
        m = MSG.search(bytes(b), t.end(), t.end() + ALWAYS_REACH)
        if not m:
            raise GateError(f"scn{sid:03d}: 타이머 뒤 {ALWAYS_REACH}B 안에 메시지가 없다")
        picks.append((t.start(), m.start(), False, t.group(1)[0] | t.group(2)[0] << 8))
    over = timing_overrides()
    out = bytearray(b)
    for at, load, page2, timer in picks:
        dist = load - (at + 2)  # 상주부가 재는 기준 = 반환 주소(JSR 마지막 바이트, at+2)
        if not 0 < dist <= 0xF0:
            raise GateError(
                f"scn{sid:03d} +{at:#x}: 메시지 적재까지 거리 {dist} — 인라인 한 바이트에 안 든다"
            )
        addr = (out[load + 1] | out[load + 5] << 8) - BASE
        tab = page_table(bytes(out[addr : addr + 0x400]), timer, page2, over.get(f"scn{sid:03d}@{at:#x}"))
        if len(out) + len(tab) > 0x2000:
            raise GateError(f"scn{sid:03d}: 쪽 마감 표 {len(tab)}B 를 붙이면 블록이 뱅크(8KB)를 넘는다")
        tab_at = BASE + len(out)
        out += tab
        if sid in VOICE0:  # 설교 창 앞에 인사(시녀 창 문안)를 음성 시각에 맞춰 띄운다 — 호출 자리는 스텁 하나로
            out[at : at + 7] = b"\x20" + _voice0_stub(sid, out, bytes(out[load : load + 11]), tab_at) + b"\xea" * 4
            continue
        out[at : at + 7] = bytes(
            [
                0x20,
                ENTRY & 0xFF,
                ENTRY >> 8,
                dist,
                tab_at & 0xFF,
                tab_at >> 8,
                (FLAG_PAGE2 if page2 else 0) | (FLAG_VOICE0 if sid in VOICE0 else 0),
            ]
        )
    if sid in VOICE0:
        _patch_greet(sid, out)
    return bytes(out), len(picks) + (sid in VOICE0)


def load_messages() -> dict[int, dict[int, dict]]:
    out = {}
    for f in glob.glob(str(common.OUT_DIR / "messages" / "scn*.json")):
        sid = int(f[-8:-5])
        out[sid] = {m["start"]: m for m in json.loads(Path(f).read_text())}
    return out


def scan() -> list[dict]:
    msgs = load_messages()
    rows, seen = [], set()
    for f in sorted(glob.glob(str(common.OUT_DIR / "text" / "*.bin"))):
        name = f.rsplit("/", 1)[-1][:-4]
        sid = int(name.split("_")[1])
        b = Path(f).read_bytes()
        for m in re.finditer(re.escape(GATE), b):
            o = m.start()
            if (sid, o) in seen:  # 공통 블록(000/001)은 컨테이너마다 같은 사본
                continue
            seen.add((sid, o))
            br, off = b[o + 3], b[o + 4]
            if br not in (0xF0, 0xD0):
                continue
            tgt = o + 5 + (off if off < 0x80 else off - 0x100)

            def ref(mm, sid=sid):
                a = mm.group(1)[0] | (mm.group(2)[0] << 8)
                e = msgs.get(sid, {}).get(a - BASE)
                return {
                    "addr": f"${a:04X}",
                    "key": e and e["key"],
                    "speaker": e and e["speaker"],
                    "head": e and e["jp"][:24].replace("\n", " "),
                }

            on_path = b[o + 5 : tgt]
            off_msg = MSG.match(b, tgt)
            rows.append(
                {
                    "block": name,
                    "scene": sid,
                    "at": f"{o:#x}",
                    "branch": "BEQ" if br == 0xF0 else "BNE",
                    "target": f"{tgt:#x}",
                    "voice_in_on": VOICE in on_path,
                    "timer_in_on": TIMER in on_path,
                    "on_msgs": [ref(x) for x in MSG.finditer(b, o + 5, tgt)],
                    "off_msg": ref(off_msg) if off_msg else None,
                }
            )
    return rows


def main() -> None:
    rows = scan()
    out = common.REVIEW_DIR / "narration_gates.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    gated = [r for r in rows if r["off_msg"]]
    print(
        f"게이트 {len(rows)} · OFF 경로 메시지 {len(gated)} · 씬 {len({r['scene'] for r in gated})}"
    )
    print(f"  그중 ON 경로 타이머 있음 {sum(r['timer_in_on'] for r in gated)}")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
