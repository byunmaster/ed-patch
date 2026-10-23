"""짝 경계 검사 — `data/align_map.json`(PCE 줄 ↔ PS1 블록 구간)이 **원문 줄의 문장과 맞는가**를 기계로 전수 본다(관리자 10-20, style 세션 「덧붙음·누락」 실증).

    python3 align_check.py            # 보고 — 고칠 곳(덧붙음·중복·구간 연장)과 남는 누락
    python3 align_check.py --apply    # 짝 정본을 고친다(결정적) — 고친 목록은 stdout
    python3 align_check.py --gate     # 게이트: 고칠 곳이 있거나 알려진 누락(`data/align_missing.tsv`) 밖 누락이 있으면 실패

왜: `align.best_span` 은 PCE 줄 전체와 **이어진 PS1 블록 구간**의 유사도(≥0.9)로 짝을 골라, 짧은 블록 하나가 끼거나 빠져도 문턱을 넘는다.
그 결과 PS1 쪽 이웃 블록이 딸려 와 ① 시스템 안내(「…를 건넸습니다」 · 「…가 동료가 되었습니다」)가 남의 대사 앞에 붙고 ② PS1 의 변형 대사 둘이 한 줄에 겹쳐 같은 말이 두 번 나오고
③ 구간이 모자라 원문 끝 문장이 빠졌다. 문안은 PS1 에서 오므로 줄마다 고치기 전에 **짝 경계**를 바로잡는다.

판정(블록마다 PCE 줄 본문 T 와 **독립으로** 맞대어 3자↑ 공통 덩이만 센다 — 한 글자씩 흩어진 일치는 무시):
  · 덧붙음 = 블록 본문의 절반 미만이 T 에 있다(시스템 안내 블록은 본문이 비고 화자 칸에 글이 든다 — 그 글을 본문으로 본다)
  · 중복 = 다른 블록과 T 의 같은 자리를 절반↑ 겹쳐 맞춘다(PS1 변형 대사) — 더 많이 맞춘 쪽만 남긴다
  · 구간 연장 = 같은 씬의 앞·뒤 이웃 블록이 T 의 **아직 못 맞춘 자리**를 새로 4자↑ 맞추고 블록의 6할↑이 T 에 있으면 구간에 넣는다
  · 누락 = 고친 구간으로도 T 에 못 맞춘 글자(문장 부호 제외)가 6자↑
"""

import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import align
import common
import dialogue
import package

MAP = common.GAME_DIR / "data" / "align_map.json"
PS1_KR = common.ROOT / "games" / "ps1-ed1+2" / "script"
KNOWN = common.GAME_DIR / "data" / "align_missing.tsv"
MIN_RUN = 3  # 공통 덩이 최소 길이
KEEP = 0.5  # 블록 본문이 T 에 들어 있어야 하는 비율
DUP = 0.5  # 둘이 T 의 같은 자리를 겹치는 비율(작은 쪽 기준)
EXT_GAIN = 4  # 구간 연장이 새로 맞춰야 하는 T 글자 수
EXT_FRAC = 0.6  # 연장 블록의 본문이 T 에 들어 있어야 하는 비율
MISS = 4  # 못 맞춘 글자가 이만큼↑이면 누락(「覚悟しろ」 4자 — 끝 문장 하나가 통째로 빠진 것까지)
EXT_BACK, EXT_FWD = 2, 3
KEEP_SENT = 0.3  # 문장 단위는 더 너그럽게 — 호칭만 겹쳐도(「バーバラさま」) 같은 문장이다(자르면 호칭이 사라진다)
DROP_MIN = 6  # 잘라 낼 문장의 최소 글자 수
PARTIAL = 8  # 블록 안 미충족이 이만큼↑이면 부분 겹침(문장 부호로 못 가른다 — 문안을 직접 쓴다)


def load():
    ps1 = align.load_ps1()
    import re

    clean = lambda t: re.sub(r"\\x[0-9A-Fa-f]{2}|[·･]", "", t)  # noqa: E731 — PS1 덤프의 값 자리표(`\\x21\\x21` = 느낌표 둘 · `\\x25\\x73` = 이름)는 글이 아니다
    by = {(b["scn"], b["id"]): dict(b, n=clean(b["n"] or align.norm(b["spk"]))) for b in ps1}  # 시스템 안내 블록은 본문이 비고 화자 칸에 글이 있다
    kr = {n: json.loads((PS1_KR / f"ED2SCN{n}.json").read_text(encoding="utf-8")) for n in range(1, 14)}
    for scn in range(1, 14):
        doc = json.loads((align.SCN_JP / f"ED2SCN{scn}.json").read_text(encoding="utf-8"))
        for e in doc["entries"]:
            k = (scn, e["entry_id"])
            if e.get("kind") == "block" and k in by:
                by[k]["jp_sents"] = jp_sentences(e["text"])
                by[k]["kr_sents"] = dialogue.kr_sentences(kr[scn].get(str(e["entry_id"]), {}).get("t") or "")
    order: dict[int, list] = {}
    for b in ps1:
        order.setdefault(b["scn"], []).append((b["scn"], b["id"]))
    pos = {k: (b["scn"], i) for scn, lst in order.items() for i, k in enumerate(lst) for b in [by[k]]}
    return by, order, pos


def jp_sentences(raw: str) -> list[str]:
    """PS1 일문 블록 → 문장 목록(`。！？` 뒤에서 끊는다). 화자 칸·제어는 뺀다."""
    import re

    m = re.match(r"\{c\}([^{]*)\{c\}(.*)", raw, re.S)
    body = m.group(2) if m and m.group(2).replace("{c}", "").replace("{n}", "").strip() else raw
    body = re.sub(r"\{[^}]*\}|[\s\u3000]", "", body)
    return [x for x in re.split(r"(?<=[。！？])", body) if x]


def hit(T: str, blk: str) -> set[int]:
    """T 의 어느 글자들이 블록과 3자↑ 덩이로 맞나."""
    sm = difflib.SequenceMatcher(None, T, blk, autojunk=False)
    out: set[int] = set()
    for a, _b, n in sm.get_matching_blocks():
        if n >= MIN_RUN:
            out.update(range(a, a + n))
    return out


def frac(T: str, blk: str, run: int = MIN_RUN) -> float:
    if not blk:
        return 0.0
    sm = difflib.SequenceMatcher(None, T, blk, autojunk=False)
    return sum(n for _a, _b, n in sm.get_matching_blocks() if n >= run) / len(blk)


def refine(T: str, refs: list, by, order, pos):
    """(새 refs, 사유 목록, 못 맞춘 글자 수)."""
    why = []
    cur = [tuple(r) for r in refs]
    # 1. 구간 연장 — 앞·뒤 이웃 블록
    if cur:
        scn = cur[0][0]
        lst = order[scn]
        covered: set[int] = set()
        for r in cur:
            covered |= hit(T, by[r]["n"])
        for _ in range(EXT_BACK + EXT_FWD):
            i0, i1 = pos[cur[0]][1], pos[cur[-1]][1]
            cands = []
            if i1 + 1 < len(lst) and i1 + 1 - i0 < 6:
                cands.append(lst[i1 + 1])
            if i0 - 1 >= 0 and i1 - i0 < 6:
                cands.append(lst[i0 - 1])
            took = False
            for c in cands:
                h = hit(T, by[c]["n"])
                if len(h - covered) >= EXT_GAIN and frac(T, by[c]["n"]) >= EXT_FRAC and len(T) - len(covered) >= EXT_GAIN:
                    cur = cur + [c] if pos[c][1] > i1 else [c] + cur
                    covered |= h
                    why.append(f"연장 {c[1]}")
                    took = True
                    break
            if not took:
                break
    # 2. 덧붙음 · 중복
    hits = {r: hit(T, by[r]["n"]) for r in cur}
    keep = []
    for r in cur:
        if frac(T, by[r]["n"], 2 if len(by[r]["n"]) <= 4 else MIN_RUN) < KEEP:  # 4자↓ 블록(「行く？」 메아리 따위)은 2자 덩이로 본다 — 3자 덩이로 재면 글이 짧아 항상 「덧붙음」이 된다(10-20 style 898:23:56)
            why.append(f"덧붙음 {r[1]}")
        else:
            keep.append(r)
    kept: list = []
    seen: set[int] = set()
    for r in sorted(keep, key=lambda r: (-len(hits[r]), keep.index(r))):
        mine = hits[r]
        if mine and len(mine & seen) / len(mine) > DUP:
            why.append(f"중복 {r[1]}")
            continue
        kept.append(r)
        seen |= mine
    out = [r for r in cur if r in set(kept)]
    # 3. 블록 안 문장 — 앞·뒤 문장이 통째로 PCE 줄에 없으면(PS1 쪽이 이웃 대사까지 한 블록으로 묶은 것) 그 문장만 잘라 낸다
    sliced = []
    partial = []
    for r in out:
        b = by[r]
        js, ks = b.get("jp_sents") or [], b.get("kr_sents") or []
        n = len(js)
        ok = [(frac(T, align.norm(x)) >= KEEP_SENT or frac(T, align.norm(x), 2) >= 0.6) if len(align.norm(x)) >= 2 else None for x in js]  # 3자 덩이로 3할↑ 이거나 2자 덩이로 6할↑(PCE 글에 깨진 글자가 끼어도 같은 문장으로 본다)
        idx = [i for i, v in enumerate(ok) if v]
        if idx:  # 맨 앞·뒤의 글자 없는 문장(감탄사 한 글자 따위 — 판정 없음)은 가장자리로 안 센다
            lo, hi = idx[0], idx[-1]
            while lo > 0 and ok[lo - 1] is None:
                lo -= 1
            while hi < n - 1 and ok[hi + 1] is None:
                hi += 1
            idx = [lo, hi] if (lo, hi) != (idx[0], idx[-1]) else idx
        if not ks:
            sliced.append(list(r))
            continue
        drop_ok = all(len(align.norm(x)) >= DROP_MIN for i, x in enumerate(js) if idx and not idx[0] <= i <= idx[-1])  # 짧은 문장(「だね。」 — 값 자리표 뒤에 붙는 꼬리)은 본문에 변수가 낀 줄에서 못 맞춘 것일 수 있어 안 자른다
        if n >= 2 and drop_ok and idx and (idx[0] > 0 or idx[-1] < n - 1) and len(ks) == n and all(ok[i] for i in range(idx[0], idx[-1] + 1) if ok[i] is not None):
            a_, b_ = idx[0], idx[-1] + 1
            why.append(f"문장 {r[1]}[{a_}:{b_}]")
            hits[r] = hit(T, "".join(align.norm(x) for x in js[a_:b_]))
            sliced.append([*r, a_, b_])
            continue
        if n >= 2 and drop_ok and idx and (idx[0] > 0 or idx[-1] < n - 1):
            partial.append(f"{r[1]}(문장 수 {n}≠한글 {len(ks)})")
        sliced.append(list(r))
        # 문장 안의 긴 미충족(구 단위 이음 — 문장 부호가 없어 못 가른다)
        sm = difflib.SequenceMatcher(None, T, b["n"], autojunk=False)
        cov2 = set()
        for a2, b2, k2 in sm.get_matching_blocks():
            if k2 >= MIN_RUN:
                cov2.update(range(b2, b2 + k2))
        run = best = 0
        for i in range(len(b["n"])):
            run = 0 if i in cov2 else run + 1
            best = max(best, run)
        if best >= PARTIAL and n < 2:
            partial.append(f"{r[1]}(미충족 {best}자)")
    out = sliced
    covered = set()
    for r in out:
        covered |= hits[tuple(r[:2])]
    punct_free = sum(1 for i in range(len(T)) if i not in covered)
    return out, why, punct_free, partial


def entries():
    mp = json.loads(MAP.read_text(encoding="utf-8"))
    pk: dict = {}
    for rel, ch, li, refs in mp:
        if rel not in pk:
            po = bytes(common.track_data(rel, 128))
            pk[rel] = (po, dict(package.chunks(po)), package.msg_table(po)[1])
        po, chs, tab = pk[rel]
        d = package.decode_chunk(po, ch, chs[ch])[0].split(b"\x00")
        msg = tab.index(ch)
        yield rel, ch, msg, li, refs, body_text(d[li])


def body_text(line: bytes) -> str:
    """줄의 **본문** 일본어(정규화) — 줄 안 어디에 있든 화자 머리(`16 … 14`)는 뺀다(한 줄에 말이 여럿인 줄의 둘째 화자 이름이 「못 맞춘 글자」로 새지 않게)."""
    import re

    import jptext

    j = jptext.decode(line)
    j = re.sub(r"\{16\}.*?\{14\}", "", j, flags=re.S)
    j = j.replace("｜", "").replace("|", "")
    return align.norm(j)


def known() -> set[str]:
    if not KNOWN.exists():
        return set()
    return {ln.split("\t")[0] for ln in KNOWN.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")}


def run():
    """(고칠 곳, 누락·부분 겹침 — 문안을 직접 써야 하는 것, 새 짝 정본). `own`(우리가 쓴 문안)이 있는 줄은 PS1 짝 대신 그 문안이 쓰이므로 누락·부분은 안 센다."""
    by, order, pos = load()
    own = dialogue.own()
    fixes, finds, new_map = [], [], []
    for rel, ch, msg, li, refs, T in entries():
        new, why, miss, partial = refine(T, [r[:2] for r in refs], by, order, pos)
        key = f"{rel}:{msg}:{li}"
        if new != [list(r) for r in refs]:
            fixes.append((key, refs, new, why))
        if f"{rel}:{ch}:{li}" not in own:
            if miss >= MISS:
                finds.append((key, f"누락 {miss}자"))
            for x in partial:
                finds.append((key, f"부분 {x}"))
        new_map.append([rel, ch, li, new])
    return fixes, finds, new_map


def main() -> int:
    a = sys.argv[1:]
    fixes, finds, new_map = run()
    kn = known()
    if "--apply" in a:
        keep = [r for r in new_map if r[3]]  # 짝이 다 지워진 줄은 PS1 문안이 없는 줄 — 짝 정본에서 뺀다
        MAP.write_text(json.dumps(keep, separators=(",", ":")), encoding="utf-8")
        for k, old, new, why in fixes:
            print(f"{k}\t{[r[1] for r in old]} → {[r[1:] if len(r) > 2 else r[1] for r in new]}\t{' '.join(why)}")
        print(f"고침 {len(fixes)}줄 · 짝 없어진 줄 {len(new_map) - len(keep)}", file=sys.stderr)
        return 0
    for k, old, new, why in fixes:
        print(f"고칠 곳 {k}\t{[r[1] for r in old]} → {[r[1:] if len(r) > 2 else r[1] for r in new]}\t{' '.join(why)}")
    keys = {k for k, _ in finds}
    bad = sorted(keys - kn)
    stale = sorted(kn - keys)
    for k, w in finds:
        print(f"{'알려짐' if k in kn else '문안 필요'} {k}\t{w}")
    print(f"짝 {len(new_map)}줄 · 고칠 곳 {len(fixes)} · 누락·부분 겹침 {len(keys)}줄(알려진 밖 {len(bad)}) · 낡은 알려진 목록 {len(stale)}")
    if "--gate" in a:
        if fixes or bad or stale:
            print("✖ 짝 경계 — `python3 tools/align_check.py --apply` 로 고치고, 남는 누락·부분 겹침은 `data/dialogue_ko` 에 문안을 쓰거나 `data/align_missing.tsv` 에 근거와 함께 올린다", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
