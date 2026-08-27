#!/usr/bin/env python3
"""**우리가 원문의 뜻을 지켰나** — 일본어 원문을 축으로 우리와 정발을 함께 잰다.

**왜.** 우리는 정발을 저본으로 출발해 **번역 정본**(`script/ED*SCN*.json`)으로 옮겨 왔다.
옮기며 고친 자리가 많고 그건 의도한 것이다 — 오역 교정 · 표기 통일 · 조판 예산. 문제는
**의도치 않게 뜻이 미끄러진 자리**가 그 안에 섞여도 아무 검사도 안 운다는 것이다.
길이도 어미도 다 그럴듯하니 눈으로는 안 걸린다.

🔴 **정발은 정답이 아니다 — 축은 일본어 원문이다.** 「우리 ↔ 정발」만 재면 순환에 빠진다.
정발 배정은 **엔트리 단위**라 우리 한 창의 짝이 그 안 어느 문장인지 안 알려 주는데,
「우리와 제일 닮은 조각」을 짝으로 고르면 **안 닮았을 때 엉뚱한 조각이 잡힌다**
(ED1SCN4 실측 2026-08-27 — 688 중 387이 임계 미만이었고 대부분이 이 오탐).

그래서 **원문을 축에 두고 삼각으로 잰다**(LaBSE 는 원래 번역쌍 찾기용이라 한↔일이 강하다):

    jp_ours  원문 ↔ 우리       ← 이게 본론이다
    jp_jb    원문 ↔ 정발       ← 대조군. 짝 조각도 **원문**이 고른다(우리가 아니라)
    ours_jb  우리 ↔ 정발       ← 표현이 얼마나 겹치나

판정이 셋으로 갈린다:

| 신호 | 뜻 | 할 일 |
| --- | --- | --- |
| `jp_ours` 낮고 `jp_jb` 높다 | **우리가 미끄러졌다** | 문장 재검토 |
| `jp_ours` 높고 `jp_jb` 낮다 | 정발이 오역, 우리가 바로잡음 | `docs/jeongbal-deviations.md` 에 적는다 |
| 둘 다 높다 | 표현만 다르다 | 넘어간다 (이 부류가 제일 많다) |

🔴 **오탐 두 부류가 체계적이다**(ED1 전수 실측 2026-08-27 — 후보 86 중 실제 수정은 1):

1. **구어체·사투리** — LaBSE 는 정식 번역쌍으로 배운 모델이라 `~구먼`·`옙`·`~올시다`·
   `~뎁쇼` 같은 문체 표지에 점수를 깎는다. 「자네들, 나그네인 모양이구먼」(`旅人のようじゃな`)이
   0.43 인 식이다. **문체가 살아 있을수록 점수가 낮다** — 이 게임에선 그게 미덕이다.
2. **문장 조각 블록** — 원문이 종결부호 없이 다음 블록으로 이어지는 자리는 반쪽만 재게
   되어 점수가 원래 낮다. `--frag` 로 따로 본다(기본은 뺀다).

그래서 **점수는 순위로만 읽고, 판정은 문맥이 한다.** 특히 블록의 `note` 를 반드시 본다 —
지난 판정이 거기 적혀 있고, 안 보면 확정된 결정을 뒤집는다(실제로 그럴 뻔했다).

⚠ 정발 배정이 없는 블록도 **`jp_ours` 는 나온다** — 대조군이 없을 뿐이다. 우리 정본이
손으로 쓴 자리로 옮겨 갈수록 이 쪽이 는다.
⚠ **글자 유사도(`ours_jb`)가 높으면 오히려 위험하다** — 정발 축자 복제는 저작권 규칙
위반이고 `check_forbidden` 이 못 보는 층이다. 따로 모아 보고한다.

⚠ **비결정적이다 — 게이트에 안 물린다.** LaBSE 점수는 머신을 타고(레포 제1원칙), 이건
**제안**이지 판정이 아니다. `check.sh` 에 넣으면 끊긴 자리에서 늘 빨간불이 된다.
⚠ **보고는 `work/review/` 에만 쓴다 — 커밋 절대 금지.** 원문·정발 문안이 통째로 들어간다.

  python3 tools/audit_nuance.py                 # ED1 전 씬
  python3 tools/audit_nuance.py --game ED2      # ED2 전 씬
  python3 tools/audit_nuance.py ED1SCN4         # 그 씬만
  python3 tools/audit_nuance.py --worst 40
  python3 tools/audit_nuance.py --gap 0.10      # 정발보다 이만큼 뒤처지면 후보
"""

import argparse
import difflib
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

from common import OUT_DIR, REVIEW_DIR, ROOT

# 정발 마크업 · 우리 센티널 · 이스케이프 리터럴 — 대조 전에 전부 걷는다
_MARKUP = re.compile(r"\{[^}]*\}|\\x[0-9A-Fa-f]{2}|[\x17\x1a\x1b]")
# 조사 병기는 **앞을 남긴다**(`을(를)` → `을`). 괄호째 두면 점수가 통째로 흔들린다
_BYEONGGI = re.compile(r"(은|는|이|가|을|를|와|과|으로|로)\((?:은|는|이|가|을|를|와|과|으로|로)\)")
_WS = re.compile(r"\s+")
_CHRNORM = re.compile(r"[\s.,!?~…·\-'\"]+")

MIN_LEN = 6  # 이름표·맞장구는 볼 것이 없다


def flatten(s):
    return _WS.sub(" ", _BYEONGGI.sub(r"\1", _MARKUP.sub(" ", s))).strip()


# ⚠ 파생 원문은 `!`·`?` 를 **`\x21`·`\x3F` 라는 여섯 글자 그대로** 들고 있다. 안 풀면
#   짧은 대사가 길어 보여 길이 바닥을 통과하고 점수도 흔들린다(`backtrans` 에서 실측).
_JP_ESC = re.compile(r"\\x([0-9A-Fa-f]{2})")
# 🔴 **원문의 화자 이름표를 뗀다.** `{c}リュナン{c}` 이 붙은 채 재면 우리 문안엔 없는 이름이
#   원문에만 남아 점수가 통째로 깎인다 — 이름창은 우리 쪽에서 `s` 로 빠져 있다.
_JP_HEAD = re.compile(r"^\{c\}[^{]{0,12}\{c\}")


def strip_jp(s):
    s = _JP_ESC.sub(lambda m: chr(int(m.group(1), 16)), s)
    return flatten(_JP_HEAD.sub("", s))


_SENT = re.compile(r"(?<=[.!?…])\s+")


def _chunks(text):
    """정발 엔트리 하나를 **여러 알갱이**로 편다 — 전문 · 페이지 · 문장 · 이웃 문장 묶음.

    🔴 **이게 없으면 결과가 통째로 못 쓴다.** 배정은 엔트리 단위인데 정발은 상점·현자처럼
    **한 NPC 의 대사 전부를 한 엔트리**에 몰아 둔 자리가 많다. 우리 블록은 창 하나라
    통째로만 대조하면 그 자리가 전부 「뜻이 갈렸다」로 떠서 진짜 후보를 덮는다
    (ED1SCN4 실측 2026-08-27 — 하위 12 중 10이 이 오탐이었다).
    """
    out = [flatten(text)]
    for page in re.split(r"\{p\}|\{n\}", text):
        out.append(flatten(page))
        sents = [x for x in (flatten(y) for y in _SENT.split(page)) if x]
        out += sents
        # 이웃 둘·셋 묶음 — 우리 한 창이 정발 두세 문장에 걸치는 자리가 흔하다
        for n in (2, 3):
            out += [" ".join(sents[i : i + n]) for i in range(len(sents) - n + 1)]
    return [c for c in dict.fromkeys(out) if len(c) >= 2]


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def jeongbal_pages(game):
    """`{(table, entry_id): [알갱이…]}` — 정발 엔트리를 대조 가능한 알갱이로 편다."""
    out = {}
    for p in sorted(glob.glob(os.path.join(OUT_DIR, "dos_kr", game, "*.json"))):
        doc = _load(p)
        if not isinstance(doc, dict):
            continue
        table = f"{game}/{os.path.basename(p)[:-5]}"
        for e in doc.get("entries", []) or []:
            if not isinstance(e, dict):
                continue
            cand = _chunks(e.get("text") or "")
            if cand:
                out[(table, e["entry_id"])] = cand
    return out


# 원문이 여기로 끝나면 온전한 문장이다 — 아니면 다음 블록으로 이어지는 **조각**이다
_TERM = tuple("。！？…」』.!?~♪〜、")


def is_fragment(raw):
    t = _JP_ESC.sub(lambda m: chr(int(m.group(1), 16)), re.sub(r"\{[cnp]\}", "", raw)).strip()
    return not t.endswith(_TERM)


def pairs(scenes, game="ED1", keep_frag=False):
    """[(키, 원문, 우리 문안, [정발 조각…])] — 우리가 옮긴 블록 전부. 정발은 있으면 붙인다."""
    amap = _load(os.path.join(ROOT, "align_map.json"))
    ovr = _load(os.path.join(ROOT, "align_overrides.json"))
    jb = jeongbal_pages(game)
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "script", f"{game}SCN*.json"))):
        scn = os.path.basename(f)[:-5]
        if scenes and scn not in scenes:
            continue
        jf = os.path.join(OUT_DIR, "scn_jp", f"{scn}.json")
        if not os.path.exists(jf):
            continue
        jp_raw = {e["entry_id"]: (e.get("text") or "") for e in _load(jf)["entries"]}
        jp = {k: strip_jp(v) for k, v in jp_raw.items()}
        canon = _load(f)
        a, o = amap.get(scn, {}), ovr.get(scn, {})
        for k, v in sorted(canon.items(), key=lambda x: int(x[0]) if x[0].isdigit() else -1):
            if not (k.isdigit() and isinstance(v, dict) and v.get("t")):
                continue
            if not keep_frag and is_fragment(jp_raw.get(int(k), "")):
                continue
            src_jp, ours = jp.get(int(k), ""), flatten(v["t"])
            if len(src_jp) < MIN_LEN or len(ours) < MIN_LEN:
                continue
            # 오버라이드가 이긴다 — 배정 정본의 규약과 같다
            src = (o.get(k) or {}) if isinstance(o.get(k), dict) else {}
            if not src.get("table"):
                src = (a.get(k) or {}) if isinstance(a.get(k), dict) else {}
            cand = jb.get((src.get("table"), src.get("entry_id"))) or []
            out.append((f"{scn}:{k}", src_jp, ours, cand))
    return out


def score(rows, batch=256):
    """[(jp_ours, jp_jb, ours_jb, 키, 원문, 우리, 정발짝)] — 원문에서 멀어진 순.

    ⚠ **정발 짝은 원문이 고른다.** 우리와 닮은 조각을 고르면 「우리가 틀렸을 때 짝도
    엉뚱해져」 두 점수가 같이 낮아진다 — 대조군이 대조군 노릇을 못 한다.
    """
    import torch
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("sentence-transformers/LaBSE", device="cpu")
    # ⚠ 조각은 **중복 제거하고** 인코딩한다 — 정발 엔트리 하나가 블록 여럿에 배정돼 있어
    #   그대로 밀면 같은 문장을 수십 번 다시 잰다(ED1SCN4 에서 조각이 10배로 불었다).
    uniq = {}
    for _k, jpt, ours, cand in rows:
        for t in (jpt, ours, *cand):
            uniq.setdefault(t, len(uniq))
    texts = [t for t, _ in sorted(uniq.items(), key=lambda x: x[1])]
    emb = model.encode(texts, batch_size=batch, convert_to_tensor=True, normalize_embeddings=True)

    out = []
    for key, jpt, ours, cand in rows:
        ej, eo = emb[uniq[jpt]], emb[uniq[ours]]
        jp_ours = float(ej @ eo)
        jp_jb = ours_jb = None
        best = ""
        if cand:
            ec = emb[[uniq[c] for c in cand]]
            sims = ec @ ej
            i = int(torch.argmax(sims))
            best, jp_jb = cand[i], float(sims[i])
            ours_jb = difflib.SequenceMatcher(
                None, _CHRNORM.sub("", ours), _CHRNORM.sub("", best)
            ).ratio()
        out.append((jp_ours, jp_jb, ours_jb, key, jpt, ours, best))
    out.sort(key=lambda x: x[0])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", nargs="*", help="ED1SCN4 처럼 씬 이름")
    ap.add_argument("--game", default="ED1", choices=("ED1", "ED2"))
    ap.add_argument("--frag", action="store_true", help="문장 조각 블록도 본다(점수를 못 믿는다)")
    ap.add_argument("--abs", type=int, default=40, help="대조군 없는 블록을 절대 점수로 몇 개")
    ap.add_argument("--worst", type=int, default=25, help="화면에 보여 줄 개수")
    ap.add_argument("--gap", type=float, default=0.10, help="정발보다 이만큼 뒤처지면 후보")
    ap.add_argument("--copy", type=float, default=0.92, help="이 글자 유사도 위를 축자 복제로")
    ap.add_argument("--copylen", type=int, default=14, help="축자 복제 판정의 길이 바닥")
    a = ap.parse_args()

    rows = pairs(set(a.scenes), a.game, a.frag)
    if not rows:
        print("대조할 것이 없다 — 정본에 옮긴 블록이 없다")
        return 1
    n_ctl = sum(1 for r in rows if r[3])
    print(f"대조 {len(rows):,} 블록 (정발 대조군 있는 것 {n_ctl:,})")
    scored = score(rows)

    med = sorted(x[0] for x in scored)[len(scored) // 2]
    # 🔴 후보의 정의 — **절대 점수가 아니라 정발과의 격차**다. 절대값은 문장 길이·문체에
    #    휘둘려 임계를 못 잡는다(첫 판에서 688 중 387 이 떴다).
    slip = [x for x in scored if x[1] is not None and x[1] - x[0] >= a.gap]
    fixed = [x for x in scored if x[1] is not None and x[0] - x[1] >= a.gap]
    copied = sorted(
        [x for x in scored if x[2] is not None and x[2] >= a.copy and len(x[5]) >= a.copylen],
        key=lambda x: -x[2],
    )
    print(
        f"\n원문↔우리 중앙값 {med:.2f}"
        f" · 우리가 뒤처진 자리 {len(slip)} · 정발보다 나은 자리 {len(fixed)}"
        f" · 축자 복제 의심 {len(copied)}"
    )

    # 🔴 **대조군이 없으면 절대 점수밖에 없다.** ED2 는 문안을 손으로 써서 정발 배정이
    #    6,083 중 92 뿐이다(실측 2026-08-27) — 격차 기준을 그대로 쓰면 후보가 0 이 된다.
    lone = [x for x in scored if x[1] is None][: a.abs]
    if lone:
        print(f"\n── 대조군 없음 · 원문↔우리가 낮은 순 {len(lone)} (⚠ 구어체는 원래 낮다)")
        for jo, _jj, _cj, key, jpt, ours, _b in lone:
            print(f"  [{jo:.2f}] {key}")
            print(f"    원문 {jpt[:60]}")
            print(f"    우리 {ours[:60]}")

    print(f"\n── ⚠ 우리가 원문에서 더 멀다 (재검토) {min(a.worst, len(slip))}")
    for jo, jj, _cj, key, jpt, ours, best in sorted(slip, key=lambda x: x[0] - x[1])[: a.worst]:
        print(f"  [원문↔우리 {jo:.2f} · 원문↔정발 {jj:.2f}] {key}")
        print(f"    원문 {jpt[:60]}")
        print(f"    우리 {ours[:60]}")
        print(f"    정발 {best[:60]}")
    if copied:
        print(f"\n── ⚠ 정발을 거의 그대로 쓴 자리 {min(a.worst, len(copied))} (저작권)")
        for _jo, _jj, cj, key, _jpt, ours, _b in copied[: a.worst]:
            print(f"  [글자 {cj:.2f}] {key}  {ours[:56]}")

    os.makedirs(os.path.join(REVIEW_DIR, "nuance"), exist_ok=True)
    tag = "-".join(sorted(a.scenes)) if a.scenes else a.game
    p = os.path.join(REVIEW_DIR, "nuance", f"{tag}.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(f"# 원문 뜻 대조 — {tag}\n\n")
        f.write("⚠ 원문·정발 문안이 들어 있다 — **커밋 금지**. 판정은 일본어 원문이 한다.\n\n")
        f.write(f"대조 {len(rows):,} · 원문↔우리 중앙값 {med:.2f}\n\n")
        for title, rowset in (
            ("⚠ 우리가 원문에서 더 멀다 — 재검토", sorted(slip, key=lambda x: x[0] - x[1])),
            (
                "정발보다 우리가 원문에 가깝다 — 편차 대장 후보",
                sorted(fixed, key=lambda x: x[1] - x[0]),
            ),
        ):
            f.write(f"## {title} ({len(rowset)})\n\n")
            f.write("| 원문↔우리 | 원문↔정발 | 블록 | 원문 | 우리 | 정발 |\n")
            f.write("| --- | --- | --- | --- | --- | --- |\n")
            for jo, jj, _cj, key, jpt, ours, best in rowset:
                f.write(f"| {jo:.2f} | {jj:.2f} | {key} | {jpt} | {ours} | {best} |\n")
            f.write("\n")
        if lone:
            f.write(f"## 대조군 없음 — 원문↔우리가 낮은 순 ({len(lone)})\n\n")
            f.write("⚠ 구어체·사투리는 원래 낮게 나온다. 순위로만 읽는다.\n\n")
            f.write("| 원문↔우리 | 블록 | 원문 | 우리 |\n| --- | --- | --- | --- |\n")
            for jo, _jj, _cj, key, jpt, ours, _b in lone:
                f.write(f"| {jo:.2f} | {key} | {jpt} | {ours} |\n")
            f.write("\n")
        if copied:
            f.write(
                f"## ⚠ 축자 복제 의심 ({len(copied)})\n\n| 글자 | 블록 | 우리 |\n| --- | --- | --- |\n"
            )
            for _jo, _jj, cj, key, _jpt, ours, _b in copied:
                f.write(f"| {cj:.2f} | {key} | {ours} |\n")
    print(f"\n검토표 → {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
