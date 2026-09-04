#!/usr/bin/env python3
"""`textmap/*.json` 코퍼스의 `ours` 에 **정발 짝이 있나** — 후보만 낸다.

## 왜 따로인가

SCN 대사는 `adopt_jeongbal.match()` 가 장소·시기·화자로 좁힌다. EXE 쪽 코퍼스(전투·엔딩·
오프닝·아이템)는 축이 다르다 — 「어느 마을」이 없고 **어느 파일**(전투면 `MONDLL/M0xx.DLL`,
엔딩이면 `ENDING.EXE`)이 그 자리를 대신한다.
그래서 게이트를 그대로 못 쓰고, 대신 같은 규율을 따른다:

    좁히기   그 항목이 이미 가리키는 파일(형제 조각의 `f`) 우선 → 없으면 전 파일
    판정     **JP 원문을 읽어서** 한다(유사도는 후보를 줄이는 데만)
    적용     채택 = `ours` → `{f,o,l}` 포인터. 그래야 문안이 리포에 안 남는다

## ⚠ 검산부터 (체크리스트 4-B)

`--verify` 는 **이미 포인터인 항목**을 정답셋으로 쓴다 — 그 문안을 매칭기에 주면 같은
좌표를 돌려줘야 한다. 정답을 아는 입력이 리포에 있는데 안 쓰면, 버그를 커밋한 뒤에 만난다.

  python3 tools/past_textmap_match.py --verify              # 매칭기 검산 (먼저)
  python3 tools/past_textmap_match.py                      # 후보 (기본 = battle)
  python3 tools/past_textmap_match.py -c opening --verify  # 다른 코퍼스
  python3 tools/past_textmap_match.py --all                # 코퍼스 전부 (검산 → 후보)

⚠ **검산이 안 되는 코퍼스가 있다** — 포인터가 하나도 없으면 정답셋이 없다(`opening` 이
그렇다). 그럴 땐 후보를 **사람이 원문과 대조해** 판정한다. 검산 결과가 「0건 통과」인 것을
「통과」로 읽지 않도록, 그 경우는 따로 말한다(체크리스트 4-B).
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import REVIEW_DIR, ROOT

DOS = os.path.join(ROOT, "..", "..", "originals", "kr", "dos-ed1")
MIN_LEN = 6  # 이보다 짧으면 몬스터 이름·조각이라 유사도가 튄다


def _files():
    return sorted(glob.glob(os.path.join(DOS, "**", "*.DLL"), recursive=True)) + sorted(
        glob.glob(os.path.join(DOS, "*.EXE"))
    )


_CACHE = {}


def blob(path):
    if path not in _CACHE:
        _CACHE[path] = open(path, "rb").read()
    return _CACHE[path]


def rel(path):
    return os.path.relpath(path, DOS).replace(os.sep, "/")


def find(text, prefer=None):
    """정발에서 이 문안을 **바이트로** 찾는다 — [(파일, 오프셋, 길이)].

    ⚠ 정발은 표시 개행을 `\\x01` 로 넣는다. 우리 문안의 공백/개행 자리가 그거일 수 있어
    **공백을 건너뛰며** 맞춘다(공백·`\\x01` 를 같은 것으로 본다).
    """
    # ⚠ `\s` 는 `\x01`(정발 표시 개행)을 **안 잡는다** — 찾을 쪽엔 남고 대상에선 지워져
    #   자기가 만든 좌표도 못 찾는다(검산이 커밋 전에 걸러 냈다, 2026-08-18).
    want = re.sub(r"[\s\x01\x02\x03]+", "", text)
    if len(want) < MIN_LEN:
        return []
    try:
        wb = want.encode("cp949")
    except Exception:
        return []
    out = []
    order = ([p for p in _files() if rel(p) == prefer] if prefer else []) + _files()
    for p in order:
        b = blob(p)
        # 공백·표시개행을 지운 사본에서 찾고, 원본 구간으로 되짚는다
        idx, buf = [], bytearray()
        i = 0
        while i < len(b):
            c = b[i]
            if c in (0x20, 0x01, 0x0A, 0x0D, 0x09):
                i += 1
                continue
            buf.append(c)
            idx.append(i)
            i += 1
        flat = bytes(buf)
        st = 0
        while True:
            j = flat.find(wb, st)
            if j < 0:
                break
            beg, end = idx[j], idx[j + len(wb) - 1]
            out.append((rel(p), beg, end - beg + 1))
            st = j + 1
        if out and prefer and rel(p) == prefer:
            break
    return out


# ED1 EXE 쪽 코퍼스 — `textmap/<이름>.json`. ED2 는 트랙이 열릴 때 더한다.
CORPORA = ("battle", "ending_ed1", "opening", "items_battle")


def runs(min_len=6):
    """정발 전 파일에서 **한글이 든 문자열 구간**을 뽑는다 — [(파일, 오프셋, 텍스트)].

    축자 일치(`find`)가 0 이어도 「정발을 살짝 고쳐 쓴 것」은 남는다 — 폭이 모자라 손댄
    오프닝이 그렇다(유저 증언 2026-08-18). 저작권 관점에서 그게 진짜 사각지대라 유사 대조를
    따로 둔다. 판정은 사람이 한다(이건 **후보 생성**이다).
    """
    out = []
    for path in _files():
        b = blob(path)
        cur, beg = bytearray(), None
        for i, c in enumerate(b + b"\x00"):
            # cp949 한글 2바이트 + 인쇄 가능 아스키·표시개행을 한 덩이로 본다
            if c >= 0x81 or c in (0x20, 0x01) or 0x21 <= c <= 0x7E:
                if beg is None:
                    beg = i
                cur.append(c)
                continue
            if beg is not None and len(cur) >= min_len * 2:
                try:
                    t = bytes(cur).decode("cp949")
                    if re.search(r"[가-힣]{2,}", t):
                        out.append((rel(path), beg, t))
                except Exception:
                    pass
            cur, beg = bytearray(), None
    return out


def decoded(path):
    """정발 파일을 통째로 디코드한 텍스트와 **글자→바이트 오프셋** 표.

    포인터는 바이트 좌표라 되짚을 표가 필요하다. cp949 는 가변폭이라 글자마다 시작
    오프셋을 들고 간다(이게 없으면 좌표를 손으로 세게 되고, 손으로 세면 틀린다).
    """
    if path in _DEC:
        return _DEC[path]
    # ⚠ 정발은 줄바꿈 자리에 **표시 개행 `\x01`** 을 넣는다. 우리 문안은 거기가 공백이라
    #   그대로 두면 「정발에 없다」가 되어 **정발 파생이 우리 것으로 남는다**(오프닝 5줄이
    #   그렇게 숨어 있었다, 2026-08-18). 맞출 때는 공백으로 보고, 옮길 때 `fix` 로 되돌린다.
    b, out, idx, i = blob(path), [], [], 0
    while i < len(b):
        n = 2 if (0x81 <= b[i] <= 0xFE and i + 1 < len(b)) else 1
        try:
            ch = b[i : i + n].decode("cp949")
        except Exception:
            ch = "\uFFFD"
        if ch in ("\x01", "\x00"):
            # 표시 개행도, 문자열 경계(NUL)도 우리 문안에서는 **공백**이다.
            # ⚠ NUL 은 「정발이 거기서 문자열을 끊었다」는 뜻이라 포인터가 넘을 수 없다 —
            #   맞출 때만 공백으로 보고, 낼 때 그 경계에서 포인터를 가른다(`_split_spans`).
            ch = " "
        out.append(ch)
        idx.append((i, n))
        i += n
    _DEC[path] = ("".join(out), idx)
    return _DEC[path]


_DEC = {}
MIN_PTR = 6  # 이보다 짧은 축자 구간은 포인터로 안 뺀다 — 낱말 수준은 저작권 대상이 아니다


def cover(text, path):
    """우리 문안을 **정발 축자 구간으로 덮는다** — [(조각, (오프셋, 길이) | None)].

    긴 축자 구간은 포인터가 되고 나머지만 우리 것으로 남는다. 어절 하나를 지워 축자
    일치를 피한 자리(오프닝이 그랬다)도 **긴 조각들은 그대로 정발**이라 이렇게 잡힌다.
    """
    dec, idx = decoded(path)
    out, i = [], 0
    while i < len(text):
        hit = None
        for j in range(len(text), i + MIN_PTR - 1, -1):  # 가장 긴 것부터
            k = dec.find(text[i:j])
            if k >= 0:
                beg = idx[k][0]
                end = idx[k + (j - i) - 1]
                hit = (text[i:j], (beg, end[0] + end[1] - beg))
                break
        if hit:
            out.append(hit)
            i += len(hit[0])
        else:
            if out and out[-1][1] is None:
                out[-1] = (out[-1][0] + text[i], None)
            else:
                out.append((text[i], None))
            i += 1
    return out


def align_line(text, path, span=24):
    """우리 줄 ↔ 정발 구간을 맞춘다 — `(parts, fixes, 덮임비율)` 또는 None.

    ⚠ 조각으로 잘게 쪼개 포인터를 다는 방식은 버렸다 — `약해`/`져` 처럼 **낱말 중간이
    갈리고**, `로 이루어진 ` 같은 우연한 일치까지 정발 것으로 만든다. 레포 관용은 **줄 통째
    포인터 + 낱말 단위 `fix`** 다(`derive_text`: 「⚠ 낱말까지만 — 문장을 여기 적으면 정발
    문안이 리포에 박힌다」). 그래서 차이가 낱말 수준일 때만 옮긴다.

    🔴 **`fix` 의 왼쪽은 절대 빈 문자열이면 안 된다** — `"".replace("", x)` 는 **모든 글자
    사이에** 끼워 넣는다. 우리 쪽에만 있는 말(삽입)은 `fix` 가 아니라 `parts` 의 `ours` 로
    낸다. (미리보기에서 `'' → '져'` 가 나와서 잡았다, 2026-08-18)
    """
    import difflib

    dec, idx = decoded(path)
    n = len(text)
    best = None
    start = 0
    while len(text) >= 4:
        k = dec.find(text[:4], start)
        if k < 0:
            break
        start = k + 1
        for dl in range(-2, span):
            seg = dec[k : k + n + dl]
            if not seg:
                continue
            r = difflib.SequenceMatcher(None, text, seg).ratio()
            if best is None or r > best[0]:
                best = (r, k, seg)
    if best is None:
        return None  # 첫 네 글자부터 다르면 정발 파생이 아니다
    _r, k, seg = best
    ops = difflib.SequenceMatcher(None, seg, text).get_opcodes()

    # 양 끝의 「우리 쪽에만 있는 말」은 잘라 `parts` 로 낸다(가운데 삽입은 안 받는다)
    head = tail = ""
    if ops and ops[0][0] == "insert":
        head = text[ops[0][3] : ops[0][4]]
        ops = ops[1:]
    if ops and ops[-1][0] == "insert":
        tail = text[ops[-1][3] : ops[-1][4]]
        ops = ops[:-1]
    fixes, equal = [], 0
    for tag, i1, i2, j1, j2 in ops:
        a, b = seg[i1:i2], text[j1:j2]
        if tag == "equal":
            equal += i2 - i1
            continue
        if not a:  # 가운데 삽입 — `fix` 로는 표현할 수 없다
            return None
        # 🔴 왼쪽이 **일반적이면 전역 치환이 된다** — `' ' → ''` 하나가 그 문장의 공백을
        #    전부 날렸다(2026-08-18 미리보기에서 잡았다). 유일해질 때까지 앞뒤로 넓힌다.
        while seg.count(a) > 1 and max(len(a), len(b)) < 8:
            if i1 > 0:
                i1 -= 1
                j1 -= 1
            elif i2 < len(seg):
                i2 += 1
                j2 += 1
            else:
                break
            a, b = seg[i1:i2], text[j1:j2]
        if seg.count(a) != 1 or max(len(a), len(b)) > 8:  # ⚠ 낱말 수준까지만
            return None
        fixes.append([a, b])
    # ⚠ **명칭·라벨은 대상이 아니다**(레포 방침: 단어 수준은 저작권 보호 대상이 아니다).
    #   비율만 보면 `썬더하운드C` 의 `썬더하운드` 가 83% 로 통과한다 — 실측 11건이 전부
    #   몬스터 이름과 `Gold를 얻었다.` 류였다. 그래서 **덮인 절대 길이 + 여러 낱말**을 본다.
    covered = "".join(seg[i1:i2] for tag, i1, i2, _j1, _j2 in ops if tag == "equal")
    if len(covered.replace(" ", "")) < 8 or " " not in covered.strip():
        return None
    if not equal or equal / len(text) < 0.6:
        return None
    beg = idx[k][0]
    end = idx[k + len(seg) - 1]
    o, ln = beg, end[0] + end[1] - beg
    raw = blob(path)[o : o + ln]
    if b"\x01" in raw:  # 표시 개행을 공백으로 되돌린다(위 `decoded` 주석)
        fixes.insert(0, ["\x01", " "])
    # ⚠ **하위 폴더까지 담는다** — `basename` 이면 `MONDLL/M200.DLL` 이 `M200.DLL` 이 돼
    #   빌드가 원본을 못 찾는다(전투에서 바로 터졌다, 2026-08-18). 좌표의 파일은 늘 `rel`.
    spans = _split_spans(rel(path), raw, o)
    parts = ([{"ours": head}] if head else []) + spans + ([{"ours": tail}] if tail else [])
    return parts, fixes, equal / len(text)


def _split_spans(name, raw, base):
    """NUL 로 끊긴 구간을 **정발 자신의 경계에서** 여러 포인터로 가른다.

    사이는 우리 공백으로 잇는다 — 낱말 중간을 가르는 것과 다르다. 정발이 거기서 문자열을
    끊었다는 사실을 그대로 옮기는 것뿐이다.
    """
    out, i = [], 0
    for chunk in raw.split(b"\x00"):
        if chunk:
            out.append({"f": name, "o": base + i, "l": len(chunk)})
        i += len(chunk) + 1
        out.append({"ours": " "})
    return out[:-1] if out and "ours" in out[-1] else out


def _derived(parts, fixes):
    """`derive_text` 와 **같은 순서로** 값을 만든다 — 미리보기 단계에서 검산하려고."""
    import derive_text as D

    val = ""
    for pt in parts:
        if "ours" in pt:
            val += pt["ours"]
            continue
        b = blob(os.path.join(DOS, pt["f"]))
        val += b[pt["o"] : pt["o"] + pt["l"]].decode("euc-kr")
    for a, b in fixes:
        val = val.replace(a, b)
    return D._PUNCT_SP.sub("", val)


def pointerize(corpus, apply=False, prefer=None):
    """`ours` 줄이 사실은 **정발 문안이면** 포인터로 옮긴다.

    ⚠ 문안은 한 글자도 안 바뀌어야 한다 — 옮기기 전에 `derive_text` 와 같은 경로로 값을
    만들어 **원문과 글자까지 대조**한다(안 맞으면 그 줄은 손대지 않는다). 커밋 뒤에 sha
    가드가 잡아 주기를 기다리지 않는다.
    """
    d = entries(corpus)
    files = sorted({p["f"] for e in d["entries"] for p in (e.get("parts") or [e]) if "f" in p})
    files = [prefer] if prefer else files
    if not files:
        print(f"  ⏭ {corpus}: 기준 파일을 모르겠다 — `--file` 로 준다")
        return 1
    moved = kept = bad = 0
    for e in d["entries"]:
        if "ours" not in e:
            continue
        t = e["ours"]
        if len(re.sub(r"\s+", "", t)) < MIN_PTR or not re.search(r"[가-힣]{2,}", t):
            kept += 1
            continue
        got = None
        for f in files:
            a = align_line(t, os.path.join(DOS, f))
            if a and (got is None or a[2] > got[2]):
                got = a
        if not got:
            kept += 1
            continue
        parts, fixes, cov = got
        val = _derived(parts, fixes)
        if val != t:
            bad += 1
            print(f"  ⚠ {e['k']} 되짚기 불일치 — 손대지 않는다: {val!r} ≠ {t!r}")
            continue
        moved += 1
        print(f"  {e['k']}  일치 {cov:.0%}  {t!r}")
        for pt in parts:
            print(f"      {'우리 것 ' + repr(pt['ours']) if 'ours' in pt else '포인터 ' + pt['f'] + f' +0x{pt[chr(111)]:X}'}")
        for a, b in fixes:
            print(f"      교정 {a!r} → {b!r}")
        if apply:
            e.pop("ours", None)
            if len(parts) == 1:
                e["src"] = parts[0]
            else:
                e["parts"] = parts
            if fixes:
                e["fix"] = fixes
    print(f"  [{corpus}] 옮길 줄 {moved} · 그대로 둘 줄 {kept} · 되짚기 실패 {bad}")
    if apply and moved:
        p = os.path.join(ROOT, "textmap", f"{corpus}.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        print(f"  → {p} 갱신")
    elif moved:
        print("  (미리보기 — 반영하려면 `--apply`)")
    return 0


def _grams(t, n=3):
    t = re.sub(r"[\s\x01-\x03]+", "", t)
    return {t[i : i + n] for i in range(max(0, len(t) - n + 1))}


def fuzzy(corpus, top=3, floor=0.55):
    """`ours` 마다 정발에서 **가장 닮은 구간**을 찾는다 — 축자 일치가 0인 자리를 위해.

    3그램 겹침으로 후보를 좁히고(전수 difflib 는 느리다) 그 안에서만 유사도를 잰다.
    """
    import difflib

    pool = runs()
    index = [(f, o, t, _grams(t)) for f, o, t in pool]
    d = entries(corpus)
    rows = []
    for i, e in enumerate(d["entries"]):
        parts = e.get("parts") or ([e] if "ours" in e else [])
        for j, pt in enumerate(parts):
            t = (pt.get("ours") or "").strip()
            if len(re.sub(r"\s+", "", t)) < MIN_LEN or not re.search(r"[가-힣]{2,}", t):
                continue
            g = _grams(t)
            if not g:
                continue
            cand = sorted(
                ((len(g & gi) / len(g), f, o, ti) for f, o, ti, gi in index if g & gi),
                reverse=True,
                key=lambda x: x[0],
            )[:40]
            best = []
            for _sc, f, o, ti in cand:
                r = difflib.SequenceMatcher(None, t, ti).ratio()
                best.append((round(r, 3), f, o, ti))
            best.sort(reverse=True)
            best = [b for b in best[:top] if b[0] >= floor]
            if best:
                rows.append(dict(entry=i, part=j, ours=t, near=best))
    print(f"  [{corpus}] 유사 후보 {len(rows)}건 (문턱 {floor})")
    os.makedirs(REVIEW_DIR, exist_ok=True)
    p = os.path.join(REVIEW_DIR, f"fuzzy_{corpus}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    if rows:
        print(f"  → {p} (⚠ 정발 문안 포함 — 커밋 금지)")
    return 0


def entries(corpus="battle"):
    p = os.path.join(ROOT, "textmap", f"{corpus}.json")
    return json.load(open(p, encoding="utf-8"))


def verify(corpus="battle"):
    """🔴 **이미 포인터인 항목**을 정답셋으로 매칭기를 검산한다."""
    d = entries(corpus)
    ok = miss = wrong = 0
    bad = []
    for i, e in enumerate(d["entries"]):
        parts = e.get("parts") or ([e] if "src" in e else [])
        for pt in parts:
            if "f" not in pt:
                continue
            b = blob(os.path.join(DOS, pt["f"]))
            try:
                txt = b[pt["o"] : pt["o"] + pt["l"]].decode("cp949")
            except Exception:
                continue
            if len(re.sub(r"\s+", "", txt)) < MIN_LEN:
                continue
            got = find(txt, prefer=pt["f"])
            if not got:
                miss += 1
                bad.append((i, pt["f"], pt["o"], "못 찾음"))
            elif any(g[0] == pt["f"] and g[1] == pt["o"] for g in got):
                # ⚠ **자리가 맞으면 통과다.** 길이는 다를 수 있다 — 공백·표시개행(`\x01`)을
                # 건너뛰며 맞추므로 꼬리 공백 포함 여부가 갈린다. 좌표가 틀린 것과는 다르다.
                ok += 1
            else:
                wrong += 1
                bad.append((i, pt["f"], pt["o"], f"다른 자리 {got[0]}"))
    n = ok + miss + wrong
    if not n:
        # ⚠ 정답셋이 없다 — 「통과」가 아니라 **검산을 못 했다**는 뜻이다
        print(f"  ⏭ {corpus}: 포인터가 없어 검산할 정답셋이 없다 — 후보는 사람이 판정한다")
        return 0
    print(f"  검산 [{corpus}] — 이미 포인터인 조각 {n}개")
    print(f"    ✅ 같은 좌표 {ok} · ⚠ 못 찾음 {miss} · 🔴 다른 자리 {wrong}")
    for x in bad[:6]:
        print(f"      #{x[0]} {x[1]}+0x{x[2]:X}: {x[3]}")
    return 1 if (miss or wrong) else 0


def scan(corpus="battle"):
    d = entries(corpus)
    rows, stat = [], collections.Counter()
    for i, e in enumerate(d["entries"]):
        parts = e.get("parts") or ([e] if "ours" in e else [])
        prefer = next((p["f"] for p in parts if "f" in p), None)
        for j, pt in enumerate(parts):
            t = (pt.get("ours") or "").strip()
            if len(re.sub(r"\s+", "", t)) < MIN_LEN or not re.search(r"[가-힣]{2,}", t):
                continue
            got = find(t, prefer=prefer)
            stat["정발에 있다" if got else "정발에 없다"] += 1
            if got:
                rows.append(dict(entry=i, part=j, ours=t, hits=got[:3], prefer=prefer))
    print(f"  [{corpus}] `ours` 조각 — {dict(stat)}")
    os.makedirs(REVIEW_DIR, exist_ok=True)
    p = os.path.join(REVIEW_DIR, f"match_{corpus}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    if rows:
        print(f"  → {p} (⚠ 정발 문안 포함 — 커밋 금지)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("-c", "--corpus", default="battle", choices=CORPORA)
    ap.add_argument("--all", action="store_true", help="코퍼스 전부 — 검산 뒤 후보")
    ap.add_argument("--fuzzy", action="store_true", help="축자 대신 **닮은 자리** (판정용)")
    ap.add_argument("--pointerize", action="store_true", help="`ours` 를 정발 포인터로 가른다")
    ap.add_argument("--apply", action="store_true", help="미리보기 대신 실제로 쓴다")
    ap.add_argument("--file", help="기준 정발 파일 (예: OPENING.EXE)")
    a = ap.parse_args()
    names = CORPORA if a.all else (a.corpus,)
    rc = 0
    for c in names:
        if a.pointerize:
            rc |= pointerize(c, apply=a.apply, prefer=a.file)
            continue
        if a.fuzzy:
            rc |= fuzzy(c)
            continue
        rc |= verify(c)
        if not a.verify:
            rc |= scan(c)
    return rc


if __name__ == "__main__":
    sys.exit(main())
