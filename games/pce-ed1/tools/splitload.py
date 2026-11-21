"""씬 컨테이너 둘로 나누기 — 한 구역의 컨테이너가 4뱅크(16섹터)를 넘을 때, 씬 열기 루틴이 「이 id 가 없다」를 만나면
**현 컨테이너를 내리고 짝 컨테이너를 올린 뒤 다시 찾는다**(10-24 구엔의탑 — devlog).

🔴 왜: 원판은 어느 구역에서든 캐시를 14칸 점유한다(필드 정상 상태 16곳 실측: 빈 칸은 늘 슬롯 14·15). 우리는 그 둘을 글리프가 써서 여유가
0 이다. 문안이 늘어 컨테이너가 5뱅크(17섹터)가 되면 1칸이 모자라 자원 하나(rel 242)가 **조용히** 안 올라온다. 컨테이너 둘이 동시에 올라가
있으면 점유가 같아 소용없으므로 **한 번에 하나만** 올린다 — 교체는 구역 전환(`$6BE3` 내림 → `$56D8` 올림)과 같은 순서다.

동작(씬 열기 `$6DF3` 의 디렉터리 탐색 루프 `$6E1C~$6E30` 을 바꾼다):
  · 사이트(뱅크 0x6A, 21B) — MPR4($8000)에 글리프 뱅크 0x86 을 잠깐 걸고 `check`(글리프 뱅크 꼬리의 빈 169B)를 부른 뒤 원래 MPR4 로 돌린다.
    성공이면 C=0 으로 원래 `$6E31`(찾음)로 간다. 실패면 원판처럼 제자리에서 돈다(「못 찾음 = 멈춤」은 그대로).
  · `check`: 디렉터리를 5B 씩 훑는다. 찾으면 C=0. FF 끝이면 한 번만(`flag`) 짝으로 바꾼다 — 짝 정보는 **표가 아니라 지금 올라온 컨테이너의
    디렉터리 끝 가짜 항목**(`[FE, 짝 rec lo, 짝 rec hi, 짝 섹터수, 0]`)에 있다(11-05, 종전 3B 짝 표·14항목·키 상위 0x26 제약을 없앴다 — 빌드가 짝을 정한 뒤
    `build.set_partner` 로 쓴다). 짝 정보를 읽어 두고 현 핸들을 내린 뒤(`$5597`) 짝을 올리고(`$56D8`) 첫 뱅크를 MPR5 에 다시 걸어 처음부터 다시 찾는다.
    찾으면 `flag` 를 지운다.
  · 압축 풀기·구역 초기화 루프(`$6D7A`, 그림 자원 번호 목록)는 다시 안 돈다 — 목록은 두 컨테이너가 같고(디렉터리 뒤 틈 그대로 복사)
    이미 캐시에 올라 있다. 그 루프는 첫 블록 앞에서 거꾸로 FF 까지만 읽으므로 FF 앞 가짜 항목은 안 건드린다.
  · 나눈 두 쪽 중 **원래 칸에 들어가는 쪽은 제자리에 두고**(참조표·재배치 장부가 안 바뀐다) 나머지만 트랙 끝 풀로 보낸다.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import containers
import font
import hook
import musicresume

SPLIT_RELS = (1508, 1380, 1348, 1396, 1252, 1268, 1620, 1540, 1284, 1332, 1364, 1444, 1476, 1524, 1572, 1588) + (  # 나눌 컨테이너(원본 rel) — 16섹터 안에 안 들어가는 것(build 게이트가 알려 준다). 1252 = 씬 6 · 1268 = 씬 18 비모달 자막 안 B(10-31) — 16섹터 안이면 안 나눈다(제품은 안 나뉜다)
    tuple(int(x) for x in os.environ.get("ED_SPLIT_EXTRA", "").split(",") if x) if common.BUILD_TAG.startswith("test-") else ()
)  # 시험 빌드(대사 보기 스텁이 컨테이너를 키운다)만 더 나눌 수 있다 — 제품 빌드는 위 둘 그대로
COMMON_IDS = (0, 1, 4, 5)  # 모든 컨테이너 공통 블록 — 양쪽에 복사한다
TAIL_BANKS = {1444: 3, 1476: 3}  # 🔴 자막 코드 영역이 든 풀 쪽을 이 뱅크 수 안으로 — 씬 168 보스전이 캐시 15칸을 쓴다(글리프 2뱅크가 16→14칸으로 줄여 놓았다, 11-05). 새 곳은 캐시표 실측으로만 넣는다
# 🔴 자막 코드가 없어도 이 씬들의 쪽을 TAIL_BANKS 뱅크 안으로 만든다(11-06 — 원판이 입구에서 보스 그림 rec 274(3뱅크)를 올리는 씬 120·123·126·130·131 은 한글판 14칸에서 3뱅크 연속 칸이 안 난다)
FORCE_Y = {1444: (120, 123, 126, 130, 131)}
# 🔴 한 컨테이너에 자막 창 위치(위/아래)가 갈리는 씬이 있으면 강제로 나눠 두 씬을 다른 쪽에 둔다(마스터 11-06 「주인공이 안 가려지는 위치로, 아래 우선·가려지면 위」) —
#   자막 코드 영역은 쪽마다 한 벌이라 위치가 다른 씬은 한 쪽에 못 둔다. 값 = (아래 쪽 씬, 위 쪽 씬) 같은 쪽에 안 둔다.
FORCE_SEP = {1268: (17, 18, 20), 1396: (98, 100)}  # 씬 17 아래·18 위(마스터 화면 확인). 204·62·63 위는 강제 시작 근사라 틀렸다(실제 걷기 화면 walk-204/v04 는 파티가 창 위) — 11-06 되돌림
LIMIT_SECTORS = 16  # 4뱅크 — 원판 최대치
PART_SECTORS = 12  # 3뱅크 — 11-17 마스터 판정 ⓣ: 원판은 2·4장 구역에서 캐시 14칸을 정상 상태로 쓰는데(실측) 한글판은 글리프 뱅크 둘이 14·15 를 가져가 여유가 0 이다 — 조각을 3뱅크 이하로 하고 참조표 섹터 수를 낮춰 구역마다 한 뱅크를 돌려받는다
MAX_HOPS = 2  # 조각 고리 교체 상한(조각 ≤ 3)
PART_RELS = (1284, 1332, 1348, 1492)  # ⓣ 대상 — 원판이 14칸을 정상 상태로 쓰는 장(2·4장) 중 구역 적재가 4뱅크인 컨테이너(1428·1444·1476 은 이미 3뱅크). 장별 steady 실측은 devlog 11-17
# 🔴 11-22 마스터 「2장 루디아성 계단 음악끊김은 왼쪽 지하감옥 계단 빼고는 전부 발생해」 — 계단으로 이어진 씬이 다른 조각이면 오르내릴 때마다 조각 교체(CD_READ ≈0.8초)가 곡을 끊는다(3장은 한 컨테이너라 안 끊김).
#   루디아 성(워프 그래프: 11·12·15·16·18·19·20·21 — 16 이 허브, 19 가 수로 허브)을 한 조각으로 묶고 나머지(7·8·33·37·42·46·47)를 다른 조각으로 둔다. 제자리(참조표 쪽) = 앞 조각.
#   각 조각 크기·4뱅크 한도는 빌드(`_write_parts`)가 확인한다. 지정이 컨테이너의 씬과 어긋나면 빌드가 죽는다.
PART_FIXED = {1284: ((7, 8, 33, 37, 42, 46, 47), (11, 12, 15, 16, 18, 19, 20, 21))}

BANK_OFF = font.BANK_GLYPH_END + len(hook.unpack_asm().bytes())  # 글리프 뱅크 0 안 코드 자리(풀기 루틴 뒤 빈 곳)
ORG = 0x8000 + BANK_OFF  # MPR4 창 기준 주소
ROOM = 0x2000 - BANK_OFF
SITE_REL_OFF = (0x6A, 0xE1C)  # 씬 열기 탐색 루프(뱅크, 오프셋) — `_main(bank, off)`
SITE_OLD = bytes.fromhex("b212cd09c0f00ea90518651285126265138513 80eb".replace(" ", ""))
SITE_FOUND = 0x6E31  # 찾았을 때 가는 곳(원래 BEQ 목표)
SITE_AT = 0x6E1C
OPEN_MPR4 = 4  # 사이트가 거는 창 번호(MPR4 = $8000)


def _asm():
    """배치: [짝 읽기(miss) · 올리기 · 다시 훑기 준비] → `check`(입구 = 디렉터리 훑기) → 찾음(ok) → 변수.
    다시 훑기 준비가 `check` 바로 앞이라 `JMP` 없이 흘러든다.
    🔴 짝은 표가 아니라 **지금 올라온 컨테이너 자신**이 말한다(11-05): 디렉터리 끝 FF 앞의 가짜 항목 `[FE, 짝 rec lo, 짝 rec hi, 짝 섹터수, 0]`(`containers.PARTNER_ID`).
    훑기가 FF 에서 멈추면 `$12/$13` 이 그 FF 를 가리키므로 5B 앞이 그 항목이다. 짝을 읽은 뒤에 내려야 한다(내리면 디렉터리가 사라진다)."""
    a = hook.Asm(ORG)
    a.label("fail")  # 앞에 둔다 — 분기(±127B)가 짧은 쪽으로 닿게
    a.op("SEC")
    a.op("RTS")
    a.label("miss")
    a.op("LDA", "abs", "flag")  # 교체 횟수(조각 고리 — 조각이 셋이면 최대 둘 교체: 처음 올라온 조각 → 짝 → 짝의 짝)
    a.op("CMP", "imm", MAX_HOPS)
    a.op("BCS", "rel", "fail")
    a.op("SEC")
    a.op("LDA", "zp", 0x12)  # 훑기 포인터를 가짜 항목 머리로(FF − 5)
    a.op("SBC", "imm", 5)
    a.op("STA", "zp", 0x12)
    a.op("LDA", "zp", 0x13)
    a.op("SBC", "imm", 0)
    a.op("STA", "zp", 0x13)
    a.op("LDA", "izp", 0x12)
    a.op("CMP", "imm", containers.PARTNER_ID)
    a.op("BNE", "rel", "fail")  # 나눈 컨테이너가 아니다(원판처럼 못 찾음)
    a.op("LDY", "imm", 3)
    a.op("LDA", "izpy", 0x12)  # 짝 섹터수 · rec hi · rec lo 를 쌓아 둔다
    a.op("PHA")
    a.op("DEY")
    a.op("LDA", "izpy", 0x12)
    a.op("PHA")
    a.op("DEY")
    a.op("LDA", "izpy", 0x12)
    a.op("PHA")
    a.op("LDA", "abs", "flag")  # 첫 교체(flag = 0)에서만 — 둘째 교체부터는 첫 CD_READ 가 이미 곡을 멈췄다
    a.op("BNE", "rel", "nosave")
    a.data(musicresume.far_call("savepos"))
    a.label("nosave")
    a.op("INC", "abs", "flag")  # 교체 횟수 +1
    a.op("LDA", "zp", 0x61)
    a.op("JSR", "abs", 0x5597)  # 현 컨테이너를 내린다(구역 전환 `$6BE3` 과 같다)
    a.op("PLA")
    a.op("TAX")
    a.op("PLY")
    a.op("PLA")
    a.op("JSR", "abs", 0x56D8)  # 짝을 올린다(X Y = rec lo·hi, A = 섹터수)
    a.op("BCS", "rel", "fail")
    a.op("STY", "zp", 0x61)
    a.op("LDA", "absy", 0x378D)
    a.op("CLC")
    a.op("ADC", "abs", 0x3EF1)
    a.op("ADC", "imm", 0x10)
    a.op("TAM", "tam", 5)  # 첫 뱅크를 MPR5($A000)에 — 원래 `$6E04~$6E12`
    a.op("STZ", "zp", 0x12)
    a.op("LDA", "imm", 0xA0)
    a.op("STA", "zp", 0x13)
    a.label("check")
    a.label("scan")
    a.op("LDA", "izp", 0x12)
    a.op("CMP", "imm", 0xFF)
    a.op("BEQ", "rel", "miss")
    a.op("CMP", "abs", 0xC009)
    a.op("BEQ", "rel", "ok")
    a.op("LDA", "zp", 0x12)
    a.op("CLC")
    a.op("ADC", "imm", 5)
    a.op("STA", "zp", 0x12)
    a.op("BCC", "rel", "scan")
    a.op("INC", "zp", 0x13)
    a.op("BRA", "rel", "scan")
    a.label("ok")
    # 🔴 11-19 음악 다시 걸기는 **짝 읽기를 다 마치고 찾은 뒤 한 번만** — 종전엔 짝을 올릴 때마다 걸어 조각 고리(짝의 짝)에서 한 전환에 곡이 셋 시작했다(마스터 「멈춤·겹침」, 원판은 구역 안 전환에 CD 호출 0회,
    #   devlog 「⑨ 음악 계단 표」). 짝 읽기 CD_READ 는 CD-DA 를 멈춘다(11-11 「루디아 입장하면 음악이 멈춰」 — 하네스 실측: CD_PLAY 직후 CD_READ). 곡 명령 바이트 `$4B` < `$10`(곡 번호 — 80 이상은 멈춤·페이드)이고
    #   `$4C` = 0(재생 모드)이면 같은 곡 루틴(뱅크 0x69 `$6856`)을 다시 부른다. 교체가 있었을 때만(`flag` ≠ 0). 호출자가 찾은 항목 포인터(`$12/$13`)와 레지스터를 쓰므로 지키고 부른다.
    #   🔴 11-20 이어 재생: 다시 걸기는 **처음부터가 아니라 교체 직전 CD 위치부터**(`musicresume.py` — 교체 전 `savepos` · 교체 뒤 `replay`). 곡 조건 검사·레지스터 보존도 그쪽이 한다.
    a.op("LDA", "abs", "flag")
    a.op("BEQ", "rel", "nomus")
    a.data(musicresume.far_call("replay"))
    a.label("nomus")
    a.op("STZ", "abs", "flag")
    # 🔴 틱 트램펄린 설치(`narration_gates.inst` 와 같은 일) — 씬이 열릴 때마다 「아직 원본이면」 건다. 부팅 때 걸어도 메인 프로그램이 곧 다시 올라와 지워지고,
    #   나레이션 `inst` 는 게이트 있는 씬에서만 불려 일반 필드에는 틱이 없었다 — SELECT+RUN 디버그 키(`debugkey`)가 필드에서도 틱을 필요로 한다.
    #   두 바이트를 TII 한 번으로 쓴다 — 블록 전송 중엔 IRQ 를 받지 않아(끝난 뒤 처리) 반쯤 바뀐 주소로 IRQ 가 뛰지 않는다(종전 PHP·SEI·…·PLP 와 같은 보장).
    a.op("LDA", "abs", 0x4155)
    a.op("CMP", "imm", 0xA5)  # 원래 `20 A5 57` — 하위가 다르면 이미 바꿨다
    a.op("BNE", "rel", "okr")
    a.data(b"\x73")  # TII tick → $4155, 2
    a.fix.append((len(a.out), "tick", "abs"))
    a.data(b"\0\0")
    a.data((0x4155).to_bytes(2, "little") + (2).to_bytes(2, "little"))
    a.label("okr")
    a.op("CLC")
    a.op("RTS")
    a.label("tick")
    a.data(hook.TICK_ADDR.to_bytes(2, "little"))
    a.label("flag")
    a.data(b"\0")
    return a


def code() -> bytes:
    """글리프 뱅크 0 의 꼬리에 얹을 `check` + 변수 + 짝 표(0). 길이는 ROOM 안."""
    b = _asm().bytes()
    assert len(b) <= ROOM, (len(b), ROOM)
    return b


def layout() -> dict:
    """(코드 길이, flag 주소)."""
    a = _asm()
    return {"len": len(a.bytes()), "flag": a.labels["flag"]}


def site_patch() -> tuple[bytes, bytes]:
    """(기대 원본 21B, 새 21B). 사이트: MPR4 ← 글리프 뱅크 0 · `JSR check` · MPR4 복원 · `BCC 찾음` · 못 찾으면 제자리."""
    check = _asm().labels["check"]
    a = hook.Asm(SITE_AT)
    a.op("TMA", "tma", OPEN_MPR4)
    a.op("PHA")
    a.op("LDA", "imm", font.GLYPH_BANK0)
    a.op("TAM", "tam", OPEN_MPR4)
    a.op("JSR", "abs", check)
    a.op("PLA")  # PLA 는 C 를 안 건드린다
    a.op("TAM", "tam", OPEN_MPR4)
    a.op("BCC", "rel", "found")
    a.label("hang")
    a.op("BRA", "rel", "hang")  # 원판처럼 못 찾으면 멈춘다(두 번째 실패)
    while len(a.out) < len(SITE_OLD):
        a.data(b"\xea")  # NOP
    a.labels["found"] = SITE_FOUND
    new = a.bytes()
    assert len(new) == len(SITE_OLD), len(new)
    return SITE_OLD, new


def slot_sectors(rel: int) -> int:
    """원본 참조표가 말하는 그 컨테이너의 섹터 수."""
    return dict(containers.referenced())[rel]


def check_limits(sectors: dict[int, int]) -> list[str]:
    """16섹터를 넘는 컨테이너 목록(게이트용)."""
    return [f"rel {r}: {n}섹터 > {LIMIT_SECTORS}" for r, n in sorted(sectors.items()) if n > LIMIT_SECTORS]


if __name__ == "__main__":
    lay = layout()
    print(f"코드 {lay['len']}B / 자리 {ROOM}B · 글리프 뱅크 0 오프셋 {BANK_OFF:#06x} · ORG {ORG:#06x} · flag {lay['flag']:#06x}")
    old, new = site_patch()
    print(old.hex(" "))
    print(new.hex(" "))
    assert common
