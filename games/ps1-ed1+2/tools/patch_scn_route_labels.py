#!/usr/bin/env python3
"""065 — ED2SCN10·ED2SCN13 안에 경로 라벨("이슈타~이즈" 등)이 원문 그대로 남아 있었다.

`patch_ed2_sys.HALFWIDTH_ROUTE_LABELS`(ED2.EXE 0xAB10 부근)는 이미 번역돼 있는데,
**같은 문자열이 SCN 오버레이 안에도 사본으로 박혀 있었다** — "늑대의입"(058ⓑ)과
같은 부류(마스터가 화면에서 "이슈타～이즈"를 봤다고 알려 발견, 2026-09-14).

슬롯 크기가 자리마다 다르다(원문 뒤 널 개수가 1~7개로 제각각) — 그래도 **전각
KR+널이 "원문 길이 + 뒤따르는 널 개수"를 안 넘으면 안전**하다. 값으로 확인: 9종 중 8종은 전각이 들어가고, `큐베라~프로스`
하나만 12B 남짓한 슬롯에 전각 14B가 안 들어가 반각이 필요하다 — **ED2.EXE 표와
정확히 같은 결론**(그쪽도 그 하나만 반각이었다).

🔴 **슬롯이 넉넉한 것과 화면에 온전히 나가는 것은 다른 물음이다**(2026-09-20 RE 로
발각, 마스터 QA 006·012). 이 독스트링엔 원래 「널종단 읽기라 우리 널 뒤는 안 읽힌다」가
근거로 적혀 있었는데 **틀렸다** — HUD 로 옮기는 코드는 널종단이 아니라 컴파일러가
**JP 원문 길이에 맞춰 인라인한 고정 길이 복사**다. 슬롯엔 들어가도 복사가 짧아 널이
안 실리거나 글자 중간에서 끊긴다. 그 뒤처리는 `patch_scn_hud_copy` 가 맡는다 —
**여기서 문자열을 늘리면 그쪽이 같이 돌아야 한다**(build.py 가 이 뒤에 부른다).

⚠ **SCN 오프셋은 `_scn_layout()` 으로 매번 다시 얻는다** — ED1SCN5 재배치 사고
(2026-09-14)를 여기서 반복하지 않는다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hangul_map as H
from common import BUILD_DIR, extract, write_user_data
from patch_sys_ui import _scn_layout

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"
SCN_TARGETS = ("ED2SCN10", "ED2SCN13")

# (JP 반각 원문 바이트, 전각 KR) — None 이면 반각 표를 쓴다.
# 🔴 구분자는 물결표에서 줄표(ASCII '-')로 전환(마스터 확정 2026-09-15) — `patch_ed2_sys`
# 의 같은 전환과 이유가 같다(ASCII 0x7E 가 이 폰트에서 오버라인으로 그려진다).
FULLWIDTH_LABELS = (
    (bytes.fromhex("b2bcadc08160b2bddeb0"), "이슈타-이즈"),
    (bytes.fromhex("b2bcadc08160b1ccd9"), "이슈타-아훌"),
    (bytes.fromhex("b2bddeb081608fe9"), "이즈-성"),
    (bytes.fromhex("b7adcdded781608fe9"), "큐베라-성"),
    (bytes.fromhex("b7adcdded78160b3b2d9"), "큐베라-윌"),
    (bytes.fromhex("b3b2d98160cdded9dd"), "윌-베른"),
    (bytes.fromhex("b1ccd981608fe9"), "아훌-성"),
    (bytes.fromhex("b3b2d981608fe9"), "윌-성"),
)
# 큐베라-프로스 — 전각 14B가 슬롯을 넘는다(ED2.EXE 표와 같은 결론). 062 조각 코드로
# (`patch_hangul_glyph_table.ROUTE_CODES`, 11코드 — 원문과 정확히 같은 길이라 슬롯
# 전체를 한 번에 덮는다). 마스터 도안(`ROUTE_GRID`)이 줄표를 그림 안에 직접 그려
# 넣으므로 여기서 구분자를 따로 안 넣는다.
HALFWIDTH_LABEL_JP = bytes.fromhex("b7adcdded78160ccdfdbbd")


def _enc_full(kr):
    out = bytearray()
    for ch in kr:
        out += H.encode_kr(ch) if "가" <= ch <= "힣" else ch.encode("shift_jis")
    return bytes(out)


def _find_all(buf, pat):
    out, s = [], 0
    while True:
        i = buf.find(pat, s)
        if i < 0:
            return out
        out.append(i)
        s = i + 1


def apply():
    import patch_hangul_glyph_table as G

    layout = {name: (lba, size) for name, lba, size in _scn_layout()}
    half_kb = bytes(G.ROUTE_CODES)
    assert len(half_kb) == len(HALFWIDTH_LABEL_JP), (
        f"062 조각 코드 {len(half_kb)}B != 원문 {len(HALFWIDTH_LABEL_JP)}B — 슬롯 전체를 못 덮는다"
    )
    n = 0
    for scn in SCN_TARGETS:
        lba, size = layout[scn]
        buf = bytearray(extract(lba, size, path=IMG))
        for jp, kr in FULLWIDTH_LABELS:
            kb = _enc_full(kr) + b"\x00"
            for off in _find_all(bytes(buf), jp):
                assert bytes(buf[off : off + len(jp)]) == jp, f"{scn}@0x{off:X} 원본 불일치"
                buf[off : off + len(kb)] = kb
                n += 1
        jp_half = HALFWIDTH_LABEL_JP
        for off in _find_all(bytes(buf), jp_half):
            assert bytes(buf[off : off + len(jp_half)]) == jp_half, (
                f"{scn}@0x{off:X}(반각) 원본 불일치"
            )
            buf[off : off + len(half_kb)] = half_kb
            n += 1
        with open(IMG, "r+b") as f:
            write_user_data(f, lba, bytes(buf), label=f"{scn} 065 경로 라벨 사본")
        # 되읽기 — 파일 전체에서 원문이 하나도 안 남았는지(전각 8종 + 반각 1종 모두)
        buf2 = extract(lba, size, path=IMG)
        remaining = sum(len(_find_all(bytes(buf2), jp)) for jp, _ in FULLWIDTH_LABELS)
        remaining += len(_find_all(bytes(buf2), jp_half))
        assert remaining == 0, f"{scn} 되읽기 — 원문이 아직 {remaining}곳 남음"
    print(f"  065 경로 라벨 사본(SCN) {n}곳 번역 — {', '.join(SCN_TARGETS)}")
    return n


if __name__ == "__main__":
    sys.exit(0 if apply() else 1)
