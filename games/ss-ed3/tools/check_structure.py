"""**구조 대조** — 원본과 구운 맵(`MAP*.BIN`)에서 **글자 바이트를 뺀 나머지(제어 코드 열)** 가 같은가.

    python3 games/ss-ed3/tools/check_structure.py                 # 검사 (어긋나면 rc 1)
    python3 games/ss-ed3/tools/check_structure.py --ledger        # relocations.tsv 를 새로 쓴다
    python3 games/ss-ed3/tools/check_structure.py --image <Disc1.bin>   # 다른 이미지로(회귀 시험)

🔴 **왜**(10-22 마스터 「새 게임에서 엄마 대사 뒤 크리스 대사가 안 나온다」): 10-21 재조판이 `10 00 FF 02` 사이에 `FF FF` 무동작 쌍을 끼운 꼴
   1,046 블록을 구웠다. **글 소실 검사도 길이 검사도 통과했고**(글자는 다 있고 길이는 보존이다) 대사 보기 하네스도 통과했다(블록을 따로 띄운다).
   스크립트가 **이어지는지**는 제어 코드의 순서가 원본과 같은지로만 가려진다 — 글자 바이트는 번역이라 달라도 되고, 제어는 달라선 안 된다.

검사 — 원본 블록(`mapfile.blocks`)을 기준으로 한다(구운 쪽은 글 길이가 달라 스스로 블록을 못 가른다):
  ① **블록 밖(틈) 바이트는 원본과 같아야 한다** — 헤더 · 종결(`10 00`) · 다음 화자 전환(`FF 02`) · 분기 · 호출 전부.
  ② **블록 안은 글 바이트(SJIS 쌍 · 반각)를 빼고 남는 제어 열이 같아야 한다** — `01 xx` 주입 토큰 포함. `0D`(개행) `0F`(쪽 넘김) `1A`(채움)는
     조판이 바꾸는 것이라 **허용 목록**(`structure_allow.json`)에서 종류별로 센다.
  ③ **옮긴 블록**(`choice_tail` 트램펄린 `FD 00 <꼬리 주소>`)은 옮긴 쪽 몸을 따라가 **돌아오는 `FD 00` 까지** 같은 열인지 본다 — 원래 자리의 덮인 구간은 ①② 에서 뺀다.
  ④ 틈의 **이름 칸 늘려 쓰기**처럼 의도한 바이트 변경은 허용 목록의 `gap_rules` 에 사유·근거와 함께 적은 꼴만 통과한다.

⚠ 허용 목록은 **「엔진이 그걸 어떻게 처리하나」의 근거**를 요구한다 — 시험 하네스는 보조일 뿐이다(블록 단독 재생은 이번 사고를 못 봤다).
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import mapfile as M
import reinsert as R

ALLOW = os.path.join(C.GAME_DIR, "structure_allow.json")
LEDGER = os.path.join(C.GAME_DIR, "relocations.tsv")
GOTO = b"\xfd\x00"
BASE = M.BASE
SOFT = (0x0D, 0x0F, 0x1A)  # 조판이 바꾸는 제어 — 종류별로 센다(개행 · 쪽 넘김 · 채움)


def tokens(span):
    """`(제어 열, {0D,0F,1A 수})` — 글 바이트(2바이트 쌍 · 반각 문자)는 버린다. `01 xx` 는 한 토큰."""
    out, soft = [], {0x0D: 0, 0x0F: 0, 0x1A: 0}
    i, n = 0, len(span)
    while i < n:
        b = span[i]
        if b in SOFT:
            soft[b] += 1
            i += 1
        elif b in (0x01, 0x02) and i + 1 < n:
            #   `01 xx` 주입 토큰 · `02 xx` 화자 머리 — 둘 다 두 바이트가 한 토큰이다(`02 01` 의 `01` 을 주입으로 읽지 않는다)
            out.append(bytes(span[i : i + 2]))
            i += 2
        elif b == 0xFF and span[i + 1 : i + 2] == b"\x81":
            out.append(bytes(span[i : i + 4]))  # 선택창 항목 머리 `FF 81 00 nn`
            i += 4
        elif b in (0xFD, 0xFE, 0xFF) and i + 1 < n:
            out.append(bytes(span[i : i + 2]))  # 옵코드 낱말(`FF xx` · `FD xx` · `FE xx`) — 글 첫 바이트가 아니다(`script_ops` 디스패처)
            i += 2
        elif b >= 0x80:
            i += 2
        elif 0x20 <= b <= 0x7E:
            i += 1
        else:
            out.append(bytes([b]))
            i += 1
    return out, soft


def trampolines(orig, built):
    """`[(p, 꼬리 주소, 돌아올 주소 r, 몸 끝 g)]` — 원래 자리 p 에 새로 놓인 `FD 00 <꼬리>` 와 그 몸이 `FD 00 <r>` 로 돌아오는 곳."""
    out = []
    n = len(orig)
    for m in re.finditer(re.escape(GOTO), bytes(built[:n])):
        p = m.start()
        if p + 6 > n or built[p : p + 6] == orig[p : p + 6]:
            continue
        t = int.from_bytes(built[p + 2 : p + 6], "big") - BASE
        if not (n <= t < len(built)):
            continue
        g = None
        for q in range(t, min(len(built) - 5, t + 4096)):
            if built[q : q + 2] == GOTO:
                r = int.from_bytes(built[q + 2 : q + 6], "big") - BASE
                if p < r <= n:
                    g = q
                    break
        if g is None:
            out.append((p, t, None, None))
        else:
            out.append((p, t, int.from_bytes(built[g + 2 : g + 6], "big") - BASE, g))
    return out


def compare_map(stem, orig, built, allow):
    """`(어긋남 목록, 장부 행, 통계)`."""
    bad, rows = [], []
    st = {"blocks": 0, "gap_bytes": 0, "moved": 0, "nl": 0, "pg": 0, "fill": 0, "blocks_soft_changed": 0, "voice_body": 0, "name_ext": 0, "total": 0}
    blks = M.blocks(orig)
    st["total"] = len(blks)
    tr = trampolines(orig, built)
    wins = []
    for p, t, r, g in tr:
        if r is None:
            bad.append((stem, p, "트램펄린이 돌아오는 `FD 00` 을 못 찾는다", t))
            continue
        wins.append((p, r))
        st["moved"] += 1
        key = next((i for i, b in enumerate(blks) if b["off"] >= p), None)
        if b"\xff\x35" in orig[p:r] or b"\xff\x35" in built[t:g]:
            #   음성 자막 몸 — `FF 35 <번호>` 호출이 있는 자리에 `voice_sub.py` 가 자막 호출을 늘려 끼운다(자체 검사 `voice_sub` 가 본다).
            #   여기서는 **원 자리로 돌아오는 것**(위 트램펄린 탐색)만 확인하고 장부에 올린다.
            st["voice_body"] += 1
            rows.append((stem, key, "스텁(음성 자막)", f"{p:#x}", f"{t:#x}", f"복귀 {r:#x}"))
            continue
        #   옮긴 몸은 글 뒤에 NUL 종료·패딩이 붙는다(선택지 항목·간판) — NUL 은 빼고 견준다
        o_tok = [x for x in tokens(orig[p:r])[0] if x != b"\x00"]
        b_tok = [x for x in tokens(built[t:g])[0] if x != b"\x00"]
        rows.append((stem, key, "스텁(옮김)", f"{p:#x}", f"{t:#x}", f"복귀 {r:#x}"))
        if o_tok != b_tok:
            bad.append((stem, p, "옮긴 몸의 제어 열이 원본 구간과 다르다", (o_tok, b_tok)))

    def inwin(a, b):
        return any(a < r and b > p for p, r in wins)

    slots = R.name_slots(blks, orig)
    nameblk = {i for i, b in enumerate(blks) if b["off"] == M.NAME_OFF} | set(slots)
    name_ends = {blks[i]["off"] + len(blks[i]["body"]) for i in nameblk}
    cut = [(0, M.NAME_OFF)]  # 헤더(포인터표) — 통째로 같아야 한다
    for blk in blks:
        cut.append((blk["off"], blk["off"] + len(blk["body"])))
    cut.sort()
    # ① 틈
    last = 0
    spans = []
    for a, b in cut:
        if a > last:
            spans.append((last, a))
        last = max(last, b)
    if last < len(orig):
        spans.append((last, len(orig)))
    for a, b in spans:
        if inwin(a, b):
            # 일부만 겹치면 겹치지 않는 조각만 본다
            segs, x = [], a
            for p, r in sorted(wins):
                if r <= x or p >= b:
                    continue
                if p > x:
                    segs.append((x, p))
                x = max(x, r)
            if x < b:
                segs.append((x, b))
        else:
            segs = [(a, b)]
        for x, y in segs:
            if x in name_ends:
                #   이름 칸 늘려 쓰기 — NUL 종료 문자열이고 칸 뒤가 **0 으로 비어 있는 만큼만**(`reinsert.patch_blocks`) 쓴다
                z = 0
                while x + z < y and orig[x + z] == 0:
                    z += 1
                dn = sum(1 for q in range(x, x + z) if built[q] != orig[q])
                st["name_ext"] += dn
                if dn:
                    nk = next((i for i in nameblk if blks[i]["off"] + len(blks[i]["body"]) == x), None)
                    rows.append((stem, nk, "이름 칸", f"{x:#x}", f"+{dn}B", "칸 뒤 0 구간까지 늘려 씀"))
                x += z
                if x >= y:
                    continue
            st["gap_bytes"] += y - x
            if orig[x:y] != built[x:y]:
                bad.append((stem, x, "틈 바이트가 달라졌다", (orig[x:y].hex()[:40], built[x:y].hex()[:40])))
    # ② 블록 본문
    for k, blk in enumerate(blks):
        a, b = blk["off"], blk["off"] + len(blk["body"])
        if inwin(a, b):
            continue
        st["blocks"] += 1
        o_tok, o_soft = tokens(orig[a:b])
        b_tok, b_soft = tokens(built[a:b])
        if k in nameblk:
            #   이름·맵 이름 칸은 NUL 종료 문자열 — 이름이 짧으면 뒤를 NUL 로 채운다
            while b_tok and b_tok[-1] == b"\x00":
                b_tok.pop()
            while o_tok and o_tok[-1] == b"\x00":
                o_tok.pop()
        if o_tok != b_tok:
            bad.append((stem, a, f"블록 {k} 의 제어 열이 다르다", (o_tok[:6], b_tok[:6])))
        st["nl"] += b_soft[0x0D] - o_soft[0x0D]
        st["pg"] += b_soft[0x0F] - o_soft[0x0F]
        st["fill"] += b_soft[0x1A]
        if b_soft != o_soft:
            st["blocks_soft_changed"] += 1
            if b_soft[0x0D] != o_soft[0x0D]:
                rows.append((stem, k, "재조판(0D)", f"{o_soft[0x0D]}", f"{b_soft[0x0D]}", "줄 수"))
            if b_soft[0x0F] != o_soft[0x0F]:
                rows.append((stem, k, "쪽 넘김(0F)", f"{o_soft[0x0F]}", f"{b_soft[0x0F]}", "쪽 수"))
            if b_soft[0x1A]:
                rows.append((stem, k, "채움(1A)", "0", "있음", "남는 바이트"))
    return bad, rows, st


def load_pair(image):
    o = C.open_disc(1, verify=False)
    n = C.Disc(image, user_off=C.USER_OFF)
    return o, n


def entry(d, name):
    for nm, lba, size in d.files():
        if nm == name:
            return d.read_extent(lba, size)
    return None


def file_rows(o, n):
    """`MAP*.BIN` 이 디스크 끝으로 옮겨졌나(LBA·크기) — 디렉터리 항목 대조."""
    of = {nm: (lba, size) for nm, lba, size in o.files() if C.is_map_file(nm)[0]}
    nf = {nm: (lba, size) for nm, lba, size in n.files() if C.is_map_file(nm)[0]}
    out = []
    for nm in sorted(of):
        if of[nm] != nf.get(nm):
            stem = C.is_map_file(nm)[1]
            out.append((stem, None, "파일 이전", f"LBA {of[nm][0]} · {of[nm][1]}B", f"LBA {nf[nm][0]} · {nf[nm][1]}B", "꼬리 증설"))
    return out


def ledger_text(rows, allow):
    """장부 — 종류별 엔진 근거·되돌리면은 `structure_allow.json` 의 같은 이름 항목에 한 번만 적는다(행마다 되풀이하면 2MB 가 된다)."""
    head = "맵\t블록\t종류\t원래 좌표\t새 좌표\t사유\t엔진 근거·되돌리면\n"
    body = []
    for stem, key, kind, a, b, why in rows:
        ref = f"structure_allow.json › {kind}" if kind in allow.get("rules", {}) else "(허용 목록에 없음)"
        body.append("\t".join([stem, "" if key is None else str(key), kind, a, b, why, ref]) + "\n")
    return head + "".join(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.join(C.BUILD_DIR, "Shiroki Majo (KR) (Disc 1).bin"))
    ap.add_argument("--ledger", action="store_true", help="relocations.tsv 를 새로 쓴다")
    ap.add_argument("--no-ledger-check", action="store_true", help="장부 일치를 보지 않는다(회귀 시험용)")
    ap.add_argument("--maps", default="")
    a = ap.parse_args()
    if not os.path.exists(a.image):
        print("이미지 없음 — 건너뜀")
        return 0
    allow = json.load(open(ALLOW, encoding="utf-8")) if os.path.exists(ALLOW) else {}
    o, n = load_pair(a.image)
    bad_all, rows_all = [], []
    tot = {"maps": 0, "blocks": 0, "gap_bytes": 0, "moved": 0, "nl": 0, "pg": 0, "fill": 0, "blocks_soft_changed": 0, "voice_body": 0, "name_ext": 0, "total": 0}
    want = set(a.maps.split(",")) if a.maps else None
    for nm, lba, size in o.files():
        ok, stem = C.is_map_file(nm)
        if not ok or (want and stem not in want):
            continue
        ob = o.read_extent(lba, size)
        bb = entry(n, nm)
        if bb is None:
            bad_all.append((stem, 0, "구운 이미지에 없다", None))
            continue
        bad, rows, st = compare_map(stem, ob, bb, allow)
        bad_all += bad
        rows_all += rows
        tot["maps"] += 1
        for k in tot:
            if k != "maps":
                tot[k] += st[k]
    if not want:
        rows_all += file_rows(o, n)
    #   허용 목록에 없는 종류가 나타나면 실패
    kinds = {}
    for r in rows_all:
        kinds[r[2]] = kinds.get(r[2], 0) + 1
        if r[2] not in allow.get("rules", {}):
            bad_all.append((r[0], 0, f"허용 목록에 없는 재배치 종류 「{r[2]}」", r[1]))
    print(f"대조 맵 {tot['maps']} · 블록 {tot['blocks']}/{tot['total']}(나머지는 옮긴 구간 — 몸을 따라가 대조) · 틈 {tot['gap_bytes']}B · 옮김 {tot['moved']} · 어긋남 {len(bad_all)}")
    print(f"  조판 증감 — 개행 {tot['nl']:+d} · 쪽 넘김 {tot['pg']:+d} · 1A {tot['fill']}B · 제어가 바뀐 블록 {tot['blocks_soft_changed']}")
    print("  장부 종류별 — " + " · ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    for b in bad_all[:30]:
        print("  ❌", b[0], f"{b[1]:#x}", b[2], str(b[3])[:140])
    text = ledger_text(rows_all, allow)
    if a.ledger:
        with open(LEDGER, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"장부 {len(rows_all)}행 → {os.path.relpath(LEDGER, C.GAME_DIR)}")
    elif not want and not a.no_ledger_check:
        cur = open(LEDGER, encoding="utf-8").read() if os.path.exists(LEDGER) else ""
        if cur != text:
            print("  ❌ relocations.tsv 가 구운 이미지와 다르다 — 장부에 없는 재배치가 있다. `check_structure.py --ledger` 로 다시 쓰고 커밋한다")
            return 1
    return 1 if bad_all else 0


if __name__ == "__main__":
    sys.exit(main())
