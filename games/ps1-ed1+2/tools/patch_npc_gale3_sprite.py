#!/usr/bin/env python3
"""004 — 늑대의입의 게일 3세 조형: 일반 도적 → 게일 3세 (원판 자산 재배치, 새 그림 없음).

원판은 늑대의입(ED2SCN7)에서 게일 3세를 **일반 도적 조형(`a2=5`)**으로 그린다 — 그 씬의
캐릭터 팩에 게일 3세 그림이 없어서다. 그림 자체는 다른 팩에 있다.

RE 확정(2026-09-22, emucap 실측 — 경위는 devlog 「004 ⑤·⑥」):
- `DATA/ED2CHR.DAT` = TIM 47장(0x6800 간격), 한 장이 **씬 캐릭터 팩**(128×192 8bpp,
  8열×12행 16px 칸, **한 행 = 인물 하나 8프레임**, CLUT 256).
- 늑대의입은 **팩 #9** 를 VRAM (384,0) 에 올린다(ED2.EXE `0x800902f8(9)`). 1~6행에 인물
  여섯, **7~12행은 채움 색만**(index≠0 이지만 그림 없음).
- NPC 설치 `jal 0x8002E610` 의 `a2` 는 **`a2-1 = 팩의 행 번호**. 게일 3세 슬롯(슬롯0)은
  ED2SCN7 파일 `0x0156cc` 의 `addiu a2, zero, 5`(도적 = 4행).
- 46세 게일 3세의 8프레임 보행 세트가 **팩 #4(그로스토스성)의 10행**에 있다 — 바로 아래
  11행 7·8칸의 **묶인 게일**과 두건·띠·견갑까지 같고 밧줄만 없다.
  ⚠ 처음(09-22)엔 **팩 #25 2행**을 옮겼는데 그건 회상 이벤트의 **26세(소년 체형)** 게일이었다
  — 마스터 화면에서 「남자아이 조형」으로 발각(09-24). 11행만 보고 「걷는 46세는 원판에
  없다」고 판단해 바로 윗줄을 놓쳤다. 47팩 × 12행을 색 분포로 전수 대조해 찾았다.

⇒ 셋을 한다(전부 제자리, 크기 불변):
  ① 팩 #9 CLUT 에 #4 10행이 쓰는 색 중 #9 에 없는 것을 **빈 항목**에 넣는다.
  ② #4 10행 8칸(128×16 인덱스)을 색 리맵해 **#9 의 7행**(0-based 6)에 쓴다.
  ③ ED2SCN7 `0x0156cc` 의 즉값 `5 → 7`.

⚠ `a2` 는 **씬에 처음 들어갈 때만** 설치에 쓰인다 — 같은 맵 안에서 로드한 세이브로는
  변화가 안 보인다(배열이 memcpy 로 복원된다). 확인은 늑대의입 바깥에서 들어와서 한다.
⚠ 038(`patch_npc_zeni_slot`)과 같은 규율: 서명 유일성·사전조건·되읽기·멱등.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import BUILD_DIR, extract, write_user_data

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"

# --- DATA/ED2CHR.DAT (TIM 아카이브) ---------------------------------------------------
CHR_LBA = 4687
TIM_STRIDE = 0x6800
TIM_CLUT = 8 + 12  # 헤더(8) + CLUT 블록 헤더(12) → 256 항목 × 2B
TIM_PIX = 8 + (12 + 256 * 2) + 12  # + CLUT 본체 + 픽셀 블록 헤더 → 64hw × 192행
ROW_BYTES = 128  # 8bpp 128px = 128B / 행
CELL_ROWS = 16

SRC_PACK, SRC_ROW = 4, 9  # #4 의 10행(0-based 9) = 46세 게일 3세 보행 8프레임
DST_PACK, DST_ROW = 9, 6  # #9 의 7행(0-based 6) = 비어 있던 자리 → a2=7
NEW_A2 = DST_ROW + 1

# --- ED2SCN7 슬롯0 설치 호출 (`move a0,zero / move a1,zero / addiu a2,zero,5 / ...`) ---
SCN_LBA = 2122  # ED2SCN7(LBA 2080) 안 0x0156cc 가 든 섹터
SCN_SIG_OFF = 1732  # 섹터 유저데이터 안 서명 시작
SCN_SIG = bytes.fromhex(
    "212000002128000005000624200007240900132460001024"
)  # 24B, 이미지 전체에 1곳
SCN_A2_OFF = SCN_SIG_OFF + 8  # `05 00 06 24` 의 첫 바이트
OLD_A2 = 0x05


def _tim(pack):
    return pack * TIM_STRIDE


def _chr_span(file_off, length, path=None):
    """ED2CHR.DAT 안 바이트 구간을 (원본 또는 빌드 이미지에서) 읽는다."""
    lba0 = CHR_LBA + file_off // 2048
    lba1 = CHR_LBA + (file_off + length - 1) // 2048
    kw = {"path": path} if path else {}  # `extract()` 의 기본 path 는 원본(originals)
    buf = b"".join(bytes(extract(lba, 2048, **kw)) for lba in range(lba0, lba1 + 1))
    st = file_off - (lba0 - CHR_LBA) * 2048
    return lba0, st, bytearray(buf)


def plan():
    """원본(originals)만 읽어 결정적으로 계산 — (새 CLUT 256, 새 7행 픽셀 2048B, 새 항목 수)."""
    _, so, src = _chr_span(_tim(SRC_PACK), TIM_STRIDE)
    _, do, dst = _chr_span(_tim(DST_PACK), TIM_STRIDE)
    src_clut = [struct.unpack_from("<H", src, so + TIM_CLUT + i * 2)[0] for i in range(256)]
    dst_clut = [struct.unpack_from("<H", dst, do + TIM_CLUT + i * 2)[0] for i in range(256)]
    dst_px = dst[do + TIM_PIX : do + TIM_PIX + ROW_BYTES * 192]
    src_rows = src[
        so + TIM_PIX + SRC_ROW * CELL_ROWS * ROW_BYTES : so
        + TIM_PIX
        + (SRC_ROW + 1) * CELL_ROWS * ROW_BYTES
    ]
    used = set(dst_px)
    free = [i for i in range(1, 256) if i not in used]
    # 사전조건: 목적 행은 그림이 없어야 한다(채움 색 하나만).
    dst_row = dst_px[DST_ROW * CELL_ROWS * ROW_BYTES : (DST_ROW + 1) * CELL_ROWS * ROW_BYTES]
    assert len(set(dst_row)) == 1, (
        f"팩 #{DST_PACK} {DST_ROW + 1}행이 비어 있지 않다: {sorted(set(dst_row))[:8]}"
    )
    need = sorted({b for b in src_rows if b != 0})
    remap, newclut, alloc = {0: 0}, list(dst_clut), 0
    for i in need:
        col = src_clut[i]
        hit = [j for j in range(256) if newclut[j] == col and (j in used or j in remap.values())]
        if hit:
            remap[i] = hit[0]
            continue
        assert alloc < len(free), "팩 #9 CLUT 에 빈 항목이 모자란다"
        j = free[alloc]
        alloc += 1
        newclut[j] = col
        remap[i] = j
    new_row = bytes(remap[b] for b in src_rows)
    clut_bytes = b"".join(c.to_bytes(2, "little") for c in newclut)
    return clut_bytes, new_row, alloc


def _sig_count(path):
    with open(path, "rb") as f:
        return f.read().count(SCN_SIG)


def apply():
    clut_bytes, new_row, alloc = plan()
    clut_off = _tim(DST_PACK) + TIM_CLUT
    row_off = _tim(DST_PACK) + TIM_PIX + DST_ROW * CELL_ROWS * ROW_BYTES

    # 멱등: 이미 들어가 있으면 넘어간다(셋을 한 묶음으로 본다).
    l1, s1, cur_clut = _chr_span(clut_off, 512, path=IMG)
    l2, s2, cur_row = _chr_span(row_off, len(new_row), path=IMG)
    scn = bytearray(extract(SCN_LBA, 2048, path=IMG))
    done_clut = bytes(cur_clut[s1 : s1 + 512]) == clut_bytes
    done_row = bytes(cur_row[s2 : s2 + len(new_row)]) == new_row
    done_a2 = scn[SCN_A2_OFF] == NEW_A2
    if done_clut and done_row and done_a2:
        print("  004 게일 3세 조형 — 이미 적용됨")
        return 0
    assert not (done_clut or done_row or done_a2), "004 일부만 적용된 상태 — 손으로 확인할 것"

    # 사전조건 — SCN7 서명은 이미지 전체에 정확히 1곳, 즉값은 5.
    n = _sig_count(IMG)
    assert n == 1, f"004 SCN7 서명 개수 이상 — {n}곳(1곳이어야 함)"
    assert scn[SCN_SIG_OFF : SCN_SIG_OFF + len(SCN_SIG)] == SCN_SIG
    assert scn[SCN_A2_OFF] == OLD_A2

    total = 0
    with open(IMG, "r+b") as f:
        cur_clut[s1 : s1 + 512] = clut_bytes
        total += write_user_data(f, l1, bytes(cur_clut), label="004 게일 3세: 팩#9 CLUT")
        cur_row[s2 : s2 + len(new_row)] = new_row
        total += write_user_data(f, l2, bytes(cur_row), label="004 게일 3세: 팩#9 7행")
        scn[SCN_A2_OFF] = NEW_A2
        total += write_user_data(f, SCN_LBA, bytes(scn), label="004 게일 3세: SCN7 a2=7")

    # 되읽기
    _, s1, chk_clut = _chr_span(clut_off, 512, path=IMG)
    _, s2, chk_row = _chr_span(row_off, len(new_row), path=IMG)
    assert bytes(chk_clut[s1 : s1 + 512]) == clut_bytes, "004 CLUT 되읽기 불일치"
    assert bytes(chk_row[s2 : s2 + len(new_row)]) == new_row, "004 7행 되읽기 불일치"
    assert bytes(extract(SCN_LBA, 2048, path=IMG))[SCN_A2_OFF] == NEW_A2, "004 a2 되읽기 불일치"
    assert _sig_count(IMG) == 0, "004 옛 서명이 아직 남아 있다"
    print(
        f"  004 게일 3세 조형: 팩#{SRC_PACK} {SRC_ROW + 1}행 → 팩#{DST_PACK} {DST_ROW + 1}행"
        f" (CLUT 신규 {alloc}) · SCN7 a2 {OLD_A2}→{NEW_A2} @lba{SCN_LBA}+0x{SCN_A2_OFF:X} (되읽기 확인)"
    )
    return total


if __name__ == "__main__":
    apply()
