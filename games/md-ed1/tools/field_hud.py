"""필드 HUD 지명 뒷말(부근·입구) · 방위(동서남북) — 텍스트맵을 거치지 않는다.

    python3 tools/field_hud.py --check   # 여덟 자리가 원본과 같은 값인지 검산

## 왜 깨졌나 (마스터 지적 2026-09-27, 캡처 m39~m41)

필드에서 마을과 떨어져 있을 때 HUD 아래 칸에 뜨는 「엘아스타 부근」·「엘아스타 입구」와 동서남북은
`textmap/*.json` 을 안 거친다. 루틴(`$1EC20`)이 SJIS 코드를 **그대로** 레지스터에 찍거나(방위,
`move.w #$938C,d6` 류) ROM 리터럴 문자열을 복사한다(뒷말, `$1ED0C`=「付近」·`$1ED10`=「入口」).
`hangul.py` 가 번역이 안 쓰는 한자 칸을 한글로 갈아엎으면서, 이 여덟 코드가 우연히 가리키던 자리도
같이 갈렸다 — `0x8bdf`(近)는 「암」, `0x8cfb`(口)는 「할」이 됐다(부근/입구 첫 글자 자리 `0x9574`·
`0x93fc` 는 아직 아무도 안 써서 빈칸). 화면에 「엘아스타 암」·「엘아스타 할」로 뜬 게 그 결과다.

## 고치는 법

여덟 자리 전부 **2B 코드 하나를 다른 2B 코드로**(길이 불변) 바꾸는 것뿐이다 — 우리가 이미 쓰는
한글 코드(`textmap/hangul_codes.json`)로 갈아 끼운다. `부·근·입·구·동·서·남·북` 은 이미 다른
문안에서 쓰여 코드가 고정돼 있다(빌드가 없다고 실패시킨다 — `hangul.Charset`).

자리 여섯은 **즉값**(레지스터에 직접 찍는 명령의 피연산자)이고 둘은 **리터럴 문자열**(4B, 2글자)이다.
즉값 중 둘(`$1ECA4`·`$1ECC8`)은 **비교값**이다 — 위쪽에서 찍은 북/동 코드와 **똑같아야** 캐시
플래그(`$FF1FDE`, 다시 안 그려도 되는지 판정)가 안 흔들린다.

## 뒷말·방위 앞 공백 (마스터 지시 2026-09-27 밤 — 기종 공통 규칙)

이름과 뒷말·방위 사이에 원판엔 공백이 없다(「エルアスタ付近」 그대로 붙는다) — 마스터가 「입구·부근·
방위 앞은 띄운다」로 정해서 하나 넣는다. `movea.l a3,a2`(0x1EC6A, 2B) 로 출력 버퍼를 잡는 자리가
방위·뒷말 두 갈래 **모두의 공통 진입점**이라 여기 한 곳에서 반각 공백 하나(`$20`, 6px)를 써 넣으면
끝난다 — 이어지는 `lea.l $1ED10,a1`(6B)까지 합쳐 12B 가 필요한데 원래 자리는 8B 뿐이라, 통째로
`jmp <꼬리>`(6B, 남는 2B 는 죽은 자리로 둔다)로 옮기고 거기서 원래 두 명령 + 공백 쓰기를 한 뒤
0x1EC72(다음 원래 코드)로 되돌아간다. 코드 흐름 나머지는 안 건드린다.

## 박스 오른쪽 넘침 — 가운데 정렬을 왼쪽 정렬로 (마스터 지적 2026-09-27 밤, 캡처 m57)

「크루즈마을 부근」처럼 이름이 길면 뒷말이 박스 오른쪽을 뚫는다. 지명 표(`place_a`/`place_b`)는
12B 칸에 **가운데 정렬**로 굽는데($1ED14`, `$1EC20` 의 유일한 호출자 — 다른 곳에서 안 쓴다), 이 함수가
**런타임에 다시** 앞뒤 공백을 트림하고 원래 칸의 빈 칸 수(`총 공백 바이트 − 2) / 2`)만큼 **앞에** 공백을
채워 되돌린다. 원문(JP) 12B 기준으로 짠 공식이라 글자 수가 다른 한글 지명에서는 앞 여백이 이름마다
들쭉날쭉하고, 특히 **짧은 지명일수록 앞 여백이 커져 뒷말이 더 오른쪽에서 시작**한다.

**마스터 재판정(2026-09-27 밤 늦게)**: 왼쪽 정렬 대신 **가운데 정렬을 유지**한다(pc98·새턴 배너도 같은
방향). 왼쪽 정렬로 껐던 2026-09-27 밤 초판은 걷고, 공식의 **상수만** 고쳐 다시 가운데 정렬한다.

원래 식은 `d1`(그 12B 칸의 총 공백 바이트 수 — 이름이 짧을수록 크다) 하나로 `(d1−2)/2` 를 낸다.
`d1 = 12 − 이름폭(반칸 단위)` 이므로 이름만 12칸 상자에 넣고 중앙을 맞추는 식이다 — **뒷말은 아예
모르는 식**이라 뒷말을 붙이면 그만큼 오른쪽으로 밀려난다.

`$1EC20` 이 호출하는 순서(이름을 먼저 자리 잡고, 그 **뒤에** 방위·뒷말을 거리로 판정해 붙인다)를
바꾸지 않고도 고치는 법 — **뒷말·방위 중 가장 넓은 경우(뒷말 2글자 + 앞 공백, 반칸 5칸)를 상수에
미리 얹는다.** `(d1 − 2)/2` 를 `(d1 − 1)/2` 로: 상수 2 는 「12칸 상자에서 이름만 중앙」이고 상수 1 은
「이름 + 뒷말 최대 폭(5칸)을 합쳐 16칸 상자에서 중앙」과 같은 식이 된다(유도는 `d1=12−이름폭` 대입해
정리하면 나온다). 자리 표(place_a/b) **50개 전부**로 계산해 **밑돌지 않음을 확인**했다(가장 긴
5음절 지명 10곳 모두 `front_pad=0` — 왼쪽 정렬과 같은 안전한 값, 나머지는 0~3칸). 방위만 붙는(뒷말보다
좁은) 경우는 여백을 실제보다 넉넉히 잡아 **살짝 왼쪽 치우친 가운데** 가 된다 — 넘칠 위험은 없다.

`subq.b #2,d1`(0x1ED30, 원래 값)을 `subq.b #1,d1` 로 — 명령 모양은 원판과 완전히 같고 상수만
바꿨다(즉값 1바이트). 자리·크기 그대로라 트램펄린이 필요 없다. 박스 실제 폭(px)을 몰라 **반칸 5칸을
예비로 미리 까는 근사**다 — 정확한 폭을 알면 상수를 더 정밀하게 맞출 수 있다.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SPACE_SITE = 0x1EC6A  # movea.l a3,a2 (2B) + lea.l $1ED10,a1 (6B) — 방위·뒷말 공통 진입점
SPACE_SITE_LEN = 8
SPACE_RESUME = 0x1EC72  # 원래 흐름으로 되돌아갈 자리(공백 삽입 다음 원래 명령)
SPACE_A1 = 0x1ED10  # lea 가 원래 가리키던 곳("입구") — 트램펄린에서 복제한다
SPACE_TRAMP_LEN = 18  # movea(2)+move.b#imm(4)+lea(6)+jmp(6)

ALIGN_SITE = 0x1ED30  # subq.b #2,d1 — 가운데 정렬 앞 공백 계산의 상수. 즉값 1바이트만 바꾼다
ALIGN_PATCH = b"\x53\x01\xe2\x09"  # subq.b #1,d1 (뒷말 최대폭 5칸을 미리 반영) + lsr.b #1,d1(원본 그대로)

# (자리, 글자) — 즉값 이동/비교 명령의 피연산자 2B. 전부 같은 함수(`$1EC20`) 안.
DIRECTIONS = [
    (0x1EC3C, "서", "move.w #서,d6 — 서쪽 기본값"),
    (0x1EC46, "동", "move.w #동,d6 — 동쪽"),
    (0x1EC5A, "북", "move.w #북,d3 — 북쪽 기본값"),
    (0x1EC64, "남", "move.w #남,d3 — 남쪽"),
    (0x1ECA4, "북", "cmpi.w #북,d3 — 북/남 갈림(캐시 플래그), 위 북 값과 같아야 한다"),
    (0x1ECC8, "동", "cmpi.w #동,d6 — 동/서 갈림(캐시 플래그), 위 동 값과 같아야 한다"),
]
# (자리, 낱말) — 4B 리터럴 문자열(2글자). 出典 위치는 표 0x1ED0C(付近)·0x1ED10(入口).
SUFFIX = [
    (0x1ED0C, "부근", "「부근」— 마을과 떨어졌을 때"),
    (0x1ED10, "입구", "「입구」— 마을 그 칸일 때"),
]


def space_tramp(at: int) -> bytes:
    """트램펄린 본체 — 원래 명령 둘 + 공백 하나, 그리고 원래 흐름으로 복귀."""
    b = bytearray()
    b += struct.pack(">H", 0x244B)  # movea.l a3,a2
    b += struct.pack(">H", 0x14FC) + struct.pack(">H", 0x0020)  # move.b #$20,(a2)+
    b += struct.pack(">H", 0x43F9) + struct.pack(">I", SPACE_A1)  # lea.l $1ED10.l,a1
    b += struct.pack(">H", 0x4EF9) + struct.pack(">I", SPACE_RESUME)  # jmp $1EC72.l
    assert len(b) == SPACE_TRAMP_LEN, len(b)
    return bytes(b)


def plan(cs, tramp_at: int) -> list[tuple[str, int, bytes]]:
    """`cs` 는 `hangul.Charset` — 순환 임포트를 피해 타입은 안 박는다."""
    out = []
    for i, (addr, ch, _why) in enumerate(DIRECTIONS):
        out.append((f"field-hud-dir:{i}", addr, cs.encode_char(ch)))
    for i, (addr, word, _why) in enumerate(SUFFIX):
        out.append((f"field-hud-suffix:{i}", addr, cs.encode(word)))
    out.append(("field-hud-space-tramp", tramp_at, space_tramp(tramp_at)))
    out.append(
        (
            "field-hud-space-site",
            SPACE_SITE,
            struct.pack(">H", 0x4EF9) + struct.pack(">I", tramp_at),
        )
    )
    out.append(("field-hud-align", ALIGN_SITE, ALIGN_PATCH))
    return out


def chars() -> set[str]:
    """이 패치가 쓰는 글자 — `collect_chars()` 가 다른 문안과 상관없이 늘 구워 둔다."""
    return set("부근입구동서남북")


ORIG = {
    0x1EC3C: b"\x90\xbc",  # 西
    0x1EC46: b"\x93\x8c",  # 東
    0x1EC5A: b"\x96\x6b",  # 北
    0x1EC64: b"\x93\xec",  # 南
    0x1ECA4: b"\x96\x6b",  # 北
    0x1ECC8: b"\x93\x8c",  # 東
    0x1ED0C: b"\x95\x74\x8b\xdf",  # 付近
    0x1ED10: b"\x93\xfc\x8c\xfb",  # 入口
    SPACE_SITE: b"\x24\x4b\x43\xf9\x00\x01\xed\x10",  # movea.l a3,a2 + lea.l $1ed10,a1
    ALIGN_SITE: b"\x55\x01\xe2\x09",  # subq.b #2,d1 + lsr.b #1,d1
}


def check(d: bytes) -> None:
    for addr, orig in ORIG.items():
        got = d[addr : addr + len(orig)]
        if got != orig:
            raise SystemExit(f"필드 HUD 자리 {addr:#x} 가 예상과 다르다: {got.hex()} ≠ {orig.hex()}")
    print(f"  필드 HUD 뒷말·방위 — 여덟 자리 원본과 일치 ({len(ORIG)}곳)")


if __name__ == "__main__":
    check(common.rom())
