"""한 줄 문장 계수 — 번역 규칙 2-10 (마스터 10-10·11-03). 창 한 줄(전각 17)에 들어가는 문장이 **두 줄로 쪼개진** 곳을 굽는 문안(`script/MAP*.json`)으로 센다.

    python3 games/ss-ed3/tools/check_oneline.py             # 개수
    python3 games/ss-ed3/tools/check_oneline.py --show 20   # 예
    python3 games/ss-ed3/tools/check_oneline.py --apply     # 고칠 수 있는 곳을 새 줄 시작으로
    python3 games/ss-ed3/tools/check_oneline.py --check     # 대장(script/oneline_pending.json) 밖 새 걸림 · 양성 대조 → rc 1

문장 = 쪽(`\\f`) 안에서 `. ! ? …` 로 끝나는 덩이(줄이 바뀌어도 이어 본다). 쪽을 넘는 문장은 안 센다(창 경계는 원문 것이다 — 2-17).
고치기(`--apply`)는 **줄 수를 안 늘리고** 쪽 줄 수 한도(이름 창 첫 쪽 2줄 · 그 밖 3줄)와 「마지막 줄 16칸 이하」를 지킬 때만 한다.
나머지는 대장에 열쇠로 둔다(문장을 한 줄에 두면 쪽이 한 줄 늘거나 이름 창 한도를 넘는 곳 — 2-17 은 문안·창 경계를 안 바꾼다).
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_linebreak as LB
import common as C
import typeset as T

SCRIPT = os.path.join(C.GAME_DIR, "script")
PENDING = os.path.join(SCRIPT, "oneline_pending.json")
END = re.compile(r"[.!?…〜~]+[)'\"」』]*$")


def _fits(s):
    s, _r = LB.expand_names(s)
    return len(T.fold(s.replace(LB.GLUE, " "))) <= 1


def split_sentences(rows):
    """`[(첫 줄, 끝 줄, 조각들)]` — 쪽의 줄 목록에서 문장 단위. 조각 = 줄마다의 글자."""
    out, cur = [], []
    for ri, row in enumerate(rows):
        words = row.strip().split(" ") if row.strip() else []
        for wi, w in enumerate(words):
            cur.append((ri, w))
            nxt = (
                words[wi + 1]
                if wi + 1 < len(words)
                else (
                    rows[ri + 1].strip().split(" ")[0]
                    if ri + 1 < len(rows) and rows[ri + 1].strip()
                    else ""
                )
            )
            if END.search(w) or (w.endswith(")") and nxt.startswith("(")):
                out.append(cur)
                cur = []
    #   끝 부호 없이 끝난 덩이(간판 줄·속말 괄호·다음 쪽으로 이어지는 말)는 문장으로 안 센다
    res = []
    for s in out:
        res.append((s[0][0], s[-1][0], s))
    return res


def hits_in(text):
    """`[(쪽 번호, 문장 글, 첫 줄, 끝 줄)]` — 여러 줄에 걸쳤지만 한 줄에 드는 문장."""
    out = []
    if text.count("〜") >= 3:
        return out  # 노래 가사 — 줄이 가락 단위다
    for pi, pg in enumerate(text.split("\f")):
        rows = pg.split("\n")
        for a, b, s in split_sentences(rows):
            if b > a:
                joined = " ".join(w for _r, w in s)
                if _fits(joined):
                    out.append((pi, joined, a, b))
    return out


def fix_text(text, named_first=False):
    """`(고친 문안, 고친 수)` — 줄 수 불변 · 쪽 한도 · 마지막 줄 16칸 이하일 때만 문장 시작에서 줄을 바꾼다."""
    pages = text.split("\f")
    n = 0
    if text.count("〜") >= 3:
        return text, 0
    for pi, pg in enumerate(pages):
        for _ in range(8):
            rows = pg.split("\n")
            vis = rows
            done = True
            for a, b, s in split_sentences(vis):
                joined = " ".join(w for _r, w in s)
                if b > a and _fits(joined):
                    first_words = [w for r, w in s if r == a]
                    keep = vis[a][
                        : len(vis[a])
                        - len(" ".join(first_words))
                        - (len(vis[a]) - len(vis[a].rstrip()))
                    ].rstrip()
                    lead = vis[a][: len(vis[a]) - len(vis[a].lstrip())]
                    if not keep.strip():
                        #   문장이 줄 첫머리에서 시작 — 줄을 합치기만 하면 된다(줄이 준다)
                        tail = rows[b]
                        last_part = " ".join(w for r, w in s if r == b)
                        rest = tail.strip()[len(last_part) :].strip()
                        cand = lead + joined + ((" " + rest) if rest else "")
                        if not _fits(cand):
                            continue
                        pg = "\n".join(rows[:a] + [cand] + rows[b + 1 :])
                        n += 1
                        done = False
                        break
                    if any("<" in x for x in rows[a : b + 1]):
                        continue  # 제어 표기 든 줄은 새 줄 시작으로는 손대지 않는다(합치기만 한다)
                    new = rows[:a] + [keep, lead + joined]
                    tail = rows[b]
                    last_part = " ".join(w for r, w in s if r == b)
                    rest = tail.strip()[len(last_part) :].strip()
                    if rest:
                        # 문장 뒤에 이어지는 말이 있으면 한 줄에 같이 못 들면 줄이 는다
                        cand = lead + joined + " " + rest
                        if _fits(cand):
                            new[-1] = cand
                        else:
                            continue
                    new += rows[b + 1 :]
                    if len(new) > len(rows):
                        continue
                    if not new[-1].strip() or len(T.fold(new[-1].rstrip())) != 1:
                        continue
                    if T.cols(new[-1]) > 16.0:
                        continue
                    pg = "\n".join(new)
                    n += 1
                    done = False
                    break
            if done:
                break
        pages[pi] = pg
    return "\f".join(pages), n


def scan():
    """`{열쇠: [(쪽, 문장)]}` — 씬 대사(나레이션 제외)."""
    narr = {(n, str(i)) for n, i, _ in LB.CN.targets()}
    out = {}
    for f in sorted(glob.glob(os.path.join(SCRIPT, "MAP*.json"))):
        n = os.path.basename(f)
        with open(f, encoding="utf-8") as fh:
            doc = json.load(fh)
        for k, v in doc.items():
            if k.startswith("_") or not isinstance(v, str) or (n, k) in narr or T.is_narration(v):
                continue
            h = hits_in(v)
            if h:
                out[f"{n[:-5]}#{k}"] = [(p, s) for p, s, _a, _b in h]
    return out


def controls():
    return [
        ("두 줄로 쪼갠 짧은 문장", bool(hits_in("류난에게\n19의 피해!!"))),
        ("앞 문장 뒤 쪼갬", bool(hits_in("올랐다. MP가\n5포인트 올랐다."))),
        (
            "정상 두 줄은 안 걸림",
            not hits_in("가나다 라마바 사아자 차카타 파하\n거너더 러머버 서어저 처커터 푸후."),
        ),
        ("줄 첫머리 시작 문장은 안 걸림", not hits_in("안녕하세요.\n반갑습니다.")),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    if a.apply:
        total = 0
        for f in sorted(glob.glob(os.path.join(SCRIPT, "MAP*.json"))):
            with open(f, encoding="utf-8") as fh:
                doc = json.load(fh)
            n = 0
            for k, v in doc.items():
                if k.startswith("_") or not isinstance(v, str) or T.is_narration(v):
                    continue
                new, c = fix_text(v)
                if c:
                    doc[k] = new
                    n += c
            if n:
                total += n
                with open(f, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh, ensure_ascii=False, indent=1)
                    fh.write("\n")
        print(f"고친 문장 {total}")
    ctl = controls()
    for name, ok in ctl:
        print(f"  양성 대조 {'✅' if ok else '🔴'} {name}")
    got = scan()
    print(
        f"  2-10 한 줄에 들어가는데 쪼갠 문장 — 블록 {len(got)} · 문장 {sum(len(v) for v in got.values())}"
    )
    for k, v in list(got.items())[: a.show]:
        print(f"    {k}  쪽{v[0][0]} {v[0][1]}")
    if a.freeze:
        with open(PENDING, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "_why": "2-10 대장 — 한 줄로 두면 쪽 줄 수가 늘거나 이름 창 한도(첫 쪽 2줄)를 넘는 곳. 2-17: 문안·창 경계를 안 바꾼다 — 원문 창대로 가른 곳(window_restore_2_17.json)에서 한 줄 문장이 창 경계로 쪼개진 것도 원문 창 우선이라 여기 둔다.",
                    "keys": sorted(got),
                },
                fh,
                ensure_ascii=False,
                indent=1,
            )
            fh.write("\n")
        return 0
    rc = 0
    if a.check:
        base = set()
        if os.path.exists(PENDING):
            with open(PENDING, encoding="utf-8") as fh:
                base = set(json.load(fh)["keys"])
        if [n for n, ok in ctl if not ok]:
            print("  🔴 양성 대조 실패")
            rc = 1
        new = sorted(set(got) - base)
        if new:
            print("  🔴 대장 밖 새 걸림:", ", ".join(new[:10]))
            rc = 1
        if rc == 0:
            print("  ✅ 2-10 — 대장 밖 새 걸림 없음")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
