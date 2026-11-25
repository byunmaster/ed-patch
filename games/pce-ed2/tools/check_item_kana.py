"""항목 토큰이 그리는 원문 가나 잔존 게이트 — 번역한 줄의 `1D xx`(항목 이름 + 조사 가나 xx 한 글자)가 가나를 그대로 두면 실패한다 (마스터 11-17).

    python3 games/pce-ed2/tools/check_item_kana.py [ISO 경로] [--gate]   # 기본 = 제품 이미지

왜: 상점 판매 줄이 「천 옷は은」 로 나갔다 — 항목 토큰 `1D CA` 가 이름 뒤에 가나 「は」 를 직접 그리는데, 번역한 틀은 그 뒤에 한국어 조사를 얹었다.
`ctrllines.blank_item_particle` 이 「뒤에 공백이 올 때」만 가나를 지워서 판매·줍기 줄이 샀다. 일본어 잔존 게이트(`residual_gate`)는 가나 4자↑ 연속·원문 글리프 줄을 보므로
**제어 토큰이 그리는 가나 한 글자**는 원리상 안 보인다(바이트에 가나가 없다 — 토큰의 인자일 뿐).
검사: 제품의 본편 패키지 13개(`package.CLEAN`)와 디버그 도달 패키지(`residual_gate.DEBUG_RELS`)의 메시지 줄 중 **한글 글리프(리드 `F0~F9`)가 든 줄**(= 번역한 줄)에서 `1D xx` 의 xx 가 빈 칸(`60`)이 아니면 실패.
번역 안 한 일본어 줄은 이 검사 밖이다(잔존 게이트 몫).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import jptext
import package
import residual_gate


def kana_args(line: bytes) -> list[int]:
    """줄의 `1D xx` 중 xx 가 빈 칸이 아닌 것의 xx 목록. 한글 글리프가 없는 줄(번역 안 한 줄)은 빈 목록."""
    out = []
    has_ko = False
    i = 0
    while i < len(line):
        a = line[i]
        if a < 0x20:
            if a == 0x1D and i + 1 < len(line) and line[i + 1] != 0x60:
                out.append(line[i + 1])
            i += 1 + jptext.ARGS.get(a, 0)
        elif a == 0xFF:  # 채움 한 바이트(조사 토큰 앞뒤에 낀다) — 두 바이트 글자의 리드가 아니다
            i += 1
        elif 0x80 <= a <= 0x9F or a >= 0xE0:
            if 0xF0 <= a <= 0xF9:
                has_ko = True
            i += 2
        else:
            i += 1
    return out if has_ko else []


def _msgs_or_empty(track, rel: int) -> dict[int, bytes]:
    try:
        return residual_gate._msgs(track(rel))
    except (ValueError, IndexError, KeyError):
        return {}


def scan(iso: Path) -> list[str]:
    track = residual_gate._built(iso)
    bad: list[str] = []
    for rel in [*package.CLEAN, *residual_gate.DEBUG_RELS]:
        msgs = _msgs_or_empty(track, rel)
        for m, d in msgs.items():
            lines = d.split(b"\x00")[:-1]
            if (
                len(lines) > 400
            ):  # 패키지 꼬리(압축 자료)가 덩이로 잡힌 것(residual_gate 와 같은 거름)
                continue
            for li, line in enumerate(lines):
                xs = kana_args(line)
                if xs:
                    bad.append(f"{rel}:{m}:{li} 1D {' '.join(f'{x:02X}' for x in xs)}")
    return bad


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    iso = Path(args[0]) if args else common.BUILD_DIR / common.BUILD_TAG / f"{common.ROM_STEM}.iso"
    bad = scan(iso)
    for b in bad:
        print("  가나 잔존", b)
    if "--gate" in sys.argv:
        if bad:
            print(f"❌ 항목 토큰 가나 잔존 {len(bad)}줄 (`blank_item_particle` 이 못 지운 `1D xx`)")
            return 1
        print("✅ 항목 토큰 가나 잔존 0줄")
    else:
        print(f"{len(bad)}줄")
    return 0


if __name__ == "__main__":
    sys.exit(main())
