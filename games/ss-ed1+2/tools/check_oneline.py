"""한 줄에 들어가는 문장이 두 줄로 쪼개졌나 — 번역 규칙 2-10 (굽는 줄 기준).

    python3 tools/check_oneline.py            # 개수 + 기준선 대조 (늘면 종료코드 1)
    python3 tools/check_oneline.py --show 20  # 표본
    python3 tools/check_oneline.py --freeze   # 기준선을 지금 값으로 (줄었을 때만)

## 두 영역

- **메시지 창**(`script/system.json`, 기계어 `msgwrap` 모델) — 이름·수·병기(`%s` `%d` `은(는)`)가 낀 문장은 폭이 런타임에 정해진다.
  고정 폭 문장만 실패로 센다(0 이어야 한다). 가변 폭은 **보고 전용**(이름이 짧으면 한 줄에 들어갈 수 있는 문장 수).
  보상 문구(`경험치 N, / M Gold를…`)는 조각마다 따로 찍히는 **엔진 조립 한계**라 여기서 못 본다.
- **씬 대사 창**(조판한 결과) — 한 쪽 안에서 문장 하나가 두 줄 이상에 걸치는데 혼자 한 줄(14.0칸)에 들어간다.
  조판기가 문장 경계 앞에서 새 줄을 시작하게 고쳤고(`linerules.clause_split` — 문장 경계는 짧은 앞 줄 가드를 안 탄다),
  남은 것은 줄 수를 늘려야 하거나 원문 줄 구조를 지키는 자리라 기준선(래칫)으로 둔다.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_wrap_rules as C
import common
import msgwrap
import patch_scn
import typeset_scn as T

_END = re.compile(r"[.!?…][」』)\"']*$")
_COLOR = re.compile(r"%c")


def baked_lines(kr):
    """메시지 조각 → 기계어가 굽는 글자 줄들(개행·공백 위치까지). 되짚기가 깨지면 None."""
    s = (C._NAME + kr) if kr.startswith(C._LEAD) else kr
    units = C._msg_units(s)
    src = b"".join(b for b, _t in units)
    got = msgwrap.wrap(src)
    body = [u for u in units if u[1] not in C._WS]
    txt, pos, k = [], 0, 0
    while pos < len(got) and k < len(body):
        c = got[pos]
        if c in (msgwrap.NL, msgwrap.SP):
            txt.append("\n" if c == msgwrap.NL else " ")
            pos += 1
            continue
        b, t = body[k]
        if got[pos : pos + len(b)] != b:
            return None
        txt.append(t)
        pos += len(b)
        k += 1
    return "".join(txt).split("\n"), units


_VAR = re.compile(r"%[sd]|은\(는\)|이\(가\)|을\(를\)|과\(와\)")
_PLATE = re.compile(r"^(%c[^%\n]*%c)\n")
_SPLIT = re.compile(r"(?<=[.!?…])[」』)\"']*(?=[ \n]|$)")


def _w(text):
    """굽는 바이트 폭 — `%c` 는 폭 없음."""
    return sum(len(b) for b, t in C._msg_units(text) if t != "%c")


def _min_w(text):
    """가장 짧은 런타임 값(이름 두 글자 · 수 한 자리 · 병기 한 글자)으로 잰 폭."""
    t = text.replace("%c", "").replace("%d", "0").replace("%s", "가나").replace("세리오스", "가나")
    t = _VAR.sub("는", t)
    return sum(1 if ord(c) < 128 else 2 for c in t)


def sentences(kr):
    """메시지 조각 → `[(문장 글자, 줄 수, 이름·병기 같은 가변 폭이 낀가)]` — 굽는 줄 기준."""
    got = baked_lines(kr)
    if got is None:
        return []
    flat = "\n".join(got[0])
    flat = _PLATE.sub("", flat)  # 화자 이름판은 문장이 아니다
    out, buf = [], ""
    for ch in flat:
        buf += ch
        if ch in "\n ":
            continue
    # 문장 자르기 — 끝 부호 뒤 공백/개행에서
    pieces, cur = [], ""
    i = 0
    while i < len(flat):
        cur += flat[i]
        if flat[i] in ".!?…":
            j = i + 1
            while j < len(flat) and flat[j] in "」』)\"'":
                cur += flat[j]
                j += 1
            if j >= len(flat) or flat[j] in " \n":
                pieces.append(cur)
                cur = ""
                i = j
                while i < len(flat) and flat[i] in " \n":
                    i += 1
                continue
            i = j
            continue
        i += 1
    if cur.strip():
        pieces.append(cur)
    for sp in pieces:
        rows = sp.count("\n") + 1 if "\n" in sp.strip("\n") else 1
        # 줄 안 공백으로 이어진 꼴: 위에서 이미 줄 경계를 개행으로 남겼다
        one = re.sub(r" *\n *", " ", sp.strip("\n ")).strip()
        out.append((one, rows if "\n" in sp.strip("\n ") else 1, bool(_VAR.search(sp))))
    return out


def scan():
    """`(조각 수, 고칠 것 [(열쇠, 원문, 문장)], 가변 폭이라 남기는 것)`."""
    lines = common.sys_lines()
    hits, var = [], []
    for h, kr in lines.items():
        for one, rows, isvar in sentences(kr):
            if rows < 2:
                continue
            if isvar:  # 가장 짧은 이름·수일 때 한 줄에 들어갈 문장 — 런타임 값에 달렸다
                if _min_w(one) <= msgwrap.LIMIT:
                    var.append((h, kr, one))
            elif _w(one) <= msgwrap.LIMIT:
                hits.append((h, kr, one))
    return len(lines), hits, var


BASELINE = os.path.join(common.GAME_DIR, "oneline_baseline.json")
_PIECE = re.compile(r"[.!?…][」』)\"']*(?=[ \n]|$)")


def page_sentences(page):
    """쪽(조판된 줄 목록) → 두 줄 이상에 걸친 문장 중 혼자 한 줄에 들어가는 것 `[(문장, 쪽 전문)]`."""
    flat = "\n".join(page)
    out, cur, i = [], "", 0
    while i < len(flat):
        cur += flat[i]
        if flat[i] in ".!?…":
            j = i + 1
            while j < len(flat) and flat[j] in "」』)\"'":
                cur += flat[j]
                j += 1
            if j >= len(flat) or flat[j] in " \n":
                out.append(cur)
                cur, i = "", j
                while i < len(flat) and flat[i] in " \n":
                    i += 1
                continue
            i = j
            continue
        i += 1
    if cur.strip():
        out.append(cur)
    hits = []
    for sp in out:
        st = sp.strip("\n ")
        if "\n" in st:
            one = re.sub(r" *\n *", " ", st)
            if T.width(one) <= T.COLS:
                hits.append((one, flat))
    return hits


def built_blocks():
    """씬 대사 창 블록마다 `(파일#오프셋, 조판된 문안)` — 다른 조판 게이트(`check_comma` 등)가 같이 쓴다."""
    canon = patch_scn.load_canon(quiet=True)
    _f, mm = common.open_image()
    canon = patch_scn.augment_names(canon, mm)
    try:
        for path in (p for p, _l, _s in common.iso_files(mm) if patch_scn.SCN_RE.match(p)):
            got = patch_scn.load(path)
            if not got or not patch_scn.DIALOG_RE.match(path):
                continue
            _base, entries = got
            sites = patch_scn.sites_for(path)
            fn = path.split("/")[-1]
            for e in entries:
                off = int(e["file_offset"], 16)
                built = patch_scn.canon_of(canon, e.get("text", ""), sites.get(off), path=path, off=off)
                if built:
                    yield f"{fn}#{off:#x}", built
    finally:
        mm.close()
        _f.close()


def scan_scene():
    """`(블록 수, [(파일#오프셋, 문장, 쪽)])` — 씬 대사 창."""
    hits, n = [], 0
    for tag, built in built_blocks():
        n += 1
        fn, _h, off = tag.partition("#")
        if "\u2028" in (patch_scn._scn_at("/BIN/" + fn, int(off, 16)) or ""):
            continue  # 🔴 마스터 승인 하드 개행 자리(`scn_at` U+2028 — ED1SCN32 0x2864)는 일부러 두 줄이다
        segs, groups = T.line_groups(built)
        for g in groups:
            for pg in "%c".join(segs[i] for i in g).split("\x08"):
                ls = [ln for ln in T.measure(pg).split("\n") if ln.strip()]
                if len(ls) >= 2:
                    hits += [(tag, one, flat) for one, flat in page_sentences(ls)]
    return n, hits


def main():
    n, hits, var = scan()
    ns, sc = scan_scene()
    show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 0
    cur = {"메시지(고정 폭)": len(hits), "씬 대사": len(sc)}
    print(
        f"  한 줄 문장 2-10 [메시지 {n:,} · 씬 {ns:,}] — 메시지 고정 폭 {len(hits)}"
        f" · 씬 {len(sc)} (보고: 메시지 가변 폭이라 남김 {len(var)})"
    )
    for h, kr, one in hits[:show]:
        print(f"      [메시지] {h[:6]} {kr!r} → {one!r}")
    for tag, one, flat in sc[:show]:
        print(f"      [씬] {tag}: {one!r}  ← {flat!r}")
    if "--freeze" in sys.argv:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"  ✍ 기준선 갱신 {cur}")
        return 0
    try:
        with open(BASELINE, encoding="utf-8") as f:
            base = json.load(f)
    except OSError:
        print("  ⚠ 기준선 없음 — `--freeze` 로 만든다 (안 쟀다는 통과가 아니다)")
        return 1
    worse = {k: (base.get(k, 0), v) for k, v in cur.items() if v > base.get(k, 0)}
    if worse:
        print("  🔴 기준선보다 늘었다 — " + " · ".join(f"{k} {a}→{b}" for k, (a, b) in worse.items()))
        return 1
    if any(v < base.get(k, 0) for k, v in cur.items()):
        print("  ✅ 기준선 이하 (줄었다) — `--freeze` 로 내린다")
    else:
        print("  ✅ 한 줄 문장 — 기준선과 같다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
