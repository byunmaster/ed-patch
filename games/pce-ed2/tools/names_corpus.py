"""공용 이름 검사(`scripts/check/check_names.py`)의 pce-ed2 어댑터 — `(자리, 원문 줄, 우리 줄|None, 갈래)` 를 문안 전체에 대해 낸다.

🔴 이름을 **들지 않는다**(마스터 10-07) — 원본 패키지의 줄과 우리 문안(대사 번역 · 제어 줄 틀 · 정본 조회)을 읽어 짝지어 넘길 뿐이다.
미번역 줄은 None 으로 낸다(분모에 든다). 갈래: `"dialog"` = 대사 창에 흐르는 글(씬 대사 · 상점·수령 문구 · 전투 문구) ·
`"slot"` = 칸에 담긴 이름(지명 라벨 · 몬스터 이름 라벨).

범위(솔직하게): ED2 본편 씬 패키지 13개의 줄(rel 386~1794 + 최종 장면 2690). 시스템 문구 표(뱅크 0x68~, 메뉴·설정·아이템·주문·지명 표)·오프닝/엔딩 자막·스태프롤은
이 어댑터가 안 낸다(스태프롤은 정본 대상이 아니다 — 마스터 10-08 · 자막은 원문 글이 없다).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import battle
import common
import ctrllines
import dialogue
import jptext
import labels
import msgs
import package

TITLE = "eiyuu"
_TAG = re.compile(r"\{[^}]*\}")
_JP = re.compile(r"[぀-ヿ一-鿿]")


def _plain(raw: bytes) -> str:
    return _TAG.sub("", jptext.decode(raw)).replace("\n", "")


def _kr_of_template(tmpl: str) -> str:
    return re.sub(r"\{[@!]\d+\}", "", tmpl).replace("\n", " ").replace("\f", " ")


def _label_kr(line: bytes) -> str | None:
    s = labels.split(line)
    if s is None:
        return None
    return labels.lookup(s[2])


def _battle_kr(line: bytes) -> str | None:
    sp = msgs.split(line, msgs.BATTLE_NAME, set())
    if sp is None:
        return None
    _lead, content, _trail = sp
    tmpl, _n, _m = msgs.template(content, msgs.BATTLE_NAME, set())
    hit = msgs.index().get(msgs.norm(tmpl))
    if hit is None and msgs.norm(tmpl).startswith("{name}"):
        hit = msgs.index().get(msgs.norm(tmpl)[len("{name}") :])
    return None if hit is None else hit[2].replace("\n", " ")


def pairs():
    out = []
    ctab = ctrllines.table()
    for rel in sorted(dialogue.package_chars()):
        po = bytes(common.track_data(rel, 128))
        for a, b in package.chunks(po):
            if po[a : a + 8] == package.SENTINEL:
                continue
            d = package.decode_chunk(po, a, b)[0]
            lines = d.split(b"\x00")
            cand = {li: (spk, txt) for li, _p, spk, txt in dialogue.candidates(rel, a, d)}
            is_battle = battle.is_battle_chunk(d)
            for i, line in enumerate(lines):
                if not line:
                    continue
                jp = _plain(line)
                if not _JP.search(jp):
                    continue
                where = f"{rel}:{a}:{i}"
                kr = _label_kr(line)  # 칸에 담긴 이름이 먼저다(PS1 짝이 붙은 지명 줄도 칸 꼴이 맞다)
                if kr is not None:
                    out.append((where, jp, kr, "slot"))
                    continue
                if i in cand:
                    spk, txt = cand[i]
                    out.append((where, jp, ((spk + " ") if spk else "") + txt.replace("\f", " "), "dialog"))
                    continue
                skel, _c, _h = ctrllines.parse(line)
                t = ctab.get(ctrllines.key_of(skel))
                if t is not None:
                    out.append((where, jp, _kr_of_template(t), "dialog"))
                    continue
                kr = _battle_kr(line) if is_battle else None
                out.append((where, jp, kr, "dialog"))
    return out
