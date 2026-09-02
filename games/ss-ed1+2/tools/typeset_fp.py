#!/usr/bin/env python3
"""조판 지문 — 이 게임 몫 (`scripts/check/typeset_fingerprint.py` 가 부른다).

## 왜 이 파일이 게임 아래 있나

공용 도구는 「지문을 대조하고 얼린다」만 알고, **「이 게임의 화면 문안을 어떻게 만드나」**는
게임마다 다르다. PS1 은 우리가 개행을 다 넣지만(krwrap 14슬롯) 새턴은 **엔진이 글자 단위로
접어서** 조판기가 아예 다르다 — 그 지식을 공용에 두면 게임 얘기가 공용으로 샌다
(루트 `CLAUDE.md` 「게임 얘기를 이 파일에 쓰지 않는다」).

## 무엇을 재나 — **공용에 닿는 면 전부**

새턴이 `shared/` 에서 쓰는 것은 셋이다. 지문은 그 셋이 흔들리면 전부 운다:

  glossary.table/lookup   이름 정본      → 씬 · UI · 몬스터 · 조우
  text.line_key.key       저본 열쇠      → 씬 (열쇠가 바뀌면 문안이 통째로 갈린다)
  text.josa.josa/batchim  조사           → 조우 문구

⚠ **`shared/text/krwrap` 은 안 쓴다** — 새턴은 엔진이 접는다. 그래서 PS1 지문이 우는
  변경(줄바꿈 규칙)에 새턴은 안 울 수 있고, 그 반대도 마찬가지다. **게임마다 따로 잰다.**

⚠ 지문은 **바이트가 아니라 문안**을 잰다. 자리 배정(migrate·sys_pack)은 안 본다 — 그건
  빌드가 매번 다시 재고 게이트가 따로 잡는다. 여기서 배정까지 재면 원본 여유가 한 칸만
  달라져도 지문이 울어 **아무도 안 보는 알림**이 된다.
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared")
)

import common
import derive_encounters as E
import patch_scn as S
import patch_ui as U
import typeset_scn as T
from glossary import table
from text.line_key import key as line_key


def _h(parts):
    h = hashlib.sha1()
    for p in parts:
        h.update((p if isinstance(p, str) else repr(p)).encode())
        h.update(b"\x01")
    return h.hexdigest()[:12]


def _scenes(mm, out):
    """씬 대사 — 파일마다 한 줄. 저본이 있는 블록을 조판기에 그대로 태운다."""
    canon = S.load_canon(quiet=True)
    names = T._names()
    for path, _lba, _size in common.iso_files(mm):
        if not S.SCN_RE.match(path):
            continue
        got = S.load(path)
        if not got:
            continue
        _base, ents = got
        mine = S.owned_elsewhere(path)
        # ⚠ 주입 `%c` 쌍이 든 블록은 **되살린 원문**으로 조판해야 이름칸이 붙는다.
        #   여기서 빠뜨리면 지문이 그 블록을 안 보게 되고, 공용이 그 조판을 흔들어도
        #   초록불이 뜬다(체크리스트 4-B — 초록불은 「없다」가 아니라 「안 봤다」다).
        sites = S.sites_for(path)
        acc = []
        for e in ents:
            jp = e.get("text", "")
            off = int(e["file_offset"], 16)
            if not jp or off in mine:
                continue
            raw = canon.get(line_key(jp))
            if raw is None:
                continue
            site = sites.get(off)
            if site:
                built, bad = S.canon_of(canon, jp, site), None
            else:
                built, bad = T.typeset(jp, raw, names)
            # ⚠ 실패 사유도 담는다 — 「조판이 되던 게 안 된다」도 조판 변화다
            acc.append(f"{off:x}\x00{bad or built}")
        if acc:
            out[path] = _h(acc)


def _ui(mm, out):
    """UI·시스템 문안 — 표마다 한 줄. `glossary.lookup` 이 여기로 들어온다."""
    _t, _p, cards, _pj, msgs = U.load_canon()
    out["UI/표"] = _h([f"{k}\x00{t}\x00{i}\x00{kr}" for k, t, i, _o, _s, _jp, kr in U.rows()])
    out["UI/이름"] = _h(
        [f"{tb['what']}\x00{jp}\x00{kr}" for tb in U.name_rows(mm) for _o, jp, kr, _p in tb["recs"]]
    )
    out["UI/시스템"] = _h(
        [f"{p}\x00{o:x}\x00{kr}" for p, _l, _s, o, _r, _pre, kr, _ptr in U.sys_rows(mm)]
    )
    out["UI/카드"] = _h([repr(r) for r in U.card_rows(mm, cards)])
    out["UI/메시지"] = _h([repr(r) for r in U.msg_rows(mm, msgs)])
    out["UI/씬머리"] = _h([repr(r) for r in U.scn_rows(mm)])


def _monsters(out):
    """몬스터 이름과 조우 문구 — 이름 정본 + `text.josa` 가 여기로 들어온다."""
    mon = table("monster")
    got = E.monster_names(mon)
    out["몬스터/이름"] = _h([f"{jp}\x00{kr}" for jp, kr in sorted(got.items()) if kr])
    lines = set()
    for path in E.FILES:
        for jp in E.targets(path):
            if not jp.rstrip("\n").endswith(E.SUFFIX):
                continue
            kr, _miss = E.render(jp, mon)
            if kr:
                lines.add(kr)
    out["몬스터/조우"] = _h(sorted(lines))


def fingerprint():
    """`{구역: sha1[:12]}` — 화면에 나갈 문안 전량."""
    out = {}
    _f, mm = common.open_image()
    try:
        _scenes(mm, out)
        _ui(mm, out)
    finally:
        mm.close()
        _f.close()
    _monsters(out)
    return out


if __name__ == "__main__":
    for k, v in fingerprint().items():
        print(f"  {v}  {k}")
