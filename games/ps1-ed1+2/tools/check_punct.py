#!/usr/bin/env python3
"""**화자가 바뀌기 전 마지막 창에 온점이 있는가** — 문장이 끝나는 자리를 본다.

**왜.** 맞춤법·띄어쓰기는 외부 검사기가 본다(`shared/text/spellcheck.py`). 그런데 온점은
**문장만 봐서는 판정이 안 된다** — 창이 이어지는 중간이면 문장이 계속될 수 있고, 그
화자의 **마지막 창**이면 끝나야 한다. 그 구분은 **블록 구조**를 알아야 나온다.

⚠ 실측 사례 `ED1SCN1:1142`(유저 QA 2026-08-19) — 「…경사스러운 날이니 말이오」로 끝난다.
**원문에도 `。` 가 없다**(`めでたき日なのですから`). 원문만 보면 결함이 아니라 안 잡힌다.

**규칙**(유저 확정 2026-08-19): **다음 블록이 새 이름창을 열면** 이 블록은 그 화자의
마지막 창이다 — 문장 종결 부호로 끝나야 한다. 창이 이어지는 중간은 예외다.

⚠ 이 정의는 **검수가 먼저 검증했다**(2026-08-19) — 거친 검출 38건 중 **20건이 오탐**이었고,
「다음 블록에 이름창이 있는가」로 좁히니 18건이 남았다. 그 좁힘을 여기 기계로 옮긴다.

⚠ **왜 맞춤법 도구에 안 묶었나.** 성격이 반대다 — 이건 **결정적 게이트**(늘 옳고 매번
돌린다)고 맞춤법은 **비결정적 제안**(외부 API·유저 승인)이다. 묶으면 게이트가 네트워크에
매달린다. 「우연히 같은 코드를 묶는 건 DRY 가 아니다」(CLAUDE.md 설계 원칙).

  python3 tools/check_punct.py            # 전 씬 요약
  python3 tools/check_punct.py -v         # 자리마다
  python3 tools/check_punct.py ED1SCN3    # 한 씬
"""

import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from patch_sys_ui import SCN_FILES

sys.path.insert(0, os.path.join(R.ROOT, "..", "..", "shared"))
import glossary as G

# 문장이 끝났다고 볼 꼬리. ⚠ 말줄임(`...`)도 끝이다 — 여운을 남기는 우리 관용이다.
END = (".", "!", "?", "…", "”", "'", "」", ")")

# 🔴 **종결 어미는 우리 문안에서 뽑았다** — 손으로 적으면 반드시 빠뜨린다.
# 온점으로 끝난 블록 **11,442개**의 종결 직전 글자를 세어 20회 이상만 남겼다
# (2026-08-19 실측: 다 2377 · 요 1976 · 까 952 · 지 401 · 야 398 …).
# ⚠ 이게 **오탐을 가르는 축**이다. 「나락의 입」(워프 목록) · 「긁적긁적」 · 「부글 부글」 ·
#   「하하하」 는 끝 글자가 이 집합 밖이라 자연히 빠진다 — 문장이 아니기 때문이다.
#   반대로 「못 보여 줘」 · 「식은 죽 먹기지」 는 종결 어미라 잡힌다.
# ⚠ 목록을 늘리려면 **다시 세어라**(위 방법). 감으로 글자를 더하면 오탐이 는다.
ENDINGS = set("다요까지야네오라어가고군나냐게서아세죠데먼님마자만해든줘니수유소쇼는봐씨")

_NAMES = frozenset(v for cat in ("person", "place") for v in G.table(cat).values())


def _is_name(s):
    """통째로 **정본에 있는 이름**인가 — 지명·이름 플레이트라 문장이 아니다.

    ⚠ 종결 어미만으로는 못 가른다. `베르가`(가) · `루디아`(아) · `라누라`(라) ·
    `사제 바바라`(라) 는 끝 글자가 종결 어미와 겹쳐 그대로 새어 나왔다(실측 2026-08-19).
    고유명사 정본(`shared/glossary`)이 채워진 뒤에야 이 판정이 가능해졌다.
    """
    t = (s or "").strip()
    return bool(t) and t in _NAMES


def _ends_ok(s):
    t = (s or "").rstrip().rstrip("\n").rstrip()
    return bool(t) and t[-1] in END


def _is_sentence(s):
    """문장인가 — **종결 어미로 끝나는가**로 본다(`ENDINGS` 주석).

    씬 파일엔 워프 목록·맵 이름 같은 **낱말 블록**이 섞여 있고, 의성어·웃음소리처럼
    온점을 안 붙이는 자리도 있다. 길이로 자르면(`≤8자`) 긴 워프 목록을 놓친다 —
    실측으로 `ED2SCN2 jp300`(지명 여섯 나열)이 그렇게 샜다.
    """
    t = (s or "").rstrip().rstrip("\n").rstrip()
    return bool(t) and t[-1] in ENDINGS


def scan(scenes=None, verbose=False):
    bad, plate = [], 0
    for scn, _l, _z in SCN_FILES:
        if scenes and scn not in scenes:
            continue
        with redirect_stdout(io.StringIO()):
            rows = [
                (eid, jp, R.render_bytes(c, ctrl=False))
                for _s, eid, jp, c, _t in R.iter_candidates((scn,))
            ]
        hdr = {eid: R.jp_has_header(jp) for eid, jp, _k in rows}
        for i, (eid, _jp, kr) in enumerate(rows):
            if not kr or not kr.strip():
                continue
            nxt = rows[i + 1][0] if i + 1 < len(rows) else None
            # 다음 블록이 **새 이름창을 열면** 여기서 화자가 바뀐다 = 이 창이 마지막이다.
            # 마지막 블록도 마찬가지로 끝나는 자리다.
            if nxt is not None and not hdr.get(nxt):
                continue
            if _is_name(kr) or not _is_sentence(kr):
                plate += 1
                continue
            if not _ends_ok(kr):
                bad.append((scn, eid, kr.replace("\n", " ")[-34:]))
    print(f"  {'✅' if not bad else '⚠'} 화자 바뀌기 전 온점 누락 {len(bad)}곳")
    if verbose:
        for scn, eid, tail in bad:
            print(f"      {scn} jp{eid}: …{tail}")
    if plate:
        print(f"      ℹ 종결 어미가 아니라 뺀 블록 {plate} — 낱말 목록·의성어·웃음")
    return len(bad)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = scan(set(args) if args else None, verbose=bool(args) or "-v" in sys.argv)
    sys.exit(1 if n else 0)
