#!/usr/bin/env python3
"""확정 대사 락 — 인게임에서 통과한 대사를 이후 라운드가 못 건드리게 못 박는다.

**왜 필요한가(2026-08-03 실측).** 정렬·배정은 매 라운드 다시 계산된다 —
`align_semantic`(LaBSE 전역 1:1)·`assign_pages`(문턱을 낮춰가며 Hungarian). 그런데 이들은
**전역 최적**이라 후보 풀이 바뀌면 *이미 잘 맞던 짝까지* 다른 블록에게 넘어간다. 게다가
`align_jp_kr` 를 인자 없이 돌리면 의미정렬 결과를 구조 신호 초안으로 통째 덮어쓴다.
그날 "원래 잘 나오던 대사가 안 나온다"가 이 세 경로로 반복됐다.

**그래서 계산에서 빼낸다.** 두 겹이다 —
① `reinsert_kr_pilot.apply_lock_src` 가 락의 **배정 좌표(`src`)를 정렬 결과에 되씌우고**,
② 빌드 끝에 문안 해시를 대조해 **달라졌으면 빌드를 실패**시킨다.
(빌드 규율 "실패한 빌드는 산출물을 무효화한다" 와 같은 자리다.)

⚠ ②만 있던 시절엔 **머신을 옮기면 빌드가 서고 앞으로 못 나갔다.** 원문에 **완전 중복 블록**이
있어(같은 대사를 하는 병사 여럿) 배정이 **정확한 동점**이 되고, 승자는 부동소수 잡음이 정한다 —
머신마다 갈린다. 점수 문턱으로 못 막고(양쪽 0.97/0.94) 정렬을 다시 돌려도 복원이 안 된다
(2026-08-03(3) 실측 — 재생성 후 똑같은 24건이 해시까지 동일).
**판정만 하는 기준선은 환경이 갈리는 순간 작업을 멈추는 장치가 된다** — 그래서 ①을 넣었다.

⚠ **문안은 저장하지 않는다 — sha1 앞 10자만.** 정발 문안이 리포에 남으면 저작권 규칙 위반이라
`textmap` 이 JP 키를 sha1 로 쓰는 것과 같은 관용을 따른다. 배정 좌표(table/entry/chain)는
포인터라 저장해도 된다.

  python3 tools/lock_lines.py --freeze ED1SCN1     # 지금 상태를 확정으로 못 박는다
  python3 tools/lock_lines.py --status             # 락 현황
  python3 tools/lock_lines.py --unlock ED1SCN1 331 # 특정 블록 해제(문안을 고칠 때)

**언제 freeze 하나** — 유저가 그 구간을 인게임으로 확인한 직후. 확인 전에 뜨면 꼬인 상태를
확정해 버린다.
"""

import hashlib
import json
import os
import sys

# 이 도구는 **락이 깨진 상태에서도** 현재 문안을 읽어야 한다(freeze 갱신·unlock 판단).
# 빌드의 락 검증이 load_translations 안에 있어 그대로 두면 복구 도구가 잠긴다.
os.environ.setdefault("LOCK_BYPASS", "1")

from common import OUT_DIR, ROOT

LOCK_PATH = os.path.join(ROOT, "locked_lines.json")


def line_sha(t):
    """번역 엔트리 → 문안 해시(sha1 앞 10자). 화자 + 창 본문만 본다(조판·바이트는 무관)."""
    if t is None:
        return None
    spk = t[0] if isinstance(t[0], str) else ""
    wins = []
    try:
        for item in t[1]:
            if isinstance(item, (list, tuple)) and len(item) > 1 and isinstance(item[1], str):
                wins.append(item[1])
    except (TypeError, IndexError):
        return None
    if not wins:
        return None
    return hashlib.sha1(("\x00".join([spk, *wins])).encode("utf-8")).hexdigest()[:10]


def load_lock():
    try:
        return json.load(open(LOCK_PATH, encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_lock(d):
    json.dump(d, open(LOCK_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _assignments(scn_name):
    """{eid: 배정 좌표} — 오버라이드 우선, 없으면 정렬 쌍에서. 락이 재적용할 포인터다."""
    import reinsert_kr_pilot as R

    out = {}
    align_name = scn_name.replace("SCN", "_SCN")
    p = os.path.join(OUT_DIR, "align", f"{align_name}.json")
    if os.path.exists(p):
        for pr in json.load(open(p, encoding="utf-8"))["pairs"]:
            if pr.get("jp") and pr.get("kr") and not pr.get("flags"):
                out[pr["jp"]["entry_id"]] = {
                    "table": pr["kr"]["table"],
                    "entry_id": pr["kr"]["entry_id"],
                }
    for jid, v in R._load_overrides().get(scn_name, {}).items():
        if jid.isdigit() and isinstance(v, dict) and "table" in v:
            out[int(jid)] = {k: v[k] for k in ("table", "entry_id", "chain", "subs") if k in v}
    return out


def freeze(scn_name):
    import reinsert_kr_pilot as R

    tr, _, _ = R.load_translations(scn_name.replace("SCN", "_SCN"), scn_name)
    src = _assignments(scn_name)
    lock = load_lock()
    lock.setdefault(
        "_doc",
        "인게임에서 확인된 대사의 확정 락. 키=씬, 하위=PS1 entry_id → {sha, src}. "
        "sha=문안 sha1 앞 10자(문안 자체는 저작권상 저장 금지), src=배정 좌표(포인터). "
        "빌드가 이 해시를 대조해 달라지면 실패한다. 갱신은 tools/lock_lines.py.",
    )
    cur = lock.setdefault(scn_name, {})
    added = updated = 0
    for eid, t in tr.items():
        sha = line_sha(t)
        if sha is None:
            continue
        entry = {"sha": sha}
        if eid in src:
            entry["src"] = src[eid]
        k = str(eid)
        if k not in cur:
            added += 1
        elif cur[k].get("sha") != sha:
            updated += 1
        cur[k] = entry
    save_lock(lock)
    print(f"{scn_name}: 확정 {len(cur)}건 (신규 {added} · 갱신 {updated}) → {LOCK_PATH}")


def verify(scn_name, tr):
    """빌드 중 호출 — 락된 문안이 달라졌으면 (eid, 기대sha, 현재sha) 목록을 돌려준다."""
    cur = load_lock().get(scn_name, {})
    bad = []
    for k, v in cur.items():
        eid = int(k)
        now = line_sha(tr.get(eid))
        if now != v.get("sha"):
            bad.append((eid, v.get("sha"), now))
    return bad


def main():
    if "--freeze" in sys.argv:
        for scn in sys.argv[sys.argv.index("--freeze") + 1 :]:
            if scn.startswith("-"):
                break
            freeze(scn)
        return
    if "--unlock" in sys.argv:
        i = sys.argv.index("--unlock")
        scn, eids = sys.argv[i + 1], sys.argv[i + 2 :]
        lock = load_lock()
        for e in eids:
            lock.get(scn, {}).pop(e, None)
        save_lock(lock)
        print(f"{scn}: {len(eids)}건 해제")
        return
    lock = load_lock()
    for scn, v in lock.items():
        if scn.startswith("_"):
            continue
        print(f"  {scn:10} 확정 {len(v)}건")
    if len(lock) <= 1:
        print("  (아직 없음 — 인게임 확인 후 `--freeze <씬>`)")


if __name__ == "__main__":
    main()
