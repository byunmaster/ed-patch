"""
풀 파이프라인 개념증명: Galmuri 완성형 2,350자 폰트 탑재 + 한국어 문장 출력.

1) ED.EXE 한자 1급 슬롯 앞 2,350칸에 Galmuri11 음절 글리프 기록 (hangul_map 배치)
2) ED1SCN1.BIN 첫 NPC 대사 「あ、王子さま いらっしゃい。」(27B)를
   「어서오세요 왕자님 반가워요 」(27B, 동일 길이)로 교체
3) EDC 재계산 → work/Eiyuu Densetsu (PoC KR).bin/.cue

성공 기준: 시작 마을 훈련사 대사 첫 줄이 한국어로 출력.
"""

import os
import shutil

import hangul_font
import hangul_map
from common import BUILD_DIR, ED1SCN1_LBA, ED1SCN1_SIZE, extract, write_cue, write_user_data
from common import ORIG_BIN as SRC

ED_LBA, ED_SIZE = 257, 1021952

DST = os.path.join(BUILD_DIR, "Eiyuu Densetsu (PoC KR).bin")
DST_CUE = os.path.join(BUILD_DIR, "Eiyuu Densetsu (PoC KR).cue")

DIALOGUE_OFF = 0x1C7  # ED1SCN1.BIN 내 「あ、王子さま…」 시작
OLD_TEXT = "あ、王子さま いらっしゃい。"
NEW_TEXT = "어서오세요 왕자님 반가워요 "


def main():
    # 1) 폰트 블록 구성: 완성형 2,350자 → Galmuri11 22B 글리프
    print("Galmuri11 → 2,350 글리프 변환 중...")
    glyphs = hangul_font.convert_chars(hangul_map.SYLLABLES)
    block = b"".join(glyphs[ch] for ch in hangul_map.SYLLABLES)
    assert len(block) == 2350 * 22
    base_off = hangul_map.slot_ed_offset(0)
    print(f"ED.EXE +0x{base_off:X}부터 {len(block):,}바이트 기록 예정")

    # 2) 대사 인코딩 (동일 바이트 수 검증)
    old = OLD_TEXT.encode("cp932")
    new = hangul_map.encode_kr(NEW_TEXT)
    assert len(old) == len(new), f"길이 불일치: 원본 {len(old)}B vs 교체 {len(new)}B"

    print("사본 생성 중...")
    shutil.copyfile(SRC, DST)
    with open(DST, "r+b") as f:
        # ED.EXE 패치
        ed = bytearray(extract(ED_LBA, ED_SIZE))
        ed[base_off : base_off + len(block)] = block
        changed = write_user_data(f, ED_LBA, ed, label="PoC (ED.EXE)")
        print(f"ED.EXE: 섹터 {changed}개 수정 (폰트 블록)")

        # ED1SCN1.BIN 패치
        scn = bytearray(extract(ED1SCN1_LBA, ED1SCN1_SIZE))
        cur = bytes(scn[DIALOGUE_OFF : DIALOGUE_OFF + len(old)])
        assert cur == old, f"원본 불일치: {cur.hex()}"
        scn[DIALOGUE_OFF : DIALOGUE_OFF + len(new)] = new
        changed = write_user_data(f, ED1SCN1_LBA, scn, label="PoC (ED1SCN1)")
        print(f"ED1SCN1.BIN: 섹터 {changed}개 수정 (대사)")

    write_cue(DST_CUE, "Eiyuu Densetsu (PoC KR).bin")
    print(f"완료:\n  {DST}\n  {DST_CUE}")


if __name__ == "__main__":
    main()
