#!/usr/bin/env python3
"""⚠ **게이트 밖 · 정발 배정 시대 진단기**(2026-09-13 실측 — 자체 번역 전환 이후 재검토
없이 남았다). 손으로 돌리는 용도로만 쓴다.

**임자 없는 정발 조각 엔트리**를 센다 — 꼬리 잘림의 가장 흔한 뿌리.

**왜.** 정발은 한 문장을 **여러 엔트리로 갈라** 둔다. 2026-08-11 하루에만 다섯 번 나왔다:

    T_126#33 `이 `      + #34 본문          → jp538 이 `#34` 만 물어 `나라에서…` 로 시작
    T_440#8  `그`       + #9  본문          → jp1107 이 `T_441#5`(`보게 코로는…`)를 물었다
    T_220#30 `…높으신` + #31 `분 이 와 ` + #32 p0 `계시다고 하더군.`
    T_220#33 `아~~ 아~~ ` + #34 `부럽다니까.`
    T_430#12 `…나도 이제 ` + #13 `푹 잘 수 ` + #14 `있게 되었구려.`

⚠ **페이지 구멍(`check_page_holes`)으로는 안 잡힌다.** 그건 한 엔트리 **안**의 `{p}` 페이지를
세는데, 이 부류는 **엔트리 자체가 여럿**이다. 층이 다르다.

찾는 법: **앞 엔트리는 쓰이는데 자기는 아무도 안 쓰고, 텍스트가 짧은 조각**인 엔트리.
문장 종결로 끝나지 않으면(`푹 잘 수 `) 특히 강한 신호다 — 혼자서는 말이 안 되니 반드시
앞뒤와 이어져야 하는 조각이다.

  python3 tools/check_orphan_entries.py            # 전 씬
  python3 tools/check_orphan_entries.py ED1SCN5    # 한 씬
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import check_page_holes as H
import reinsert_kr_pilot as R
from patch_sys_ui import _scn_layout

MAX_FRAG = 24  # 이보다 길면 조각이 아니라 독립 대사로 본다
_SPK = None


def _speakers():
    global _SPK
    if _SPK is None:
        _SPK = set(R._speaker_map().values()) | {"남자", "여자", "노인", "병사", "신부", "아이"}
    return _SPK


_TERM = ".!?…"


def _used_entries(scn):
    """{표: {쓰이는 엔트리 번호}} — 배정이 실제로 무는 자리."""
    used, _loose = H._used(scn)
    out = {}
    for table, eid in used:
        out.setdefault(table, set()).add(eid)
    return out


def scan(scenes=None):
    tot = 0
    for scn, _lba, _size in _scn_layout():
        if scenes and scn not in scenes:
            continue
        rows = []
        for table, eids in sorted(_used_entries(scn).items()):
            pages_cache = {}
            for e in sorted(eids):
                nxt = e + 1
                if nxt in eids:
                    continue
                pg = pages_cache.get(nxt) or H._pages(table, nxt)
                pages_cache[nxt] = pg
                if not pg:
                    continue
                body = re.sub(r"\{/?spk\}|\{n\}|\\x[0-9A-Fa-f]{2}", " ", "".join(pg))
                body = re.sub(r"\s+", " ", body).strip()
                if not body or len(body) > MAX_FRAG:
                    continue
                if not re.search(r"[가-힣]", body):
                    continue
                # ⚠ **화자 이름 조각은 결손이 아니다.** 정발이 `{spk}신부{/spk}` 를 별도
                # 엔트리로 두는 자리가 흔한데 우리는 화자를 따로 처리한다. 첫 전수 188곳 중
                # 대부분이 이것이었다(2026-08-11).
                if body in _speakers():
                    continue
                # ⚠ 상점·정형 블록은 공통 메시지 처리 대상이라 조각이 남는 게 정상이다
                # (유저 확정). SCN5 첫 판정에서 17곳 중 대부분이 이것이었다.
                if H._shop(table, e) or H._shop(table, nxt):
                    continue
                # 종결부호로 안 끝나면 혼자 설 수 없는 조각 = 강한 신호
                rows.append((table, e, nxt, body, body[-1] not in _TERM))
        strong = [r for r in rows if r[4]]
        tot += len(strong)
        print(
            f"  {'✅' if not strong else '⚠'} {scn}: 조각 {len(strong)}곳"
            f" (약한 신호 {len(rows) - len(strong)})"
        )
        for table, e, nxt, body, _s in strong:
            print(f"      {table}#{nxt} {body!r}  ← #{e} 를 무는 블록이 이어야 한다")
    print(
        f"\n{'✅ 임자 없는 조각 없음' if not tot else f'⚠ 임자 없는 조각 {tot}곳'}"
        "\n  ⚠ 조각이 곧 결손은 아니다 — 정발이 PS1 에 없는 문장을 가진 자리도 있다."
        "\n     앞 엔트리를 무는 블록의 JP 원문을 읽고 `chain` 으로 이을지 판정한다."
    )
    return tot


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    sys.exit(1 if scan(set(args) if args else None) else 0)
