"""세피아 레터박스의 검은 띠에 자막을 띄운다 — 패키지 38(대관식)의 화면 설정 패치 (2026-10-15 마스터 「무조건 까만색에 나오게」).

원판은 세피아 장면에서 VDC 표시창을 128줄(VDR=127)로 줄여, 위·아래 띠(각 52줄)가 **표시창 밖**이라 스프라이트가 안 그려진다.
그래서 표시창을 항상 전체 높이(232줄)로 두고, 띠에는 BG 를 꺼서 검정으로 만든다(스프라이트는 켜 둔다 → 자막이 띠에 뜬다).

  1. 화면모드 루틴(논리 `$4216~`)이 높이 변수 `$26E6` 을 읽는 두 곳 → 도우미: 세피아(0x80)면 232, 아니면 그대로
     (장면 전환 때 게임이 높이를 줄여 화면을 끄는 경로도 살린다).
  2. 매 프레임 BXR/BYR 쓰기(`$40B6` 자리) → 훅: 세피아면 BYR += 460(그림이 52줄 아래, 원래 자리), RCR = 그림 시작 줄,
     CR = 래스터 IRQ 켬·BG 끔(위 띠 검정). 원래 CR 의 BB·SB 는 BIOS 그림자 `$F3` 를 프레임 시작에 저장해 둔다
     (`$30` 은 우리가 고친 값이 남아 못 쓴다 — 오인하면 BG 가 꺼진 채 남는다).
  3. 게임 자체 IRQ1 핸들러(`$403C`, `$2202` 벡터) 의 래스터 분기(원래는 그냥 반환) → 우리 핸들러: 단계 P 로
     0→1 그림 시작(BG 를 게임이 원한 대로 켬) · 1→2 그림 끝(BG·스프라이트 끔) · 2→3 스프라이트 복귀(자막 바로 위 줄).
     게임이 화면을 꺼 둔 동안(CR=0x08)엔 켜지 않는다 → 장면 전환이 원판과 같다.
  4. 게임 스프라이트(얼굴·머리카락) Y 기준 `CLC·ADC #$40·STA $51`(`$4B51`) → 세피아면 +52: 표시창이 52줄 일찍 시작하므로.
     **만드는 자리에서** 높이를 본다(VBlank 훅에서 상수를 고치면 장면 첫 프레임에 한 프레임 어긋났다).
경계는 원판 표시창과 같다: 화면 줄 55~182(원판 실측 — BYR 460 으로 그림 0행이 줄 55, 그 위 두 줄은 BAT 아래쪽의 다른 자료라 가린다). 줄 = RCR − 60. 마스터가 「한 줄 안쪽」을 정했으나 원판 범위를 잘못 알고 잡은 값이라 원판과 같게 바로잡았다.

⚠ 손으로 인코딩한 기계어다 — `tools/tests/test_band.py` 가 바이트 구조(분기 거리·자리)를 검산하고, 빌드가 원본 바이트를 대조한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

B = bytes.fromhex

RCR_TOP = 115  # 이 값−60 = 55: 그림 시작(BG 켬) — 원판 세피아 표시창은 화면 줄 55~182(실측: 세 구간 네 그림 모두)
RCR_BOT = 243  # 183: 그림 끝 다음(BG·스프라이트 끔)
RCR_SBON = 246  # 186: 스프라이트 복귀(자막 첫 줄 y187 직전)
RUN2_OFF = 0x1E98  # 뱅크 0x6A 의 둘째 0xFF 런(344B, 논리 $9E98) — 첫 런(스텁 374B)은 훅만 두면 찬다
RUN2_MAX = 344

SEGMENTS = ((23.8, 38.7), (60.8, 84.2), (101.6, 112.1))  # 세피아(레터박스) 구간(초) — 높이 변수 `$26E6` 쓰기 브레이크포인트 실측(10-15): 대관식은 셋


def in_band(t: float) -> bool:
    """그 시각의 자막이 검은 띠 안(세피아 구간)인가 — 띠 안 한 줄은 첫째 줄 높이(2-14)."""
    return any(a <= t <= b for a, b in SEGMENTS)


# 패키지 안 오프셋(패키지 38 = 뱅크 0x68 부터, 논리 = 0x4000 + 오프셋)
SITE_HEIGHT = (0x259, 0x27B)  # `LDA $26E6`
SITE_BYR = 0x0B6  # `LDA $2212·STA $0002·LDA $2213·STA $0003`(12B)
SITE_SPR = 0xB51  # `CLC·ADC #$40·STA $51`(5B)
SITE_IRQ = 0x040  # `BIT #$04·BNE · BIT #$10·BNE`(8B)
OLD_BYR = B("ad12228d0200ad13228d0300")
OLD_SPR = B("18694085" "51")
OLD_IRQ = B("8904d0f68910d0f2")
OLD_HEIGHT = B("ade626")


def _resolve(items):
    """[(바이트 | ("lbl", 이름) | ("br", 옵코드, 이름))] → 바이트열."""
    pos, lab = 0, {}
    for it in items:
        if isinstance(it, bytes):
            pos += len(it)
        elif it[0] == "lbl":
            lab[it[1]] = pos
        else:
            pos += 2
    out, pos = b"", 0
    for it in items:
        if isinstance(it, bytes):
            out += it
            pos += len(it)
        elif it[0] == "lbl":
            pass
        else:
            d = lab[it[2]] - (pos + 2)
            assert -128 <= d < 128, (it, d)
            out += bytes([it[1], d & 0xFF])
            pos += 2
    return out


def gen(p_at):
    """(VBlank 훅, 래스터 핸들러, 스프라이트 Y 도우미). `p_at` = 단계 P 바이트 주소(다음 바이트가 저장한 CR)."""
    lo, hi = p_at & 0xFF, p_at >> 8
    olo, ohi = (p_at + 1) & 0xFF, (p_at + 1) >> 8
    hl, cn, kk = (p_at + 2), (p_at + 3), (p_at + 4)
    L2 = lambda v: bytes([v & 0xFF, v >> 8])  # noqa: E731
    # 장면 전환 강제 닫기: 높이 변수가 바뀌면 3프레임 동안 스프라이트(SB)를 끈다 — 전환 직후 첫 그림 프레임에 직전 자막의 깨진 조각이 비치던 것(틱이 그림 읽기 겹침 가드로 미뤄 못 닫는다). K = SB 마스크
    pre = _resolve([
        B("ade626 cd") + L2(hl), ("br", 0xF0, "nochg"), B("8d") + L2(hl) + B("a903 8d") + L2(cn),
        ("lbl", "nochg"), B("ad") + L2(cn), ("br", 0xF0, "ok"), B("ce") + L2(cn), ("br", 0xF0, "last"),
        B("a9bf 8d") + L2(kk) + B("a530 29bf 8530"), ("br", 0x80, "go"),
        ("lbl", "last"), B("a9ff 8d") + L2(kk) + B("a5f3 8530"), ("br", 0x80, "go"),  # 마지막 억제 프레임 다음: $30 을 게임 값으로 되돌린다
        ("lbl", "ok"), B("a9ff 8d") + L2(kk),
        ("lbl", "go"),
    ])
    msk = B("2d") + L2(kk)  # AND K
    sep = (
        B("0306 a9") + bytes([RCR_TOP]) + B("8d0200 9c0300 0308")  # ST0 #6 · RCR = 그림 시작 줄 · ST0 #8(BYR 로 되돌린다)
        + B("9c") + bytes([lo, hi])  # P = 0
        + B("a5f3") + msk + B("8d") + bytes([olo, ohi])  # 게임이 원한 CR(억제 중이면 SB 뺀 것) 저장
        + B("a5f3") + msk + B("0904 297f 8530")  # $30 = ($F3 & K | 래스터 IRQ) & ~BB
        + B("ad1222 18 69cc 8d0200 ad1322 6901 2901 8d0300 60")  # BYR = $2212 + 460
    )
    normal = B("ad1222 8d0200 ad1322 8d0300 60")
    hook = pre + B("ade626 c980") + bytes([0xD0, len(sep)]) + sep + normal
    items = [
        B("2904"), ("br", 0xF0, "out"), B("da"),  # AND #$04 · BEQ out · PHX
        B("ae") + bytes([lo, hi]), ("br", 0xF0, "s1"), B("e001"), ("br", 0xF0, "s2"),  # LDX P · BEQ s1 · CPX #1 · BEQ s2
        B("a903 8d") + bytes([lo, hi]) + B("ad") + bytes([olo, ohi]) + B("2940 0530 8530 a2ff"), ("br", 0x80, "wr"),  # 2→3: SB 를 원한 대로
        ("lbl", "s1"),
        B("a901 8d") + bytes([lo, hi]) + B("a530 297f 8530 ad") + bytes([olo, ohi]) + B("2980 0530 8530 a2") + bytes([RCR_BOT]),
        ("br", 0x80, "wr"),  # 0→1: BB 를 원한 대로
        ("lbl", "s2"),
        B("a902 8d") + bytes([lo, hi]) + B("a530 293f 8530 a2") + bytes([RCR_SBON]),  # 1→2: BB·SB 끔
        ("lbl", "wr"),
        B("0305 a530 8d0200 a531 8d0300 0306 8e0200 e0ff"), ("br", 0xD0, "lo"), B("a903"), ("br", 0x80, "hi"),  # CR 쓰기 · RCR = X(0xFF 면 0x3FF)
        ("lbl", "lo"), B("62"),
        ("lbl", "hi"), B("8d0300 a5f7 8d0000 fa"),  # 선택 레지스터 복원 · PLX
        ("lbl", "out"), B("4c3a40"),  # JMP $403A(원래 반환)
    ]
    ras = _resolve(items)
    spr = B("8551 ade626 c980 d008 a551 18 6974 8551 60 a551 18 6940 8551 60")
    return hook, ras, spr


HEIGHT_HELPER = B("ade626 c980 d002 a9e8 60")  # LDA $26E6 · CMP #$80 · BNE +2 · LDA #232 · RTS


def spans(pkg, base, lin, stub_bank, stub_off, stub_len, stub_lin):
    """[(선형 오프셋, 새 바이트, 기대 원본, 라벨)] — `pkg` = 원본 패키지 38 바이트, `base` = 그 선형 시작, `lin(뱅크, 오프셋)` = 선형 위치."""
    hook0, ras0, spr0 = gen(0x9000)
    ras_at = 0x8000 + RUN2_OFF
    spr_at = ras_at + len(ras0)
    hgt_at = spr_at + len(spr0)
    p_at = hgt_at + len(HEIGHT_HELPER)
    hook, ras, spr = gen(p_at)
    assert len(hook) == len(hook0) and len(ras) == len(ras0) and len(spr) == len(spr0)
    hook_at = 0x8000 + stub_off + stub_len
    run2 = ras + spr + HEIGHT_HELPER + b"\x00" * 5  # P · 원한 CR · 마지막 높이 · 억제 카운트 · SB 마스크
    assert len(run2) <= RUN2_MAX, len(run2)
    r2 = lin(stub_bank, RUN2_OFF)
    assert pkg[r2 - base : r2 - base + len(run2)] == b"\xff" * len(run2), "둘째 0xFF 런이 비어 있지 않다"
    h_lin = lin(stub_bank, stub_off + stub_len)
    assert pkg[h_lin - base : h_lin - base + len(hook)] == b"\xff" * len(hook), "첫 0xFF 런에 훅이 안 든다"
    for site, old in ((SITE_HEIGHT[0], OLD_HEIGHT), (SITE_HEIGHT[1], OLD_HEIGHT), (SITE_BYR, OLD_BYR), (SITE_SPR, OLD_SPR), (SITE_IRQ, OLD_IRQ)):
        assert pkg[site : site + len(old)] == old, hex(site)
    out = [
        (h_lin, hook, b"\xff" * len(hook), "검은 띠: VBlank 훅(BYR·RCR·CR)"),
        (r2, run2, b"\xff" * len(run2), "검은 띠: 래스터 핸들러·스프라이트 Y·높이 도우미"),
        (base + SITE_BYR, bytes([0x20, hook_at & 0xFF, hook_at >> 8]) + b"\xea" * 9, OLD_BYR, "검은 띠: BXR/BYR 쓰기 → 훅"),
        (base + SITE_SPR, bytes([0x20, spr_at & 0xFF, spr_at >> 8, 0xEA, 0xEA]), OLD_SPR, "검은 띠: 스프라이트 Y 기준 → 도우미"),
        (base + SITE_IRQ, B("8914f003 4c".replace(" ", "")) + bytes([ras_at & 0xFF, ras_at >> 8, 0xEA]), OLD_IRQ, "검은 띠: IRQ 래스터 분기 → 핸들러"),
    ]
    for off in SITE_HEIGHT:
        out.append((base + off, bytes([0x20, hgt_at & 0xFF, hgt_at >> 8]), OLD_HEIGHT, "검은 띠: 화면모드 높이 → 도우미"))
    return out, {"band": len(hook) + len(run2)}
