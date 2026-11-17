"""원판 텍스트 사본 잔존 게이트 — 제품 이미지 **전체**(섹터 전량)에서 「우리가 번역해 바꾼 원판 덩어리」의 원판 바이트를 찾는다.

    python3 tools/check_stray_copies.py [--image 경로]

왜: 다른 게임(PCE I)에서 원판 디스크에 대사 블록의 **사본**이 우리가 고친 자리 밖(맵별 레코드 안)에 따로 있었고, 정상 진행이 그 사본을 읽어
2장 장면 전체가 원문으로 나왔다. 빌드·게이트는 고친 자리만 분모로 보므로 못 잡는다 → 분모를 **이미지 전체**로 넓힌다.

방법: ① 원판 대본 조각(번역한 것, 코드 5개↑)·실행파일 UI 문자열(번역한 것)·바꿔 끼운 그림 멤버의 **원판 바이트**를 바늘로 삼는다.
② 원판 이미지에서 바늘을 센다(양성 대조 — 못 찾으면 검색기가 죽은 것). ③ 제품 이미지 전체(사용자 데이터 2048B 이어 붙임)에서 같은 바늘을 센다.
제품에 남은 원판 바이트가 곧 「고치지 않은 사본」이다 — 단 **번역이 없는 조각과 바이트가 같은 바늘**(원문이 그대로 나가기로 한 자리)은 뺀다.
⚠ 우리 번역 멤버가 안 바뀌고 남은 것(탈락)도 여기 걸린다 — 그건 원래 결함이다.
기준선 없음 — 하나라도 남으면 실패(사본 0 이 정상).
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import struct

import build
import common
import reinsert
import script_kr
import textenc
import uitext

MIN_SEG_CODES = 5  # 조각 바늘 최소 길이(코드) — 이보다 짧은 말(「네」 따위)은 우연히 겹친다
MIN_UI_BYTES = 8
# 아이템 메뉴 구조체의 옛 자리(실행파일 0xA38~): 통째로 둘째 동굴로 옮기고 사용처를 패치했다(`uitext.ITEM_TBL`) — 옛 자리를 가리키던 명령(`lui 0x8001 + 0x238`)이
# 제품엔 없다(원판엔 0x800256c4 에 있다). 안 읽히는 옛 문안이라 면제(사용처 정적 검산 · devlog 「아이템 구조체 사용처 패치」).
ITEM_OLD = (0xA38, 0xAA0)


def item_old_refs(exe):
    """실행파일에서 옛 구조체 주소(0x80010238~0x8001029F)를 `lui 0x8001` + 8명령 안의 12비트 상수로 가리키는 명령 수 — 제품은 0 이어야 한다."""
    w = struct.unpack_from(f"<{len(exe) // 4}I", exe)
    n = 0
    for i, x in enumerate(w):
        if x >> 26 == 0x0F and (x & 0xFFFF) == 0x8001:
            rt = (x >> 16) & 31
            for y in w[i + 1 : i + 8]:
                if (
                    (y >> 21) & 31 == rt
                    and (y >> 26) in (9, 0xD, 0x20, 0x21, 0x23, 0x24, 0x25, 0x28, 0x29, 0x2B)
                    and 0x238 <= (y & 0xFFFF) < 0x2A0
                ):
                    n += 1
    return n


def user_stream(path):
    """이미지 → 사용자 데이터(2048B) 이어 붙인 uint8 배열(섹터마다 24B 머리·꼬리 제거)."""
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    n = len(raw) // common.SECTOR
    sec = raw[: n * common.SECTOR].reshape(n, common.SECTOR)
    return np.ascontiguousarray(
        sec[:, common.MODE2_FORM1_USER_OFF : common.MODE2_FORM1_USER_OFF + common.USER_SIZE]
    ).reshape(-1)


def _has_jp(codes):
    import check_jp_left

    cm = textenc.charmap()
    return any(check_jp_left.is_jp(ch) for c in codes for ch in cm.get(c, ""))


def _same_codes(kr, codes):
    try:
        return reinsert.codes_for(kr) == list(codes)
    except (KeyError, ValueError):
        return False


def needles():
    """[(라벨, 바이트)] — 번역한(원판과 값이 바뀐) 것의 원판 바이트. 그리고 번역이 없는 조각의 바이트 집합(면제)."""
    members = build.identity_gate({})
    out, keep = [], set()
    for (arc, mem), rows in script_kr.load_all().items():
        segs = reinsert.member_segments(members[(arc, mem)])
        for si, codes in enumerate(segs):
            b = struct.pack(f"<{len(codes)}H", *codes)
            r = rows.get(si)
            if (
                r is None or not r.get("kr") or _same_codes(r["kr"], codes) or not _has_jp(codes)
            ):  # 번역 없음 · 번역 코드가 원판과 같음 · 가나·한자 없는 조각(숫자 암호 — 퍼즐 쪽지 표가 실행파일에 같은 숫자 칸을 둔다, 마스터 11-05 「퍼즐은 그대로」) — 원판 바이트가 정상
                keep.add(b)  # 번역 없음 — 원문 그대로 나가는 자리
                continue
            if len(codes) >= MIN_SEG_CODES:
                out.append((f"{os.path.basename(script_kr.path_of(arc, mem))}#{si}", b))
    exe = bytes(common.read_file(common.EXE_PATH))
    done = {
        k for k, v in uitext.load().items() if v.get("kr")
    }  # 번역한 UI 문자열만(안 옮긴 건 원문이 정상)
    for off, s in uitext.sites(exe).items():
        b = struct.pack(f"<{len(s['codes'])}H", *s["codes"])
        if off in done and len(b) >= MIN_UI_BYTES and not (ITEM_OLD[0] <= off < ITEM_OLD[1]):
            out.append((f"EXE@{off:#x}", b))
    return out, keep


def find(data, ndl):
    """데이터에서 바늘의 모든 출현 위치 {바이트: [오프셋]} — 앞 8B 를 u64 로 해시 표에 걸러 전체 비교로 확인(멤버 시작 바이트가 홀수일 수 있어 8정렬 전부)."""
    by8 = {}
    for b in ndl:
        by8.setdefault(b[:8], []).append(b)
    keys = np.array(sorted({int.from_bytes(k, "little") for k in by8}), dtype=np.uint64)
    mul = np.uint64(0x9E3779B97F4A7C15)
    sh38 = np.uint64(38)
    tab = np.zeros(1 << 26, dtype=bool)
    tab[((keys * mul) >> sh38).astype(np.int64)] = True
    kset = {int(k) for k in keys}
    hits = {}
    n = len(data)
    for sh in range(8):
        m = (n - sh) // 8
        view = data[sh : sh + m * 8].view("<u8")
        for lo in range(0, m, 1 << 24):
            chunk = view[lo : lo + (1 << 24)]
            cand = np.nonzero(tab[((chunk * mul) >> sh38).astype(np.int64)])[0]
            for pos in cand:
                if int(chunk[pos]) not in kset:
                    continue
                at = sh + (lo + int(pos)) * 8
                for b in by8[int(chunk[pos]).to_bytes(8, "little")]:
                    if bytes(data[at : at + len(b)]) == b:
                        hits.setdefault(b, []).append(at)
    return hits


def live_file(files, at):
    """제품 디렉터리가 가리키는 파일 안이면 경로, 아니면 None(재배치로 비워진 옛 자리 — 아무도 안 읽는다)."""
    lba = at // common.USER_SIZE
    for p, (l, sz) in files.items():
        if l <= lba < l + (sz + common.USER_SIZE - 1) // common.USER_SIZE:
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image")
    a = ap.parse_args()
    image = a.image
    if image is None:
        import check_jp_left

        image, _why = check_jp_left.product_image()
        if image is None:
            print(f"  ✗ 제품 이미지를 못 잡았다 — {_why}")
            return 1
    nd, keep = needles()
    byb = {}
    for lab, b in nd:
        byb.setdefault(b, []).append(lab)
    ndl = [b for b in byb if b not in keep]
    # ② 양성 대조 — 원판 아카이브 셋(앞·가운데·끝)의 영역에서 그 아카이브 바늘이 다 나와야 한다
    ofiles = common.iso_files()

    def tag(p):  # "/A/SC000.DAT" → "A_SC000.DAT__" (조각 라벨 앞머리)
        return p.strip("/").replace("/", "_") + "__"

    arcs = sorted(
        p for p in ofiles if any(lab.startswith(tag(p)) for labs in byb.values() for lab in labs)
    )
    ostream = user_stream(common.orig_bin())
    tot = got = 0
    for p in (arcs[0], arcs[len(arcs) // 2], arcs[-1]):
        l, sz = ofiles[p]
        mine = [b for b in ndl if any(lab.startswith(tag(p)) for lab in byb[b])]
        h = find(ostream[l * common.USER_SIZE : l * common.USER_SIZE + sz], mine)
        tot += len(mine)
        got += sum(1 for b in mine if b in h)
    del ostream
    print(
        f"  원판 사본 잔존 [ps1-ed4] — 바늘 {len(ndl)}(번역 조각·UI) · 면제(번역 없는 조각) {len(keep)} · 양성 대조(원판 아카이브 셋) {got}/{tot}"
    )
    if tot == 0 or got < tot * 0.95:
        print("    ✗ 양성 대조 실패 — 검색기가 바늘을 못 찾는다")
        return 1
    # ③ 제품 — 디렉터리가 가리키는 파일 안의 출현만 센다(재배치로 비워진 옛 자리는 아무도 안 읽는다)
    hits = find(user_stream(image), ndl)
    files = common.iso_files(image)
    bad, dead = [], 0
    for b, ats in hits.items():
        for at in ats:
            f = live_file(files, at)
            if f is None:
                dead += 1
            else:
                bad.append((byb[b][0], len(b), f, at - files[f][0] * common.USER_SIZE))
    for lab, n, f, off in sorted(bad)[:12]:
        print(f"    ✗ 제품에 원판 바이트 그대로 — {lab} ({n}B) @ {f}+{off:#x}")
    refs = item_old_refs(bytes(common.read_file(common.EXE_PATH, image=image)))
    if refs:
        print(f"    ✗ 아이템 구조체 옛 자리를 가리키는 명령 {refs} 개 — 면제 근거가 깨졌다")
        bad.append(("ITEM_OLD", 0, "exe", 0))
    print(
        f"  → 사본 {len(bad)} (재배치로 비워진 옛 자리의 출현 {dead} 은 제외 — 디렉터리가 안 가리킨다)"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
