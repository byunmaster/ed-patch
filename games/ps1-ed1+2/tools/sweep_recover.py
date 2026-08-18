#!/usr/bin/env python3
"""정발 회수 1차 스윕 — 미매칭 블록을 고유 본문으로 묶고, 위험군을 자동으로 갈라낸다.

`classify_unmatched.py`가 "정발 후보가 있다"까지 말해주면, 이 도구는 **구조적으로 위험한
것을 먼저 걷어내고** 남은 것을 사람이 읽고 판정할 수 있는 표로 만든다.

⚠ **구조통과 = 적용 가능이 아니다.** 여기 필터는 `%c`/`%s` 계약과 배정 충돌만 본다.
의미가 맞는지는 못 본다 — 실제로 sim 0.55~0.67 구간에는 구조는 멀쩡한데 뜻이 전혀 다른
오매칭이 섞여 있다(SCN1 실측: 구조통과 27종 중 9종이 오매칭). **표를 읽고 판정해야 한다.**
SCN1 43건을 손으로 판정하며 드러난 위험 셋이 전부 구조로 판별 가능해서다(2026-07-30):

  ⛔ 데이터 블록  — `%c` 0개 + 선두가 바이너리 포인터 배열이고 꼬리에만 지명이 붙은 블록.
                   분류기가 지명으로 매칭하지만 대사가 아니라 **이동 금지** 대상이다.
  ⚠ 서식 보유    — `%s`/`%d`가 있는 블록에 정발 엔트리를 통째로 넣으면 서식이 빠져
                   `fmt_drop`으로 **블록이 통째 탈락**한다. `ours`+센티널로 따로 써야 한다.
  ⚠ 중복 타깃    — 서로 다른 JP 블록이 같은 정발 엔트리를 가리키면 같은 문장이 두 번 나온다.
                   JP 본문까지 같으면 정상(같은 대사의 반복), 다르면 사람이 갈라야 한다.

**고유 JP 본문으로 묶는다** — 782건 중 고유 본문은 446종뿐이라(2026-07-30 실측) 판정
한 번이 여러 블록을 덮는다.

산출물은 둘 다 `out/review/`(gitignore) 아래다 — 검토표에는 팔콤 일문과 정발 문안이 그대로
들어가므로 **커밋하지 않는다**. 커밋되는 결정은 `align_overrides.json`의 포인터뿐이다
(레포 루트 `docs/publishing.md`).

usage:
  sweep_recover.py ED1 1            검토표 + 오버라이드 초안 생성
  sweep_recover.py ED1 1 --bucket 경계
"""

import collections
import json
import os
import re
import sys

from align_jp_kr import DOS_KR_DIR
from common import OUT_DIR, REVIEW_DIR

BIN_ESC = re.compile(r"\\x[0-9A-Fa-f]{2}")
FMT_S, FMT_D = "\\x25\\x73", "\\x25\\x64"


def jp_blocks(game, scn):
    p = os.path.join(OUT_DIR, "scn_jp", f"{game}SCN{scn}.json")
    return {e["entry_id"]: e for e in json.load(open(p, encoding="utf-8"))["entries"]}


def parse_report(path, bucket):
    """분류기 리포트에서 (jp_id, sim, table, entry_id) 목록을 뽑는다."""
    txt = open(path, encoding="utf-8").read()
    heads = ["## 회수가능", "## 경계(확인 필요)", "## 신규 번역 필요"]
    key = {"회수가능": 0, "경계": 1, "신규": 2}[bucket]
    if heads[key] not in txt:
        return []
    sec = txt.split(heads[key])[1]
    for nxt in heads[key + 1 :]:
        sec = sec.split(nxt)[0]
    out, cur = [], None
    for line in sec.splitlines():
        m = re.match(r"- jp(\d+) \(([\d.]+)\)", line)
        if m:
            cur = (int(m.group(1)), float(m.group(2)))
        m2 = re.search(r"→ (\S+)#(\d+)", line)
        if m2 and cur:
            out.append((cur[0], cur[1], m2.group(1), int(m2.group(2))))
            cur = None
    return out


def risk_of(text):
    """블록 구조에서 읽어낼 수 있는 위험 태그."""
    tags = []
    if text.count("{c}") == 0 and len(BIN_ESC.findall(text[:40])) >= 3:
        tags.append("데이터블록")
    if FMT_S in text or FMT_D in text:
        tags.append("서식보유")
    return tags


_KR_CACHE = {}


def kr_text(table, eid):
    """정발 엔트리 본문 — 판정에 꼭 필요하다(포인터만 보고는 뜻을 알 수 없다)."""
    if table not in _KR_CACHE:
        p = os.path.join(DOS_KR_DIR, table + ".json")
        doc = json.load(open(p, encoding="utf-8"))
        _KR_CACHE[table] = {e["entry_id"]: e for e in doc["entries"]}
    e = _KR_CACHE[table].get(eid)
    return (e or {}).get("text", "(없음)").removesuffix("{end}")


def norm_key(text):
    """중복 판정용 정규화 — 제어토큰·바이너리 이스케이프·공백 제거."""
    t = BIN_ESC.sub("", text)
    t = re.sub(r"\{[cnp]\}", "", t)
    return re.sub(r"\s+", "", t)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    game, scn = sys.argv[1], int(sys.argv[2])
    bucket = sys.argv[sys.argv.index("--bucket") + 1] if "--bucket" in sys.argv else "회수가능"

    rep = os.path.join(REVIEW_DIR, f"unmatched_{game}SCN{scn}_0-99999.md")
    if not os.path.exists(rep):
        sys.exit(f"{rep} 없다 — classify_unmatched.py {game} {scn} 0 99999 를 먼저 돌려라")

    B = jp_blocks(game, scn)
    rows = parse_report(rep, bucket)

    # 같은 정발 엔트리를 가리키는 JP가 여럿인지 (본문까지 같으면 정상 반복)
    per_target = collections.defaultdict(set)
    for jid, _, tbl, eid in rows:
        per_target[(tbl, eid)].add(norm_key(B.get(jid, {}).get("text", "")))

    groups = collections.OrderedDict()  # 고유 본문 → 묶음
    for jid, sim, tbl, eid in rows:
        text = B.get(jid, {}).get("text", "")
        k = norm_key(text)
        g = groups.setdefault(
            k, {"ids": [], "sim": sim, "table": tbl, "entry_id": eid, "text": text}
        )
        g["ids"].append(jid)

    ok, held = [], []
    for g in groups.values():
        tags = risk_of(g["text"])
        if len(per_target[(g["table"], g["entry_id"])]) > 1:
            tags.append("중복타깃")
        g["tags"] = tags
        (held if tags else ok).append(g)

    # ── 검토표 (사람용, gitignore) ─────────────────────────────────────────
    outdir = REVIEW_DIR
    os.makedirs(outdir, exist_ok=True)
    md = [
        f"# {game}SCN{scn} — {bucket} 스윕 검토표",
        "",
        f"블록 {len(rows)}건 / 고유 본문 {len(groups)}종 (구조통과 {len(ok)} · 구조보류 {len(held)})",
        "",
        "⚠ 이 파일은 원문과 정발 문안을 그대로 담는다 — **커밋 금지**(gitignore).",
        "",
        "## 구조통과 — ⚠ 의미 판정 필요 (적용 가능이 아니다)",
        "",
        "| sim | 블록 | JP 원문 | 정발 후보 | 정발 대사 |",
        "| ---: | --- | --- | --- | --- |",
    ]

    def row(g):
        ids = ",".join(f"jp{i}" for i in g["ids"][:6]) + ("…" if len(g["ids"]) > 6 else "")
        jp = BIN_ESC.sub("·", g["text"]).replace("|", "\\|")[:70]
        kr = BIN_ESC.sub("·", kr_text(g["table"], g["entry_id"])).replace("|", "\\|")[:70]
        return f"| {g['sim']:.2f} | {ids} | `{jp}` | `{g['table']}#{g['entry_id']}` | `{kr}` |"

    md += [row(g) for g in ok]
    md += [
        "",
        "## 보류 (사람 판정 필요)",
        "",
        "| sim | 블록 | 위험 | JP 원문 | 정발 후보 | 정발 대사 |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for g in held:
        md.append(row(g).replace("| `", f"| {'·'.join(g['tags'])} | `", 1))
    path_md = os.path.join(outdir, f"sweep_{game}SCN{scn}_{bucket}.md")
    open(path_md, "w", encoding="utf-8").write("\n".join(md) + "\n")

    # ── 오버라이드 초안 (자동통과분만) ────────────────────────────────────
    prop = {}
    for g in ok:
        for jid in g["ids"]:
            prop[str(jid)] = {
                "table": g["table"],
                "entry_id": g["entry_id"],
                "note": f"1차 스윕 구조통과(의미 미판정) sim={g['sim']:.2f} ({bucket})",
            }
    path_js = os.path.join(outdir, f"candidates_{game}SCN{scn}_{bucket}.json")
    json.dump(prop, open(path_js, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    tagc = collections.Counter(t for g in held for t in g["tags"])
    print(f"{game}SCN{scn} [{bucket}] 블록 {len(rows)} / 고유 {len(groups)}종")
    print(
        f"  구조통과 {len(ok)}종 → 블록 {len(prop)}건 (의미 판정 필요)  → {os.path.relpath(path_js)}"
    )
    print(f"  보류     {len(held)}종  {dict(tagc)}")
    print(f"  검토표   {os.path.relpath(path_md)}")


if __name__ == "__main__":
    main()
