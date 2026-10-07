"""선택지 항목이 **칸(원문 바이트 예산)보다 길 때** — 맵 꼬리로 옮겨 그린다.

    `script/MAPnnn.json` 의 `_wide: {"블록": "대역"}` — 값(정본 문안)은 진짜 문안이고
    `reinsert.load_script` 가 칸 안에는 대역을 쓴다. 여기서는 **진짜 문안을 꼬리에 붙이고**
    엔진이 그걸 읽게 트램펄린(`FD 00` GOTO)을 건다. 음성 자막(`voice_sub.py`)과 같은 길이다.

선택창 구조(MAP041 #33~35 실측 · 핸들러 `FF 81` = `0x060155CC`):

    ... 00 | 09 | FF 80 | FF 81 00 00 <글1> 00 | 09 FF 81 00 01 <글2> 00 | 09 FF 81 00 02 <글3> 00 | 09 FF 00 ...
               S

`FF 81 <번호 2B>` 뒤 NUL 까지가 항목 글이고 핸들러는 **그 포인터만 표에 등록**한다(해석 안 함).
선택창 그리기가 이 표를 읽으므로 글이 꼬리에 있어도 된다 — 단 `01 xx`(인라인 아이템 코드)는
선택창이 안 그린다(시험 2026-10-07: 칸이 빈다) 그래서 글자로 쓴다.

방법: `FF 80`(S)부터 **6 바이트만**(`FF 80 FF 81 00 NN` — 앞 `09` 는 건드리지 않는다: 그 바이트가 옵코드인지 본문 꼬리 처리의 일부인지 확정 못 했다. 첫 판이 `09` 부터 덮어 선택창이 안 떴다) `FD 00 <꼬리 주소>` 로 덮고, 꼬리에는 S 부터 **긴 글 앞까지**
(밀어낸 옵코드 + 앞 항목들)를 그대로 복사한 뒤 진짜 글 + NUL + `FD 00 <긴 글 뒤 원래 자리>` 를 둔다.
⚠ 덮는 6 바이트의 **마지막 바이트는 원래 값을 지킨다** — 거기가 첫 항목 블록의 머리(`00 00`)라
`mapfile` 이 블록을 못 알아보면 되풀이 검사가 깨진다. 꼬리 주소의 낮은 바이트를 그 값에 맞춘다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hangul_map as H
import mapfile as M
import reinsert as R

BASE = 0x200000  # 스크립트 포인터 기준 (`voice_sub.BASE` · `mapfile.BASE`)
GOTO = b"\xfd\x00"
TRAMP = 6  # `FD 00` + 주소 4
CHOICE_START = b"\xff\x80"  # 선택창 열기 — `FF 80` 이 S


def has(stem):
    return bool(R.wide(stem))


def patch(data, stem, table, orig):
    """칸에 대역이 든 맵 바이트 → 꼬리가 붙고 트램펄린이 걸린 맵 바이트.

    `orig` 는 재삽입 **전** 원본이다 — 블록 경계는 거기서 읽는다(한글이 든 바이트는 `mapfile` 이 같게 못 가른다).
    """
    wides = R.wide(stem)
    if not wides:
        return data
    blocks = M.blocks(orig)
    out = bytearray(data)
    for key in sorted(wides, key=int):
        blk = blocks[int(key)]
        text_off = blk["off"]
        # 이 항목의 `FF 81 <번호>` — 글 바로 앞 4 바이트
        assert data[text_off - 4 : text_off - 2] == b"\xff\x81", f"{stem}#{key}: 선택 항목이 아니다"
        head = text_off - len(bytes.fromhex(blk["head"]))
        s = data.rfind(CHOICE_START, max(0, head - 400), head)
        if s < 0:
            raise SystemExit(f"{stem}#{key}: 앞에 선택창 열기(FF 80)가 없다")
        assert data[s + 2 : s + 4] == b"\xff\x81", f"{stem}#{key}: FF 80 바로 뒤가 첫 항목(FF 81)이 아니다"
        last = data[s + TRAMP - 1]  # 지킬 바이트(= 첫 항목 머리의 앞 바이트)
        # 꼬리 위치 — 낮은 바이트가 `last` 인 가장 가까운 짝수 주소
        tail = len(out)
        tail += (last - tail) % 256
        assert tail % 2 == 0, f"꼬리 주소 낮은 바이트 {last:#x} 가 홀수라 정렬이 안 맞는다"
        raw = H.encode_kr(wides[key], table)
        #   🔴 **옵코드는 짝수 주소 단위다** — 글이 홀수 바이트면 끝의 `00 09`(NUL + 옵코드 09)가 홀수 주소에 앉아
        #     스크립트 읽기가 한 바이트 어긋난다(2차 시험: 11B 「진홍의 불꽃」에서 화면이 멈추고 PC 가 0 으로 떨어졌다).
        #     뒤에 반각 공백 하나를 붙여 짝수로 맞춘다 — 줄 끝 공백이라 화면엔 안 보인다.
        #     같은 이유로 꼬리 시작과 덮는 자리(S)의 홀짝이 같아야 한다(1차 시험: `09` 부터 덮어 꼬리가 반 바이트 어긋나 저장 목록이 떴다).
        if len(raw) % 2:
            raw += b" "
        assert s % 2 == 0 and (text_off - s) % 2 == 0, f"{stem}#{key}: 덮는 자리/글 시작의 홀짝이 맞지 않는다"
        assert data[text_off + len(blk["body"]) : text_off + len(blk["body"]) + 2] == b"\x00\x09", f"{stem}#{key}: 글 뒤가 `00 09` 가 아니다"
        ret = BASE + text_off + len(blk["body"]) + 2  # 긴 글 뒤 `00 09` 다음 옵코드
        body = bytes(data[s:text_off]) + raw + b"\x00\x09" + GOTO + struct.pack(">I", ret)
        out.extend(b"\x00" * (tail - len(out)))
        out.extend(body)
        out[s : s + TRAMP] = GOTO + struct.pack(">I", BASE + tail)
        assert out[s + TRAMP - 1] == last
    return bytes(out)
