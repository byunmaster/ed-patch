"""ED1 → ED2 엔진 주소 대응표 — 후킹 자리를 ED2 에서 다시 잡은 것(2026-10-12).

    python3 tools/engine.py --check    # ED2 의 각 자리 바이트가 고정해 둔 지문과 같은지

ED2 의 텍스트 엔진은 ED1 과 **같은 코드가 다른 주소에 있다**(바이트가 그대로 일치한다 — 절대 주소를
피연산자로 갖는 명령만 다르다). 대응은 ED1 쪽 16B 창을 ED2 롬에서 찾는 앵커 맞춤으로 얻었고(구간마다
이동량이 다르다: 0x9xxx → +0x1FAC~0x1FB8, 0x1Exxx → +0x4378), 아래 자리는 **디스어셈블로 명령이 같음을
확인**한 것이다. ED1 의 `josa.py`·`wordwrap.py`·`punctwrap.py`·`halfspace.py`·`field_hud.py` 를 이식할 때
ED1 상수 대신 이 표의 ED2 주소를 쓴다.

⚠ 아직 이식하지 않았다(번역 라운드의 몫): 자막(`captions.py`) 영역은 ED2 의 오프닝·엔딩이 다른 구조일 수
있어 별도 조사가 필요하다. 시스템 메시지는 코드 영역에 아카이브 밖 SJIS 런으로 있다(status.md).
"""

import hashlib
import sys

import common

# (이름, ED1 주소, ED2 주소, 길이, ED2 바이트의 sha1 앞 12자)
SITES = [
    ("lz_decomp", 0xC9E, 0xE04, 32, "256a1ef1ff4d"),
    ("font_lookup", 0x9BA0, 0xBB58, 40, "c495fdb099f0"),
    ("render", 0x978C, 0xB738, 32, "211592a30f63"),
    ("arglen_tbl", 0x9FE2, 0xBF9A, 54, "b9fdcfe037f6"),
    ("handler_tbl", 0xA018, 0xBFD0, 64, "311da330d439"),
    ("dead_handler", 0xA4D2, 0xC48A, 30, "b9b79c8f2068"),
    ("name_fn", 0xA94A, 0xC93C, 32, "50ab07e982fb"),
    ("name_fn_patch", 0xA94E, 0xC940, 6, "9b1a753e0813"),
    ("punct_site", 0xA9BE, 0xC9B0, 6, "a863fd78be88"),
    ("half_site", 0x9898, 0xB844, 6, "63a37a815407"),
    ("half_draw", 0x9B32, 0xBAEA, 32, "5fb2de3d662c"),
    ("field_space", 0x1EC6A, 0x22FE2, 8, "65630cb7bda6"),
    ("field_align", 0x1ED30, 0x230A8, 2, "354691ba25af"),
]
ED2 = {name: addr for name, _a1, addr, _n, _h in SITES}


def check() -> None:
    d = common.rom()
    for name, _a1, a2, n, h in SITES:
        got = hashlib.sha1(d[a2 : a2 + n]).hexdigest()[:12]
        if got != h:
            raise SystemExit(f"엔진 자리 {name} @{a2:#x} 가 고정 지문과 다르다 ({got} ≠ {h})")
    print(f"  엔진 대응 {len(SITES)}곳 지문 OK (ED1 → ED2 주소 이동 0x1FAC~0x4378)")


if __name__ == "__main__":
    if "--check" not in sys.argv:
        for name, a1, a2, n, _h in SITES:
            print(f"{name:14s} ED1 {a1:#08x} → ED2 {a2:#08x} ({n}B, 이동 {a2 - a1:+#x})")
    else:
        check()
