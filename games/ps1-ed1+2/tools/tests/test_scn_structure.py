#!/usr/bin/env python3
"""`scn_structure` 구조 대조 회귀 — **원본 없이** 돈다(가짜 바이트로 짠 씬).

핵심은 「일부러 망가뜨린 사본으로 검사가 실제로 우는가」다. 검사가 늘 초록이면 아무도 안 본다(검사기 자신의 커버리지).
가짜 블록은 실제 문안이 아니라 글자 자리에 아무 2바이트 코드를 넣어 만들었다.
"""

import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import scn_structure as SS

G = b"\x88\x9f"  # 아무 2바이트 글자 코드(내용 무관)
MC, PS = b"%c", b"%s"
OVB = 0x80100000


def blk(*parts):
    raw = b"".join(parts)
    return raw + b"\x00" * (-len(raw) % 4 or 4)


# 원본 블록 셋: [이름창+본문 두 줄+종단 %c] · 본문만 · 이름 주입
OLD = {
    1: blk(MC, G, G, MC, b"\n", G, G, b"\n", G, MC),
    2: blk(G, G, b"\n", G, MC),
    3: blk(MC, PS, MC, b"\n", G, G, MC),
}


def lui(rt, imm):
    return 0x3C000000 | (rt << 16) | (imm & 0xFFFF)


def addiu(rt, rs, imm):
    return 0x24000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def fake_scene(layout_new, new_blocks, text_end, ptr_sites):
    """원본 쪽은 블록을 0x10 부터 4B 정렬로 나란히, 코드는 text_end 뒤. 빌드 쪽은 layout_new 자리에 new_blocks."""
    orig = bytearray(text_end + 0x40)
    off = 0x10
    old_pos = {}
    for eid in sorted(OLD):
        orig[off : off + len(OLD[eid])] = OLD[eid]
        old_pos[eid] = off
        off += len(OLD[eid])
    built = bytearray(len(orig))
    for eid, no in layout_new.items():
        built[no : no + len(new_blocks[eid])] = new_blocks[eid]
    # 코드: 사이트마다 lui/addiu 두 워드(블록 시작을 가리킴)
    sites = []
    for i, eid in enumerate(sorted(OLD)):
        c = text_end + 8 * i
        for buf, pos in ((orig, old_pos[eid]), (built, layout_new[eid])):
            a = OVB + pos
            buf[c : c + 4] = struct.pack(
                "<I", lui(4, (a >> 16) + (1 if (a & 0xFFFF) >= 0x8000 else 0))
            )
            buf[c + 4 : c + 8] = struct.pack("<I", addiu(4, 4, a & 0xFFFF))
        sites.append([c + 4, c, OVB + layout_new[eid], 0, "b", eid])
    rec = {
        "scene": "FAKE1",
        "text_end": text_end,
        "ov_base": OVB,
        "ext_base": len(orig),
        "blocks": [],
        "donors": {},
        "alias": {},
        "mid": {},
        "stubs": [],
        "struct": {},
        "special": [],
        "ptr_sites": sites,
    }
    for eid in sorted(OLD):
        nb = new_blocks[eid]
        h = hashlib.sha1(bytes(built[layout_new[eid] : layout_new[eid] + len(nb)])).hexdigest()[:10]
        rec["blocks"].append([eid, old_pos[eid], len(OLD[eid]), layout_new[eid], len(nb), 1, "", h])
    return rec, bytes(orig), bytes(built)


def _good():
    # 번역: 글자 수가 달라져 블록이 줄고(2번째 블록이 앞으로 당겨짐) 개행이 하나 더 생긴 꼴 — 구조는 같다
    nb = {
        1: blk(MC, G, MC, b"\n", G, G, G, b"\n", G, G, b"\n", G, MC),
        2: blk(G, b"\n", G, G, MC),
        3: blk(MC, PS, MC, b"\n", G, MC),
    }
    lay, pos = {}, 0x10
    for eid in sorted(nb):
        lay[eid] = pos
        pos += len(nb[eid])
    return fake_scene(lay, nb, 0x80, None)


def _run(rec, orig, built):
    f, cnt, _ = SS.check_scene(rec, orig, built, OLD)
    return f, cnt


def test_skeleton_ignores_glyphs_and_counts_controls():
    a = SS.skeleton(blk(MC, G, G, MC, b"\n", G, MC))
    b = SS.skeleton(blk(MC, G, MC, b"\n", b"\n", G, G, G, MC))
    assert a == ("C", "C", "N", "C", "Z")
    assert SS.hard(a) == SS.hard(b)  # 개행 수·글자 수가 달라도 같은 열


def test_clean_scene_passes():
    f, cnt = _run(*_good())
    assert f == [], f
    assert cnt["compared"] == 3 and cnt["ptr_ok"] == 3


def test_changed_control_byte_is_caught():
    rec, orig, built = _good()
    b = bytearray(built)
    no = rec["blocks"][0][3]
    i = bytes(b[no : no + 40]).find(MC)  # 첫 %c → 두 바이트를 FF FF 로(ss-ed3 사고 꼴)
    b[no + i : no + i + 2] = b"\xff\xff"
    f, _ = _run(rec, orig, bytes(b))
    assert any(x[0] in ("구조", "후속패치") for x in f), f


def test_missing_terminator_is_caught():
    rec, orig, built = _good()
    b = bytearray(built)
    no, nl = rec["blocks"][1][3], rec["blocks"][1][4]
    b[no + nl - 1] = 0x41  # 끝 00 하나를 지운다(종단 사라짐)
    for k in range(no + nl - 4, no + nl):
        b[k] = 0x41
    f, _ = _run(rec, orig, bytes(b))
    assert f, "종단이 없어졌는데 안 울었다"


def test_dirty_gap_is_caught():
    rec, orig, built = _good()
    b = bytearray(built)
    last = rec["blocks"][-1]
    gap = last[3] + last[4]
    assert gap < rec["text_end"]
    b[gap] = 0xFF  # 블록 사이 빈틈에 00 이 아닌 값
    f, _ = _run(rec, orig, bytes(b))
    assert any(x[0] == "빈틈" for x in f), f


def test_wrong_pointer_is_caught():
    rec, orig, built = _good()
    b = bytearray(built)
    ai = rec["ptr_sites"][1][0]
    w = struct.unpack_from("<I", b, ai)[0]
    struct.pack_into(
        "<I", b, ai, (w & 0xFFFF0000) | ((w + 0x100) & 0xFFFF)
    )  # 블록 시작에서 0x100 어긋난 주소(빈 곳)
    f, _ = _run(rec, orig, bytes(b))
    assert any(x[0] == "포인터" for x in f), f


def test_unlisted_structure_change_needs_allowlist():
    # %c 하나가 늘어난 번역 — 허용 표에 없으면 실패, 의도 표(why)와 분류가 맞으면 통과
    nb = {1: blk(MC, G, MC, b"\n", G, MC, G, MC), 2: OLD[2], 3: OLD[3]}
    lay, pos = {}, 0x10
    for eid in sorted(nb):
        lay[eid] = pos
        pos += len(nb[eid])
    rec, orig, built = fake_scene(lay, nb, 0x80, None)
    f, _ = _run(rec, orig, built)
    assert any(x[0] == "구조" for x in f), f
    rec["struct"]["1"] = {
        "kinds": SS.classify(OLD[1], nb[1]),
        "old": "",
        "new": "",
        "why": ["TEST"],
    }
    f, _ = _run(rec, orig, built)
    assert f == [], f


def test_ledger_rows_have_all_columns():
    rec, _o, _b = _good()
    rec.update(
        {
            "scene": "FAKE1",
            "orig_lba": 1,
            "orig_size": 100,
            "new_size": 100,
            "runs": [[0x10, 0x40, 3, 4, False]],
            "pin_ovr": [],
            "ptr_moved": {"1": 2},
            "args": [],
        }
    )
    rows = SS.ledger_rows({"FAKE1": rec}, {"FAKE1": {"lba": 1, "size": 100}}, {})
    assert rows and all(len(r) == 7 and all(r) for r in rows)
    assert SS.ledger_text(rows).count("\n") == len(rows) + 1


if __name__ == "__main__":
    ok = 0
    for k, v in sorted(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok ", k)
            ok += 1
    print(f"{ok} passed")


def test_pointer_target_byte_class_is_checked():
    """남이 포인터로 들어오는 자리(블록 속 개행·종단)를 우리가 글자로 바꾸면 운다(pce-ed1 10-22 꼴)."""
    rec, orig, built = _good()
    f, cnt = _run(rec, orig, built)
    assert f == [] and cnt["tgt"] == cnt["tgt_ok"] == 3
    # 첫 블록의 델타 8(원본에서 개행 자리)을 가리키는 사이트를 하나 더 — 빌드 쪽 그 자리는 글자다
    assert OLD[1][8] == 0x0A
    no = rec["blocks"][0][3]
    c, a = rec["ptr_sites"][0][1], OVB + no + 8
    b = bytearray(built)
    b[c : c + 4] = struct.pack("<I", lui(4, (a >> 16) + (1 if (a & 0xFFFF) >= 0x8000 else 0)))
    b[c + 4 : c + 8] = struct.pack("<I", addiu(4, 4, a & 0xFFFF))
    rec["ptr_sites"][0] = [c + 4, c, a, 8, "b", 1]
    f, _ = _run(rec, orig, bytes(b))
    assert any(x[0] == "목표바이트" for x in f), f


def test_leading_newline_drop_at_head_is_allowed():
    rec, orig, built = _good()
    o = bytearray(orig)
    o[rec["blocks"][0][1]] = 0x0A  # 원본 블록 머리가 개행 — 번역이 선두 개행을 떼는 건 의도
    f, cnt = _run(rec, bytes(o), built)
    assert not any(x[0] == "목표바이트" for x in f), f
    assert cnt.get("tgt_lead_nl") == 1
