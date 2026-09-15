#!/usr/bin/env python3
"""확정 대사 락 — 인게임에서 통과한 대사를 이후 라운드가 못 건드리게 못 박는다.

**왜 필요한가(2026-08-03 실측).** 정렬·배정은 매 라운드 다시 계산된다 —
`past_align_semantic`(LaBSE 전역 1:1)·`past_assign_pages`(문턱을 낮춰가며 Hungarian). 그런데 이들은
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
  python3 tools/lock_lines.py --observe            # 관측 대장 갱신(전 씬, 아래)

**언제 freeze 하나** — 유저가 그 구간을 인게임으로 확인한 직후. 확인 전에 뜨면 꼬인 상태를
확정해 버린다.

## 관측 대장(observed_lines.json) — 락의 짝

락은 **인게임 확인분만** 지킨다. 그래서 아직 QA 안 한 구간은 상류를 건드려도 **아무도 안
알려준다** — 실제로 2장 QA 중에 추출기를 고치면서, 무엇이 바뀌었는지 보려고 세션 시작
커밋으로 워크트리를 떠서 렌더를 통째로 비교해야 했다(2026-08-08). 그 과정에서 측정을
세 번 틀렸다. **손으로 할 일이 아니다.**

그래서 **전 블록 해시**를 대장에 두고 빌드마다 차이를 **보고만** 한다.

| | 대상 | 어긋나면 |
| --- | --- | --- |
| 락 `locked_lines.json` | 인게임 확인분 | **빌드 실패** — 승인 없이 못 지나감 |
| 관측 `observed_lines.json` | **전 블록** | **목록 출력** — 빌드는 그대로 진행 |

⚠ 대장은 **자동 갱신하지 않는다.** `--observe` 로 사람이 받아들일 때만 갱신한다 — 자동이면
"바뀐 걸 알려준다"는 목적 자체가 사라진다(freeze 와 같은 규율).
⚠ 여기도 **해시만** 담는다 — 문안을 담으면 저작권 규칙 위반이다.
"""

import hashlib
import json
import os
import sys

from common import OUT_DIR, ROOT

LOCK_PATH = os.path.join(ROOT, "locked_lines.json")
OBS_PATH = os.path.join(ROOT, "observed_lines.json")
SCENES = [f"ED1SCN{i}" for i in range(1, 7)]
# 🔴 `observe()` 전용 — 락(`SCENES`)은 인게임 확인분(ED1)만 지키지만, 관측은 **전 블록**을
# 봐야 한다(도크스트링 그대로). ED2 를 빼면 오늘 발견된 것과 똑같은 구멍이 된다 —
# check_window_nl·check_shop_verbs·check_variants·check_leader_variants 가 전부 이 꼴로
# ED1 만 보다 걸렸다(2026-09-13). observe() 는 SCENES 가 아니라 이걸 돈다.
_SCN_COUNT = {"ED1": 6, "ED2": 13}
SCENES_OBSERVE = [f"{g}SCN{i}" for g in ("ED1", "ED2") for i in range(1, _SCN_COUNT[g] + 1)]


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


def load_obs():
    try:
        return json.load(open(OBS_PATH, encoding="utf-8"))
    except FileNotFoundError:
        return {}


def obs_diff(scn_name, tr):
    """대장 대비 (바뀐, 새로 생긴, 사라진) eid 목록. 빌드가 보고용으로 부른다."""
    old = load_obs().get(scn_name, {})
    now = {str(e): line_sha(t) for e, t in tr.items() if line_sha(t) is not None}
    changed = sorted(int(k) for k in now if k in old and old[k] != now[k])
    added = sorted(int(k) for k in now if k not in old)
    dropped = sorted(int(k) for k in old if k not in now)
    return changed, added, dropped


def observe():
    """전 씬 문안 해시를 대장에 굳힌다 — 지금 상태를 '받아들인다'는 선언."""
    import reinsert_kr_pilot as R

    obs = load_obs()
    obs["_doc"] = (
        "관측 대장 — 전 블록의 문안 sha1 앞 10자. 락(locked_lines.json)이 인게임 확인분만 "
        "지키는 데 반해 이쪽은 **전 블록**을 보되 어긋나도 빌드를 세우지 않고 목록만 낸다. "
        "문안 자체는 저작권상 저장 금지. 갱신은 `tools/lock_lines.py --observe` 로 사람이 "
        "받아들일 때만 — 자동 갱신하면 알림의 목적이 사라진다."
    )
    tot = ch = ad = dr = 0
    for scn in SCENES_OBSERVE:
        tr, _, _ = R.load_translations(scn.replace("SCN", "_SCN"), scn)
        c, a, d = obs_diff(scn, tr)
        ch, ad, dr = ch + len(c), ad + len(a), dr + len(d)
        obs[scn] = {str(e): line_sha(t) for e, t in sorted(tr.items()) if line_sha(t) is not None}
        tot += len(obs[scn])
    json.dump(obs, open(OBS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(OBS_PATH, "a", encoding="utf-8").write("\n")
    print(f"관측 대장 {tot}블록 갱신 (문안 변경 {ch} · 신규 {ad} · 사라짐 {dr}) → {OBS_PATH}")


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


REQUA = "_requa"  # **인게임 확인 뒤 문안이 바뀐 자리** — QA 판정이 무효가 됐다
SETTLED = "_settled"  # **영영 손댈 것 없음** (락은 번역된 문안만 지킨다)
PENDING = "_pending"  # **나중에 채운다** — 목록에 계속 뜬다(아래 참조)


def settled(scn_name):
    """{eid: 사유} — 미번역 목록에서 **빼야 할** 블록.

    ⚠ `_pending` 은 여기 안 들어간다. 그게 이 둘을 가른 이유다."""
    return load_lock().get(SETTLED, {}).get(scn_name, {})


def pending(scn_name):
    """{eid: 사유} — 미번역이지만 **지금 할 일은 아닌** 블록(해당 장 QA 때 채운다)."""
    return load_lock().get(PENDING, {}).get(scn_name, {})


def mark_settled(scn_name, eids, why, later=False):
    """⚠ 락이 못 덮는 자리를 덮는다.

    락은 **번역된 블록의 문안 해시**만 본다. 그래서 "미번역이지만 인게임에서 확인해 보니
    문제없다"(다른 블록이 덮는다 · 사본이 리타깃된다)나 "이 장에서는 도달하지 않는다"는
    판정이 어디에도 안 남아, 다음 검토 때 **똑같은 블록이 또 목록에 뜬다**(유저 지적
    2026-08-04 — 곶의 동굴 보물상자·네리아 현자가 그랬다). 여기 적어 두면 빠진다.

    ⚠ **두 뜻을 가른다**(2026-08-10). 한 표식에 「영영 손댈 것 없음」과 「해당 장 QA 때
    채운다」가 섞여 있었고, 둘 다 목록에서 조용히 빠지니 **후자가 잊혔다** — SCN1 여섯이
    그렇게 일본어로 남아 있었다. `later=True`(`--later`)는 `_pending` 으로 들어가
    **`todo_untranslated` 가 계속 보고**한다. 잊히지 않는 게 요점이다."""
    lock = load_lock()
    d = lock.setdefault(PENDING if later else SETTLED, {}).setdefault(scn_name, {})
    for e in eids:
        d[str(e)] = why
    save_lock(lock)
    kind = "나중에 채움" if later else "판정 완료"
    print(f"{scn_name}: {kind} {len(eids)}건 기록 — {why}")


def relock(scn_name, eids=(), why=""):
    """**이미 잠긴 블록의 해시만** 갱신한다 — 새 블록은 절대 안 잠근다.

    맞춤법 일괄 교정처럼 **의도한 상류 변경**은 확인이 끝난 대사까지 같이 바꾼다. 그때
    `--freeze` 를 쓰면 아직 확인 안 된 블록까지 정본으로 승격시킨다(실측 933 → 935) —
    검증기를 갱신기로 쓰는 셈이라 락이 지키려던 것을 락 갱신이 무너뜨린다. 이건 개수를
    바꾸지 않으니 "무엇을 확인했는가"는 그대로 두고 "무엇으로 확인했는가"만 옮긴다."""
    import reinsert_kr_pilot as R

    tr, _, _ = R.load_translations(scn_name.replace("SCN", "_SCN"), scn_name)
    lock = load_lock()
    cur = lock.get(scn_name, {})
    n0 = len(cur)
    moved = []
    todo = [str(e) for e in eids] if eids else sorted(cur, key=int)
    for k in todo:
        if k not in cur:
            raise SystemExit(f"jp{k} 는 락에 없다 — 새로 잠그려면 인게임 확인이 먼저다")
        sha = line_sha(tr.get(int(k)))
        if sha and cur[k].get("sha") != sha:
            cur[k]["sha"] = sha
            moved.append(k)
    assert len(cur) == n0, "relock 이 락 개수를 바꿨다"
    # ⚠ **relock 은 「인게임 확인한 대사가 바뀌었다」는 뜻이다** — 그 자리의 QA 판정은 무효다.
    # 해시만 갱신하고 넘어가면 무엇을 다시 봐야 하는지가 사라진다(실제로 2장 QA 뒤 264건이
    # 조용히 바뀌어 있었고, 알아내려고 옛 커밋으로 워크트리를 떠서 역산해야 했다 — 2026-08-11).
    if moved:
        q = lock.setdefault(REQUA, {}).setdefault(scn_name, {})
        for k in moved:
            q[k] = why or q.get(k) or "relock"
    save_lock(lock)
    tail = f" · 재검수 대기 +{len(moved)}" if moved else ""
    print(f"{scn_name}: 해시 갱신 (총 {n0}건, 개수 불변){tail}")


def main():
    # ⚠ 우회는 **스크립트로 직접 돌 때만** 건다. 모듈 최상단에 두면 이 모듈을 import 하는 것만으로
    # **빌드 전체의 락 검증이 꺼진다** — 실제로 그렇게 됐다(2026-08-04 실측: `ours` 가드가
    # `load_lock` 을 import 하면서 같은 프로세스의 검증이 통째로 무력화, 불일치 3건이 통과).
    # `align_map.py` 가 같은 사고를 낸 자리와 판박이다. **모듈 최상단 env 변경은 하지 않는다.**
    # 이 도구는 락이 깨진 상태에서도 현재 문안을 읽어야 하므로(freeze 갱신·unlock 판단) 우회가 필요하다.
    os.environ["LOCK_BYPASS"] = "1"
    if "--settled" in sys.argv:
        i = sys.argv.index("--settled")
        why = sys.argv[sys.argv.index("--why") + 1] if "--why" in sys.argv else "인게임 확인"
        # ⚠ `--why` 를 **먼저** 잘라낸 뒤 인자를 모은다. 예전엔 `-` 로 시작하는 토큰을 먼저
        # 걸러내서 `"--why" in args` 가 영영 거짓이었고, 사유 문구가 eid 로 등록됐다
        # (SCN1 3건 · SCN3 1건 · SCN4 3건이 그렇게 들어가 있었다 — 2026-08-10 발견·정리).
        end = sys.argv.index("--why") if "--why" in sys.argv else len(sys.argv)
        args = [a for a in sys.argv[i + 1 : end] if not a.startswith("-")]
        mark_settled(args[0], args[1:], why, later="--later" in sys.argv)
        return
    if "--observe" in sys.argv:
        observe()
        return
    if "--freeze" in sys.argv:
        for scn in sys.argv[sys.argv.index("--freeze") + 1 :]:
            if scn.startswith("-"):
                break
            freeze(scn)
        return
    if "--relock" in sys.argv:
        i = sys.argv.index("--relock")
        end = sys.argv.index("--why") if "--why" in sys.argv else len(sys.argv)
        why = sys.argv[sys.argv.index("--why") + 1] if "--why" in sys.argv else ""
        args = [a for a in sys.argv[i + 1 : end] if not a.startswith("-")]
        relock(args[0], args[1:], why)
        return
    if "--requa" in sys.argv:  # 재검수 대기 목록
        q = load_lock().get(REQUA, {})
        n = sum(len(v) for v in q.values())
        print(f"인게임 확인 뒤 문안이 바뀐 자리 — **재검수 대기 {n}건**")
        for scn in sorted(q):
            eids = sorted(q[scn], key=int)
            print(f"  {scn}: {len(eids)}건")
            for e in eids[:40]:
                print(f"      jp{e}  ({q[scn][e]})")
            if len(eids) > 40:
                print(f"      … 그 밖 {len(eids) - 40}건")
        if n:
            print("\n확인이 끝나면 `--requa-clear <씬> [eid …]`(eid 없으면 그 씬 전부).")
        return
    if "--requa-clear" in sys.argv:
        i = sys.argv.index("--requa-clear")
        args = [a for a in sys.argv[i + 1 :] if not a.startswith("-")]
        lock = load_lock()
        q = lock.setdefault(REQUA, {})
        scn = args[0]
        if len(args) > 1:
            for e in args[1:]:
                q.get(scn, {}).pop(e, None)
        else:
            q.pop(scn, None)
        if not q.get(scn):
            q.pop(scn, None)
        save_lock(lock)
        print(f"{scn}: 재검수 대기에서 뺐다 (남은 {sum(len(v) for v in q.values())}건)")
        return
    if "--unlock" in sys.argv:
        i = sys.argv.index("--unlock")
        scn, eids = sys.argv[i + 1], sys.argv[i + 2 :]
        lock = load_lock()
        # eid 를 안 주면 **그 씬 전부** — `--requa-clear` 와 같은 규약이다.
        # ⚠ 번역 방침이 바뀌면 옛 확인은 근거를 잃는다. 락은 「정발대로 들어갔는가」를
        # 확인한 것이라, 「정발을 살리되 고친다」로 옮긴 뒤에는 전부 다시 봐야 한다
        # (유저 지시 2026-08-12 "락 다 풀고 전체대상으로 하자").
        n = len(eids) if eids else len(lock.get(scn, {}))
        if eids:
            for e in eids:
                lock.get(scn, {}).pop(e, None)
        else:
            lock.pop(scn, None)
            lock.get(REQUA, {}).pop(scn, None)
        save_lock(lock)
        print(f"{scn}: {n}건 해제")
        return
    lock = load_lock()
    for scn, v in lock.items():
        if scn.startswith("_"):
            continue
        s = len(lock.get(SETTLED, {}).get(scn, {}))
        print(f"  {scn:10} 확정 {len(v)}건" + (f" · 판정완료(미번역) {s}건" if s else ""))
    if len(lock) <= 1:
        print("  (아직 없음 — 인게임 확인 후 `--freeze <씬>`)")


if __name__ == "__main__":
    main()
