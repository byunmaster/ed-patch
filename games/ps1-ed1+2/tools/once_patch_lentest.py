"""
길이 변경 실험: 엔진이 대사 블록을 순차 파싱하는지, 오프셋 테이블을 쓰는지 판별.

원본에서 ED1SCN1.BIN 첫 대사의 「ゃ」(2바이트)를 삭제해 이후 텍스트를 전부
2바이트 앞으로 당기고, 마지막 대사 뒤 00 패딩에 2바이트를 보충한다.
 - 순차 파싱      → 첫 대사만 「ちんと」, 이후 NPC 대사 전부 정상
 - 오프셋 테이블  → 두 번째 대사부터 깨짐 (2바이트 어긋난 지점부터 파싱)
"""

import os
import re
import shutil

from common import BUILD_DIR, SECTOR, USER_OFF, USER_SIZE, write_cue, write_user_data
from common import ED1SCN1_LBA as LBA
from common import ED1SCN1_SIZE as FSIZE
from common import ORIG_BIN as SRC

DST = os.path.join(BUILD_DIR, "Eiyuu Densetsu (Len Test).bin")
DST_CUE = os.path.join(BUILD_DIR, "Eiyuu Densetsu (Len Test).cue")

DEL_AT = 0x21  # 「ちゃんと」의 ゃ(82 E1) 위치 (파일 내 오프셋)
SJIS_RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){4,}")


def main():
    with open(SRC, "rb") as f:
        nsec = (FSIZE + USER_SIZE - 1) // USER_SIZE
        data = bytearray()
        for i in range(nsec):
            f.seek((LBA + i) * SECTOR + USER_OFF)
            data += f.read(USER_SIZE)
        data = bytearray(data[:FSIZE])

    # 1) 삭제 위치 검증: 王子、ちゃんと
    assert data[0x19:0x27] == "王子、ちゃんと".encode("cp932"), "원본 불일치"
    assert data[DEL_AT : DEL_AT + 2] == "ゃ".encode("cp932")

    # 2) 텍스트 영역 끝 찾기: 마지막 일본어 문자열 뒤 00 런에 2바이트 보충
    last_end = None
    for m in SJIS_RUN.finditer(bytes(data)):
        try:
            m.group().decode("cp932")
        except UnicodeDecodeError:
            continue
        last_end = m.end()
    zero_run = re.compile(rb"\x00{4,}").search(bytes(data), last_end)
    assert zero_run, "텍스트 뒤 00 패딩을 못 찾음"
    ins_at = zero_run.start()
    print(f"마지막 문자열 끝: 0x{last_end:X}, 00 보충 위치: 0x{ins_at:X}")
    tail_sjis = bytes(data[last_end - 20 : last_end]).decode("cp932", "replace")
    print(f"마지막 문자열 꼬리: …{tail_sjis}")

    # 3) 2바이트 삭제 + 2바이트 보충 (파일 크기 유지, ins_at 이후는 원본 그대로)
    new = data[:DEL_AT] + data[DEL_AT + 2 : ins_at] + b"\x00\x00" + data[ins_at:]
    assert len(new) == FSIZE

    # 4) 사본 만들고 섹터 재기록 + EDC 재계산
    print("사본 생성 중...")
    shutil.copyfile(SRC, DST)
    with open(DST, "r+b") as f:
        changed = write_user_data(f, LBA, new, nsec, label="길이 실험")
    print(f"수정 섹터: {changed}/{nsec}")

    write_cue(DST_CUE, "Eiyuu Densetsu (Len Test).bin")
    print(f"완료:\n  {DST}\n  {DST_CUE}")


if __name__ == "__main__":
    main()
