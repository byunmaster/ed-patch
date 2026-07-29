#!/usr/bin/env python3
"""NE DLL에 export를 하나 이식한다 (본보기 DLL에서 thunk + relocation을 그대로 뜬다).

만트라판 `F_501`/`F_502`(스엘 유람선이 쓰는 필드 씬)에는 `ALGO_00`이 빠져 있다.
엔진의 `FIELD_MAIN`(ED2MAIN #354)이 필드 씬 DLL에서 인덱스 2 = `ALGO_00`을
`GetProcAddress`로 찾으므로, 없으면 `Scenario_GetFuncPtr / Fails in getting
func ptr`로 죽는다. F 계열 12개 중 이 둘만 없다.

하는 일:
  1. 본보기 DLL에서 해당 export의 thunk 바이트와 그 안의 relocation 레코드를 뜬다
  2. 대상 DLL의 그 세그먼트 **끝에** thunk를 덧붙이고(길이 +N) relocation을 추가
  3. entry table에 새 ordinal 추가, resident-name table에 이름 추가
  4. 이동한 테이블에 맞춰 NE 헤더 오프셋을 갱신

세그먼트 뒤 패딩(다음 세그먼트 sector 경계까지)에서 자리를 빌리므로 **파일 크기와
모든 세그먼트의 sector 오프셋이 그대로**다. 여유가 모자라면 중단한다.

usage:
  ne_add_export.py <target.dll> <NAME> --model <model.dll> --out <out.dll>
  ne_add_export.py <target.dll> <NAME> --model <model.dll> --dry-run
"""

import struct
import sys

from ne_entries import entries
from ne_info import find_ne, parse_ne


def hdr(b, ne):
    """NE 헤더에서 우리가 손대는 필드만."""
    f = {}
    (f["cbenttab"],) = struct.unpack_from("<H", b, ne + 0x06)
    (f["enttab"],) = struct.unpack_from("<H", b, ne + 0x04)
    (f["segtab"],) = struct.unpack_from("<H", b, ne + 0x22)
    (f["rsrctab"],) = struct.unpack_from("<H", b, ne + 0x24)
    (f["restab"],) = struct.unpack_from("<H", b, ne + 0x26)
    (f["modtab"],) = struct.unpack_from("<H", b, ne + 0x28)
    (f["imptab"],) = struct.unpack_from("<H", b, ne + 0x2A)
    (f["nonres"],) = struct.unpack_from("<I", b, ne + 0x2C)
    return f


def relocs_raw(b, seg):
    """세그먼트 데이터 뒤의 relocation 테이블을 (count, [8바이트 레코드]) 로."""
    if not (seg["flags"] & 0x0100):
        return 0, []
    p = seg["file_off"] + seg["length"]
    (n,) = struct.unpack_from("<H", b, p)
    return n, [b[p + 2 + i * 8 : p + 2 + (i + 1) * 8] for i in range(n)]


def name_entries(b, off):
    """[len][name][ordinal] 목록과 테이블 총 길이(종료 0 포함)."""
    out, p = [], off
    while b[p]:
        n = b[p]
        out.append(
            (b[p + 1 : p + 1 + n].decode("latin1"), struct.unpack_from("<H", b, p + 1 + n)[0])
        )
        p += 1 + n + 2
    return out, p + 1 - off


def build_names(items):
    out = bytearray()
    for name, ordv in items:
        out += bytes([len(name)]) + name.encode("latin1") + struct.pack("<H", ordv)
    return bytes(out + b"\x00")


def take_model(model_path, name):
    """본보기에서 (thunk 바이트, [(레코드 내 상대오프셋, 레코드)]) 를 뜬다."""
    b = open(model_path, "rb").read()
    ne = find_ne(b)
    h = parse_ne(b, ne)
    ordv = dict(h["resident_names"] + h["nonresident_names"]).get(name)
    if ordv is None:
        sys.exit(f"본보기에 {name} 이 없다: {model_path}")
    seg_i, off = entries(b, h)[ordv]
    seg = h["segments"][seg_i - 1]

    # thunk 길이 = 같은 세그먼트에서 바로 다음 export 시작까지 (없으면 retf 까지)
    others = sorted(f for o, (s, f) in entries(b, h).items() if s == seg_i and f > off)
    end = others[0] if others else off + 6
    body = b[seg["file_off"] + off : seg["file_off"] + end]

    _, recs = relocs_raw(b, seg)
    mine = []
    for r in recs:
        roff = struct.unpack_from("<H", r, 2)[0]
        if off <= roff < end:
            mine.append((roff - off, r))
    return seg_i, body, mine


def main():
    if len(sys.argv) < 3 or "--model" not in sys.argv:
        sys.exit(__doc__)
    target = sys.argv[1]
    name = sys.argv[2]
    model = sys.argv[sys.argv.index("--model") + 1]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    if not out and "--dry-run" not in sys.argv:
        sys.exit("--out 또는 --dry-run 이 필요하다")

    seg_i, body, mrecs = take_model(model, name)
    print(f"# 본보기 {model}: {name} = seg{seg_i}:+{len(body)}B  {body.hex(' ')}")
    for d, r in mrecs:
        print(f"#   reloc +{d}: {r.hex(' ')}")

    b = bytearray(open(target, "rb").read())
    ne = find_ne(b)
    h = parse_ne(bytes(b), ne)
    f = hdr(b, ne)
    if name in dict(h["resident_names"] + h["nonresident_names"]):
        sys.exit(f"{target} 에 이미 {name} 이 있다")

    seg = h["segments"][seg_i - 1]
    nxt = min(
        (s["file_off"] for s in h["segments"] if s["file_off"] > seg["file_off"]),
        default=len(b),
    )
    cnt, recs = relocs_raw(bytes(b), seg)
    rel_end = seg["file_off"] + seg["length"] + 2 + cnt * 8
    slack = nxt - rel_end
    need = len(body) + 8 * len(mrecs)
    print(f"# 대상 seg{seg_i}: len={seg['length']:#x} relocs={cnt} 슬랙={slack}B 필요={need}B")
    if need > slack:
        sys.exit(f"세그먼트 뒤 여유 부족: {slack} < {need}")

    new_off = seg["length"]  # 새 export 는 세그먼트 끝에 붙는다
    ordv = max(o for _, o in h["resident_names"] + h["nonresident_names"]) + 1
    print(f"# 이식: seg{seg_i}:{new_off:#06x}  ordinal #{ordv}")

    # --- 세그먼트 데이터 + relocation 재구성 ---
    for d, r in mrecs:
        r = bytearray(r)
        struct.pack_into("<H", r, 2, new_off + d)
        recs.append(bytes(r))
    seg_blob = (
        bytes(b[seg["file_off"] : seg["file_off"] + seg["length"]])
        + body
        + struct.pack("<H", len(recs))
        + b"".join(recs)
    )
    b[seg["file_off"] : nxt] = seg_blob + b"\x00" * (nxt - seg["file_off"] - len(seg_blob))
    # length 뿐 아니라 minalloc 도 늘려야 한다. DPMI 로더는 minalloc 으로 셀렉터를
    # 만든 뒤 파일에서 length 만큼 읽어 넣으므로, minalloc 이 작으면 마지막 바이트를
    # 쓰다가 "Segment limit violation" 으로 죽는다. 이 게임의 DLL은 전부 두 값이 같다.
    ent_off = ne + f["segtab"] + (seg_i - 1) * 8
    new_len = seg["length"] + len(body)
    struct.pack_into("<H", b, ent_off + 2, new_len)
    (minalloc,) = struct.unpack_from("<H", b, ent_off + 6)
    if minalloc and minalloc < new_len:
        struct.pack_into("<H", b, ent_off + 6, new_len)
        print(f"# minalloc {minalloc:#06x} -> {new_len:#06x}")

    # --- entry table: 마지막 fixed 번들에 붙이거나 새 번들 ---
    ep, end = ne + f["enttab"], ne + f["enttab"] + f["cbenttab"]
    last_start, last_ind, last_cnt = None, None, None
    p = ep
    while p < end and b[p]:
        c, ind = b[p], b[p + 1]
        last_start, last_ind, last_cnt = p, ind, c
        p += 2 + c * (6 if ind == 0xFF else 3 if ind else 0)
    ent = bytearray(b[ep:end])
    if last_ind == seg_i:  # 같은 세그먼트 fixed 번들 → count 증가 후 뒤에 삽입
        rel = last_start - ep
        ent[rel] = last_cnt + 1
        ins = rel + 2 + last_cnt * 3
        ent[ins:ins] = bytes([0x03]) + struct.pack("<H", new_off)
    else:  # 새 fixed 번들을 종료자 앞에 추가
        ent[-2:-2] = bytes([1, seg_i, 0x03]) + struct.pack("<H", new_off)
    d_ent = len(ent) - f["cbenttab"]

    # --- resident-name table ---
    items, res_len = name_entries(b, ne + f["restab"])
    res = build_names(items + [(name, ordv)])
    d_res = len(res) - res_len

    # --- 테이블 구간 통째로 재조립 (restab → nonres 끝) ---
    mod_off, imp_off = ne + f["modtab"], ne + f["imptab"]
    nr_items, nr_len = name_entries(b, f["nonres"])
    mid = bytes(b[mod_off:imp_off]) + bytes(b[imp_off : ne + f["enttab"]])
    blob = res + mid + bytes(ent) + bytes(b[f["nonres"] : f["nonres"] + nr_len])
    seg1 = min(s["file_off"] for s in h["segments"])
    if ne + f["restab"] + len(blob) > seg1:
        sys.exit("헤더 테이블 영역 여유 부족")
    b[ne + f["restab"] : seg1] = blob + b"\x00" * (seg1 - ne - f["restab"] - len(blob))

    # --- 헤더 오프셋 갱신 ---
    struct.pack_into("<H", b, ne + 0x06, f["cbenttab"] + d_ent)
    for fld, base in ((0x28, f["modtab"]), (0x2A, f["imptab"]), (0x04, f["enttab"])):
        struct.pack_into("<H", b, ne + fld, base + d_res)
    struct.pack_into("<I", b, ne + 0x2C, f["nonres"] + d_res + d_ent)
    print(f"# 이름테이블 +{d_res}B, entry table +{d_ent}B (파일 크기 불변)")

    if out:
        open(out, "wb").write(bytes(b))
        print(f"# 기록: {out}")
    else:
        print("# --dry-run: 기록 안 함")


if __name__ == "__main__":
    main()
