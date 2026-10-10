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
import typeset as T

BASE = 0x200000  # 스크립트 포인터 기준 (`voice_sub.BASE` · `mapfile.BASE`)
GOTO = b"\xfd\x00"
TRAMP = 6  # `FD 00` + 주소 4
COVER = 4  # 간판류: 트램펄린이 머리 뒤 글 앞 4 바이트까지 덮는다
CHOICE_START = b"\xff\x80"  # 선택창 열기 — `FF 80` 이 S


def _is_sign(data, text_off, head):
    """간판류 꼴인가 — `FE 00 xxxx · FF FF · FF 00` 머리."""
    return (
        head == "ff00"
        and data[text_off - 4 : text_off - 2] == b"\xff\xff"
        and data[text_off - 8 : text_off - 6] == b"\xfe\x00"
    )


_CARD_B_HEAD = bytes.fromhex("ff0019ff") + b"\x0d" * 6  # 장 카드(세로 줄바꿈형) 머리 — 글 앞 10B


def _card_kind(data, blocks, key):
    """장 카드 꼴인가 — `"A"` = 앞 대사에 `0E` 로 이어 붙은 카드(`10 00` 로 끝나는 세션의 끝 블록) ·
    `"B"` = `FF 00 19 FF` + 개행 6 으로 시작해 `00 09` 로 끝나는 단독 카드 · `"C"` = 같은 머리에 `00` 한 바이트로 끝나는 카드 · 아니면 `None`."""
    blk = blocks[int(key)]
    off = blk["off"]
    end = off + len(blk["body"])
    if blk["head"] == "420e" and data[end : end + 2] == b"\x10\x00":
        return "A"
    if data[off - 10 : off] == _CARD_B_HEAD:
        if data[end : end + 2] == b"\x00\x09":
            return "B"
        if data[end] == 0:
            return "C"
    return None


def _session_start(data, blocks, key):
    """`0E` 로 이어진 글 세션의 첫 블록 색인과 그 머리(`FF 00`) 주소 `s`."""
    j = int(key)
    while j > 0:
        e = blocks[j - 1]["off"] + len(blocks[j - 1]["body"])
        if data[e] == 0x0E and blocks[j]["off"] - e == 1:
            j -= 1
        else:
            break
    s = blocks[j]["off"] - 2
    assert data[s : s + 2] == b"\xff\x00", (
        f"세션 첫 블록 {j} 앞이 FF 00 이 아니다: {data[s : s + 2].hex()}"
    )
    return j, s


def covers(src, stem):
    """`{블록 색인: 칸 안 글 앞에서 트램펄린이 덮는 바이트 수}` — 되풀이 검사가 건너뛸 길이. `src` = 원본 맵.

    간판류는 그 블록 자신의 글 앞 4B, 장 카드 `A` 는 **세션 첫 블록**의 글 앞 4B 를 덮는다(카드 `B` 는 글을 안 덮는다)."""
    wides = R.wide(stem)
    if not wides:
        return {}
    blocks = M.blocks(src)
    out = {}
    for k in wides:
        blk = blocks[int(k)]
        if _is_sign(src, blk["off"], blk["head"]):
            out[k] = COVER
        elif _card_kind(src, blocks, k) == "A":
            out[str(_session_start(src, blocks, k)[0])] = COVER
    return out


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
        head_len = len(bytes.fromhex(blk["head"]))
        free_low = False
        if data[text_off - 4 : text_off - 2] == b"\xff\x81":
            # 선택지 항목 — 앞쪽 `FF 80 FF 81 <번호>` 6 바이트를 덮고 긴 글 뒤 `00 09` 다음 옵코드로 돌아온다
            s = data.rfind(CHOICE_START, max(0, text_off - head_len - 400), text_off - head_len)
            if s < 0:
                raise SystemExit(f"{stem}#{key}: 앞에 선택창 열기(FF 80)가 없다")
            assert data[s + 2 : s + 4] == b"\xff\x81", (
                f"{stem}#{key}: FF 80 바로 뒤가 첫 항목(FF 81)이 아니다"
            )
            end_ops = b"\x00\x09"
            ret_skip = 2
        elif blk["head"] == "ff00" and data[text_off - 6 : text_off - 4] == b"\xff\x02":
            # 대사 블록(나레이션 머리) — 앞 `FF 02 00 00` + 머리 `FF 00` = 6 바이트를 덮고 종결 옵코드 뒤로 돌아온다
            T_over = T.overflows(wides[key])
            if T_over:
                raise SystemExit(
                    f"{stem}#{key}: 긴 글이 창 계약(17×{T.WIN_ROWS})을 넘는다 — 페이지 {T_over}"
                )
            s = text_off - 6
            term = data[text_off + len(blk["body"])]
            end_ops = bytes([term])
            ret_skip = 1
        elif _is_sign(data, text_off, blk["head"]):
            # 간판류 대사 — `FE 00 xxxx`(4B) + `FF FF`(패딩) + 머리 `FF 00` + 글. 🔴 **들어오는 길이 둘이다** —
            # 조건분기가 `FF FF` 를, 이벤트 표가 `FF 00` 을 곧바로 가리킨다(MAP002 #45: 0x213a82 · 0x213a84). 그래서 트램펄린을
            # **머리(`FF 00`)부터** 놓는다 — `FF FF` 로 들어와도(무동작) 이어서 트램펄린을 밟는다. 덮는 6 바이트 = 머리 2 + **글 앞 4**.
            # 🔴 **글 모드는 `0E` 로 안 끝난다**(1차 시험: `0E` 뒤에 `FD 00` 을 놓았더니 글 모드가 `FD` 를 글자로 읽고 `00` 에서 끝나 빈
            #   창만 남았다). `0E` 는 키 대기 뒤 **같은 글 모드로 이어지는** 쪽이라(다음 화자 `02 xx` 가 바로 온다) 블록 하나만 옮길 수 없다 —
            #   **글 모드가 끝나는 `10 00` 까지** 한 세션을 통째로 꼬리에 옮기고 그 뒤 옵코드로 돌아온다. 이어지는 블록의 글은 재삽입이
            #   끝난 `data` 에서 그대로 복사한다.
            # 칸 안 글의 앞 4 바이트(한글 둘)는 주소가 되므로 되풀이 검사는 그만큼 건너뛴다(`covers` · `check_no_loss`).
            T_over = T.overflows(wides[key])
            if T_over:
                raise SystemExit(
                    f"{stem}#{key}: 긴 글이 창 계약(17×{T.WIN_ROWS})을 넘는다 — 페이지 {T_over}"
                )
            assert len(blk["body"]) >= COVER, (
                f"{stem}#{key}: 글이 {COVER}B 미만이라 트램펄린이 덮을 수 없다"
            )
            s = text_off - 2
            end = text_off + len(blk["body"])
            for j in range(int(key), len(blocks)):
                bj = blocks[j]
                end = bj["off"] + len(bj["body"])
                if data[end : end + 2] == b"\x10\x00":
                    end += 2
                    break
                if data[end] not in (0x0E, 0x0F):
                    raise SystemExit(
                        f"{stem}#{key}: 세션 끝(10 00)을 못 찾았다 — 블록 {j} 뒤 {data[end : end + 2].hex()}"
                    )
            else:
                raise SystemExit(f"{stem}#{key}: 세션 끝(10 00)을 못 찾았다")
            rest = bytes(data[text_off + len(blk["body"]) : end])  # 첫 블록 글 뒤 ~ `10 00`
            raw = H.encode_kr(wides[key], table)
            if (2 + len(raw) + len(rest)) % 2:
                raw += b" "  # 꼬리 끝의 `FD 00` 이 짝수 주소에 앉게 — 줄 끝 공백이라 안 보인다
            tail = len(out) + len(out) % 2
            assert s % 2 == 0
            body = bytes(data[s:text_off]) + raw + rest + GOTO + struct.pack(">I", BASE + end)
            out.extend(b"\x00" * (tail - len(out)))
            out.extend(body)
            out[s : s + TRAMP] = GOTO + struct.pack(">I", BASE + tail)
            continue
        elif _card_kind(data, blocks, key) == "A":
            # 장 카드 A — 앞 대사와 `0E` 로 이어진 같은 글 세션의 끝 블록(`10 00` 로 끝난다). 글 모드 한복판엔 트램펄린을 못 놓으니
            # (간판과 같은 이유) **세션 첫 블록의 머리(`FF 00`) 부터 `10 00` 까지** 통째로 꼬리에 옮기고 카드 글만 진짜 문안으로 바꾼다.
            # 덮는 6B = 머리 2 + 첫 블록 글 앞 4 — `covers` 가 되풀이 검사에 알린다. 카드는 화면 전폭(24칸)이라 창 계약(17칸)은 안 본다.
            j, s = _session_start(data, blocks, key)
            assert s % 2 == 0, f"{stem}#{key}: 세션 머리 {s:#x} 가 홀수 주소다"
            assert len(blocks[j]["body"]) >= COVER, (
                f"{stem}#{key}: 세션 첫 블록 {j} 글이 {COVER}B 미만"
            )
            text_end = text_off + len(blk["body"])
            end = text_end + 2
            raw = H.encode_kr(wides[key], table)
            if ((text_off - s) + len(raw)) % 2:
                raw += b" "
            tail = len(out) + len(out) % 2
            body = (
                bytes(data[s:text_off])
                + raw
                + bytes(data[text_end:end])
                + GOTO
                + struct.pack(">I", BASE + end)
            )
            out.extend(b"\x00" * (tail - len(out)))
            out.extend(body)
            out[s : s + TRAMP] = GOTO + struct.pack(">I", BASE + tail)
            continue
        elif _card_kind(data, blocks, key) in ("B", "C"):
            # 장 카드 B·C — `FF 00 19 FF` + 개행 6 + 글 + 종결(B `00 09` · C `00`). 머리(`FF 00`)부터 6B 를 트램펄린으로 덮고(글은 안 덮는다),
            # 꼬리에 머리 10B + 진짜 문안 + `00 09` 를 두고 종결 뒤 옵코드로 돌아온다.
            s = text_off - len(_CARD_B_HEAD)
            assert s % 2 == 0, f"{stem}#{key}: 카드 머리 {s:#x} 가 홀수 주소다"
            text_end = text_off + len(blk["body"])
            end_ops = b"\x00\x09" if data[text_end + 1] == 0x09 else b"\x00"
            assert (text_end + len(end_ops)) % 2 == 0, f"{stem}#{key}: 복귀 주소가 홀수다"
            raw = H.encode_kr(wides[key], table)
            if (len(_CARD_B_HEAD) + len(raw) + len(end_ops)) % 2:
                raw += b" "
            tail = len(out) + len(out) % 2
            body = (
                bytes(data[s:text_off])
                + raw
                + end_ops
                + GOTO
                + struct.pack(">I", BASE + text_end + len(end_ops))
            )
            out.extend(b"\x00" * (tail - len(out)))
            out.extend(body)
            out[s : s + TRAMP] = GOTO + struct.pack(">I", BASE + tail)
            continue
        else:
            raise SystemExit(
                f"{stem}#{key}: `_wide` 가 지원하는 꼴(선택지 항목 · FF 02 + FF 00 머리 대사 · FE 00 + FF FF + FF 00 대사)이 아니다"
            )
        last = data[s + TRAMP - 1]  # 지킬 바이트
        tail = len(out)
        if free_low:
            tail += tail % 2
        else:
            tail += (last - tail) % 256
        assert tail % 2 == 0, f"꼬리 주소 낮은 바이트 {last:#x} 가 홀수라 정렬이 안 맞는다"
        raw = H.encode_kr(wides[key], table)
        #   🔴 **옵코드는 짝수 주소 단위다** — 글 + 종결(`00 09` 2B 또는 `0E` 1B)의 길이가 짝수여야 다음 옵코드가 짝수에 앉는다.
        #     (선택지 2차 시험: 11B 글 + `00 09` 가 홀수에 앉아 PC 가 0 으로 떨어졌다. 대사는 원래 29B + `0E` 1B = 30B 짝수.)
        #     모자라면 줄 끝 반각 공백 하나를 붙인다 — 화면엔 안 보인다.
        if (len(raw) + len(end_ops)) % 2:
            raw += b" "
        assert s % 2 == 0 and (text_off - s) % 2 == 0, (
            f"{stem}#{key}: 덮는 자리/글 시작의 홀짝이 맞지 않는다"
        )
        ret = BASE + text_off + len(blk["body"]) + ret_skip  # 원래 종결 바로 뒤 옵코드
        assert (
            data[text_off + len(blk["body"]) : text_off + len(blk["body"]) + ret_skip] == end_ops
        ), f"{stem}#{key}: 글 뒤가 기대한 종결({end_ops.hex()})이 아니다"
        body = bytes(data[s:text_off]) + raw + end_ops + GOTO + struct.pack(">I", ret)
        out.extend(b"\x00" * (tail - len(out)))
        out.extend(body)
        out[s : s + TRAMP] = GOTO + struct.pack(">I", BASE + tail)
        assert free_low or out[s + TRAMP - 1] == last
    return bytes(out)
