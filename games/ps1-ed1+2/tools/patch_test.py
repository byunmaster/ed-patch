"""
첫 사이클 검증용 테스트 패치.
원본 .bin의 사본을 만들고, ED1 시작 마을 NPC 대사 5곳의 앞 두 글자를
「ぱぴ」로 교체한다 (같은 바이트 수, 폰트에 확실히 존재하는 히라가나).
수정된 섹터는 Mode2 Form1 EDC를 재계산한다 (ECC는 에뮬레이터가 검사하지 않아 생략).
"""

import os
import shutil

from common import BUILD_DIR, SECTOR, USER_OFF, USER_SIZE, edc_compute, write_cue
from common import ORIG_BIN as SRC

DST = os.path.join(BUILD_DIR, "Eiyuu Densetsu (Test Patch).bin")
DST_CUE = os.path.join(BUILD_DIR, "Eiyuu Densetsu (Test Patch).cue")

# (raw 오프셋, 원본 문자열 앞부분, 교체 문자열) — 바이트 수 동일해야 함
PATCHES = [
    (0x2A7501, "王子、ちゃんと", "王子、ぱぴんと"),
    (0x2A755D, "お出かけですか、王子", "ぱぴかけですか、王子"),
    (0x2A759D, "あら、王子さま。", "ぱぴ、王子さま。"),
    (0x2A761D, "お出かけですか、王子", "ぱぴかけですか、王子"),
    (0x2A76AF, "あ、王子さま", "ぱ、王子さま"),
]


def main():
    print("사본 생성 중...")
    shutil.copyfile(SRC, DST)

    with open(DST, "r+b") as f:
        for off, old_s, new_s in PATCHES:
            old = old_s.encode("cp932")
            new = new_s.encode("cp932")
            assert len(old) == len(new), f"길이 불일치: {old_s} → {new_s}"

            sec_idx = off // SECTOR
            sec_base = sec_idx * SECTOR
            pos_in_sec = off - sec_base
            # 수정 범위가 유저 데이터(24~2071) 안인지 확인
            assert (
                USER_OFF <= pos_in_sec and pos_in_sec + len(old) <= USER_OFF + 8 + USER_SIZE - 8
            ), f"0x{off:X}: 섹터 경계 걸침 — 분할 패치 필요"

            f.seek(off)
            cur = f.read(len(old))
            assert cur == old, f"0x{off:X}: 원본 불일치 (기대 {old.hex()} 실제 {cur.hex()})"
            f.seek(off)
            f.write(new)

            # Mode2 Form1 EDC 재계산: subheader+data(16~2071) → 2072에 LE 저장
            f.seek(sec_base)
            sec = bytearray(f.read(SECTOR))
            submode = sec[18]
            assert not (submode & 0x20), f"섹터 {sec_idx}는 Form2 — 대상 아님"
            edc = edc_compute(bytes(sec[16:2072]))
            sec[2072:2076] = edc.to_bytes(4, "little")
            f.seek(sec_base)
            f.write(sec)
            print(f"0x{off:X} (섹터 {sec_idx}): {old_s} → {new_s}  [EDC {edc:08X}]")

    write_cue(DST_CUE, "Eiyuu Densetsu (Test Patch).bin")
    print(f"\n완료:\n  {DST}\n  {DST_CUE}")


if __name__ == "__main__":
    main()
