#!/usr/bin/env python3
"""세그먼트(=시점) ↔ 정발 사본 파일 **단조 배정**. 사본 오선택을 유사도 없이 구조로 푼다.

**왜.** 마을은 시점마다 대사가 조금씩 다르다. 정발은 그걸 **파일로 복제**해 두었고
(네리아 `T_040`~`T_044`, 루디아 성 `C_000`~`C_00H`), PS1 도 **지명 헤더 세그먼트**를
시점 수만큼 늘어놓는다. 그런데 사본끼리는 JP 가 같으니 유사도 배정기는 원리적으로 못 가른다
— 2장 QA 에서 유저가 짚은 오배정 대부분이 이것이었다(2026-08-04).

**푸는 열쇠는 순서다.** 양쪽 다 **스토리 순서로 정렬돼 있다** — PS1 은 SCN 안의 세그먼트
차례, 정발은 파일명 차례. 그러면 대응은 유사도 문제가 아니라 **단조 정렬(DP)** 문제가 된다.
실측으로 이미 대각선이 서 있다(2026-08-05, 현행 배정의 다수결):

    베르가 광산  #1~#5 → T_030 T_031 T_032 T_033 T_034     5/5
    론도 항구    #1~#4 → T_100 T_101 T_102 T_103           4/4
    랄파 요새    #1~#7 → T_110 … T_117                     7/7
    루디아 성    #7~#22 → C_000 … C_00H                   16/16
    네리아 항구  #1~#5 → T_040 T_041 ???                    2/5  ← 유저가 짚은 자리

⚠ **PS1 이 정발 시점 하나를 통째로 빼는 자리가 있다**(크루즈 세그먼트 8 : 정발 9 — T_023
누락). 그래서 "k번째끼리"가 아니라 **건너뜀을 허용하는 DP** 여야 한다.
⚠ 배정 결과는 **커밋되는 정본**(`segment_tables.json`)에 박는다. 빌드는 정본만 읽는다 —
제1원칙(빌드 결정성).

  python3 tools/past_segment_copy.py ED1SCN1              # 배정 제안 보기
  python3 tools/past_segment_copy.py ED1SCN1 --apply      # segment_tables.json 갱신
  python3 tools/past_segment_copy.py ED1SCN1 --retarget   # 정본에 맞춰 블록 배정을 옮긴다
"""

import bisect
import collections
import difflib
import json
import os
import re
import sys

os.environ.setdefault("LOCK_BYPASS", "1")

from align_map import scene_map
from common import MARKUP, OUT_DIR, REVIEW_DIR, ROOT
from scn_maps import _anchors, segments, table_maps

SEG_TABLES = os.path.join(ROOT, "segment_tables.json")
W_OVERRIDE = 4  # 사람이 확정한 오버라이드 표
W_ALIGN = 1  # 정렬기 무플래그 쌍 표(노이즈가 섞여 있다)
PIN_MIN = 6  # 확신 세그먼트 최소 표
PIN_SHARE = 0.6  # 확신 세그먼트 최소 점유율
HEAD = 10  # 머리글 비교 길이
HEAD_SIM = 0.45  # 머리글 최소 유사도 — 이보다 낮으면 사본 짝으로 안 본다
SIM = 0.62  # 사본 간 엔트리 대응 문턱 — 사본끼리는 어투만 달라 높게 나온다
# 마크업 한 벌은 **`common.MARKUP` 이 정본**이다 — 사본을 두면 조용히 갈린다
# (2026-08-29 통합: 여섯 파일 중 둘이 대문자 헥스만 봤다).
_STRIP = MARKUP
_NORM = re.compile(r"[\s.,!?~…·\-'\"]+")
_SCENES = tuple(range(1, 7))
# ⚠ 화자 태그는 **문안이 아니다.** 정발은 같은 대사를 파일마다 화자를 붙이거나 뺀 채 써 두는데
# (`T_028#6` 은 `{spk}농부{/spk}` 있고 `T_024#15` 는 없다), 화면의 이름판은 PS1 JP 가 정한다.
# 태그를 문안으로 세면 감사가 "글자가 다름"으로 오탐한다(46건 중 6건, 유저 지적 2026-08-06).
_SPK_TAG = re.compile(r"\{spk\}.*?\{/spk\}\{n\}?")


def top(c):
    """최다 득표 (테이블, 표). ⚠ `Counter.most_common` 은 동점에서 **삽입 순서**를 따른다 —
    빌드 결정성 원칙상 이름으로 못 박는다."""
    return min(c.items(), key=lambda kv: (-kv[1], kv[0]))


def norm(s):
    return _NORM.sub("", _STRIP.sub("", s))


def mapkey(s):
    """지명 정규화. ⚠ `work/derived/scn_maps/` 캐시는 지명 붙여쓰기(2026-08-04) **이전**
    이름으로 굳어 있어 `block_maps`(캐시)와 `segments`(즉석)의 이름이 어긋난다. 공백을
    떼어 양쪽을 같은 키로 본다 — 캐시를 지우면 정렬 풀이 흔들리므로 여기서 흡수한다."""
    return (s or "").replace(" ", "")


def seg_blocks(game, scn):
    """[(지명, [entry_id…])] — 지명 헤더 세그먼트 = 시점 하나."""
    segs = segments(game, scn)
    offs = [s[0] for s in segs]
    doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{game}SCN{scn}.json"), encoding="utf-8"))
    out = [(n, []) for _, n in segs]
    for e in doc["entries"]:
        k = bisect.bisect_right(offs, int(e["file_offset"], 16)) - 1
        if k >= 0:
            out[k][1].append(e["entry_id"])
    return out


def seg_keys(game, scn):
    """[(키, 지명, [eid…])] — 키는 `지명#i`(같은 지명 안에서의 등장 차례)."""
    seen = collections.Counter()
    out = []
    for mp, eids in seg_blocks(game, scn):
        mp = mapkey(mp)
        seen[mp] += 1
        out.append((f"{mp}#{seen[mp]}", mp, eids))
    return out


def table_pool(game):
    """{지명: {접두: [테이블…]}} — 학습된 테이블의 **파일명 접두**로 풀을 넓힌다.

    학습(`table_maps`)은 앵커가 닿은 테이블만 잡아 시점 사본을 통째로 빠뜨린다. 접두가
    같으면 같은 방이라는 게 정발 파일명 규약이므로(`T_04x`=네리아 · `C_00x`=루디아 성),
    학습된 하나를 씨앗 삼아 그 접두 전부를 후보로 올린다.
    """
    learned, exempt = table_maps(game)
    d = os.path.join(OUT_DIR, "dos_kr", game)
    allt = sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json") and not f.startswith("_"))
    seed = collections.defaultdict(set)
    for t, mp in learned.items():
        if not t:  # ⚠ 비운 블록 등에서 table 이 None 으로 온다(2026-08-12)
            continue
        if t.startswith(f"{game}/"):
            t = t.split("/", 1)[1]
        seed[mapkey(mp)].add(t[:4])
    out = {}
    for mp, prefixes in seed.items():
        out[mp] = {p: [t for t in allt if t.startswith(p)] for p in sorted(prefixes)}
    return out, exempt


def votes(game, scn):
    """{entry_id: {테이블: 가중치}} 를 합쳐 {세그먼트키: Counter(테이블)} 로."""
    ov = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8")).get(
        f"{game}SCN{scn}", {}
    )
    w = collections.defaultdict(collections.Counter)
    hard = {}
    for k, v in ov.items():
        if k.isdigit() and isinstance(v, dict) and "table" in v and not v.get("exclude"):
            hard[int(k)] = v["table"]
    for jid, tbl in _anchors(game, scn):
        w[jid][tbl] += W_OVERRIDE if hard.get(jid) == tbl else W_ALIGN
    return w


def _resolve_pins(pin):
    """확신 핀 열을 **순증**으로 다듬는다. 다듬을 수 없으면 False(=이 맵은 손대지 않는다).

    ⚠ **제자리와 역행은 성격이 다르다.**
    · 제자리(연속 두 세그먼트가 같은 파일을 확신) = **사본 번짐**이 굳은 자국이다.
      `past_recover_twins` 가 앞 세그먼트의 배정을 뒤로 복제해 놓은 것이라 **뒤쪽 핀을 푼다**
      (루디아 마을 실측: `#4`·`#5` 가 나란히 `T_013` 87%·72% → `#5` 를 풀면 DP 가
      `T_014`·`T_015` 로 대각선을 세운다. 안 풀면 마을 6세그먼트가 통째로 배정을 잃었다).
    · 역행 = 시점 순서가 아니라는 뜻이니 그 맵은 통째로 건너뛴다.
    파일이 세그먼트보다 적어 재사용이 정당한 자리(시련의 동굴 `D_122`)는 호출 전에 뺀다.
    """
    while True:
        ks = sorted(pin)
        for a, b in zip(ks, ks[1:], strict=False):
            if pin[a] > pin[b]:
                return False
            if pin[a] == pin[b]:
                del pin[b]
                break
        else:
            return True


def _monotone(n, m, score, reuse):
    """세그먼트 i ↔ 파일 j 를 **순서를 지키며** 배정. 파일 건너뜀 허용.

    `reuse` 면 같은 파일을 이어 쓸 수 있다(정발 사본이 세그먼트보다 적은 자리).
    `score(i, j)` 가 `-inf` 면 그 칸은 금지 — 확신 세그먼트를 못 박는 데 쓴다.
    """
    NEG = float("-inf")
    if not n or not m:
        return [None] * n
    dp = [[NEG] * m for _ in range(n)]
    bk = [[None] * m for _ in range(n)]
    for j in range(m):
        dp[0][j] = score(0, j)
    for i in range(1, n):
        for j in range(m):
            s = score(i, j)
            if s == NEG:
                continue
            best, arg = NEG, None
            for k in range(j + 1 if reuse else j):
                if dp[i - 1][k] > best:
                    best, arg = dp[i - 1][k], k
            if arg is None or best == NEG:
                continue
            dp[i][j] = best + s
            bk[i][j] = arg
    j = max(range(m), key=lambda j: dp[n - 1][j])
    if dp[n - 1][j] == NEG:
        return [None] * n
    out = [None] * n
    for i in range(n - 1, -1, -1):
        out[i] = j
        j = bk[i][j] if i else j
    return out


def propose(game, scn, drop=()):
    """[(세그먼트키, 지명, [eid…], 현행 다수, 제안)] — 단조 배정 제안.

    `drop` 에 든 세그먼트는 **표를 지운 채** 푼다 — 홀드아웃 검증용(구조만으로 맞히는가).
    """
    pool, exempt = table_pool(game)
    vt = votes(game, scn)
    rows = []
    bymap = collections.defaultdict(list)
    for key, mp, eids in seg_keys(game, scn):
        c = collections.Counter()
        for e in eids:
            for t, n in vt.get(e, {}).items():
                if t not in exempt:
                    c[t] += n
        bymap[mp].append((key, eids, collections.Counter() if key in drop else c))
        rows.append([key, mp, eids, c, None])
    idx = {r[0]: r for r in rows}

    for mp, items in bymap.items():
        groups = pool.get(mp) or {}
        if not groups:
            continue
        # 세그먼트를 접두 그룹에 배정한다(루디아는 마을 `T_01x` 뒤에 성 `C_00x` 가 온다).
        # 표가 없는 세그먼트는 **앞 세그먼트의 그룹**을 잇는다 — 세그먼트 순서가 곧 진행이라
        # 그룹이 중간에 왔다 갔다 하지 않는다.
        own = {}
        for key, _eids, c in items:
            cand = collections.Counter()
            for t, n in c.items():
                if not t:  # 비운 블록 등 — table 이 None
                    continue
                q = t.split("/", 1)[-1][:4]
                if q in groups:
                    cand[q] += n
            own[key] = top(cand)[0] if cand else None
        pref_of, last = {}, None
        for key, _e, _c in items:  # 앞에서 채우고
            last = own[key] or last
            pref_of[key] = last
        last = None
        for key, _e, _c in reversed(items):  # 뒤에서도 채운다(맨 앞 세그먼트용)
            last = own[key] or last
            pref_of[key] = pref_of[key] or last
        for p, files in groups.items():
            full = [f"{game}/{t}" for t in files]
            # ⚠ **이 풀 안에 표가 없는 세그먼트는 배정하지 않는다.** 근거 없이 자리만 채우면
            # DP 가 남는 파일을 뿌려 놓는다(엘아스타#3·리젤#4·세리스#4 실측 — 1블록짜리에
            # 엉뚱한 사본이 붙었다). 풀 밖 표(다른 맵 오배정)는 근거로 안 친다.
            sel = []
            for k, _e, c in items:
                if pref_of[k] != p:
                    continue
                cin = collections.Counter({t: n for t, n in c.items() if t in full})
                if cin or k in drop:  # drop = 홀드아웃 대상 — 표 없이 자리만 남긴다
                    sel.append((k, cin))
            if not sel:
                continue
            # 확신 세그먼트 = 한 파일이 표를 확실히 쥔 자리. 여기는 DP 가 못 건드린다.
            pin = {}
            for i, (_k, c) in enumerate(sel):
                if not c:
                    continue
                t, n = top(c)
                if n >= PIN_MIN and n / sum(c.values()) >= PIN_SHARE and t in full:
                    pin[i] = full.index(t)
            reuse = len(full) < len(sel)
            if not reuse and not _resolve_pins(pin):
                # ⚠ **역행이 있으면 시점 사본 구조가 아니다** — 손대면 멀쩡한 배정을 망친다.
                continue
            NEG = float("-inf")

            def score(i, j, sel=sel, full=full, pin=pin, NEG=NEG):
                if i in pin:
                    return 0 if pin[i] == j else NEG
                return sel[i][1].get(full[j], 0)

            got = _monotone(len(sel), len(full), score, reuse=reuse)
            for (k, _c), j in zip(sel, got, strict=True):
                idx[k][4] = full[j] if j is not None else None
    return rows


def _entries(table):
    game, name = table.split("/")
    p = os.path.join(OUT_DIR, "dos_kr", game, f"{name}.json")
    if not os.path.exists(p):
        return {}
    doc = json.load(open(p, encoding="utf-8"))
    # (정규화 본문, 화자, 원문) — 대응 판정은 정규화로, **변경 여부는 원문으로** 본다.
    # ⚠ 정규화는 공백·부호를 지우므로 그걸로 "문안 동일"을 판정하면 놓친다(jp445 실측:
    # 무해로 분류됐는데 확정 락이 위반을 잡았다).
    return {
        e["entry_id"]: (norm(e.get("text") or ""), e.get("speaker") or "", e.get("text") or "")
        for e in doc["entries"]
        if isinstance(e, dict) and e.get("kind") == "block"
    }


_cache = {}


def entries(table):
    if table not in _cache:
        _cache[table] = _entries(table)
    return _cache[table]


def copy_map(src, dst):
    """{src 엔트리: dst 엔트리} — 두 사본 파일의 **단조 대응표**.

    사본끼리는 같은 말을 어투만 달리한 것이고 **순서도 거의 보존된다**. 그래서 최선 짝을
    따로따로 고르지 않고(같은 자리에 둘이 몰린다) 순서를 지키는 DP 로 한 번에 맞춘다.
    """
    a = sorted(entries(src))
    b = sorted(entries(dst))
    A, B = entries(src), entries(dst)
    n, m = len(a), len(b)
    if not n or not m:
        return {}
    sim = [[0.0] * m for _ in range(n)]
    for i, ea in enumerate(a):
        ta, sa = A[ea][0], A[ea][1]
        if len(ta) < 6:
            continue
        for j, eb in enumerate(b):
            tb, sb = B[eb][0], B[eb][1]
            if len(tb) < 6:
                continue
            r = difflib.SequenceMatcher(None, ta, tb).ratio()
            if sa and sb:  # 화자가 같으면 밀어주고 다르면 깎는다(사본은 화자를 안 바꾼다)
                r += 0.06 if sa == sb else -0.10
            # ⚠ **머리글이 안 닮으면 짝이 아니다.** 사본은 같은 대사 자리라 첫 어절이
            # 갈려도(`오오 왕자님`↔`아니 왕자님`) 머리는 닮는다. 이 게이트가 없으면
            # **엔트리 분할이 다른 자리에서 꼬리만 보고 문다** — 네리아 밀매상 실측: 정발이
            # T_041 은 프롬프트+본문을 한 엔트리에, T_040 은 `#5`·`#7` 로 쪼개 놓아
            # `#5→#7`(꼬리 0.83)이 옳은 짝 `#5→#5`(0.27)를 이겼다. 1:2 분할은 1:1 대응표로
            # 표현할 수 없으니 **아예 짝을 안 짓고 넘긴다**(건너뜀으로 보고된다).
            if difflib.SequenceMatcher(None, ta[:HEAD], tb[:HEAD]).ratio() < HEAD_SIM:
                continue
            sim[i][j] = r
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            s = sim[i - 1][j - 1]
            dp[i][j] = max(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1] + (s if s >= SIM else 0.0))
    out, i, j = {}, n, m
    while i and j:
        if dp[i][j] == dp[i - 1][j]:
            i -= 1
        elif dp[i][j] == dp[i][j - 1]:
            j -= 1
        else:
            if sim[i - 1][j - 1] >= SIM:
                out[a[i - 1]] = b[j - 1]
            i -= 1
            j -= 1
    return out


def slice_text(raw, item):
    """체인 항목 하나가 실제로 뽑아 쓰는 조각 — `eid~변형#페이지.문장` 을 그대로 흉내낸다.

    ⚠ **감사는 이걸로 비교해야 한다.** 엔트리 전체를 비교하면 슬라이스를 쓰는 블록에서
    통째로 오탐이 난다(41건 중 33건이 슬라이스, 2026-08-06 유저 지적 jp607·jp627·jp1073 —
    렌더는 넷 다 같은데 감사만 다르다고 우겼다).
    """
    from reinsert_kr_pilot import _sentences

    base, _, rest = str(item).partition("#")
    _base, _, vi = base.partition("~")
    t = raw
    if vi and vi.isdigit():
        vs = t.split("\\x06")
        if int(vi) >= len(vs):
            return None
        t = vs[int(vi)]
    pi, _, si = rest.partition(".")
    if pi == "tail":
        return "tail"
    if pi:
        if not pi.isdigit() or int(pi) >= len(t.split("{p}")):
            return None
        t = t.split("{p}")[int(pi)]
    if si:
        sents = _sentences(t)
        lo, dash, hi = si.partition("-")
        if not lo.isdigit() or int(lo) >= len(sents):
            return None
        a = int(lo)
        b = (int(hi) + 1 if hi else len(sents)) if dash else a + 1
        t = "".join(sents[a:b])
    return t.strip()


def load_seg_tables():
    if os.path.exists(SEG_TABLES):
        return json.load(open(SEG_TABLES, encoding="utf-8"))
    return {}


def scene_map_doc(game, scenes=_SCENES):
    """씬 지도 — 어느 씬이 어디를 담고, 세그먼트마다 어느 **시점**인지. QA 단위를 잡는 문서.

    ⚠ 담는 건 **지명·정발 파일명·화자 라벨·개수**뿐이다. 문장은 한 글자도 안 들어간다
    (저작권 — 이 문서는 커밋된다).
    """
    import reinsert_kr_pilot as R
    from align_jp_kr import load_jp_scene

    out = [
        "# ED1 씬 지도 — 어느 씬이 어디까지인가",
        "",
        "**씬 파일 ≠ 장이다.** 한 씬은 한 지역 묶음을 담고, 그 안에 **같은 지명이 시점 수만큼**",
        "반복된다(재방문 상태). 그래서 씬 100% 는 그 장만 플레이해선 도달할 수 없다 —",
        "QA 는 씬이 아니라 **세그먼트(=시점)** 단위로 닫는 게 맞다.",
        "",
        "`시점 사본` 은 그 세그먼트가 쓰는 정발 파일이다(`segment_tables.json` 이 정본).",
        "`고유 화자` 는 **그 씬에서 이 세그먼트에만 나오는** 정발 화자 — 어느 대목인지 가려낸다.",
        "생성: `python3 tools/past_segment_copy.py --map > docs/scene-map.md`",
        "",
    ]
    seg = load_seg_tables()
    for scn in scenes:
        name = f"{game}SCN{scn}"
        rows = propose(game, scn)
        jp = {b["id"]: b for b in load_jp_scene(game, scn)}
        tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
        spk_of = {}
        for key, _mp, _eids, _c, _w in rows:
            t = seg.get(name, {}).get(key)
            spk_of[key] = {s for _e, (_n, s, _r) in entries(t).items() if s} if t else set()
        seen = collections.Counter(s for v in spk_of.values() for s in v)
        out += [
            f"## {name}",
            "",
            "| 세그먼트 | 시점 사본 | 블록 | 번역 | 고유 화자 |",
            "| -------- | --------- | ---- | ---- | --------- |",
        ]
        for key, _mp, eids, _c, _w in rows:
            body = [e for e in eids if (jp.get(e, {}).get("body") or "").strip()]
            if not body:
                continue
            done = sum(1 for e in body if e in tr)
            t = seg.get(name, {}).get(key)
            uniq = sorted(s for s in spk_of[key] if seen[s] == 1)
            out.append(
                f"| {key} | {t.split('/')[-1] if t else '—'} | {len(body)} | "
                f"{done}/{len(body)} | {', '.join(uniq[:6]) or '—'} |"
            )
        out.append("")
    return "\n".join(out)


def audit(game, scenes=_SCENES):
    """**전수 감사** — 블록이 자기 세그먼트의 시점 사본을 쓰고 있는가.

    유저 문제 제기(2026-08-05): "의미는 거의 같은데 텍스트가 미세하게 다른 게 있다. 이건
    정발 대조 아니면 잡기 힘들다." 맞다 — **인게임으로는 원리적으로 못 잡는다.** 어느 쪽을
    골랐든 자연스러운 한국어라 화면만 봐서는 틀린 줄 모른다.

    그런데 시점 사본 정본이 생기고 나면 **기계가 물을 수 있는 질문**이 된다. 셋으로 가른다:
      · 그 사본에 **대응 문장이 없다** → 세그먼트가 정발 파일 둘에 걸친 정당한 경우이거나
        진짜 오배정. 개수만으로는 못 가른다(판단 보류).
      · 대응 문장이 있고 **글자가 같다** → 어느 사본을 골랐든 결과가 같다. 무해.
      · 대응 문장이 있고 **글자가 다르다** → **시점 어긋남 의심.** 유저가 말한 그 증상이다.

    ⚠ 블록↔엔트리 **순서 단조성은 신호가 안 된다**(실측 24% 위반). PS1 은 NPC·메시지ID 순,
    정발은 스크립트 흐름 순이라 애초에 순서가 다르다 — 이 길로 좁히려던 시도는 버렸다.
    """
    seg = load_seg_tables()
    _pool, exempt = table_pool(game)
    tally, rows = collections.Counter(), []
    for scn in scenes:
        name = f"{game}SCN{scn}"
        base = scene_map(name)
        ov = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8")).get(
            name, {}
        )
        for key, _mp, eids, _c, _w in propose(game, scn):
            want = seg.get(name, {}).get(key)
            for e in eids:
                o = ov.get(str(e)) or {}
                if not isinstance(o, dict):
                    continue
                if "ours" in o or o.get("exclude"):
                    tally["우리 문안·제외"] += 1
                    continue
                # 상투 문구 통일(`unify_common_lines`)은 **일부러** 전 마을이 한 엔트리를
                # 공유한다 — 시점 사본이 아닌 게 정상이라 감사 대상이 아니다(유저 확정
                # 2026-08-05: "상점 관련 공통처리된 부분은 완료처리"). 안 빼면 오탐이 는다.
                # 유저가 "이대로 두자"고 정한 자리는 감사에서 뺀다. ⚠ 표식이 없으면 같은
                # 항목이 라운드마다 다시 올라와 목록을 못 믿게 된다(`--settled` 와 같은 이유).
                if "유저 확정 유지" in (o.get("note") or ""):
                    tally["🙆 유저 확정 유지"] += 1
                    continue
                # 감사에서 "현행이 맞다"고 판정한 자리 — **이유를 노트에 적어야** 다음 라운드에
                # 다시 안 올라온다. 세그먼트가 늘 옳은 건 아니다(화자 증거·표기 통일이
                # 세그먼트보다 강한 자리가 실재한다 — jp479·jp569·jp1016 실측 2026-08-06).
                if "감사 판정:" in (o.get("note") or ""):
                    tally["🙆 감사 판정 완료(현행 유지)"] += 1
                    continue
                if "unify_common_lines" in (o.get("note") or ""):
                    tally["🛒 상투 문구 공통(완료)"] += 1
                    continue
                # 시스템 문구 일원화(`past_sys_phrases`)도 **일부러** 한 엔트리를 공유한다 —
                # 세그먼트 밖을 가리키는 게 의도다. 안 빼면 감사가 10→53 으로 뛴다(2026-08-06,
                # 전부 `어느 것을/어느것을` 같은 표기 흔들림 — 통일이 없애려던 바로 그것).
                if "시스템 문구 일원화" in (o.get("note") or ""):
                    tally["🛒 시스템 문구 일원화(완료)"] += 1
                    continue
                src = o.get("table") or (base.get(e) or {}).get("table")
                ent = o.get("entry_id")
                if ent is None:
                    ent = (base.get(e) or {}).get("entry_id")
                if not src or ent is None:
                    continue
                if not want:
                    tally["세그먼트 배정 없음"] += 1
                elif src in exempt:
                    tally["맵무관(상점 공통)"] += 1
                elif src == want:
                    tally["✅ 자기 시점 사본"] += 1
                else:
                    tgt = copy_map(src, want).get(ent)
                    a = entries(src).get(ent, ("", "", ""))[2]
                    b = entries(want).get(tgt, ("", "", ""))[2] if tgt is not None else None
                    # ⚠ 슬라이스를 쓰는 블록은 **뽑아 쓰는 조각끼리** 비교한다(위 `slice_text`).
                    ch = o.get("chain")
                    if tgt is not None and ch:
                        sa = [slice_text(a, x) for x in ch]
                        nb = _remap_chain(ch, ent, tgt, b)
                        sb = [slice_text(b, x) for x in nb] if nb else None
                        if sb is None or None in sa or None in sb:
                            # ⚠ 슬라이스를 못 옮긴다 = **그 사본에 그 자리가 없다**. 문장이
                            # 다른 게 아니라 아예 없는 것이라 `판단 보류` 다(jp416 실측
                            # 2026-08-06: `T_024#2` 변형2 에 `그거 유감이군요` 가 없다).
                            tally["그 사본에 대응 문장 없음(판단 보류)"] += 1
                            continue
                        a, b = "".join(sa), "".join(sb)
                    if tgt is None:
                        tally["그 사본에 대응 문장 없음(판단 보류)"] += 1
                    elif _SPK_TAG.sub("", a).strip() == _SPK_TAG.sub("", b).strip():
                        tally["사본은 달라도 문장이 같음(무해)"] += 1
                    else:
                        tally["⚠ 시점 어긋남 의심"] += 1
                        # ⚠ 이전 라운드에서 이미 본 자리인지 알려 준다 — 노트에 유저 QA
                        # 기록이 있으면 표시(유저 되물음 2026-08-06 jp1259 "이미 수정한 걸로
                        # 알고 있어" — 노트에 `유저 QA 2026-07-31` 이 적혀 있었다).
                        seen_note = ""
                        m_qa = re.search(r"유저 (?:QA|확정)[^)|]*", o.get("note") or "")
                        if m_qa:
                            seen_note = m_qa.group(0).strip()
                        rows.append((name, key, e, src, ent, want, tgt, a, b, seen_note))
    return tally, rows


def checklist(game, scenes=_SCENES):
    """플레이 대조용 체크리스트 — **세그먼트(=시점) 순서대로** 무엇을 봐야 하는지.

    유저 방침(2026-08-05): "순서대로 대조하면서 플레이한다." 그때 **전수 대조는 낭비**다 —
    2,959블록 중 손댈 이유가 있는 자리는 도구가 이미 안다.

    ⚠ **담는 건 "남은 일"뿐이다**(유저 지적 2026-08-06: "완료는 문서에서 빠져야 하는 것
    아닌지?"). 한때 "이번에 문안이 바뀐 것"도 같이 실었는데, 그건 **완료분**이라 확인하고
    나면 지워질 길이 없어 목록이 계속 부풀었다(status.md 의 "현재 상태 + 남은 일만" 원칙과도
    어긋난다). 완료분 전/후 대조는 `segment_copy_REVIEW.md` 가 따로 담는다.
      ① 시점 어긋남 의심(`--audit`) — 고치면 자동으로 빠진다 · ② 미번역
    ⚠ 정발 문안이 들어가므로 REVIEW_DIR(gitignore)로만 나간다.
    """
    from todo_untranslated import pending

    seg = load_seg_tables()
    _t, arows = audit(game, scenes)
    sus = collections.defaultdict(list)
    for nm, key, e, src, ent, want, tgt, a, b, qa in arows:
        sus[(nm, key)].append((e, src.split("/")[-1], ent, want.split("/")[-1], tgt, a, b, qa))
    out = [
        "# 플레이 대조 체크리스트 — 세그먼트(시점) 순서",
        "",
        "**전수 대조하지 말 것.** 아래 표시된 자리만 정발과 맞춰 보면 된다.",
        "🔴 **정발 대조 필요** — 자기 시점 사본과 글자가 다르다. 화면만 봐선 못 잡는 클래스.",
        "🇯🇵 **미번역** — 아직 일본어. 화면에 바로 보인다.",
        "",
        "**고치면 다음 생성 때 자동으로 빠진다** — 완료분은 여기 안 남는다.",
        "",
    ]
    for scn in scenes:
        name = f"{game}SCN{scn}"
        todo = collections.Counter()
        segof = {}
        rows = propose(game, scn)
        for key, _mp, eids, _c, _w in rows:
            for e in eids:
                segof[e] = key
        for e, _mp, _spk, _body in pending(game, scn):
            todo[segof.get(e)] += 1
        out.append(f"\n---\n\n# {name}\n")
        for key, _mp, _eids, _c, _w in rows:
            S_ = sus.get((name, key), [])
            T_ = todo.get(key, 0)
            if not (S_ or T_):
                continue
            t = seg.get(name, {}).get(key)
            tags = []
            if S_:
                tags.append(f"🔴 대조 {len(S_)}")
            if T_:
                tags.append(f"🇯🇵 미번역 {T_}")
            out.append(f"\n## {key}  ({t.split('/')[-1] if t else '—'})   {' · '.join(tags)}\n")
            for e, s0, n0, t1, n1, a, b, qa in sorted(S_):
                tag = f"   ⟨이전 {qa}⟩" if qa else ""
                out.append(f"\n🔴 jp{e}  {s0}#{n0} → {t1}#{n1}{tag}\n- {a[:150]}\n+ {b[:150]}")
        out.append("")
    return "\n".join(out)


def main():
    game = "ED1"
    if "--checklist" in sys.argv:
        os.makedirs(REVIEW_DIR, exist_ok=True)
        p = os.path.join(REVIEW_DIR, "PLAYTHROUGH.md")
        open(p, "w", encoding="utf-8").write(checklist(game))
        print(f"  → {p}")
        return 0
    if "--audit" in sys.argv:
        tally, rows = audit(game)
        for k, v in tally.most_common():
            print(f"  {v:6d}  {k}")
        os.makedirs(REVIEW_DIR, exist_ok=True)
        p = os.path.join(REVIEW_DIR, "segment_copy_AUDIT.md")
        by = collections.Counter(f"{n}/{k}" for n, k, *_ in rows)
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# 시점 어긋남 의심 {len(rows)}건 — 자기 세그먼트의 사본과 글자가 다르다\n\n")
            f.write(
                "`-` = **지금 화면에 나오는 문안** · `+` = **제안**(그 세그먼트의 시점 사본). 둘 다 정발이다.\n"
            )
            for nm_key, _n in by.most_common():
                f.write(f"\n## {nm_key}\n")
                for nm, key, e, s0, n0, t1, n1, a, b, qa in rows:
                    if f"{nm}/{key}" != nm_key:
                        continue
                    tag = f"   ⟨이전 {qa}⟩" if qa else ""
                    f.write(f"\njp{e}  {s0.split('/')[-1]}#{n0} → {t1.split('/')[-1]}#{n1}{tag}\n")
                    f.write(f"- {a[:170]}\n+ {b[:170]}\n")
        print(f"  → {p}")
        return 0
    if "--map" in sys.argv:
        print(scene_map_doc(game))
        return 0
    scn_name = next((a for a in sys.argv[1:] if a.startswith("ED")), "ED1SCN1")
    scn = int(scn_name.split("SCN")[1])
    rows = propose(game, scn)

    if "--retarget" in sys.argv:
        return retarget(game, scn, scn_name)

    changed = 0
    print(f"{scn_name}: 세그먼트 {len(rows)}")
    for key, _mp, eids, c, want in rows:
        cur = top(c)[0] if c else None
        mark = " " if cur == want or want is None else "*"
        if mark == "*":
            changed += 1
        vote = " ".join(f"{t.split('/')[-1]}:{n}" for t, n in c.most_common(4))
        w = want.split("/")[-1] if want else "—"
        print(f" {mark}{key:16s} {len(eids):4d}블록 → {w:6s}  현행 [{vote}]")
    print(f"  현행 다수와 다른 세그먼트 {changed}건")

    if "--apply" in sys.argv:
        doc = load_seg_tables()
        sc = doc.setdefault(scn_name, {})
        for key, _mp, _eids, _c, want in rows:
            if want:
                sc[key] = want
        json.dump(doc, open(SEG_TABLES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  → segment_tables.json 반영 {len(sc)}건")
    return 0


def twins(game, scn, rows):
    """여러 세그먼트에 흩어진 **JP 동일 블록** 집합 — 재조준의 유일한 표적.

    ⚠ **세그먼트 전체를 한 파일로 몰면 안 된다.** 한 세그먼트가 정발 파일 둘에 정당하게
    걸치는 자리가 실재한다(크루즈#4 = T_023 44표 + T_024 62표). 실측으로 세그먼트 통째
    재조준은 이동 151건 중 129건이 확정 락과 부딪혔다(2026-08-05).

    진짜 표적은 **같은 JP 가 시점별로 반복되는 블록**이다 — 상점 인사·여관·현자처럼
    `past_recover_twins`(JP 동일 → 배정 복제)가 한 시점의 문안을 전 시점에 퍼뜨린 자리.
    유사도로는 원리적으로 못 가르고, 세그먼트가 정하면 답이 하나로 떨어진다.
    """
    from align_jp_kr import load_jp_scene

    segof = {}
    for key, _mp, eids, _c, _w in rows:
        for e in eids:
            segof[e] = key
    grp = collections.defaultdict(list)
    for b in load_jp_scene(game, scn):
        body = (b.get("body") or "").strip()
        if body:
            grp[((b.get("speaker") or ""), body)].append(b["id"])
    return {e for g in grp.values() if len({segof.get(x) for x in g}) > 1 for e in g}


def _remap_chain(chain, old, new, raw_new):
    """페이지 슬라이스를 새 엔트리로 옮긴다. None 이면 옮기지 말라는 뜻.

    형식은 `eid~변형#페이지.문장` — ⚠ **`~변형` 을 안 벗기면 `eid` 판정이 통째로 실패한다**
    (`4~1#0.0` 의 `4~1` 이 `isdigit()` 이 아니라 44건이 조용히 건너뛰어졌다, 2026-08-06).
    ⚠ 사본마다 변형(`\x06`)·페이지(`{p}`) 수가 다르니 **새 엔트리에 그 자리가 있는지**
    세어야 한다 — 안 세면 `chain_text` 가 `IndexError` 로 빌드를 세운다.
    ⚠ 여러 엔트리를 엮은 손수 체인은 옮기지 않는다(사람이 창에 맞춰 짠 것이다).
    """
    out = []
    for it in chain:
        base, _, rest = str(it).partition("#")
        base, _, vi = base.partition("~")
        if not base.isdigit() or int(base) != old:
            return None
        t = raw_new
        if vi:
            vs = t.split("\\x06")
            if not vi.isdigit() or int(vi) >= len(vs):
                return None
            t = vs[int(vi)]
        pi, _, si = rest.partition(".")
        if pi and pi != "tail":
            if not pi.isdigit() or int(pi) >= len(t.split("{p}")):
                return None
            t = t.split("{p}")[int(pi)]
        # ⚠ **문장 인덱스까지 세야 한다.** 페이지·변형만 보고 옮겼다가 `2~2#0.2` 가 문장
        # 하나뿐인 변형을 가리켜 빌드가 `본문 없음` 경고를 냈다(jp416 실측 2026-08-06).
        if si:
            from reinsert_kr_pilot import _sentences

            lo = si.partition("-")[0]
            if not lo.isdigit() or int(lo) >= len(_sentences(t)):
                return None
        head = f"{new}~{vi}" if vi else str(new)
        out.append(f"{head}#{rest}" if rest else head)
    return out


def retarget(game, scn, scn_name):
    """정본 세그먼트 배정에 맞춰 **어긋난 블록의 좌표를 옮긴다**(사본 대응표 경유)."""
    wide = "--wide" in sys.argv
    seg = load_seg_tables().get(scn_name, {})
    if not seg:
        print(f"{scn_name}: segment_tables.json 없음 — 먼저 --apply")
        return 1
    _pool, exempt = table_pool(game)
    ov_path = os.path.join(ROOT, "align_overrides.json")
    ov = json.load(open(ov_path, encoding="utf-8"))
    sc = ov.setdefault(scn_name, {})
    base = scene_map(scn_name)
    rows = propose(game, scn)
    tw = twins(game, scn, rows)

    moves, skips = [], collections.Counter()
    for key, _mp, eids, _c, _w in rows:
        want = seg.get(key)
        if not want:
            continue
        for e in eids:
            # 기본은 쌍둥이(여러 세그먼트에 흩어진 JP 동일 블록)만 건드린다.
            # ⚠ **`--wide`(자기 사본 아닌 블록 전부)는 재보고 채택하지 않았다**(2026-08-05):
            #    31건을 더 옮겨 감사 의심이 98→82 로 줄었지만 **겹침이 241→253 으로 늘었다**
            #    (같은 문장이 두 창에 렌더). 세그먼트가 정발 파일 둘에 정당하게 걸치는 자리를
            #    뭉개기 때문이다. 손익이 안 맞아 기본은 좁게 간다 — 플래그는 재측정용으로만 둔다.
            if e not in tw and not wide:
                continue
            o = sc.get(str(e)) or {}
            if not isinstance(o, dict):
                continue
            if "ours" in o or o.get("exclude"):
                skips["우리 문안·제외"] += 1
                continue
            if "유저 확정" in (o.get("note") or ""):
                skips["유저 확정"] += 1
                continue
            src = o.get("table") or (base.get(e) or {}).get("table")
            ent = o.get("entry_id")
            if ent is None:
                ent = (base.get(e) or {}).get("entry_id")
            if not src or ent is None or src == want or src in exempt:
                continue
            tgt = copy_map(src, want).get(ent)
            if tgt is None:
                skips["사본에 짝 없음"] += 1
                continue
            a = entries(src).get(ent, ("", "", ""))[2]
            b = entries(want).get(tgt, ("", "", ""))[2]
            chain = o.get("chain")
            if chain is not None:
                chain = _remap_chain(chain, ent, tgt, b)
                if chain is None:
                    skips["체인을 못 옮김(다중 엔트리·페이지 부족)"] += 1
                    continue
            # ⚠ `subs`(문안 치환)는 사람이 넣은 것이다. 새 사본에 그 문자열이 없으면
            # 치환이 조용히 죽으니 옮기지 않는다.
            if any(norm(s[0]) and norm(s[0]) not in norm(b) for s in o.get("subs") or []):
                skips["subs 가 새 사본에 안 맞음"] += 1
                continue
            # ⚠ **화자 유무가 뒤집히는 이동은 안 한다.** 정발 사본끼리 `{spk}` 유무가 다른
            # 자리가 있는데(크루즈 농부: `T_024#15` 없음 ↔ `T_028#6` 있음), PS1 이 그 대사를
            # 두 블록으로 쪼갠 뒤쪽 블록에 화자가 붙으면 이름판이 한 번 더 뜬다(jp441 실측).
            if ("{spk}" in a) != ("{spk}" in b):
                skips["화자 유무가 뒤집힘"] += 1
                continue
            moves.append((e, key, src, ent, want, tgt, chain, a, b))

    same = [m for m in moves if m[7] == m[8]]
    diff = [m for m in moves if m[7] != m[8]]
    print(f"{scn_name}: 쌍둥이 {len(tw)}블록 · 재조준 {len(moves)}건")
    print(f"  좌표만 교정(문안 동일) {len(same)}건 · **문안 바뀜 {len(diff)}건**")
    for w, n in skips.most_common():
        print(f"  건너뜀 {w}: {n}건")

    # ⚠ 이동이 없으면 검토표를 **덮지 않는다** — 반영 뒤 다시 돌리면 0건이라, 덮으면
    #    방금 만든 검토표가 빈 파일이 된다(실측 2026-08-05).
    if not moves:
        return 0
    os.makedirs(REVIEW_DIR, exist_ok=True)
    path = os.path.join(REVIEW_DIR, f"segment_copy_{scn_name}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {scn_name} 시점 사본 재조준 — 문안이 바뀌는 {len(diff)}건\n\n")
        f.write("`-` = **지금 화면에 나오는 문안** · `+` = **제안**. 둘 다 정발 문안이다.\n")
        for e, key, s, n, t, m, _c, a, b in diff:
            f.write(f"\n## jp{e} [{key}] {s.split('/')[-1]}#{n} → {t.split('/')[-1]}#{m}\n")
            f.write(f"- {a[:160]}\n+ {b[:160]}\n")
    print(f"  → 검토표 {path}")

    if "--apply" in sys.argv:
        for e, _key, s, n, t, m, chain, _a, _b in moves:
            cur = dict(sc.get(str(e)) or base.get(e) or {})
            cur.update(table=t, entry_id=m)
            if chain is not None:
                cur["chain"] = chain
            cur["note"] = f"시점 사본 정본(past_segment_copy 2026-08-05) — {s}#{n} → {t}#{m}"
            sc[str(e)] = cur
        json.dump(ov, open(ov_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  → align_overrides.json 반영 {len(moves)}건")
        if diff:
            ids = " ".join(str(m[0]) for m in diff)
            print(
                f"  ⚠ 확정 락 해제 필요:\n    python3 tools/lock_lines.py --unlock {scn_name} {ids}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
