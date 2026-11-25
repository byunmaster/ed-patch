#!/usr/bin/env python3
"""씬 대사 번호별 짝 표 — 원판 롬 ↔ 제품 롬 (문안 검수용, 마스터 10-20 꼴 · 촬영 없음).

  python3 tools/pair_table.py --out <폴더> [--kr-bin <제품 이미지 bin>]

산출 `<out>/pairs.tsv`(번호 · 원판 대사 · 한글 대사 · 표시) + `<out>/manifest.md`(롬 sha1 · 분모 · 표시별 수).
⚠ 원문 포함 — 저장소 밖(`.local/work/inbox/`)에만 낸다. **탭으로만 나눠 읽을 것**(따옴표 이스케이프 없음).

번호: `씬:eid`(예 `ED2SCN9:514` — 원판 SCN 블록 번호 = `script/<씬>.json` 키) · `씬:H`(씬 0번 항목 = 맵 이름 머리글).
표기: `/` = 줄 바꿈 · `⏎` = 이 쪽 뒤에 같은 블록의 다음 쪽이 이어진다(쪽 넘김, 대사창 갈아 끼움) ·
      `%c이름%c` = 화자 머리 · 끝 `%c` = 블록 끝 · `%s`(이름)·`%d`(수치) 그대로 · 그 밖의 제어 바이트 `<NN>`.
      ⏎ 는 본문 중간의 `%c` 를 쪽 넘김으로 읽은 것이다 — `%c%s%c`(이름 주입) 와 짧은 글자 둘러싸기(색 강조,
      ≤8자·줄 바꿈 없음·문장 끝 부호 없음)는 `%c` 그대로 둔다.
표시: (비어 있음) 정상 짝 · 번역 대상 아님 · 원문 일본어 없음 · 둘 다 빔 · 접두 사본 추정 ·
      빌드 이미지에서 못 찾음 · 앞 스크립트 바이트만 뗀 것 …
일본어 글자가 없는 원문(전각 영문·숫자·부호·스크립트 바이트뿐) 블록도 행에 넣는다 — `표시` 에 `원문 일본어 없음`.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault(
    "LOCK_BYPASS", "1"
)  # 락 관리 도구용 우회 — 방출 바이트는 안 바뀐다(검증만 건너뜀)

import hangul_map
import patch_sys_ui as P
import reinsert_kr_pilot as R
from common import BUILD_DIR, ORIG_BIN, OUT_DIR, extract

MC, PS, PD = b"%c", b"%s", b"%d"
KANA_HAN = re.compile(
    "[\u3040-\u30ff\u3400-\u9fff]"
)  # 반각 가나(스크립트 바이트와 구분 불가)는 뺀다
SENT_END = set("。！？…」』".replace("」", ""))
_KR_REV = None


def kr_rev():
    global _KR_REV
    if _KR_REV is None:
        _KR_REV = {hangul_map.syllable_sjis(ch): ch for ch in hangul_map.SYL_INDEX}
        _KR_REV.update({0xD8: "“", 0xDA: "”"})  # 반각 여닫는 따옴표 전용 글리프 코드
    return _KR_REV


def decode(b, kr):
    """바이트 → 토큰 목록 [("t", 글자) | ("c",) | ("s",) | ("d",) | ("n",) | ("x", 코드)] (끝 00 은 뗀다)."""
    b = b.rstrip(b"\x00")
    toks, i = [], 0
    rev = kr_rev() if kr else {}
    while i < len(b):
        c = b[i]
        if c == 0x25 and i + 1 < len(b) and b[i + 1] in b"csd":
            toks.append((chr(b[i + 1]),))
            i += 2
        elif c == 0x0A:
            toks.append(("n",))
            i += 1
        elif c < 0x20:
            toks.append(("x", c))
            i += 1
        elif kr and c in rev:  # 1바이트 전용 코드(반각 따옴표)
            toks.append(("t", rev[c]))
            i += 1
        elif (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) and i + 1 < len(b):
            w = int.from_bytes(b[i : i + 2], "big")
            if w in rev:
                toks.append(("t", rev[w]))
                i += 2
                continue
            try:
                toks.append(("t", b[i : i + 2].decode("cp932")))
                i += 2
            except UnicodeDecodeError:  # 스크립트 바이트 — 글자로 읽지 않는다
                toks.append(("x", c))
                i += 1
        elif c >= 0x80:
            toks.append(
                ("t", b[i : i + 1].decode("cp932", "replace")) if 0xA1 <= c <= 0xDF else ("x", c)
            )
            i += 1
        else:
            toks.append(("t", chr(c)))
            i += 1
    return toks


def render(toks):
    """토큰 → 표 문자열. 본문 중간 %c 는 쪽 넘김 ⏎ (머리 %c이름%c · 끝 %c · %c%s%c · 짧은 강조는 %c 그대로)."""
    idx = [i for i, t in enumerate(toks) if t[0] == "c"]
    keep = set()
    # 화자 머리: 선두 %c … %c
    if idx and idx[0] == 0 and len(idx) >= 2 and all(t[0] in ("t",) for t in toks[1 : idx[1]]):
        keep |= {idx[0], idx[1]}
    if idx and idx[-1] == len(toks) - 1:
        keep.add(idx[-1])  # 블록 끝 %c
    # %c%s%c
    for i in idx:
        if i + 2 < len(toks) and toks[i + 1][0] == "s" and toks[i + 2][0] == "c":
            keep |= {i, i + 2}
    # 짧은 강조 쌍: 본문 중간 %c … %c (≤8자, 줄 바꿈·문장 끝 부호 없음)
    mid = [i for i in idx if i not in keep]
    j = 0
    while j + 1 < len(mid):
        a, b = mid[j], mid[j + 1]
        seg = toks[a + 1 : b]
        txt = "".join(t[1] for t in seg if t[0] == "t")
        if (
            seg
            and all(t[0] == "t" for t in seg)
            and len(txt) <= 8
            and not (set(txt) & set("。！？…"))
        ):
            keep |= {a, b}
            j += 2
        else:
            j += 1
    out = []
    for i, t in enumerate(toks):
        if t[0] == "t":
            out.append(t[1])
        elif t[0] == "c":
            out.append("%c" if i in keep else "⏎")
        elif t[0] == "s":
            out.append("%s")
        elif t[0] == "d":
            out.append("%d")
        elif t[0] == "n":
            out.append("/")
        else:
            out.append(f"<{t[1]:02X}>")
    return "".join(out).replace("\t", " ")


def clean(s):
    return s.replace("\n", "/").replace("\r", "")


def scene_files(kr_bin):
    """제품 롬의 씬 파일 {씬: bytes} — 재배치 매니페스트(scn_layout.json)의 현재 LBA."""
    out = {}
    for name, lba, size in P._scn_layout():
        out[name] = extract(lba, size, path=kr_bin)
    return out


def sha1_of(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_scn(scn):
    with open(os.path.join(OUT_DIR, "scn_jp", f"{scn}.json"), encoding="utf-8") as f:
        return json.load(f)


def header_pairs():
    jp2kr = {}
    for jp, kr in P.places_for_build() + P.SCN_PLACES + P._ed2_scn_places():
        jp2kr.setdefault(jp, kr)
    for jp, kr, _ in P.CHAR_NAMES:
        jp2kr.setdefault(jp, kr)
    return jp2kr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--kr-bin", default=os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin"))
    a = ap.parse_args()
    kr_bin = a.kr_bin
    os.makedirs(a.out, exist_ok=True)

    cands = {}
    for scn, eid, _raw, cand, _t in R.iter_candidates():
        cands[(scn, eid)] = cand
    rom = scene_files(kr_bin)
    jp2kr = header_pairs()

    rows, cnt = [], Counter()
    notfound = []
    for scn, _lba, _size in R.SCN_FILES:
        doc = _load_scn(scn)
        data = rom[scn]
        for e in doc["entries"]:
            eid = e["entry_id"]
            raw = bytes.fromhex(e["raw_hex"]) if e.get("raw_hex") else b""
            if e.get("kind") == "header":
                nm = raw.split(b"\x00")[0]
                jp = nm.decode("cp932", "replace")
                kr = jp2kr.get(jp)
                kb = hangul_map and P.H.encode_kr(kr) if kr else None
                tag = ""
                if kr is None:
                    tag = (
                        "번역 대상 아님" if not KANA_HAN.search(jp) else "한글 없음(지명 표에 없음)"
                    )
                    krs = jp
                else:
                    krs = kr
                    if kb is not None and kb not in data:
                        tag = "빌드 이미지에서 못 찾음"
                if not KANA_HAN.search(jp):
                    tag = (tag + " · " if tag else "") + "원문 일본어 없음"
                rows.append(
                    (
                        f"{scn}:H",
                        clean(jp),
                        clean(krs),
                        "맵 이름 머리글" + (f" · {tag}" if tag else ""),
                    )
                )
                cnt["맵 이름 머리글"] += 1
                continue
            jt = decode(raw, False)
            jpv = render(jt)
            # %c 도 없고 제어 바이트가 셋 이상 섞인 블록은 대사가 아니라 스크립트·표 데이터(깨진 글자처럼 보이는 바이트열)
            ctrl = sum(1 for c in raw.rstrip(b"\x00") if c < 0x20 and c != 0x0A)
            dialogue = MC in raw or ctrl < 3
            has_jp = dialogue and bool(KANA_HAN.search("".join(t[1] for t in jt if t[0] == "t")))
            cand = cands.get((scn, eid))
            tags = []
            if cand is None:
                krv = jpv
                if not has_jp:
                    tags.append("번역 대상 아님" + ("" if dialogue else "(스크립트·표 데이터)"))
                else:
                    nm = _place_swap(raw, jp2kr, data)
                    if nm:
                        krv, tg = nm
                        tags.append(tg)
                    else:
                        # 대사 경로가 아니라 지명·비명 치환 등 다른 경로가 제자리에서 바꾼 블록 — 롬의 같은 자리를 읽는다
                        off = int(e["file_offset"], 16)
                        at = data[off : off + len(raw)]
                        if len(at) == len(raw) and at.rstrip(b"\x00") != raw.rstrip(b"\x00"):
                            krv = render(decode(at, True))
                            tags.append("롬 제자리 읽음(다른 경로가 치환)")
                        elif _only_prefix(raw):
                            tags.append("번역 대상 아님(포인터 표 접두만 있고 본문 없음)")
                        else:
                            tags.append(
                                "접두 사본 추정" if _prefix_copy(scn, eid) else "한글 후보 없음"
                            )
            else:
                kt = decode(cand, True)
                krv = render(kt)
                if cand.rstrip(b"\x00") not in data:
                    stripped = cand.lstrip(b"\x00")
                    # 앞 스크립트 바이트만 뗀 꼴이 롬에 있는지
                    body = cand.rstrip(b"\x00")
                    k0 = next((i for i, c in enumerate(body) if c >= 0x20), 0)
                    if body[k0:] in data:
                        tags.append("앞 스크립트 바이트만 뗀 것")
                    else:
                        got = _rom_read(data, krv)
                        if got:
                            krv = got
                            tags.append("롬에서 읽음(줄 바꿈·꼬리 표기만 방출 후보와 다름)")
                        else:
                            tags.append("빌드 이미지에서 못 찾음")
                        notfound.append(f"{scn}:{eid}")
                    del stripped
                if (
                    not "".join(t[1] for t in kt if t[0] == "t").strip()
                    and not "".join(t[1] for t in jt if t[0] == "t").strip()
                ):
                    tags.append("둘 다 빔")
            if not has_jp:
                tags.append("원문 일본어 없음")
            if krv == jpv and has_jp and cand is not None:
                tags.append("원판과 같음")
            rows.append((f"{scn}:{eid}", clean(jpv), clean(krv), " · ".join(tags)))
            for t in tags:
                cnt[t] += 1
            if not tags:
                cnt["정상"] += 1

    p = os.path.join(a.out, "pairs.tsv")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("번호\t원판 대사\t한글 대사\t표시\n")
        f.writelines("\t".join(r) + "\n" for r in rows)
    stats = {
        "rows": len(rows),
        "cnt": dict(cnt),
        "notfound": notfound,
        "kr_sha1": sha1_of(kr_bin),
        "orig_sha1": sha1_of(ORIG_BIN),
    }
    with open(os.path.join(a.out, "stats.json"), "w") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in stats.items() if k != "notfound"}, ensure_ascii=False))
    print("못 찾음", len(notfound), notfound[:40])


def _only_prefix(raw):
    """블록이 포인터 표 접두(4B 워드 `xx xx 1N 80`)뿐이고 본문이 없다."""
    b, k = raw.rstrip(b"\x00"), 0
    while k + 4 <= len(b) and b[k + 3] == 0x80 and b[k + 2] < 0x20:
        k += 4
    return k > 0 and k == len(b)


HANGUL = re.compile("[가-힣]")


def _rom_read(data, krv):
    """방출 후보 바이트가 롬에 그대로 없을 때 — 후보의 한글 음절열을 (사이에 낀 줄 바꿈·공백·%c 를 건너뛰며) 롬에서 찾아 그 블록을 읽는다."""
    syl = [hangul_map.syllable_sjis(c).to_bytes(2, "big") for c in krv if HANGUL.match(c)]
    if len(syl) < 5:  # 너무 짧으면 같은 낱말이 여러 곳에 걸려 엉뚱한 블록을 읽는다
        return None
    gap = rb"(?:[\x01-\x7f]|\x81[\x40-\xac]){0,8}"  # 줄 바꿈·공백·%c·ASCII/전각 부호
    hits = list(re.finditer(gap.join(re.escape(x) for x in syl), data, re.DOTALL))
    if len(hits) != 1:
        return None
    m = hits[0]
    h = m.start()
    r1 = data.rfind(b"%c", 0, h)
    r0 = data.rfind(b"%c", 0, r1) if r1 >= 0 else -1
    start = r0 if r0 >= 0 and b"\x0a" not in data[r0:r1] and r1 - r0 <= 30 else r1
    if start < 0 or h - start > 40:
        start = h
    end = data.find(b"\x00", m.end())
    return render(decode(data[start:end], True))


def _place_swap(raw, jp2kr, data):
    """대사 경로가 아니라 `patch_scn_headers` 가 바꾸는 지명·이름 표 항목 — 이름 앞 스크립트 바이트는 그대로."""
    body = raw.rstrip(b"\x00")
    for jp, kr in jp2kr.items():
        jb = jp.encode("cp932")
        if body.endswith(jb) and len(body) - len(jb) <= 6:
            kb = P.H.encode_kr(kr)
            pre = render(decode(body[: len(body) - len(jb)], False))
            ok = kb in data
            return pre + kr, "지명 표 치환(롬 확인)" if ok else "지명 표 치환인데 롬에서 못 찾음"
    return None


_PREFIX = None


def _prefix_copy(scn, eid):
    """원문에 가나 문장이 있는데 한글 후보가 없는 블록이 다른 블록의 접두 사본인가(대표 사본이 번역한다고 추정)."""
    global _PREFIX
    if _PREFIX is None:
        _PREFIX = {}
        for s, _l, _z in R.SCN_FILES:
            d = _load_scn(s)
            ent = [
                (x["entry_id"], bytes.fromhex(x["raw_hex"]).rstrip(b"\x00"))
                for x in d["entries"]
                if x.get("raw_hex")
            ]
            _PREFIX[s] = ent
    me = dict(_PREFIX[scn]).get(eid, b"")
    return bool(me) and any(
        i != eid and len(r) > len(me) and r.startswith(me) for i, r in _PREFIX[scn]
    )


if __name__ == "__main__":
    main()
