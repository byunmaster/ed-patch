#!/usr/bin/env python3
"""문안이 **어느 시대에 쓰였는가**를 센다 — 「정발 유래」가 얼마나 남았나.

**왜 필요한가(2026-08-19).** 「script 에 `t` 가 있다」를 「우리가 썼다」로 읽으면 안 된다.
`script/` 의 뿌리는 **08-12 초안 소진**이고, 그 초안은 정발 문안이었다. 08-18 에 방침이
「JP 원문에서 우리가 번역」으로 바뀌었지만 **이미 들어와 있던 문안은 그대로**다.

⚠ 유사도로는 못 가른다. 축자 게이트는 공백 무시 비교라 **맞춤법 한 글자만 달라도** 통과하고
(devlog 08-18: 어절 하나 지운 정발 문장 9줄이 통과하고 있었다), 유사도 0.7 이 「우리가 썼다」를
뜻하지도 않는다 — **손을 많이 본 정발**도 같은 점수가 나온다. 판별은 **이력**으로 한다.

시대는 셋이다(`--pivot` 으로 경계를 옮길 수 있다):

    B 자체번역   전환 커밋 이후에 들어온 문안 — JP 원문에서 썼다
    C 전환 이전  전환 커밋 시점에 이미 있던 문안 — **정발 유래로 본다**
    A 작업 중    커밋 안 된 변경(지금 손대는 중)

🔴 **이 도구는 `script/` 만 센다 — 화면에 나가는 전부가 아니다.**(2026-08-19 유저 QA 로 발각)
번역 정본에 없는 블록은 **옛 정렬 경로**(`align_map`)로도 화면에 나가는데, 그건 정발 유래다.
ED1 은 `script/` 기준으로 「전환 이전 0」이 됐는데도 정렬 경로로 **97블록**이 그대로 나가고
있었다. 즉 **이 수치가 0 이어도 저작권 축이 닫힌 게 아니다.**

    python3 tools/audit_provenance.py --unlisted   # ← 정렬 경로로만 나가는 블록을 센다

⚠ 새 편(ED2)·새 게임에서도 **먼저 `--unlisted` 로 사각을 재고** 시작해라.

  python3 tools/audit_provenance.py            # 시대별 블록 수
  python3 tools/audit_provenance.py --scene    # 씬마다
  python3 tools/audit_provenance.py --list ED1SCN4   # C 블록 eid 목록(재작성 대상)
"""

import argparse
import collections
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = os.path.relpath(ROOT, os.path.abspath(os.path.join(ROOT, "..", "..")))
# 자체 번역 전환 직전 커밋 — 이 시점에 있던 문안이 「정발 유래」다(policy.md 「자체 번역」).
PIVOT = "9f4ce32"

# 🔴 **다시 썼는데 옛 문안과 글자까지 같아진 자리.** 이력만 보면 「안 고쳤다」와 구별이
# 안 되지만 **동일 = 베낌이 아니다** — 원문이 평범하면 자연스러운 한국어가 한 자리로
# 모인다(유저 지적 2026-08-19: "상투적인거라 동일할 수도 있지"). `check_forbidden` 의
# `CANON_CONVERGED_OK` 와 같은 성격이라 같은 방식으로 **자리를 콕 집어** 둔다.
# ⚠ 등록 조건은 하나다 — **재작성 때 옛 문안을 안 보고 썼다**(페이로드에서 가렸다).
REWRITTEN_CONVERGED = {
    ("ED1SCN3", "71"),  # `いつ王位につかれるんですか` — 같은 JP 의 자체 번역분과 같은 문안
    ("ED1SCN5", "951"),  # (원문 생략 — 짧은 감사 인사) — 대안이 어색
    ("ED2SCN12", "239"),  # `皇帝が 強力な力を得る前に倒したい` — 평서문, 한 가지로 수렴
    # ② 통(2026-08-19) — 496건 재작성 중 16건(3.2%)이 옛 문안과 같아졌다. 태반은 **같은 JP 의
    # 자체 번역분 문안을 그대로 쓴 자리**(같은 원문 = 같은 문안 규칙이 이긴다)이고, 나머지는
    # 인사·안내 같은 상투 문구다. 유저 지적 그대로 — 동일이 곧 베낌은 아니다.
    ("ED1SCN1", "148"),
    ("ED1SCN1", "163"),
    ("ED1SCN1", "621"),
    ("ED1SCN1", "676"),
    ("ED1SCN1", "702"),
    ("ED1SCN1", "734"),
    ("ED1SCN1", "1065"),
    ("ED1SCN1", "1236"),
    ("ED1SCN1", "1239"),
    ("ED1SCN1", "1278"),
    ("ED1SCN1", "1326"),
    ("ED1SCN2", "334"),
    ("ED1SCN2", "357"),
    ("ED1SCN2", "380"),
    ("ED1SCN2", "385"),
    ("ED1SCN2", "406"),
    # ③ QA 판정이 되돌려 옛 문안과 같아진 자리(2026-09-27) — 둘 다 전환 뒤 한 번 다르게 썼다.
    # 여기 안 넣으면 「C 전환 이전」으로 잡혀 `line_dict` 에서 **조용히 빠진다** → 다른 기종이
    # 옛 문안을 받는다(새턴이 PS1 ED1 사전을 받기 직전에 발각).
    ("ED1SCN1", "537"),  # qa2 088 더듬는 말 「무, 뭐라고」→「뭐, 뭐라고」(첫 음절 반복)
    ("ED1SCN3", "1120"),  # 시스템 메시지 「~없었다」→「~없었습니다」(원문 정중 — 문체는 원문을 따른다)
}

# ⚠ **문장이 아닌 자리**는 애초에 재작성 대상이 아니다 — 낱말 나열과 전용 빌더가 만드는
# 정형 안내문. 루트 `CLAUDE.md`: 단어 수준 명칭·라벨은 저작권 대상이 아니다.
NOT_A_SENTENCE = {
    ("ED2SCN2", "300"),  # 워프 목적지 34개 나열 — `check_forbidden.WORDLIST_OK` 와 같은 자리
    ("ED2SCN8", "261"),  # 보물상자 획득 안내(이름창 셋) — 정형문, 구조가 계약이다
}


def _at(rev, name):
    """그 리비전의 `script/<name>.json` (없으면 빈 dict)."""
    r = subprocess.run(
        ["git", "show", f"{rev}:{REL}/script/{name}.json"],
        capture_output=True,
        text=True,
        check=False,
    )
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout else {}


# 🔴 **재작성 장부**(`rewrite_apply` 가 남긴다). 다시 썼는데 옛 문안과 글자까지 같아지면
# 이력으로는 「안 고쳤다」와 구별이 안 된다 — 「같은 원문이면 같은 문안」이 규칙이라 자연히
# 수렴한다(실측: 한 배치 41건 중 32건). 손으로 등록하던 `REWRITTEN_CONVERGED` 를 대신한다.
# ⚠ 이 파일은 **기계만 쓴다** — 손으로 좌표를 적으면 「정발을 세탁하는 장부」가 된다.
def _rewrite_log():
    path = os.path.join(ROOT, "rewrite_log.json")
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {(scn, e) for scn, v in d.items() if not scn.startswith("_") for e in v}


_LOG = None


def era_of(eid, t, committed, before, scn=None):
    global _LOG
    if _LOG is None:
        _LOG = _rewrite_log()
    if (committed.get(eid) or {}).get("t") != t:
        return "A 작업 중"
    if (before.get(eid) or {}).get("t") == t:
        if (scn, eid) in REWRITTEN_CONVERGED | NOT_A_SENTENCE | _LOG:
            return "B 자체번역"
        return "C 전환 이전"
    return "B 자체번역"


def scan(pivot=PIVOT):
    """{씬: {시대: [eid…]}}

    ⚠ **2패스다.** 1패스에서 시대를 매기고, 2패스에서 「우리가 쓴 문안과 **글자까지 같은**
    C」를 B 로 올린다 — 우리가 어딘가에 우리 손으로 쓴 문장이면 그 사본도 우리 것이다
    (`rewrite_dupfill` 과 같은 의미론). 안 그러면 정형문 한 벌이 통째로 「정발 유래」로
    잡힌다(2026-08-19 실측: 번역 에이전트 97건 중 33건이 보물상자 정형문이었다).
    """
    raw, texts = {}, {}
    for path in sorted(glob.glob(os.path.join(ROOT, "script", "ED*SCN*.json"))):
        scn = os.path.basename(path)[:-5]
        with open(path, encoding="utf-8") as f:
            cur = json.load(f)
        committed, before = _at("HEAD", scn), _at(pivot, scn)
        per = collections.defaultdict(list)
        for eid, v in cur.items():
            t = v.get("t")
            if t:
                per[era_of(eid, t, committed, before, scn)].append(eid)
                texts[(scn, eid)] = t
        raw[scn] = dict(per)

    ours = {
        texts[(scn, e)]
        for scn, per in raw.items()
        for k in ("A 작업 중", "B 자체번역")
        for e in per.get(k, ())
    }
    out = {}
    for scn, per in raw.items():
        keep, moved = [], []
        for eid in per.get("C 전환 이전", ()):
            (moved if texts[(scn, eid)] in ours else keep).append(eid)
        per = dict(per)
        if moved:
            per["B 자체번역"] = list(per.get("B 자체번역", ())) + moved
            per["C 전환 이전"] = keep
        out[scn] = per
    return out


def _unlisted():
    """번역 정본에 없는데 **화면에는 나가는** 블록 — 정렬 경로(정발 유래)로 채워진다.

    ⚠ 재삽입기를 태워야 알 수 있다(`align_map` + 오버라이드 + 체인이 다 얽힌다).
    그래서 느리다 — 상시 게이트가 아니라 **사각을 잴 때** 부른다.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import reinsert_kr_pilot as R

    tot = 0
    for scn in sorted(
        os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ROOT, "script", "ED*SCN*.json"))
    ):
        with open(os.path.join(ROOT, "script", f"{scn}.json"), encoding="utf-8") as f:
            have = {e for e, v in json.load(f).items() if (v or {}).get("t")}
        try:
            tr, _, _ = R.load_translations(scn.replace("SCN", "_SCN"), scn)
        except Exception as exc:  # noqa: BLE001 — 체인 밖 씬은 셀 수 없다(ED2 다수)
            print(f"  {scn:<9} – 셀 수 없다 ({type(exc).__name__})")
            continue
        n = len([e for e in tr if str(e) not in have])
        tot += n
        print(f"  {scn:<9} 재삽입 {len(tr):>5} · 정본 {len(tr) - n:>5} · **정본 밖 {n:>4}**")
    # ⚠ **지금 남은 4는 전부 화자 이름표다** — 문안이 아니라 재작성 대상이 아니다
    #   (실측 2026-09-01): `ED1SCN6:141`(`ドルカスの手下`) · `ED2SCN2:564·614·734`
    #   (`教育係 ラウエル`). 원문도 본문 없이 이름만 있는 블록이고, ED1SCN6:141 은
    #   **일부러 대답을 안 하는 장면**임을 인게임으로 확인했다(유저 2026-09-02).
    #   ⇒ 이 수치가 0 이 아니어도 저작권 축은 닫혀 있다. 매번 다시 판정하지 말 것.
    print(f"\n  🔴 정본 밖에서 화면에 나가는 블록 {tot} — 정발 유래다. 재작성 대상.")
    print("     ⚠ 지금 넷은 전부 **화자 이름표**라 문안이 아니다(판정 끝 2026-09-02).")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pivot", default=PIVOT)
    ap.add_argument("--scene", action="store_true", help="씬마다")
    ap.add_argument("--list", metavar="SCN", help="그 씬의 「전환 이전」 eid 목록")
    ap.add_argument(
        "--unlisted", action="store_true", help="번역 정본 밖에서 화면에 나가는 블록(정렬 경로)"
    )
    a = ap.parse_args()

    if a.unlisted:
        return _unlisted()

    data = scan(a.pivot)
    if a.list:
        eids = data.get(a.list, {}).get("C 전환 이전", [])
        print(" ".join(sorted(eids, key=int)))
        return 0

    eras = ("A 작업 중", "B 자체번역", "C 전환 이전")
    if a.scene:
        for scn, per in data.items():
            row = " · ".join(f"{e[2:]} {len(per.get(e, ())):5}" for e in eras)
            print(f"  {scn:<9} {row}")
        print()
    for game in ("ED1", "ED2"):
        c = collections.Counter()
        for scn, per in data.items():
            if scn.startswith(game):
                for e in eras:
                    c[e] += len(per.get(e, ()))
        tot = sum(c.values())
        if not tot:
            continue
        print(f"  {game} 합 {tot}")
        for e in eras:
            print(f"    {e:<12} {c[e]:5}  {c[e] / tot * 100:5.1f}%")
    print(
        f"\n  ⚠ 「C 전환 이전」이 **정발 유래**다(기준 커밋 {a.pivot}). 유사도가 낮아도"
        "\n    「우리가 썼다」가 아니라 「손을 많이 봤다」일 수 있다 — 재작성 대상."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
