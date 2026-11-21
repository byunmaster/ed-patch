"""아이템 값 계산(뱅크 0x6F `$864B` 안 ×10 고리)을 빠른 꼴로 — 「버린다」 확인 직후 한 프레임 뚫림의 원인 (마스터 11-20 「버리기할때 순간적으로 뚫려서 프레임 보이는」 · 「특정 아이템들만 발생」).

## 무엇이 느렸나 (실측 11-21, mednafen · 제품 롬 2c606b6b)

아이템 레코드 루틴 `$864B`(입력 `$F8` = 아이템 번호 → 이름 14B 를 `$CFF1`, 값 3B 를 `$D000~$D002`, 꼬리 능력치를 `$D003~`)는 값을
「가수(꼬리[0]) × 10^지수(꼬리[1])」로 적어 두고 **지수만큼 고리를 돌며 ×10** 한다. 원판 고리(`$86AE~$86E0`, 51B)는 한 바퀴에 범용 곱셈 둘
(`$59C1` 16×16 · `$5962` 8×8)을 불러 **약 1,135 사이클**이고, 「버린다」를 확인한 프레임에 이 루틴이 **두 번** 불린다 ⇒ 지수 1 마다 주사선 약 5줄.

그 뒤에 원판이 창을 다시 그린다 — `$9D8B`(틀 안쪽 열 2·25 와 행 0·21 을 투명 타일 `0100` 으로) → 목록 창 지우기·다시 쓰기. 이 둘이 주사선이
목록 창 첫 줄(VDC Line 70)에 닿기 **전에** 끝나야 한 프레임 안에 「옛 글자 + 틀 스프라이트 조각」이 안 보인다. 값 지수가 0 이면 `$9D8B` 가 Line 52,
3 이면 Line 68(지우기는 그 10줄쯤 뒤) — 그래서 **비싼 아이템(지수 ≥ 3)만** 뚫렸다. 우리 글리프 길(`$2300`)이 원판 BIOS 길보다 느려 여유를 먹은 데다
원판의 느린 곱셈이 겹친 것이다(원판 롬의 비싼 아이템은 안 재 봤다 — 가설).

## 고침

같은 51B 자리에 24비트 제자리 ×10(= 2N + 8N, 시프트·덧셈만 — 한 바퀴 약 100 사이클)을 넣는다. 새 롬 실측(74148ba0 · 콜드 부팅):
`$9D8B` 가 지수 3 = Line 54(전 68) · 지수 6 = Line 56 — 지수 0 의 52 와 두어 줄 차이라 확인 뒤 첫 프레임이 지수와 무관하게 「빈 창」이다.
입력·출력은 원판 그대로다: 들어올 때 `$20` = 가수 · `$1E/$1F` = 0 · `$21` = 지수(≠0 — 0 이면 앞의 `BEQ $86E1` 이 건너뛴다),
나갈 때 값 = `$20`(하위) · `$1E`(중위) · `$1F`(상위), `$21` = 0. `$F8/$F9/$7F/$80` 은 고리 뒤(`$86FA~`)에서 원판이 다시 채우고 X·Y 는
Y 를 `$86A3` 에서 쌓아 두었으며 X 는 루틴이 안 쓴다 — 고리 안에서 자유다.

🔴 **원판 고리는 진짜 24비트 곱이 아니다** — 중위 덧셈의 올림을 상위에 안 올린다(`ADC $F9 / STA $1E` 뒤 `$1F` 를 안 건드린다). (가수 0~255) × (지수 0~7) 가운데
60쌍에서 진짜 곱과 다르다. 아이템 표 117종은 전부 같은 값이라(`check_items`) 바꿔도 화면 값이 같다 — 표가 바뀌어 한 종이라도 갈리면 **빌드가 죽는다**.
"""

import asm65

BANK = 0x6F
OFF = 0x06AE  # 뱅크 안 — 논리 `$86AE`(뱅크 0x6F 는 `$8000` 에 걸린다)
ORG = 0x8000 + OFF
END = 0x86E1  # 고리 뒤 첫 명령(`LDA $20 / STA $D000 …`)
OLD = bytes.fromhex(
    "a90a85f864f9a51e857fa51f858020c159"  # LDA #10 · STA $F8 · STZ $F9 · ($1F:$1E) → $7F/$80 · JSR $59C1
    "a5f8851ea5f9851f"  # 곱 → $1E/$1F
    "a90a85f8a520857f206259"  # LDA #10 · STA $F8 · $20 → $7F · JSR $5962
    "a5f88520a51e1865f9851e"  # 하위 → $20 · $1E += 올림(상위로는 안 올린다)
    "c621d0cd"  # DEC $21 · BNE 고리
)
LO, MID, HI, EXP, TMP = 0x20, 0x1E, 0x1F, 0x21, 0xF8


def code() -> bytes:
    a = asm65.Asm(ORG)
    a.L("loop")
    a.op("LDA", "zp", LO)
    a.op("ASL")
    a.op("STA", "zp", TMP)  # 2N 하위
    a.op("ROL", "zp", MID)
    a.op("LDX", "zp", MID)  # 2N 중위(LDX·LDY 는 올림을 안 건드린다)
    a.op("ROL", "zp", HI)
    a.op("LDY", "zp", HI)  # 2N 상위
    for _ in range(2):  # ×4 더 → 8N (하위는 A 에)
        a.op("ASL")
        a.op("ROL", "zp", MID)
        a.op("ROL", "zp", HI)
    a.op("CLC")
    a.op("ADC", "zp", TMP)
    a.op("STA", "zp", LO)
    a.op("TXA")
    a.op("ADC", "zp", MID)
    a.op("STA", "zp", MID)
    a.op("TYA")
    a.op("ADC", "zp", HI)
    a.op("STA", "zp", HI)
    a.op("DEC", "zp", EXP)
    a.op("BNE", "rel", "loop")
    a.labels["end"] = END
    a.op("BRA", "rel", "end")
    b = a.bytes()
    assert len(b) <= len(OLD), (len(b), len(OLD))
    return b + b"\xea" * (len(OLD) - len(b))  # 남는 칸은 안 지나간다(BRA 가 건너뛴다)


def price_orig(mant: int, exp: int) -> int:
    """원판 고리의 값 — 중위 올림을 상위에 안 올리는 것까지 그대로."""
    lo, mid, hi = mant, 0, 0
    for _ in range(exp):
        w = ((hi << 8 | mid) * 10) & 0xFFFF  # `$59C1` — 16×16 의 하위 16비트
        mid, hi = w & 0xFF, w >> 8
        p = lo * 10  # `$5962` — 8×8
        lo = p & 0xFF
        mid = (mid + (p >> 8)) & 0xFF
    return lo | mid << 8 | hi << 16


def price_new(mant: int, exp: int) -> int:
    return (mant * 10**exp) & 0xFFFFFF


def check_items(tails: list[bytes]):
    """아이템 표의 모든 (가수, 지수)에서 원판 고리와 새 고리의 값이 같아야 한다 — 다르면 화면의 값이 바뀐다."""
    bad = [
        (i, t[0], t[1])
        for i, t in enumerate(tails)
        if price_orig(t[0], t[1]) != price_new(t[0], t[1])
    ]
    assert not bad, f"값 고리 교체로 값이 달라지는 아이템(번호, 가수, 지수): {bad}"
