#!/usr/bin/env python3
"""문안 교정 **제안 배치** — 검증하고, 승인된 것만, 한꺼번에 반영한다.

**왜 대화만으로는 안 되나.** ED1 은 회수가 끝나 남은 게 QA뿐이라 "이거 이렇게 고치자"가
대화로 돌아간다. 그런데 **ED2 는 7,272블록을 처음부터** 배정해야 하고, 오늘 B급 맞춤법
1,636건을 다뤄 보니 그 규모에서는 대화가 기록도 검증도 못 한다. mcpads PC-98 패처의
`export/apply_translation_proposal` 이 같은 자리를 푼다(2026-08-11 흡수).

**우리가 실제로 틀린 방식**에 맞춰 검증 항목을 골랐다 — 넷 다 오늘 물린 것이다:

| 검증            | 막는 사고                                                             |
| --------------- | --------------------------------------------------------------------- |
| `before` 대조   | 코퍼스가 그새 바뀌어 앵커가 안 맞는다(제안이 **조용히 무변화**로 죽는다) |
| `affected` 완전성 | **같은 원문의 다른 사본을 빠뜨린다** — 여덟 번 틀린 그 부류            |
| 제어 토큰 보존  | `%s`·`%c`·`\\xNN` 을 잃으면 구조 계약이 깨져 소프트락·꼬리 잘림        |
| 코퍼스 지문     | 승인 시점과 반영 시점의 코퍼스가 같은가                               |

⚠ **부분 반영을 안 한다.** 전량 재검증에 하나라도 걸리면 아무것도 안 쓴다 — 절반만 들어간
상태가 제일 나쁘다(어디까지 됐는지 아무도 모른다).
⚠ **배치 파일엔 정발 문안이 들어간다** — `work/review/` 아래에만 두고 **커밋 금지**.
커밋되는 건 반영 결과(`dos_spelling_fixes.json`)와 devlog 의 판단 근거다.

배치 형식(`work/review/proposals/<batch_id>.json`):

    {"schema_version": 1, "batch_id": "punct-0811", "status": "draft",
     "purpose": "정발이 두 문장을 붙여 둔 자리에 온점",
     "corpus_sha": "…",                      ← verify 가 채운다
     "decisions": [
       {"id": "d1", "kind": "replace", "before": "…", "after": "…",
        "affected": ["ED1/T_101#0"],          ← verify 가 채우고, 이후엔 대조한다
        "why": "JP 가 `。` 로 끝낸다"}]}

  python3 tools/proposal.py verify <batch.json>   # 검증 + affected·corpus_sha 채우기
  python3 tools/proposal.py apply  <batch.json>   # status=approved 만, 전량 재검증 후 반영
"""

import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import REVIEW_DIR, ROOT
from past_llm_assign import _raw

SPELL_JSON = os.path.join(ROOT, "dos_spelling_fixes.json")
PROPOSAL_DIR = os.path.join(REVIEW_DIR, "proposals")
SCHEMA = 1
# 구조 계약이 걸린 토큰 — 개수가 달라지면 창 수·인자 소비가 어긋난다
TOKENS = re.compile(r"%[csd]|\\x[0-9A-Fa-f]{2}|\{[np]\}")


def corpus():
    """{"표#엔트리": 교정 후 문안} — `spell_fix` 를 통과한 뒤, 곧 화면 표기."""
    return {f"{t}#{e}": R.corpus_text(v) for (t, e), v in _raw("ED1").items() if v}


def corpus_sha(c):
    h = hashlib.sha1()
    for k in sorted(c):
        h.update(k.encode() + b"\x00" + c[k].encode() + b"\x00")
    return h.hexdigest()[:16]


def _tokens(s):
    return sorted(TOKENS.findall(s))


def check(batch, c):
    """(problems, filled) — 검증 결과와 채워 넣은 배치."""
    bad = []
    if batch.get("schema_version") != SCHEMA:
        bad.append(f"schema_version {batch.get('schema_version')} ≠ {SCHEMA}")
    sha = corpus_sha(c)
    if batch.get("corpus_sha") and batch["corpus_sha"] != sha:
        bad.append(
            f"코퍼스가 승인 시점과 다르다 ({batch['corpus_sha']} → {sha}) — 다시 verify 할 것"
        )
    batch["corpus_sha"] = sha
    seen = set()
    for d in batch.get("decisions", []):
        did = d.get("id") or "?"
        if did in seen:
            bad.append(f"{did}: id 중복")
        seen.add(did)
        if d.get("kind") != "replace":
            bad.append(f"{did}: kind `{d.get('kind')}` 는 아직 미지원(지금은 replace 만)")
            continue
        before, after = d.get("before"), d.get("after")
        if not before or after is None:
            bad.append(f"{did}: before/after 가 없다")
            continue
        # ① before 가 지금 코퍼스에 실제로 있는가 + ② 어디에 있는가(전수)
        found = sorted(k for k, t in c.items() if before in t)
        if not found:
            bad.append(
                f"{did}: `{before}` 가 지금 코퍼스에 없다 — 앵커는 **기존 규칙이 다 돌아간 뒤**의"
                " 문안을 겨냥해야 한다(새 규칙은 목록 끝에 붙는다). 이미 고쳐졌을 수도 있다"
            )
        if "affected" in d and sorted(d["affected"]) != found:
            miss = set(found) - set(d["affected"])
            extra = set(d["affected"]) - set(found)
            bad.append(
                f"{did}: affected 불일치 — 빠짐 {sorted(miss)} · 남음 {sorted(extra)}"
                " (같은 원문의 다른 사본을 놓친 자리다)"
            )
        d["affected"] = found
        # ③ 제어 토큰 보존
        if _tokens(before) != _tokens(after):
            bad.append(f"{did}: 제어 토큰이 바뀐다 {_tokens(before)} → {_tokens(after)}")
        # ④ 이미 반영돼 있지 않은가(중복 규칙)
        rep = json.load(open(SPELL_JSON, encoding="utf-8"))["replace"]
        if any(a == before for a, _b in rep):
            bad.append(f"{did}: `{before}` 는 이미 치환표에 있다")
    return bad, batch


def _report(batch, bad):
    n = len(batch.get("decisions", []))
    print(f"배치 `{batch.get('batch_id')}` · 결정 {n}건 · 상태 {batch.get('status')}")
    for d in batch.get("decisions", []):
        aff = d.get("affected") or []
        print(f"  [{d.get('id')}] {d.get('before')!r} → {d.get('after')!r}  ({len(aff)}곳)")
        for k in aff[:6]:
            print(f"        {k}")
        if len(aff) > 6:
            print(f"        … 그 밖 {len(aff) - 6}곳")
        if d.get("why"):
            print(f"        근거: {d['why']}")
    if bad:
        print(f"\n❌ 문제 {len(bad)}건")
        for b in bad:
            print(f"  - {b}")
    else:
        print("\n✅ 검증 통과")


def verify(path):
    batch = json.load(open(path, encoding="utf-8"))
    bad, batch = check(batch, corpus())
    json.dump(batch, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    _report(batch, bad)
    if not bad and batch.get("status") == "draft":
        print("\n승인하려면 `status` 를 `approved` 로 바꾸고 `apply` 한다.")
    return 1 if bad else 0


def apply(path):
    batch = json.load(open(path, encoding="utf-8"))
    if batch.get("status") != "approved":
        raise SystemExit(f"status 가 `{batch.get('status')}` 다 — `approved` 만 반영한다")
    bad, batch = check(batch, corpus())
    if bad:
        _report(batch, bad)
        raise SystemExit("\n❌ 재검증 실패 — **아무것도 안 썼다**(부분 반영을 하지 않는다)")
    doc = json.load(open(SPELL_JSON, encoding="utf-8"))
    doc["replace"].extend([d["before"], d["after"]] for d in batch["decisions"])
    open(SPELL_JSON, "w", encoding="utf-8").write(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    )
    print(f"✅ {len(batch['decisions'])}건 반영 — replace {len(doc['replace'])}쌍")
    print("  ⚠ 다음 둘을 이어서 돌 것 — 넣은 규칙이 **화면에 닿았는지**는 별개다:")
    print("     python3 tools/check_spell_rules.py --new")
    print("     python3 tools/build.py")
    return 0


def main(argv):
    if len(argv) != 2 or argv[0] not in ("verify", "apply"):
        raise SystemExit(__doc__)
    path = argv[1]
    if not os.path.exists(path):
        path = os.path.join(PROPOSAL_DIR, argv[1])
    return verify(path) if argv[0] == "verify" else apply(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
